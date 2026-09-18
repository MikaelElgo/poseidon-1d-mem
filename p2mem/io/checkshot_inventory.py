"""
p2mem.io.checkshot_inventory - Deterministic, metadata-only inventory-table
builders for the Increment 4 checkshot / time-depth layer.

Mirrors the design of `p2mem.io.deviation_inventory` (Increment 3, LOCKED):
every function here returns a list of plain dicts (one per output row),
ready for `csv.DictWriter`, or a single JSON-serializable manifest dict -
never a full per-sample checkshot or LAS array (see "Package deterministic
summaries and QC metadata only" in the Increment 4 specification). Every
row uses only a file's BASENAME for any path-shaped field, and every
numeric field is a plain Python float/int (never a NumPy scalar) so the
output is stable JSON/CSV regardless of environment - this is the same
environment-independence discipline established in Increment 3.1's
`_sanitize_message` correction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from p2mem.checkshot_models import (
    CheckshotAvailabilityRecord,
    CheckshotIngestionFailure,
    CheckshotWellResult,
    SonicCheckshotDriftResult,
    TimeDepthMappingSummary,
)

__all__ = [
    "build_checkshot_file_inventory_rows",
    "build_checkshot_issues_rows",
    "build_duplicate_tie_register_rows",
    "build_checkshot_time_axis_tie_register_rows",
    "build_checkshot_depth_tie_qc_rows",
    "build_checkshot_velocity_summary_rows",
    "build_sonic_checkshot_drift_rows",
    "build_time_depth_mapping_rows",
    "build_checkshot_time_depth_manifest",
]


def _sanitize_message(message: str, source_path: str) -> str:
    """Replace a literal full path inside `message` with its basename
    (mirrors `p2mem.io.deviation_inventory._sanitize_message`)."""
    basename = Path(source_path).name
    return message.replace(source_path, basename)


def build_checkshot_file_inventory_rows(
    results: Dict[str, CheckshotWellResult],
    failures: Dict[str, CheckshotIngestionFailure],
    availability: Dict[str, CheckshotAvailabilityRecord] = None,
) -> List[dict]:
    availability = availability or {}
    rows: List[dict] = []
    for well_key in sorted(set(results) | set(failures) | set(availability)):
        if well_key in results:
            r = results[well_key]
            n_errors = sum(1 for i in r.issues if i.severity == "ERROR")
            n_warnings = sum(1 for i in r.issues if i.severity == "WARNING")
            rows.append(
                {
                    "well_key": well_key,
                    "source_filename": r.header.source_filename,
                    "sha256": r.header.sha256,
                    "project_well_key": r.contract.project_well_key,
                    "well_identity_evidence_status": r.contract.well_identity_evidence_status,
                    "model_use_status": r.contract.model_use_status,
                    "n_raw_rows": int(r.raw.Depth_source_m.size),
                    "n_conditioned_rows": r.conditioned.n_conditioned_rows,
                    "n_tie_groups": r.conditioned.n_tie_groups,
                    "depth_min_m": float(r.raw.Depth_source_m.min()),
                    "depth_max_m": float(r.raw.Depth_source_m.max()),
                    "tvdss_min_m": float(r.raw.TVDSS_source_m.min()),
                    "tvdss_max_m": float(r.raw.TVDSS_source_m.max()),
                    "owt_min_s": float(r.raw.OWT_source_s.min()),
                    "owt_max_s": float(r.raw.OWT_source_s.max()),
                    "contract_status": r.contract_status,
                    "n_errors": n_errors,
                    "n_warnings": n_warnings,
                    "error_type": "",
                    "error_message": "",
                }
            )
        elif well_key in failures:
            f = failures[well_key]
            rows.append(
                {
                    "well_key": well_key,
                    "source_filename": Path(f.source_path).name,
                    "sha256": "",
                    "project_well_key": "",
                    "well_identity_evidence_status": "",
                    "model_use_status": "",
                    "n_raw_rows": "",
                    "n_conditioned_rows": "",
                    "n_tie_groups": "",
                    "depth_min_m": "",
                    "depth_max_m": "",
                    "tvdss_min_m": "",
                    "tvdss_max_m": "",
                    "owt_min_s": "",
                    "owt_max_s": "",
                    "contract_status": "FAILED",
                    "n_errors": "",
                    "n_warnings": "",
                    "error_type": f.error_type,
                    "error_message": _sanitize_message(f.message, f.source_path),
                }
            )
        else:
            a = availability[well_key]
            rows.append(
                {
                    "well_key": well_key,
                    "source_filename": "",
                    "sha256": "",
                    "project_well_key": well_key,
                    "well_identity_evidence_status": "",
                    "model_use_status": "",
                    "n_raw_rows": "",
                    "n_conditioned_rows": "",
                    "n_tie_groups": "",
                    "depth_min_m": "",
                    "depth_max_m": "",
                    "tvdss_min_m": "",
                    "tvdss_max_m": "",
                    "owt_min_s": "",
                    "owt_max_s": "",
                    "contract_status": a.checkshot_availability,
                    "n_errors": "",
                    "n_warnings": "",
                    "error_type": "",
                    "error_message": a.notes,
                }
            )
    return rows


def build_checkshot_issues_rows(
    results: Dict[str, CheckshotWellResult], failures: Dict[str, CheckshotIngestionFailure]
) -> List[dict]:
    rows: List[dict] = []
    for well_key in sorted(results):
        r = results[well_key]
        for issue in r.issues:
            rows.append(
                {
                    "well_key": well_key,
                    "source_filename": r.header.source_filename,
                    "severity": issue.severity,
                    "code": issue.code,
                    "message": issue.message,
                    "context": issue.context,
                }
            )
    for well_key in sorted(failures):
        f = failures[well_key]
        rows.append(
            {
                "well_key": well_key,
                "source_filename": Path(f.source_path).name,
                "severity": "ERROR",
                "code": f.error_type.upper(),
                "message": _sanitize_message(f.message, f.source_path),
                "context": Path(f.source_path).name,
            }
        )
    return rows


def build_duplicate_tie_register_rows(results: Dict[str, CheckshotWellResult]) -> List[dict]:
    rows: List[dict] = []
    for well_key in sorted(results):
        r = results[well_key]
        for tie in r.duplicate_ties:
            rows.append(
                {
                    "well_key": tie.well_key,
                    "axis": tie.axis,
                    "tie_value_m": tie.tie_value_m,
                    "source_row_indices": ";".join(str(i) for i in tie.source_row_indices),
                    "original_tvdss_m": ";".join(str(v) for v in tie.original_tvdss_m),
                    "original_owt_s": ";".join(str(v) for v in tie.original_owt_s),
                    "duplicate_type": tie.duplicate_type,
                    "group_size": tie.group_size,
                    "tvdss_value_spread_m": tie.tvdss_value_spread_m,
                    "owt_value_spread_s": tie.owt_value_spread_s,
                    "selected_representative_tvdss_m": tie.selected_representative_tvdss_m,
                    "selected_representative_owt_s": tie.selected_representative_owt_s,
                    "conditioning_rule": tie.conditioning_rule,
                    "affected_downstream_outputs": ";".join(tie.affected_downstream_outputs),
                }
            )
    return rows


def build_checkshot_time_axis_tie_register_rows(results: Dict[str, CheckshotWellResult]) -> List[dict]:
    """
    One row per `AxisTimeDepthTieRegisterEntry` (Increment 4.1) - the
    order-invariant TVDSS/OWT-axis tie register, separate from (and never
    confused with) `build_duplicate_tie_register_rows`'s Depth-axis
    register. `conditioned_row_indices` index into that well's
    Depth-conditioned arrays (`ConditionedCheckshotData`), NOT the raw
    arrays - see `checkshot_duplicate_tie_register.csv` for the raw-row
    (Depth-axis) register.
    """
    rows: List[dict] = []
    for well_key in sorted(results):
        r = results[well_key]
        for tie in r.axis_tie_entries:
            rows.append(
                {
                    "well_key": tie.well_key,
                    "interpolation_direction": tie.interpolation_direction,
                    "axis": tie.axis,
                    "dependent_axis": tie.dependent_axis,
                    "tie_axis_value": tie.tie_axis_value,
                    "conditioned_row_indices": ";".join(str(i) for i in tie.conditioned_row_indices),
                    "associated_depth_m": ";".join(str(v) for v in tie.associated_depth_m),
                    "original_dependent_values": ";".join(str(v) for v in tie.original_dependent_values),
                    "group_size": tie.group_size,
                    "dependent_value_spread": tie.dependent_value_spread,
                    "selected_representative_dependent_value": tie.selected_representative_dependent_value,
                    "conditioning_rule": tie.conditioning_rule,
                    "tie_kind": tie.tie_kind,
                    "affected_downstream_outputs": ";".join(tie.affected_downstream_outputs),
                }
            )
    return rows


def build_checkshot_depth_tie_qc_rows(results: Dict[str, CheckshotWellResult]) -> List[dict]:
    rows: List[dict] = []
    for well_key in sorted(results):
        c = results[well_key].depth_comparison
        if c is None:
            continue
        rows.append(
            {
                "well_key": c.well_key,
                "n_compared": c.n_compared,
                "n_outside_survey_md_coverage": c.n_outside_survey_md_coverage,
                "min_residual_m": c.min_residual_m,
                "max_residual_m": c.max_residual_m,
                "max_abs_residual_m": c.max_abs_residual_m,
                "mean_residual_m": c.mean_residual_m,
                "median_residual_m": c.median_residual_m,
                "rmse_m": c.rmse_m,
                "first_residual_m": c.first_residual_m,
                "last_residual_m": c.last_residual_m,
                "residual_trend_description": c.residual_trend_description,
                "depth_basis_interpretation_status": c.depth_basis_interpretation_status,
                "residual_sign_convention": c.residual_sign_convention,
            }
        )
    return rows


def build_checkshot_velocity_summary_rows(results: Dict[str, CheckshotWellResult]) -> List[dict]:
    rows: List[dict] = []
    for well_key in sorted(results):
        v = results[well_key].velocity
        import numpy as np  # local import: only used for this summary reduction

        vavg_finite = v.Vavg_m_s[np.isfinite(v.Vavg_m_s)]
        vint_valid = v.Vint_m_s[~v.vint_invalid_mask] if v.n_vint_intervals else np.array([])
        rows.append(
            {
                "well_key": v.well_key,
                "n_conditioned_rows": int(v.Depth_conditioned_m.size),
                "vavg_min_m_s": float(vavg_finite.min()) if vavg_finite.size else "",
                "vavg_max_m_s": float(vavg_finite.max()) if vavg_finite.size else "",
                "vavg_mean_m_s": float(vavg_finite.mean()) if vavg_finite.size else "",
                "n_vint_intervals": v.n_vint_intervals,
                "n_vint_invalid": v.n_vint_invalid,
                "vint_valid_min_m_s": float(vint_valid.min()) if vint_valid.size else "",
                "vint_valid_max_m_s": float(vint_valid.max()) if vint_valid.size else "",
                "vint_valid_mean_m_s": float(vint_valid.mean()) if vint_valid.size else "",
                "non_positive_delta_owt_count": v.vint_invalid_reason_counts.get(
                    "non_positive_delta_owt", 0
                ),
                "non_positive_delta_tvdss_count": v.vint_invalid_reason_counts.get(
                    "non_positive_delta_tvdss", 0
                ),
            }
        )
    return rows


def build_sonic_checkshot_drift_rows(
    drift_results: Dict[str, SonicCheckshotDriftResult]
) -> List[dict]:
    rows: List[dict] = []
    for well_key in sorted(drift_results):
        d = drift_results[well_key]
        rows.append(
            {
                "well_key": d.well_key,
                "md_interval_start_m": d.md_interval_start_m,
                "md_interval_end_m": d.md_interval_end_m,
                "n_sonic_samples": d.n_sonic_samples,
                "selection_criteria": d.selection_criteria,
                "integration_method": d.integration_method,
                "sonic_transit_time_s": d.sonic_transit_time_s,
                "checkshot_owt_increment_s": d.checkshot_owt_increment_s,
                "sonic_minus_checkshot_ms": d.sonic_minus_checkshot_ms,
                "checkshot_minus_sonic_ms": d.checkshot_minus_sonic_ms,
                "sonic_minus_checkshot_percent": d.sonic_minus_checkshot_percent,
                "limitations": " | ".join(d.limitations),
            }
        )
    return rows


def build_time_depth_mapping_rows(mappings: Dict[str, TimeDepthMappingSummary]) -> List[dict]:
    rows: List[dict] = []
    for well_key in sorted(mappings):
        m = mappings[well_key]
        rows.append(
            {
                "well_key": m.well_key,
                "n_las_samples": m.n_las_samples,
                "n_inside_coverage": m.n_inside_coverage,
                "n_shallower_than_coverage": m.n_shallower_than_coverage,
                "n_deeper_than_coverage": m.n_deeper_than_coverage,
                "mapped_fraction": m.mapped_fraction,
                "checkshot_depth_min_m": m.checkshot_depth_min_m,
                "checkshot_depth_max_m": m.checkshot_depth_max_m,
                "las_md_min_m": m.las_md_min_m,
                "las_md_max_m": m.las_md_max_m,
                "interpolation_method": m.interpolation_method,
                "n_extrapolated": m.n_extrapolated,
            }
        )
    return rows


def _axis_tie_conditioning_summary(r: CheckshotWellResult) -> dict:
    """
    Per-well summary (Increment 4.1) of the order-invariant axis-tie
    conditioning applied to each inversion direction's lookup table -
    NEVER confused with `n_tie_groups` above, which counts Depth-axis
    (raw-row) ties only. `axis_tie_conditioning_policy` names the
    deterministic representative rule actually used (median, per group,
    order-invariant) so a reader never has to infer it from the counts
    alone.
    """
    to_owt = r.axis_tables.get("tvdss_to_owt") if r.axis_tables else None
    to_tvdss = r.axis_tables.get("owt_to_tvdss") if r.axis_tables else None
    return {
        "axis_tie_conditioning_policy": (
            "order-invariant: ties on the axis being inverted are grouped by exact value "
            "(regardless of which tied row was parsed first), and each group's dependent-value "
            "MEDIAN becomes the group's single conditioned representative; a genuine reversal "
            "(not a tie) raises TimeDepthError rather than being sorted or forced monotonic."
        ),
        "n_tvdss_axis_tie_groups": to_owt.n_axis_tie_groups if to_owt is not None else 0,
        "n_tvdss_axis_collapsed_points": to_owt.n_collapsed_points if to_owt is not None else 0,
        "n_tvdss_axis_identical_pairs": to_owt.n_identical_pairs if to_owt is not None else 0,
        "n_tvdss_axis_genuinely_nonunique_groups": (
            to_owt.n_genuinely_nonunique_groups if to_owt is not None else 0
        ),
        "n_owt_axis_tie_groups": to_tvdss.n_axis_tie_groups if to_tvdss is not None else 0,
        "n_owt_axis_collapsed_points": to_tvdss.n_collapsed_points if to_tvdss is not None else 0,
        "n_owt_axis_identical_pairs": to_tvdss.n_identical_pairs if to_tvdss is not None else 0,
        "n_owt_axis_genuinely_nonunique_groups": (
            to_tvdss.n_genuinely_nonunique_groups if to_tvdss is not None else 0
        ),
    }


def build_checkshot_time_depth_manifest(
    results: Dict[str, CheckshotWellResult],
    failures: Dict[str, CheckshotIngestionFailure],
    availability: Dict[str, CheckshotAvailabilityRecord],
    drift_results: Dict[str, SonicCheckshotDriftResult],
    mappings: Dict[str, TimeDepthMappingSummary],
) -> dict:
    wells = {}
    for well_key in sorted(results):
        r = results[well_key]
        wells[well_key] = {
            "checkshot_availability": "AVAILABLE",
            "source_filename": r.header.source_filename,
            "sha256": r.header.sha256,
            "project_well_key": r.contract.project_well_key,
            "well_identity_evidence_status": r.contract.well_identity_evidence_status,
            "model_use_status": r.contract.model_use_status,
            "n_raw_rows": int(r.raw.Depth_source_m.size),
            "n_conditioned_rows": r.conditioned.n_conditioned_rows,
            "n_tie_groups": r.conditioned.n_tie_groups,
            "contract_status": r.contract_status,
            "n_issue_errors": sum(1 for i in r.issues if i.severity == "ERROR"),
            "n_issue_warnings": sum(1 for i in r.issues if i.severity == "WARNING"),
            "depth_comparison": (
                {
                    "n_compared": r.depth_comparison.n_compared,
                    "max_abs_residual_m": r.depth_comparison.max_abs_residual_m,
                    "mean_residual_m": r.depth_comparison.mean_residual_m,
                    "residual_trend_description": r.depth_comparison.residual_trend_description,
                    "residual_sign_convention": r.depth_comparison.residual_sign_convention,
                }
                if r.depth_comparison is not None
                else None
            ),
            "axis_tie_conditioning": _axis_tie_conditioning_summary(r),
        }
    for well_key in sorted(availability):
        a = availability[well_key]
        wells[well_key] = {
            "checkshot_availability": a.checkshot_availability,
            "notes": a.notes,
        }

    failed = {
        well_key: {"error_type": f.error_type, "message": _sanitize_message(f.message, f.source_path)}
        for well_key, f in failures.items()
    }

    return {
        "increment": "4.1",
        "corrective_patch_of": "4",
        "tier_classification": "Tier C - Screening-Level / Uncalibrated Educational",
        "scope": (
            "Checkshot ingestion, per-file contracts, raw QC/provenance, checkshot-to-deviation "
            "depth-reference comparison, duplicate-tie conditioning, OWT/TWT handling, "
            "average/interval velocity diagnostics, Poseidon 2 sonic-checkshot drift diagnostic, "
            "and forward/inverse time-depth interpolation within validated checkshot coverage "
            "only. Increment 4.1 is a narrowly scoped corrective patch: it replaces the order-"
            "dependent 'keep first, drop later' resolution of a repeated TVDSS/OWT value in the "
            "Depth-conditioned table with an explicit, order-invariant, median-based, fully "
            "registered axis-tie conditioning policy, and adds numerical-validation hardening to "
            "the trapezoidal integrator and the sonic-checkshot drift diagnostic. No formation-"
            "top correction, lithology interpretation, density modelling, pore-pressure "
            "prediction, elastic properties, rock strength, stress modelling, or wellbore-"
            "stability analysis is performed in this increment."
        ),
        "n_wells_checkshot_available": len(results),
        "n_wells_checkshot_not_available": len(availability),
        "n_wells_failed": len(failures),
        "wells": wells,
        "failed_wells": failed,
        "sonic_checkshot_drift": (
            {
                well_key: {
                    "md_interval_m": [d.md_interval_start_m, d.md_interval_end_m],
                    "sonic_minus_checkshot_ms": d.sonic_minus_checkshot_ms,
                    "sonic_minus_checkshot_percent": d.sonic_minus_checkshot_percent,
                }
                for well_key, d in drift_results.items()
            }
        ),
        "time_depth_mapping": (
            {
                well_key: {
                    "mapped_fraction": m.mapped_fraction,
                    "n_extrapolated": m.n_extrapolated,
                    "checkshot_depth_range_m": [m.checkshot_depth_min_m, m.checkshot_depth_max_m],
                }
                for well_key, m in mappings.items()
            }
        ),
    }
