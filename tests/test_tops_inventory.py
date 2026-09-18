"""
tests/test_tops_inventory.py - Validation suite for p2mem.io.tops_inventory
(Increment 5: deterministic, metadata-only inventory-table builders for the
formation-top ingestion/reconciliation/survey-mapping layer).

PORTABLE unit tests only: hand-built typed result objects (mirroring
tests/test_checkshot_inventory.py's pattern), never the real project top
files. Verifies (a) correct row content, (b) deterministic/sorted ordering,
(c) environment-independent output (no absolute-path leakage in a failure
row's sanitized message), and (d) Tier C classification and well-status
disclosure in the JSON manifest.
"""

import numpy as np
import pytest

from p2mem.top_models import (
    FormationTopAvailabilityRecord,
    FormationTopWellResult,
    HRSTopFileContract,
    HRSTopHeaderInfo,
    HRSTopStationData,
    ReadableTopFileContract,
    ReadableTopHeaderInfo,
    ReadableTopStationData,
    TopIngestionFailure,
    TopIngestionIssue,
    TopMarkerRecord,
    TopReconciliationEntry,
)
from p2mem.io.tops_inventory import (
    build_formation_top_manifest,
    build_top_availability_rows,
    build_top_corrected_marker_rows,
    build_top_file_inventory_rows,
    build_top_issues_rows,
    build_top_marker_register_rows,
    build_top_reconciliation_rows,
)


def _make_hrs_contract(well_key) -> HRSTopFileContract:
    return HRSTopFileContract(
        source_filename=f"{well_key}_HRS_tops_no_wellname_MDRT.txt",
        expected_sha256="a" * 64,
        project_well_key=well_key,
        representation_type="HRS_MDRT_only",
        well_identity_evidence_status="inferred_unverified",
        well_identity_evidence_notes="filename-only association; never content-verified.",
        model_use_status="primary_model",
        expected_column_header_line="Top_Name\tMDRT_m",
        expected_column_order=("Top_Name", "MDRT_m"),
        expected_column_count=2,
        expected_marker_count=2,
        expected_mdrt_min_m=100.0,
        expected_mdrt_max_m=200.0,
        numeric_range_tolerance=0.005,
        datum_depth_column_interpretation="MDRT referenced to rotary table, increasing downward.",
        notes="test",
    )


def _make_readable_contract(well_key) -> ReadableTopFileContract:
    return ReadableTopFileContract(
        source_filename=f"{well_key}_selected_well_tops.txt",
        expected_sha256="b" * 64,
        project_well_key=well_key,
        representation_type="selected_readable_MDRT_TVDSS",
        well_identity_evidence_status="inferred_unverified",
        well_identity_evidence_notes="project-supplied in-file comment only; never content-verified.",
        model_use_status="primary_model",
        expected_well_name_from_comment=well_key.replace("_", " "),
        expected_column_header_line="TOP_NAME\tMDRT_M\tTVDSS_M\tNOTE",
        expected_column_order=("TOP_NAME", "MDRT_M", "TVDSS_M", "NOTE"),
        expected_column_count=4,
        expected_marker_count=2,
        expected_mdrt_min_m=100.0,
        expected_mdrt_max_m=200.0,
        expected_tvdss_min_m=95.0,
        expected_tvdss_max_m=190.0,
        numeric_range_tolerance=0.005,
        datum_depth_column_interpretation="MDRT referenced to rotary table; TVDSS is the file's own supplied value.",
        notes="test",
    )


def _make_result(well_key, issues=()) -> FormationTopWellResult:
    hrs_contract = _make_hrs_contract(well_key)
    readable_contract = _make_readable_contract(well_key)
    hrs_header = HRSTopHeaderInfo(
        source_filename=hrs_contract.source_filename, sha256="a" * 64,
        column_header_line="Top_Name\tMDRT_m", column_names=("Top_Name", "MDRT_m"),
        well_identity_source="filename_only", line_ending_convention="LF",
        header_line_count=1, data_line_offset=1,
    )
    readable_header = ReadableTopHeaderInfo(
        source_filename=readable_contract.source_filename, sha256="b" * 64,
        comment_lines=(f"# Selected readable well tops for {well_key.replace('_', ' ')}",),
        well_name_from_comment=well_key.replace("_", " "),
        column_header_line="TOP_NAME\tMDRT_M\tTVDSS_M\tNOTE",
        column_names=("TOP_NAME", "MDRT_M", "TVDSS_M", "NOTE"),
        separator_line_raw="-" * 40, well_identity_source="in_file_comment_project_supplied",
        line_ending_convention="LF", header_line_count=4, data_line_offset=4,
    )
    hrs_raw = HRSTopStationData(
        Top_Name_source=("Marker A", "Marker B"), MDRT_source_m=np.array([100.0, 200.0]),
    )
    readable_raw = ReadableTopStationData(
        TOP_NAME_source=("Marker A", "Marker B"), MDRT_source_m=np.array([100.0, 200.0]),
        TVDSS_source_m=np.array([95.0, 190.0]), NOTE_source=("", ""),
    )
    reconciliation = (
        TopReconciliationEntry(
            well_key=well_key, canonical_marker_name="Marker A",
            hrs_marker_name_raw="Marker A", readable_marker_name_raw="Marker A",
            hrs_row_number=0, readable_row_number=0,
            present_in_hrs=True, present_in_readable=True, name_match_status="exact",
            MDRT_source_hrs_m=100.0, MDRT_source_readable_m=100.0,
            MDRT_agreement_readable_minus_hrs_m=0.0, mdrt_status="MATCHED",
            TVDSS_source_readable_m=95.0, note_readable="",
            reconciliation_notes="Present in both sources; MDRT agrees within tolerance.",
        ),
        TopReconciliationEntry(
            well_key=well_key, canonical_marker_name="Marker B",
            hrs_marker_name_raw="Marker B", readable_marker_name_raw="Marker B",
            hrs_row_number=1, readable_row_number=1,
            present_in_hrs=True, present_in_readable=True, name_match_status="exact",
            MDRT_source_hrs_m=200.0, MDRT_source_readable_m=200.0,
            MDRT_agreement_readable_minus_hrs_m=0.0, mdrt_status="MATCHED",
            TVDSS_source_readable_m=190.0, note_readable="",
            reconciliation_notes="Present in both sources; MDRT agrees within tolerance.",
        ),
    )
    markers = (
        TopMarkerRecord(
            well_key=well_key, canonical_marker_name="Marker A",
            MDRT_source_hrs_m=100.0, MDRT_source_readable_m=100.0, MDRT_reconciled_m=100.0,
            mdrt_authority_basis="hrs_and_readable_agree", TVDSS_source_m=95.0,
            depth_basis_used="petrel_source_trace", interpolation_method="piecewise_linear_station_interpolation",
            TVD_survey_m=99.5, TVDSS_survey_corrected_m=79.5,
            TVDSS_residual_source_minus_survey_m=15.5, mapping_status="mapped_within_coverage",
            well_identity_evidence_status="inferred_unverified", notes="mapped",
        ),
        TopMarkerRecord(
            well_key=well_key, canonical_marker_name="Marker B",
            MDRT_source_hrs_m=200.0, MDRT_source_readable_m=200.0, MDRT_reconciled_m=200.0,
            mdrt_authority_basis="hrs_and_readable_agree", TVDSS_source_m=190.0,
            depth_basis_used="petrel_source_trace", interpolation_method="piecewise_linear_station_interpolation",
            TVD_survey_m=194.6, TVDSS_survey_corrected_m=174.6,
            TVDSS_residual_source_minus_survey_m=15.4, mapping_status="mapped_within_coverage",
            well_identity_evidence_status="inferred_unverified", notes="mapped",
        ),
    )
    return FormationTopWellResult(
        well_key=well_key, hrs_header=hrs_header, hrs_contract=hrs_contract, hrs_raw=hrs_raw,
        readable_header=readable_header, readable_contract=readable_contract, readable_raw=readable_raw,
        reconciliation=reconciliation, markers=markers, issues=issues, contract_status="PASSED",
    )


# ---------------------------------------------------------------------------
# File inventory rows
# ---------------------------------------------------------------------------
def test_file_inventory_rows_two_rows_per_well_plus_failures_and_availability():
    results = {"Boreas_1": _make_result("Boreas_1")}
    failures = {
        "Broken_Well": TopIngestionFailure(
            well_key="Broken_Well", source_path="/abs/path/to/Broken_Well_HRS_tops_no_wellname_MDRT.txt",
            error_type="parsing_failure", message="/abs/path/to/Broken_Well_HRS_tops_no_wellname_MDRT.txt: bad row",
            exception=ValueError("bad row"),
        )
    }
    availability = {
        "Poseidon_North_1": FormationTopAvailabilityRecord(
            "Poseidon_North_1", "NOT_AVAILABLE", "No approved formation-top file exists."
        )
    }
    rows = build_top_file_inventory_rows(results, failures, availability)
    well_keys = [r["well_key"] for r in rows]
    # Two rows for Boreas_1 (HRS + readable), one each for the failure and
    # the NOT_AVAILABLE well.
    assert well_keys.count("Boreas_1") == 2
    assert well_keys.count("Broken_Well") == 1
    assert well_keys.count("Poseidon_North_1") == 1
    assert well_keys == sorted(well_keys)

    boreas_rows = [r for r in rows if r["well_key"] == "Boreas_1"]
    hrs_row = next(r for r in boreas_rows if r["representation_type"] == "HRS_MDRT_only")
    readable_row = next(r for r in boreas_rows if r["representation_type"] == "selected_readable_MDRT_TVDSS")
    assert hrs_row["tvdss_min_m"] == ""  # HRS format has no TVDSS column
    assert readable_row["tvdss_min_m"] == pytest.approx(95.0)
    assert hrs_row["n_markers"] == 2
    assert hrs_row["contract_status"] == "PASSED"

    broken_row = next(r for r in rows if r["well_key"] == "Broken_Well")
    assert broken_row["contract_status"] == "FAILED"

    na_row = next(r for r in rows if r["well_key"] == "Poseidon_North_1")
    assert na_row["contract_status"] == "NOT_AVAILABLE"


def test_file_inventory_rows_count_errors_and_warnings_per_source_file():
    issues = (
        TopIngestionIssue("WARNING", "MDRT_MISMATCH", "msg", "Poseidon_2_HRS_tops_no_wellname_MDRT.txt"),
        TopIngestionIssue("ERROR", "DUPLICATE_MARKER_NAME", "msg", "Poseidon_2_selected_well_tops.txt"),
    )
    results = {"Poseidon_2": _make_result("Poseidon_2", issues=issues)}
    rows = build_top_file_inventory_rows(results, {}, {})
    hrs_row = next(r for r in rows if r["representation_type"] == "HRS_MDRT_only")
    readable_row = next(r for r in rows if r["representation_type"] == "selected_readable_MDRT_TVDSS")
    assert hrs_row["n_warnings"] == 1 and hrs_row["n_errors"] == 0
    assert readable_row["n_errors"] == 1 and readable_row["n_warnings"] == 0


# ---------------------------------------------------------------------------
# Marker / source register rows
# ---------------------------------------------------------------------------
def test_marker_register_rows_preserve_raw_source_values_per_file():
    results = {"Poseidon_2": _make_result("Poseidon_2")}
    rows = build_top_marker_register_rows(results)
    # 2 HRS rows + 2 readable rows = 4 total for this one well.
    assert len(rows) == 4
    hrs_rows = [r for r in rows if r["source_representation"] == "HRS_MDRT_only"]
    readable_rows = [r for r in rows if r["source_representation"] == "selected_readable_MDRT_TVDSS"]
    assert len(hrs_rows) == 2 and len(readable_rows) == 2
    assert hrs_rows[0]["TVDSS_source_m"] == ""  # HRS carries no TVDSS at all
    assert readable_rows[0]["TVDSS_source_m"] == pytest.approx(95.0)
    assert hrs_rows[0]["well_identity_source"] == "filename_only"
    assert readable_rows[0]["well_identity_source"] == "in_file_comment_project_supplied"
    # Row numbers trace back to original (0-indexed) file order.
    assert [r["source_row_number"] for r in hrs_rows] == [0, 1]


def test_marker_register_rows_sorted_by_well_key():
    results = {"Poseidon_2": _make_result("Poseidon_2"), "Boreas_1": _make_result("Boreas_1")}
    rows = build_top_marker_register_rows(results)
    well_keys = [r["well_key"] for r in rows]
    assert well_keys == sorted(well_keys)
    assert well_keys[0] == "Boreas_1"


# ---------------------------------------------------------------------------
# HRS-versus-readable reconciliation rows
# ---------------------------------------------------------------------------
def test_reconciliation_rows_content_and_none_handling():
    results = {"Poseidon_2": _make_result("Poseidon_2")}
    rows = build_top_reconciliation_rows(results)
    assert len(rows) == 2
    row_a = next(r for r in rows if r["canonical_marker_name"] == "Marker A")
    assert row_a["mdrt_status"] == "MATCHED"
    assert row_a["present_in_hrs"] is True and row_a["present_in_readable"] is True
    assert row_a["MDRT_source_hrs_m"] == pytest.approx(100.0)
    assert row_a["TVDSS_source_readable_m"] == pytest.approx(95.0)


def test_reconciliation_rows_none_fields_become_empty_string():
    entry = TopReconciliationEntry(
        well_key="Test_Well", canonical_marker_name="Marker Z",
        hrs_marker_name_raw=None, readable_marker_name_raw="Marker Z",
        hrs_row_number=None, readable_row_number=0,
        present_in_hrs=False, present_in_readable=True, name_match_status="missing_in_hrs",
        MDRT_source_hrs_m=None, MDRT_source_readable_m=300.0,
        MDRT_agreement_readable_minus_hrs_m=None, mdrt_status="NOT_COMPARABLE",
        TVDSS_source_readable_m=285.0, note_readable="", reconciliation_notes="Present only in readable source.",
    )
    from dataclasses import replace
    result = replace(_make_result("Test_Well"), reconciliation=(entry,))
    rows = build_top_reconciliation_rows({"Test_Well": result})
    assert len(rows) == 1
    assert rows[0]["hrs_marker_name_raw"] == ""
    assert rows[0]["hrs_row_number"] == ""
    assert rows[0]["MDRT_source_hrs_m"] == ""
    assert rows[0]["mdrt_status"] == "NOT_COMPARABLE"


# ---------------------------------------------------------------------------
# Corrected, survey-mapped marker rows
# ---------------------------------------------------------------------------
def test_corrected_marker_rows_carry_explicit_residual_field():
    results = {"Poseidon_2": _make_result("Poseidon_2")}
    rows = build_top_corrected_marker_rows(results)
    assert len(rows) == 2
    row_a = next(r for r in rows if r["canonical_marker_name"] == "Marker A")
    assert row_a["TVDSS_residual_source_minus_survey_m"] == pytest.approx(15.5)
    assert row_a["mapping_status"] == "mapped_within_coverage"
    assert row_a["mdrt_authority_basis"] == "hrs_and_readable_agree"


def test_corrected_marker_rows_none_fields_become_empty_string_when_not_mapped():
    marker = TopMarkerRecord(
        well_key="Test_Well", canonical_marker_name="Marker Z",
        MDRT_source_hrs_m=100.0, MDRT_source_readable_m=999.0, MDRT_reconciled_m=None,
        mdrt_authority_basis="disagreement_unresolved", TVDSS_source_m=None,
        depth_basis_used=None, interpolation_method=None, TVD_survey_m=None,
        TVDSS_survey_corrected_m=None, TVDSS_residual_source_minus_survey_m=None,
        mapping_status="not_mapped_mdrt_unresolved", well_identity_evidence_status="inferred_unverified",
        notes="MDRT disagreement beyond tolerance; not silently resolved.",
    )
    from dataclasses import replace
    result = replace(_make_result("Test_Well"), markers=(marker,))
    rows = build_top_corrected_marker_rows({"Test_Well": result})
    assert len(rows) == 1
    assert rows[0]["MDRT_reconciled_m"] == ""
    assert rows[0]["TVDSS_survey_corrected_m"] == ""
    assert rows[0]["TVDSS_residual_source_minus_survey_m"] == ""
    assert rows[0]["mapping_status"] == "not_mapped_mdrt_unresolved"


# ---------------------------------------------------------------------------
# Issues rows
# ---------------------------------------------------------------------------
def test_issues_rows_include_well_issues_and_sanitize_failure_paths():
    issues = (TopIngestionIssue("WARNING", "MDRT_MISMATCH", "msg", "Poseidon_2_HRS_tops_no_wellname_MDRT.txt"),)
    results = {"Poseidon_2": _make_result("Poseidon_2", issues=issues)}
    failures = {
        "Well_X": TopIngestionFailure(
            well_key="Well_X", source_path="/home/user/secret_build_dir/Well_X_HRS_tops_no_wellname_MDRT.txt",
            error_type="file_not_found",
            message="/home/user/secret_build_dir/Well_X_HRS_tops_no_wellname_MDRT.txt not found",
            exception=FileNotFoundError(),
        )
    }
    rows = build_top_issues_rows(results, failures)
    assert len(rows) == 2
    well_row = next(r for r in rows if r["well_key"] == "Poseidon_2")
    assert well_row["code"] == "MDRT_MISMATCH" and well_row["severity"] == "WARNING"
    failure_row = next(r for r in rows if r["well_key"] == "Well_X")
    assert "/home/user/secret_build_dir/" not in failure_row["message"]
    assert failure_row["context"] == "Well_X_HRS_tops_no_wellname_MDRT.txt"


# ---------------------------------------------------------------------------
# Availability rows
# ---------------------------------------------------------------------------
def test_availability_rows_cover_available_failed_and_not_available_wells():
    results = {"Boreas_1": _make_result("Boreas_1")}
    failures = {
        "Well_X": TopIngestionFailure(
            well_key="Well_X", source_path="/abs/Well_X_HRS_tops_no_wellname_MDRT.txt",
            error_type="parsing_failure", message="/abs/Well_X_HRS_tops_no_wellname_MDRT.txt: bad row",
            exception=ValueError("bad row"),
        )
    }
    availability = {
        "Poseidon_North_1": FormationTopAvailabilityRecord(
            "Poseidon_North_1", "NOT_AVAILABLE", "No approved formation-top file exists."
        )
    }
    rows = build_top_availability_rows(results, failures, availability)
    well_keys = [r["well_key"] for r in rows]
    assert well_keys == sorted(well_keys)
    boreas = next(r for r in rows if r["well_key"] == "Boreas_1")
    assert boreas["formation_top_availability"] == "AVAILABLE"
    well_x = next(r for r in rows if r["well_key"] == "Well_X")
    assert well_x["formation_top_availability"] == "INGESTION_FAILED"
    assert "/abs/" not in well_x["notes"]
    na = next(r for r in rows if r["well_key"] == "Poseidon_North_1")
    assert na["formation_top_availability"] == "NOT_AVAILABLE"


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
def test_manifest_carries_tier_c_and_well_statuses():
    results = {"Poseidon_2": _make_result("Poseidon_2"), "Boreas_1": _make_result("Boreas_1")}
    availability = {
        "Poseidon_North_1": FormationTopAvailabilityRecord(
            "Poseidon_North_1", "NOT_AVAILABLE", "No approved formation-top file exists."
        ),
        "Proteus_1ST2": FormationTopAvailabilityRecord(
            "Proteus_1ST2", "NOT_AVAILABLE", "No approved formation-top file exists."
        ),
    }
    manifest = build_formation_top_manifest(results, {}, availability)
    assert manifest["tier_classification"].startswith("Tier C")
    assert manifest["increment"] == "5"
    assert manifest["wells"]["Poseidon_2"]["formation_top_availability"] == "AVAILABLE"
    assert manifest["wells"]["Poseidon_2"]["well_identity_evidence_status"] == "inferred_unverified"
    assert manifest["wells"]["Poseidon_2"]["n_canonical_markers"] == 2
    assert manifest["wells"]["Poseidon_2"]["n_markers_matched"] == 2
    assert manifest["wells"]["Poseidon_2"]["n_markers_mapped_within_coverage"] == 2
    assert manifest["wells"]["Poseidon_2"]["max_abs_tvdss_residual_source_minus_survey_m"] == pytest.approx(15.5)
    assert manifest["wells"]["Poseidon_North_1"]["formation_top_availability"] == "NOT_AVAILABLE"
    assert manifest["wells"]["Proteus_1ST2"]["formation_top_availability"] == "NOT_AVAILABLE"
    assert manifest["n_wells_formation_top_available"] == 2
    assert manifest["n_wells_formation_top_not_available"] == 2


def test_manifest_never_upgrades_to_verified_when_only_one_representation_is_verified():
    from dataclasses import replace

    result = _make_result("Poseidon_2")
    result = replace(result, hrs_contract=replace(result.hrs_contract, well_identity_evidence_status="verified"))
    # readable_contract remains "inferred_unverified" -> combined status must
    # NOT silently upgrade to "verified".
    manifest = build_formation_top_manifest({"Poseidon_2": result}, {}, {})
    assert manifest["wells"]["Poseidon_2"]["well_identity_evidence_status"] == "inferred_unverified"


def test_manifest_excludes_unmapped_markers_from_residual_statistics():
    from dataclasses import replace

    unresolved_marker = TopMarkerRecord(
        well_key="Poseidon_2", canonical_marker_name="Marker Z",
        MDRT_source_hrs_m=100.0, MDRT_source_readable_m=999.0, MDRT_reconciled_m=None,
        mdrt_authority_basis="disagreement_unresolved", TVDSS_source_m=None,
        depth_basis_used=None, interpolation_method=None, TVD_survey_m=None,
        TVDSS_survey_corrected_m=None, TVDSS_residual_source_minus_survey_m=None,
        mapping_status="not_mapped_mdrt_unresolved", well_identity_evidence_status="inferred_unverified",
        notes="MDRT disagreement beyond tolerance.",
    )
    base = _make_result("Poseidon_2")
    result = replace(base, markers=base.markers + (unresolved_marker,))
    manifest = build_formation_top_manifest({"Poseidon_2": result}, {}, {})
    well = manifest["wells"]["Poseidon_2"]
    assert well["n_markers_mapped_within_coverage"] == 2
    assert well["n_markers_not_mapped_mdrt_unresolved"] == 1
    # Residual max must be computed only over the two mapped markers (15.5,
    # 15.4), never inflated/deflated by the unresolved marker's None residual.
    assert well["max_abs_tvdss_residual_source_minus_survey_m"] == pytest.approx(15.5)


def test_manifest_is_json_serializable_and_deterministic():
    import json

    results = {"Poseidon_2": _make_result("Poseidon_2")}
    m1 = build_formation_top_manifest(results, {}, {})
    m2 = build_formation_top_manifest(results, {}, {})
    assert json.dumps(m1, sort_keys=True) == json.dumps(m2, sort_keys=True)


def test_manifest_sanitizes_failed_well_paths():
    failures = {
        "Well_X": TopIngestionFailure(
            well_key="Well_X", source_path="/home/user/build/Well_X_HRS_tops_no_wellname_MDRT.txt",
            error_type="file_not_found", message="/home/user/build/Well_X_HRS_tops_no_wellname_MDRT.txt missing",
            exception=FileNotFoundError(),
        )
    }
    manifest = build_formation_top_manifest({}, failures, {})
    assert "/home/user/build/" not in manifest["failed_wells"]["Well_X"]["message"]
    assert manifest["n_wells_failed"] == 1


# ===========================================================================
# Increment 5.1 - Finding 2 regression tests (readable-file absolute-path
# leakage): a failure originating from the READABLE file must have its own
# absolute path sanitized in every exported field - never only the (wrong)
# HRS path.
# ===========================================================================
def _readable_origin_failure(readable_abs_path: str, hrs_abs_path: str = "/build/Well_X_HRS_tops_no_wellname_MDRT.txt") -> TopIngestionFailure:
    return TopIngestionFailure(
        well_key="Well_X",
        source_path=readable_abs_path,  # correctly identifies the readable file as primary, post-fix
        error_type="parsing_failure",
        message=f"{readable_abs_path}: data row 1 contains a non-numeric MDRT/TVDSS token",
        exception=ValueError("bad row"),
        failure_origin="readable",
        hrs_path=hrs_abs_path,
        readable_path=readable_abs_path,
    )


def test_issues_rows_sanitize_readable_origin_failure_path():
    readable_path = "/home/private_build/Poseidon_2_selected_well_tops.txt"
    failures = {"Well_X": _readable_origin_failure(readable_path)}
    rows = build_top_issues_rows({}, failures)
    assert len(rows) == 1
    assert readable_path not in rows[0]["message"]
    assert "/home/private_build/" not in rows[0]["message"]
    # The context must identify the READABLE file, not the (unrelated) HRS path.
    assert rows[0]["context"] == "Poseidon_2_selected_well_tops.txt"


def test_availability_rows_sanitize_readable_origin_failure_path():
    readable_path = "/home/private_build/Poseidon_2_selected_well_tops.txt"
    failures = {"Well_X": _readable_origin_failure(readable_path)}
    rows = build_top_availability_rows({}, failures, {})
    row = next(r for r in rows if r["well_key"] == "Well_X")
    assert readable_path not in row["notes"]
    assert "/home/private_build/" not in row["notes"]


def test_manifest_sanitizes_readable_origin_failure_path():
    readable_path = "/home/private_build/Poseidon_2_selected_well_tops.txt"
    failures = {"Well_X": _readable_origin_failure(readable_path)}
    manifest = build_formation_top_manifest({}, failures, {})
    assert readable_path not in manifest["failed_wells"]["Well_X"]["message"]
    assert "/home/private_build/" not in manifest["failed_wells"]["Well_X"]["message"]


def test_file_inventory_rows_sanitize_readable_origin_failure_context():
    readable_path = "/home/private_build/Poseidon_2_selected_well_tops.txt"
    failures = {"Well_X": _readable_origin_failure(readable_path)}
    rows = build_top_file_inventory_rows({}, failures, {})
    row = next(r for r in rows if r["well_key"] == "Well_X")
    assert row["source_filename"] == "Poseidon_2_selected_well_tops.txt"
    assert "/home/private_build/" not in row["source_filename"]


def test_hrs_origin_failure_still_sanitizes_and_identifies_hrs_context():
    """The pre-existing HRS-failure sanitization behavior must remain
    correct after the Finding 2 restructuring (both explicit `hrs_path`
    now present, `failure_origin='hrs'`)."""
    hrs_path = "/home/user/secret_build_dir/Well_X_HRS_tops_no_wellname_MDRT.txt"
    failures = {
        "Well_X": TopIngestionFailure(
            well_key="Well_X", source_path=hrs_path, error_type="file_not_found",
            message=f"Formation-top (HRS) file not found: {hrs_path}", exception=FileNotFoundError(),
            failure_origin="hrs", hrs_path=hrs_path, readable_path="/home/user/secret_build_dir/Well_X_selected_well_tops.txt",
        )
    }
    issues_rows = build_top_issues_rows({}, failures)
    assert "/home/user/secret_build_dir/" not in issues_rows[0]["message"]
    assert issues_rows[0]["context"] == "Well_X_HRS_tops_no_wellname_MDRT.txt"
    availability_rows = build_top_availability_rows({}, failures, {})
    assert "/home/user/secret_build_dir/" not in availability_rows[0]["notes"]


def test_reconciliation_origin_failure_context_combines_both_basenames():
    """A "reconciliation"-origin failure has BOTH files successfully
    parsed - neither is individually "the" failing file, so the exported
    context retains both basenames (never silently drops one)."""
    hrs_path = "/build/Boreas_1_HRS_tops_no_wellname_MDRT.txt"
    readable_path = "/build/Boreas_1_selected_well_tops.txt"
    failures = {
        "Boreas_1": TopIngestionFailure(
            well_key="Boreas_1", source_path=hrs_path, error_type="reconciliation_failure",
            message="Boreas_1: 1 source-reconciliation ERROR(s): [NO_COMMON_MARKERS] ...",
            exception=RuntimeError("no common markers"),
            failure_origin="reconciliation", hrs_path=hrs_path, readable_path=readable_path,
        )
    }
    rows = build_top_issues_rows({}, failures)
    assert rows[0]["context"] == "Boreas_1_HRS_tops_no_wellname_MDRT.txt+Boreas_1_selected_well_tops.txt"
    assert "/build/" not in rows[0]["message"]
