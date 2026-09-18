"""
p2mem.petrophysics - Increment 6 gamma-ray QC, endpoint sensitivity, and
dimensionless screening-proxy calculation.

Scope
-----
This module answers exactly three questions, and refuses to answer any
other:

  1. What does each well's gamma-ray-family curve factually look like?
     (`compute_gr_family_qc_stats` - descriptive statistics only, computed
     for every well including an excluded one.)

  2. Under a configured endpoint rule, what endpoint values does this
     well's own data produce? (`resolve_endpoint_scenarios` - measured
     values from an ASSUMED rule, never a calibration.)

  3. Given those endpoints, what is the dimensionless GR index and the
     linear screening proxy? (`compute_gr_proxy` - retaining clipped and
     unclipped results side by side.)

It does NOT interpret lithology, does not correct or rescale any curve,
does not compute a calibrated shale volume, and does not implement any
nonlinear Vsh transform.

The GR index
------------
    IGR_unclipped = (GR - GR_low_endpoint) / (GR_high_endpoint - GR_low_endpoint)
    IGR_clipped   = clip(IGR_unclipped, 0, 1)

Both are retained. `IGR_unclipped` outside [0, 1] is not an error - it is
the measurable statement that the well's real data ran past the assumed
endpoint bracket, and suppressing it would hide exactly the sensitivity
this increment exists to quantify.

Input validation philosophy
---------------------------
This module's public entry points accept caller-supplied in-memory arrays,
so they validate their own inputs rather than trusting them. The
established project split is honoured exactly (see the LOCKED
`p2mem.io.tops` Increment 5.1 precedent):

  * `TypeError`             - a TYPE-CLASS defect (boolean, string/bytes,
                              complex, or otherwise non-numeric dtype).
  * `PetrophysicsInputError` - a STRUCTURAL or VALUE defect (wrong
                              dimensionality, length mismatch, non-finite
                              or mis-ordered endpoints, identical
                              endpoints, insufficient separation).

An incidental `IndexError`, broadcasting error, or bare comparison
`TypeError` from deep inside a calculation is never an acceptable
substitute for one of these.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import yaml

from p2mem.petrophysics_models import (
    EXCLUSION_REASON_BOREAS_ECGR,
    USE_STATUS_PROXY_ALLOWED,
    USE_STATUS_PROXY_ALLOWED_DEPTH_TIED,
    GR_EXCLUDED_UNRESOLVED_SCALE,
    GR_NOT_AVAILABLE,
    GR_PROXY_HIGH,
    GR_PROXY_INTERMEDIATE,
    GR_PROXY_LOW,
    PROXY_PERMITTED_USE_STATUSES,
    GrEndpointScenario,
    GrFamilyDisposition,
    GrFamilyQcStats,
    GrProxyResult,
    PetrophysicsEligibilityConfig,
    PetrophysicsIssue,
)
from p2mem.wellframe_models import WellFrame, assert_no_lithology_vocabulary

__all__ = [
    "PetrophysicsConfigError",
    "PetrophysicsInputError",
    "PetrophysicsExclusionError",
    "load_petrophysics_eligibility_config",
    "compute_gr_family_qc_stats",
    "resolve_endpoint_scenarios",
    "compute_gr_index",
    "compute_gr_proxy",
    "classify_gr_proxy_confidence",
    "find_contiguous_blocks",
]


class PetrophysicsConfigError(ValueError):
    """Raised when `config/petrophysics_eligibility.yml` is missing,
    malformed, internally inconsistent, or missing a required key. A
    configuration problem is never silently defaulted."""


class PetrophysicsInputError(ValueError):
    """Raised for a structural or value defect in caller-supplied
    in-memory data (wrong dimensionality, length mismatch, non-finite or
    mis-ordered endpoints). Deliberately distinct from `TypeError`, which
    this module reserves for type-class defects."""


class PetrophysicsExclusionError(RuntimeError):
    """Raised when a GR-derived calculation is attempted for a well whose
    configured disposition forbids it (e.g. Boreas 1 under
    `BOREAS_ECGR_SCALE_UNRESOLVED`). This is a hard scientific boundary,
    enforced as an exception rather than a silent no-op so that a caller
    cannot mistake an empty result for a computed one."""


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------

def _reject_ambiguous_dtype(raw: np.ndarray, context: str) -> None:
    """
    Reject boolean, string/bytes, complex, and otherwise non-numeric dtype
    input with `TypeError` before any numeric use.

    Documented local copy of the identical check already established in
    the LOCKED `p2mem.units`, `p2mem.time_depth` (Increment 4.1.1) and
    `p2mem.io.tops` (Increment 5.1) modules. Those modules remain
    unmodified; duplicating ~8 lines here is deliberately preferred over
    editing a locked module to export a private helper.
    """
    kind = raw.dtype.kind
    if kind == "b":
        raise TypeError(f"{context}: boolean input is not accepted as a numeric quantity.")
    if kind in ("U", "S"):
        raise TypeError(f"{context}: string/bytes input is not accepted as a numeric quantity.")
    if kind == "c":
        raise TypeError(f"{context}: complex input is not accepted as a numeric quantity.")
    if kind not in ("i", "u", "f"):
        raise TypeError(f"{context}: unsupported array dtype {raw.dtype!r} for a numeric quantity.")


def _validate_numeric_1d(values, context: str) -> np.ndarray:
    """
    Validate that `values` is a 1-D numeric array and return it as float64.

    Order of checks is deliberate: dtype class first (so a string array
    raises a clear `TypeError` rather than a confusing cast failure), then
    dimensionality. A 0-d, 2-D, or higher-dimensional array is rejected
    with `PetrophysicsInputError` - never silently ravelled, which would
    destroy the sample-position correspondence every mask in this
    increment depends on.
    """
    if isinstance(values, bool):
        raise TypeError(f"{context}: boolean input is not accepted as a numeric array.")
    arr = np.asarray(values)
    _reject_ambiguous_dtype(arr, context)
    if arr.ndim != 1:
        raise PetrophysicsInputError(
            f"{context}: expected a 1-D array, got shape {arr.shape} ({arr.ndim}-D). A "
            f"multidimensional array is never silently flattened - sample positions must stay "
            f"aligned with the well frame's depth arrays."
        )
    return arr.astype(np.float64, copy=True)


def _validate_endpoints(low, high, context: str, min_separation: float) -> Tuple[float, float]:
    """
    Validate an endpoint pair and return it as plain Python floats.

    Rejects (with `TypeError`) boolean, string/bytes and complex values;
    rejects (with `PetrophysicsInputError`) non-finite values, a high
    endpoint that is not strictly greater than the low endpoint - including
    the exactly-identical case, which would otherwise divide by zero - and
    a separation below the configured minimum, which would turn ordinary
    log noise into full-scale IGR swings.
    """
    for label, value in (("low", low), ("high", high)):
        if isinstance(value, bool):
            raise TypeError(f"{context}: {label} endpoint must not be boolean, got {value!r}.")
        if isinstance(value, (str, bytes)):
            raise TypeError(f"{context}: {label} endpoint must not be a string/bytes, got {value!r}.")
        if isinstance(value, complex):
            raise TypeError(f"{context}: {label} endpoint must not be complex, got {value!r}.")
        try:
            float(value)
        except (TypeError, ValueError) as exc:
            raise TypeError(f"{context}: {label} endpoint is not a real numeric scalar: {value!r}.") from exc

    lo = float(low)
    hi = float(high)
    if not np.isfinite(lo) or not np.isfinite(hi):
        raise PetrophysicsInputError(
            f"{context}: endpoints must both be finite; got low={lo!r}, high={hi!r}."
        )
    if hi == lo:
        raise PetrophysicsInputError(
            f"{context}: low and high endpoints are identical ({lo}); the GR-index denominator "
            f"would be exactly zero. An identical endpoint pair is rejected, never nudged."
        )
    if hi < lo:
        raise PetrophysicsInputError(
            f"{context}: high endpoint ({hi}) must be strictly greater than low endpoint ({lo}); "
            f"a reversed pair would invert the proxy's sense without any visible error."
        )
    if (hi - lo) < float(min_separation):
        raise PetrophysicsInputError(
            f"{context}: endpoint separation {hi - lo:.6f} is below the configured minimum "
            f"{float(min_separation):.6f}; such a narrow bracket amplifies ordinary log noise to "
            f"full IGR scale and is rejected."
        )
    return lo, hi


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class _NoDuplicateKeySafeLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate mapping keys, mirroring the
    LOCKED `p2mem.io.deviation` precedent: a silently overwritten
    duplicate key in a human-authored config is a real, hard-to-see
    configuration defect."""


def _construct_mapping_no_duplicates(loader, node, deep: bool = False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise PetrophysicsConfigError(
                f"Duplicate key {key!r} in petrophysics eligibility config at line "
                f"{key_node.start_mark.line + 1}; a duplicated key silently overwrites the first "
                f"value and is rejected."
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_NoDuplicateKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping_no_duplicates
)

_REQUIRED_TOP_KEYS = (
    "schema_version", "increment", "assurance_tier", "policy",
    "endpoint_scenarios", "wells", "gr_proxy_confidence", "method_eligibility",
)
_REQUIRED_WELL_KEYS = (
    "source_las_filename", "gr_family_canonical_name", "gr_family_source_curve_name",
    "use_status", "exclusion_reason", "evidence_class", "has_approved_formation_tops",
)
_REQUIRED_POLICY_KEYS = (
    "endpoint_estimation_method", "cross_well_shared_endpoints_allowed",
    "endpoint_sample_basis", "clipping_policy", "clip_lower", "clip_upper",
    "min_endpoint_separation_api", "shale_proxy_transform",
    "nonlinear_vsh_transforms_enabled", "contiguity",
    "nct_candidate_proxy_thresholds", "physical_bounds",
)


def load_petrophysics_eligibility_config(yaml_path: str) -> PetrophysicsEligibilityConfig:
    """
    Load and validate `config/petrophysics_eligibility.yml`.

    Every required key is checked here so a typo fails at load time rather
    than deep inside a calculation. Two policy invariants are enforced as
    hard errors because violating either would silently cross an Increment
    6 scientific boundary:

      * `cross_well_shared_endpoints_allowed` must be false - a shared
        cross-well endpoint pair would assert a tool equivalence no
        evidence supports;
      * `nonlinear_vsh_transforms_enabled` must be false - no nonlinear
        Vsh transform has a closed primary-source method record in this
        project.
    """
    path = Path(yaml_path)
    if not path.is_file():
        raise PetrophysicsConfigError(f"Petrophysics eligibility config not found: {yaml_path!r}.")
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.load(fh, Loader=_NoDuplicateKeySafeLoader)
    if not isinstance(raw, dict):
        raise PetrophysicsConfigError(f"{path.name}: top level must be a mapping.")

    for key in _REQUIRED_TOP_KEYS:
        if key not in raw:
            raise PetrophysicsConfigError(f"{path.name}: required top-level key {key!r} is missing.")

    policy = raw["policy"]
    if not isinstance(policy, dict):
        raise PetrophysicsConfigError(f"{path.name}: 'policy' must be a mapping.")
    for key in _REQUIRED_POLICY_KEYS:
        if key not in policy:
            raise PetrophysicsConfigError(f"{path.name}: required policy key {key!r} is missing.")

    if bool(policy["cross_well_shared_endpoints_allowed"]):
        raise PetrophysicsConfigError(
            f"{path.name}: cross_well_shared_endpoints_allowed must be false. A single universal "
            f"cross-well endpoint pair would assert an equivalence between four differently named "
            f"GR-family tools that no calibration evidence in this project supports."
        )
    if bool(policy["nonlinear_vsh_transforms_enabled"]):
        raise PetrophysicsConfigError(
            f"{path.name}: nonlinear_vsh_transforms_enabled must be false in Increment 6. A "
            f"nonlinear Vsh transform requires a retrieved, verified primary-source method record "
            f"and a closed method-register entry; none exists in this project."
        )

    scenarios = raw["endpoint_scenarios"]
    if not isinstance(scenarios, list) or len(scenarios) < 3:
        raise PetrophysicsConfigError(
            f"{path.name}: 'endpoint_scenarios' must be a list of at least three scenarios "
            f"(low/base/high endpoint sensitivity is mandatory in Increment 6)."
        )
    seen_names = set()
    for sc in scenarios:
        for key in ("scenario_name", "low_percentile", "high_percentile", "description"):
            if key not in sc:
                raise PetrophysicsConfigError(
                    f"{path.name}: endpoint scenario is missing required key {key!r}: {sc!r}."
                )
        name = str(sc["scenario_name"])
        if name in seen_names:
            raise PetrophysicsConfigError(f"{path.name}: duplicate scenario_name {name!r}.")
        seen_names.add(name)
        lo_p = float(sc["low_percentile"])
        hi_p = float(sc["high_percentile"])
        if not (0.0 <= lo_p < hi_p <= 100.0):
            raise PetrophysicsConfigError(
                f"{path.name}: scenario {name!r} requires 0 <= low_percentile < high_percentile "
                f"<= 100; got low={lo_p}, high={hi_p}."
            )

    me = raw["method_eligibility"]
    if not isinstance(me, dict):
        raise PetrophysicsConfigError(f"{path.name}: 'method_eligibility' must be a mapping.")
    for required_mask in (
        "eligible_density_for_sv", "eligible_dynamic_elastic", "eligible_sonic_nct_candidate",
    ):
        if required_mask not in me:
            raise PetrophysicsConfigError(
                f"{path.name}: required method_eligibility entry {required_mask!r} is missing. "
                f"All three Increment 6 masks must be declared and described."
            )
        if "purpose" not in me[required_mask]:
            raise PetrophysicsConfigError(
                f"{path.name}: method_eligibility entry {required_mask!r} is missing 'purpose'; "
                f"an undocumented eligibility mask is not auditable."
            )

    wells_raw = raw["wells"]
    if not isinstance(wells_raw, dict) or not wells_raw:
        raise PetrophysicsConfigError(f"{path.name}: 'wells' must be a non-empty mapping.")
    wells: Dict[str, GrFamilyDisposition] = {}
    for well_key, spec in wells_raw.items():
        if not isinstance(spec, dict):
            raise PetrophysicsConfigError(f"{path.name}: well {well_key!r} entry must be a mapping.")
        for key in _REQUIRED_WELL_KEYS:
            if key not in spec:
                raise PetrophysicsConfigError(
                    f"{path.name}: well {well_key!r} is missing required key {key!r}."
                )
        use_status = str(spec["use_status"])
        has_tops = bool(spec["has_approved_formation_tops"])
        # Increment 6.1 (Finding 2) invariant: a proxy-permitted well with NO
        # approved formation tops must carry the DEPTH-TIED status. The plain
        # `screening_proxy_allowed` status asserts that results can be tied to
        # approved stratigraphy; for a well with no tops that is false, and the
        # contradiction must fail loudly at config-load time rather than
        # surviving as a machine-readable claim that contradicts the prose.
        if use_status == USE_STATUS_PROXY_ALLOWED and not has_tops:
            raise PetrophysicsConfigError(
                f"{path.name}: well {well_key!r} declares use_status="
                f"{USE_STATUS_PROXY_ALLOWED!r} but has_approved_formation_tops=false. A "
                f"proxy-permitted well with no approved formation tops must use "
                f"{USE_STATUS_PROXY_ALLOWED_DEPTH_TIED!r}, because its results cannot be tied "
                f"to approved stratigraphy. Fix the config; this contradiction is never "
                f"silently accepted."
            )
        # The converse is also checked: claiming depth-tied status for a well
        # that DOES have approved tops understates what the data support and is
        # equally a config/reality mismatch.
        if use_status == USE_STATUS_PROXY_ALLOWED_DEPTH_TIED and has_tops:
            raise PetrophysicsConfigError(
                f"{path.name}: well {well_key!r} declares use_status="
                f"{USE_STATUS_PROXY_ALLOWED_DEPTH_TIED!r} but has_approved_formation_tops=true. "
                f"The depth-tied status is reserved for wells with NO approved formation tops; "
                f"a well that has them must use {USE_STATUS_PROXY_ALLOWED!r}."
            )

        wells[str(well_key)] = GrFamilyDisposition(
            well_key=str(well_key),
            source_las_filename=str(spec["source_las_filename"]),
            gr_family_canonical_name=str(spec["gr_family_canonical_name"]),
            gr_family_source_curve_name=str(spec["gr_family_source_curve_name"]),
            use_status=str(spec["use_status"]),
            exclusion_reason=(None if spec["exclusion_reason"] is None else str(spec["exclusion_reason"])),
            evidence_class=str(spec["evidence_class"]),
            has_approved_formation_tops=bool(spec["has_approved_formation_tops"]),
            notes=str(spec.get("notes", "") or ""),
        )

    return PetrophysicsEligibilityConfig(
        schema_version=str(raw["schema_version"]),
        increment=int(raw["increment"]),
        assurance_tier=str(raw["assurance_tier"]),
        policy=policy,
        endpoint_scenarios=tuple(scenarios),
        wells=wells,
        gr_proxy_confidence=raw["gr_proxy_confidence"],
        method_eligibility=raw["method_eligibility"],
        source_filename=path.name,
    )


# ---------------------------------------------------------------------------
# Contiguous-block detection (shared by QC stats and eligibility intervals)
# ---------------------------------------------------------------------------

def find_contiguous_blocks(
    mask: np.ndarray,
    depth_m: Optional[np.ndarray] = None,
    *,
    max_gap_samples: int = 0,
    max_gap_depth_m: float = 0.0,
) -> List[Tuple[int, int]]:
    """
    Return `[(start_index, end_index_inclusive), ...]` for runs of True in
    `mask`, optionally bridging short interruptions.

    A gap is bridged into the surrounding block ONLY when BOTH conditions
    hold:
      * its length is <= `max_gap_samples`, AND
      * (when `depth_m` is given) the physical depth span across the gap
        is <= `max_gap_depth_m`.

    Requiring both is the whole point: sample-count continuity and
    physical-depth continuity are different things, and a 2-sample gap
    that spans a 400 m depth jump is not a continuous interval. With the
    defaults (`max_gap_samples=0`) nothing is ever bridged.

    A missing interval is never silently bridged beyond these explicit,
    configured, tested tolerances, and nothing here extrapolates: bridged
    samples remain False in the caller's own mask - only the reported
    BLOCK spans them, and the caller can always recover the true valid
    count from the mask itself.
    """
    m = np.asarray(mask, dtype=bool)
    if m.ndim != 1:
        raise PetrophysicsInputError(
            f"find_contiguous_blocks: mask must be 1-D, got shape {m.shape}."
        )
    if depth_m is not None:
        d = np.asarray(depth_m, dtype=np.float64)
        if d.shape != m.shape:
            raise PetrophysicsInputError(
                f"find_contiguous_blocks: depth array shape {d.shape} does not match mask shape "
                f"{m.shape}."
            )
    else:
        d = None

    if not m.any():
        return []

    idx = np.flatnonzero(m)
    blocks: List[Tuple[int, int]] = []
    start = int(idx[0])
    prev = int(idx[0])
    for i in idx[1:]:
        i = int(i)
        gap = i - prev - 1
        bridge = False
        if 0 < gap <= int(max_gap_samples):
            if d is None:
                bridge = True
            else:
                span = abs(float(d[i]) - float(d[prev]))
                bridge = np.isfinite(span) and span <= float(max_gap_depth_m)
        if gap == 0 or bridge:
            prev = i
            continue
        blocks.append((start, prev))
        start = i
        prev = i
    blocks.append((start, prev))
    return blocks


# ---------------------------------------------------------------------------
# GR-family QC statistics
# ---------------------------------------------------------------------------

def compute_gr_family_qc_stats(
    frame: WellFrame,
    disposition: GrFamilyDisposition,
    *,
    seabed_mdrt_m: Optional[float] = None,
) -> GrFamilyQcStats:
    """
    Compute purely factual statistics for one well's GR-family curve.

    Computed for EVERY well regardless of `use_status`: factual QC
    reporting and availability disclosure are exactly what an excluded
    well remains available for, and the numbers that justify an exclusion
    must themselves be measured and published, not asserted.

    `seabed_mdrt_m`, when supplied, must come from the LOCKED Increment 5
    survey-corrected formation-top output. When it is None,
    `n_samples_above_seabed` is None and `seabed_basis` records that the
    quantity is not determinable from approved data - never 0, which would
    falsely assert that no such samples exist.
    """
    canonical = disposition.gr_family_canonical_name
    slot = frame.curve(canonical)
    if slot is None:
        return GrFamilyQcStats(
            well_key=frame.well_key,
            gr_family_canonical_name=canonical,
            gr_family_source_curve_name=disposition.gr_family_source_curve_name,
            source_las_filename=frame.source_las_filename,
            unit="API",
            n_samples=frame.n_samples,
            valid_count=0, valid_fraction=0.0,
            min_api=None, max_api=None, median_api=None,
            p01_api=None, p05_api=None, p10_api=None, p25_api=None, p50_api=None,
            p75_api=None, p90_api=None, p95_api=None, p99_api=None,
            dynamic_range_p05_p95_api=None,
            n_negative_samples=0, n_zero_samples=0,
            n_samples_above_seabed=None,
            seabed_basis="not_applicable_gr_family_curve_absent",
            n_valid_blocks=0, longest_valid_block_samples=0,
            longest_missing_block_samples=frame.n_samples,
            longest_missing_block_md_start_m=None, longest_missing_block_md_end_m=None,
            statistics_basis=(
                f"GR-family curve {canonical!r} is not present in this well's contract-resolved "
                f"curves; reported as a factual data gap, never substituted from another well."
            ),
        )

    gr = np.asarray(slot.values, dtype=np.float64)
    md = np.asarray(frame.MD_m, dtype=np.float64)
    valid = np.asarray(slot.valid_mask, dtype=bool)
    n = int(gr.size)
    vc = int(np.count_nonzero(valid))

    if vc:
        v = gr[valid]
        pcts = np.percentile(v, [1, 5, 10, 25, 50, 75, 90, 95, 99])
        p01, p05, p10, p25, p50, p75, p90, p95, p99 = (float(x) for x in pcts)
        vmin, vmax, vmed = float(np.min(v)), float(np.max(v)), float(np.median(v))
        dyn = p95 - p05
        n_neg = int(np.count_nonzero(v < 0.0))
        n_zero = int(np.count_nonzero(v == 0.0))
    else:
        p01 = p05 = p10 = p25 = p50 = p75 = p90 = p95 = p99 = None
        vmin = vmax = vmed = None
        dyn = None
        n_neg = n_zero = 0

    if seabed_mdrt_m is not None and np.isfinite(float(seabed_mdrt_m)):
        above = int(np.count_nonzero(md < float(seabed_mdrt_m)))
        basis = (
            f"Counted where canonical LAS MD_m < {float(seabed_mdrt_m):.4f} m MDRT, the seabed "
            f"marker's reconciled MDRT from the LOCKED Increment 5 survey-corrected output."
        )
    else:
        above = None
        basis = (
            "Not determinable: this well has no approved formation-top file, so no seabed marker "
            "exists in the locked Increment 5 output. Reported as None (unknown), never as 0."
        )

    valid_blocks = find_contiguous_blocks(valid)
    longest_valid = max((e - s + 1 for s, e in valid_blocks), default=0)
    missing_blocks = find_contiguous_blocks(~valid)
    if missing_blocks:
        s, e = max(missing_blocks, key=lambda b: b[1] - b[0])
        longest_missing = e - s + 1
        miss_start_md: Optional[float] = float(md[s])
        miss_end_md: Optional[float] = float(md[e])
    else:
        longest_missing = 0
        miss_start_md = miss_end_md = None

    return GrFamilyQcStats(
        well_key=frame.well_key,
        gr_family_canonical_name=canonical,
        gr_family_source_curve_name=slot.source_curve_name,
        source_las_filename=frame.source_las_filename,
        unit=slot.canonical_unit or "API",
        n_samples=n,
        valid_count=vc,
        valid_fraction=(vc / n) if n else 0.0,
        min_api=vmin, max_api=vmax, median_api=vmed,
        p01_api=p01, p05_api=p05, p10_api=p10, p25_api=p25, p50_api=p50,
        p75_api=p75, p90_api=p90, p95_api=p95, p99_api=p99,
        dynamic_range_p05_p95_api=dyn,
        n_negative_samples=n_neg, n_zero_samples=n_zero,
        n_samples_above_seabed=above, seabed_basis=basis,
        n_valid_blocks=len(valid_blocks),
        longest_valid_block_samples=int(longest_valid),
        longest_missing_block_samples=int(longest_missing),
        longest_missing_block_md_start_m=miss_start_md,
        longest_missing_block_md_end_m=miss_end_md,
        statistics_basis=(
            "Descriptive statistics over finite samples of this well's OWN GR-family curve, in its "
            "own recorded API units. No environmental correction, rescaling, normalization, or "
            "cross-well transfer of any kind has been applied. These numbers describe the curve as "
            "recorded and imply no lithology."
        ),
    )


# ---------------------------------------------------------------------------
# Endpoint scenarios
# ---------------------------------------------------------------------------

def resolve_endpoint_scenarios(
    frame: WellFrame,
    disposition: GrFamilyDisposition,
    config: PetrophysicsEligibilityConfig,
) -> Tuple[GrEndpointScenario, ...]:
    """
    Compute the MEASURED endpoint values each configured scenario produces
    for THIS well, from THIS well's own valid, depth-mapped GR samples.

    Raises
    ------
    PetrophysicsExclusionError
        If this well's configured `use_status` forbids GR-derived
        calculation. An excluded well gets no endpoints at all - not even
        "for reference" - because a published endpoint pair is exactly the
        artefact someone would later be tempted to rescale the curve with.
    PetrophysicsInputError
        If the well has no valid, depth-mapped GR samples to estimate from,
        or if a scenario's rule produces a degenerate endpoint pair.
    """
    if not disposition.proxy_permitted:
        raise PetrophysicsExclusionError(
            f"{frame.well_key}: GR-derived calculation is forbidden for this well "
            f"(use_status={disposition.use_status!r}, exclusion_reason="
            f"{disposition.exclusion_reason!r}). No endpoint, index, proxy, flag, "
            f"lithology-dependent mask, or NCT-donor status may be computed for it."
        )

    slot = frame.curve(disposition.gr_family_canonical_name)
    if slot is None:
        raise PetrophysicsInputError(
            f"{frame.well_key}: GR-family curve {disposition.gr_family_canonical_name!r} is absent; "
            f"endpoints cannot be estimated and are never borrowed from another well."
        )

    gr = np.asarray(slot.values, dtype=np.float64)
    usable = np.asarray(slot.valid_mask, dtype=bool) & np.asarray(frame.depth_valid_mask, dtype=bool)
    n_used = int(np.count_nonzero(usable))
    if n_used == 0:
        raise PetrophysicsInputError(
            f"{frame.well_key}: no finite, depth-mapped GR-family sample exists; endpoints cannot "
            f"be estimated from zero valid coverage."
        )

    v = gr[usable]
    min_sep = float(config.policy["min_endpoint_separation_api"])
    basis = str(config.policy["endpoint_sample_basis"])

    out: List[GrEndpointScenario] = []
    for sc in config.endpoint_scenarios:
        name = str(sc["scenario_name"])
        lo_p = float(sc["low_percentile"])
        hi_p = float(sc["high_percentile"])
        lo_raw = float(np.percentile(v, lo_p))
        hi_raw = float(np.percentile(v, hi_p))
        lo, hi = _validate_endpoints(
            lo_raw, hi_raw,
            f"{frame.well_key}/{name} endpoints (p{lo_p:g}/p{hi_p:g} of "
            f"{disposition.gr_family_canonical_name})",
            min_sep,
        )
        out.append(
            GrEndpointScenario(
                well_key=frame.well_key,
                scenario_name=name,
                low_percentile=lo_p,
                high_percentile=hi_p,
                gr_low_endpoint_api=lo,
                gr_high_endpoint_api=hi,
                endpoint_separation_api=hi - lo,
                n_samples_used_for_endpoints=n_used,
                endpoint_sample_basis=basis,
                description=str(sc["description"]).strip(),
            )
        )
    return tuple(out)


# ---------------------------------------------------------------------------
# GR index and screening proxy
# ---------------------------------------------------------------------------

def compute_gr_index(
    gr_values,
    gr_low_endpoint,
    gr_high_endpoint,
    *,
    context: str = "compute_gr_index",
    min_endpoint_separation_api: float = 1.0,
    valid_mask=None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute `(igr_unclipped, igr_clipped, valid_mask)` from a GR array and
    an explicit endpoint pair.

        IGR_unclipped = (GR - low) / (high - low)
        IGR_clipped   = clip(IGR_unclipped, 0, 1)

    Both arrays are full-length and aligned with `gr_values`. A sample
    that is NaN on input stays NaN in both outputs and False in the
    returned mask - a NaN is never coerced to 0, to an endpoint, or to a
    neighbouring value. An infinite input sample is explicitly INVALIDATED
    (masked out and set to NaN) rather than propagating a signed infinity
    through the division: an infinite gamma-ray reading is not a
    measurement, and silently normalizing it would produce a
    plus/minus-infinity IGR that clipping would then quietly turn into a
    clean-looking 0 or 1.

    `valid_mask`, when supplied, is ANDed with the finiteness mask - used
    by callers to additionally require a mapped depth.
    """
    arr = _validate_numeric_1d(gr_values, f"{context}: gr_values")
    lo, hi = _validate_endpoints(
        gr_low_endpoint, gr_high_endpoint, context, min_endpoint_separation_api
    )

    finite = np.isfinite(arr)
    if valid_mask is not None:
        extra = np.asarray(valid_mask)
        if extra.dtype != np.bool_:
            raise TypeError(
                f"{context}: valid_mask must be a boolean array, got dtype {extra.dtype!r}."
            )
        if extra.shape != arr.shape:
            raise PetrophysicsInputError(
                f"{context}: valid_mask shape {extra.shape} does not match gr_values shape "
                f"{arr.shape}; a length mismatch is never reconciled by truncation or padding."
            )
        finite = finite & extra

    igr_unclipped = np.full(arr.shape, np.nan, dtype=np.float64)
    np.divide(arr - lo, hi - lo, out=igr_unclipped, where=finite)
    igr_clipped = np.full(arr.shape, np.nan, dtype=np.float64)
    np.clip(igr_unclipped, 0.0, 1.0, out=igr_clipped, where=finite)
    # `np.clip(..., where=)` leaves untouched positions at their `out`
    # initial value (NaN), which is exactly what is wanted; re-assert it
    # explicitly so the invariant does not depend on that subtlety.
    igr_clipped[~finite] = np.nan
    igr_unclipped[~finite] = np.nan
    return igr_unclipped, igr_clipped, finite


def compute_gr_proxy(
    frame: WellFrame,
    disposition: GrFamilyDisposition,
    scenario: GrEndpointScenario,
    config: PetrophysicsEligibilityConfig,
) -> GrProxyResult:
    """
    Compute one well's GR index and linear screening proxy under ONE
    endpoint scenario.

    The proxy is the LINEAR IDENTITY of the clipped index - the only
    transform Increment 6 permits. It is named
    `VSH_GR_linear_proxy_frac` and is documented, in every field and
    every export, as an uncalibrated screening proxy that is NOT a shale
    volume and NOT a lithology.

    Raises `PetrophysicsExclusionError` for a well whose disposition
    forbids GR-derived calculation.
    """
    if not disposition.proxy_permitted:
        raise PetrophysicsExclusionError(
            f"{frame.well_key}: GR-derived screening proxy is forbidden for this well "
            f"(use_status={disposition.use_status!r}, exclusion_reason="
            f"{disposition.exclusion_reason!r})."
        )
    if scenario.well_key != frame.well_key:
        raise PetrophysicsInputError(
            f"Endpoint scenario belongs to well {scenario.well_key!r} but was supplied for well "
            f"{frame.well_key!r}; endpoints are per-well and are never transferred between wells."
        )

    slot = frame.curve(disposition.gr_family_canonical_name)
    if slot is None:
        raise PetrophysicsInputError(
            f"{frame.well_key}: GR-family curve {disposition.gr_family_canonical_name!r} is absent."
        )

    igr_unclipped, igr_clipped, valid = compute_gr_index(
        np.asarray(slot.values, dtype=np.float64),
        scenario.gr_low_endpoint_api,
        scenario.gr_high_endpoint_api,
        context=f"{frame.well_key}/{scenario.scenario_name}",
        min_endpoint_separation_api=float(config.policy["min_endpoint_separation_api"]),
        valid_mask=np.asarray(frame.depth_valid_mask, dtype=bool),
    )

    proxy = igr_clipped.copy()  # linear identity transform, by policy
    n_valid = int(np.count_nonzero(valid))
    n_low = int(np.count_nonzero(valid & (igr_unclipped < 0.0)))
    n_high = int(np.count_nonzero(valid & (igr_unclipped > 1.0)))

    if n_valid:
        pv = proxy[valid]
        med: Optional[float] = float(np.median(pv))
        q25: Optional[float] = float(np.percentile(pv, 25))
        q75: Optional[float] = float(np.percentile(pv, 75))
    else:
        med = q25 = q75 = None

    return GrProxyResult(
        well_key=frame.well_key,
        scenario_name=scenario.scenario_name,
        gr_family_canonical_name=disposition.gr_family_canonical_name,
        gr_low_endpoint_api=scenario.gr_low_endpoint_api,
        gr_high_endpoint_api=scenario.gr_high_endpoint_api,
        igr_unclipped_frac=igr_unclipped,
        igr_clipped_frac=igr_clipped,
        VSH_GR_linear_proxy_frac=proxy,
        valid_mask=valid,
        n_valid=n_valid,
        n_clipped_low=n_low,
        n_clipped_high=n_high,
        clipped_fraction=((n_low + n_high) / n_valid) if n_valid else 0.0,
        proxy_median=med, proxy_p25=q25, proxy_p75=q75,
    )


# ---------------------------------------------------------------------------
# Data/proxy confidence classification
# ---------------------------------------------------------------------------

def classify_gr_proxy_confidence(
    stats: GrFamilyQcStats,
    disposition: GrFamilyDisposition,
    proxy_results: Sequence[GrProxyResult],
    config: PetrophysicsEligibilityConfig,
) -> Tuple[str, str]:
    """
    Return `(confidence_class, rationale)` describing confidence in the
    DATA and the PROXY - never a lithology.

    The returned class is asserted against the prohibited named-lithology
    vocabulary before it is returned, so a rock name can never leave this
    function even if the config were edited to introduce one.

    Ordering of the checks matters: an explicitly excluded well is
    classified as excluded regardless of how good its coverage statistics
    look, because the exclusion is about an unresolved SCALE anomaly that
    good coverage does nothing to resolve.
    """
    if not disposition.proxy_permitted:
        cls = GR_EXCLUDED_UNRESOLVED_SCALE
        rationale = (
            f"Formally excluded from every GR-derived calculation "
            f"(exclusion_reason={disposition.exclusion_reason!r}). The curve remains available for "
            f"factual raw QC display and availability reporting only. Good coverage does not "
            f"resolve an unresolved scale/acquisition anomaly, so coverage statistics do not "
            f"override this classification."
        )
    elif stats.valid_count == 0 or stats.dynamic_range_p05_p95_api is None:
        cls = GR_NOT_AVAILABLE
        rationale = "No finite GR-family sample is available for this well; reported as a factual data gap."
    else:
        rules = config.gr_proxy_confidence["rules"]
        medians = [p.proxy_median for p in proxy_results if p.proxy_median is not None]
        spread = (max(medians) - min(medians)) if len(medians) >= 2 else 0.0
        vf = float(stats.valid_fraction)
        dr = float(stats.dynamic_range_p05_p95_api)
        hi = rules["high"]
        mid = rules["intermediate"]
        if (
            vf >= float(hi["min_valid_fraction"])
            and dr >= float(hi["min_dynamic_range_api"])
            and spread <= float(hi["max_proxy_median_spread_across_scenarios"])
        ):
            cls = GR_PROXY_HIGH
        elif (
            vf >= float(mid["min_valid_fraction"])
            and dr >= float(mid["min_dynamic_range_api"])
            and spread <= float(mid["max_proxy_median_spread_across_scenarios"])
        ):
            cls = GR_PROXY_INTERMEDIATE
        else:
            cls = GR_PROXY_LOW
        rationale = (
            f"valid_fraction={vf:.4f}, dynamic_range_p05_p95={dr:.3f} API, "
            f"proxy_median_spread_across_{len(medians)}_scenarios={spread:.4f}. Describes "
            f"confidence in the DATA and the SCREENING PROXY only; asserts no lithology and no "
            f"calibration."
        )

    assert_no_lithology_vocabulary(cls, f"{stats.well_key}: gr_proxy_confidence class")
    return cls, rationale
