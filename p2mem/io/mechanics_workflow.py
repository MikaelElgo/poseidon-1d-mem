"""Offline reproduction of conditional mechanics from verified Increment 9 outputs.

Four reference profiles retain every original sample. Seven one-at-a-time
parameter cases are represented by the config and numerical summary tables;
evaluate_mechanics reconstructs any full scenario profile without guessing.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from itertools import zip_longest
import numpy as np
from p2mem.mechanics import (MechanicsInputError, PROPERTIES, STATUS, default_config,
                            evaluate_mechanics, load_config, require, unique_object)
from p2mem.io.elastic_workflow import WELLS, validate_elastic_outputs

CONFIG = 'config/mechanics_scenarios.json'
REGISTRY_PATH = 'config/mechanics_correlations.json'
BASELINE_LEDGER = 'INCREMENT_09_SHA256SUMS.txt'
ELASTIC_DIR = 'outputs/09_dynamic_elasticity'
TOPS_PATH = 'outputs/05_formation_tops/top_survey_corrected_markers.csv'
DESTINATION = 'outputs/10_static_mechanics_strength'
MANIFEST = 'mechanics_manifest.json'
NUMBERS = ('sample_index', 'MD_m', 'TVD_m', 'TVDSS_m', 'E_dynamic_GPa', *PROPERTIES)
PROFILE_FIELDS = ('well_key', 'case_id', *NUMBERS, 'upstream_dynamic_valid',
                  'scenario_numeric_supported', 'field_mechanics_eligible', 'status',
                  'evidence_class', 'calibration_status', 'material_hypothesis')
SUMMARY_FIELDS = ('well_key', 'case_id', 'property', 'n_original', 'n_supported',
                  'fraction_supported', 'min', 'median', 'max', 'median_change_from_reference',
                  'evidence_class')
COVERAGE_FIELDS = ('well_key','n_original','n_upstream_dynamic','n_analogue_numeric',
                  'fraction_original_analogue_numeric','n_field_eligible','n_outside_predictor_span',
                  'n_missing_dynamic','source_support_meaning')
FORMATION_FIELDS = ('well_key','case_id','top_marker','base_marker','top_MD_m','base_MD_m',
                    'top_TVDSS_m','base_TVDSS_m','n_original','n_supported','fraction_supported',
                    'property','min','median','max','depth_basis','well_identity_status','interpretation')
METHOD_FIELDS = ('well_key','method_id','implemented','field_eligible','purpose','blocker')
DATA_FILES = tuple(w+'_mechanics.csv' for w in WELLS) + (
    'mechanics_summary.csv','mechanics_coverage.csv','formation_interval_summary.csv',
    'method_applicability.csv')
FIGURES = tuple(w+'_mechanics_qc.png' for w in WELLS)
ARTIFACTS = DATA_FILES + FIGURES
EVIDENCE = 'derived_under_unverified_analogue_and_parameter_assumptions'
CALIBRATION = 'uncalibrated'
MATERIAL = 'sandstone_analogue_not_interpreted_lithology'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def registry():
    return {
      'schema_version':'10.0.0',
      'static':{'id':'mahdi_alrazzaq_2024_eq8','formula':'Estatic_GPa = 0.3655 * Edyn_GPa ** 1.0959',
         'source':'Mahdi and Alrazzaq (2024), Iraqi Geological Journal 57(2B), 77-88, Eq. 8 p.81; Table 2 p.79',
         'url':'https://igj-iraq.org/igj/index.php/igj/article/download/2423/2031/27811',
         'doi':'10.46717/igj.57.2B.5ms-2024-8-15',
         'input_span_GPa':[17.90,43.45], 'span_meaning':'reported source predictor range, not transferable validity',
         'population':'Rumaila Nahr Umr sandstone; 17 core measurements; 663 log points',
         'review':'Exact Eq. 8 and Table 2 inspected. Surrounding paper contains editorial inconsistencies; no claim of independent source validation.',
         'field_eligible':False,'reason':'Poseidon material identity, conditions and calibration transfer unproven'},
      'strength':{'id':'chang_2006_table1_eq8','formula':'UCS_MPa = 46.2 * exp(0.027 * Estatic_GPa)',
         'source':'Chang, Zoback and Khaksar (2006), JPSE 51, 223-237, Table 1 Eq. 8 p.227; static E discussion on same page',
         'url':"https://pangea.stanford.edu/departments/geophysics/dropbox/STRESS/publications/MDZ%20PDF's/2006/2006_Empirical_relations_between_rock_strenght.pdf",
         'doi':'10.1016/j.petrol.2006.01.003',
         'population':'sandstone relation evaluated in paper; originating region/reference not identified in Table 1',
         'numeric_support':'limited here to the output span of the selected static experiment; not an empirical validity domain',
         'field_eligible':False,'reason':'unproven material, static transfer, saturation and originating calibration'},
      'isotropic':{'formulae':['G_GPa = E_GPa / (2*(1+nu))','K_GPa = E_GPa / (3*(1-2*nu))'],
         'source':'isotropic linear elasticity identities; same constitutive family as Increment 9',
         'url':'https://ocw.mit.edu/courses/22-314j-structural-mechanics-in-nuclear-power-technology-fall-2006/137e6469e37e9d347b7b3b69292da2f3_l4_2.pdf'},
      'mohr_coulomb':{'formulae':['c_MPa = UCS_MPa*(1-sin(phi))/(2*cos(phi))','mu = tan(phi)',
          'T0_MPa = tensile_ratio * UCS_MPa'],
         'source':'cohesion algebra from Mohr-Coulomb; tensile ratio is a project assumption, not a correlation',
         'url':'https://doi.org/10.1007/s00603-012-0281-7',
         'constraint':'tensile_ratio <= (1-sin(phi))/(1+sin(phi)); angles passed in degrees and converted explicitly'},
      'parameter_experiment':{'nu':[.20,.25,.30],'phi_deg':[20.,30.,40.],'tensile_ratio':[0.,.05,.10],
         'basis':'project-selected one-at-a-time numerical experiments; not literature bounds, probabilities or estimates of Poseidon parameters',
         'reference':'nu=.25, phi=30 degrees, T0/UCS=.05; comparison anchor only',
         'blocked_use':'no operational use; no calibrated input; no implication that case extrema bound nature'},
      'candidate_decisions':[
         {'id':'horsrud_2001','implemented':False,'reason':'material applicability and Vp input unavailable in delivered elastic profiles; originating full text not inspected'},
         {'id':'bradford_1998','implemented':False,'reason':'originating equation text not inspected; a secondary table is not used to activate a field method'},
         {'id':'universal_dynamic_static_ratio','implemented':False,'reason':'no universal conversion justified'},
         {'id':'gr_to_material_class','implemented':False,'reason':'GR proxy does not establish named lithology'}],
      'claim':'No new direct measurements. No calibrated static/strength quantity. No stress or WBS calculation.',
      'accessed':'2026-09-07'}


def json_write(path, obj):
    with Path(path).open('w',encoding='utf-8',newline='\n') as f:
        f.write(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n')


def scalar(value):
    if value is None:return ''
    if isinstance(value,(bool,np.bool_)):return 'true' if value else 'false'
    if isinstance(value,(int,np.integer)):return str(int(value))
    if isinstance(value,(float,np.floating)):
        return repr(float(value)) if math.isfinite(value) else ''
    return str(value)


def write_csv(path, fields, rows):
    with Path(path).open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,lineterminator='\n',extrasaction='raise');writer.writeheader()
        for row in rows:
            require(set(row)==set(fields),'Row schema mismatch')
            writer.writerow({k:scalar(v) for k,v in row.items()})


def verify_sources(root):
    root=Path(root)
    # The baseline ledger itself is frozen in this release; replace this
    # placeholder during package construction with the observed ledger hash.
    require(sha256(root/BASELINE_LEDGER)==BASELINE_LEDGER_HASH,'Increment 9 ledger identity mismatch')
    entries={}
    for line in (root/BASELINE_LEDGER).read_text().splitlines():
        if not line or line.startswith('#'):continue
        digest,name=line.split('  ',1);p=PurePosixPath(name)
        require(not p.is_absolute() and '..' not in p.parts and '\\' not in name and ':' not in name,
                'Invalid baseline path')
        require(name not in entries,'Duplicate baseline path');entries[name]=digest
    paths=[f'{ELASTIC_DIR}/{w}_elastic.csv' for w in WELLS]+[
        f'{ELASTIC_DIR}/elastic_manifest.json',TOPS_PATH,'config/dynamic_elasticity.json',
        'config/las_curve_contracts.yml','config/deviation_survey_contracts.yml',
        'config/petrophysics_eligibility.yml']
    for name in paths:
        path=root/name
        require(path.is_file() and not path.is_symlink() and sha256(path)==entries.get(name),
                'Locked source changed: '+name)
    validate_elastic_outputs(root/ELASTIC_DIR)
    require(json.dumps(json.loads((root/REGISTRY_PATH).read_text(), object_pairs_hook=unique_object),sort_keys=True,allow_nan=False)==json.dumps(registry(),sort_keys=True,allow_nan=False),'Correlation registry differs from reviewed release')
    return {name:sha256(root/name) for name in paths+[BASELINE_LEDGER,CONFIG,REGISTRY_PATH]}


BASELINE_LEDGER_HASH = 'da9b90269787b13e45738d8c7442abd051a2f1d48045284863bb93273c94db47'


def read_profile(root,well):
    with (Path(root)/ELASTIC_DIR/(well+'_elastic.csv')).open(newline='') as f:
        rows=list(csv.DictReader(f))
    data={k:np.array([float(r[k]) if r[k] else np.nan for r in rows])
          for k in ('MD_m','TVD_m','TVDSS_m','E_dynamic_GPa')}
    data['sample_index']=np.array([int(r['sample_index']) for r in rows])
    data['valid']=np.array([r['E_valid']=='true' for r in rows])
    require(np.array_equal(data['sample_index'],np.arange(len(rows))),'Sample indices changed')
    require(all(r['well_key']==well for r in rows),'Well mix in profile')
    return data


def intervals(root,well):
    with (Path(root)/TOPS_PATH).open(newline='') as f:rows=list(csv.DictReader(f))
    rows=[r for r in rows if r['well_key']==well and r['mapping_status']=='mapped_within_coverage'
          and r['mdrt_authority_basis']=='hrs_and_readable_agree']
    rows.sort(key=lambda r:float(r['MDRT_reconciled_m']))
    for a,b in zip(rows,rows[1:]):
        require(float(b['MDRT_reconciled_m'])>float(a['MDRT_reconciled_m']),'Ambiguous top interval')
        require(a['depth_basis_used']==b['depth_basis_used'],'Top depth bases differ')
    return list(zip(rows,rows[1:]))


def profile_rows(well,data,result,case):
    for i in range(len(data['MD_m'])):
        yield {'well_key':well,'case_id':case.case_id,
            **{k:data[k][i] for k in ('sample_index','MD_m','TVD_m','TVDSS_m','E_dynamic_GPa')},
            **{k:result[k][i] for k in (*PROPERTIES,'upstream_dynamic_valid',
                'scenario_numeric_supported','field_mechanics_eligible','status')},
            'evidence_class':EVIDENCE,'calibration_status':CALIBRATION,'material_hypothesis':MATERIAL}


def stats(arr):
    v=arr[np.isfinite(arr)]
    return (int(len(v)),*(map(float,(np.min(v),np.median(v),np.max(v))) if len(v) else (None,None,None)))


def build(root):
    root=Path(root);source_hashes=verify_sources(root);config,cases=load_config(root/CONFIG)
    runs={};summary=[];formation=[];coverage=[];methods=[]
    for well in WELLS:
        data=read_profile(root,well);ref=evaluate_mechanics(data['E_dynamic_GPa'],data['valid'],cases[0])
        runs[well]=(data,ref)
        n=len(data['MD_m']);keep=ref['scenario_numeric_supported']
        coverage.append(dict(zip(COVERAGE_FIELDS,(well,n,int(data['valid'].sum()),int(keep.sum()),
            float(keep.mean()),0,int(np.sum(ref['status']==STATUS[1])),int(np.sum(ref['status']==STATUS[0])),
            'numeric_span_only_not_material_eligibility'))))
        for method in ('static_modulus','ucs','nu_static','friction_angle','cohesion','tensile_strength'):
            methods.append(dict(zip(METHOD_FIELDS,(well,method,True,False,'conditional_experiment_only',
                'no_accepted_material_applicability_or_local_static_strength_calibration'))))
        for method in registry()['candidate_decisions']:
            methods.append(dict(zip(METHOD_FIELDS,(well,method['id'],False,False,'not_implemented',method['reason']))))
        ivals=intervals(root,well)
        for case in cases:
            result=ref if case==cases[0] else evaluate_mechanics(data['E_dynamic_GPa'],data['valid'],case)
            for prop in PROPERTIES:
                count,lo,med,hi=stats(result[prop]);refmed=stats(ref[prop])[2]
                summary.append(dict(zip(SUMMARY_FIELDS,(well,case.case_id,prop,n,count,count/n,
                    lo,med,hi,None if med is None else med-refmed,EVIDENCE))))
            for a,b in ivals:
                top,base=float(a['MDRT_reconciled_m']),float(b['MDRT_reconciled_m'])
                m=(data['MD_m']>=top)&(data['MD_m']<base)
                # This is marker-to-marker context, not a newly interpreted lithology.
                for prop in ('E_static_scenario_GPa','UCS_scenario_MPa'):
                    count,lo,med,hi=stats(result[prop][m]);total=int(m.sum())
                    formation.append(dict(zip(FORMATION_FIELDS,(well,case.case_id,a['canonical_marker_name'],
                        b['canonical_marker_name'],top,base,float(a['TVDSS_survey_corrected_m']),
                        float(b['TVDSS_survey_corrected_m']),total,count,count/total if total else 0.,
                        prop,lo,med,hi,a['depth_basis_used'],a['well_identity_evidence_status'],
                        'half_open_marker_interval_not_lithology;unweighted_sample_statistics'))))
    return {'runs':runs,'summary':summary,'formation':formation,'coverage':coverage,
            'methods':methods,'config':config,'cases':cases,'source_sha256':source_hashes}


def expected_tables(run):
    result={w+'_mechanics.csv':(PROFILE_FIELDS,profile_rows(w,*run['runs'][w],run['cases'][0])) for w in WELLS}
    result.update({'mechanics_summary.csv':(SUMMARY_FIELDS,iter(run['summary'])),
        'mechanics_coverage.csv':(COVERAGE_FIELDS,iter(run['coverage'])),
        'formation_interval_summary.csv':(FORMATION_FIELDS,iter(run['formation'])),
        'method_applicability.csv':(METHOD_FIELDS,iter(run['methods']))})
    return result


def manifest_for(run,artifacts):
    return {'schema_version':'10.0.0','assurance':'Tier C - screening only; uncalibrated',
        'source_sha256':run['source_sha256'],'config':run['config'],'correlation_registry':registry(),
        'coverage':run['coverage'],'artifacts':artifacts,
        'primary_profile_case':run['cases'][0].case_id,'n_parameter_cases':len(run['cases']),
        'n_finite_field_mechanics':0,'n_direct_static_strength_measurements':0,
        'statistics':'Unweighted original-sample statistics, not depth-weighted; scenario min/max are not uncertainty bounds.',
        'scope':'Conditional static/strength experiments only. No pressure prediction, horizontal stress or WBS.',
        'source_access':'Uses packaged derived Increment 9 outputs; no raw-source regeneration claimed.',
        'formation_context':'Only accepted mapped marker pairs. Half-open MD intervals; no invented tops or lithology.'}


def plot(well,data,result,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with plt.rc_context({'font.size':9,'font.family':'DejaVu Sans','savefig.dpi':140}):
        fig,axs=plt.subplots(1,4,figsize=(13,7),sharey=True)
        try:
            axes_props=[('E_static_scenario_GPa','Static E experiment (GPa)'),
                        ('UCS_scenario_MPa','UCS experiment (MPa)'),
                        ('cohesion_scenario_MPa','Cohesion experiment (MPa)'),
                        ('T0_assumed_MPa','Tensile cutoff assumption (MPa)')]
            y=data['TVDSS_m']
            for ax,(prop,label),color in zip(axs,axes_props,['#007F88','#325B96','#94569B','#B67927']):
                ax.plot(result[prop],y,color=color,lw=.7);ax.set_xlabel(label);ax.grid(alpha=.2)
                ax.set_title('Reference experiment only',fontsize=9)
            axs[0].plot(data['E_dynamic_GPa'],y,color='#7B8790',lw=.5,alpha=.65,label='Dynamic E input')
            axs[0].legend(fontsize=8,loc='best');axs[0].set_ylabel('TVDSS (m, positive down from MSL)')
            allm=data['valid']
            if allm.any():axs[0].set_ylim(float(y[allm].max())+20,float(y[allm].min())-20)
            else:axs[0].invert_yaxis()
            n=int(result['scenario_numeric_supported'].sum())
            fig.suptitle(well.replace('_',' ')+' | Hypothetical sandstone analogue',fontsize=14)
            fig.text(.5,.055,f'{n:,} / {len(y):,} original samples in numeric support. Field eligible: 0.',ha='center')
            fig.text(.5,.025,'Uncalibrated; material unproven. Gaps retained. nu=0.25, phi=30 deg, T0/UCS=0.05 are assumed.',ha='center',fontsize=9)
            fig.tight_layout(rect=(0,.09,1,.94));fig.savefig(path,metadata={'Software':'p2mem Increment 10'})
        finally:plt.close(fig)


def compare_table(path,fields,expected):
    with Path(path).open(newline='',encoding='utf-8') as f:
        reader=csv.DictReader(f);require(tuple(reader.fieldnames or ())==tuple(fields),'CSV schema mismatch: '+Path(path).name)
        for index,pair in enumerate(zip_longest(reader,expected)):
            actual,wanted=pair
            require(actual is not None and wanted is not None,'CSV row count mismatch')
            require(None not in actual and all(v is not None for v in actual.values()),'Malformed CSV row')
            for k,v in wanted.items():
                a=actual[k];s=scalar(v)
                if isinstance(v,(float,np.floating)) and math.isfinite(v):
                    try:x=float(a)
                    except (ValueError,TypeError) as exc:raise MechanicsInputError('Invalid number '+k) from exc
                    require(math.isfinite(x) and math.isclose(x,float(v),rel_tol=1e-11,abs_tol=1e-11),
                            f'Numeric mismatch {Path(path).name}:{index}:{k}')
                else:require(a==s,f'Value mismatch {Path(path).name}:{index}:{k}')


def validate(root,destination,*,run=None):
    root=Path(root);dest=Path(destination)
    require(dest.is_dir() and not dest.is_symlink(),'Invalid output directory')
    require({p.name for p in dest.iterdir()}==set(ARTIFACTS)|{MANIFEST},'Output inventory mismatch')
    require(all(p.is_file() and not p.is_symlink() for p in dest.iterdir()),'Non-regular output')
    if run is None:run=build(root)
    with (dest/MANIFEST).open() as f:manifest=json.load(f,object_pairs_hook=unique_object)
    hashes={name:sha256(dest/name) for name in ARTIFACTS}
    require(json.dumps(manifest,sort_keys=True,allow_nan=False)==json.dumps(manifest_for(run,hashes),sort_keys=True,allow_nan=False),'Manifest or artifact hash mismatch')
    for name,(fields,rows) in expected_tables(run).items():compare_table(dest/name,fields,rows)
    for name in FIGURES:require((dest/name).read_bytes().startswith(b'\x89PNG\r\n\x1a\n'),'Invalid figure signature')
    return manifest


def publish(root,destination=None):
    root=Path(root).resolve();dest=Path(destination) if destination is not None else root/DESTINATION
    dest=dest.absolute()
    # Only the two owned output locations are accepted. No arbitrary directory
    # can be overwritten by supplying a path.
    allowed={root/DESTINATION,root/(DESTINATION+'_regenerated')}
    require(dest in allowed,'Destination must be an owned Increment 10 output location')
    require(not dest.is_symlink() and not dest.parent.is_symlink(),'Symlink destination')
    dest.parent.mkdir(parents=True,exist_ok=True)
    lock=dest.parent/(dest.name+'.lock')
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError as exc:raise MechanicsInputError('Another writer owns this output location') from exc
    os.close(fd);workspace=None;backup=None
    try:
        run=build(root)
        if dest.exists():validate(root,dest,run=run)
        workspace=Path(tempfile.mkdtemp(prefix='mechanics_stage_',dir=dest.parent));stage=workspace/'candidate';stage.mkdir()
        for name,(fields,rows) in expected_tables(run).items():write_csv(stage/name,fields,rows)
        for well,(data,result) in run['runs'].items():plot(well,data,result,stage/(well+'_mechanics_qc.png'))
        json_write(stage/MANIFEST,manifest_for(run,{name:sha256(stage/name) for name in ARTIFACTS}))
        validate(root,stage,run=run)
        if dest.exists():backup=workspace/'previous';os.replace(dest,backup)
        try:os.replace(stage,dest)
        except BaseException:
            if backup is not None and backup.exists() and not dest.exists():os.replace(backup,dest)
            raise
        return manifest_for(run,{name:sha256(dest/name) for name in ARTIFACTS})
    finally:
        if workspace is not None and not (backup is not None and backup.exists() and not dest.exists()):
            shutil.rmtree(workspace,ignore_errors=True)
        lock.unlink(missing_ok=True)
