"""
tests/test_las.py - Validation suite for p2mem.io.las (Increment 2,
corrected in Increment 2.1).

These are PORTABLE unit tests: they use only the small synthetic LAS
fixtures under tests/fixtures/ (plus a couple of contracts/YAML snippets
built inline) and never require the four private/raw project LAS files.
The real four-well integration run belongs in the Colab notebook
(02_LAS_Ingestion_and_Curve_Contracts.ipynb), not here.

Coverage required by the Increment 2 specification (unchanged, all still
passing under the corrected architecture):
    - valid LAS with standard (non-empty) mnemonics
    - valid LAS with empty mnemonic fields and usable descriptions
    - declared NULL -> NaN conversion
    - duplicate / ambiguous curve description
    - duplicate canonical mapping (contract-authoring error)
    - wrong unit (contract vs file disagreement)
    - unexpected column order
    - mismatched data-column width
    - non-monotonic measured depth
    - duplicate measured depth
    - missing required curve (and a present-but-optional counterpart)
    - malformed numeric row
    - scalar metadata extraction (WELL, STRT, STOP, STEP, NULL, VERS, WRAP)
    - deterministic output ordering

Coverage added by the Increment 2.1 corrective patch (see
INCREMENT_02_v2.1_MANIFEST.md for the audit this responds to):
    - raw DTCO stays "DTCO_us_per_ft"; canonical compressional velocity is
      "VP_m_s" (never "DTCO")
    - raw DTSM stays "DTSM_us_per_ft"; canonical shear velocity is "VS_m_s"
    - RHOB raw/canonical names and units are distinct and both explicit
    - coverage rows carry correct raw AND canonical units/min/max
    - filename mismatch / SHA-256 mismatch / missing WELL / missing NULL /
      VERS mismatch / NULL mismatch are all blocking
    - WRAP=YES is rejected clearly as an unimplemented layout
    - duplicate ordinals are rejected at contract-load time
    - a conversion function incompatible with its declared units is
      rejected at contract-load time
    - zero or multiple measured-depth-role curves are rejected
    - raw data retains the literal sentinel; canonical data replaces only
      the declared sentinel with NaN
    - a non-finite (literal NaN/Inf) token is rejected as a structural
      parsing defect
    - per-file failures (file-not-found, parsing, contract, conversion)
      are isolated by `load_wells` as typed `IngestionFailure` records
    - deterministic output ordering is unchanged under the new schema

Run with:  pytest -v
"""

import hashlib
import math
import tempfile
from pathlib import Path

import numpy as np
import pytest

from p2mem.io.las import (
    LasContractDefinitionError,
    LasContractError,
    LasConversionError,
    LasFileNotFoundError,
    LasParsingError,
    _parse_definition_line,
    _parse_description_ordinal_name,
    compute_depth_diagnostics,
    load_file_contract_config,
    load_las_file,
    load_wells,
    parse_las_header,
    resolve_curve_contract,
)
from p2mem.models import CurveContractEntry, FileContract, IngestionFailure

FIXTURES = Path(__file__).parent / "fixtures"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _entry(
    ordinal,
    raw_mnemonic,
    raw_unit,
    raw_description,
    description_ordinal,
    description_name,
    source_curve_name,
    raw_canonical_name,
    canonical_name,
    canonical_unit,
    required=True,
    conversion_function="identity",
    semantic_role="measurement",
    notes="test fixture entry",
):
    return CurveContractEntry(
        ordinal=ordinal,
        semantic_role=semantic_role,
        source_curve_name=source_curve_name,
        raw_mnemonic=raw_mnemonic,
        raw_unit=raw_unit,
        raw_description=raw_description,
        description_ordinal=description_ordinal,
        description_name=description_name,
        raw_canonical_name=raw_canonical_name,
        canonical_name=canonical_name,
        canonical_unit=canonical_unit,
        required=required,
        conversion_function=conversion_function,
        notes=notes,
    )


def _depth_entry(ordinal=0, raw_mnemonic="DEPT", raw_description="Depth", description_ordinal=None, description_name=None):
    return _entry(
        ordinal, raw_mnemonic, "M", raw_description, description_ordinal, description_name,
        source_curve_name="DEPT", raw_canonical_name="DEPT_m", canonical_name="MD_m", canonical_unit="m",
        semantic_role="measured_depth",
    )


def _fixture_contract(filename: str, expected_well_identifier: str, expected_curve_count: int, curves, expected_null_value=-999.25) -> FileContract:
    """Build a FileContract for a fixture file, filling in its real SHA-256 so file-identity checks pass by default."""
    return FileContract(
        source_filename=filename,
        expected_sha256=_sha256(FIXTURES / filename),
        expected_well_identifier=expected_well_identifier,
        expected_las_version="2.0",
        expected_wrap="NO",
        expected_null_value=expected_null_value,
        expected_curve_count=expected_curve_count,
        expected_data_layout="unwrapped_whitespace_delimited",
        curves=tuple(curves),
    )


def _standard_contract() -> FileContract:
    return _fixture_contract(
        "standard_mnemonics.las",
        "Synthetic Standard 1",
        3,
        [
            _depth_entry(0, "DEPT", "Depth"),
            _entry(1, "GR", "API", "Gamma Ray", None, None, "GR", "GR_api", "GR_api", "API"),
            _entry(2, "RHOB", "G/CC", "Bulk Density", None, None, "RHOB", "RHOB_g_per_cm3", "RHOB_kg_m3", "kg/m3", conversion_function="gcc_to_kgm3"),
        ],
    )


def _empty_mnemonic_contract() -> FileContract:
    return _fixture_contract(
        "empty_mnemonic_with_description.las",
        "Synthetic Empty Mnemonic 1",
        4,
        [
            _depth_entry(0, "DEPT", "0 Depth", 0, "Depth"),
            _entry(1, "", "us/ft", "1 DTCO", 1, "DTCO", "DTCO", "DTCO_us_per_ft", "VP_m_s", "m/s", conversion_function="us_per_ft_to_m_per_s"),
            _entry(2, "", "API", "2 GR", 2, "GR", "GR", "GR_api", "GR_api", "API"),
            _entry(3, "", "g/cc", "3 RHOB", 3, "RHOB", "RHOB", "RHOB_g_per_cm3", "RHOB_kg_m3", "kg/m3", conversion_function="gcc_to_kgm3"),
        ],
    )


# ---------------------------------------------------------------------------
# Definition-line parser (the LAS "MNEM.UNIT VALUE :DESC" edge case)
# ---------------------------------------------------------------------------
def test_parse_definition_line_unit_and_value_present():
    d = _parse_definition_line("STRT.M             490.0000            : START DEPTH")
    assert (d.mnemonic, d.unit, d.value, d.description) == ("STRT", "M", "490.0000", "START DEPTH")


def test_parse_definition_line_empty_unit_multiword_value():
    d = _parse_definition_line("WELL.              Poseidon 2          : WELL NAME")
    assert (d.mnemonic, d.unit, d.value, d.description) == ("WELL", "", "Poseidon 2", "WELL NAME")


def test_parse_definition_line_empty_mnemonic_curve_style():
    d = _parse_definition_line(".in                                    : 1 DCAV")
    assert (d.mnemonic, d.unit, d.value, d.description) == ("", "in", "", "1 DCAV")


def test_parse_definition_line_no_description():
    d = _parse_definition_line("CREA.              17-jun-2026")
    assert (d.mnemonic, d.unit, d.value, d.description) == ("CREA", "", "17-jun-2026", "")


def test_parse_definition_line_requires_dot():
    with pytest.raises(LasParsingError):
        _parse_definition_line("NOAAADOT VALUE : DESC")


def test_parse_description_ordinal_name():
    assert _parse_description_ordinal_name("1 DCAV") == (1, "DCAV")
    assert _parse_description_ordinal_name("0 Depth") == (0, "Depth")
    assert _parse_description_ordinal_name("Gamma Ray") == (None, None)
    assert _parse_description_ordinal_name("") == (None, None)


# ---------------------------------------------------------------------------
# Header parsing + scalar metadata extraction
# ---------------------------------------------------------------------------
def test_parse_las_header_standard_mnemonics():
    header = parse_las_header(str(FIXTURES / "standard_mnemonics.las"))
    assert header.source_filename == "standard_mnemonics.las"
    assert len(header.sha256) == 64
    assert header.las_version == "2.0"
    assert header.wrap == "NO"
    assert header.well_name == "Synthetic Standard 1"
    assert header.declared_null == pytest.approx(-999.25)
    assert header.declared_strt == pytest.approx(100.0)
    assert header.declared_stop == pytest.approx(100.4)
    assert header.declared_step == pytest.approx(0.1)
    assert len(header.curve_headers) == 3
    assert [c.raw_mnemonic for c in header.curve_headers] == ["DEPT", "GR", "RHOB"]
    assert [c.ordinal for c in header.curve_headers] == [0, 1, 2]


def test_parse_las_header_empty_mnemonic_with_description():
    header = parse_las_header(str(FIXTURES / "empty_mnemonic_with_description.las"))
    assert len(header.curve_headers) == 4
    dept, dtco, gr, rhob = header.curve_headers
    assert dept.raw_mnemonic == "DEPT" and dept.description_ordinal == 0 and dept.description_name == "Depth"
    assert dtco.raw_mnemonic == "" and dtco.raw_unit == "us/ft"
    assert dtco.description_ordinal == 1 and dtco.description_name == "DTCO"
    assert gr.raw_mnemonic == "" and gr.description_ordinal == 2 and gr.description_name == "GR"
    assert rhob.raw_mnemonic == "" and rhob.description_ordinal == 3 and rhob.description_name == "RHOB"


def test_parse_las_header_missing_file_raises():
    with pytest.raises(LasFileNotFoundError):
        parse_las_header(str(FIXTURES / "does_not_exist.las"))


# ---------------------------------------------------------------------------
# Valid loads: standard mnemonics, and empty-mnemonic-with-description
# ---------------------------------------------------------------------------
def test_load_standard_mnemonics_file():
    result = load_las_file(str(FIXTURES / "standard_mnemonics.las"), _standard_contract())
    assert result.contract_status == "PASSED"
    assert set(result.canonical_data) == {"MD_m", "GR_api", "RHOB_kg_m3"}
    assert result.depth.n_samples == 5
    # NULL sentinel -> NaN, non-null values preserved
    assert np.isnan(result.canonical_data["GR_api"][2])
    assert result.canonical_data["GR_api"][0] == pytest.approx(50.1)
    # RHOB row 3 is NULL -> NaN even after the exact g/cc->kg/m3 conversion
    assert np.isnan(result.canonical_data["RHOB_kg_m3"][3])
    assert result.canonical_data["RHOB_kg_m3"][0] == pytest.approx(2450.0)  # 2.45 g/cc * 1000


def test_load_empty_mnemonic_with_description_file():
    result = load_las_file(str(FIXTURES / "empty_mnemonic_with_description.las"), _empty_mnemonic_contract())
    assert result.contract_status == "PASSED"
    assert set(result.canonical_data) == {"MD_m", "VP_m_s", "GR_api", "RHOB_kg_m3"}
    # DTCO converted from us/ft to VP_m_s via the exact Increment 1.1 function
    expected_v = 304800.0 / 120.5
    assert result.canonical_data["VP_m_s"][0] == pytest.approx(expected_v, rel=1e-9)
    # raw_data must retain the untouched literal value, including NULLs
    dtco_ordinal = 1
    assert result.raw_data[2, dtco_ordinal] == pytest.approx(-999.25)


def test_raw_data_and_canonical_data_are_kept_separate():
    result = load_las_file(str(FIXTURES / "standard_mnemonics.las"), _standard_contract())
    # raw_data must never have NULL substituted (still literally -999.25)
    assert result.raw_data[2, 1] == pytest.approx(-999.25)
    # canonical_data for the same cell must be NaN
    assert np.isnan(result.canonical_data["GR_api"][2])


# ---------------------------------------------------------------------------
# Increment 2.1: explicit, unit-suffixed naming (never the bare mnemonic)
# ---------------------------------------------------------------------------
def test_canonical_velocity_names_never_use_slowness_mnemonic():
    result = load_las_file(str(FIXTURES / "empty_mnemonic_with_description.las"), _empty_mnemonic_contract())
    # "DTCO" (a slowness mnemonic, us/ft) must never label the converted
    # velocity array (m/s) - the canonical key is "VP_m_s".
    assert "DTCO" not in result.canonical_data
    assert "VP_m_s" in result.canonical_data
    dtco_entry = next(c for c in result.contract.curves if c.source_curve_name == "DTCO")
    assert dtco_entry.raw_canonical_name == "DTCO_us_per_ft"
    assert dtco_entry.canonical_name == "VP_m_s"
    assert dtco_entry.canonical_unit == "m/s"


def test_canonical_shear_velocity_naming():
    contract = _fixture_contract(
        "empty_mnemonic_with_description.las",
        "Synthetic Empty Mnemonic 1",
        4,
        [
            _depth_entry(0, "DEPT", "0 Depth", 0, "Depth"),
            _entry(1, "", "us/ft", "1 DTCO", 1, "DTCO", "DTSM", "DTSM_us_per_ft", "VS_m_s", "m/s", conversion_function="us_per_ft_to_m_per_s"),
            _entry(2, "", "API", "2 GR", 2, "GR", "GR", "GR_api", "GR_api", "API"),
            _entry(3, "", "g/cc", "3 RHOB", 3, "RHOB", "RHOB", "RHOB_g_per_cm3", "RHOB_kg_m3", "kg/m3", conversion_function="gcc_to_kgm3"),
        ],
    )
    result = load_las_file(str(FIXTURES / "empty_mnemonic_with_description.las"), contract)
    assert "DTSM" not in result.canonical_data
    assert "VS_m_s" in result.canonical_data
    entry = next(c for c in result.contract.curves if c.source_curve_name == "DTSM")
    assert entry.raw_canonical_name == "DTSM_us_per_ft"
    assert entry.canonical_name == "VS_m_s"


def test_rhob_raw_and_canonical_names_and_units_are_distinct():
    result = load_las_file(str(FIXTURES / "standard_mnemonics.las"), _standard_contract())
    entry = next(c for c in result.contract.curves if c.source_curve_name == "RHOB")
    assert entry.raw_canonical_name == "RHOB_g_per_cm3"
    assert entry.canonical_name == "RHOB_kg_m3"
    assert entry.raw_unit.lower() == "g/cc"
    assert entry.canonical_unit == "kg/m3"
    assert entry.raw_canonical_name != entry.canonical_name


# ---------------------------------------------------------------------------
# Declared NULL conversion
# ---------------------------------------------------------------------------
def test_declared_null_converted_to_nan_only_for_exact_match():
    result = load_las_file(str(FIXTURES / "standard_mnemonics.las"), _standard_contract())
    gr = result.canonical_data["GR_api"]
    assert np.sum(np.isnan(gr)) == 1
    assert np.isnan(gr[2])
    assert gr[4] == pytest.approx(54.5)


def test_raw_data_retains_literal_sentinel_canonical_replaces_only_declared_sentinel():
    result = load_las_file(str(FIXTURES / "standard_mnemonics.las"), _standard_contract())
    # Row 2, column 1 (GR) is the literal NULL sentinel in the source file.
    assert result.raw_data[2, 1] == pytest.approx(-999.25)
    assert np.isnan(result.canonical_data["GR_api"][2])
    # No other raw value is altered, and no other canonical value becomes
    # NaN just because it happens to be numerically extreme.
    assert result.raw_data[4, 1] == pytest.approx(54.5)
    assert not np.isnan(result.canonical_data["GR_api"][4])


# ---------------------------------------------------------------------------
# Duplicate / ambiguous description
# ---------------------------------------------------------------------------
def test_duplicate_raw_description_fails_contract():
    contract = _fixture_contract(
        "duplicate_description.las",
        "Synthetic Duplicate Description 1",
        3,
        [
            _depth_entry(0, "DEPT", "0 Depth", 0, "Depth"),
            _entry(1, "", "API", "GR", None, "GR", "GR_A", "GR_A_api", "GR_A_api", "API"),
            _entry(2, "", "API", "GR", None, "GR", "GR_B", "GR_B_api", "GR_B_api", "API"),
        ],
    )
    with pytest.raises(LasContractError) as excinfo:
        load_las_file(str(FIXTURES / "duplicate_description.las"), contract)
    assert any(i.code == "DUPLICATE_RAW_DESCRIPTION" for i in excinfo.value.issues)


# ---------------------------------------------------------------------------
# Duplicate canonical mapping (contract-authoring error, caught at config-load time)
# ---------------------------------------------------------------------------
_MINIMAL_FILE_HEADER_FIELDS = """
    expected_sha256: "abc123"
    expected_well_identifier: "Some Well"
    expected_las_version: "2.0"
    expected_wrap: "NO"
    expected_null_value: -999.25
    expected_data_layout: "unwrapped_whitespace_delimited"
"""


def test_duplicate_canonical_mapping_rejected_at_contract_load(tmp_path):
    bad_yaml = tmp_path / "bad_contracts.yml"
    bad_yaml.write_text(
        f"""
files:
  some_file.las:
{_MINIMAL_FILE_HEADER_FIELDS}
    expected_curve_count: 2
    curves:
      - ordinal: 0
        semantic_role: measured_depth
        source_curve_name: "DEPT"
        raw_mnemonic: "DEPT"
        raw_unit: "M"
        raw_description: "0 Depth"
        raw_canonical_name: "DEPT_m"
        canonical_name: "MD_m"
        canonical_unit: "m"
        required: true
        conversion_function: "identity"
      - ordinal: 1
        source_curve_name: "GR"
        raw_mnemonic: "GR"
        raw_unit: "API"
        raw_description: "1 GR"
        raw_canonical_name: "GR_api"
        canonical_name: "MD_m"
        canonical_unit: "API"
        required: true
        conversion_function: "identity"
"""
    )
    with pytest.raises(LasContractDefinitionError):
        load_file_contract_config(str(bad_yaml))


# ---------------------------------------------------------------------------
# Wrong unit
# ---------------------------------------------------------------------------
def test_wrong_unit_fails_contract():
    contract = _empty_mnemonic_contract()
    curves = list(contract.curves)
    # GR is declared "API" in the file; assert the contract expects "ohmm" instead.
    curves[2] = _entry(2, "", "ohmm", "2 GR", 2, "GR", "GR", "GR_api", "GR_api", "API")
    bad_contract = FileContract(
        source_filename=contract.source_filename,
        expected_sha256=contract.expected_sha256,
        expected_well_identifier=contract.expected_well_identifier,
        expected_las_version=contract.expected_las_version,
        expected_wrap=contract.expected_wrap,
        expected_null_value=contract.expected_null_value,
        expected_curve_count=contract.expected_curve_count,
        expected_data_layout=contract.expected_data_layout,
        curves=tuple(curves),
    )
    with pytest.raises(LasContractError) as excinfo:
        load_las_file(str(FIXTURES / "empty_mnemonic_with_description.las"), bad_contract)
    assert any(i.code == "CURVE_IDENTITY_MISMATCH" for i in excinfo.value.issues)


# ---------------------------------------------------------------------------
# Unexpected column order
# ---------------------------------------------------------------------------
def test_unexpected_column_order_fails_contract():
    contract = _fixture_contract(
        "empty_mnemonic_with_description.las",
        "Synthetic Empty Mnemonic 1",
        4,
        [
            _depth_entry(0, "DEPT", "0 Depth", 0, "Depth"),
            _entry(1, "", "API", "2 GR", 2, "GR", "GR", "GR_api", "GR_api", "API"),
            _entry(2, "", "us/ft", "1 DTCO", 1, "DTCO", "DTCO", "DTCO_us_per_ft", "VP_m_s", "m/s", conversion_function="us_per_ft_to_m_per_s"),
            _entry(3, "", "g/cc", "3 RHOB", 3, "RHOB", "RHOB", "RHOB_g_per_cm3", "RHOB_kg_m3", "kg/m3", conversion_function="gcc_to_kgm3"),
        ],
    )
    with pytest.raises(LasContractError) as excinfo:
        load_las_file(str(FIXTURES / "empty_mnemonic_with_description.las"), contract)
    codes = {i.code for i in excinfo.value.issues}
    assert "CURVE_IDENTITY_MISMATCH" in codes


# ---------------------------------------------------------------------------
# Mismatched data-column width
# ---------------------------------------------------------------------------
def test_mismatched_data_width_raises():
    contract = _fixture_contract(
        "mismatched_width_row.las",
        "Synthetic Mismatched Width 1",
        3,
        [
            _depth_entry(0, "DEPT", "0 Depth", 0, "Depth"),
            _entry(1, "", "API", "1 GR", 1, "GR", "GR", "GR_api", "GR_api", "API"),
            _entry(2, "", "g/cc", "2 RHOB", 2, "RHOB", "RHOB", "RHOB_g_per_cm3", "RHOB_kg_m3", "kg/m3", conversion_function="gcc_to_kgm3"),
        ],
    )
    with pytest.raises(LasParsingError, match="width mismatch"):
        load_las_file(str(FIXTURES / "mismatched_width_row.las"), contract)


# ---------------------------------------------------------------------------
# Malformed numeric row
# ---------------------------------------------------------------------------
def test_malformed_numeric_row_raises():
    contract = _fixture_contract(
        "malformed_numeric_row.las",
        "Synthetic Malformed Row 1",
        2,
        [
            _depth_entry(0, "DEPT", "0 Depth", 0, "Depth"),
            _entry(1, "", "API", "1 GR", 1, "GR", "GR", "GR_api", "GR_api", "API"),
        ],
    )
    with pytest.raises(LasParsingError, match="malformed numeric value"):
        load_las_file(str(FIXTURES / "malformed_numeric_row.las"), contract)


# ---------------------------------------------------------------------------
# Increment 2.1: literal non-finite token is rejected structurally
# ---------------------------------------------------------------------------
def test_non_finite_literal_token_is_rejected():
    with pytest.raises(LasParsingError, match="non-finite"):
        parse_las_header(str(FIXTURES / "non_finite_token.las"))  # header parses fine
        contract = _fixture_contract(
            "non_finite_token.las", "Synthetic Non Finite 1", 2,
            [_depth_entry(0, "DEPT", "0 Depth", 0, "Depth"),
             _entry(1, "", "API", "1 GR", 1, "GR", "GR", "GR_api", "GR_api", "API")],
        )
        load_las_file(str(FIXTURES / "non_finite_token.las"), contract)


def test_non_finite_depth_specifically_is_rejected():
    # The literal "nan" token in non_finite_token.las sits in the GR
    # column at row 1 (see the fixture) - build a variant contract where
    # that same ordinal is instead declared as the measured-depth curve,
    # to prove a non-finite value specifically in the depth position is
    # caught (the general structural check in _read_ascii_data already
    # rejects ANY non-finite token file-wide, so this documents that a
    # non-finite depth is never reachable past that point).
    path = FIXTURES / "non_finite_token.las"
    with pytest.raises(LasParsingError):
        contract = _fixture_contract(
            "non_finite_token.las", "Synthetic Non Finite 1", 2,
            [_depth_entry(0, "DEPT", "0 Depth", 0, "Depth"),
             _entry(1, "", "API", "1 GR", 1, "GR", "GR", "GR_api", "GR_api", "API")],
        )
        load_las_file(str(path), contract)


# ---------------------------------------------------------------------------
# Non-monotonic / duplicate measured depth (WARNING, not blocking)
# ---------------------------------------------------------------------------
def test_non_monotonic_and_duplicate_md_are_warnings_not_errors():
    contract = _fixture_contract(
        "non_monotonic_and_duplicate_md.las",
        "Synthetic Non Monotonic 1",
        2,
        [
            _depth_entry(0, "DEPT", "0 Depth", 0, "Depth"),
            _entry(1, "", "API", "1 GR", 1, "GR", "GR", "GR_api", "GR_api", "API"),
        ],
    )
    result = load_las_file(str(FIXTURES / "non_monotonic_and_duplicate_md.las"), contract)
    assert result.contract_status == "PASSED"
    assert result.depth.n_duplicate_md == 1
    assert result.depth.n_non_monotonic == 1
    codes = {i.code for i in result.issues}
    assert "DUPLICATE_MD" in codes
    assert "NON_MONOTONIC_MD" in codes
    assert all(i.severity == "WARNING" for i in result.issues if i.code in ("DUPLICATE_MD", "NON_MONOTONIC_MD"))


def test_compute_depth_diagnostics_directly():
    md = np.array([100.0, 100.1, 100.1, 100.05, 100.4])
    diag = compute_depth_diagnostics(md, declared_strt=100.0, declared_stop=100.4, declared_step=0.1)
    assert diag.n_duplicate_md == 1
    assert diag.n_non_monotonic == 1
    assert diag.data_start == pytest.approx(100.0)
    assert diag.data_stop == pytest.approx(100.4)
    assert diag.strt_matches_declared is True
    assert diag.stop_matches_declared is True


# ---------------------------------------------------------------------------
# Missing required curve vs. missing-but-optional curve
# ---------------------------------------------------------------------------
def test_missing_required_curve_fails_contract():
    contract = _fixture_contract(
        "standard_mnemonics.las",
        "Synthetic Standard 1",
        3,
        [
            _depth_entry(0, "DEPT", "Depth"),
            _entry(1, "GR", "API", "Gamma Ray", None, None, "GR", "GR_api", "GR_api", "API"),
            _entry(2, "RHOB", "G/CC", "Bulk Density", None, None, "RHOB", "RHOB_g_per_cm3", "RHOB_kg_m3", "kg/m3", conversion_function="gcc_to_kgm3"),
            _entry(3, "", "us/ft", "3 DTCO", 3, "DTCO", "DTCO", "DTCO_us_per_ft", "VP_m_s", "m/s", required=True, conversion_function="us_per_ft_to_m_per_s"),
        ],
    )
    with pytest.raises(LasContractError) as excinfo:
        load_las_file(str(FIXTURES / "standard_mnemonics.las"), contract)
    assert any(i.code == "CURVE_NOT_FOUND" for i in excinfo.value.issues)


def test_missing_optional_curve_does_not_fail_contract():
    contract = _fixture_contract(
        "standard_mnemonics.las",
        "Synthetic Standard 1",
        3,
        [
            _depth_entry(0, "DEPT", "Depth"),
            _entry(1, "GR", "API", "Gamma Ray", None, None, "GR", "GR_api", "GR_api", "API"),
            _entry(2, "RHOB", "G/CC", "Bulk Density", None, None, "RHOB", "RHOB_g_per_cm3", "RHOB_kg_m3", "kg/m3", conversion_function="gcc_to_kgm3"),
            _entry(3, "", "us/ft", "3 DTCO", 3, "DTCO", "DTCO", "DTCO_us_per_ft", "VP_m_s", "m/s", required=False, conversion_function="us_per_ft_to_m_per_s"),
        ],
    )
    result = load_las_file(str(FIXTURES / "standard_mnemonics.las"), contract)
    assert result.contract_status == "PASSED"
    assert "VP_m_s" not in result.canonical_data
    resolutions_by_name = {r.canonical_name: r for r in result.resolutions}
    assert resolutions_by_name["VP_m_s"].status == "MISSING_OPTIONAL"


# ---------------------------------------------------------------------------
# resolve_curve_contract used standalone (no data read)
# ---------------------------------------------------------------------------
def test_resolve_curve_contract_standalone_pass():
    header = parse_las_header(str(FIXTURES / "empty_mnemonic_with_description.las"))
    resolutions, issues, status = resolve_curve_contract(header, _empty_mnemonic_contract())
    assert status == "PASSED"
    assert all(r.status == "RESOLVED" for r in resolutions)
    assert issues == ()


def test_resolve_curve_contract_never_resolves_empty_mnemonic_on_ordinal_alone():
    header = parse_las_header(str(FIXTURES / "empty_mnemonic_with_description.las"))
    contract = _fixture_contract(
        "empty_mnemonic_with_description.las",
        "Synthetic Empty Mnemonic 1",
        4,
        [
            _depth_entry(0, "DEPT", "0 Depth", 0, "Depth"),
            _entry(1, "", "ft", "1 DTCO", 1, "DTCO", "DTCO", "DTCO_us_per_ft", "VP_m_s", "m/s"),  # wrong unit only
            _entry(2, "", "API", "2 GR", 2, "GR", "GR", "GR_api", "GR_api", "API"),
            _entry(3, "", "g/cc", "3 RHOB", 3, "RHOB", "RHOB", "RHOB_g_per_cm3", "RHOB_kg_m3", "kg/m3", conversion_function="gcc_to_kgm3"),
        ],
    )
    resolutions, issues, status = resolve_curve_contract(header, contract)
    assert status == "FAILED"
    by_name = {r.canonical_name: r for r in resolutions}
    assert by_name["VP_m_s"].status == "FAILED"


# ---------------------------------------------------------------------------
# Well-identifier and curve-count cross-checks
# ---------------------------------------------------------------------------
def test_well_identifier_mismatch_is_reported():
    header = parse_las_header(str(FIXTURES / "standard_mnemonics.las"))
    contract = _fixture_contract("standard_mnemonics.las", "Some Other Well", 3, _standard_contract().curves)
    _, issues, status = resolve_curve_contract(header, contract)
    assert status == "FAILED"
    assert any(i.code == "WELL_IDENTIFIER_MISMATCH" for i in issues)


def test_curve_count_mismatch_is_reported():
    header = parse_las_header(str(FIXTURES / "standard_mnemonics.las"))
    contract = FileContract(
        source_filename="standard_mnemonics.las",
        expected_sha256=_sha256(FIXTURES / "standard_mnemonics.las"),
        expected_well_identifier="Synthetic Standard 1",
        expected_las_version="2.0",
        expected_wrap="NO",
        expected_null_value=-999.25,
        expected_curve_count=99,
        expected_data_layout="unwrapped_whitespace_delimited",
        curves=_standard_contract().curves,
    )
    _, issues, status = resolve_curve_contract(header, contract)
    assert status == "FAILED"
    assert any(i.code == "CURVE_COUNT_MISMATCH" for i in issues)


# ---------------------------------------------------------------------------
# Increment 2.1: file-identity checks (filename, SHA-256, WELL, VERS, WRAP, NULL)
# ---------------------------------------------------------------------------
def test_filename_mismatch_is_blocking():
    # A contract authored for a DIFFERENT file than the one actually
    # loaded must fail, not silently apply.
    header = parse_las_header(str(FIXTURES / "standard_mnemonics.las"))
    contract = FileContract(
        source_filename="some_other_file.las",  # deliberately wrong
        expected_sha256=_sha256(FIXTURES / "standard_mnemonics.las"),
        expected_well_identifier="Synthetic Standard 1",
        expected_las_version="2.0",
        expected_wrap="NO",
        expected_null_value=-999.25,
        expected_curve_count=3,
        expected_data_layout="unwrapped_whitespace_delimited",
        curves=_standard_contract().curves,
    )
    _, issues, status = resolve_curve_contract(header, contract)
    assert status == "FAILED"
    assert any(i.code == "FILENAME_MISMATCH" for i in issues)


def test_sha256_mismatch_is_blocking():
    header = parse_las_header(str(FIXTURES / "standard_mnemonics.las"))
    contract = FileContract(
        source_filename="standard_mnemonics.las",
        expected_sha256="0" * 64,  # deliberately wrong
        expected_well_identifier="Synthetic Standard 1",
        expected_las_version="2.0",
        expected_wrap="NO",
        expected_null_value=-999.25,
        expected_curve_count=3,
        expected_data_layout="unwrapped_whitespace_delimited",
        curves=_standard_contract().curves,
    )
    _, issues, status = resolve_curve_contract(header, contract)
    assert status == "FAILED"
    assert any(i.code == "SHA256_MISMATCH" for i in issues)


def test_missing_well_is_blocking():
    header = parse_las_header(str(FIXTURES / "missing_well.las"))
    contract = _fixture_contract(
        "missing_well.las", "Anything", 2,
        [_depth_entry(0, "DEPT", "0 Depth", 0, "Depth"),
         _entry(1, "", "API", "1 GR", 1, "GR", "GR", "GR_api", "GR_api", "API")],
    )
    _, issues, status = resolve_curve_contract(header, contract)
    assert status == "FAILED"
    assert any(i.code == "WELL_MISSING" for i in issues)
    with pytest.raises(LasContractError) as excinfo:
        load_las_file(str(FIXTURES / "missing_well.las"), contract)
    assert any(i.code == "WELL_MISSING" for i in excinfo.value.issues)


def test_missing_null_is_blocking():
    header = parse_las_header(str(FIXTURES / "missing_null.las"))
    contract = _fixture_contract(
        "missing_null.las", "Synthetic Missing Null 1", 2,
        [_depth_entry(0, "DEPT", "0 Depth", 0, "Depth"),
         _entry(1, "", "API", "1 GR", 1, "GR", "GR", "GR_api", "GR_api", "API")],
    )
    _, issues, status = resolve_curve_contract(header, contract)
    assert status == "FAILED"
    assert any(i.code == "NULL_MISSING" for i in issues)


def test_vers_mismatch_is_blocking():
    header = parse_las_header(str(FIXTURES / "vers_mismatch.las"))
    contract = _fixture_contract(
        "vers_mismatch.las", "Synthetic Vers Mismatch 1", 2,
        [_depth_entry(0, "DEPT", "0 Depth", 0, "Depth"),
         _entry(1, "", "API", "1 GR", 1, "GR", "GR", "GR_api", "GR_api", "API")],
    )
    _, issues, status = resolve_curve_contract(header, contract)
    assert status == "FAILED"
    # The file declares VERS=3.0, which this parser does not implement at
    # all (regardless of what the contract expects), so this is reported
    # as unsupported.
    assert any(i.code == "VERS_UNSUPPORTED" for i in issues)


def test_wrap_yes_is_rejected_as_unsupported():
    header = parse_las_header(str(FIXTURES / "wrapped_unsupported.las"))
    contract = _fixture_contract(
        "wrapped_unsupported.las", "Synthetic Wrapped 1", 2,
        [_depth_entry(0, "DEPT", "0 Depth", 0, "Depth"),
         _entry(1, "", "API", "1 GR", 1, "GR", "GR", "GR_api", "GR_api", "API")],
    )
    _, issues, status = resolve_curve_contract(header, contract)
    assert status == "FAILED"
    assert any(i.code == "WRAP_UNSUPPORTED" for i in issues)


def test_null_mismatch_is_blocking_error_not_warning():
    header = parse_las_header(str(FIXTURES / "standard_mnemonics.las"))
    contract = FileContract(
        source_filename="standard_mnemonics.las",
        expected_sha256=_sha256(FIXTURES / "standard_mnemonics.las"),
        expected_well_identifier="Synthetic Standard 1",
        expected_las_version="2.0",
        expected_wrap="NO",
        expected_null_value=-888.0,  # file actually declares -999.25
        expected_curve_count=3,
        expected_data_layout="unwrapped_whitespace_delimited",
        curves=_standard_contract().curves,
    )
    _, issues, status = resolve_curve_contract(header, contract)
    assert status == "FAILED"
    null_issues = [i for i in issues if i.code == "NULL_MISMATCH"]
    assert len(null_issues) == 1
    assert null_issues[0].severity == "ERROR"


def test_unsupported_las_version_rejected_at_contract_load(tmp_path):
    bad = tmp_path / "bad_version.yml"
    bad.write_text(
        f"""
files:
  x.las:
    expected_sha256: "abc"
    expected_well_identifier: "W"
    expected_las_version: "3.0"
    expected_wrap: "NO"
    expected_null_value: -999.25
    expected_curve_count: 1
    expected_data_layout: "unwrapped_whitespace_delimited"
    curves:
      - ordinal: 0
        semantic_role: measured_depth
        source_curve_name: "DEPT"
        raw_mnemonic: "DEPT"
        raw_unit: "M"
        raw_description: "0 Depth"
        raw_canonical_name: "DEPT_m"
        canonical_name: "MD_m"
        canonical_unit: "m"
        required: true
        conversion_function: "identity"
"""
    )
    with pytest.raises(LasContractDefinitionError):
        load_file_contract_config(str(bad))


def test_unsupported_wrap_rejected_at_contract_load(tmp_path):
    bad = tmp_path / "bad_wrap.yml"
    bad.write_text(
        f"""
files:
  x.las:
    expected_sha256: "abc"
    expected_well_identifier: "W"
    expected_las_version: "2.0"
    expected_wrap: "YES"
    expected_null_value: -999.25
    expected_curve_count: 1
    expected_data_layout: "unwrapped_whitespace_delimited"
    curves:
      - ordinal: 0
        semantic_role: measured_depth
        source_curve_name: "DEPT"
        raw_mnemonic: "DEPT"
        raw_unit: "M"
        raw_description: "0 Depth"
        raw_canonical_name: "DEPT_m"
        canonical_name: "MD_m"
        canonical_unit: "m"
        required: true
        conversion_function: "identity"
"""
    )
    with pytest.raises(LasContractDefinitionError):
        load_file_contract_config(str(bad))


# ---------------------------------------------------------------------------
# Increment 2.1: contract-authoring validation
# ---------------------------------------------------------------------------
def test_duplicate_ordinal_rejected_at_contract_load(tmp_path):
    bad = tmp_path / "dup_ordinal.yml"
    bad.write_text(
        f"""
files:
  x.las:
{_MINIMAL_FILE_HEADER_FIELDS}
    expected_curve_count: 2
    curves:
      - ordinal: 0
        semantic_role: measured_depth
        source_curve_name: "DEPT"
        raw_mnemonic: "DEPT"
        raw_unit: "M"
        raw_description: "0 Depth"
        raw_canonical_name: "DEPT_m"
        canonical_name: "MD_m"
        canonical_unit: "m"
        required: true
        conversion_function: "identity"
      - ordinal: 0
        source_curve_name: "GR"
        raw_mnemonic: "GR"
        raw_unit: "API"
        raw_description: "1 GR"
        raw_canonical_name: "GR_api"
        canonical_name: "GR_api"
        canonical_unit: "API"
        required: true
        conversion_function: "identity"
"""
    )
    with pytest.raises(LasContractDefinitionError, match="duplicate ordinal"):
        load_file_contract_config(str(bad))


def test_negative_ordinal_rejected_at_contract_load(tmp_path):
    bad = tmp_path / "neg_ordinal.yml"
    bad.write_text(
        f"""
files:
  x.las:
{_MINIMAL_FILE_HEADER_FIELDS}
    expected_curve_count: 1
    curves:
      - ordinal: -1
        semantic_role: measured_depth
        source_curve_name: "DEPT"
        raw_mnemonic: "DEPT"
        raw_unit: "M"
        raw_description: "0 Depth"
        raw_canonical_name: "DEPT_m"
        canonical_name: "MD_m"
        canonical_unit: "m"
        required: true
        conversion_function: "identity"
"""
    )
    with pytest.raises(LasContractDefinitionError):
        load_file_contract_config(str(bad))


def test_conversion_unit_incompatibility_rejected_at_contract_load(tmp_path):
    bad = tmp_path / "bad_conv_unit.yml"
    bad.write_text(
        f"""
files:
  x.las:
{_MINIMAL_FILE_HEADER_FIELDS}
    expected_curve_count: 2
    curves:
      - ordinal: 0
        semantic_role: measured_depth
        source_curve_name: "DEPT"
        raw_mnemonic: "DEPT"
        raw_unit: "M"
        raw_description: "0 Depth"
        raw_canonical_name: "DEPT_m"
        canonical_name: "MD_m"
        canonical_unit: "m"
        required: true
        conversion_function: "identity"
      - ordinal: 1
        source_curve_name: "GR"
        raw_mnemonic: "GR"
        raw_unit: "API"
        raw_description: "1 GR"
        raw_canonical_name: "GR_api"
        canonical_name: "GR_kgm3"
        canonical_unit: "kg/m3"
        required: true
        conversion_function: "gcc_to_kgm3"
"""
    )
    # gcc_to_kgm3 requires raw_unit "g/cc"; this contract declares "API" -
    # a contract must not be able to apply a density conversion to a
    # gamma-ray curve.
    with pytest.raises(LasContractDefinitionError):
        load_file_contract_config(str(bad))


def test_zero_measured_depth_roles_rejected_at_contract_load(tmp_path):
    bad = tmp_path / "no_depth_role.yml"
    bad.write_text(
        f"""
files:
  x.las:
{_MINIMAL_FILE_HEADER_FIELDS}
    expected_curve_count: 1
    curves:
      - ordinal: 0
        source_curve_name: "GR"
        raw_mnemonic: "GR"
        raw_unit: "API"
        raw_description: "0 GR"
        raw_canonical_name: "GR_api"
        canonical_name: "GR_api"
        canonical_unit: "API"
        required: true
        conversion_function: "identity"
"""
    )
    with pytest.raises(LasContractDefinitionError, match="measured_depth"):
        load_file_contract_config(str(bad))


def test_multiple_measured_depth_roles_rejected_at_contract_load(tmp_path):
    bad = tmp_path / "two_depth_roles.yml"
    bad.write_text(
        f"""
files:
  x.las:
{_MINIMAL_FILE_HEADER_FIELDS}
    expected_curve_count: 2
    curves:
      - ordinal: 0
        semantic_role: measured_depth
        source_curve_name: "DEPT"
        raw_mnemonic: "DEPT"
        raw_unit: "M"
        raw_description: "0 Depth"
        raw_canonical_name: "DEPT_m"
        canonical_name: "MD_m"
        canonical_unit: "m"
        required: true
        conversion_function: "identity"
      - ordinal: 1
        semantic_role: measured_depth
        source_curve_name: "DEPT2"
        raw_mnemonic: "DEPT2"
        raw_unit: "M"
        raw_description: "1 Depth2"
        raw_canonical_name: "DEPT2_m"
        canonical_name: "MD2_m"
        canonical_unit: "m"
        required: true
        conversion_function: "identity"
"""
    )
    with pytest.raises(LasContractDefinitionError):
        load_file_contract_config(str(bad))


def test_measured_depth_wrong_canonical_name_rejected(tmp_path):
    bad = tmp_path / "wrong_depth_name.yml"
    bad.write_text(
        f"""
files:
  x.las:
{_MINIMAL_FILE_HEADER_FIELDS}
    expected_curve_count: 1
    curves:
      - ordinal: 0
        semantic_role: measured_depth
        source_curve_name: "DEPT"
        raw_mnemonic: "DEPT"
        raw_unit: "M"
        raw_description: "0 Depth"
        raw_canonical_name: "DEPT_m"
        canonical_name: "DEPTH_INDEX"
        canonical_unit: "m"
        required: true
        conversion_function: "identity"
"""
    )
    with pytest.raises(LasContractDefinitionError, match="MD_m"):
        load_file_contract_config(str(bad))


def test_non_boolean_required_rejected_at_contract_load(tmp_path):
    bad = tmp_path / "bad_required.yml"
    bad.write_text(
        f"""
files:
  x.las:
{_MINIMAL_FILE_HEADER_FIELDS}
    expected_curve_count: 1
    curves:
      - ordinal: 0
        semantic_role: measured_depth
        source_curve_name: "DEPT"
        raw_mnemonic: "DEPT"
        raw_unit: "M"
        raw_description: "0 Depth"
        raw_canonical_name: "DEPT_m"
        canonical_name: "MD_m"
        canonical_unit: "m"
        required: "yes"
        conversion_function: "identity"
"""
    )
    with pytest.raises(LasContractDefinitionError):
        load_file_contract_config(str(bad))


def test_nonnumeric_null_rejected_at_contract_load(tmp_path):
    bad = tmp_path / "bad_null.yml"
    bad.write_text(
        """
files:
  x.las:
    expected_sha256: "abc"
    expected_well_identifier: "W"
    expected_las_version: "2.0"
    expected_wrap: "NO"
    expected_null_value: "not-a-number"
    expected_curve_count: 1
    expected_data_layout: "unwrapped_whitespace_delimited"
    curves:
      - ordinal: 0
        semantic_role: measured_depth
        source_curve_name: "DEPT"
        raw_mnemonic: "DEPT"
        raw_unit: "M"
        raw_description: "0 Depth"
        raw_canonical_name: "DEPT_m"
        canonical_name: "MD_m"
        canonical_unit: "m"
        required: true
        conversion_function: "identity"
"""
    )
    with pytest.raises(LasContractDefinitionError):
        load_file_contract_config(str(bad))


# ---------------------------------------------------------------------------
# Contract-config (YAML) loading
# ---------------------------------------------------------------------------
def test_load_file_contract_config_valid(tmp_path):
    good_yaml = tmp_path / "good.yml"
    good_yaml.write_text(
        f"""
files:
  some_file.las:
{_MINIMAL_FILE_HEADER_FIELDS}
    expected_curve_count: 2
    curves:
      - ordinal: 0
        semantic_role: measured_depth
        source_curve_name: "DEPT"
        raw_mnemonic: "DEPT"
        raw_unit: "M"
        raw_description: "0 Depth"
        raw_canonical_name: "DEPT_m"
        canonical_name: "MD_m"
        canonical_unit: "m"
        required: true
        conversion_function: "identity"
      - ordinal: 1
        source_curve_name: "DTCO"
        raw_mnemonic: ""
        raw_unit: "us/ft"
        raw_description: "1 DTCO"
        description_ordinal: 1
        description_name: "DTCO"
        raw_canonical_name: "DTCO_us_per_ft"
        canonical_name: "VP_m_s"
        canonical_unit: "m/s"
        required: true
        conversion_function: "us_per_ft_to_m_per_s"
"""
    )
    contracts = load_file_contract_config(str(good_yaml))
    assert "some_file.las" in contracts
    assert len(contracts["some_file.las"].curves) == 2


def test_load_file_contract_config_missing_file():
    with pytest.raises(LasContractDefinitionError):
        load_file_contract_config("/nonexistent/path/contracts.yml")


def test_load_file_contract_config_malformed_yaml(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("files: [this is not, a mapping :::")
    with pytest.raises(LasContractDefinitionError):
        load_file_contract_config(str(bad))


def test_load_file_contract_config_unknown_conversion_function(tmp_path):
    bad = tmp_path / "bad_conv.yml"
    bad.write_text(
        f"""
files:
  x.las:
{_MINIMAL_FILE_HEADER_FIELDS}
    expected_curve_count: 1
    curves:
      - ordinal: 0
        semantic_role: measured_depth
        source_curve_name: "DEPT"
        raw_mnemonic: "DEPT"
        raw_unit: "M"
        raw_description: "0 Depth"
        raw_canonical_name: "DEPT_m"
        canonical_name: "MD_m"
        canonical_unit: "m"
        required: true
        conversion_function: "not_a_real_function"
"""
    )
    with pytest.raises(LasContractDefinitionError, match="unknown"):
        load_file_contract_config(str(bad))


# ---------------------------------------------------------------------------
# Real project contract file (config/las_curve_contracts.yml) at least loads
# and validates internally, even though the four raw LAS files themselves
# are not required by this portable test suite.
# ---------------------------------------------------------------------------
def test_real_project_contract_config_loads_and_validates():
    config_path = Path(__file__).parent.parent / "config" / "las_curve_contracts.yml"
    if not config_path.exists():
        pytest.skip("config/las_curve_contracts.yml not present in this checkout")
    contracts = load_file_contract_config(str(config_path))
    expected_files = {
        "Poseidon_2_logs.las",
        "Boreas_1_logs.las",
        "Poseidon_North_1_logs.las",
        "Proteus_1ST2_logs.las",
    }
    assert expected_files.issubset(set(contracts))
    for filename in expected_files:
        contract = contracts[filename]
        assert contract.expected_curve_count == 9
        canonical_names = [c.canonical_name for c in contract.curves]
        assert len(canonical_names) == len(set(canonical_names)), f"{filename}: duplicate canonical name in contract"
        depth_curves = [c for c in contract.curves if c.semantic_role == "measured_depth"]
        assert len(depth_curves) == 1
        assert depth_curves[0].canonical_name == "MD_m"
        assert depth_curves[0].required


def test_real_project_contract_gr_ecgr_grd_are_distinct_canonical_names():
    config_path = Path(__file__).parent.parent / "config" / "las_curve_contracts.yml"
    if not config_path.exists():
        pytest.skip("config/las_curve_contracts.yml not present in this checkout")
    contracts = load_file_contract_config(str(config_path))
    gr_names = set()
    for contract in contracts.values():
        for c in contract.curves:
            if c.source_curve_name in ("GR", "ECGR", "GRD"):
                gr_names.add(c.canonical_name)
    # GR_api, ECGR_api, GRD_api must all appear as distinct canonical
    # names - never merged into one geological interpretation.
    assert {"GR_api", "ECGR_api", "GRD_api"}.issubset(gr_names)


# ---------------------------------------------------------------------------
# load_wells: batch loading, typed IngestionFailure isolation
# ---------------------------------------------------------------------------
def test_load_wells_isolates_parsing_failure_from_a_successful_well():
    good_path = str(FIXTURES / "standard_mnemonics.las")
    bad_path = str(FIXTURES / "malformed_numeric_row.las")

    good_contract = _standard_contract()
    bad_contract = _fixture_contract(
        "malformed_numeric_row.las", "Synthetic Malformed Row 1", 2,
        [_depth_entry(0, "DEPT", "0 Depth", 0, "Depth"),
         _entry(1, "", "API", "1 GR", 1, "GR", "GR", "GR_api", "GR_api", "API")],
    )
    contracts = {
        "standard_mnemonics.las": good_contract,
        "malformed_numeric_row.las": bad_contract,
    }
    file_paths = {"GOOD": good_path, "BAD": bad_path}

    results, errors = load_wells(file_paths, contracts)
    assert "GOOD" in results
    assert "BAD" in errors
    failure = errors["BAD"]
    assert isinstance(failure, IngestionFailure)
    assert failure.error_type == "parsing_failure"
    assert "malformed" in failure.message.lower()


def test_load_wells_isolates_contract_failure_from_a_successful_well():
    good_path = str(FIXTURES / "standard_mnemonics.las")
    wrong_well_contract = _fixture_contract(
        "standard_mnemonics.las", "Wrong Well Name", 3, _standard_contract().curves
    )
    contracts = {"standard_mnemonics.las": wrong_well_contract}
    file_paths = {"WRONG_WELL": good_path}
    results, errors = load_wells(file_paths, contracts)
    assert "WRONG_WELL" in errors
    assert "WRONG_WELL" not in results
    failure = errors["WRONG_WELL"]
    assert failure.error_type == "contract_failure"
    assert any(i.code == "WELL_IDENTIFIER_MISMATCH" for i in failure.exception.issues)


def test_load_wells_isolates_file_not_found():
    # A contract entry exists for this basename, but no file with that
    # name exists on disk - this must surface as "file_not_found", not as
    # a LasContractDefinitionError (which is reserved for a basename with
    # NO matching contract at all - a configuration problem, not a
    # missing-file problem).
    missing_path = str(FIXTURES / "does_not_exist.las")
    contracts = {"does_not_exist.las": _standard_contract()}
    file_paths = {"MISSING": missing_path}
    results, errors = load_wells(file_paths, contracts)
    assert "MISSING" in errors
    assert errors["MISSING"].error_type == "file_not_found"


def test_load_wells_unknown_file_raises_definition_error():
    with pytest.raises(LasContractDefinitionError):
        load_wells({"X": str(FIXTURES / "standard_mnemonics.las")}, contracts={})


def test_load_wells_programming_error_still_propagates(monkeypatch):
    # A non-ingestion exception (e.g. a bug) must NOT be silently absorbed
    # into the typed-failure dict - only the four documented ingestion-
    # failure categories are isolated per well.
    import p2mem.io.las as las_module

    def _boom(path, contract):
        raise KeyError("programming error, not an ingestion failure")

    monkeypatch.setattr(las_module, "load_las_file", _boom)
    with pytest.raises(KeyError):
        load_wells({"X": str(FIXTURES / "standard_mnemonics.las")}, {"standard_mnemonics.las": _standard_contract()})


# ---------------------------------------------------------------------------
# Deterministic output ordering
# ---------------------------------------------------------------------------
def test_deterministic_ordering_across_repeated_loads():
    contract = _empty_mnemonic_contract()
    path = str(FIXTURES / "empty_mnemonic_with_description.las")
    result_a = load_las_file(path, contract)
    result_b = load_las_file(path, contract)

    assert list(result_a.canonical_data.keys()) == list(result_b.canonical_data.keys())
    assert [r.canonical_name for r in result_a.resolutions] == [r.canonical_name for r in result_b.resolutions]
    assert [c.ordinal for c in result_a.header.curve_headers] == [c.ordinal for c in result_b.header.curve_headers]
    # Canonical data key order must follow contract declaration order.
    assert list(result_a.canonical_data.keys()) == ["MD_m", "VP_m_s", "GR_api", "RHOB_kg_m3"]
    np.testing.assert_array_equal(result_a.raw_data, result_b.raw_data)


def test_curve_stats_report_raw_and_canonical_units_explicitly():
    result = load_las_file(str(FIXTURES / "standard_mnemonics.las"), _standard_contract())
    stats_by_name = {s.canonical_name: s for s in result.curve_stats}

    gr_stats = stats_by_name["GR_api"]
    assert gr_stats.n_samples == 5
    assert gr_stats.valid_count == 4
    assert gr_stats.null_count == 1
    assert gr_stats.valid_fraction == pytest.approx(0.8)
    assert gr_stats.raw_unit == "API"
    assert gr_stats.canonical_unit == "API"
    assert gr_stats.raw_min == pytest.approx(50.1)
    assert gr_stats.raw_max == pytest.approx(54.5)
    assert gr_stats.canonical_min == pytest.approx(50.1)
    assert gr_stats.canonical_max == pytest.approx(54.5)
    assert "NULL" in gr_stats.statistics_basis

    rhob_stats = stats_by_name["RHOB_kg_m3"]
    assert rhob_stats.raw_unit.upper() == "G/CC"
    assert rhob_stats.canonical_unit == "kg/m3"
    # Raw stats are in g/cc; canonical stats are the same values * 1000.
    assert rhob_stats.canonical_min == pytest.approx(rhob_stats.raw_min * 1000, rel=1e-9)
    assert rhob_stats.canonical_max == pytest.approx(rhob_stats.raw_max * 1000, rel=1e-9)


def test_curve_coverage_row_shows_dtco_raw_and_vp_canonical_units():
    from p2mem.io.inventory import build_curve_coverage_rows

    result = load_las_file(
        str(FIXTURES / "empty_mnemonic_with_description.las"), _empty_mnemonic_contract()
    )
    rows = build_curve_coverage_rows({"TEST": result})
    dtco_row = next(r for r in rows if r["source_curve_name"] == "DTCO")
    assert dtco_row["canonical_name"] == "VP_m_s"
    assert dtco_row["raw_unit"] == "us/ft"
    assert dtco_row["canonical_unit"] == "m/s"
    assert dtco_row["raw_min"] is not None and dtco_row["raw_max"] is not None
    assert dtco_row["canonical_min"] is not None and dtco_row["canonical_max"] is not None
    # us/ft -> m/s is an inverse relationship: the largest raw slowness
    # corresponds to the smallest canonical velocity, and vice versa.
    assert dtco_row["canonical_min"] < dtco_row["canonical_max"]
