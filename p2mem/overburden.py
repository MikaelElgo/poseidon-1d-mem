"""
p2mem.overburden - vertical overburden-stress framework (Increment 7).

The integral
------------
    sigma_v(z) = INTEGRAL_0^z rho(z') g dz'

evaluated in TRUE VERTICAL DEPTH. For a deviated well this is NOT the same as
integrating against measured depth: the measured-depth span of an interval
always equals or exceeds its true-vertical span, and integrating in MD would
inflate the result by exactly that ratio. This module accepts a VERTICAL-depth
array and rejects a non-monotonic one, so measured-depth integration is not
merely discouraged - it is structurally unavailable.

No well name appears anywhere in this module, in `p2mem.density_qc`, or in
`config/overburden_stress.yml`. Method eligibility is derived from measured
coverage and QC evidence; there is no identifier for a branch to read.

Sign convention - VERIFIED, not inferred from a variable name
--------------------------------------------------------------
The locked `p2mem.depth_mapping` module documents and independently tests:

    TVD is zero at the well datum and increases DOWNWARD; datum elevation is
    referenced to mean sea level, positive UPWARD; TVDSS = TVD - datum
    elevation, so TVDSS is positive DOWNWARD from mean sea level.

`verify_depth_sign_convention` re-derives this from the LOCKED well frame's
own arrays at run time - it checks that TVD increases with MD, that
TVDSS == TVD - datum_elevation to floating-point tolerance, and that the
constant offset is exactly the datum elevation - and raises rather than
proceeding if any of those fails. Nothing in this module reads a sign from a
name.

Separation of measurement from assumption
-----------------------------------------
Every reported stress is partitioned into:

  * water column          - ASSUMED seawater density, configured
  * measured formation    - recorded RHOB only
  * conditioned short gap - linearly bridged density, reported separately
  * unresolved shallow    - model-dependent, only ever a labelled scenario

A total is reported only when no component is unresolved. An unresolved
component is never treated as zero.
"""

from __future__ import annotations

import math
from numbers import Real
from typing import Dict, List, Optional, Tuple

import numpy as np

from p2mem.overburden_models import (
    GAP_CLASS_LONG_INTERNAL,
    GAP_CLASS_SHALLOW,
    GAP_CLASS_TERMINAL,
    GAP_DISPOSITION_UNRESOLVED,
    GAP_DISPOSITION_BRIDGED,
    REASON_DEPTH_MAPPING_INCOMPLETE,
    REASON_INSUFFICIENT_ELIGIBLE_SAMPLES,
    REASON_INTERNAL_GAP_EXCEEDS_LIMIT,
    REASON_INTERNAL_GAP_UNRESOLVED,
    REASON_RHOB_ALL_INVALID,
    REASON_RHOB_NOT_AVAILABLE,
    REASON_SCREENING_BOUND_FAILURES,
    REASON_SEABED_DATUM_UNRESOLVED,
    REASON_SHALLOW_COLUMN_UNRESOLVED,
    REASON_SURVEY_COVERAGE_INSUFFICIENT,
    REASON_TERMINAL_COLUMN_UNRESOLVED,
    REASON_UNIT_NOT_RESOLVED,
    SCENARIO_BASE,
    SCENARIO_BASE_SEAWATER_HIGH,
    SCENARIO_BASE_SEAWATER_LOW,
    SCENARIO_HIGH,
    SCENARIO_LOW,
    SCENARIO_BASIS_BASE,
    SCENARIO_BASIS_HIGH,
    SCENARIO_BASIS_LOW,
    SEABED_BASIS_LOCKED_MARKER,
    SEABED_BASIS_NOT_DETERMINABLE,
    STATUS_ABSOLUTE,
    STATUS_NOT_ELIGIBLE,
    STATUS_PARTIAL_ONLY,
    STATUS_SENSITIVITY_ONLY,
    DensityQcStats,
    GapConditioningResult,
    OverburdenConfig,
    OverburdenEligibility,
    OverburdenInputError,
    ShallowColumnScenario,
    StressPartition,
    VerticalStressProfile,
    readonly,
)

__all__ = [
    "DEPTH_CONVENTION_STATEMENT",
    "SIGN_CONVENTION_ID",
    "verify_depth_sign_convention",
    "integrate_vertical_stress",
    "water_column_stress_pa",
    "uniform_column_stress_pa",
    "build_stress_profile",
    "build_gap_threshold_sensitivity",
    "derive_overburden_eligibility",
    "build_shallow_column_scenarios",
    "pa_to_mpa",
]

#: The verified, machine-checkable identity of the depth convention this
#: module integrates in. Emitted with every result so that a reader never has
#: to reconstruct it from a variable name.
SIGN_CONVENTION_ID = "tvd_and_tvdss_increase_downward_tvdss_zero_at_msl"

DEPTH_CONVENTION_STATEMENT = (
    "TVD is zero at the well datum and increases downward; the datum elevation is "
    "referenced to mean sea level, positive upward; TVDSS = TVD - datum elevation and is "
    "positive downward from mean sea level. A downward interval therefore has a positive "
    "increment in both coordinates, and dTVD equals dTVDSS exactly. This convention is "
    "documented and independently tested in the locked depth-mapping module, and is "
    "re-verified against each well frame's own arrays at run time rather than inferred "
    "from a variable name."
)


def pa_to_mpa(value: Optional[float]) -> Optional[float]:
    """Convert pascals to megapascals. Exact decimal factor, no rounding."""
    return None if value is None else float(value) / 1.0e6


# ---------------------------------------------------------------------------
# Sign-convention verification
# ---------------------------------------------------------------------------

def verify_depth_sign_convention(well_frame, *, tolerance_m: float = 1e-6) -> Dict[str, object]:
    """Re-derive and confirm the project's depth-sign convention for ONE well.

    Three independent checks against the LOCKED well frame's own arrays:

      1. TVD is non-decreasing with increasing MD over the depth-mapped
         samples (a well trajectory cannot rise as measured depth increases);
      2. `TVDSS == TVD - datum_elevation_m` to within `tolerance_m`;
      3. the constant offset between TVD and TVDSS equals the frame's own
         recorded datum elevation, to within `tolerance_m`.

    Raises `OverburdenInputError` naming the failed check rather than
    proceeding. Returns the measured evidence so it can be exported.
    """
    tvd = np.asarray(well_frame.TVD_m, dtype=np.float64)
    tvdss = np.asarray(well_frame.TVDSS_m, dtype=np.float64)
    md = np.asarray(well_frame.MD_m, dtype=np.float64)
    valid = np.asarray(well_frame.depth_valid_mask, dtype=bool)
    datum = float(well_frame.datum_elevation_m)

    if int(np.count_nonzero(valid)) < 2:
        raise OverburdenInputError(
            f"{well_frame.well_key}: fewer than two depth-mapped samples; the depth-sign "
            f"convention cannot be verified, and Increment 7 does not assume it.")

    t, s, m = tvd[valid], tvdss[valid], md[valid]
    order = np.argsort(m, kind="stable")
    t_ord = t[order]
    d_tvd = np.diff(t_ord)
    n_decreasing = int(np.count_nonzero(d_tvd < -tolerance_m))
    if n_decreasing:
        raise OverburdenInputError(
            f"{well_frame.well_key}: TVD decreases with increasing MD at {n_decreasing} "
            f"sample interval(s) (most negative {float(np.min(d_tvd)):.9f} m). The project "
            f"depth convention requires TVD to increase downward; Increment 7 refuses to "
            f"integrate against a coordinate whose direction it cannot confirm.")

    offset = t - s
    max_offset_dev = float(np.max(np.abs(offset - datum)))
    if max_offset_dev > tolerance_m:
        raise OverburdenInputError(
            f"{well_frame.well_key}: TVD - TVDSS deviates from the recorded datum elevation "
            f"({datum} m) by up to {max_offset_dev:.9f} m, exceeding the {tolerance_m} m "
            f"tolerance. The relationship TVDSS = TVD - datum_elevation is the project's "
            f"stated convention and is not assumed when it cannot be confirmed.")

    d_tvdss = np.diff(s[order])
    max_increment_dev = float(np.max(np.abs(d_tvd - d_tvdss))) if d_tvd.size else 0.0
    if max_increment_dev > tolerance_m:
        raise OverburdenInputError(
            f"{well_frame.well_key}: dTVD and dTVDSS differ by up to {max_increment_dev:.9f} "
            f"m; they must be identical because the two coordinates differ by a per-well "
            f"constant.")

    return {
        "sign_convention_id": SIGN_CONVENTION_ID,
        "verified": True,
        "n_depth_mapped_samples": int(np.count_nonzero(valid)),
        "datum_elevation_m": datum,
        "max_tvd_minus_tvdss_deviation_m": max_offset_dev,
        "max_dtvd_minus_dtvdss_deviation_m": max_increment_dev,
        "min_tvd_increment_m": float(np.min(d_tvd)) if d_tvd.size else 0.0,
        "tvd_increases_downward": True,
    }


# ---------------------------------------------------------------------------
# Core integration
# ---------------------------------------------------------------------------

def _reject_ambiguous_dtype(raw: np.ndarray, context: str) -> None:
    """Reject boolean, string/bytes, complex and object dtype with `TypeError`.

    Documented local copy of the check established in the locked
    `p2mem.units` / `p2mem.time_depth` / `p2mem.io.tops` modules.
    """
    kind = raw.dtype.kind
    if kind == "b":
        raise TypeError(f"{context}: boolean input is not accepted as a numeric quantity.")
    if kind in ("U", "S"):
        raise TypeError(f"{context}: string/bytes input is not accepted as a numeric quantity.")
    if kind == "c":
        raise TypeError(f"{context}: complex input is not accepted as a numeric quantity.")
    if kind == "O":
        raise TypeError(f"{context}: object-dtype input is not accepted as a numeric quantity.")
    if kind not in ("i", "u", "f"):
        raise TypeError(f"{context}: unsupported array dtype {raw.dtype!r} for a numeric quantity.")


def _require_real_scalar(value, name: str, context: str, *, positive: bool = False,
                         non_negative: bool = False) -> float:
    """Validate one finite real scalar without coercing strings or complex values."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(
            f"{context}: {name} must be a real numeric scalar, got "
            f"{type(value).__name__} {value!r}.")
    out = float(value)
    if not math.isfinite(out):
        raise OverburdenInputError(f"{context}: {name} must be finite, got {value!r}.")
    if positive and out <= 0.0:
        raise OverburdenInputError(
            f"{context}: {name} must be strictly positive, got {value!r}.")
    if non_negative and out < 0.0:
        raise OverburdenInputError(f"{context}: {name} must be >= 0, got {value!r}.")
    return out


def integrate_vertical_stress(
    density_kg_m3,
    vertical_depth_m,
    gravity_m_s2: float,
    *,
    context: str = "integrate_vertical_stress",
) -> Tuple[np.ndarray, int]:
    """Trapezoidal integration of rho*g*dz against a VERTICAL depth coordinate.

    Returns `(cumulative_pa, n_zero_thickness_intervals)`, where
    `cumulative_pa[0]` is exactly 0.0 and `cumulative_pa[i]` is the integral
    from the first node down to node `i`.

    Preconditions, checked in order and never silently repaired:

      * both inputs are 1-D numeric arrays of equal length, at least 2 long;
      * neither carries boolean, string, complex, or object dtype;
      * every density is finite and strictly positive;
      * every vertical depth is finite;
      * every vertical increment is non-negative. A ZERO increment (a repeated
        or equal vertical coordinate) contributes exactly zero, is counted,
        and is returned to the caller for disclosure. A NEGATIVE increment is
        REJECTED with `OverburdenInputError` - it is either a sorting defect
        or an attempt to integrate the wrong coordinate, and sorting it away
        silently would hide both.

    The inputs are never mutated; the returned array is a new read-only array.
    """
    rho_raw = np.asarray(density_kg_m3)
    z_raw = np.asarray(vertical_depth_m)
    _reject_ambiguous_dtype(rho_raw, f"{context}: density")
    _reject_ambiguous_dtype(z_raw, f"{context}: vertical depth")

    rho = rho_raw.astype(np.float64, copy=True)
    z = z_raw.astype(np.float64, copy=True)
    if rho.ndim != 1 or z.ndim != 1:
        raise OverburdenInputError(
            f"{context}: density and vertical depth must both be 1-D arrays, got shapes "
            f"{rho.shape} and {z.shape}.")
    if rho.size != z.size:
        raise OverburdenInputError(
            f"{context}: density has {rho.size} sample(s) but vertical depth has {z.size}; "
            f"a stress integral never truncates or pads to reconcile a length disagreement.")
    if rho.size < 2:
        raise OverburdenInputError(
            f"{context}: at least two samples are required to form one trapezoid, got "
            f"{rho.size}.")

    g = _require_real_scalar(
        gravity_m_s2, "gravity_m_s2", context, positive=True)

    if not np.all(np.isfinite(rho)):
        n_bad = int(np.count_nonzero(~np.isfinite(rho)))
        raise OverburdenInputError(
            f"{context}: {n_bad} non-finite density value(s) reached the integrator. A NaN or "
            f"infinity is never treated as zero and is never interpolated away here; it must "
            f"be excluded by an explicit mask upstream.")
    if not np.all(rho > 0.0):
        n_bad = int(np.count_nonzero(rho <= 0.0))
        raise OverburdenInputError(
            f"{context}: {n_bad} non-positive density value(s) reached the integrator; a "
            f"non-positive bulk density is not a formation property.")
    if not np.all(np.isfinite(z)):
        n_bad = int(np.count_nonzero(~np.isfinite(z)))
        raise OverburdenInputError(
            f"{context}: {n_bad} non-finite vertical-depth value(s) reached the integrator.")

    dz = np.diff(z)
    if np.any(dz < 0.0):
        n_bad = int(np.count_nonzero(dz < 0.0))
        worst = float(np.min(dz))
        raise OverburdenInputError(
            f"{context}: {n_bad} negative vertical increment(s) (most negative {worst:.9f} m). "
            f"The integrator refuses a non-monotonic vertical coordinate rather than sorting "
            f"it: a decreasing vertical depth is either a data-ordering defect or the wrong "
            f"coordinate (for example measured depth in a deviated well), and silently "
            f"sorting would hide both.")

    n_zero = int(np.count_nonzero(dz == 0.0))
    segment = 0.5 * (rho[:-1] + rho[1:]) * g * dz
    cumulative = np.empty(rho.size, dtype=np.float64)
    cumulative[0] = 0.0
    np.cumsum(segment, out=cumulative[1:])
    return readonly(cumulative), n_zero


def water_column_stress_pa(
    seabed_tvdss_m: float, seawater_density_kg_m3: float, gravity_m_s2: float
) -> float:
    """Vertical stress at the seabed from the ASSUMED seawater column.

    The seawater density is a CONFIGURED ASSUMPTION. This project holds no
    measured seawater density, salinity, or temperature profile for these
    locations, and this value must never be described as measured data.
    """
    return uniform_column_stress_pa(
        seabed_tvdss_m, seawater_density_kg_m3, gravity_m_s2,
        context="water_column_stress_pa")


def uniform_column_stress_pa(
    thickness_m: float, density_kg_m3: float, gravity_m_s2: float,
    *, context: str = "uniform_column_stress_pa",
) -> float:
    """`rho * g * h` for a column of uniform assumed density.

    Used for the water column and for the unresolved shallow-column scenarios.
    It is deliberately a single explicit product rather than a call into the
    array integrator: a uniform assumed density is not a measurement, and
    routing it through the measured-data path would blur that distinction.
    """
    h = _require_real_scalar(
        thickness_m, "thickness_m", context, non_negative=True)
    rho = _require_real_scalar(
        density_kg_m3, "density_kg_m3", context, positive=True)
    g = _require_real_scalar(
        gravity_m_s2, "gravity_m_s2", context, positive=True)
    return rho * g * h


# ---------------------------------------------------------------------------
# Per-well stress profile
# ---------------------------------------------------------------------------

def build_stress_profile(
    well_frame,
    masks,
    gap_result: GapConditioningResult,
    config: OverburdenConfig,
) -> Optional[VerticalStressProfile]:
    """Build ONE well's measured vertical-stress increment profile.

    The profile spans the contiguous integrable column: the eligible measured
    samples, plus any sample the configured policy actually bridged. It is
    TRUNCATED at the first unresolved internal gap - Increment 7 never integrates
    through an unresolved gap, because the density there is unknown and
    treating it as absent would silently join two columns that are not
    adjacent.

    Why the FIRST segment, rather than the longest one
    ---------------------------------------------------
    Vertical stress accumulates downward, so a segment is only ever useful if
    it can be tied to the column above it. The segment beginning at the
    SHALLOWEST eligible sample is the only one that could ever be connected to
    the shallow column and therefore to an absolute stress; a deeper segment
    sitting below an unresolved gap is stress-disconnected from everything
    above it and cannot contribute to sigma_v at all until that gap is
    resolved. Selecting the longest segment instead would report a larger
    number that is no more connectable, which is exactly the kind of
    flattering-but-useless result this increment is built to avoid.

    Returns `None` when that first segment holds fewer than the configured
    minimum number of samples - which is a genuine "no measured increment",
    even when the well holds many eligible samples further down.
    """
    elig = np.asarray(masks.eligible_for_measured_integration, dtype=bool)
    bridged = np.asarray(gap_result.bridged_mask, dtype=bool)
    usable = elig | bridged

    idx = np.flatnonzero(elig)
    if idx.size < config.min_eligible_samples_for_increment:
        return None

    first = int(idx[0])
    # Truncate at the first unresolved INTERNAL gap below the first eligible
    # sample.  This is disposition-driven rather than class-driven: a short
    # gap can remain unresolved when bridging is disabled or when a bridge
    # precondition fails, and an unmapped-depth gap is equally non-integrable.
    # Shallow and terminal gaps lie outside the bracketed measured column.
    unresolved_starts = sorted(
        int(g.start_index) for g in gap_result.gaps
        if g.disposition == GAP_DISPOSITION_UNRESOLVED
        and g.gap_class not in (GAP_CLASS_SHALLOW, GAP_CLASS_TERMINAL)
        and g.start_index is not None
        and int(g.start_index) > first)
    stop = unresolved_starts[0] if unresolved_starts else int(usable.size)

    window = np.zeros(usable.size, dtype=bool)
    window[first:stop] = True
    take = np.flatnonzero(usable & window)
    if take.size < config.min_eligible_samples_for_increment:
        return None

    density = np.asarray(gap_result.conditioned_density_kg_m3, dtype=np.float64)[take]
    md_nodes = np.asarray(well_frame.MD_m, dtype=np.float64)[take]
    tvd = np.asarray(well_frame.TVD_m, dtype=np.float64)[take]
    tvdss = np.asarray(well_frame.TVDSS_m, dtype=np.float64)[take]
    bridged_take = bridged[take]

    cumulative, n_zero = integrate_vertical_stress(
        density, tvdss, config.gravity_m_s2,
        context=f"{well_frame.well_key}: measured vertical-stress increment")

    # The bridged contribution is the part of the same integral whose
    # trapezoid touches at least one conditioned sample. Attributing a
    # trapezoid with one measured and one bridged endpoint to the bridged
    # side is the conservative choice: it can only overstate how much of the
    # result depends on interpolation, never understate it.
    dz = np.diff(tvdss)
    seg = 0.5 * (density[:-1] + density[1:]) * float(config.gravity_m_s2) * dz
    touches_bridge = bridged_take[:-1] | bridged_take[1:]
    bridged_pa = float(np.sum(seg[touches_bridge])) if seg.size else 0.0

    return VerticalStressProfile(
        well_key=well_frame.well_key,
        n_nodes=int(take.size),
        integration_coordinate="tvdss_m",
        gravity_m_s2=float(config.gravity_m_s2),
        md_m=readonly(md_nodes.copy()),
        tvd_m=readonly(tvd.copy()),
        tvdss_m=readonly(tvdss.copy()),
        density_kg_m3=readonly(density.copy()),
        bridged_mask=readonly(bridged_take.copy()),
        cumulative_measured_increment_pa=cumulative,
        total_measured_increment_pa=float(cumulative[-1]),
        total_bridged_increment_pa=bridged_pa,
        n_zero_thickness_intervals=n_zero,
        n_intervals=int(take.size) - 1,
        top_tvd_m=float(tvd[0]),
        base_tvd_m=float(tvd[-1]),
        top_tvdss_m=float(tvdss[0]),
        base_tvdss_m=float(tvdss[-1]),
        column_truncated_at_unresolved_gap=bool(unresolved_starts),
        n_eligible_samples_below_truncation=int(np.count_nonzero(elig[stop:])),
    )


# ---------------------------------------------------------------------------
# Eligibility derivation
# ---------------------------------------------------------------------------

def derive_overburden_eligibility(
    stats: DensityQcStats,
    masks,
    gap_result: GapConditioningResult,
    profile: Optional[VerticalStressProfile],
    config: OverburdenConfig,
) -> OverburdenEligibility:
    """DERIVE ONE well's overburden method-eligibility status from evidence.

    No well name participates. The status is a function of measured coverage
    and QC results only:

      not_eligible                    - no density curve, or fewer than the
                                        configured minimum eligible samples
      partial_measured_increment_only - an eligible measured column exists,
                                        but the seabed datum is UNRESOLVED, so
                                        the unmeasured shallow column's
                                        thickness is not even quantifiable and
                                        no bracket can be constructed
      screening_sensitivity_only      - an eligible measured column exists and
                                        the seabed datum IS resolved, so the
                                        unmeasured column's thickness is known
                                        and can be transparently bracketed -
                                        but it is not measured
      absolute_overburden_supported   - the density column reaches the seabed
                                        within the configured tolerance and no
                                        unresolved internal gap of any class
                                        interrupts it

    The ladder is deliberately ordered by what the EVIDENCE can support, not
    by how complete an answer each rung produces.
    """
    reasons: List[str] = []
    seabed_resolved = stats.seabed_basis == SEABED_BASIS_LOCKED_MARKER

    if not stats.curve_present:
        reasons.append(REASON_RHOB_NOT_AVAILABLE)
    if not stats.unit_resolved and stats.curve_present:
        reasons.append(REASON_UNIT_NOT_RESOLVED)
    if stats.curve_present and stats.n_finite == 0:
        reasons.append(REASON_RHOB_ALL_INVALID)
    if stats.n_screening_bound_failures > 0:
        reasons.append(REASON_SCREENING_BOUND_FAILURES)
    if stats.n_depth_unmapped > 0:
        reasons.append(REASON_DEPTH_MAPPING_INCOMPLETE)
    if stats.n_samples_outside_survey_coverage > 0:
        reasons.append(REASON_SURVEY_COVERAGE_INSUFFICIENT)
    if not seabed_resolved:
        reasons.append(REASON_SEABED_DATUM_UNRESOLVED)

    n_long = int(gap_result.n_long_gaps)
    unresolved_internal = tuple(
        g for g in gap_result.gaps
        if g.disposition == GAP_DISPOSITION_UNRESOLVED
        and g.gap_class not in (GAP_CLASS_SHALLOW, GAP_CLASS_TERMINAL))
    has_unresolved_internal = bool(unresolved_internal)
    if n_long > 0:
        reasons.append(REASON_INTERNAL_GAP_EXCEEDS_LIMIT)
    if any(g.gap_class != GAP_CLASS_LONG_INTERNAL for g in unresolved_internal):
        reasons.append(REASON_INTERNAL_GAP_UNRESOLVED)

    terminal = next((g for g in gap_result.gaps if g.gap_class == GAP_CLASS_TERMINAL), None)
    if terminal is not None and (terminal.thickness_tvd_m or 0.0) > 0.0:
        reasons.append(REASON_TERMINAL_COLUMN_UNRESOLVED)

    shallow = next((g for g in gap_result.gaps if g.gap_class == GAP_CLASS_SHALLOW), None)
    shallow_thickness = None if shallow is None else shallow.thickness_tvd_m
    shallow_unresolved = (
        seabed_resolved and shallow_thickness is not None
        and shallow_thickness > config.shallow_gap_tolerance_tvd_m)
    if shallow_unresolved:
        reasons.append(REASON_SHALLOW_COLUMN_UNRESOLVED)

    n_eligible = int(stats.n_eligible)
    if n_eligible < config.min_eligible_samples_for_increment or profile is None:
        reasons.append(REASON_INSUFFICIENT_ELIGIBLE_SAMPLES)
        status = STATUS_NOT_ELIGIBLE
    elif not seabed_resolved:
        status = STATUS_PARTIAL_ONLY
    elif shallow_unresolved or (
            has_unresolved_internal and config.absolute_requires_uninterrupted_column):
        status = STATUS_SENSITIVITY_ONLY
    else:
        status = STATUS_ABSOLUTE

    if status == STATUS_ABSOLUTE:
        # An absolute status admits no limiting reason. Any reason that
        # survived above but does not actually restrict the absolute integral
        # (a screening-bound failure among excluded samples, for instance)
        # would still be misleading here, so the absolute rung is granted only
        # when the reason list is genuinely empty.
        blocking = [r for r in reasons if r != REASON_TERMINAL_COLUMN_UNRESOLVED]
        if blocking:
            status = STATUS_SENSITIVITY_ONLY
        else:
            reasons = []

    water_thickness = (None if stats.seabed_tvdss_m is None
                       else max(0.0, float(stats.seabed_tvdss_m)))

    return OverburdenEligibility(
        well_key=stats.well_key,
        status=status,
        limiting_reasons=tuple(sorted(set(reasons))),
        seabed_resolved=seabed_resolved,
        seabed_basis=stats.seabed_basis,
        n_eligible_samples=n_eligible,
        n_bridged_samples=int(gap_result.n_bridged_samples),
        eligible_top_tvd_m=(None if profile is None else profile.top_tvd_m),
        eligible_base_tvd_m=(None if profile is None else profile.base_tvd_m),
        eligible_top_tvdss_m=(None if profile is None else profile.top_tvdss_m),
        eligible_base_tvdss_m=(None if profile is None else profile.base_tvdss_m),
        measured_thickness_tvd_m=(
            None if profile is None else profile.base_tvd_m - profile.top_tvd_m),
        shallow_unresolved_thickness_tvd_m=shallow_thickness,
        terminal_unresolved_thickness_tvd_m=(
            None if terminal is None else terminal.thickness_tvd_m),
        water_column_thickness_tvd_m=water_thickness,
        n_unresolved_internal_gaps=len(unresolved_internal),
        n_unresolved_long_gaps=n_long,
        unresolved_long_gap_thickness_tvd_m=float(gap_result.long_gap_thickness_tvd_m),
        column_uninterrupted=not has_unresolved_internal,
        measured_increment_pa=(
            None if profile is None else profile.total_measured_increment_pa),
        bridged_increment_pa=(
            None if profile is None else profile.total_bridged_increment_pa),
        absolute_stress_supported=(status == STATUS_ABSOLUTE),
    )


# ---------------------------------------------------------------------------
# Shallow-column screening scenarios
# ---------------------------------------------------------------------------

def build_shallow_column_scenarios(
    stats: DensityQcStats,
    eligibility: OverburdenEligibility,
    profile: Optional[VerticalStressProfile],
    config: OverburdenConfig,
) -> Tuple[ShallowColumnScenario, ...]:
    """Build the transparent low/base/high screening scenarios for ONE well.

    Returns an EMPTY tuple unless the well's derived status is
    `screening_sensitivity_only` - the only status for which the unmeasured
    column's thickness is known and can therefore be bracketed at all. A well
    whose seabed is unresolved produces no scenario, because bracketing an
    interval of unknown thickness would be arithmetic without content.

    Scenario endpoints, restated here because they govern what the numbers mean:

      low  = the configured seawater density. This is a conditional lower
             scenario only under a fully saturated-column assumption; the
             project does not establish the unknown interval's fluid state.
      high = the configured low percentile of the SAME WELL'S OWN measured
             eligible density population. This is an illustrative upper
             scenario motivated by monotonic-compaction reasoning, not a
             physical ceiling or rigorous uncertainty bound: no lithology,
             fluid-state or depth-dependent density model constrains it.
      base = the arithmetic midpoint. NO evidentiary support. It exists only
             so the bracket has a labelled centre, and it is never a result.

    Two further rows re-run the base case at the configured seawater-density
    bracket, so the reader can see how little of the spread comes from the
    seawater assumption and how much from the unmeasured sediment column.
    """
    if not config.scenarios_enabled:
        return ()
    if eligibility.status != STATUS_SENSITIVITY_ONLY:
        return ()
    if profile is None or stats.seabed_tvdss_m is None:
        return ()
    unresolved_thickness = eligibility.shallow_unresolved_thickness_tvd_m
    if unresolved_thickness is None or unresolved_thickness <= 0.0:
        return ()
    if stats.rhob_eligible_p05_kg_m3 is None:
        return ()

    g = float(config.gravity_m_s2)
    water_thickness = float(stats.seabed_tvdss_m)
    measured_thickness = float(profile.base_tvd_m - profile.top_tvd_m)
    measured_pa = float(profile.total_measured_increment_pa)
    bridged_pa = float(profile.total_bridged_increment_pa)
    # The measured formation contribution reported in the partition excludes
    # the conditioned part, which travels in its own component.
    measured_only_pa = max(0.0, measured_pa - bridged_pa)

    low_density = float(config.seawater_density_kg_m3)
    high_density = float(stats.rhob_eligible_p05_kg_m3)
    if high_density <= low_density:
        # The evidence does not support a bracket with a positive width: the
        # two selected scenario endpoints are inverted or degenerate. No
        # scenario is published rather than an inverted or degenerate one.
        return ()
    base_density = 0.5 * (low_density + high_density)

    plan: List[Tuple[str, float, str, float]] = [
        (SCENARIO_LOW, low_density, config_low_basis(), float(config.seawater_density_kg_m3)),
        (SCENARIO_BASE, base_density, config_base_basis(),
         float(config.seawater_density_kg_m3)),
        (SCENARIO_HIGH, high_density, config_high_basis(),
         float(config.seawater_density_kg_m3)),
        (SCENARIO_BASE_SEAWATER_LOW, base_density, config_base_basis(),
         float(config.seawater_density_low_kg_m3)),
        (SCENARIO_BASE_SEAWATER_HIGH, base_density, config_base_basis(),
         float(config.seawater_density_high_kg_m3)),
    ]

    out: List[ShallowColumnScenario] = []
    for name, density, basis, seawater in plan:
        water_pa = water_column_stress_pa(water_thickness, seawater, g)
        shallow_pa = uniform_column_stress_pa(unresolved_thickness, density, g,
                                              context=f"{stats.well_key}: shallow scenario")
        total = water_pa + measured_only_pa + bridged_pa + shallow_pa
        partition = StressPartition(
            water_column_pa=water_pa,
            measured_formation_pa=measured_only_pa,
            bridged_gap_pa=bridged_pa,
            unresolved_shallow_pa=shallow_pa,
            total_pa=total,
        )
        assumed = (water_pa + shallow_pa) / total if total > 0.0 else 0.0
        conditioned_fraction = bridged_pa / total if total > 0.0 else 0.0
        measured_fraction = measured_only_pa / total if total > 0.0 else 0.0
        out.append(ShallowColumnScenario(
            well_key=stats.well_key,
            scenario_name=name,
            assumed_shallow_density_kg_m3=density,
            assumed_density_basis=basis,
            seawater_density_kg_m3=seawater,
            gravity_m_s2=g,
            unresolved_thickness_tvd_m=float(unresolved_thickness),
            water_column_thickness_tvd_m=water_thickness,
            measured_thickness_tvd_m=measured_thickness,
            partition=partition,
            assumed_fraction_of_total=assumed,
            conditioned_fraction_of_total=conditioned_fraction,
            measured_fraction_of_total=measured_fraction,
        ))
    return tuple(out)


# ---------------------------------------------------------------------------
# Gap-threshold sensitivity
# ---------------------------------------------------------------------------

def build_gap_threshold_sensitivity(
    well_frame,
    masks,
    stats: DensityQcStats,
    config: OverburdenConfig,
    *,
    seabed_tvd_m: Optional[float] = None,
) -> Tuple["GapThresholdSensitivity", ...]:
    """Re-run gap conditioning, integration and status derivation at EVERY
    configured threshold, for ONE well.

    This is the mandatory sensitivity to the approved gap threshold. It exists
    so that a reader can see exactly what the approved threshold changed - how
    many gaps it bridged, how much stress that contributed, and whether it
    moved the derived status - rather than taking a single configured number
    on trust. The approved threshold is flagged in its own row; nothing here
    selects a preferred value.

    The import is local to avoid a module-level cycle: `density_qc` imports
    the shared models, and this function is the only place `overburden` needs
    the conditioning entry point.
    """
    from p2mem.density_qc import condition_density_gaps
    from p2mem.overburden_models import GapThresholdSensitivity

    out: List[GapThresholdSensitivity] = []
    for threshold in config.sensitivity_thresholds_tvd_m:
        gap_result = condition_density_gaps(
            well_frame, masks, config, seabed_tvd_m=seabed_tvd_m,
            threshold_tvd_m=float(threshold))
        profile = build_stress_profile(well_frame, masks, gap_result, config)
        eligibility = derive_overburden_eligibility(
            stats, masks, gap_result, profile, config)
        usable = int(np.count_nonzero(
            np.asarray(masks.eligible_for_measured_integration, dtype=bool)
            | np.asarray(gap_result.bridged_mask, dtype=bool)))
        out.append(GapThresholdSensitivity(
            well_key=well_frame.well_key,
            threshold_tvd_m=float(threshold),
            is_approved_threshold=bool(
                float(threshold) == float(config.short_gap_max_tvd_m)),
            n_bridged_gaps=int(gap_result.n_bridged_gaps),
            n_bridged_samples=int(gap_result.n_bridged_samples),
            bridged_thickness_tvd_m=float(gap_result.bridged_thickness_tvd_m),
            n_long_gaps=int(gap_result.n_long_gaps),
            long_gap_thickness_tvd_m=float(gap_result.long_gap_thickness_tvd_m),
            n_eligible_or_bridged_samples=usable,
            total_measured_increment_pa=(
                None if profile is None else profile.total_measured_increment_pa),
            bridged_increment_pa=(
                None if profile is None else profile.total_bridged_increment_pa),
            derived_status=eligibility.status,
        ))
    return tuple(out)


#: The three bracket bases, as enumerated tokens rather than prose. They are
#: emitted verbatim and are members of the Increment 7 controlled vocabulary.
def config_low_basis() -> str:
    return SCENARIO_BASIS_LOW


def config_base_basis() -> str:
    return SCENARIO_BASIS_BASE


def config_high_basis() -> str:
    return SCENARIO_BASIS_HIGH
