"""
tests/test_time_depth.py - Validation suite for p2mem.time_depth
(Increment 4: duplicate-tie conditioning, velocity diagnostics,
forward/inverse time-depth interpolation, checkshot-vs-survey depth
comparison, and the sonic-checkshot drift diagnostic; Increment 4.1:
order-invariant axis-tie conditioning for TVDSS<->OWT/TWT inversion, and
numerical-validation hardening of trapezoidal_integrate and
compute_sonic_checkshot_drift; Increment 4.1.1: a hidden-reversal-via-
global-grouping regression suite for build_axis_conditioned_lookup_table,
full-canonical-MD (not just selected-run) monotonicity tests for
compute_sonic_checkshot_drift, a typed-error test for zero in-coverage
checkshot rows in compare_checkshot_to_survey, and a dtype-rejection
audit for seconds_to_milliseconds/milliseconds_to_seconds).

PORTABLE unit tests only: small synthetic arrays, never the real project
files. The exact real-data axis-tie-conditioning results (the three
specific Increment 4 first-point regressions this patch fixes) are
independently reproduced and asserted against the real checkshot files in
`dev_scratch_inc4_1/run_integration_04.py` (dev-only, not packaged) - not
here, consistent with this file's synthetic-data-only scope. The synthetic
tests below reproduce the identical *shape* of that defect (an
order-dependent "keep first" tie-break vs. an order-invariant median) so
the mechanism is unit-tested independently of any real file.
"""

import math

import numpy as np
import pytest

from p2mem.checkshot_models import AxisConditionedLookupTable, ConditionedCheckshotData
from p2mem.time_depth import (
    TimeDepthError,
    build_axis_conditioned_lookup_table,
    build_axis_conditioned_tables_for_well,
    compare_checkshot_to_survey,
    compute_sonic_checkshot_drift,
    compute_velocity_diagnostics,
    depth_to_owt,
    depth_to_tvdss,
    depth_to_twt,
    detect_and_condition_depth_ties,
    find_longest_finite_positive_run,
    map_las_md_to_checkshot_time,
    milliseconds_to_seconds,
    owt_to_tvdss,
    seconds_to_milliseconds,
    trapezoidal_integrate,
    tvdss_to_owt,
    tvdss_to_twt,
    twt_to_tvdss,
)
from p2mem.units import owt_to_twt as locked_owt_to_twt


def _conditioned(depth, tvdss, owt) -> ConditionedCheckshotData:
    depth = np.asarray(depth, dtype=np.float64)
    tvdss = np.asarray(tvdss, dtype=np.float64)
    owt = np.asarray(owt, dtype=np.float64)
    return ConditionedCheckshotData(
        Depth_conditioned_m=depth,
        TVDSS_conditioned_m=tvdss,
        OWT_conditioned_s=owt,
        n_raw_rows=int(depth.size),
        n_conditioned_rows=int(depth.size),
        n_tie_groups=0,
        conditioning_method="test",
    )


# ---------------------------------------------------------------------------
# Unit helpers / integration
# ---------------------------------------------------------------------------
def test_seconds_milliseconds_round_trip():
    s = np.array([0.5, 1.0, 2.25])
    ms = seconds_to_milliseconds(s)
    assert np.allclose(ms, [500.0, 1000.0, 2250.0])
    assert np.allclose(milliseconds_to_seconds(ms), s)


def test_trapezoidal_integrate_constant_function():
    x = np.array([0.0, 1.0, 2.0, 3.0])
    y = np.array([2.0, 2.0, 2.0, 2.0])
    assert trapezoidal_integrate(y, x) == pytest.approx(6.0)


def test_trapezoidal_integrate_linear_function_matches_analytic():
    x = np.linspace(0.0, 10.0, 101)
    y = 3.0 * x + 1.0
    # integral of (3x+1) from 0 to 10 = 1.5*100 + 10 = 160
    assert trapezoidal_integrate(y, x) == pytest.approx(160.0, rel=1e-9)


def test_trapezoidal_integrate_rejects_non_1d_input():
    with pytest.raises(TimeDepthError):
        trapezoidal_integrate(np.array([[1.0, 2.0]]), np.array([[0.0, 1.0]]))


def test_trapezoidal_integrate_rejects_mismatched_lengths():
    with pytest.raises(TimeDepthError):
        trapezoidal_integrate(np.array([1.0, 2.0, 3.0]), np.array([0.0, 1.0]))


def test_trapezoidal_integrate_rejects_fewer_than_two_samples():
    with pytest.raises(TimeDepthError):
        trapezoidal_integrate(np.array([1.0]), np.array([0.0]))


def test_trapezoidal_integrate_rejects_non_finite_values():
    with pytest.raises(TimeDepthError):
        trapezoidal_integrate(np.array([1.0, np.nan]), np.array([0.0, 1.0]))
    with pytest.raises(TimeDepthError):
        trapezoidal_integrate(np.array([1.0, 2.0]), np.array([0.0, np.inf]))


def test_trapezoidal_integrate_rejects_non_increasing_x_never_sorts():
    # Regression (Increment 4.1): the pre-4.1 implementation performed no
    # validation and could silently integrate a decreasing/duplicate x into
    # a physically invalid (e.g. negative) result. It must now reject
    # rather than sort or otherwise repair x.
    with pytest.raises(TimeDepthError):
        trapezoidal_integrate(np.array([1.0, 2.0, 3.0]), np.array([0.0, 1.0, 1.0]))  # duplicate
    with pytest.raises(TimeDepthError):
        trapezoidal_integrate(np.array([1.0, 2.0, 3.0]), np.array([0.0, 2.0, 1.0]))  # decreasing


# ---------------------------------------------------------------------------
# Duplicate-tie detection and conditioning
# ---------------------------------------------------------------------------
def test_no_ties_passes_through_unchanged():
    ties, cond = detect_and_condition_depth_ties(
        "W", [100.0, 200.0, 300.0], [95.0, 190.0, 285.0], [0.1, 0.19, 0.28]
    )
    assert ties == ()
    assert cond.n_conditioned_rows == 3
    assert cond.n_tie_groups == 0
    assert np.allclose(cond.Depth_conditioned_m, [100.0, 200.0, 300.0])


def test_duplicate_pair_collapses_to_median_which_equals_mean_for_pairs():
    ties, cond = detect_and_condition_depth_ties(
        "W", [100.0, 200.0, 200.0, 300.0], [95.0, 190.0, 190.5, 285.0], [0.10, 0.19, 0.191, 0.28]
    )
    assert cond.n_conditioned_rows == 3
    assert cond.n_tie_groups == 1
    assert len(ties) == 1
    tie = ties[0]
    assert tie.group_size == 2
    assert tie.source_row_indices == (1, 2)
    assert tie.selected_representative_tvdss_m == pytest.approx((190.0 + 190.5) / 2.0)
    assert tie.selected_representative_owt_s == pytest.approx((0.19 + 0.191) / 2.0)
    idx200 = np.where(cond.Depth_conditioned_m == 200.0)[0][0]
    assert cond.TVDSS_conditioned_m[idx200] == pytest.approx((190.0 + 190.5) / 2.0)


def test_odd_sized_group_median_is_middle_value():
    ties, cond = detect_and_condition_depth_ties(
        "W", [100.0, 100.0, 100.0], [10.0, 20.0, 30.0], [0.1, 0.2, 0.3]
    )
    assert len(ties) == 1
    assert ties[0].group_size == 3
    assert ties[0].selected_representative_tvdss_m == pytest.approx(20.0)  # median of 10,20,30


def test_raw_rows_never_overwritten_all_preserved_in_register():
    ties, _ = detect_and_condition_depth_ties(
        "W", [100.0, 200.0, 200.0], [95.0, 190.0, 190.5], [0.10, 0.19, 0.191]
    )
    assert ties[0].original_tvdss_m == (190.0, 190.5)
    assert ties[0].original_owt_s == (0.19, 0.191)


def test_mismatched_array_lengths_raises():
    with pytest.raises(TimeDepthError):
        detect_and_condition_depth_ties("W", [1.0, 2.0], [1.0], [1.0, 2.0])


def test_empty_arrays_raises():
    with pytest.raises(TimeDepthError):
        detect_and_condition_depth_ties("W", [], [], [])


def test_out_of_order_distinct_depths_raises():
    # distinct Depth values visited out of sorted order (1, 3, 2) -- not an
    # ordinary repeated tie-in, should be rejected rather than silently conditioned.
    with pytest.raises(TimeDepthError):
        detect_and_condition_depth_ties("W", [1.0, 3.0, 2.0], [1.0, 3.0, 2.0], [0.1, 0.3, 0.2])


# ---------------------------------------------------------------------------
# Velocity diagnostics
# ---------------------------------------------------------------------------
def test_vavg_and_vint_basic_case():
    cond = _conditioned([0.0, 100.0, 200.0], [0.0, 100.0, 200.0], [0.05, 0.10, 0.15])
    result = compute_velocity_diagnostics("W", cond)
    assert np.allclose(result.Vavg_m_s[1:], [1000.0, 1333.333333], rtol=1e-6)
    assert np.allclose(result.Vint_m_s, [2000.0, 2000.0])
    assert result.n_vint_invalid == 0


def test_vint_nan_on_zero_delta_owt_never_inf():
    cond = _conditioned([0.0, 100.0], [0.0, 100.0], [0.05, 0.05])
    result = compute_velocity_diagnostics("W", cond)
    assert math.isnan(result.Vint_m_s[0])
    assert not np.isinf(result.Vint_m_s[0])
    assert result.n_vint_invalid == 1
    assert result.vint_invalid_reason_counts["non_positive_delta_owt"] == 1


def test_vint_nan_on_negative_delta_tvdss_never_negative_velocity():
    cond = _conditioned([0.0, 100.0], [100.0, 50.0], [0.05, 0.10])
    result = compute_velocity_diagnostics("W", cond)
    assert math.isnan(result.Vint_m_s[0])
    assert result.vint_invalid_reason_counts["non_positive_delta_tvdss"] == 1


def test_vavg_nan_when_owt_non_positive():
    cond = _conditioned([0.0, 100.0], [0.0, 100.0], [0.0, 0.10])
    result = compute_velocity_diagnostics("W", cond)
    assert math.isnan(result.Vavg_m_s[0])


# ---------------------------------------------------------------------------
# Checkshot-vs-survey depth comparison
# ---------------------------------------------------------------------------
def test_compare_checkshot_to_survey_zero_residual_when_consistent():
    survey_md = np.array([0.0, 100.0, 200.0, 300.0])
    survey_tvd = np.array([0.0, 95.0, 190.0, 285.0])
    depth_source = np.array([100.0, 200.0])
    tvdss_source = np.array([95.0, 190.0])
    result = compare_checkshot_to_survey(
        "W", depth_source, tvdss_source, survey_md, survey_tvd, datum_elevation_m=0.0,
        depth_basis_interpretation_status="candidate_md_evaluated_against_locked_survey",
    )
    assert result.max_abs_residual_m == pytest.approx(0.0, abs=1e-9)
    assert result.n_compared == 2
    assert result.n_outside_survey_md_coverage == 0


def test_compare_checkshot_to_survey_constant_offset_detected():
    survey_md = np.array([0.0, 100.0, 200.0, 300.0])
    survey_tvd = np.array([0.0, 95.0, 190.0, 285.0])
    depth_source = np.array([100.0, 200.0, 300.0])
    tvdss_source = survey_tvd[1:] - 0.5  # checkshot reads 0.5 m shallower everywhere
    result = compare_checkshot_to_survey(
        "W", depth_source, tvdss_source, survey_md, survey_tvd, datum_elevation_m=0.0,
        depth_basis_interpretation_status="candidate_md_evaluated_against_locked_survey",
    )
    assert result.mean_residual_m == pytest.approx(0.5, abs=1e-9)
    assert "near-constant" in result.residual_trend_description


def test_compare_checkshot_to_survey_excludes_out_of_coverage_rows():
    survey_md = np.array([0.0, 100.0, 200.0])
    survey_tvd = np.array([0.0, 95.0, 190.0])
    depth_source = np.array([50.0, 500.0])  # 500 is outside survey MD coverage
    tvdss_source = np.array([47.5, 999.0])
    result = compare_checkshot_to_survey(
        "W", depth_source, tvdss_source, survey_md, survey_tvd, datum_elevation_m=0.0,
        depth_basis_interpretation_status="candidate_md_evaluated_against_locked_survey",
    )
    assert result.n_compared == 1
    assert result.n_outside_survey_md_coverage == 1


def test_compare_checkshot_to_survey_rejects_non_monotonic_survey():
    survey_md = np.array([0.0, 100.0, 50.0])
    survey_tvd = np.array([0.0, 95.0, 190.0])
    with pytest.raises(TimeDepthError):
        compare_checkshot_to_survey(
            "W", np.array([10.0]), np.array([10.0]), survey_md, survey_tvd, datum_elevation_m=0.0,
            depth_basis_interpretation_status="candidate_md_evaluated_against_locked_survey",
        )


# ---------------------------------------------------------------------------
# Depth-domain forward interpolation
# ---------------------------------------------------------------------------
def test_depth_to_tvdss_inside_and_outside_coverage():
    cond = _conditioned([100.0, 200.0, 300.0], [95.0, 190.0, 285.0], [0.10, 0.19, 0.28])
    values, mask = depth_to_tvdss([150.0, 50.0, 400.0], cond)
    assert values[0] == pytest.approx(142.5)
    assert math.isnan(values[1])
    assert math.isnan(values[2])
    assert mask.tolist() == [True, False, False]


def test_depth_to_owt_exact_at_station():
    cond = _conditioned([100.0, 200.0, 300.0], [95.0, 190.0, 285.0], [0.10, 0.19, 0.28])
    values, mask = depth_to_owt([200.0], cond)
    assert values[0] == pytest.approx(0.19)


def test_depth_to_twt_uses_locked_owt_to_twt():
    cond = _conditioned([100.0, 200.0], [95.0, 190.0], [0.10, 0.20])
    twt, mask = depth_to_twt([100.0, 200.0], cond)
    owt, _ = depth_to_owt([100.0, 200.0], cond)
    assert np.allclose(twt, locked_owt_to_twt(owt))
    assert np.allclose(twt, [0.20, 0.40])


# ---------------------------------------------------------------------------
# Time-domain forward/inverse interpolation via AxisConditionedLookupTable
# (Increment 4.1: tvdss_to_owt/owt_to_tvdss/tvdss_to_twt/twt_to_tvdss now
# take a pre-built AxisConditionedLookupTable, not a bare
# ConditionedCheckshotData, and return a 2-tuple (values, mask) - the old
# 3-tuple with n_dropped no longer exists, because points are never
# dropped: every tied point is registered and folded into a median
# representative instead.)
# ---------------------------------------------------------------------------
def test_owt_to_tvdss_inverts_cleanly_when_strictly_monotonic():
    cond = _conditioned([100.0, 200.0, 300.0], [95.0, 190.0, 285.0], [0.10, 0.19, 0.28])
    _, tables = build_axis_conditioned_tables_for_well("W", cond)
    values, mask = owt_to_tvdss([0.19], tables["owt_to_tvdss"])
    assert values[0] == pytest.approx(190.0)
    assert bool(mask[0]) is True


def test_tvdss_to_owt_and_owt_to_tvdss_are_consistent_round_trip():
    cond = _conditioned([100.0, 200.0, 300.0], [95.0, 190.0, 285.0], [0.10, 0.19, 0.28])
    _, tables = build_axis_conditioned_tables_for_well("W", cond)
    owt, mask1 = tvdss_to_owt([142.5], tables["tvdss_to_owt"])
    tvdss_back, mask2 = owt_to_tvdss(owt, tables["owt_to_tvdss"])
    assert tvdss_back[0] == pytest.approx(142.5, abs=1e-6)
    assert bool(mask1[0]) and bool(mask2[0])


def test_tvdss_to_twt_and_twt_to_tvdss_round_trip():
    cond = _conditioned([100.0, 200.0, 300.0], [95.0, 190.0, 285.0], [0.10, 0.19, 0.28])
    _, tables = build_axis_conditioned_tables_for_well("W", cond)
    twt, _ = tvdss_to_twt([190.0], tables["tvdss_to_owt"])
    assert twt[0] == pytest.approx(0.38)
    tvdss_back, _ = twt_to_tvdss([0.38], tables["owt_to_tvdss"])
    assert tvdss_back[0] == pytest.approx(190.0)


def test_tvdss_to_owt_and_owt_to_tvdss_reject_wrong_direction_table():
    # Guards against passing the OWT->TVDSS table where a TVDSS->OWT table
    # (or vice versa) is required.
    cond = _conditioned([100.0, 200.0, 300.0], [95.0, 190.0, 285.0], [0.10, 0.19, 0.28])
    _, tables = build_axis_conditioned_tables_for_well("W", cond)
    with pytest.raises(TimeDepthError):
        tvdss_to_owt([150.0], tables["owt_to_tvdss"])
    with pytest.raises(TimeDepthError):
        owt_to_tvdss([0.15], tables["tvdss_to_owt"])


def test_tvdss_to_owt_never_extrapolates_outside_table_coverage():
    cond = _conditioned([100.0, 200.0, 300.0], [95.0, 190.0, 285.0], [0.10, 0.19, 0.28])
    _, tables = build_axis_conditioned_tables_for_well("W", cond)
    values, mask = tvdss_to_owt([50.0, 142.5, 400.0], tables["tvdss_to_owt"])
    assert math.isnan(values[0])
    assert not math.isnan(values[1])
    assert math.isnan(values[2])
    assert mask.tolist() == [False, True, False]


# ---------------------------------------------------------------------------
# Order-invariant axis-tie conditioning (Increment 4.1 core fix):
# build_axis_conditioned_lookup_table / build_axis_conditioned_tables_for_well
# ---------------------------------------------------------------------------
def test_tvdss_axis_tie_resolves_to_median_and_is_order_invariant():
    # A TVDSS tie (depths 200 & 300 both read TVDSS=100.0) with DIFFERENT
    # OWT dependent values. Two versions below carry the identical set of
    # tied values but with the assignment across the two physical rows
    # swapped - this reproduces the Increment 4 "keep first, drop later"
    # defect shape: an order-dependent tie-break would give a DIFFERENT
    # answer for version A vs version B (whichever value happened to sit
    # in the row visited "first"); the Increment 4.1 median representative
    # must give the IDENTICAL answer for both.
    depth = np.array([100.0, 200.0, 300.0])
    tvdss = np.array([90.0, 100.0, 100.0])
    owt_a = np.array([0.10, 0.20, 0.21])
    owt_b = np.array([0.10, 0.21, 0.20])  # same tied values, swapped assignment

    entries_a, table_a = build_axis_conditioned_lookup_table(
        "W", "tvdss_to_owt", "TVDSS_conditioned_m", "OWT_conditioned_s", depth, tvdss, owt_a
    )
    entries_b, table_b = build_axis_conditioned_lookup_table(
        "W", "tvdss_to_owt", "TVDSS_conditioned_m", "OWT_conditioned_s", depth, tvdss, owt_b
    )

    assert np.allclose(table_a.axis_values, [90.0, 100.0])
    assert np.allclose(table_a.dependent_values, table_b.dependent_values)
    assert table_a.dependent_values[1] == pytest.approx(0.205)  # median (== mean) of {0.20, 0.21}
    assert len(entries_a) == 1 and len(entries_b) == 1
    assert entries_a[0].tie_kind == "genuinely_non_unique"
    assert entries_a[0].group_size == 2
    assert entries_a[0].dependent_value_spread == pytest.approx(0.01)
    assert entries_a[0].selected_representative_dependent_value == pytest.approx(0.205)
    assert table_a.n_axis_tie_groups == 1
    assert table_a.n_genuinely_nonunique_groups == 1
    assert table_a.n_identical_pairs == 0
    assert table_a.n_collapsed_points == 1
    assert table_a.n_input_points == 3
    assert table_a.n_output_points == 2


def test_owt_axis_tie_resolves_to_median_and_is_order_invariant():
    # Same defect shape as above, but the tie is now on the OWT axis (the
    # independent axis being inverted FROM for owt_to_tvdss) with different
    # TVDSS dependent values.
    depth = np.array([100.0, 200.0, 300.0])
    owt = np.array([0.10, 0.20, 0.20])
    tvdss_a = np.array([90.0, 190.0, 191.0])
    tvdss_b = np.array([90.0, 191.0, 190.0])  # same tied values, swapped assignment

    entries_a, table_a = build_axis_conditioned_lookup_table(
        "W", "owt_to_tvdss", "OWT_conditioned_s", "TVDSS_conditioned_m", depth, owt, tvdss_a
    )
    entries_b, table_b = build_axis_conditioned_lookup_table(
        "W", "owt_to_tvdss", "OWT_conditioned_s", "TVDSS_conditioned_m", depth, owt, tvdss_b
    )

    assert np.allclose(table_a.dependent_values, table_b.dependent_values)
    assert table_a.dependent_values[1] == pytest.approx(190.5)
    assert entries_a[0].tie_kind == "genuinely_non_unique"
    assert entries_a[0].group_size == 2


def test_identical_axis_and_dependent_pair_collapses_without_changing_value():
    # Both the independent axis AND the dependent value are identical
    # across the tied rows: this must still be counted/registered
    # (tie_kind="identical_pair"), never silently merged away unrecorded,
    # even though the representative value is numerically unchanged.
    depth = np.array([100.0, 200.0, 300.0])
    tvdss = np.array([90.0, 100.0, 100.0])
    owt = np.array([0.10, 0.20, 0.20])
    entries, table = build_axis_conditioned_lookup_table(
        "W", "tvdss_to_owt", "TVDSS_conditioned_m", "OWT_conditioned_s", depth, tvdss, owt
    )
    assert len(entries) == 1
    assert entries[0].tie_kind == "identical_pair"
    assert entries[0].dependent_value_spread == 0.0
    assert entries[0].selected_representative_dependent_value == pytest.approx(0.20)
    assert table.n_identical_pairs == 1
    assert table.n_genuinely_nonunique_groups == 0
    assert table.n_collapsed_points == 1


def test_exact_duplicate_axis_and_dependent_rows_are_still_counted():
    # A three-row group, all identical on both axes: group_size must be 3,
    # not silently deduplicated to a smaller count.
    depth = np.array([100.0, 200.0, 300.0, 400.0])
    tvdss = np.array([90.0, 100.0, 100.0, 100.0])
    owt = np.array([0.10, 0.20, 0.20, 0.20])
    entries, table = build_axis_conditioned_lookup_table(
        "W", "tvdss_to_owt", "TVDSS_conditioned_m", "OWT_conditioned_s", depth, tvdss, owt
    )
    assert len(entries) == 1
    assert entries[0].group_size == 3
    assert entries[0].tie_kind == "identical_pair"
    assert table.n_collapsed_points == 2


def test_genuine_reversal_after_grouping_raises_never_sorted_or_discarded():
    # Group values are 100.0 then 90.0 in axis order - a genuine reversal
    # (not a tie), which must raise rather than being sorted, discarded,
    # or otherwise forced monotonic.
    depth = np.array([100.0, 200.0, 300.0])
    tvdss = np.array([100.0, 100.0, 90.0])
    owt = np.array([0.20, 0.21, 0.05])
    with pytest.raises(TimeDepthError):
        build_axis_conditioned_lookup_table(
            "W", "tvdss_to_owt", "TVDSS_conditioned_m", "OWT_conditioned_s", depth, tvdss, owt
        )


def test_axis_conditioned_table_rejects_non_finite_independent_values():
    depth = np.array([100.0, 200.0])
    tvdss = np.array([90.0, np.nan])
    owt = np.array([0.1, 0.2])
    with pytest.raises(TimeDepthError):
        build_axis_conditioned_lookup_table(
            "W", "tvdss_to_owt", "TVDSS_conditioned_m", "OWT_conditioned_s", depth, tvdss, owt
        )


def test_axis_conditioned_table_rejects_non_finite_dependent_values():
    depth = np.array([100.0, 200.0])
    tvdss = np.array([90.0, 100.0])
    owt = np.array([0.1, np.inf])
    with pytest.raises(TimeDepthError):
        build_axis_conditioned_lookup_table(
            "W", "tvdss_to_owt", "TVDSS_conditioned_m", "OWT_conditioned_s", depth, tvdss, owt
        )


def test_axis_conditioned_table_rejects_mismatched_array_lengths():
    depth = np.array([100.0, 200.0, 300.0])
    tvdss = np.array([90.0, 100.0])
    owt = np.array([0.1, 0.2, 0.3])
    with pytest.raises(TimeDepthError):
        build_axis_conditioned_lookup_table(
            "W", "tvdss_to_owt", "TVDSS_conditioned_m", "OWT_conditioned_s", depth, tvdss, owt
        )


def test_build_axis_conditioned_tables_for_well_builds_both_directions():
    cond = _conditioned(
        [100.0, 200.0, 300.0, 400.0], [95.0, 190.0, 190.5, 285.0], [0.10, 0.19, 0.191, 0.28]
    )
    entries, tables = build_axis_conditioned_tables_for_well("W", cond)
    assert set(tables.keys()) == {"tvdss_to_owt", "owt_to_tvdss"}
    assert isinstance(tables["tvdss_to_owt"], AxisConditionedLookupTable)
    assert tables["tvdss_to_owt"].interpolation_direction == "tvdss_to_owt"
    assert tables["owt_to_tvdss"].interpolation_direction == "owt_to_tvdss"
    # No ties on TVDSS or OWT in this fixture -> zero axis-tie entries.
    assert entries == ()
    assert tables["tvdss_to_owt"].n_axis_tie_groups == 0
    assert tables["owt_to_tvdss"].n_axis_tie_groups == 0


# ---------------------------------------------------------------------------
# LAS MD -> checkshot time mapping (partial coverage)
# ---------------------------------------------------------------------------
def test_map_las_md_to_checkshot_time_partial_coverage_never_extrapolates():
    cond = _conditioned([100.0, 200.0, 300.0], [95.0, 190.0, 285.0], [0.10, 0.19, 0.28])
    las_md = np.array([50.0, 150.0, 250.0, 350.0])
    owt_mapped, twt_mapped, summary = map_las_md_to_checkshot_time("W", las_md, cond)
    assert math.isnan(owt_mapped[0])  # shallower than coverage
    assert not math.isnan(owt_mapped[1])
    assert not math.isnan(owt_mapped[2])
    assert math.isnan(owt_mapped[3])  # deeper than coverage
    assert summary.n_extrapolated == 0
    assert summary.n_inside_coverage == 2
    assert summary.n_shallower_than_coverage == 1
    assert summary.n_deeper_than_coverage == 1
    assert summary.mapped_fraction == pytest.approx(0.5)


def test_map_las_md_rejects_non_finite_input():
    cond = _conditioned([100.0, 200.0], [95.0, 190.0], [0.10, 0.19])
    with pytest.raises(TimeDepthError):
        map_las_md_to_checkshot_time("W", np.array([100.0, np.nan]), cond)


# ---------------------------------------------------------------------------
# Sonic-checkshot drift
# ---------------------------------------------------------------------------
def test_find_longest_finite_positive_run_picks_longest():
    md = np.arange(10.0)
    vp = np.array([np.nan, 1.0, 2.0, np.nan, np.nan, 3.0, 4.0, 5.0, np.nan, np.nan])
    start, end = find_longest_finite_positive_run(md, vp)
    assert (start, end) == (5, 7)


def test_find_longest_finite_positive_run_raises_when_none_valid():
    md = np.arange(5.0)
    vp = np.full(5, np.nan)
    with pytest.raises(TimeDepthError):
        find_longest_finite_positive_run(md, vp)


def test_sonic_checkshot_drift_known_constant_velocity_matches_analytic():
    # Constant VP => sonic transit time = (md2-md1)/VP exactly (trapezoidal
    # integration of a constant is exact).
    md = np.linspace(0.0, 1000.0, 1001)
    vp = np.full(md.shape, 2000.0)  # m/s
    cond = _conditioned([0.0, 1000.0], [0.0, 1000.0], [0.0, 1000.0 / 2000.0])
    drift = compute_sonic_checkshot_drift("Poseidon_2", md, vp, cond)
    assert drift.sonic_transit_time_s == pytest.approx(1000.0 / 2000.0, rel=1e-9)
    assert drift.checkshot_owt_increment_s == pytest.approx(1000.0 / 2000.0, rel=1e-9)
    assert drift.sonic_minus_checkshot_ms == pytest.approx(0.0, abs=1e-6)
    assert drift.checkshot_minus_sonic_ms == pytest.approx(0.0, abs=1e-6)


def test_sonic_checkshot_drift_reports_both_signs_and_percent():
    md = np.linspace(0.0, 100.0, 101)
    vp = np.full(md.shape, 1000.0)  # transit time = 0.1 s
    cond = _conditioned([0.0, 100.0], [0.0, 100.0], [0.0, 0.09])  # checkshot increment 0.09 s
    drift = compute_sonic_checkshot_drift("Poseidon_2", md, vp, cond)
    assert drift.sonic_minus_checkshot_ms == pytest.approx(-drift.checkshot_minus_sonic_ms)
    assert drift.sonic_minus_checkshot_percent == pytest.approx(
        (0.1 - 0.09) / 0.09 * 100.0, rel=1e-6
    )


def test_sonic_checkshot_drift_rejects_interval_beyond_checkshot_coverage():
    md = np.linspace(0.0, 1000.0, 1001)
    vp = np.full(md.shape, 2000.0)
    cond = _conditioned([200.0, 500.0], [190.0, 480.0], [0.19, 0.45])  # narrower than sonic run
    with pytest.raises(TimeDepthError):
        compute_sonic_checkshot_drift("Poseidon_2", md, vp, cond)


def test_sonic_checkshot_drift_rejects_decreasing_md_never_negative_transit_time():
    # Regression (Increment 4.1): the pre-4.1 implementation validated none
    # of this and could silently integrate a decreasing MD run into a
    # physically invalid NEGATIVE "transit time". It must now raise
    # TimeDepthError instead of returning any result.
    md = np.array([100.0, 200.0, 150.0, 250.0])  # decreasing at index 1->2
    vp = np.full(md.shape, 2000.0)
    cond = _conditioned([0.0, 300.0], [0.0, 300.0], [0.0, 0.15])
    with pytest.raises(TimeDepthError):
        compute_sonic_checkshot_drift("Poseidon_2", md, vp, cond)


def test_sonic_checkshot_drift_rejects_duplicate_md():
    md = np.array([100.0, 200.0, 200.0, 300.0])
    vp = np.full(md.shape, 2000.0)
    cond = _conditioned([0.0, 300.0], [0.0, 300.0], [0.0, 0.15])
    with pytest.raises(TimeDepthError):
        compute_sonic_checkshot_drift("Poseidon_2", md, vp, cond)


def test_sonic_checkshot_drift_rejects_non_finite_md():
    md = np.array([100.0, np.nan, 300.0])
    vp = np.full(md.shape, 2000.0)
    cond = _conditioned([0.0, 300.0], [0.0, 300.0], [0.0, 0.15])
    with pytest.raises(TimeDepthError):
        compute_sonic_checkshot_drift("Poseidon_2", md, vp, cond)


def test_sonic_checkshot_drift_rejects_incompatible_md_vp_shapes():
    md = np.array([100.0, 200.0, 300.0])
    vp = np.array([2000.0, 2000.0])  # length mismatch
    cond = _conditioned([0.0, 300.0], [0.0, 300.0], [0.0, 0.15])
    with pytest.raises(TimeDepthError):
        compute_sonic_checkshot_drift("Poseidon_2", md, vp, cond)


def test_sonic_checkshot_drift_rejects_non_positive_checkshot_owt_increment():
    md = np.linspace(100.0, 300.0, 21)
    vp = np.full(md.shape, 2000.0)
    # Checkshot OWT is flat (zero increment) across the identical Depth
    # interval used for comparison.
    cond = _conditioned([100.0, 300.0], [100.0, 300.0], [0.15, 0.15])
    with pytest.raises(TimeDepthError):
        compute_sonic_checkshot_drift("Poseidon_2", md, vp, cond)


# ---------------------------------------------------------------------------
# Increment 4.1.1 - Blocking Defect 1: hidden reversal via global exact-
# value grouping in build_axis_conditioned_lookup_table
# ---------------------------------------------------------------------------
def test_hidden_reversal_returning_to_seen_value_raises():
    # [100.0, 200.0, 100.0]: the pre-4.1.1 implementation grouped ALL
    # occurrences of 100.0 together globally BEFORE checking for a
    # reversal, producing an apparently-valid [100.0, 200.0] and silently
    # hiding the genuine 200 -> 100 reversal. This must now raise.
    depth = np.array([100.0, 200.0, 300.0])
    independent = np.array([100.0, 200.0, 100.0])
    dependent = np.array([1.0, 2.0, 3.0])
    with pytest.raises(TimeDepthError):
        build_axis_conditioned_lookup_table(
            "W", "tvdss_to_owt", "TVDSS_conditioned_m", "OWT_conditioned_s",
            depth, independent, dependent,
        )


def test_hidden_reversal_with_adjacent_tie_before_it_raises():
    # [100.0, 200.0, 150.0, 150.0, 300.0]: a genuine reversal (200 -> 150)
    # immediately followed by a valid adjacent tie (150.0, 150.0) and then
    # a further increase. The reversal must still be caught even though a
    # legitimate adjacent tie appears later in the sequence.
    depth = np.array([100.0, 200.0, 300.0, 400.0, 500.0])
    independent = np.array([100.0, 200.0, 150.0, 150.0, 300.0])
    dependent = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    with pytest.raises(TimeDepthError):
        build_axis_conditioned_lookup_table(
            "W", "tvdss_to_owt", "TVDSS_conditioned_m", "OWT_conditioned_s",
            depth, independent, dependent,
        )


def test_valid_leading_adjacent_tie_remains_valid_and_order_invariant():
    # [100.0, 100.0, 200.0]: a genuine adjacent tie at the START of the
    # sequence, not a reversal - must remain valid (Increment 4.1.1 must
    # not regress this legitimate case) and order-invariant across which
    # of the two tied rows carries which dependent value.
    depth = np.array([100.0, 200.0, 300.0])
    independent = np.array([100.0, 100.0, 200.0])
    dependent_a = np.array([1.0, 2.0, 3.0])
    dependent_b = np.array([2.0, 1.0, 3.0])  # same tied values, swapped assignment

    entries_a, table_a = build_axis_conditioned_lookup_table(
        "W", "tvdss_to_owt", "TVDSS_conditioned_m", "OWT_conditioned_s",
        depth, independent, dependent_a,
    )
    entries_b, table_b = build_axis_conditioned_lookup_table(
        "W", "tvdss_to_owt", "TVDSS_conditioned_m", "OWT_conditioned_s",
        depth, independent, dependent_b,
    )
    assert np.allclose(table_a.axis_values, [100.0, 200.0])
    assert np.allclose(table_a.dependent_values, table_b.dependent_values)
    assert table_a.dependent_values[0] == pytest.approx(1.5)  # median (== mean) of {1.0, 2.0}
    assert len(entries_a) == 1
    assert entries_a[0].group_size == 2


def test_valid_trailing_adjacent_tie_remains_valid_and_order_invariant():
    # [100.0, 200.0, 200.0, 300.0]: a genuine adjacent tie in the MIDDLE of
    # the sequence, not a reversal - must remain valid and order-invariant.
    depth = np.array([100.0, 200.0, 300.0, 400.0])
    independent = np.array([100.0, 200.0, 200.0, 300.0])
    dependent_a = np.array([1.0, 2.0, 3.0, 4.0])
    dependent_b = np.array([1.0, 3.0, 2.0, 4.0])  # same tied values, swapped assignment

    entries_a, table_a = build_axis_conditioned_lookup_table(
        "W", "tvdss_to_owt", "TVDSS_conditioned_m", "OWT_conditioned_s",
        depth, independent, dependent_a,
    )
    entries_b, table_b = build_axis_conditioned_lookup_table(
        "W", "tvdss_to_owt", "TVDSS_conditioned_m", "OWT_conditioned_s",
        depth, independent, dependent_b,
    )
    assert np.allclose(table_a.axis_values, [100.0, 200.0, 300.0])
    assert np.allclose(table_a.dependent_values, table_b.dependent_values)
    assert table_a.dependent_values[1] == pytest.approx(2.5)  # median (== mean) of {2.0, 3.0}
    assert len(entries_a) == 1
    assert entries_a[0].group_size == 2


def test_axis_conditioned_table_rejects_non_finite_or_non_increasing_depth_conditioned():
    # Increment 4.1.1 hardening: depth_conditioned_m itself is now
    # validated finite and strictly increasing on entry.
    independent = np.array([100.0, 200.0])
    dependent = np.array([1.0, 2.0])
    with pytest.raises(TimeDepthError):
        build_axis_conditioned_lookup_table(
            "W", "tvdss_to_owt", "TVDSS_conditioned_m", "OWT_conditioned_s",
            np.array([100.0, np.nan]), independent, dependent,
        )
    with pytest.raises(TimeDepthError):
        build_axis_conditioned_lookup_table(
            "W", "tvdss_to_owt", "TVDSS_conditioned_m", "OWT_conditioned_s",
            np.array([200.0, 100.0]), independent, dependent,
        )


# ---------------------------------------------------------------------------
# Increment 4.1.1 - Blocking Defect 2: full-canonical-MD validation must
# not be limited to the selected finite-positive-VP run
# ---------------------------------------------------------------------------
def test_sonic_checkshot_drift_rejects_decreasing_md_outside_selected_run():
    # Full md_m = [0.0, 1.0, 0.0]: the final station is a decreasing MD
    # step, but its VP_m_s is NaN so it would be EXCLUDED from the
    # selected finite-positive-VP run (indices 0-1 only). The pre-4.1.1
    # implementation validated monotonicity only within that selected
    # run and would not have caught this. The COMPLETE canonical md_m
    # array must now be validated before run-selection.
    md = np.array([0.0, 1.0, 0.0])
    vp = np.array([2000.0, 2000.0, np.nan])
    cond = _conditioned([0.0, 1.0], [0.0, 1.0], [0.0, 0.0005])
    with pytest.raises(TimeDepthError):
        compute_sonic_checkshot_drift("Poseidon_2", md, vp, cond)


def test_sonic_checkshot_drift_rejects_duplicate_md_outside_selected_run():
    # Full md_m = [0.0, 1.0, 1.0]: the final station duplicates the prior
    # MD value, but its VP_m_s is NaN so it would be excluded from the
    # selected run (indices 0-1 only). Must still raise.
    md = np.array([0.0, 1.0, 1.0])
    vp = np.array([2000.0, 2000.0, np.nan])
    cond = _conditioned([0.0, 1.0], [0.0, 1.0], [0.0, 0.0005])
    with pytest.raises(TimeDepthError):
        compute_sonic_checkshot_drift("Poseidon_2", md, vp, cond)


def test_find_longest_finite_positive_run_rejects_non_1d_input():
    with pytest.raises(TimeDepthError):
        find_longest_finite_positive_run(np.array([[1.0, 2.0]]), np.array([[1.0, 2.0]]))
    with pytest.raises(TimeDepthError):
        find_longest_finite_positive_run(np.arange(4.0), np.array([[1.0, 2.0], [3.0, 4.0]]))


def test_find_longest_finite_positive_run_rejects_mismatched_shapes():
    with pytest.raises(TimeDepthError):
        find_longest_finite_positive_run(np.arange(4.0), np.arange(3.0))


# ---------------------------------------------------------------------------
# Increment 4.1.1 - Blocking Defect 3: zero in-coverage checkshot rows
# must raise a typed TimeDepthError, never an untyped NumPy ValueError
# ---------------------------------------------------------------------------
def test_compare_checkshot_to_survey_raises_typed_error_when_zero_rows_in_coverage():
    survey_md = np.array([0.0, 100.0, 200.0])
    survey_tvd = np.array([0.0, 95.0, 190.0])
    depth_source = np.array([500.0, 600.0])  # both entirely outside survey MD coverage
    tvdss_source = np.array([499.0, 599.0])
    with pytest.raises(TimeDepthError) as excinfo:
        compare_checkshot_to_survey(
            "Boreas_1", depth_source, tvdss_source, survey_md, survey_tvd, datum_elevation_m=0.0,
            depth_basis_interpretation_status="candidate_md_evaluated_against_locked_survey",
        )
    message = str(excinfo.value)
    assert "Boreas_1" in message
    assert "500.0000" in message and "600.0000" in message  # checkshot Depth range
    assert "0.0000" in message and "200.0000" in message  # survey MD coverage
    assert "no comparison was" in message
    assert "no extrapolation was attempted" in message


# ---------------------------------------------------------------------------
# Increment 4.1.1 - unit-helper input-safety audit: seconds_to_milliseconds
# / milliseconds_to_seconds must not silently coerce boolean, string, or
# complex input, mirroring the p2mem.units Increment-1 policy
# ---------------------------------------------------------------------------
def test_seconds_to_milliseconds_rejects_boolean_input():
    with pytest.raises(TypeError):
        seconds_to_milliseconds(True)
    with pytest.raises(TypeError):
        seconds_to_milliseconds(np.array([True, False]))


def test_seconds_to_milliseconds_rejects_string_input():
    with pytest.raises(TypeError):
        seconds_to_milliseconds("3.5")
    with pytest.raises(TypeError):
        seconds_to_milliseconds(np.array(["1.0", "2.0"]))


def test_seconds_to_milliseconds_rejects_complex_input():
    with pytest.raises(TypeError):
        seconds_to_milliseconds(1.0 + 2.0j)
    with pytest.raises(TypeError):
        seconds_to_milliseconds(np.array([1.0 + 2.0j]))


def test_milliseconds_to_seconds_rejects_boolean_string_complex_input():
    with pytest.raises(TypeError):
        milliseconds_to_seconds(False)
    with pytest.raises(TypeError):
        milliseconds_to_seconds("1500")
    with pytest.raises(TypeError):
        milliseconds_to_seconds(np.array(["1500.0"]))
    with pytest.raises(TypeError):
        milliseconds_to_seconds(3.0 - 1.0j)


def test_seconds_milliseconds_still_accept_valid_scalars_arrays_and_nan():
    # Increment 4.1.1 must not regress any previously valid input: Python
    # numeric scalars, NumPy numeric arrays, and NaN propagation.
    assert seconds_to_milliseconds(1.5) == pytest.approx(1500.0)
    assert milliseconds_to_seconds(1500) == pytest.approx(1.5)
    arr = np.array([0.5, 1.0, np.nan])
    ms = seconds_to_milliseconds(arr)
    assert np.allclose(ms[:2], [500.0, 1000.0])
    assert math.isnan(ms[2])
    int_arr = np.array([1, 2, 3], dtype=np.int64)
    assert np.allclose(seconds_to_milliseconds(int_arr), [1000.0, 2000.0, 3000.0])
