"""
p2mem.top_models - Typed, documented result/schema objects for the
Increment 5 formation-top ingestion, source-reconciliation, and
survey-corrected stratigraphic depth layer.

Design rationale
-----------------
Mirrors `p2mem.deviation_models` (Increment 3) and `p2mem.checkshot_models`
(Increment 4): every object here is a frozen `dataclass`, nothing here
performs I/O or numerical computation, and every array/field name is
explicit about what it holds (raw vs. reconciled vs. survey-derived - see
"Naming discipline" below). This module collects every typed object used
by `p2mem.io.tops` and `p2mem.io.tops_inventory`.

Two source representations, reconciled - never silently preferred
--------------------------------------------------------------------
Each approved well (Poseidon 2, Boreas 1) has TWO independently supplied
formation-top files:

* an "HRS" file (`Top_Name`, `MDRT_m` only - no TVDSS, no well name
  embedded in the file body; the well association rests on the filename
  alone);
* a "selected readable" file (`TOP_NAME`, `MDRT_M`, `TVDSS_M`, `NOTE`,
  preceded by `#`-prefixed comment lines that NAME the well - project-
  supplied metadata, not independently verified file content).

Neither file is treated as more authoritative than the other for MDRT
placement: `p2mem.io.tops` explicitly RECONCILES the two (exact/
normalized/aliased name matching, MDRT cross-check within a documented
tolerance) and registers every match, mismatch, and single-source marker
in `TopReconciliationEntry` - never silently picking one file's value.
Supplied TVDSS (only ever present in the "selected readable" file) is
preserved under its own `_source_` name and is NEVER treated as the
corrected depth; the project's corrected stratigraphic depth is always
`TVDSS_survey_corrected_m`, computed by mapping the well's reconciled
MDRT through the LOCKED Increment 3.1.1 `petrel_source_trace` survey
trajectory (`p2mem.depth_mapping.map_las_md_to_tvd_tvdss` - reused
unmodified; this module never reimplements minimum curvature or the
TVD/TVDSS formula). See `TopMarkerRecord` and the module-level residual-
sign-convention note below.

Naming discipline (explicit, unit-suffixed names - project-wide policy)
-------------------------------------------------------------------------
* `MDRT_source_hrs_m` / `MDRT_source_readable_m` - each source file's own
  literal MDRT value for a marker, UNMODIFIED. Never overwritten.
* `MDRT_reconciled_m` - the single MDRT value actually used for depth
  mapping, chosen ONLY when both sources agree within tolerance (or only
  one source supplies the marker); see `mdrt_authority_basis`. Never
  silently chosen when the two sources disagree beyond tolerance - such a
  marker is excluded from mapping and reported (`mapping_status ==
  "not_mapped_mdrt_unresolved"`).
* `TVDSS_source_m` - the "selected readable" file's own supplied TVDSS
  column, UNMODIFIED, preserved for residual/QC comparison only.
* `TVD_survey_m` / `TVDSS_survey_corrected_m` - the project's corrected
  depth representation, computed by mapping `MDRT_reconciled_m` through
  the locked survey trajectory (`TVDSS_survey_corrected_m = TVD_survey_m
  - datum_elevation_m`, identical convention to
  `p2mem.depth_mapping`/`p2mem.checkshot_models`).
* `TVDSS_residual_source_minus_survey_m` - the ONE explicit, named
  residual field used everywhere in this layer (never a bare `error_m` or
  similarly ambiguous name):

      TVDSS_residual_source_minus_survey_m = TVDSS_source_m - TVDSS_survey_corrected_m

  Positive means the source-supplied TVDSS is DEEPER (more positive) than
  the survey-corrected value at the same reconciled MDRT.

Evidence-status vocabulary (reused from `p2mem.checkshot_models`)
----------------------------------------------------------------------
`well_identity_evidence_status` reuses the project's established two-value
vocabulary: "verified" (the file's own content, or an independently
verified cross-reference, proves which well it belongs to) or
"inferred_unverified" (association rests on filename and/or project-
supplied in-file comments only - see `p2mem.io.tops` module docstring for
why NEITHER of this increment's two file representations is ever
described as "verified" by content alone). `model_use_status` is likewise
reused: every approved well's formation tops here are declared
"primary_model" (both Poseidon 2 and Boreas 1 formation-top sets feed the
project's stratigraphic marker framework equally - there is no
primary/qc_only distinction analogous to Increment 4's checkshot layer,
because reconciliation, not selection-of-one-well's-curve, is this
increment's authority mechanism; this is declared explicitly in the
contract, not left implicit). `formation_top_availability` mirrors
`CheckshotAvailabilityRecord.checkshot_availability` exactly
("AVAILABLE" / "NOT_AVAILABLE").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import numpy as np

__all__ = [
    "STATUS_PASS",
    "STATUS_WARNING",
    "STATUS_FAIL",
    "VALID_IDENTITY_EVIDENCE_STATUSES",
    "VALID_MODEL_USE_STATUSES",
    "VALID_TOP_AVAILABILITY_STATUSES",
    "VALID_REPRESENTATION_TYPES",
    "VALID_NAME_MATCH_STATUSES",
    "VALID_MDRT_STATUSES",
    "VALID_MAPPING_STATUSES",
    "VALID_TOP_FAILURE_ORIGINS",
    "HRSTopHeaderInfo",
    "ReadableTopHeaderInfo",
    "HRSTopFileContract",
    "ReadableTopFileContract",
    "TopIngestionIssue",
    "HRSTopStationData",
    "ReadableTopStationData",
    "TopReconciliationEntry",
    "TopMarkerRecord",
    "TopIngestionFailure",
    "FormationTopWellResult",
    "FormationTopAvailabilityRecord",
]

# ---------------------------------------------------------------------------
# Shared status vocabulary (mirrors p2mem.deviation_models / checkshot_models)
# ---------------------------------------------------------------------------
STATUS_PASS = "PASS"
STATUS_WARNING = "WARNING"
STATUS_FAIL = "FAIL"

VALID_IDENTITY_EVIDENCE_STATUSES = ("verified", "inferred_unverified")
VALID_MODEL_USE_STATUSES = ("primary_model", "qc_only")
VALID_TOP_AVAILABILITY_STATUSES = ("AVAILABLE", "NOT_AVAILABLE")
VALID_REPRESENTATION_TYPES = ("HRS_MDRT_only", "selected_readable_MDRT_TVDSS")
VALID_NAME_MATCH_STATUSES = (
    "exact",
    "normalized_match",
    "aliased_match",
    "missing_in_hrs",
    "missing_in_readable",
)
VALID_MDRT_STATUSES = ("MATCHED", "MISMATCH", "NOT_COMPARABLE")
VALID_MAPPING_STATUSES = (
    "mapped_within_coverage",
    "rejected_outside_coverage",
    "not_mapped_mdrt_unresolved",
)

# Increment 5.1 (Finding 2 fix) - identifies which stage of ingestion a
# `TopIngestionFailure` actually originated from, so the correct source
# path(s) can be sanitized wherever the failure is exported. "unknown" is
# reserved for a `TopIngestionFailure` built without this classification
# (e.g. directly by a caller/test predating this field) - never assumed to
# be "hrs" by default.
VALID_TOP_FAILURE_ORIGINS = ("hrs", "readable", "reconciliation", "mapping", "unknown")


# ---------------------------------------------------------------------------
# Raw header / provenance - one dataclass per file representation, since the
# two formats are structurally different (mirrors p2mem.io.checkshot vs
# p2mem.io.deviation each having their own header dataclass).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HRSTopHeaderInfo:
    """
    The literal, structurally parsed header of one "HRS" formation-top
    file: a single tab-separated column-header line (`Top_Name`,
    `MDRT_m`), no comment lines, no embedded well name anywhere in the
    file body. `well_identity_source` is always the literal string
    `"filename_only"` - this is stated here as a factual, structural
    property of the file format, never as a claim of verification.
    """

    source_filename: str
    sha256: str
    column_header_line: str
    column_names: Tuple[str, ...]
    well_identity_source: str  # always "filename_only" for this format
    line_ending_convention: str
    header_line_count: int
    data_line_offset: int


@dataclass(frozen=True)
class ReadableTopHeaderInfo:
    """
    The literal, structurally parsed header of one "selected readable"
    formation-top file: one or more leading `#`-prefixed comment lines
    (preserved verbatim in `comment_lines`), a blank line, a whitespace-
    padded column-header line (`TOP_NAME`, `MDRT_M`, `TVDSS_M`, `NOTE`),
    and a dashed separator line (preserved verbatim in
    `separator_line_raw`, structurally recognized and skipped, never
    accidentally treated as a data row).

    `well_name_from_comment` is whatever well name string this file's own
    comment block states (e.g. parsed from "# Selected readable well tops
    for Boreas 1") - this is PROJECT-SUPPLIED METADATA embedded in the
    file, not independently verified file content, and is never described
    as "verified" identity evidence (see `p2mem.io.tops` module
    docstring). `None` if no such comment line is present.
    """

    source_filename: str
    sha256: str
    comment_lines: Tuple[str, ...]
    well_name_from_comment: Optional[str]
    column_header_line: str
    column_names: Tuple[str, ...]
    separator_line_raw: str
    well_identity_source: str  # always "in_file_comment_project_supplied" for this format
    line_ending_convention: str
    header_line_count: int
    data_line_offset: int


# ---------------------------------------------------------------------------
# Per-file contract (config/formation_top_contracts.yml)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HRSTopFileContract:
    """
    One HRS-format file's complete, human-authored expectation set.
    `expected_tvdss_min_m` / `expected_tvdss_max_m` do not apply to this
    format (no TVDSS column) and are intentionally absent from this
    dataclass - see `ReadableTopFileContract` for those fields.
    """

    source_filename: str
    expected_sha256: str
    project_well_key: str
    representation_type: str  # always "HRS_MDRT_only"
    well_identity_evidence_status: str
    well_identity_evidence_notes: str
    model_use_status: str
    expected_column_header_line: str
    expected_column_order: Tuple[str, ...]
    expected_column_count: int
    expected_marker_count: int
    expected_mdrt_min_m: float
    expected_mdrt_max_m: float
    numeric_range_tolerance: float
    datum_depth_column_interpretation: str
    notes: str


@dataclass(frozen=True)
class ReadableTopFileContract:
    """One "selected readable"-format file's complete, human-authored
    expectation set."""

    source_filename: str
    expected_sha256: str
    project_well_key: str
    representation_type: str  # always "selected_readable_MDRT_TVDSS"
    well_identity_evidence_status: str
    well_identity_evidence_notes: str
    model_use_status: str
    expected_well_name_from_comment: str
    expected_column_header_line: str
    expected_column_order: Tuple[str, ...]
    expected_column_count: int
    expected_marker_count: int
    expected_mdrt_min_m: float
    expected_mdrt_max_m: float
    expected_tvdss_min_m: float
    expected_tvdss_max_m: float
    numeric_range_tolerance: float
    datum_depth_column_interpretation: str
    notes: str


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TopIngestionIssue:
    """One ERROR (blocking) or WARNING (non-blocking, disclosed) fact."""

    severity: str  # "ERROR" or "WARNING"
    code: str
    message: str
    context: str


# ---------------------------------------------------------------------------
# Raw station data - every raw row preserved exactly, in file order
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HRSTopStationData:
    """
    Exact, raw parsed HRS-file rows, in original file order. Nothing here
    is deduplicated, reordered, renamed, or repaired.
    """

    Top_Name_source: Tuple[str, ...]
    MDRT_source_m: np.ndarray


@dataclass(frozen=True)
class ReadableTopStationData:
    """
    Exact, raw parsed "selected readable"-file rows, in original file
    order. `NOTE_source` preserves the file's own free-text note column
    exactly (empty string where the file's own NOTE field is blank -
    never fabricated).
    """

    TOP_NAME_source: Tuple[str, ...]
    MDRT_source_m: np.ndarray
    TVDSS_source_m: np.ndarray
    NOTE_source: Tuple[str, ...]


# ---------------------------------------------------------------------------
# HRS-versus-readable source reconciliation (one row per canonical marker)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TopReconciliationEntry:
    """
    One auditable row reconciling ONE canonical marker between this well's
    HRS file and its selected-readable file. Both raw row numbers
    (0-indexed, into that source's own original file order) are preserved
    so a reader can trace this entry back to the exact source line.

    `name_match_status` records how the two sources' own marker-name
    spellings were matched (see `p2mem.io.tops.MARKER_NAME_ALIAS_CONTRACT`
    for the human-authored alias table; "aliased_match" is the ONLY status
    that consulted it - "normalized_match" means whitespace/padding
    differed but the stripped, whitespace-collapsed names were identical,
    with no alias table involved).

    `mdrt_status` is "NOT_COMPARABLE" whenever the marker is present in
    only one source (there is nothing to compare); it is never reported
    as "MATCHED" in that case.
    """

    well_key: str
    canonical_marker_name: str
    hrs_marker_name_raw: Optional[str]
    readable_marker_name_raw: Optional[str]
    hrs_row_number: Optional[int]
    readable_row_number: Optional[int]
    present_in_hrs: bool
    present_in_readable: bool
    name_match_status: str
    MDRT_source_hrs_m: Optional[float]
    MDRT_source_readable_m: Optional[float]
    MDRT_agreement_readable_minus_hrs_m: Optional[float]
    mdrt_status: str
    TVDSS_source_readable_m: Optional[float]
    note_readable: str
    reconciliation_notes: str


# ---------------------------------------------------------------------------
# Corrected, auditable stratigraphic marker record (one per canonical
# marker per well - the project's corrected depth representation)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TopMarkerRecord:
    """
    The complete, typed, auditable record for one canonical formation-top
    marker: every raw source value preserved separately, plus the
    project's corrected survey-derived depth and the explicit residual
    against the source-supplied TVDSS (where supplied).

    `mdrt_authority_basis` documents exactly how `MDRT_reconciled_m` (or
    its absence) was decided:
      * "hrs_and_readable_agree" - both sources supplied this marker and
        agreed within `TopReconciliationEntry` tolerance; the (identical,
        within tolerance) HRS value is used.
      * "hrs_only" / "readable_only" - only one source supplied this
        marker; that source's value is used, flagged as not cross-
        validated.
      * "disagreement_unresolved" - both sources supplied this marker but
        disagreed beyond tolerance; `MDRT_reconciled_m` is `None` and
        `mapping_status == "not_mapped_mdrt_unresolved"` - this project
        never silently picks one source's value in this case.

    `mapping_status` is one of `p2mem.top_models.VALID_MAPPING_STATUSES`;
    every field from `TVD_survey_m` onward is `None` unless
    `mapping_status == "mapped_within_coverage"`.
    """

    well_key: str
    canonical_marker_name: str
    MDRT_source_hrs_m: Optional[float]
    MDRT_source_readable_m: Optional[float]
    MDRT_reconciled_m: Optional[float]
    mdrt_authority_basis: str
    TVDSS_source_m: Optional[float]
    depth_basis_used: Optional[str]
    interpolation_method: Optional[str]
    TVD_survey_m: Optional[float]
    TVDSS_survey_corrected_m: Optional[float]
    TVDSS_residual_source_minus_survey_m: Optional[float]
    mapping_status: str
    well_identity_evidence_status: str
    notes: str


# ---------------------------------------------------------------------------
# Ingestion failure (typed, mirrors CheckshotIngestionFailure)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TopIngestionFailure:
    """
    One well's failed formation-top ingestion attempt.

    `source_path` is retained for backward compatibility and always holds
    the single path judged most representative of the failure (the HRS
    path for an "hrs"-origin failure, the readable path for a
    "readable"-origin failure, the HRS path for a "reconciliation"-origin
    failure since both files parsed successfully in that case). It is
    never assumed to be the HRS path by construction - see `failure_origin`.

    `failure_origin` (Increment 5.1 Finding 2 fix) is one of
    `VALID_TOP_FAILURE_ORIGINS` and records which stage actually failed:
    "hrs" (HRS file parsing/reading/contract resolution), "readable" (the
    selected-readable file's own parsing/reading/contract resolution),
    "reconciliation" (both files parsed and contract-resolved, but could
    not be reconciled - e.g. `NO_COMMON_MARKERS`), or "mapping" (reserved;
    not currently raised as a fatal condition). "unknown" only appears for
    a `TopIngestionFailure` constructed without this classification.

    `hrs_path` / `readable_path` preserve BOTH source paths for this well,
    independent of which one actually failed, so every consumer that
    exports a failure message/context can sanitize both - never only the
    one path recorded in `source_path`.
    """

    well_key: str
    source_path: str
    error_type: str
    message: str
    exception: BaseException
    failure_origin: str = "unknown"
    hrs_path: Optional[str] = None
    readable_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Combined per-well result
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FormationTopWellResult:
    """
    The complete, typed result of successfully loading, contract-
    resolving, reconciling, and survey-mapping one well's pair of
    formation-top files.
    """

    well_key: str
    hrs_header: HRSTopHeaderInfo
    hrs_contract: HRSTopFileContract
    hrs_raw: HRSTopStationData
    readable_header: ReadableTopHeaderInfo
    readable_contract: ReadableTopFileContract
    readable_raw: ReadableTopStationData
    reconciliation: Tuple[TopReconciliationEntry, ...]
    markers: Tuple[TopMarkerRecord, ...]
    issues: Tuple[TopIngestionIssue, ...] = field(default_factory=tuple)
    contract_status: str = "PASSED"


# ---------------------------------------------------------------------------
# Data-availability record (e.g. Poseidon North 1, Proteus 1ST2 - a factual gap)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FormationTopAvailabilityRecord:
    """
    Records that a project well has NO approved formation-top file, as a
    factual data gap - never as, or alongside, an ingestion failure, and
    never filled by substituting another well's tops or correlating them
    by depth alone.
    """

    well_key: str
    formation_top_availability: str  # "NOT_AVAILABLE"
    notes: str
