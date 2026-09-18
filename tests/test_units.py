"""
tests/test_units.py - Validation suite for p2mem.units.

Coverage required by the Increment 1 / 1.1 specification:
    1. Analytical reference values (independently known correct answers,
       several of them fixed external references rather than values
       derived from the module's own constants - e.g. the ppg-to-kg/m3
       factor and the equivalent-mud-weight check).
    2. Forward/inverse round-trip consistency.
    3. Scalar inputs.
    4. NumPy array inputs.
    5. NaN preservation (missing samples must remain missing).
    6. Rejection of invalid / nonphysical inputs (must raise, never clip).
    7. Unit-consistency tolerances (round-trips within floating-point noise).
    8. Rejection of ambiguous input types - booleans, numeric-looking
       strings, string arrays, and complex values - with a clear
       TypeError, while continuing to support ordinary Python numeric
       scalars and NumPy integer/floating arrays and preserving NaN.

Run with:  pytest -v
"""

import math

import numpy as np
import pytest

from p2mem import units


# ---------------------------------------------------------------------------
# Length: feet <-> metres
# ---------------------------------------------------------------------------
def test_feet_to_meters_analytical():
    # 1 ft = 0.3048 m exactly; 100 ft = 30.48 m
    assert units.feet_to_meters(1.0) == pytest.approx(0.3048, abs=1e-12)
    assert units.feet_to_meters(100.0) == pytest.approx(30.48, abs=1e-9)


def test_meters_to_feet_analytical():
    assert units.meters_to_feet(0.3048) == pytest.approx(1.0, abs=1e-9)


def test_length_round_trip_array():
    ft = np.array([0.0, 1.0, 5350.9507, 490.0])
    m = units.feet_to_meters(ft)
    back = units.meters_to_feet(m)
    np.testing.assert_allclose(back, ft, rtol=0, atol=1e-9)


def test_length_scalar_returns_python_float():
    result = units.feet_to_meters(10.0)
    assert isinstance(result, float)


def test_length_array_returns_ndarray():
    result = units.feet_to_meters(np.array([1.0, 2.0]))
    assert isinstance(result, np.ndarray)


def test_length_nan_preserved():
    arr = np.array([1.0, np.nan, 3.0])
    out = units.feet_to_meters(arr)
    assert np.isnan(out[1])
    assert not np.isnan(out[0])
    assert not np.isnan(out[2])


def test_length_rejects_inf():
    with pytest.raises(ValueError):
        units.feet_to_meters(float("inf"))
    with pytest.raises(ValueError):
        units.meters_to_feet(np.array([1.0, float("-inf")]))


# ---------------------------------------------------------------------------
# Sonic slowness <-> velocity
# ---------------------------------------------------------------------------
def test_sonic_analytical_freshwater_style_value():
    # 189 us/ft is a plausible shale DTCO value; check against hand
    # calculation: V = 304800 / 189 m/s
    dt = 189.0
    expected_v = 304800.0 / dt
    assert units.us_per_ft_to_m_per_s(dt) == pytest.approx(expected_v, rel=1e-12)


def test_sonic_known_matrix_value_quartz_like():
    # A commonly cited fast matrix transit time is ~55.5 us/ft (~5490 m/s).
    dt = 55.5
    v = units.us_per_ft_to_m_per_s(dt)
    assert v == pytest.approx(304800.0 / 55.5, rel=1e-12)
    assert 5000.0 < v < 6000.0  # sanity bound, not an empirical claim


def test_sonic_round_trip_array():
    dt = np.array([40.0, 55.5, 100.0, 189.0, 240.0])
    v = units.us_per_ft_to_m_per_s(dt)
    back = units.m_per_s_to_us_per_ft(v)
    np.testing.assert_allclose(back, dt, rtol=1e-10)


def test_sonic_nan_preserved():
    dt = np.array([100.0, np.nan, 200.0])
    v = units.us_per_ft_to_m_per_s(dt)
    assert np.isnan(v[1])
    assert np.isfinite(v[0]) and np.isfinite(v[2])


def test_sonic_rejects_zero_and_negative():
    with pytest.raises(ValueError):
        units.us_per_ft_to_m_per_s(0.0)
    with pytest.raises(ValueError):
        units.us_per_ft_to_m_per_s(-50.0)
    with pytest.raises(ValueError):
        units.m_per_s_to_us_per_ft(np.array([1500.0, -1.0]))


def test_sonic_rejects_inf():
    with pytest.raises(ValueError):
        units.us_per_ft_to_m_per_s(float("inf"))


# ---------------------------------------------------------------------------
# Density: g/cc <-> kg/m3
# ---------------------------------------------------------------------------
def test_density_analytical():
    # Quartz-like density ~2.65 g/cc -> 2650 kg/m3 (definitional scaling)
    assert units.gcc_to_kgm3(2.65) == pytest.approx(2650.0, abs=1e-9)
    assert units.kgm3_to_gcc(2650.0) == pytest.approx(2.65, abs=1e-12)


def test_density_round_trip_array():
    gcc = np.array([1.0, 1.95, 2.65, 2.98])
    back = units.kgm3_to_gcc(units.gcc_to_kgm3(gcc))
    np.testing.assert_allclose(back, gcc, rtol=1e-12)


def test_density_nan_preserved():
    arr = np.array([2.0, np.nan])
    out = units.gcc_to_kgm3(arr)
    assert np.isnan(out[1])


def test_density_rejects_zero_and_negative():
    with pytest.raises(ValueError):
        units.gcc_to_kgm3(0.0)
    with pytest.raises(ValueError):
        units.gcc_to_kgm3(np.array([2.0, -1.0]))
    with pytest.raises(ValueError):
        units.kgm3_to_gcc(-500.0)


# ---------------------------------------------------------------------------
# Pressure: Pa <-> MPa <-> psi
# ---------------------------------------------------------------------------
def test_pressure_analytical():
    assert units.mpa_to_pa(1.0) == pytest.approx(1.0e6, abs=1e-6)
    assert units.pa_to_mpa(1.0e6) == pytest.approx(1.0, abs=1e-12)
    # 1000 psi = 6,894,757.293168 Pa (exact, from defined psi->Pa factor)
    assert units.psi_to_pa(1000.0) == pytest.approx(6894757.293168, rel=1e-12)
    assert units.pa_to_psi(6894757.293168) == pytest.approx(1000.0, rel=1e-10)


def test_pressure_mpa_psi_composed():
    # 1 MPa = 145.037737730... psi (cross-check against psi->Pa factor)
    expected = 1.0e6 / 6894.757293168
    assert units.mpa_to_psi(1.0) == pytest.approx(expected, rel=1e-10)
    assert units.psi_to_mpa(expected) == pytest.approx(1.0, rel=1e-10)


def test_pressure_round_trip_array():
    # 14,696 psi is approximately 101.3 MPa - a representative high-pressure
    # magnitude check only. (For reference, 1 standard atmosphere is
    # approximately 14.696 psi, not 14,696 psi - see
    # test_pressure_atmospheric_reference for the actual atmosphere check.)
    psi = np.array([0.0, 500.0, 5000.0, 14696.0])
    back = units.pa_to_psi(units.psi_to_pa(psi))
    np.testing.assert_allclose(back, psi, rtol=1e-9)


def test_pressure_atmospheric_reference():
    # 1 standard atmosphere = 101,325 Pa exactly (definition). In psi this
    # is approximately 14.6959488 psi - an independent, genuinely
    # atmospheric reference value (distinct from the 14,696 psi magnitude
    # check above, which is roughly 1000x atmospheric pressure, not 1 atm).
    one_atm_pa = 101325.0
    one_atm_psi = units.pa_to_psi(one_atm_pa)
    assert one_atm_psi == pytest.approx(14.6959488, rel=1e-6)
    # Round trip back to Pa should return the exact reference value.
    assert units.psi_to_pa(one_atm_psi) == pytest.approx(one_atm_pa, rel=1e-9)


def test_pressure_nan_preserved():
    arr = np.array([1.0, np.nan, 3.0])
    out = units.psi_to_pa(arr)
    assert np.isnan(out[1])


def test_pressure_rejects_negative():
    with pytest.raises(ValueError):
        units.psi_to_pa(-1.0)
    with pytest.raises(ValueError):
        units.pa_to_mpa(np.array([1.0, -2.0]))


def test_pressure_allows_zero():
    # Zero pressure is physically valid (unlike zero density or zero TVD)
    assert units.psi_to_pa(0.0) == 0.0
    assert units.pa_to_mpa(0.0) == 0.0


# ---------------------------------------------------------------------------
# Angle: degrees <-> radians
# ---------------------------------------------------------------------------
def test_angle_analytical():
    assert units.degrees_to_radians(180.0) == pytest.approx(math.pi, rel=1e-12)
    assert units.degrees_to_radians(90.0) == pytest.approx(math.pi / 2, rel=1e-12)
    assert units.radians_to_degrees(math.pi) == pytest.approx(180.0, rel=1e-12)


def test_angle_round_trip_array_including_negative_and_large():
    deg = np.array([-720.5, -90.0, 0.0, 4.99, 90.0, 360.0, 725.3])
    back = units.radians_to_degrees(units.degrees_to_radians(deg))
    np.testing.assert_allclose(back, deg, rtol=1e-12, atol=1e-12)


def test_angle_nan_preserved():
    arr = np.array([0.0, np.nan, 45.0])
    out = units.degrees_to_radians(arr)
    assert np.isnan(out[1])


def test_angle_rejects_inf():
    with pytest.raises(ValueError):
        units.degrees_to_radians(float("inf"))


# ---------------------------------------------------------------------------
# Mud weight: ppg <-> kg/m3
# ---------------------------------------------------------------------------
def test_ppg_fixed_external_reference():
    # Independent, fixed reference value: 1 ppg = 119.82642731689663 kg/m3.
    # This value is computed OUTSIDE of units.CONST (i.e. it is not derived
    # from the same code path being tested) from the exact international
    # pound (0.45359237 kg) and US liquid gallon (0.003785411784 m3)
    # definitions, so it is an independent check of the conversion function
    # rather than a tautology against the module's own constant.
    assert units.ppg_to_kgm3(1.0) == pytest.approx(119.82642731689663, rel=0, abs=1e-9)


def test_ppg_analytical_freshwater_reference():
    # Freshwater is ~8.33 ppg; using the fixed external reference factor
    # above, this should land close to, but need not exactly equal,
    # 1000 kg/m3 - this checks plausible magnitude, not a claim that
    # 8.33 ppg IS exactly freshwater density.
    kgm3 = units.ppg_to_kgm3(8.33)
    assert kgm3 == pytest.approx(8.33 * 119.82642731689663, rel=0, abs=1e-9)
    assert 990.0 < kgm3 < 1010.0


def test_ppg_round_trip_array():
    ppg = np.array([8.33, 9.5, 10.0, 12.5, 16.0])
    back = units.kgm3_to_ppg(units.ppg_to_kgm3(ppg))
    np.testing.assert_allclose(back, ppg, rtol=1e-10)


def test_ppg_rejects_zero_and_negative():
    with pytest.raises(ValueError):
        units.ppg_to_kgm3(0.0)
    with pytest.raises(ValueError):
        units.kgm3_to_ppg(-100.0)


def test_ppg_nan_preserved():
    arr = np.array([9.5, np.nan])
    out = units.ppg_to_kgm3(arr)
    assert np.isnan(out[1])


# ---------------------------------------------------------------------------
# Pressure gradient <-> density, and equivalent mud weight
# ---------------------------------------------------------------------------
def test_pressure_gradient_analytical_freshwater_hydrostatic():
    # Freshwater hydrostatic gradient: rho*g = 1000 kg/m3 * 9.80665 m/s2
    #                                        = 9806.65 Pa/m
    gradient = units.density_to_pressure_gradient(1000.0)
    assert gradient == pytest.approx(9806.65, rel=1e-12)
    back = units.pressure_gradient_to_density(gradient)
    assert back == pytest.approx(1000.0, rel=1e-12)


def test_pressure_gradient_round_trip_array():
    rho = np.array([1000.0, 1030.0, 1250.0, 1500.0])
    back = units.pressure_gradient_to_density(units.density_to_pressure_gradient(rho))
    np.testing.assert_allclose(back, rho, rtol=1e-12)


def test_pressure_gradient_rejects_nonphysical():
    with pytest.raises(ValueError):
        units.density_to_pressure_gradient(0.0)
    with pytest.raises(ValueError):
        units.density_to_pressure_gradient(-1200.0)
    with pytest.raises(ValueError):
        units.pressure_gradient_to_density(-100.0)
    with pytest.raises(ValueError):
        units.density_to_pressure_gradient(1000.0, gravity_m_s2=0.0)


def test_equivalent_mud_weight_analytical():
    # Hydrostatic freshwater column: P = rho*g*TVD
    rho = 1000.0
    tvd = 2000.0
    p = units.density_to_pressure_gradient(rho) * tvd  # Pa
    emw = units.equivalent_mud_weight_kgm3(p, tvd)
    assert emw == pytest.approx(rho, rel=1e-10)


def test_equivalent_mud_weight_fixed_external_reference():
    # Independent, fixed reference values (not derived from any units.*
    # function call): P = 19,613,300 Pa, TVD = 2,000 m, g = 9.80665 m/s^2.
    # By construction this is exactly rho=1000 kg/m3 * g=9.80665 * TVD=2000
    # = 19,613,300 Pa, so the expected EMW is exactly 1000 kg/m3.
    pressure_pa = 19613300.0
    tvd_m = 2000.0
    gravity_m_s2 = 9.80665
    expected_emw_kgm3 = 1000.0
    emw = units.equivalent_mud_weight_kgm3(pressure_pa, tvd_m, gravity_m_s2=gravity_m_s2)
    assert emw == pytest.approx(expected_emw_kgm3, rel=1e-10)


def test_equivalent_mud_weight_array_broadcast():
    p = np.array([1.0e7, 2.0e7])
    tvd = np.array([1000.0, 2000.0])
    emw = units.equivalent_mud_weight_kgm3(p, tvd)
    expected = p / (units.CONST.STANDARD_GRAVITY * tvd)
    np.testing.assert_allclose(emw, expected, rtol=1e-12)


def test_equivalent_mud_weight_rejects_zero_tvd():
    with pytest.raises(ValueError):
        units.equivalent_mud_weight_kgm3(1.0e7, 0.0)


def test_equivalent_mud_weight_rejects_negative_pressure():
    with pytest.raises(ValueError):
        units.equivalent_mud_weight_kgm3(-1.0, 1000.0)


def test_equivalent_mud_weight_nan_preserved():
    p = np.array([1.0e7, np.nan])
    tvd = np.array([1000.0, 1000.0])
    out = units.equivalent_mud_weight_kgm3(p, tvd)
    assert np.isnan(out[1])
    assert np.isfinite(out[0])


# ---------------------------------------------------------------------------
# Seismic time: OWT <-> TWT
# ---------------------------------------------------------------------------
def test_owt_twt_analytical():
    assert units.owt_to_twt(500.0) == pytest.approx(1000.0, abs=1e-9)
    assert units.twt_to_owt(1000.0) == pytest.approx(500.0, abs=1e-9)


def test_owt_twt_round_trip_array():
    owt = np.array([0.0, 250.5, 1267.8, 4700.0])
    back = units.twt_to_owt(units.owt_to_twt(owt))
    np.testing.assert_allclose(back, owt, rtol=1e-12)


def test_owt_twt_rejects_negative_time():
    with pytest.raises(ValueError):
        units.owt_to_twt(-1.0)
    with pytest.raises(ValueError):
        units.twt_to_owt(np.array([10.0, -5.0]))


def test_owt_twt_nan_preserved():
    arr = np.array([100.0, np.nan])
    out = units.owt_to_twt(arr)
    assert np.isnan(out[1])


# ---------------------------------------------------------------------------
# Ambiguous-input rejection: booleans, strings (including numeric-looking
# strings), string arrays, and complex values must be rejected outright
# with a clear TypeError rather than silently coerced. Exercised across a
# representative sample of functions, not just one.
# ---------------------------------------------------------------------------
AMBIGUOUS_INPUT_FUNCTIONS = [
    units.feet_to_meters,
    units.gcc_to_kgm3,
    units.psi_to_pa,
    units.degrees_to_radians,
    units.ppg_to_kgm3,
    units.us_per_ft_to_m_per_s,
]


@pytest.mark.parametrize("func", AMBIGUOUS_INPUT_FUNCTIONS)
def test_rejects_boolean_scalar(func):
    with pytest.raises(TypeError):
        func(True)
    with pytest.raises(TypeError):
        func(False)


@pytest.mark.parametrize("func", AMBIGUOUS_INPUT_FUNCTIONS)
def test_rejects_boolean_array(func):
    with pytest.raises(TypeError):
        func(np.array([True, False]))


@pytest.mark.parametrize("func", AMBIGUOUS_INPUT_FUNCTIONS)
def test_rejects_numeric_string_scalar(func):
    with pytest.raises(TypeError):
        func("3.5")  # a numeric-looking string must still be rejected


@pytest.mark.parametrize("func", AMBIGUOUS_INPUT_FUNCTIONS)
def test_rejects_string_array(func):
    with pytest.raises(TypeError):
        func(np.array(["1.0", "2.0"]))


@pytest.mark.parametrize("func", AMBIGUOUS_INPUT_FUNCTIONS)
def test_rejects_complex_scalar(func):
    with pytest.raises(TypeError):
        func(1.0 + 2.0j)


@pytest.mark.parametrize("func", AMBIGUOUS_INPUT_FUNCTIONS)
def test_rejects_complex_array(func):
    with pytest.raises(TypeError):
        func(np.array([1.0 + 2.0j, 3.0 + 0.0j]))


def test_gravity_parameter_rejects_boolean():
    # The gravity_m_s2 keyword argument on the three hydrostatic functions
    # is a plain scalar, not routed through _to_array, so it is validated
    # separately - confirm it is covered too.
    with pytest.raises(TypeError):
        units.density_to_pressure_gradient(1000.0, gravity_m_s2=True)
    with pytest.raises(TypeError):
        units.pressure_gradient_to_density(9806.65, gravity_m_s2=True)
    with pytest.raises(TypeError):
        units.equivalent_mud_weight_kgm3(1.0e7, 1000.0, gravity_m_s2=False)


def test_ambiguous_rejection_does_not_break_valid_numeric_input():
    # Confirm the stricter type checks did not collaterally break ordinary
    # Python numeric scalars, NumPy integer arrays, or NaN preservation.
    assert units.feet_to_meters(10) == pytest.approx(3.048, rel=1e-9)  # python int
    int_arr = np.array([1, 2, 3], dtype=np.int64)
    out = units.gcc_to_kgm3(int_arr)
    np.testing.assert_allclose(out, np.array([1000.0, 2000.0, 3000.0]))
    nan_arr = np.array([1.0, np.nan])
    assert np.isnan(units.psi_to_pa(nan_arr)[1])


# ---------------------------------------------------------------------------
# Cross-cutting: scalar/array type contract enforced on a representative
# sample of functions (not just length conversions).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "func,scalar_arg",
    [
        (units.gcc_to_kgm3, 2.5),
        (units.psi_to_pa, 1000.0),
        (units.degrees_to_radians, 45.0),
        (units.ppg_to_kgm3, 10.0),
        (units.us_per_ft_to_m_per_s, 100.0),
    ],
)
def test_scalar_in_scalar_out_contract(func, scalar_arg):
    result = func(scalar_arg)
    assert isinstance(result, float)


@pytest.mark.parametrize(
    "func,array_arg",
    [
        (units.gcc_to_kgm3, np.array([2.5, 2.6])),
        (units.psi_to_pa, np.array([1000.0, 2000.0])),
        (units.degrees_to_radians, np.array([45.0, 90.0])),
        (units.ppg_to_kgm3, np.array([10.0, 12.0])),
        (units.us_per_ft_to_m_per_s, np.array([100.0, 150.0])),
    ],
)
def test_array_in_array_out_contract(func, array_arg):
    result = func(array_arg)
    assert isinstance(result, np.ndarray)
    assert result.shape == array_arg.shape
