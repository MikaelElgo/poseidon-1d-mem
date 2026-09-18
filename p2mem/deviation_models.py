"""
p2mem.deviation_models - Typed, documented dataclasses for the
deviation-survey ingestion, minimum-curvature trajectory, and depth-mapping
layer (Increment 3).

Design rationale
-----------------
This mirrors the design philosophy already established in `p2mem.models`
for the LAS-ingestion layer: every ingestion/computation result is a
frozen `dataclasses.dataclass`, never an undocumented tuple, and every
raw/source quantity is kept in a separately named array from any derived
or computed quantity (see the "source vs. computed" naming pattern below).
No third-party schema library is introduced.

This module is data structure only - it performs no I/O, no parsing, no
numerical computation. See:
    `p2mem.io.deviation`   - Petrel deviation-file parsing and per-file
                              contract resolution.
    `p2mem.trajectory`     - minimum-curvature computation
                              (`MinimumCurvatureResult` is defined there,
                              alongside the numerical functions that
                              produce it, and is reused unmodified here).
    `p2mem.depth_mapping`  - MD-to-TVD/TVDSS interpolation.

Source-versus-computed naming
-------------------------------
Every quantity that came directly from the Petrel deviation file is named
with an explicit `_source_` component (e.g. `TVD_source_m`,
`DX_source_m`), and every quantity computed independently by this
project's minimum-curvature implementation is named with an explicit
`_mc_` component (e.g. `TVD_mc_m`, `EASTING_offset_mc_m`). A `_source_`
array is never overwritten by a `_mc_` computation, and the two are never
silently mixed - see `p2mem.trajectory` and `p2mem.io.deviation` for the
computation and residual-comparison logic that keeps them explicitly
separate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import numpy as np

from p2mem.trajectory import MinimumCurvatureResult

__all__ = [
    "DeviationHeaderInfo",
    "DeviationFileContract",
    "DeviationStationData",
    "DeviationIngestionIssue",
    "TrajectoryValidationResult",
    "DepthBasisSelection",
    "DeviationWellResult",
    "DeviationIngestionFailure",
    "LasDepthMappingResult",
]

# Recognized values for `DeviationFileContract.depth_basis_policy` (see
# `p2mem.io.deviation` for where this is applied).
DEPTH_BASIS_PETREL_SOURCE = "petrel_source_trace"
DEPTH_BASIS_MINIMUM_CURVATURE = "minimum_curvature_computed"
VALID_DEPTH_BASIS_POLICIES = (DEPTH_BASIS_PETREL_SOURCE, DEPTH_BASIS_MINIMUM_CURVATURE)

# Recognized values for a residual-comparison "status" field.
STATUS_PASS = "PASS"
STATUS_WARNING = "WARNING"
STATUS_FAIL = "FAIL"


# ---------------------------------------------------------------------------
# Header / provenance
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DeviationHeaderInfo:
    """
    Everything read from a Petrel deviation-survey text file's leading
    comment-header block, plus file-identity metadata, WITHOUT reading or
    parsing the station data rows.

    Every field here is a LITERAL statement parsed out of the file's own
    header lines (or file-system/hash identity) - never inferred, assumed,
    or filled in. `depth_reference_statement`, `angle_unit_statement`,
    `dx_dy_statement`, and `z_statement` preserve the file's own declared
    convention text verbatim (or a normalized-but-traceable summary of
    it), so a later reader never has to trust an unstated assumption about
    sign, datum, or units.
    """

    source_path: str
    source_filename: str
    sha256: str
    well_name: str
    survey_name: str
    wellhead_x_m: float
    wellhead_y_m: float
    datum_elevation_m: float
    datum_reference: str
    well_type: str
    coordinate_reference_system: str
    depth_reference_statement: str
    angle_unit_statement: str
    dx_dy_statement: str
    z_statement: str
    column_names: Tuple[str, ...]
    header_line_count: int
    data_line_offset: int


# ---------------------------------------------------------------------------
# Contract (what config/deviation_survey_contracts.yml says a given file
# SHOULD be)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DeviationFileContract:
    """
    The complete expected identity, structure, and validation policy for
    one specific deviation-survey source file, as declared in
    `config/deviation_survey_contracts.yml`.

    `header_tolerance_m` bounds how far a file's actual wellhead X/Y and
    datum elevation may differ from the contract's declared expected
    values before being treated as a mismatch (guards against a
    reasonable floating-point/rounding difference while still catching a
    genuinely wrong file).

    `residual_tolerance_tvd_m` / `residual_tolerance_horizontal_m` are the
    PASS thresholds for the independent minimum-curvature-vs-Petrel-source
    trajectory comparison; `residual_fail_threshold_m` is the outer bound
    beyond which a residual is treated as FAIL (indicating a likely
    parsing/contract error) rather than WARNING (a real, documented
    trajectory-reconstruction discrepancy - see `TrajectoryValidationResult`
    and the Increment 3 manifest's discussion of the Proteus 1ST2 finding).
    These three tolerances are deliberately declared identically across
    all four wells in the shipped contract (not tuned per well to force a
    particular pass/fail outcome) - see the contract file's own header
    comment for the rationale.

    `azimuth_reference_for_grid_coordinates` names which of the file's two
    azimuth columns (`AZIM_TN` or `AZIM_GN`) is used for the
    minimum-curvature northing/easting computation - always `"AZIM_GN"`
    for these Petrel files, since the accompanying X/Y/DX/DY columns are
    stated to be grid coordinates, but this is declared explicitly in the
    contract (never hard-coded silently) so a future file using a
    different reference is not silently mishandled.

    `depth_basis_policy` selects, per well, which trajectory
    (`DEPTH_BASIS_PETREL_SOURCE` or `DEPTH_BASIS_MINIMUM_CURVATURE`) is
    used as the downstream MD-to-TVD/TVDSS mapping basis - see
    `DepthBasisSelection`.
    """

    source_filename: str
    expected_sha256: str
    expected_well_identifier: str
    expected_survey_identifier: str
    expected_coordinate_reference_system: str
    expected_wellhead_x_m: float
    expected_wellhead_y_m: float
    expected_datum_m: float
    expected_datum_reference: str
    expected_column_count: int
    expected_column_order: Tuple[str, ...]
    expected_units: Dict[str, str]
    expected_station_count: int
    expected_md_min_m: float
    expected_md_max_m: float
    azimuth_reference_for_grid_coordinates: str
    source_depth_convention: str
    header_tolerance_m: float
    residual_tolerance_tvd_m: float
    residual_tolerance_horizontal_m: float
    residual_fail_threshold_m: float
    depth_basis_policy: str
    notes: str


# ---------------------------------------------------------------------------
# Raw station data (literal, source-preserving)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DeviationStationData:
    """
    The literal, source-preserving numeric station arrays for one
    deviation-survey file, in original file (increasing-MD) row order.
    Every array has the same length (the station count).

    These are the EXACT values parsed from the file - no NULL/sentinel
    substitution is applicable here (Petrel deviation files, unlike LAS
    files, have no declared NULL-value convention; a missing/invalid
    numeric token is a structural parsing failure, not a sentinel to
    substitute - see `p2mem.io.deviation`), and no unit conversion is
    applied (all quantities are already in the file's declared units:
    metres for MD/X/Y/Z/TVD/DX/DY, degrees for AZIM_TN/INCL/AZIM_GN, and
    degrees-per-30-metres for the file's own supplied DLS column).
    """

    MD_source_m: np.ndarray
    X_source_m: np.ndarray
    Y_source_m: np.ndarray
    Z_source_m: np.ndarray
    TVD_source_m: np.ndarray
    DX_source_m: np.ndarray
    DY_source_m: np.ndarray
    AZIM_TN_source_deg: np.ndarray
    INCL_source_deg: np.ndarray
    DLS_source_deg_per_30m: np.ndarray
    AZIM_GN_source_deg: np.ndarray


@dataclass(frozen=True)
class DeviationIngestionIssue:
    """
    One fact worth reporting about a deviation-survey ingestion attempt:
    either an ERROR (blocks a successful load) or a WARNING (recorded and
    surfaced, but does not by itself stop ingestion). Mirrors
    `p2mem.models.IngestionIssue` from the LAS-ingestion layer, redefined
    locally here so this module stays independent of the locked LAS
    layer's data structures.
    """

    severity: str  # "ERROR" or "WARNING"
    code: str
    message: str
    context: str


# ---------------------------------------------------------------------------
# Trajectory validation (source-vs-computed comparison)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TrajectoryValidationResult:
    """
    The complete, typed result of comparing the independently computed
    minimum-curvature trajectory against the Petrel-supplied source
    trajectory for one well.

    Every residual metric is reported for THREE separate axes (TVD,
    easting-offset-vs-DX, northing-offset-vs-DY), never pooled into one
    combined number, plus three internal source-consistency checks
    (X ~= X_wellhead + DX, Y ~= Y_wellhead + DY, Z ~= Datum - TVD) that
    verify the Petrel-supplied columns are mutually consistent with each
    other, independent of the minimum-curvature computation.

    `overall_status` is the worst (PASS < WARNING < FAIL) of all six
    per-axis statuses. A WARNING here does not mean ingestion failed -
    see `DeviationWellResult.contract_status`, which is tracked
    separately - it means this specific, disclosed trajectory-consistency
    check did not meet its PASS tolerance and must be reported, not
    hidden.

    `origin_initialization_note` documents, for this specific well, that
    the minimum-curvature trajectory was initialized from that well's own
    first-station source TVD/DX/DY (see `p2mem.trajectory
    .MinimumCurvatureResult` and `p2mem.io.deviation
    .compute_well_trajectory`) - never a hard-coded (0, 0, 0) origin.
    """

    well_key: str
    comparison_basis: str

    tvd_max_abs_residual_m: float
    tvd_mean_residual_m: float
    tvd_rmse_m: float
    tvd_endpoint_residual_m: float
    tvd_tolerance_m: float
    tvd_status: str

    easting_max_abs_residual_m: float
    easting_mean_residual_m: float
    easting_rmse_m: float
    easting_endpoint_residual_m: float
    easting_tolerance_m: float
    easting_status: str

    northing_max_abs_residual_m: float
    northing_mean_residual_m: float
    northing_rmse_m: float
    northing_endpoint_residual_m: float
    northing_tolerance_m: float
    northing_status: str

    x_consistency_max_abs_residual_m: float
    x_consistency_status: str
    y_consistency_max_abs_residual_m: float
    y_consistency_status: str
    z_consistency_max_abs_residual_m: float
    z_consistency_status: str

    overall_status: str
    origin_initialization_note: str


@dataclass(frozen=True)
class DepthBasisSelection:
    """
    The explicit, auditable record of which trajectory (Petrel-supplied
    source, or independently computed minimum-curvature) was selected as
    THIS well's downstream MD-to-TVD/TVDSS mapping basis, and why. Never
    inferred implicitly from `TrajectoryValidationResult.overall_status` -
    always a recorded, per-well decision (see
    `config/deviation_survey_contracts.yml:depth_basis_policy` and
    `p2mem.io.deviation`).
    """

    well_key: str
    selected_basis: str  # one of VALID_DEPTH_BASIS_POLICIES
    rationale: str


# ---------------------------------------------------------------------------
# Combined per-well result
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DeviationWellResult:
    """
    The complete, typed result of successfully loading, contract-
    resolving, and trajectory-validating one deviation-survey file.

    `contract_status` reflects ONLY file-identity/structural contract
    resolution ("PASSED" when no ERROR-severity `issues` entry exists;
    "FAILED" is never returned here - a contract failure raises
    `p2mem.io.deviation.DeviationContractError` instead, mirroring the
    LAS-layer convention that a successfully RETURNED result is always a
    passed one). It is deliberately independent of
    `validation.overall_status`: a well can have `contract_status ==
    "PASSED"` (the file and contract are valid) while
    `validation.overall_status == "WARNING"` (its computed and supplied
    trajectories disagree by more than the pass tolerance) - see the
    Proteus 1ST2 finding in the Increment 3 manifest. Ingestion success
    and trajectory agreement are two different questions, and this
    dataclass keeps their answers in two different fields on purpose.
    """

    header: DeviationHeaderInfo
    contract: DeviationFileContract
    raw: DeviationStationData
    mc: MinimumCurvatureResult
    validation: TrajectoryValidationResult
    depth_basis: DepthBasisSelection
    issues: Tuple[DeviationIngestionIssue, ...] = field(default_factory=tuple)
    contract_status: str = "PASSED"


@dataclass(frozen=True)
class DeviationIngestionFailure:
    """
    A typed, structured record of why one well's deviation-survey file
    failed to load during a batch (`p2mem.io.deviation.load_deviation_surveys`).
    Mirrors `p2mem.models.IngestionFailure` from the LAS-ingestion layer.

    `error_type` is one of "file_not_found", "parsing_failure",
    "contract_failure", or "trajectory_failure" (a
    `p2mem.trajectory.TrajectoryComputationError` raised while computing
    the minimum-curvature trajectory for an otherwise contract-valid
    file - kept distinct from "contract_failure" since it identifies a
    different stage of the pipeline).
    """

    well_key: str
    source_path: str
    error_type: str
    message: str
    exception: BaseException


# ---------------------------------------------------------------------------
# LAS MD -> TVD/TVDSS mapping (p2mem.depth_mapping)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LasDepthMappingResult:
    """
    The complete, typed result of mapping one well's Increment-2.1.1-
    canonical LAS `MD_m` array onto TVD and TVDSS, using the explicitly
    selected depth basis for that well.

    `las_md_source_m` is the ORIGINAL, unmodified LAS canonical `MD_m`
    array (never overwritten - see `p2mem.depth_mapping`).
    `tvd_mapped_m` / `tvdss_mapped_m` are the interpolated results, one
    value per LAS sample, in the same order.

    `interpolation_method` names the deterministic method used (this
    project's implementation: piecewise-linear interpolation of the
    validated, selected-basis station trajectory - explicitly NOT a
    per-sample minimum-curvature recomputation; see
    `p2mem.depth_mapping` module docstring for the rationale).

    `n_extrapolated` counts LAS samples that would have required
    extrapolation beyond the survey's station MD coverage; by policy this
    is always 0 for a successful mapping result (extrapolation is
    rejected - see `p2mem.depth_mapping.DepthMappingError`) and is
    reported here only as a confirming, self-describing field.
    """

    well_key: str
    depth_basis_used: str
    interpolation_method: str
    las_md_source_m: np.ndarray
    tvd_mapped_m: np.ndarray
    tvdss_mapped_m: np.ndarray
    n_samples: int
    survey_md_min_m: float
    survey_md_max_m: float
    las_md_min_m: float
    las_md_max_m: float
    coverage_margin_lower_m: float
    coverage_margin_upper_m: float
    n_extrapolated: int
    datum_elevation_m: float
