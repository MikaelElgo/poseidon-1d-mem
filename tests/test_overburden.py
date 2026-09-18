"""
Increment 7 - vertical-stress integration, sign convention, eligibility
derivation, scenarios, and gap-threshold sensitivity.

Every analytical expectation here is computed by hand from `rho * g * h`, not
from the implementation. A test that compared the code against itself would
prove only that the code is deterministic.
"""

from __future__ import annotations

from dataclasses import replace
import math

import numpy as np
import pytest

from p2mem.density_qc import build_density_masks, condition_density_gaps
from p2mem.overburden import (
    SIGN_CONVENTION_ID,
    build_gap_threshold_sensitivity,
    build_shallow_column_scenarios,
    build_stress_profile,
    derive_overburden_eligibility,
    integrate_vertical_stress,
    pa_to_mpa,
    uniform_column_stress_pa,
    verify_depth_sign_convention,
    water_column_stress_pa,
)
from p2mem.overburden_models import (
    REASON_INSUFFICIENT_ELIGIBLE_SAMPLES,
    REASON_INTERNAL_GAP_EXCEEDS_LIMIT,
    REASON_RHOB_NOT_AVAILABLE,
    REASON_SEABED_DATUM_UNRESOLVED,
    REASON_SHALLOW_COLUMN_UNRESOLVED,
    REASON_TERMINAL_COLUMN_UNRESOLVED,
    STATUS_ABSOLUTE,
    STATUS_NOT_ELIGIBLE,
    STATUS_PARTIAL_ONLY,
    STATUS_SENSITIVITY_ONLY,
    OverburdenInputError,
    StressPartition,
    VerticalStressProfile,
)

from helpers_inc7 import overburden_config, prepared  # noqa: E402
from synthetic_inc7 import (  # noqa: E402
    STANDARD_G, constant_density_frame, gap_frame, make_frame, two_layer_frame,
)


# ---------------------------------------------------------------------------
# Analytical integration
# ---------------------------------------------------------------------------

def test_constant_density_integration_is_exact():
    """A constant integrand: trapezoidal quadrature must be EXACT."""
    z = np.arange(0.0, 101.0, 1.0)
    rho = np.full(z.size, 2000.0)
    cum, n_zero = integrate_vertical_stress(rho, z, STANDARD_G)
    assert n_zero == 0
    assert cum[0] == 0.0
    assert math.isclose(float(cum[-1]), 2000.0 * STANDARD_G * 100.0, rel_tol=1e-12)
    # Every intermediate value must also be exact, not merely the total.
    for i in (1, 17, 50, 99):
        assert math.isclose(float(cum[i]), 2000.0 * STANDARD_G * float(z[i]),
                            rel_tol=1e-12)


def test_two_layer_integration_matches_hand_computed_sum():
    z = np.concatenate([np.arange(0.0, 51.0, 1.0), np.arange(51.0, 101.0, 1.0)])
    rho = np.where(z <= 50.0, 2000.0, 2500.0)
    cum, _ = integrate_vertical_stress(rho, z, STANDARD_G)
    # Layer 1 is exact. The 50->51 m interval straddles the contrast and the
    # trapezoid averages the two densities, which is the correct value for a
    # piecewise-linear density profile through those two nodes.
    upper = 2000.0 * STANDARD_G * 50.0
    straddle = 0.5 * (2000.0 + 2500.0) * STANDARD_G * 1.0
    lower = 2500.0 * STANDARD_G * 49.0
    assert math.isclose(float(cum[-1]), upper + straddle + lower, rel_tol=1e-12)


def test_water_column_plus_formation_sum_is_the_hand_computed_total():
    water = water_column_stress_pa(500.0, 1025.0, STANDARD_G)
    assert math.isclose(water, 1025.0 * STANDARD_G * 500.0, rel_tol=1e-15)
    z = np.arange(500.0, 601.0, 1.0)
    rho = np.full(z.size, 2200.0)
    cum, _ = integrate_vertical_stress(rho, z, STANDARD_G)
    total = water + float(cum[-1])
    assert math.isclose(
        total, 1025.0 * STANDARD_G * 500.0 + 2200.0 * STANDARD_G * 100.0,
        rel_tol=1e-12)


def test_integration_in_tvd_differs_from_integration_in_md_for_a_deviated_well():
    """The whole point of integrating in TVD, demonstrated numerically."""
    md = np.arange(0.0, 101.0, 1.0)
    tvd = md * 0.8            # 36.87 degrees from vertical, constant
    rho = np.full(md.size, 2400.0)
    cum_tvd, _ = integrate_vertical_stress(rho, tvd, STANDARD_G)
    cum_md, _ = integrate_vertical_stress(rho, md, STANDARD_G)
    assert math.isclose(float(cum_tvd[-1]), 2400.0 * STANDARD_G * 80.0, rel_tol=1e-12)
    assert math.isclose(float(cum_md[-1]), 2400.0 * STANDARD_G * 100.0, rel_tol=1e-12)
    # Integrating in MD would overstate the stress by exactly 1/0.8.
    assert float(cum_md[-1]) > float(cum_tvd[-1])
    assert math.isclose(float(cum_md[-1]) / float(cum_tvd[-1]), 1.25, rel_tol=1e-12)


def test_repeated_vertical_coordinate_contributes_exactly_zero_and_is_counted():
    z = np.array([0.0, 10.0, 10.0, 20.0])
    rho = np.array([2000.0, 2000.0, 2000.0, 2000.0])
    cum, n_zero = integrate_vertical_stress(rho, z, STANDARD_G)
    assert n_zero == 1
    assert float(cum[1]) == float(cum[2])           # the repeat adds nothing
    assert math.isclose(float(cum[-1]), 2000.0 * STANDARD_G * 20.0, rel_tol=1e-12)


def test_zero_thickness_whole_column_gives_exactly_zero_stress():
    z = np.zeros(5)
    rho = np.full(5, 2500.0)
    cum, n_zero = integrate_vertical_stress(rho, z, STANDARD_G)
    assert n_zero == 4
    assert float(cum[-1]) == 0.0


def test_decreasing_vertical_coordinate_is_rejected_not_sorted():
    z = np.array([0.0, 10.0, 5.0, 20.0])
    rho = np.full(4, 2000.0)
    with pytest.raises(OverburdenInputError, match="negative vertical increment"):
        integrate_vertical_stress(rho, z, STANDARD_G)


def test_fully_reversed_vertical_coordinate_is_rejected():
    z = np.array([100.0, 75.0, 50.0, 25.0])
    with pytest.raises(OverburdenInputError):
        integrate_vertical_stress(np.full(4, 2000.0), z, STANDARD_G)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_non_finite_density_reaches_no_integral(bad):
    rho = np.array([2000.0, bad, 2000.0])
    with pytest.raises(OverburdenInputError, match="non-finite density"):
        integrate_vertical_stress(rho, np.array([0.0, 1.0, 2.0]), STANDARD_G)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_non_finite_vertical_depth_reaches_no_integral(bad):
    z = np.array([0.0, bad, 2.0])
    with pytest.raises(OverburdenInputError, match="non-finite vertical-depth"):
        integrate_vertical_stress(np.full(3, 2000.0), z, STANDARD_G)


@pytest.mark.parametrize("value", [0.0, -1.0, -2500.0])
def test_non_positive_density_is_rejected(value):
    rho = np.array([2000.0, value, 2000.0])
    with pytest.raises(OverburdenInputError, match="non-positive density"):
        integrate_vertical_stress(rho, np.array([0.0, 1.0, 2.0]), STANDARD_G)


@pytest.mark.parametrize("arr", [
    np.array([True, False, True]),
    np.array(["a", "b", "c"]),
    np.array([b"a", b"b", b"c"]),
    np.array([1 + 2j, 2 + 0j, 3 + 0j]),
    np.array([object(), object(), object()], dtype=object),
])
def test_ambiguous_dtype_density_raises_typeerror(arr):
    with pytest.raises(TypeError):
        integrate_vertical_stress(arr, np.array([0.0, 1.0, 2.0]), STANDARD_G)


@pytest.mark.parametrize("arr", [
    np.array([True, False, True]),
    np.array(["0", "1", "2"]),
    np.array([0 + 0j, 1 + 0j, 2 + 0j]),
])
def test_ambiguous_dtype_depth_raises_typeerror(arr):
    with pytest.raises(TypeError):
        integrate_vertical_stress(np.full(3, 2000.0), arr, STANDARD_G)


def test_boolean_gravity_is_a_typeerror_not_a_silent_one():
    with pytest.raises(TypeError):
        integrate_vertical_stress(np.full(3, 2000.0), np.array([0.0, 1.0, 2.0]), True)


@pytest.mark.parametrize("gravity", ["9.80665", b"9.80665", 9.80665 + 0j, [9.80665]])
def test_non_real_scalar_gravity_is_rejected_without_coercion(gravity):
    with pytest.raises(TypeError, match="real numeric scalar"):
        integrate_vertical_stress(
            np.full(3, 2000.0), np.array([0.0, 1.0, 2.0]), gravity)


@pytest.mark.parametrize("g", [0.0, -9.80665, float("nan"), float("inf")])
def test_invalid_gravity_is_rejected(g):
    with pytest.raises(OverburdenInputError):
        integrate_vertical_stress(np.full(3, 2000.0), np.array([0.0, 1.0, 2.0]), g)


def test_length_mismatch_is_never_reconciled_by_truncation():
    with pytest.raises(OverburdenInputError, match="never truncates"):
        integrate_vertical_stress(np.full(5, 2000.0), np.arange(4.0), STANDARD_G)


def test_single_sample_cannot_form_a_trapezoid():
    with pytest.raises(OverburdenInputError, match="at least two samples"):
        integrate_vertical_stress(np.array([2000.0]), np.array([0.0]), STANDARD_G)


def test_integration_does_not_mutate_its_inputs():
    rho = np.array([2000.0, 2100.0, 2200.0])
    z = np.array([0.0, 1.0, 2.0])
    rho_before, z_before = rho.copy(), z.copy()
    integrate_vertical_stress(rho, z, STANDARD_G)
    assert np.array_equal(rho, rho_before)
    assert np.array_equal(z, z_before)


def test_returned_cumulative_array_is_read_only():
    cum, _ = integrate_vertical_stress(
        np.full(3, 2000.0), np.array([0.0, 1.0, 2.0]), STANDARD_G)
    assert not cum.flags.writeable
    with pytest.raises(ValueError):
        cum[0] = 1.0


def test_integration_is_deterministic_across_repeated_calls():
    rho = np.linspace(1900.0, 2600.0, 257)
    z = np.linspace(0.0, 256.0, 257)
    first, _ = integrate_vertical_stress(rho, z, STANDARD_G)
    for _ in range(3):
        again, _ = integrate_vertical_stress(rho, z, STANDARD_G)
        assert np.array_equal(np.asarray(first), np.asarray(again))


# ---------------------------------------------------------------------------
# Uniform-column helpers
# ---------------------------------------------------------------------------

def test_uniform_column_matches_rho_g_h():
    assert math.isclose(uniform_column_stress_pa(120.0, 1800.0, STANDARD_G),
                        1800.0 * STANDARD_G * 120.0, rel_tol=1e-15)


def test_zero_thickness_uniform_column_is_zero():
    assert uniform_column_stress_pa(0.0, 1025.0, STANDARD_G) == 0.0


def test_negative_thickness_column_is_rejected():
    with pytest.raises(OverburdenInputError):
        uniform_column_stress_pa(-1.0, 1025.0, STANDARD_G)


@pytest.mark.parametrize("args", [
    ("10", 2000.0, STANDARD_G),
    (10.0, "2000", STANDARD_G),
    (10.0, 2000.0, "9.80665"),
    (10.0 + 0j, 2000.0, STANDARD_G),
])
def test_uniform_column_rejects_coercible_non_real_scalars(args):
    with pytest.raises(TypeError, match="real numeric scalar"):
        uniform_column_stress_pa(*args)


def test_pa_to_mpa_is_an_exact_decimal_factor():
    assert pa_to_mpa(1.0e6) == 1.0
    assert pa_to_mpa(None) is None


# ---------------------------------------------------------------------------
# Sign convention
# ---------------------------------------------------------------------------

def test_sign_convention_is_verified_from_the_frames_own_arrays():
    frame = constant_density_frame(datum_elevation_m=25.0)
    ev = verify_depth_sign_convention(frame)
    assert ev["verified"] is True
    assert ev["sign_convention_id"] == SIGN_CONVENTION_ID
    assert ev["datum_elevation_m"] == 25.0
    assert ev["max_tvd_minus_tvdss_deviation_m"] < 1e-9
    assert ev["tvd_increases_downward"] is True


def test_sign_convention_rejects_a_tvdss_that_is_not_tvd_minus_datum():
    md = np.arange(1000.0, 1101.0, 10.0)
    # Deliberately wrong: TVDSS built with the OPPOSITE sign of the datum.
    frame = make_frame(md=md, tvd=md, tvdss=md + 25.0, datum_elevation_m=25.0,
                       density=np.full(md.size, 2000.0))
    with pytest.raises(OverburdenInputError, match="datum elevation"):
        verify_depth_sign_convention(frame)


def test_sign_convention_rejects_a_trajectory_that_rises_with_measured_depth():
    md = np.array([1000.0, 1010.0, 1020.0, 1030.0])
    tvd = np.array([1000.0, 1010.0, 1005.0, 1030.0])
    frame = make_frame(md=md, tvd=tvd, datum_elevation_m=25.0,
                       density=np.full(4, 2000.0))
    with pytest.raises(OverburdenInputError, match="TVD decreases"):
        verify_depth_sign_convention(frame)


def test_sign_convention_needs_at_least_two_mapped_samples():
    md = np.array([1000.0, 1010.0])
    frame = make_frame(md=md, density=np.full(2, 2000.0),
                       depth_valid_mask=np.array([True, False]))
    with pytest.raises(OverburdenInputError, match="fewer than two"):
        verify_depth_sign_convention(frame)


# ---------------------------------------------------------------------------
# Profiles built from real well frames
# ---------------------------------------------------------------------------

def test_profile_over_a_constant_density_frame_is_analytical(overburden_config):
    frame = constant_density_frame(rho=2000.0, n=11, step=10.0)
    p = prepared(frame, overburden_config, seabed_mdrt_m=None)
    profile = p["profile"]
    assert profile is not None
    assert profile.n_nodes == 11
    assert profile.n_intervals == 10
    assert profile.integration_coordinate == "tvdss_m"
    assert math.isclose(profile.total_measured_increment_pa,
                        2000.0 * overburden_config.gravity_m_s2 * 100.0,
                        rel_tol=1e-12)
    assert profile.total_bridged_increment_pa == 0.0
    assert profile.column_truncated_at_unresolved_gap is False


def test_profile_over_a_two_layer_frame_is_analytical(overburden_config):
    frame = two_layer_frame(rho_upper=2000.0, rho_lower=2500.0,
                            n_upper=6, n_lower=6, step=10.0)
    profile = prepared(frame, overburden_config, seabed_mdrt_m=None)["profile"]
    g = overburden_config.gravity_m_s2
    upper = 2000.0 * g * 50.0
    straddle = 0.5 * (2000.0 + 2500.0) * g * 10.0
    lower = 2500.0 * g * 40.0
    assert math.isclose(profile.total_measured_increment_pa,
                        upper + straddle + lower, rel_tol=1e-12)


def test_profile_is_zero_at_the_first_node_by_definition(overburden_config):
    profile = prepared(constant_density_frame(), overburden_config,
                       seabed_mdrt_m=None)["profile"]
    assert float(profile.cumulative_measured_increment_pa[0]) == 0.0


def test_profile_arrays_are_read_only(overburden_config):
    profile = prepared(constant_density_frame(), overburden_config,
                       seabed_mdrt_m=None)["profile"]
    for arr in (profile.md_m, profile.tvd_m, profile.tvdss_m,
                profile.density_kg_m3, profile.cumulative_measured_increment_pa):
        assert not arr.flags.writeable


def test_no_profile_when_only_one_valid_sample_exists(overburden_config):
    md = np.arange(1000.0, 1051.0, 10.0)
    rho = np.full(md.size, np.nan)
    rho[2] = 2200.0
    frame = make_frame(md=md, density=rho)
    assert prepared(frame, overburden_config, seabed_mdrt_m=None)["profile"] is None


def test_no_profile_when_density_is_entirely_invalid(overburden_config):
    md = np.arange(1000.0, 1051.0, 10.0)
    frame = make_frame(md=md, density=np.full(md.size, np.nan))
    assert prepared(frame, overburden_config, seabed_mdrt_m=None)["profile"] is None


def test_no_profile_when_the_well_has_no_density_curve(overburden_config):
    md = np.arange(1000.0, 1051.0, 10.0)
    frame = make_frame(md=md, curves={})
    out = prepared(frame, overburden_config, seabed_mdrt_m=None)
    assert out["profile"] is None
    assert REASON_RHOB_NOT_AVAILABLE in out["eligibility"].limiting_reasons
    assert out["eligibility"].status == STATUS_NOT_ELIGIBLE


def test_profile_never_extrapolates_beyond_the_eligible_interval(overburden_config):
    """The profile's span equals the eligible samples' own span, exactly."""
    md = np.arange(1000.0, 1101.0, 10.0)
    rho = np.full(md.size, 2000.0)
    rho[:3] = np.nan
    rho[-2:] = np.nan
    frame = make_frame(md=md, density=rho)
    profile = prepared(frame, overburden_config, seabed_mdrt_m=None)["profile"]
    assert profile.top_tvd_m == 1030.0
    assert profile.base_tvd_m == 1080.0
    assert profile.n_nodes == 6


def test_survey_coverage_truncates_the_eligible_interval(overburden_config):
    """Samples outside locked survey MD coverage are never integrated."""
    md = np.arange(1000.0, 1101.0, 10.0)
    frame = make_frame(md=md, density=np.full(md.size, 2000.0),
                       survey_md_min_m=1020.0, survey_md_max_m=1080.0)
    out = prepared(frame, overburden_config, seabed_mdrt_m=None)
    profile = out["profile"]
    assert profile.top_tvd_m == 1020.0
    assert profile.base_tvd_m == 1080.0
    assert out["stats"].n_samples_outside_survey_coverage == 4


# ---------------------------------------------------------------------------
# Gaps and truncation
# ---------------------------------------------------------------------------

def test_short_internal_gap_is_bridged_and_reported_separately(overburden_config):
    frame = gap_frame([slice(20, 23)], rho=2000.0, n=41, step=1.0)
    out = prepared(frame, overburden_config, seabed_mdrt_m=None)
    gr, profile = out["gaps"], out["profile"]
    assert gr.n_bridged_gaps == 1
    assert gr.n_bridged_samples == 3
    assert profile.total_bridged_increment_pa > 0.0
    # Constant density either side: bridging reproduces the same constant, so
    # the integral must still be the exact analytical value over 40 m.
    assert math.isclose(profile.total_measured_increment_pa,
                        2000.0 * overburden_config.gravity_m_s2 * 40.0,
                        rel_tol=1e-12)


def test_multiple_short_gaps_in_one_column_are_all_bridged(overburden_config):
    frame = gap_frame([slice(10, 12), slice(20, 23), slice(30, 31)],
                      rho=2000.0, n=41, step=1.0)
    gr = prepared(frame, overburden_config, seabed_mdrt_m=None)["gaps"]
    assert gr.n_bridged_gaps == 3
    assert gr.n_bridged_samples == 6
    assert gr.n_long_gaps == 0


def test_long_internal_gap_is_never_bridged_and_truncates_the_column(
        overburden_config):
    # 15 m of gap against a 10 m approved threshold.
    frame = gap_frame([slice(10, 25)], rho=2000.0, n=41, step=1.0)
    out = prepared(frame, overburden_config, seabed_mdrt_m=None)
    gr, profile, elig = out["gaps"], out["profile"], out["eligibility"]
    assert gr.n_bridged_gaps == 0
    assert gr.n_long_gaps == 1
    assert profile.column_truncated_at_unresolved_gap is True
    assert profile.n_eligible_samples_below_truncation == 16
    # Only the 10 m above the gap is integrated: no silent join across it.
    assert math.isclose(profile.total_measured_increment_pa,
                        2000.0 * overburden_config.gravity_m_s2 * 9.0,
                        rel_tol=1e-12)
    assert REASON_INTERNAL_GAP_EXCEEDS_LIMIT in elig.limiting_reasons
    assert elig.column_uninterrupted is False


def test_unresolved_short_gap_truncates_when_bridging_is_disabled(
        overburden_config):
    """Regression: no trapezoid may jump over an unresolved short gap."""
    config = replace(overburden_config, bridge_short_internal_gaps=False)
    frame = gap_frame([slice(10, 13)], rho=2000.0, n=21, step=1.0)
    out = prepared(frame, config, seabed_mdrt_m=None)
    gap = next(g for g in out["gaps"].gaps if g.gap_class == "short_internal_gap")
    profile = out["profile"]
    assert gap.disposition == "unresolved_not_bridged"
    assert out["gaps"].n_bridged_gaps == 0
    assert profile.column_truncated_at_unresolved_gap is True
    assert profile.n_nodes == 10
    assert profile.n_eligible_samples_below_truncation == 8
    assert math.isclose(
        profile.total_measured_increment_pa,
        2000.0 * config.gravity_m_s2 * 9.0,
        rel_tol=1e-12,
    )
    assert out["eligibility"].column_uninterrupted is False
    assert "internal_gap_unresolved" in out["eligibility"].limiting_reasons


def test_unmapped_internal_gap_also_truncates_the_profile(overburden_config):
    md = np.arange(1000.0, 1021.0, 1.0)
    depth_valid = np.ones(md.size, dtype=bool)
    depth_valid[10:13] = False
    tvd = md.copy()
    tvdss = tvd - 25.0
    tvd[10:13] = np.nan
    tvdss[10:13] = np.nan
    frame = make_frame(
        md=md, tvd=tvd, tvdss=tvdss, density=np.full(md.size, 2000.0),
        depth_valid_mask=depth_valid,
    )
    out = prepared(frame, overburden_config, seabed_mdrt_m=None)
    gap = next(g for g in out["gaps"].gaps
               if g.gap_class == "gap_caused_by_missing_depth_mapping")
    assert gap.disposition == "unresolved_not_bridged"
    assert out["profile"].column_truncated_at_unresolved_gap is True
    assert out["profile"].n_nodes == 10
    assert out["eligibility"].column_uninterrupted is False


def test_an_isolated_invalid_sample_is_a_one_sample_internal_gap(
        overburden_config):
    frame = gap_frame([slice(15, 16)], rho=2000.0, n=41, step=1.0)
    gr = prepared(frame, overburden_config, seabed_mdrt_m=None)["gaps"]
    bridged = [g for g in gr.gaps if g.disposition == "bridged_linear_in_tvd"]
    assert len(bridged) == 1
    assert bridged[0].n_samples == 1


def test_gap_conditioning_does_not_touch_the_original_density_array(
        overburden_config):
    frame = gap_frame([slice(20, 23)], rho=2000.0, n=41, step=1.0)
    original = np.array(frame.curve("RHOB_kg_m3").values, copy=True)
    out = prepared(frame, overburden_config, seabed_mdrt_m=None)
    after = np.asarray(frame.curve("RHOB_kg_m3").values)
    assert np.array_equal(np.isnan(original), np.isnan(after))
    assert np.array_equal(original[~np.isnan(original)], after[~np.isnan(after)])
    # The conditioned array is a DIFFERENT array with the gap filled.
    cond = np.asarray(out["gaps"].conditioned_density_kg_m3)
    assert np.isnan(original[21]) and np.isfinite(cond[21])


def test_bridged_values_are_linear_in_vertical_depth(overburden_config):
    md = np.arange(1000.0, 1011.0, 1.0)
    rho = np.full(md.size, np.nan)
    rho[0] = 2000.0
    rho[10] = 3000.0
    frame = make_frame(md=md, density=rho)
    out = prepared(frame, overburden_config, seabed_mdrt_m=None)
    cond = np.asarray(out["gaps"].conditioned_density_kg_m3)
    # Linear ramp from 2000 to 3000 over 10 m: node i is 2000 + 100*i.
    for i in range(11):
        assert math.isclose(float(cond[i]), 2000.0 + 100.0 * i, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# Eligibility derivation
# ---------------------------------------------------------------------------

def test_absolute_status_when_density_reaches_the_seabed(overburden_config):
    """The only configuration in which an absolute curve is defensible."""
    md = np.arange(500.0, 1001.0, 10.0)
    frame = make_frame(md=md, density=np.full(md.size, 2000.0),
                       datum_elevation_m=25.0)
    out = prepared(frame, overburden_config, seabed_mdrt_m=500.0,
                   seabed_tvd_m=500.0, seabed_tvdss_m=475.0)
    elig = out["eligibility"]
    assert elig.status == STATUS_ABSOLUTE
    assert elig.limiting_reasons == ()
    assert elig.absolute_stress_supported is True


def test_shallow_gap_downgrades_absolute_to_sensitivity_only(overburden_config):
    md = np.arange(1000.0, 1501.0, 10.0)
    frame = make_frame(md=md, density=np.full(md.size, 2000.0))
    out = prepared(frame, overburden_config, seabed_mdrt_m=500.0,
                   seabed_tvd_m=500.0, seabed_tvdss_m=475.0)
    elig = out["eligibility"]
    assert elig.status == STATUS_SENSITIVITY_ONLY
    assert REASON_SHALLOW_COLUMN_UNRESOLVED in elig.limiting_reasons
    assert elig.absolute_stress_supported is False
    assert math.isclose(elig.shallow_unresolved_thickness_tvd_m, 500.0)


def test_unresolved_seabed_gives_partial_measured_increment_only(
        overburden_config):
    frame = constant_density_frame()
    elig = prepared(frame, overburden_config, seabed_mdrt_m=None)["eligibility"]
    assert elig.status == STATUS_PARTIAL_ONLY
    assert REASON_SEABED_DATUM_UNRESOLVED in elig.limiting_reasons
    assert elig.water_column_thickness_tvd_m is None


def test_status_is_derived_from_evidence_not_from_the_well_name(
        overburden_config):
    """The SAME arrays under two different well keys derive the same status."""
    md = np.arange(1000.0, 1101.0, 10.0)
    rho = np.full(md.size, 2000.0)
    a = prepared(make_frame(well_key="ALPHA_1", md=md, density=rho),
                 overburden_config, seabed_mdrt_m=None)["eligibility"]
    b = prepared(make_frame(well_key="OMEGA_9", md=md, density=rho),
                 overburden_config, seabed_mdrt_m=None)["eligibility"]
    assert a.status == b.status
    assert a.limiting_reasons == b.limiting_reasons


def test_limiting_reasons_are_sorted_deduplicated_enumerated_codes(
        overburden_config):
    frame = gap_frame([slice(10, 25)], rho=2000.0, n=41, step=1.0)
    elig = prepared(frame, overburden_config, seabed_mdrt_m=None)["eligibility"]
    assert list(elig.limiting_reasons) == sorted(set(elig.limiting_reasons))
    assert all(isinstance(r, str) and " " not in r for r in elig.limiting_reasons)


def test_terminal_gap_is_reported_but_does_not_block_an_absolute_status(
        overburden_config):
    md = np.arange(500.0, 1001.0, 10.0)
    rho = np.full(md.size, 2000.0)
    rho[-3:] = np.nan
    frame = make_frame(md=md, density=rho, datum_elevation_m=25.0)
    elig = prepared(frame, overburden_config, seabed_mdrt_m=500.0,
                    seabed_tvd_m=500.0, seabed_tvdss_m=475.0)["eligibility"]
    assert elig.status == STATUS_ABSOLUTE
    assert elig.terminal_unresolved_thickness_tvd_m == 30.0


def test_not_eligible_when_fewer_than_two_eligible_samples(overburden_config):
    md = np.arange(1000.0, 1051.0, 10.0)
    rho = np.full(md.size, np.nan)
    rho[1] = 2000.0
    elig = prepared(make_frame(md=md, density=rho), overburden_config,
                    seabed_mdrt_m=None)["eligibility"]
    assert elig.status == STATUS_NOT_ELIGIBLE
    assert REASON_INSUFFICIENT_ELIGIBLE_SAMPLES in elig.limiting_reasons


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def test_scenarios_are_published_only_for_sensitivity_only_wells(
        overburden_config):
    partial = prepared(constant_density_frame(), overburden_config,
                       seabed_mdrt_m=None)
    assert build_shallow_column_scenarios(
        partial["stats"], partial["eligibility"], partial["profile"],
        overburden_config) == ()


def test_scenarios_bracket_low_base_high_and_disclose_all_three_fractions(
        overburden_config):
    md = np.arange(1000.0, 1501.0, 10.0)
    frame = make_frame(md=md, density=np.full(md.size, 2000.0))
    out = prepared(frame, overburden_config, seabed_mdrt_m=500.0,
                   seabed_tvd_m=500.0, seabed_tvdss_m=475.0)
    scen = build_shallow_column_scenarios(
        out["stats"], out["eligibility"], out["profile"], overburden_config)
    by_name = {s.scenario_name: s for s in scen}
    assert {"low", "base", "high"} <= set(by_name)
    lo, base, hi = by_name["low"], by_name["base"], by_name["high"]
    # The bracket is ordered and the base is exactly the midpoint.
    assert (lo.assumed_shallow_density_kg_m3
            < base.assumed_shallow_density_kg_m3
            < hi.assumed_shallow_density_kg_m3)
    assert math.isclose(
        base.assumed_shallow_density_kg_m3,
        0.5 * (lo.assumed_shallow_density_kg_m3 + hi.assumed_shallow_density_kg_m3),
        rel_tol=1e-12)
    assert lo.partition.total_pa < base.partition.total_pa < hi.partition.total_pa
    for s in (lo, base, hi):
        assert 0.0 <= s.assumed_fraction_of_total <= 1.0
        assert 0.0 <= s.conditioned_fraction_of_total <= 1.0
        assert 0.0 <= s.measured_fraction_of_total <= 1.0
        assert math.isclose(
            s.assumed_fraction_of_total + s.conditioned_fraction_of_total
            + s.measured_fraction_of_total, 1.0,
            rel_tol=1e-9, abs_tol=1e-9)


def test_scenario_low_bound_is_the_configured_seawater_density(
        overburden_config):
    md = np.arange(1000.0, 1501.0, 10.0)
    frame = make_frame(md=md, density=np.full(md.size, 2000.0))
    out = prepared(frame, overburden_config, seabed_mdrt_m=500.0,
                   seabed_tvd_m=500.0, seabed_tvdss_m=475.0)
    scen = {s.scenario_name: s for s in build_shallow_column_scenarios(
        out["stats"], out["eligibility"], out["profile"], overburden_config)}
    assert (scen["low"].assumed_shallow_density_kg_m3
            == overburden_config.seawater_density_kg_m3)
    assert (scen["high"].assumed_shallow_density_kg_m3
            == out["stats"].rhob_eligible_p05_kg_m3)


def test_high_scenario_ignores_finite_density_below_the_eligible_domain(
        overburden_config):
    md = np.arange(0.0, 101.0, 1.0)
    rho = np.full(md.size, 2400.0)
    rho[:40] = 1100.0
    rho[40:50] = np.nan
    out = prepared(
        make_frame(md=md, density=rho), overburden_config,
        seabed_mdrt_m=40.0, seabed_tvd_m=40.0, seabed_tvdss_m=15.0)
    scenarios = {s.scenario_name: s for s in build_shallow_column_scenarios(
        out["stats"], out["eligibility"], out["profile"], overburden_config)}
    assert out["stats"].rhob_p05_kg_m3 == 1100.0
    assert out["stats"].rhob_eligible_p05_kg_m3 == 2400.0
    assert scenarios["high"].assumed_shallow_density_kg_m3 == 2400.0


def test_scenario_partition_components_sum_exactly_to_the_total(
        overburden_config):
    md = np.arange(1000.0, 1501.0, 10.0)
    frame = make_frame(md=md, density=np.full(md.size, 2000.0))
    out = prepared(frame, overburden_config, seabed_mdrt_m=500.0,
                   seabed_tvd_m=500.0, seabed_tvdss_m=475.0)
    for s in build_shallow_column_scenarios(
            out["stats"], out["eligibility"], out["profile"], overburden_config):
        p = s.partition
        assert math.isclose(
            p.water_column_pa + p.measured_formation_pa + p.bridged_gap_pa
            + p.unresolved_shallow_pa, p.total_pa, rel_tol=1e-12, abs_tol=1e-6)


def test_scenario_fraction_accounting_includes_a_nonzero_bridged_component(
        overburden_config):
    md = np.arange(0.0, 101.0, 1.0)
    rho = np.full(md.size, 2400.0)
    rho[:50] = np.nan
    rho[70:72] = np.nan
    frame = make_frame(md=md, density=rho)
    out = prepared(
        frame, overburden_config, seabed_mdrt_m=40.0,
        seabed_tvd_m=40.0, seabed_tvdss_m=15.0)
    scenarios = build_shallow_column_scenarios(
        out["stats"], out["eligibility"], out["profile"], overburden_config)
    assert scenarios
    assert out["profile"].total_bridged_increment_pa > 0.0
    for scenario in scenarios:
        total = scenario.partition.total_pa
        assert scenario.conditioned_fraction_of_total > 0.0
        assert math.isclose(
            scenario.conditioned_fraction_of_total,
            scenario.partition.bridged_gap_pa / total, rel_tol=1e-12)
        assert math.isclose(
            scenario.assumed_fraction_of_total
            + scenario.conditioned_fraction_of_total
            + scenario.measured_fraction_of_total,
            1.0, rel_tol=1e-12, abs_tol=1e-12)


def test_scenario_constructor_rejects_fraction_accounting_that_drops_bridging(
        overburden_config):
    md = np.arange(1000.0, 1501.0, 10.0)
    out = prepared(
        make_frame(md=md, density=np.full(md.size, 2000.0)),
        overburden_config, seabed_mdrt_m=500.0,
        seabed_tvd_m=500.0, seabed_tvdss_m=475.0)
    scenario = build_shallow_column_scenarios(
        out["stats"], out["eligibility"], out["profile"], overburden_config)[0]
    with pytest.raises(OverburdenInputError, match="fractions must sum to 1"):
        replace(scenario, measured_fraction_of_total=0.0)


def test_seawater_variants_move_only_the_water_component(overburden_config):
    md = np.arange(1000.0, 1501.0, 10.0)
    frame = make_frame(md=md, density=np.full(md.size, 2000.0))
    out = prepared(frame, overburden_config, seabed_mdrt_m=500.0,
                   seabed_tvd_m=500.0, seabed_tvdss_m=475.0)
    scen = {s.scenario_name: s for s in build_shallow_column_scenarios(
        out["stats"], out["eligibility"], out["profile"], overburden_config)}
    base, low, high = (scen["base"], scen["base_seawater_low"],
                       scen["base_seawater_high"])
    assert low.partition.water_column_pa < base.partition.water_column_pa
    assert high.partition.water_column_pa > base.partition.water_column_pa
    for other in (low, high):
        assert (other.partition.unresolved_shallow_pa
                == base.partition.unresolved_shallow_pa)
        assert (other.partition.measured_formation_pa
                == base.partition.measured_formation_pa)


def test_a_partition_with_an_unresolved_component_cannot_report_a_total():
    with pytest.raises(OverburdenInputError, match="unresolved component is not zero"):
        StressPartition(water_column_pa=None, measured_formation_pa=1.0,
                        bridged_gap_pa=0.0, unresolved_shallow_pa=None,
                        total_pa=1.0)


def test_a_partition_total_must_equal_the_sum_of_its_components():
    with pytest.raises(OverburdenInputError, match="components sum to"):
        StressPartition(water_column_pa=1.0, measured_formation_pa=1.0,
                        bridged_gap_pa=0.0, unresolved_shallow_pa=1.0,
                        total_pa=99.0)


def test_a_partition_rejects_a_negative_component():
    with pytest.raises(OverburdenInputError, match="must be >= 0"):
        StressPartition(water_column_pa=-1.0, measured_formation_pa=1.0,
                        bridged_gap_pa=0.0, unresolved_shallow_pa=None,
                        total_pa=None)


# ---------------------------------------------------------------------------
# Constructor invariants
# ---------------------------------------------------------------------------

def test_profile_rejects_a_decreasing_cumulative_series(overburden_config):
    from synthetic_inc7 import readonly
    arrs = dict(
        md_m=readonly(np.array([0.0, 1.0])), tvd_m=readonly(np.array([0.0, 1.0])),
        tvdss_m=readonly(np.array([0.0, 1.0])),
        density_kg_m3=readonly(np.array([2000.0, 2000.0])),
        bridged_mask=readonly(np.array([False, False])),
        cumulative_measured_increment_pa=readonly(np.array([0.0, -1.0])))
    with pytest.raises(OverburdenInputError, match="non-decreasing"):
        VerticalStressProfile(
            well_key="X", n_nodes=2, integration_coordinate="tvdss_m",
            gravity_m_s2=STANDARD_G, total_measured_increment_pa=-1.0,
            total_bridged_increment_pa=0.0, n_zero_thickness_intervals=0,
            n_intervals=1, top_tvd_m=0.0, base_tvd_m=1.0, top_tvdss_m=0.0,
            base_tvdss_m=1.0, column_truncated_at_unresolved_gap=False,
            n_eligible_samples_below_truncation=0, **arrs)


def test_profile_rejects_a_measured_depth_integration_coordinate():
    from synthetic_inc7 import readonly
    arrs = dict(
        md_m=readonly(np.array([0.0, 1.0])), tvd_m=readonly(np.array([0.0, 1.0])),
        tvdss_m=readonly(np.array([0.0, 1.0])),
        density_kg_m3=readonly(np.array([2000.0, 2000.0])),
        bridged_mask=readonly(np.array([False, False])),
        cumulative_measured_increment_pa=readonly(np.array([0.0, 1.0])))
    with pytest.raises(OverburdenInputError, match="integration_coordinate"):
        VerticalStressProfile(
            well_key="X", n_nodes=2, integration_coordinate="md_m",
            gravity_m_s2=STANDARD_G, total_measured_increment_pa=1.0,
            total_bridged_increment_pa=0.0, n_zero_thickness_intervals=0,
            n_intervals=1, top_tvd_m=0.0, base_tvd_m=1.0, top_tvdss_m=0.0,
            base_tvdss_m=1.0, column_truncated_at_unresolved_gap=False,
            n_eligible_samples_below_truncation=0, **arrs)


# ---------------------------------------------------------------------------
# Gap-threshold sensitivity
# ---------------------------------------------------------------------------

def test_gap_threshold_sensitivity_covers_every_configured_threshold(
        overburden_config):
    frame = gap_frame([slice(10, 15)], rho=2000.0, n=41, step=1.0)
    out = prepared(frame, overburden_config, seabed_mdrt_m=None)
    rows = build_gap_threshold_sensitivity(
        frame, out["masks"], out["stats"], overburden_config)
    assert [r.threshold_tvd_m for r in rows] == list(
        overburden_config.sensitivity_thresholds_tvd_m)
    assert sum(1 for r in rows if r.is_approved_threshold) == 1


def test_a_larger_threshold_bridges_at_least_as_many_gaps(overburden_config):
    frame = gap_frame([slice(10, 13), slice(20, 35)], rho=2000.0, n=61, step=1.0)
    out = prepared(frame, overburden_config, seabed_mdrt_m=None)
    rows = build_gap_threshold_sensitivity(
        frame, out["masks"], out["stats"], overburden_config)
    counts = [r.n_bridged_gaps for r in rows]
    assert counts == sorted(counts)


def test_zero_threshold_bridges_nothing(overburden_config):
    frame = gap_frame([slice(10, 13)], rho=2000.0, n=41, step=1.0)
    out = prepared(frame, overburden_config, seabed_mdrt_m=None)
    rows = build_gap_threshold_sensitivity(
        frame, out["masks"], out["stats"], overburden_config)
    zero = next(r for r in rows if r.threshold_tvd_m == 0.0)
    assert zero.n_bridged_gaps == 0
    assert zero.n_bridged_samples == 0


@pytest.mark.parametrize("bad", [True, "10", 10 + 0j, np.nan, np.inf, -np.inf, -1.0])
def test_gap_sensitivity_constructor_rejects_invalid_thresholds(
        bad, overburden_config):
    frame = gap_frame([slice(10, 13)], rho=2000.0, n=41, step=1.0)
    out = prepared(frame, overburden_config)
    good = build_gap_threshold_sensitivity(
        frame, out["masks"], out["stats"], overburden_config)[0]
    with pytest.raises(OverburdenInputError, match="threshold_tvd_m"):
        replace(good, threshold_tvd_m=bad)
