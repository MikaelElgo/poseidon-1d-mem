"""
p2mem.io.las - Auditable LAS 2.0 ingestion with explicit per-file curve
contracts (Increment 2, corrected in Increment 2.1).

Why this module exists
------------------------
The four LAS files approved for this project (Poseidon 2, Boreas 1,
Poseidon North 1, Proteus 1ST2) all have EMPTY mnemonic fields for every
curve except DEPT: the ~Curve Information Section carries only a unit and
a free-text description such as ":  1 DCAV" (an embedded ordinal number
plus the intended curve name). A generic LAS parser has no reliable way
to name these curves - it would either fabricate placeholder names
(``UNKNOWN``, ``UNKNOWN:1``) or guess identity from column position alone,
either of which risks silently mislabeling a curve.

This module never guesses. Every curve in every file is resolved against
an explicit, human-authored contract (`config/las_curve_contracts.yml`)
that was built by directly inspecting each file's actual header text (see
the Increment 2 manifest for the inspection method). Resolution requires
several independent identifiers to agree - ordinal position, the
description's embedded ordinal, the description's embedded name, and unit
- and NEVER relies on ordinal position alone, per the project's explicit
mandate. Any disagreement fails that curve's resolution rather than
silently choosing a different column.

Two further LAS-format nuances specific to these files, discovered while
building the contracts, are handled explicitly rather than assumed away:

* Column order is NOT the same across the four files. Poseidon 2, Boreas 1,
  and Poseidon North 1 all place their neutron-porosity curve last
  (ordinal 8), but Proteus 1ST2 places it at ordinal 5, shifting RD, RHOB,
  and RS one position earlier than in the other three files. A shared,
  cross-well column-order assumption would silently mislabel Proteus's
  curves - hence one contract per file, never one contract for all wells.
* The curve carrying gamma-ray-like information is named differently in
  every file that has one (GR in Poseidon 2 and Proteus 1ST2, ECGR in
  Boreas 1, GRD in Poseidon North 1). Boreas 1's ECGR curve is additionally
  known (from the Rev 1 design review) to carry an unresolved scale
  anomaly. This module reports that anomaly as a fact (via curve
  statistics) but does not rescale it, reinterpret it, or otherwise act on
  it - that adjudication remains outside this increment's scope.

Scope boundary
--------------
This module parses LAS structure and resolves curve identity ONLY. It
performs no deviation-survey processing, no MD-to-TVD conversion, no
petrophysical interpretation, and no empirical/correlation calculations.
The only numeric transformations it ever applies are (a) NULL-sentinel
substitution to NaN and (b) the exact, contract-declared unit conversions
implemented in `p2mem.units` (e.g. us/ft -> m/s, g/cc -> kg/m3). No curve
is clipped, interpolated, despiked, resampled, smoothed, normalized, or
derived from another curve.

Increment 2.1 correction (independent audit of Increment 2)
-------------------------------------------------------------
The parsing architecture above (definition-line parsing, multi-signal
curve resolution, per-file contracts) is UNCHANGED and is preserved as-is
- it worked correctly against all four real wells and is not the subject
of this correction. What changed:

1. Canonical array names are now explicit and unit-suffixed everywhere
   (e.g. "VP_m_s" for converted compressional velocity, "DTCO_us_per_ft"
   as the raw curve's documented identity) - a canonical name can no
   longer be mistaken for a different physical quantity or unit than the
   array it labels. See `p2mem.models.CurveContractEntry`.
2. The "measured depth" curve is now identified by an explicit contract
   field (`semantic_role: measured_depth`), never by searching for a
   canonical name spelled "DEPT" - a contract that renames its depth
   curve's canonical target (as this correction itself does, to "MD_m")
   would otherwise silently break depth-diagnostic computation.
3. File-identity checks an independent audit found the Increment 2
   resolver did NOT perform (a missing WELL, a missing NULL, a changed
   VERS or WRAP, or even a contract for a different file than the one
   actually being loaded, all previously passed silently) are now
   blocking ERRORs, checked before any curve is resolved. A NULL mismatch
   is now an ERROR, not a WARNING, because it changes which samples get
   substituted to NaN.
4. Curve-coverage statistics are now reported as an explicit RAW/
   CANONICAL pair, each with its own unit, rather than a single
   min/max pair mislabeled with a canonical (implicitly converted) name
   while actually holding pre-conversion values.
5. A curve contract is validated, at YAML-load time, against a small
   conversion-signature registry so it cannot declare an internally
   incompatible unit/conversion-function pairing (e.g. applying
   `gcc_to_kgm3` to an API gamma-ray curve).
6. `load_wells` now returns a typed `IngestionFailure` per failed well
   (carrying an `error_type` of "file_not_found", "parsing_failure",
   "contract_failure", or "conversion_failure") instead of a bare caught
   exception, and isolates all four of those expected failure modes per
   well; any other exception is a programming error and still propagates.
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Callable, Dict, FrozenSet, List, Optional, Tuple

import numpy as np
import yaml

from p2mem import units
from p2mem.models import (
    SEMANTIC_ROLE_MEASURED_DEPTH,
    SEMANTIC_ROLE_MEASUREMENT,
    CurveContractEntry,
    CurveHeaderEntry,
    CurveResolution,
    CurveStats,
    DefinitionLine,
    DepthDiagnostics,
    FileContract,
    IngestionFailure,
    IngestionIssue,
    LasFileResult,
    LasHeaderInfo,
)

__all__ = [
    "LasFileNotFoundError",
    "LasParsingError",
    "LasContractDefinitionError",
    "LasContractError",
    "LasConversionError",
    "parse_las_header",
    "load_file_contract_config",
    "resolve_curve_contract",
    "compute_depth_diagnostics",
    "compute_curve_stats",
    "load_las_file",
    "load_wells",
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class LasFileNotFoundError(FileNotFoundError):
    """Raised when a required LAS source file cannot be found on disk."""


class LasParsingError(ValueError):
    """
    Raised for a structural/syntactic defect that prevents safely parsing a
    LAS file: a definition line with no '.' separator, a data row whose
    column count does not match the declared curve count, a data token
    that cannot be parsed as a number, or (Increment 2.1) a data token
    that DOES parse but to a non-finite value (a literal "nan"/"inf"/"-inf"
    text token) - this project's NULL policy is a single finite sentinel
    value, so a literal non-finite token is never treated as that
    sentinel and is rejected as a structural defect rather than silently
    substituted, clipped, or passed through. The loader stops immediately
    rather than skipping or guessing at the offending row.
    """


class LasContractDefinitionError(ValueError):
    """
    Raised when `config/las_curve_contracts.yml` itself is malformed or
    internally inconsistent. Increment 2.1 checks (in addition to the
    Increment 2 checks - an unparsable YAML document, a missing required
    field, an unknown `conversion_function`, or two curves mapped to the
    same `canonical_name`): a declared but unimplemented LAS version,
    WRAP value, or data layout; a non-boolean `required`; a non-numeric
    `expected_null_value`; a duplicate or negative curve ordinal; an
    ordinal set with an unjustified gap; a `conversion_function` whose
    declared raw/canonical units are incompatible with its registered
    signature; zero or more than one curve declared with
    `semantic_role: measured_depth`; or a measured-depth curve whose
    identity/canonical name/unit do not match the required convention.
    This is a configuration-authoring error, distinct from a data-
    resolution error.
    """


class LasContractError(RuntimeError):
    """
    Raised by `load_las_file` when the file's actual header cannot be
    safely reconciled with its contract: a file-identity mismatch
    (filename, SHA-256, WELL, VERS, WRAP, NULL, or curve count), a
    required curve failed to resolve, or a data-column-count mismatch was
    found.

    Ingestion stops - no alternate column is ever silently substituted.
    The exception carries `.issues` (all `IngestionIssue`s found, both
    ERROR and any WARNING already raised at that point), `.resolutions`
    (every attempted `CurveResolution`), and `.header` (the successfully
    parsed `LasHeaderInfo`, for diagnostic reporting, or `None` if the
    contract does not even define a measured-depth curve) so a caller can
    report exactly what went wrong without re-parsing the file.
    """

    issues: Tuple[IngestionIssue, ...] = ()
    resolutions: Tuple[CurveResolution, ...] = ()
    header: Optional[LasHeaderInfo] = None


class LasConversionError(RuntimeError):
    """
    Raised when applying a contract-declared exact unit conversion to a
    curve's NULL-substituted values cannot be done safely: either the
    conversion function itself raised (e.g. rejected an ambiguous dtype),
    or it produced a non-finite (Inf/-Inf) result from a value that was
    NOT a NULL-sentinel match - i.e. a real, non-null measurement that the
    exact conversion cannot represent (for example, a zero sonic slowness
    converting to an infinite velocity).

    This exception always names the source file, the curve involved
    (by its source curve name and canonical name), the expected canonical
    unit, and - when identifiable - the offending raw value and its row's
    measured depth, so a caller never sees a raw NumPy exception with no
    project context.
    """


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Declared STRT/STOP are frequently rounded to a "nice" number rather than
# the exact first/last sample (e.g. Poseidon 2 declares STOP=5351.0000 m
# while its last actual sample is 5350.9507 m) - a tolerance-based
# comparison is therefore used rather than exact equality.
_DEPTH_ENDPOINT_TOLERANCE_M = 0.5
_DEPTH_STEP_TOLERANCE_M = 1e-3
_NULL_TOLERANCE = 1e-6

_DESC_ORDINAL_RE = re.compile(r"^\s*(\d+)\s+(\S.*?)\s*$")

# What this parser actually implements. A contract that declares anything
# outside these sets is rejected at YAML-load time (LasContractDefinitionError)
# rather than silently "supported" - see the Increment 2.1 module docstring,
# point 3, and the corrective-patch requirement: "do not pretend to support
# a mode that has not been implemented."
_SUPPORTED_LAS_VERSIONS: FrozenSet[str] = frozenset({"2.0"})
_SUPPORTED_WRAP_VALUES: FrozenSet[str] = frozenset({"NO"})
_SUPPORTED_DATA_LAYOUTS: FrozenSet[str] = frozenset({"unwrapped_whitespace_delimited"})

# Conversion functions this module is permitted to apply, keyed by the
# name a contract entry may write in `conversion_function`. Every entry
# here is an EXACT, unit-only conversion from p2mem.units (Increment 1.1);
# no empirical/correlation function is ever listed here. "identity" is
# handled separately (see `_KNOWN_CONVERSION_NAMES` / `_apply_conversion`)
# since it is not a p2mem.units function - it is a declared no-op.
_ALLOWED_CONVERSION_FUNCTIONS: Dict[str, Callable] = {
    "us_per_ft_to_m_per_s": units.us_per_ft_to_m_per_s,
    "m_per_s_to_us_per_ft": units.m_per_s_to_us_per_ft,
    "gcc_to_kgm3": units.gcc_to_kgm3,
    "kgm3_to_gcc": units.kgm3_to_gcc,
    "feet_to_meters": units.feet_to_meters,
    "meters_to_feet": units.meters_to_feet,
}

_IDENTITY_CONVERSION = "identity"
_KNOWN_CONVERSION_NAMES = {_IDENTITY_CONVERSION} | set(_ALLOWED_CONVERSION_FUNCTIONS)

# Increment 2.1: a controlled conversion-signature registry. Each non-
# identity entry maps a conversion-function name to the set of raw units
# (lower-cased) it may be declared FROM and the single canonical unit
# (lower-cased) it produces. `load_file_contract_config` uses this to
# reject a contract that pairs a conversion function with an incompatible
# unit (e.g. `gcc_to_kgm3` on a curve whose raw_unit is "API") - a purely
# contract-authoring-time check, independent of what any actual LAS file
# declares.
_CONVERSION_UNIT_SIGNATURES: Dict[str, Tuple[FrozenSet[str], str]] = {
    "us_per_ft_to_m_per_s": (frozenset({"us/ft"}), "m/s"),
    "m_per_s_to_us_per_ft": (frozenset({"m/s"}), "us/ft"),
    "gcc_to_kgm3": (frozenset({"g/cc"}), "kg/m3"),
    "kgm3_to_gcc": (frozenset({"kg/m3"}), "g/cc"),
    "feet_to_meters": (frozenset({"ft"}), "m"),
    "meters_to_feet": (frozenset({"m"}), "ft"),
}

_REQUIRED_FILE_FIELDS = (
    "expected_sha256",
    "expected_well_identifier",
    "expected_las_version",
    "expected_wrap",
    "expected_null_value",
    "expected_curve_count",
    "expected_data_layout",
    "curves",
)
_REQUIRED_CURVE_FIELDS = (
    "ordinal",
    "source_curve_name",
    "raw_unit",
    "raw_description",
    "raw_canonical_name",
    "canonical_name",
    "canonical_unit",
    "required",
    "conversion_function",
)


# ---------------------------------------------------------------------------
# Definition-line parsing (LAS "MNEM.UNIT  VALUE  :DESCRIPTION" convention)
# ---------------------------------------------------------------------------
def _parse_definition_line(line: str) -> DefinitionLine:
    """
    Parse one LAS definition line into (mnemonic, unit, value, description).

    The LAS 2.0 convention is ``MNEM.UNIT<ws>VALUE/NAME<ws>:DESCRIPTION``,
    where UNIT occupies the characters immediately after the '.' up to the
    first whitespace - critically, if the '.' is immediately followed by
    whitespace, the unit field is EMPTY and everything up to the colon
    (which may itself contain internal spaces, e.g. a well name) is the
    value, not a unit-plus-value pair. Getting this rule wrong is exactly
    the kind of silent misparse this module is designed to avoid, since
    several of these files declare well/company names with no unit field.
    """
    if "." not in line:
        raise LasParsingError(
            f"Malformed LAS definition line (no '.' separating mnemonic from unit): {line!r}"
        )
    mnem_part, rest = line.split(".", 1)
    mnemonic = mnem_part.strip()

    if ":" in rest:
        pre_colon, desc_part = rest.split(":", 1)
        description = desc_part.strip()
    else:
        pre_colon = rest
        description = ""

    if pre_colon == "":
        unit, value = "", ""
    elif pre_colon[0].isspace():
        # '.' immediately followed by whitespace => empty unit field;
        # everything before the colon (stripped) is the value.
        unit = ""
        value = pre_colon.strip()
    else:
        parts = pre_colon.split(None, 1)
        unit = parts[0]
        value = parts[1].strip() if len(parts) > 1 else ""

    return DefinitionLine(mnemonic=mnemonic, unit=unit, value=value, description=description)


def _parse_description_ordinal_name(description: str) -> Tuple[Optional[int], Optional[str]]:
    """
    Extract an embedded "<ordinal> <NAME>" pattern from a curve description
    (e.g. "1 DCAV" -> (1, "DCAV")), if present. Returns (None, None) when
    the description does not follow this pattern - callers must not treat
    the absence of this pattern as an error by itself, only as one fewer
    corroborating signal available for resolution.
    """
    m = _DESC_ORDINAL_RE.match(description)
    if not m:
        return None, None
    return int(m.group(1)), m.group(2).strip()


def _find_by_mnemonic(lines: Tuple[DefinitionLine, ...], mnemonic: str) -> Optional[DefinitionLine]:
    for d in lines:
        if d.mnemonic.strip().upper() == mnemonic.upper():
            return d
    return None


def _to_float_or_none(d: Optional[DefinitionLine]) -> Optional[float]:
    if d is None or d.value.strip() == "":
        return None
    try:
        return float(d.value)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Header parsing (Version / Well / Curve / Parameter sections only)
# ---------------------------------------------------------------------------
def parse_las_header(path: str) -> LasHeaderInfo:
    """
    Parse a LAS file's Version, Well, Curve, and Parameter sections and
    compute its SHA-256, WITHOUT reading the ~Ascii data section.

    Section boundaries are detected from lines beginning with '~' (after
    stripping leading whitespace); the section kind is the first letter
    following '~', uppercased (V/W/C/P/O/A). Parsing stops as soon as the
    'A' (Ascii data) section marker is reached - original header order is
    preserved exactly as encountered, and nothing after the first comment
    or section marker is reordered or deduplicated.

    Raises
    ------
    LasFileNotFoundError
        If `path` does not exist.
    LasParsingError
        If a definition line cannot be parsed, or no data-section marker
        is found at all.
    """
    p = Path(path)
    if not p.exists():
        raise LasFileNotFoundError(f"LAS file not found: {path}")

    raw_bytes = p.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    text = raw_bytes.decode("utf-8", errors="strict")
    lines = text.splitlines()

    version_lines: List[DefinitionLine] = []
    well_lines: List[DefinitionLine] = []
    param_lines: List[DefinitionLine] = []
    curve_def_lines: List[DefinitionLine] = []

    section: Optional[str] = None
    data_start_idx: Optional[int] = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("~"):
            key = stripped[1:2].upper()
            section = key
            if key == "A":
                data_start_idx = i + 1
                break
            continue
        if stripped == "" or stripped.startswith("#"):
            continue
        if section == "V":
            version_lines.append(_parse_definition_line(line))
        elif section == "W":
            well_lines.append(_parse_definition_line(line))
        elif section == "C":
            curve_def_lines.append(_parse_definition_line(line))
        elif section == "P":
            param_lines.append(_parse_definition_line(line))
        # section == "O" (Other) or None: intentionally not modeled;
        # this project's files carry no content there.

    if data_start_idx is None:
        raise LasParsingError(f"{p.name}: no '~A' (Ascii data) section marker found.")

    curve_headers: List[CurveHeaderEntry] = []
    for ordinal, d in enumerate(curve_def_lines):
        desc_ordinal, desc_name = _parse_description_ordinal_name(d.description)
        curve_headers.append(
            CurveHeaderEntry(
                ordinal=ordinal,
                raw_mnemonic=d.mnemonic,
                raw_unit=d.unit,
                raw_api_code=d.value,
                raw_description=d.description,
                description_ordinal=desc_ordinal,
                description_name=desc_name,
            )
        )

    vers_line = _find_by_mnemonic(tuple(version_lines), "VERS")
    wrap_line = _find_by_mnemonic(tuple(version_lines), "WRAP")
    well_line = _find_by_mnemonic(tuple(well_lines), "WELL")
    null_line = _find_by_mnemonic(tuple(well_lines), "NULL")
    strt_line = _find_by_mnemonic(tuple(well_lines), "STRT")
    stop_line = _find_by_mnemonic(tuple(well_lines), "STOP")
    step_line = _find_by_mnemonic(tuple(well_lines), "STEP")

    return LasHeaderInfo(
        source_path=str(p),
        source_filename=p.name,
        sha256=sha256,
        las_version=vers_line.value if vers_line and vers_line.value else None,
        wrap=wrap_line.value if wrap_line and wrap_line.value else None,
        well_name=well_line.value if well_line and well_line.value else None,
        declared_null=_to_float_or_none(null_line),
        declared_strt=_to_float_or_none(strt_line),
        declared_stop=_to_float_or_none(stop_line),
        declared_step=_to_float_or_none(step_line),
        version_section=tuple(version_lines),
        well_section=tuple(well_lines),
        parameter_section=tuple(param_lines),
        curve_headers=tuple(curve_headers),
        data_section_line_offset=data_start_idx,
    )


# ---------------------------------------------------------------------------
# Ascii data-section parsing
# ---------------------------------------------------------------------------
def _read_ascii_data(path: str, header: LasHeaderInfo) -> np.ndarray:
    """
    Parse the ~Ascii data section into a float64 matrix of shape
    (n_samples, n_curves), exactly as written in the file (no NULL
    substitution here - see `_apply_null_sentinel`).

    Raises
    ------
    LasParsingError
        If any data row's column count does not match the number of
        declared curves, if any token cannot be parsed as a number, if
        any token DOES parse but to a non-finite value (a literal "nan"/
        "inf"/"-inf" text - Increment 2.1: this project's NULL policy is
        a single finite sentinel, so a non-finite literal is a structural
        defect, never silently treated as that sentinel), or if no data
        rows are found at all. The error message names the exact line
        number, column, and offending content.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines()
    n_curves = len(header.curve_headers)

    rows: List[List[float]] = []
    for lineno, line in enumerate(lines[header.data_section_line_offset :], start=header.data_section_line_offset + 1):
        if line.strip() == "":
            continue
        tokens = line.split()
        if len(tokens) != n_curves:
            raise LasParsingError(
                f"{header.source_filename}: line {lineno} has {len(tokens)} data column(s), "
                f"but {n_curves} curve(s) are declared in the ~Curve section "
                f"(curve/data-column width mismatch). Line content: {line!r}"
            )
        row: List[float] = []
        for col_idx, token in enumerate(tokens):
            try:
                value = float(token)
            except ValueError as exc:
                raise LasParsingError(
                    f"{header.source_filename}: malformed numeric value at line {lineno}, "
                    f"column {col_idx}: {token!r} ({exc})"
                ) from exc
            if not math.isfinite(value):
                raise LasParsingError(
                    f"{header.source_filename}: line {lineno}, column {col_idx} contains a literal "
                    f"non-finite numeric token {token!r} (parses to {value!r}). This project's NULL "
                    f"policy is a single finite sentinel value declared in the file's ~Well section - "
                    f"a literal NaN/Inf token is never treated as that sentinel and is rejected here "
                    f"as a structural defect rather than silently substituted or clipped."
                )
            row.append(value)
        rows.append(row)

    if not rows:
        raise LasParsingError(f"{header.source_filename}: no data rows found in the ~Ascii data section.")

    return np.array(rows, dtype=np.float64)


def _apply_null_sentinel(raw_column: np.ndarray, declared_null: Optional[float]) -> np.ndarray:
    """
    Return a copy of `raw_column` with values matching `declared_null`
    (within `_NULL_TOLERANCE`) replaced by NaN. No other value is ever
    replaced, regardless of how extreme it looks - an out-of-range but
    non-null value is a fact about the data to report via `CurveStats`,
    never a value to silently discard.
    """
    out = raw_column.astype(np.float64, copy=True)
    if declared_null is None:
        return out
    mask = np.abs(out - declared_null) <= _NULL_TOLERANCE
    out[mask] = np.nan
    return out


# ---------------------------------------------------------------------------
# Contract-authoring validation helpers (Increment 2.1)
# ---------------------------------------------------------------------------
def _validate_conversion_unit_compatibility(
    conversion_function: str, raw_unit: str, canonical_unit: str, context: str
) -> None:
    """
    Reject, at contract-load time, a `conversion_function` whose declared
    raw/canonical units are incompatible with the controlled conversion-
    signature registry (`_CONVERSION_UNIT_SIGNATURES`). For example, a
    contract must not be able to pair `gcc_to_kgm3` with a raw_unit of
    "API" - the function's registered signature is g/cc -> kg/m3 only.
    """
    if conversion_function == _IDENTITY_CONVERSION:
        if raw_unit.strip().lower() != canonical_unit.strip().lower():
            raise LasContractDefinitionError(
                f"{context}: conversion_function 'identity' requires raw_unit and canonical_unit to "
                f"be the same physical unit; contract declares raw_unit={raw_unit!r}, "
                f"canonical_unit={canonical_unit!r}."
            )
        return

    signature = _CONVERSION_UNIT_SIGNATURES.get(conversion_function)
    if signature is None:
        # Unreachable in practice (caller already validated membership in
        # _KNOWN_CONVERSION_NAMES), but fail loudly rather than silently
        # skipping validation if the registries ever drift apart.
        raise LasContractDefinitionError(
            f"{context}: conversion_function {conversion_function!r} has no registered unit signature."
        )
    expected_raw_units, expected_canonical_unit = signature
    if raw_unit.strip().lower() not in expected_raw_units:
        raise LasContractDefinitionError(
            f"{context}: conversion_function {conversion_function!r} expects raw_unit in "
            f"{sorted(expected_raw_units)}; contract declares raw_unit={raw_unit!r}. A contract must "
            f"not pair a conversion function with an incompatible source unit."
        )
    if canonical_unit.strip().lower() != expected_canonical_unit:
        raise LasContractDefinitionError(
            f"{context}: conversion_function {conversion_function!r} produces canonical_unit "
            f"{expected_canonical_unit!r}; contract declares canonical_unit={canonical_unit!r}."
        )


# ---------------------------------------------------------------------------
# Curve-contract configuration (config/las_curve_contracts.yml)
# ---------------------------------------------------------------------------
def load_file_contract_config(yaml_path: str) -> Dict[str, FileContract]:
    """
    Load and validate `config/las_curve_contracts.yml`, returning a
    mapping of source filename -> `FileContract`.

    Validates, at load time (before any LAS file is touched):
    * the YAML parses and has a top-level `files` mapping;
    * every required file-level and curve-level field is present
      (Increment 2.1 requires several new fields - see
      `_REQUIRED_FILE_FIELDS` / `_REQUIRED_CURVE_FIELDS`);
    * `expected_las_version`, `expected_wrap`, and `expected_data_layout`
      each name something this parser actually implements - never a mode
      it would silently mishandle;
    * `expected_null_value` is numeric and `expected_curve_count` is an
      integer matching the number of curve entries actually listed;
    * every curve ordinal is a non-negative integer, unique within the
      file, and the full ordinal set is contiguous from 0 unless the file
      explicitly sets `ordinal_gaps_justified: true` with a non-empty
      `ordinal_gap_notes`;
    * no two curve entries within the same file map to the same
      `canonical_name` (a "duplicate canonical target" contract-authoring
      bug);
    * `required` is a genuine boolean (not a truthy string or number);
    * every non-identity `conversion_function` name is one of the exact,
      unit-only conversions this module recognizes, AND is compatible
      with the entry's declared raw_unit/canonical_unit per the
      conversion-signature registry;
    * exactly one curve per file declares `semantic_role: measured_depth`,
      and that curve's `source_curve_name` is "DEPT"/"Depth", its
      `canonical_name` is "MD_m", its `canonical_unit` is "m", and it is
      `required`.

    Raises
    ------
    LasContractDefinitionError
        On any of the above validation failures, or if the file is
        missing / not valid YAML.
    """
    p = Path(yaml_path)
    if not p.exists():
        raise LasContractDefinitionError(f"Curve contract file not found: {yaml_path}")

    try:
        with p.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise LasContractDefinitionError(f"{yaml_path}: not valid YAML ({exc})") from exc

    if not raw or "files" not in raw or not isinstance(raw["files"], dict):
        raise LasContractDefinitionError(f"{yaml_path}: expected a top-level 'files' mapping.")

    contracts: Dict[str, FileContract] = {}
    for filename, file_def in raw["files"].items():
        if not isinstance(file_def, dict):
            raise LasContractDefinitionError(f"{yaml_path}: entry for {filename!r} must be a mapping.")

        missing_file_fields = [field for field in _REQUIRED_FILE_FIELDS if field not in file_def]
        if missing_file_fields:
            raise LasContractDefinitionError(
                f"{yaml_path}: file {filename!r} is missing required field(s): {missing_file_fields}."
            )

        expected_las_version = str(file_def["expected_las_version"])
        if expected_las_version not in _SUPPORTED_LAS_VERSIONS:
            raise LasContractDefinitionError(
                f"{yaml_path}: file {filename!r} declares expected_las_version={expected_las_version!r}, "
                f"which this parser does not implement (supported: {sorted(_SUPPORTED_LAS_VERSIONS)}). "
                f"Refusing to pretend support for an unimplemented LAS version."
            )
        expected_wrap = str(file_def["expected_wrap"])
        if expected_wrap not in _SUPPORTED_WRAP_VALUES:
            raise LasContractDefinitionError(
                f"{yaml_path}: file {filename!r} declares expected_wrap={expected_wrap!r}, which this "
                f"parser does not implement (supported: {sorted(_SUPPORTED_WRAP_VALUES)} - unwrapped "
                f"LAS only). Refusing to pretend support for wrapped LAS parsing."
            )
        expected_data_layout = str(file_def["expected_data_layout"])
        if expected_data_layout not in _SUPPORTED_DATA_LAYOUTS:
            raise LasContractDefinitionError(
                f"{yaml_path}: file {filename!r} declares expected_data_layout={expected_data_layout!r}, "
                f"which this parser does not implement (supported: {sorted(_SUPPORTED_DATA_LAYOUTS)})."
            )

        expected_null_value = file_def["expected_null_value"]
        if isinstance(expected_null_value, bool) or not isinstance(expected_null_value, (int, float)):
            raise LasContractDefinitionError(
                f"{yaml_path}: file {filename!r} has a non-numeric expected_null_value="
                f"{expected_null_value!r}."
            )

        expected_curve_count = file_def["expected_curve_count"]
        if isinstance(expected_curve_count, bool) or not isinstance(expected_curve_count, int):
            raise LasContractDefinitionError(
                f"{yaml_path}: file {filename!r} has a non-integer expected_curve_count="
                f"{expected_curve_count!r}."
            )

        curve_defs = file_def.get("curves")
        if not isinstance(curve_defs, list) or not curve_defs:
            raise LasContractDefinitionError(
                f"{yaml_path}: file {filename!r} has an empty or missing 'curves' list."
            )
        if len(curve_defs) != expected_curve_count:
            raise LasContractDefinitionError(
                f"{yaml_path}: file {filename!r} declares expected_curve_count={expected_curve_count} "
                f"but lists {len(curve_defs)} curve entries - the contract is internally inconsistent."
            )

        curves: List[CurveContractEntry] = []
        seen_canonical: set = set()
        seen_ordinals: set = set()
        measured_depth_count = 0

        for c in curve_defs:
            if not isinstance(c, dict):
                raise LasContractDefinitionError(
                    f"{yaml_path}: file {filename!r} has a curve entry that is not a mapping."
                )

            missing = [field for field in _REQUIRED_CURVE_FIELDS if field not in c]
            if missing:
                raise LasContractDefinitionError(
                    f"{yaml_path}: file {filename!r} has a curve entry missing required field(s): {missing}."
                )

            ordinal = c["ordinal"]
            if isinstance(ordinal, bool) or not isinstance(ordinal, int):
                raise LasContractDefinitionError(
                    f"{yaml_path}: file {filename!r} has a non-integer ordinal {ordinal!r}."
                )
            if ordinal < 0:
                raise LasContractDefinitionError(
                    f"{yaml_path}: file {filename!r} has a negative ordinal {ordinal!r}, which is not "
                    f"a valid column position."
                )
            if ordinal in seen_ordinals:
                raise LasContractDefinitionError(
                    f"{yaml_path}: file {filename!r} declares ordinal {ordinal} more than once "
                    f"(duplicate ordinal)."
                )
            seen_ordinals.add(ordinal)

            canonical_name = c["canonical_name"]
            if canonical_name in seen_canonical:
                raise LasContractDefinitionError(
                    f"{yaml_path}: file {filename!r} maps more than one curve to canonical name "
                    f"{canonical_name!r} (duplicate canonical target)."
                )
            seen_canonical.add(canonical_name)

            required_flag = c["required"]
            if not isinstance(required_flag, bool):
                raise LasContractDefinitionError(
                    f"{yaml_path}: file {filename!r} curve {canonical_name!r} has a non-boolean "
                    f"'required' value {required_flag!r}."
                )

            conv_name = c["conversion_function"]
            if conv_name not in _KNOWN_CONVERSION_NAMES:
                raise LasContractDefinitionError(
                    f"{yaml_path}: file {filename!r} curve {canonical_name!r} names unknown "
                    f"conversion_function {conv_name!r}. Allowed: {sorted(_KNOWN_CONVERSION_NAMES)}."
                )

            raw_unit = str(c["raw_unit"])
            canonical_unit = str(c["canonical_unit"])
            _validate_conversion_unit_compatibility(
                conv_name, raw_unit, canonical_unit, context=f"{yaml_path}: {filename}:{canonical_name}"
            )

            semantic_role = c.get("semantic_role", SEMANTIC_ROLE_MEASUREMENT)
            if semantic_role not in (SEMANTIC_ROLE_MEASURED_DEPTH, SEMANTIC_ROLE_MEASUREMENT):
                raise LasContractDefinitionError(
                    f"{yaml_path}: file {filename!r} curve {canonical_name!r} has unknown "
                    f"semantic_role {semantic_role!r}."
                )
            if semantic_role == SEMANTIC_ROLE_MEASURED_DEPTH:
                measured_depth_count += 1

            curves.append(
                CurveContractEntry(
                    ordinal=ordinal,
                    semantic_role=semantic_role,
                    source_curve_name=str(c["source_curve_name"]),
                    raw_mnemonic=str(c.get("raw_mnemonic", "")),
                    raw_unit=raw_unit,
                    raw_description=str(c["raw_description"]),
                    description_ordinal=c.get("description_ordinal"),
                    description_name=c.get("description_name"),
                    raw_canonical_name=str(c["raw_canonical_name"]),
                    canonical_name=canonical_name,
                    canonical_unit=canonical_unit,
                    required=required_flag,
                    conversion_function=conv_name,
                    notes=str(c.get("notes", "")),
                )
            )

        # Ordinal contiguity: unless explicitly justified, ordinals must be
        # exactly {0, 1, ..., expected_curve_count - 1}. A gap most often
        # means a contract-authoring mistake (a curve entry skipped or
        # mis-numbered), not a deliberate design, so it is rejected unless
        # the file explicitly says otherwise and explains why.
        expected_ordinal_set = set(range(expected_curve_count))
        if seen_ordinals != expected_ordinal_set:
            if not bool(file_def.get("ordinal_gaps_justified", False)):
                raise LasContractDefinitionError(
                    f"{yaml_path}: file {filename!r} has ordinals {sorted(seen_ordinals)}, which are "
                    f"not contiguous from 0 (expected {sorted(expected_ordinal_set)}). If this is "
                    f"deliberate, set 'ordinal_gaps_justified: true' and explain why in "
                    f"'ordinal_gap_notes'."
                )
            if not str(file_def.get("ordinal_gap_notes", "")).strip():
                raise LasContractDefinitionError(
                    f"{yaml_path}: file {filename!r} sets ordinal_gaps_justified but has no "
                    f"'ordinal_gap_notes' explaining the gap."
                )

        if measured_depth_count == 0:
            raise LasContractDefinitionError(
                f"{yaml_path}: file {filename!r} declares no curve with "
                f"semantic_role='{SEMANTIC_ROLE_MEASURED_DEPTH}'. Exactly one curve must be declared "
                f"as the measured-depth role; it is never inferred from a canonical name."
            )
        if measured_depth_count > 1:
            raise LasContractDefinitionError(
                f"{yaml_path}: file {filename!r} declares {measured_depth_count} curves with "
                f"semantic_role='{SEMANTIC_ROLE_MEASURED_DEPTH}'; exactly one is required."
            )

        depth_entry = next(c for c in curves if c.semantic_role == SEMANTIC_ROLE_MEASURED_DEPTH)
        if depth_entry.source_curve_name.strip().upper() not in ("DEPT", "DEPTH"):
            raise LasContractDefinitionError(
                f"{yaml_path}: file {filename!r}'s measured-depth curve has source_curve_name="
                f"{depth_entry.source_curve_name!r}; expected 'DEPT' or 'Depth'."
            )
        if depth_entry.canonical_name != "MD_m":
            raise LasContractDefinitionError(
                f"{yaml_path}: file {filename!r}'s measured-depth curve must have canonical_name "
                f"'MD_m'; found {depth_entry.canonical_name!r}."
            )
        if depth_entry.canonical_unit.strip().lower() != "m":
            raise LasContractDefinitionError(
                f"{yaml_path}: file {filename!r}'s measured-depth curve must have canonical_unit "
                f"'m' (metres); found {depth_entry.canonical_unit!r}."
            )
        if not depth_entry.required:
            raise LasContractDefinitionError(
                f"{yaml_path}: file {filename!r}'s measured-depth curve must be required=true."
            )

        contracts[filename] = FileContract(
            source_filename=filename,
            expected_sha256=str(file_def["expected_sha256"]),
            expected_well_identifier=str(file_def["expected_well_identifier"]),
            expected_las_version=expected_las_version,
            expected_wrap=expected_wrap,
            expected_null_value=float(expected_null_value),
            expected_curve_count=int(expected_curve_count),
            expected_data_layout=expected_data_layout,
            curves=tuple(curves),
        )

    return contracts


# ---------------------------------------------------------------------------
# Contract resolution
# ---------------------------------------------------------------------------
def resolve_curve_contract(
    header: LasHeaderInfo, contract: FileContract
) -> Tuple[Tuple[CurveResolution, ...], Tuple[IngestionIssue, ...], str]:
    """
    Attempt to resolve every curve in `contract` against the curves
    actually present in `header`, WITHOUT reading any numeric data.

    Increment 2.1 adds a block of FILE-IDENTITY checks, run before any
    curve is resolved, that an independent audit found Increment 2 did
    not perform (the resolver previously "passed" a file with a missing
    WELL, a missing NULL, a changed VERS/WRAP, or a contract for an
    entirely different file than the one being loaded): the loaded file's
    basename must match `contract.source_filename`; its SHA-256 must
    match `contract.expected_sha256`; it must declare a WELL value
    matching `contract.expected_well_identifier`; it must declare a
    supported, contract-matching VERS and WRAP; and it must declare a
    NULL value matching `contract.expected_null_value` (a NULL mismatch
    is an ERROR, not a warning, because it changes which samples are
    substituted to NaN). Every one of these is blocking.

    Curve-level resolution (unchanged from Increment 2): a contract entry
    resolves only when the curve found at its declared `ordinal` has both
    the expected `raw_unit` AND (when the header curve carries an
    embedded description ordinal/name) matching `description_ordinal`/
    `description_name`, AND, when the contract declares a non-empty
    `raw_mnemonic`, a matching mnemonic. Ordinal position is never, by
    itself, treated as sufficient.

    Also performs file-level checks independent of any single curve:
    duplicate raw curve descriptions (which would make description-based
    disambiguation unsafe) and the file's declared curve count against
    the contract's `expected_curve_count`.

    Returns
    -------
    (resolutions, issues, status) where `status` is "PASSED" if no
    ERROR-severity issue or FAILED resolution was found, else "FAILED".
    This function never raises for a data-content problem (only
    `load_las_file` raises, after also considering the numeric data) -
    it is used standalone by the "validate contract before loading"
    notebook step.
    """
    issues: List[IngestionIssue] = []
    resolutions: List[CurveResolution] = []

    # --- File-identity checks (Increment 2.1 correction) ---------------
    if header.source_filename != contract.source_filename:
        issues.append(
            IngestionIssue(
                severity="ERROR",
                code="FILENAME_MISMATCH",
                message=(
                    f"File being loaded is named {header.source_filename!r}, but this contract is "
                    f"declared for {contract.source_filename!r}. Refusing to apply a contract "
                    f"authored for a different file."
                ),
                context=header.source_filename,
            )
        )

    if header.sha256 != contract.expected_sha256:
        issues.append(
            IngestionIssue(
                severity="ERROR",
                code="SHA256_MISMATCH",
                message=(
                    f"File SHA-256 is {header.sha256!r}; contract expects "
                    f"{contract.expected_sha256!r}. The file's content does not match what this "
                    f"contract was authored against."
                ),
                context=header.source_filename,
            )
        )

    if header.well_name is None:
        issues.append(
            IngestionIssue(
                severity="ERROR",
                code="WELL_MISSING",
                message="File declares no WELL value in its ~Well section; cannot verify well identity.",
                context=header.source_filename,
            )
        )
    elif contract.expected_well_identifier.strip() != header.well_name.strip():
        issues.append(
            IngestionIssue(
                severity="ERROR",
                code="WELL_IDENTIFIER_MISMATCH",
                message=(
                    f"Contract expects WELL={contract.expected_well_identifier!r}; file declares "
                    f"WELL={header.well_name!r}."
                ),
                context=header.source_filename,
            )
        )

    if header.las_version is None:
        issues.append(
            IngestionIssue(
                severity="ERROR",
                code="VERS_MISSING",
                message="File declares no VERS value in its ~Version section; cannot verify LAS version.",
                context=header.source_filename,
            )
        )
    elif header.las_version not in _SUPPORTED_LAS_VERSIONS:
        issues.append(
            IngestionIssue(
                severity="ERROR",
                code="VERS_UNSUPPORTED",
                message=(
                    f"File declares VERS={header.las_version!r}, which this parser does not "
                    f"implement (supported: {sorted(_SUPPORTED_LAS_VERSIONS)})."
                ),
                context=header.source_filename,
            )
        )
    elif header.las_version != contract.expected_las_version:
        issues.append(
            IngestionIssue(
                severity="ERROR",
                code="VERS_MISMATCH",
                message=(
                    f"Contract expects VERS={contract.expected_las_version!r}; file declares "
                    f"VERS={header.las_version!r}."
                ),
                context=header.source_filename,
            )
        )

    if header.wrap is None:
        issues.append(
            IngestionIssue(
                severity="ERROR",
                code="WRAP_MISSING",
                message="File declares no WRAP value in its ~Version section; cannot verify data layout.",
                context=header.source_filename,
            )
        )
    elif header.wrap not in _SUPPORTED_WRAP_VALUES:
        issues.append(
            IngestionIssue(
                severity="ERROR",
                code="WRAP_UNSUPPORTED",
                message=(
                    f"File declares WRAP={header.wrap!r}. This parser implements unwrapped "
                    f"(WRAP=NO), whitespace-delimited LAS data only; wrapped or other layouts are "
                    f"explicitly rejected rather than silently misread."
                ),
                context=header.source_filename,
            )
        )
    elif header.wrap != contract.expected_wrap:
        issues.append(
            IngestionIssue(
                severity="ERROR",
                code="WRAP_MISMATCH",
                message=(
                    f"Contract expects WRAP={contract.expected_wrap!r}; file declares "
                    f"WRAP={header.wrap!r}."
                ),
                context=header.source_filename,
            )
        )

    if header.declared_null is None:
        issues.append(
            IngestionIssue(
                severity="ERROR",
                code="NULL_MISSING",
                message="File declares no NULL value in its ~Well section; NULL-sentinel substitution cannot be safely performed.",
                context=header.source_filename,
            )
        )
    elif abs(contract.expected_null_value - header.declared_null) > _NULL_TOLERANCE:
        issues.append(
            IngestionIssue(
                severity="ERROR",
                code="NULL_MISMATCH",
                message=(
                    f"Contract expects NULL={contract.expected_null_value}; file declares "
                    f"NULL={header.declared_null}. A NULL-value mismatch changes which samples are "
                    f"substituted to NaN and is treated as blocking, not advisory."
                ),
                context=header.source_filename,
            )
        )

    # --- File-level structural checks (unchanged from Increment 2) -----
    desc_positions: Dict[str, List[int]] = {}
    for ch in header.curve_headers:
        key = ch.raw_description.strip()
        if key == "":
            continue
        desc_positions.setdefault(key, []).append(ch.ordinal)
    for desc, ordinals in desc_positions.items():
        if len(ordinals) > 1:
            issues.append(
                IngestionIssue(
                    severity="ERROR",
                    code="DUPLICATE_RAW_DESCRIPTION",
                    message=(
                        f"Curve description {desc!r} appears at ordinals {ordinals}; "
                        f"curve identity cannot be safely disambiguated by description."
                    ),
                    context=header.source_filename,
                )
            )

    if contract.expected_curve_count != len(header.curve_headers):
        issues.append(
            IngestionIssue(
                severity="ERROR",
                code="CURVE_COUNT_MISMATCH",
                message=(
                    f"Contract expects {contract.expected_curve_count} curves; the file's "
                    f"~Curve section declares {len(header.curve_headers)}."
                ),
                context=header.source_filename,
            )
        )

    # --- Curve-level resolution (unchanged logic; names updated) -------
    by_ordinal = {ch.ordinal: ch for ch in header.curve_headers}

    for entry in contract.curves:
        header_entry = by_ordinal.get(entry.ordinal)

        if header_entry is None:
            if entry.required:
                issues.append(
                    IngestionIssue(
                        severity="ERROR",
                        code="CURVE_NOT_FOUND",
                        message=(
                            f"No curve found at ordinal {entry.ordinal} for required curve "
                            f"{entry.source_curve_name!r} (canonical {entry.canonical_name!r})."
                        ),
                        context=header.source_filename,
                    )
                )
                status = "FAILED"
            else:
                status = "MISSING_OPTIONAL"
            resolutions.append(
                CurveResolution(
                    canonical_name=entry.canonical_name,
                    source_curve_name=entry.source_curve_name,
                    status=status,
                    ordinal=entry.ordinal,
                    matched_raw_mnemonic=None,
                    matched_raw_unit=None,
                    matched_raw_description=None,
                    conversion_applied=None,
                    detail="No header entry found at the contract's declared ordinal.",
                )
            )
            continue

        mismatches: List[str] = []

        if entry.raw_mnemonic.strip() != "" and header_entry.raw_mnemonic.strip() != entry.raw_mnemonic.strip():
            mismatches.append(
                f"mnemonic: contract expects {entry.raw_mnemonic!r}, file has {header_entry.raw_mnemonic!r}"
            )

        if header_entry.raw_unit.strip() != entry.raw_unit.strip():
            mismatches.append(f"unit: contract expects {entry.raw_unit!r}, file has {header_entry.raw_unit!r}")

        if entry.description_ordinal is not None and header_entry.description_ordinal != entry.description_ordinal:
            mismatches.append(
                f"description ordinal: contract expects {entry.description_ordinal!r}, "
                f"file has {header_entry.description_ordinal!r}"
            )

        if entry.description_name is not None:
            found_name = (header_entry.description_name or "").upper()
            if found_name != entry.description_name.upper():
                mismatches.append(
                    f"description name: contract expects {entry.description_name!r}, "
                    f"file has {header_entry.description_name!r}"
                )

        # File-internal self-consistency: an empty-mnemonic curve's own
        # embedded description ordinal (when present) must match its
        # physical column position. This check exists so that ordinal
        # position is never the ONLY thing standing behind a resolution -
        # the file's own description must independently agree with where
        # it physically sits.
        if header_entry.description_ordinal is not None and header_entry.description_ordinal != header_entry.ordinal:
            mismatches.append(
                f"file-internal inconsistency: description ordinal {header_entry.description_ordinal} "
                f"does not match this curve's physical column position {header_entry.ordinal}"
            )

        if mismatches:
            issues.append(
                IngestionIssue(
                    severity="ERROR",
                    code="CURVE_IDENTITY_MISMATCH",
                    message=(
                        f"{entry.source_curve_name} / {entry.canonical_name} (ordinal {entry.ordinal}): "
                        + "; ".join(mismatches)
                    ),
                    context=header.source_filename,
                )
            )
            resolutions.append(
                CurveResolution(
                    canonical_name=entry.canonical_name,
                    source_curve_name=entry.source_curve_name,
                    status="FAILED",
                    ordinal=entry.ordinal,
                    matched_raw_mnemonic=None,
                    matched_raw_unit=None,
                    matched_raw_description=None,
                    conversion_applied=None,
                    detail="; ".join(mismatches),
                )
            )
        else:
            agreed = ["ordinal", "unit"]
            if entry.description_ordinal is not None:
                agreed.append("description ordinal")
            if entry.description_name is not None:
                agreed.append("description name")
            if entry.raw_mnemonic.strip():
                agreed.append("mnemonic")
            resolutions.append(
                CurveResolution(
                    canonical_name=entry.canonical_name,
                    source_curve_name=entry.source_curve_name,
                    status="RESOLVED",
                    ordinal=entry.ordinal,
                    matched_raw_mnemonic=header_entry.raw_mnemonic,
                    matched_raw_unit=header_entry.raw_unit,
                    matched_raw_description=header_entry.raw_description,
                    conversion_applied=entry.conversion_function,
                    detail="Agreement confirmed on: " + ", ".join(agreed) + ".",
                )
            )

    has_error = any(i.severity == "ERROR" for i in issues) or any(r.status == "FAILED" for r in resolutions)
    status = "FAILED" if has_error else "PASSED"
    return tuple(resolutions), tuple(issues), status


# ---------------------------------------------------------------------------
# Depth and curve diagnostics
# ---------------------------------------------------------------------------
def compute_depth_diagnostics(
    md: np.ndarray,
    declared_strt: Optional[float],
    declared_stop: Optional[float],
    declared_step: Optional[float],
) -> DepthDiagnostics:
    """
    Compute data-derived depth-index diagnostics and compare them against
    the file's declared STRT/STOP/STEP header values.

    `md` must be the raw (NOT NULL-substituted) measured-depth column -
    depth is an index, never subject to NULL-sentinel treatment, and (see
    `load_las_file`) is required to be entirely finite before this
    function is called. Duplicate and non-monotonic samples are DETECTED
    and reported here; per the Increment 2 specification this function
    never raises for them (they are not on the "reject" list) - only
    `resolve_curve_contract` / `load_las_file`'s ERROR-severity issues
    stop ingestion.
    """
    md = np.asarray(md, dtype=np.float64)
    diffs = np.diff(md)
    n_duplicate = int(np.sum(diffs == 0.0))
    n_non_monotonic = int(np.sum(diffs < 0.0))

    data_start = float(md[0]) if md.size else float("nan")
    data_stop = float(md[-1]) if md.size else float("nan")
    data_min_step = float(np.min(diffs)) if diffs.size else float("nan")
    data_max_step = float(np.max(diffs)) if diffs.size else float("nan")
    data_median_step = float(np.median(diffs)) if diffs.size else float("nan")

    def _close(declared: Optional[float], derived: float, tol: float) -> Optional[bool]:
        if declared is None:
            return None
        return bool(abs(declared - derived) <= tol)

    return DepthDiagnostics(
        declared_strt=declared_strt,
        declared_stop=declared_stop,
        declared_step=declared_step,
        data_start=data_start,
        data_stop=data_stop,
        data_min_step=data_min_step,
        data_max_step=data_max_step,
        data_median_step=data_median_step,
        n_samples=int(md.size),
        n_duplicate_md=n_duplicate,
        n_non_monotonic=n_non_monotonic,
        strt_matches_declared=_close(declared_strt, data_start, _DEPTH_ENDPOINT_TOLERANCE_M),
        stop_matches_declared=_close(declared_stop, data_stop, _DEPTH_ENDPOINT_TOLERANCE_M),
        step_matches_declared=_close(declared_step, data_median_step, _DEPTH_STEP_TOLERANCE_M),
    )


def compute_curve_stats(
    entry: CurveContractEntry,
    raw_column: np.ndarray,
    canonical_column: np.ndarray,
    declared_null: Optional[float],
) -> CurveStats:
    """
    Compute descriptive (non-judgemental), unit-explicit statistics for
    one resolved curve.

    `raw_column` is the literal parsed column (from `LasFileResult.raw_data`
    at `entry.ordinal`), still containing the NULL sentinel wherever it
    occurs. `canonical_column` is the corresponding
    `LasFileResult.canonical_data[entry.canonical_name]` array (NULL-
    substituted to NaN, and exactly unit-converted if
    `entry.conversion_function != "identity"`).

    Increment 2.1 correction: Increment 2 computed a single min/max pair
    from the NULL-substituted-but-NOT-converted array and reported it
    under the canonical (post-conversion-implying) name with no unit
    field at all - so, for example, DTCO's coverage row showed numbers
    that were still in us/ft while being labeled with a name that implied
    m/s. This function now reports RAW and CANONICAL statistics
    separately, each tagged with its own explicit unit, so no number can
    be misread as being in the wrong unit.
    """
    raw_column = np.asarray(raw_column, dtype=np.float64)
    canonical_column = np.asarray(canonical_column, dtype=np.float64)
    n = int(raw_column.size)

    if declared_null is not None:
        null_mask = np.abs(raw_column - declared_null) <= _NULL_TOLERANCE
    else:
        null_mask = np.zeros(n, dtype=bool)
    valid_mask = ~null_mask
    valid_count = int(np.sum(valid_mask))
    null_count = n - valid_count
    valid_fraction = (valid_count / n) if n > 0 else 0.0

    if valid_count > 0:
        raw_min: Optional[float] = float(np.min(raw_column[valid_mask]))
        raw_max: Optional[float] = float(np.max(raw_column[valid_mask]))
        canonical_min: Optional[float] = float(np.nanmin(canonical_column))
        canonical_max: Optional[float] = float(np.nanmax(canonical_column))
    else:
        raw_min = raw_max = canonical_min = canonical_max = None

    display_mnemonic = entry.raw_mnemonic.strip() or f"(empty mnemonic, ordinal {entry.ordinal})"

    return CurveStats(
        source_curve_name=entry.source_curve_name,
        raw_mnemonic=display_mnemonic,
        raw_description=entry.raw_description,
        raw_unit=entry.raw_unit,
        canonical_name=entry.canonical_name,
        canonical_unit=entry.canonical_unit,
        conversion_function=entry.conversion_function,
        n_samples=n,
        valid_count=valid_count,
        null_count=null_count,
        valid_fraction=valid_fraction,
        raw_min=raw_min,
        raw_max=raw_max,
        canonical_min=canonical_min,
        canonical_max=canonical_max,
        statistics_basis=(
            f"valid_count/null_count/valid_fraction and min/max are computed over samples whose raw "
            f"value does NOT exactly match the file's declared NULL sentinel (tolerance "
            f"{_NULL_TOLERANCE:g}). raw_min/raw_max are in raw_unit, computed directly from the "
            f"unconverted raw column. canonical_min/canonical_max are in canonical_unit, computed "
            f"from the NULL-substituted array after any declared exact conversion "
            f"(conversion_function={entry.conversion_function!r})."
        ),
    )


def _apply_conversion(
    entry: CurveContractEntry,
    substituted: np.ndarray,
    source_filename: str,
    md_raw: Optional[np.ndarray],
) -> np.ndarray:
    """
    Apply `entry.conversion_function` to a NULL-substituted column,
    raising `LasConversionError` with full project context rather than
    letting a raw NumPy/`p2mem.units` exception escape, and rather than
    silently accepting a non-finite result for a non-null input value.
    """
    if entry.conversion_function == _IDENTITY_CONVERSION:
        return substituted

    conv_fn = _ALLOWED_CONVERSION_FUNCTIONS[entry.conversion_function]
    try:
        canonical = conv_fn(substituted)
    except Exception as exc:
        raise LasConversionError(
            f"{source_filename}: applying conversion_function {entry.conversion_function!r} to curve "
            f"{entry.source_curve_name!r} (canonical {entry.canonical_name!r}, expected canonical "
            f"unit {entry.canonical_unit!r}) raised {type(exc).__name__}: {exc}"
        ) from exc

    canonical = np.asarray(canonical, dtype=np.float64)
    # A non-null physical value must never silently convert to a
    # non-finite result (e.g. a zero sonic slowness -> infinite velocity).
    bad_mask = np.isinf(canonical) & ~np.isnan(substituted)
    if np.any(bad_mask):
        bad_idx = int(np.argmax(bad_mask))
        offending_raw = float(substituted[bad_idx])
        depth_note = ""
        if md_raw is not None and bad_idx < md_raw.size:
            depth_note = f" at row {bad_idx} (MD={float(md_raw[bad_idx])!r})"
        raise LasConversionError(
            f"{source_filename}: converting curve {entry.source_curve_name!r} (canonical "
            f"{entry.canonical_name!r}) via {entry.conversion_function!r} produced a non-finite "
            f"result{depth_note} from raw value {offending_raw!r} (expected canonical unit "
            f"{entry.canonical_unit!r}). This is not a NULL-sentinel row - the raw value is a real, "
            f"non-null measurement that the exact conversion cannot represent safely."
        )
    return canonical


# ---------------------------------------------------------------------------
# Top-level loader
# ---------------------------------------------------------------------------
def load_las_file(path: str, contract: FileContract) -> LasFileResult:
    """
    Fully load and contract-resolve one LAS file.

    Sequence: parse header -> resolve contract against header, including
    the Increment 2.1 file-identity checks (no data read yet) -> parse
    ~Ascii data -> cross-check data column count -> if any ERROR-severity
    issue exists at this point, raise `LasContractError` (ingestion stops;
    no data is returned) -> locate the contract's declared measured-depth
    curve (by `semantic_role`, never by searching for a canonical name
    "DEPT") and require its measured-depth column to be entirely finite
    -> compute depth diagnostics -> for every RESOLVED curve, apply NULL-
    sentinel substitution and, if the contract declares one, an exact
    `p2mem.units` conversion (raising `LasConversionError` with full
    context if that conversion cannot be applied safely), producing
    `canonical_data` - the raw column is separately preserved unchanged
    in `raw_data`.

    Raises
    ------
    LasFileNotFoundError, LasParsingError
        For file-access or structural parsing problems (see
        `parse_las_header` / `_read_ascii_data`).
    LasContractError
        If the file's header cannot be safely reconciled with `contract`
        (a file-identity mismatch, a required curve failed to resolve, a
        duplicate/ambiguous description was found, or the data section's
        column count does not match the contract).
    LasConversionError
        If a contract-declared exact unit conversion cannot be safely
        applied to a resolved curve's values.
    """
    header = parse_las_header(path)
    resolutions, issues, status = resolve_curve_contract(header, contract)

    raw = _read_ascii_data(path, header)

    issues_list = list(issues)
    if raw.shape[1] != contract.expected_curve_count:
        issues_list.append(
            IngestionIssue(
                severity="ERROR",
                code="DATA_COLUMN_COUNT_MISMATCH",
                message=(
                    f"~Ascii data section has {raw.shape[1]} column(s); contract expects "
                    f"{contract.expected_curve_count}."
                ),
                context=header.source_filename,
            )
        )
        status = "FAILED"

    error_issues = [i for i in issues_list if i.severity == "ERROR"]
    if error_issues:
        msg = "; ".join(f"[{i.code}] {i.message}" for i in error_issues)
        exc = LasContractError(f"{header.source_filename}: contract resolution FAILED - {msg}")
        exc.issues = tuple(issues_list)
        exc.resolutions = tuple(resolutions)
        exc.header = header
        raise exc

    # The measured-depth curve is found by its declared semantic role,
    # never by matching a canonical name spelled "DEPT" (Increment 2.1
    # correction). `load_file_contract_config` guarantees exactly one
    # such entry exists in any contract it returns; the check below is
    # defensive, for a contract constructed directly in Python (e.g. in a
    # test) rather than loaded from YAML.
    depth_entry = next(
        (c for c in contract.curves if c.semantic_role == SEMANTIC_ROLE_MEASURED_DEPTH), None
    )
    if depth_entry is None:
        exc = LasContractError(f"{header.source_filename}: contract defines no measured-depth curve.")
        exc.issues = tuple(issues_list)
        exc.resolutions = tuple(resolutions)
        exc.header = header
        raise exc

    depth_resolution = next(r for r in resolutions if r.canonical_name == depth_entry.canonical_name)
    if depth_resolution.status != "RESOLVED":
        exc = LasContractError(
            f"{header.source_filename}: the contract's measured-depth curve "
            f"({depth_entry.source_curve_name!r}) did not resolve."
        )
        exc.issues = tuple(issues_list)
        exc.resolutions = tuple(resolutions)
        exc.header = header
        raise exc

    md_raw = raw[:, depth_entry.ordinal]
    if not np.all(np.isfinite(md_raw)):
        exc = LasContractError(
            f"{header.source_filename}: measured-depth column ({depth_entry.source_curve_name!r}) "
            f"contains non-finite value(s); depth must always be finite."
        )
        exc.issues = tuple(issues_list)
        exc.resolutions = tuple(resolutions)
        exc.header = header
        raise exc

    depth = compute_depth_diagnostics(md_raw, header.declared_strt, header.declared_stop, header.declared_step)

    if depth.n_duplicate_md > 0:
        issues_list.append(
            IngestionIssue(
                "WARNING", "DUPLICATE_MD",
                f"{depth.n_duplicate_md} duplicate measured-depth sample(s) detected.",
                header.source_filename,
            )
        )
    if depth.n_non_monotonic > 0:
        issues_list.append(
            IngestionIssue(
                "WARNING", "NON_MONOTONIC_MD",
                f"{depth.n_non_monotonic} non-monotonic measured-depth step(s) detected.",
                header.source_filename,
            )
        )
    if depth.strt_matches_declared is False:
        issues_list.append(
            IngestionIssue(
                "WARNING", "STRT_MISMATCH",
                f"Declared STRT={depth.declared_strt} vs data-derived start={depth.data_start}.",
                header.source_filename,
            )
        )
    if depth.stop_matches_declared is False:
        issues_list.append(
            IngestionIssue(
                "WARNING", "STOP_MISMATCH",
                f"Declared STOP={depth.declared_stop} vs data-derived stop={depth.data_stop}.",
                header.source_filename,
            )
        )
    if depth.step_matches_declared is False:
        issues_list.append(
            IngestionIssue(
                "WARNING", "STEP_MISMATCH",
                f"Declared STEP={depth.declared_step} vs data-derived median step={depth.data_median_step}.",
                header.source_filename,
            )
        )

    resolutions_by_name = {r.canonical_name: r for r in resolutions}
    canonical_data: Dict[str, np.ndarray] = {}
    curve_stats: List[CurveStats] = []

    for entry in contract.curves:
        res = resolutions_by_name[entry.canonical_name]
        if res.status != "RESOLVED":
            continue
        col = raw[:, entry.ordinal]
        substituted = _apply_null_sentinel(col, header.declared_null)
        canonical_values = _apply_conversion(entry, substituted, header.source_filename, md_raw)
        canonical_data[entry.canonical_name] = canonical_values
        curve_stats.append(compute_curve_stats(entry, col, canonical_values, header.declared_null))

    return LasFileResult(
        header=header,
        contract=contract,
        resolutions=resolutions,
        depth=depth,
        curve_stats=tuple(curve_stats),
        raw_data=raw,
        canonical_data=canonical_data,
        issues=tuple(issues_list),
        contract_status="PASSED",
    )


def load_wells(
    file_paths: Dict[str, str], contracts: Dict[str, FileContract]
) -> Tuple[Dict[str, LasFileResult], Dict[str, IngestionFailure]]:
    """
    Load several LAS files against their respective contracts.

    `file_paths` maps an arbitrary caller-chosen key (e.g. a canonical
    well name) to a filesystem path; the matching contract is looked up
    by the file's basename. One well's ingestion failure does not stop
    the others from loading - each key ends up in exactly one of the two
    returned dicts, never both.

    Increment 2.1 correction: a failed well is now recorded as a typed
    `IngestionFailure` (with `error_type` one of "file_not_found",
    "parsing_failure", "contract_failure", "conversion_failure") rather
    than a bare caught exception, so a caller can branch on the kind of
    failure without importing every exception class or parsing message
    text. All four of those are EXPECTED per-file ingestion-failure
    modes and are isolated here; any other exception (a programming
    error, not an expected data-quality problem) is NOT caught and still
    propagates out of this function.

    Raises
    ------
    LasContractDefinitionError
        If a path's basename has no matching entry in `contracts` - this
        is a configuration problem (contracts and file set out of sync),
        not a per-well data problem, so it is not caught per-well.
    """
    results: Dict[str, LasFileResult] = {}
    errors: Dict[str, IngestionFailure] = {}
    for key, path in file_paths.items():
        filename = Path(path).name
        contract = contracts.get(filename)
        if contract is None:
            raise LasContractDefinitionError(
                f"No curve contract found for {filename!r} (key {key!r}). "
                f"Contracts are defined for: {sorted(contracts)}."
            )
        try:
            results[key] = load_las_file(path, contract)
        except LasFileNotFoundError as exc:
            errors[key] = IngestionFailure(key, path, "file_not_found", str(exc), exc)
        except LasParsingError as exc:
            errors[key] = IngestionFailure(key, path, "parsing_failure", str(exc), exc)
        except LasContractError as exc:
            errors[key] = IngestionFailure(key, path, "contract_failure", str(exc), exc)
        except LasConversionError as exc:
            errors[key] = IngestionFailure(key, path, "conversion_failure", str(exc), exc)
    return results, errors
