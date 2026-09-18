"""
tests/test_trajectory.py - Validation suite for p2mem.trajectory
(Increment 3: minimum-curvature trajectory computation).

These are PORTABLE, synthetic-data unit tests: no real project deviation
file is required. Real four-well integration (which DOES require the
private/raw project deviation files) is a separate notebook/script run.
"""

import numpy as np
import pytest

from p2mem.trajectory import (
    MinimumCurvatureResult,
    TrajectoryComputationError,
    compute_minimum_curvature_trajectory,
    dogleg_angle_rad,
    minimum_curvature_intervals,
    ratio_factor,
)
from p2mem.units import degrees_to_radians


# ---------------------------------------------------------------------------
# Ratio-factor limit / numerical stability
# ---------------------------------------------------------------------------
def test_ratio_factor_exact_zero_dogleg_returns_one():
    rf = ratio_factor(np.array([0.0]))
    assert rf[0] == pytest.approx(1.0, abs=0.0)


def test_ratio_factor_taylor_and_direct_branches_agree_at_threshold():
    # Just below and just above the small-dogleg threshold should agree
    # to high precision (continuity of the piecewise definition).
    from p2mem.trajectory import _SMALL_DOGLEG_THRESHOLD_RAD as THRESH

    below = ratio_factor(np.array([THRESH * 0.5]))[0]
    above = ratio_factor(np.array([THRESH * 2.0]))[0]
    assert below == pytest.approx(1.0, abs=1e-12)
    assert above == pytest.approx(1.0, abs=1e-12)
    assert abs(below - above) < 1e-12


def test_ratio_factor_extremely_small_dogleg_is_numerically_stable():
    beta = np.array([1e-12, 1e-10, 1e-9, 1e-8])
    rf = ratio_factor(beta)
    assert np.all(np.isfinite(rf))
    assert np.allclose(rf, 1.0, atol=1e-10)


def test_ratio_factor_known_value_at_moderate_dogleg():
    # RF at beta = 1 radian: (2/1)*tan(0.5) computed independently via math.
    import math

    beta = np.array([1.0])
    expected = (2.0 / 1.0) * math.tan(0.5)
    assert ratio_factor(beta)[0] == pytest.approx(expected, rel=1e-12)


# ---------------------------------------------------------------------------
# Dogleg angle: analytical / independent cross-checks
# ---------------------------------------------------------------------------
def test_dogleg_angle_zero_when_stations_identical_direction():
    beta = dogleg_angle_rad(
        np.array([30.0]), np.array([30.0]), np.array([45.0]), np.array([45.0])
    )
    assert beta[0] == pytest.approx(0.0, abs=1e-12)


def test_dogleg_angle_identical_nonvertical_direction_is_exact_zero_machine_precision():
    # Increment 3.1 correction: the arctan2(|u1 x u2|, u1 . u2) formulation
    # must report EXACTLY 0.0 (bit-for-bit, not merely "very small") for
    # two stations with identical, nonvertical inclination and azimuth,
    # across a range of angle values - not just the one value spot-checked
    # above. The previous arccos(cos_beta) formulation could not meet this
    # bar (it left a ~1e-6-degree noise floor even for identical stations).
    for incl_deg, azim_deg in [
        (5.0, 0.0), (30.0, 45.0), (60.0, 123.4), (89.9, 270.0), (10.0, 359.999),
    ]:
        beta = dogleg_angle_rad(
            np.array([incl_deg]), np.array([incl_deg]), np.array([azim_deg]), np.array([azim_deg])
        )
        assert beta[0] == 0.0, f"expected exact 0.0 for incl={incl_deg}, azim={azim_deg}, got {beta[0]!r}"


def test_dogleg_angle_preserves_genuinely_tiny_nonzero_dogleg():
    # A genuinely tiny (but real) inclination change must NOT be erased by
    # the numerically stable formulation - it must be resolved accurately,
    # not rounded down to 0.0 the way a naive "if very small, call it zero"
    # implementation might.
    tiny_deg = 1.0e-6
    beta = dogleg_angle_rad(
        np.array([30.0]), np.array([30.0 + tiny_deg]), np.array([45.0]), np.array([45.0])
    )
    beta_deg = np.rad2deg(beta[0])
    assert beta_deg > 0.0
    assert beta_deg == pytest.approx(tiny_deg, rel=1e-6)


def test_dogleg_angle_from_vertical_equals_inclination_independent_of_azimuth():
    # I1 = 0 (vertical): sin(I1) = 0, so the azimuth cross-term vanishes
    # regardless of A1 or A2 - dogleg from vertical to (I2, A2) must equal
    # I2 exactly, for ANY A1/A2 pair.
    for a1, a2 in [(0.0, 0.0), (0.0, 90.0), (123.4, 987.6), (0.0, 359.999)]:
        beta = dogleg_angle_rad(
            np.array([0.0]), np.array([17.5]), np.array([a1]), np.array([a2])
        )
        assert beta[0] == pytest.approx(np.deg2rad(17.5), abs=1e-10)


def test_azimuth_undefined_at_zero_inclination_does_not_inflate_dogleg():
    # A vertical station (I=0) carrying an arbitrary placeholder azimuth
    # must not itself generate a spurious "azimuth discontinuity" dogleg.
    # Two consecutive vertical stations with wildly different recorded
    # azimuths must show dogleg == 0 (both inclinations are 0).
    beta = dogleg_angle_rad(
        np.array([0.0]), np.array([0.0]), np.array([12.3]), np.array([321.9])
    )
    assert beta[0] == pytest.approx(0.0, abs=1e-12)


def test_dogleg_angle_matches_independent_direction_cosine_dot_product():
    # Independent cross-check: the tangent unit vector at a station is
    # (sin I cos A, sin I sin A, cos I) in (N, E, Down); the dogleg angle
    # between two stations is the angle between their tangent vectors,
    # i.e. arccos(t1 . t2). This is mathematically the same quantity as
    # the trig identity used in dogleg_angle_rad, computed via a
    # completely independent expression (a 3-vector dot product) - a
    # coding bug in the trig implementation (index swap, sign error,
    # degree/radian mixup) would not, in general, also satisfy this
    # independent check.
    rng = np.random.default_rng(42)
    incl1 = rng.uniform(0, 60, size=25)
    incl2 = rng.uniform(0, 60, size=25)
    azim1 = rng.uniform(0, 360, size=25)
    azim2 = rng.uniform(0, 360, size=25)

    beta = dogleg_angle_rad(incl1, incl2, azim1, azim2)

    i1r = np.deg2rad(incl1)
    i2r = np.deg2rad(incl2)
    a1r = np.deg2rad(azim1)
    a2r = np.deg2rad(azim2)
    t1 = np.stack([np.sin(i1r) * np.cos(a1r), np.sin(i1r) * np.sin(a1r), np.cos(i1r)], axis=-1)
    t2 = np.stack([np.sin(i2r) * np.cos(a2r), np.sin(i2r) * np.sin(a2r), np.cos(i2r)], axis=-1)
    dot = np.clip(np.sum(t1 * t2, axis=-1), -1.0, 1.0)
    beta_independent = np.arccos(dot)

    assert np.allclose(beta, beta_independent, atol=1e-10)


def test_dogleg_angle_azimuth_wraparound_gives_small_dogleg():
    # 359 deg -> 1 deg is a true azimuth change of only 2 degrees, not 358.
    beta_wrap = dogleg_angle_rad(
        np.array([30.0]), np.array([30.0]), np.array([359.0]), np.array([1.0])
    )
    beta_direct_2deg = dogleg_angle_rad(
        np.array([30.0]), np.array([30.0]), np.array([0.0]), np.array([2.0])
    )
    assert beta_wrap[0] == pytest.approx(beta_direct_2deg[0], abs=1e-12)
    assert np.rad2deg(beta_wrap[0]) < 5.0  # small, not ~358 deg


def test_ratio_factor_stable_for_dogleg_computed_near_vertical_wraparound_case():
    # End-to-end check that a tiny dogleg produced by the (Increment 3.1)
    # numerically stable dogleg computation still feeds cleanly into
    # ratio_factor's small-angle Taylor branch, for a near-vertical survey
    # with an azimuth wraparound (azimuth is poorly defined near vertical,
    # so this exercises both edge cases at once).
    beta = dogleg_angle_rad(
        np.array([0.05]), np.array([0.05]), np.array([359.5]), np.array([0.5])
    )
    rf = ratio_factor(beta)
    assert np.all(np.isfinite(rf))
    assert rf[0] == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Minimum-curvature displacement: closed-form / independent checks
# ---------------------------------------------------------------------------
def test_fully_vertical_well_tvd_equals_md_zero_horizontal_offset():
    md = np.array([0.0, 500.0, 1000.0, 1500.0])
    incl = np.zeros_like(md)
    azim = np.zeros_like(md)  # undefined but harmless at incl == 0
    result = compute_minimum_curvature_trajectory(
        md, incl, azim, tvd_origin_m=0.0, northing_origin_m=0.0, easting_origin_m=0.0
    )
    assert np.allclose(result.tvd_mc_m, md, atol=1e-9)
    assert np.allclose(result.northing_offset_mc_m, 0.0, atol=1e-9)
    assert np.allclose(result.easting_offset_mc_m, 0.0, atol=1e-9)
    assert np.allclose(result.dogleg_deg, 0.0, atol=1e-9)


def test_constant_inclination_straight_trajectory_matches_closed_form():
    # Straight tangent hold section (I, A constant): dogleg == 0 exactly,
    # RF == 1 exactly, so minimum curvature reduces to the simple
    # closed-form tangential displacement:
    #   dTVD = dMD cos(I); dN = dMD sin(I) cos(A); dE = dMD sin(I) sin(A)
    md = np.array([0.0, 100.0, 250.0, 400.0])
    incl = np.full_like(md, 40.0)
    azim = np.full_like(md, 70.0)
    result = compute_minimum_curvature_trajectory(
        md, incl, azim, tvd_origin_m=0.0, northing_origin_m=0.0, easting_origin_m=0.0
    )
    i = np.deg2rad(40.0)
    a = np.deg2rad(70.0)
    expected_tvd = md * np.cos(i)
    expected_n = md * np.sin(i) * np.cos(a)
    expected_e = md * np.sin(i) * np.sin(a)
    assert np.allclose(result.tvd_mc_m, expected_tvd, atol=1e-9)
    assert np.allclose(result.northing_offset_mc_m, expected_n, atol=1e-9)
    assert np.allclose(result.easting_offset_mc_m, expected_e, atol=1e-9)
    # Increment 3.1: dogleg_deg is now computed via the numerically stable
    # arctan2(|u1 x u2|, u1 . u2) formulation (see p2mem.trajectory module
    # docstring, "Numerical stability of the dogleg angle"), which reports
    # EXACTLY 0.0 for identical (I, A) stations - no residual noise floor
    # remains (the previous arccos(cos_beta) formulation left a ~1e-6-deg
    # spurious noise floor here, tolerated at the time via atol=1e-5; that
    # tolerance is tightened back down now that the root cause is fixed).
    assert np.array_equal(result.dogleg_deg, np.zeros_like(result.dogleg_deg))
    assert np.array_equal(result.dls_deg_per_30m, np.zeros_like(result.dls_deg_per_30m))


def test_correct_north_east_sign_convention_by_azimuth_quadrant():
    # Azimuth 0 (north): pure +N, ~0 E. Azimuth 90 (east): pure +E, ~0 N.
    # Azimuth 180 (south): pure -N. Azimuth 270 (west): pure -E.
    md = np.array([0.0, 100.0])
    incl = np.array([0.0, 30.0])
    for azim_val, expect_n_sign, expect_e_sign in [
        (0.0, +1, 0),
        (90.0, 0, +1),
        (180.0, -1, 0),
        (270.0, 0, -1),
    ]:
        azim = np.array([azim_val, azim_val])
        result = compute_minimum_curvature_trajectory(
            md, incl, azim, tvd_origin_m=0.0, northing_origin_m=0.0, easting_origin_m=0.0
        )
        n_final, e_final = result.northing_offset_mc_m[-1], result.easting_offset_mc_m[-1]
        if expect_n_sign > 0:
            assert n_final > 1.0
        elif expect_n_sign < 0:
            assert n_final < -1.0
        else:
            assert abs(n_final) < 1e-6
        if expect_e_sign > 0:
            assert e_final > 1.0
        elif expect_e_sign < 0:
            assert e_final < -1.0
        else:
            assert abs(e_final) < 1e-6


def test_dls_degrees_per_30m_known_value():
    # Two stations 30 m apart with a dogleg of exactly 3 degrees (achieved
    # via a pure inclination build at constant azimuth, so beta == the
    # inclination change) should report DLS == 3.0 deg/30m exactly.
    md = np.array([1000.0, 1030.0])
    incl = np.array([10.0, 13.0])
    azim = np.array([0.0, 0.0])
    beta_deg, rf, d_tvd, d_n, d_e = minimum_curvature_intervals(md, incl, azim)
    assert beta_deg[0] == pytest.approx(3.0, abs=1e-9)
    dls = (beta_deg[0] / (md[1] - md[0])) * 30.0
    assert dls == pytest.approx(3.0, abs=1e-9)


def test_dls_scales_inversely_with_interval_length_for_fixed_dogleg():
    # Same 3-degree dogleg over 15 m instead of 30 m -> DLS doubles.
    md = np.array([1000.0, 1015.0])
    incl = np.array([10.0, 13.0])
    azim = np.array([0.0, 0.0])
    beta_deg, *_ = minimum_curvature_intervals(md, incl, azim)
    dls = (beta_deg[0] / (md[1] - md[0])) * 30.0
    assert dls == pytest.approx(6.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Origin initialization
# ---------------------------------------------------------------------------
def test_origin_values_are_used_as_station_zero_not_hard_coded_zero():
    # Proteus-style tiny nonzero first-station origin must be preserved
    # exactly as the trajectory's starting condition.
    md = np.array([-7.63e-7, 500.0])
    incl = np.array([0.0, 5.0])
    azim = np.array([0.0, 45.0])
    result = compute_minimum_curvature_trajectory(
        md,
        incl,
        azim,
        tvd_origin_m=-7.63e-7,
        northing_origin_m=-1e-6,
        easting_origin_m=2e-6,
    )
    assert result.tvd_mc_m[0] == -7.63e-7
    assert result.northing_offset_mc_m[0] == -1e-6
    assert result.easting_offset_mc_m[0] == 2e-6


def test_scalar_result_shapes_and_types_are_ndarrays():
    md = np.array([0.0, 100.0, 200.0])
    incl = np.array([0.0, 10.0, 20.0])
    azim = np.array([0.0, 30.0, 30.0])
    result = compute_minimum_curvature_trajectory(
        md, incl, azim, tvd_origin_m=0.0, northing_origin_m=0.0, easting_origin_m=0.0
    )
    assert isinstance(result, MinimumCurvatureResult)
    for arr in (
        result.dogleg_deg,
        result.dls_deg_per_30m,
        result.tvd_mc_m,
        result.northing_offset_mc_m,
        result.easting_offset_mc_m,
    ):
        assert isinstance(arr, np.ndarray)
        assert arr.shape == (3,)
    assert result.dogleg_deg[0] == 0.0
    assert result.dls_deg_per_30m[0] == 0.0


# ---------------------------------------------------------------------------
# Rejection of nonphysical / structurally invalid input
# ---------------------------------------------------------------------------
def test_rejects_inclination_above_180():
    with pytest.raises(TrajectoryComputationError, match="physically valid range"):
        compute_minimum_curvature_trajectory(
            np.array([0.0, 100.0]),
            np.array([0.0, 181.0]),
            np.array([0.0, 0.0]),
            tvd_origin_m=0.0,
            northing_origin_m=0.0,
            easting_origin_m=0.0,
        )


def test_rejects_negative_inclination():
    with pytest.raises(TrajectoryComputationError, match="physically valid range"):
        compute_minimum_curvature_trajectory(
            np.array([0.0, 100.0]),
            np.array([0.0, -5.0]),
            np.array([0.0, 0.0]),
            tvd_origin_m=0.0,
            northing_origin_m=0.0,
            easting_origin_m=0.0,
        )


def test_rejects_non_increasing_md():
    with pytest.raises(TrajectoryComputationError, match="strictly increasing"):
        compute_minimum_curvature_trajectory(
            np.array([0.0, 100.0, 100.0]),
            np.array([0.0, 5.0, 6.0]),
            np.array([0.0, 10.0, 10.0]),
            tvd_origin_m=0.0,
            northing_origin_m=0.0,
            easting_origin_m=0.0,
        )


def test_rejects_decreasing_md():
    with pytest.raises(TrajectoryComputationError, match="strictly increasing"):
        compute_minimum_curvature_trajectory(
            np.array([0.0, 200.0, 100.0]),
            np.array([0.0, 5.0, 6.0]),
            np.array([0.0, 10.0, 10.0]),
            tvd_origin_m=0.0,
            northing_origin_m=0.0,
            easting_origin_m=0.0,
        )


def test_rejects_nan_policy_non_finite_md():
    with pytest.raises(TrajectoryComputationError, match="non-finite"):
        compute_minimum_curvature_trajectory(
            np.array([0.0, np.nan, 200.0]),
            np.array([0.0, 5.0, 6.0]),
            np.array([0.0, 10.0, 10.0]),
            tvd_origin_m=0.0,
            northing_origin_m=0.0,
            easting_origin_m=0.0,
        )


def test_rejects_infinite_azimuth():
    with pytest.raises(TrajectoryComputationError, match="non-finite"):
        compute_minimum_curvature_trajectory(
            np.array([0.0, 100.0]),
            np.array([0.0, 5.0]),
            np.array([0.0, np.inf]),
            tvd_origin_m=0.0,
            northing_origin_m=0.0,
            easting_origin_m=0.0,
        )


def test_rejects_mismatched_array_shapes():
    with pytest.raises(TrajectoryComputationError, match="shape"):
        compute_minimum_curvature_trajectory(
            np.array([0.0, 100.0, 200.0]),
            np.array([0.0, 5.0]),
            np.array([0.0, 10.0, 10.0]),
            tvd_origin_m=0.0,
            northing_origin_m=0.0,
            easting_origin_m=0.0,
        )


def test_single_station_trajectory_returns_origin_only():
    md = np.array([500.0])
    incl = np.array([12.0])
    azim = np.array([45.0])
    result = compute_minimum_curvature_trajectory(
        md, incl, azim, tvd_origin_m=500.0, northing_origin_m=1.0, easting_origin_m=2.0
    )
    assert result.tvd_mc_m[0] == 500.0
    assert result.northing_offset_mc_m[0] == 1.0
    assert result.easting_offset_mc_m[0] == 2.0
    assert result.dogleg_deg[0] == 0.0
