"""
p2mem.io.petrophysics_inventory - Deterministic, metadata-oriented output
builders for the Increment 6 GR-QC / eligibility layer.

Mirrors the design of the LOCKED `p2mem.io.tops_inventory` (Increment 5)
and `p2mem.io.checkshot_inventory` (Increment 4): every function returns a
list of plain dicts (one per output row) ready for `csv.DictWriter`, or a
single JSON-serializable manifest dict.

Two disciplines are enforced here and tested directly:

1. NO PER-SAMPLE REAL-DATA ARRAYS ARE EVER EXPORTED. Every row is a
   summary, a scenario record, or an interval register entry. Exporting a
   full per-sample GR/VP/VS/RHOB array would effectively reproduce the
   private source logs inside a deliverable ZIP, which this project does
   not do. Interval registers carry depths and counts, never the sample
   values inside the interval.

2. NO ABSOLUTE PATH IS EVER EXPORTED. Any path-shaped field is reduced to
   its basename, and any free-text message is sanitized against every
   candidate source path (both the LAS path and the survey path, since a
   well-frame failure may originate from either - the Increment 5.1
   Finding-2 lesson applied here from the start).

Every numeric field is a plain Python float/int/None, never a NumPy
scalar, so CSV and JSON output is byte-stable across environments.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from p2mem.method_eligibility import EligibilityInterval, EligibilityMaskResult
from p2mem.petrophysics_models import (
    GrEndpointScenario,
    GrFamilyDisposition,
    GrFamilyQcStats,
    GrProxyResult,
    PetrophysicsIssue,
)
from p2mem.io.output_policy import OUTPUT_STATEMENTS
from p2mem.petrophysics import PetrophysicsInputError
from p2mem.wellframe_models import (
    SCOPE_EXPLANATORY,
    SCOPE_METHOD,
    Authorization,
    REGISTERED_STATEMENTS,
    REGISTERED_TEMPLATES,
    SCOPE_INTERPRETIVE,
    SCOPE_LABEL,
    WellFrame,
    WellFrameAssemblyFailure,
    validate_no_prohibited_interpretation,
)

__all__ = [
    "build_gr_family_qc_rows",
    "build_gr_endpoint_scenario_rows",
    "build_gr_proxy_sensitivity_rows",
    "build_method_eligibility_rows",
    "build_eligibility_interval_rows",
    "build_thickness_sensitivity_rows",
    "build_petrophysics_issue_rows",
    "build_petrophysics_manifest",
    "build_lithology_validation_scope",
]

TIER_CLASSIFICATION = "Tier C - Screening-Level / Uncalibrated Educational"

_NOT_A_LITHOLOGY = (
    "Data/proxy confidence only - asserts no named lithology and no calibration."
)


def _sanitize_message(message: str, *source_paths) -> str:
    """Replace every literal full path in `source_paths` with its
    basename. Literal substring replacement only, never a regex, so
    unrelated scientific text is never corrupted. Mirrors the LOCKED
    `p2mem.io.tops_inventory._sanitize_message`."""
    for source_path in source_paths:
        if not source_path:
            continue
        message = message.replace(str(source_path), Path(str(source_path)).name)
    return message


def _f(value) -> Optional[float]:
    """Plain Python float, or None. NaN/Inf become None so CSV/JSON never
    carries a non-finite literal that a downstream reader may parse
    inconsistently."""
    if value is None:
        return None
    v = float(value)
    return v if np.isfinite(v) else None


def _i(value) -> Optional[int]:
    return None if value is None else int(value)


def build_gr_family_qc_rows(
    stats_by_well: Dict[str, GrFamilyQcStats],
    dispositions: Dict[str, GrFamilyDisposition],
    confidence_by_well: Dict[str, str],
) -> List[Dict]:
    """
    One factual QC row per well, INCLUDING every excluded well - the
    numbers that justify an exclusion must themselves be published.
    Sorted by well key for deterministic output.
    """
    rows: List[Dict] = []
    for well_key in sorted(stats_by_well):
        s = stats_by_well[well_key]
        d = dispositions.get(well_key)
        rows.append(
            {
                "well_key": s.well_key,
                "source_las_filename": s.source_las_filename,
                "gr_family_canonical_name": s.gr_family_canonical_name,
                "gr_family_source_curve_name": s.gr_family_source_curve_name,
                "unit": s.unit,
                "use_status": (d.use_status if d else ""),
                "exclusion_reason": (d.exclusion_reason if d and d.exclusion_reason else ""),
                "evidence_class": (d.evidence_class if d else ""),
                "gr_proxy_confidence_class": confidence_by_well.get(well_key, ""),
                "has_approved_formation_tops": (bool(d.has_approved_formation_tops) if d else False),
                "n_samples": _i(s.n_samples),
                "valid_count": _i(s.valid_count),
                "valid_fraction": _f(s.valid_fraction),
                "min_api": _f(s.min_api),
                "max_api": _f(s.max_api),
                "median_api": _f(s.median_api),
                "p01_api": _f(s.p01_api),
                "p05_api": _f(s.p05_api),
                "p10_api": _f(s.p10_api),
                "p25_api": _f(s.p25_api),
                "p50_api": _f(s.p50_api),
                "p75_api": _f(s.p75_api),
                "p90_api": _f(s.p90_api),
                "p95_api": _f(s.p95_api),
                "p99_api": _f(s.p99_api),
                "dynamic_range_p05_p95_api": _f(s.dynamic_range_p05_p95_api),
                "n_negative_samples": _i(s.n_negative_samples),
                "n_zero_samples": _i(s.n_zero_samples),
                "n_samples_above_seabed": _i(s.n_samples_above_seabed),
                "seabed_basis": s.seabed_basis,
                "n_valid_blocks": _i(s.n_valid_blocks),
                "longest_valid_block_samples": _i(s.longest_valid_block_samples),
                "longest_missing_block_samples": _i(s.longest_missing_block_samples),
                "longest_missing_block_md_start_m": _f(s.longest_missing_block_md_start_m),
                "longest_missing_block_md_end_m": _f(s.longest_missing_block_md_end_m),
                "depth_basis": "MDRT (measured depth below rotary table), metres",
                "assurance_tier": TIER_CLASSIFICATION,
                "statistics_basis": s.statistics_basis,
                "limitations": (
                    "Descriptive statistics of the curve AS RECORDED. No environmental correction, "
                    "rescaling, or cross-well normalization applied. " + _NOT_A_LITHOLOGY
                ),
            }
        )
    return rows


#: The authorization-carrying derivation text, itself a registered output
#: statement so this assurance prose is authorized like any other emitted field.
_LITHOLOGY_DERIVATION = OUTPUT_STATEMENTS["lithology_validation_derivation"].text


def _assert_emitted_field_authorized(artifact, field, value, where):
    """Increment 6.1.6 (Finding 1): a row builder must not be able to emit an
    unauthorized controlled value merely because a manifest validator runs
    later. Authorization is checked HERE, on the value actually placed in the
    record, and the resolved credential is returned so it travels with the
    value until serialization."""
    from p2mem.io.output_policy import FieldOccurrence, authorize_occurrence
    ok, auth, reason = authorize_occurrence(
        FieldOccurrence(artifact, field, value, where))
    if not ok:
        raise PetrophysicsInputError(
            f"{artifact}:{field} at {where} is not authorized for emission - {reason}")
    return auth


def build_gr_endpoint_scenario_rows(
    scenarios_by_well: Dict[str, Sequence[GrEndpointScenario]],
) -> List[Dict]:
    """One row per (well, scenario), recording the MEASURED endpoint values
    each configured rule actually produced. Sorted by well then scenario
    name for deterministic output."""
    rows: List[Dict] = []
    for well_key in sorted(scenarios_by_well):
        for sc in sorted(scenarios_by_well[well_key], key=lambda s: s.scenario_name):
            rows.append(
                {
                    "well_key": sc.well_key,
                    "scenario_name": sc.scenario_name,
                    "low_percentile": _f(sc.low_percentile),
                    "high_percentile": _f(sc.high_percentile),
                    "gr_low_endpoint_api": _f(sc.gr_low_endpoint_api),
                    "gr_high_endpoint_api": _f(sc.gr_high_endpoint_api),
                    "endpoint_separation_api": _f(sc.endpoint_separation_api),
                    "n_samples_used_for_endpoints": _i(sc.n_samples_used_for_endpoints),
                    "endpoint_sample_basis": sc.endpoint_sample_basis,
                    "unit": "API",
                    "evidence_class": sc.evidence_class,
                    "calibration_status": sc.calibration_status,
                    "assurance_tier": TIER_CLASSIFICATION,
                    "description": _assert_emitted_field_authorized(
                        "gr_endpoint_scenarios.csv", "description", sc.description,
                        f"{sc.well_key}/{sc.scenario_name}") and sc.description,
                    "limitations": (
                        "Endpoints are ASSUMED, configured percentile values estimated from this "
                        "well's OWN samples. They are not calibrated, are not shared across wells, "
                        "and must never be presented as a validated endpoint pair. " + _NOT_A_LITHOLOGY
                    ),
                }
            )
    return rows


def build_gr_proxy_sensitivity_rows(
    proxies_by_well: Dict[str, Sequence[GrProxyResult]],
    dispositions: Dict[str, GrFamilyDisposition],
) -> List[Dict]:
    """One row per (well, scenario) summarizing IGR/proxy behavior -
    summary statistics and clipping counts only, never per-sample arrays."""
    rows: List[Dict] = []
    for well_key in sorted(proxies_by_well):
        d = dispositions.get(well_key)
        for p in sorted(proxies_by_well[well_key], key=lambda x: x.scenario_name):
            rows.append(
                {
                    "well_key": p.well_key,
                    "scenario_name": p.scenario_name,
                    "gr_family_canonical_name": p.gr_family_canonical_name,
                    "use_status": (d.use_status if d else ""),
                    "gr_low_endpoint_api": _f(p.gr_low_endpoint_api),
                    "gr_high_endpoint_api": _f(p.gr_high_endpoint_api),
                    "transform_name": p.transform_name,
                    "proxy_field_name": "VSH_GR_linear_proxy_frac",
                    "unit": "dimensionless_fraction",
                    "n_valid": _i(p.n_valid),
                    "n_clipped_low": _i(p.n_clipped_low),
                    "n_clipped_high": _i(p.n_clipped_high),
                    "clipped_fraction": _f(p.clipped_fraction),
                    "proxy_median": _f(p.proxy_median),
                    "proxy_p25": _f(p.proxy_p25),
                    "proxy_p75": _f(p.proxy_p75),
                    "calibration_status": p.calibration_status,
                    "evidence_class": "correlation_derived_screening_proxy_uncalibrated",
                    "assurance_tier": TIER_CLASSIFICATION,
                    "limitations": (
                        "IGR and the linear screening proxy are dimensionless quantities derived "
                        "under ASSUMED endpoints. The proxy is NOT a calibrated shale volume and "
                        "NOT a lithology. Clipped and unclipped indices are computed and retained "
                        "together in memory; the clipped counts here quantify how far the real "
                        "data fell outside the assumed endpoint bracket. " + _NOT_A_LITHOLOGY
                    ),
                }
            )
    return rows


def build_method_eligibility_rows(
    mask_results: Sequence[EligibilityMaskResult],
    frames: Dict[str, WellFrame],
    dispositions: Dict[str, GrFamilyDisposition],
) -> List[Dict]:
    """One row per (well, mask, scenario, threshold). Deterministically
    sorted by well, mask, scenario, threshold."""

    def sort_key(m: EligibilityMaskResult):
        return (
            m.well_key,
            m.mask_name,
            m.scenario_name or "",
            float("-inf") if m.proxy_threshold is None else float(m.proxy_threshold),
        )

    rows: List[Dict] = []
    for m in sorted(mask_results, key=sort_key):
        fr = frames.get(m.well_key)
        d = dispositions.get(m.well_key)
        rows.append(
            {
                "well_key": m.well_key,
                "mask_name": m.mask_name,
                "scenario_name": m.scenario_name or "",
                "proxy_threshold": _f(m.proxy_threshold),
                "lithology_dependent": bool(m.lithology_dependent),
                "use_status": (d.use_status if d else ""),
                "exclusion_reason": (d.exclusion_reason if d and d.exclusion_reason else ""),
                "n_samples": _i(m.n_samples),
                "n_eligible": _i(m.n_eligible),
                "eligible_fraction": _f(m.eligible_fraction),
                "limiting_criterion": m.limiting_criterion,
                "criteria_counts": ";".join(f"{k}={v}" for k, v in sorted(m.criteria_counts.items())),
                "diagnostic_counts": ";".join(
                    f"{k}={v}" for k, v in sorted(getattr(m, "diagnostic_counts", {}).items())
                ),
                "depth_basis_used": (fr.depth_basis_used if fr else ""),
                "interpolation_method": (fr.interpolation_method if fr else ""),
                "depth_map_status": (fr.depth_map_status if fr else ""),
                "n_depth_unmapped": _i(fr.n_depth_unmapped) if fr else None,
                "n_extrapolated": _i(fr.n_extrapolated) if fr else None,
                "unit": "sample_count_and_fraction",
                "assurance_tier": TIER_CLASSIFICATION,
                "purpose": m.purpose,
                "limitations": (
                    "ELIGIBILITY IS NOT VALIDITY. This is a necessary, not sufficient, condition "
                    "for a LATER method; the method itself is not implemented, not fitted, and not "
                    "validated in Increment 6. " + m.notes + " " + _NOT_A_LITHOLOGY
                ),
            }
        )
    return rows


def build_eligibility_interval_rows(
    intervals: Sequence[EligibilityInterval],
) -> List[Dict]:
    """
    One row per contiguous eligible block, on MD/TVD/TVDSS.

    Increment 6.1 (Finding 4): thickness is exported under explicitly
    qualified names - `gross_thickness_*_m` (endpoint span, which under the
    configured policy may contain disclosed bridged samples) and
    `net_thickness_*_m` (that span with the bridged gaps removed) - never
    an unqualified "thickness". `contiguity_policy` states which
    decomposition produced the row, and `meets_configured_minimums` states
    whether it qualifies.

    Carries depths, counts and limiting reasons only - never the sample
    values inside the interval, which would reproduce the private source
    log.
    """
    def sort_key(iv: EligibilityInterval):
        return (
            iv.well_key or "",
            iv.mask_name or "",
            iv.contiguity_policy or "",
            iv.scenario_name or "",
            float("-inf") if iv.proxy_threshold is None else float(iv.proxy_threshold),
            int(iv.start_index or 0),
        )

    rows: List[Dict] = []
    for iv in sorted(intervals, key=sort_key):
        d = iv.as_dict()
        rows.append(
            {
                "well_key": d["well_key"],
                "mask_name": d["mask_name"],
                "contiguity_policy": d["contiguity_policy"],
                "scenario_name": d["scenario_name"] or "",
                "proxy_threshold": _f(d["proxy_threshold"]),
                "block_index": _i(d["block_index"]),
                "start_index": _i(d["start_index"]),
                "end_index": _i(d["end_index"]),
                "n_samples": _i(d["n_samples"]),
                "n_eligible_samples": _i(d["n_eligible_samples"]),
                "n_bridged_samples": _i(d["n_bridged_samples"]),
                "n_bridged_gaps": _i(d["n_bridged_gaps"]),
                "n_eligible_subruns": _i(d["n_eligible_subruns"]),
                "meets_configured_minimums": bool(d["meets_configured_minimums"]),
                "md_start_m": _f(d["md_start_m"]),
                "md_end_m": _f(d["md_end_m"]),
                "gross_thickness_md_m": _f(d["gross_thickness_md_m"]),
                "net_thickness_md_m": _f(d["net_thickness_md_m"]),
                "tvd_start_m": _f(d["tvd_start_m"]),
                "tvd_end_m": _f(d["tvd_end_m"]),
                "gross_thickness_tvd_m": _f(d["gross_thickness_tvd_m"]),
                "net_thickness_tvd_m": _f(d["net_thickness_tvd_m"]),
                "tvdss_start_m": _f(d["tvdss_start_m"]),
                "tvdss_end_m": _f(d["tvdss_end_m"]),
                "gross_thickness_tvdss_m": _f(d["gross_thickness_tvdss_m"]),
                "net_thickness_tvdss_m": _f(d["net_thickness_tvdss_m"]),
                "limiting_reason": d["limiting_reason"],
                "depth_basis_used": d["depth_basis_used"],
                "unit": "metres",
                "assurance_tier": TIER_CLASSIFICATION,
                "limitations": (
                    "Candidate/eligible DATA extent only. GROSS thickness is the block's "
                    "endpoint span and, under the configured contiguity policy, may include "
                    "explicitly bridged ineligible samples (see n_bridged_samples); NET "
                    "thickness removes those gaps. Neither is an unqualified 'eligible "
                    "thickness'. A sonic-NCT-candidate interval is not proof of normal "
                    "compaction, is not a fitted trend, and is not a selected donor interval. "
                    + _NOT_A_LITHOLOGY
                ),
            }
        )
    return rows


def build_thickness_sensitivity_rows(
    intervals: Sequence[EligibilityInterval],
) -> List[Dict]:
    """
    Aggregate interval records into one row per
    (well, mask, contiguity policy, scenario, threshold), reporting the
    QUALIFYING population's gross and net thickness side by side together
    with the bridging that separates them.

    Increment 6.1 (Finding 4): every sensitivity case states its population
    explicitly - how many blocks were found, how many qualify, how many
    bridged samples the gross figure absorbed, and how many blocks were
    interrupted - so a gross span can never be read as unbroken eligible
    section.
    """
    keys = sorted({
        (iv.well_key, iv.mask_name, iv.contiguity_policy, iv.scenario_name or "",
         float("-inf") if iv.proxy_threshold is None else float(iv.proxy_threshold))
        for iv in intervals
    })
    rows: List[Dict] = []
    for wk, mask_name, policy, scenario, thr in keys:
        sel = [
            iv for iv in intervals
            if iv.well_key == wk and iv.mask_name == mask_name
            and iv.contiguity_policy == policy
            and (iv.scenario_name or "") == scenario
            and (float("-inf") if iv.proxy_threshold is None
                 else float(iv.proxy_threshold)) == thr
        ]
        qual = [iv for iv in sel if iv.meets_configured_minimums]
        def _sum(items, attr):
            vals = [getattr(iv, attr) for iv in items]
            return None if any(v is None for v in vals) else float(sum(vals))
        rows.append({
            "well_key": wk,
            "mask_name": mask_name,
            "contiguity_policy": policy,
            "scenario_name": scenario,
            "proxy_threshold": None if thr == float("-inf") else _f(thr),
            "n_blocks_all": len(sel),
            "n_blocks_qualifying": len(qual),
            "n_blocks_rejected_below_minimums": len(sel) - len(qual),
            # Increment 6.1.1 (Finding 3): three distinct quantities, each
            # named for exactly what it counts. Samples and gaps are different
            # magnitudes (one gap can absorb several samples), and the count of
            # AFFECTED BLOCKS is different again.
            "n_bridged_samples_in_qualifying_blocks": int(
                sum(iv.n_bridged_samples for iv in qual)
            ),
            "n_bridged_gaps_in_qualifying_blocks": int(
                sum(iv.n_bridged_gaps for iv in qual)
            ),
            "n_interrupted_qualifying_blocks": int(
                sum(1 for iv in qual if iv.n_bridged_gaps > 0)
            ),
            "gross_qualifying_thickness_tvdss_m": _f(_sum(qual, "gross_thickness_tvdss_m")),
            "net_qualifying_thickness_tvdss_m": _f(_sum(qual, "net_thickness_tvdss_m")),
            "gross_all_block_thickness_tvdss_m": _f(_sum(sel, "gross_thickness_tvdss_m")),
            "n_eligible_samples_qualifying": int(sum(iv.n_eligible_samples for iv in qual)),
            "unit": "metres",
            "population_statement": (
                f"Totals cover the {len(qual)} block(s) meeting the configured minimums out of "
                f"{len(sel)} found under the {policy!r} contiguity policy. GROSS is the sum of "
                f"block endpoint spans and includes "
                f"{int(sum(iv.n_bridged_samples for iv in qual))} disclosed bridged sample(s) "
                f"across {int(sum(iv.n_bridged_gaps for iv in qual))} bridged gap(s) in "
                f"{int(sum(1 for iv in qual if iv.n_bridged_gaps > 0))} interrupted block(s); "
                f"NET removes those gaps."
            ),
            "assurance_tier": TIER_CLASSIFICATION,
            "limitations": (
                "Eligible/candidate DATA extent only. No gated method is implemented, fitted, or "
                "validated. " + _NOT_A_LITHOLOGY
            ),
        })
    return rows


def build_petrophysics_issue_rows(
    issues: Sequence[PetrophysicsIssue],
    failures: Dict[str, WellFrameAssemblyFailure],
) -> List[Dict]:
    """Issue rows plus one row per well-frame assembly failure, with every
    message sanitized against BOTH candidate source paths."""
    rows: List[Dict] = []
    for iss in issues:
        rows.append(
            {
                "severity": iss.severity,
                "code": iss.code,
                "context": iss.context,
                "message": iss.message,
                "assurance_tier": TIER_CLASSIFICATION,
            }
        )
    for well_key in sorted(failures):
        f = failures[well_key]
        rows.append(
            {
                "severity": "ERROR",
                "code": f"WELLFRAME_{f.error_type.upper()}",
                "context": (
                    f"{f.well_key} (failure_origin={f.failure_origin}; "
                    f"{'+'.join(sorted({Path(p).name for p in (f.las_path, f.survey_path) if p}))})"
                ),
                "message": _sanitize_message(f.message, f.las_path, f.survey_path),
                "assurance_tier": TIER_CLASSIFICATION,
            }
        )
    return rows


_RATIONALE_TEMPLATE_ID = "gr_proxy_confidence_rationale"


def _template_binding(text):
    """Resolve `text` against the registered rationale template by PARSING the
    declared substitution slots out of it. Returns the Authorization when the
    rendered result matches exactly, else None.

    This is a lookup against a registered template, not an inference about
    meaning: the surrounding prose must match the template character for
    character, and only the declared numeric slots may differ.
    """
    tpl = REGISTERED_TEMPLATES.get(_RATIONALE_TEMPLATE_ID)
    if tpl is None:
        return None
    names, literals = [], []
    rest, buf = tpl.template, ""
    while "{" in rest:
        head, _, rest = rest.partition("{")
        name, _, rest = rest.partition("}")
        literals.append(buf + head)
        names.append(name)
        buf = ""
    literals.append(buf + rest)
    remainder, values = text, {}
    if not remainder.startswith(literals[0]):
        return None
    remainder = remainder[len(literals[0]):]
    for name, nxt in zip(names, literals[1:]):
        if nxt:
            value, sep, remainder = remainder.partition(nxt)
            if not sep:
                return None
        else:
            value, remainder = remainder, ""
        values[name] = value
    if remainder:
        return None
    auth = Authorization(template_id=_RATIONALE_TEMPLATE_ID, fields=values)
    return auth if tpl.render(values) == text else None


def _auth_for_text(text, scope):
    """Return the Authorization for an exact registered statement in `scope`,
    or a template binding, or None when nothing registered matches."""
    for statement_id, st in REGISTERED_STATEMENTS.items():
        if st.scope == scope and st.text == text:
            return Authorization(statement_id=statement_id)
    if scope == SCOPE_INTERPRETIVE:
        return _template_binding(text)
    return None


def _authorized(context, text, scope):
    """Emit one scope entry carrying whatever authorization the text resolves
    to. Unresolvable text is emitted WITHOUT authorization, so the validator
    reports it rather than this builder hiding it."""
    if not isinstance(text, str) or not text:
        return (context, text, scope)
    auth = _auth_for_text(text, scope)
    return (context, text, scope) if auth is None else (context, text, scope, auth)


def build_lithology_validation_scope(
    dispositions: Dict[str, GrFamilyDisposition],
    confidence_by_well: Dict[str, str],
    confidence_rationale_by_well: Dict[str, str],
    mask_results: Sequence[EligibilityMaskResult],
    extra_entries: Optional[Sequence] = None,
):
    """
    Assemble the ACTUAL persisted content that the named-lithology validation
    must inspect, as `(context, text, scope)` triples.

    Increment 6.1 (Finding 3): the manifest's `named_lithology_assigned` flag
    is DERIVED from running the validator over this scope. It is not a
    constant, and it cannot report "false" while a rock name sits in a
    persisted field - injecting one makes the validation, the manifest flag,
    and the completion gate all fail together.

    Everything a well is JUDGED by is scanned as INTERPRETIVE: its confidence
    class and the rationale behind it, its configured use-status, evidence
    class, exclusion reason, curve identity, the human-authored per-well
    note, and every mask name and mask note. Callers may add further entries
    (for example the manifest's own statements) via `extra_entries`.

    Increment 6.1.3 closes a real gap. Three strings that this project WRITES
    INTO PACKAGED EXPORTS had never been inside the validated scope in any
    previous increment - including a `calibration_status` label value literally
    containing `not_a_shale_volume`, persisted to every row of
    gr_proxy_sensitivity_summary.csv. Those fields are now scanned in
    SCOPE_METHOD, which admits them only by exact membership of the closed
    METHOD_STATEMENTS registry. Widening the scope raises
    `n_fields_checked`; that is the intended, disclosed consequence of
    validating content the project already ships.
    """
    entries = []
    # Every persisted field below is emitted WITH its authorization. A field
    # with no authorization is rejected by the validator, so this builder
    # cannot silently introduce an unauthorized string.
    #
    # Increment 6.1.5: authorization is by id. `_auth_for_text` resolves the
    # registered statement (or template binding) whose canonical text this
    # field carries; if no registered statement matches, it returns None and
    # the validator reports the field as unauthorized. It is a LOOKUP, never a
    # judgement about wording.
    for statement_id in sorted(REGISTERED_STATEMENTS):
        st = REGISTERED_STATEMENTS[statement_id]
        if st.scope in (SCOPE_METHOD, SCOPE_EXPLANATORY):
            entries.append((f"{st.scope}_statement.{statement_id}", st.text, st.scope,
                            Authorization(statement_id=statement_id)))
    for well_key in sorted(dispositions):
        d = dispositions[well_key]
        # LABELS - verdicts a well is stamped with. Typed, enumerated values.
        entries.extend([
            (f"{well_key}.use_status", d.use_status, SCOPE_LABEL,
             Authorization(field_kind="use_status")),
            (f"{well_key}.evidence_class", d.evidence_class, SCOPE_LABEL,
             Authorization(field_kind="evidence_class")),
            (f"{well_key}.exclusion_reason", d.exclusion_reason or "", SCOPE_LABEL,
             Authorization(field_kind="exclusion_reason")),
            (f"{well_key}.gr_family_canonical_name", d.gr_family_canonical_name, SCOPE_LABEL,
             Authorization(field_kind="gr_family_canonical_name")),
            (f"{well_key}.gr_family_source_curve_name", d.gr_family_source_curve_name,
             SCOPE_LABEL, Authorization(field_kind="gr_family_source_curve_name")),
        ])
        entries.append(_authorized(f"{well_key}.config_notes", d.notes, SCOPE_INTERPRETIVE))
    for well_key in sorted(confidence_by_well):
        entries.append(
            (f"{well_key}.gr_proxy_confidence_class", confidence_by_well[well_key],
             SCOPE_LABEL, Authorization(field_kind="gr_proxy_confidence_class"))
        )
    for well_key in sorted(confidence_rationale_by_well):
        entries.append(_authorized(
            f"{well_key}.gr_proxy_confidence_rationale",
            confidence_rationale_by_well[well_key], SCOPE_INTERPRETIVE))
    for m in mask_results:
        entries.append((f"{m.well_key}.{m.mask_name}.mask_name", m.mask_name, SCOPE_LABEL,
                        Authorization(field_kind="mask_name")))
        entries.append(_authorized(f"{m.well_key}.{m.mask_name}.notes", m.notes,
                                   SCOPE_INTERPRETIVE))
        entries.append(_authorized(f"{m.well_key}.{m.mask_name}.purpose", m.purpose,
                                   SCOPE_INTERPRETIVE))
    if extra_entries:
        entries.extend(list(extra_entries))
    return entries


def build_petrophysics_manifest(
    frames: Dict[str, WellFrame],
    dispositions: Dict[str, GrFamilyDisposition],
    stats_by_well: Dict[str, GrFamilyQcStats],
    confidence_by_well: Dict[str, str],
    confidence_rationale_by_well: Dict[str, str],
    scenarios_by_well: Dict[str, Sequence[GrEndpointScenario]],
    mask_results: Sequence[EligibilityMaskResult],
    failures: Dict[str, WellFrameAssemblyFailure],
    issues: Sequence[PetrophysicsIssue],
    *,
    config_filename: str,
    config_schema_version: str,
    nct_candidate_thresholds: Sequence[float],
    output_payloads: Optional[Dict[str, object]] = None,
) -> Dict:
    """
    Build the single JSON-serializable Increment 6 manifest.

    Contains only metadata, counts and summary statistics - never a
    per-sample array, and never an absolute path.
    """
    # The manifest's own free-text statement about lithology is itself part of
    # the validated scope - it is explanatory, so it may not attach a rock name
    # to any of this project's wells.
    # Increment 6.1.6 (Finding 5): ONE source of truth. The literal previously
    # duplicated here could diverge from the registered copy while the gate
    # stayed green, because the scope validated the registry entry rather than
    # the value actually persisted. The persisted value IS the registered text.
    _named_lithology_statement = REGISTERED_STATEMENTS["named_lithology_statement"].text
    # Increment 6.1.5: the manifest's own explanatory statement is emitted by
    # the scope builder from REGISTERED_STATEMENTS, with its authorization, so
    # it is no longer injected here as unauthorized extra text.
    _lith_scope = list(build_lithology_validation_scope(
        dispositions, confidence_by_well, confidence_rationale_by_well, mask_results,
    ))
    _lith_violations = validate_no_prohibited_interpretation(_lith_scope)

    # Increment 6.1.6 (Finding 2): authorize the ACTUAL emitted CSV records, not
    # a reconstruction of them. `output_payloads` maps artifact filename ->
    # pre-serialization rows. When it is omitted the coverage block records that
    # honestly rather than implying a check that did not run.
    _emitted_violations = []
    if output_payloads:
        from p2mem.io.output_policy import validate_emitted_records
        _rep = validate_emitted_records(dict(output_payloads), well_keys=set(frames),
                                       expected_artifacts=set(output_payloads))
        _emitted_coverage = _rep.as_dict()
        _emitted_coverage["violations"] = len(_rep.violations)
        _emitted_violations = [
            {"context": f"{v['artifact']}:{v['field']}", "scope": "emitted_output",
             "terms": v.get("linter_terms", []), "reason": v["reason"]}
            for v in _rep.violations]
    else:
        _emitted_coverage = {"status": "not_supplied",
                             "note": "No emitted CSV records were presented to this "
                                     "builder, so no emission-boundary coverage is "
                                     "claimed here. The export gate enforces it."}

    wells_block = {}
    for well_key in sorted(set(frames) | set(dispositions) | set(stats_by_well)):
        fr = frames.get(well_key)
        d = dispositions.get(well_key)
        s = stats_by_well.get(well_key)
        well_masks = [m for m in mask_results if m.well_key == well_key]
        wells_block[well_key] = {
            "source_las_filename": (fr.source_las_filename if fr else (d.source_las_filename if d else "")),
            "source_survey_filename": (fr.source_survey_filename if fr else ""),
            "well_frame_assembled": fr is not None,
            "n_samples": (_i(fr.n_samples) if fr else None),
            "depth_basis_used": (fr.depth_basis_used if fr else ""),
            "interpolation_method": (fr.interpolation_method if fr else ""),
            "depth_map_status": (fr.depth_map_status if fr else ""),
            "n_depth_unmapped": (_i(fr.n_depth_unmapped) if fr else None),
            "n_extrapolated": (_i(fr.n_extrapolated) if fr else None),
            "datum_elevation_m": (_f(fr.datum_elevation_m) if fr else None),
            "well_identity_evidence_status": (fr.well_identity_evidence_status if fr else ""),
            "qc_flags": list(fr.qc_flags) if fr else [],
            "gr_family_canonical_name": (d.gr_family_canonical_name if d else ""),
            "gr_family_source_curve_name": (d.gr_family_source_curve_name if d else ""),
            "use_status": (d.use_status if d else ""),
            "exclusion_reason": (d.exclusion_reason if d and d.exclusion_reason else None),
            "has_approved_formation_tops": (bool(d.has_approved_formation_tops) if d else None),
            "gr_proxy_confidence_class": confidence_by_well.get(well_key, ""),
            "gr_proxy_confidence_rationale": confidence_rationale_by_well.get(well_key, ""),
            "gr_valid_fraction": (_f(s.valid_fraction) if s else None),
            "gr_median_api": (_f(s.median_api) if s else None),
            "gr_min_api": (_f(s.min_api) if s else None),
            "gr_max_api": (_f(s.max_api) if s else None),
            "gr_n_samples_above_seabed": (_i(s.n_samples_above_seabed) if s else None),
            "endpoint_scenarios": [
                {
                    "scenario_name": sc.scenario_name,
                    "gr_low_endpoint_api": _f(sc.gr_low_endpoint_api),
                    "gr_high_endpoint_api": _f(sc.gr_high_endpoint_api),
                    "endpoint_separation_api": _f(sc.endpoint_separation_api),
                    "evidence_class": sc.evidence_class,
                    "calibration_status": sc.calibration_status,
                }
                for sc in sorted(scenarios_by_well.get(well_key, ()), key=lambda x: x.scenario_name)
            ],
            "method_eligibility": [
                {
                    "mask_name": m.mask_name,
                    "scenario_name": m.scenario_name or "",
                    "proxy_threshold": _f(m.proxy_threshold),
                    "n_eligible": _i(m.n_eligible),
                    "eligible_fraction": _f(m.eligible_fraction),
                    "limiting_criterion": m.limiting_criterion,
                    "lithology_dependent": bool(m.lithology_dependent),
                }
                for m in sorted(
                    well_masks,
                    key=lambda x: (
                        x.mask_name,
                        x.scenario_name or "",
                        float("-inf") if x.proxy_threshold is None else float(x.proxy_threshold),
                    ),
                )
            ],
        }

    return {
        "increment": 6,
        "increment_title": (
            "Gamma-Ray QC, Shale-Proxy Sensitivity, Well-Frame Assembly, and "
            "Method-Eligibility Framework"
        ),
        "assurance_tier": TIER_CLASSIFICATION,
        "config_filename": config_filename,
        "config_schema_version": config_schema_version,
        "depth_reference_convention": (
            "MD and TVD are referenced to the well datum (rotary table), increasing downward; "
            "TVDSS_m = TVD_m - DatumElevation_m, with datum elevation referenced to MSL, positive "
            "upward. Identical to the LOCKED Increment 3.1.1 convention - not re-derived here."
        ),
        "nct_candidate_proxy_thresholds": [float(t) for t in nct_candidate_thresholds],
        "n_wells_frame_assembled": len(frames),
        "n_wells_frame_failed": len(failures),
        "n_wells_gr_proxy_permitted": sum(1 for d in dispositions.values() if d.proxy_permitted),
        "n_wells_gr_excluded": sum(1 for d in dispositions.values() if not d.proxy_permitted),
        "total_samples_extrapolated": int(sum(fr.n_extrapolated for fr in frames.values())),
        # DERIVED, never hardcoded (Increment 6.1, Finding 3): this is the
        # result of running the validator over the scope assembled above from
        # real persisted content. If a prohibited term were injected anywhere
        # in that scope, this flag would flip to true and the completion gate
        # would fail.
        "named_lithology_assigned": bool(_lith_violations) or bool(_emitted_violations),
        "lithology_validation": {
            "model": "schema_driven_transactional_authorization_at_emission_boundary",
            "derivation": _LITHOLOGY_DERIVATION,
            # Increment 6.1.6 (§6): the counts below say WHAT they count.
            # `scope_object_*` describes the constructed validation scope - the
            # object Increment 6.1.5 called "every persisted field", which it was
            # not. `emitted_field_coverage` describes the ACTUAL CSV records this
            # run will write; this manifest is itself re-validated by the export
            # gate after serialization, which is why it cannot count itself here.
            "scope_object_fields_checked": len(_lith_scope),
            "scope_object_violations": len(_lith_violations),
            "emitted_field_coverage": _emitted_coverage,
            "violations": [dict(v) for v in _lith_violations] + list(_emitted_violations),
        },
        "named_lithology_statement": _named_lithology_statement,
        "nonlinear_vsh_transforms_implemented": False,
        "nonlinear_vsh_deferral_statement": (
            "No nonlinear Vsh transform (Larionov, Clavier, Stieber, or any other) is implemented. "
            "Each would require a retrieved, verified primary-source method record and a closed "
            "method-register entry; none exists in this project."
        ),
        "methods_not_implemented": [
            "vertical_stress_integration", "hydrostatic_pressure_modelling",
            "normal_compaction_trend_fitting", "eaton_sonic_pore_pressure",
            "eaton_resistivity_pore_pressure", "bowers_pore_pressure",
            "dynamic_elastic_property_calculation", "static_elastic_conversion",
            "rock_strength_correlation", "friction_angle_modelling",
            "shmin_shmax_modelling", "stress_polygon_construction",
            "wellbore_stability_analysis", "mud_weight_recommendation",
            "named_lithology_interpretation", "environmental_gr_correction",
            "gr_rescaling_or_normalization_across_wells", "density_reconstruction_or_extrapolation",
        ],
        "calibration_data_available": {
            "pressure_rft_mdt_dst": False,
            "stress_fit_lot_xlot_dfit": False,
            "independent_vp_vs_calibration": False,
            "statement": (
                "No RFT, MDT, DST, FIT, LOT, XLOT or DFIT data exist for this project. The "
                "supplied Vp/Vs text file is derived from the existing sonic curves and is NOT "
                "independent calibration data. Every quantity in this increment therefore remains "
                "uncalibrated."
            ),
        },
        "wells": wells_block,
        "issues": [
            {"severity": i.severity, "code": i.code, "context": i.context, "message": i.message}
            for i in issues
        ],
        "assembly_failures": [
            {
                "well_key": failures[k].well_key,
                "failure_origin": failures[k].failure_origin,
                "error_type": failures[k].error_type,
                "message": _sanitize_message(
                    failures[k].message, failures[k].las_path, failures[k].survey_path
                ),
            }
            for k in sorted(failures)
        ],
        "limitations": [
            "Tier C - screening-level and uncalibrated. Nothing here is validated against "
            "independent measurement.",
            "Eligibility is a necessary, not sufficient, condition. No method gated by these masks "
            "is implemented, fitted, or validated in this increment.",
            "A sonic-NCT-candidate interval is candidate DATA only. It is not a fitted trend, not a "
            "selected donor interval, and not evidence of normal compaction or overpressure.",
            "GR endpoints are ASSUMED configured percentiles of each well's own samples, never "
            "calibrated and never shared across wells.",
            "Boreas 1 is formally excluded from all GR-derived work under "
            "BOREAS_ECGR_SCALE_UNRESOLVED and is retained for factual raw QC display only. It is "
            "excluded rather than corrected because no calibration evidence exists to support any "
            "correction.",
            "Poseidon North 1 and Proteus 1ST2 have no approved formation tops; their results are "
            "depth-tied and stratigraphically unvalidated.",
            "No named lithology is assigned, and the available data do not support assigning one.",
        ],
    }
