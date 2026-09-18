"""
p2mem.depth_mapping - MD-to-TVD/TVDSS interpolation and coverage checks
(Increment 3).

Scope
-----
This module maps the locked Increment 2.1.1 LAS loader's canonical
`MD_m` array onto true vertical depth (TVD) and true vertical depth
subsea (TVDSS), using ONE explicitly selected well-trajectory basis (see
`p2mem.io.deviation.DepthBasisSelection` - either the Petrel-supplied
source trajectory or the independently computed minimum-curvature
trajectory) as the MD-TVD relationship to interpolate against.

It does not read LAS files, does not read deviation files, and does not
decide which basis to use - it is a pure, typed numerical mapping step
that takes (survey MD array, survey TVD array, datum elevation, LAS MD
array) and returns TVD/TVDSS at every LAS sample.

Depth-reference convention
----------------------------
For these wells, MD and TVD are both referenced to zero at the well
datum (rotary table) and increase downward; the well datum elevation
itself is referenced to mean sea level (MSL), positive upward. Therefore:

    TVDSS_m = TVD_m - DatumElevation_m

which is consistent with the Petrel-supplied elevation coordinate
Z_m = DatumElevation_m - TVD_m (positive upward), i.e. TVDSS_m == -Z_m.
Both relationships are independently exercised in `tests/test_depth_
mapping.py`.

Interpolation method
----------------------
A transparent, deterministic PIECEWISE-LINEAR interpolation of the
validated station trajectory (`numpy.interp`) is used - explicitly named
and documented as depth interpolation between discrete survey stations,
NOT a minimum-curvature recomputation at every log sample (minimum
curvature is a station-to-station method; re-deriving it at thousands of
LAS sample depths would not add trajectory information beyond what is
already captured by the station-level TVD values themselves, and would
silently blur the distinction between "the validated station trajectory"
and "a depth grid interpolated from it"). This method:

* is deterministic (no randomness, no fitted/optimized parameters);
* is numerically stable (linear interpolation has no ill-conditioning);
* preserves exact survey-station values (`numpy.interp` returns the
  station's own TVD exactly at an input MD that exactly equals a station
  MD - the underlying data structure is not resampled or smoothed);
* introduces no new dependency (`numpy.interp` is already a project
  dependency);
* never extrapolates silently - see `DepthMappingError` /
  `ExtrapolationRejectedError` below.
"""

from __future__ import annotations

import numpy as np

from p2mem.deviation_models import (
    DEPTH_BASIS_MINIMUM_CURVATURE,
    DEPTH_BASIS_PETREL_SOURCE,
    DeviationWellResult,
    LasDepthMappingResult,
)

__all__ = [
    "DepthMappingError",
    "ExtrapolationRejectedError",
    "INTERPOLATION_METHOD",
    "select_survey_trajectory_for_mapping",
    "map_las_md_to_tvd_tvdss",
]

INTERPOLATION_METHOD = "piecewise_linear_station_interpolation"


class DepthMappingError(RuntimeError):
    """
    Raised when LAS MD cannot be safely mapped to TVD/TVDSS: the survey
    trajectory for the selected basis is not strictly increasing in MD
    (which would make a well-defined piecewise-linear function
    impossible), or any other structural precondition for interpolation
    is not met.
    """


class ExtrapolationRejectedError(DepthMappingError):
    """
    Raised when one or more LAS MD samples fall outside the selected
    survey trajectory's MD coverage. This module never extrapolates
    silently (e.g. by clamping to the nearest station or holding the
    boundary TVD constant) - a LAS MD sample beyond survey coverage is a
    real data-coverage gap that must be reported, not hidden.
    """


def select_survey_trajectory_for_mapping(
    well_result: DeviationWellResult,
) -> tuple[np.ndarray, np.ndarray, str]:
    """
    Return `(survey_md_m, survey_tvd_m, basis_used)` for the depth basis
    explicitly selected for this well
    (`well_result.depth_basis.selected_basis`) - either the Petrel-
    supplied source TVD (`DeviationStationData.TVD_source_m`) or the
    independently computed minimum-curvature TVD
    (`MinimumCurvatureResult.tvd_mc_m`). The MD array is always the
    survey's own source MD (`DeviationStationData.MD_source_m` - MD is
    never recomputed, only TVD differs between the two bases).
    """
    basis = well_result.depth_basis.selected_basis
    if basis == DEPTH_BASIS_PETREL_SOURCE:
        return well_result.raw.MD_source_m, well_result.raw.TVD_source_m, basis
    if basis == DEPTH_BASIS_MINIMUM_CURVATURE:
        return well_result.raw.MD_source_m, well_result.mc.tvd_mc_m, basis
    raise DepthMappingError(
        f"Unrecognized depth_basis_policy {basis!r} for well {well_result.depth_basis.well_key!r}."
    )


def map_las_md_to_tvd_tvdss(
    well_key: str,
    las_md_source_m: np.ndarray,
    well_result: DeviationWellResult,
) -> LasDepthMappingResult:
    """
    Map a well's canonical LAS `MD_m` array onto TVD and TVDSS using the
    explicitly selected depth basis for that well.

    Preconditions checked, in order:
    1. The selected survey trajectory's MD array is strictly increasing
       (`DepthMappingError` if not - this should already be guaranteed
       for the Petrel-source basis by `resolve_deviation_contract`'s
       duplicate/non-monotonic-MD checks, and for the minimum-curvature
       basis by construction, but this is re-verified independently here
       rather than assumed).
    2. Every LAS MD sample lies within `[survey_md_min, survey_md_max]`
       (`ExtrapolationRejectedError` naming the offending sample count and
       the exact out-of-coverage margin if not).

    `las_md_source_m` is returned unmodified as `LasDepthMappingResult
    .las_md_source_m` - this function never overwrites or resamples the
    original LAS MD array, only computes TVD/TVDSS at each of its
    existing sample depths.
    """
    survey_md, survey_tvd, basis_used = select_survey_trajectory_for_mapping(well_result)

    if survey_md.size < 2 or not np.all(np.diff(survey_md) > 0.0):
        raise DepthMappingError(
            f"{well_key}: selected survey trajectory (basis={basis_used!r}) MD array is not "
            f"strictly increasing; cannot construct a well-defined piecewise-linear MD->TVD map."
        )

    las_md = np.asarray(las_md_source_m, dtype=np.float64)
    if las_md.ndim != 1 or las_md.size == 0:
        raise DepthMappingError(f"{well_key}: LAS MD array must be a non-empty 1-D array.")
    if not np.all(np.isfinite(las_md)):
        raise DepthMappingError(f"{well_key}: LAS MD array contains non-finite value(s).")

    survey_md_min = float(survey_md[0])
    survey_md_max = float(survey_md[-1])
    las_md_min = float(np.min(las_md))
    las_md_max = float(np.max(las_md))

    below = las_md < survey_md_min
    above = las_md > survey_md_max
    n_extrapolated_would_be = int(np.sum(below) + np.sum(above))
    if n_extrapolated_would_be > 0:
        margin_below = survey_md_min - las_md_min if las_md_min < survey_md_min else 0.0
        margin_above = las_md_max - survey_md_max if las_md_max > survey_md_max else 0.0
        raise ExtrapolationRejectedError(
            f"{well_key}: {n_extrapolated_would_be} LAS MD sample(s) fall outside the selected "
            f"survey trajectory's MD coverage [{survey_md_min:.4f}, {survey_md_max:.4f}] m "
            f"(basis={basis_used!r}); LAS MD range is [{las_md_min:.4f}, {las_md_max:.4f}] m "
            f"(below-coverage margin {margin_below:.6f} m, above-coverage margin "
            f"{margin_above:.6f} m). Extrapolation is rejected by default - this function never "
            f"silently extends the trajectory beyond its surveyed range."
        )

    tvd_mapped = np.interp(las_md, survey_md, survey_tvd)
    tvdss_mapped = tvd_mapped - well_result.header.datum_elevation_m

    return LasDepthMappingResult(
        well_key=well_key,
        depth_basis_used=basis_used,
        interpolation_method=INTERPOLATION_METHOD,
        las_md_source_m=las_md,
        tvd_mapped_m=tvd_mapped,
        tvdss_mapped_m=tvdss_mapped,
        n_samples=int(las_md.size),
        survey_md_min_m=survey_md_min,
        survey_md_max_m=survey_md_max,
        las_md_min_m=las_md_min,
        las_md_max_m=las_md_max,
        coverage_margin_lower_m=las_md_min - survey_md_min,
        coverage_margin_upper_m=survey_md_max - las_md_max,
        n_extrapolated=0,
        datum_elevation_m=well_result.header.datum_elevation_m,
    )
