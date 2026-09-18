"""
p2mem.io.deviation_inventory - Deterministic, metadata-only inventory-table
builders for the Increment 3 deviation-survey / depth-mapping layer.

Mirrors the design of `p2mem.io.inventory` (the locked LAS-layer inventory
builder) but is a separate module so that file is never modified. Every
function here returns a list of plain dicts (one per output row), ready
for `csv.DictWriter` - never raw per-sample station or LAS arrays (those
stay out of the packaged deliverable; see the Increment 3 manifest).

Environment-independent output (Increment 3.1 correction)
-------------------------------------------------------------
Every row built here uses only a file's BASENAME (e.g.
"Poseidon 2_dev.txt") for `source_filename` and issue `context` fields -
never `DeviationIngestionFailure.source_path` or any other full
filesystem path verbatim. A full path is environment-dependent (a Colab
Drive mount path, a local development build path, a CI temp directory)
even for byte-identical source data, so embedding one in an exported
CSV/JSON deliverable would make that deliverable non-reproducible across
environments. `DeviationIngestionFailure.source_path` remains available
on the underlying typed object for interactive debugging; it is only the
row-builders here (the functions that feed the packaged, deterministic
outputs) that deliberately reduce it to a basename.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from p2mem.deviation_models import DeviationIngestionFailure, DeviationWellResult, LasDepthMappingResult

__all__ = [
    "build_deviation_file_inventory_rows",
    "build_trajectory_validation_rows",
    "build_depth_reference_register_rows",
    "build_las_depth_mapping_rows",
    "build_deviation_issues_rows",
    "build_deviation_depth_manifest",
]


def _sanitize_message(message: str, source_path: str) -> str:
    """
    Replace a literal occurrence of `source_path` (a full filesystem path,
    potentially environment-dependent - a Colab Drive mount path, a local
    build path, a CI temp directory) inside an exception/failure `message`
    string with just that path's basename, so a failure row's exported
    `error_message` never embeds an absolute, environment-specific path
    (Increment 3.1 correction). This only ever matters for a well that
    actually failed to load - every well in this project's real four-well
    delivery loads successfully, so `failed_wells`/failure rows are empty
    in the actual shipped outputs; this function exists so that remains
    true even if a future run does encounter a load failure.
    """
    basename = Path(source_path).name
    return message.replace(source_path, basename)


def build_deviation_file_inventory_rows(
    results: Dict[str, DeviationWellResult], failures: Dict[str, DeviationIngestionFailure]
) -> List[dict]:
    rows: List[dict] = []
    for well_key in sorted(set(results) | set(failures)):
        if well_key in results:
            r = results[well_key]
            n_errors = sum(1 for i in r.issues if i.severity == "ERROR")
            n_warnings = sum(1 for i in r.issues if i.severity == "WARNING")
            rows.append(
                {
                    "well_key": well_key,
                    "source_filename": r.header.source_filename,
                    "sha256": r.header.sha256,
                    "well_name": r.header.well_name,
                    "survey_name": r.header.survey_name,
                    "well_type": r.header.well_type,
                    "wellhead_x_m": r.header.wellhead_x_m,
                    "wellhead_y_m": r.header.wellhead_y_m,
                    "datum_elevation_m": r.header.datum_elevation_m,
                    "datum_reference": r.header.datum_reference,
                    "coordinate_reference_system": r.header.coordinate_reference_system,
                    "n_stations": int(r.raw.MD_source_m.size),
                    "md_min_m": float(r.raw.MD_source_m.min()),
                    "md_max_m": float(r.raw.MD_source_m.max()),
                    "max_inclination_deg": float(r.raw.INCL_source_deg.max()),
                    "contract_status": r.contract_status,
                    "n_errors": n_errors,
                    "n_warnings": n_warnings,
                    "error_type": "",
                    "error_message": "",
                }
            )
        else:
            f = failures[well_key]
            rows.append(
                {
                    "well_key": well_key,
                    "source_filename": Path(f.source_path).name,
                    "sha256": "",
                    "well_name": "",
                    "survey_name": "",
                    "well_type": "",
                    "wellhead_x_m": "",
                    "wellhead_y_m": "",
                    "datum_elevation_m": "",
                    "datum_reference": "",
                    "coordinate_reference_system": "",
                    "n_stations": "",
                    "md_min_m": "",
                    "md_max_m": "",
                    "max_inclination_deg": "",
                    "contract_status": "FAILED",
                    "n_errors": "",
                    "n_warnings": "",
                    "error_type": f.error_type,
                    "error_message": _sanitize_message(f.message, f.source_path),
                }
            )
    return rows


def build_trajectory_validation_rows(results: Dict[str, DeviationWellResult]) -> List[dict]:
    rows: List[dict] = []
    for well_key in sorted(results):
        v = results[well_key].validation
        rows.append(
            {
                "well_key": well_key,
                "comparison_basis": v.comparison_basis,
                "tvd_max_abs_residual_m": v.tvd_max_abs_residual_m,
                "tvd_mean_residual_m": v.tvd_mean_residual_m,
                "tvd_rmse_m": v.tvd_rmse_m,
                "tvd_endpoint_residual_m": v.tvd_endpoint_residual_m,
                "tvd_tolerance_m": v.tvd_tolerance_m,
                "tvd_status": v.tvd_status,
                "easting_max_abs_residual_m": v.easting_max_abs_residual_m,
                "easting_mean_residual_m": v.easting_mean_residual_m,
                "easting_rmse_m": v.easting_rmse_m,
                "easting_endpoint_residual_m": v.easting_endpoint_residual_m,
                "easting_tolerance_m": v.easting_tolerance_m,
                "easting_status": v.easting_status,
                "northing_max_abs_residual_m": v.northing_max_abs_residual_m,
                "northing_mean_residual_m": v.northing_mean_residual_m,
                "northing_rmse_m": v.northing_rmse_m,
                "northing_endpoint_residual_m": v.northing_endpoint_residual_m,
                "northing_tolerance_m": v.northing_tolerance_m,
                "northing_status": v.northing_status,
                "x_consistency_max_abs_residual_m": v.x_consistency_max_abs_residual_m,
                "x_consistency_status": v.x_consistency_status,
                "y_consistency_max_abs_residual_m": v.y_consistency_max_abs_residual_m,
                "y_consistency_status": v.y_consistency_status,
                "z_consistency_max_abs_residual_m": v.z_consistency_max_abs_residual_m,
                "z_consistency_status": v.z_consistency_status,
                "overall_status": v.overall_status,
                "origin_initialization_note": v.origin_initialization_note,
            }
        )
    return rows


def build_depth_reference_register_rows(results: Dict[str, DeviationWellResult]) -> List[dict]:
    rows: List[dict] = []
    for well_key in sorted(results):
        r = results[well_key]
        rows.append(
            {
                "well_key": well_key,
                "datum_elevation_m": r.header.datum_elevation_m,
                "datum_reference": r.header.datum_reference,
                "md_reference_convention": (
                    "MD referenced to zero at well datum (rotary table), positive downward"
                ),
                "tvd_reference_convention": (
                    "TVD referenced to zero at well datum (rotary table), positive downward"
                ),
                "tvdss_formula": "TVDSS_m = TVD_m - DatumElevation_m",
                "z_formula": "Z_m = DatumElevation_m - TVD_m  (equivalently, TVDSS_m = -Z_m)",
                "depth_basis_selected": r.depth_basis.selected_basis,
                "depth_basis_rationale": r.depth_basis.rationale,
                "trajectory_validation_overall_status": r.validation.overall_status,
            }
        )
    return rows


def build_las_depth_mapping_rows(mappings: Dict[str, LasDepthMappingResult]) -> List[dict]:
    rows: List[dict] = []
    for well_key in sorted(mappings):
        m = mappings[well_key]
        rows.append(
            {
                "well_key": well_key,
                "depth_basis_used": m.depth_basis_used,
                "interpolation_method": m.interpolation_method,
                "n_samples": m.n_samples,
                "survey_md_min_m": m.survey_md_min_m,
                "survey_md_max_m": m.survey_md_max_m,
                "las_md_min_m": m.las_md_min_m,
                "las_md_max_m": m.las_md_max_m,
                "coverage_margin_lower_m": m.coverage_margin_lower_m,
                "coverage_margin_upper_m": m.coverage_margin_upper_m,
                "n_extrapolated": m.n_extrapolated,
                "tvd_at_final_las_md_m": float(m.tvd_mapped_m[-1]),
                "tvdss_at_final_las_md_m": float(m.tvdss_mapped_m[-1]),
                "datum_elevation_m": m.datum_elevation_m,
            }
        )
    return rows


def build_deviation_issues_rows(
    results: Dict[str, DeviationWellResult], failures: Dict[str, DeviationIngestionFailure]
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


def build_deviation_depth_manifest(
    results: Dict[str, DeviationWellResult],
    failures: Dict[str, DeviationIngestionFailure],
    mappings: Dict[str, LasDepthMappingResult],
) -> dict:
    wells = {}
    for well_key in sorted(results):
        r = results[well_key]
        m = mappings.get(well_key)
        wells[well_key] = {
            "source_filename": r.header.source_filename,
            "sha256": r.header.sha256,
            "well_name": r.header.well_name,
            "well_type": r.header.well_type,
            "n_stations": int(r.raw.MD_source_m.size),
            "md_range_m": [float(r.raw.MD_source_m.min()), float(r.raw.MD_source_m.max())],
            "max_inclination_deg": float(r.raw.INCL_source_deg.max()),
            "contract_status": r.contract_status,
            "n_issue_errors": sum(1 for i in r.issues if i.severity == "ERROR"),
            "n_issue_warnings": sum(1 for i in r.issues if i.severity == "WARNING"),
            "trajectory_validation": {
                "overall_status": r.validation.overall_status,
                "tvd_max_abs_residual_m": r.validation.tvd_max_abs_residual_m,
                "tvd_status": r.validation.tvd_status,
                "easting_max_abs_residual_m": r.validation.easting_max_abs_residual_m,
                "easting_status": r.validation.easting_status,
                "northing_max_abs_residual_m": r.validation.northing_max_abs_residual_m,
                "northing_status": r.validation.northing_status,
            },
            "depth_basis_selected": r.depth_basis.selected_basis,
            "las_depth_mapping": (
                {
                    "n_samples": m.n_samples,
                    "las_md_range_m": [m.las_md_min_m, m.las_md_max_m],
                    "survey_md_range_m": [m.survey_md_min_m, m.survey_md_max_m],
                    "n_extrapolated": m.n_extrapolated,
                    "tvd_at_final_las_md_m": float(m.tvd_mapped_m[-1]),
                    "tvdss_at_final_las_md_m": float(m.tvdss_mapped_m[-1]),
                }
                if m is not None
                else None
            ),
        }

    failed = {
        well_key: {"error_type": f.error_type, "message": _sanitize_message(f.message, f.source_path)}
        for well_key, f in failures.items()
    }

    return {
        "increment": "3",
        "n_wells_loaded": len(results),
        "n_wells_failed": len(failures),
        "total_stations_all_wells": sum(int(r.raw.MD_source_m.size) for r in results.values()),
        "contracts_passed": sum(1 for r in results.values() if r.contract_status == "PASSED"),
        "trajectory_validation_pass_count": sum(
            1 for r in results.values() if r.validation.overall_status == "PASS"
        ),
        "trajectory_validation_warning_count": sum(
            1 for r in results.values() if r.validation.overall_status == "WARNING"
        ),
        "trajectory_validation_fail_count": sum(
            1 for r in results.values() if r.validation.overall_status == "FAIL"
        ),
        "wells": wells,
        "failed_wells": failed,
    }
