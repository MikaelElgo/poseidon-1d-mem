"""
tests/test_deviation.py - Validation suite for p2mem.io.deviation
(Increment 3: Petrel deviation-survey ingestion and per-file contract
resolution).

These are PORTABLE unit tests: they use only small synthetic fixtures
under tests/fixtures/ (dev_*.txt) and never require the four real project
deviation files. Real four-well integration (which DOES require the
private/raw project deviation files) is a separate notebook/script run.
"""

import hashlib
import math
from pathlib import Path

import numpy as np
import pytest
import yaml

from p2mem.deviation_models import (
    DEPTH_BASIS_MINIMUM_CURVATURE,
    DEPTH_BASIS_PETREL_SOURCE,
    STATUS_PASS,
    STATUS_WARNING,
    DeviationFileContract,
)
from p2mem.io.deviation import (
    DLS_NORMALIZATION_INFERRED_CODE,
    DeviationContractDefinitionError,
    DeviationContractError,
    DeviationFileNotFoundError,
    DeviationParsingError,
    load_deviation_contract_config,
    load_deviation_file,
    load_deviation_surveys,
    parse_deviation_header,
    read_deviation_stations,
    resolve_deviation_contract,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_contract(filename: str, **overrides) -> DeviationFileContract:
    fixture_path = FIXTURES / filename
    default_sha256 = _sha256(fixture_path) if fixture_path.exists() else "0" * 64
    defaults = dict(
        source_filename=filename,
        expected_sha256=default_sha256,
        expected_well_identifier="Test Well 1",
        expected_survey_identifier="Test survey 1",
        expected_coordinate_reference_system='GDA94 / MGA Zone 51 ("") [null,null]',
        expected_wellhead_x_m=100000.0,
        expected_wellhead_y_m=200000.0,
        expected_datum_m=10.0,
        expected_datum_reference="RT, Rotary table, from MSL",
        expected_column_count=11,
        expected_column_order=("MD", "X", "Y", "Z", "TVD", "DX", "DY", "AZIM_TN", "INCL", "DLS", "AZIM_GN"),
        expected_units={
            "MD": "m", "X": "m", "Y": "m", "Z": "m", "TVD": "m", "DX": "m", "DY": "m",
            "AZIM_TN": "deg", "INCL": "deg", "DLS": "deg_per_30m", "AZIM_GN": "deg",
        },
        expected_station_count=6,
        expected_md_min_m=0.0,
        expected_md_max_m=1200.0,
        azimuth_reference_for_grid_coordinates="AZIM_GN",
        source_depth_convention="MD and TVD referenced to zero at well datum, increasing downward",
        header_tolerance_m=0.001,
        residual_tolerance_tvd_m=0.01,
        residual_tolerance_horizontal_m=0.01,
        residual_fail_threshold_m=5.0,
        depth_basis_policy=DEPTH_BASIS_PETREL_SOURCE,
        notes="Synthetic fixture for Increment 3 unit tests.",
    )
    defaults.update(overrides)
    return DeviationFileContract(**defaults)


def _near_zero_contract(**overrides) -> DeviationFileContract:
    return _base_contract(
        "dev_near_zero_negative_origin.txt",
        expected_station_count=4,
        expected_md_min_m=-7.63e-7,
        expected_md_max_m=600.0,
        **overrides,
    )


# ---------------------------------------------------------------------------
# Header / structural parsing
# ---------------------------------------------------------------------------
def test_valid_file_parses_full_header():
    header, data_start, cols = parse_deviation_header(str(FIXTURES / "dev_valid.txt"))
    assert header.well_name == "Test Well 1"
    assert header.survey_name == "Test survey 1"
    assert header.wellhead_x_m == pytest.approx(100000.0)
    assert header.wellhead_y_m == pytest.approx(200000.0)
    assert header.datum_elevation_m == pytest.approx(10.0)
    assert header.well_type == "GAS"
    assert header.coordinate_reference_system == 'GDA94 / MGA Zone 51 ("") [null,null]'
    assert cols == ("MD", "X", "Y", "Z", "TVD", "DX", "DY", "AZIM_TN", "INCL", "DLS", "AZIM_GN")
    assert header.sha256 == _sha256(FIXTURES / "dev_valid.txt")


def test_exact_column_order_preserved():
    _, _, cols = parse_deviation_header(str(FIXTURES / "dev_valid.txt"))
    assert cols == ("MD", "X", "Y", "Z", "TVD", "DX", "DY", "AZIM_TN", "INCL", "DLS", "AZIM_GN")


def test_missing_column_rejected():
    with pytest.raises(DeviationParsingError, match="missing required column"):
        parse_deviation_header(str(FIXTURES / "dev_missing_column.txt"))


def test_duplicate_column_rejected():
    with pytest.raises(DeviationParsingError, match="duplicate column name"):
        parse_deviation_header(str(FIXTURES / "dev_duplicate_column.txt"))


def test_malformed_numeric_row_rejected():
    header, data_start, cols = parse_deviation_header(str(FIXTURES / "dev_malformed_numeric_row.txt"))
    with pytest.raises(DeviationParsingError, match="non-numeric token"):
        read_deviation_stations(str(FIXTURES / "dev_malformed_numeric_row.txt"), data_start, cols)


def test_row_width_mismatch_rejected():
    header, data_start, cols = parse_deviation_header(str(FIXTURES / "dev_row_width_mismatch.txt"))
    with pytest.raises(DeviationParsingError, match="row-width mismatch"):
        read_deviation_stations(str(FIXTURES / "dev_row_width_mismatch.txt"), data_start, cols)


def test_nonfinite_literal_token_rejected():
    header, data_start, cols = parse_deviation_header(str(FIXTURES / "dev_nonfinite_token.txt"))
    with pytest.raises(DeviationParsingError, match="non-finite literal token"):
        read_deviation_stations(str(FIXTURES / "dev_nonfinite_token.txt"), data_start, cols)


def test_file_not_found_raises_typed_error():
    with pytest.raises(DeviationFileNotFoundError):
        parse_deviation_header(str(FIXTURES / "does_not_exist_dev.txt"))


def test_unsupported_angle_convention_rejected():
    with pytest.raises(DeviationParsingError, match="unsupported angle-unit convention"):
        parse_deviation_header(str(FIXTURES / "dev_unsupported_angle_convention.txt"))


def test_proteus_style_near_zero_negative_md_is_preserved_not_rejected():
    path = str(FIXTURES / "dev_near_zero_negative_origin.txt")
    header, data_start, cols = parse_deviation_header(path)
    stations = read_deviation_stations(path, data_start, cols)
    assert stations.MD_source_m[0] == pytest.approx(-7.63e-7, abs=1e-12)
    assert stations.MD_source_m[0] < 0.0


# ---------------------------------------------------------------------------
# Contract resolution
# ---------------------------------------------------------------------------
def _load_valid(contract=None):
    contract = contract or _base_contract("dev_valid.txt")
    return load_deviation_file(str(FIXTURES / "dev_valid.txt"), contract)


def test_valid_file_and_contract_resolves_cleanly():
    result = _load_valid()
    assert result.contract_status == "PASSED"
    error_issues = [i for i in result.issues if i.severity == "ERROR"]
    assert error_issues == []
    assert result.raw.MD_source_m.size == 6


def test_wrong_filename_is_blocking():
    contract = _base_contract("dev_valid.txt", source_filename="some_other_file.txt")
    with pytest.raises(DeviationContractError) as excinfo:
        load_deviation_file(str(FIXTURES / "dev_valid.txt"), contract)
    assert any(i.code == "FILENAME_MISMATCH" for i in excinfo.value.issues)


def test_wrong_sha256_is_blocking():
    contract = _base_contract("dev_valid.txt", expected_sha256="0" * 64)
    with pytest.raises(DeviationContractError) as excinfo:
        load_deviation_file(str(FIXTURES / "dev_valid.txt"), contract)
    assert any(i.code == "SHA256_MISMATCH" for i in excinfo.value.issues)


def test_wrong_well_identifier_is_blocking():
    contract = _base_contract("dev_valid.txt", expected_well_identifier="Wrong Well")
    with pytest.raises(DeviationContractError) as excinfo:
        load_deviation_file(str(FIXTURES / "dev_valid.txt"), contract)
    assert any(i.code == "WELL_IDENTIFIER_MISMATCH" for i in excinfo.value.issues)


def test_wrong_datum_is_blocking():
    contract = _base_contract("dev_valid.txt", expected_datum_m=999.0)
    with pytest.raises(DeviationContractError) as excinfo:
        load_deviation_file(str(FIXTURES / "dev_valid.txt"), contract)
    assert any(i.code == "DATUM_MISMATCH" for i in excinfo.value.issues)


def test_wrong_wellhead_coordinates_is_blocking():
    contract = _base_contract("dev_valid.txt", expected_wellhead_x_m=1.0)
    with pytest.raises(DeviationContractError) as excinfo:
        load_deviation_file(str(FIXTURES / "dev_valid.txt"), contract)
    assert any(i.code == "WELLHEAD_X_MISMATCH" for i in excinfo.value.issues)


def test_wrong_crs_is_blocking():
    contract = _base_contract("dev_valid.txt", expected_coordinate_reference_system="WGS84")
    with pytest.raises(DeviationContractError) as excinfo:
        load_deviation_file(str(FIXTURES / "dev_valid.txt"), contract)
    assert any(i.code == "CRS_MISMATCH" for i in excinfo.value.issues)


def test_wrong_station_count_is_blocking():
    contract = _base_contract("dev_valid.txt", expected_station_count=999)
    with pytest.raises(DeviationContractError) as excinfo:
        load_deviation_file(str(FIXTURES / "dev_valid.txt"), contract)
    assert any(i.code == "STATION_COUNT_MISMATCH" for i in excinfo.value.issues)


def test_wrong_md_coverage_is_blocking():
    contract = _base_contract("dev_valid.txt", expected_md_max_m=1.0)
    with pytest.raises(DeviationContractError) as excinfo:
        load_deviation_file(str(FIXTURES / "dev_valid.txt"), contract)
    assert any(i.code == "MD_MAX_MISMATCH" for i in excinfo.value.issues)


def test_duplicate_md_is_blocking():
    contract = _base_contract("dev_duplicate_md.txt")
    with pytest.raises(DeviationContractError) as excinfo:
        load_deviation_file(str(FIXTURES / "dev_duplicate_md.txt"), contract)
    assert any(i.code == "DUPLICATE_MD" for i in excinfo.value.issues)


def test_non_monotonic_md_is_blocking():
    contract = _base_contract("dev_non_monotonic_md.txt")
    with pytest.raises(DeviationContractError) as excinfo:
        load_deviation_file(str(FIXTURES / "dev_non_monotonic_md.txt"), contract)
    assert any(i.code == "NON_MONOTONIC_MD" for i in excinfo.value.issues)


def test_invalid_inclination_is_blocking():
    contract = _base_contract("dev_invalid_inclination.txt")
    with pytest.raises(DeviationContractError) as excinfo:
        load_deviation_file(str(FIXTURES / "dev_invalid_inclination.txt"), contract)
    assert any(i.code == "INVALID_INCLINATION" for i in excinfo.value.issues)


def test_md_unit_not_declared_warning_always_present():
    result = _load_valid()
    codes = [i.code for i in result.issues]
    assert "MD_UNIT_NOT_EXPLICITLY_DECLARED" in codes
    warning = next(i for i in result.issues if i.code == "MD_UNIT_NOT_EXPLICITLY_DECLARED")
    assert warning.severity == "WARNING"


# ---------------------------------------------------------------------------
# Increment 3.1: DLS-normalization-inferred disclosure
# ---------------------------------------------------------------------------
def test_dls_normalization_inferred_warning_always_present_on_success():
    result = _load_valid()
    codes = [i.code for i in result.issues]
    assert DLS_NORMALIZATION_INFERRED_CODE in codes
    warning = next(i for i in result.issues if i.code == DLS_NORMALIZATION_INFERRED_CODE)
    assert warning.severity == "WARNING"
    # The message must actually state a computed discrepancy figure (not a
    # boilerplate "trust me" claim) and must state the raw column is
    # untouched.
    assert "deg/30m" in warning.message
    assert "never altered" in warning.message
    assert warning.context == result.header.source_filename


def test_dls_normalization_check_reports_actual_computed_discrepancy_not_hardcoded():
    # dev_valid.txt was built using the project's own trusted minimum-
    # curvature function, so its own supplied DLS column should already be
    # self-consistent with an independent recomputation to within a tiny,
    # genuinely computed (not assumed) discrepancy.
    result = _load_valid()
    warning = next(i for i in result.issues if i.code == DLS_NORMALIZATION_INFERRED_CODE)
    # Independently recompute the same comparison from the typed result's
    # own public fields, and confirm the message's reported figure is
    # consistent with it (not a different, hard-coded number).
    independent_max_diff = float(
        np.max(np.abs(result.raw.DLS_source_deg_per_30m - result.mc.dls_deg_per_30m))
    )
    assert f"{independent_max_diff:.6e}" in warning.message
    # Raw source DLS values are untouched by the check.
    assert result.raw.DLS_source_deg_per_30m is not result.mc.dls_deg_per_30m


def test_dls_normalization_warning_present_even_when_trajectory_validation_warns():
    # The DLS-normalization disclosure is about the DLS column's own
    # normalization convention, not about trajectory agreement - it must
    # still be present (and still WARNING, not escalated) even for a well
    # whose independent trajectory reconstruction disagrees with the
    # source trajectory (mirroring the real Proteus 1ST2 finding).
    contract = _base_contract(
        "dev_valid.txt",
        residual_tolerance_tvd_m=1e-12,
        residual_tolerance_horizontal_m=1e-12,
    )
    result = load_deviation_file(str(FIXTURES / "dev_valid.txt"), contract)
    assert result.validation.overall_status == STATUS_WARNING
    codes = [i.code for i in result.issues]
    assert DLS_NORMALIZATION_INFERRED_CODE in codes
    warning = next(i for i in result.issues if i.code == DLS_NORMALIZATION_INFERRED_CODE)
    assert warning.severity == "WARNING"


def test_column_order_mismatch_is_blocking():
    # Same physical columns, declared in a different required order.
    contract = _base_contract(
        "dev_valid.txt",
        expected_column_order=("X", "MD", "Y", "Z", "TVD", "DX", "DY", "AZIM_TN", "INCL", "DLS", "AZIM_GN"),
    )
    with pytest.raises(DeviationContractError) as excinfo:
        load_deviation_file(str(FIXTURES / "dev_valid.txt"), contract)
    assert any(i.code == "COLUMN_ORDER_MISMATCH" for i in excinfo.value.issues)


# ---------------------------------------------------------------------------
# Increment 3.1: filenames containing spaces (the real Petrel deviation
# files' actual names, e.g. "Poseidon 2_dev.txt") must resolve correctly,
# and a file renamed to substitute underscores for spaces must NOT
# silently match a contract declared for the space-containing name - this
# is the exact defect the Increment 3.1 corrective patch fixed (Increment
# 3 had silently renamed these to underscore variants internally).
# ---------------------------------------------------------------------------
REAL_DEVIATION_FILENAMES_WITH_SPACES = (
    "Poseidon 2_dev.txt",
    "Boreas 1_dev.txt",
    "Poseidon North 1_dev.txt",
    "Proteus 1ST2_dev.txt",
)


@pytest.mark.parametrize("spaced_name", REAL_DEVIATION_FILENAMES_WITH_SPACES)
def test_real_filenames_with_spaces_resolve_successfully(tmp_path, spaced_name):
    spaced_path = tmp_path / spaced_name
    spaced_path.write_bytes((FIXTURES / "dev_valid.txt").read_bytes())
    contract = _base_contract(spaced_name, expected_sha256=_sha256(spaced_path))
    result = load_deviation_file(str(spaced_path), contract)
    assert result.contract_status == "PASSED"
    assert result.header.source_filename == spaced_name
    assert " " in result.header.source_filename


@pytest.mark.parametrize("spaced_name", REAL_DEVIATION_FILENAMES_WITH_SPACES)
def test_underscore_renamed_filename_does_not_silently_match_contract(tmp_path, spaced_name):
    # Same byte content, but the file on disk has been renamed to
    # substitute underscores for spaces (exactly the Increment 3 defect).
    # A contract declared for the space-containing name must reject this
    # as a FILENAME_MISMATCH, never silently accept it as a match.
    underscored_name = spaced_name.replace(" ", "_")
    underscored_path = tmp_path / underscored_name
    underscored_path.write_bytes((FIXTURES / "dev_valid.txt").read_bytes())
    contract = _base_contract(spaced_name, expected_sha256=_sha256(underscored_path))
    with pytest.raises(DeviationContractError) as excinfo:
        load_deviation_file(str(underscored_path), contract)
    assert any(i.code == "FILENAME_MISMATCH" for i in excinfo.value.issues)


def test_proteus_style_near_zero_origin_contract_resolves_cleanly():
    result = load_deviation_file(
        str(FIXTURES / "dev_near_zero_negative_origin.txt"), _near_zero_contract()
    )
    assert result.contract_status == "PASSED"
    assert result.raw.MD_source_m[0] == pytest.approx(-7.63e-7, abs=1e-12)
    # Preserved exactly as the trajectory's own tie-on origin, not zeroed.
    assert result.mc.tvd_mc_m[0] == pytest.approx(-7.63e-7, abs=1e-12)


# ---------------------------------------------------------------------------
# Deviation-contract YAML authoring validation
# (load_deviation_contract_config)
# ---------------------------------------------------------------------------
def _write_yaml(tmp_path, text: str) -> str:
    p = tmp_path / "contracts.yml"
    p.write_text(text)
    return str(p)


def _minimal_yaml_entry(sha: str) -> str:
    return f"""
files:
  dev_valid.txt:
    expected_sha256: "{sha}"
    expected_well_identifier: "Test Well 1"
    expected_survey_identifier: "Test survey 1"
    expected_coordinate_reference_system: 'GDA94 / MGA Zone 51 ("") [null,null]'
    expected_wellhead_x_m: 100000.0
    expected_wellhead_y_m: 200000.0
    expected_datum_m: 10.0
    expected_datum_reference: "RT, Rotary table, from MSL"
    expected_column_count: 11
    expected_column_order: [MD, X, Y, Z, TVD, DX, DY, AZIM_TN, INCL, DLS, AZIM_GN]
    expected_units:
      MD: m
      X: m
      Y: m
      Z: m
      TVD: m
      DX: m
      DY: m
      AZIM_TN: deg
      INCL: deg
      DLS: deg_per_30m
      AZIM_GN: deg
    expected_station_count: 6
    expected_md_min_m: 0.0
    expected_md_max_m: 1200.0
    azimuth_reference_for_grid_coordinates: AZIM_GN
    source_depth_convention: "test"
    header_tolerance_m: 0.001
    residual_tolerance_tvd_m: 0.01
    residual_tolerance_horizontal_m: 0.01
    residual_fail_threshold_m: 5.0
    depth_basis_policy: petrel_source_trace
    notes: "test"
"""


def test_valid_yaml_contract_loads(tmp_path):
    sha = _sha256(FIXTURES / "dev_valid.txt")
    path = _write_yaml(tmp_path, _minimal_yaml_entry(sha))
    contracts = load_deviation_contract_config(path)
    assert "dev_valid.txt" in contracts
    assert contracts["dev_valid.txt"].expected_station_count == 6


def test_duplicate_contract_key_rejected(tmp_path):
    sha = _sha256(FIXTURES / "dev_valid.txt")
    text = _minimal_yaml_entry(sha) + _minimal_yaml_entry(sha).replace(
        "dev_valid.txt:", "dev_valid.txt:  # duplicate\n"
    )
    # Force an actual duplicate top-level key by concatenating two "files:" blocks
    # is invalid YAML shape; instead duplicate the key WITHIN one files: mapping.
    dup_text = """
files:
  dev_valid.txt:
    expected_sha256: "%s"
    expected_well_identifier: "A"
    expected_survey_identifier: "S"
    expected_coordinate_reference_system: "CRS"
    expected_wellhead_x_m: 1.0
    expected_wellhead_y_m: 1.0
    expected_datum_m: 1.0
    expected_datum_reference: "RT"
    expected_column_count: 11
    expected_column_order: [MD, X, Y, Z, TVD, DX, DY, AZIM_TN, INCL, DLS, AZIM_GN]
    expected_units: {MD: m, X: m, Y: m, Z: m, TVD: m, DX: m, DY: m, AZIM_TN: deg, INCL: deg, DLS: deg_per_30m, AZIM_GN: deg}
    expected_station_count: 6
    expected_md_min_m: 0.0
    expected_md_max_m: 1.0
    azimuth_reference_for_grid_coordinates: AZIM_GN
    source_depth_convention: "test"
    header_tolerance_m: 0.001
    residual_tolerance_tvd_m: 0.01
    residual_tolerance_horizontal_m: 0.01
    residual_fail_threshold_m: 5.0
    depth_basis_policy: petrel_source_trace
    notes: "test"
  dev_valid.txt:
    expected_sha256: "%s"
    expected_well_identifier: "B"
    expected_survey_identifier: "S"
    expected_coordinate_reference_system: "CRS"
    expected_wellhead_x_m: 1.0
    expected_wellhead_y_m: 1.0
    expected_datum_m: 1.0
    expected_datum_reference: "RT"
    expected_column_count: 11
    expected_column_order: [MD, X, Y, Z, TVD, DX, DY, AZIM_TN, INCL, DLS, AZIM_GN]
    expected_units: {MD: m, X: m, Y: m, Z: m, TVD: m, DX: m, DY: m, AZIM_TN: deg, INCL: deg, DLS: deg_per_30m, AZIM_GN: deg}
    expected_station_count: 6
    expected_md_min_m: 0.0
    expected_md_max_m: 1.0
    azimuth_reference_for_grid_coordinates: AZIM_GN
    source_depth_convention: "test"
    header_tolerance_m: 0.001
    residual_tolerance_tvd_m: 0.01
    residual_tolerance_horizontal_m: 0.01
    residual_fail_threshold_m: 5.0
    depth_basis_policy: petrel_source_trace
    notes: "test"
""" % (sha, sha)
    path = _write_yaml(tmp_path, dup_text)
    with pytest.raises(DeviationContractDefinitionError, match="Duplicate key"):
        load_deviation_contract_config(path)


def test_invalid_type_rejected(tmp_path):
    sha = _sha256(FIXTURES / "dev_valid.txt")
    text = _minimal_yaml_entry(sha).replace("expected_column_count: 11", 'expected_column_count: "eleven"')
    path = _write_yaml(tmp_path, text)
    with pytest.raises(DeviationContractDefinitionError, match="expected_column_count"):
        load_deviation_contract_config(path)


def test_unsupported_azimuth_reference_rejected(tmp_path):
    sha = _sha256(FIXTURES / "dev_valid.txt")
    text = _minimal_yaml_entry(sha).replace(
        "azimuth_reference_for_grid_coordinates: AZIM_GN",
        "azimuth_reference_for_grid_coordinates: AZIM_MAGNETIC",
    )
    path = _write_yaml(tmp_path, text)
    with pytest.raises(DeviationContractDefinitionError, match="azimuth_reference_for_grid_coordinates"):
        load_deviation_contract_config(path)


def test_unsupported_depth_basis_policy_rejected(tmp_path):
    sha = _sha256(FIXTURES / "dev_valid.txt")
    text = _minimal_yaml_entry(sha).replace(
        "depth_basis_policy: petrel_source_trace", "depth_basis_policy: made_up_policy"
    )
    path = _write_yaml(tmp_path, text)
    with pytest.raises(DeviationContractDefinitionError, match="depth_basis_policy"):
        load_deviation_contract_config(path)


def test_invalid_tolerance_rejected(tmp_path):
    sha = _sha256(FIXTURES / "dev_valid.txt")
    text = _minimal_yaml_entry(sha).replace("residual_tolerance_tvd_m: 0.01", "residual_tolerance_tvd_m: -0.01")
    path = _write_yaml(tmp_path, text)
    with pytest.raises(DeviationContractDefinitionError, match="non-negative"):
        load_deviation_contract_config(path)


def test_fail_threshold_not_exceeding_tolerance_rejected(tmp_path):
    sha = _sha256(FIXTURES / "dev_valid.txt")
    text = _minimal_yaml_entry(sha).replace("residual_fail_threshold_m: 5.0", "residual_fail_threshold_m: 0.005")
    path = _write_yaml(tmp_path, text)
    with pytest.raises(DeviationContractDefinitionError, match="must exceed"):
        load_deviation_contract_config(path)


def test_incompatible_column_count_rejected(tmp_path):
    sha = _sha256(FIXTURES / "dev_valid.txt")
    text = _minimal_yaml_entry(sha).replace("expected_column_count: 11", "expected_column_count: 10")
    path = _write_yaml(tmp_path, text)
    with pytest.raises(DeviationContractDefinitionError, match="does not match"):
        load_deviation_contract_config(path)


def test_missing_required_field_rejected(tmp_path):
    sha = _sha256(FIXTURES / "dev_valid.txt")
    text = _minimal_yaml_entry(sha).replace('    expected_datum_reference: "RT, Rotary table, from MSL"\n', "")
    path = _write_yaml(tmp_path, text)
    with pytest.raises(DeviationContractDefinitionError, match="missing required field"):
        load_deviation_contract_config(path)


# ---------------------------------------------------------------------------
# Batch loading / error isolation
# ---------------------------------------------------------------------------
def test_batch_isolates_one_failed_well_from_successful_wells():
    contracts = {
        "dev_valid.txt": _base_contract("dev_valid.txt"),
        "dev_duplicate_md.txt": _base_contract("dev_duplicate_md.txt"),
    }
    file_paths = {
        "GOOD_WELL": str(FIXTURES / "dev_valid.txt"),
        "BAD_WELL": str(FIXTURES / "dev_duplicate_md.txt"),
    }
    results, failures = load_deviation_surveys(file_paths, contracts)
    assert "GOOD_WELL" in results
    assert "BAD_WELL" in failures
    assert failures["BAD_WELL"].error_type == "contract_failure"


def test_batch_isolates_file_not_found():
    contracts = {"does_not_exist_dev.txt": _base_contract("does_not_exist_dev.txt")}
    file_paths = {"MISSING": str(FIXTURES / "does_not_exist_dev.txt")}
    results, failures = load_deviation_surveys(file_paths, contracts)
    assert "MISSING" in failures
    assert failures["MISSING"].error_type == "file_not_found"


def test_batch_deterministic_row_ordering():
    contracts = {
        "dev_valid.txt": _base_contract("dev_valid.txt"),
    }
    file_paths = {"WELL_A": str(FIXTURES / "dev_valid.txt")}
    results1, _ = load_deviation_surveys(file_paths, contracts)
    results2, _ = load_deviation_surveys(file_paths, contracts)
    assert list(results1["WELL_A"].raw.MD_source_m) == list(results2["WELL_A"].raw.MD_source_m)


def test_batch_unexpected_programming_error_propagates(monkeypatch):
    import p2mem.io.deviation as devmod

    def _boom(*args, **kwargs):
        raise KeyError("simulated programming error")

    monkeypatch.setattr(devmod, "parse_deviation_header", _boom)
    contracts = {"dev_valid.txt": _base_contract("dev_valid.txt")}
    file_paths = {"WELL_A": str(FIXTURES / "dev_valid.txt")}
    with pytest.raises(KeyError):
        devmod.load_deviation_surveys(file_paths, contracts)


# ---------------------------------------------------------------------------
# Trajectory validation status integration (PASS vs WARNING)
# ---------------------------------------------------------------------------
def test_trajectory_validation_status_pass_for_self_consistent_fixture():
    result = _load_valid()
    assert result.validation.overall_status == STATUS_PASS
    assert result.validation.tvd_status == STATUS_PASS


def test_source_and_computed_trajectories_never_overwritten():
    result = _load_valid()
    # Source arrays are untouched by the MC computation.
    assert result.raw.TVD_source_m is not result.mc.tvd_mc_m
    assert not np.array_equal(result.raw.TVD_source_m, np.zeros_like(result.raw.TVD_source_m))
    # Both remain independently accessible on the same result object.
    assert result.raw.TVD_source_m.shape == result.mc.tvd_mc_m.shape


def test_azim_tn_never_used_for_grid_coordinate_residuals():
    # dev_valid.txt was generated with AZIM_TN deliberately offset from
    # AZIM_GN. If the implementation mistakenly used AZIM_TN for the
    # grid-coordinate (northing/easting) computation, residuals against
    # the (AZIM_GN-derived) source DX/DY would be large, not near-zero.
    result = _load_valid()
    assert result.validation.easting_max_abs_residual_m < 1e-6
    assert result.validation.northing_max_abs_residual_m < 1e-6
