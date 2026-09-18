"""
p2mem.io.tops - Auditable formation-top file ingestion, HRS-versus-readable
source reconciliation, and survey-corrected stratigraphic depth mapping
(Increment 5).

Why this module exists
------------------------
Each approved well (Poseidon 2, Boreas 1) has TWO independently supplied
formation-top files, in two structurally different formats:

* an "HRS" file (`Top_Name`, `MDRT_m` - tab-separated, no comments, no
  TVDSS, no well name anywhere in the file BODY - the well association
  rests on the filename alone, e.g.
  "Poseidon_2_HRS_tops_no_wellname_MDRT.txt". This is recorded honestly as
  `well_identity_source = "filename_only"`, never as content-verified
  identity.);
* a "selected readable" file (`#`-prefixed comment lines - including one
  naming the well - a blank line, a whitespace-padded
  `TOP_NAME`/`MDRT_M`/`TVDSS_M`/`NOTE` header, a dashed separator line,
  then whitespace-padded data rows). The comment naming the well is
  PROJECT-SUPPLIED METADATA embedded in the file, not independently
  verified file content - recorded as `well_identity_source =
  "in_file_comment_project_supplied"`, never as "verified".

STRUCTURAL PARSING (can the file be tokenized at all: is the expected
header/separator present, does every data row have the expected number of
numeric tokens, are all numeric tokens finite and non-negative) is kept
separate from CONTRACT RESOLUTION (does this specific file's actual
identity/schema/range agree with `config/formation_top_contracts.yml`) is
kept separate from SOURCE RECONCILIATION (do the two independently
supplied files for the SAME well agree with each other). A structural
defect raises `TopParsingError`; a contract mismatch raises
`TopContractError`; an unresolvable cross-file reconciliation problem
raises `TopSourceReconciliationError`. All three are always blocking.

Neither source file is ever treated as unconditionally authoritative. See
`reconcile_formation_top_sources` for the explicit name/MDRT reconciliation
policy, and `build_formation_top_markers` for the explicit MDRT-authority
and survey-mapping policy: the reconciled MDRT is mapped through the
LOCKED Increment 3.1.1 `petrel_source_trace` deviation-survey trajectory
using the UNMODIFIED, already-locked `p2mem.depth_mapping
.map_las_md_to_tvd_tvdss` function (this module never reimplements minimum
curvature or the TVD/TVDSS formula - that function is generic over ANY
1-D array of measured-depth values referenced to the same rotary-table
datum as the survey, not LAS-specific despite its parameter name; every
approved deviation-survey file's own header states "MD AND TVD ARE
REFERENCED (=0) AT WELL DATUM [RT]" - the identical zero/RT/downward-
increasing convention as this project's `MDRT_m` formation-top columns,
independently confirmed for both approved wells in
`INCREMENT_05_MANIFEST.md` Section 1).

Marker-name matching discipline (no silent fuzzy matching)
-------------------------------------------------------------
Two marker names are treated as the SAME canonical marker only if:

1. their raw strings are IDENTICAL (`name_match_status = "exact"`), or
2. they are identical after stripping leading/trailing whitespace and
   collapsing internal whitespace runs to a single space
   (`name_match_status = "normalized_match"` - this is the ONLY
   normalization applied, and it never changes letter case or
   punctuation), or
3. one of them appears, verbatim, as a key in the human-authored
   `marker_name_aliases` table in `config/formation_top_contracts.yml`,
   mapping it to the SAME canonical name the other side resolves to
   (`name_match_status = "aliased_match"`).

No similarity/fuzzy-distance matching of any kind is used. A marker name
that matches by none of the three rules above is recorded as present in
only one source (`name_match_status` = "missing_in_hrs" /
"missing_in_readable") - never silently paired with the nearest-looking
name from the other file.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import yaml

from p2mem.depth_mapping import DepthMappingError, ExtrapolationRejectedError, map_las_md_to_tvd_tvdss
from p2mem.deviation_models import DeviationWellResult
from p2mem.top_models import (
    VALID_IDENTITY_EVIDENCE_STATUSES,
    VALID_MODEL_USE_STATUSES,
    VALID_REPRESENTATION_TYPES,
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

__all__ = [
    "TopFileNotFoundError",
    "TopParsingError",
    "TopContractDefinitionError",
    "TopContractError",
    "TopSourceReconciliationError",
    "MDRT_AGREEMENT_TOLERANCE_M",
    "load_formation_top_contract_config",
    "parse_hrs_top_header",
    "read_hrs_top_rows",
    "parse_readable_top_header",
    "read_readable_top_rows",
    "resolve_hrs_top_contract",
    "resolve_readable_top_contract",
    "normalize_marker_name",
    "reconcile_formation_top_sources",
    "build_formation_top_markers",
    "load_formation_top_well",
    "load_formation_top_surveys",
]

_HRS_REQUIRED_COLUMN_COUNT = 2
_READABLE_REQUIRED_COLUMN_COUNT = 4

# The MDRT cross-check tolerance used when reconciling the two source
# files (Section 4 of the Increment 5 specification: "MDRT agreement").
# Both approved wells' HRS and readable files agree EXACTLY (0.00 m
# difference on every marker - independently confirmed in
# INCREMENT_05_MANIFEST.md Section 1); this tolerance absorbs only
# ordinary floating-point text round-trip noise (the files carry 2
# decimal places), never a genuinely different MDRT placement.
MDRT_AGREEMENT_TOLERANCE_M = 0.005


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class TopFileNotFoundError(FileNotFoundError):
    """A formation-top file path given to `load_formation_top_well` does not exist."""


class TopParsingError(ValueError):
    """
    A structural defect in a formation-top file, or in a caller-supplied
    in-memory formation-top data structure: a missing/malformed header or
    separator line, a data row without the expected number of tokens, a
    non-finite (NaN/Inf) or negative depth value, a duplicate canonical
    marker name within one source, a marker-order reversal within one
    source, an ambiguous-dtype (boolean/string/complex) numeric array, or
    a length mismatch between a station dataclass's name tuple and its
    numeric array(s). Raised before any contract or reconciliation step is
    reached (or, for a caller-supplied dataclass, before any downstream
    numerical use).
    """


class TopContractDefinitionError(ValueError):
    """
    `config/formation_top_contracts.yml` itself is malformed: a duplicate
    top-level key, a missing required field, an invalid type, an
    unsupported enum value, or an internally inconsistent expected-value
    set (e.g. min > max).
    """


class TopContractError(RuntimeError):
    """
    A specific file's actual parsed header/data does not agree with its
    contract: wrong filename, SHA-256 mismatch, header/schema mismatch,
    marker-count mismatch, or a numeric range outside the contract's
    declared tolerance. Carries `.issues` (the full tuple, ERROR and
    WARNING alike).
    """

    def __init__(self, message: str, issues: Tuple[TopIngestionIssue, ...]):
        super().__init__(message)
        self.issues = issues


class TopSourceReconciliationError(RuntimeError):
    """
    The HRS and selected-readable files for one well could not be
    reconciled at all: a duplicate canonical marker name within one
    source, a marker-order reversal within one source, or (a case never
    observed in either approved well's real data) zero canonical markers
    in common between the two sources. Carries `.issues`. A per-marker
    MDRT disagreement between otherwise-well-formed sources is NOT fatal -
    it is registered in the reconciliation table and that one marker is
    excluded from mapping (see `TopMarkerRecord.mdrt_authority_basis ==
    "disagreement_unresolved"`) without raising this exception.
    """

    def __init__(self, message: str, issues: Tuple[TopIngestionIssue, ...]):
        super().__init__(message)
        self.issues = issues


# ---------------------------------------------------------------------------
# Contract configuration (config/formation_top_contracts.yml)
# ---------------------------------------------------------------------------
class _NoDuplicateKeySafeLoader(yaml.SafeLoader):
    """
    A `yaml.SafeLoader` subclass that raises on a duplicate mapping key
    rather than silently keeping only the last occurrence. File-scoped to
    this module (mirrors, but does not import, the identical private
    pattern in `p2mem.io.checkshot` / `p2mem.io.deviation` - each of those
    classes is private to its own module and not exported for reuse).
    """


def _construct_mapping_no_duplicates(loader: yaml.SafeLoader, node, deep: bool = False):
    mapping: Dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise TopContractDefinitionError(
                f"Duplicate key {key!r} found while parsing formation-top contract YAML "
                f"(line {key_node.start_mark.line + 1}); duplicate contract keys are "
                f"rejected rather than silently keeping only the last one."
            )
        value = loader.construct_object(value_node, deep=deep)
        mapping[key] = value
    return mapping


_NoDuplicateKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping_no_duplicates
)

_COMMON_REQUIRED_FIELDS = (
    "expected_sha256",
    "project_well_key",
    "representation_type",
    "well_identity_evidence_status",
    "well_identity_evidence_notes",
    "model_use_status",
    "expected_column_header_line",
    "expected_column_order",
    "expected_marker_count",
    "expected_mdrt_min_m",
    "expected_mdrt_max_m",
    "numeric_range_tolerance",
    "datum_depth_column_interpretation",
    "notes",
)
_READABLE_ONLY_REQUIRED_FIELDS = (
    "expected_well_name_from_comment",
    "expected_tvdss_min_m",
    "expected_tvdss_max_m",
)


def _num(value, field_name: str, filename: str):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TopContractDefinitionError(f"{filename}: field {field_name!r} must be numeric, got {value!r}.")
    return float(value)


def _validate_common_fields(entry: dict, filename: str) -> None:
    missing = [f for f in _COMMON_REQUIRED_FIELDS if f not in entry]
    if missing:
        raise TopContractDefinitionError(f"{filename}: missing required field(s) {missing}.")
    if entry["representation_type"] not in VALID_REPRESENTATION_TYPES:
        raise TopContractDefinitionError(
            f"{filename}: representation_type must be one of {VALID_REPRESENTATION_TYPES}, "
            f"got {entry['representation_type']!r}."
        )
    if entry["well_identity_evidence_status"] not in VALID_IDENTITY_EVIDENCE_STATUSES:
        raise TopContractDefinitionError(
            f"{filename}: well_identity_evidence_status must be one of "
            f"{VALID_IDENTITY_EVIDENCE_STATUSES}, got {entry['well_identity_evidence_status']!r}."
        )
    if entry["model_use_status"] not in VALID_MODEL_USE_STATUSES:
        raise TopContractDefinitionError(
            f"{filename}: model_use_status must be one of {VALID_MODEL_USE_STATUSES}, "
            f"got {entry['model_use_status']!r}."
        )
    marker_count = entry["expected_marker_count"]
    if isinstance(marker_count, bool) or not isinstance(marker_count, int) or marker_count < 1:
        raise TopContractDefinitionError(f"{filename}: expected_marker_count must be a positive integer.")
    for f in (
        "expected_sha256", "project_well_key", "well_identity_evidence_notes",
        "expected_column_header_line", "datum_depth_column_interpretation", "notes",
    ):
        if not isinstance(entry[f], str) or not entry[f].strip():
            raise TopContractDefinitionError(f"{filename}: field {f!r} must be a non-empty string.")
    col_order = entry["expected_column_order"]
    if not isinstance(col_order, list) or not col_order or not all(isinstance(c, str) for c in col_order):
        raise TopContractDefinitionError(f"{filename}: expected_column_order must be a list of strings.")


def load_formation_top_contract_config(
    yaml_path: str,
) -> Tuple[Dict[str, HRSTopFileContract], Dict[str, ReadableTopFileContract], Dict[str, str]]:
    """
    Load and validate `config/formation_top_contracts.yml`, returning
    `(hrs_contracts, readable_contracts, marker_name_aliases)`:

    * `hrs_contracts` / `readable_contracts` are each keyed by exact
      source filename, containing only contracts of that representation
      type (a file listed under `representation_type:
      selected_readable_MDRT_TVDSS` never appears in `hrs_contracts`, and
      vice versa - this is enforced, not merely assumed).
    * `marker_name_aliases` is the flat, human-authored, project-wide
      alias table (raw marker-name string -> canonical marker-name
      string) from the YAML's top-level `marker_name_aliases` key
      (`{}` if absent - both approved wells' real data need zero aliases;
      see `reconcile_formation_top_sources`).

    Raises `TopContractDefinitionError` for any structural or internal-
    consistency problem, before any formation-top file is opened.
    """
    with open(yaml_path, "r", encoding="utf-8") as fh:
        raw = yaml.load(fh, Loader=_NoDuplicateKeySafeLoader)

    if not isinstance(raw, dict) or "files" not in raw:
        raise TopContractDefinitionError(f"{yaml_path}: top-level YAML must be a mapping with a 'files' key.")
    files_section = raw["files"]
    if not isinstance(files_section, dict) or not files_section:
        raise TopContractDefinitionError(f"{yaml_path}: 'files' must be a non-empty mapping.")

    aliases_section = raw.get("marker_name_aliases", {}) or {}
    if not isinstance(aliases_section, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in aliases_section.items()
    ):
        raise TopContractDefinitionError(f"{yaml_path}: 'marker_name_aliases' must be a mapping of string to string.")

    hrs_contracts: Dict[str, HRSTopFileContract] = {}
    readable_contracts: Dict[str, ReadableTopFileContract] = {}

    for filename, entry in files_section.items():
        if not isinstance(entry, dict):
            raise TopContractDefinitionError(f"{filename}: contract entry must be a mapping.")
        _validate_common_fields(entry, filename)

        mdrt_min = _num(entry["expected_mdrt_min_m"], "expected_mdrt_min_m", filename)
        mdrt_max = _num(entry["expected_mdrt_max_m"], "expected_mdrt_max_m", filename)
        tolerance = _num(entry["numeric_range_tolerance"], "numeric_range_tolerance", filename)
        if tolerance < 0.0:
            raise TopContractDefinitionError(f"{filename}: numeric_range_tolerance must be >= 0.")
        if mdrt_min > mdrt_max:
            raise TopContractDefinitionError(f"{filename}: expected_mdrt_min_m > expected_mdrt_max_m.")

        if entry["representation_type"] == "HRS_MDRT_only":
            if len(entry["expected_column_order"]) != _HRS_REQUIRED_COLUMN_COUNT:
                raise TopContractDefinitionError(
                    f"{filename}: HRS expected_column_order must have exactly "
                    f"{_HRS_REQUIRED_COLUMN_COUNT} entries."
                )
            hrs_contracts[filename] = HRSTopFileContract(
                source_filename=filename,
                expected_sha256=entry["expected_sha256"],
                project_well_key=entry["project_well_key"],
                representation_type=entry["representation_type"],
                well_identity_evidence_status=entry["well_identity_evidence_status"],
                well_identity_evidence_notes=entry["well_identity_evidence_notes"],
                model_use_status=entry["model_use_status"],
                expected_column_header_line=entry["expected_column_header_line"],
                expected_column_order=tuple(entry["expected_column_order"]),
                expected_column_count=_HRS_REQUIRED_COLUMN_COUNT,
                expected_marker_count=entry["expected_marker_count"],
                expected_mdrt_min_m=mdrt_min,
                expected_mdrt_max_m=mdrt_max,
                numeric_range_tolerance=tolerance,
                datum_depth_column_interpretation=entry["datum_depth_column_interpretation"],
                notes=entry["notes"],
            )
        elif entry["representation_type"] == "selected_readable_MDRT_TVDSS":
            missing = [f for f in _READABLE_ONLY_REQUIRED_FIELDS if f not in entry]
            if missing:
                raise TopContractDefinitionError(f"{filename}: missing required field(s) {missing}.")
            if len(entry["expected_column_order"]) != _READABLE_REQUIRED_COLUMN_COUNT:
                raise TopContractDefinitionError(
                    f"{filename}: readable expected_column_order must have exactly "
                    f"{_READABLE_REQUIRED_COLUMN_COUNT} entries."
                )
            tvdss_min = _num(entry["expected_tvdss_min_m"], "expected_tvdss_min_m", filename)
            tvdss_max = _num(entry["expected_tvdss_max_m"], "expected_tvdss_max_m", filename)
            if tvdss_min > tvdss_max:
                raise TopContractDefinitionError(f"{filename}: expected_tvdss_min_m > expected_tvdss_max_m.")
            if not isinstance(entry["expected_well_name_from_comment"], str) or not entry[
                "expected_well_name_from_comment"
            ].strip():
                raise TopContractDefinitionError(
                    f"{filename}: expected_well_name_from_comment must be a non-empty string."
                )
            readable_contracts[filename] = ReadableTopFileContract(
                source_filename=filename,
                expected_sha256=entry["expected_sha256"],
                project_well_key=entry["project_well_key"],
                representation_type=entry["representation_type"],
                well_identity_evidence_status=entry["well_identity_evidence_status"],
                well_identity_evidence_notes=entry["well_identity_evidence_notes"],
                model_use_status=entry["model_use_status"],
                expected_well_name_from_comment=entry["expected_well_name_from_comment"],
                expected_column_header_line=entry["expected_column_header_line"],
                expected_column_order=tuple(entry["expected_column_order"]),
                expected_column_count=_READABLE_REQUIRED_COLUMN_COUNT,
                expected_marker_count=entry["expected_marker_count"],
                expected_mdrt_min_m=mdrt_min,
                expected_mdrt_max_m=mdrt_max,
                expected_tvdss_min_m=tvdss_min,
                expected_tvdss_max_m=tvdss_max,
                numeric_range_tolerance=tolerance,
                datum_depth_column_interpretation=entry["datum_depth_column_interpretation"],
                notes=entry["notes"],
            )
        else:  # pragma: no cover - already validated above
            raise TopContractDefinitionError(f"{filename}: unrecognized representation_type.")

    return hrs_contracts, readable_contracts, dict(aliases_section)


# ---------------------------------------------------------------------------
# Structural parsing - HRS format
# ---------------------------------------------------------------------------
def parse_hrs_top_header(path: str) -> HRSTopHeaderInfo:
    """
    Parse the single-line HRS header: one tab-separated column-header line
    (`Top_Name`, `MDRT_m`). Raises `TopFileNotFoundError` if the path does
    not exist, or `TopParsingError` if no header line is present.
    """
    p = Path(path)
    if not p.exists():
        raise TopFileNotFoundError(f"Formation-top (HRS) file not found: {path}")

    raw_bytes = p.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    line_ending = "CRLF" if b"\r\n" in raw_bytes else ("LF" if b"\n" in raw_bytes else "NONE")

    text = raw_bytes.decode("utf-8")
    lines = text.splitlines()
    if len(lines) < 1 or not lines[0].strip():
        raise TopParsingError(f"{path}: expected a non-empty column-header line as the first line.")
    column_header_line = lines[0]
    column_names = tuple(column_header_line.split("\t"))
    if len(column_names) != _HRS_REQUIRED_COLUMN_COUNT:
        raise TopParsingError(
            f"{path}: column-header line must have exactly {_HRS_REQUIRED_COLUMN_COUNT} "
            f"tab-separated fields; found {len(column_names)} in {column_header_line!r}."
        )

    return HRSTopHeaderInfo(
        source_filename=p.name,
        sha256=sha256,
        column_header_line=column_header_line,
        column_names=column_names,
        well_identity_source="filename_only",
        line_ending_convention=line_ending,
        header_line_count=1,
        data_line_offset=1,
    )


def read_hrs_top_rows(path: str) -> HRSTopStationData:
    """
    Parse the data rows (all non-empty lines after the 1-line header) into
    raw `HRSTopStationData`, in original file order. A blank line is
    permitted only as a trailing end-of-file artifact; a blank line found
    before the last non-empty line is a structural defect. Every MDRT
    value must be finite and non-negative (a negative measured depth below
    rotary table has no physical meaning for a downhole marker).
    """
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    data_lines = lines[1:]

    last_nonblank = -1
    for i, ln in enumerate(data_lines):
        if ln.strip():
            last_nonblank = i
    if last_nonblank < 0:
        raise TopParsingError(f"{path}: no data rows found after the 1-line header.")

    names: List[str] = []
    mdrt_vals: List[float] = []
    for i, ln in enumerate(data_lines[: last_nonblank + 1]):
        if not ln.strip():
            raise TopParsingError(
                f"{path}: blank line found at data row {i + 1} before the last data row; "
                f"only a trailing blank line (end-of-file artifact) is permitted."
            )
        parts = ln.split("\t")
        if len(parts) != _HRS_REQUIRED_COLUMN_COUNT:
            raise TopParsingError(
                f"{path}: data row {i + 1} has {len(parts)} tab-separated field(s), "
                f"expected {_HRS_REQUIRED_COLUMN_COUNT}: {ln!r}"
            )
        name = parts[0]
        try:
            mdrt = float(parts[1])
        except ValueError as exc:
            raise TopParsingError(f"{path}: data row {i + 1} contains a non-numeric MDRT token: {ln!r} ({exc})") from exc
        if not np.isfinite(mdrt):
            raise TopParsingError(f"{path}: data row {i + 1} contains a non-finite MDRT value: {ln!r}")
        if mdrt < 0.0:
            raise TopParsingError(f"{path}: data row {i + 1} contains a negative MDRT value: {ln!r}")
        names.append(name)
        mdrt_vals.append(mdrt)

    return HRSTopStationData(
        Top_Name_source=tuple(names),
        MDRT_source_m=np.asarray(mdrt_vals, dtype=np.float64),
    )


# ---------------------------------------------------------------------------
# Structural parsing - selected-readable format
# ---------------------------------------------------------------------------
def parse_readable_top_header(path: str) -> ReadableTopHeaderInfo:
    """
    Parse the "selected readable" header: one or more leading `#`-prefixed
    comment lines, a blank line, a whitespace-padded column-header line
    (`TOP_NAME`, `MDRT_M`, `TVDSS_M`, `NOTE`), and a dashed separator
    line - each recognized structurally and deliberately, never
    accidentally treated as a data row. Raises `TopParsingError` if any of
    these structural elements is missing.
    """
    p = Path(path)
    if not p.exists():
        raise TopFileNotFoundError(f"Formation-top (selected readable) file not found: {path}")

    raw_bytes = p.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    line_ending = "CRLF" if b"\r\n" in raw_bytes else ("LF" if b"\n" in raw_bytes else "NONE")

    text = raw_bytes.decode("utf-8")
    lines = text.splitlines()

    comment_lines: List[str] = []
    idx = 0
    while idx < len(lines) and lines[idx].startswith("#"):
        comment_lines.append(lines[idx])
        idx += 1
    if not comment_lines:
        raise TopParsingError(f"{path}: expected at least one leading '#'-prefixed comment line.")

    well_name_from_comment: Optional[str] = None
    for cl in comment_lines:
        marker = "Selected readable well tops for "
        if marker in cl:
            well_name_from_comment = cl.split(marker, 1)[1].strip()
            break

    # Skip exactly one blank line separating the comment block from the header.
    if idx >= len(lines) or lines[idx].strip():
        raise TopParsingError(f"{path}: expected a blank line after the comment block (line {idx + 1}).")
    idx += 1

    if idx >= len(lines) or not lines[idx].strip().startswith("TOP_NAME"):
        raise TopParsingError(f"{path}: expected the column-header line (starting 'TOP_NAME') at line {idx + 1}.")
    column_header_line = lines[idx]
    column_names = tuple(c.strip() for c in column_header_line.split() if c.strip())
    # The header line's own fields are whitespace-padded/aligned, not
    # tab-separated - split() on any whitespace run is the correct,
    # deliberate tokenization here (never accidentally merging TOP_NAME
    # tokens that themselves contain a single space, since the header only
    # contains the 4 declared column names).
    if len(column_names) != _READABLE_REQUIRED_COLUMN_COUNT:
        raise TopParsingError(
            f"{path}: column-header line must tokenize to exactly {_READABLE_REQUIRED_COLUMN_COUNT} "
            f"fields; found {len(column_names)} in {column_header_line!r}."
        )
    idx += 1

    if idx >= len(lines) or not lines[idx].strip() or set(lines[idx].strip()) != {"-"}:
        raise TopParsingError(f"{path}: expected a dashed separator line (all '-' characters) at line {idx + 1}.")
    separator_line_raw = lines[idx]
    idx += 1

    return ReadableTopHeaderInfo(
        source_filename=p.name,
        sha256=sha256,
        comment_lines=tuple(comment_lines),
        well_name_from_comment=well_name_from_comment,
        column_header_line=column_header_line,
        column_names=column_names,
        separator_line_raw=separator_line_raw,
        well_identity_source="in_file_comment_project_supplied",
        line_ending_convention=line_ending,
        header_line_count=idx,
        data_line_offset=idx,
    )


def read_readable_top_rows(path: str) -> ReadableTopStationData:
    """
    Parse the data rows (every non-empty line after the header/separator
    block) into raw `ReadableTopStationData`, in original file order.
    Fields are whitespace-delimited, but `TOP_NAME` may itself contain
    single internal spaces (e.g. "Sea Bed") - this function tokenizes each
    data line by splitting on 2-or-more-space runs / tabs (the file's own
    fixed-width column alignment), never on every single space, so a
    multi-word marker name is never accidentally split across fields.
    `NOTE` may be empty (preserved as `""`, never fabricated).
    """
    import re

    header = parse_readable_top_header(path)
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    data_lines = lines[header.data_line_offset :]

    last_nonblank = -1
    for i, ln in enumerate(data_lines):
        if ln.strip():
            last_nonblank = i
    if last_nonblank < 0:
        raise TopParsingError(f"{path}: no data rows found after the header/separator block.")

    field_splitter = re.compile(r"\t|  +")  # a tab, or 2-or-more consecutive spaces

    names: List[str] = []
    mdrt_vals: List[float] = []
    tvdss_vals: List[float] = []
    notes: List[str] = []
    for i, ln in enumerate(data_lines[: last_nonblank + 1]):
        if not ln.strip():
            raise TopParsingError(
                f"{path}: blank line found at data row {i + 1} before the last data row; "
                f"only a trailing blank line (end-of-file artifact) is permitted."
            )
        parts = [p.strip() for p in field_splitter.split(ln.rstrip("\n\r"))]
        parts = [p for p in parts if p != ""]
        if len(parts) < 3:
            raise TopParsingError(
                f"{path}: data row {i + 1} could not be tokenized into at least "
                f"TOP_NAME/MDRT_M/TVDSS_M fields: {ln!r}"
            )
        name = parts[0]
        try:
            mdrt = float(parts[1])
            tvdss = float(parts[2])
        except ValueError as exc:
            raise TopParsingError(f"{path}: data row {i + 1} contains a non-numeric MDRT/TVDSS token: {ln!r} ({exc})") from exc
        if not (np.isfinite(mdrt) and np.isfinite(tvdss)):
            raise TopParsingError(f"{path}: data row {i + 1} contains a non-finite MDRT/TVDSS value: {ln!r}")
        if mdrt < 0.0:
            raise TopParsingError(f"{path}: data row {i + 1} contains a negative MDRT value: {ln!r}")
        note = parts[3] if len(parts) >= 4 else ""
        names.append(name)
        mdrt_vals.append(mdrt)
        tvdss_vals.append(tvdss)
        notes.append(note)

    return ReadableTopStationData(
        TOP_NAME_source=tuple(names),
        MDRT_source_m=np.asarray(mdrt_vals, dtype=np.float64),
        TVDSS_source_m=np.asarray(tvdss_vals, dtype=np.float64),
        NOTE_source=tuple(notes),
    )


# ---------------------------------------------------------------------------
# Contract resolution
# ---------------------------------------------------------------------------
def resolve_hrs_top_contract(
    header: HRSTopHeaderInfo, stations: HRSTopStationData, contract: HRSTopFileContract
) -> Tuple[TopIngestionIssue, ...]:
    """Compare the actual parsed HRS header/data against `contract`."""
    issues: List[TopIngestionIssue] = []

    def err(code: str, message: str) -> None:
        issues.append(TopIngestionIssue("ERROR", code, message, header.source_filename))

    def warn(code: str, message: str) -> None:
        issues.append(TopIngestionIssue("WARNING", code, message, header.source_filename))

    if header.source_filename != contract.source_filename:
        err("FILENAME_MISMATCH", f"Actual filename {header.source_filename!r} does not match contract key {contract.source_filename!r}.")
    if header.sha256 != contract.expected_sha256:
        err("SHA256_MISMATCH", f"Actual SHA-256 {header.sha256!r} does not match expected {contract.expected_sha256!r}.")
    if header.column_header_line != contract.expected_column_header_line:
        err("COLUMN_HEADER_LINE_MISMATCH", f"Actual column-header line {header.column_header_line!r} does not match expected {contract.expected_column_header_line!r}.")
    if header.column_names != contract.expected_column_order:
        err("COLUMN_ORDER_MISMATCH", f"Actual column order {header.column_names!r} does not match expected {contract.expected_column_order!r}.")

    n_markers = len(stations.Top_Name_source)
    if n_markers != contract.expected_marker_count:
        err("MARKER_COUNT_MISMATCH", f"Actual marker count {n_markers} does not match expected {contract.expected_marker_count}.")

    if n_markers:
        tol = contract.numeric_range_tolerance
        actual_min, actual_max = float(stations.MDRT_source_m.min()), float(stations.MDRT_source_m.max())
        if abs(actual_min - contract.expected_mdrt_min_m) > tol or abs(actual_max - contract.expected_mdrt_max_m) > tol:
            err("NUMERIC_RANGE_MISMATCH", f"MDRT_source_m: actual range [{actual_min}, {actual_max}] does not match expected [{contract.expected_mdrt_min_m}, {contract.expected_mdrt_max_m}] within tolerance {tol}.")

    warn(
        "WELL_IDENTITY_FILENAME_ONLY",
        f"This HRS file carries NO well name in its own body; association with project well "
        f"{contract.project_well_key!r} rests on the filename alone. {contract.well_identity_evidence_notes} "
        f"Never described as content-verified identity.",
    )
    return tuple(issues)


def resolve_readable_top_contract(
    header: ReadableTopHeaderInfo, stations: ReadableTopStationData, contract: ReadableTopFileContract
) -> Tuple[TopIngestionIssue, ...]:
    """Compare the actual parsed selected-readable header/data against `contract`."""
    issues: List[TopIngestionIssue] = []

    def err(code: str, message: str) -> None:
        issues.append(TopIngestionIssue("ERROR", code, message, header.source_filename))

    def warn(code: str, message: str) -> None:
        issues.append(TopIngestionIssue("WARNING", code, message, header.source_filename))

    if header.source_filename != contract.source_filename:
        err("FILENAME_MISMATCH", f"Actual filename {header.source_filename!r} does not match contract key {contract.source_filename!r}.")
    if header.sha256 != contract.expected_sha256:
        err("SHA256_MISMATCH", f"Actual SHA-256 {header.sha256!r} does not match expected {contract.expected_sha256!r}.")
    if header.well_name_from_comment != contract.expected_well_name_from_comment:
        err("WELL_NAME_COMMENT_MISMATCH", f"Actual in-file comment well name {header.well_name_from_comment!r} does not match expected {contract.expected_well_name_from_comment!r}.")
    if header.column_names != contract.expected_column_order:
        err("COLUMN_ORDER_MISMATCH", f"Actual column order {header.column_names!r} does not match expected {contract.expected_column_order!r}.")

    n_markers = len(stations.TOP_NAME_source)
    if n_markers != contract.expected_marker_count:
        err("MARKER_COUNT_MISMATCH", f"Actual marker count {n_markers} does not match expected {contract.expected_marker_count}.")

    if n_markers:
        tol = contract.numeric_range_tolerance
        for label, arr, exp_min, exp_max in (
            ("MDRT_source_m", stations.MDRT_source_m, contract.expected_mdrt_min_m, contract.expected_mdrt_max_m),
            ("TVDSS_source_m", stations.TVDSS_source_m, contract.expected_tvdss_min_m, contract.expected_tvdss_max_m),
        ):
            actual_min, actual_max = float(arr.min()), float(arr.max())
            if abs(actual_min - exp_min) > tol or abs(actual_max - exp_max) > tol:
                err("NUMERIC_RANGE_MISMATCH", f"{label}: actual range [{actual_min}, {actual_max}] does not match expected [{exp_min}, {exp_max}] within tolerance {tol}.")

    warn(
        "WELL_IDENTITY_IN_FILE_COMMENT_PROJECT_SUPPLIED",
        f"This file's well name is stated in a leading '#' comment ({header.well_name_from_comment!r}) - "
        f"project-supplied metadata embedded in the file, NOT independently verified file content. "
        f"{contract.well_identity_evidence_notes} Never described as content-verified identity.",
    )
    warn(
        "SUPPLIED_TVDSS_NOT_CORRECTED_DEPTH",
        "This file's own TVDSS_M column is preserved as TVDSS_source_m for residual/QC comparison "
        "only - it is never treated as this project's corrected stratigraphic depth. The corrected "
        "depth is always TVDSS_survey_corrected_m, computed by mapping the reconciled MDRT through "
        "the locked petrel_source_trace survey (see p2mem.io.tops module docstring).",
    )
    return tuple(issues)


# ---------------------------------------------------------------------------
# Marker-name normalization (no fuzzy matching - see module docstring)
# ---------------------------------------------------------------------------
def normalize_marker_name(name: str) -> str:
    """Strip leading/trailing whitespace and collapse internal whitespace
    runs to a single space. Never changes letter case or punctuation."""
    return " ".join(name.split())


def _reject_ambiguous_dtype(raw: np.ndarray, context: str) -> None:
    """
    Local, documented copy of `p2mem.units`'s identical private dtype
    check (`p2mem/units.py` itself remains LOCKED and unmodified - see
    `p2mem.time_depth._reject_ambiguous_dtype` for the identical, already-
    established Increment 4.1.1 precedent for this exact pattern). Rejects
    boolean, string/bytes, and complex dtype input with `TypeError` before
    any numeric use; only integer- or floating-dtype arrays are accepted.
    """
    kind = raw.dtype.kind
    if kind == "b":
        raise TypeError(f"{context}: boolean input is not accepted as a numeric quantity.")
    if kind in ("U", "S"):
        raise TypeError(f"{context}: string/bytes input is not accepted as a numeric quantity.")
    if kind == "c":
        raise TypeError(f"{context}: complex input is not accepted as a numeric quantity.")
    if kind not in ("i", "u", "f"):
        raise TypeError(f"{context}: unsupported array dtype {raw.dtype!r} for a numeric quantity.")


def _validate_name_tuple(names: Tuple, label: str, well_key: str) -> None:
    """
    Increment 5.1 (Finding 3 fix): every element of a marker-name or note
    tuple must be a genuine `str` - never silently accepted as a bare
    length-N sequence of arbitrary objects. Raises `TopParsingError` (a
    structural/type defect in caller-supplied in-memory data, per this
    module's documented `TopParsingError` scope), never an incidental
    `TypeError` from a downstream string operation.
    """
    for i, n in enumerate(names):
        if not isinstance(n, str):
            raise TopParsingError(f"{well_key}: {label} element at index {i} must be a string, got {type(n).__name__!r}.")


def _validate_mdrt_agreement_tolerance(value, well_key: str) -> float:
    """
    Increment 5.1 (Finding 3 fix): explicitly validate the
    `mdrt_agreement_tolerance_m` keyword before it is used in any
    numerical comparison. Boolean, string/bytes, and complex values are
    rejected with `TypeError` (mirrors `_reject_ambiguous_dtype`'s
    type-class-versus-value-defect split); NaN, Inf, and negative values
    are rejected with `TopParsingError` (a value defect, not a type
    defect). Valid Python `int`/`float` and NumPy integer/floating
    scalars (including 0-d/size-1 NumPy arrays) are accepted and returned
    as a plain Python `float`.
    """
    if isinstance(value, bool):
        raise TypeError(f"{well_key}: mdrt_agreement_tolerance_m must not be boolean, got {value!r}.")
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{well_key}: mdrt_agreement_tolerance_m must not be a string/bytes value, got {value!r}.")
    if isinstance(value, complex):
        raise TypeError(f"{well_key}: mdrt_agreement_tolerance_m must not be complex, got {value!r}.")
    if isinstance(value, np.ndarray):
        if value.size != 1:
            raise TypeError(
                f"{well_key}: mdrt_agreement_tolerance_m must be a scalar, got an array of size {value.size}."
            )
        _reject_ambiguous_dtype(value, f"{well_key}: mdrt_agreement_tolerance_m")
        value = float(value.reshape(()))
    elif isinstance(value, (np.integer, np.floating)):
        value = float(value)
    elif isinstance(value, (int, float)):
        value = float(value)
    else:
        raise TypeError(
            f"{well_key}: mdrt_agreement_tolerance_m must be a real numeric scalar, got {type(value).__name__!r}."
        )
    if not np.isfinite(value):
        raise TopParsingError(f"{well_key}: mdrt_agreement_tolerance_m must be finite, got {value!r}.")
    if value < 0.0:
        raise TopParsingError(f"{well_key}: mdrt_agreement_tolerance_m must be non-negative, got {value!r}.")
    return value


# ---------------------------------------------------------------------------
# HRS-versus-readable source reconciliation
# ---------------------------------------------------------------------------
def reconcile_formation_top_sources(
    well_key: str,
    hrs_raw: HRSTopStationData,
    readable_raw: ReadableTopStationData,
    marker_name_aliases: Dict[str, str],
    *,
    mdrt_agreement_tolerance_m: float = MDRT_AGREEMENT_TOLERANCE_M,
) -> Tuple[Tuple[TopIngestionIssue, ...], Tuple[TopReconciliationEntry, ...]]:
    """
    Reconcile one well's HRS and selected-readable formation-top sources.
    See the module docstring for the exact/normalized/aliased marker-name
    matching policy (no fuzzy matching). Returns `(issues, entries)` -
    never raises for an ordinary per-marker MDRT disagreement (that is
    registered in the returned entries); raises `TopParsingError` for a
    malformed/ambiguous input array, and lets the caller
    (`load_formation_top_well`) decide whether an ERROR-severity issue
    (duplicate canonical name, marker-order reversal, or zero markers in
    common) is fatal via `TopSourceReconciliationError`.
    """
    # ------------------------------------------------------------------
    # Increment 5.1 (Finding 3 fix): full structural/type/value
    # validation of caller-supplied in-memory data, enforced BEFORE any
    # reconciliation or numerical comparison. The file parsers
    # (`read_hrs_top_rows` / `read_readable_top_rows`) already enforce
    # every one of these checks on file-derived data - this closes the
    # gap for this public in-memory API, which a caller/test can invoke
    # directly with hand-built dataclasses. Deliberate, typed exceptions
    # only: never an incidental IndexError (mismatched NOTE_source
    # length), NumPy broadcasting error, or bare comparison TypeError.
    # ------------------------------------------------------------------
    hrs_mdrt = hrs_raw.MDRT_source_m
    readable_mdrt = readable_raw.MDRT_source_m
    readable_tvdss = readable_raw.TVDSS_source_m

    for arr, label in (
        (hrs_mdrt, "HRS MDRT_source_m"),
        (readable_mdrt, "readable MDRT_source_m"),
        (readable_tvdss, "readable TVDSS_source_m"),
    ):
        if not isinstance(arr, np.ndarray):
            raise TopParsingError(f"{well_key}: {label} must be a NumPy array, got {type(arr).__name__!r}.")
        if arr.ndim != 1:
            raise TopParsingError(f"{well_key}: {label} must be 1-dimensional, got ndim={arr.ndim}.")

    _reject_ambiguous_dtype(hrs_mdrt, f"{well_key}: HRS MDRT_source_m")
    _reject_ambiguous_dtype(readable_mdrt, f"{well_key}: readable MDRT_source_m")
    _reject_ambiguous_dtype(readable_tvdss, f"{well_key}: readable TVDSS_source_m")

    if len(hrs_raw.Top_Name_source) != hrs_mdrt.size:
        raise TopParsingError(f"{well_key}: HRS Top_Name_source length does not match MDRT_source_m length.")
    _readable_lengths = {
        len(readable_raw.TOP_NAME_source),
        int(readable_mdrt.size),
        int(readable_tvdss.size),
        len(readable_raw.NOTE_source),
    }
    if len(_readable_lengths) != 1:
        raise TopParsingError(
            f"{well_key}: readable TOP_NAME_source/MDRT_source_m/TVDSS_source_m/NOTE_source "
            f"lengths do not match."
        )

    _validate_name_tuple(hrs_raw.Top_Name_source, "HRS Top_Name_source", well_key)
    _validate_name_tuple(readable_raw.TOP_NAME_source, "readable TOP_NAME_source", well_key)
    _validate_name_tuple(readable_raw.NOTE_source, "readable NOTE_source", well_key)

    if hrs_mdrt.size and not np.all(np.isfinite(hrs_mdrt)):
        raise TopParsingError(f"{well_key}: HRS MDRT_source_m contains a non-finite (NaN/Inf) value.")
    if hrs_mdrt.size and np.any(hrs_mdrt < 0.0):
        raise TopParsingError(f"{well_key}: HRS MDRT_source_m contains a negative value.")
    if readable_mdrt.size and not np.all(np.isfinite(readable_mdrt)):
        raise TopParsingError(f"{well_key}: readable MDRT_source_m contains a non-finite (NaN/Inf) value.")
    if readable_mdrt.size and np.any(readable_mdrt < 0.0):
        raise TopParsingError(f"{well_key}: readable MDRT_source_m contains a negative value.")
    if readable_tvdss.size and not np.all(np.isfinite(readable_tvdss)):
        raise TopParsingError(f"{well_key}: readable TVDSS_source_m contains a non-finite (NaN/Inf) value.")

    mdrt_agreement_tolerance_m = _validate_mdrt_agreement_tolerance(mdrt_agreement_tolerance_m, well_key)

    issues: List[TopIngestionIssue] = []

    def err(code: str, message: str) -> None:
        issues.append(TopIngestionIssue("ERROR", code, message, well_key))

    def warn(code: str, message: str) -> None:
        issues.append(TopIngestionIssue("WARNING", code, message, well_key))

    # --- Canonical-name resolution: raw string as an alias key first,
    # then its whitespace-normalized form as an alias key, then the
    # normalized form itself. No fuzzy/similarity matching of any kind. ---
    def _canon(name: str) -> str:
        if name in marker_name_aliases:
            return marker_name_aliases[name]
        norm = normalize_marker_name(name)
        return marker_name_aliases.get(norm, norm)

    # --- Structural per-source QC: duplicate canonical names, ordering ---
    def _check_source(names: Tuple[str, ...], mdrt: np.ndarray, label: str) -> None:
        seen: Dict[str, int] = {}
        for i, n in enumerate(names):
            canon = _canon(n)
            if canon in seen:
                err(
                    "DUPLICATE_MARKER_NAME",
                    f"{label} row {i}: canonical marker name {canon!r} duplicates row {seen[canon]} "
                    f"in the same source - never silently merged.",
                )
            else:
                seen[canon] = i
        if mdrt.size >= 2 and not np.all(np.diff(mdrt) > 0.0):
            err(
                "MARKER_ORDER_REVERSAL",
                f"{label}: MDRT_m is not strictly increasing in file row order "
                f"(values: {mdrt.tolist()}) - a stratigraphic marker order reversal "
                f"is never silently sorted or accepted.",
            )

    _check_source(hrs_raw.Top_Name_source, hrs_raw.MDRT_source_m, "HRS")
    _check_source(readable_raw.TOP_NAME_source, readable_raw.MDRT_source_m, "readable")

    # --- Build canonical marker order: HRS order first, then any
    # readable-only markers appended in readable file order. Deterministic,
    # traceable to file order - never alphabetically re-sorted. ---
    hrs_by_canon: Dict[str, Tuple[int, str]] = {}
    for i, n in enumerate(hrs_raw.Top_Name_source):
        hrs_by_canon.setdefault(_canon(n), (i, n))
    readable_by_canon: Dict[str, Tuple[int, str]] = {}
    for i, n in enumerate(readable_raw.TOP_NAME_source):
        readable_by_canon.setdefault(_canon(n), (i, n))

    canonical_order: List[str] = list(hrs_by_canon.keys())
    for c in readable_by_canon.keys():
        if c not in hrs_by_canon:
            canonical_order.append(c)

    # Increment 5.1 (Finding 1 fix, further corrected in Increment 5.1.1):
    # the ERROR condition documented by `TopSourceReconciliationError`
    # ("zero canonical markers in common between the two sources") is the
    # INTERSECTION of the two sources' canonical marker names being empty
    # - never the emptiness of `canonical_order` above, which is a UNION.
    # Increment 5.1 gated this on "both sources non-empty AND intersection
    # empty" (plus a separate both-empty case), which left one remaining
    # gap: exactly ONE source empty, the other non-empty - the
    # intersection of an empty set with anything is itself empty, so this
    # is still a zero-common-markers condition, but the 5.1 condition's
    # `hrs_by_canon and readable_by_canon` guard (both dicts truthy/non-
    # empty) skipped it. Increment 5.1.1 replaces the whole condition with
    # the single, strictly equivalent-or-stronger check the intersection
    # itself: `not common_markers` is empty in EVERY zero-common-markers
    # case (both empty, either side alone empty, or both non-empty and
    # disjoint) and is never empty whenever at least one canonical marker
    # is genuinely shared - so a legitimate one-sided marker (HRS-only or
    # readable-only, alongside at least one shared marker) remains the
    # pre-existing, non-fatal NOT_COMPARABLE case, unaffected.
    common_markers = set(hrs_by_canon) & set(readable_by_canon)
    if not common_markers:
        err(
            "NO_COMMON_MARKERS",
            f"{well_key}: HRS and readable sources share zero canonical markers in common "
            f"(HRS canonical markers: {len(hrs_by_canon)}, readable canonical markers: "
            f"{len(readable_by_canon)}) - this includes the case where one source is "
            f"entirely empty and the other is not; a marker present in only one source is "
            f"legitimate ONLY when at least one other canonical marker is genuinely shared "
            f"between both sources, never merely tolerated as a bare one-sided set.",
        )

    entries: List[TopReconciliationEntry] = []
    for canon in canonical_order:
        in_hrs = canon in hrs_by_canon
        in_readable = canon in readable_by_canon
        hrs_row, hrs_name_raw = hrs_by_canon.get(canon, (None, None))
        readable_row, readable_name_raw = readable_by_canon.get(canon, (None, None))

        mdrt_hrs = float(hrs_raw.MDRT_source_m[hrs_row]) if in_hrs else None
        mdrt_readable = float(readable_raw.MDRT_source_m[readable_row]) if in_readable else None
        tvdss_readable = float(readable_raw.TVDSS_source_m[readable_row]) if in_readable else None
        note_readable = readable_raw.NOTE_source[readable_row] if in_readable else ""

        if in_hrs and in_readable:
            if hrs_name_raw == readable_name_raw:
                name_match_status = "exact"
            elif canon in marker_name_aliases.values() and (
                hrs_name_raw in marker_name_aliases or readable_name_raw in marker_name_aliases
            ):
                name_match_status = "aliased_match"
            else:
                name_match_status = "normalized_match"
            agreement = mdrt_readable - mdrt_hrs
            if abs(agreement) <= mdrt_agreement_tolerance_m:
                mdrt_status = "MATCHED"
            else:
                mdrt_status = "MISMATCH"
                warn(
                    "MDRT_MISMATCH",
                    f"{canon!r}: HRS MDRT={mdrt_hrs} m vs readable MDRT={mdrt_readable} m "
                    f"(difference {agreement:+.4f} m exceeds tolerance {mdrt_agreement_tolerance_m} m).",
                )
        elif in_hrs:
            name_match_status = "missing_in_readable"
            mdrt_status = "NOT_COMPARABLE"
            agreement = None
        else:
            name_match_status = "missing_in_hrs"
            mdrt_status = "NOT_COMPARABLE"
            agreement = None

        entries.append(
            TopReconciliationEntry(
                well_key=well_key,
                canonical_marker_name=canon,
                hrs_marker_name_raw=hrs_name_raw,
                readable_marker_name_raw=readable_name_raw,
                hrs_row_number=hrs_row,
                readable_row_number=readable_row,
                present_in_hrs=in_hrs,
                present_in_readable=in_readable,
                name_match_status=name_match_status,
                MDRT_source_hrs_m=mdrt_hrs,
                MDRT_source_readable_m=mdrt_readable,
                MDRT_agreement_readable_minus_hrs_m=agreement,
                mdrt_status=mdrt_status,
                TVDSS_source_readable_m=tvdss_readable,
                note_readable=note_readable,
                reconciliation_notes=(
                    "Present in both sources; MDRT agrees within tolerance." if mdrt_status == "MATCHED"
                    else "Present in both sources; MDRT disagreement registered above." if mdrt_status == "MISMATCH"
                    else f"Present only in {'HRS' if in_hrs else 'readable'} source."
                ),
            )
        )

    return tuple(issues), tuple(entries)


# ---------------------------------------------------------------------------
# Survey-corrected stratigraphic marker table
# ---------------------------------------------------------------------------
def build_formation_top_markers(
    well_key: str,
    reconciliation: Tuple[TopReconciliationEntry, ...],
    deviation_well_result: DeviationWellResult,
    well_identity_evidence_status: str,
) -> Tuple[Tuple[TopIngestionIssue, ...], Tuple[TopMarkerRecord, ...]]:
    """
    Build the corrected, auditable stratigraphic marker table for one
    well: for each reconciled canonical marker, decide the authoritative
    MDRT (see `TopMarkerRecord.mdrt_authority_basis`), then map it through
    the LOCKED `petrel_source_trace` survey trajectory (unmodified
    `p2mem.depth_mapping.map_las_md_to_tvd_tvdss`, called ONE MARKER AT A
    TIME so a single out-of-coverage marker is isolated and reported -
    `mapping_status = "rejected_outside_coverage"` - without blocking any
    other marker for the same well; see `p2mem.depth_mapping
    .ExtrapolationRejectedError`, never silently extrapolated).
    """
    issues: List[TopIngestionIssue] = []
    markers: List[TopMarkerRecord] = []

    for entry in reconciliation:
        if entry.mdrt_status == "MATCHED":
            mdrt_reconciled = entry.MDRT_source_hrs_m
            basis = "hrs_and_readable_agree"
        elif entry.mdrt_status == "MISMATCH":
            mdrt_reconciled = None
            basis = "disagreement_unresolved"
        elif entry.present_in_hrs:
            mdrt_reconciled = entry.MDRT_source_hrs_m
            basis = "hrs_only"
        else:
            mdrt_reconciled = entry.MDRT_source_readable_m
            basis = "readable_only"

        if mdrt_reconciled is None:
            issues.append(
                TopIngestionIssue(
                    "WARNING", "MDRT_UNRESOLVED_NOT_MAPPED",
                    f"{entry.canonical_marker_name!r}: MDRT disagreement between sources exceeds "
                    f"tolerance - this marker is EXCLUDED from survey mapping rather than silently "
                    f"choosing one source's value.",
                    well_key,
                )
            )
            markers.append(
                TopMarkerRecord(
                    well_key=well_key, canonical_marker_name=entry.canonical_marker_name,
                    MDRT_source_hrs_m=entry.MDRT_source_hrs_m, MDRT_source_readable_m=entry.MDRT_source_readable_m,
                    MDRT_reconciled_m=None, mdrt_authority_basis=basis,
                    TVDSS_source_m=entry.TVDSS_source_readable_m,
                    depth_basis_used=None, interpolation_method=None,
                    TVD_survey_m=None, TVDSS_survey_corrected_m=None,
                    TVDSS_residual_source_minus_survey_m=None,
                    mapping_status="not_mapped_mdrt_unresolved",
                    well_identity_evidence_status=well_identity_evidence_status,
                    notes=entry.reconciliation_notes,
                )
            )
            continue

        mdrt_array = np.asarray([mdrt_reconciled], dtype=np.float64)
        try:
            mapped = map_las_md_to_tvd_tvdss(well_key, mdrt_array, deviation_well_result)
        except ExtrapolationRejectedError as exc:
            issues.append(
                TopIngestionIssue(
                    "WARNING", "MARKER_OUTSIDE_SURVEY_COVERAGE",
                    f"{entry.canonical_marker_name!r} (MDRT={mdrt_reconciled} m): {exc}",
                    well_key,
                )
            )
            markers.append(
                TopMarkerRecord(
                    well_key=well_key, canonical_marker_name=entry.canonical_marker_name,
                    MDRT_source_hrs_m=entry.MDRT_source_hrs_m, MDRT_source_readable_m=entry.MDRT_source_readable_m,
                    MDRT_reconciled_m=mdrt_reconciled, mdrt_authority_basis=basis,
                    TVDSS_source_m=entry.TVDSS_source_readable_m,
                    depth_basis_used=None, interpolation_method=None,
                    TVD_survey_m=None, TVDSS_survey_corrected_m=None,
                    TVDSS_residual_source_minus_survey_m=None,
                    mapping_status="rejected_outside_coverage",
                    well_identity_evidence_status=well_identity_evidence_status,
                    notes=entry.reconciliation_notes,
                )
            )
            continue

        tvd_survey = float(mapped.tvd_mapped_m[0])
        tvdss_survey = float(mapped.tvdss_mapped_m[0])
        tvdss_source = entry.TVDSS_source_readable_m
        residual = (tvdss_source - tvdss_survey) if tvdss_source is not None else None

        markers.append(
            TopMarkerRecord(
                well_key=well_key, canonical_marker_name=entry.canonical_marker_name,
                MDRT_source_hrs_m=entry.MDRT_source_hrs_m, MDRT_source_readable_m=entry.MDRT_source_readable_m,
                MDRT_reconciled_m=mdrt_reconciled, mdrt_authority_basis=basis,
                TVDSS_source_m=tvdss_source,
                depth_basis_used=mapped.depth_basis_used, interpolation_method=mapped.interpolation_method,
                TVD_survey_m=tvd_survey, TVDSS_survey_corrected_m=tvdss_survey,
                TVDSS_residual_source_minus_survey_m=residual,
                mapping_status="mapped_within_coverage",
                well_identity_evidence_status=well_identity_evidence_status,
                notes=entry.reconciliation_notes,
            )
        )

    return tuple(issues), tuple(markers)


# ---------------------------------------------------------------------------
# High-level load functions
# ---------------------------------------------------------------------------
def load_formation_top_well(
    hrs_path: str,
    readable_path: str,
    hrs_contract: HRSTopFileContract,
    readable_contract: ReadableTopFileContract,
    marker_name_aliases: Dict[str, str],
    deviation_well_result: DeviationWellResult,
) -> FormationTopWellResult:
    """
    Parse, contract-resolve, reconcile, and survey-map one well's pair of
    formation-top files, returning a complete `FormationTopWellResult`.

    Raises `TopFileNotFoundError`, `TopParsingError`, `TopContractError`,
    or `TopSourceReconciliationError` (never returns a partially valid
    result).
    """
    well_key = hrs_contract.project_well_key

    def _tag(exc: BaseException, origin: str) -> BaseException:
        """
        Increment 5.1 (Finding 2 fix): attach which stage actually failed,
        and BOTH this well's source paths, to the exception before it
        propagates - so `load_formation_top_surveys` never has to guess
        (or default to the HRS path) when building a `TopIngestionFailure`.
        """
        exc.failure_origin = origin  # type: ignore[attr-defined]
        exc.hrs_path = hrs_path  # type: ignore[attr-defined]
        exc.readable_path = readable_path  # type: ignore[attr-defined]
        return exc

    try:
        hrs_header = parse_hrs_top_header(hrs_path)
        hrs_raw = read_hrs_top_rows(hrs_path)
    except (TopFileNotFoundError, TopParsingError) as exc:
        _tag(exc, "hrs")
        raise
    hrs_issues = resolve_hrs_top_contract(hrs_header, hrs_raw, hrs_contract)
    hrs_errors = tuple(i for i in hrs_issues if i.severity == "ERROR")
    if hrs_errors:
        raise _tag(
            TopContractError(
                f"{hrs_path}: {len(hrs_errors)} contract-resolution ERROR(s): "
                + "; ".join(f"[{i.code}] {i.message}" for i in hrs_errors),
                hrs_issues,
            ),
            "hrs",
        )

    try:
        readable_header = parse_readable_top_header(readable_path)
        readable_raw = read_readable_top_rows(readable_path)
    except (TopFileNotFoundError, TopParsingError) as exc:
        _tag(exc, "readable")
        raise
    readable_issues = resolve_readable_top_contract(readable_header, readable_raw, readable_contract)
    readable_errors = tuple(i for i in readable_issues if i.severity == "ERROR")
    if readable_errors:
        raise _tag(
            TopContractError(
                f"{readable_path}: {len(readable_errors)} contract-resolution ERROR(s): "
                + "; ".join(f"[{i.code}] {i.message}" for i in readable_errors),
                readable_issues,
            ),
            "readable",
        )

    recon_issues, reconciliation = reconcile_formation_top_sources(well_key, hrs_raw, readable_raw, marker_name_aliases)
    recon_errors = tuple(i for i in recon_issues if i.severity == "ERROR")
    if recon_errors:
        raise _tag(
            TopSourceReconciliationError(
                f"{well_key}: {len(recon_errors)} source-reconciliation ERROR(s): "
                + "; ".join(f"[{i.code}] {i.message}" for i in recon_errors),
                recon_issues,
            ),
            "reconciliation",
        )

    identity_status = (
        "verified"
        if hrs_contract.well_identity_evidence_status == "verified"
        and readable_contract.well_identity_evidence_status == "verified"
        else "inferred_unverified"
    )
    mapping_issues, markers = build_formation_top_markers(well_key, reconciliation, deviation_well_result, identity_status)

    all_issues = hrs_issues + readable_issues + recon_issues + mapping_issues
    return FormationTopWellResult(
        well_key=well_key,
        hrs_header=hrs_header, hrs_contract=hrs_contract, hrs_raw=hrs_raw,
        readable_header=readable_header, readable_contract=readable_contract, readable_raw=readable_raw,
        reconciliation=reconciliation, markers=markers,
        issues=all_issues, contract_status="PASSED",
    )


def load_formation_top_surveys(
    file_paths: Dict[str, Tuple[str, str]],
    hrs_contracts: Dict[str, HRSTopFileContract],
    readable_contracts: Dict[str, ReadableTopFileContract],
    marker_name_aliases: Dict[str, str],
    deviation_well_results: Dict[str, DeviationWellResult],
) -> Tuple[Dict[str, FormationTopWellResult], Dict[str, TopIngestionFailure]]:
    """
    Load a batch of formation-top file pairs keyed by well key, isolating
    expected per-well ingestion failures as typed `TopIngestionFailure`
    records. One well's failure never stops the others from loading.
    Never caught with a blanket `except Exception` - only the specific
    typed exceptions this module is documented to raise.

    `file_paths` maps well key -> `(hrs_path, readable_path)`.
    `deviation_well_results` maps well key -> the LOCKED
    `DeviationWellResult` for that well (required for every well passed
    here - a well with no locked deviation survey cannot have its markers
    survey-mapped and must not be included in this batch call).
    """
    results: Dict[str, FormationTopWellResult] = {}
    failures: Dict[str, TopIngestionFailure] = {}

    for well_key, (hrs_path, readable_path) in file_paths.items():
        hrs_basename = Path(hrs_path).name
        readable_basename = Path(readable_path).name
        hrs_contract = hrs_contracts.get(hrs_basename)
        readable_contract = readable_contracts.get(readable_basename)
        if hrs_contract is None or readable_contract is None:
            raise TopContractDefinitionError(
                f"No formation-top contract found for well key {well_key!r} "
                f"(hrs={hrs_basename!r}, readable={readable_basename!r}); contracts are keyed by "
                f"source filename and must be authored before ingestion."
            )
        deviation_result = deviation_well_results.get(well_key)
        if deviation_result is None:
            raise ValueError(
                f"No locked DeviationWellResult supplied for well key {well_key!r}; formation-top "
                f"markers cannot be survey-mapped without the well's locked deviation survey."
            )
        def _record_failure(exc: BaseException, error_type: str) -> None:
            """
            Increment 5.1 (Finding 2 fix): identify the actually-failing
            path from the exception's own `failure_origin` tag (set by
            `load_formation_top_well`), rather than unconditionally
            recording the HRS path regardless of which file/stage failed.
            Both source paths are always retained on the failure record so
            every consumer can sanitize both.
            """
            origin = getattr(exc, "failure_origin", "unknown")
            primary_path = readable_path if origin == "readable" else hrs_path
            failures[well_key] = TopIngestionFailure(
                well_key, primary_path, error_type, str(exc), exc,
                failure_origin=origin, hrs_path=hrs_path, readable_path=readable_path,
            )

        try:
            results[well_key] = load_formation_top_well(
                hrs_path, readable_path, hrs_contract, readable_contract, marker_name_aliases, deviation_result
            )
        except TopFileNotFoundError as exc:
            _record_failure(exc, "file_not_found")
        except TopParsingError as exc:
            _record_failure(exc, "parsing_failure")
        except TopContractError as exc:
            _record_failure(exc, "contract_failure")
        except TopSourceReconciliationError as exc:
            _record_failure(exc, "reconciliation_failure")

    return results, failures
