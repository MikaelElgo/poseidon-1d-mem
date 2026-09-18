"""Serialized science, upstream identity, interval support and publication checks."""
import csv
import json
from pathlib import Path
import shutil
import numpy as np
import pytest
from p2mem.mechanics import MechanicsInputError,PROPERTIES,evaluate_mechanics
import p2mem.io.mechanics_workflow as w
ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def run():return w.build(ROOT)


def test_packaged_bundle_matches_recomputation(run):
    m=w.validate(ROOT,ROOT/w.DESTINATION,run=run)
    assert m['n_finite_field_mechanics']==0
    assert sum(x['n_analogue_numeric'] for x in m['coverage'])==5845
    assert sum(x['n_original'] for x in m['coverage'])==127287


def test_coverage_partitions(run):
    for r in run['coverage']:
        assert r['n_analogue_numeric']+r['n_outside_predictor_span']==r['n_upstream_dynamic']
        assert r['n_upstream_dynamic']+r['n_missing_dynamic']==r['n_original']
        assert r['n_field_eligible']==0


def test_summary_does_not_mix_case_population(run):
    for r in run['summary']:
        assert r['n_supported']==next(x['n_analogue_numeric'] for x in run['coverage'] if x['well_key']==r['well_key'])
        if r['case_id']=='reference_experiment':assert r['median_change_from_reference']==0
        if r['property'] in ('E_static_scenario_GPa','UCS_scenario_MPa'):assert r['median_change_from_reference']==0


def test_marker_interval_counts_and_provenance(run):
    assert {r['well_key'] for r in run['formation']}=={'Boreas_1','Poseidon_2'}
    for r in run['formation']:
        data,result=run['runs'][r['well_key']]
        m=(data['MD_m']>=r['top_MD_m'])&(data['MD_m']<r['base_MD_m'])
        assert r['n_original']==int(m.sum())
        assert r['n_supported']==int((m & result['scenario_numeric_supported']).sum())
        assert r['well_identity_status']=='inferred_unverified'

@pytest.mark.parametrize('alteration',['value','field_claim','case_id','missingness','order','extra_column'])
def test_profile_mutation_rejected_even_with_rehashed_manifest(tmp_path,run,alteration):
    out=tmp_path/'bundle';shutil.copytree(ROOT/w.DESTINATION,out)
    name='Poseidon_2_mechanics.csv';p=out/name
    with p.open(newline='') as f:r=csv.DictReader(f);fields=list(r.fieldnames);rows=list(r)
    i=next(j for j,x in enumerate(rows) if x['scenario_numeric_supported']=='true')
    if alteration=='value':rows[i]['UCS_scenario_MPa']='999'
    if alteration=='field_claim':rows[i]['field_mechanics_eligible']='true'
    if alteration=='case_id':rows[i]['case_id']='calibrated'
    if alteration=='missingness':rows[0]['E_static_scenario_GPa']='20'
    if alteration=='order':rows[i],rows[i+1]=rows[i+1],rows[i]
    if alteration=='extra_column':fields.append('lithology');[x.update(lithology='') for x in rows]
    with p.open('w',newline='') as f:writer=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');writer.writeheader();writer.writerows(rows)
    m=json.loads((out/w.MANIFEST).read_text());m['artifacts'][name]=w.sha256(p);w.json_write(out/w.MANIFEST,m)
    with pytest.raises(MechanicsInputError):w.validate(ROOT,out,run=run)

@pytest.mark.parametrize('change',['integer_boolean','extra','stale_file','missing_file','truncated'])
def test_manifest_inventory_contract(tmp_path,run,change):
    out=tmp_path/'bundle';shutil.copytree(ROOT/w.DESTINATION,out);p=out/w.MANIFEST
    m=json.loads(p.read_text())
    if change=='integer_boolean':m['correlation_registry']['static']['field_eligible']=0
    if change=='extra':m['calibrated']=False
    if change=='stale_file':(out/'stale.csv').write_text('')
    if change=='missing_file':(out/w.FIGURES[0]).unlink()
    if change=='truncated':(out/w.DATA_FILES[0]).write_text('')
    w.json_write(p,m)
    with pytest.raises(MechanicsInputError):w.validate(ROOT,out,run=run)


def test_upstream_hash_identity_rejects_before_derivation(tmp_path):
    root=tmp_path/'root';root.mkdir();shutil.copyfile(ROOT/w.BASELINE_LEDGER,root/w.BASELINE_LEDGER)
    p=root/w.ELASTIC_DIR/(w.WELLS[0]+'_elastic.csv');p.parent.mkdir(parents=True);p.write_text('changed')
    with pytest.raises(MechanicsInputError,match='Locked source changed'):w.verify_sources(root)


def test_foreign_destination_cannot_be_overwritten(tmp_path):
    p=tmp_path/'precious';p.mkdir();(p/'keep').write_text('keep')
    with pytest.raises(MechanicsInputError):w.publish(ROOT,p)
    assert (p/'keep').read_text()=='keep'


def test_publish_rollback_and_no_baseline_mutation(tmp_path,run,monkeypatch):
    root=tmp_path/'root';dest=root/w.DESTINATION;dest.parent.mkdir(parents=True);shutil.copytree(ROOT/w.DESTINATION,dest)
    before={p.name:w.sha256(p) for p in dest.iterdir()}
    monkeypatch.setattr(w,'build',lambda ignored:run)
    # Reuse valid figures to isolate the publication failure path from rendering.
    monkeypatch.setattr(w,'plot',lambda well,data,result,path:shutil.copyfile(ROOT/w.DESTINATION/(well+'_mechanics_qc.png'),path))
    actual=w.os.replace
    def fail_candidate(src,dst):
        if Path(src).name=='candidate':raise OSError('injected publish failure')
        return actual(src,dst)
    monkeypatch.setattr(w.os,'replace',fail_candidate)
    with pytest.raises(OSError,match='injected'):w.publish(root)
    assert before=={p.name:w.sha256(p) for p in dest.iterdir()}
    assert not (dest.parent/(dest.name+'.lock')).exists()


def test_existing_writer_lock_fails_without_writes(tmp_path):
    root=tmp_path/'root';dest=root/w.DESTINATION;dest.parent.mkdir(parents=True)
    lock=dest.parent/(dest.name+'.lock');lock.write_text('owner')
    with pytest.raises(MechanicsInputError,match='Another writer'):w.publish(root)
    assert lock.read_text()=='owner' and not dest.exists()
