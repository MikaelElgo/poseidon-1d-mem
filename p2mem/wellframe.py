"""
p2mem.wellframe - Increment 6 well-frame assembly.

What this module does
---------------------
Takes ONE well's already-loaded, already-contract-validated LOCKED
Increment 2.1.1 `LasFileResult` and its LOCKED Increment 3.1.1
`DeviationWellResult`, and assembles a typed `WellFrame`: the canonical
curve arrays, the MD -> TVD/TVDSS mapping computed from that well's
explicitly selected survey basis, per-sample validity masks, per-curve
provenance, and QC flags.

What this module explicitly does NOT do
---------------------------------------
* It does not open, read, parse, or re-parse any file. Both inputs are
  already-validated in-memory results produced by locked modules.
* It does not recompute minimum curvature, does not choose a depth basis,
  and does not replace `petrel_source_trace`. The basis is whatever the
  locked `DeviationWellResult.depth_basis.selected_basis` already says,
  and the mapping arithmetic is performed by the locked
  `p2mem.depth_mapping.map_las_md_to_tvd_tvdss` - never re-implemented
  here.
* It does not extrapolate. See "Coverage handling" below.
* It does not modify, resample, reorder, gap-fill, smooth, or delete any
  canonical curve sample. Sample count and order are preserved exactly;
  invalidity is expressed only through masks.
* It does not read, transfer, or re-derive formation tops.

Coverage handling (why this module calls the locked mapper twice)
-----------------------------------------------------------------
The locked `map_las_md_to_tvd_tvdss` is deliberately all-or-nothing: if
ANY LAS MD sample falls outside the survey's own station MD coverage it
raises `ExtrapolationRejectedError` for the whole array, because silently
extending a trajectory beyond its surveyed range is exactly the failure
mode Increment 3 was written to prevent. That is the correct behavior for
a mapping primitive, and this module does not weaken it.

A well frame, however, must still be assemblable when a log runs a little
beyond the last survey station - the scientifically honest result there is
"these N samples have no defensible TVD", not "the whole well is
unusable" and certainly not "hold the last TVD constant". So this module:

  1. reads the selected trajectory's own MD coverage via the locked
     `select_survey_trajectory_for_mapping` (no re-derivation);
  2. builds a per-sample in-coverage mask;
  3. calls the LOCKED mapper on the in-coverage subset only - so every
     TVD/TVDSS number in a well frame is produced by the locked,
     already-reviewed interpolation, never by code in this module;
  4. writes those results back into full-length arrays at their original
     positions, leaving out-of-coverage samples as NaN with
     `depth_valid_mask == False`.

The result is that a well frame never contains an extrapolated depth:
`n_extrapolated` is 0 by construction, and `n_depth_unmapped` reports the
honest coverage gap instead. When every sample is in coverage (the case
for all four approved wells in this project's real data), step 3 is a
single call on the whole array and the result is bit-for-bit what the
locked mapper would have returned on its own.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

from p2mem.deviation_models import DeviationWellResult
from p2mem.depth_mapping import (
    DepthMappingError,
    map_las_md_to_tvd_tvdss,
    select_survey_trajectory_for_mapping,
)
from p2mem.models import LasFileResult
from p2mem.wellframe_models import (
    DEPTH_MAP_STATUS_FULL,
    DEPTH_MAP_STATUS_NONE,
    DEPTH_MAP_STATUS_PARTIAL,
    EVIDENCE_CLASS_MEASURED,
    CurveSlot,
    WellFrame,
    WellFrameAssemblyFailure,
)

__all__ = [
    "WellFrameAssemblyError",
    "QC_FLAG_DEPTH_COVERAGE_LIMITED",
    "QC_FLAG_NO_DEPTH_COVERAGE",
    "QC_FLAG_GR_FAMILY_ABSENT",
    "QC_FLAG_SPARSE_CURVE_COVERAGE",
    "SPARSE_COVERAGE_FRACTION",
    "assemble_well_frame",
    "assemble_well_frames",
]


class WellFrameAssemblyError(RuntimeError):
    """
    Raised when a well frame cannot be assembled from otherwise-valid
    inputs (for example a LAS result carrying no canonical `MD_m` array,
    or a curve array whose length disagrees with `MD_m`). This is a
    structural precondition failure, deliberately distinct from the
    locked layers' own ingestion exceptions.
    """


QC_FLAG_DEPTH_COVERAGE_LIMITED = "DEPTH_COVERAGE_LIMITED_SOME_SAMPLES_UNMAPPED"
QC_FLAG_NO_DEPTH_COVERAGE = "NO_SURVEY_MD_COVERAGE_OVERLAP"
QC_FLAG_GR_FAMILY_ABSENT = "GR_FAMILY_CURVE_ABSENT"
QC_FLAG_SPARSE_CURVE_COVERAGE = "SPARSE_CURVE_COVERAGE"

# A curve whose valid fraction falls below this is flagged as sparse. This
# is a REPORTING threshold only - it never removes, rejects, or rescales a
# curve, and it never by itself makes a well ineligible for anything.
SPARSE_COVERAGE_FRACTION = 0.10


def _readonly(arr: np.ndarray) -> np.ndarray:
    """
    Return a read-only VIEW of `arr` (never a copy, so no per-sample data
    is duplicated in memory, and never a mutable alias, so a downstream
    consumer cannot silently corrupt a locked loader's array through a
    well frame). The locked source array itself is left untouched.
    """
    view = arr.view()
    view.setflags(write=False)
    return view


def _map_depths_without_extrapolation(
    well_key: str,
    las_md_m: np.ndarray,
    dev_result: DeviationWellResult,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, str, str, float, float, float, str]:
    """
    Map `las_md_m` onto TVD/TVDSS using the LOCKED mapper, restricted to
    samples inside the selected survey trajectory's own MD coverage.

    Returns
    -------
    (tvd_full, tvdss_full, depth_valid_mask, depth_basis_used,
     interpolation_method, datum_elevation_m, survey_md_min_m,
     survey_md_max_m, depth_map_status)

    `tvd_full` / `tvdss_full` are full-length float arrays with NaN at
    every out-of-coverage sample. No value in them is extrapolated: each
    finite entry was produced by the locked mapper from in-coverage input.
    """
    survey_md, _survey_tvd, _basis = select_survey_trajectory_for_mapping(dev_result)
    if survey_md.size < 2:
        raise DepthMappingError(
            f"{well_key}: selected survey trajectory has fewer than 2 stations; no MD->TVD "
            f"relationship can be interpolated."
        )

    survey_md_min = float(np.min(survey_md))
    survey_md_max = float(np.max(survey_md))

    md = np.asarray(las_md_m, dtype=np.float64)
    in_coverage = np.isfinite(md) & (md >= survey_md_min) & (md <= survey_md_max)

    tvd_full = np.full(md.shape, np.nan, dtype=np.float64)
    tvdss_full = np.full(md.shape, np.nan, dtype=np.float64)

    n_in = int(np.count_nonzero(in_coverage))
    if n_in == 0:
        # Nothing can be mapped. This is reported, never worked around.
        datum = float(dev_result.header.datum_elevation_m)
        return (
            tvd_full,
            tvdss_full,
            in_coverage,
            dev_result.depth_basis.selected_basis,
            "not_applicable_no_coverage_overlap",
            datum,
            survey_md_min,
            survey_md_max,
            DEPTH_MAP_STATUS_NONE,
        )

    # Delegate every actual TVD/TVDSS number to the LOCKED mapper. When all
    # samples are in coverage this is one call on the whole array and the
    # result is exactly what the locked mapper returns unaided.
    mapped = map_las_md_to_tvd_tvdss(well_key, md[in_coverage], dev_result)
    tvd_full[in_coverage] = mapped.tvd_mapped_m
    tvdss_full[in_coverage] = mapped.tvdss_mapped_m

    status = DEPTH_MAP_STATUS_FULL if n_in == md.size else DEPTH_MAP_STATUS_PARTIAL
    return (
        tvd_full,
        tvdss_full,
        in_coverage,
        mapped.depth_basis_used,
        mapped.interpolation_method,
        float(mapped.datum_elevation_m),
        survey_md_min,
        survey_md_max,
        status,
    )


def assemble_well_frame(
    well_key: str,
    las_result: LasFileResult,
    dev_result: DeviationWellResult,
    *,
    las_path: str,
    survey_path: str,
    gr_family_canonical_name: Optional[str] = None,
) -> WellFrame:
    """
    Assemble one `WellFrame` from a LOCKED `LasFileResult` and a LOCKED
    `DeviationWellResult`.

    `gr_family_canonical_name`, when given, names which of this well's
    canonical curves is its gamma-ray-family curve (e.g. `"GR_api"`,
    `"GRD_api"`, `"ECGR_api"`). It is recorded, never guessed: this
    project never adjudicates tool identity from the data, and two wells
    sharing a canonical GR name are still two different measurements.
    If the named curve is absent, a QC flag is raised and the frame's
    `gr_family_canonical_name` is left None - it is never silently
    substituted with another well's or another mnemonic's curve.

    Raises
    ------
    WellFrameAssemblyError
        If the LAS result carries no canonical `MD_m`, or any canonical
        curve's length disagrees with `MD_m` (a structural inconsistency
        that must never be papered over by truncation or padding).
    DepthMappingError
        Propagated from the locked depth layer when no well-defined
        MD->TVD relationship exists at all.
    """
    md = las_result.canonical_data.get("MD_m")
    if md is None:
        raise WellFrameAssemblyError(
            f"{well_key}: LAS result has no canonical 'MD_m' array; a well frame cannot be "
            f"assembled without the depth index."
        )
    md = np.asarray(md)
    if md.ndim != 1 or md.size == 0:
        raise WellFrameAssemblyError(f"{well_key}: canonical 'MD_m' must be a non-empty 1-D array.")

    n_samples = int(md.size)
    for canonical_name, arr in las_result.canonical_data.items():
        a = np.asarray(arr)
        if a.ndim != 1 or a.size != n_samples:
            raise WellFrameAssemblyError(
                f"{well_key}: canonical curve {canonical_name!r} has shape {a.shape} but 'MD_m' has "
                f"{n_samples} samples; a well frame never truncates, pads, or resamples to "
                f"reconcile a length disagreement."
            )

    (
        tvd_full,
        tvdss_full,
        depth_valid_mask,
        depth_basis_used,
        interpolation_method,
        datum_elevation_m,
        survey_md_min_m,
        survey_md_max_m,
        depth_map_status,
    ) = _map_depths_without_extrapolation(well_key, md, dev_result)

    # Per-curve provenance, taken from the locked loader's own resolutions
    # and stats - never re-derived here.
    stats_by_canonical = {s.canonical_name: s for s in las_result.curve_stats}
    resolution_by_canonical = {r.canonical_name: r for r in las_result.resolutions}
    las_basename = Path(las_path).name
    survey_basename = Path(survey_path).name

    curves: Dict[str, CurveSlot] = {}
    qc_flags = []
    for canonical_name, arr in las_result.canonical_data.items():
        values = np.asarray(arr)
        valid_mask = np.isfinite(values)
        valid_count = int(np.count_nonzero(valid_mask))
        st = stats_by_canonical.get(canonical_name)
        rs = resolution_by_canonical.get(canonical_name)
        curves[canonical_name] = CurveSlot(
            canonical_name=canonical_name,
            source_curve_name=(st.source_curve_name if st is not None else (rs.source_curve_name if rs is not None else "")),
            raw_mnemonic=(st.raw_mnemonic if st is not None else (rs.matched_raw_mnemonic or "")),
            raw_unit=(st.raw_unit if st is not None else (rs.matched_raw_unit or "")),
            canonical_unit=(st.canonical_unit if st is not None else ""),
            conversion_function=(st.conversion_function if st is not None else (rs.conversion_applied or "")),
            source_filename=las_basename,
            evidence_class=EVIDENCE_CLASS_MEASURED,
            values=_readonly(values),
            valid_mask=_readonly(valid_mask),
            n_samples=n_samples,
            valid_count=valid_count,
            valid_fraction=(valid_count / n_samples) if n_samples else 0.0,
        )
        if n_samples and canonical_name != "MD_m" and (valid_count / n_samples) < SPARSE_COVERAGE_FRACTION:
            qc_flags.append(f"{QC_FLAG_SPARSE_CURVE_COVERAGE}:{canonical_name}")

    resolved_gr_name: Optional[str] = None
    resolved_gr_source: Optional[str] = None
    if gr_family_canonical_name is not None:
        slot = curves.get(gr_family_canonical_name)
        if slot is None:
            qc_flags.append(f"{QC_FLAG_GR_FAMILY_ABSENT}:{gr_family_canonical_name}")
        else:
            resolved_gr_name = slot.canonical_name
            resolved_gr_source = slot.source_curve_name

    n_depth_unmapped = int(n_samples - np.count_nonzero(depth_valid_mask))
    if depth_map_status == DEPTH_MAP_STATUS_PARTIAL:
        qc_flags.append(f"{QC_FLAG_DEPTH_COVERAGE_LIMITED}:{n_depth_unmapped}")
    elif depth_map_status == DEPTH_MAP_STATUS_NONE:
        qc_flags.append(QC_FLAG_NO_DEPTH_COVERAGE)

    return WellFrame(
        well_key=well_key,
        source_las_filename=las_basename,
        source_survey_filename=survey_basename,
        n_samples=n_samples,
        MD_m=_readonly(md),
        TVD_m=_readonly(tvd_full),
        TVDSS_m=_readonly(tvdss_full),
        depth_valid_mask=_readonly(np.asarray(depth_valid_mask, dtype=bool)),
        depth_basis_used=depth_basis_used,
        interpolation_method=interpolation_method,
        datum_elevation_m=datum_elevation_m,
        depth_map_status=depth_map_status,
        survey_md_min_m=survey_md_min_m,
        survey_md_max_m=survey_md_max_m,
        las_md_min_m=float(np.min(md)),
        las_md_max_m=float(np.max(md)),
        n_depth_unmapped=n_depth_unmapped,
        n_extrapolated=0,
        curves=curves,
        gr_family_canonical_name=resolved_gr_name,
        gr_family_source_curve_name=resolved_gr_source,
        # LAS well identity is genuinely verified from file CONTENT: the
        # locked contract resolver compares `FileContract
        # .expected_well_identifier` against the file's own `WELL` header
        # line and raises a contract ERROR on disagreement, so a
        # successfully loaded `LasFileResult` has already had its declared
        # well name checked against the file itself. This is a stronger
        # evidence status than the Increment 5 formation-top files earned
        # (filename-only association), and is recorded as such rather than
        # being flattened to the weaker label for uniformity's sake.
        well_identity_evidence_status="verified_against_file_well_header",
        qc_flags=tuple(qc_flags),
    )


def assemble_well_frames(
    las_results: Dict[str, LasFileResult],
    dev_results: Dict[str, DeviationWellResult],
    *,
    las_paths: Dict[str, str],
    survey_paths: Dict[str, str],
    gr_family_by_well: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, WellFrame], Dict[str, WellFrameAssemblyFailure]]:
    """
    Assemble well frames for a batch of wells, isolating per-well failures
    exactly as the locked batch loaders do: one well's failure never stops
    the others, and each well key ends up in exactly one of the two
    returned dicts, never both.

    A well present in `las_results` but absent from `dev_results` (or vice
    versa) is recorded as a typed failure with the correct
    `failure_origin` - it is never assembled against another well's survey
    and never given a substituted trajectory.

    Results are keyed and iterated deterministically (sorted by well key)
    so that downstream output tables are byte-reproducible.
    """
    gr_family_by_well = gr_family_by_well or {}
    frames: Dict[str, WellFrame] = {}
    failures: Dict[str, WellFrameAssemblyFailure] = {}

    for well_key in sorted(set(las_results) | set(dev_results)):
        las_path = las_paths.get(well_key, "")
        survey_path = survey_paths.get(well_key, "")
        las_result = las_results.get(well_key)
        dev_result = dev_results.get(well_key)

        if las_result is None:
            failures[well_key] = WellFrameAssemblyFailure(
                well_key=well_key,
                failure_origin="las",
                error_type="missing_las_result",
                message=f"{well_key}: no successfully loaded LAS result was supplied for this well.",
                las_path=las_path or None,
                survey_path=survey_path or None,
            )
            continue
        if dev_result is None:
            failures[well_key] = WellFrameAssemblyFailure(
                well_key=well_key,
                failure_origin="survey",
                error_type="missing_survey_result",
                message=(
                    f"{well_key}: no successfully loaded deviation-survey result was supplied for "
                    f"this well; a well frame is never assembled against another well's trajectory."
                ),
                las_path=las_path or None,
                survey_path=survey_path or None,
            )
            continue

        try:
            frames[well_key] = assemble_well_frame(
                well_key,
                las_result,
                dev_result,
                las_path=las_path,
                survey_path=survey_path,
                gr_family_canonical_name=gr_family_by_well.get(well_key),
            )
        except WellFrameAssemblyError as exc:
            failures[well_key] = WellFrameAssemblyFailure(
                well_key=well_key, failure_origin="curve_assembly", error_type="assembly_failure",
                message=str(exc), las_path=las_path or None, survey_path=survey_path or None, exception=exc,
            )
        except DepthMappingError as exc:
            failures[well_key] = WellFrameAssemblyFailure(
                well_key=well_key, failure_origin="depth_mapping", error_type="depth_mapping_failure",
                message=str(exc), las_path=las_path or None, survey_path=survey_path or None, exception=exc,
            )

    return frames, failures
