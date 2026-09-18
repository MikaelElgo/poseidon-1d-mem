from dataclasses import replace
import math
import numpy as np
import pytest
from p2mem.horizontal_stress import StressCase,StressInputError,evaluate_stress,friction_polygon,stress_regime


def test_hand_uniaxial_case():
    r=evaluate_stress(90,30,StressCase())
    assert r['Shmin_MPa']==r['SHmax_MPa']==50
    assert r['Sv_biot_effective_MPa']==60
    assert r['conditional_fault_admissible']
    assert r['SHmax_relative_axis']=='undetermined_equal_horizontal'

@pytest.mark.parametrize('nu',[.1,.2,.25,.3,.45])
@pytest.mark.parametrize('alpha',[.0,.8,1.])
def test_isotropic_compliance_inversion(nu,alpha):
    case=StressCase(nu=nu,alpha=alpha,epsilon_x=.0005,epsilon_y=-.0002)
    r=evaluate_stress(90,30,case,20)
    # Independent solve of the horizontal effective-stress compliance equations.
    v=90-alpha*30
    expected=np.linalg.solve([[1,-nu],[-nu,1]],[20000*.0005+nu*v,20000*(-.0002)+nu*v])+alpha*30
    assert [r['Sx_MPa'],r['Sy_MPa']]==pytest.approx(expected)

@pytest.mark.parametrize('key,value',[('nu',0),('nu',.5),('nu',-.1),('alpha',-1),('alpha',1.1),('fault_mu',0),('fluid_density_kg_m3',-1),('epsilon_x',.1),('nu',True),('alpha',float('nan')),('fault_mu',float('inf')),('case_id','../evil')])
def test_invalid_case_rejected(key,value):
    with pytest.raises(StressInputError):StressCase(**{key:value})

@pytest.mark.parametrize('sv,pp',[(-1,0),(1,-1),(float('inf'),0),(True,0),(1,float('nan'))])
def test_invalid_stress_rejected(sv,pp):
    with pytest.raises(StressInputError):evaluate_stress(sv,pp,StressCase())


def test_E_dependency_is_conditional():
    r=evaluate_stress(90,30,StressCase(),None)
    assert r['numeric_stress_supported']
    for E in (None,):
        r=evaluate_stress(90,30,StressCase(epsilon_x=.0005),E)
        assert r['status']=='missing_static_E_for_strain' and r['Shmin_MPa'] is None
    for E in (0,-1,float('nan'),True):
        with pytest.raises(StressInputError):evaluate_stress(90,30,StressCase(epsilon_x=.0005),E)


def test_missingness_not_silently_filled():
    r=evaluate_stress(90,30,StressCase(epsilon_x=.0005),None)
    assert not r['conditional_fault_admissible'] and r['fault_ratio'] is None


def test_hydrostatic_degeneracy():
    r=evaluate_stress(30,30,StressCase())
    assert r['Sx_MPa']==r['Sy_MPa']==30
    assert r['regime']=='isotropic_degenerate'
    assert r['status']=='nonpositive_fault_effective_stress'
    assert not r['conditional_fault_admissible']


def test_negative_effective_retained():
    r=evaluate_stress(20,30,StressCase())
    assert r['Sv_biot_effective_MPa']==-10
    assert r['status']=='negative_biot_effective_vertical_stress'


def test_fault_pressure_distinct_from_biot():
    r=evaluate_stress(90,30,StressCase(alpha=.8))
    assert r['Shmin_MPa']==46
    assert r['Shmin_biot_effective_MPa']==22
    assert r['fault_effective_min_MPa']==16
    assert not r['conditional_fault_admissible']


def test_fault_mu_never_changes_total_stress():
    a=evaluate_stress(90,30,StressCase(fault_mu=.4))
    b=evaluate_stress(90,30,StressCase(fault_mu=.8))
    assert a['Shmin_MPa']==b['Shmin_MPa'] and a['SHmax_MPa']==b['SHmax_MPa']
    assert not a['conditional_fault_admissible'] and b['conditional_fault_admissible']

@pytest.mark.parametrize('mu',[.4,.6,.8,1.])
def test_polygon_vertices_satisfy_mohr_geometry(mu):
    vertices=friction_polygon(90,30,mu)
    for h,H in vertices:
        lo=min(90,h)-30;hi=max(90,H)-30
        slope=(hi-lo)/(2*math.sqrt(hi*lo))
        assert h<=H and slope==pytest.approx(mu)

@pytest.mark.parametrize('v,p',[(0,0),(20,30)])
def test_polygon_noncompressive_domain_rejected(v,p):
    with pytest.raises(StressInputError):friction_polygon(v,p,.6)

@pytest.mark.parametrize('sv,h,H,label',[(90,50,70,'normal'),(60,50,90,'strike_slip'),(40,50,90,'reverse'),(90,50,90,'normal_strike_slip_boundary'),(50,50,90,'strike_slip_reverse_boundary'),(90,50,50,'normal_axisymmetric'),(30,50,50,'reverse_axisymmetric'),(50,50,50,'isotropic_degenerate')])
def test_regime_without_imposed_order(sv,h,H,label):
    assert stress_regime(sv,h,H)==label


def test_equal_strain_symmetry_and_axis_swap():
    equal=evaluate_stress(90,30,StressCase(epsilon_x=.0005,epsilon_y=.0005),20)
    assert equal['Shmin_MPa']==equal['SHmax_MPa']
    x=evaluate_stress(90,30,StressCase(epsilon_x=.0005),20)
    y=evaluate_stress(90,30,StressCase(epsilon_y=.0005),20)
    assert x['Shmin_MPa']==y['Shmin_MPa'] and x['SHmax_MPa']==y['SHmax_MPa']
    assert x['SHmax_relative_axis']=='x' and y['SHmax_relative_axis']=='y'


def test_total_stress_translation_invariance():
    a=evaluate_stress(90,30,StressCase())
    b=evaluate_stress(100,40,StressCase())
    assert b['Shmin_MPa']==a['Shmin_MPa']+10
    assert b['fault_ratio']==a['fault_ratio']
