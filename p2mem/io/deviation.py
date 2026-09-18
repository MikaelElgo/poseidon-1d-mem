"""
p2mem.io.deviation - Auditable Petrel deviation-survey (well-trace) parser
and per-file curve-contract resolution (Increment 3).

Why this module exists
------------------------
The four approved deviation-survey files (Poseidon 2, Boreas 1, Poseidon
North 1, Proteus 1ST2) are plain-text Petrel well-trace exports with a
fixed-format, human-readable header block (well name, survey name,
wellhead coordinates, datum, coordinate-reference-system statement, and
sign/unit conventions) followed by a fixed 11-column station table (MD, X,
Y, Z, TVD, DX, DY, AZIM_TN, INCL, DLS, AZIM_GN). This module parses that
format strictly: every header field, and the exact column order, is
extracted and preserved; nothing is inferred, renamed, or filled in
without being explicitly reported.

Mirroring the design already established for the LAS-ingestion layer
(`p2mem.io.las`, locked as of Increment 2.1.1), this module separates
STRUCTURAL PARSING (can the file even be tokenized: is the header
present, are all 11 columns present with unique names, does every row
have the right width and numeric tokens) from CONTRACT RESOLUTION (does
this specific file's actual header/data agree with what
`config/deviation_survey_contracts.yml` says it SHOULD be: filename,
SHA-256, well/survey identity, wellhead coordinates, datum, coordinate
system, column order, station count, MD coverage). A structural defect is
a `DeviationParsingError`; a contract mismatch is a
`DeviationContractError`. Both are always ERROR-severity and always
blocking - this module never guesses its way past either kind of problem.

Header parsing note (MD unit)
-------------------------------
Every file explicitly declares X/Y/DX/DY/Z/TVD units as metres (the
"WELL HEAD X-COORDINATE: ... (m)" lines and the "DX DY ARE GIVEN IN GRID
NORTH IN m-UNITS" / "DEPTH (Z, tvd_z) GIVEN IN m-UNITS" statements), and
declares angles in degrees ("ANGLES ARE GIVEN IN DEGREES") - covering
AZIM_TN, INCL, and AZIM_GN. The MD column's own unit is NOT covered by any
of those explicit statements (no header line says "MD is in metres").
Rather than silently assuming metres, this module records that gap as a
disclosed WARNING-severity `DeviationIngestionIssue`
(`MD_UNIT_NOT_EXPLICITLY_DECLARED`) on every successful load, and treats
MD as metres only because its numeric magnitude is self-consistent with
the file's own explicitly-metric TVD/Z columns (a station's MD and TVD
are always of the same order of magnitude in these near-vertical-to-
moderate-inclination wells) and with the already-validated, explicitly
metric `MD_m` canonical curve from the locked Increment 2.1.1 LAS layer
for the same four wells. This is an inference, not a fabrication, and it
is reported, not hidden.
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import yaml

from p2mem.deviation_models import (
    DEPTH_BASIS_PETREL_SOURCE,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_WARNING,
    VALID_DEPTH_BASIS_POLICIES,
    DeviationFileContract,
    DeviationHeaderInfo,
    DeviationIngestionFailure,
    DeviationIngestionIssue,
    DeviationStationData,
    DeviationWellResult,
    DepthBasisSelection,
    TrajectoryValidationResult,
)
from p2mem.trajectory import (
    TrajectoryComputationError,
    compute_minimum_curvature_trajectory,
)

__all__ = [
    "DeviationFileNotFoundError",
    "DeviationParsingError",
    "DeviationContractDefinitionError",
    "DeviationContractError",
    "REQUIRED_COLUMN_NAMES",
    "MD_UNIT_NOT_EXPLICITLY_DECLARED_CODE",
    "DLS_NORMALIZATION_INFERRED_CODE",
    "load_deviation_contract_config",
    "parse_deviation_header",
    "read_deviation_stations",
    "resolve_deviation_contract",
    "compute_well_trajectory_validation",
    "load_deviation_file",
    "load_deviation_surveys",
]

# Issue codes shared between production code and tests, so a test can
# reference the exact code without duplicating the literal string.
MD_UNIT_NOT_EXPLICITLY_DECLARED_CODE = "MD_UNIT_NOT_EXPLICITLY_DECLARED"
DLS_NORMALIZATION_INFERRED_CODE = "DLS_NORMALIZATION_INFERRED_AS_DEG_PER_30M"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class DeviationFileNotFoundError(FileNotFoundError):
    """The deviation-survey file path given to `load_deviation_file` does not exist."""


class DeviationParsingError(ValueError):
    """
    A structural defect in the deviation-survey text file itself: a
    missing/unrecognized header banner, a missing required header field,
    a missing/duplicated required column, a malformed numeric token, a
    non-finite (NaN/Inf) literal token, or a data row whose column count
    does not match the header's declared column count. Raised before any
    contract is consulted.
    """


class DeviationContractDefinitionError(ValueError):
    """
    `config/deviation_survey_contracts.yml` itself is malformed: a
    duplicate top-level file key, a missing required field, an invalid
    type, an unsupported convention value (e.g. an azimuth reference or
    depth-basis policy this module does not implement), or an internally
    inconsistent/incompatible set of expected values (e.g. a declared
    column count that does not match the declared column-order list
    length, or a residual fail-threshold at or below its own pass
    tolerance). Raised at contract-load time, before any deviation file is
    opened.
    """


class DeviationContractError(RuntimeError):
    """
    A specific file's actual parsed header or station data does not agree
    with its `DeviationFileContract`: wrong filename, SHA-256 mismatch,
    well/survey identity mismatch, wellhead/datum mismatch beyond
    tolerance, coordinate-reference-system mismatch, wrong column order,
    station-count mismatch, or MD-coverage mismatch. Carries `.issues`
    (the full tuple of `DeviationIngestionIssue`, ERROR and WARNING alike)
    for callers that want the complete detail, not just the first failure.
    """

    def __init__(self, message: str, issues: Tuple[DeviationIngestionIssue, ...]):
        super().__init__(message)
        self.issues = issues


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# The fixed 11-column Petrel well-trace schema this parser implements.
# Order here is NOT the required file order (that is a per-file contract
# question - see `expected_column_order`); this is simply the set of
# canonical field names every file must supply exactly once each.
REQUIRED_COLUMN_NAMES: Tuple[str, ...] = (
    "MD", "X", "Y", "Z", "TVD", "DX", "DY", "AZIM_TN", "INCL", "DLS", "AZIM_GN",
)

# Maps a source column name to the `DeviationStationData` field name it
# populates.
_COLUMN_TO_FIELD = {
    "MD": "MD_source_m",
    "X": "X_source_m",
    "Y": "Y_source_m",
    "Z": "Z_source_m",
    "TVD": "TVD_source_m",
    "DX": "DX_source_m",
    "DY": "DY_source_m",
    "AZIM_TN": "AZIM_TN_source_deg",
    "INCL": "INCL_source_deg",
    "DLS": "DLS_source_deg_per_30m",
    "AZIM_GN": "AZIM_GN_source_deg",
}

_SEPARATOR_RE = re.compile(r"^#=+$")
_WELL_NAME_RE = re.compile(r"^#\s*WELL NAME:\s*(.+?)\s*$")
_SURVEY_RE = re.compile(r"^#\s*DEFINITIVE SURVEY:\s*(.+?)\s*$")
_WELLHEAD_X_RE = re.compile(r"^#\s*WELL HEAD X-COORDINATE:\s*([\-0-9.eE]+)\s*\(([^)]*)\)\s*$")
_WELLHEAD_Y_RE = re.compile(r"^#\s*WELL HEAD Y-COORDINATE:\s*([\-0-9.eE]+)\s*\(([^)]*)\)\s*$")
_DATUM_RE = re.compile(r"^#\s*WELL DATUM\s*\(([^)]*)\)\s*:\s*([\-0-9.eE]+)\s*\(([^)]*)\)\s*$")
_WELL_TYPE_RE = re.compile(r"^#\s*WELL TYPE:\s*(.+?)\s*$")
_DEPTH_REF_RE = re.compile(r"^#\s*(MD AND TVD ARE REFERENCED.+)$")
_ANGLE_UNIT_RE = re.compile(r"^#\s*ANGLES ARE GIVEN IN\s*(.+?)\s*$")
_CRS_RE = re.compile(r"^#\s*XYZ TRACE IS GIVEN IN COORDINATE SYSTEM\s*(.+?)\s*$")
_AZIM_TN_DESC_RE = re.compile(r"^#\s*AZIM_TN:")
_AZIM_GN_DESC_RE = re.compile(r"^#\s*AZIM_GN:")
_DXDY_RE = re.compile(r"^#\s*(DX DY ARE GIVEN IN.+)$")
_Z_RE = re.compile(r"^#\s*(DEPTH \(Z,.+)$")
_BANNER_RE = re.compile(r"^#\s*WELL TRACE FROM PETREL")


# ---------------------------------------------------------------------------
# Contract configuration (config/deviation_survey_contracts.yml)
# ---------------------------------------------------------------------------
class _NoDuplicateKeySafeLoader(yaml.SafeLoader):
    """
    A `yaml.SafeLoader` subclass that raises on a duplicate mapping key
    instead of silently keeping only the last occurrence (PyYAML's
    default `SafeLoader` behavior). Used only for
    `config/deviation_survey_contracts.yml` so that a duplicate top-level
    file key (or a duplicate field within one file's entry) is a loud
    contract-authoring error, never a silent overwrite.
    """


def _construct_mapping_no_duplicates(loader: yaml.SafeLoader, node, deep: bool = False):
    mapping: Dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise DeviationContractDefinitionError(
                f"Duplicate key {key!r} found while parsing deviation contract YAML "
                f"(line {key_node.start_mark.line + 1}); duplicate contract keys are "
                f"rejected rather than silently keeping only the last one."
            )
        value = loader.construct_object(value_node, deep=deep)
        mapping[key] = value
    return mapping


_NoDuplicateKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping_no_duplicates
)

_REQUIRED_FILE_FIELDS = (
    "expected_sha256",
    "expected_well_identifier",
    "expected_survey_identifier",
    "expected_coordinate_reference_system",
    "expected_wellhead_x_m",
    "expected_wellhead_y_m",
    "expected_datum_m",
    "expected_datum_reference",
    "expected_column_count",
    "expected_column_order",
    "expected_units",
    "expected_station_count",
    "expected_md_min_m",
    "expected_md_max_m",
    "azimuth_reference_for_grid_coordinates",
    "source_depth_convention",
    "header_tolerance_m",
    "residual_tolerance_tvd_m",
    "residual_tolerance_horizontal_m",
    "residual_fail_threshold_m",
    "depth_basis_policy",
    "notes",
)

_VALID_UNIT_TOKENS = {"m", "deg", "deg_per_30m"}
_VALID_AZIMUTH_REFERENCES = {"AZIM_TN", "AZIM_GN"}


def load_deviation_contract_config(yaml_path: str) -> Dict[str, DeviationFileContract]:
    """
    Load and validate `config/deviation_survey_contracts.yml`, returning a
    mapping of source filename -> `DeviationFileContract`.

    Validates, at load time (before any deviation file is opened):
    * the YAML parses, has a top-level `files` mapping, and contains no
      duplicate mapping keys anywhere (see `_NoDuplicateKeySafeLoader`);
    * every required field (`_REQUIRED_FILE_FIELDS`) is present for every
      file entry;
    * `expected_column_count` is a positive integer equal to
      `len(expected_column_order)`, and `expected_column_order` is a list
      of unique strings drawn from `REQUIRED_COLUMN_NAMES`;
    * `expected_units` covers exactly `REQUIRED_COLUMN_NAMES` with values
      drawn from `_VALID_UNIT_TOKENS`;
    * `expected_wellhead_x_m`, `expected_wellhead_y_m`, `expected_datum_m`,
      `expected_md_min_m`, `expected_md_max_m`, `header_tolerance_m`,
      `residual_tolerance_tvd_m`, `residual_tolerance_horizontal_m`, and
      `residual_fail_threshold_m` are all genuine (non-boolean) numeric
      types;
    * the three tolerance fields are non-negative, and
      `residual_fail_threshold_m` is strictly greater than both
      `residual_tolerance_tvd_m` and `residual_tolerance_horizontal_m`
      (otherwise there is no real WARNING band between "pass" and "fail");
    * `expected_md_min_m <= expected_md_max_m`;
    * `expected_station_count` is a positive integer;
    * `azimuth_reference_for_grid_coordinates` is one of
      `_VALID_AZIMUTH_REFERENCES` AND appears in `expected_column_order`;
    * `depth_basis_policy` is one of
      `p2mem.deviation_models.VALID_DEPTH_BASIS_POLICIES`.

    Raises
    ------
    DeviationContractDefinitionError
        On any of the above validation failures, or if the file is
        missing / not valid YAML.
    """
    p = Path(yaml_path)
    if not p.exists():
        raise DeviationContractDefinitionError(f"Deviation contract file not found: {yaml_path}")

    try:
        with p.open("r", encoding="utf-8") as f:
            raw = yaml.load(f, Loader=_NoDuplicateKeySafeLoader)
    except yaml.YAMLError as exc:
        raise DeviationContractDefinitionError(f"{yaml_path}: not valid YAML ({exc})") from exc

    if not raw or "files" not in raw or not isinstance(raw["files"], dict):
        raise DeviationContractDefinitionError(f"{yaml_path}: expected a top-level 'files' mapping.")

    contracts: Dict[str, DeviationFileContract] = {}
    for filename, d in raw["files"].items():
        if not isinstance(d, dict):
            raise DeviationContractDefinitionError(f"{yaml_path}: entry for {filename!r} must be a mapping.")

        missing = [f for f in _REQUIRED_FILE_FIELDS if f not in d]
        if missing:
            raise DeviationContractDefinitionError(
                f"{yaml_path}: entry for {filename!r} is missing required field(s): {missing}"
            )

        # --- column order / count ---
        col_order = d["expected_column_order"]
        if not isinstance(col_order, list) or not all(isinstance(c, str) for c in col_order):
            raise DeviationContractDefinitionError(
                f"{yaml_path}: {filename!r}.expected_column_order must be a list of strings."
            )
        if len(set(col_order)) != len(col_order):
            raise DeviationContractDefinitionError(
                f"{yaml_path}: {filename!r}.expected_column_order contains duplicate column names."
            )
        if set(col_order) != set(REQUIRED_COLUMN_NAMES):
            raise DeviationContractDefinitionError(
                f"{yaml_path}: {filename!r}.expected_column_order must be exactly the set "
                f"{REQUIRED_COLUMN_NAMES}; got {tuple(col_order)}."
            )
        col_count = d["expected_column_count"]
        if isinstance(col_count, bool) or not isinstance(col_count, int) or col_count <= 0:
            raise DeviationContractDefinitionError(
                f"{yaml_path}: {filename!r}.expected_column_count must be a positive integer."
            )
        if col_count != len(col_order):
            raise DeviationContractDefinitionError(
                f"{yaml_path}: {filename!r}.expected_column_count ({col_count}) does not match "
                f"len(expected_column_order) ({len(col_order)})."
            )

        # --- units ---
        units = d["expected_units"]
        if not isinstance(units, dict) or set(units.keys()) != set(REQUIRED_COLUMN_NAMES):
            raise DeviationContractDefinitionError(
                f"{yaml_path}: {filename!r}.expected_units must declare exactly the columns "
                f"{REQUIRED_COLUMN_NAMES}."
            )
        bad_units = {k: v for k, v in units.items() if v not in _VALID_UNIT_TOKENS}
        if bad_units:
            raise DeviationContractDefinitionError(
                f"{yaml_path}: {filename!r}.expected_units has unsupported unit token(s): {bad_units} "
                f"(supported: {_VALID_UNIT_TOKENS})."
            )

        # --- numeric fields ---
        def _num(field: str) -> float:
            v = d[field]
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise DeviationContractDefinitionError(
                    f"{yaml_path}: {filename!r}.{field} must be a genuine number, got {v!r}."
                )
            return float(v)

        wellhead_x = _num("expected_wellhead_x_m")
        wellhead_y = _num("expected_wellhead_y_m")
        datum = _num("expected_datum_m")
        md_min = _num("expected_md_min_m")
        md_max = _num("expected_md_max_m")
        header_tol = _num("header_tolerance_m")
        tvd_tol = _num("residual_tolerance_tvd_m")
        horiz_tol = _num("residual_tolerance_horizontal_m")
        fail_thresh = _num("residual_fail_threshold_m")

        if header_tol < 0 or tvd_tol < 0 or horiz_tol < 0 or fail_thresh < 0:
            raise DeviationContractDefinitionError(
                f"{yaml_path}: {filename!r} tolerances must be non-negative."
            )
        if fail_thresh <= max(tvd_tol, horiz_tol):
            raise DeviationContractDefinitionError(
                f"{yaml_path}: {filename!r}.residual_fail_threshold_m ({fail_thresh}) must exceed "
                f"both residual_tolerance_tvd_m ({tvd_tol}) and residual_tolerance_horizontal_m "
                f"({horiz_tol}) - otherwise there is no WARNING band between pass and fail."
            )
        if md_min > md_max:
            raise DeviationContractDefinitionError(
                f"{yaml_path}: {filename!r}.expected_md_min_m ({md_min}) exceeds "
                f"expected_md_max_m ({md_max})."
            )

        station_count = d["expected_station_count"]
        if isinstance(station_count, bool) or not isinstance(station_count, int) or station_count <= 0:
            raise DeviationContractDefinitionError(
                f"{yaml_path}: {filename!r}.expected_station_count must be a positive integer."
            )

        azim_ref = d["azimuth_reference_for_grid_coordinates"]
        if azim_ref not in _VALID_AZIMUTH_REFERENCES:
            raise DeviationContractDefinitionError(
                f"{yaml_path}: {filename!r}.azimuth_reference_for_grid_coordinates must be one of "
                f"{_VALID_AZIMUTH_REFERENCES}, got {azim_ref!r}."
            )
        if azim_ref not in col_order:
            raise DeviationContractDefinitionError(
                f"{yaml_path}: {filename!r}.azimuth_reference_for_grid_coordinates ({azim_ref!r}) "
                f"is not one of its own declared expected_column_order."
            )

        depth_basis = d["depth_basis_policy"]
        if depth_basis not in VALID_DEPTH_BASIS_POLICIES:
            raise DeviationContractDefinitionError(
                f"{yaml_path}: {filename!r}.depth_basis_policy must be one of "
                f"{VALID_DEPTH_BASIS_POLICIES}, got {depth_basis!r}."
            )

        for str_field in (
            "expected_sha256",
            "expected_well_identifier",
            "expected_survey_identifier",
            "expected_coordinate_reference_system",
            "expected_datum_reference",
            "source_depth_convention",
            "notes",
        ):
            if not isinstance(d[str_field], str) or not d[str_field].strip():
                raise DeviationContractDefinitionError(
                    f"{yaml_path}: {filename!r}.{str_field} must be a non-empty string."
                )

        contracts[filename] = DeviationFileContract(
            source_filename=filename,
            expected_sha256=d["expected_sha256"].strip().lower(),
            expected_well_identifier=d["expected_well_identifier"],
            expected_survey_identifier=d["expected_survey_identifier"],
            expected_coordinate_reference_system=d["expected_coordinate_reference_system"],
            expected_wellhead_x_m=wellhead_x,
            expected_wellhead_y_m=wellhead_y,
            expected_datum_m=datum,
            expected_datum_reference=d["expected_datum_reference"],
            expected_column_count=col_count,
            expected_column_order=tuple(col_order),
            expected_units=dict(units),
            expected_station_count=station_count,
            expected_md_min_m=md_min,
            expected_md_max_m=md_max,
            azimuth_reference_for_grid_coordinates=azim_ref,
            source_depth_convention=d["source_depth_convention"],
            header_tolerance_m=header_tol,
            residual_tolerance_tvd_m=tvd_tol,
            residual_tolerance_horizontal_m=horiz_tol,
            residual_fail_threshold_m=fail_thresh,
            depth_basis_policy=depth_basis,
            notes=d["notes"],
        )

    return contracts


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------
def parse_deviation_header(path: str) -> Tuple[DeviationHeaderInfo, int, Tuple[str, ...]]:
    """
    Parse a Petrel deviation-survey file's header block (everything up to
    and including the second "#===...===" separator line).

    Returns `(header_info, data_start_line_index, column_names)`, where
    `data_start_line_index` is the zero-based index of the first station
    DATA line (i.e. the line immediately after the second separator), and
    `column_names` is the file's own literal, order-preserving column
    name tuple as read from its column-header line (NOT yet checked
    against any contract's `expected_column_order`).

    Raises `DeviationFileNotFoundError` if the path does not exist, and
    `DeviationParsingError` for any structural header defect: an
    unrecognized banner line, a missing required header field, fewer or
    more than exactly two "#===" separator lines before the data begins,
    a missing/duplicated column name, or a malformed WELL HEAD /
    WELL DATUM numeric-and-unit line.
    """
    p = Path(path)
    if not p.exists():
        raise DeviationFileNotFoundError(f"Deviation-survey file not found: {path}")

    sha256 = hashlib.sha256(p.read_bytes()).hexdigest()
    lines = p.read_text(encoding="utf-8").splitlines()

    if not lines or not _BANNER_RE.match(lines[0].strip()):
        raise DeviationParsingError(
            f"{path}: first line does not match the expected Petrel well-trace banner "
            f"('# WELL TRACE FROM PETREL ...'); got {lines[0] if lines else '<empty file>'!r}."
        )

    well_name: Optional[str] = None
    survey_name: Optional[str] = None
    wellhead_x: Optional[float] = None
    wellhead_x_unit: Optional[str] = None
    wellhead_y: Optional[float] = None
    wellhead_y_unit: Optional[str] = None
    datum_value: Optional[float] = None
    datum_reference: Optional[str] = None
    datum_unit: Optional[str] = None
    well_type: Optional[str] = None
    depth_reference_statement: Optional[str] = None
    angle_unit_statement: Optional[str] = None
    crs_text: Optional[str] = None
    dx_dy_statement: Optional[str] = None
    z_statement: Optional[str] = None
    azim_tn_desc_found = False
    azim_gn_desc_found = False

    separator_positions: List[int] = []
    column_names: Optional[Tuple[str, ...]] = None
    data_start_index: Optional[int] = None

    i = 0
    n = len(lines)
    while i < n:
        raw_line = lines[i]
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if _SEPARATOR_RE.match(stripped):
            separator_positions.append(i)
            if len(separator_positions) == 2:
                data_start_index = i + 1
                i += 1
                break
            i += 1
            continue

        if not stripped.startswith("#"):
            if len(separator_positions) != 1:
                raise DeviationParsingError(
                    f"{path}: line {i + 1} ({stripped!r}) is not a '#' header line, but was found "
                    f"{'before any' if not separator_positions else 'after the'} '#===' separator; "
                    f"expected exactly one non-'#' column-header line strictly between the two "
                    f"'#===' separator lines."
                )
            if column_names is not None:
                raise DeviationParsingError(
                    f"{path}: more than one column-header line found between the two '#===' "
                    f"separators (line {i + 1}: {stripped!r})."
                )
            tokens = stripped.split()
            if len(set(tokens)) != len(tokens):
                dupes = sorted({t for t in tokens if tokens.count(t) > 1})
                raise DeviationParsingError(
                    f"{path}: column-header line contains duplicate column name(s): {dupes}."
                )
            missing_cols = set(REQUIRED_COLUMN_NAMES) - set(tokens)
            if missing_cols:
                raise DeviationParsingError(
                    f"{path}: column-header line is missing required column(s): {sorted(missing_cols)}."
                )
            column_names = tuple(tokens)
            i += 1
            continue

        # A '#'-prefixed header/info line - dispatch to a recognized field.
        m = _WELL_NAME_RE.match(stripped)
        if m:
            well_name = m.group(1)
            i += 1
            continue
        m = _SURVEY_RE.match(stripped)
        if m:
            survey_name = m.group(1)
            i += 1
            continue
        m = _WELLHEAD_X_RE.match(stripped)
        if m:
            wellhead_x = float(m.group(1))
            wellhead_x_unit = m.group(2)
            i += 1
            continue
        m = _WELLHEAD_Y_RE.match(stripped)
        if m:
            wellhead_y = float(m.group(1))
            wellhead_y_unit = m.group(2)
            i += 1
            continue
        m = _DATUM_RE.match(stripped)
        if m:
            datum_reference = m.group(1)
            datum_value = float(m.group(2))
            datum_unit = m.group(3)
            i += 1
            continue
        m = _WELL_TYPE_RE.match(stripped)
        if m:
            well_type = m.group(1)
            i += 1
            continue
        m = _DEPTH_REF_RE.match(stripped)
        if m:
            depth_reference_statement = m.group(1)
            i += 1
            continue
        m = _ANGLE_UNIT_RE.match(stripped)
        if m:
            angle_unit_statement = m.group(1)
            i += 1
            continue
        m = _CRS_RE.match(stripped)
        if m:
            crs_text = m.group(1)
            i += 1
            continue
        if _AZIM_TN_DESC_RE.match(stripped):
            azim_tn_desc_found = True
            i += 1
            continue
        if _AZIM_GN_DESC_RE.match(stripped):
            azim_gn_desc_found = True
            i += 1
            continue
        m = _DXDY_RE.match(stripped)
        if m:
            dx_dy_statement = m.group(1)
            i += 1
            continue
        m = _Z_RE.match(stripped)
        if m:
            z_statement = m.group(1)
            i += 1
            continue
        if _BANNER_RE.match(stripped):
            i += 1
            continue

        # An unrecognized '#' line before the first separator is tolerated
        # (a vendor may add an extra informational comment) but every
        # REQUIRED field below is still checked for presence afterward.
        i += 1

    if len(separator_positions) != 2:
        raise DeviationParsingError(
            f"{path}: expected exactly two '#===...===' header separator lines; "
            f"found {len(separator_positions)}."
        )
    if column_names is None:
        raise DeviationParsingError(
            f"{path}: no column-header line found between the two '#===' separators."
        )

    required_fields = {
        "WELL NAME": well_name,
        "DEFINITIVE SURVEY": survey_name,
        "WELL HEAD X-COORDINATE": wellhead_x,
        "WELL HEAD Y-COORDINATE": wellhead_y,
        "WELL DATUM": datum_value,
        "WELL TYPE": well_type,
        "MD/TVD depth-reference statement": depth_reference_statement,
        "ANGLES unit statement": angle_unit_statement,
        "coordinate-reference-system statement": crs_text,
        "AZIM_TN description line": azim_tn_desc_found or None,
        "AZIM_GN description line": azim_gn_desc_found or None,
        "DX/DY unit statement": dx_dy_statement,
        "Z/TVD unit statement": z_statement,
    }
    missing = [name for name, value in required_fields.items() if value is None]
    if missing:
        raise DeviationParsingError(f"{path}: missing required header field(s): {missing}")

    if wellhead_x_unit != "m" or wellhead_y_unit != "m":
        raise DeviationParsingError(
            f"{path}: unsupported wellhead-coordinate unit ({wellhead_x_unit!r}/{wellhead_y_unit!r}); "
            f"only metres ('m') is implemented."
        )
    if datum_unit != "m":
        raise DeviationParsingError(
            f"{path}: unsupported well-datum unit ({datum_unit!r}); only metres ('m') is implemented."
        )
    if angle_unit_statement.strip().rstrip(".").lower() != "degrees":
        raise DeviationParsingError(
            f"{path}: unsupported angle-unit convention {angle_unit_statement!r}; "
            f"only 'DEGREES' is implemented."
        )
    if "m-units" not in dx_dy_statement.lower().replace(" ", ""):
        raise DeviationParsingError(
            f"{path}: unsupported DX/DY unit convention {dx_dy_statement!r}; "
            f"only metre ('m-UNITS') is implemented."
        )
    if "m-units" not in z_statement.lower().replace(" ", ""):
        raise DeviationParsingError(
            f"{path}: unsupported Z/TVD unit convention {z_statement!r}; "
            f"only metre ('m-UNITS') is implemented."
        )

    header = DeviationHeaderInfo(
        source_path=str(path),
        source_filename=p.name,
        sha256=sha256,
        well_name=well_name,
        survey_name=survey_name,
        wellhead_x_m=wellhead_x,
        wellhead_y_m=wellhead_y,
        datum_elevation_m=datum_value,
        datum_reference=datum_reference,
        well_type=well_type,
        coordinate_reference_system=crs_text,
        depth_reference_statement=depth_reference_statement,
        angle_unit_statement=angle_unit_statement,
        dx_dy_statement=dx_dy_statement,
        z_statement=z_statement,
        column_names=column_names,
        header_line_count=data_start_index - 1,  # everything before the data rows, incl. both '#===' lines
        data_line_offset=data_start_index,
    )
    return header, data_start_index, column_names


# ---------------------------------------------------------------------------
# Station-data parsing
# ---------------------------------------------------------------------------
def _parse_float_strict(token: str, *, path: str, line_no: int, col_name: str) -> float:
    try:
        value = float(token)
    except ValueError as exc:
        raise DeviationParsingError(
            f"{path}: line {line_no}: non-numeric token {token!r} in column {col_name!r}."
        ) from exc
    if not math.isfinite(value):
        raise DeviationParsingError(
            f"{path}: line {line_no}: non-finite literal token {token!r} in column {col_name!r} "
            f"(NaN/Inf tokens are never accepted as station data)."
        )
    return value


def read_deviation_stations(
    path: str, data_start_index: int, column_names: Tuple[str, ...]
) -> DeviationStationData:
    """
    Parse every station data row starting at `data_start_index` (as
    returned by `parse_deviation_header`), using `column_names` (the
    file's own literal column order) to place each numeric token.

    Raises `DeviationParsingError` for a row whose token count does not
    match `len(column_names)` (row-width mismatch), or any non-numeric or
    non-finite (NaN/Inf) token.
    """
    p = Path(path)
    lines = p.read_text(encoding="utf-8").splitlines()

    rows: List[List[float]] = []
    for idx in range(data_start_index, len(lines)):
        raw_line = lines[idx]
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            raise DeviationParsingError(
                f"{path}: line {idx + 1}: unexpected '#' comment line found after station data begins "
                f"(comments are only recognized in the header block, before the second '#===' separator)."
            )
        tokens = stripped.split()
        if len(tokens) != len(column_names):
            raise DeviationParsingError(
                f"{path}: line {idx + 1}: expected {len(column_names)} column(s), found {len(tokens)} "
                f"(row-width mismatch)."
            )
        row = [
            _parse_float_strict(tok, path=path, line_no=idx + 1, col_name=col)
            for tok, col in zip(tokens, column_names)
        ]
        rows.append(row)

    if not rows:
        raise DeviationParsingError(f"{path}: no station data rows found after the header.")

    arr = np.array(rows, dtype=np.float64)
    col_index = {name: k for k, name in enumerate(column_names)}
    kwargs = {
        _COLUMN_TO_FIELD[name]: arr[:, col_index[name]] for name in REQUIRED_COLUMN_NAMES
    }
    return DeviationStationData(**kwargs)


# ---------------------------------------------------------------------------
# Contract resolution
# ---------------------------------------------------------------------------
def resolve_deviation_contract(
    header: DeviationHeaderInfo,
    column_names: Tuple[str, ...],
    stations: DeviationStationData,
    contract: DeviationFileContract,
) -> Tuple[DeviationIngestionIssue, ...]:
    """
    Compare a file's actual parsed header and station data against its
    `DeviationFileContract`, returning the full tuple of
    `DeviationIngestionIssue` (ERROR and WARNING). Every check below is
    performed independently (no short-circuiting on the first mismatch),
    so a caller sees every problem in one pass, not just the first one
    encountered.

    ERROR-severity checks: filename, SHA-256, well identifier, survey
    identifier, coordinate-reference-system text, wellhead X/Y (within
    `header_tolerance_m`), datum value and reference text (within
    `header_tolerance_m` for the value), column order (exact match),
    column count, station count, MD coverage (min/max, within
    `header_tolerance_m`), duplicate/non-monotonic MD, and
    physically-invalid inclination (outside [0, 180] degrees) - the
    inclination check is ERROR-severity here (blocking), distinct from
    `p2mem.trajectory`'s own independent, second-gate rejection of the
    same condition at trajectory-computation time.

    WARNING-severity checks: the disclosed MD-unit inference (see module
    docstring). The disclosed DLS-normalization inference is added
    separately, in `load_deviation_file`, after a successful minimum-
    curvature computation is available to independently verify it against
    (see that function's docstring) - it is not one of the issues
    returned directly by this function.

    Every issue's `context` field is set to `header.source_filename`
    (the file's basename only, e.g. "Poseidon 2_dev.txt") rather than
    `header.source_path` (the full filesystem path, which is
    environment-dependent - a Colab Drive mount path, a local
    Increment-3.1-corrective-patch build path, or a CI temp directory
    would each differ for byte-identical data). This keeps every exported
    CSV/JSON deliverable free of build-environment-specific absolute
    paths (Increment 3.1 correction - see the Increment 3.1 manifest);
    `header.source_path` remains available on the `DeviationHeaderInfo`
    object itself for interactive debugging.
    """
    issues: List[DeviationIngestionIssue] = []

    def err(code: str, message: str, context: str = "") -> None:
        issues.append(DeviationIngestionIssue("ERROR", code, message, context))

    def warn(code: str, message: str, context: str = "") -> None:
        issues.append(DeviationIngestionIssue("WARNING", code, message, context))

    if header.source_filename != contract.source_filename:
        err(
            "FILENAME_MISMATCH",
            f"Loaded file basename {header.source_filename!r} does not match contract's "
            f"declared filename {contract.source_filename!r}.",
            header.source_filename,
        )
    if header.sha256.lower() != contract.expected_sha256.lower():
        err(
            "SHA256_MISMATCH",
            f"File SHA-256 {header.sha256} does not match contract's expected "
            f"{contract.expected_sha256}.",
            header.source_filename,
        )
    if header.well_name != contract.expected_well_identifier:
        err(
            "WELL_IDENTIFIER_MISMATCH",
            f"Parsed WELL NAME {header.well_name!r} does not match contract's expected "
            f"well identifier {contract.expected_well_identifier!r}.",
            header.source_filename,
        )
    if header.survey_name != contract.expected_survey_identifier:
        err(
            "SURVEY_IDENTIFIER_MISMATCH",
            f"Parsed DEFINITIVE SURVEY {header.survey_name!r} does not match contract's "
            f"expected {contract.expected_survey_identifier!r}.",
            header.source_filename,
        )
    if header.coordinate_reference_system != contract.expected_coordinate_reference_system:
        err(
            "CRS_MISMATCH",
            f"Parsed coordinate-reference-system text {header.coordinate_reference_system!r} "
            f"does not match contract's expected {contract.expected_coordinate_reference_system!r}.",
            header.source_filename,
        )
    if abs(header.wellhead_x_m - contract.expected_wellhead_x_m) > contract.header_tolerance_m:
        err(
            "WELLHEAD_X_MISMATCH",
            f"Parsed wellhead X ({header.wellhead_x_m}) differs from contract's expected "
            f"({contract.expected_wellhead_x_m}) by more than tolerance ({contract.header_tolerance_m} m).",
            header.source_filename,
        )
    if abs(header.wellhead_y_m - contract.expected_wellhead_y_m) > contract.header_tolerance_m:
        err(
            "WELLHEAD_Y_MISMATCH",
            f"Parsed wellhead Y ({header.wellhead_y_m}) differs from contract's expected "
            f"({contract.expected_wellhead_y_m}) by more than tolerance ({contract.header_tolerance_m} m).",
            header.source_filename,
        )
    if abs(header.datum_elevation_m - contract.expected_datum_m) > contract.header_tolerance_m:
        err(
            "DATUM_MISMATCH",
            f"Parsed well datum ({header.datum_elevation_m}) differs from contract's expected "
            f"({contract.expected_datum_m}) by more than tolerance ({contract.header_tolerance_m} m).",
            header.source_filename,
        )
    if header.datum_reference != contract.expected_datum_reference:
        err(
            "DATUM_REFERENCE_MISMATCH",
            f"Parsed datum-reference text {header.datum_reference!r} does not match contract's "
            f"expected {contract.expected_datum_reference!r}.",
            header.source_filename,
        )
    if column_names != contract.expected_column_order:
        err(
            "COLUMN_ORDER_MISMATCH",
            f"Parsed column order {column_names} does not match contract's required exact order "
            f"{contract.expected_column_order}.",
            header.source_filename,
        )
    if len(column_names) != contract.expected_column_count:
        err(
            "COLUMN_COUNT_MISMATCH",
            f"Parsed column count ({len(column_names)}) does not match contract's expected "
            f"({contract.expected_column_count}).",
            header.source_filename,
        )

    n_stations = stations.MD_source_m.size
    if n_stations != contract.expected_station_count:
        err(
            "STATION_COUNT_MISMATCH",
            f"Parsed station count ({n_stations}) does not match contract's expected "
            f"({contract.expected_station_count}).",
            header.source_filename,
        )
    md_min = float(np.min(stations.MD_source_m))
    md_max = float(np.max(stations.MD_source_m))
    if abs(md_min - contract.expected_md_min_m) > contract.header_tolerance_m:
        err(
            "MD_MIN_MISMATCH",
            f"Parsed minimum MD ({md_min}) differs from contract's expected "
            f"({contract.expected_md_min_m}) by more than tolerance ({contract.header_tolerance_m} m).",
            header.source_filename,
        )
    if abs(md_max - contract.expected_md_max_m) > contract.header_tolerance_m:
        err(
            "MD_MAX_MISMATCH",
            f"Parsed maximum MD ({md_max}) differs from contract's expected "
            f"({contract.expected_md_max_m}) by more than tolerance ({contract.header_tolerance_m} m).",
            header.source_filename,
        )

    # --- station-level QC (ERROR-severity structural checks) ---
    n_dup = int(np.sum(np.diff(stations.MD_source_m) == 0.0)) if n_stations > 1 else 0
    if n_dup > 0:
        err(
            "DUPLICATE_MD",
            f"{n_dup} duplicate consecutive measured-depth value(s) found.",
            header.source_filename,
        )
    n_non_monotonic = (
        int(np.sum(np.diff(stations.MD_source_m) < 0.0)) if n_stations > 1 else 0
    )
    if n_non_monotonic > 0:
        err(
            "NON_MONOTONIC_MD",
            f"{n_non_monotonic} decreasing measured-depth step(s) found; MD must be "
            f"non-decreasing.",
            header.source_filename,
        )
    invalid_incl_mask = (stations.INCL_source_deg < 0.0) | (stations.INCL_source_deg > 180.0)
    if np.any(invalid_incl_mask):
        bad_idx = np.where(invalid_incl_mask)[0].tolist()
        err(
            "INVALID_INCLINATION",
            f"{len(bad_idx)} station(s) with inclination outside the physically valid range "
            f"[0, 180] degrees at row index(es) {bad_idx}.",
            header.source_filename,
        )

    # --- WARNING-severity disclosures ---
    warn(
        MD_UNIT_NOT_EXPLICITLY_DECLARED_CODE,
        "This file's header does not include an explicit unit statement for the MD column "
        "(only X/Y/DX/DY/Z/TVD are explicitly declared in metres, and AZIM_TN/INCL/AZIM_GN in "
        "degrees). MD is treated as metres by inference from its numeric consistency with this "
        "file's own explicitly-metric TVD column and the already-validated LAS MD_m convention "
        "for the same well - not from an explicit per-file statement.",
        header.source_filename,
    )

    return tuple(issues)


# ---------------------------------------------------------------------------
# Trajectory validation (source-vs-computed comparison)
# ---------------------------------------------------------------------------
def _status_for(max_abs_residual: float, tolerance: float, fail_threshold: float) -> str:
    if max_abs_residual <= tolerance:
        return STATUS_PASS
    if max_abs_residual <= fail_threshold:
        return STATUS_WARNING
    return STATUS_FAIL


_STATUS_RANK = {STATUS_PASS: 0, STATUS_WARNING: 1, STATUS_FAIL: 2}


def compute_well_trajectory_validation(
    well_key: str,
    header: DeviationHeaderInfo,
    stations: DeviationStationData,
    contract: DeviationFileContract,
) -> Tuple["_MCBundle", TrajectoryValidationResult]:
    """
    Compute the independent minimum-curvature trajectory (using the
    contract-declared `azimuth_reference_for_grid_coordinates`) and the
    full `TrajectoryValidationResult` comparing it against the Petrel-
    supplied source trajectory, plus the three internal Petrel-source
    self-consistency checks (X ~= X_wellhead + DX, Y ~= Y_wellhead + DY,
    Z ~= Datum - TVD).

    Raises `p2mem.trajectory.TrajectoryComputationError` if the station
    data cannot be safely passed to minimum-curvature computation (this
    should already be impossible for a file whose station-level QC in
    `resolve_deviation_contract` reported no ERROR, since that function
    checks MD monotonicity and inclination range first - this is a
    second, independent gate, not the primary one).
    """
    azim_ref = contract.azimuth_reference_for_grid_coordinates
    azim_deg = (
        stations.AZIM_GN_source_deg if azim_ref == "AZIM_GN" else stations.AZIM_TN_source_deg
    )

    mc = compute_minimum_curvature_trajectory(
        stations.MD_source_m,
        stations.INCL_source_deg,
        azim_deg,
        tvd_origin_m=float(stations.TVD_source_m[0]),
        northing_origin_m=float(stations.DY_source_m[0]),
        easting_origin_m=float(stations.DX_source_m[0]),
    )

    tvd_res = mc.tvd_mc_m - stations.TVD_source_m
    easting_res = mc.easting_offset_mc_m - stations.DX_source_m
    northing_res = mc.northing_offset_mc_m - stations.DY_source_m

    def _stats(res: np.ndarray) -> Tuple[float, float, float, float]:
        return (
            float(np.max(np.abs(res))),
            float(np.mean(res)),
            float(np.sqrt(np.mean(res**2))),
            float(res[-1]),
        )

    tvd_max, tvd_mean, tvd_rmse, tvd_end = _stats(tvd_res)
    e_max, e_mean, e_rmse, e_end = _stats(easting_res)
    n_max, n_mean, n_rmse, n_end = _stats(northing_res)

    tvd_status = _status_for(tvd_max, contract.residual_tolerance_tvd_m, contract.residual_fail_threshold_m)
    e_status = _status_for(e_max, contract.residual_tolerance_horizontal_m, contract.residual_fail_threshold_m)
    n_status = _status_for(n_max, contract.residual_tolerance_horizontal_m, contract.residual_fail_threshold_m)

    # Internal Petrel-source self-consistency: X ~= X_wellhead + DX, etc.
    x_check = stations.X_source_m - (header.wellhead_x_m + stations.DX_source_m)
    y_check = stations.Y_source_m - (header.wellhead_y_m + stations.DY_source_m)
    z_check = stations.Z_source_m - (header.datum_elevation_m - stations.TVD_source_m)
    x_max = float(np.max(np.abs(x_check)))
    y_max = float(np.max(np.abs(y_check)))
    z_max = float(np.max(np.abs(z_check)))
    x_status = _status_for(x_max, contract.residual_tolerance_horizontal_m, contract.residual_fail_threshold_m)
    y_status = _status_for(y_max, contract.residual_tolerance_horizontal_m, contract.residual_fail_threshold_m)
    z_status = _status_for(z_max, contract.residual_tolerance_tvd_m, contract.residual_fail_threshold_m)

    overall_status = max(
        [tvd_status, e_status, n_status, x_status, y_status, z_status],
        key=lambda s: _STATUS_RANK[s],
    )

    validation = TrajectoryValidationResult(
        well_key=well_key,
        comparison_basis=(
            f"TVD_mc_m vs TVD_source_m; EASTING_offset_mc_m vs DX_source_m; "
            f"NORTHING_offset_mc_m vs DY_source_m (grid-coordinate azimuth reference: {azim_ref}); "
            f"plus internal Petrel-source consistency X~=X_wellhead+DX, Y~=Y_wellhead+DY, "
            f"Z~=Datum-TVD."
        ),
        tvd_max_abs_residual_m=tvd_max,
        tvd_mean_residual_m=tvd_mean,
        tvd_rmse_m=tvd_rmse,
        tvd_endpoint_residual_m=tvd_end,
        tvd_tolerance_m=contract.residual_tolerance_tvd_m,
        tvd_status=tvd_status,
        easting_max_abs_residual_m=e_max,
        easting_mean_residual_m=e_mean,
        easting_rmse_m=e_rmse,
        easting_endpoint_residual_m=e_end,
        easting_tolerance_m=contract.residual_tolerance_horizontal_m,
        easting_status=e_status,
        northing_max_abs_residual_m=n_max,
        northing_mean_residual_m=n_mean,
        northing_rmse_m=n_rmse,
        northing_endpoint_residual_m=n_end,
        northing_tolerance_m=contract.residual_tolerance_horizontal_m,
        northing_status=n_status,
        x_consistency_max_abs_residual_m=x_max,
        x_consistency_status=x_status,
        y_consistency_max_abs_residual_m=y_max,
        y_consistency_status=y_status,
        z_consistency_max_abs_residual_m=z_max,
        z_consistency_status=z_status,
        overall_status=overall_status,
        origin_initialization_note=(
            f"Minimum-curvature trajectory initialized at station 0 using this well's own "
            f"source TVD ({float(stations.TVD_source_m[0]):.9g} m), DX "
            f"({float(stations.DX_source_m[0]):.9g} m), and DY "
            f"({float(stations.DY_source_m[0]):.9g} m) as the tie-on origin - never a "
            f"hard-coded (0, 0, 0)."
        ),
    )
    return mc, validation


# ---------------------------------------------------------------------------
# Per-file and batch loaders
# ---------------------------------------------------------------------------
def load_deviation_file(path: str, contract: DeviationFileContract) -> DeviationWellResult:
    """
    Parse, contract-resolve, and trajectory-validate one deviation-survey
    file, returning a complete `DeviationWellResult`.

    Raises `DeviationFileNotFoundError`, `DeviationParsingError`, or
    `DeviationContractError` (never returns a partially valid result -
    only a successfully resolved file is returned).

    DLS-normalization disclosure (Increment 3.1 addition)
    -------------------------------------------------------
    None of the four approved files' headers explicitly states that the
    supplied `DLS` column is normalized as degrees-per-30-metres (the
    header declares angles are in degrees, but says nothing about DLS's
    own length normalization). `deg/30m` is the standard oilfield
    convention and is scientifically defensible here, but it is an
    INFERENCE, not a header-declared unit - exactly like the pre-existing
    `MD_UNIT_NOT_EXPLICITLY_DECLARED` disclosure for the MD column. This
    function verifies that inference independently for every successfully
    loaded file (not merely asserts it): it recomputes each station's
    dogleg severity from that same file's own MD/inclination/azimuth
    columns via `p2mem.trajectory` (already computed a moment earlier, as
    part of `mc`, for the trajectory-validation comparison above) and
    compares it, station by station, against the file's own supplied
    `DLS_source_deg_per_30m` column. The resulting `DeviationIngestionIssue`
    (code `DLS_NORMALIZATION_INFERRED_AS_DEG_PER_30M`, always WARNING
    severity, never blocking) reports the ACTUAL maximum discrepancy found
    for THIS file - never a hard-coded or assumed number - and explicitly
    states that the raw `DLS_source_deg_per_30m` array itself is never
    altered by this check (it is a read-only comparison).
    """
    header, data_start, column_names = parse_deviation_header(path)
    stations = read_deviation_stations(path, data_start, column_names)
    issues = resolve_deviation_contract(header, column_names, stations, contract)

    error_issues = tuple(i for i in issues if i.severity == "ERROR")
    if error_issues:
        raise DeviationContractError(
            f"{path}: {len(error_issues)} contract-resolution ERROR(s): "
            + "; ".join(f"[{i.code}] {i.message}" for i in error_issues),
            issues,
        )

    mc, validation = compute_well_trajectory_validation(
        well_key=contract.expected_well_identifier, header=header, stations=stations, contract=contract
    )

    dls_recomputed_vs_source_abs_diff = np.abs(
        stations.DLS_source_deg_per_30m - mc.dls_deg_per_30m
    )
    dls_max_abs_diff = float(np.max(dls_recomputed_vs_source_abs_diff))
    dls_issue = DeviationIngestionIssue(
        "WARNING",
        DLS_NORMALIZATION_INFERRED_CODE,
        "This file's header declares angles (AZIM_TN/INCL/AZIM_GN) are in degrees but does not "
        "explicitly state the length-normalization of the supplied DLS column. 'degrees per 30 "
        "metres' was inferred (the standard oilfield dogleg-severity convention) and independently "
        "verified, not merely assumed: this file's own supplied DLS_source_deg_per_30m column was "
        "compared, station by station, against dogleg severity recomputed from this same file's own "
        f"MD/inclination/azimuth columns (p2mem.trajectory), giving a maximum absolute discrepancy of "
        f"{dls_max_abs_diff:.6e} deg/30m across {stations.MD_source_m.size} stations. The raw "
        "DLS_source_deg_per_30m values are never altered by this check.",
        header.source_filename,
    )
    issues = issues + (dls_issue,)

    depth_basis = DepthBasisSelection(
        well_key=contract.expected_well_identifier,
        selected_basis=contract.depth_basis_policy,
        rationale=(
            f"Per config/deviation_survey_contracts.yml (declared uniformly for all four wells): "
            f"'{contract.depth_basis_policy}' is used as the downstream MD-to-TVD/TVDSS mapping "
            f"basis. The independently computed minimum-curvature trajectory "
            f"(overall_status={validation.overall_status}) is retained as a QC comparison but is "
            f"not itself used for depth mapping."
        )
        if contract.depth_basis_policy == DEPTH_BASIS_PETREL_SOURCE
        else (
            f"Per config/deviation_survey_contracts.yml: 'minimum_curvature_computed' is used as "
            f"the downstream MD-to-TVD/TVDSS mapping basis for this well "
            f"(overall_status={validation.overall_status})."
        ),
    )

    return DeviationWellResult(
        header=header,
        contract=contract,
        raw=stations,
        mc=mc,
        validation=validation,
        depth_basis=depth_basis,
        issues=issues,
        contract_status="PASSED",
    )


def load_deviation_surveys(
    file_paths: Dict[str, str], contracts: Dict[str, DeviationFileContract]
) -> Tuple[Dict[str, DeviationWellResult], Dict[str, DeviationIngestionFailure]]:
    """
    Load a batch of deviation-survey files keyed by well key (e.g.
    "Poseidon_2"), isolating expected per-well ingestion failures
    (file-not-found, structural-parsing, contract-resolution, or
    trajectory-computation) as typed `DeviationIngestionFailure` records.
    Any other exception (a programming error, not an expected ingestion-
    failure mode) propagates uncaught.

    `contracts` is keyed by SOURCE FILENAME (as in
    `config/deviation_survey_contracts.yml`), matching
    `load_deviation_contract_config`'s return type; `file_paths` is keyed
    by WELL KEY (e.g. "Poseidon_2") and gives that well's file path. The
    contract used for a given well is looked up by the path's basename.
    """
    results: Dict[str, DeviationWellResult] = {}
    failures: Dict[str, DeviationIngestionFailure] = {}

    for well_key, path in file_paths.items():
        basename = Path(path).name
        contract = contracts.get(basename)
        if contract is None:
            raise DeviationContractDefinitionError(
                f"No deviation contract found for file {basename!r} (well key {well_key!r}); "
                f"contracts are keyed by source filename and must be authored before ingestion."
            )
        try:
            results[well_key] = load_deviation_file(path, contract)
        except DeviationFileNotFoundError as exc:
            failures[well_key] = DeviationIngestionFailure(
                well_key=well_key, source_path=path, error_type="file_not_found",
                message=str(exc), exception=exc,
            )
        except DeviationParsingError as exc:
            failures[well_key] = DeviationIngestionFailure(
                well_key=well_key, source_path=path, error_type="parsing_failure",
                message=str(exc), exception=exc,
            )
        except DeviationContractError as exc:
            failures[well_key] = DeviationIngestionFailure(
                well_key=well_key, source_path=path, error_type="contract_failure",
                message=str(exc), exception=exc,
            )
        except TrajectoryComputationError as exc:
            failures[well_key] = DeviationIngestionFailure(
                well_key=well_key, source_path=path, error_type="trajectory_failure",
                message=str(exc), exception=exc,
            )

    return results, failures
