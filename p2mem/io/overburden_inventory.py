"""
p2mem.io.overburden_inventory - deterministic Increment 7 export builders.

Every function here turns typed Increment 7 results into the EXACT records the
Increment 7 output policy governs. The records these builders return are the
records that are serialized: nothing downstream reconstructs a parallel scope,
and the manifest's own coverage block is computed from these very payloads.

Determinism
-----------
Row order is fixed by an explicit sort on stable keys (well key, then index or
enumerated position), never by dictionary iteration order. Column order is the
schema's own declared order. Two runs from two independent roots produce
byte-identical artifacts.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from p2mem import ASSURANCE_TIER
from p2mem.overburden import (
    DEPTH_CONVENTION_STATEMENT, SIGN_CONVENTION_ID, pa_to_mpa,
)
from p2mem.overburden_models import (
    SEABED_BASIS_LOCKED_MARKER,
    STATUS_ABSOLUTE,
    STATUS_NOT_ELIGIBLE,
    STATUS_PARTIAL_ONLY,
    STATUS_SENSITIVITY_ONLY,
    DENSITY_MASK_NAMES,
    DensityGapRecord,
    DensityQcStats,
    GapConditioningResult,
    GapThresholdSensitivity,
    OverburdenConfig,
    OverburdenEligibility,
    OverburdenIssue,
    ShallowColumnScenario,
    VerticalStressProfile,
)
from p2mem.io.overburden_policy import validate_emitted_records
from p2mem.io.overburden_registry import (
    ASSURANCE_TIER_VALUE, AVAILABILITY, ELIGIBILITY, GAPS, INCREMENT_TITLE, ISSUES,
    NA_DENSITY, NOT_IMPLEMENTED_TOKENS, OVERBURDEN_BUNDLE, OVERBURDEN_STATEMENTS,
    OVERBURDEN_TEMPLATES, PROFILE, QC, SCENARIOS, SENSITIVITY,
)

__all__ = [
    "OVERBURDEN_OUTPUT_DIR",
    "build_density_availability_rows",
    "build_density_qc_rows",
    "build_density_gap_rows",
    "build_overburden_eligibility_rows",
    "build_vertical_stress_profile_rows",
    "build_shallow_column_scenario_rows",
    "build_gap_threshold_sensitivity_rows",
    "build_overburden_issue_rows",
    "build_overburden_manifest",
    "derive_overburden_issues",
]

OVERBURDEN_OUTPUT_DIR = "outputs/07_density_overburden"

_TIER = ASSURANCE_TIER_VALUE
_UNIT_ALL = "kg/m3; m; Pa; MPa"
_UNIT_M = "m"
_EVIDENCE_MEASURED = "measured"
_EVIDENCE_ASSUMED = "assumed_configured"
_CALIBRATION = "uncalibrated_screening_only"

# Sanity: the tier string this module stamps on every record must be the
# project-wide tier declared by the locked package, not a second copy that
# could drift from it.
if _TIER != ASSURANCE_TIER:  # pragma: no cover - fails at import
    raise ValueError(
        f"Increment 7 assurance tier {_TIER!r} differs from the locked package tier "
        f"{ASSURANCE_TIER!r}.")


def _f(value) -> Optional[float]:
    """Return a plain float, or None. Never a numpy scalar: the schema's
    pre-serialization type check requires `type(value) in (int, float)`, and a
    `numpy.float64` is neither."""
    return None if value is None else float(value)


def _i(value) -> Optional[int]:
    return None if value is None else int(value)


def _dec(value: float, places: int = 4) -> str:
    """Format a number as a decimal literal for a controlled-template slot."""
    return f"{float(value):.{places}f}"


def _sanitize(text: str, limit: int = 480) -> str:
    """Reduce an operator-facing string to the sanitized-diagnostic contract.

    Path separators, newlines and any character outside the declared charset
    are removed rather than escaped, because a diagnostic must never become a
    channel for a path or for arbitrary text.
    """
    from p2mem.io.output_policy import SANITIZED_DIAGNOSTIC_CHARSET
    cleaned = "".join(ch if ch in SANITIZED_DIAGNOSTIC_CHARSET else " " for ch in text)
    cleaned = " ".join(cleaned.split())
    return cleaned[:limit]


# ---------------------------------------------------------------------------
# CSV row builders
# ---------------------------------------------------------------------------

def build_density_availability_rows(
    stats_by_well: Dict[str, DensityQcStats],
    frames: Dict[str, object],
) -> List[dict]:
    """One row per well: what density exists, in what unit, over what interval."""
    rows = []
    for wk in sorted(stats_by_well):
        s = stats_by_well[wk]
        rows.append({
            "well_key": wk,
            "source_las_filename": s.source_las_filename,
            "source_survey_filename": frames[wk].source_survey_filename,
            "density_curve_present": bool(s.curve_present),
            "canonical_curve_name": s.canonical_curve_name or NA_DENSITY,
            "source_curve_name": s.source_curve_name or NA_DENSITY,
            "raw_mnemonic": s.raw_mnemonic or NA_DENSITY,
            "raw_unit": s.raw_unit or NA_DENSITY,
            "canonical_unit": s.canonical_unit or NA_DENSITY,
            "conversion_function": s.conversion_function or NA_DENSITY,
            "unit_resolved": bool(s.unit_resolved),
            "conversion_confirmed": bool(s.conversion_confirmed),
            "evidence_class": _EVIDENCE_MEASURED,
            "n_samples": _i(s.n_samples),
            "n_finite_rhob": _i(s.n_finite),
            "n_non_finite_rhob": _i(s.n_non_finite),
            "n_non_positive_rhob": _i(s.n_non_positive),
            "n_below_screening_min": _i(s.n_below_screening_min),
            "n_above_screening_max": _i(s.n_above_screening_max),
            "n_screening_bound_failures": _i(s.n_screening_bound_failures),
            "n_in_screening_band": _i(s.n_in_screening_band),
            "n_depth_mapped": _i(s.n_depth_mapped),
            "n_depth_unmapped": _i(s.n_depth_unmapped),
            "n_outside_survey_coverage": _i(s.n_samples_outside_survey_coverage),
            "n_eligible": _i(s.n_eligible),
            "first_valid_md_m": _f(s.first_valid_md_m),
            "last_valid_md_m": _f(s.last_valid_md_m),
            "first_valid_tvd_m": _f(s.first_valid_tvd_m),
            "last_valid_tvd_m": _f(s.last_valid_tvd_m),
            "first_valid_tvdss_m": _f(s.first_valid_tvdss_m),
            "last_valid_tvdss_m": _f(s.last_valid_tvdss_m),
            "gross_coverage_md_m": _f(s.gross_coverage_md_m),
            "gross_coverage_tvd_m": _f(s.gross_coverage_tvd_m),
            "median_md_step_m": _f(s.median_md_step_m),
            "depth_basis_used": s.depth_basis_used,
            "depth_map_status": s.depth_map_status,
            "survey_md_min_m": _f(s.survey_md_min_m),
            "survey_md_max_m": _f(s.survey_md_max_m),
            "unit": _UNIT_ALL,
            "assurance_tier": _TIER,
            "statistics_basis": OVERBURDEN_STATEMENTS["availability_statistics_basis"].text,
            "limitations": OVERBURDEN_STATEMENTS["availability_limitations"].text,
        })
    return rows


def build_density_qc_rows(
    stats_by_well: Dict[str, DensityQcStats],
    masks_by_well: Dict[str, object],
    config: OverburdenConfig,
) -> List[dict]:
    """One row per well: every mask count and the QC statistics behind it."""
    rows = []
    for wk in sorted(stats_by_well):
        s = stats_by_well[wk]
        counts = masks_by_well[wk].counts()
        # A machine-diagnostic rendering of the SAME counts, in the declared
        # `name=integer` grammar, so a reader diffing two runs sees one field
        # change rather than twelve.
        diag = ";".join(
            f"{name}={counts[name]}" for name in DENSITY_MASK_NAMES
            if counts[name] is not None)
        rows.append({
            "well_key": wk,
            "canonical_curve_name": s.canonical_curve_name or NA_DENSITY,
            "screening_min_kg_m3": _f(config.rhob_min_kg_m3),
            "screening_max_kg_m3": _f(config.rhob_max_kg_m3),
            "bounds_are_inclusive": bool(config.bounds_are_inclusive),
            "n_source_value_present": _i(counts["source_value_present"]),
            "n_finite_numeric_density": _i(counts["finite_numeric_density"]),
            "n_unit_resolved": _i(counts["unit_resolved"]),
            "n_screening_range_plausible": _i(counts["screening_range_plausible"]),
            "n_below_seabed_sample": _i(counts["below_seabed_sample"]),
            "n_depth_mapping_valid": _i(counts["depth_mapping_valid"]),
            "n_within_survey_coverage": _i(counts["within_survey_coverage"]),
            "n_eligible_for_measured_integration": _i(
                counts["eligible_for_measured_integration"]),
            "n_bridged_short_gap": _i(counts["bridged_short_gap"]),
            "n_unresolved_long_gap": _i(counts["unresolved_long_gap"]),
            "n_unresolved_shallow_column": _i(counts["unresolved_shallow_column"]),
            "n_unresolved_terminal_column": _i(counts["unresolved_terminal_column"]),
            "rhob_min_kg_m3": _f(s.rhob_min_kg_m3),
            "rhob_p05_kg_m3": _f(s.rhob_p05_kg_m3),
            "rhob_median_kg_m3": _f(s.rhob_median_kg_m3),
            "rhob_p95_kg_m3": _f(s.rhob_p95_kg_m3),
            "rhob_max_kg_m3": _f(s.rhob_max_kg_m3),
            "rhob_eligible_p05_kg_m3": _f(s.rhob_eligible_p05_kg_m3),
            "seabed_basis": s.seabed_basis,
            "seabed_mdrt_m": _f(s.seabed_mdrt_m),
            "seabed_tvd_m": _f(s.seabed_tvd_m),
            "seabed_tvdss_m": _f(s.seabed_tvdss_m),
            "shallow_gap_md_m": _f(s.shallow_gap_md_m),
            "shallow_gap_tvd_m": _f(s.shallow_gap_tvd_m),
            "terminal_gap_md_m": _f(s.terminal_gap_md_m),
            "terminal_gap_tvd_m": _f(s.terminal_gap_tvd_m),
            "n_internal_gaps": _i(s.n_internal_gaps),
            "n_internal_gap_samples": _i(s.n_internal_gap_samples),
            "longest_internal_gap_md_m": _f(s.longest_internal_gap_md_m),
            "longest_internal_gap_tvd_m": _f(s.longest_internal_gap_tvd_m),
            "mask_counts": diag,
            "unit": _UNIT_ALL,
            "assurance_tier": _TIER,
            "statistics_basis": OVERBURDEN_STATEMENTS["qc_statistics_basis"].text,
            "limitations": OVERBURDEN_STATEMENTS["qc_limitations"].text,
        })
    return rows


def build_density_gap_rows(
    gaps_by_well: Dict[str, Sequence[DensityGapRecord]],
) -> List[dict]:
    """One row per classified gap, ordered by well then by gap index."""
    rows = []
    for wk in sorted(gaps_by_well):
        for gap in sorted(gaps_by_well[wk], key=lambda g: g.gap_index):
            rows.append({
                "well_key": wk,
                "gap_index": _i(gap.gap_index),
                "gap_class": gap.gap_class,
                "disposition": gap.disposition,
                "n_samples": _i(gap.n_samples),
                "start_index": _i(gap.start_index),
                "end_index": _i(gap.end_index),
                "md_start_m": _f(gap.md_start_m),
                "md_end_m": _f(gap.md_end_m),
                "thickness_md_m": _f(gap.thickness_md_m),
                "tvd_start_m": _f(gap.tvd_start_m),
                "tvd_end_m": _f(gap.tvd_end_m),
                "thickness_tvd_m": _f(gap.thickness_tvd_m),
                "threshold_tvd_m": _f(gap.threshold_tvd_m),
                "bounding_density_above_kg_m3": _f(gap.bounding_density_above_kg_m3),
                "bounding_density_below_kg_m3": _f(gap.bounding_density_below_kg_m3),
                "unit": _UNIT_ALL,
                "assurance_tier": _TIER,
                "limitations": OVERBURDEN_STATEMENTS["gap_inventory_limitations"].text,
            })
    return rows


def build_overburden_eligibility_rows(
    eligibility_by_well: Dict[str, OverburdenEligibility],
    profiles_by_well: Dict[str, Optional[VerticalStressProfile]],
    config: OverburdenConfig,
) -> List[dict]:
    """One row per well: the derived verdict and the evidence behind it."""
    rows = []
    for wk in sorted(eligibility_by_well):
        e = eligibility_by_well[wk]
        p = profiles_by_well.get(wk)
        reasons = ";".join(e.limiting_reasons) if e.limiting_reasons else "none"
        rows.append({
            "well_key": wk,
            "overburden_status": e.status,
            "limiting_reasons": reasons,
            "seabed_resolved": bool(e.seabed_resolved),
            "seabed_basis": e.seabed_basis,
            "n_eligible_samples": _i(e.n_eligible_samples),
            "n_bridged_samples": _i(e.n_bridged_samples),
            "n_unresolved_internal_gaps": _i(e.n_unresolved_internal_gaps),
            "n_unresolved_long_gaps": _i(e.n_unresolved_long_gaps),
            "column_uninterrupted": bool(e.column_uninterrupted),
            "column_truncated_at_unresolved_gap": bool(
                False if p is None else p.column_truncated_at_unresolved_gap),
            "n_eligible_samples_below_truncation": _i(
                0 if p is None else p.n_eligible_samples_below_truncation),
            "eligible_top_tvd_m": _f(e.eligible_top_tvd_m),
            "eligible_base_tvd_m": _f(e.eligible_base_tvd_m),
            "eligible_top_tvdss_m": _f(e.eligible_top_tvdss_m),
            "eligible_base_tvdss_m": _f(e.eligible_base_tvdss_m),
            "measured_thickness_tvd_m": _f(e.measured_thickness_tvd_m),
            "water_column_thickness_tvd_m": _f(e.water_column_thickness_tvd_m),
            "shallow_unresolved_thickness_tvd_m": _f(
                e.shallow_unresolved_thickness_tvd_m),
            "terminal_unresolved_thickness_tvd_m": _f(
                e.terminal_unresolved_thickness_tvd_m),
            "unresolved_long_gap_thickness_tvd_m": _f(
                e.unresolved_long_gap_thickness_tvd_m),
            "measured_increment_pa": _f(e.measured_increment_pa),
            "measured_increment_mpa": _f(pa_to_mpa(e.measured_increment_pa)),
            "bridged_increment_pa": _f(e.bridged_increment_pa),
            "bridged_increment_mpa": _f(pa_to_mpa(e.bridged_increment_pa)),
            "absolute_stress_supported": bool(e.absolute_stress_supported),
            "gravity_m_s2": _f(config.gravity_m_s2),
            "integration_method": config.integration_method,
            "integration_coordinate": "tvdss_m",
            "depth_convention": SIGN_CONVENTION_ID,
            "evidence_class": _EVIDENCE_MEASURED,
            "calibration_status": _CALIBRATION,
            "unit": _UNIT_ALL,
            "assurance_tier": _TIER,
            "purpose": OVERBURDEN_STATEMENTS["eligibility_purpose"].text,
            "limitations": OVERBURDEN_STATEMENTS["eligibility_limitations"].text,
        })
    return rows


def _profile_node_indices(profile: VerticalStressProfile, step_m: float) -> List[int]:
    """Select existing profile nodes at approximately `step_m` in TVDSS.

    Nodes are SELECTED, never interpolated: every exported depth, density and
    cumulative value is one this well actually has. The first and last nodes
    are always included so the reported span equals the integrated span.
    """
    tvdss = np.asarray(profile.tvdss_m, dtype=np.float64)
    picked = [0]
    last = float(tvdss[0])
    for i in range(1, tvdss.size - 1):
        if float(tvdss[i]) - last >= step_m:
            picked.append(i)
            last = float(tvdss[i])
    if tvdss.size > 1:
        picked.append(int(tvdss.size) - 1)
    return picked


def build_vertical_stress_profile_rows(
    profiles_by_well: Dict[str, Optional[VerticalStressProfile]],
    config: OverburdenConfig,
) -> List[dict]:
    """The decimated measured-increment profile, ordered by well then depth."""
    rows = []
    for wk in sorted(profiles_by_well):
        p = profiles_by_well[wk]
        if p is None:
            continue
        md = np.asarray(p.md_m, dtype=np.float64)
        tvd = np.asarray(p.tvd_m, dtype=np.float64)
        tvdss = np.asarray(p.tvdss_m, dtype=np.float64)
        rho = np.asarray(p.density_kg_m3, dtype=np.float64)
        bridged = np.asarray(p.bridged_mask, dtype=bool)
        cum = np.asarray(p.cumulative_measured_increment_pa, dtype=np.float64)
        for node, i in enumerate(_profile_node_indices(
                p, float(config.profile_report_step_tvdss_m))):
            rows.append({
                "well_key": wk,
                "node_index": int(node),
                "md_m": float(md[i]),
                "tvd_m": float(tvd[i]),
                "tvdss_m": float(tvdss[i]),
                "rhob_kg_m3": float(rho[i]),
                "density_source": ("bridged_linear_in_tvd" if bool(bridged[i])
                                   else "measured_rhob"),
                "cumulative_measured_increment_pa": float(cum[i]),
                "cumulative_measured_increment_mpa": float(pa_to_mpa(float(cum[i]))),
                "gravity_m_s2": _f(config.gravity_m_s2),
                "integration_coordinate": "tvdss_m",
                "evidence_class": ("assumed_configured" if bool(bridged[i])
                                   else _EVIDENCE_MEASURED),
                "calibration_status": _CALIBRATION,
                "unit": _UNIT_ALL,
                "assurance_tier": _TIER,
                "limitations": OVERBURDEN_STATEMENTS["profile_limitations"].text,
            })
    return rows


def build_shallow_column_scenario_rows(
    scenarios_by_well: Dict[str, Sequence[ShallowColumnScenario]],
) -> List[dict]:
    """The transparent low/base/high scenarios, in declared scenario order."""
    from p2mem.overburden_models import VALID_SCENARIO_NAMES
    order = {name: i for i, name in enumerate(VALID_SCENARIO_NAMES)}
    tpl = OVERBURDEN_TEMPLATES["scenario_basis"]
    rows = []
    for wk in sorted(scenarios_by_well):
        for sc in sorted(scenarios_by_well[wk], key=lambda s: order[s.scenario_name]):
            part = sc.partition
            rows.append({
                "well_key": wk,
                "scenario_name": sc.scenario_name,
                "assumed_shallow_density_kg_m3": _f(sc.assumed_shallow_density_kg_m3),
                "assumed_density_basis": sc.assumed_density_basis,
                "seawater_density_kg_m3": _f(sc.seawater_density_kg_m3),
                "gravity_m_s2": _f(sc.gravity_m_s2),
                "water_column_thickness_tvd_m": _f(sc.water_column_thickness_tvd_m),
                "unresolved_thickness_tvd_m": _f(sc.unresolved_thickness_tvd_m),
                "measured_thickness_tvd_m": _f(sc.measured_thickness_tvd_m),
                "water_column_stress_pa": _f(part.water_column_pa),
                "unresolved_shallow_stress_pa": _f(part.unresolved_shallow_pa),
                "measured_formation_stress_pa": _f(part.measured_formation_pa),
                "bridged_gap_stress_pa": _f(part.bridged_gap_pa),
                "total_stress_pa": _f(part.total_pa),
                "total_stress_mpa": _f(pa_to_mpa(part.total_pa)),
                "assumed_fraction_of_total": _f(sc.assumed_fraction_of_total),
                "conditioned_fraction_of_total": _f(
                    sc.conditioned_fraction_of_total),
                "measured_fraction_of_total": _f(sc.measured_fraction_of_total),
                "evidence_class": _EVIDENCE_ASSUMED,
                "calibration_status": _CALIBRATION,
                "unit": _UNIT_ALL,
                "assurance_tier": _TIER,
                "scenario_basis": tpl.render({
                    "assumed_density_kg_m3": _dec(sc.assumed_shallow_density_kg_m3),
                    "unresolved_thickness_m": _dec(sc.unresolved_thickness_tvd_m),
                    "assumed_fraction_pct": _dec(
                        100.0 * sc.assumed_fraction_of_total, 2),
                    "conditioned_fraction_pct": _dec(
                        100.0 * sc.conditioned_fraction_of_total, 2),
                    "measured_fraction_pct": _dec(
                        100.0 * sc.measured_fraction_of_total, 2),
                }),
                "limitations": OVERBURDEN_STATEMENTS["scenario_limitations"].text,
            })
    return rows


def build_gap_threshold_sensitivity_rows(
    sensitivity_by_well: Dict[str, Sequence[GapThresholdSensitivity]],
) -> List[dict]:
    """One row per (well, candidate threshold), ordered by well then threshold."""
    rows = []
    for wk in sorted(sensitivity_by_well):
        for t in sorted(sensitivity_by_well[wk], key=lambda x: x.threshold_tvd_m):
            rows.append({
                "well_key": wk,
                "threshold_tvd_m": _f(t.threshold_tvd_m),
                "is_approved_threshold": bool(t.is_approved_threshold),
                "n_bridged_gaps": _i(t.n_bridged_gaps),
                "n_bridged_samples": _i(t.n_bridged_samples),
                "bridged_thickness_tvd_m": _f(t.bridged_thickness_tvd_m),
                "n_long_gaps": _i(t.n_long_gaps),
                "long_gap_thickness_tvd_m": _f(t.long_gap_thickness_tvd_m),
                "n_eligible_or_bridged_samples": _i(t.n_eligible_or_bridged_samples),
                "total_measured_increment_pa": _f(t.total_measured_increment_pa),
                "total_measured_increment_mpa": _f(
                    pa_to_mpa(t.total_measured_increment_pa)),
                "bridged_increment_pa": _f(t.bridged_increment_pa),
                "derived_status": t.derived_status,
                "unit": _UNIT_ALL,
                "assurance_tier": _TIER,
                "limitations": OVERBURDEN_STATEMENTS["gap_sensitivity_limitations"].text,
            })
    return rows


def build_overburden_issue_rows(issues: Sequence[OverburdenIssue]) -> List[dict]:
    """The operator-facing issue table, sorted for determinism."""
    rows = []
    for issue in sorted(issues, key=lambda i: (i.severity, i.code, i.context)):
        rows.append({
            "severity": issue.severity,
            "code": issue.code,
            "context": _sanitize(issue.context),
            "message": _sanitize(issue.message),
            "assurance_tier": _TIER,
        })
    return rows


# ---------------------------------------------------------------------------
# Issue derivation
# ---------------------------------------------------------------------------

def derive_overburden_issues(
    stats_by_well: Dict[str, DensityQcStats],
    eligibility_by_well: Dict[str, OverburdenEligibility],
    gap_results: Dict[str, GapConditioningResult],
    profiles_by_well: Dict[str, Optional[VerticalStressProfile]],
    config: OverburdenConfig,
    *,
    near_bound_tolerance_kg_m3: float = 25.0,
) -> List[OverburdenIssue]:
    """Derive the run's QC issues from MEASURED results, never from a well name."""
    issues: List[OverburdenIssue] = []
    for wk in sorted(stats_by_well):
        s = stats_by_well[wk]
        e = eligibility_by_well[wk]
        gr = gap_results[wk]
        p = profiles_by_well.get(wk)
        if not s.curve_present:
            issues.append(OverburdenIssue(
                "ERROR", "DENSITY_CURVE_ABSENT", wk,
                "No contract-resolved density curve; this well cannot contribute a "
                "measured vertical-stress increment."))
            continue
        if not s.conversion_confirmed:
            issues.append(OverburdenIssue(
                "WARNING", "DENSITY_CONVERSION_FUNCTION_UNEXPECTED", wk,
                f"Locked contract applied conversion {s.conversion_function} where the "
                f"Increment 7 configuration expects "
                f"{config.expected_conversion_function}; reported, not corrected."))
        if s.n_screening_bound_failures:
            issues.append(OverburdenIssue(
                "WARNING", "SCREENING_BOUND_FAILURES_PRESENT", wk,
                f"{s.n_screening_bound_failures} sample(s) fall outside the configured "
                f"screening plausibility band; they are masked out, never modified."))
        if (s.rhob_max_kg_m3 is not None
                and 0.0 <= config.rhob_max_kg_m3 - s.rhob_max_kg_m3
                <= near_bound_tolerance_kg_m3):
            issues.append(OverburdenIssue(
                "INFO", "MEASURED_MAXIMUM_NEAR_SCREENING_BOUND", wk,
                f"The maximum recorded density lies within "
                f"{config.rhob_max_kg_m3 - s.rhob_max_kg_m3:.4f} kg/m3 of the configured "
                f"upper screening bound; the band admits it, and a small change to the "
                f"bound would not."))
        if not e.seabed_resolved:
            issues.append(OverburdenIssue(
                "WARNING", "SEABED_DATUM_UNRESOLVED", wk,
                "No approved formation-top file, so no seabed marker exists in the locked "
                "Increment 5 output; water column and shallow-gap thickness are not "
                "determinable and are reported as unresolved, never as zero."))
        elif e.shallow_unresolved_thickness_tvd_m:
            issues.append(OverburdenIssue(
                "WARNING", "SHALLOW_DENSITY_COLUMN_UNRESOLVED", wk,
                f"{e.shallow_unresolved_thickness_tvd_m:.2f} m of true vertical depth "
                f"between the seabed and the first eligible density sample carries no "
                f"measured density; no absolute vertical stress is defensible for this "
                f"well."))
        if gr.n_long_gaps:
            issues.append(OverburdenIssue(
                "WARNING", "LONG_INTERNAL_GAP_PRESENT", wk,
                f"{gr.n_long_gaps} internal gap(s) totalling "
                f"{gr.long_gap_thickness_tvd_m:.2f} m of true vertical depth exceed the "
                f"approved bridging threshold and are not bridged."))
        if e.terminal_unresolved_thickness_tvd_m:
            issues.append(OverburdenIssue(
                "INFO", "TERMINAL_DENSITY_COLUMN_UNRESOLVED", wk,
                f"{e.terminal_unresolved_thickness_tvd_m:.2f} m of true vertical depth "
                f"below the last eligible density sample carries no measured density."))
        if p is not None and p.column_truncated_at_unresolved_gap:
            issues.append(OverburdenIssue(
                "WARNING", "STRESS_COLUMN_TRUNCATED_AT_UNRESOLVED_GAP", wk,
                f"The integrable column stops at the first unresolved long gap; "
                f"{p.n_eligible_samples_below_truncation} eligible sample(s) below it are "
                f"excluded rather than joined across unknown density."))
        if not e.absolute_stress_supported:
            issues.append(OverburdenIssue(
                "INFO", "ABSOLUTE_OVERBURDEN_NOT_SUPPORTED", wk,
                f"Derived status {e.status}; the measured density coverage does not "
                f"support an absolute vertical overburden-stress curve."))
    return issues


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def build_overburden_manifest(
    stats_by_well: Dict[str, DensityQcStats],
    eligibility_by_well: Dict[str, OverburdenEligibility],
    gap_results: Dict[str, GapConditioningResult],
    profiles_by_well: Dict[str, Optional[VerticalStressProfile]],
    scenarios_by_well: Dict[str, Sequence[ShallowColumnScenario]],
    sensitivity_by_well: Dict[str, Sequence[GapThresholdSensitivity]],
    issues: Sequence[OverburdenIssue],
    frames: Dict[str, object],
    config: OverburdenConfig,
    *,
    depth_convention_verified: bool,
    output_payloads: Dict[str, list],
) -> dict:
    """Build the Increment 7 manifest, including its DERIVED coverage block.

    The coverage block is computed by running the Increment 7 validator over
    `output_payloads` - the ACTUAL CSV records this run will serialize. The
    manifest cannot present itself (it is still being built), so the CSV set is
    passed as the expected artifact set for that pass; the export gate then
    re-validates the COMPLETE set, manifest included, before and after
    serialization.
    """
    coverage = validate_emitted_records(
        OVERBURDEN_BUNDLE, output_payloads, well_keys=set(frames),
        expected_artifacts=set(output_payloads), serialization_stage="pre")
    cov = coverage.as_dict()
    # `emitted_field_coverage` is a COUNT block: its own `violations` key is the
    # number of violations, and the violation records themselves live once, in
    # the sibling `violations` list. Mirrors the locked Increment 6 manifest
    # shape so an auditor reads the two manifests the same way.
    cov["violations"] = len(coverage.violations)

    wells: Dict[str, dict] = {}
    for wk in sorted(stats_by_well):
        s = stats_by_well[wk]
        e = eligibility_by_well[wk]
        p = profiles_by_well.get(wk)
        fr = frames[wk]
        wells[wk] = {
            "source_las_filename": s.source_las_filename,
            "source_survey_filename": fr.source_survey_filename,
            "n_samples": _i(s.n_samples),
            "density_curve_present": bool(s.curve_present),
            "canonical_curve_name": s.canonical_curve_name or NA_DENSITY,
            "canonical_unit": s.canonical_unit or NA_DENSITY,
            "conversion_function": s.conversion_function or NA_DENSITY,
            "unit_resolved": bool(s.unit_resolved),
            "n_finite_rhob": _i(s.n_finite),
            "n_eligible": _i(s.n_eligible),
            "rhob_eligible_p05_kg_m3": _f(s.rhob_eligible_p05_kg_m3),
            "n_bridged_samples": _i(e.n_bridged_samples),
            "n_unresolved_internal_gaps": _i(e.n_unresolved_internal_gaps),
            "n_screening_bound_failures": _i(s.n_screening_bound_failures),
            "n_unresolved_long_gaps": _i(e.n_unresolved_long_gaps),
            "depth_basis_used": s.depth_basis_used,
            "depth_map_status": s.depth_map_status,
            "n_depth_unmapped": _i(s.n_depth_unmapped),
            "datum_elevation_m": _f(fr.datum_elevation_m),
            "seabed_resolved": bool(e.seabed_resolved),
            "seabed_basis": e.seabed_basis,
            "seabed_tvdss_m": _f(s.seabed_tvdss_m),
            "overburden_status": e.status,
            "limiting_reasons": list(e.limiting_reasons),
            "measured_increment_pa": _f(e.measured_increment_pa),
            "measured_increment_mpa": _f(pa_to_mpa(e.measured_increment_pa)),
            "bridged_increment_pa": _f(e.bridged_increment_pa),
            "shallow_unresolved_thickness_tvd_m": _f(
                e.shallow_unresolved_thickness_tvd_m),
            "terminal_unresolved_thickness_tvd_m": _f(
                e.terminal_unresolved_thickness_tvd_m),
            "column_uninterrupted": bool(e.column_uninterrupted),
            "column_truncated_at_unresolved_gap": bool(
                False if p is None else p.column_truncated_at_unresolved_gap),
            "absolute_stress_supported": bool(e.absolute_stress_supported),
            "shallow_column_scenarios": [
                {
                    "scenario_name": sc.scenario_name,
                    "assumed_density_basis": sc.assumed_density_basis,
                    "assumed_shallow_density_kg_m3": _f(
                        sc.assumed_shallow_density_kg_m3),
                    "total_stress_pa": _f(sc.partition.total_pa),
                    "total_stress_mpa": _f(pa_to_mpa(sc.partition.total_pa)),
                    "assumed_fraction_of_total": _f(sc.assumed_fraction_of_total),
                    "conditioned_fraction_of_total": _f(
                        sc.conditioned_fraction_of_total),
                    "measured_fraction_of_total": _f(sc.measured_fraction_of_total),
                }
                for sc in scenarios_by_well.get(wk, ())
            ],
            "gap_threshold_sensitivity": [
                {
                    "threshold_tvd_m": _f(t.threshold_tvd_m),
                    "is_approved_threshold": bool(t.is_approved_threshold),
                    "n_bridged_gaps": _i(t.n_bridged_gaps),
                    "n_long_gaps": _i(t.n_long_gaps),
                    "derived_status": t.derived_status,
                }
                for t in sorted(sensitivity_by_well.get(wk, ()),
                                key=lambda x: x.threshold_tvd_m)
            ],
        }

    statuses = [e.status for e in eligibility_by_well.values()]

    return {
        "assurance_tier": _TIER,
        "increment": 7,
        "increment_title": INCREMENT_TITLE,
        "config_filename": config.source_filename,
        "config_schema_version": config.schema_version,
        "depth_convention": SIGN_CONVENTION_ID,
        "depth_convention_statement": OVERBURDEN_STATEMENTS[
            "manifest_depth_convention_statement"].text,
        "depth_convention_verified": bool(depth_convention_verified),
        "integration_method": config.integration_method,
        "integration_coordinate": "tvdss_m",
        "gravity_m_s2": _f(config.gravity_m_s2),
        "gravity_basis": OVERBURDEN_STATEMENTS["manifest_gravity_basis"].text,
        "assumption_register": {
            "rhob_min_kg_m3": _f(config.rhob_min_kg_m3),
            "rhob_max_kg_m3": _f(config.rhob_max_kg_m3),
            "bounds_are_inclusive": bool(config.bounds_are_inclusive),
            "short_gap_max_tvd_m": _f(config.short_gap_max_tvd_m),
            "shallow_gap_tolerance_tvd_m": _f(config.shallow_gap_tolerance_tvd_m),
            "profile_report_step_tvdss_m": _f(config.profile_report_step_tvdss_m),
            "seawater_density_kg_m3": _f(config.seawater_density_kg_m3),
            "seawater_density_low_kg_m3": _f(config.seawater_density_low_kg_m3),
            "seawater_density_high_kg_m3": _f(config.seawater_density_high_kg_m3),
            "scenario_high_percentile": _f(config.scenario_high_percentile),
            "statement": OVERBURDEN_STATEMENTS["manifest_assumption_statement"].text,
        },
        "calibration_data_available": {
            "pressure_rft_mdt_dst": False,
            "stress_fit_lot_xlot_dfit": False,
            "core_or_log_calibrated_density_control": False,
            "measured_seawater_density": False,
            "local_gravity_survey": False,
            "statement": OVERBURDEN_STATEMENTS["manifest_calibration_statement"].text,
        },
        "n_wells_evaluated": len(stats_by_well),
        "n_wells_absolute_supported": sum(1 for s in statuses if s == STATUS_ABSOLUTE),
        "n_wells_screening_sensitivity_only": sum(
            1 for s in statuses if s == STATUS_SENSITIVITY_ONLY),
        "n_wells_partial_measured_only": sum(
            1 for s in statuses if s == STATUS_PARTIAL_ONLY),
        "n_wells_not_eligible": sum(1 for s in statuses if s == STATUS_NOT_ELIGIBLE),
        "total_eligible_density_samples": sum(
            int(s.n_eligible) for s in stats_by_well.values()),
        "total_bridged_density_samples": sum(
            int(g.n_bridged_samples) for g in gap_results.values()),
        # DERIVED, never hardcoded: a violation means an emitted controlled
        # field escaped its closed registry, which is precisely the condition
        # under which a named lithology could have reached an artifact.
        "named_lithology_assigned": bool(coverage.violations),
        "named_lithology_statement": OVERBURDEN_STATEMENTS[
            "manifest_named_lithology_statement"].text,
        "lithology_validation": {
            "model": OVERBURDEN_STATEMENTS["manifest_lithology_model"].text,
            "derivation": OVERBURDEN_STATEMENTS["manifest_lithology_derivation"].text,
            "emitted_field_coverage": cov,
            "violations": [dict(v) for v in coverage.violations],
        },
        "methods_not_implemented": list(NOT_IMPLEMENTED_TOKENS),
        "limitations": [
            OVERBURDEN_STATEMENTS["limitation_no_absolute_without_full_column"].text,
            OVERBURDEN_STATEMENTS["limitation_no_density_repair"].text,
            OVERBURDEN_STATEMENTS["limitation_assumed_components"].text,
            OVERBURDEN_STATEMENTS["limitation_seabed_provenance"].text,
            OVERBURDEN_STATEMENTS["limitation_no_pore_pressure"].text,
        ],
        "issues": [
            {"severity": r["severity"], "code": r["code"],
             "context": r["context"], "message": r["message"]}
            for r in build_overburden_issue_rows(issues)
        ],
        "wells": wells,
    }
