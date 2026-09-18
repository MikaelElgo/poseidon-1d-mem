"""
p2mem.io.inventory - Deterministic inventory-report builders for LAS
ingestion results (Increment 2, corrected in Increment 2.1).

This module turns the typed results from `p2mem.io.las` into the flat,
tabular rows the Increment 2 specification requires under
`outputs/02_las_inventory/`:

    las_file_inventory.csv     - one row per source file
    las_curve_catalog.csv      - one row per contract-declared curve
    las_curve_coverage.csv     - one row per successfully resolved curve
    las_ingestion_issues.csv   - one row per WARNING/ERROR issue found
    las_ingestion_manifest.json - one JSON document tying it all together

No raw LAS sample data is ever written by this module - every function
here emits metadata, provenance, and descriptive statistics only. Row
order is always the deterministic order of the inputs (file iteration
order as given by the caller, then contract-declaration order within a
file), so re-running ingestion against unchanged inputs reproduces
byte-identical output ordering.

Increment 2.1 correction
-------------------------
* `las_curve_coverage.csv` is redesigned (see `build_curve_coverage_rows`)
  to report an explicit RAW/CANONICAL pair of statistics, each tagged
  with its own unit, instead of a single min/max pair labeled only with a
  canonical name and no unit.
* `las.py:load_wells` now returns `IngestionFailure` objects (not bare
  exceptions) for failed wells; every function here that previously took
  `Dict[str, LasContractError]` now takes `Dict[str, IngestionFailure]`
  and reports `error_type`/`error_message` explicitly for every failure
  category (file-not-found and structural-parsing failures included,
  which Increment 2 did not surface in these tables at all since
  `load_wells` let them propagate as uncaught exceptions in most cases).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from p2mem.models import IngestionFailure, LasFileResult


def _failed_well_header_and_issues(failure: IngestionFailure):
    """
    For a "contract_failure", the wrapped `LasContractError` carries a
    successfully-parsed `.header` and the `.issues` collected before
    ingestion stopped - return those. For every other failure category
    ("file_not_found", "parsing_failure", "conversion_failure"), no such
    header/issue list exists (the failure happened before or outside
    per-curve issue tracking), so both are reported as absent rather than
    guessed at.
    """
    if failure.error_type == "contract_failure":
        exc = failure.exception
        return getattr(exc, "header", None), getattr(exc, "issues", ())
    return None, ()


def build_file_inventory_rows(
    results: Dict[str, LasFileResult], errors: Optional[Dict[str, IngestionFailure]] = None
) -> List[dict]:
    """One row per source file: identity, provenance, and header-level facts."""
    rows: List[dict] = []
    for key, result in results.items():
        h = result.header
        rows.append(
            {
                "well_key": key,
                "source_filename": h.source_filename,
                "sha256": h.sha256,
                "well_name": h.well_name,
                "las_version": h.las_version,
                "wrap": h.wrap,
                "declared_null": h.declared_null,
                "declared_strt_m": h.declared_strt,
                "declared_stop_m": h.declared_stop,
                "declared_step_m": h.declared_step,
                "declared_curve_count": len(h.curve_headers),
                "n_samples": result.depth.n_samples,
                "data_start_m": result.depth.data_start,
                "data_stop_m": result.depth.data_stop,
                "data_min_step_m": result.depth.data_min_step,
                "data_max_step_m": result.depth.data_max_step,
                "data_median_step_m": result.depth.data_median_step,
                "n_duplicate_md": result.depth.n_duplicate_md,
                "n_non_monotonic_md": result.depth.n_non_monotonic,
                "strt_matches_declared": result.depth.strt_matches_declared,
                "stop_matches_declared": result.depth.stop_matches_declared,
                "step_matches_declared": result.depth.step_matches_declared,
                "contract_status": result.contract_status,
                "n_warnings": sum(1 for i in result.issues if i.severity == "WARNING"),
                "n_errors": sum(1 for i in result.issues if i.severity == "ERROR"),
                "error_type": None,
                "error_message": None,
            }
        )
    if errors:
        for key, failure in errors.items():
            h, issues = _failed_well_header_and_issues(failure)
            rows.append(
                {
                    "well_key": key,
                    "source_filename": h.source_filename if h else Path(failure.source_path).name,
                    "sha256": h.sha256 if h else None,
                    "well_name": h.well_name if h else None,
                    "las_version": h.las_version if h else None,
                    "wrap": h.wrap if h else None,
                    "declared_null": h.declared_null if h else None,
                    "declared_strt_m": h.declared_strt if h else None,
                    "declared_stop_m": h.declared_stop if h else None,
                    "declared_step_m": h.declared_step if h else None,
                    "declared_curve_count": len(h.curve_headers) if h else None,
                    "n_samples": None,
                    "data_start_m": None,
                    "data_stop_m": None,
                    "data_min_step_m": None,
                    "data_max_step_m": None,
                    "data_median_step_m": None,
                    "n_duplicate_md": None,
                    "n_non_monotonic_md": None,
                    "strt_matches_declared": None,
                    "stop_matches_declared": None,
                    "step_matches_declared": None,
                    "contract_status": "FAILED",
                    "n_warnings": sum(1 for i in issues if i.severity == "WARNING"),
                    "n_errors": sum(1 for i in issues if i.severity == "ERROR") or 1,
                    "error_type": failure.error_type,
                    "error_message": failure.message,
                }
            )
    return rows


def build_curve_catalog_rows(results: Dict[str, LasFileResult]) -> List[dict]:
    """One row per contract-declared curve: raw identity, canonical target, resolution status."""
    rows: List[dict] = []
    for key, result in results.items():
        resolutions_by_name = {r.canonical_name: r for r in result.resolutions}
        for entry in result.contract.curves:
            res = resolutions_by_name[entry.canonical_name]
            rows.append(
                {
                    "well_key": key,
                    "source_filename": result.header.source_filename,
                    "ordinal": entry.ordinal,
                    "semantic_role": entry.semantic_role,
                    "source_curve_name": entry.source_curve_name,
                    "raw_mnemonic": entry.raw_mnemonic,
                    "raw_unit": entry.raw_unit,
                    "raw_description": entry.raw_description,
                    "raw_canonical_name": entry.raw_canonical_name,
                    "canonical_name": entry.canonical_name,
                    "canonical_unit": entry.canonical_unit,
                    "required": entry.required,
                    "conversion_function": entry.conversion_function,
                    "resolution_status": res.status,
                    "resolution_detail": res.detail,
                    "notes": entry.notes.strip(),
                }
            )
    return rows


def build_curve_coverage_rows(results: Dict[str, LasFileResult]) -> List[dict]:
    """
    One row per successfully resolved curve, with EVERY number tagged by
    an explicit unit (Increment 2.1 correction - see the module and
    `CurveStats` docstrings for why the Increment 2 version of this table
    was ambiguous).
    """
    rows: List[dict] = []
    for key, result in results.items():
        for stat in result.curve_stats:
            rows.append(
                {
                    "well_key": key,
                    "source_filename": result.header.source_filename,
                    "source_curve_name": stat.source_curve_name,
                    "raw_mnemonic": stat.raw_mnemonic,
                    "raw_description": stat.raw_description,
                    "raw_unit": stat.raw_unit,
                    "canonical_name": stat.canonical_name,
                    "canonical_unit": stat.canonical_unit,
                    "conversion_function": stat.conversion_function,
                    "n_samples": stat.n_samples,
                    "valid_count": stat.valid_count,
                    "null_count": stat.null_count,
                    "valid_fraction": stat.valid_fraction,
                    "raw_min": stat.raw_min,
                    "raw_max": stat.raw_max,
                    "canonical_min": stat.canonical_min,
                    "canonical_max": stat.canonical_max,
                    "statistics_basis": stat.statistics_basis,
                }
            )
    return rows


def build_issues_rows(
    results: Dict[str, LasFileResult], errors: Optional[Dict[str, IngestionFailure]] = None
) -> List[dict]:
    """One row per WARNING/ERROR issue found across all wells (successes and failures)."""
    rows: List[dict] = []
    for key, result in results.items():
        for issue in result.issues:
            rows.append(
                {
                    "well_key": key,
                    "source_filename": result.header.source_filename,
                    "severity": issue.severity,
                    "code": issue.code,
                    "message": issue.message,
                    "context": issue.context,
                }
            )
    if errors:
        for key, failure in errors.items():
            _, issues = _failed_well_header_and_issues(failure)
            if issues:
                for issue in issues:
                    rows.append(
                        {
                            "well_key": key,
                            "source_filename": Path(failure.source_path).name,
                            "severity": issue.severity,
                            "code": issue.code,
                            "message": issue.message,
                            "context": issue.context,
                        }
                    )
            else:
                # file_not_found / parsing_failure / conversion_failure carry
                # no structured IngestionIssue list (the failure happened
                # before or outside per-curve issue tracking) - the failure
                # itself is still recorded as a single ERROR row so it is
                # never silently absent from this table.
                rows.append(
                    {
                        "well_key": key,
                        "source_filename": Path(failure.source_path).name,
                        "severity": "ERROR",
                        "code": failure.error_type.upper(),
                        "message": failure.message,
                        "context": failure.source_path,
                    }
                )
    return rows


def build_ingestion_manifest(
    results: Dict[str, LasFileResult], errors: Optional[Dict[str, IngestionFailure]] = None
) -> dict:
    """
    Build the single JSON manifest document tying every well's provenance,
    contract-resolution outcome, and summary statistics together.
    """
    errors = errors or {}
    wells = {}
    for key, result in results.items():
        h = result.header
        wells[key] = {
            "source_filename": h.source_filename,
            "sha256": h.sha256,
            "well_name": h.well_name,
            "las_version": h.las_version,
            "wrap": h.wrap,
            "declared_null": h.declared_null,
            "declared_strt_m": h.declared_strt,
            "declared_stop_m": h.declared_stop,
            "declared_step_m": h.declared_step,
            "n_samples": result.depth.n_samples,
            "data_start_m": result.depth.data_start,
            "data_stop_m": result.depth.data_stop,
            "contract_status": result.contract_status,
            "resolved_curves": [r.canonical_name for r in result.resolutions if r.status == "RESOLVED"],
            "missing_optional_curves": [
                r.canonical_name for r in result.resolutions if r.status == "MISSING_OPTIONAL"
            ],
            "n_warnings": sum(1 for i in result.issues if i.severity == "WARNING"),
            "n_errors": sum(1 for i in result.issues if i.severity == "ERROR"),
        }
    for key, failure in errors.items():
        h, issues = _failed_well_header_and_issues(failure)
        wells[key] = {
            "source_filename": h.source_filename if h else Path(failure.source_path).name,
            "sha256": h.sha256 if h else None,
            "well_name": h.well_name if h else None,
            "las_version": h.las_version if h else None,
            "wrap": h.wrap if h else None,
            "declared_null": h.declared_null if h else None,
            "declared_strt_m": h.declared_strt if h else None,
            "declared_stop_m": h.declared_stop if h else None,
            "declared_step_m": h.declared_step if h else None,
            "n_samples": None,
            "data_start_m": None,
            "data_stop_m": None,
            "contract_status": "FAILED",
            "resolved_curves": [],
            "missing_optional_curves": [],
            "n_warnings": sum(1 for i in issues if i.severity == "WARNING"),
            "n_errors": sum(1 for i in issues if i.severity == "ERROR") or 1,
            "error_type": failure.error_type,
            "error_message": failure.message,
        }

    total_rows = sum(r.depth.n_samples for r in results.values())
    return {
        "increment": "2.1",
        "assurance_tier": "Tier C - Screening-Level / Uncalibrated Educational",
        "wells": wells,
        "summary": {
            "n_wells_loaded": len(results),
            "n_wells_failed": len(errors),
            "total_log_rows_all_wells": total_rows,
        },
    }
