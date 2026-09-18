"""
tests/test_tops.py - Validation suite for p2mem.io.tops (Increment 5:
formation-top ingestion, HRS-versus-readable source reconciliation, and
survey-corrected stratigraphic depth mapping).

PORTABLE unit tests only: small synthetic fixtures under
tests/fixtures/top_*.txt, and hand-built typed `DeviationWellResult`
objects (mirroring `tests/test_depth_mapping.py`'s established pattern).
Real four-file integration (which requires the private/real project
formation-top files) is a separate notebook/script run - see
dev_scratch_inc5/run_integration_05.py (not packaged) and
INCREMENT_05_MANIFEST.md for the actual recomputed real-data results.
"""

import hashlib
from pathlib import Path

import numpy as np
import pytest

from p2mem.deviation_models import (
    DEPTH_BASIS_PETREL_SOURCE,
    DepthBasisSelection,
    DeviationFileContract,
    DeviationHeaderInfo,
    DeviationStationData,
    DeviationWellResult,
    TrajectoryValidationResult,
)
from p2mem.top_models import HRSTopFileContract, ReadableTopFileContract
from p2mem.io.tops import (
    MDRT_AGREEMENT_TOLERANCE_M,
    TopContractDefinitionError,
    TopContractError,
    TopFileNotFoundError,
    TopParsingError,
    TopSourceReconciliationError,
    build_formation_top_markers,
    load_formation_top_contract_config,
    load_formation_top_surveys,
    load_formation_top_well,
    normalize_marker_name,
    parse_hrs_top_header,
    parse_readable_top_header,
    read_hrs_top_rows,
    read_readable_top_rows,
    reconcile_formation_top_sources,
    resolve_hrs_top_contract,
    resolve_readable_top_contract,
)
from p2mem.trajectory import compute_minimum_curvature_trajectory

FIXTURES = Path(__file__).parent / "fixtures"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Synthetic DeviationWellResult builder (mirrors tests/test_depth_mapping.py)
# ---------------------------------------------------------------------------
def _make_deviation_well_result(md, incl, azim_gn, datum_elevation_m=20.0) -> DeviationWellResult:
    md = np.asarray(md, dtype=np.float64)
    incl = np.asarray(incl, dtype=np.float64)
    azim_gn = np.asarray(azim_gn, dtype=np.float64)
    mc = compute_minimum_curvature_trajectory(
        md, incl, azim_gn, tvd_origin_m=float(md[0]), northing_origin_m=0.0, easting_origin_m=0.0
    )
    stations = DeviationStationData(
        MD_source_m=md, X_source_m=np.zeros_like(md), Y_source_m=np.zeros_like(md),
        Z_source_m=datum_elevation_m - mc.tvd_mc_m, TVD_source_m=mc.tvd_mc_m.copy(),
        DX_source_m=mc.easting_offset_mc_m.copy(), DY_source_m=mc.northing_offset_mc_m.copy(),
        AZIM_TN_source_deg=azim_gn.copy(), INCL_source_deg=incl,
        DLS_source_deg_per_30m=mc.dls_deg_per_30m, AZIM_GN_source_deg=azim_gn,
    )
    header = DeviationHeaderInfo(
        source_path="synthetic", source_filename="synthetic_dev.txt", sha256="0" * 64,
        well_name="Test_Well_1", survey_name="Synthetic survey", wellhead_x_m=0.0, wellhead_y_m=0.0,
        datum_elevation_m=datum_elevation_m, datum_reference="RT, Rotary table, from MSL",
        well_type="GAS", coordinate_reference_system="TEST", depth_reference_statement="test",
        angle_unit_statement="DEGREES", dx_dy_statement="m-UNITS", z_statement="m-UNITS",
        column_names=("MD", "X", "Y", "Z", "TVD", "DX", "DY", "AZIM_TN", "INCL", "DLS", "AZIM_GN"),
        header_line_count=16, data_line_offset=17,
    )
    contract = DeviationFileContract(
        source_filename="synthetic_dev.txt", expected_sha256="0" * 64,
        expected_well_identifier="Test_Well_1", expected_survey_identifier="Synthetic survey",
        expected_coordinate_reference_system="TEST", expected_wellhead_x_m=0.0, expected_wellhead_y_m=0.0,
        expected_datum_m=datum_elevation_m, expected_datum_reference="RT, Rotary table, from MSL",
        expected_column_count=11,
        expected_column_order=("MD", "X", "Y", "Z", "TVD", "DX", "DY", "AZIM_TN", "INCL", "DLS", "AZIM_GN"),
        expected_units={}, expected_station_count=int(md.size),
        expected_md_min_m=float(md[0]), expected_md_max_m=float(md[-1]),
        azimuth_reference_for_grid_coordinates="AZIM_GN", source_depth_convention="test",
        header_tolerance_m=0.001, residual_tolerance_tvd_m=0.01, residual_tolerance_horizontal_m=0.01,
        residual_fail_threshold_m=5.0, depth_basis_policy=DEPTH_BASIS_PETREL_SOURCE, notes="synthetic",
    )
    validation = TrajectoryValidationResult(
        well_key="Test_Well_1", comparison_basis="synthetic self-consistent fixture",
        tvd_max_abs_residual_m=0.0, tvd_mean_residual_m=0.0, tvd_rmse_m=0.0,
        tvd_endpoint_residual_m=0.0, tvd_tolerance_m=0.01, tvd_status="PASS",
        easting_max_abs_residual_m=0.0, easting_mean_residual_m=0.0, easting_rmse_m=0.0,
        easting_endpoint_residual_m=0.0, easting_tolerance_m=0.01, easting_status="PASS",
        northing_max_abs_residual_m=0.0, northing_mean_residual_m=0.0, northing_rmse_m=0.0,
        northing_endpoint_residual_m=0.0, northing_tolerance_m=0.01, northing_status="PASS",
        x_consistency_max_abs_residual_m=0.0, x_consistency_status="PASS",
        y_consistency_max_abs_residual_m=0.0, y_consistency_status="PASS",
        z_consistency_max_abs_residual_m=0.0, z_consistency_status="PASS",
        overall_status="PASS", origin_initialization_note="synthetic",
    )
    depth_basis_sel = DepthBasisSelection(
        well_key="Test_Well_1", selected_basis=DEPTH_BASIS_PETREL_SOURCE, rationale="test"
    )
    return DeviationWellResult(
        header=header, contract=contract, raw=stations, mc=mc,
        validation=validation, depth_basis=depth_basis_sel,
    )


_VERTICAL_WELL = _make_deviation_well_result(
    md=[0.0, 100.0, 200.0, 300.0, 400.0], incl=[0.0, 0.0, 0.0, 0.0, 0.0],
    azim_gn=[0.0, 0.0, 0.0, 0.0, 0.0], datum_elevation_m=20.0,
)
_DEVIATED_WELL = _make_deviation_well_result(
    md=[0.0, 100.0, 200.0, 300.0, 400.0], incl=[0.0, 10.0, 25.0, 35.0, 40.0],
    azim_gn=[0.0, 30.0, 30.0, 30.0, 30.0], datum_elevation_m=20.0,
)


def _base_hrs_contract(filename: str, **overrides) -> HRSTopFileContract:
    fixture_path = FIXTURES / filename
    defaults = dict(
        source_filename=filename,
        expected_sha256=_sha256(fixture_path) if fixture_path.exists() else "0" * 64,
        project_well_key="Test_Well_1",
        representation_type="HRS_MDRT_only",
        well_identity_evidence_status="inferred_unverified",
        well_identity_evidence_notes="Test fixture; identity not a real project well.",
        model_use_status="primary_model",
        expected_column_header_line="Top_Name\tMDRT_m",
        expected_column_order=("Top_Name", "MDRT_m"),
        expected_column_count=2,
        expected_marker_count=3,
        expected_mdrt_min_m=100.0,
        expected_mdrt_max_m=300.0,
        numeric_range_tolerance=0.005,
        datum_depth_column_interpretation="test",
        notes="test",
    )
    defaults.update(overrides)
    return HRSTopFileContract(**defaults)


def _base_readable_contract(filename: str, **overrides) -> ReadableTopFileContract:
    fixture_path = FIXTURES / filename
    defaults = dict(
        source_filename=filename,
        expected_sha256=_sha256(fixture_path) if fixture_path.exists() else "0" * 64,
        project_well_key="Test_Well_1",
        representation_type="selected_readable_MDRT_TVDSS",
        well_identity_evidence_status="inferred_unverified",
        well_identity_evidence_notes="Test fixture; identity not a real project well.",
        model_use_status="primary_model",
        expected_well_name_from_comment="Test Well 1",
        expected_column_header_line="TOP_NAME                                     \t    MDRT_M\t   TVDSS_M\tNOTE",
        expected_column_order=("TOP_NAME", "MDRT_M", "TVDSS_M", "NOTE"),
        expected_column_count=4,
        expected_marker_count=3,
        expected_mdrt_min_m=100.0,
        expected_mdrt_max_m=300.0,
        expected_tvdss_min_m=95.0,
        expected_tvdss_max_m=285.0,
        numeric_range_tolerance=0.005,
        datum_depth_column_interpretation="test",
        notes="test",
    )
    defaults.update(overrides)
    return ReadableTopFileContract(**defaults)


# ---------------------------------------------------------------------------
# Structural parsing - both formats, comments/separator handling
# ---------------------------------------------------------------------------
def test_parse_hrs_header_and_rows():
    header = parse_hrs_top_header(str(FIXTURES / "top_hrs_valid.txt"))
    assert header.column_names == ("Top_Name", "MDRT_m")
    assert header.well_identity_source == "filename_only"
    rows = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    assert rows.Top_Name_source == ("Marker A", "Marker B", "Marker C")
    assert list(rows.MDRT_source_m) == [100.0, 200.0, 300.0]


def test_parse_readable_header_comments_and_separator_deliberately():
    header = parse_readable_top_header(str(FIXTURES / "top_readable_valid.txt"))
    assert header.well_name_from_comment == "Test Well 1"
    assert len(header.comment_lines) == 3
    assert set(header.separator_line_raw.strip()) == {"-"}
    assert header.well_identity_source == "in_file_comment_project_supplied"
    rows = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    assert rows.TOP_NAME_source == ("Marker A", "Marker B", "Marker C")
    assert list(rows.TVDSS_source_m) == [95.0, 190.0, 285.0]
    assert rows.NOTE_source == ("Top marker", "Middle marker", "Bottom marker")


def test_readable_missing_separator_line_is_parsing_error():
    with pytest.raises(TopParsingError, match="separator"):
        parse_readable_top_header(str(FIXTURES / "top_readable_missing_separator.txt"))


def test_hrs_file_not_found_raises_typed_error():
    with pytest.raises(TopFileNotFoundError):
        parse_hrs_top_header(str(FIXTURES / "does_not_exist_hrs.txt"))


def test_readable_file_not_found_raises_typed_error():
    with pytest.raises(TopFileNotFoundError):
        parse_readable_top_header(str(FIXTURES / "does_not_exist_readable.txt"))


# ---------------------------------------------------------------------------
# Malformed / non-finite / negative numeric input
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "fixture",
    ["top_hrs_malformed_numeric.txt", "top_hrs_nonfinite.txt", "top_hrs_negative_depth.txt"],
)
def test_hrs_malformed_or_nonfinite_or_negative_depth_rejected(fixture):
    with pytest.raises(TopParsingError):
        read_hrs_top_rows(str(FIXTURES / fixture))


# ---------------------------------------------------------------------------
# Contract resolution - exact filename and SHA-256 validation
# ---------------------------------------------------------------------------
def test_hrs_contract_passes_for_matching_file():
    header = parse_hrs_top_header(str(FIXTURES / "top_hrs_valid.txt"))
    rows = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    contract = _base_hrs_contract("top_hrs_valid.txt")
    issues = resolve_hrs_top_contract(header, rows, contract)
    assert not any(i.severity == "ERROR" for i in issues)
    assert any(i.code == "WELL_IDENTITY_FILENAME_ONLY" for i in issues)


def test_hrs_contract_sha256_mismatch_is_error():
    header = parse_hrs_top_header(str(FIXTURES / "top_hrs_valid.txt"))
    rows = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    contract = _base_hrs_contract("top_hrs_valid.txt", expected_sha256="0" * 64)
    issues = resolve_hrs_top_contract(header, rows, contract)
    assert any(i.code == "SHA256_MISMATCH" and i.severity == "ERROR" for i in issues)


def test_hrs_contract_filename_mismatch_is_error():
    header = parse_hrs_top_header(str(FIXTURES / "top_hrs_valid.txt"))
    rows = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    contract = _base_hrs_contract("a_different_filename.txt", expected_sha256=header.sha256)
    issues = resolve_hrs_top_contract(header, rows, contract)
    assert any(i.code == "FILENAME_MISMATCH" and i.severity == "ERROR" for i in issues)


def test_readable_contract_passes_for_matching_file():
    header = parse_readable_top_header(str(FIXTURES / "top_readable_valid.txt"))
    rows = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    contract = _base_readable_contract("top_readable_valid.txt")
    issues = resolve_readable_top_contract(header, rows, contract)
    assert not any(i.severity == "ERROR" for i in issues)
    assert any(i.code == "WELL_IDENTITY_IN_FILE_COMMENT_PROJECT_SUPPLIED" for i in issues)
    assert any(i.code == "SUPPLIED_TVDSS_NOT_CORRECTED_DEPTH" for i in issues)


def test_readable_contract_well_name_comment_mismatch_is_error():
    header = parse_readable_top_header(str(FIXTURES / "top_readable_valid.txt"))
    rows = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    contract = _base_readable_contract("top_readable_valid.txt", expected_well_name_from_comment="Wrong Well")
    issues = resolve_readable_top_contract(header, rows, contract)
    assert any(i.code == "WELL_NAME_COMMENT_MISMATCH" and i.severity == "ERROR" for i in issues)


# ---------------------------------------------------------------------------
# Embedded (in-file-comment) vs filename-derived well identity
# ---------------------------------------------------------------------------
def test_well_identity_evidence_never_verified_for_either_format():
    hrs_header = parse_hrs_top_header(str(FIXTURES / "top_hrs_valid.txt"))
    readable_header = parse_readable_top_header(str(FIXTURES / "top_readable_valid.txt"))
    assert hrs_header.well_identity_source == "filename_only"
    assert readable_header.well_identity_source == "in_file_comment_project_supplied"
    # Neither source's structural identity evidence is "verified" - that
    # status is a contract-level declaration, never inferred automatically
    # from a successful parse.
    contract = _base_hrs_contract("top_hrs_valid.txt")
    assert contract.well_identity_evidence_status == "inferred_unverified"


# ---------------------------------------------------------------------------
# Marker-name normalization and alias-contract behavior (no fuzzy matching)
# ---------------------------------------------------------------------------
def test_normalize_marker_name_collapses_whitespace_only():
    assert normalize_marker_name("  Marker   A  ") == "Marker A"
    assert normalize_marker_name("Marker A") == "Marker A"
    # Case and punctuation are never altered.
    assert normalize_marker_name("marker a") == "marker a"


def test_reconciliation_matches_whitespace_padded_names_without_alias():
    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    readable = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    issues, entries = reconcile_formation_top_sources("Test_Well_1", hrs, readable, {})
    assert not any(i.severity == "ERROR" for i in issues)
    assert all(e.name_match_status in ("exact", "normalized_match") for e in entries)


def test_alias_contract_resolves_differently_spelled_marker():
    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    aliased = read_readable_top_rows(str(FIXTURES / "top_readable_aliased_name.txt"))
    # Without the alias, "Marker B (Alt Spelling)" is NOT recognized as
    # the same marker as "Marker B" - no fuzzy matching.
    issues_no_alias, entries_no_alias = reconcile_formation_top_sources("Test_Well_1", hrs, aliased, {})
    names = {e.canonical_marker_name for e in entries_no_alias}
    assert "Marker B" in names and "Marker B (Alt Spelling)" in names
    assert any(e.name_match_status == "missing_in_readable" for e in entries_no_alias)
    assert any(e.name_match_status == "missing_in_hrs" for e in entries_no_alias)

    # With the explicit, human-authored alias, they ARE reconciled as one
    # canonical marker.
    issues_aliased, entries_aliased = reconcile_formation_top_sources(
        "Test_Well_1", hrs, aliased, {"Marker B (Alt Spelling)": "Marker B"}
    )
    b_entry = next(e for e in entries_aliased if e.canonical_marker_name == "Marker B")
    assert b_entry.name_match_status == "aliased_match"
    assert b_entry.present_in_hrs and b_entry.present_in_readable
    assert b_entry.mdrt_status == "MATCHED"


def test_no_silent_fuzzy_matching_of_similar_but_unaliased_names():
    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    aliased = read_readable_top_rows(str(FIXTURES / "top_readable_aliased_name.txt"))
    _, entries = reconcile_formation_top_sources("Test_Well_1", hrs, aliased, {})
    # "Marker B" and "Marker B (Alt Spelling)" are textually similar but
    # NOT identical/normalized-identical/aliased - they must be reported
    # as two separate, single-source markers, never silently paired.
    canon_names = [e.canonical_marker_name for e in entries]
    assert canon_names.count("Marker B") == 1
    assert canon_names.count("Marker B (Alt Spelling)") == 1


# ---------------------------------------------------------------------------
# Duplicate marker names / marker-order reversal (reconciliation-time QC)
# ---------------------------------------------------------------------------
def test_duplicate_marker_name_within_one_source_is_error():
    hrs_dup = read_hrs_top_rows(str(FIXTURES / "top_hrs_duplicate_marker.txt"))
    readable = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    issues, _ = reconcile_formation_top_sources("Test_Well_1", hrs_dup, readable, {})
    assert any(i.code == "DUPLICATE_MARKER_NAME" and i.severity == "ERROR" for i in issues)


def test_marker_order_reversal_within_one_source_is_error():
    hrs_rev = read_hrs_top_rows(str(FIXTURES / "top_hrs_order_reversal.txt"))
    readable = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    issues, _ = reconcile_formation_top_sources("Test_Well_1", hrs_rev, readable, {})
    assert any(i.code == "MARKER_ORDER_REVERSAL" and i.severity == "ERROR" for i in issues)


# ---------------------------------------------------------------------------
# Source marker mismatch (missing-in-one-source) / MDRT mismatch
# ---------------------------------------------------------------------------
def test_marker_present_in_only_one_source_is_not_comparable():
    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    missing = read_readable_top_rows(str(FIXTURES / "top_readable_missing_marker.txt"))
    _, entries = reconcile_formation_top_sources("Test_Well_1", hrs, missing, {})
    c_entry = next(e for e in entries if e.canonical_marker_name == "Marker C")
    assert c_entry.name_match_status == "missing_in_readable"
    assert c_entry.mdrt_status == "NOT_COMPARABLE"
    assert c_entry.MDRT_source_readable_m is None
    assert c_entry.TVDSS_source_readable_m is None


def test_mdrt_mismatch_beyond_tolerance_is_registered_not_silently_chosen():
    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    mismatch = read_readable_top_rows(str(FIXTURES / "top_readable_mdrt_mismatch.txt"))
    issues, entries = reconcile_formation_top_sources("Test_Well_1", hrs, mismatch, {})
    assert any(i.code == "MDRT_MISMATCH" and i.severity == "WARNING" for i in issues)
    b_entry = next(e for e in entries if e.canonical_marker_name == "Marker B")
    assert b_entry.mdrt_status == "MISMATCH"
    assert b_entry.MDRT_agreement_readable_minus_hrs_m == pytest.approx(5.0)
    assert abs(b_entry.MDRT_agreement_readable_minus_hrs_m) > MDRT_AGREEMENT_TOLERANCE_M


def test_mdrt_mismatch_marker_excluded_from_mapping_not_silently_picked():
    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    mismatch = read_readable_top_rows(str(FIXTURES / "top_readable_mdrt_mismatch.txt"))
    _, entries = reconcile_formation_top_sources("Test_Well_1", hrs, mismatch, {})
    issues, markers = build_formation_top_markers("Test_Well_1", entries, _VERTICAL_WELL, "inferred_unverified")
    b_marker = next(m for m in markers if m.canonical_marker_name == "Marker B")
    assert b_marker.mapping_status == "not_mapped_mdrt_unresolved"
    assert b_marker.MDRT_reconciled_m is None
    assert b_marker.mdrt_authority_basis == "disagreement_unresolved"
    assert any(i.code == "MDRT_UNRESOLVED_NOT_MAPPED" for i in issues)
    # The other two markers, unaffected, still map normally.
    a_marker = next(m for m in markers if m.canonical_marker_name == "Marker A")
    assert a_marker.mapping_status == "mapped_within_coverage"


# ---------------------------------------------------------------------------
# Mapping inside coverage / rejection outside coverage / no extrapolation
# ---------------------------------------------------------------------------
def test_mapping_within_survey_coverage_succeeds():
    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    readable = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    _, entries = reconcile_formation_top_sources("Test_Well_1", hrs, readable, {})
    issues, markers = build_formation_top_markers("Test_Well_1", entries, _VERTICAL_WELL, "inferred_unverified")
    assert all(m.mapping_status == "mapped_within_coverage" for m in markers)
    assert not any(i.code == "MARKER_OUTSIDE_SURVEY_COVERAGE" for i in issues)
    for m in markers:
        assert m.TVD_survey_m is not None
        assert m.depth_basis_used == DEPTH_BASIS_PETREL_SOURCE


def test_marker_outside_survey_coverage_is_rejected_never_extrapolated():
    # _VERTICAL_WELL's survey MD coverage is [0, 400] m; a marker at
    # MDRT=500 m is genuinely outside coverage.
    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_extra_marker.txt"))  # Marker D at 400.0, within range
    readable = read_readable_top_rows(str(FIXTURES / "top_readable_extra_padding.txt"))
    _, entries = reconcile_formation_top_sources("Test_Well_1", hrs, readable, {})
    # Manually construct one marker beyond coverage by reusing the
    # reconciliation machinery's own output shape - simplest robust way is
    # to add a synthetic entry via the same dataclass used elsewhere.
    from p2mem.top_models import TopReconciliationEntry

    beyond_entry = TopReconciliationEntry(
        well_key="Test_Well_1", canonical_marker_name="Marker Beyond Coverage",
        hrs_marker_name_raw="Marker Beyond Coverage", readable_marker_name_raw="Marker Beyond Coverage",
        hrs_row_number=0, readable_row_number=0, present_in_hrs=True, present_in_readable=True,
        name_match_status="exact", MDRT_source_hrs_m=999.0, MDRT_source_readable_m=999.0,
        MDRT_agreement_readable_minus_hrs_m=0.0, mdrt_status="MATCHED",
        TVDSS_source_readable_m=900.0, note_readable="", reconciliation_notes="test",
    )
    issues, markers = build_formation_top_markers("Test_Well_1", (beyond_entry,), _VERTICAL_WELL, "inferred_unverified")
    assert markers[0].mapping_status == "rejected_outside_coverage"
    assert markers[0].TVD_survey_m is None
    assert markers[0].TVDSS_survey_corrected_m is None
    assert any(i.code == "MARKER_OUTSIDE_SURVEY_COVERAGE" and i.severity == "WARNING" for i in issues)


# ---------------------------------------------------------------------------
# Explicit residual sign convention
# ---------------------------------------------------------------------------
def test_residual_sign_convention_is_source_minus_survey():
    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    readable = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    _, entries = reconcile_formation_top_sources("Test_Well_1", hrs, readable, {})
    _, markers = build_formation_top_markers("Test_Well_1", entries, _VERTICAL_WELL, "inferred_unverified")
    for m in markers:
        expected = m.TVDSS_source_m - m.TVDSS_survey_corrected_m
        assert m.TVDSS_residual_source_minus_survey_m == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Poseidon-like vertical-assumption defect / Boreas-like survey-consistent
# tops (synthetic analogs of the real Increment 5 regression findings -
# see INCREMENT_05_MANIFEST.md Section 1 for the actual real-data numbers)
# ---------------------------------------------------------------------------
def test_vertical_assumption_defect_grows_with_deviation_poseidon_like():
    """
    A synthetic analog of the confirmed Poseidon 2 finding: when a
    well's supplied TVDSS was generated by assuming zero deviation
    (TVDSS_source = MDRT - datum_elevation_m, i.e. TVD == MD from the
    well datum), the source-minus-survey residual is ~0 at MD == 0 and
    grows monotonically as the well's real surveyed deviation increases
    with depth. Built the same way the real Poseidon 2 defect was
    independently discovered: from the well's own datum elevation, not
    an arbitrary constant.
    """
    from p2mem.top_models import ReadableTopStationData

    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    mdrt = np.array([100.0, 200.0, 300.0])
    vertical_assumption_tvdss = mdrt - _DEVIATED_WELL.header.datum_elevation_m
    readable = ReadableTopStationData(
        TOP_NAME_source=("Marker A", "Marker B", "Marker C"),
        MDRT_source_m=mdrt, TVDSS_source_m=vertical_assumption_tvdss,
        NOTE_source=("", "", ""),
    )
    _, entries = reconcile_formation_top_sources("Test_Well_1", hrs, readable, {})
    _, markers = build_formation_top_markers("Test_Well_1", entries, _DEVIATED_WELL, "inferred_unverified")
    residuals = [abs(m.TVDSS_residual_source_minus_survey_m) for m in markers]
    # Monotonically non-decreasing residual as MD (and therefore
    # inclination/deviation) increases - the vertical-assumption defect
    # signature.
    assert residuals == sorted(residuals)
    assert residuals[0] < residuals[-1]


def test_survey_consistent_tops_boreas_like_small_residual():
    """
    A synthetic analog of the confirmed Boreas 1 finding: when a well's
    supplied TVDSS was itself generated from the real surveyed
    trajectory (not a vertical assumption), the source-minus-survey
    residual stays small even for a deviated well.
    """
    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    # Build a "survey-consistent" readable fixture in-memory: TVDSS equal
    # to the deviated well's own actual survey-derived TVDSS at each
    # marker (i.e., generated from the real trajectory, not MDRT - const).
    from p2mem.depth_mapping import map_las_md_to_tvd_tvdss
    from p2mem.top_models import ReadableTopStationData

    mdrt = np.array([100.0, 200.0, 300.0])
    mapped = map_las_md_to_tvd_tvdss("Test_Well_1", mdrt, _DEVIATED_WELL)
    readable = ReadableTopStationData(
        TOP_NAME_source=("Marker A", "Marker B", "Marker C"),
        MDRT_source_m=mdrt, TVDSS_source_m=mapped.tvdss_mapped_m.copy(),
        NOTE_source=("", "", ""),
    )
    _, entries = reconcile_formation_top_sources("Test_Well_1", hrs, readable, {})
    _, markers = build_formation_top_markers("Test_Well_1", entries, _DEVIATED_WELL, "inferred_unverified")
    max_abs_residual = max(abs(m.TVDSS_residual_source_minus_survey_m) for m in markers)
    assert max_abs_residual < 1e-6  # essentially zero - never "corrected" when already consistent


# ---------------------------------------------------------------------------
# Ambiguous-dtype / malformed input rejection
# ---------------------------------------------------------------------------
def test_reconcile_rejects_boolean_dtype_mdrt_array():
    from p2mem.top_models import HRSTopStationData, ReadableTopStationData

    hrs_bad = HRSTopStationData(Top_Name_source=("Marker A",), MDRT_source_m=np.array([True]))
    readable = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    with pytest.raises(TypeError):
        reconcile_formation_top_sources("Test_Well_1", hrs_bad, readable, {})


def test_reconcile_rejects_string_dtype_tvdss_array():
    from p2mem.top_models import ReadableTopStationData

    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    readable_bad = ReadableTopStationData(
        TOP_NAME_source=("Marker A", "Marker B", "Marker C"),
        MDRT_source_m=np.array([100.0, 200.0, 300.0]),
        TVDSS_source_m=np.array(["95.0", "190.0", "285.0"]),
        NOTE_source=("", "", ""),
    )
    with pytest.raises(TypeError):
        reconcile_formation_top_sources("Test_Well_1", hrs, readable_bad, {})


def test_reconcile_rejects_mismatched_array_lengths():
    from p2mem.top_models import HRSTopStationData

    hrs_bad = HRSTopStationData(Top_Name_source=("Marker A", "Marker B"), MDRT_source_m=np.array([100.0]))
    readable = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    with pytest.raises(TopParsingError):
        reconcile_formation_top_sources("Test_Well_1", hrs_bad, readable, {})


# ---------------------------------------------------------------------------
# End-to-end well loading and contract-definition validation
# ---------------------------------------------------------------------------
def test_load_formation_top_well_end_to_end_succeeds():
    hrs_contract = _base_hrs_contract("top_hrs_valid.txt")
    readable_contract = _base_readable_contract("top_readable_valid.txt")
    result = load_formation_top_well(
        str(FIXTURES / "top_hrs_valid.txt"), str(FIXTURES / "top_readable_valid.txt"),
        hrs_contract, readable_contract, {}, _VERTICAL_WELL,
    )
    assert result.contract_status == "PASSED"
    assert len(result.markers) == 3
    assert all(m.mapping_status == "mapped_within_coverage" for m in result.markers)


def test_load_formation_top_well_raises_contract_error_on_sha_mismatch():
    hrs_contract = _base_hrs_contract("top_hrs_valid.txt", expected_sha256="0" * 64)
    readable_contract = _base_readable_contract("top_readable_valid.txt")
    with pytest.raises(TopContractError):
        load_formation_top_well(
            str(FIXTURES / "top_hrs_valid.txt"), str(FIXTURES / "top_readable_valid.txt"),
            hrs_contract, readable_contract, {}, _VERTICAL_WELL,
        )


def test_load_formation_top_well_raises_reconciliation_error_on_duplicate():
    hrs_contract = _base_hrs_contract(
        "top_hrs_duplicate_marker.txt", expected_marker_count=2, expected_mdrt_min_m=100.0, expected_mdrt_max_m=150.0
    )
    readable_contract = _base_readable_contract("top_readable_valid.txt")
    with pytest.raises(TopSourceReconciliationError):
        load_formation_top_well(
            str(FIXTURES / "top_hrs_duplicate_marker.txt"), str(FIXTURES / "top_readable_valid.txt"),
            hrs_contract, readable_contract, {}, _VERTICAL_WELL,
        )


def test_contract_definition_duplicate_yaml_key_rejected(tmp_path):
    bad_yaml = tmp_path / "bad_formation_top_contracts.yml"
    bad_yaml.write_text(
        "files:\n"
        "  \"dup.txt\":\n"
        "    expected_sha256: \"a\"\n"
        "  \"dup.txt\":\n"
        "    expected_sha256: \"b\"\n"
    )
    with pytest.raises(TopContractDefinitionError):
        load_formation_top_contract_config(str(bad_yaml))


def test_contract_definition_invalid_representation_type_rejected(tmp_path):
    bad_yaml = tmp_path / "bad2.yml"
    bad_yaml.write_text(
        "files:\n"
        "  \"x.txt\":\n"
        "    expected_sha256: \"a\"\n"
        "    project_well_key: \"W\"\n"
        "    representation_type: \"not_a_real_type\"\n"
        "    well_identity_evidence_status: \"inferred_unverified\"\n"
        "    well_identity_evidence_notes: \"n\"\n"
        "    model_use_status: \"primary_model\"\n"
        "    expected_column_header_line: \"h\"\n"
        "    expected_column_order: [\"a\", \"b\"]\n"
        "    expected_marker_count: 1\n"
        "    expected_mdrt_min_m: 0.0\n"
        "    expected_mdrt_max_m: 1.0\n"
        "    numeric_range_tolerance: 0.01\n"
        "    datum_depth_column_interpretation: \"d\"\n"
        "    notes: \"n\"\n"
    )
    with pytest.raises(TopContractDefinitionError):
        load_formation_top_contract_config(str(bad_yaml))


# ---------------------------------------------------------------------------
# Batch failure isolation and absolute-path sanitization
# ---------------------------------------------------------------------------
def test_batch_isolates_one_well_contract_failure_from_another_success(tmp_path):
    hrs_contracts = {
        "top_hrs_valid.txt": _base_hrs_contract("top_hrs_valid.txt"),
        "top_hrs_duplicate_marker.txt": _base_hrs_contract(
            "top_hrs_duplicate_marker.txt", project_well_key="Test_Well_2",
            expected_marker_count=2, expected_mdrt_min_m=100.0, expected_mdrt_max_m=150.0,
        ),
    }
    readable_contracts = {
        "top_readable_valid.txt": _base_readable_contract("top_readable_valid.txt"),
    }
    # Test_Well_2 has no readable contract at all in this deliberately
    # incomplete map - simulate via a missing readable file path instead,
    # reusing the same readable file (well-2's HRS has a duplicate-name
    # defect regardless, which is what this test isolates).
    file_paths = {
        "Test_Well_1": (str(FIXTURES / "top_hrs_valid.txt"), str(FIXTURES / "top_readable_valid.txt")),
        "Test_Well_2": (str(FIXTURES / "top_hrs_duplicate_marker.txt"), str(FIXTURES / "top_readable_valid.txt")),
    }
    readable_contracts["top_readable_valid.txt"] = _base_readable_contract("top_readable_valid.txt")
    results, failures = load_formation_top_surveys(
        file_paths, hrs_contracts, readable_contracts, {},
        {"Test_Well_1": _VERTICAL_WELL, "Test_Well_2": _VERTICAL_WELL},
    )
    assert "Test_Well_1" in results
    assert "Test_Well_2" in failures
    assert failures["Test_Well_2"].error_type == "reconciliation_failure"
    # The failure message must never leak an absolute path.
    assert str(FIXTURES) not in failures["Test_Well_2"].message


def test_batch_missing_contract_raises_contract_definition_error():
    file_paths = {"Test_Well_1": (str(FIXTURES / "top_hrs_valid.txt"), str(FIXTURES / "top_readable_valid.txt"))}
    with pytest.raises(TopContractDefinitionError):
        load_formation_top_surveys(file_paths, {}, {}, {}, {"Test_Well_1": _VERTICAL_WELL})


def test_batch_missing_deviation_result_raises_value_error():
    hrs_contracts = {"top_hrs_valid.txt": _base_hrs_contract("top_hrs_valid.txt")}
    readable_contracts = {"top_readable_valid.txt": _base_readable_contract("top_readable_valid.txt")}
    file_paths = {"Test_Well_1": (str(FIXTURES / "top_hrs_valid.txt"), str(FIXTURES / "top_readable_valid.txt"))}
    with pytest.raises(ValueError):
        load_formation_top_surveys(file_paths, hrs_contracts, readable_contracts, {}, {})


# ===========================================================================
# Increment 5.1 - corrective-patch regression tests
# ===========================================================================
# Finding 1: zero-common-marker logic defect (disjoint non-empty sources
# were silently accepted as one-sided NOT_COMPARABLE entries instead of a
# fatal NO_COMMON_MARKERS ERROR).
# ---------------------------------------------------------------------------
def test_disjoint_nonempty_sources_produce_no_common_markers_error():
    """Two entirely disjoint, non-empty marker sets (HRS={Marker X, Marker
    Y}, readable={Marker A, Marker B, Marker C}) must raise a fatal
    NO_COMMON_MARKERS ERROR - never be silently accepted as five one-sided
    NOT_COMPARABLE entries."""
    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_disjoint_markers.txt"))
    readable = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    issues, entries = reconcile_formation_top_sources("Test_Well_1", hrs, readable, {})
    assert any(i.code == "NO_COMMON_MARKERS" and i.severity == "ERROR" for i in issues)
    # The entries are still constructed (for audit visibility) but every one
    # of them is one-sided - no fuzzy pairing is invented to "fix" this.
    assert len(entries) == 5
    assert all(e.mdrt_status == "NOT_COMPARABLE" for e in entries)


def test_load_formation_top_well_raises_reconciliation_error_for_disjoint_sources():
    """`load_formation_top_well()` must consequently raise
    `TopSourceReconciliationError` for the disjoint-non-empty-sources
    condition - it must never construct/map an apparently valid model from
    two unrelated marker sets."""
    hrs_contract = _base_hrs_contract(
        "top_hrs_disjoint_markers.txt", expected_marker_count=2,
        expected_mdrt_min_m=100.0, expected_mdrt_max_m=200.0,
    )
    readable_contract = _base_readable_contract("top_readable_valid.txt")
    with pytest.raises(TopSourceReconciliationError) as excinfo:
        load_formation_top_well(
            str(FIXTURES / "top_hrs_disjoint_markers.txt"), str(FIXTURES / "top_readable_valid.txt"),
            hrs_contract, readable_contract, {}, _VERTICAL_WELL,
        )
    assert any(i.code == "NO_COMMON_MARKERS" for i in excinfo.value.issues)


def test_common_subset_plus_one_sided_markers_remains_auditable_nonfatal():
    """When at least one canonical marker IS shared between the two
    sources, a legitimate one-sided marker (present in only one source)
    remains a non-fatal, auditable NOT_COMPARABLE entry - the Finding 1 fix
    must not turn this already-correct, already-tested behavior into a
    false-positive NO_COMMON_MARKERS ERROR."""
    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))  # Marker A, B, C
    missing = read_readable_top_rows(str(FIXTURES / "top_readable_missing_marker.txt"))  # missing Marker C
    issues, entries = reconcile_formation_top_sources("Test_Well_1", hrs, missing, {})
    assert not any(i.code == "NO_COMMON_MARKERS" for i in issues)
    assert not any(i.severity == "ERROR" for i in issues)
    c_entry = next(e for e in entries if e.canonical_marker_name == "Marker C")
    assert c_entry.mdrt_status == "NOT_COMPARABLE"
    assert c_entry.name_match_status == "missing_in_readable"


# ===========================================================================
# Increment 5.1.1 - corrective-patch regression tests
# ===========================================================================
# Finding 1: one-empty-source zero-common-marker defect (Increment 5.1
# correctly rejected two non-empty disjoint sources, but still silently
# accepted the case where exactly ONE source is entirely empty and the
# other is not - the intersection with an empty set is itself empty, so
# this is still a zero-common-markers condition and must also be fatal).
# ---------------------------------------------------------------------------
def test_no_common_markers_hrs_empty_readable_nonempty():
    """HRS entirely empty, readable contains a marker: must raise a fatal
    NO_COMMON_MARKERS ERROR, never silently accept the marker as a bare
    'missing_in_hrs' NOT_COMPARABLE entry with no ERROR."""
    from p2mem.top_models import HRSTopStationData

    hrs_empty = HRSTopStationData(Top_Name_source=(), MDRT_source_m=np.array([]))
    readable = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    issues, entries = reconcile_formation_top_sources("Test_Well_1", hrs_empty, readable, {})
    assert any(i.code == "NO_COMMON_MARKERS" and i.severity == "ERROR" for i in issues)
    assert all(e.mdrt_status == "NOT_COMPARABLE" for e in entries)


def test_no_common_markers_hrs_nonempty_readable_empty():
    """HRS contains a marker, readable entirely empty: must raise a fatal
    NO_COMMON_MARKERS ERROR, never silently accept the marker as a bare
    'missing_in_readable' NOT_COMPARABLE entry with no ERROR."""
    from p2mem.top_models import ReadableTopStationData

    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    readable_empty = ReadableTopStationData(
        TOP_NAME_source=(), MDRT_source_m=np.array([]), TVDSS_source_m=np.array([]), NOTE_source=(),
    )
    issues, entries = reconcile_formation_top_sources("Test_Well_1", hrs, readable_empty, {})
    assert any(i.code == "NO_COMMON_MARKERS" and i.severity == "ERROR" for i in issues)
    assert all(e.mdrt_status == "NOT_COMPARABLE" for e in entries)


def test_no_common_markers_both_sources_empty():
    """Both sources entirely empty: the pre-existing, already-correct
    behavior (fatal NO_COMMON_MARKERS ERROR) must remain unaffected by the
    Increment 5.1.1 condition rewrite."""
    from p2mem.top_models import HRSTopStationData, ReadableTopStationData

    hrs_empty = HRSTopStationData(Top_Name_source=(), MDRT_source_m=np.array([]))
    readable_empty = ReadableTopStationData(
        TOP_NAME_source=(), MDRT_source_m=np.array([]), TVDSS_source_m=np.array([]), NOTE_source=(),
    )
    issues, entries = reconcile_formation_top_sources("Test_Well_1", hrs_empty, readable_empty, {})
    assert any(i.code == "NO_COMMON_MARKERS" and i.severity == "ERROR" for i in issues)
    assert entries == ()


def test_no_common_markers_both_nonempty_disjoint_still_rejected():
    """Both sources non-empty but disjoint (the Increment 5.1 case): must
    remain rejected under the Increment 5.1.1 simplified single-condition
    check - this is a non-regression check on the 5.1 fix itself."""
    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_disjoint_markers.txt"))
    readable = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    issues, entries = reconcile_formation_top_sources("Test_Well_1", hrs, readable, {})
    assert any(i.code == "NO_COMMON_MARKERS" and i.severity == "ERROR" for i in issues)
    assert all(e.mdrt_status == "NOT_COMPARABLE" for e in entries)


def test_load_formation_top_well_raises_reconciliation_error_for_one_empty_source():
    """`load_formation_top_well()` must consequently raise
    `TopSourceReconciliationError` for the one-empty-source condition too -
    never construct/map an apparently valid model when one entire source
    supplied zero markers."""
    from p2mem.top_models import ReadableTopStationData

    hrs_contract = _base_hrs_contract("top_hrs_valid.txt")
    readable_contract = _base_readable_contract(
        "top_readable_valid.txt", expected_marker_count=0, expected_mdrt_min_m=0.0, expected_mdrt_max_m=0.0,
        expected_tvdss_min_m=0.0, expected_tvdss_max_m=0.0,
    )
    # Directly exercise reconcile_formation_top_sources with an empty
    # readable source (constructing a genuinely empty readable FILE would
    # itself be rejected by the file parser as "no data rows found" before
    # reconciliation is ever reached - the in-memory API is what Finding 1
    # of Increment 5.1.1 targets).
    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    readable_empty = ReadableTopStationData(
        TOP_NAME_source=(), MDRT_source_m=np.array([]), TVDSS_source_m=np.array([]), NOTE_source=(),
    )
    issues, _ = reconcile_formation_top_sources("Test_Well_1", hrs, readable_empty, {})
    assert any(i.severity == "ERROR" and i.code == "NO_COMMON_MARKERS" for i in issues)
    # The same ERROR-severity-issue-to-exception conversion already used by
    # load_formation_top_well for every other reconciliation ERROR applies
    # here unchanged - confirmed via the existing duplicate-marker case
    # (test_load_formation_top_well_raises_reconciliation_error_on_duplicate)
    # and the disjoint-sources case above; this test isolates the specific
    # one-empty-source reconciliation-level ERROR that must feed that same
    # conversion.


def test_common_subset_plus_one_sided_markers_still_nonfatal_after_5_1_1():
    """Re-verification (post Increment 5.1.1 condition rewrite) that a
    genuinely shared marker alongside a one-sided marker remains the
    pre-existing, non-fatal NOT_COMPARABLE case - the single-condition
    `not common_markers` check must not be broader than intended."""
    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))  # Marker A, B, C
    missing = read_readable_top_rows(str(FIXTURES / "top_readable_missing_marker.txt"))  # missing Marker C
    issues, entries = reconcile_formation_top_sources("Test_Well_1", hrs, missing, {})
    assert not any(i.code == "NO_COMMON_MARKERS" for i in issues)
    assert not any(i.severity == "ERROR" for i in issues)
    matched = [e for e in entries if e.mdrt_status == "MATCHED"]
    assert len(matched) >= 1
    c_entry = next(e for e in entries if e.canonical_marker_name == "Marker C")
    assert c_entry.mdrt_status == "NOT_COMPARABLE"


# ---------------------------------------------------------------------------
# Finding 2: readable-file absolute-path leakage (the batch loader recorded
# only the HRS path for every failure type, regardless of which file/stage
# actually failed).
# ---------------------------------------------------------------------------
def test_batch_missing_readable_file_reports_readable_origin_and_both_paths():
    hrs_contracts = {"top_hrs_valid.txt": _base_hrs_contract("top_hrs_valid.txt")}
    # Contracts are keyed by source filename, not by file existence - a
    # contract entry for the (missing) readable file must exist so the
    # batch loader reaches `load_formation_top_well` and genuinely fails
    # at the file-not-found stage, not at contract lookup.
    readable_contracts = {
        "does_not_exist_readable.txt": _base_readable_contract("top_readable_valid.txt", source_filename="does_not_exist_readable.txt"),
    }
    missing_readable_path = str(FIXTURES / "does_not_exist_readable.txt")
    file_paths = {"Test_Well_1": (str(FIXTURES / "top_hrs_valid.txt"), missing_readable_path)}
    _, failures = load_formation_top_surveys(
        file_paths, hrs_contracts, readable_contracts, {}, {"Test_Well_1": _VERTICAL_WELL}
    )
    f = failures["Test_Well_1"]
    assert f.error_type == "file_not_found"
    assert f.failure_origin == "readable"
    assert f.readable_path == missing_readable_path
    assert f.hrs_path == str(FIXTURES / "top_hrs_valid.txt")
    # The absolute readable path must appear in the raw exception message
    # (it is a genuine, unsanitized internal record) ...
    assert missing_readable_path in f.message
    # ... but must never survive into any exported builder row/manifest field.
    from p2mem.io.tops_inventory import build_formation_top_manifest, build_top_availability_rows, build_top_issues_rows

    issues_rows = build_top_issues_rows({}, failures)
    assert not any(str(FIXTURES) in row["message"] for row in issues_rows)
    assert issues_rows[0]["context"] == "does_not_exist_readable.txt"
    availability_rows = build_top_availability_rows({}, failures, {})
    assert not any(str(FIXTURES) in row["notes"] for row in availability_rows)
    manifest = build_formation_top_manifest({}, failures, {})
    assert str(FIXTURES) not in manifest["failed_wells"]["Test_Well_1"]["message"]


def test_batch_malformed_readable_file_reports_readable_origin():
    hrs_contracts = {"top_hrs_valid.txt": _base_hrs_contract("top_hrs_valid.txt")}
    readable_contracts = {
        "top_readable_malformed_numeric.txt": _base_readable_contract(
            "top_readable_malformed_numeric.txt", expected_marker_count=1,
            expected_mdrt_min_m=0.0, expected_mdrt_max_m=1000.0,
            expected_tvdss_min_m=0.0, expected_tvdss_max_m=1000.0,
        ),
    }
    readable_path = str(FIXTURES / "top_readable_malformed_numeric.txt")
    file_paths = {"Test_Well_1": (str(FIXTURES / "top_hrs_valid.txt"), readable_path)}
    _, failures = load_formation_top_surveys(
        file_paths, hrs_contracts, readable_contracts, {}, {"Test_Well_1": _VERTICAL_WELL}
    )
    f = failures["Test_Well_1"]
    assert f.error_type == "parsing_failure"
    assert f.failure_origin == "readable"
    assert f.readable_path == readable_path

    from p2mem.io.tops_inventory import build_top_availability_rows, build_top_issues_rows

    issues_rows = build_top_issues_rows({}, failures)
    assert not any(str(FIXTURES) in row["message"] for row in issues_rows)
    assert issues_rows[0]["context"] == "top_readable_malformed_numeric.txt"
    availability_rows = build_top_availability_rows({}, failures, {})
    assert not any(str(FIXTURES) in row["notes"] for row in availability_rows)


def test_batch_readable_contract_failure_reports_readable_origin():
    hrs_contracts = {"top_hrs_valid.txt": _base_hrs_contract("top_hrs_valid.txt")}
    # A deliberately wrong expected_sha256 forces a TopContractError whose
    # message embeds the readable file's own absolute path.
    readable_contracts = {"top_readable_valid.txt": _base_readable_contract("top_readable_valid.txt", expected_sha256="0" * 64)}
    readable_path = str(FIXTURES / "top_readable_valid.txt")
    file_paths = {"Test_Well_1": (str(FIXTURES / "top_hrs_valid.txt"), readable_path)}
    _, failures = load_formation_top_surveys(
        file_paths, hrs_contracts, readable_contracts, {}, {"Test_Well_1": _VERTICAL_WELL}
    )
    f = failures["Test_Well_1"]
    assert f.error_type == "contract_failure"
    assert f.failure_origin == "readable"
    assert f.readable_path == readable_path
    assert readable_path in f.message

    from p2mem.io.tops_inventory import build_top_issues_rows

    issues_rows = build_top_issues_rows({}, failures)
    assert not any(str(FIXTURES) in row["message"] for row in issues_rows)
    assert issues_rows[0]["context"] == "top_readable_valid.txt"


def test_batch_hrs_failure_still_reports_hrs_origin_and_sanitizes_correctly():
    """The pre-existing HRS-failure sanitization path must remain correct
    after the Finding 2 restructuring."""
    hrs_contracts = {"top_hrs_valid.txt": _base_hrs_contract("top_hrs_valid.txt", expected_sha256="0" * 64)}
    readable_contracts = {"top_readable_valid.txt": _base_readable_contract("top_readable_valid.txt")}
    hrs_path = str(FIXTURES / "top_hrs_valid.txt")
    file_paths = {"Test_Well_1": (hrs_path, str(FIXTURES / "top_readable_valid.txt"))}
    _, failures = load_formation_top_surveys(
        file_paths, hrs_contracts, readable_contracts, {}, {"Test_Well_1": _VERTICAL_WELL}
    )
    f = failures["Test_Well_1"]
    assert f.error_type == "contract_failure"
    assert f.failure_origin == "hrs"
    assert f.hrs_path == hrs_path

    from p2mem.io.tops_inventory import build_top_issues_rows

    issues_rows = build_top_issues_rows({}, failures)
    assert not any(str(FIXTURES) in row["message"] for row in issues_rows)
    assert issues_rows[0]["context"] == "top_hrs_valid.txt"


# ---------------------------------------------------------------------------
# Finding 3: incomplete caller-supplied numerical validation of
# `reconcile_formation_top_sources()`.
# ---------------------------------------------------------------------------
def test_reconcile_rejects_nan_in_hrs_mdrt():
    from p2mem.top_models import HRSTopStationData

    hrs_bad = HRSTopStationData(Top_Name_source=("Marker A",), MDRT_source_m=np.array([np.nan]))
    readable = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    with pytest.raises(TopParsingError):
        reconcile_formation_top_sources("Test_Well_1", hrs_bad, readable, {})


def test_reconcile_rejects_inf_in_readable_mdrt():
    from p2mem.top_models import ReadableTopStationData

    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    readable_bad = ReadableTopStationData(
        TOP_NAME_source=("Marker A", "Marker B", "Marker C"),
        MDRT_source_m=np.array([100.0, np.inf, 300.0]),
        TVDSS_source_m=np.array([95.0, 190.0, 285.0]),
        NOTE_source=("", "", ""),
    )
    with pytest.raises(TopParsingError):
        reconcile_formation_top_sources("Test_Well_1", hrs, readable_bad, {})


def test_reconcile_rejects_nan_in_readable_tvdss():
    from p2mem.top_models import ReadableTopStationData

    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    readable_bad = ReadableTopStationData(
        TOP_NAME_source=("Marker A", "Marker B", "Marker C"),
        MDRT_source_m=np.array([100.0, 200.0, 300.0]),
        TVDSS_source_m=np.array([95.0, np.nan, 285.0]),
        NOTE_source=("", "", ""),
    )
    with pytest.raises(TopParsingError):
        reconcile_formation_top_sources("Test_Well_1", hrs, readable_bad, {})


def test_reconcile_rejects_negative_hrs_mdrt():
    from p2mem.top_models import HRSTopStationData

    hrs_bad = HRSTopStationData(Top_Name_source=("Marker A",), MDRT_source_m=np.array([-5.0]))
    readable = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    with pytest.raises(TopParsingError):
        reconcile_formation_top_sources("Test_Well_1", hrs_bad, readable, {})


def test_reconcile_rejects_non_1d_array():
    from p2mem.top_models import HRSTopStationData

    hrs_bad = HRSTopStationData(
        Top_Name_source=("Marker A", "Marker B"), MDRT_source_m=np.array([[100.0], [200.0]])
    )
    readable = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    with pytest.raises(TopParsingError):
        reconcile_formation_top_sources("Test_Well_1", hrs_bad, readable, {})


def test_reconcile_rejects_shorter_note_source_with_typed_error_not_indexerror():
    """A shorter `NOTE_source` tuple must be rejected with a documented
    `TopParsingError` before any reconciliation - never allowed to reach an
    untyped `IndexError` deep inside the reconciliation loop."""
    from p2mem.top_models import ReadableTopStationData

    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    readable_bad = ReadableTopStationData(
        TOP_NAME_source=("Marker A", "Marker B", "Marker C"),
        MDRT_source_m=np.array([100.0, 200.0, 300.0]),
        TVDSS_source_m=np.array([95.0, 190.0, 285.0]),
        NOTE_source=("only one note",),  # length 1, not 3
    )
    with pytest.raises(TopParsingError):
        reconcile_formation_top_sources("Test_Well_1", hrs, readable_bad, {})


@pytest.mark.parametrize("bad_tolerance", [np.nan, np.inf, -np.inf, -0.01])
def test_reconcile_rejects_invalid_tolerance_values(bad_tolerance):
    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    readable = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    with pytest.raises(TopParsingError):
        reconcile_formation_top_sources("Test_Well_1", hrs, readable, {}, mdrt_agreement_tolerance_m=bad_tolerance)


@pytest.mark.parametrize("bad_tolerance", [True, False, "0.5", b"0.5", 1 + 2j])
def test_reconcile_rejects_invalid_tolerance_types(bad_tolerance):
    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    readable = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    with pytest.raises(TypeError):
        reconcile_formation_top_sources("Test_Well_1", hrs, readable, {}, mdrt_agreement_tolerance_m=bad_tolerance)


@pytest.mark.parametrize(
    "good_tolerance",
    [0.5, 1, np.float64(0.5), np.int32(1), np.array(0.5), np.array([0.5])],
)
def test_reconcile_accepts_valid_tolerance_scalars_and_arrays(good_tolerance):
    hrs = read_hrs_top_rows(str(FIXTURES / "top_hrs_valid.txt"))
    readable = read_readable_top_rows(str(FIXTURES / "top_readable_valid.txt"))
    issues, entries = reconcile_formation_top_sources(
        "Test_Well_1", hrs, readable, {}, mdrt_agreement_tolerance_m=good_tolerance
    )
    assert not any(i.severity == "ERROR" for i in issues)
    assert len(entries) == 3


# ---------------------------------------------------------------------------
# Finding 3 (readable-format-equivalent coverage): the readable-file parser
# already enforces malformed/non-finite/negative-MDRT rejection (unlike the
# in-memory reconciliation API's prior gap above), but only HRS-format
# fixtures previously existed for these three conditions - this closes that
# coverage gap for the readable format.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "fixture",
    ["top_readable_malformed_numeric.txt", "top_readable_nonfinite.txt", "top_readable_negative_depth.txt"],
)
def test_readable_malformed_or_nonfinite_or_negative_depth_rejected(fixture):
    with pytest.raises(TopParsingError):
        read_readable_top_rows(str(FIXTURES / fixture))
