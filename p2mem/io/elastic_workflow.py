"""One file-backed dynamic-elastic workflow for notebook, CLI and tests.

The published tables contain derived quantities and fixed-schema QC fields.
They do not accept interpretive prose or assign lithology. Private LAS and
survey contents are never copied into the published directory.
"""
from __future__ import annotations

import csv
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile

import numpy as np

from p2mem.dynamic_elasticity import (
    ElasticInputError, ElasticPolicy, NONNEGATIVE_NU_BOUND, POSITIVE_BULK_BOUND,
    PROPERTIES, REGIMES, compute_dynamic_elasticity, load_elastic_policy,
)
from p2mem.io.deviation import load_deviation_contract_config, load_deviation_file
from p2mem.io.las import load_file_contract_config, load_las_file
from p2mem.method_eligibility import compute_dynamic_elastic_eligibility
from p2mem.petrophysics import load_petrophysics_eligibility_config
from p2mem.wellframe import assemble_well_frame


WELLS = ('Boreas_1', 'Poseidon_2', 'Poseidon_North_1', 'Proteus_1ST2')
CONFIG_FILES = ('config/dynamic_elasticity.json', 'config/las_curve_contracts.yml',
                'config/deviation_survey_contracts.yml', 'config/petrophysics_eligibility.yml')
CURVES = ('VP_m_s', 'VS_m_s', 'RHOB_kg_m3')
BOOL_FIELDS = ('depth_valid', 'vp_available', 'vs_available', 'rhob_available',
               'vp_in_bounds', 'vs_in_bounds', 'rhob_in_bounds', 'nu_valid',
               'G_valid', 'K_valid', 'E_valid', 'legacy_full_eligible')
FLOAT_FIELDS = ('MD_m', 'TVD_m', 'TVDSS_m', 'vp_vs_ratio', 'nu_stable_diagnostic',
                *PROPERTIES, 'K_velocity_condition_number')
PROFILE_FIELDS = ('well_key', 'sample_index', *FLOAT_FIELDS, *BOOL_FIELDS, 'ratio_regime')
SUMMARY_FIELDS = ('well_key', 'property', 'n_samples', 'n_valid', 'fraction_valid',
                  'min', 'p05', 'median', 'p95', 'max', 'first_MD_m', 'last_MD_m')
ARTIFACTS = tuple(f'{w}_elastic.csv' for w in WELLS) + ('elastic_summary.csv',) + tuple(
    f'{w}_elastic_qc.png' for w in WELLS)
MANIFEST_NAME = 'elastic_manifest.json'
METHODS = {
    'assurance': 'Tier C; dynamic isotropic screening estimates; uncalibrated',
    'G_Pa': 'rho_kg_m3 * Vs_m_s**2',
    'K_Pa': 'rho_kg_m3 * (Vp_m_s**2 - (4/3)*Vs_m_s**2)',
    'nu': '(r**2 - 2)/(2*(r**2 - 1)); r=Vp/Vs',
    'E_Pa': '9*K*G/(3*K+G)',
    'primary_ratio_screen': 'sqrt(2) <= r <= 4; inherited project policy, not physical possibility',
    'stable_negative_nu': 'sqrt(4/3) < r < sqrt(2); diagnostic only; primary nu/K/E withheld',
    'G_coverage': 'Vs and RHOB in bounds at mapped depth; independent of Vp availability',
    'nu_coverage': 'Vp and Vs in bounds at mapped depth and primary ratio screen; no RHOB requirement',
    'K_E_coverage': 'nu coverage plus RHOB in bounds; exact inherited full eligibility mask',
    'condition_number': '(2*r**2 + 8/3)/(r**2 - 4/3); first-order worst-case relative K sensitivity to equal independent fractional Vp/Vs perturbations, fixed density; not a confidence interval',
    'missing_data': 'No interpolation, gap bridging, clipping, resampling or source-array modification',
    'static_properties': 'Not estimated; no calibrated dynamic-to-static relationship',
    'uncertainty': 'Input measurement uncertainty, anisotropy and frequency/strain dependence are unquantified; no statistical error bars or calibration claim',
    'classification': 'No lithology or strength classification fields are generated',
    'sources': [
        {'title': 'MIT Introduction to Seismology, wave-speed relations, p. 2',
         'url': 'https://ocw.mit.edu/courses/12-510-introduction-to-seismology-spring-2010/d77d74b5471755994a9dae8a19eddba0_lec1.pdf'},
        {'title': 'MIT Structural Mechanics, Note L.4, sections 2.1-2.2',
         'url': 'https://ocw.mit.edu/courses/22-314j-structural-mechanics-in-nuclear-power-technology-fall-2006/137e6469e37e9d347b7b3b69292da2f3_l4_2.pdf'},
    ],
}


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _require(condition, message):
    if not condition:
        raise ElasticInputError(message)


def _json_write(path, obj):
    with Path(path).open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + '\n')


def _scalar(v):
    if isinstance(v, (bool, np.bool_)):
        return 'true' if v else 'false'
    if isinstance(v, (float, np.floating)):
        return repr(float(v)) if math.isfinite(v) else ''
    return str(v)


def _write_csv(path, fields, rows):
    with Path(path).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n', extrasaction='raise')
        writer.writeheader()
        for row in rows:
            _require(set(row) == set(fields), 'CSV row schema mismatch')
            writer.writerow({k: _scalar(v) for k, v in row.items()})


def summarize(well, data):
    rows = []
    for prop in PROPERTIES:
        arr = data[prop]
        keep = np.isfinite(arr)
        vals = arr[keep]
        stats = [float(x) for x in np.percentile(vals, [0, 5, 50, 95, 100])] if len(vals) else [None]*5
        rows.append(dict(zip(SUMMARY_FIELDS, [well, prop, len(arr), len(vals),
            len(vals)/len(arr) if len(arr) else 0.0, *stats,
            float(data['MD_m'][keep][0]) if len(vals) else None,
            float(data['MD_m'][keep][-1]) if len(vals) else None])))
    return rows


def _counts(data):
    return {**{k: int(np.count_nonzero(data[k])) for k in BOOL_FIELDS},
            **{r: int(np.count_nonzero(data['ratio_regime'] == r)) for r in REGIMES},
            'n_samples': len(data['MD_m'])}


def run_elastic_workflow(project_root, las_dir, survey_dir):
    """Read all four approved wells through locked loaders; any failure stops publication."""
    root = Path(project_root)
    policy = load_elastic_policy(root / CONFIG_FILES[0])
    _require(policy == ElasticPolicy(), 'Published Increment 9 requires the declared inherited bounds')
    las_contracts = load_file_contract_config(str(root / CONFIG_FILES[1]))
    dev_contracts = load_deviation_contract_config(str(root / CONFIG_FILES[2]))
    old_config = load_petrophysics_eligibility_config(str(root / CONFIG_FILES[3]))
    runs = {}
    for well in WELLS:
        las_path = Path(las_dir) / f'{well}_logs.las'
        survey_path = Path(survey_dir) / (well.replace('_', ' ') + '_dev.txt')
        # Explicit source hashes are retained alongside the locked semantic contracts.
        hashes_before = [sha256(las_path), sha256(survey_path)]
        las = load_las_file(str(las_path), las_contracts[las_path.name])
        survey = load_deviation_file(str(survey_path), dev_contracts[survey_path.name])
        frame = assemble_well_frame(well, las, survey, las_path=str(las_path), survey_path=str(survey_path))
        _require(hashes_before == [sha256(las_path), sha256(survey_path)], 'Source changed while reading')
        data = dict(compute_dynamic_elasticity(*(frame.values_or_none(k) for k in CURVES),
                                             frame.depth_valid_mask, policy=policy))
        _require(np.array_equal(data['legacy_full_eligible'], compute_dynamic_elastic_eligibility(frame, old_config).mask),
                 'Increment 6 full eligibility comparison failed')
        _require(frame.n_extrapolated == 0, 'Extrapolated depth is prohibited')
        data.update(MD_m=frame.MD_m.copy(), TVD_m=frame.TVD_m.copy(), TVDSS_m=frame.TVDSS_m.copy())
        curves = {}
        for canonical in CURVES:
            slot = frame.curve(canonical)
            curves[canonical] = None if slot is None else {k: getattr(slot, k) for k in (
                'raw_mnemonic', 'raw_unit', 'canonical_unit', 'conversion_function', 'source_filename', 'evidence_class')}
        provenance = {
            'las_filename': las_path.name, 'las_sha256': hashes_before[0],
            'survey_filename': survey_path.name, 'survey_sha256': hashes_before[1],
            'curves': curves, 'depth_basis_used': frame.depth_basis_used,
            'datum_elevation_m': frame.datum_elevation_m,
            'n_depth_unmapped': frame.n_depth_unmapped, 'n_extrapolated': frame.n_extrapolated,
        }
        runs[well] = {'data': data, 'provenance': provenance}
    return {'runs': runs, 'config_sha256': {p: sha256(root/p) for p in CONFIG_FILES}}


def _profile_rows(well, data):
    for i in range(len(data['MD_m'])):
        yield {'well_key': well, 'sample_index': i,
               **{k: data[k][i] for k in (*FLOAT_FIELDS, *BOOL_FIELDS, 'ratio_regime')}}


def _plot(well, data, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with plt.rc_context({'font.size': 9, 'savefig.dpi': 150, 'font.family': 'DejaVu Sans'}):
        fig, axes = plt.subplots(1, 4, figsize=(12, 6), sharey=True)
        try:
            for ax, prop, color in zip(axes, PROPERTIES, ('#365d8d', '#238b8d', '#725f9e', '#ba6a32')):
                # Full arrays retain NaNs: plotted lines never join missing samples.
                ax.plot(data[prop], data['TVDSS_m'], color=color, linewidth=.7)
                ax.set_xlabel(prop.replace('_dynamic', '').replace('_', ' '))
                ax.grid(alpha=.2)
                count = np.isfinite(data[prop]).sum()
                ax.set_title(f'{count:,} / {len(data[prop]):,} samples', fontsize=9)
            axes[0].axvline(0, color='gray', linewidth=.6)
            axes[0].set_ylabel('TVDSS (m; positive down from mean sea level)')
            axes[0].invert_yaxis()
            fig.suptitle(well.replace('_', ' ') + ' | Dynamic isotropic elastic estimates', fontsize=13)
            fig.text(.5, .02, 'Screening only, uncalibrated. Blank intervals are withheld; no static conversion.',
                     ha='center', fontsize=9)
            fig.tight_layout(rect=(0, .05, 1, .94))
            fig.savefig(path, metadata={'Software': 'p2mem Increment 9'})
        finally:
            plt.close(fig)


def _write_run(run, stage):
    _require(set(run) == {'runs', 'config_sha256'} and set(run['runs']) == set(WELLS), 'Run schema mismatch')
    manifest = {'schema_version': '9.0.0', 'methods': METHODS, 'policy': asdict(ElasticPolicy()),
                'config_sha256': run['config_sha256'], 'wells': {}, 'artifacts': {}}
    all_stats = []
    for well in WELLS:
        item = run['runs'][well]
        _require(set(item) == {'data', 'provenance'}, 'Unexpected well-run field')
        data = item['data']
        _require(set(data) == set(FLOAT_FIELDS + BOOL_FIELDS + ('ratio_regime',)), 'Unexpected profile field')
        _write_csv(stage / f'{well}_elastic.csv', PROFILE_FIELDS, _profile_rows(well, data))
        stats = summarize(well, data)
        all_stats.extend(stats)
        manifest['wells'][well] = {'counts': _counts(data), 'statistics': stats, 'provenance': item['provenance']}
        _plot(well, data, stage / f'{well}_elastic_qc.png')
    _write_csv(stage/'elastic_summary.csv', SUMMARY_FIELDS,
               ({k: ('' if v is None else v) for k, v in row.items()} for row in all_stats))
    manifest['artifacts'] = {name: sha256(stage/name) for name in ARTIFACTS}
    _json_write(stage/MANIFEST_NAME, manifest)


def publish_elastic_outputs(run, destination):
    """Validate a complete staged generation, then swap directories with rollback.

    destination must be a dedicated output directory. Concurrent writers are
    rejected by an exclusive sibling lock. Existing outputs remain intact if
    serialization, plotting, validation or publication fails.
    """
    dest = Path(destination).absolute()
    _require(not dest.is_symlink(), 'Output destination may not be a symlink')
    if dest.exists():
        _require(dest.is_dir(), 'Output destination must be a directory')
        validate_elastic_outputs(dest)  # Never replace an unrelated directory.
    dest.parent.mkdir(parents=True, exist_ok=True)
    lock = dest.with_name(dest.name + '.lock')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ElasticInputError('Another publisher holds the output lock') from exc
    os.close(fd)
    stage = None
    backup = None
    try:
        stage = Path(tempfile.mkdtemp(prefix='.'+dest.name+'-stage-', dir=dest.parent))
        _write_run(run, stage)
        validate_elastic_outputs(stage)
        if dest.exists():
            backup = stage.with_name(stage.name + '-backup')
            os.replace(dest, backup)
        try:
            os.replace(stage, dest)
        except BaseException:
            if backup is not None:
                os.replace(backup, dest)
                backup = None
            raise
        if backup is not None:
            shutil.rmtree(backup)
            backup = None
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)
        lock.unlink(missing_ok=True)
    return dest


def _read_profile(path, well):
    with Path(path).open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        _require(reader.fieldnames == list(PROFILE_FIELDS), 'Profile schema mismatch')
        rows = list(reader)
    data = {}
    for i, row in enumerate(rows):
        _require(set(row) == set(PROFILE_FIELDS) and None not in row.values(), 'Malformed profile row')
        _require(row['well_key'] == well and row['sample_index'] == str(i), 'Well/sample order mismatch')
    for k in BOOL_FIELDS:
        _require(all(row[k] in ('true', 'false') for row in rows), 'Invalid serialized boolean')
        data[k] = np.array([row[k] == 'true' for row in rows], dtype=bool)
    for k in FLOAT_FIELDS:
        vals = []
        for row in rows:
            value = np.nan if row[k] == '' else float(row[k])
            _require(row[k] == '' or math.isfinite(value), 'Nonfinite serialized number')
            vals.append(value)
        data[k] = np.asarray(vals, dtype=float)
    data['ratio_regime'] = np.asarray([row['ratio_regime'] for row in rows], dtype=str)
    _validate_profile(data)
    return data


def _same_mask(a, b, message):
    _require(np.array_equal(a, b), message)


def _close(a, b, message):
    _require(np.allclose(a, b, rtol=5e-13, atol=5e-14, equal_nan=True), message)


def _validate_profile(d):
    _require(np.isfinite(d['MD_m']).all() and (np.diff(d['MD_m']) > 0).all(), 'Invalid MD order')
    depth = d['depth_valid']
    _same_mask(np.isfinite(d['TVD_m']) & np.isfinite(d['TVDSS_m']), depth, 'Depth validity mismatch')
    if depth.any():
        _require((np.diff(d['TVD_m'][depth]) >= 0).all(), 'TVD reverses')
    for name in ('vp', 'vs', 'rhob'):
        _require(not (d[name+'_in_bounds'] & ~d[name+'_available']).any(), 'Availability contradicts bounds')
    both = d['vp_in_bounds'] & d['vs_in_bounds']
    r = d['vp_vs_ratio']
    _same_mask(np.isfinite(r), both, 'Ratio availability mismatch')
    expected = np.full(len(r), 'missing_velocity', dtype='<U25')
    expected[d['vp_available'] & d['vs_available'] & ~both] = 'velocity_out_of_bounds'
    expected[both & (r <= POSITIVE_BULK_BOUND)] = 'nonpositive_bulk_ratio'
    expected[both & (r > POSITIVE_BULK_BOUND) & (r < NONNEGATIVE_NU_BOUND)] = 'negative_poisson_ratio'
    expected[both & (r > 4)] = 'ratio_above_policy'
    screen = both & (r >= NONNEGATIVE_NU_BOUND) & (r <= 4)
    expected[screen] = 'passes_ratio_screen'
    _same_mask(d['ratio_regime'], expected, 'Ratio regime mismatch')
    nu_ok = depth & screen
    g_ok = depth & d['vs_in_bounds'] & d['rhob_in_bounds']
    full = nu_ok & d['rhob_in_bounds']
    for k, mask in (('nu_valid', nu_ok), ('G_valid', g_ok), ('K_valid', full),
                    ('E_valid', full), ('legacy_full_eligible', full)):
        _same_mask(d[k], mask, f'{k} coverage mismatch')
    for prop, mask in zip(PROPERTIES, (nu_ok, g_ok, full, full)):
        _same_mask(np.isfinite(d[prop]), mask, f'{prop} missingness mismatch')
    for prop in PROPERTIES[1:]:
        _require((d[prop][np.isfinite(d[prop])] > 0).all(), 'Nonpositive primary modulus')
    stable = both & depth & (r > POSITIVE_BULK_BOUND) & (r <= 4)
    diag = np.full(len(r), np.nan)
    q = r[stable]**2
    diag[stable] = (q-2)/(2*(q-1))
    _close(d['nu_stable_diagnostic'], diag, 'Poisson diagnostic equation mismatch')
    primary = np.full(len(r), np.nan)
    primary[nu_ok] = diag[nu_ok]
    _close(d['nu_dynamic'], primary, 'Primary Poisson equation mismatch')
    _close(d['K_dynamic_GPa'][full], d['G_dynamic_GPa'][full]*(r[full]**2-4/3), 'K/G ratio equation mismatch')
    _close(d['E_dynamic_GPa'][full], 2*d['G_dynamic_GPa'][full]*(1+d['nu_dynamic'][full]), 'Young modulus equation mismatch')
    condition = np.full(len(r), np.nan)
    q = r[nu_ok]**2
    condition[nu_ok] = (2*q+8/3)/(q-4/3)
    _close(d['K_velocity_condition_number'], condition, 'Condition-number equation mismatch')


def validate_elastic_outputs(directory):
    """Verify exact artifact set, hashes, actual serialized records and derived statistics.

    This checks internal consistency of packaged results. Reproducing the
    measurements additionally requires the private input files and workflow.
    """
    root = Path(directory)
    try:
        _require({p.name for p in root.iterdir()} == set(ARTIFACTS + (MANIFEST_NAME,)), 'Artifact inventory mismatch')
        _require(all(p.is_file() and not p.is_symlink() for p in root.iterdir()), 'Invalid artifact type')
        from p2mem.dynamic_elasticity import _unique_object
        m = json.loads((root/MANIFEST_NAME).read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
        _require(set(m) == {'schema_version','methods','policy','config_sha256','wells','artifacts'}, 'Manifest schema mismatch')
        _require(m['schema_version'] == '9.0.0' and m['methods'] == METHODS and m['policy'] == asdict(ElasticPolicy()), 'Method/policy mismatch')
        _require(set(m['wells']) == set(WELLS) and set(m['config_sha256']) == set(CONFIG_FILES), 'Well/config inventory mismatch')
        _require(set(m['artifacts']) == set(ARTIFACTS), 'Manifest artifact inventory mismatch')
        for name in ARTIFACTS:
            _require(sha256(root/name) == m['artifacts'][name], f'Artifact hash mismatch: {name}')
        stats = []
        for well in WELLS:
            data = _read_profile(root/f'{well}_elastic.csv', well)
            item = m['wells'][well]
            _require(set(item) == {'counts', 'statistics', 'provenance'}, 'Well manifest schema mismatch')
            _require(all(type(v) is int and v >= 0 for v in item['counts'].values()), 'Counts must be nonnegative integers')
            _require(item['counts'] == _counts(data), 'Counts differ from serialized records')
            computed = summarize(well, data)
            for s in item['statistics']:
                _require(type(s['n_samples']) is int and type(s['n_valid']) is int, 'Statistics counts must be integers')
                for key in set(SUMMARY_FIELDS)-{'well_key','property','n_samples','n_valid'}:
                    value=s[key]
                    _require(value is None or (type(value) in (int,float) and math.isfinite(value)), 'Invalid summary number')
            _require(item['statistics'] == computed, 'Statistics differ from serialized records')
            stats.extend(computed)
            provenance = item['provenance']
            _require(set(provenance) == {'las_filename','las_sha256','survey_filename','survey_sha256','curves',
                'depth_basis_used','datum_elevation_m','n_depth_unmapped','n_extrapolated'}, 'Provenance schema mismatch')
            _require(provenance['las_filename'] == well+'_logs.las' and
                provenance['survey_filename'] == well.replace('_',' ')+'_dev.txt', 'Source identity mismatch')
            _require(provenance['n_extrapolated'] == 0 and provenance['n_depth_unmapped'] == int((~data['depth_valid']).sum()), 'Mapping count mismatch')
            _require(all(type(provenance[k]) is int for k in ('n_extrapolated','n_depth_unmapped')), 'Mapping counts must be integers')
            _require(provenance['depth_basis_used']=='petrel_source_trace', 'Unapproved depth basis')
            _require(set(provenance['curves']) == set(CURVES), 'Curve provenance inventory mismatch')
            for canonical, slot in provenance['curves'].items():
                _require(slot is None or set(slot) == {'raw_mnemonic','raw_unit','canonical_unit','conversion_function','source_filename','evidence_class'}, 'Curve provenance schema mismatch')
                available = {'VP_m_s':'vp_available','VS_m_s':'vs_available','RHOB_kg_m3':'rhob_available'}[canonical]
                if slot is None:
                    _require(not data[available].any(), 'Missing curve provenance contradicts available samples')
                    continue
                density=canonical=='RHOB_kg_m3'
                _require(slot['source_filename']==provenance['las_filename'] and slot['evidence_class']=='measured', 'Curve source/evidence mismatch')
                _require((slot['raw_unit'],slot['canonical_unit'],slot['conversion_function']) ==
                         (('g/cc','kg/m3','gcc_to_kgm3') if density else ('us/ft','m/s','us_per_ft_to_m_per_s')), 'Curve conversion provenance mismatch')
                _require(isinstance(slot['raw_mnemonic'],str) and re.fullmatch(
                    r'(?:\(empty mnemonic, ordinal [1-9][0-9]*\)|[A-Za-z][A-Za-z0-9_]*)',slot['raw_mnemonic']) is not None,
                    'Invalid raw mnemonic field')
            datum = provenance['datum_elevation_m']
            _require(type(datum) in (int, float) and math.isfinite(datum), 'Invalid datum')
            keep = data['depth_valid']
            _close(data['TVD_m'][keep]-data['TVDSS_m'][keep], datum, 'Depth datum identity mismatch')
            for digest in [provenance['las_sha256'], provenance['survey_sha256'], *m['config_sha256'].values()]:
                _require(isinstance(digest,str) and len(digest)==64 and all(c in '0123456789abcdef' for c in digest), 'Malformed provenance checksum')
        with (root/'elastic_summary.csv').open(encoding='utf-8', newline='') as stream:
            reader = csv.DictReader(stream)
            _require(reader.fieldnames == list(SUMMARY_FIELDS), 'Summary schema mismatch')
            actual = list(reader)
        expected = [{k: '' if v is None else _scalar(v) for k,v in row.items()} for row in stats]
        _require(actual == expected, 'Summary differs from profiles')
        return m
    except (OSError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ElasticInputError):
            raise
        raise ElasticInputError('Malformed elastic outputs') from exc
