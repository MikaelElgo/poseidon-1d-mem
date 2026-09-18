from pathlib import Path
from copy import deepcopy
import importlib.util
import json
import shutil
import pytest
from p2mem.io import stress_workflow as w
from p2mem.horizontal_stress import StressInputError,load_cases,default_config
ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def data():return w.build(ROOT)[0]


def test_packaged_output_recomputes():
    assert w.validate(ROOT)['field_eligible_rows']==0


def test_exact_coverage_and_missingness(data):
    assert len(data['depth_alignment.csv'])==202
    rr=data['stress_scenarios.csv']
    assert len(rr)==6666
    assert sum(r['numeric_stress_supported'] for r in rr)==5082
    assert sum(r['conditional_fault_admissible'] for r in rr)==3175
    assert all(not r['field_stress_eligible'] and r['geographic_SHmax_azimuth_deg'] is None for r in rr)
    assert sum(r['status']=='missing_static_E_for_strain' for r in rr)==1584


def test_all_source7_and_10_files_frozen():
    assert len(w.verify_baseline(ROOT))==313

@pytest.mark.parametrize('change',['md','tvd','well','duplicate'])
def test_bad_join_rejected(change):
    n=[dict(well_key='x',node_index='0',md_m='10',tvd_m='9',tvdss_m='8')]
    m=[dict(well_key='x',MD_m='10',TVD_m='9',TVDSS_m='8')]
    if change=='md':m[0]['MD_m']='10.01'
    if change=='tvd':m[0]['TVDSS_m']='9'
    if change=='well':m[0]['well_key']='y'
    if change=='duplicate':m=m+m
    with pytest.raises(StressInputError):w.exact_join(n,m)


def test_config_and_duplicate_keys_rejected(tmp_path):
    p=tmp_path/'bad.json';c=default_config();c['geographic_azimuth_deg']=45;p.write_text(json.dumps(c))
    with pytest.raises(StressInputError):load_cases(p)
    p.write_text('{"cases": [], "cases": []}')
    with pytest.raises(StressInputError):load_cases(p)


def test_formations_use_real_marker_names_and_half_open_nodes(data):
    for r in data['formation_stress_summary.csv']:
        assert r['top_marker'] and not r['top_marker'][0].isdigit()
        nodes=[x for x in data['stress_scenarios.csv'] if x['well_key']==r['well_key'] and x['scenario_id']==r['scenario_id'] and r['top_MD_m']<=x['MD_m']<r['base_MD_m']]
        assert len(nodes)==r['n_report_nodes']


def test_shallow_spread_preserved(data):
    rr=data['stress_scenarios.csv'];refs=[r for r in rr if r['parameter_case']=='reference']
    grouped={}
    for r in refs:grouped.setdefault((r['well_key'],r['upstream_node_index']),{})[r['sv_scenario']]=r
    for g in grouped.values():
        assert g['low']['Sv_MPa']<g['base']['Sv_MPa']<g['high']['Sv_MPa']
        assert g['low']['Pp_reference_MPa']==g['high']['Pp_reference_MPa']


def test_independent_export_checker():
    spec=importlib.util.spec_from_file_location('independent11',ROOT/'scripts/verify_increment_11_independent.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    result=m.verify(ROOT/w.DESTINATION)
    assert result['passed'] and result['checked_numeric_rows']==5082


def test_rehashed_output_mutation_still_rejected(tmp_path):
    dst=tmp_path/'out';shutil.copytree(ROOT/w.DESTINATION,dst)
    p=dst/'stress_scenarios.csv';p.write_text(p.read_text().replace('conditional_admissible','altered_claim',1))
    m=json.loads((dst/'stress_manifest.json').read_text());m['files'][p.name]=w.sha(p);w.write_json(dst/'stress_manifest.json',m)
    with pytest.raises(StressInputError,match='Scientific table'):w.validate(ROOT,dst)


def test_foreign_publish_rejected(tmp_path):
    with pytest.raises(StressInputError):w.publish(ROOT,tmp_path/'foreign')


def test_failed_publication_preserves_previous_bundle(tmp_path,monkeypatch,data):
    root=tmp_path/'project';dst=root/'outputs/11_test';dst.mkdir(parents=True);(dst/'existing').write_text('preserve')
    monkeypatch.setattr(w,'build',lambda root:(data,{}))
    def fail(*args):raise RuntimeError('render failed')
    monkeypatch.setattr(w,'render',fail)
    with pytest.raises(RuntimeError,match='render failed'):w.publish(root,dst)
    assert (dst/'existing').read_text()=='preserve'
    assert {p.name for p in dst.parent.iterdir()}=={'11_test'}
