"""
p2mem.checkshot_models - Typed, documented result/schema objects for the
Increment 4 checkshot-ingestion and time-depth layer.

Design rationale
-----------------
Mirrors `p2mem.deviation_models` (Increment 3): every object here is a
frozen `dataclass`, nothing performs I/O or numerical computation, and
every array/field name is explicit about what it holds (raw vs.
conditioned, source vs. survey-derived, seconds vs. milliseconds - see
"Naming discipline" below). This module collects every typed object used
by `p2mem.io.checkshot`, `p2mem.io.checkshot_inventory`, and
`p2mem.time_depth` in one place.

Naming discipline (explicit, unit-suffixed names - project-wide policy)
-------------------------------------------------------------------------
* `Depth_source_m`   - the checkshot file's own first column, EXACTLY as
                        labelled in its header ("Depth"). This name is
                        deliberately NOT `MD_source_m`: the header never
                        states this column is measured depth, so it is
                        never silently renamed to imply that. Whether it
                        behaves as MD is evaluated empirically (see
                        `CheckshotSurveyDepthComparisonResult`) and the
                        evidence is recorded, never assumed.
* `TVDSS_source_m`   - the file's own supplied TVDSS column, unmodified.
* `OWT_source_s`     - the file's own supplied one-way-time column
                        (seconds), unmodified, WITH every raw duplicate
                        row preserved (see `CheckshotStationData`).
* `OWT_conditioned_s`, `TVDSS_conditioned_m`, `Depth_conditioned_m` - the
                        SEPARATE, explicitly named conditioned-tie
                        representation built by `p2mem.time_depth`. Never
                        confused with the `_source_` arrays above; the
                        conditioning rule that produced them is always
                        recorded (see `ConditionedCheckshotData`).
* `TWT_s`, `TWT_ms`  - two-way time, always derived via the LOCKED
                        Increment 1 `p2mem.units.owt_to_twt` (never
                        reimplemented here). `_s` and `_ms` are never
                        mixed in one computation without an explicit,
                        named conversion step.
* `Vavg_m_s`, `Vint_m_s` - average and interval velocity (see
                        `p2mem.time_depth` for their exact definitions
                        and NaN-on-invalid-interval semantics).

Axis-tie conditioning (Increment 4.1 addition)
------------------------------------------------
Increment 4's original `_build_strictly_increasing_table` (removed in this
patch) resolved a repeated TVDSS or OWT value in the Depth-conditioned
table by keeping whichever tied row happened to come first and silently
dropping the other - deterministic, but an order-dependent tie-break: a
file whose two tied rows were supplied in the opposite order would have
produced a different, silently different, inverse mapping. This is
corrected by `p2mem.time_depth.build_axis_conditioned_lookup_table`, which
groups every value tied on the axis being inverted (TVDSS, for
`owt_to_tvdss`'s independent variable... note the OPPOSITE naming
direction below), takes the group's dependent-value MEDIAN as a
representative (order-invariant), and registers every group -
`AxisTimeDepthTieRegisterEntry` - independently of the pre-existing
Depth-tie register (`DuplicateTieRegisterEntry`), which conditions the
raw rows against the Depth axis and is unaffected by this patch. A
genuine reversal (not a tie - a group's axis value less than the
preceding group's) raises `TimeDepthError` rather than being sorted,
discarded, or forced monotonic. See `p2mem.time_depth` module docstring,
section "Order-invariant axis-tie conditioning" for full detail.

Evidence-status vocabulary (Increment 4 addition)
----------------------------------------------------
Extends the project's established measured / derived / correlation-
derived / assumed / unavailable disclosure discipline with three new,
explicit fields used only for checkshot association and model role:

* `well_identity_evidence_status` - "verified" (the file's own content,
  or an independently verified cross-reference, proves which well it
  belongs to) or "inferred_unverified" (association rests on filename,
  project context, and numerical depth-tie plausibility only - see
  Proteus 1ST2 in `config/checkshot_contracts.yml`). Never described as
  "verified" when it is not.
* `model_use_status` - "primary_model" (this well's checkshot may define
  the primary time-depth relationship used elsewhere) or "qc_only"
  (supporting QC/comparison data only - must never be transferred into
  another well's time-depth model).
* `checkshot_availability` - "AVAILABLE" or "NOT_AVAILABLE" (a factual
  data-gap statement for a well with no approved checkshot file at all,
  e.g. Poseidon North 1 - never treated as, or reported alongside, an
  ingestion failure).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np

__all__ = [
    "STATUS_PASS",
    "STATUS_WARNING",
    "STATUS_FAIL",
    "VALID_IDENTITY_EVIDENCE_STATUSES",
    "VALID_MODEL_USE_STATUSES",
    "VALID_CHECKSHOT_AVAILABILITY_STATUSES",
    "VALID_DEPTH_BASIS_INTERPRETATION_STATUSES",
    "CheckshotHeaderInfo",
    "CheckshotFileContract",
    "CheckshotIngestionIssue",
    "CheckshotStationData",
    "DuplicateTieRegisterEntry",
    "ConditionedCheckshotData",
    "AxisTimeDepthTieRegisterEntry",
    "AxisConditionedLookupTable",
    "VelocityDiagnosticsResult",
    "CheckshotSurveyDepthComparisonResult",
    "SonicCheckshotDriftResult",
    "TimeDepthMappingSummary",
    "CheckshotIngestionFailure",
    "CheckshotWellResult",
    "CheckshotAvailabilityRecord",
]

# ---------------------------------------------------------------------------
# Shared status vocabulary (mirrors p2mem.deviation_models)
# ---------------------------------------------------------------------------
STATUS_PASS = "PASS"
STATUS_WARNING = "WARNING"
STATUS_FAIL = "FAIL"

VALID_IDENTITY_EVIDENCE_STATUSES = ("verified", "inferred_unverified")
VALID_MODEL_USE_STATUSES = ("primary_model", "qc_only")
VALID_CHECKSHOT_AVAILABILITY_STATUSES = ("AVAILABLE", "NOT_AVAILABLE")
VALID_DEPTH_BASIS_INTERPRETATION_STATUSES = (
    "candidate_md_evaluated_against_locked_survey",
)


# ---------------------------------------------------------------------------
# Raw header / provenance
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CheckshotHeaderInfo:
    """
    The literal, structurally parsed header of one checkshot file. Every
    approved file in this project shares the identical two-line header
    format (one free-text survey statement, one tab-separated column-
    header line) - this dataclass stores what was actually parsed, not an
    assumed constant, so a genuinely different header is caught by
    contract resolution rather than silently accepted.
    """

    source_filename: str
    sha256: str
    survey_statement: str
    column_header_line: str
    column_names: Tuple[str, ...]
    line_ending_convention: str  # e.g. "CRLF" - disclosed, never "corrected"


# ---------------------------------------------------------------------------
# Per-file contract
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CheckshotFileContract:
    """
    One file's complete, human-authored expectation set, resolved against
    the actual file by `p2mem.io.checkshot.resolve_checkshot_contract`.
    Mirrors `p2mem.deviation_models.DeviationFileContract`'s "declare
    everything, verify everything" pattern.
    """

    source_filename: str
    expected_sha256: str
    project_well_key: str
    well_identity_evidence_status: str
    well_identity_evidence_notes: str
    model_use_status: str
    expected_survey_statement: str
    expected_column_header_line: str
    expected_column_order: Tuple[str, ...]
    expected_column_count: int
    expected_time_type: str
    expected_time_unit: str
    expected_vertical_correction_fragment: str
    expected_srd_reference_fragment: str
    expected_row_count: int
    expected_depth_min_m: float
    expected_depth_max_m: float
    expected_tvdss_min_m: float
    expected_tvdss_max_m: float
    expected_owt_min_s: float
    expected_owt_max_s: float
    numeric_range_tolerance: float
    depth_basis_interpretation_status: str
    duplicate_tie_policy: str
    interpolation_policy: str
    extrapolation_policy: str
    notes: str


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CheckshotIngestionIssue:
    """One ERROR (blocking) or WARNING (non-blocking, disclosed) fact."""

    severity: str  # "ERROR" or "WARNING"
    code: str
    message: str
    context: str


# ---------------------------------------------------------------------------
# Raw station data (never overwritten; every raw row preserved exactly)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CheckshotStationData:
    """
    The exact, raw parsed checkshot rows, column-ordered as
    (Depth, TVDSS, OWT), with EVERY row preserved exactly as read -
    including any repeated/duplicate Depth, TVDSS, or OWT value. Nothing
    here is deduplicated, reordered, or averaged; see
    `ConditionedCheckshotData` for the separate, explicitly named
    conditioned representation.
    """

    Depth_source_m: np.ndarray
    TVDSS_source_m: np.ndarray
    OWT_source_s: np.ndarray


# ---------------------------------------------------------------------------
# Duplicate / repeated-tie register
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DuplicateTieRegisterEntry:
    """
    One auditable record of a repeated (tied) independent-axis (Depth)
    value found in a file's raw data, per the project's "never silently
    average ties" policy. `source_row_indices` are 0-indexed positions
    into that well's `CheckshotStationData` arrays.
    """

    well_key: str
    axis: str  # "Depth" (the only independent-axis tie type detected)
    tie_value_m: float
    source_row_indices: Tuple[int, ...]
    original_tvdss_m: Tuple[float, ...]
    original_owt_s: Tuple[float, ...]
    duplicate_type: str  # e.g. "repeated_depth_distinct_tvdss_owt"
    group_size: int
    tvdss_value_spread_m: float
    owt_value_spread_s: float
    selected_representative_tvdss_m: float
    selected_representative_owt_s: float
    conditioning_rule: str
    affected_downstream_outputs: Tuple[str, ...]


# ---------------------------------------------------------------------------
# Conditioned (tie-collapsed) representation
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ConditionedCheckshotData:
    """
    The SEPARATE, explicitly named conditioned-tie representation used
    for all downstream interpolation/velocity work. Built by collapsing
    each repeated-Depth tie group in `CheckshotStationData` to one
    deterministic representative row (see `DuplicateTieRegisterEntry
    .conditioning_rule`) - never by silently averaging, never by
    injecting artificial epsilon separations to force strict
    monotonicity. `Depth_conditioned_m` is therefore strictly increasing
    by construction (every distinct raw Depth value contributes exactly
    one conditioned row).
    """

    Depth_conditioned_m: np.ndarray
    TVDSS_conditioned_m: np.ndarray
    OWT_conditioned_s: np.ndarray
    n_raw_rows: int
    n_conditioned_rows: int
    n_tie_groups: int
    conditioning_method: str


# ---------------------------------------------------------------------------
# Axis-tie register and axis-conditioned lookup table (Increment 4.1)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AxisTimeDepthTieRegisterEntry:
    """
    One auditable record of a repeated (tied) value on the AXIS being
    inverted (TVDSS, for `tvdss_to_owt`; OWT, for `owt_to_tvdss`) found in
    the Depth-conditioned table - separate from, and never confused with,
    `DuplicateTieRegisterEntry` (which registers repeated Depth values in
    the RAW table). `conditioned_row_indices` are 0-indexed positions into
    that well's `ConditionedCheckshotData` arrays (Depth_conditioned_m /
    TVDSS_conditioned_m / OWT_conditioned_s) - NOT into the raw arrays.

    `tie_kind` is `"identical_pair"` when every tied row shares an
    IDENTICAL dependent value too (spread == 0.0 exactly - the group
    collapses without changing any value, but is still counted and
    registered per the project's "never silently average, never silently
    drop" policy), or `"genuinely_non_unique"` when the dependent values
    differ (the axis alone cannot distinguish these rows - the median
    representative is a screening-level choice, not proof the original
    relationship was single-valued at that axis value).
    """

    well_key: str
    interpolation_direction: str  # "tvdss_to_owt" | "owt_to_tvdss"
    axis: str  # "TVDSS_conditioned_m" | "OWT_conditioned_s" - the independent axis being grouped
    dependent_axis: str  # the other axis - the one whose value is conditioned per group
    tie_axis_value: float
    conditioned_row_indices: Tuple[int, ...]
    associated_depth_m: Tuple[float, ...]
    original_dependent_values: Tuple[float, ...]
    group_size: int
    dependent_value_spread: float
    selected_representative_dependent_value: float
    conditioning_rule: str
    tie_kind: str  # "identical_pair" | "genuinely_non_unique"
    affected_downstream_outputs: Tuple[str, ...]


@dataclass(frozen=True)
class AxisConditionedLookupTable:
    """
    An order-invariant, axis-tie-conditioned lookup table used ONLY for
    inverse/forward interpolation FROM the named independent axis (TVDSS
    or OWT) TO the named dependent axis. This is explicitly NOT the raw
    checkshot data and NOT the Depth-conditioned table
    (`ConditionedCheckshotData`) - it is a further-conditioned view of the
    latter, built by grouping ties on `independent_axis_name` and taking
    each group's dependent-value median (see `AxisTimeDepthTieRegisterEntry`
    for the per-group audit trail). `axis_values` is guaranteed strictly
    increasing (a genuine reversal raises `TimeDepthError` at construction
    - see `p2mem.time_depth.build_axis_conditioned_lookup_table`).

    Never described as raw, uniquely measured, or unconditioned - the
    median representative used here is a screening-level choice, not
    evidence that the original TVDSS<->OWT relationship was single-valued
    at every tied axis value.
    """

    well_key: str
    interpolation_direction: str  # "tvdss_to_owt" | "owt_to_tvdss"
    independent_axis_name: str
    dependent_axis_name: str
    axis_values: np.ndarray
    dependent_values: np.ndarray
    n_input_points: int
    n_output_points: int
    n_axis_tie_groups: int
    n_collapsed_points: int
    n_identical_pairs: int
    n_genuinely_nonunique_groups: int
    conditioning_method: str


# ---------------------------------------------------------------------------
# Velocity diagnostics
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class VelocityDiagnosticsResult:
    """
    Average velocity (Vavg = TVDSS / OWT) at every conditioned row, and
    interval velocity (Vint = dTVDSS / dOWT) between consecutive
    conditioned rows. `Vint_m_s` has length `n_conditioned_rows - 1`;
    index k is the interval between conditioned row k and k+1.
    Non-positive dTVDSS or dOWT yields NaN (never inf or a negative
    velocity) at that index, flagged in `vint_invalid_mask`.
    """

    well_key: str
    Depth_conditioned_m: np.ndarray
    Vavg_m_s: np.ndarray
    Vint_m_s: np.ndarray
    vint_invalid_mask: np.ndarray
    n_vint_intervals: int
    n_vint_invalid: int
    vint_invalid_reason_counts: dict


# ---------------------------------------------------------------------------
# Checkshot-vs-locked-survey depth-reference comparison
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CheckshotSurveyDepthComparisonResult:
    """
    Compares checkshot `Depth_source_m` (treated as a CANDIDATE measured-
    depth axis - see the module docstring's naming-discipline note)
    against TVDSS interpolated from the LOCKED Increment 3/3.1.1
    `petrel_source_trace` survey MD->TVD relationship for the same well
    (TVDSS_survey_m = TVD_survey_m - datum_elevation_m).

    Sign convention (explicit, never implicit): `residual_m` at each
    compared row is defined as

        residual_m = TVDSS_survey_interpolated_m - TVDSS_source_m

    i.e. positive means the locked survey trajectory places that depth
    DEEPER (more positive TVDSS) than the checkshot file's own supplied
    TVDSS at the same Depth value. This is the convention used
    consistently for all three admitted files' recomputed residuals in
    `INCREMENT_04_MANIFEST.md`.
    """

    well_key: str
    n_compared: int
    n_outside_survey_md_coverage: int
    min_residual_m: float
    max_residual_m: float
    max_abs_residual_m: float
    mean_residual_m: float
    median_residual_m: float
    rmse_m: float
    first_residual_m: float
    last_residual_m: float
    residual_trend_description: str
    depth_basis_interpretation_status: str
    residual_sign_convention: str


# ---------------------------------------------------------------------------
# Poseidon 2 sonic-checkshot drift diagnostic
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SonicCheckshotDriftResult:
    """
    Poseidon-2-only diagnostic comparing integrated sonic one-way transit
    time (trapezoidal integration of slowness = 1/VP_m_s against MD, over
    an algorithmically identified continuous-coverage sonic interval)
    against the checkshot-interpolated OWT increment over the identical
    MD/Depth endpoints. Diagnostic only - no correction is applied to
    VP_m_s, DTCO, checkshot OWT, or the time-depth curve as a result of
    this comparison (see `limitations`).
    """

    well_key: str
    md_interval_start_m: float
    md_interval_end_m: float
    n_sonic_samples: int
    selection_criteria: str
    integration_method: str
    sonic_transit_time_s: float
    checkshot_owt_increment_s: float
    sonic_minus_checkshot_ms: float
    checkshot_minus_sonic_ms: float
    sonic_minus_checkshot_percent: float
    limitations: Tuple[str, ...]


# ---------------------------------------------------------------------------
# LAS MD -> checkshot time mapping summary (Poseidon 2 only; no raw arrays)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TimeDepthMappingSummary:
    """
    Deterministic SUMMARY (never the full per-sample array - see the
    module docstring's "do not package full proprietary...arrays" policy)
    of mapping a well's canonical LAS MD onto checkshot-derived OWT/TWT,
    within validated checkshot coverage only. Samples outside checkshot
    Depth coverage are never extrapolated; `n_extrapolated` must be 0 by
    construction (see `p2mem.time_depth.map_las_md_to_checkshot_time`).
    """

    well_key: str
    n_las_samples: int
    n_inside_coverage: int
    n_shallower_than_coverage: int
    n_deeper_than_coverage: int
    mapped_fraction: float
    checkshot_depth_min_m: float
    checkshot_depth_max_m: float
    las_md_min_m: float
    las_md_max_m: float
    interpolation_method: str
    n_extrapolated: int


# ---------------------------------------------------------------------------
# Ingestion failure (typed, mirrors DeviationIngestionFailure)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CheckshotIngestionFailure:
    well_key: str
    source_path: str
    error_type: str
    message: str
    exception: BaseException


# ---------------------------------------------------------------------------
# Combined per-well result
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CheckshotWellResult:
    """The complete, typed result of successfully loading and contract-
    resolving, conditioning, and diagnosing one checkshot file.

    `axis_tie_entries` (Increment 4.1) is the FLAT tuple of every
    `AxisTimeDepthTieRegisterEntry` found across BOTH inversion directions
    (`tvdss_to_owt` and `owt_to_tvdss`) - separate from, and never
    confused with, `duplicate_ties` (the pre-existing Depth-axis register).
    `axis_tables` maps `"tvdss_to_owt"` / `"owt_to_tvdss"` to the
    corresponding `AxisConditionedLookupTable`, built once per well at
    load time (see `p2mem.time_depth.build_axis_conditioned_lookup_table`)
    so every caller (interpolation, the CSV/JSON exporters, the notebook)
    shares one order-invariant table rather than each silently rebuilding
    its own."""

    header: CheckshotHeaderInfo
    contract: CheckshotFileContract
    raw: CheckshotStationData
    duplicate_ties: Tuple[DuplicateTieRegisterEntry, ...]
    conditioned: ConditionedCheckshotData
    velocity: VelocityDiagnosticsResult
    depth_comparison: Optional[CheckshotSurveyDepthComparisonResult]
    issues: Tuple[CheckshotIngestionIssue, ...] = field(default_factory=tuple)
    contract_status: str = "PASSED"
    axis_tie_entries: Tuple[AxisTimeDepthTieRegisterEntry, ...] = field(default_factory=tuple)
    axis_tables: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Data-availability record (e.g. Poseidon North 1 - a factual gap)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CheckshotAvailabilityRecord:
    """
    Records that a project well has NO approved checkshot file, as a
    factual data gap - never as, or alongside, an ingestion failure, and
    never filled by substituting another well's file.
    """

    well_key: str
    checkshot_availability: str  # "NOT_AVAILABLE"
    notes: str
