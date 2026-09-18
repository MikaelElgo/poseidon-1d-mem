"""
p2mem.method_eligibility - Increment 6 method-eligibility masks and
contiguous-interval registers.

ELIGIBILITY IS NOT VALIDITY
---------------------------
Every mask in this module answers one narrow question:

    "Is this sample technically ADMISSIBLE as INPUT to a later method?"

It never answers any of these:

    "Is that method appropriate here?"
    "Would its result be defensible?"
    "Is this interval normally compacted?"
    "What rock is this?"

Eligibility is a NECESSARY, not a SUFFICIENT, condition. A sample can be
eligible for a density-based overburden integration and that integration
can still be indefensible - for instance because the density log starts
hundreds of metres below the seabed, so no amount of per-sample
eligibility supplies the missing shallow section. This distinction is the
reason these masks are computed in a separate increment from the methods
they gate, and it is restated in every exported table.

The three masks
---------------
1. `eligible_density_for_sv`
   Finite, physically plausible RHOB at a mapped depth. Increment 6 does
   NOT fill missing density and does NOT compute Sv.

2. `eligible_dynamic_elastic`
   Finite, positive, physically plausible VP, VS and RHOB at a mapped
   depth, with VP > VS and a Vp/Vs ratio that passes the CONFIGURED
   NON-NEGATIVE-POISSON-RATIO APPLICABILITY SCREEN - an INCLUSIVE
   `Vp/Vs >= sqrt(2)` bound, together with a configured plausibility
   maximum. That screen is a conservative PROJECT POLICY about what to
   admit to a later dynamic-elastic calculation; it is NOT a
   physical-possibility test and NOT a boundary of the mathematical
   Poisson domain. `Vp/Vs = sqrt(2)` gives a Poisson's ratio of exactly
   zero and is ACCEPTED; ratios below it are excluded by policy and are
   diagnosed BY REGIME (non-positive bulk modulus versus positive bulk
   modulus with negative Poisson's ratio), never aggregated under a
   single "non-physical" label. See `compute_dynamic_elastic_eligibility`
   for the full derivation. Increment 6 computes NO elastic property -
   not Young's modulus, not Poisson's ratio, not bulk or shear modulus.
   This is an input-admissibility mask only.

3. `eligible_sonic_nct_candidate`
   CANDIDATE DATA for a later sonic normal-compaction-trend analysis:
   an approved GR-family disposition, finite VP, a finite screening
   proxy at or above a scenario-specific threshold, and a mapped depth.
   It does NOT fit a trend, does NOT select a donor interval, does NOT
   claim normal compaction, and does NOT claim overpressure. A candidate
   mask is emphatically NOT proof that an interval is normally compacted,
   and it names no lithology.

Both mask 1 and mask 2 are lithology-independent and are therefore
computed for EVERY well, including a GR-excluded one - excluding Boreas 1
from GR-derived work says nothing about whether its density or sonic
samples are finite. Mask 3 is lithology-dependent (it consumes the GR
screening proxy) and is therefore NEVER computed for a GR-excluded well.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import math

import numpy as np

from p2mem.petrophysics import PetrophysicsInputError, find_contiguous_blocks
from p2mem.petrophysics_models import (
    GrFamilyDisposition,
    GrProxyResult,
    PetrophysicsEligibilityConfig,
)
from p2mem.wellframe_models import WellFrame

__all__ = [
    "MASK_DENSITY_FOR_SV",
    "MASK_DYNAMIC_ELASTIC",
    "MASK_SONIC_NCT_CANDIDATE",
    "VALID_MASK_NAMES",
    "EligibilityMaskResult",
    "EligibilityInterval",
    "compute_density_eligibility",
    "compute_dynamic_elastic_eligibility",
    "compute_sonic_nct_candidate_eligibility",
    "build_eligibility_intervals",
    "CONTIGUITY_POLICY_CONFIGURED",
    "CONTIGUITY_POLICY_STRICT",
    "VALID_CONTIGUITY_POLICIES",
]

MASK_DENSITY_FOR_SV = "eligible_density_for_sv"
MASK_DYNAMIC_ELASTIC = "eligible_dynamic_elastic"
MASK_SONIC_NCT_CANDIDATE = "eligible_sonic_nct_candidate"

VALID_MASK_NAMES: Tuple[str, ...] = (
    MASK_DENSITY_FOR_SV,
    MASK_DYNAMIC_ELASTIC,
    MASK_SONIC_NCT_CANDIDATE,
)


class EligibilityMaskResult:
    """
    One well's boolean eligibility mask for one method, plus the per-
    criterion counts that explain it.

    `criteria_counts` records how many samples PASSED each individual
    criterion, so a reader can see which requirement actually limited the
    result rather than only the final total. `limiting_criterion` names
    the single most restrictive one. Neither is an interpretation - both
    are counts.
    """

    __slots__ = (
        "well_key", "mask_name", "scenario_name", "proxy_threshold", "mask",
        "n_samples", "n_eligible", "eligible_fraction", "criteria_counts",
        "diagnostic_counts", "limiting_criterion", "lithology_dependent",
        "purpose", "notes",
    )

    def __init__(
        self,
        well_key: str,
        mask_name: str,
        mask: np.ndarray,
        criteria_counts: Dict[str, int],
        *,
        diagnostic_counts: Optional[Dict[str, int]] = None,
        scenario_name: Optional[str] = None,
        proxy_threshold: Optional[float] = None,
        lithology_dependent: bool = False,
        purpose: str = "",
        notes: str = "",
    ) -> None:
        if mask_name not in VALID_MASK_NAMES:
            raise ValueError(f"Unknown mask_name {mask_name!r}; expected one of {VALID_MASK_NAMES}.")
        m = np.asarray(mask, dtype=bool)
        if m.ndim != 1:
            raise PetrophysicsInputError(f"{well_key}/{mask_name}: mask must be 1-D, got {m.shape}.")
        self.well_key = well_key
        self.mask_name = mask_name
        self.scenario_name = scenario_name
        self.proxy_threshold = proxy_threshold
        self.mask = m
        self.n_samples = int(m.size)
        self.n_eligible = int(np.count_nonzero(m))
        self.eligible_fraction = (self.n_eligible / self.n_samples) if self.n_samples else 0.0
        self.criteria_counts = dict(criteria_counts)
        # Reported alongside, but deliberately EXCLUDED from the
        # limiting-criterion comparison: these are conditional counts whose
        # magnitude is bounded by another criterion, so comparing them
        # directly against unconditional pass counts would misattribute the
        # cause of a low eligible fraction.
        self.diagnostic_counts = dict(diagnostic_counts or {})
        self.limiting_criterion = (
            min(criteria_counts, key=lambda k: criteria_counts[k]) if criteria_counts else ""
        )
        self.lithology_dependent = bool(lithology_dependent)
        self.purpose = purpose
        self.notes = notes

    def __repr__(self) -> str:  # pragma: no cover - debug convenience only
        return (
            f"EligibilityMaskResult({self.well_key!r}, {self.mask_name!r}, "
            f"scenario={self.scenario_name!r}, n_eligible={self.n_eligible}/{self.n_samples})"
        )


class EligibilityInterval:
    """
    One contiguous block of eligible samples, reported on all three depth
    references (MD, TVD, TVDSS) so a reader never has to guess which basis
    a thickness refers to.

    Increment 6.1 (Finding 4): thickness is reported in THREE explicitly
    named forms, because the single unqualified "thickness" of Increment 6
    conflated them:

      * `gross_thickness_*_m` - the block's ENDPOINT SPAN, first sample to
        last. Under the configured contiguity policy this span may CONTAIN
        explicitly bridged ineligible samples, so it is a gross figure and
        is named as one. It is never called simply "eligible thickness".

      * `net_thickness_*_m` - the sum of the depth spans of the maximal
        STRICTLY-CONTIGUOUS eligible sub-runs inside this block, i.e. the
        gross span minus the spans of the bridged gaps. This is the
        rigorous "how much eligible section is actually here" figure.

    Increment 6.1.1 (Finding 3) replaces the ambiguous interruption fields
    with three that each state exactly what they count:

      * `n_bridged_samples`   - total ineligible samples absorbed INSIDE the
                                gross block;
      * `n_bridged_gaps`      - number of DISTINCT bridged False runs;
      * `n_eligible_subruns`  - number of strict contiguous eligible sub-runs
                                inside the gross block.

    The previous `n_interruptions` was a boolean-like flag masquerading as a
    count (it was 1 for every one of the 327 bridged blocks in the real data,
    whatever the actual number of gaps), and `n_interrupted_subruns` did not
    say what it counted. Both are gone; no ambiguous alias survives in the
    active exports.

    Invariants, enforced at construction and asserted by tests:

        no gap            -> n_bridged_samples == 0
                             n_bridged_gaps    == 0
                             n_eligible_subruns == 1
        two bridged gaps  -> n_bridged_gaps    == 2
                             n_eligible_subruns == 3
        general           -> n_eligible_subruns > 0 implies
                             n_bridged_gaps == n_eligible_subruns - 1

    `contiguity_policy` records which decomposition produced this record:
    `configured_bridging` (the project's configured gap tolerances) or
    `strict_no_gap` (no bridging at all). Under `strict_no_gap`, gross and
    net are equal by construction.

    A thickness is None when either end of the relevant span has no mapped
    depth - never 0, and never silently substituted with the MD span, which
    in a deviated well is a different quantity.
    """

    __slots__ = (
        "well_key", "mask_name", "scenario_name", "proxy_threshold", "block_index",
        "start_index", "end_index", "n_samples", "n_eligible_samples",
        "md_start_m", "md_end_m", "gross_thickness_md_m", "net_thickness_md_m",
        "tvd_start_m", "tvd_end_m", "gross_thickness_tvd_m", "net_thickness_tvd_m",
        "tvdss_start_m", "tvdss_end_m", "gross_thickness_tvdss_m", "net_thickness_tvdss_m",
        "n_bridged_samples", "n_bridged_gaps", "n_eligible_subruns",
        "contiguity_policy", "meets_configured_minimums", "limiting_reason",
        "depth_basis_used",
    )

    #: The three interruption-count fields, validated together as one record.
    COUNT_FIELDS = ("n_bridged_samples", "n_bridged_gaps", "n_eligible_subruns")

    #: Field names removed in Increment 6.1.1. Named explicitly so a caller
    #: still using the ambiguous schema gets a message that says so, rather
    #: than the generic unknown-keyword message.
    REMOVED_COUNT_FIELDS = ("n_interruptions", "n_interrupted_subruns")

    def _require_count(self, name: str) -> int:
        """Return a validated non-negative integer count for `name`.

        Increment 6.1.2 enforced the relational rules but let the TYPE gate
        through in three ways an audit found: `0.0 / 0.0 / 1.0` was accepted
        although the contract requires integers, and NaN / Inf escaped as a
        bare `ValueError` / `OverflowError` from `int()` rather than as a
        typed `PetrophysicsInputError`. Increment 6.1.3 decides the type
        before any conversion is attempted, so no arithmetic on an
        unvalidated value can raise first.
        """
        value = getattr(self, name)
        where = f"{self.well_key}/{self.mask_name}"
        if value is None:
            raise PetrophysicsInputError(
                f"{where}: interval record is missing required count {name!r}. "
                f"All of {self.COUNT_FIELDS} must be supplied together."
            )
        # `bool` is a subclass of `int`; a True/False count is a category
        # error - it is the very confusion the removed `n_interruptions` flag
        # embodied - and must not be silently read as 1/0.
        if isinstance(value, bool):
            raise PetrophysicsInputError(
                f"{where}: {name}={value!r} is a boolean, not a count. "
                f"A count says HOW MANY, not whether."
            )
        if isinstance(value, (int, np.integer)):
            return self._check_non_negative(name, int(value), where)
        # Floats are rejected OUTRIGHT, including whole-valued ones. The
        # contract is an integer count; `0.0` is not `0`, and accepting it
        # would mean the type gate depends on the value. Non-finite values are
        # named specifically, because `float('nan')` reaching `int()` is what
        # produced an untyped exception before.
        if isinstance(value, (float, np.floating)):
            if not math.isfinite(float(value)):
                raise PetrophysicsInputError(
                    f"{where}: {name}={value!r} is not finite; a count must be a "
                    f"finite integer."
                )
            raise PetrophysicsInputError(
                f"{where}: {name}={value!r} is a float; an integer count is required "
                f"({float(value)!r} is not {int(value)!r}). Counts are never coerced "
                f"from another numeric type."
            )
        raise PetrophysicsInputError(
            f"{where}: {name}={value!r} has type {type(value).__name__}; an integer "
            f"count is required (strings, complex values and other types are never "
            f"coerced)."
        )

    def _check_non_negative(self, name: str, ivalue: int, where: str) -> int:
        if ivalue < 0:
            raise PetrophysicsInputError(
                f"{where}: {name}={ivalue} is negative; counts cannot be negative."
            )
        return ivalue

    def __init__(self, **kwargs) -> None:
        # Increment 6.1.3: keyword acceptance is a WHITELIST, not a denylist.
        # Increment 6.1.2 rejected only the two known legacy names, so a typo
        # such as `n_bridged_sample=99` was silently ignored and the record was
        # built with that count unset - the same category error as guarding a
        # prohibition with an allowlist. Only real slots are accepted now.
        unknown = sorted(set(kwargs) - set(self.__slots__))
        if unknown:
            legacy = [k for k in unknown if k in self.REMOVED_COUNT_FIELDS]
            if legacy:
                raise PetrophysicsInputError(
                    f"{kwargs.get('well_key')}/{kwargs.get('mask_name')}: field(s) "
                    f"{legacy} were removed in Increment 6.1.1 and have no replacement "
                    f"alias. Use {self.COUNT_FIELDS} instead."
                )
            raise PetrophysicsInputError(
                f"{kwargs.get('well_key')}/{kwargs.get('mask_name')}: unknown field(s) "
                f"{unknown}. An interval record accepts only its declared fields, so a "
                f"misspelled count cannot silently leave the real one unset."
            )
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

        # Per-field validation first, so an error names the offending field.
        n_samples = self._require_count("n_bridged_samples")
        n_gaps = self._require_count("n_bridged_gaps")
        n_runs = self._require_count("n_eligible_subruns")
        self.n_bridged_samples, self.n_bridged_gaps = n_samples, n_gaps
        self.n_eligible_subruns = n_runs
        where = f"{self.well_key}/{self.mask_name}"

        # A block exists, so it has at least one eligible sub-run.
        if n_runs < 1:
            raise PetrophysicsInputError(
                f"{where}: n_eligible_subruns={n_runs}; a constructed interval "
                f"record describes an existing block and must have at least one "
                f"strictly contiguous eligible sub-run."
            )
        # The gap/sub-run relationship is structural, not incidental: cutting a
        # block into k pieces takes exactly k-1 cuts.
        if n_gaps != n_runs - 1:
            raise PetrophysicsInputError(
                f"{where}: inconsistent interval record - "
                f"n_eligible_subruns={n_runs} requires n_bridged_gaps={n_runs - 1}, "
                f"got {n_gaps}."
            )
        # Samples and gaps must agree about whether any bridging happened at
        # all. Either both are zero or both are positive - "5 bridged samples
        # in 0 gaps" and "2 gaps holding 0 samples" are each impossible.
        if (n_samples == 0) != (n_gaps == 0):
            raise PetrophysicsInputError(
                f"{where}: n_bridged_samples={n_samples} and n_bridged_gaps="
                f"{n_gaps} disagree - bridged samples exist if and only if a "
                f"bridged gap exists."
            )
        # Every distinct gap holds at least one sample, so samples >= gaps.
        if n_gaps > 0 and n_samples < n_gaps:
            raise PetrophysicsInputError(
                f"{where}: n_bridged_samples={n_samples} is fewer than "
                f"n_bridged_gaps={n_gaps}; every distinct bridged gap contains "
                f"at least one ineligible sample."
            )

    def as_dict(self) -> Dict:
        """Plain-Python dict view, JSON/CSV-safe (no NumPy scalars)."""
        out = {}
        for slot in self.__slots__:
            v = getattr(self, slot)
            if isinstance(v, (np.floating,)):
                v = float(v)
            elif isinstance(v, (np.integer,)):
                v = int(v)
            elif isinstance(v, (np.bool_,)):
                v = bool(v)
            out[slot] = v
        return out


def _purpose(config: PetrophysicsEligibilityConfig, mask_name: str) -> str:
    """The configured human-authored purpose string for a mask.

    Returns "" when the config carries no descriptive entry. Descriptive
    metadata is validated at CONFIG LOAD time (see
    `p2mem.petrophysics.load_petrophysics_eligibility_config`), which is
    where a real misconfiguration must fail loudly; a missing description
    must never abort a numerical computation that is otherwise correct.
    """
    entry = (config.method_eligibility or {}).get(mask_name) or {}
    return str(entry.get("purpose", "")).strip()


def _finite_within(values: Optional[np.ndarray], lo: float, hi: float) -> np.ndarray:
    """True where `values` is finite AND within [lo, hi]. An absent curve
    yields an all-False mask of the caller's length - a factual data gap,
    never an implicit pass."""
    if values is None:
        return None  # caller substitutes a correctly sized all-False mask
    v = np.asarray(values, dtype=np.float64)
    return np.isfinite(v) & (v >= lo) & (v <= hi)


def compute_density_eligibility(
    frame: WellFrame, config: PetrophysicsEligibilityConfig
) -> EligibilityMaskResult:
    """
    Mask samples technically admissible as input to a LATER vertical-stress
    (Sv) integration: finite, physically plausible RHOB at a mapped depth.

    Lithology-independent, so computed for every well including a
    GR-excluded one. This function does not fill missing density and does
    not compute Sv.
    """
    n = frame.n_samples
    bounds = config.policy["physical_bounds"]
    rhob = frame.values_or_none("RHOB_kg_m3")

    if rhob is None:
        rhob_finite = np.zeros(n, dtype=bool)
        rhob_in_bounds = np.zeros(n, dtype=bool)
    else:
        r = np.asarray(rhob, dtype=np.float64)
        rhob_finite = np.isfinite(r)
        rhob_in_bounds = rhob_finite & (r >= float(bounds["rhob_min_kg_m3"])) & (
            r <= float(bounds["rhob_max_kg_m3"])
        )

    depth_ok = np.asarray(frame.depth_valid_mask, dtype=bool)
    mask = rhob_in_bounds & depth_ok

    return EligibilityMaskResult(
        frame.well_key, MASK_DENSITY_FOR_SV, mask,
        {
            "rhob_finite": int(np.count_nonzero(rhob_finite)),
            "rhob_within_physical_bounds": int(np.count_nonzero(rhob_in_bounds)),
            "depth_mapped": int(np.count_nonzero(depth_ok)),
        },
        lithology_dependent=False,
        purpose=_purpose(config, MASK_DENSITY_FOR_SV),
        notes=(
            "Eligibility is a necessary, not sufficient, condition. Increment 6 does not fill "
            "missing density and does not compute vertical stress. A log that begins well below "
            "the seabed cannot support an overburden integral from surface regardless of how many "
            "of its own samples are eligible."
        ),
    )


def compute_dynamic_elastic_eligibility(
    frame: WellFrame, config: PetrophysicsEligibilityConfig
) -> EligibilityMaskResult:
    r"""
    Mask samples technically admissible as input to a LATER dynamic-elastic
    calculation: finite, physically plausible VP, VS and RHOB at a mapped
    depth, with VP > VS and a Vp/Vs ratio that passes the CONFIGURED
    NON-NEGATIVE-POISSON-RATIO APPLICABILITY SCREEN.

    The Vp/Vs domain, stated precisely (Increment 6.1 correction)
    ------------------------------------------------------------
    For an isotropic elastic solid with r = Vp/Vs:

        nu = (r^2 - 2) / (2 * (r^2 - 1))          [dynamic Poisson's ratio]
        K  = rho * (Vp^2 - (4/3) * Vs^2)          [bulk modulus]

    from which four DISTINCT regimes follow, which Increment 6 wrongly
    collapsed into a single "non-physical" label:

      * r <= sqrt(4/3) ~= 1.154701
            K <= 0. A non-positive bulk modulus IS outside the isotropic
            elastic model - this is the only regime that genuinely
            warrants the word "non-physical" under that model.

      * sqrt(4/3) < r < sqrt(2)
            K > 0 but nu < 0. A negative Poisson's ratio is UNUSUAL and
            is outside this project's conservative applicability policy,
            but it is NOT mathematically impossible and NOT "non-physical"
            - auxetic behavior is a real, if rare, elastic response. These
            samples are excluded by POLICY, and are diagnosed separately
            so a reader can see that the exclusion is a policy choice
            rather than a physical impossibility.

      * r = sqrt(2) EXACTLY
            nu = 0 exactly. A policy requiring a NON-NEGATIVE Poisson's
            ratio must ACCEPT this value. Increment 6 used a strictly
            exclusive bound and therefore wrongly rejected nu = 0; the
            bound is INCLUSIVE here (`ratio >= sqrt(2)`).

      * r > ratio_max (configured, 4.0)
            nu ~= 0.467 at r = 4 - an entirely ordinary Poisson's ratio.
            This bound is a CONFIGURED PLAUSIBILITY LIMIT reflecting what
            this project is willing to treat as a credible logged ratio,
            NOT a boundary of the mathematical Poisson domain.

    The screen is applied on the RATIO directly, with an inclusive
    `>= sqrt(2)` comparison against the configured constant, rather than
    on a floating-point evaluation of `nu >= 0`. This matters: evaluating
    the nu expression at r = sqrt(2) in IEEE-754 returns ~2.2e-16 rather
    than exactly 0, so a naive `nu >= 0` test would be decided by rounding
    noise at precisely the boundary the policy is about.

    Excluded samples are never deleted from the well frame and never
    "corrected". Increment 6 computes NO elastic property whatsoever -
    no Young's modulus, no Poisson's ratio curve, no bulk or shear
    modulus. The nu and K relations above are stated to DEFINE the
    screen's boundaries, not to compute anything.
    """
    n = frame.n_samples
    b = config.policy["physical_bounds"]
    vp_arr = frame.values_or_none("VP_m_s")
    vs_arr = frame.values_or_none("VS_m_s")
    rhob_arr = frame.values_or_none("RHOB_kg_m3")

    vp_ok = _finite_within(vp_arr, float(b["vp_min_m_s"]), float(b["vp_max_m_s"]))
    vs_ok = _finite_within(vs_arr, float(b["vs_min_m_s"]), float(b["vs_max_m_s"]))
    rhob_ok = _finite_within(rhob_arr, float(b["rhob_min_kg_m3"]), float(b["rhob_max_kg_m3"]))
    vp_ok = np.zeros(n, dtype=bool) if vp_ok is None else vp_ok
    vs_ok = np.zeros(n, dtype=bool) if vs_ok is None else vs_ok
    rhob_ok = np.zeros(n, dtype=bool) if rhob_ok is None else rhob_ok

    r_nu_min = float(b["vp_vs_ratio_nonnegative_poisson_min_inclusive"])
    r_k_bound = float(b["vp_vs_ratio_positive_bulk_modulus_min_exclusive"])
    r_max = float(b["vp_vs_ratio_plausibility_max"])

    both = vp_ok & vs_ok
    vp_gt_vs = np.zeros(n, dtype=bool)
    screen_ok = np.zeros(n, dtype=bool)
    nonpositive_K = np.zeros(n, dtype=bool)
    posK_negnu = np.zeros(n, dtype=bool)
    above_max = np.zeros(n, dtype=bool)

    if both.any():
        vp = np.asarray(vp_arr, dtype=np.float64)
        vs = np.asarray(vs_arr, dtype=np.float64)
        vp_gt_vs[both] = vp[both] > vs[both]
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.full(n, np.nan, dtype=np.float64)
            np.divide(vp, vs, out=ratio, where=both & (vs != 0.0))
        finite_r = np.isfinite(ratio)
        # Mutually exclusive, exhaustive classification of the finite-ratio
        # samples. `screen_ok` uses the INCLUSIVE sqrt(2) bound so that
        # nu == 0 passes a non-negative-nu policy.
        nonpositive_K = finite_r & (ratio <= r_k_bound)
        posK_negnu = finite_r & (ratio > r_k_bound) & (ratio < r_nu_min)
        above_max = finite_r & (ratio > r_max)
        screen_ok = finite_r & (ratio >= r_nu_min) & (ratio <= r_max)

    depth_ok = np.asarray(frame.depth_valid_mask, dtype=bool)
    mask = vp_ok & vs_ok & rhob_ok & vp_gt_vs & screen_ok & depth_ok

    # The Vp/Vs conditions are only MEANINGFUL where both velocities exist,
    # so their raw pass counts are structurally bounded by VS availability.
    # Using such a bounded count to pick the "limiting criterion" would
    # misreport a DATA-COVERAGE problem (VS is the scarcest curve in these
    # wells) as a PHYSICS problem. The counts compared for the limiting
    # criterion are therefore the independently meaningful per-curve
    # availability criteria plus depth mapping; the Vp/Vs conditions are
    # reported separately, and SEPARATELY BY REGIME - never aggregated
    # under a single "non-physical" label.
    return EligibilityMaskResult(
        frame.well_key, MASK_DYNAMIC_ELASTIC, mask,
        {
            "vp_finite_positive_in_bounds": int(np.count_nonzero(vp_ok)),
            "vs_finite_positive_in_bounds": int(np.count_nonzero(vs_ok)),
            "rhob_finite_in_bounds": int(np.count_nonzero(rhob_ok)),
            "depth_mapped": int(np.count_nonzero(depth_ok)),
        },
        diagnostic_counts={
            "n_vp_and_vs_both_valid": int(np.count_nonzero(both)),
            "n_vp_not_greater_than_vs": int(np.count_nonzero(both & ~vp_gt_vs)),
            "n_ratio_nonpositive_bulk_modulus": int(np.count_nonzero(nonpositive_K)),
            "n_ratio_positive_bulk_but_negative_poisson": int(np.count_nonzero(posK_negnu)),
            "n_ratio_above_configured_plausibility_max": int(np.count_nonzero(above_max)),
            "n_passes_nonnegative_poisson_screen": int(np.count_nonzero(screen_ok)),
        },
        lithology_dependent=False,
        purpose=_purpose(config, MASK_DYNAMIC_ELASTIC),
        notes=(
            "Input-admissibility only. Increment 6 computes no Young's modulus, Poisson ratio, "
            "bulk modulus, or shear modulus. The Vp/Vs condition is a CONFIGURED NON-NEGATIVE-"
            "POISSON-RATIO APPLICABILITY SCREEN (inclusive at Vp/Vs = sqrt(2), where nu = 0 "
            "exactly), not a test of physical possibility. Excluded ratios are diagnosed by "
            "regime: non-positive bulk modulus (Vp/Vs <= sqrt(4/3), genuinely outside the "
            "isotropic elastic model); positive bulk modulus with negative Poisson ratio "
            "(sqrt(4/3) < Vp/Vs < sqrt(2), unusual and outside this project's conservative "
            "policy, but NOT non-physical); and above the configured plausibility maximum "
            "(Vp/Vs > 4, a project credibility limit, not a Poisson-domain boundary). These are "
            "never aggregated into a single 'non-physical' count. No excluded sample is deleted "
            "from the well frame or corrected."
        ),
    )


def compute_sonic_nct_candidate_eligibility(
    frame: WellFrame,
    disposition: GrFamilyDisposition,
    proxy: GrProxyResult,
    proxy_threshold: float,
    config: PetrophysicsEligibilityConfig,
) -> EligibilityMaskResult:
    """
    Mask CANDIDATE DATA for a LATER sonic normal-compaction-trend analysis.

    Requires an approved GR-family disposition, finite VP, a finite
    screening proxy at or above `proxy_threshold`, and a mapped depth.

    Raises `PetrophysicsInputError` if called for a well whose disposition
    forbids GR-derived work - such a well can never have a candidate mask,
    because the mask consumes a GR proxy that must not exist for it.

    This mask fits nothing, selects no donor interval, and claims neither
    normal compaction nor overpressure. It must never be read as proof
    that an interval is normally compacted, and it names no lithology.
    """
    if not disposition.proxy_permitted:
        raise PetrophysicsInputError(
            f"{frame.well_key}: sonic-NCT candidate eligibility is lithology-dependent and cannot "
            f"be computed for a well excluded from GR-derived work "
            f"(use_status={disposition.use_status!r}, exclusion_reason="
            f"{disposition.exclusion_reason!r})."
        )
    if proxy.well_key != frame.well_key:
        raise PetrophysicsInputError(
            f"Proxy result belongs to well {proxy.well_key!r} but was supplied for "
            f"{frame.well_key!r}; a proxy is never transferred between wells."
        )

    n = frame.n_samples
    b = config.policy["physical_bounds"]
    vp_ok = _finite_within(frame.values_or_none("VP_m_s"), float(b["vp_min_m_s"]), float(b["vp_max_m_s"]))
    vp_ok = np.zeros(n, dtype=bool) if vp_ok is None else vp_ok

    proxy_vals = np.asarray(proxy.VSH_GR_linear_proxy_frac, dtype=np.float64)
    if proxy_vals.size != n:
        raise PetrophysicsInputError(
            f"{frame.well_key}: proxy array length {proxy_vals.size} does not match well-frame "
            f"sample count {n}."
        )
    proxy_finite = np.isfinite(proxy_vals)
    thr = float(proxy_threshold)
    if not np.isfinite(thr):
        raise PetrophysicsInputError(f"{frame.well_key}: proxy_threshold must be finite, got {thr!r}.")
    proxy_at_or_above = proxy_finite & (proxy_vals >= thr)

    depth_ok = np.asarray(frame.depth_valid_mask, dtype=bool)
    mask = vp_ok & proxy_at_or_above & depth_ok

    return EligibilityMaskResult(
        frame.well_key, MASK_SONIC_NCT_CANDIDATE, mask,
        {
            "gr_disposition_approved": n,  # gate already passed above, else this raised
            "vp_finite_in_bounds": int(np.count_nonzero(vp_ok)),
            "proxy_finite": int(np.count_nonzero(proxy_finite)),
            "proxy_at_or_above_threshold": int(np.count_nonzero(proxy_at_or_above)),
            "depth_mapped": int(np.count_nonzero(depth_ok)),
        },
        scenario_name=proxy.scenario_name,
        proxy_threshold=thr,
        lithology_dependent=True,
        purpose=_purpose(config, MASK_SONIC_NCT_CANDIDATE),
        notes=(
            "CANDIDATE DATA ONLY - no NCT fitted. This mask does not fit a trend, does not select "
            "a donor interval, does not claim normal compaction, and does not claim overpressure. "
            "It is not proof that any interval is normally compacted, and it assigns no lithology."
        ),
    )


CONTIGUITY_POLICY_CONFIGURED = "configured_bridging"
CONTIGUITY_POLICY_STRICT = "strict_no_gap"
VALID_CONTIGUITY_POLICIES: Tuple[str, ...] = (
    CONTIGUITY_POLICY_CONFIGURED,
    CONTIGUITY_POLICY_STRICT,
)


def _span(depth: np.ndarray, i0: int, i1: int) -> Optional[float]:
    """Depth span between two indices, or None if either end is unmapped."""
    a, b = depth[i0], depth[i1]
    if not (np.isfinite(a) and np.isfinite(b)):
        return None
    return float(b) - float(a)


def _net_span(depth: np.ndarray, mask: np.ndarray, i0: int, i1: int) -> Optional[float]:
    """
    Sum of the depth spans of the maximal STRICTLY-CONTIGUOUS True runs
    inside `[i0, i1]` - i.e. the block's gross span minus the spans of any
    bridged gaps.

    Returns None if any contributing run has an unmapped endpoint, so a
    partially-unmapped block reports "unknown" rather than an
    understated number.
    """
    sub = mask[i0 : i1 + 1]
    if not sub.any():
        return 0.0
    total = 0.0
    for a, b in find_contiguous_blocks(sub):
        sp = _span(depth, i0 + a, i0 + b)
        if sp is None:
            return None
        total += sp
    return total


def build_eligibility_intervals(
    frame: WellFrame,
    mask_result: EligibilityMaskResult,
    config: PetrophysicsEligibilityConfig,
    *,
    contiguity_policy: str = CONTIGUITY_POLICY_CONFIGURED,
) -> List[EligibilityInterval]:
    """
    Convert one eligibility mask into contiguous interval records on MD,
    TVD and TVDSS.

    `contiguity_policy` selects the decomposition:

      * `configured_bridging` (default) - uses the project's configured
        gap tolerances. A gap is bridged into a block only when BOTH the
        sample gap AND the physical depth span are within tolerance, so a
        two-sample gap across a large depth jump correctly starts a new
        block. Bridged samples are always disclosed via
        `n_bridged_samples` / `n_bridged_gaps` / `n_eligible_subruns`,
        and the block's
        `gross_thickness_*_m` is explicitly labelled gross because it
        spans them. `net_thickness_*_m` reports the same block with those
        gaps removed.

      * `strict_no_gap` - no bridging at all. Gross and net coincide by
        construction, giving the conservative comparison figure.

    Nothing is extrapolated under either policy. A block is emitted even
    when it fails the configured minimum sample count or thickness -
    `meets_configured_minimums` is False and `limiting_reason` records
    which requirement it failed - so sub-threshold eligible data is
    disclosed rather than silently dropped.
    """
    if contiguity_policy not in VALID_CONTIGUITY_POLICIES:
        raise PetrophysicsInputError(
            f"Unknown contiguity_policy {contiguity_policy!r}; expected one of "
            f"{VALID_CONTIGUITY_POLICIES}."
        )
    cont = config.policy["contiguity"]
    if contiguity_policy == CONTIGUITY_POLICY_STRICT:
        max_gap_samples, max_gap_depth_m = 0, 0.0
    else:
        max_gap_samples = int(cont["max_gap_samples"])
        max_gap_depth_m = float(cont["max_gap_depth_m"])
    min_block_samples = int(cont["min_block_samples"])
    min_block_thickness_m = float(cont["min_block_thickness_m"])

    md = np.asarray(frame.MD_m, dtype=np.float64)
    tvd = np.asarray(frame.TVD_m, dtype=np.float64)
    tvdss = np.asarray(frame.TVDSS_m, dtype=np.float64)
    mask = mask_result.mask

    blocks = find_contiguous_blocks(
        mask, md, max_gap_samples=max_gap_samples, max_gap_depth_m=max_gap_depth_m
    )

    out: List[EligibilityInterval] = []
    for i, (s0, e0) in enumerate(blocks):
        span_n = e0 - s0 + 1
        n_elig = int(np.count_nonzero(mask[s0 : e0 + 1]))
        n_bridged = span_n - n_elig
        # Strict (unbridged) eligible sub-runs inside this gross block, and the
        # distinct bridged False runs that separate them.
        sub = mask[s0 : e0 + 1]
        n_eligible_subruns = len(find_contiguous_blocks(sub))
        n_bridged_gaps = len(find_contiguous_blocks(~sub)) if n_bridged else 0

        md_s, md_e = float(md[s0]), float(md[e0])
        tvd_s = float(tvd[s0]) if np.isfinite(tvd[s0]) else None
        tvd_e = float(tvd[e0]) if np.isfinite(tvd[e0]) else None
        ss_s = float(tvdss[s0]) if np.isfinite(tvdss[s0]) else None
        ss_e = float(tvdss[e0]) if np.isfinite(tvdss[e0]) else None

        gross_md = md_e - md_s
        gross_tvd = (tvd_e - tvd_s) if (tvd_s is not None and tvd_e is not None) else None
        gross_ss = (ss_e - ss_s) if (ss_s is not None and ss_e is not None) else None
        net_md = _net_span(md, mask, s0, e0)
        net_tvd = _net_span(tvd, mask, s0, e0)
        net_ss = _net_span(tvdss, mask, s0, e0)

        reasons = []
        if span_n < min_block_samples:
            reasons.append(f"below_min_block_samples({span_n}<{min_block_samples})")
        thickness_for_test = gross_ss if gross_ss is not None else gross_md
        if thickness_for_test is not None and thickness_for_test < min_block_thickness_m:
            reasons.append(
                f"below_min_block_thickness({thickness_for_test:.3f}m<{min_block_thickness_m}m)"
            )
        meets = not reasons
        limiting = ";".join(reasons) if reasons else "none_meets_all_configured_minimums"

        out.append(
            EligibilityInterval(
                well_key=frame.well_key,
                mask_name=mask_result.mask_name,
                scenario_name=mask_result.scenario_name,
                proxy_threshold=mask_result.proxy_threshold,
                block_index=i,
                start_index=int(s0),
                end_index=int(e0),
                n_samples=int(span_n),
                n_eligible_samples=n_elig,
                md_start_m=md_s, md_end_m=md_e,
                gross_thickness_md_m=gross_md, net_thickness_md_m=net_md,
                tvd_start_m=tvd_s, tvd_end_m=tvd_e,
                gross_thickness_tvd_m=gross_tvd, net_thickness_tvd_m=net_tvd,
                tvdss_start_m=ss_s, tvdss_end_m=ss_e,
                gross_thickness_tvdss_m=gross_ss, net_thickness_tvdss_m=net_ss,
                n_bridged_samples=int(n_bridged),
                n_bridged_gaps=int(n_bridged_gaps),
                n_eligible_subruns=int(n_eligible_subruns),
                contiguity_policy=contiguity_policy,
                meets_configured_minimums=bool(meets),
                limiting_reason=limiting,
                depth_basis_used=frame.depth_basis_used,
            )
        )
    return out
