"""Independent equation values, physical identities and fail-closed behavior."""
import json
import math
from dataclasses import replace
import numpy as np
import pytest
from p2mem.mechanics import (MechanicsInputError,MechanicsCase,DEFAULT_CASES,PROPERTIES,
    SOURCE_EDYN_RANGE,analogue_static_modulus,analogue_strength,evaluate_mechanics,
    strength_parameters,isotropic_moduli,default_config,load_config)

# 60-digit Decimal exp/ln reference values, independent of the NumPy implementation.
@pytest.mark.parametrize('ed,es,ucs',[
 (17.9,8.6275804554912635276,58.318797610616605269),
 (20.,9.7428530801003159600,60.101622103415263377),
 (30.,15.193735591605903695,69.631054909913341856),
 (43.45,22.801340602753501584,85.508517799109929115)])
def test_independent_equation_values(ed,es,ucs):
    r=evaluate_mechanics([ed],np.array([True]),DEFAULT_CASES[0])
    assert r['E_static_scenario_GPa'][0]==pytest.approx(es,rel=1e-12)
    assert r['UCS_scenario_MPa'][0]==pytest.approx(ucs,rel=1e-12)

@pytest.mark.parametrize('nu',[-.5,0,.2,.25,.3,.49])
def test_isotropic_energy_and_wave_identity(nu):
    e=np.array([1.,10.,30.]);g,k=isotropic_moduli(e,nu)
    assert np.all(g>0) and np.all(k>0)
    np.testing.assert_allclose(9*k*g/(3*k+g),e,rtol=1e-13)
    np.testing.assert_allclose((3*k-2*g)/(2*(3*k+g)),nu,atol=1e-13)

@pytest.mark.parametrize('phi',[0.,20.,30.,40.,60.])
def test_mohr_circle_tangent_and_tensile_cutoff(phi):
    u=np.array([10.,60.,100.]);c,mu,t=strength_parameters(u,phi,0.)
    np.testing.assert_allclose((c+mu*u/2)/math.sqrt(1+mu*mu),u/2,rtol=1e-13)
    assert np.all(t==0)

def test_closed_form_phi30_case():
    c,mu,t=strength_parameters([60.],30.,.1)
    assert c[0]==pytest.approx(10*math.sqrt(3))
    assert mu==pytest.approx(1/math.sqrt(3));assert t[0]==6.

@pytest.mark.parametrize('key,bad',[('nu_static',True),('nu_static',-1.),
 ('nu_static',.5),('nu_static',float('nan')),('nu_static','0.25'),
 ('phi_deg',True),('phi_deg',-1.),('phi_deg',89.),('phi_deg',float('inf')),
 ('tensile_ratio',True),('tensile_ratio',-0.1),('tensile_ratio',.4),
 ('case_id','../bad'),('case_id',''),('case_id',None)])
def test_bad_case(key,bad):
    with pytest.raises(MechanicsInputError):replace(DEFAULT_CASES[0],**{key:bad})

@pytest.mark.parametrize('values',[[True,False],['20'],[[20]],np.array([20+1j]),[None]])
def test_nonnumeric_predictors(values):
    with pytest.raises(MechanicsInputError):analogue_static_modulus(values)

@pytest.mark.parametrize('value',[np.nan,np.inf,-np.inf,-1.,0.,17.899,43.451])
def test_no_extrapolation_or_clipping(value):
    assert np.isnan(analogue_static_modulus([value])[0])

def test_source_boundaries_nextafter():
    lo,hi=SOURCE_EDYN_RANGE
    a=analogue_static_modulus([np.nextafter(lo,-np.inf),lo,hi,np.nextafter(hi,np.inf)])
    assert np.isnan(a[[0,3]]).all();assert np.isfinite(a[[1,2]]).all()

def test_property_masks_missingness_and_immutability():
    x=np.array([20.,np.nan,30.,45.]);v=np.array([True,False,False,True]);original=x.copy()
    r=evaluate_mechanics(x,v,DEFAULT_CASES[0])
    for prop in PROPERTIES:
        assert np.array_equal(np.isfinite(r[prop]),[True,False,False,False])
        with pytest.raises(ValueError):r[prop][0]=999
    assert not r['field_mechanics_eligible'].any()
    np.testing.assert_array_equal(x,original)
    assert list(r['status'])==['conditional_analogue_only','upstream_dynamic_unavailable',
                              'upstream_dynamic_unavailable','outside_source_predictor_span']

@pytest.mark.parametrize('valid',[[1],[False,True],np.array([[True]])])
def test_strict_mask(valid):
    with pytest.raises(MechanicsInputError):evaluate_mechanics([20.],valid,DEFAULT_CASES[0])

@pytest.mark.parametrize('value',[np.nan,np.inf,0.,-1.])
def test_valid_flag_cannot_rescue_bad_predictor(value):
    with pytest.raises(MechanicsInputError):evaluate_mechanics([value],np.array([True]),DEFAULT_CASES[0])

def test_dependencies_one_at_a_time():
    r=[evaluate_mechanics([20.,30.],np.array([True,True]),c) for c in DEFAULT_CASES]
    for index,changed in [(1,{'nu_static_assumed','G_static_scenario_GPa','K_static_scenario_GPa'}),
                          (3,{'phi_assumed_deg','mu_derived','cohesion_scenario_MPa'}),
                          (5,{'T0_assumed_MPa'})]:
        for prop in PROPERTIES:
            if prop not in changed:np.testing.assert_array_equal(r[0][prop],r[index][prop])

def test_empty_input():
    r=evaluate_mechanics([],np.array([],dtype=bool),DEFAULT_CASES[0])
    assert all(len(v)==0 for v in r.values())

@pytest.mark.parametrize('change',['extra','mode','method','duplicate_case','bad_case','bad_schema'])
def test_config_rejection(tmp_path,change):
    d=default_config()
    if change=='extra':d['calibrated']=True
    if change=='mode':d['mode']='field_prediction'
    if change=='method':d['static_method']='unreviewed'
    if change=='duplicate_case':d['cases'].append(d['cases'][0])
    if change=='bad_case':d['cases'][0]['nu_static']=True
    if change=='bad_schema':d['schema_version']='11'
    p=tmp_path/'config.json';p.write_text(json.dumps(d))
    with pytest.raises(MechanicsInputError):load_config(p)

@pytest.mark.parametrize('text',['{"x":1,"x":2}','{"x":NaN}','[]','not json'])
def test_malformed_config(tmp_path,text):
    p=tmp_path/'bad.json';p.write_text(text)
    with pytest.raises(MechanicsInputError):load_config(p)

def test_approved_config_roundtrip(tmp_path):
    p=tmp_path/'good.json';p.write_text(json.dumps(default_config()));obj,cases=load_config(p)
    assert cases==DEFAULT_CASES and obj==default_config()
