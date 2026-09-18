"""
p2mem.io.checkshot - Auditable checkshot (velocity survey) file parser and
per-file contract resolution (Increment 4).

Why this module exists
------------------------
The three approved checkshot files (Poseidon 2, Boreas 1, Proteus 1ST2)
are plain-text Schlumberger-format velocity surveys with a minimal,
fixed two-line header (one free-text survey statement, one tab-separated
column-header line: "Depth\\tTVDSS\\tOWT(sec)") followed by a three-column
data table. This is structurally much simpler than the Petrel deviation-
survey format (`p2mem.io.deviation`), but the same discipline is applied
at reduced complexity: STRUCTURAL PARSING (can the file even be
tokenized - is the two-line header present, does every data row have
exactly 3 numeric tokens) is kept separate from CONTRACT RESOLUTION (does
this specific file's actual header/data agree with what
`config/checkshot_contracts.yml` says it should be: filename, SHA-256,
exact header text, column order, row count, numeric ranges). A structural
defect is a `CheckshotParsingError`; a contract mismatch is a
`CheckshotContractError`. Both are always ERROR-severity and blocking.

Raw file identity is never altered: this module never rewrites, renames,
or "cleans" a raw checkshot file; it only reads it (recording identity by
SHA-256) and reports what it finds.

Depth-basis disclosure (DEPTH_BASIS_NOT_EXPLICITLY_DECLARED)
------------------------------------------------------------------
Every approved file's header declares OWT (seconds), "vertically
corrected, relative to SRD (MSL)", and supplies a TVDSS column - but its
first column is labelled only "Depth", never "MD". This module never
silently renames that column to `MD_m`; it is stored as `Depth_source_m`
(see `p2mem.checkshot_models`), and a WARNING-severity
`CheckshotIngestionIssue` (this code) is always raised on a successful
load, disclosing that the column's MD-like behavior must be, and was,
evaluated empirically (see `p2mem.time_depth.compare_checkshot_to_survey`,
invoked by `load_checkshot_file` whenever a locked survey trajectory is
supplied) rather than assumed from the header alone.

Well-identity evidence disclosure
------------------------------------
`Proteus1-Checkshot.txt` carries no embedded well identifier of its own;
its association with Proteus 1ST2 is declared in
`config/checkshot_contracts.yml` as `well_identity_evidence_status:
inferred_unverified` (filename, project context, and depth-tie
plausibility only - never independently proven by file content). This
module raises a dedicated, always-WARNING
`WELL_IDENTITY_INFERRED_UNVERIFIED` issue for any file contract declaring
that status, and never upgrades that status to "verified" on the strength
of a successful contract resolution (a clean structural/numeric match
does not, by itself, prove which physical well a file came from).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import yaml

from p2mem.checkshot_models import (
    VALID_CHECKSHOT_AVAILABILITY_STATUSES,
    VALID_IDENTITY_EVIDENCE_STATUSES,
    VALID_MODEL_USE_STATUSES,
    CheckshotFileContract,
    CheckshotHeaderInfo,
    CheckshotIngestionFailure,
    CheckshotIngestionIssue,
    CheckshotStationData,
    CheckshotWellResult,
)
from p2mem.time_depth import (
    TimeDepthError,
    build_axis_conditioned_tables_for_well,
    compare_checkshot_to_survey,
    compute_velocity_diagnostics,
    detect_and_condition_depth_ties,
)

__all__ = [
    "CheckshotFileNotFoundError",
    "CheckshotParsingError",
    "CheckshotContractDefinitionError",
    "CheckshotContractError",
    "DEPTH_BASIS_NOT_EXPLICITLY_DECLARED_CODE",
    "WELL_IDENTITY_INFERRED_UNVERIFIED_CODE",
    "load_checkshot_contract_config",
    "parse_checkshot_header",
    "read_checkshot_rows",
    "resolve_checkshot_contract",
    "load_checkshot_file",
    "load_checkshot_surveys",
]

DEPTH_BASIS_NOT_EXPLICITLY_DECLARED_CODE = "DEPTH_BASIS_NOT_EXPLICITLY_DECLARED"
WELL_IDENTITY_INFERRED_UNVERIFIED_CODE = "WELL_IDENTITY_INFERRED_UNVERIFIED"

_REQUIRED_COLUMN_COUNT = 3


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class CheckshotFileNotFoundError(FileNotFoundError):
    """The checkshot file path given to `load_checkshot_file` does not exist."""


class CheckshotParsingError(ValueError):
    """
    A structural defect in the checkshot text file itself: fewer than 2
    header lines, a data row without exactly 3 tab-separated numeric
    tokens, a non-finite (NaN/Inf) literal token, or no data rows at all.
    Raised before any contract is consulted.
    """


class CheckshotContractDefinitionError(ValueError):
    """
    `config/checkshot_contracts.yml` itself is malformed: a duplicate
    top-level file key, a missing required field, an invalid type, an
    unsupported enum value, or an internally inconsistent expected-value
    set (e.g. min > max).
    """


class CheckshotContractError(RuntimeError):
    """
    A specific file's actual parsed header or data does not agree with
    its `CheckshotFileContract`: wrong filename, SHA-256 mismatch, header
    text mismatch, column-order/count mismatch, row-count mismatch, or a
    numeric range outside the contract's declared tolerance. Carries
    `.issues` (the full tuple, ERROR and WARNING alike).
    """

    def __init__(self, message: str, issues: Tuple[CheckshotIngestionIssue, ...]):
        super().__init__(message)
        self.issues = issues


# ---------------------------------------------------------------------------
# Contract configuration (config/checkshot_contracts.yml)
# ---------------------------------------------------------------------------
class _NoDuplicateKeySafeLoader(yaml.SafeLoader):
    """
    A `yaml.SafeLoader` subclass that raises on a duplicate mapping key
    rather than silently keeping only the last occurrence. File-scoped to
    this module (mirrors, but does not import, the identical private
    pattern in `p2mem.io.deviation` - that class is private to its own
    module and not exported for reuse).
    """


def _construct_mapping_no_duplicates(loader: yaml.SafeLoader, node, deep: bool = False):
    mapping: Dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise CheckshotContractDefinitionError(
                f"Duplicate key {key!r} found while parsing checkshot contract YAML "
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
    "project_well_key",
    "well_identity_evidence_status",
    "well_identity_evidence_notes",
    "model_use_status",
    "expected_survey_statement",
    "expected_column_header_line",
    "expected_column_order",
    "expected_time_type",
    "expected_time_unit",
    "expected_vertical_correction_fragment",
    "expected_srd_reference_fragment",
    "expected_row_count",
    "expected_depth_min_m",
    "expected_depth_max_m",
    "expected_tvdss_min_m",
    "expected_tvdss_max_m",
    "expected_owt_min_s",
    "expected_owt_max_s",
    "numeric_range_tolerance",
    "depth_basis_interpretation_status",
    "duplicate_tie_policy",
    "interpolation_policy",
    "extrapolation_policy",
    "notes",
)


def _num(value, field_name: str, filename: str):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CheckshotContractDefinitionError(
            f"{filename}: field {field_name!r} must be numeric, got {value!r}."
        )
    return float(value)


def load_checkshot_contract_config(yaml_path: str) -> Dict[str, CheckshotFileContract]:
    """
    Load and validate `config/checkshot_contracts.yml`, returning a dict
    keyed by exact source filename (e.g. "Poseidon2-Checkshot.txt").
    Raises `CheckshotContractDefinitionError` for any structural or
    internal-consistency problem in the YAML itself, before any checkshot
    file is opened.
    """
    with open(yaml_path, "r", encoding="utf-8") as fh:
        raw = yaml.load(fh, Loader=_NoDuplicateKeySafeLoader)

    if not isinstance(raw, dict) or "files" not in raw:
        raise CheckshotContractDefinitionError(
            f"{yaml_path}: top-level YAML must be a mapping with a 'files' key."
        )
    files_section = raw["files"]
    if not isinstance(files_section, dict) or not files_section:
        raise CheckshotContractDefinitionError(f"{yaml_path}: 'files' must be a non-empty mapping.")

    contracts: Dict[str, CheckshotFileContract] = {}
    for filename, entry in files_section.items():
        if not isinstance(entry, dict):
            raise CheckshotContractDefinitionError(f"{filename}: contract entry must be a mapping.")
        missing = [f for f in _REQUIRED_FILE_FIELDS if f not in entry]
        if missing:
            raise CheckshotContractDefinitionError(f"{filename}: missing required field(s) {missing}.")

        col_order = entry["expected_column_order"]
        if (
            not isinstance(col_order, list)
            or not col_order
            or len(set(col_order)) != len(col_order)
            or not all(isinstance(c, str) for c in col_order)
        ):
            raise CheckshotContractDefinitionError(
                f"{filename}: expected_column_order must be a list of unique strings."
            )
        if len(col_order) != _REQUIRED_COLUMN_COUNT:
            raise CheckshotContractDefinitionError(
                f"{filename}: expected_column_order must have exactly {_REQUIRED_COLUMN_COUNT} "
                f"entries (Depth, TVDSS, OWT); got {len(col_order)}."
            )

        identity_status = entry["well_identity_evidence_status"]
        if identity_status not in VALID_IDENTITY_EVIDENCE_STATUSES:
            raise CheckshotContractDefinitionError(
                f"{filename}: well_identity_evidence_status must be one of "
                f"{VALID_IDENTITY_EVIDENCE_STATUSES}, got {identity_status!r}."
            )
        model_use = entry["model_use_status"]
        if model_use not in VALID_MODEL_USE_STATUSES:
            raise CheckshotContractDefinitionError(
                f"{filename}: model_use_status must be one of {VALID_MODEL_USE_STATUSES}, "
                f"got {model_use!r}."
            )

        row_count = entry["expected_row_count"]
        if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count < 1:
            raise CheckshotContractDefinitionError(
                f"{filename}: expected_row_count must be a positive integer."
            )

        depth_min = _num(entry["expected_depth_min_m"], "expected_depth_min_m", filename)
        depth_max = _num(entry["expected_depth_max_m"], "expected_depth_max_m", filename)
        tvdss_min = _num(entry["expected_tvdss_min_m"], "expected_tvdss_min_m", filename)
        tvdss_max = _num(entry["expected_tvdss_max_m"], "expected_tvdss_max_m", filename)
        owt_min = _num(entry["expected_owt_min_s"], "expected_owt_min_s", filename)
        owt_max = _num(entry["expected_owt_max_s"], "expected_owt_max_s", filename)
        tolerance = _num(entry["numeric_range_tolerance"], "numeric_range_tolerance", filename)
        if tolerance < 0.0:
            raise CheckshotContractDefinitionError(f"{filename}: numeric_range_tolerance must be >= 0.")
        for lo, hi, name in (
            (depth_min, depth_max, "depth"),
            (tvdss_min, tvdss_max, "tvdss"),
            (owt_min, owt_max, "owt"),
        ):
            if lo > hi:
                raise CheckshotContractDefinitionError(f"{filename}: expected {name} min > max.")

        for f in (
            "expected_sha256",
            "project_well_key",
            "well_identity_evidence_notes",
            "expected_survey_statement",
            "expected_column_header_line",
            "expected_time_type",
            "expected_time_unit",
            "expected_vertical_correction_fragment",
            "expected_srd_reference_fragment",
            "depth_basis_interpretation_status",
            "duplicate_tie_policy",
            "interpolation_policy",
            "extrapolation_policy",
            "notes",
        ):
            if not isinstance(entry[f], str) or not entry[f].strip():
                raise CheckshotContractDefinitionError(f"{filename}: field {f!r} must be a non-empty string.")

        contracts[filename] = CheckshotFileContract(
            source_filename=filename,
            expected_sha256=entry["expected_sha256"],
            project_well_key=entry["project_well_key"],
            well_identity_evidence_status=identity_status,
            well_identity_evidence_notes=entry["well_identity_evidence_notes"],
            model_use_status=model_use,
            expected_survey_statement=entry["expected_survey_statement"],
            expected_column_header_line=entry["expected_column_header_line"],
            expected_column_order=tuple(col_order),
            expected_column_count=_REQUIRED_COLUMN_COUNT,
            expected_time_type=entry["expected_time_type"],
            expected_time_unit=entry["expected_time_unit"],
            expected_vertical_correction_fragment=entry["expected_vertical_correction_fragment"],
            expected_srd_reference_fragment=entry["expected_srd_reference_fragment"],
            expected_row_count=row_count,
            expected_depth_min_m=depth_min,
            expected_depth_max_m=depth_max,
            expected_tvdss_min_m=tvdss_min,
            expected_tvdss_max_m=tvdss_max,
            expected_owt_min_s=owt_min,
            expected_owt_max_s=owt_max,
            numeric_range_tolerance=tolerance,
            depth_basis_interpretation_status=entry["depth_basis_interpretation_status"],
            duplicate_tie_policy=entry["duplicate_tie_policy"],
            interpolation_policy=entry["interpolation_policy"],
            extrapolation_policy=entry["extrapolation_policy"],
            notes=entry["notes"],
        )
    return contracts


# ---------------------------------------------------------------------------
# Structural parsing
# ---------------------------------------------------------------------------
def parse_checkshot_header(path: str) -> CheckshotHeaderInfo:
    """
    Parse the fixed two-line checkshot header: line 1 is a free-text
    survey statement, line 2 is the tab-separated column-header line.
    Raises `CheckshotFileNotFoundError` if the path does not exist, or
    `CheckshotParsingError` if fewer than 2 lines are present.

    Raw files in this project use CRLF line endings; opened in universal-
    newlines text mode, Python normalizes this transparently. That is
    disclosed here (`line_ending_convention`), not "corrected" - the raw
    file bytes on disk are never altered by this module.
    """
    p = Path(path)
    if not p.exists():
        raise CheckshotFileNotFoundError(f"Checkshot file not found: {path}")

    raw_bytes = p.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    line_ending = "CRLF" if b"\r\n" in raw_bytes else ("LF" if b"\n" in raw_bytes else "NONE")

    text = raw_bytes.decode("utf-8")
    lines = text.splitlines()
    if len(lines) < 2:
        raise CheckshotParsingError(
            f"{path}: expected at least 2 header lines (survey statement, column-header "
            f"line); found {len(lines)}."
        )
    survey_statement = lines[0]
    column_header_line = lines[1]
    column_names = tuple(column_header_line.split("\t"))
    if len(column_names) != _REQUIRED_COLUMN_COUNT:
        raise CheckshotParsingError(
            f"{path}: column-header line must have exactly {_REQUIRED_COLUMN_COUNT} "
            f"tab-separated fields; found {len(column_names)} in {column_header_line!r}."
        )

    return CheckshotHeaderInfo(
        source_filename=p.name,
        sha256=sha256,
        survey_statement=survey_statement,
        column_header_line=column_header_line,
        column_names=column_names,
        line_ending_convention=line_ending,
    )


def read_checkshot_rows(path: str) -> CheckshotStationData:
    """
    Parse the data rows (all non-empty lines after the 2-line header) into
    raw `CheckshotStationData`. Every row must have exactly 3 tab-
    separated numeric tokens; a blank line is permitted only as a trailing
    end-of-file artifact (all 3 approved files end this way) - a blank
    line found BEFORE the last non-empty line is a structural defect.
    """
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    data_lines = lines[2:]

    last_nonblank = -1
    for i, ln in enumerate(data_lines):
        if ln.strip():
            last_nonblank = i
    if last_nonblank < 0:
        raise CheckshotParsingError(f"{path}: no data rows found after the 2-line header.")

    depth_vals, tvdss_vals, owt_vals = [], [], []
    for i, ln in enumerate(data_lines[: last_nonblank + 1]):
        if not ln.strip():
            raise CheckshotParsingError(
                f"{path}: blank line found at data row {i + 1} before the last data row; "
                f"only a trailing blank line (end-of-file artifact) is permitted."
            )
        parts = ln.split("\t")
        if len(parts) != _REQUIRED_COLUMN_COUNT:
            raise CheckshotParsingError(
                f"{path}: data row {i + 1} has {len(parts)} tab-separated field(s), "
                f"expected {_REQUIRED_COLUMN_COUNT}: {ln!r}"
            )
        try:
            d, t, o = float(parts[0]), float(parts[1]), float(parts[2])
        except ValueError as exc:
            raise CheckshotParsingError(
                f"{path}: data row {i + 1} contains a non-numeric token: {ln!r} ({exc})"
            ) from exc
        if not (np.isfinite(d) and np.isfinite(t) and np.isfinite(o)):
            raise CheckshotParsingError(
                f"{path}: data row {i + 1} contains a non-finite (NaN/Inf) value: {ln!r}"
            )
        depth_vals.append(d)
        tvdss_vals.append(t)
        owt_vals.append(o)

    return CheckshotStationData(
        Depth_source_m=np.asarray(depth_vals, dtype=np.float64),
        TVDSS_source_m=np.asarray(tvdss_vals, dtype=np.float64),
        OWT_source_s=np.asarray(owt_vals, dtype=np.float64),
    )


# ---------------------------------------------------------------------------
# Contract resolution
# ---------------------------------------------------------------------------
def resolve_checkshot_contract(
    header: CheckshotHeaderInfo,
    stations: CheckshotStationData,
    contract: CheckshotFileContract,
) -> Tuple[CheckshotIngestionIssue, ...]:
    """
    Compare the actual parsed header/data against `contract`, returning
    the complete tuple of issues (ERROR and WARNING). Never raises itself
    - `load_checkshot_file` raises `CheckshotContractError` if any ERROR
    is present. Blocking (ERROR) checks: filename, SHA-256, header text
    (both lines), column order/count, row count, and each numeric range
    beyond `numeric_range_tolerance`. Non-blocking (WARNING) disclosures:
    depth-basis-not-explicitly-declared (always) and well-identity-
    inferred-unverified (only for a contract declaring that status).
    """
    issues: list = []

    def err(code: str, message: str) -> None:
        issues.append(CheckshotIngestionIssue("ERROR", code, message, header.source_filename))

    def warn(code: str, message: str) -> None:
        issues.append(CheckshotIngestionIssue("WARNING", code, message, header.source_filename))

    if header.source_filename != contract.source_filename:
        err(
            "FILENAME_MISMATCH",
            f"Actual filename {header.source_filename!r} does not match contract key "
            f"{contract.source_filename!r}.",
        )
    if header.sha256 != contract.expected_sha256:
        err(
            "SHA256_MISMATCH",
            f"Actual SHA-256 {header.sha256!r} does not match expected "
            f"{contract.expected_sha256!r}; raw file identity could not be confirmed.",
        )
    if header.survey_statement != contract.expected_survey_statement:
        err(
            "SURVEY_STATEMENT_MISMATCH",
            f"Actual survey-statement line {header.survey_statement!r} does not match "
            f"expected {contract.expected_survey_statement!r}.",
        )
    if header.column_header_line != contract.expected_column_header_line:
        err(
            "COLUMN_HEADER_LINE_MISMATCH",
            f"Actual column-header line {header.column_header_line!r} does not match "
            f"expected {contract.expected_column_header_line!r}.",
        )
    if header.column_names != contract.expected_column_order:
        err(
            "COLUMN_ORDER_MISMATCH",
            f"Actual column order {header.column_names!r} does not match expected "
            f"{contract.expected_column_order!r}.",
        )
    if len(header.column_names) != contract.expected_column_count:
        err(
            "COLUMN_COUNT_MISMATCH",
            f"Actual column count {len(header.column_names)} does not match expected "
            f"{contract.expected_column_count}.",
        )
    if contract.expected_vertical_correction_fragment not in header.survey_statement:
        err(
            "VERTICAL_CORRECTION_STATEMENT_MISSING",
            f"Expected vertical-correction statement fragment "
            f"{contract.expected_vertical_correction_fragment!r} not found in survey "
            f"statement {header.survey_statement!r}.",
        )
    if contract.expected_srd_reference_fragment not in header.survey_statement:
        err(
            "SRD_REFERENCE_STATEMENT_MISSING",
            f"Expected SRD-reference statement fragment "
            f"{contract.expected_srd_reference_fragment!r} not found in survey statement "
            f"{header.survey_statement!r}.",
        )

    n_rows = int(stations.Depth_source_m.size)
    if n_rows != contract.expected_row_count:
        err(
            "ROW_COUNT_MISMATCH",
            f"Actual row count {n_rows} does not match expected {contract.expected_row_count}.",
        )

    tol = contract.numeric_range_tolerance
    for label, actual_min, actual_max, exp_min, exp_max in (
        ("Depth_source_m", float(stations.Depth_source_m.min()), float(stations.Depth_source_m.max()),
         contract.expected_depth_min_m, contract.expected_depth_max_m),
        ("TVDSS_source_m", float(stations.TVDSS_source_m.min()), float(stations.TVDSS_source_m.max()),
         contract.expected_tvdss_min_m, contract.expected_tvdss_max_m),
        ("OWT_source_s", float(stations.OWT_source_s.min()), float(stations.OWT_source_s.max()),
         contract.expected_owt_min_s, contract.expected_owt_max_s),
    ):
        if abs(actual_min - exp_min) > tol or abs(actual_max - exp_max) > tol:
            err(
                "NUMERIC_RANGE_MISMATCH",
                f"{label}: actual range [{actual_min}, {actual_max}] does not match expected "
                f"[{exp_min}, {exp_max}] within tolerance {tol}.",
            )

    # Non-blocking disclosures.
    warn(
        DEPTH_BASIS_NOT_EXPLICITLY_DECLARED_CODE,
        "This file's header labels its first column only 'Depth', never explicitly 'MD'. "
        "'Depth_source_m' is preserved under that literal name (never silently renamed to "
        "MD_m); whether it behaves as measured depth is evaluated empirically against the "
        "locked deviation-survey MD->TVDSS relationship for this well "
        "(see p2mem.time_depth.compare_checkshot_to_survey / "
        "checkshot_depth_tie_qc.csv), not assumed from the header.",
    )
    if contract.well_identity_evidence_status == "inferred_unverified":
        warn(
            WELL_IDENTITY_INFERRED_UNVERIFIED_CODE,
            f"This file's association with project well {contract.project_well_key!r} is "
            f"NOT independently proven by file content (no embedded well identifier); it "
            f"is inferred from filename, project context, and depth-tie plausibility only. "
            f"{contract.well_identity_evidence_notes} model_use_status="
            f"{contract.model_use_status!r} - never treated as verified, and never "
            f"transferred into another well's primary time-depth model.",
        )

    return tuple(issues)


# ---------------------------------------------------------------------------
# High-level load functions
# ---------------------------------------------------------------------------
def load_checkshot_file(
    path: str,
    contract: CheckshotFileContract,
    *,
    survey_md_m: "np.ndarray | None" = None,
    survey_tvd_m: "np.ndarray | None" = None,
    datum_elevation_m: "float | None" = None,
) -> CheckshotWellResult:
    """
    Parse, contract-resolve, condition, and diagnose one checkshot file,
    returning a complete `CheckshotWellResult`.

    If `survey_md_m`/`survey_tvd_m`/`datum_elevation_m` are supplied (the
    locked `petrel_source_trace` survey for the SAME well, per
    `config/deviation_survey_contracts.yml`), the checkshot-vs-survey
    depth-reference comparison is computed and attached as
    `.depth_comparison`; otherwise it is `None` (no survey available for
    this well - never fabricated).

    Also builds (Increment 4.1) BOTH order-invariant axis-conditioned
    lookup tables (`.axis_tables["tvdss_to_owt"]`,
    `.axis_tables["owt_to_tvdss"]`) and the combined axis-tie register
    (`.axis_tie_entries`) - see `p2mem.time_depth
    .build_axis_conditioned_tables_for_well`. TVDSS and OWT are NOT
    guaranteed strictly increasing after Depth-tie conditioning alone (a
    real, distinct Depth value can carry an equal TVDSS or OWT to its
    neighbor); this call raises `TimeDepthError` only for a genuine
    reversal (never observed in any of the three approved real files),
    not for an ordinary tie.

    Raises `CheckshotFileNotFoundError`, `CheckshotParsingError`,
    `CheckshotContractError`, or (only for a genuine axis reversal after
    Depth-tie conditioning, not for an ordinary tie) `TimeDepthError`
    (never returns a partially valid result).

    "Genuine axis reversal" here (Increment 4.1.1 clarification) means any
    strictly negative step in the ORIGINAL, ungrouped axis sequence,
    including a reversal that returns to an already-seen value (e.g.
    `[100.0, 200.0, 100.0]`) - not only a reversal that survives global
    exact-value grouping. See `p2mem.time_depth
    .build_axis_conditioned_lookup_table` for the full corrected
    detection logic and `INCREMENT_04_1_1_MANIFEST.md` for the audit
    finding this corrects.
    """
    header = parse_checkshot_header(path)
    stations = read_checkshot_rows(path)
    issues = resolve_checkshot_contract(header, stations, contract)

    error_issues = tuple(i for i in issues if i.severity == "ERROR")
    if error_issues:
        raise CheckshotContractError(
            f"{path}: {len(error_issues)} contract-resolution ERROR(s): "
            + "; ".join(f"[{i.code}] {i.message}" for i in error_issues),
            issues,
        )

    ties, conditioned = detect_and_condition_depth_ties(
        contract.project_well_key,
        stations.Depth_source_m,
        stations.TVDSS_source_m,
        stations.OWT_source_s,
    )
    velocity = compute_velocity_diagnostics(contract.project_well_key, conditioned)

    # Increment 4.1: build BOTH order-invariant axis-conditioned lookup
    # tables (tvdss_to_owt, owt_to_tvdss) once per well here, so every
    # downstream consumer (interpolation calls, the CSV/JSON exporters,
    # the notebook) shares the same tables and tie register rather than
    # each silently rebuilding its own - see p2mem.time_depth module
    # docstring, "Order-invariant axis-tie conditioning".
    axis_tie_entries, axis_tables = build_axis_conditioned_tables_for_well(
        contract.project_well_key, conditioned
    )

    depth_comparison = None
    if survey_md_m is not None and survey_tvd_m is not None and datum_elevation_m is not None:
        depth_comparison = compare_checkshot_to_survey(
            contract.project_well_key,
            stations.Depth_source_m,
            stations.TVDSS_source_m,
            survey_md_m,
            survey_tvd_m,
            datum_elevation_m,
            depth_basis_interpretation_status=contract.depth_basis_interpretation_status,
        )

    return CheckshotWellResult(
        header=header,
        contract=contract,
        raw=stations,
        duplicate_ties=ties,
        conditioned=conditioned,
        velocity=velocity,
        depth_comparison=depth_comparison,
        issues=issues,
        contract_status="PASSED",
        axis_tie_entries=axis_tie_entries,
        axis_tables=axis_tables,
    )


def load_checkshot_surveys(
    file_paths: Dict[str, str],
    contracts: Dict[str, CheckshotFileContract],
    *,
    survey_trajectories: "Dict[str, tuple] | None" = None,
) -> Tuple[Dict[str, CheckshotWellResult], Dict[str, CheckshotIngestionFailure]]:
    """
    Load a batch of checkshot files keyed by well key (e.g. "Poseidon_2"),
    isolating expected per-well ingestion failures as typed
    `CheckshotIngestionFailure` records. One well's failure never stops
    the others from loading - this now explicitly includes a
    `TimeDepthError` raised anywhere inside `load_checkshot_file` (Depth-
    tie conditioning, axis-tie conditioning, or checkshot-vs-survey
    comparison), which is caught per well and recorded with
    `error_type="numerical_conditioning_failure"` (Increment 4.1.1 fix -
    the Increment 4.1 implementation caught only file/parsing/contract
    errors, so a numerical defect in one well's data could previously
    stop the entire batch). Never caught with a blanket `except
    Exception` - only the specific typed exceptions this module and
    `p2mem.time_depth` are documented to raise.

    `contracts` is keyed by SOURCE FILENAME (as in
    `config/checkshot_contracts.yml`); `file_paths` is keyed by WELL KEY.
    `survey_trajectories`, if given, maps well key ->
    (survey_md_m, survey_tvd_m, datum_elevation_m) for wells that have a
    locked deviation survey available for the depth-reference comparison.
    """
    results: Dict[str, CheckshotWellResult] = {}
    failures: Dict[str, CheckshotIngestionFailure] = {}
    survey_trajectories = survey_trajectories or {}

    for well_key, path in file_paths.items():
        basename = Path(path).name
        contract = contracts.get(basename)
        if contract is None:
            raise CheckshotContractDefinitionError(
                f"No checkshot contract found for file {basename!r} (well key {well_key!r}); "
                f"contracts are keyed by source filename and must be authored before ingestion."
            )
        survey_md_m = survey_tvd_m = datum_elevation_m = None
        if well_key in survey_trajectories:
            survey_md_m, survey_tvd_m, datum_elevation_m = survey_trajectories[well_key]
        try:
            results[well_key] = load_checkshot_file(
                path, contract,
                survey_md_m=survey_md_m, survey_tvd_m=survey_tvd_m, datum_elevation_m=datum_elevation_m,
            )
        except CheckshotFileNotFoundError as exc:
            failures[well_key] = CheckshotIngestionFailure(
                well_key=well_key, source_path=path, error_type="file_not_found",
                message=str(exc), exception=exc,
            )
        except CheckshotParsingError as exc:
            failures[well_key] = CheckshotIngestionFailure(
                well_key=well_key, source_path=path, error_type="parsing_failure",
                message=str(exc), exception=exc,
            )
        except CheckshotContractError as exc:
            failures[well_key] = CheckshotIngestionFailure(
                well_key=well_key, source_path=path, error_type="contract_failure",
                message=str(exc), exception=exc,
            )
        except TimeDepthError as exc:
            # Increment 4.1.1 fix (Blocking Defect 4): a numerical/
            # structural conditioning failure (Depth-tie conditioning,
            # axis-tie conditioning, checkshot-vs-survey comparison, or
            # any other TimeDepthError-raising validation inside
            # load_checkshot_file) must isolate exactly like every other
            # expected per-well failure above - it must NOT be allowed to
            # propagate out of this batch loader and stop every other
            # well from loading. TimeDepthError messages are built from
            # well_key and numeric values only (never a file path), so
            # str(exc) here carries no absolute-path leakage risk.
            failures[well_key] = CheckshotIngestionFailure(
                well_key=well_key, source_path=path, error_type="numerical_conditioning_failure",
                message=str(exc), exception=exc,
            )

    return results, failures
