from pathlib import Path
import json
import shutil
import numpy as np
import pytest
from p2mem.io.wbs_workflow import inputs,read_csv,validate,config,DESTINATION,STRESS
ROOT=Path(__file__).resolve().parents[1]


def test_exact_join_and_inherited_blockers():
    audit,eligible,_=inputs(ROOT)
    assert len(audit)==6666 and len(eligible)==546
    assert len({(r['well_key'],r['original_sample_index']) for r in eligible})==26
    assert all(r['field_wbs_eligible'] is False for r in audit)
    assert all(float(r['biot_alpha'])==1 and r['conditional_fault_admissible']=='true' for r in eligible)
    assert all(r['UCS_MPa'] is not None and r['matched_E_static_GPa']>0 for r in eligible)


def test_exact_case_and_original_sample_provenance():
    _,eligible,_=inputs(ROOT)
    rows=read_csv(ROOT/DESTINATION/'pressure_envelopes.csv')
    source={(r['well_key'],r['scenario_id'],r['original_sample_index']):r for r in eligible}
    assert len(rows)==len(eligible)*7
    keys=set()
    for r in rows:
        key=(r['well_key'],r['scenario_id'],r['original_sample_index'])
        assert (*key,r['orientation_id']) not in keys;keys.add((*key,r['orientation_id']))
        for field in ('MD_m','TVD_m','TVDSS_m','SHmax_MPa','Shmin_MPa','Sv_MPa','Pp_reference_MPa','mechanics_case','nu_static_assumed'):
            assert r[field]==source[key][field]
        for field in ('UCS_MPa','phi_deg','T0_MPa'):
            assert float(r[field]) == pytest.approx(source[key][field], rel=1e-12, abs=1e-12)
        assert r['geographic_azimuth_deg']=='' and r['field_wbs_eligible']=='false'


def test_coverage_and_empty_intervals():
    m=validate(ROOT)
    assert sum(r['supported_intervals'] for r in m['coverage'])==3491
    assert sum(r['empty_intervals'] for r in m['coverage'])==331
    assert all(r['unconverged_rows']==0 for r in m['coverage'])
    blocked=[r for r in m['coverage'] if not r['stress_input_rows']]
    assert {r['well_key'] for r in blocked}=={'Poseidon_North_1','Proteus_1ST2'}
    for r in read_csv(ROOT/DESTINATION/'pressure_envelopes.csv'):
        if r['status']=='empty':
            assert r['lower_MPa']==r['upper_MPa']==r['lower_MSL_equivalent_density_kg_m3']==''
            assert r['screening_interval_supported']=='false' and float(r['peak_margin_MPa'])<0


def test_output_tampering_detected(tmp_path):
    dest=tmp_path/'results';shutil.copytree(ROOT/DESTINATION,dest)
    with (dest/'pressure_envelopes.csv').open('a') as f:f.write('tamper\n')
    with pytest.raises(ValueError,match='Changed WBS output'):validate(ROOT,dest)


def test_configuration_rejects_pressure_boundary_change(tmp_path):
    (tmp_path/'config').mkdir();c=config(ROOT);c['boundary']='permeable'
    (tmp_path/'config/wellbore_stability.json').write_text(json.dumps(c))
    with pytest.raises(ValueError,match='boundary'):config(tmp_path)


def test_current_upstream_science_modules_unchanged():
    import hashlib
    metadata={'README.md','pyproject.toml','p2mem/__init__.py'}
    for line in (ROOT/'INCREMENT_11_SHA256SUMS.txt').read_text().splitlines():
        digest,name=line.split('  ',1)
        source=ROOT/'verification/increment_11_metadata'/name if name in metadata else ROOT/name
        assert hashlib.sha256(source.read_bytes()).hexdigest()==digest,name


def test_provenance_accepts_last_bit_roundoff(monkeypatch):
    import sys
    original=inputs
    def perturbed(root):
        audit,eligible,sources=original(root)
        for row in eligible:
            for field in ('UCS_MPa','phi_deg','T0_MPa'):
                row[field]=float(np.nextafter(row[field],np.inf))
        return audit,eligible,sources
    monkeypatch.setattr(sys.modules[__name__],'inputs',perturbed)
    test_exact_case_and_original_sample_provenance()


def test_provenance_rejects_material_strength_change(monkeypatch):
    import sys
    original=inputs
    def perturbed(root):
        audit,eligible,sources=original(root)
        eligible[0]['UCS_MPa']+=1e-6
        return audit,eligible,sources
    monkeypatch.setattr(sys.modules[__name__],'inputs',perturbed)
    with pytest.raises(AssertionError):test_exact_case_and_original_sample_provenance()


@pytest.mark.parametrize('left,right,expected',[
    ('59.3356598708641','59.33565987086411',True),
    ('59.3356598708641','59.3356608708641',False),
    ('2000000000000000','2000000000000001',False),
    ('true','false',False),('','0.0',False),('nan','1.0',False)])
def test_reproduction_value_comparison(left,right,expected):
    import sys
    sys.path.insert(0,str(ROOT/'scripts'))
    from compare_increment_12_reproduction import same_value
    assert same_value(left,right) is expected


def test_reproduction_table_rounding_and_drift(tmp_path):
    import sys
    sys.path.insert(0,str(ROOT/'scripts'))
    from compare_increment_12_reproduction import compare_tables
    a,b=tmp_path/'a.csv',tmp_path/'b.csv'
    a.write_text('sample_index,UCS_MPa,status\n1,59.3356598708641,interval\n')
    b.write_text('sample_index,UCS_MPa,status\n1,59.33565987086411,interval\n')
    assert compare_tables(a,b)==1
    b.write_text('sample_index,UCS_MPa,status\n2,59.33565987086411,interval\n')
    with pytest.raises(ValueError):compare_tables(a,b)
    b.write_text('sample_index,UCS_MPa,status\n1,59.3356608708641,interval\n')
    with pytest.raises(ValueError):compare_tables(a,b)


def test_equivalent_critical_angles_require_matching_stress_state(tmp_path):
    import sys
    sys.path.insert(0,str(ROOT/'scripts'))
    from compare_increment_12_reproduction import compare_tables
    (tmp_path/'a').mkdir();(tmp_path/'b').mkdir()
    a,b=(tmp_path/x/'critical_wall_states.csv' for x in ('a','b'))
    header='theta_deg,shear_MPa,sigma1_MPa,sigma3_MPa,criterion\n'
    a.write_text(header+'3.0,2.0,50.0,10.0,Mohr_Coulomb\n')
    b.write_text(header+'357.0,-2.0,50.0,10.0,Mohr_Coulomb\n')
    assert compare_tables(a,b)==1
    b.write_text(header+'357.0,-2.0,50.001,10.0,Mohr_Coulomb\n')
    with pytest.raises(ValueError):compare_tables(a,b)
