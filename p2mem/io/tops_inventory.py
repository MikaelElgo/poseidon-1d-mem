"""
p2mem.io.tops_inventory - Deterministic, metadata-oriented output-table
builders for the Increment 5 formation-top layer.

Mirrors the design of `p2mem.io.checkshot_inventory` (Increment 4, LOCKED):
every function here returns a list of plain dicts (one per output row),
ready for `csv.DictWriter`, or a single JSON-serializable manifest dict -
never a full per-sample array. Every row uses only a file's BASENAME for
any path-shaped field, and every numeric field is a plain Python
float/int/`None` (never a NumPy scalar), so output is stable JSON/CSV
regardless of environment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from p2mem.top_models import (
    FormationTopAvailabilityRecord,
    FormationTopWellResult,
    TopIngestionFailure,
)

__all__ = [
    "build_top_file_inventory_rows",
    "build_top_marker_register_rows",
    "build_top_reconciliation_rows",
    "build_top_corrected_marker_rows",
    "build_top_issues_rows",
    "build_top_availability_rows",
    "build_formation_top_manifest",
]


def _sanitize_message(message: str, *source_paths) -> str:
    """Replace every literal full path in `source_paths` inside `message`
    with its basename (mirrors `p2mem.io.checkshot_inventory
    ._sanitize_message`; extended in Increment 5.1 - Finding 2 fix - to
    accept more than one candidate path, since a formation-top ingestion
    failure may originate from either the HRS file or the readable file,
    and both must be sanitized wherever a failure message is exported -
    never only the single path recorded in `TopIngestionFailure
    .source_path`). A falsy/`None` path is skipped. Literal substring
    replacement only - never a broad regex, so unrelated scientific text
    is never corrupted."""
    for source_path in source_paths:
        if not source_path:
            continue
        message = message.replace(source_path, Path(source_path).name)
    return message


def _failure_context_basename(f: TopIngestionFailure) -> str:
    """
    Increment 5.1 (Finding 2 fix): the basename of the file that actually
    caused this failure, chosen from `f.failure_origin` - never assumed to
    be the HRS file. For a "reconciliation"/"mapping"-origin failure (both
    files parsed successfully) both source basenames are retained,
    separated by '+', since either or neither may be individually
    implicated. Falls back to `f.source_path`'s basename when no typed
    origin/path is available (e.g. a `TopIngestionFailure` built without
    this classification)."""
    if f.failure_origin == "hrs" and f.hrs_path:
        return Path(f.hrs_path).name
    if f.failure_origin == "readable" and f.readable_path:
        return Path(f.readable_path).name
    if f.hrs_path and f.readable_path:
        return f"{Path(f.hrs_path).name}+{Path(f.readable_path).name}"
    return Path(f.source_path).name


def build_top_file_inventory_rows(
    results: Dict[str, FormationTopWellResult],
    failures: Dict[str, TopIngestionFailure],
    availability: Dict[str, FormationTopAvailabilityRecord] = None,
) -> List[dict]:
    """One row per source FILE (two rows per successfully loaded well -
    HRS and readable - one row per failed/unavailable well)."""
    availability = availability or {}
    rows: List[dict] = []
    for well_key in sorted(results):
        r = results[well_key]
        rows.append(
            {
                "well_key": well_key,
                "representation_type": r.hrs_contract.representation_type,
                "source_filename": r.hrs_header.source_filename,
                "sha256": r.hrs_header.sha256,
                "well_identity_source": r.hrs_header.well_identity_source,
                "well_identity_evidence_status": r.hrs_contract.well_identity_evidence_status,
                "model_use_status": r.hrs_contract.model_use_status,
                "n_markers": len(r.hrs_raw.Top_Name_source),
                "mdrt_min_m": float(r.hrs_raw.MDRT_source_m.min()),
                "mdrt_max_m": float(r.hrs_raw.MDRT_source_m.max()),
                "tvdss_min_m": "",
                "tvdss_max_m": "",
                "contract_status": r.contract_status,
                "n_errors": sum(1 for i in r.issues if i.severity == "ERROR" and i.context == r.hrs_header.source_filename),
                "n_warnings": sum(1 for i in r.issues if i.severity == "WARNING" and i.context == r.hrs_header.source_filename),
            }
        )
        rows.append(
            {
                "well_key": well_key,
                "representation_type": r.readable_contract.representation_type,
                "source_filename": r.readable_header.source_filename,
                "sha256": r.readable_header.sha256,
                "well_identity_source": r.readable_header.well_identity_source,
                "well_identity_evidence_status": r.readable_contract.well_identity_evidence_status,
                "model_use_status": r.readable_contract.model_use_status,
                "n_markers": len(r.readable_raw.TOP_NAME_source),
                "mdrt_min_m": float(r.readable_raw.MDRT_source_m.min()),
                "mdrt_max_m": float(r.readable_raw.MDRT_source_m.max()),
                "tvdss_min_m": float(r.readable_raw.TVDSS_source_m.min()),
                "tvdss_max_m": float(r.readable_raw.TVDSS_source_m.max()),
                "contract_status": r.contract_status,
                "n_errors": sum(1 for i in r.issues if i.severity == "ERROR" and i.context == r.readable_header.source_filename),
                "n_warnings": sum(1 for i in r.issues if i.severity == "WARNING" and i.context == r.readable_header.source_filename),
            }
        )
    for well_key in sorted(failures):
        f = failures[well_key]
        rows.append(
            {
                "well_key": well_key, "representation_type": "", "source_filename": _failure_context_basename(f),
                "sha256": "", "well_identity_source": "", "well_identity_evidence_status": "",
                "model_use_status": "", "n_markers": "", "mdrt_min_m": "", "mdrt_max_m": "",
                "tvdss_min_m": "", "tvdss_max_m": "", "contract_status": "FAILED",
                "n_errors": "", "n_warnings": "",
            }
        )
    for well_key in sorted(availability):
        a = availability[well_key]
        rows.append(
            {
                "well_key": well_key, "representation_type": "", "source_filename": "",
                "sha256": "", "well_identity_source": "", "well_identity_evidence_status": "",
                "model_use_status": "", "n_markers": "", "mdrt_min_m": "", "mdrt_max_m": "",
                "tvdss_min_m": "", "tvdss_max_m": "", "contract_status": a.formation_top_availability,
                "n_errors": "", "n_warnings": "",
            }
        )
    return rows


def build_top_marker_register_rows(results: Dict[str, FormationTopWellResult]) -> List[dict]:
    """One row per raw marker per source file (the full source/provenance
    register: name, source depth, source filename/representation, row
    number, well-association evidence - see the Increment 5 specification,
    'preservation of source marker names and source depths')."""
    rows: List[dict] = []
    for well_key in sorted(results):
        r = results[well_key]
        for i, (name, mdrt) in enumerate(zip(r.hrs_raw.Top_Name_source, r.hrs_raw.MDRT_source_m)):
            rows.append(
                {
                    "well_key": well_key, "source_filename": r.hrs_header.source_filename,
                    "source_representation": r.hrs_contract.representation_type,
                    "source_row_number": i, "top_name_source": name,
                    "MDRT_source_m": float(mdrt), "TVDSS_source_m": "",
                    "note_source": "", "well_identity_source": r.hrs_header.well_identity_source,
                    "well_identity_evidence_status": r.hrs_contract.well_identity_evidence_status,
                }
            )
        for i, (name, mdrt, tvdss, note) in enumerate(
            zip(r.readable_raw.TOP_NAME_source, r.readable_raw.MDRT_source_m, r.readable_raw.TVDSS_source_m, r.readable_raw.NOTE_source)
        ):
            rows.append(
                {
                    "well_key": well_key, "source_filename": r.readable_header.source_filename,
                    "source_representation": r.readable_contract.representation_type,
                    "source_row_number": i, "top_name_source": name,
                    "MDRT_source_m": float(mdrt), "TVDSS_source_m": float(tvdss),
                    "note_source": note, "well_identity_source": r.readable_header.well_identity_source,
                    "well_identity_evidence_status": r.readable_contract.well_identity_evidence_status,
                }
            )
    return rows


def build_top_reconciliation_rows(results: Dict[str, FormationTopWellResult]) -> List[dict]:
    """One row per canonical marker per well - the HRS-versus-readable
    source reconciliation table."""
    rows: List[dict] = []
    for well_key in sorted(results):
        for e in results[well_key].reconciliation:
            rows.append(
                {
                    "well_key": e.well_key, "canonical_marker_name": e.canonical_marker_name,
                    "hrs_marker_name_raw": e.hrs_marker_name_raw or "",
                    "readable_marker_name_raw": e.readable_marker_name_raw or "",
                    "hrs_row_number": e.hrs_row_number if e.hrs_row_number is not None else "",
                    "readable_row_number": e.readable_row_number if e.readable_row_number is not None else "",
                    "present_in_hrs": e.present_in_hrs, "present_in_readable": e.present_in_readable,
                    "name_match_status": e.name_match_status,
                    "MDRT_source_hrs_m": e.MDRT_source_hrs_m if e.MDRT_source_hrs_m is not None else "",
                    "MDRT_source_readable_m": e.MDRT_source_readable_m if e.MDRT_source_readable_m is not None else "",
                    "MDRT_agreement_readable_minus_hrs_m": (
                        e.MDRT_agreement_readable_minus_hrs_m if e.MDRT_agreement_readable_minus_hrs_m is not None else ""
                    ),
                    "mdrt_status": e.mdrt_status,
                    "TVDSS_source_readable_m": e.TVDSS_source_readable_m if e.TVDSS_source_readable_m is not None else "",
                    "note_readable": e.note_readable, "reconciliation_notes": e.reconciliation_notes,
                }
            )
    return rows


def build_top_corrected_marker_rows(results: Dict[str, FormationTopWellResult]) -> List[dict]:
    """One row per canonical marker per well - the corrected, auditable
    survey-mapped stratigraphic marker table (the project's corrected
    depth representation; see `p2mem.top_models.TopMarkerRecord`)."""
    rows: List[dict] = []
    for well_key in sorted(results):
        for m in results[well_key].markers:
            rows.append(
                {
                    "well_key": m.well_key, "canonical_marker_name": m.canonical_marker_name,
                    "MDRT_source_hrs_m": m.MDRT_source_hrs_m if m.MDRT_source_hrs_m is not None else "",
                    "MDRT_source_readable_m": m.MDRT_source_readable_m if m.MDRT_source_readable_m is not None else "",
                    "MDRT_reconciled_m": m.MDRT_reconciled_m if m.MDRT_reconciled_m is not None else "",
                    "mdrt_authority_basis": m.mdrt_authority_basis,
                    "TVDSS_source_m": m.TVDSS_source_m if m.TVDSS_source_m is not None else "",
                    "depth_basis_used": m.depth_basis_used or "",
                    "interpolation_method": m.interpolation_method or "",
                    "TVD_survey_m": m.TVD_survey_m if m.TVD_survey_m is not None else "",
                    "TVDSS_survey_corrected_m": m.TVDSS_survey_corrected_m if m.TVDSS_survey_corrected_m is not None else "",
                    "TVDSS_residual_source_minus_survey_m": (
                        m.TVDSS_residual_source_minus_survey_m
                        if m.TVDSS_residual_source_minus_survey_m is not None else ""
                    ),
                    "mapping_status": m.mapping_status,
                    "well_identity_evidence_status": m.well_identity_evidence_status,
                    "notes": m.notes,
                }
            )
    return rows


def build_top_issues_rows(
    results: Dict[str, FormationTopWellResult], failures: Dict[str, TopIngestionFailure]
) -> List[dict]:
    rows: List[dict] = []
    for well_key in sorted(results):
        for issue in results[well_key].issues:
            rows.append(
                {
                    "well_key": well_key, "severity": issue.severity, "code": issue.code,
                    "message": issue.message, "context": issue.context,
                }
            )
    for well_key in sorted(failures):
        f = failures[well_key]
        rows.append(
            {
                "well_key": well_key, "severity": "ERROR", "code": f.error_type.upper(),
                "message": _sanitize_message(f.message, f.hrs_path, f.readable_path, f.source_path),
                "context": _failure_context_basename(f),
            }
        )
    return rows


def build_top_availability_rows(
    results: Dict[str, FormationTopWellResult],
    failures: Dict[str, TopIngestionFailure],
    availability: Dict[str, FormationTopAvailabilityRecord],
) -> List[dict]:
    rows: List[dict] = []
    for well_key in sorted(set(results) | set(failures) | set(availability)):
        if well_key in results:
            status, notes = "AVAILABLE", ""
        elif well_key in failures:
            f = failures[well_key]
            status, notes = "INGESTION_FAILED", _sanitize_message(f.message, f.hrs_path, f.readable_path, f.source_path)
        else:
            status, notes = availability[well_key].formation_top_availability, availability[well_key].notes
        rows.append({"well_key": well_key, "formation_top_availability": status, "notes": notes})
    return rows


def build_formation_top_manifest(
    results: Dict[str, FormationTopWellResult],
    failures: Dict[str, TopIngestionFailure],
    availability: Dict[str, FormationTopAvailabilityRecord],
) -> dict:
    wells = {}
    for well_key in sorted(results):
        r = results[well_key]
        mapped = [m for m in r.markers if m.mapping_status == "mapped_within_coverage"]
        residuals = [m.TVDSS_residual_source_minus_survey_m for m in mapped if m.TVDSS_residual_source_minus_survey_m is not None]
        wells[well_key] = {
            "formation_top_availability": "AVAILABLE",
            "hrs_source_filename": r.hrs_header.source_filename,
            "hrs_sha256": r.hrs_header.sha256,
            "readable_source_filename": r.readable_header.source_filename,
            "readable_sha256": r.readable_header.sha256,
            "well_identity_evidence_status": (
                "verified"
                if r.hrs_contract.well_identity_evidence_status == "verified"
                and r.readable_contract.well_identity_evidence_status == "verified"
                else "inferred_unverified"
            ),
            "model_use_status": r.hrs_contract.model_use_status,
            "n_canonical_markers": len(r.reconciliation),
            "n_markers_matched": sum(1 for e in r.reconciliation if e.mdrt_status == "MATCHED"),
            "n_markers_mismatch": sum(1 for e in r.reconciliation if e.mdrt_status == "MISMATCH"),
            "n_markers_single_source": sum(1 for e in r.reconciliation if e.mdrt_status == "NOT_COMPARABLE"),
            "n_markers_mapped_within_coverage": len(mapped),
            "n_markers_rejected_outside_coverage": sum(1 for m in r.markers if m.mapping_status == "rejected_outside_coverage"),
            "n_markers_not_mapped_mdrt_unresolved": sum(1 for m in r.markers if m.mapping_status == "not_mapped_mdrt_unresolved"),
            "max_abs_tvdss_residual_source_minus_survey_m": max((abs(x) for x in residuals), default=None),
            "n_issue_errors": sum(1 for i in r.issues if i.severity == "ERROR"),
            "n_issue_warnings": sum(1 for i in r.issues if i.severity == "WARNING"),
        }
    for well_key in sorted(availability):
        a = availability[well_key]
        wells[well_key] = {"formation_top_availability": a.formation_top_availability, "notes": a.notes}

    failed = {
        well_key: {
            "error_type": f.error_type,
            "message": _sanitize_message(f.message, f.hrs_path, f.readable_path, f.source_path),
        }
        for well_key, f in failures.items()
    }

    return {
        "increment": "5",
        "corrective_patch_of": None,
        "tier_classification": "Tier C - Screening-Level / Uncalibrated Educational",
        "scope": (
            "Contract-driven formation-top file ingestion (two independently supplied source "
            "representations per well: 'HRS' MDRT-only, and 'selected readable' MDRT+TVDSS), "
            "explicit HRS-versus-readable source reconciliation (name matching with a human-"
            "authored alias contract, MDRT cross-check), mapping of reconciled MDRT through the "
            "LOCKED Increment 3.1.1 petrel_source_trace survey trajectory, survey-derived TVD/"
            "TVDSS, an explicit source-minus-survey TVDSS residual comparison, corrected auditable "
            "stratigraphic marker tables, formation-top availability/provenance records, and "
            "formation-top QC outputs/figures. No gamma-ray normalization, shale-volume "
            "calculation, named lithology classification, petrophysical interpretation, method-"
            "eligibility masks, shallow-density modelling, overburden-stress integration, NCT "
            "fitting, pore-pressure prediction, elastic properties, rock strength, horizontal "
            "stresses, or wellbore-stability analysis is performed in this increment."
        ),
        "n_wells_formation_top_available": len(results),
        "n_wells_formation_top_not_available": len(availability),
        "n_wells_failed": len(failures),
        "wells": wells,
        "failed_wells": failed,
    }
