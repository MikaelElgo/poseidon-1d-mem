"""Independent mechanics identities, coverage, boundaries and malformed inputs."""
import json
import math

import numpy as np
import pytest

from p2mem.dynamic_elasticity import (
    ElasticInputError, ElasticPolicy, NONNEGATIVE_NU_BOUND, POSITIVE_BULK_BOUND,
    PROPERTIES, REGIMES, compute_dynamic_elasticity as calc, load_elastic_policy,
)


@pytest.mark.parametrize('rho', [1000., 2300., 3500.])
@pytest.mark.parametrize('nu', [0.01, 0.1, 0.25, 0.4])
def test_forward_inverse_from_independent_moduli(rho, nu):
    # Construct waves from independently chosen G and nu, invert back.
    shear = 3.0e9
    young = 2*shear*(1+nu)
    bulk = young/(3*(1-2*nu))
    vs = math.sqrt(shear/rho)
    vp = math.sqrt((bulk+4*shear/3)/rho)
    result = calc([vp], [vs], [rho], [True])
    for field, expected in zip(PROPERTIES, (nu, shear/1e9, bulk/1e9, young/1e9)):
        assert result[field][0] == pytest.approx(expected, rel=5e-13, abs=5e-14)


def test_known_si_units():
    r = calc([4000.], [2000.], [2500.], [True])
    assert r['G_dynamic_GPa'][0] == 10
    assert r['K_dynamic_GPa'][0] == pytest.approx(80/3)
    assert r['nu_dynamic'][0] == pytest.approx(1/3)
    assert r['E_dynamic_GPa'][0] == pytest.approx(80/3)


@pytest.mark.parametrize('ratio,state,eligible', [
    (1., 'nonpositive_bulk_ratio', False),
    (POSITIVE_BULK_BOUND, 'nonpositive_bulk_ratio', False),
    (np.nextafter(POSITIVE_BULK_BOUND, 0), 'nonpositive_bulk_ratio', False),
    (np.nextafter(POSITIVE_BULK_BOUND, math.inf), 'negative_poisson_ratio', False),
    (1.25, 'negative_poisson_ratio', False),
    (np.nextafter(NONNEGATIVE_NU_BOUND, 0), 'negative_poisson_ratio', False),
    (NONNEGATIVE_NU_BOUND, 'passes_ratio_screen', True),
    (np.nextafter(NONNEGATIVE_NU_BOUND, math.inf), 'passes_ratio_screen', True),
    (4., 'passes_ratio_screen', True),
    (np.nextafter(4., math.inf), 'ratio_above_policy', False),
])
def test_exact_inclusive_exclusive_ratio_policy(ratio, state, eligible):
    # Binary-exact scale keeps boundary ratios from changing in test setup.
    r = calc([ratio*1024], [1024.], [2400.], [True])
    assert r['ratio_regime'][0] == state
    assert bool(r['legacy_full_eligible'][0]) == eligible
    assert bool(r['E_valid'][0]) == eligible
    if state == 'negative_poisson_ratio':
        assert -1 < r['nu_stable_diagnostic'][0] < 0
        assert np.isnan(r['nu_dynamic'][0])


@pytest.mark.parametrize('missing', ['vp', 'vs', 'rho', 'depth'])
def test_property_specific_information_requirements(missing):
    args = {'vp': [4000.], 'vs': [2000.], 'rho': [2500.], 'depth': [True]}
    args[missing] = [False] if missing == 'depth' else None
    r = calc(args['vp'], args['vs'], args['rho'], args['depth'])
    assert bool(r['nu_valid'][0]) == (missing == 'rho')
    assert bool(r['G_valid'][0]) == (missing == 'vp')
    assert not r['K_valid'][0] and not r['E_valid'][0]


@pytest.mark.parametrize('value', [math.nan, math.inf, -math.inf, -1., 0., 1e300])
@pytest.mark.parametrize('column', [0, 1, 2])
def test_invalid_measurements_never_enter_dependent_properties(value, column):
    values = [[4000.], [2000.], [2500.]]
    values[column] = [value]
    r = calc(*values, [True])
    assert not r['E_valid'][0]
    assert not r['K_valid'][0]
    if column != 2:
        assert not r['nu_valid'][0]
    if column != 0:
        assert not r['G_valid'][0]


@pytest.mark.parametrize('vp,vs,rho,field', [
    (1000., 500., 1000., 'E_valid'), (8000., 4000., 3500., 'E_valid'),
    (1000., 300., 2500., 'E_valid'), (8000., 5000., 2500., 'E_valid'),
])
def test_curve_screen_endpoints_are_inclusive(vp, vs, rho, field):
    assert calc([vp], [vs], [rho], [True])[field][0]


def test_input_order_arrays_and_readonly_results():
    vp = np.array([4000., np.nan, 4100., 2000.])
    before = vp.copy()
    r = calc(vp, [2000.]*4, [2500.]*4, [True,True,False,True])
    np.testing.assert_array_equal(vp, before)
    assert len(r['E_dynamic_GPa']) == 4
    assert r['E_valid'].tolist() == [True,False,False,False]
    for arr in r.values():
        assert not arr.flags.writeable


@pytest.mark.parametrize('invalid', [[True], ['4000'], [1+2j], [[4000]], [4000,4000], np.array([4000],dtype=object)])
def test_structurally_invalid_velocity_rejected(invalid):
    with pytest.raises(ElasticInputError):
        calc(invalid, [2000.], [2500.], [True])


@pytest.mark.parametrize('depth', [[1], ['true'], [[True]], True, [math.nan]])
def test_depth_mask_cannot_be_coerced(depth):
    with pytest.raises(ElasticInputError):
        calc([4000.], [2000.], [2500.], depth)


def test_empty_arrays_have_consistent_output():
    r = calc([], [], [], np.array([], dtype=bool))
    assert all(len(a)==0 for a in r.values())


@pytest.mark.parametrize('invalid', [True, '4', math.nan, math.inf, 0, -1, 1.1])
def test_invalid_policy_ratio_rejected(invalid):
    with pytest.raises(ElasticInputError):
        ElasticPolicy(ratio_max=invalid)


@pytest.mark.parametrize('raw', [
    '{}', '[]', '{', '{"schema_version":"9.0.0","schema_version":"9.0.0","bounds":{}}',
    '{"schema_version":"9.0.0","bounds":{},"typo":3}',
    '{"schema_version":"8.0.0","bounds":{}}',
])
def test_policy_schema_fails_closed(tmp_path, raw):
    path = tmp_path/'policy.json'
    path.write_text(raw)
    with pytest.raises(ElasticInputError):
        load_elastic_policy(path)


def test_policy_bound_order_and_unknown_keyword():
    with pytest.raises(ElasticInputError):
        ElasticPolicy(vp_min_m_s=9000)
    with pytest.raises(TypeError):
        ElasticPolicy(vp_mni_m_s=1000)


def test_condition_number_matches_finite_difference():
    vp,vs,rho = 4000., 2000., 2500.
    h = 1e-7
    r = calc([vp], [vs], [rho], [True])
    plus = calc([vp*(1+h)], [vs*(1-h)], [rho], [True])['K_dynamic_GPa'][0]
    minus = calc([vp*(1-h)], [vs*(1+h)], [rho], [True])['K_dynamic_GPa'][0]
    derivative = (plus-minus)/(2*h*r['K_dynamic_GPa'][0])
    assert derivative == pytest.approx(r['K_velocity_condition_number'][0], rel=1e-8)


def test_seeded_random_forward_mechanics_and_exhaustive_regimes():
    rng = np.random.default_rng(91824)
    vp = rng.uniform(1000,8000,1000)
    vs = rng.uniform(300,5000,1000)
    rho = rng.uniform(1000,3500,1000)
    r = calc(vp,vs,rho,np.ones(1000,dtype=bool))
    assert set(r['ratio_regime']).issubset(REGIMES)
    keep = r['E_valid']
    e = r['E_dynamic_GPa'][keep]*1e9
    nu = r['nu_dynamic'][keep]
    # Reconstruct Vp independently using E, nu and rho.
    recovered = np.sqrt(e*(1-nu)/(rho[keep]*(1+nu)*(1-2*nu)))
    np.testing.assert_allclose(recovered, vp[keep], rtol=2e-14)
