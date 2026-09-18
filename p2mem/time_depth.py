"""
p2mem.time_depth - Numerical checkshot conditioning, velocity diagnostics,
forward/inverse time-depth interpolation, checkshot-vs-survey depth
comparison, and the Poseidon-2-only sonic-checkshot drift diagnostic
(Increment 4).

Scope
-----
This module is pure numerical computation on already-parsed checkshot
arrays (see `p2mem.io.checkshot` for file I/O and contract resolution) and
already-loaded LAS/deviation-survey arrays (see `p2mem.io.las` /
`p2mem.io.deviation`, both LOCKED and unmodified). It does not read files
and does not decide which files are approved for which well - it takes
typed/plain NumPy inputs and returns typed, documented results.

Why this module exists separately from `p2mem.depth_mapping`
-----------------------------------------------------------------
The locked Increment 3 `p2mem.depth_mapping.map_las_md_to_tvd_tvdss` is an
ALL-OR-NOTHING design: `ExtrapolationRejectedError` is raised if even one
LAS sample falls outside survey MD coverage. That is the correct policy
for MD->TVD/TVDSS mapping against a full-well deviation survey (extending
a trajectory beyond its last surveyed station is not defensible).
Checkshot coverage is different in kind: Poseidon 2's checkshot Depth
range (1267.8-4700.0 m) is a genuine PARTIAL subset of its LAS MD
interval, by the nature of when/how checkshot surveys are acquired - this
is an expected, disclosed coverage gap, not an error condition. Increment
4 therefore requires LAS samples outside checkshot coverage to be
reported as out-of-coverage (via an explicit mask and count) and mapped
to NaN, never rejected outright and never extrapolated. `map_las_md_to_
checkshot_time` below is consequently a NEW, separate function with a
coverage-masking contract, deliberately different from `depth_mapping
.py`'s reject-on-any-extrapolation contract - not a modification of the
locked module.

Interpolation method
----------------------
Every interpolation in this module is transparent PIECEWISE-LINEAR
(`numpy.interp`), never a higher-order spline, per the project's stated
preference for transparency over curve smoothness. No interpolation here
ever extrapolates: every function reports (and NaNs) samples outside the
validated coverage of the axis being interpolated against, explicitly.

Duplicate-tie conditioning policy
------------------------------------
Real checkshot files in this project contain REPEATED Depth values
(distinct rows sharing an identical Depth but slightly different TVDSS/
OWT - see `detect_and_condition_depth_ties`). These are acquisition
artifacts (e.g. a repeated tie-in shot), not measurement noise to be
smoothed. Every raw row is preserved exactly in `CheckshotStationData`;
this module never overwrites the raw arrays. A SEPARATE "conditioned"
representation is built by collapsing each repeated-Depth group to one
deterministic representative row before any interpolation is attempted -
`numpy.interp` requires a monotonic (here, strictly increasing) x-axis,
which raw duplicate-Depth data does not provide.

The representative for a tied group's TVDSS (and, independently, its OWT)
is that group's MEDIAN value. Median is used, rather than an arbitrary
"first" or "last" row, because it is order-independent (does not silently
depend on which duplicate happened to be typed/exported first) and
generalizes correctly to a group of any size. It is disclosed here that
for a group of exactly 2 rows (every duplicate group observed in this
project's three approved checkshot files has exactly 2 rows), the median
of 2 values equals their arithmetic mean - this is a documented,
deterministic consequence of the chosen rule, not an undisclosed
"averaging" of ties: the raw rows remain fully preserved and individually
registered (see `DuplicateTieRegisterEntry`), and TVDSS/OWT are each
conditioned independently (so the conditioned row's TVDSS and OWT are not
guaranteed to have both come from the same original raw row - disclosed
here explicitly). No artificial epsilon separation is ever injected to
force strict monotonicity beyond what the median rule itself produces;
where the median rule still leaves a non-strictly-increasing step in a
TVDSS or OWT axis used for TIME-domain (inverse) interpolation, that is
handled and disclosed separately - see "Locally non-unique inversion"
below.

Order-invariant axis-tie conditioning (Increment 4.1)
---------------------------------------------------------
Depth-domain forward interpolation (`depth_to_tvdss`, `depth_to_owt`,
`depth_to_twt`, `map_las_md_to_checkshot_time`) is always well-defined
after Depth-tie conditioning, because `Depth_conditioned_m` is strictly
increasing by construction (one representative row per distinct Depth
value). TVDSS and OWT are each conditioned independently of Depth,
however, and are NOT guaranteed strictly increasing after Depth-tie
conditioning alone: real, distinct Depth values in this project's actual
files carry an equal TVDSS or OWT at adjacent depths (e.g. Poseidon 2 has
two such TVDSS ties and two such OWT ties after Depth-tie conditioning;
Boreas 1 has one TVDSS tie and zero OWT ties; Proteus 1ST2 has none of
either - see `INCREMENT_04_1_MANIFEST.md` for the exact, independently
reproduced counts and the corrected statement of this fact. An earlier
statement in `INCREMENT_04_MANIFEST.md` that TVDSS was strictly
increasing after conditioning for all three wells was INCORRECT and has
been corrected there and here.)

TIME-domain interpolation (`tvdss_to_owt`, `owt_to_tvdss`, and their TWT
equivalents) requires the axis being interpolated FROM (TVDSS or OWT) to
itself be strictly increasing - `numpy.interp` does not detect a
non-monotonic axis and will silently return nonsense for one. Increment
4's original resolution (`_build_strictly_increasing_table`, REMOVED in
this patch) kept whichever tied row happened to appear first in the
Depth-conditioned table and silently discarded the other: deterministic,
but an ORDER-DEPENDENT tie-break - a file whose two tied rows were
supplied in the opposite relative order would silently resolve to a
different inverse value, and the discarded row's information vanished
with no audit trail beyond a bare count.

`build_axis_conditioned_lookup_table` replaces this with an explicit,
ORDER-INVARIANT policy: every value tied on the axis being inverted is
grouped (regardless of which tied row was parsed first), the group's
COMPLETE original rows are preserved in a typed audit register
(`AxisTimeDepthTieRegisterEntry` - separate from, and never confused
with, the raw checkshot data or the Depth-conditioned table), and the
group's dependent-value MEDIAN becomes the conditioned representative
(order-invariant, and disclosed as reducing to the arithmetic mean for a
tied group of size 2 - the only size observed in this project's real
data). A group whose tied rows also share an IDENTICAL dependent value
(`tie_kind="identical_pair"`) collapses without changing the value, but
is still counted and registered, never silently merged away unrecorded.
A GENUINE reversal in the axis being inverted (a group's value less than
the preceding group's - not a tie) raises `TimeDepthError`: this function
never sorts, greedily discards, or forces monotonicity to make a
reversal disappear. The resulting `AxisConditionedLookupTable` is never
described as raw, uniquely measured, or unconditioned - the median
representative is a screening-level choice, not proof that the original
TVDSS<->OWT relationship was single-valued at every tied axis value.

Numerical-validation corrective patch (Increment 4.1.1)
-------------------------------------------------------
An independent numerical-validation audit of Increment 4.1 found four
blocking defects in the reversal/validation logic described above and in
`compute_sonic_checkshot_drift`/`compare_checkshot_to_survey`, plus an
input-safety gap in `seconds_to_milliseconds`/`milliseconds_to_seconds`.
None of these defects altered any previously verified REAL Poseidon
2/Boreas 1/Proteus 1ST2 result - all such results are reproduced exactly
in this patch - they were latent gaps that a specific, previously
untested input shape could have triggered.

1. Hidden reversal via global exact-value grouping (`build_axis_
   conditioned_lookup_table`). The Increment 4.1 implementation grouped
   ALL occurrences of an identical axis value together, globally, before
   checking for a reversal - so `[100.0, 200.0, 100.0]` was incorrectly
   accepted (the trailing `100.0` silently merged into the first group,
   producing an apparently-valid `[100.0, 200.0]` and hiding the genuine
   `200 -> 100` reversal). Fixed by evaluating `np.diff` of the ORIGINAL,
   ungrouped axis sequence for any negative step BEFORE grouping is
   attempted; only once the original sequence is confirmed non-decreasing
   are exact ADJACENT ties grouped and median-conditioned, exactly as in
   4.1. This is provably equivalent to the 4.1 behavior for every
   legitimate adjacent tie (once no negative diff exists anywhere in the
   original sequence, any two occurrences of the same value are
   necessarily adjacent - a non-adjacent repeat would require descending
   back down to that value after a strictly larger one, which is exactly
   the negative diff already excluded) and strictly stronger against a
   reversal that returns to an already-seen value. `depth_conditioned_m`
   is also now validated finite and strictly increasing on entry.
2. Incomplete MD validation in the sonic-checkshot integration path
   (`compute_sonic_checkshot_drift`, `find_longest_finite_positive_run`).
   Increment 4.1 validated strict MD monotonicity only WITHIN the
   selected finite-positive-VP run, so a decreasing or duplicate MD value
   at a station outside that run (e.g. one with `VP_m_s=NaN`) could pass
   silently. Fixed by requiring the COMPLETE canonical `md_m` array to be
   one-dimensional, finite, strictly increasing, and free of duplicates
   BEFORE run-selection; `find_longest_finite_positive_run` also now
   validates compatible one-dimensional shapes when called directly. The
   real Poseidon 2 canonical MD array (31,897 samples) was independently
   re-verified fully finite and strictly increasing across its ENTIRE
   length, so this stricter check does not alter the real sonic-drift
   result.
3. Untyped crash on zero survey-coverage overlap (`compare_checkshot_to_
   survey`). If every checkshot Depth row fell outside the locked
   survey's own MD coverage, NumPy's `min`/`max`/`mean` reductions on the
   resulting empty residual array raised an untyped
   `ValueError: zero-size array to reduction operation ...` rather than a
   documented, typed failure. Fixed by explicitly checking for zero
   in-coverage rows and raising `TimeDepthError` naming the well key, the
   checkshot Depth range, and the survey MD coverage, and stating plainly
   that no comparison was performed and no extrapolation was attempted.
4. Missing batch isolation for numerical failures (`p2mem.io.checkshot.
   load_checkshot_surveys`). Only file/parsing/contract errors were
   caught per well; a `TimeDepthError` raised during Depth-tie
   conditioning, axis-tie conditioning, or survey comparison for one well
   would propagate out of the batch loader and stop every other well from
   loading, contradicting this project's documented batch-isolation
   guarantee. Fixed by catching `TimeDepthError` per well (never via a
   blanket `except Exception`) and recording a typed
   `CheckshotIngestionFailure(error_type="numerical_conditioning_
   failure")`, exactly like every other expected per-well failure mode.
5. Unit-helper input-safety gap (`seconds_to_milliseconds`,
   `milliseconds_to_seconds`). These Increment-4 helpers coerced their
   input with `np.asarray(..., dtype=np.float64)` directly, unlike
   `p2mem.units`'s Increment-1 policy, so a boolean, a numeric-looking
   string (or string array), or a complex value would be silently
   reinterpreted rather than rejected. Fixed with a local
   `_reject_ambiguous_dtype` check (a deliberate, documented LOCAL copy of
   `p2mem.units`'s identical private check - `p2mem/units.py` is LOCKED
   and this project's convention is never to import a private/
   underscore-prefixed name across a module boundary) applied to the raw
   input's dtype before any numeric coercion.

See `INCREMENT_04_1_1_MANIFEST.md` for the full defect writeup, the
required regression-test list, and the distinction this patch draws
between a valid adjacent tie, a globally repeated (non-adjacent) value, a
genuine negative successive-axis step, median conditioning, and numerical
rejection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np

from p2mem.checkshot_models import (
    AxisConditionedLookupTable,
    AxisTimeDepthTieRegisterEntry,
    ConditionedCheckshotData,
    CheckshotSurveyDepthComparisonResult,
    DuplicateTieRegisterEntry,
    SonicCheckshotDriftResult,
    TimeDepthMappingSummary,
    VelocityDiagnosticsResult,
)
from p2mem.units import owt_to_twt, twt_to_owt

__all__ = [
    "TimeDepthError",
    "CONDITIONING_METHOD",
    "AXIS_TIE_CONDITIONING_METHOD",
    "INTERPOLATION_METHOD",
    "INTEGRATION_METHOD",
    "seconds_to_milliseconds",
    "milliseconds_to_seconds",
    "trapezoidal_integrate",
    "detect_and_condition_depth_ties",
    "compute_velocity_diagnostics",
    "compare_checkshot_to_survey",
    "depth_to_tvdss",
    "depth_to_owt",
    "depth_to_twt",
    "build_axis_conditioned_lookup_table",
    "build_axis_conditioned_tables_for_well",
    "tvdss_to_owt",
    "tvdss_to_twt",
    "owt_to_tvdss",
    "twt_to_tvdss",
    "map_las_md_to_checkshot_time",
    "find_longest_finite_positive_run",
    "compute_sonic_checkshot_drift",
]

CONDITIONING_METHOD = "duplicate_depth_median_representative_v1"
AXIS_TIE_CONDITIONING_METHOD = "axis_tie_median_representative_order_invariant_v1"
INTERPOLATION_METHOD = "piecewise_linear_no_extrapolation"
INTEGRATION_METHOD = "trapezoidal_rule_on_slowness_vs_md"


class TimeDepthError(ValueError):
    """
    Raised for a structural/numerical precondition failure in this module:
    fewer than 2 conditioned rows, a non-finite input array, a shape/
    length mismatch, a non-strictly-increasing axis where one is required
    (including a genuine reversal in an axis-tie-conditioned lookup table
    - see `build_axis_conditioned_lookup_table` - which this module never
    resolves by sorting, discarding, or forcing monotonicity), a sonic
    interval too short (or insufficiently well-behaved - decreasing/
    duplicate/non-finite MD) to integrate, a non-positive checkshot OWT
    increment, or a drift-comparison endpoint falling outside checkshot
    Depth coverage (this module never extrapolates to satisfy a request).
    """


# ---------------------------------------------------------------------------
# Shared numerical-validation helpers (Increment 4.1 hardening)
# ---------------------------------------------------------------------------
def _as_1d_finite(label: str, arr) -> np.ndarray:
    """Coerce `arr` to a NumPy float64 array and require it be
    one-dimensional and fully finite (no NaN/inf); raise `TimeDepthError`
    (naming `label`) otherwise."""
    a = np.asarray(arr, dtype=np.float64)
    if a.ndim != 1:
        raise TimeDepthError(f"{label} must be a one-dimensional array; got shape {a.shape}.")
    if a.size == 0:
        raise TimeDepthError(f"{label} must not be empty.")
    if not np.all(np.isfinite(a)):
        raise TimeDepthError(f"{label} contains a non-finite value (NaN or inf).")
    return a


def _require_equal_length(pairs) -> None:
    """`pairs` is an iterable of (label, array). Raise `TimeDepthError`
    naming every label if the arrays do not all share one length."""
    lengths = {label: int(np.shape(a)[0]) if np.ndim(a) else 0 for label, a in pairs}
    if len(set(lengths.values())) > 1:
        raise TimeDepthError(f"arrays must share one length; got {lengths}.")


def _reject_ambiguous_dtype(raw: np.ndarray, context: str) -> None:
    """
    Reject input kinds that are not genuine numeric scalars/arrays,
    mirroring the input-safety policy `p2mem.units` established in
    Increment 1 (Increment 4.1.1 audit finding: `seconds_to_milliseconds`/
    `milliseconds_to_seconds`, added in Increment 4 as thin local helpers
    - see the module docstring - had never been checked against that
    policy and would otherwise silently coerce a boolean to 1.0/0.0, a
    numeric-looking string to a float, or a complex value with its
    imaginary part discarded).

    This is a LOCAL copy of the identical dtype-kind check performed by
    `p2mem.units._reject_ambiguous_dtype` (that module's own version is
    private and is not imported here, since `p2mem/units.py` is LOCKED
    and this project's convention is never to import a private/
    underscore-prefixed name across module boundaries) - not a
    reimplementation of different behavior. Only integer- or floating-
    dtype input is accepted; boolean, string/bytes, complex, and object
    dtypes all raise `TypeError`.
    """
    kind = raw.dtype.kind
    if kind == "b":
        raise TypeError(
            f"{context}: boolean input is not accepted (True/False would be "
            f"silently reinterpreted as 1.0/0.0). Pass a numeric value instead."
        )
    if kind in ("U", "S"):
        raise TypeError(
            f"{context}: string input is not accepted, even a numeric-looking "
            f"string (e.g. \"3.5\"). Pass a numeric value instead."
        )
    if kind == "c":
        raise TypeError(
            f"{context}: complex input is not accepted (this module handles "
            f"only real-valued physical quantities). Pass a real numeric value instead."
        )
    if kind not in ("i", "u", "f"):
        raise TypeError(
            f"{context}: unsupported input type (dtype={raw.dtype!r}). "
            f"Only Python numeric scalars and NumPy integer/floating arrays are accepted."
        )


def _require_strictly_increasing(label: str, arr: np.ndarray) -> None:
    """Raise `TimeDepthError` (naming `label` and the offending interval
    index/indices) if `arr` (size >= 2) is not strictly increasing.
    Never sorts, discards, or otherwise repairs `arr` - a genuine
    reversal or a tie in a context requiring strict monotonicity is
    always reported, never silently resolved."""
    if arr.size < 2:
        return
    diffs = np.diff(arr)
    if not np.all(diffs > 0.0):
        bad = np.where(diffs <= 0.0)[0].tolist()
        raise TimeDepthError(
            f"{label} is not strictly increasing at interval index(es) {bad}; this function "
            f"never sorts, discards, or forces monotonicity to resolve a tie or reversal here."
        )


# ---------------------------------------------------------------------------
# Trivial, locally-scoped unit helpers (seconds <-> milliseconds).
# Not added to the LOCKED p2mem.units module - see project instructions:
# only p2mem/__init__.py, pyproject.toml, README.md may be touched among
# existing files for Increment 4.
# ---------------------------------------------------------------------------
def seconds_to_milliseconds(seconds: np.ndarray) -> np.ndarray:
    """
    TWT_ms = TWT_s * 1000 (exact scaling; NaN preserved).

    Validated (Increment 4.1.1 audit finding - unit-helper input
    consistency): this helper was added in Increment 4 as a thin local
    scaling function and, unlike `p2mem.units`, had never been checked
    against the input-safety policy established in Increment 1. Before
    this fix, `np.asarray(seconds, dtype=np.float64)` would silently
    coerce a boolean (`True`/`False` -> `1.0`/`0.0`), a numeric-looking
    string or string array (e.g. `"3.5"`), or a complex value (silently
    discarding its imaginary part) into a float, rather than raising.
    `_reject_ambiguous_dtype` (a local copy of `p2mem.units`'s identical,
    private, un-imported check - see that function's docstring) is now
    called on the raw input's dtype before any numeric coercion, so
    boolean/string/complex input raises `TypeError`. Python numeric
    scalars, NumPy integer/floating arrays, and NaN values are accepted
    exactly as before.
    """
    raw = np.asarray(seconds)
    _reject_ambiguous_dtype(raw, "seconds_to_milliseconds: seconds")
    return raw.astype(np.float64) * 1000.0


def milliseconds_to_seconds(milliseconds: np.ndarray) -> np.ndarray:
    """
    TWT_s = TWT_ms / 1000 (exact scaling; NaN preserved).

    Validated (Increment 4.1.1 audit finding - unit-helper input
    consistency): see `seconds_to_milliseconds`'s docstring above for the
    full rationale. The same `_reject_ambiguous_dtype` guard is applied
    here before numeric coercion, so boolean/string/complex input raises
    `TypeError` while valid Python numeric scalars, NumPy integer/
    floating arrays, and NaN values are accepted exactly as before.
    """
    raw = np.asarray(milliseconds)
    _reject_ambiguous_dtype(raw, "milliseconds_to_seconds: milliseconds")
    return raw.astype(np.float64) / 1000.0


def trapezoidal_integrate(y: np.ndarray, x: np.ndarray) -> float:
    """
    Manual trapezoidal-rule integration of `y` against `x`
    (sum of (y[i]+y[i+1])/2 * (x[i+1]-x[i]) over all i), implemented
    locally rather than via `numpy.trapz`/`numpy.trapezoid` so this
    module's numerical behavior does not depend on which of those two
    (mutually exclusive across NumPy versions - `trapz` was removed in
    NumPy 2.0 in favor of `trapezoid`) happens to be available in a given
    execution environment (including Google Colab).

    Validated (Increment 4.1 hardening - the pre-4.1 implementation
    performed none of this and could silently integrate garbage,
    including returning a physically invalid NEGATIVE "transit time" for
    a decreasing `x`): `x` and `y` must each be one-dimensional, finite,
    and of equal length; at least 2 samples are required; and `x` must be
    STRICTLY increasing (a decreasing or duplicate-value `x` raises
    `TimeDepthError` rather than being silently integrated, sorted, or
    otherwise repaired). This validation does not change the arithmetic
    performed on already-valid input - the real Poseidon 2 sonic-drift
    result in `INCREMENT_04_1_MANIFEST.md` is bit-for-bit unchanged from
    Increment 4's.
    """
    x = _as_1d_finite("trapezoidal_integrate: x", x)
    y = _as_1d_finite("trapezoidal_integrate: y", y)
    _require_equal_length([("x", x), ("y", y)])
    if x.size < 2:
        raise TimeDepthError("trapezoidal_integrate: at least 2 samples are required to integrate.")
    _require_strictly_increasing("trapezoidal_integrate: x", x)
    dx = np.diff(x)
    avg = (y[:-1] + y[1:]) / 2.0
    return float(np.sum(avg * dx))


# ---------------------------------------------------------------------------
# Duplicate-tie detection and conditioning
# ---------------------------------------------------------------------------
def detect_and_condition_depth_ties(
    well_key: str,
    depth_source_m: np.ndarray,
    tvdss_source_m: np.ndarray,
    owt_source_s: np.ndarray,
) -> Tuple[Tuple[DuplicateTieRegisterEntry, ...], ConditionedCheckshotData]:
    """
    Group raw rows by exact `Depth_source_m` value (in order of first
    appearance), register every group of size > 1 as a
    `DuplicateTieRegisterEntry`, and build the conditioned representation
    (one row per distinct Depth, using the tied group's median TVDSS/OWT
    as its representative - see module docstring). Singleton groups pass
    through unchanged; `Depth_conditioned_m` is returned strictly
    increasing by construction whenever `depth_source_m` visits each
    distinct value in non-decreasing order overall (verified: raises
    `TimeDepthError` if a distinct Depth value re-appears out of the
    surrounding sort order, which would indicate a genuinely unsorted or
    corrupted source file, not an ordinary repeated tie-in).
    """
    depth_source_m = np.asarray(depth_source_m, dtype=np.float64)
    tvdss_source_m = np.asarray(tvdss_source_m, dtype=np.float64)
    owt_source_s = np.asarray(owt_source_s, dtype=np.float64)
    n = depth_source_m.size
    if not (tvdss_source_m.size == n and owt_source_s.size == n):
        raise TimeDepthError(
            f"{well_key}: Depth/TVDSS/OWT source arrays must share one length; got "
            f"{n}, {tvdss_source_m.size}, {owt_source_s.size}."
        )
    if n == 0:
        raise TimeDepthError(f"{well_key}: checkshot source arrays are empty.")
    for _name, _arr in (
        ("Depth_source_m", depth_source_m),
        ("TVDSS_source_m", tvdss_source_m),
        ("OWT_source_s", owt_source_s),
    ):
        if not np.all(np.isfinite(_arr)):
            raise TimeDepthError(
                f"{well_key}: {_name} contains a non-finite value (NaN or inf); this function "
                f"never conditions or interpolates against non-finite source data."
            )

    groups: Dict[float, list] = {}
    order: list = []
    for i, d in enumerate(depth_source_m):
        if d not in groups:
            groups[d] = []
            order.append(d)
        groups[d].append(i)

    ties: list = []
    cond_depth: list = []
    cond_tvdss: list = []
    cond_owt: list = []

    for d in order:
        idxs = tuple(groups[d])
        tvdss_group = tvdss_source_m[list(idxs)]
        owt_group = owt_source_s[list(idxs)]
        rep_tvdss = float(np.median(tvdss_group))
        rep_owt = float(np.median(owt_group))
        cond_depth.append(d)
        cond_tvdss.append(rep_tvdss)
        cond_owt.append(rep_owt)

        if len(idxs) > 1:
            spread_tvdss = float(np.max(tvdss_group) - np.min(tvdss_group))
            spread_owt = float(np.max(owt_group) - np.min(owt_group))
            ties.append(
                DuplicateTieRegisterEntry(
                    well_key=well_key,
                    axis="Depth",
                    tie_value_m=float(d),
                    source_row_indices=idxs,
                    original_tvdss_m=tuple(float(v) for v in tvdss_group),
                    original_owt_s=tuple(float(v) for v in owt_group),
                    duplicate_type="repeated_depth_distinct_tvdss_owt",
                    group_size=len(idxs),
                    tvdss_value_spread_m=spread_tvdss,
                    owt_value_spread_s=spread_owt,
                    selected_representative_tvdss_m=rep_tvdss,
                    selected_representative_owt_s=rep_owt,
                    conditioning_rule=(
                        "median of the tied group's TVDSS values (independently, median of "
                        "its OWT values); for this group's size "
                        f"({len(idxs)}), median "
                        + ("equals the arithmetic mean." if len(idxs) % 2 == 0 else "is the middle value.")
                    ),
                    affected_downstream_outputs=(
                        "conditioned_time_depth_curve",
                        "velocity_diagnostics",
                        "forward_inverse_interpolation",
                    ),
                )
            )

    cond_depth_arr = np.asarray(cond_depth, dtype=np.float64)
    cond_tvdss_arr = np.asarray(cond_tvdss, dtype=np.float64)
    cond_owt_arr = np.asarray(cond_owt, dtype=np.float64)

    if cond_depth_arr.size > 1 and not np.all(np.diff(cond_depth_arr) > 0.0):
        bad = np.where(np.diff(cond_depth_arr) <= 0.0)[0].tolist()
        raise TimeDepthError(
            f"{well_key}: conditioned Depth values are not strictly increasing at "
            f"interval index(es) {bad}; this indicates the source file's distinct Depth "
            f"values are not presented in non-decreasing order (not an ordinary repeated "
            f"tie-in) and cannot be safely conditioned by this function."
        )

    conditioned = ConditionedCheckshotData(
        Depth_conditioned_m=cond_depth_arr,
        TVDSS_conditioned_m=cond_tvdss_arr,
        OWT_conditioned_s=cond_owt_arr,
        n_raw_rows=n,
        n_conditioned_rows=int(cond_depth_arr.size),
        n_tie_groups=len(ties),
        conditioning_method=CONDITIONING_METHOD,
    )
    return tuple(ties), conditioned


# ---------------------------------------------------------------------------
# Velocity diagnostics
# ---------------------------------------------------------------------------
def compute_velocity_diagnostics(
    well_key: str, conditioned: ConditionedCheckshotData
) -> VelocityDiagnosticsResult:
    """
    Vavg_m_s = TVDSS_conditioned_m / OWT_conditioned_s at every conditioned
    row (NaN if OWT <= 0, which does not occur in any admitted file but is
    guarded rather than assumed).

    Vint_m_s[k] = (TVDSS[k+1]-TVDSS[k]) / (OWT[k+1]-OWT[k]) for the
    interval between conditioned rows k and k+1. NaN (never inf or a
    negative value) whenever either increment is <= 0 - this is the
    project's explicit "zero/negative delta-OWT must yield NaN + QC
    reason, never infinite/negative velocity" requirement. No smoothing is
    applied for visual/aesthetic purposes.
    """
    depth = conditioned.Depth_conditioned_m
    tvdss = conditioned.TVDSS_conditioned_m
    owt = conditioned.OWT_conditioned_s
    n = depth.size

    with np.errstate(divide="ignore", invalid="ignore"):
        vavg = np.where(owt > 0.0, tvdss / owt, np.nan)

    if n < 2:
        vint = np.zeros(0, dtype=np.float64)
        invalid_mask = np.zeros(0, dtype=bool)
    else:
        d_tvdss = np.diff(tvdss)
        d_owt = np.diff(owt)
        valid = (d_tvdss > 0.0) & (d_owt > 0.0)
        with np.errstate(divide="ignore", invalid="ignore"):
            vint = np.where(valid, d_tvdss / d_owt, np.nan)
        invalid_mask = ~valid

    reason_counts = {
        "non_positive_delta_owt": int(np.sum((np.diff(owt) <= 0.0)) if n >= 2 else 0),
        "non_positive_delta_tvdss": int(np.sum((np.diff(tvdss) <= 0.0)) if n >= 2 else 0),
    }

    return VelocityDiagnosticsResult(
        well_key=well_key,
        Depth_conditioned_m=depth,
        Vavg_m_s=vavg,
        Vint_m_s=vint,
        vint_invalid_mask=invalid_mask,
        n_vint_intervals=int(vint.size),
        n_vint_invalid=int(np.sum(invalid_mask)),
        vint_invalid_reason_counts=reason_counts,
    )


# ---------------------------------------------------------------------------
# Checkshot-vs-locked-survey depth-reference comparison
# ---------------------------------------------------------------------------
def _describe_residual_trend(depth: np.ndarray, residual: np.ndarray) -> str:
    if residual.size < 2:
        return "insufficient compared points to characterize a trend"
    std_resid = float(np.std(residual))
    rng = float(np.max(residual) - np.min(residual))
    if np.std(depth) > 0.0 and np.std(residual) > 0.0:
        r = float(np.corrcoef(depth, residual)[0, 1])
        slope = float(np.polyfit(depth, residual, 1)[0])
    else:
        r = 0.0
        slope = 0.0
    if std_resid < 0.02:
        return (
            f"near-constant residual across the compared depth interval "
            f"(standard deviation {std_resid:.4f} m, range {rng:.4f} m)"
        )
    if abs(r) > 0.6:
        direction = "increases" if slope > 0 else "decreases"
        return (
            f"residual {direction} approximately linearly with depth "
            f"(slope {slope:.3e} m/m, correlation r={r:.3f}, standard deviation {std_resid:.4f} m)"
        )
    return (
        f"residual does not show a strong monotonic trend with depth "
        f"(standard deviation {std_resid:.4f} m, correlation r={r:.3f})"
    )


def compare_checkshot_to_survey(
    well_key: str,
    depth_source_m: np.ndarray,
    tvdss_source_m: np.ndarray,
    survey_md_m: np.ndarray,
    survey_tvd_m: np.ndarray,
    datum_elevation_m: float,
    *,
    depth_basis_interpretation_status: str,
) -> CheckshotSurveyDepthComparisonResult:
    """
    Compare checkshot `Depth_source_m` (as a CANDIDATE MD axis) against
    TVDSS interpolated from the locked survey MD->TVD relationship for the
    same well (`survey_md_m`, `survey_tvd_m` - the Petrel `petrel_source_
    trace`, e.g. `DeviationWellResult.raw.MD_source_m` /
    `.TVD_source_m`), converting TVD to TVDSS via `datum_elevation_m`
    (`DeviationWellResult.header.datum_elevation_m`).

    Sign convention: residual_m = TVDSS_survey_interpolated_m -
    TVDSS_source_m (see `CheckshotSurveyDepthComparisonResult` docstring).
    Only checkshot rows whose Depth falls within the survey's own MD
    coverage are compared; rows outside that coverage are counted
    (`n_outside_survey_md_coverage`) but never extrapolated against.

    Validated (Increment 4.1.1 hardening - Blocking Defect 3): if EVERY
    checkshot `depth_source_m` row falls outside the survey's own MD
    coverage, there are zero rows left to compare and no residual
    statistic (min/max/mean/median/RMSE) can be computed - the pre-4.1.1
    implementation reached NumPy's `min`/`max`/`mean` reductions on an
    empty array in this case, raising an untyped `ValueError` ("zero-size
    array to reduction operation minimum which has no identity") instead
    of this module's own typed `TimeDepthError`. This is now detected
    explicitly and raises `TimeDepthError` naming the well, the
    checkshot's own Depth range, the survey's MD coverage, and stating
    plainly that no comparison was performed and no extrapolation was
    attempted - never a bare NumPy exception, and never a silently
    empty/NaN result.
    """
    depth_source_m = _as_1d_finite(f"{well_key}: compare_checkshot_to_survey: depth_source_m", depth_source_m)
    tvdss_source_m = _as_1d_finite(f"{well_key}: compare_checkshot_to_survey: tvdss_source_m", tvdss_source_m)
    survey_md_m = _as_1d_finite(f"{well_key}: compare_checkshot_to_survey: survey_md_m", survey_md_m)
    survey_tvd_m = _as_1d_finite(f"{well_key}: compare_checkshot_to_survey: survey_tvd_m", survey_tvd_m)
    _require_equal_length(
        [("depth_source_m", depth_source_m), ("tvdss_source_m", tvdss_source_m)]
    )
    _require_equal_length([("survey_md_m", survey_md_m), ("survey_tvd_m", survey_tvd_m)])

    if survey_md_m.size < 2 or not np.all(np.diff(survey_md_m) > 0.0):
        raise TimeDepthError(
            f"{well_key}: locked survey MD array is not strictly increasing; cannot "
            f"interpolate a well-defined MD->TVDSS relationship."
        )

    survey_tvdss_m = survey_tvd_m - float(datum_elevation_m)
    md_min, md_max = float(survey_md_m[0]), float(survey_md_m[-1])
    inside = (depth_source_m >= md_min) & (depth_source_m <= md_max)
    n_outside = int(np.sum(~inside))

    if not np.any(inside):
        checkshot_min, checkshot_max = float(np.min(depth_source_m)), float(np.max(depth_source_m))
        raise TimeDepthError(
            f"{well_key}: compare_checkshot_to_survey: every checkshot Depth_source_m row "
            f"falls outside the locked survey's own MD coverage - no comparison was "
            f"performed and no extrapolation was attempted. Checkshot Depth range: "
            f"[{checkshot_min:.4f}, {checkshot_max:.4f}] m. Survey MD coverage: "
            f"[{md_min:.4f}, {md_max:.4f}] m."
        )

    depth_in = depth_source_m[inside]
    tvdss_survey_interp = np.interp(depth_in, survey_md_m, survey_tvdss_m)
    residual = tvdss_survey_interp - tvdss_source_m[inside]

    return CheckshotSurveyDepthComparisonResult(
        well_key=well_key,
        n_compared=int(depth_in.size),
        n_outside_survey_md_coverage=n_outside,
        min_residual_m=float(np.min(residual)),
        max_residual_m=float(np.max(residual)),
        max_abs_residual_m=float(np.max(np.abs(residual))),
        mean_residual_m=float(np.mean(residual)),
        median_residual_m=float(np.median(residual)),
        rmse_m=float(np.sqrt(np.mean(residual**2))),
        first_residual_m=float(residual[0]) if residual.size else float("nan"),
        last_residual_m=float(residual[-1]) if residual.size else float("nan"),
        residual_trend_description=_describe_residual_trend(depth_in, residual),
        depth_basis_interpretation_status=depth_basis_interpretation_status,
        residual_sign_convention="residual_m = TVDSS_survey_interpolated_m - TVDSS_source_m",
    )


# ---------------------------------------------------------------------------
# Depth-domain forward interpolation (always well-defined post-conditioning)
# ---------------------------------------------------------------------------
def _coverage_mask(query: np.ndarray, axis_min: float, axis_max: float) -> np.ndarray:
    return (query >= axis_min) & (query <= axis_max)


def _interp_with_coverage(
    query: np.ndarray, x: np.ndarray, y: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """Piecewise-linear interpolate `query` against strictly increasing `x`/`y`,
    returning (values with NaN outside [x[0], x[-1]], the coverage mask).

    Defensive validation (Increment 4.1): `x` and `y` must be finite,
    one-dimensional, equal-length, and `x` strictly increasing. Every
    caller in this module already guarantees this by construction
    (`ConditionedCheckshotData.Depth_conditioned_m` from
    `detect_and_condition_depth_ties`; `AxisConditionedLookupTable
    .axis_values` from `build_axis_conditioned_lookup_table`) - this is a
    second, independent line of defense against a future caller violating
    that contract, not a change to any currently-produced value.
    """
    x = _as_1d_finite("_interp_with_coverage: x", x)
    y = _as_1d_finite("_interp_with_coverage: y", y)
    _require_equal_length([("x", x), ("y", y)])
    _require_strictly_increasing("_interp_with_coverage: x", x)
    query = np.asarray(query, dtype=np.float64)
    mask = _coverage_mask(query, float(x[0]), float(x[-1]))
    out = np.full(query.shape, np.nan, dtype=np.float64)
    if np.any(mask):
        out[mask] = np.interp(query[mask], x, y)
    return out, mask


def depth_to_tvdss(depth_query, conditioned: ConditionedCheckshotData):
    """Depth -> TVDSS, piecewise-linear, NaN outside conditioned Depth coverage."""
    return _interp_with_coverage(
        np.atleast_1d(depth_query), conditioned.Depth_conditioned_m, conditioned.TVDSS_conditioned_m
    )


def depth_to_owt(depth_query, conditioned: ConditionedCheckshotData):
    """Depth -> OWT_source_s, piecewise-linear, NaN outside conditioned Depth coverage."""
    return _interp_with_coverage(
        np.atleast_1d(depth_query), conditioned.Depth_conditioned_m, conditioned.OWT_conditioned_s
    )


def depth_to_twt(depth_query, conditioned: ConditionedCheckshotData):
    """Depth -> TWT_s = 2 * (Depth -> OWT), via the LOCKED owt_to_twt conversion."""
    owt, mask = depth_to_owt(depth_query, conditioned)
    return owt_to_twt(owt), mask


# ---------------------------------------------------------------------------
# Time-domain forward/inverse interpolation: order-invariant axis-tie
# conditioning (Increment 4.1 - replaces the removed, order-dependent
# `_build_strictly_increasing_table` "keep first, drop later" logic)
# ---------------------------------------------------------------------------
def _group_by_exact_value(values: np.ndarray) -> Tuple[list, Dict[float, list]]:
    """Group indices of `values` by exact float equality, in order of
    first appearance (mirrors `detect_and_condition_depth_ties`'s own
    grouping logic, applied here to an axis-conditioned array instead of
    raw source data)."""
    groups: Dict[float, list] = {}
    order: list = []
    for i, v in enumerate(values):
        v = float(v)
        if v not in groups:
            groups[v] = []
            order.append(v)
        groups[v].append(i)
    return order, groups


def build_axis_conditioned_lookup_table(
    well_key: str,
    interpolation_direction: str,
    independent_axis_name: str,
    dependent_axis_name: str,
    depth_conditioned_m: np.ndarray,
    independent_values: np.ndarray,
    dependent_values: np.ndarray,
) -> Tuple[Tuple[AxisTimeDepthTieRegisterEntry, ...], AxisConditionedLookupTable]:
    """
    Build an order-invariant, axis-tie-conditioned lookup table for
    interpolating FROM `independent_values` (TVDSS or OWT, already
    Depth-tie conditioned - see `ConditionedCheckshotData`) TO
    `dependent_values` (the other of the two).

    Every value tied on `independent_values` is grouped by exact equality
    (regardless of which tied row appears first - this is the fix for the
    Increment 4 "keep first, drop later" order-dependence defect), its
    COMPLETE original rows are registered as one `AxisTimeDepthTieRegisterEntry`
    (never discarded unrecorded), and the group's `dependent_values`
    MEDIAN becomes that group's single conditioned representative -
    order-invariant, and disclosed as reducing to the arithmetic mean for
    a group of size 2. A group whose members ALSO share an identical
    dependent value (`tie_kind="identical_pair"`) still collapses to one
    row (its value is unchanged by taking the median of identical values)
    but is still counted and registered.

    Validated BEFORE any grouping is attempted (Increment 4.1.1 hardening
    - see "Reversal detection on the ORIGINAL sequence" below): the
    original, ungrouped `independent_values` sequence's successive
    differences must be non-negative everywhere (a tie, i.e. a zero
    difference, is allowed; a negative difference is a genuine reversal
    and raises `TimeDepthError` immediately, before grouping ever runs).
    After grouping, the resulting per-group `independent_values` sequence
    is additionally required to be STRICTLY increasing as a second,
    independent check; if it is not (which cannot actually occur once the
    pre-grouping check above has passed, since every tied value in a
    non-decreasing sequence is necessarily contiguous - see below), this
    function raises `TimeDepthError` rather than sorting, discarding, or
    forcing monotonicity. Real data from all three approved checkshot
    files, independently verified, contains only ties (zero-width
    intervals) at this stage, never a genuine reversal - see
    `INCREMENT_04_1_MANIFEST.md` / `INCREMENT_04_1_1_MANIFEST.md`.

    Reversal detection on the ORIGINAL sequence (Increment 4.1.1 fix)
    -------------------------------------------------------------------
    Increment 4.1's `_group_by_exact_value` groups every occurrence of a
    given axis value by EXACT equality regardless of its position in the
    array (this is what makes the median representative order-invariant
    for a genuine, adjacent tie). This has a defect: if the SAME axis
    value reappears after a LARGER value has already been seen (e.g.
    `[100.0, 200.0, 100.0]`), the global-equality grouping silently merges
    the first and third rows into one group, and the interior `200.0`
    simply disappears from the post-grouping array - `[100.0, 100.0,
    100.0]`'s grouped result is `[100.0]`, and `[100.0, 200.0, 100.0]`'s
    grouped result is `[100.0, 200.0]`, with no diff between adjacent
    output values ever exposing the `200 -> 100` reversal that existed in
    the original data. A reversal HIDDEN this way is never "a tie" - it
    is a decreasing step in the original measurement order, and this
    function must never sort, group away, or otherwise make it
    disappear. The fix checks `np.diff` of the ORIGINAL, ungrouped
    `independent_values` for any negative step BEFORE grouping is
    attempted, and raises immediately if one is found. This is safe and
    non-restrictive for every legitimate case: in a sequence that has
    already passed this check (no negative step anywhere), every group of
    equal values is guaranteed to be a CONTIGUOUS run (a non-adjacent
    repeat of the same value would require passing back down to it after
    a strictly larger value, which is exactly the negative step this
    check forbids) - so ordinary adjacent ties (e.g. `[100.0, 100.0,
    200.0]` or `[100.0, 200.0, 200.0, 300.0]`) are entirely unaffected and
    continue to be grouped and median-conditioned exactly as before.
    """
    depth_conditioned_m = _as_1d_finite(
        f"{well_key}: {interpolation_direction}: depth_conditioned_m", depth_conditioned_m
    )
    independent_values = _as_1d_finite(
        f"{well_key}: {interpolation_direction}: {independent_axis_name}", independent_values
    )
    dependent_values = _as_1d_finite(
        f"{well_key}: {interpolation_direction}: {dependent_axis_name}", dependent_values
    )
    _require_equal_length(
        [
            ("depth_conditioned_m", depth_conditioned_m),
            (independent_axis_name, independent_values),
            (dependent_axis_name, dependent_values),
        ]
    )
    _require_strictly_increasing(
        f"{well_key}: {interpolation_direction}: depth_conditioned_m", depth_conditioned_m
    )

    # Increment 4.1.1 fix (Blocking Defect 1): check the ORIGINAL,
    # ungrouped sequence for a genuine reversal BEFORE any grouping is
    # attempted - grouping by global exact-value equality can otherwise
    # silently hide a reversal that passes back down to an
    # already-seen value (see the docstring section above). A zero
    # difference (an ordinary tie) is explicitly allowed here; only a
    # strictly negative difference is a reversal.
    if independent_values.size > 1:
        _orig_diffs = np.diff(independent_values)
        _bad = np.where(_orig_diffs < 0.0)[0]
        if _bad.size > 0:
            raise TimeDepthError(
                f"{well_key}: {interpolation_direction}: {independent_axis_name} contains a "
                f"genuine reversal (a decreasing step, not a tie) at original interval "
                f"index(es) {_bad.tolist()}; this function never sorts, groups away, or "
                f"otherwise hides a reversal by merging a repeated value with an earlier, "
                f"non-adjacent occurrence of the same value."
            )

    order, groups = _group_by_exact_value(independent_values)

    entries: list = []
    out_axis: list = []
    out_dependent: list = []
    n_collapsed = 0
    n_identical_pairs = 0
    n_nonunique = 0

    for v in order:
        idxs = tuple(groups[v])
        dep_group = dependent_values[list(idxs)]
        depth_group = depth_conditioned_m[list(idxs)]
        rep_dependent = float(np.median(dep_group))
        out_axis.append(v)
        out_dependent.append(rep_dependent)

        if len(idxs) > 1:
            spread = float(np.max(dep_group) - np.min(dep_group))
            is_identical = spread == 0.0
            tie_kind = "identical_pair" if is_identical else "genuinely_non_unique"
            if is_identical:
                n_identical_pairs += 1
            else:
                n_nonunique += 1
            n_collapsed += len(idxs) - 1
            entries.append(
                AxisTimeDepthTieRegisterEntry(
                    well_key=well_key,
                    interpolation_direction=interpolation_direction,
                    axis=independent_axis_name,
                    dependent_axis=dependent_axis_name,
                    tie_axis_value=float(v),
                    conditioned_row_indices=idxs,
                    associated_depth_m=tuple(float(x) for x in depth_group),
                    original_dependent_values=tuple(float(x) for x in dep_group),
                    group_size=len(idxs),
                    dependent_value_spread=spread,
                    selected_representative_dependent_value=rep_dependent,
                    conditioning_rule=(
                        f"median of the tied group's {dependent_axis_name} values, computed "
                        f"independently of which tied row appeared first (order-invariant); "
                        f"for this group's size ({len(idxs)}), median "
                        + ("equals the arithmetic mean." if len(idxs) % 2 == 0 else "is the middle value.")
                    ),
                    tie_kind=tie_kind,
                    affected_downstream_outputs=(
                        f"{interpolation_direction}_lookup_table",
                        "forward_inverse_time_depth_interpolation",
                    ),
                )
            )

    out_axis_arr = np.asarray(out_axis, dtype=np.float64)
    out_dependent_arr = np.asarray(out_dependent, dtype=np.float64)

    _require_strictly_increasing(
        f"{well_key}: {interpolation_direction}: {independent_axis_name} after axis-tie conditioning",
        out_axis_arr,
    )

    table = AxisConditionedLookupTable(
        well_key=well_key,
        interpolation_direction=interpolation_direction,
        independent_axis_name=independent_axis_name,
        dependent_axis_name=dependent_axis_name,
        axis_values=out_axis_arr,
        dependent_values=out_dependent_arr,
        n_input_points=int(independent_values.size),
        n_output_points=int(out_axis_arr.size),
        n_axis_tie_groups=len(entries),
        n_collapsed_points=n_collapsed,
        n_identical_pairs=n_identical_pairs,
        n_genuinely_nonunique_groups=n_nonunique,
        conditioning_method=AXIS_TIE_CONDITIONING_METHOD,
    )
    return tuple(entries), table


def build_axis_conditioned_tables_for_well(
    well_key: str, conditioned: ConditionedCheckshotData
) -> Tuple[Tuple[AxisTimeDepthTieRegisterEntry, ...], Dict[str, AxisConditionedLookupTable]]:
    """
    Build BOTH axis-conditioned lookup tables (`tvdss_to_owt` and
    `owt_to_tvdss`) for one well in a single call, returning the combined,
    flat tuple of every `AxisTimeDepthTieRegisterEntry` found across both
    directions plus a dict of the two `AxisConditionedLookupTable`
    objects keyed by direction name. This is the function
    `p2mem.io.checkshot.load_checkshot_file` calls once per well so every
    downstream consumer (interpolation, the CSV/JSON exporters, the
    notebook) shares the same order-invariant tables.
    """
    entries_to_owt, table_to_owt = build_axis_conditioned_lookup_table(
        well_key,
        "tvdss_to_owt",
        "TVDSS_conditioned_m",
        "OWT_conditioned_s",
        conditioned.Depth_conditioned_m,
        conditioned.TVDSS_conditioned_m,
        conditioned.OWT_conditioned_s,
    )
    entries_to_tvdss, table_to_tvdss = build_axis_conditioned_lookup_table(
        well_key,
        "owt_to_tvdss",
        "OWT_conditioned_s",
        "TVDSS_conditioned_m",
        conditioned.Depth_conditioned_m,
        conditioned.OWT_conditioned_s,
        conditioned.TVDSS_conditioned_m,
    )
    return (
        tuple(entries_to_owt) + tuple(entries_to_tvdss),
        {"tvdss_to_owt": table_to_owt, "owt_to_tvdss": table_to_tvdss},
    )


def tvdss_to_owt(tvdss_query, table: AxisConditionedLookupTable):
    """
    TVDSS -> OWT_source_s, piecewise-linear against the order-invariant
    `tvdss_to_owt` `AxisConditionedLookupTable` (see
    `build_axis_conditioned_lookup_table` /
    `build_axis_conditioned_tables_for_well`). Returns (values with NaN
    outside coverage, coverage_mask).
    """
    if table.interpolation_direction != "tvdss_to_owt":
        raise TimeDepthError(
            f"tvdss_to_owt requires a table built with interpolation_direction="
            f"'tvdss_to_owt'; got {table.interpolation_direction!r}."
        )
    return _interp_with_coverage(np.atleast_1d(tvdss_query), table.axis_values, table.dependent_values)


def owt_to_tvdss(owt_query, table: AxisConditionedLookupTable):
    """
    OWT_source_s -> TVDSS, piecewise-linear against the order-invariant
    `owt_to_tvdss` `AxisConditionedLookupTable`. Returns (values with NaN
    outside coverage, coverage_mask).
    """
    if table.interpolation_direction != "owt_to_tvdss":
        raise TimeDepthError(
            f"owt_to_tvdss requires a table built with interpolation_direction="
            f"'owt_to_tvdss'; got {table.interpolation_direction!r}."
        )
    return _interp_with_coverage(np.atleast_1d(owt_query), table.axis_values, table.dependent_values)


def tvdss_to_twt(tvdss_query, table: AxisConditionedLookupTable):
    """TVDSS -> TWT_s, via TVDSS -> OWT (the supplied `tvdss_to_owt` table)
    then the LOCKED owt_to_twt conversion."""
    owt, mask = tvdss_to_owt(tvdss_query, table)
    return owt_to_twt(owt), mask


def twt_to_tvdss(twt_query, table: AxisConditionedLookupTable):
    """TWT_s -> TVDSS, via the LOCKED twt_to_owt conversion then OWT -> TVDSS
    (the supplied `owt_to_tvdss` table)."""
    owt_query = twt_to_owt(np.atleast_1d(twt_query))
    return owt_to_tvdss(owt_query, table)


# ---------------------------------------------------------------------------
# LAS MD -> checkshot-derived OWT/TWT (partial-coverage NaN masking)
# ---------------------------------------------------------------------------
def map_las_md_to_checkshot_time(
    well_key: str, las_md_source_m: np.ndarray, conditioned: ConditionedCheckshotData
) -> Tuple[np.ndarray, np.ndarray, TimeDepthMappingSummary]:
    """
    Map a well's canonical LAS `MD_m` onto checkshot-derived OWT/TWT,
    treating LAS MD directly as the checkshot Depth axis (both wells'
    Depth-basis interpretation is `candidate_md_evaluated_against_locked_
    survey` - see `config/checkshot_contracts.yml`). Samples outside
    checkshot Depth coverage are NaN, never extrapolated
    (`n_extrapolated` is always 0 by construction). Returns the full
    per-sample arrays (for notebook plotting only - never packaged as a
    per-sample CSV, per project policy) plus the deterministic
    `TimeDepthMappingSummary`.
    """
    las_md = np.asarray(las_md_source_m, dtype=np.float64)
    if las_md.ndim != 1 or las_md.size == 0 or not np.all(np.isfinite(las_md)):
        raise TimeDepthError(f"{well_key}: LAS MD array must be a non-empty, finite 1-D array.")

    owt_mapped, inside_mask = depth_to_owt(las_md, conditioned)
    twt_mapped = owt_to_twt(owt_mapped)

    depth_min = float(conditioned.Depth_conditioned_m[0])
    depth_max = float(conditioned.Depth_conditioned_m[-1])
    n_shallower = int(np.sum(las_md < depth_min))
    n_deeper = int(np.sum(las_md > depth_max))
    n_inside = int(np.sum(inside_mask))

    summary = TimeDepthMappingSummary(
        well_key=well_key,
        n_las_samples=int(las_md.size),
        n_inside_coverage=n_inside,
        n_shallower_than_coverage=n_shallower,
        n_deeper_than_coverage=n_deeper,
        mapped_fraction=float(n_inside) / float(las_md.size),
        checkshot_depth_min_m=depth_min,
        checkshot_depth_max_m=depth_max,
        las_md_min_m=float(np.min(las_md)),
        las_md_max_m=float(np.max(las_md)),
        interpolation_method=INTERPOLATION_METHOD,
        n_extrapolated=0,
    )
    return owt_mapped, twt_mapped, summary


# ---------------------------------------------------------------------------
# Poseidon 2 sonic-checkshot drift diagnostic
# ---------------------------------------------------------------------------
def find_longest_finite_positive_run(md_m: np.ndarray, values: np.ndarray) -> Tuple[int, int]:
    """
    Return the (start_index, end_index_inclusive) of the longest maximal
    contiguous run of finite, strictly positive `values` in `md_m` order
    (`md_m` assumed already in ascending log order, as every canonical LAS
    `MD_m` array in this project is). Raises `TimeDepthError` if no finite
    positive sample exists at all.

    Validated (Increment 4.1.1 hardening): `md_m` and `values` must each
    be one-dimensional and of equal, compatible shape when this function
    is called directly (`compute_sonic_checkshot_drift` already validates
    both arrays more strictly - full MD finiteness/monotonicity - before
    calling this function, but this function is part of the module's
    public API and must not silently misbehave on a malformed shape when
    called on its own).
    """
    md_m = np.asarray(md_m)
    values = np.asarray(values)
    if md_m.ndim != 1:
        raise TimeDepthError(f"find_longest_finite_positive_run: md_m must be one-dimensional; got shape {md_m.shape}.")
    if values.ndim != 1:
        raise TimeDepthError(f"find_longest_finite_positive_run: values must be one-dimensional; got shape {values.shape}.")
    if md_m.shape != values.shape:
        raise TimeDepthError(
            f"find_longest_finite_positive_run: md_m and values must share one shape; got "
            f"{md_m.shape} and {values.shape}."
        )
    valid = np.isfinite(values) & (values > 0.0)
    idx_valid = np.where(valid)[0]
    if idx_valid.size == 0:
        raise TimeDepthError("no finite, strictly positive sample found to select a run from.")
    splits = np.where(np.diff(idx_valid) > 1)[0]
    runs = np.split(idx_valid, splits + 1)
    longest = max(runs, key=lambda r: r.size)
    return int(longest[0]), int(longest[-1])


def compute_sonic_checkshot_drift(
    well_key: str,
    md_m: np.ndarray,
    vp_m_s: np.ndarray,
    conditioned: ConditionedCheckshotData,
) -> SonicCheckshotDriftResult:
    """
    Poseidon-2-only diagnostic: integrate sonic slowness (1/VP_m_s)
    trapezoidally over MD across the longest contiguous finite-VP interval
    (`find_longest_finite_positive_run`), and compare it against the
    checkshot-interpolated OWT increment across the identical MD/Depth
    endpoints (`depth_to_owt`, applied to `conditioned` - i.e. Depth is
    used directly as the comparison axis for the same reason documented
    in `map_las_md_to_checkshot_time`).

    Both signed differences are reported (`sonic_minus_checkshot_ms`,
    `checkshot_minus_sonic_ms`) plus a signed percent
    (`sonic_minus_checkshot_percent`, relative to the checkshot
    increment). This is a DIAGNOSTIC comparison only - see `limitations`;
    VP_m_s, DTCO, checkshot OWT, and the conditioned time-depth curve are
    never modified as a result of this computation.

    Validated (Increment 4.1 hardening, EXTENDED in Increment 4.1.1 - see
    below): `md_m` and `vp_m_s` must each be one-dimensional, finite*, and
    of equal shape (*`vp_m_s` may contain non-finite/non-positive samples
    anywhere - those are exactly what `find_longest_finite_positive_run`
    screens for - but `md_m` itself, the log's own canonical depth index,
    must be entirely finite); the resulting checkshot OWT increment over
    the selected interval must be strictly positive (a non-positive
    increment would make the percent-difference calculation meaningless
    or divide-by-zero).

    Full-MD monotonicity requirement (Increment 4.1.1 fix - Blocking
    Defect 2). The Increment 4.1 implementation checked strict MD
    monotonicity only WITHIN the selected finite-positive-VP run, not
    across the complete canonical `md_m` array. This allowed a decreasing
    or duplicate MD value OUTSIDE the selected run (e.g. at a station
    whose `VP_m_s` happens to be NaN, and is therefore excluded from the
    run-selection step entirely) to pass silently - the canonical MD
    index itself is a structural precondition of this function's
    contract, not just of the one sub-interval it happens to select for
    integration. This function now requires the COMPLETE `md_m` array to
    be strictly increasing (no decreasing step and no duplicate MD value
    anywhere in the log, not only inside the selected run) BEFORE the run
    is even selected, raising `TimeDepthError` otherwise. This validation
    does not alter the arithmetic path for already-valid input - the real
    Poseidon 2 canonical `MD_m` array (31,897 samples) was independently
    confirmed entirely finite and strictly increasing throughout before
    this hardening was added, so the real Poseidon 2 result is bit-for-
    bit unchanged from Increment 4.1's.
    """
    md_m = _as_1d_finite(f"{well_key}: compute_sonic_checkshot_drift: md_m", md_m)
    vp_m_s = np.asarray(vp_m_s, dtype=np.float64)
    if vp_m_s.ndim != 1:
        raise TimeDepthError(f"{well_key}: vp_m_s must be a one-dimensional array; got shape {vp_m_s.shape}.")
    if md_m.shape != vp_m_s.shape:
        raise TimeDepthError(
            f"{well_key}: MD and VP arrays must share one shape; got {md_m.shape} and {vp_m_s.shape}."
        )
    # Increment 4.1.1 fix (Blocking Defect 2): the COMPLETE canonical MD
    # index must be strictly increasing, not only the sub-run this
    # function later selects for integration - a decreasing or duplicate
    # MD value outside the selected run (e.g. at a NaN-VP station) must
    # not be allowed to pass silently.
    _require_strictly_increasing(f"{well_key}: compute_sonic_checkshot_drift: md_m (complete canonical array)", md_m)

    start_idx, end_idx = find_longest_finite_positive_run(md_m, vp_m_s)
    md_run = md_m[start_idx : end_idx + 1]
    vp_run = vp_m_s[start_idx : end_idx + 1]
    if md_run.size < 2:
        raise TimeDepthError(f"{well_key}: selected sonic interval has fewer than 2 samples.")
    _require_strictly_increasing(f"{well_key}: selected sonic interval's MD_m", md_run)

    slowness = 1.0 / vp_run
    md1, md2 = float(md_run[0]), float(md_run[-1])
    sonic_transit_time_s = trapezoidal_integrate(slowness, md_run)

    depth_min = float(conditioned.Depth_conditioned_m[0])
    depth_max = float(conditioned.Depth_conditioned_m[-1])
    if md1 < depth_min or md2 > depth_max:
        raise TimeDepthError(
            f"{well_key}: sonic interval [{md1:.4f}, {md2:.4f}] extends beyond checkshot Depth "
            f"coverage [{depth_min:.4f}, {depth_max:.4f}]; this diagnostic never extrapolates "
            f"checkshot time beyond its validated coverage."
        )

    owt_at_md1 = float(np.interp(md1, conditioned.Depth_conditioned_m, conditioned.OWT_conditioned_s))
    owt_at_md2 = float(np.interp(md2, conditioned.Depth_conditioned_m, conditioned.OWT_conditioned_s))
    checkshot_owt_increment_s = owt_at_md2 - owt_at_md1
    if checkshot_owt_increment_s <= 0.0:
        raise TimeDepthError(
            f"{well_key}: checkshot OWT increment over [{md1:.4f}, {md2:.4f}] is non-positive "
            f"({checkshot_owt_increment_s:.6g} s); this diagnostic requires a strictly positive "
            f"checkshot time increment to compare against the integrated sonic transit time."
        )

    diff_ms = (sonic_transit_time_s - checkshot_owt_increment_s) * 1000.0
    pct = (
        (sonic_transit_time_s - checkshot_owt_increment_s) / checkshot_owt_increment_s * 100.0
        if checkshot_owt_increment_s != 0.0
        else float("nan")
    )

    return SonicCheckshotDriftResult(
        well_key=well_key,
        md_interval_start_m=md1,
        md_interval_end_m=md2,
        n_sonic_samples=int(md_run.size),
        selection_criteria=(
            "longest maximal contiguous run of finite, strictly positive VP_m_s samples in "
            "canonical LAS MD order"
        ),
        integration_method=INTEGRATION_METHOD,
        sonic_transit_time_s=sonic_transit_time_s,
        checkshot_owt_increment_s=checkshot_owt_increment_s,
        sonic_minus_checkshot_ms=diff_ms,
        checkshot_minus_sonic_ms=-diff_ms,
        sonic_minus_checkshot_percent=pct,
        limitations=(
            "Sonic transit time is integrated along the borehole (MD) path; checkshot OWT is a "
            "vertically corrected (near-vertical raypath) travel time - the two are not measured "
            "along an identical raypath for a deviated interval.",
            "No acquisition or environmental corrections (temperature, pressure, tool eccentering, "
            "cycle-skip editing) are supplied with either the sonic log or the checkshot survey; "
            "none are applied here.",
            "No run-merging metadata is available to confirm the sonic log is a single, "
            "continuously calibrated logging run over the selected interval.",
            "This is a diagnostic comparison only, not a calibration: no drift correction is "
            "applied to VP_m_s, DTCO, checkshot OWT, or the conditioned time-depth curve.",
        ),
    )
