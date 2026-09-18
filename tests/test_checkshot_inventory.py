"""
tests/test_checkshot_inventory.py - Validation suite for
p2mem.io.checkshot_inventory (Increment 4: deterministic, metadata-only
inventory-table builders).

PORTABLE unit tests only: hand-built typed result objects, never the real
project files. Verifies (a) correct row content, (b) deterministic/sorted
ordering, (c) environment-independent output (no absolute path leakage in
a failure row's sanitized message), and (d) Tier C classification and
well-status disclosure in the JSON manifest.
"""

import numpy as np
import pytest

from p2mem.checkshot_models import (
    AxisConditionedLookupTable,
    AxisTimeDepthTieRegisterEntry,
    CheckshotAvailabilityRecord,
    CheckshotFileContract,
    CheckshotHeaderInfo,
    CheckshotIngestionFailure,
    CheckshotIngestionIssue,
    CheckshotStationData,
    CheckshotSurveyDepthComparisonResult,
    CheckshotWellResult,
    ConditionedCheckshotData,
    DuplicateTieRegisterEntry,
    SonicCheckshotDriftResult,
    TimeDepthMappingSummary,
    VelocityDiagnosticsResult,
)
from p2mem.io.checkshot_inventory import (
    build_checkshot_depth_tie_qc_rows,
    build_checkshot_file_inventory_rows,
    build_checkshot_issues_rows,
    build_checkshot_time_axis_tie_register_rows,
    build_checkshot_time_depth_manifest,
    build_checkshot_velocity_summary_rows,
    build_duplicate_tie_register_rows,
    build_sonic_checkshot_drift_rows,
    build_time_depth_mapping_rows,
)


def _make_contract(project_well_key, identity_status, model_use) -> CheckshotFileContract:
    return CheckshotFileContract(
        source_filename=f"{project_well_key}-Checkshot.txt",
        expected_sha256="a" * 64,
        project_well_key=project_well_key,
        well_identity_evidence_status=identity_status,
        well_identity_evidence_notes="test",
        model_use_status=model_use,
        expected_survey_statement="stmt",
        expected_column_header_line="Depth\tTVDSS\tOWT(sec)",
        expected_column_order=("Depth", "TVDSS", "OWT(sec)"),
        expected_column_count=3,
        expected_time_type="OWT",
        expected_time_unit="s",
        expected_vertical_correction_fragment="vertically corrected",
        expected_srd_reference_fragment="SRD",
        expected_row_count=3,
        expected_depth_min_m=100.0,
        expected_depth_max_m=300.0,
        expected_tvdss_min_m=95.0,
        expected_tvdss_max_m=285.0,
        expected_owt_min_s=0.1,
        expected_owt_max_s=0.28,
        numeric_range_tolerance=0.0001,
        depth_basis_interpretation_status="candidate_md_evaluated_against_locked_survey",
        duplicate_tie_policy="test_policy",
        interpolation_policy="piecewise_linear_no_extrapolation",
        extrapolation_policy="disallowed_nan_outside_coverage",
        notes="test",
    )


def _make_result(well_key, identity_status="verified", model_use="primary_model") -> CheckshotWellResult:
    contract = _make_contract(well_key, identity_status, model_use)
    header = CheckshotHeaderInfo(
        source_filename=contract.source_filename,
        sha256="a" * 64,
        survey_statement="stmt",
        column_header_line="Depth\tTVDSS\tOWT(sec)",
        column_names=("Depth", "TVDSS", "OWT(sec)"),
        line_ending_convention="CRLF",
    )
    raw = CheckshotStationData(
        Depth_source_m=np.array([100.0, 200.0, 300.0]),
        TVDSS_source_m=np.array([95.0, 190.0, 285.0]),
        OWT_source_s=np.array([0.10, 0.19, 0.28]),
    )
    conditioned = ConditionedCheckshotData(
        Depth_conditioned_m=raw.Depth_source_m,
        TVDSS_conditioned_m=raw.TVDSS_source_m,
        OWT_conditioned_s=raw.OWT_source_s,
        n_raw_rows=3, n_conditioned_rows=3, n_tie_groups=0,
        conditioning_method="test",
    )
    velocity = VelocityDiagnosticsResult(
        well_key=well_key,
        Depth_conditioned_m=conditioned.Depth_conditioned_m,
        Vavg_m_s=np.array([950.0, 1000.0, 1017.857]),
        Vint_m_s=np.array([950.0, 1055.556]),
        vint_invalid_mask=np.array([False, False]),
        n_vint_intervals=2, n_vint_invalid=0,
        vint_invalid_reason_counts={"non_positive_delta_owt": 0, "non_positive_delta_tvdss": 0},
    )
    comparison = CheckshotSurveyDepthComparisonResult(
        well_key=well_key, n_compared=3, n_outside_survey_md_coverage=0,
        min_residual_m=-0.05, max_residual_m=0.05, max_abs_residual_m=0.05,
        mean_residual_m=0.0, median_residual_m=0.0, rmse_m=0.03,
        first_residual_m=0.05, last_residual_m=-0.05,
        residual_trend_description="near-constant residual across the compared depth interval",
        depth_basis_interpretation_status="candidate_md_evaluated_against_locked_survey",
        residual_sign_convention="residual_m = TVDSS_survey_interpolated_m - TVDSS_source_m",
    )
    issues = (
        CheckshotIngestionIssue("WARNING", "DEPTH_BASIS_NOT_EXPLICITLY_DECLARED", "msg", header.source_filename),
    )
    return CheckshotWellResult(
        header=header, contract=contract, raw=raw, duplicate_ties=(), conditioned=conditioned,
        velocity=velocity, depth_comparison=comparison, issues=issues, contract_status="PASSED",
    )


# ---------------------------------------------------------------------------
# File inventory rows
# ---------------------------------------------------------------------------
def test_file_inventory_rows_include_results_failures_and_availability_sorted():
    results = {"Boreas_1": _make_result("Boreas_1")}
    failures = {
        "Broken_Well": CheckshotIngestionFailure(
            well_key="Broken_Well", source_path="/abs/path/to/Broken_Well-Checkshot.txt",
            error_type="parsing_failure", message="/abs/path/to/Broken_Well-Checkshot.txt: bad row",
            exception=ValueError("bad row"),
        )
    }
    availability = {
        "Poseidon_North_1": CheckshotAvailabilityRecord(
            "Poseidon_North_1", "NOT_AVAILABLE", "No approved checkshot file exists."
        )
    }
    rows = build_checkshot_file_inventory_rows(results, failures, availability)
    well_keys = [r["well_key"] for r in rows]
    assert well_keys == sorted(well_keys)
    assert well_keys == ["Boreas_1", "Broken_Well", "Poseidon_North_1"]

    boreas_row = next(r for r in rows if r["well_key"] == "Boreas_1")
    assert boreas_row["contract_status"] == "PASSED"
    assert boreas_row["n_raw_rows"] == 3

    broken_row = next(r for r in rows if r["well_key"] == "Broken_Well")
    assert broken_row["contract_status"] == "FAILED"
    assert "/abs/path/to/" not in broken_row["error_message"]
    assert "Broken_Well-Checkshot.txt" in broken_row["error_message"]

    na_row = next(r for r in rows if r["well_key"] == "Poseidon_North_1")
    assert na_row["contract_status"] == "NOT_AVAILABLE"


def test_issues_rows_sanitize_absolute_paths():
    failures = {
        "Well_X": CheckshotIngestionFailure(
            well_key="Well_X", source_path="/home/user/secret_build_dir/Well_X-Checkshot.txt",
            error_type="file_not_found",
            message="/home/user/secret_build_dir/Well_X-Checkshot.txt not found",
            exception=FileNotFoundError(),
        )
    }
    rows = build_checkshot_issues_rows({}, failures)
    assert len(rows) == 1
    assert "/home/user/secret_build_dir/" not in rows[0]["message"]
    assert rows[0]["source_filename"] == "Well_X-Checkshot.txt"


def test_issues_rows_include_well_issues():
    results = {"Poseidon_2": _make_result("Poseidon_2")}
    rows = build_checkshot_issues_rows(results, {})
    assert len(rows) == 1
    assert rows[0]["code"] == "DEPTH_BASIS_NOT_EXPLICITLY_DECLARED"
    assert rows[0]["severity"] == "WARNING"


# ---------------------------------------------------------------------------
# Duplicate tie register rows
# ---------------------------------------------------------------------------
def test_duplicate_tie_register_rows_serialize_tuples_as_delimited_strings():
    result = _make_result("Poseidon_2")
    tie = DuplicateTieRegisterEntry(
        well_key="Poseidon_2", axis="Depth", tie_value_m=200.0,
        source_row_indices=(1, 2), original_tvdss_m=(190.0, 190.5), original_owt_s=(0.19, 0.191),
        duplicate_type="repeated_depth_distinct_tvdss_owt", group_size=2,
        tvdss_value_spread_m=0.5, owt_value_spread_s=0.001,
        selected_representative_tvdss_m=190.25, selected_representative_owt_s=0.1905,
        conditioning_rule="median of the tied group", affected_downstream_outputs=("a", "b"),
    )
    from dataclasses import replace
    result = replace(result, duplicate_ties=(tie,))
    rows = build_duplicate_tie_register_rows({"Poseidon_2": result})
    assert len(rows) == 1
    assert rows[0]["source_row_indices"] == "1;2"
    assert rows[0]["original_tvdss_m"] == "190.0;190.5"
    assert rows[0]["affected_downstream_outputs"] == "a;b"


# ---------------------------------------------------------------------------
# Axis-tie (TVDSS/OWT) register rows (Increment 4.1)
# ---------------------------------------------------------------------------
def _make_axis_tie_entry(well_key="Poseidon_2", direction="tvdss_to_owt"):
    axis, dependent = (
        ("TVDSS_conditioned_m", "OWT_conditioned_s")
        if direction == "tvdss_to_owt"
        else ("OWT_conditioned_s", "TVDSS_conditioned_m")
    )
    return AxisTimeDepthTieRegisterEntry(
        well_key=well_key,
        interpolation_direction=direction,
        axis=axis,
        dependent_axis=dependent,
        tie_axis_value=100.0,
        conditioned_row_indices=(1, 2),
        associated_depth_m=(200.0, 300.0),
        original_dependent_values=(0.20, 0.21),
        group_size=2,
        dependent_value_spread=0.01,
        selected_representative_dependent_value=0.205,
        conditioning_rule="median of the tied group's values, order-invariant",
        tie_kind="genuinely_non_unique",
        affected_downstream_outputs=(f"{direction}_lookup_table", "forward_inverse_time_depth_interpolation"),
    )


def test_axis_tie_register_rows_serialize_tuples_as_delimited_strings():
    from dataclasses import replace

    result = _make_result("Poseidon_2")
    entry = _make_axis_tie_entry("Poseidon_2")
    result = replace(result, axis_tie_entries=(entry,))
    rows = build_checkshot_time_axis_tie_register_rows({"Poseidon_2": result})
    assert len(rows) == 1
    row = rows[0]
    assert row["well_key"] == "Poseidon_2"
    assert row["interpolation_direction"] == "tvdss_to_owt"
    assert row["conditioned_row_indices"] == "1;2"
    assert row["associated_depth_m"] == "200.0;300.0"
    assert row["original_dependent_values"] == "0.2;0.21"
    assert row["group_size"] == 2
    assert row["tie_kind"] == "genuinely_non_unique"
    assert row["affected_downstream_outputs"] == "tvdss_to_owt_lookup_table;forward_inverse_time_depth_interpolation"


def test_axis_tie_register_rows_sorted_by_well_key_and_empty_when_no_ties():
    from dataclasses import replace

    result_a = replace(_make_result("Boreas_1"), axis_tie_entries=(_make_axis_tie_entry("Boreas_1"),))
    result_b = _make_result("Poseidon_2")  # default axis_tie_entries=() -- no ties
    rows = build_checkshot_time_axis_tie_register_rows({"Poseidon_2": result_b, "Boreas_1": result_a})
    assert len(rows) == 1
    assert rows[0]["well_key"] == "Boreas_1"


def test_axis_tie_register_rows_deterministic_and_json_serializable_no_absolute_paths():
    import json
    from dataclasses import replace

    result = replace(_make_result("Poseidon_2"), axis_tie_entries=(_make_axis_tie_entry("Poseidon_2"),))
    rows1 = build_checkshot_time_axis_tie_register_rows({"Poseidon_2": result})
    rows2 = build_checkshot_time_axis_tie_register_rows({"Poseidon_2": result})
    assert json.dumps(rows1, sort_keys=True) == json.dumps(rows2, sort_keys=True)
    serialized = json.dumps(rows1)
    assert "/home/" not in serialized and "/root/" not in serialized and "C:\\" not in serialized


# ---------------------------------------------------------------------------
# Per-well axis-tie-conditioning summary embedded in the manifest
# (Increment 4.1) - distinct from n_tie_groups (Depth-axis ties only)
# ---------------------------------------------------------------------------
def test_manifest_axis_tie_conditioning_summary_defaults_to_zero_counts_when_no_axis_tables():
    results = {"Poseidon_2": _make_result("Poseidon_2")}  # axis_tables defaults to {}
    manifest = build_checkshot_time_depth_manifest(results, {}, {}, {}, {})
    summary = manifest["wells"]["Poseidon_2"]["axis_tie_conditioning"]
    assert summary["n_tvdss_axis_tie_groups"] == 0
    assert summary["n_owt_axis_tie_groups"] == 0
    assert "order-invariant" in summary["axis_tie_conditioning_policy"]


def test_manifest_axis_tie_conditioning_summary_reflects_axis_tables():
    from dataclasses import replace

    table_to_owt = AxisConditionedLookupTable(
        well_key="Poseidon_2", interpolation_direction="tvdss_to_owt",
        independent_axis_name="TVDSS_conditioned_m", dependent_axis_name="OWT_conditioned_s",
        axis_values=np.array([90.0, 100.0]), dependent_values=np.array([0.10, 0.205]),
        n_input_points=3, n_output_points=2, n_axis_tie_groups=1,
        n_collapsed_points=1, n_identical_pairs=0, n_genuinely_nonunique_groups=1,
        conditioning_method="axis_tie_median_representative_order_invariant_v1",
    )
    table_to_tvdss = AxisConditionedLookupTable(
        well_key="Poseidon_2", interpolation_direction="owt_to_tvdss",
        independent_axis_name="OWT_conditioned_s", dependent_axis_name="TVDSS_conditioned_m",
        axis_values=np.array([0.10, 0.205]), dependent_values=np.array([90.0, 100.0]),
        n_input_points=3, n_output_points=2, n_axis_tie_groups=0,
        n_collapsed_points=0, n_identical_pairs=0, n_genuinely_nonunique_groups=0,
        conditioning_method="axis_tie_median_representative_order_invariant_v1",
    )
    result = replace(
        _make_result("Poseidon_2"),
        axis_tables={"tvdss_to_owt": table_to_owt, "owt_to_tvdss": table_to_tvdss},
    )
    manifest = build_checkshot_time_depth_manifest({"Poseidon_2": result}, {}, {}, {}, {})
    summary = manifest["wells"]["Poseidon_2"]["axis_tie_conditioning"]
    assert summary["n_tvdss_axis_tie_groups"] == 1
    assert summary["n_tvdss_axis_genuinely_nonunique_groups"] == 1
    assert summary["n_owt_axis_tie_groups"] == 0


# ---------------------------------------------------------------------------
# Depth-tie QC rows
# ---------------------------------------------------------------------------
def test_depth_tie_qc_rows_skip_none_comparison():
    from dataclasses import replace
    result = _make_result("Boreas_1")
    result_no_comparison = replace(result, depth_comparison=None)
    rows = build_checkshot_depth_tie_qc_rows({"Boreas_1": result_no_comparison})
    assert rows == []


def test_depth_tie_qc_rows_content():
    result = _make_result("Boreas_1")
    rows = build_checkshot_depth_tie_qc_rows({"Boreas_1": result})
    assert len(rows) == 1
    assert rows[0]["well_key"] == "Boreas_1"
    assert rows[0]["max_abs_residual_m"] == 0.05


# ---------------------------------------------------------------------------
# Velocity summary rows
# ---------------------------------------------------------------------------
def test_velocity_summary_rows_aggregate_statistics():
    result = _make_result("Proteus_1ST2")
    rows = build_checkshot_velocity_summary_rows({"Proteus_1ST2": result})
    assert len(rows) == 1
    row = rows[0]
    assert row["n_conditioned_rows"] == 3
    assert row["n_vint_intervals"] == 2
    assert row["n_vint_invalid"] == 0
    assert row["vavg_min_m_s"] == pytest.approx(950.0)


# ---------------------------------------------------------------------------
# Sonic drift / time-depth mapping rows
# ---------------------------------------------------------------------------
def test_sonic_drift_rows_join_limitations():
    drift = SonicCheckshotDriftResult(
        well_key="Poseidon_2", md_interval_start_m=2448.6, md_interval_end_m=4064.2,
        n_sonic_samples=10602, selection_criteria="longest run", integration_method="trapezoidal",
        sonic_transit_time_s=0.3913, checkshot_owt_increment_s=0.3746,
        sonic_minus_checkshot_ms=16.66, checkshot_minus_sonic_ms=-16.66,
        sonic_minus_checkshot_percent=4.45,
        limitations=("limitation one", "limitation two"),
    )
    rows = build_sonic_checkshot_drift_rows({"Poseidon_2": drift})
    assert rows[0]["limitations"] == "limitation one | limitation two"


def test_time_depth_mapping_rows_content():
    summary = TimeDepthMappingSummary(
        well_key="Poseidon_2", n_las_samples=31897, n_inside_coverage=22521,
        n_shallower_than_coverage=5104, n_deeper_than_coverage=4272,
        mapped_fraction=0.706, checkshot_depth_min_m=1267.8, checkshot_depth_max_m=4700.0,
        las_md_min_m=490.0, las_md_max_m=5350.9507,
        interpolation_method="piecewise_linear_no_extrapolation", n_extrapolated=0,
    )
    rows = build_time_depth_mapping_rows({"Poseidon_2": summary})
    assert rows[0]["n_extrapolated"] == 0
    assert rows[0]["mapped_fraction"] == pytest.approx(0.706)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
def test_manifest_carries_tier_c_and_well_statuses():
    results = {
        "Poseidon_2": _make_result("Poseidon_2", "verified", "primary_model"),
        "Boreas_1": _make_result("Boreas_1", "verified", "qc_only"),
        "Proteus_1ST2": _make_result("Proteus_1ST2", "inferred_unverified", "qc_only"),
    }
    availability = {
        "Poseidon_North_1": CheckshotAvailabilityRecord(
            "Poseidon_North_1", "NOT_AVAILABLE", "No approved checkshot file exists."
        )
    }
    manifest = build_checkshot_time_depth_manifest(results, {}, availability, {}, {})
    assert manifest["tier_classification"].startswith("Tier C")
    assert manifest["wells"]["Poseidon_2"]["model_use_status"] == "primary_model"
    assert manifest["wells"]["Boreas_1"]["model_use_status"] == "qc_only"
    assert manifest["wells"]["Proteus_1ST2"]["well_identity_evidence_status"] == "inferred_unverified"
    assert manifest["wells"]["Poseidon_North_1"]["checkshot_availability"] == "NOT_AVAILABLE"
    assert manifest["n_wells_checkshot_available"] == 3
    assert manifest["n_wells_checkshot_not_available"] == 1


def test_manifest_is_json_serializable_and_deterministic():
    import json
    results = {"Poseidon_2": _make_result("Poseidon_2")}
    m1 = build_checkshot_time_depth_manifest(results, {}, {}, {}, {})
    m2 = build_checkshot_time_depth_manifest(results, {}, {}, {}, {})
    assert json.dumps(m1, sort_keys=True) == json.dumps(m2, sort_keys=True)


def test_manifest_sanitizes_failed_well_paths():
    failures = {
        "Well_X": CheckshotIngestionFailure(
            well_key="Well_X", source_path="/home/user/build/Well_X-Checkshot.txt",
            error_type="file_not_found", message="/home/user/build/Well_X-Checkshot.txt missing",
            exception=FileNotFoundError(),
        )
    }
    manifest = build_checkshot_time_depth_manifest({}, failures, {}, {}, {})
    assert "/home/user/build/" not in manifest["failed_wells"]["Well_X"]["message"]
