"""Publication tests exercise the files actually written, including failures."""
import copy
import csv
import json
from pathlib import Path

import numpy as np
import pytest

from p2mem.dynamic_elasticity import ElasticInputError, compute_dynamic_elasticity
from p2mem.io import elastic_workflow as ew


def synthetic_run():
    runs = {}
    for well in ew.WELLS:
        data = dict(compute_dynamic_elasticity(
            [4000,4000,np.nan,2500,2000,4000], [2000]*6,
            [2500, np.nan, 2500, 2500,2500,2500], [True]*5+[False]))
        data.update(MD_m=np.arange(6.)+100, TVD_m=np.array([100.,101.,102.,103.,104.,np.nan]),
                    TVDSS_m=np.array([80.,81.,82.,83.,84.,np.nan]))
        provenance = dict(las_filename=well+'_logs.las', las_sha256='a'*64,
            survey_filename=well.replace('_',' ')+'_dev.txt', survey_sha256='b'*64,
            curves={c: dict(raw_mnemonic='RHOB' if c=='RHOB_kg_m3' else 'DT',
                           raw_unit='g/cc' if c=='RHOB_kg_m3' else 'us/ft',
                           canonical_unit='kg/m3' if c=='RHOB_kg_m3' else 'm/s',
                           conversion_function='gcc_to_kgm3' if c=='RHOB_kg_m3' else 'us_per_ft_to_m_per_s',
                           source_filename=well+'_logs.las',evidence_class='measured') for c in ew.CURVES},
            depth_basis_used='petrel_source_trace',
            datum_elevation_m=20.0, n_depth_unmapped=1, n_extrapolated=0)
        runs[well] = dict(data=data, provenance=provenance)
    return dict(runs=runs, config_sha256={p:'c'*64 for p in ew.CONFIG_FILES})


@pytest.fixture
def fast_plots(monkeypatch):
    # Real rendering is verified in the explicit plotting test and clean-room run.
    monkeypatch.setattr(ew, '_plot', lambda well,data,path: Path(path).write_bytes(b'synthetic plot'))


@pytest.fixture
def published(tmp_path, fast_plots):
    dest = tmp_path/'outputs'
    ew.publish_elastic_outputs(synthetic_run(), dest)
    return dest


def snapshot(root):
    return {p.name:p.read_bytes() for p in root.iterdir()}


def rewrite_profile(root, mutation):
    name = ew.WELLS[0]+'_elastic.csv'
    with (root/name).open(newline='') as f:
        reader=csv.DictReader(f)
        rows=list(reader)
    mutation(rows)
    with (root/name).open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=ew.PROFILE_FIELDS,lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    # Updating the hash deliberately demonstrates validation beyond checksums.
    m=json.loads((root/ew.MANIFEST_NAME).read_text())
    m['artifacts'][name]=ew.sha256(root/name)
    ew._json_write(root/ew.MANIFEST_NAME,m)


def test_exact_roundtrip_counts_diagnostics_and_nullable_statistics(published):
    m=ew.validate_elastic_outputs(published)
    c=m['wells'][ew.WELLS[0]]['counts']
    assert c['n_samples']==6 and c['G_valid']==4 and c['nu_valid']==2
    assert c['E_valid']==1 and c['nonpositive_bulk_ratio']==1 and c['negative_poisson_ratio']==1
    with (published/'elastic_summary.csv').open() as f:
        assert len(list(csv.DictReader(f)))==16


@pytest.mark.parametrize('field,value', [
    ('well_key','unapproved'), ('sample_index','20'), ('MD_m','NaN'), ('MD_m','inf'),
    ('nu_valid','yes'), ('nu_valid','false'), ('legacy_full_eligible','false'),
    ('G_dynamic_GPa','11'), ('K_dynamic_GPa','1'), ('E_dynamic_GPa','12'),
    ('nu_dynamic','0.2'), ('nu_stable_diagnostic','0.1'),
    ('ratio_regime','negative_poisson_ratio'), ('K_velocity_condition_number','0'),
    ('vp_available','false'), ('depth_valid','false'),
])
def test_actual_serialized_record_mutations_rejected(published,field,value):
    rewrite_profile(published,lambda rows:rows[0].__setitem__(field,value))
    with pytest.raises(ElasticInputError):
        ew.validate_elastic_outputs(published)


def test_absent_value_cannot_be_fabricated(published):
    rewrite_profile(published,lambda rows:rows[1].__setitem__('E_dynamic_GPa','20'))
    with pytest.raises(ElasticInputError):
        ew.validate_elastic_outputs(published)


@pytest.mark.parametrize('kind',['count','stats','methods','policy','unknown','datum','source','hash','boolean_count','float_count','curve_missing','curve_unit'])
def test_manifest_mutations_rejected(published,kind):
    path=published/ew.MANIFEST_NAME
    m=json.loads(path.read_text())
    w=m['wells'][ew.WELLS[0]]
    if kind=='count': w['counts']['E_valid']=123
    elif kind=='stats': w['statistics'][0]['median']=99
    elif kind=='methods': m['methods']['assurance']='calibrated'
    elif kind=='policy': m['policy']['ratio_max']=5
    elif kind=='unknown': m['unknown']='new claim'
    elif kind=='datum': w['provenance']['datum_elevation_m']=21
    elif kind=='source': w['provenance']['las_filename']='another.las'
    elif kind=='hash': w['provenance']['las_sha256']='unknown'
    elif kind=='boolean_count': w['counts']['E_valid']=True
    elif kind=='float_count': w['counts']['E_valid']=1.0
    elif kind=='curve_missing': w['provenance']['curves']['VP_m_s']=None
    elif kind=='curve_unit': w['provenance']['curves']['VP_m_s']['raw_unit']='m/s'
    ew._json_write(path,m)
    with pytest.raises(ElasticInputError):
        ew.validate_elastic_outputs(published)


def test_unlisted_file_is_rejected(published):
    (published/'extra.txt').write_text('unexpected')
    with pytest.raises(ElasticInputError):
        ew.validate_elastic_outputs(published)


def test_summary_is_validated_even_if_hash_updated(published):
    p=published/'elastic_summary.csv'
    p.write_text(p.read_text().replace('nu_dynamic','invented_property'))
    m=json.loads((published/ew.MANIFEST_NAME).read_text())
    m['artifacts'][p.name]=ew.sha256(p)
    ew._json_write(published/ew.MANIFEST_NAME,m)
    with pytest.raises(ElasticInputError):
        ew.validate_elastic_outputs(published)


def test_determinism_across_roots(published,tmp_path):
    other=tmp_path/'other'
    ew.publish_elastic_outputs(synthetic_run(),other)
    assert snapshot(other)==snapshot(published)


@pytest.mark.parametrize('phase',['serialize','plot','validate','stage','publish'])
def test_failure_preserves_existing_bundle_and_no_residue(published,monkeypatch,phase):
    before=snapshot(published)
    def fail(*args,**kwargs): raise OSError('injected failure')
    if phase=='serialize': monkeypatch.setattr(ew,'_write_csv',fail)
    elif phase=='plot': monkeypatch.setattr(ew,'_plot',fail)
    elif phase=='stage': monkeypatch.setattr(ew.tempfile,'mkdtemp',fail)
    elif phase=='validate':
        original=ew.validate_elastic_outputs
        def check(path):
            if Path(path)==published: return original(path)
            raise ElasticInputError('injected validation failure')
        monkeypatch.setattr(ew,'validate_elastic_outputs',check)
    else:
        original=ew.os.replace
        count=[0]
        def replace(src,dst):
            count[0]+=1
            if count[0]==2: raise OSError('injected directory publication failure')
            return original(src,dst)
        monkeypatch.setattr(ew.os,'replace',replace)
    with pytest.raises((OSError,ElasticInputError)):
        ew.publish_elastic_outputs(synthetic_run(),published)
    assert snapshot(published)==before
    assert {p.name for p in published.parent.iterdir()}=={published.name}


def test_existing_unrelated_folder_is_never_overwritten(tmp_path,fast_plots):
    dest=tmp_path/'unrelated'
    dest.mkdir()
    (dest/'private.txt').write_text('preserve')
    with pytest.raises(ElasticInputError):
        ew.publish_elastic_outputs(synthetic_run(),dest)
    assert (dest/'private.txt').read_text()=='preserve'


def test_concurrent_publication_lock(published):
    lock=published.with_name(published.name+'.lock')
    lock.touch()
    with pytest.raises(ElasticInputError,match='lock'):
        ew.publish_elastic_outputs(synthetic_run(),published)


def test_regeneration_does_not_modify_input_arrays(published):
    run=synthetic_run()
    before=copy.deepcopy(run)
    ew.publish_elastic_outputs(run,published)
    for well in ew.WELLS:
        for key,value in run['runs'][well]['data'].items():
            np.testing.assert_array_equal(value,before['runs'][well]['data'][key])


def test_actual_png_render_and_close(tmp_path):
    import matplotlib.pyplot as plt
    before=plt.get_fignums()
    well=ew.WELLS[0]
    p=tmp_path/'figure.png'
    ew._plot(well,synthetic_run()['runs'][well]['data'],p)
    assert p.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    assert plt.get_fignums()==before


def test_all_missing_curves_remain_empty_not_zero(tmp_path,fast_plots):
    run=synthetic_run()
    for item in run['runs'].values():
        item['data'].update(compute_dynamic_elasticity(None,None,None,[True]*5+[False]))
    dest=tmp_path/'empty'
    ew.publish_elastic_outputs(run,dest)
    m=ew.validate_elastic_outputs(dest)
    for item in m['wells'].values():
        assert all(s['n_valid']==0 and s['median'] is None for s in item['statistics'])


def test_unknown_profile_field_blocks_publication(tmp_path,fast_plots):
    run=synthetic_run()
    run['runs'][ew.WELLS[0]]['data']['interpretation']=['arbitrary prose']*6
    with pytest.raises(ElasticInputError):
        ew.publish_elastic_outputs(run,tmp_path/'out')
