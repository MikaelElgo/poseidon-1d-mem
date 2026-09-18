import numpy as np
import pytest
from p2mem.wellbore_stability import rotate_stress, WallModel, pressure_interval, converged_envelope

@pytest.mark.parametrize('inclination',[0,30,60,90])
@pytest.mark.parametrize('azimuth',[0,33,90,180])
def test_rotation_invariants(inclination,azimuth):
    s=rotate_stress(80,50,100,inclination,azimuth)
    np.testing.assert_allclose(np.linalg.eigvalsh(s),[50,80,100],atol=1e-12)
    assert np.trace(s)==pytest.approx(230)
    np.testing.assert_allclose(s,s.T,atol=1e-12)

@pytest.mark.parametrize('pw',[0,20,45,100])
@pytest.mark.parametrize('inclination',[0,45,90])
def test_tensor_principals_and_radial_traction(pw,inclination):
    m=WallModel(rotate_stress(80,50,100,inclination,31),20,.25,40,30,2)
    state=m.state(pw)
    tensor=np.zeros((len(m.angles),3,3));tensor[:,0,0]=state['radial'];tensor[:,1,1]=state['hoop'];tensor[:,2,2]=state['axial'];tensor[:,1,2]=tensor[:,2,1]=state['shear']
    e=np.linalg.eigvalsh(tensor)
    for i,k in enumerate(('sigma3','sigma2','sigma1')):np.testing.assert_allclose(e[:,i],state[k],atol=1e-12)
    np.testing.assert_allclose(state['radial']+m.pp,pw)


def test_vertical_wall_analytical_components():
    m=WallModel(np.diag([80,50,100]),20,.25,40,30,2)
    s=m.state(30)
    assert s['hoop'][0]==pytest.approx(20)
    assert s['hoop'][90]==pytest.approx(140)
    assert s['axial'][0]==pytest.approx(65)
    assert s['axial'][90]==pytest.approx(95)
    np.testing.assert_array_equal(s['shear'],0)


def test_isotropic_full_principal_interval_shear_both_ends():
    m=WallModel(np.eye(3)*60,20,.25,40,30,2)
    r=pressure_interval(m)
    assert r['status']=='interval'
    assert r['lower_MPa']==pytest.approx(30,abs=1e-5)
    assert r['upper_MPa']==pytest.approx(90,abs=1e-5)
    assert r['lower_boundary']==r['upper_boundary']=='Mohr_Coulomb'
    assert min(m.margins(29.99))<0 and min(m.margins(90.01))<0


def test_isotropic_tensile_both_ends():
    m=WallModel(np.eye(3)*60,20,.25,1000,30,2)
    r=pressure_interval(m)
    assert r['lower_MPa']==pytest.approx(18,abs=1e-5)
    assert r['upper_MPa']==pytest.approx(102,abs=1e-5)
    assert r['lower_boundary']==r['upper_boundary']=='tensile'


def test_empty_and_tangent_not_reported_as_intervals():
    assert pressure_interval(WallModel(np.eye(3)*5,20,.25,40,30,2))['status']=='empty'
    assert pressure_interval(WallModel(np.zeros((3,3)),0,.25,40,30,0))['status']=='tangent_or_unresolved'


def test_zero_pressure_domain_boundary():
    r=pressure_interval(WallModel(np.eye(3)*5,0,.25,100,30,1))
    assert r['lower_MPa']==0 and r['lower_boundary']=='domain_zero'


def test_narrow_interval_not_lost_between_pressure_grid_points():
    # Isotropic effective stress .0001 MPa; tiny but nonzero stable interval.
    m=WallModel(np.eye(3)*20.0001,20,.25,1e-4,30,0)
    r=pressure_interval(m,pressure_tolerance=1e-9)
    assert r['status']=='interval' and 0<r['upper_MPa']-r['lower_MPa']<.001


def test_angular_convergence_inclined_shear():
    args=(rotate_stress(80,50,100,60,37),20,.25,100,30,3)
    r,m=converged_envelope(*args)
    assert r['angular_converged'] and r['screening_interval_supported']
    fine=pressure_interval(WallModel(*args,angular_step_deg=.1))
    assert abs(r['lower_MPa']-fine['lower_MPa'])<.02
    assert abs(r['upper_MPa']-fine['upper_MPa'])<.02

@pytest.mark.parametrize('kwargs',[{'alpha':.8},{'pp':-1},{'nu':.5},{'ucs':0},{'phi_deg':90},{'tensile_strength':-1},{'angular_step_deg':0},{'pp':float('nan')}])
def test_invalid_material_and_boundary_rejected(kwargs):
    args=dict(total_stress=np.eye(3)*60,pp=20,nu=.25,ucs=40,phi_deg=30,tensile_strength=2)
    args.update(kwargs)
    with pytest.raises(ValueError):WallModel(**args)


def test_nonsymmetric_stress_rejected():
    with pytest.raises(ValueError):WallModel(np.array([[60,1,0],[0,60,0],[0,0,60]]),20,.25,40,30,2)


def test_equal_horizontal_azimuth_invariance():
    a=WallModel(rotate_stress(60,60,100,45,0),20,.25,100,30,2)
    b=WallModel(rotate_stress(60,60,100,45,37),20,.25,100,30,2)
    for p in (10,30,60):np.testing.assert_allclose(a.margins(p),b.margins(p),atol=1e-12)
