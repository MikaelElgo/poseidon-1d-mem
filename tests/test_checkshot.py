"""
tests/test_checkshot.py - Validation suite for p2mem.io.checkshot
(Increment 4: checkshot file ingestion and per-file contract resolution;
Increment 4.1.1: a batch-isolation regression test proving a TimeDepthError
raised during numerical conditioning for one well - via the synthetic
`checkshot_hidden_reversal.txt` fixture - is caught and isolated exactly
like every other expected per-well failure, never propagated out of
load_checkshot_surveys and never caught with a blanket except Exception).

PORTABLE unit tests only: small synthetic fixtures under tests/fixtures/
(checkshot_*.txt). Real three-file integration (which requires the
private/raw project checkshot files) is a separate notebook/script run -
see dev_scratch_inc4/analyze_checkshot.py (not packaged) and
INCREMENT_04_MANIFEST.md for the actual recomputed results.
"""

import hashlib
from pathlib import Path

import pytest
import yaml

from p2mem.checkshot_models import CheckshotFileContract
from p2mem.io.checkshot import (
    DEPTH_BASIS_NOT_EXPLICITLY_DECLARED_CODE,
    WELL_IDENTITY_INFERRED_UNVERIFIED_CODE,
    CheckshotContractDefinitionError,
    CheckshotContractError,
    CheckshotFileNotFoundError,
    CheckshotParsingError,
    load_checkshot_contract_config,
    load_checkshot_file,
    load_checkshot_surveys,
    parse_checkshot_header,
    read_checkshot_rows,
    resolve_checkshot_contract,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_contract(filename: str, **overrides) -> CheckshotFileContract:
    fixture_path = FIXTURES / filename
    default_sha256 = _sha256(fixture_path) if fixture_path.exists() else "0" * 64
    defaults = dict(
        source_filename=filename,
        expected_sha256=default_sha256,
        project_well_key="Test_Well_1",
        well_identity_evidence_status="verified",
        well_identity_evidence_notes="Test fixture; identity not a real project well.",
        model_use_status="primary_model",
        expected_survey_statement=(
            "VELOCITY SURVEY:(Schlumberger) OWT, vertically corrected, relative to SRD (MSL)"
        ),
        expected_column_header_line="Depth\tTVDSS\tOWT(sec)",
        expected_column_order=("Depth", "TVDSS", "OWT(sec)"),
        expected_column_count=3,
        expected_time_type="OWT",
        expected_time_unit="s",
        expected_vertical_correction_fragment="vertically corrected",
        expected_srd_reference_fragment="relative to SRD (MSL)",
        expected_row_count=5,
        expected_depth_min_m=100.0,
        expected_depth_max_m=400.0,
        expected_tvdss_min_m=95.0,
        expected_tvdss_max_m=380.0,
        expected_owt_min_s=0.1000,
        expected_owt_max_s=0.3700,
        numeric_range_tolerance=0.0001,
        depth_basis_interpretation_status="candidate_md_evaluated_against_locked_survey",
        duplicate_tie_policy="raw_rows_preserved_median_representative_all_ties_registered",
        interpolation_policy="piecewise_linear_no_extrapolation",
        extrapolation_policy="disallowed_nan_outside_coverage",
        notes="Test fixture contract.",
    )
    defaults.update(overrides)
    return CheckshotFileContract(**defaults)


# ---------------------------------------------------------------------------
# Structural parsing
# ---------------------------------------------------------------------------
def test_valid_file_parses_header_and_rows():
    header = parse_checkshot_header(str(FIXTURES / "checkshot_valid.txt"))
    assert header.survey_statement.startswith("VELOCITY SURVEY")
    assert header.column_names == ("Depth", "TVDSS", "OWT(sec)")
    assert header.line_ending_convention == "CRLF"
    stations = read_checkshot_rows(str(FIXTURES / "checkshot_valid.txt"))
    assert stations.Depth_source_m.size == 5
    assert stations.Depth_source_m.tolist() == [100.0, 200.0, 200.0, 300.0, 400.0]


def test_strictly_increasing_file_has_no_duplicate_depth():
    stations = read_checkshot_rows(str(FIXTURES / "checkshot_strictly_increasing.txt"))
    assert stations.Depth_source_m.tolist() == [100.0, 200.0, 300.0]


def test_file_not_found_raises_typed_error():
    with pytest.raises(CheckshotFileNotFoundError):
        parse_checkshot_header(str(FIXTURES / "does_not_exist.txt"))


def test_missing_header_line_rejected():
    with pytest.raises(CheckshotParsingError):
        parse_checkshot_header(str(FIXTURES / "checkshot_missing_header.txt"))


def test_wrong_header_column_count_rejected():
    with pytest.raises(CheckshotParsingError):
        parse_checkshot_header(str(FIXTURES / "checkshot_wrong_header_columns.txt"))


def test_row_width_mismatch_rejected():
    with pytest.raises(CheckshotParsingError):
        read_checkshot_rows(str(FIXTURES / "checkshot_row_width_mismatch.txt"))


def test_malformed_numeric_token_rejected():
    with pytest.raises(CheckshotParsingError):
        read_checkshot_rows(str(FIXTURES / "checkshot_malformed_numeric.txt"))


def test_nonfinite_literal_token_rejected():
    with pytest.raises(CheckshotParsingError):
        read_checkshot_rows(str(FIXTURES / "checkshot_nonfinite.txt"))


def test_blank_line_before_last_row_rejected():
    with pytest.raises(CheckshotParsingError):
        read_checkshot_rows(str(FIXTURES / "checkshot_blank_line_mid.txt"))


def test_no_data_rows_rejected():
    with pytest.raises(CheckshotParsingError):
        read_checkshot_rows(str(FIXTURES / "checkshot_no_data_rows.txt"))


# ---------------------------------------------------------------------------
# Contract resolution
# ---------------------------------------------------------------------------
def test_valid_file_and_contract_resolves_cleanly():
    path = str(FIXTURES / "checkshot_valid.txt")
    header = parse_checkshot_header(path)
    stations = read_checkshot_rows(path)
    contract = _base_contract("checkshot_valid.txt")
    issues = resolve_checkshot_contract(header, stations, contract)
    assert all(i.severity == "WARNING" for i in issues)
    codes = {i.code for i in issues}
    assert DEPTH_BASIS_NOT_EXPLICITLY_DECLARED_CODE in codes


def test_wrong_filename_is_blocking():
    path = str(FIXTURES / "checkshot_valid.txt")
    header = parse_checkshot_header(path)
    stations = read_checkshot_rows(path)
    contract = _base_contract("checkshot_valid.txt", source_filename="Some-Other-Name.txt")
    issues = resolve_checkshot_contract(header, stations, contract)
    assert any(i.code == "FILENAME_MISMATCH" and i.severity == "ERROR" for i in issues)


def test_wrong_sha256_is_blocking():
    path = str(FIXTURES / "checkshot_valid.txt")
    header = parse_checkshot_header(path)
    stations = read_checkshot_rows(path)
    contract = _base_contract("checkshot_valid.txt", expected_sha256="0" * 64)
    issues = resolve_checkshot_contract(header, stations, contract)
    assert any(i.code == "SHA256_MISMATCH" and i.severity == "ERROR" for i in issues)


def test_wrong_survey_statement_is_blocking():
    path = str(FIXTURES / "checkshot_valid.txt")
    header = parse_checkshot_header(path)
    stations = read_checkshot_rows(path)
    contract = _base_contract("checkshot_valid.txt", expected_survey_statement="WRONG STATEMENT")
    issues = resolve_checkshot_contract(header, stations, contract)
    codes = {(i.code, i.severity) for i in issues}
    assert ("SURVEY_STATEMENT_MISMATCH", "ERROR") in codes


def test_fragment_missing_from_actual_header_is_blocking():
    # Fragment checks are independent of the exact-statement check: they
    # verify the CONTRACT's declared fragment is present in the ACTUAL
    # file's own header text (not the contract's expected text).
    path = str(FIXTURES / "checkshot_valid.txt")
    header = parse_checkshot_header(path)
    stations = read_checkshot_rows(path)
    contract = _base_contract(
        "checkshot_valid.txt", expected_vertical_correction_fragment="this fragment is not present"
    )
    issues = resolve_checkshot_contract(header, stations, contract)
    assert any(i.code == "VERTICAL_CORRECTION_STATEMENT_MISSING" and i.severity == "ERROR" for i in issues)


def test_wrong_column_header_line_is_blocking():
    path = str(FIXTURES / "checkshot_valid.txt")
    header = parse_checkshot_header(path)
    stations = read_checkshot_rows(path)
    contract = _base_contract("checkshot_valid.txt", expected_column_header_line="A\tB\tC")
    issues = resolve_checkshot_contract(header, stations, contract)
    assert any(i.code == "COLUMN_HEADER_LINE_MISMATCH" and i.severity == "ERROR" for i in issues)


def test_wrong_column_order_is_blocking():
    path = str(FIXTURES / "checkshot_valid.txt")
    header = parse_checkshot_header(path)
    stations = read_checkshot_rows(path)
    contract = _base_contract("checkshot_valid.txt", expected_column_order=("TVDSS", "Depth", "OWT(sec)"))
    issues = resolve_checkshot_contract(header, stations, contract)
    assert any(i.code == "COLUMN_ORDER_MISMATCH" and i.severity == "ERROR" for i in issues)


def test_wrong_row_count_is_blocking():
    path = str(FIXTURES / "checkshot_valid.txt")
    header = parse_checkshot_header(path)
    stations = read_checkshot_rows(path)
    contract = _base_contract("checkshot_valid.txt", expected_row_count=999)
    issues = resolve_checkshot_contract(header, stations, contract)
    assert any(i.code == "ROW_COUNT_MISMATCH" and i.severity == "ERROR" for i in issues)


def test_numeric_range_mismatch_is_blocking():
    path = str(FIXTURES / "checkshot_valid.txt")
    header = parse_checkshot_header(path)
    stations = read_checkshot_rows(path)
    contract = _base_contract("checkshot_valid.txt", expected_depth_max_m=999.0)
    issues = resolve_checkshot_contract(header, stations, contract)
    assert any(i.code == "NUMERIC_RANGE_MISMATCH" and i.severity == "ERROR" for i in issues)


def test_numeric_range_within_tolerance_is_not_flagged():
    path = str(FIXTURES / "checkshot_valid.txt")
    header = parse_checkshot_header(path)
    stations = read_checkshot_rows(path)
    contract = _base_contract("checkshot_valid.txt", expected_depth_max_m=400.00005)
    issues = resolve_checkshot_contract(header, stations, contract)
    assert not any(i.code == "NUMERIC_RANGE_MISMATCH" for i in issues)


def test_depth_basis_warning_always_present_on_success():
    path = str(FIXTURES / "checkshot_valid.txt")
    header = parse_checkshot_header(path)
    stations = read_checkshot_rows(path)
    contract = _base_contract("checkshot_valid.txt")
    issues = resolve_checkshot_contract(header, stations, contract)
    codes = {i.code for i in issues}
    assert DEPTH_BASIS_NOT_EXPLICITLY_DECLARED_CODE in codes


def test_well_identity_inferred_unverified_warning_present_when_declared():
    path = str(FIXTURES / "checkshot_valid.txt")
    header = parse_checkshot_header(path)
    stations = read_checkshot_rows(path)
    contract = _base_contract(
        "checkshot_valid.txt",
        well_identity_evidence_status="inferred_unverified",
        model_use_status="qc_only",
    )
    issues = resolve_checkshot_contract(header, stations, contract)
    codes = {i.code for i in issues}
    assert WELL_IDENTITY_INFERRED_UNVERIFIED_CODE in codes


def test_well_identity_inferred_warning_absent_when_verified():
    path = str(FIXTURES / "checkshot_valid.txt")
    header = parse_checkshot_header(path)
    stations = read_checkshot_rows(path)
    contract = _base_contract("checkshot_valid.txt", well_identity_evidence_status="verified")
    issues = resolve_checkshot_contract(header, stations, contract)
    codes = {i.code for i in issues}
    assert WELL_IDENTITY_INFERRED_UNVERIFIED_CODE not in codes


# ---------------------------------------------------------------------------
# load_checkshot_file / load_checkshot_surveys
# ---------------------------------------------------------------------------
def test_load_checkshot_file_returns_typed_result_with_ties_and_conditioning():
    contract = _base_contract("checkshot_valid.txt")
    result = load_checkshot_file(str(FIXTURES / "checkshot_valid.txt"), contract)
    assert result.contract_status == "PASSED"
    assert result.raw.Depth_source_m.size == 5
    assert result.conditioned.n_conditioned_rows == 4  # one duplicate Depth=200.0 group collapsed
    assert result.conditioned.n_tie_groups == 1
    assert len(result.duplicate_ties) == 1
    tie = result.duplicate_ties[0]
    assert tie.tie_value_m == 200.0
    assert tie.group_size == 2
    assert tie.selected_representative_tvdss_m == pytest.approx((190.0 + 190.5) / 2.0)
    assert result.depth_comparison is None  # no survey trajectory supplied


def test_load_checkshot_file_contract_error_carries_all_issues():
    contract = _base_contract("checkshot_valid.txt", expected_sha256="0" * 64)
    with pytest.raises(CheckshotContractError) as exc_info:
        load_checkshot_file(str(FIXTURES / "checkshot_valid.txt"), contract)
    assert any(i.code == "SHA256_MISMATCH" for i in exc_info.value.issues)


def test_load_checkshot_file_with_survey_trajectory_computes_depth_comparison():
    import numpy as np

    contract = _base_contract(
        "checkshot_strictly_increasing.txt",
        expected_row_count=3,
        expected_depth_min_m=100.0, expected_depth_max_m=300.0,
        expected_tvdss_min_m=95.0, expected_tvdss_max_m=285.0,
        expected_owt_min_s=0.10, expected_owt_max_s=0.28,
    )
    survey_md = np.array([0.0, 100.0, 200.0, 300.0, 400.0])
    survey_tvd = np.array([0.0, 95.0, 190.0, 285.0, 380.0])
    result = load_checkshot_file(
        str(FIXTURES / "checkshot_strictly_increasing.txt"),
        contract,
        survey_md_m=survey_md,
        survey_tvd_m=survey_tvd,
        datum_elevation_m=0.0,
    )
    assert result.depth_comparison is not None
    assert result.depth_comparison.n_compared == 3
    assert result.depth_comparison.max_abs_residual_m == pytest.approx(0.0, abs=1e-9)


def test_load_checkshot_file_builds_axis_conditioned_tables_when_no_axis_ties():
    # checkshot_valid.txt has a Depth tie but its Depth-conditioned
    # TVDSS/OWT arrays are both strictly increasing already -> zero
    # axis-tie entries, but the tables must still be built (Increment 4.1).
    contract = _base_contract("checkshot_valid.txt")
    result = load_checkshot_file(str(FIXTURES / "checkshot_valid.txt"), contract)
    assert result.axis_tie_entries == ()
    assert set(result.axis_tables.keys()) == {"tvdss_to_owt", "owt_to_tvdss"}
    assert result.axis_tables["tvdss_to_owt"].n_axis_tie_groups == 0
    assert result.axis_tables["owt_to_tvdss"].n_axis_tie_groups == 0


def test_load_checkshot_file_registers_genuine_axis_tie_and_conditions_median(tmp_path=None):
    # checkshot_axis_tie.txt has NO Depth ties, but TVDSS=190.0 repeats at
    # Depth=200 and Depth=300 with DIFFERENT OWT values (0.19 vs 0.20) -
    # this is the Increment 4.1 order-invariant axis-tie-conditioning path
    # exercised end-to-end through load_checkshot_file.
    contract = _base_contract(
        "checkshot_axis_tie.txt",
        expected_row_count=4,
        expected_depth_min_m=100.0, expected_depth_max_m=400.0,
        expected_tvdss_min_m=95.0, expected_tvdss_max_m=285.0,
        expected_owt_min_s=0.10, expected_owt_max_s=0.28,
    )
    result = load_checkshot_file(str(FIXTURES / "checkshot_axis_tie.txt"), contract)
    assert result.conditioned.n_tie_groups == 0  # no Depth ties
    assert len(result.axis_tie_entries) == 1
    tie = result.axis_tie_entries[0]
    assert tie.interpolation_direction == "tvdss_to_owt"
    assert tie.tie_axis_value == pytest.approx(190.0)
    assert tie.tie_kind == "genuinely_non_unique"
    assert tie.selected_representative_dependent_value == pytest.approx(0.195)  # median of 0.19/0.20
    table = result.axis_tables["tvdss_to_owt"]
    assert table.n_axis_tie_groups == 1
    assert table.axis_values.size == 3  # 4 input points collapse to 3 after the tie


def test_batch_isolates_one_failed_well_from_successful_wells():
    contracts = {
        "checkshot_valid.txt": _base_contract("checkshot_valid.txt"),
        "checkshot_strictly_increasing.txt": _base_contract(
            "checkshot_strictly_increasing.txt", expected_sha256="0" * 64, expected_row_count=3
        ),
    }
    file_paths = {
        "Well_A": str(FIXTURES / "checkshot_valid.txt"),
        "Well_B": str(FIXTURES / "checkshot_strictly_increasing.txt"),
    }
    results, failures = load_checkshot_surveys(file_paths, contracts)
    assert "Well_A" in results
    assert "Well_B" in failures
    assert failures["Well_B"].error_type == "contract_failure"


def test_batch_isolates_numerical_conditioning_failure_from_successful_wells():
    # Increment 4.1.1 (Blocking Defect 4): a TimeDepthError raised during
    # numerical conditioning (here, the hidden-reversal-via-global-
    # grouping defect fixed in build_axis_conditioned_lookup_table) for
    # one well must be caught and isolated exactly like a file/parsing/
    # contract failure - it must NOT propagate out of load_checkshot_
    # surveys and stop the other, valid well from loading. Never caught
    # via a blanket `except Exception`.
    contracts = {
        "checkshot_valid.txt": _base_contract("checkshot_valid.txt"),
        "checkshot_hidden_reversal.txt": _base_contract(
            "checkshot_hidden_reversal.txt",
            expected_row_count=4,
            expected_depth_min_m=100.0, expected_depth_max_m=400.0,
            expected_tvdss_min_m=95.0, expected_tvdss_max_m=285.0,
            expected_owt_min_s=0.10, expected_owt_max_s=0.28,
        ),
    }
    file_paths = {
        "Well_A": str(FIXTURES / "checkshot_valid.txt"),
        "Well_B": str(FIXTURES / "checkshot_hidden_reversal.txt"),
    }
    results, failures = load_checkshot_surveys(file_paths, contracts)

    assert "Well_A" in results  # valid well still loads
    assert "Well_B" in failures  # failing well is isolated, not propagated
    assert failures["Well_B"].error_type == "numerical_conditioning_failure"
    message = failures["Well_B"].message
    assert "genuine reversal" in message
    # No absolute path leakage in the failure message.
    assert str(FIXTURES) not in message
    assert "/" not in message  # TimeDepthError messages carry well_key/numeric values only


def test_batch_missing_contract_raises_definition_error():
    contracts = {"checkshot_valid.txt": _base_contract("checkshot_valid.txt")}
    file_paths = {"Well_X": str(FIXTURES / "checkshot_strictly_increasing.txt")}
    with pytest.raises(CheckshotContractDefinitionError):
        load_checkshot_surveys(file_paths, contracts)


# ---------------------------------------------------------------------------
# Contract YAML loading
# ---------------------------------------------------------------------------
def _valid_yaml_entry(filename: str, sha256: str) -> dict:
    return {
        "expected_sha256": sha256,
        "project_well_key": "Test_Well_1",
        "well_identity_evidence_status": "verified",
        "well_identity_evidence_notes": "Test note.",
        "model_use_status": "primary_model",
        "expected_survey_statement": (
            "VELOCITY SURVEY:(Schlumberger) OWT, vertically corrected, relative to SRD (MSL)"
        ),
        "expected_column_header_line": "Depth\tTVDSS\tOWT(sec)",
        "expected_column_order": ["Depth", "TVDSS", "OWT(sec)"],
        "expected_time_type": "OWT",
        "expected_time_unit": "s",
        "expected_vertical_correction_fragment": "vertically corrected",
        "expected_srd_reference_fragment": "relative to SRD (MSL)",
        "expected_row_count": 5,
        "expected_depth_min_m": 100.0,
        "expected_depth_max_m": 400.0,
        "expected_tvdss_min_m": 95.0,
        "expected_tvdss_max_m": 380.0,
        "expected_owt_min_s": 0.1,
        "expected_owt_max_s": 0.37,
        "numeric_range_tolerance": 0.0001,
        "depth_basis_interpretation_status": "candidate_md_evaluated_against_locked_survey",
        "duplicate_tie_policy": "raw_rows_preserved_median_representative_all_ties_registered",
        "interpolation_policy": "piecewise_linear_no_extrapolation",
        "extrapolation_policy": "disallowed_nan_outside_coverage",
        "notes": "Test entry.",
    }


def test_valid_contract_yaml_loads(tmp_path):
    sha = _sha256(FIXTURES / "checkshot_valid.txt")
    doc = {"files": {"checkshot_valid.txt": _valid_yaml_entry("checkshot_valid.txt", sha)}}
    p = tmp_path / "contracts.yml"
    p.write_text(yaml.safe_dump(doc))
    contracts = load_checkshot_contract_config(str(p))
    assert "checkshot_valid.txt" in contracts
    assert contracts["checkshot_valid.txt"].expected_row_count == 5


def test_duplicate_contract_key_rejected(tmp_path):
    sha = _sha256(FIXTURES / "checkshot_valid.txt")
    raw_yaml = f"""
files:
  checkshot_valid.txt:
    expected_sha256: "{sha}"
  checkshot_valid.txt:
    expected_sha256: "{sha}"
"""
    p = tmp_path / "contracts.yml"
    p.write_text(raw_yaml)
    with pytest.raises(CheckshotContractDefinitionError):
        load_checkshot_contract_config(str(p))


def test_missing_required_field_rejected(tmp_path):
    sha = _sha256(FIXTURES / "checkshot_valid.txt")
    entry = _valid_yaml_entry("checkshot_valid.txt", sha)
    del entry["expected_row_count"]
    doc = {"files": {"checkshot_valid.txt": entry}}
    p = tmp_path / "contracts.yml"
    p.write_text(yaml.safe_dump(doc))
    with pytest.raises(CheckshotContractDefinitionError):
        load_checkshot_contract_config(str(p))


def test_invalid_identity_status_rejected(tmp_path):
    sha = _sha256(FIXTURES / "checkshot_valid.txt")
    entry = _valid_yaml_entry("checkshot_valid.txt", sha)
    entry["well_identity_evidence_status"] = "not_a_real_status"
    doc = {"files": {"checkshot_valid.txt": entry}}
    p = tmp_path / "contracts.yml"
    p.write_text(yaml.safe_dump(doc))
    with pytest.raises(CheckshotContractDefinitionError):
        load_checkshot_contract_config(str(p))


def test_invalid_model_use_status_rejected(tmp_path):
    sha = _sha256(FIXTURES / "checkshot_valid.txt")
    entry = _valid_yaml_entry("checkshot_valid.txt", sha)
    entry["model_use_status"] = "not_a_real_status"
    doc = {"files": {"checkshot_valid.txt": entry}}
    p = tmp_path / "contracts.yml"
    p.write_text(yaml.safe_dump(doc))
    with pytest.raises(CheckshotContractDefinitionError):
        load_checkshot_contract_config(str(p))


def test_wrong_column_order_length_rejected(tmp_path):
    sha = _sha256(FIXTURES / "checkshot_valid.txt")
    entry = _valid_yaml_entry("checkshot_valid.txt", sha)
    entry["expected_column_order"] = ["Depth", "TVDSS"]
    doc = {"files": {"checkshot_valid.txt": entry}}
    p = tmp_path / "contracts.yml"
    p.write_text(yaml.safe_dump(doc))
    with pytest.raises(CheckshotContractDefinitionError):
        load_checkshot_contract_config(str(p))


def test_min_greater_than_max_rejected(tmp_path):
    sha = _sha256(FIXTURES / "checkshot_valid.txt")
    entry = _valid_yaml_entry("checkshot_valid.txt", sha)
    entry["expected_depth_min_m"] = 500.0
    entry["expected_depth_max_m"] = 100.0
    doc = {"files": {"checkshot_valid.txt": entry}}
    p = tmp_path / "contracts.yml"
    p.write_text(yaml.safe_dump(doc))
    with pytest.raises(CheckshotContractDefinitionError):
        load_checkshot_contract_config(str(p))


def test_negative_tolerance_rejected(tmp_path):
    sha = _sha256(FIXTURES / "checkshot_valid.txt")
    entry = _valid_yaml_entry("checkshot_valid.txt", sha)
    entry["numeric_range_tolerance"] = -0.1
    doc = {"files": {"checkshot_valid.txt": entry}}
    p = tmp_path / "contracts.yml"
    p.write_text(yaml.safe_dump(doc))
    with pytest.raises(CheckshotContractDefinitionError):
        load_checkshot_contract_config(str(p))


def test_real_checkshot_contracts_yaml_loads_and_matches_real_files():
    """Sanity check against the actual packaged Increment 4 contract file
    and the real approved (hyphenated) filenames - values themselves are
    exercised end-to-end only in the dev-only real integration run."""
    contracts = load_checkshot_contract_config(
        str(Path(__file__).parent.parent / "config" / "checkshot_contracts.yml")
    )
    assert set(contracts) == {
        "Poseidon2-Checkshot.txt",
        "Boreas1-Checkshot.txt",
        "Proteus1-Checkshot.txt",
    }
    assert contracts["Poseidon2-Checkshot.txt"].model_use_status == "primary_model"
    assert contracts["Boreas1-Checkshot.txt"].model_use_status == "qc_only"
    assert contracts["Proteus1-Checkshot.txt"].well_identity_evidence_status == "inferred_unverified"
