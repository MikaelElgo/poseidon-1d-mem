"""
p2mem.trajectory - Minimum-curvature well-trajectory computation (Increment 3).

Scope
-----
This module implements ONLY the standard minimum-curvature method for
converting a sequence of (MD, inclination, azimuth) directional-survey
stations into a 3D trajectory (TVD, northing offset, easting offset), plus
the numerically stable ratio-factor limit, dogleg-severity computation, and
residual comparison against an independently supplied ("source") trajectory
(e.g. the Petrel-computed X/Y/Z/TVD columns in a deviation-survey file).

Nothing here reads a file, applies a contract, or decides which trajectory
("Petrel-supplied" vs "minimum-curvature-computed") should be used
downstream - that policy decision belongs to `p2mem.depth_mapping` and the
per-well `deviation_survey_contracts.yml` configuration. This module is
pure numerical computation only.

Governing theory
-----------------
For two consecutive survey stations 1 and 2 with inclination I (measured
from vertical) and azimuth A (measured clockwise from north, in the same
azimuth reference used for the accompanying grid coordinates), the dogleg
angle `beta` (the angle, in 3D space, between the two stations'
tangent-direction unit vectors) satisfies:

    cos(beta) = cos(I1) cos(I2) + sin(I1) sin(I2) cos(A2 - A1)

This is the standard textbook statement of the dogleg-angle relationship,
and remains the definition this module implements. However, `beta` itself
is NOT computed by evaluating this right-hand side and then taking
`arccos` of it (see "Numerical stability of the dogleg angle" below for
why) - it is instead computed via an equivalent, numerically stable
vector formulation that agrees with this formula everywhere but does not
share `arccos`'s ill-conditioning near `beta == 0`.

The minimum-curvature method then fits a single circular arc, of constant
curvature, between the two station directions - as opposed to the (less
accurate) tangential or average-angle methods, which assume straight-line
or simple-average behavior between stations.

The ratio factor:

    RF = (2 / beta) * tan(beta / 2)

converts the straight-line ("tangential") displacement into the
arc-corrected minimum-curvature displacement. As beta -> 0 (no direction
change - a perfectly straight hold section), RF has the well-defined limit
RF -> 1 (a straight line is a degenerate circular arc of infinite radius).
This module evaluates that limit via a Taylor-series expansion for very
small beta, rather than relying on floating-point division/tan() behavior
at or near beta == 0, which otherwise produces 0/0 (NaN) exactly at
beta == 0 and can lose precision for beta approaching it.

Displacement over an interval of measured-depth length dMD is then:

    dTVD      = (dMD / 2) (cos I1 + cos I2) RF
    dNorthing = (dMD / 2) (sin I1 cos A1 + sin I2 cos A2) RF
    dEasting  = (dMD / 2) (sin I1 sin A1 + sin I2 sin A2) RF

and dogleg severity, expressed in the oilfield-conventional degrees per 30
metres, is:

    DLS_deg_per_30m = (beta_deg / dMD) * 30

Numerical stability of the dogleg angle (Increment 3.1 correction)
---------------------------------------------------------------------
Increment 3 originally computed `beta` as `arccos(clip(cos_beta, -1, 1))`,
evaluating the right-hand side of the formula above directly. `arccos` is
ill-conditioned as its argument approaches +1 (`beta -> 0`): its
derivative diverges there, so an ordinary ~1e-16 floating-point residual
in `cos_beta` surfaced as a spurious dogleg of order 1e-8 radians (~1e-6
degrees) even for two stations with EXACTLY identical inclination and
azimuth - a perfectly straight hold section that should report `beta ==
0.0` exactly. This was reported (not hidden) at the time, with a widened
test tolerance and a docstring note - but a widened tolerance treats the
symptom, not the cause, and this corrective patch replaces the
ill-conditioned formulation instead.

`dogleg_angle_rad` now computes `beta` as the angle between the two
stations' 3-D tangent unit vectors via `arctan2(|u1 x u2|, u1 . u2)`
rather than `arccos(u1 . u2)`. This is mathematically the identical angle
for every `beta` in `[0, pi]` (both the cross-product magnitude and the
dot product are continuous, well-conditioned functions of `u1`/`u2` even
as the vectors converge), but unlike `arccos`, `arctan2` has a bounded
derivative everywhere on this domain, including exactly at `beta == 0`:
two identical unit vectors have an EXACT (floating-point-zero) cross
product, so `arctan2(0.0, ~1.0)` returns exactly `0.0`, with no residual
noise floor. A genuinely tiny nonzero dogleg (e.g. 1e-6 degrees of real
curvature) remains numerically well-resolved, since `arctan2` near
`y = 0` does not suffer the vanishing-derivative problem `arccos` has
near `x = 1`. See `tests/test_trajectory.py` for a direct comparison of
old-versus-new behavior on identical, tiny, and moderate doglegs.

Angle handling
--------------
All angle trigonometry is performed in radians. Degree<->radian conversion
uses the already-locked, tested `p2mem.units.degrees_to_radians` /
`radians_to_degrees` functions (Increment 1.1) rather than reimplementing
degree/radian conversion here, so the exact same validated conversion is
used project-wide.

Azimuth is measured mod 360 degrees; the dogleg formula above uses
`cos(A2 - A1)`, which is inherently periodic in the azimuth difference, so
a wraparound case (e.g. A1 = 359 deg, A2 = 1 deg, an actual difference of
only 2 degrees) is handled correctly WITHOUT any explicit modulo-360
normalization of the input azimuths themselves - `cos` already treats
359 deg and -1 deg identically.

Azimuth is physically undefined at zero inclination (a vertical borehole
has no horizontal direction to reference an azimuth against). This is not
special-cased in `dogleg_angle_rad`: when I1 == 0, `sin(I1) == 0`, so the
`sin(I1) sin(I2) cos(A2 - A1)` cross-term vanishes identically regardless
of what azimuth value the survey happens to record for that station (real
files commonly record 0.0 or an arbitrary placeholder azimuth at a
vertical station) - so no artificial "azimuth discontinuity" dogleg is
ever generated purely from a vertical station's azimuth value. See
`test_trajectory.py::test_azimuth_undefined_at_zero_inclination_does_not_
inflate_dogleg`.

Failure handling
-----------------
`TrajectoryComputationError` is raised for nonphysical inputs (inclination
outside [0, 180] degrees, non-finite MD/inclination/azimuth, or a
non-increasing MD sequence) - this module never silently clips, drops, or
"repairs" a station; the caller (`p2mem.io.deviation`) is responsible for
station-level QC before trajectory computation is attempted, and this
module performs its own defensive validation as a second, independent
gate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from p2mem.units import degrees_to_radians, radians_to_degrees

__all__ = [
    "TrajectoryComputationError",
    "MinimumCurvatureResult",
    "dogleg_angle_rad",
    "ratio_factor",
    "minimum_curvature_intervals",
    "compute_minimum_curvature_trajectory",
]

# Below this dogleg angle (radians), the ratio factor is evaluated via its
# Taylor-series limit (RF = 1 + beta^2/12) rather than the direct
# 2/beta * tan(beta/2) expression, which is an exact 0/0 (NaN) form at
# beta == 0 and is unnecessary to evaluate directly at all once the
# quadratic term is already many orders of magnitude below float64
# precision (beta ~ 1e-6 rad gives a Taylor correction of ~8e-14, i.e.
# already below double-precision resolution of the leading 1.0 term).
# This threshold is independent of, and unaffected by, the Increment 3.1
# dogleg-angle numerical-stability correction (see module docstring):
# beta == 0.0 (identical stations) and any genuinely tiny beta are both
# still routed to this Taylor branch exactly as before.
_SMALL_DOGLEG_THRESHOLD_RAD = 1.0e-9


class TrajectoryComputationError(ValueError):
    """
    Raised when minimum-curvature trajectory computation is asked to
    operate on nonphysical or structurally invalid station data:
    inclination outside [0, 180] degrees, a non-finite MD/inclination/
    azimuth value, or a measured-depth sequence that is not strictly
    increasing. Never silently clipped, dropped, or repaired.
    """


@dataclass(frozen=True)
class MinimumCurvatureResult:
    """
    The complete, typed result of a minimum-curvature trajectory
    computation over a full station sequence of length n.

    All arrays have length n (one value per station). The first station
    (index 0) has no preceding interval, so its `dogleg_deg` and
    `dls_deg_per_30m` are defined as exactly 0.0 by convention (consistent
    with how the real Petrel deviation files themselves record DLS = 0.0
    at their first station) - not NaN, since a "no computation possible
    here" placeholder value of 0.0 for an angle/severity index at the very
    top of the well is the same convention the source data already uses.

    `tvd_mc_m`, `northing_offset_mc_m`, and `easting_offset_mc_m` are
    CUMULATIVE, computed by initializing station 0 from the caller-
    supplied `tvd_origin_m` / `northing_origin_m` / `easting_origin_m`
    (see `compute_minimum_curvature_trajectory`) and then accumulating the
    per-interval minimum-curvature deltas station-by-station. This
    initialization choice - using the survey's own first-station source
    offsets as the tie-on point, rather than assuming a hard-coded (0, 0,
    0) origin - is deliberate: real files (e.g. Proteus 1ST2 in this
    project) can carry a tiny nonzero first-station MD/TVD/offset
    (~-7.63e-7 m) that must be preserved as the literal starting
    condition, not silently zeroed.
    """

    dogleg_deg: np.ndarray
    dls_deg_per_30m: np.ndarray
    tvd_mc_m: np.ndarray
    northing_offset_mc_m: np.ndarray
    easting_offset_mc_m: np.ndarray


def _validate_stations(
    md_m: np.ndarray, incl_deg: np.ndarray, azim_deg: np.ndarray
) -> None:
    if not (md_m.shape == incl_deg.shape == azim_deg.shape):
        raise TrajectoryComputationError(
            f"minimum-curvature input arrays must share one shape; got "
            f"md_m={md_m.shape}, incl_deg={incl_deg.shape}, azim_deg={azim_deg.shape}"
        )
    if md_m.ndim != 1 or md_m.size < 1:
        raise TrajectoryComputationError(
            "minimum-curvature input must be a 1-D array of at least one station"
        )
    for name, arr in (("md_m", md_m), ("incl_deg", incl_deg), ("azim_deg", azim_deg)):
        if not np.all(np.isfinite(arr)):
            bad = np.where(~np.isfinite(arr))[0].tolist()
            raise TrajectoryComputationError(
                f"{name} contains non-finite value(s) at station index(es) {bad}; "
                f"minimum-curvature computation requires every station finite"
            )
    if md_m.size > 1 and not np.all(np.diff(md_m) > 0.0):
        bad = np.where(np.diff(md_m) <= 0.0)[0].tolist()
        raise TrajectoryComputationError(
            f"MD must be strictly increasing for minimum-curvature computation; "
            f"non-increasing step(s) found starting at interval index(es) {bad}"
        )
    if np.any((incl_deg < 0.0) | (incl_deg > 180.0)):
        bad = np.where((incl_deg < 0.0) | (incl_deg > 180.0))[0].tolist()
        raise TrajectoryComputationError(
            f"inclination outside the physically valid range [0, 180] degrees "
            f"at station index(es) {bad}: {incl_deg[bad].tolist()}"
        )


def dogleg_angle_rad(
    incl1_deg: np.ndarray,
    incl2_deg: np.ndarray,
    azim1_deg: np.ndarray,
    azim2_deg: np.ndarray,
) -> np.ndarray:
    """
    Compute the dogleg angle beta (radians) between consecutive stations,
    mathematically defined by:

        cos(beta) = cos(I1) cos(I2) + sin(I1) sin(I2) cos(A2 - A1)

    Inputs are in degrees (converted internally via
    `p2mem.units.degrees_to_radians`); output is in radians, always in
    [0, pi].

    Numerically stable implementation (Increment 3.1 correction): rather
    than evaluating the right-hand side above and taking `arccos` of it
    (ill-conditioned as `beta -> 0` - see the module docstring's
    "Numerical stability of the dogleg angle" section for the full
    rationale and the defect this replaced), `beta` is computed as the
    angle between each station pair's 3-D tangent unit vectors
    `u = (cos I, sin I cos A, sin I sin A)` via

        beta = arctan2(|u1 x u2|, u1 . u2)

    This is the identical angle for every beta in [0, pi] (the dot
    product above expands to exactly `cos(I1)cos(I2) +
    sin(I1)sin(I2)cos(A2-A1)` by the standard trig product-to-sum
    identity), but has a bounded derivative everywhere on this domain,
    including exactly at beta == 0: two numerically identical tangent
    vectors have an exactly-zero cross product, so identical (I, A)
    station pairs now report beta == 0.0 to full floating-point
    precision, with no residual noise floor, while genuinely tiny nonzero
    doglegs remain accurately resolved (no clipping of the dot product is
    needed here, unlike the old `arccos` formulation, since `arctan2` is
    well-behaved for any finite argument pair).
    """
    i1 = degrees_to_radians(np.asarray(incl1_deg, dtype=np.float64))
    i2 = degrees_to_radians(np.asarray(incl2_deg, dtype=np.float64))
    a1 = degrees_to_radians(np.asarray(azim1_deg, dtype=np.float64))
    a2 = degrees_to_radians(np.asarray(azim2_deg, dtype=np.float64))

    u1 = np.stack([np.cos(i1), np.sin(i1) * np.cos(a1), np.sin(i1) * np.sin(a1)], axis=-1)
    u2 = np.stack([np.cos(i2), np.sin(i2) * np.cos(a2), np.sin(i2) * np.sin(a2)], axis=-1)

    cross_norm = np.linalg.norm(np.cross(u1, u2), axis=-1)
    dot = np.sum(u1 * u2, axis=-1)
    return np.arctan2(cross_norm, dot)


def ratio_factor(beta_rad: np.ndarray) -> np.ndarray:
    """
    Compute the minimum-curvature ratio factor RF = (2/beta) tan(beta/2),
    using the numerically stable limit RF -> 1 + beta^2/12 for
    beta < `_SMALL_DOGLEG_THRESHOLD_RAD` (including beta == 0 exactly,
    which the direct formula cannot evaluate: 2/0 * tan(0) is a 0/0 form).

    The Taylor series RF = 1 + beta^2/12 + O(beta^4) follows from
    tan(x) = x + x^3/3 + O(x^5) with x = beta/2:

        (2/beta) tan(beta/2) = (2/beta) (beta/2 + (beta/2)^3/3 + ...)
                              = 1 + beta^2/12 + O(beta^4)
    """
    beta = np.asarray(beta_rad, dtype=np.float64)
    small = np.abs(beta) < _SMALL_DOGLEG_THRESHOLD_RAD
    with np.errstate(divide="ignore", invalid="ignore"):
        direct = (2.0 / beta) * np.tan(beta / 2.0)
    taylor = 1.0 + (beta**2) / 12.0
    return np.where(small, taylor, direct)


def minimum_curvature_intervals(
    md_m: np.ndarray,
    incl_deg: np.ndarray,
    azim_deg: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute per-interval dogleg angle, ratio factor, and minimum-curvature
    displacement deltas (dTVD, dNorthing, dEasting) for every consecutive
    station pair in a station sequence of length n.

    Returns (beta_deg, rf, delta_tvd_m, delta_northing_m, delta_easting_m),
    each of length (n - 1): index k corresponds to the interval from
    station k to station k+1.

    `azim_deg` must already be the single azimuth reference the caller
    intends to use for the grid-coordinate (northing/easting) computation
    (i.e. AZIM_GN for these Petrel files, per the project's deviation
    contracts) - this function does not know about, and never mixes,
    multiple azimuth references; that separation is the caller's
    responsibility (see `p2mem.io.deviation`).
    """
    md_m = np.asarray(md_m, dtype=np.float64)
    incl_deg = np.asarray(incl_deg, dtype=np.float64)
    azim_deg = np.asarray(azim_deg, dtype=np.float64)
    _validate_stations(md_m, incl_deg, azim_deg)

    i1_deg, i2_deg = incl_deg[:-1], incl_deg[1:]
    a1_deg, a2_deg = azim_deg[:-1], azim_deg[1:]
    delta_md = md_m[1:] - md_m[:-1]

    beta_rad = dogleg_angle_rad(i1_deg, i2_deg, a1_deg, a2_deg)
    rf = ratio_factor(beta_rad)

    i1 = degrees_to_radians(i1_deg)
    i2 = degrees_to_radians(i2_deg)
    a1 = degrees_to_radians(a1_deg)
    a2 = degrees_to_radians(a2_deg)

    half_md = delta_md / 2.0
    delta_tvd = half_md * (np.cos(i1) + np.cos(i2)) * rf
    delta_northing = half_md * (np.sin(i1) * np.cos(a1) + np.sin(i2) * np.cos(a2)) * rf
    delta_easting = half_md * (np.sin(i1) * np.sin(a1) + np.sin(i2) * np.sin(a2)) * rf

    beta_deg = radians_to_degrees(beta_rad)
    return beta_deg, rf, delta_tvd, delta_northing, delta_easting


def compute_minimum_curvature_trajectory(
    md_m: np.ndarray,
    incl_deg: np.ndarray,
    azim_deg: np.ndarray,
    tvd_origin_m: float,
    northing_origin_m: float,
    easting_origin_m: float,
) -> MinimumCurvatureResult:
    """
    Compute the full cumulative minimum-curvature trajectory (TVD,
    northing offset, easting offset) for a station sequence of length n,
    initialized at station 0 from the caller-supplied origin values
    (typically that well's own first-station source TVD/DY/DX, so the
    independent trajectory starts from exactly the same tie-on point as
    the source survey - see `MinimumCurvatureResult` docstring).

    Dogleg severity is reported in the oilfield-conventional
    degrees-per-30-metres: DLS_deg_per_30m = (beta_deg / delta_MD) * 30.
    A zero-length interval (delta_MD == 0) cannot occur here because
    `_validate_stations` requires MD strictly increasing.
    """
    md_m = np.asarray(md_m, dtype=np.float64)
    incl_deg = np.asarray(incl_deg, dtype=np.float64)
    azim_deg = np.asarray(azim_deg, dtype=np.float64)
    _validate_stations(md_m, incl_deg, azim_deg)
    n = md_m.size

    dogleg_deg_full = np.zeros(n, dtype=np.float64)
    dls_full = np.zeros(n, dtype=np.float64)
    tvd_mc = np.empty(n, dtype=np.float64)
    northing_mc = np.empty(n, dtype=np.float64)
    easting_mc = np.empty(n, dtype=np.float64)

    tvd_mc[0] = tvd_origin_m
    northing_mc[0] = northing_origin_m
    easting_mc[0] = easting_origin_m

    if n > 1:
        beta_deg, _rf, d_tvd, d_north, d_east = minimum_curvature_intervals(
            md_m, incl_deg, azim_deg
        )
        delta_md = md_m[1:] - md_m[:-1]
        dls_intervals = (beta_deg / delta_md) * 30.0

        dogleg_deg_full[1:] = beta_deg
        dls_full[1:] = dls_intervals
        tvd_mc[1:] = tvd_origin_m + np.cumsum(d_tvd)
        northing_mc[1:] = northing_origin_m + np.cumsum(d_north)
        easting_mc[1:] = easting_origin_m + np.cumsum(d_east)

    return MinimumCurvatureResult(
        dogleg_deg=dogleg_deg_full,
        dls_deg_per_30m=dls_full,
        tvd_mc_m=tvd_mc,
        northing_offset_mc_m=northing_mc,
        easting_offset_mc_m=easting_mc,
    )
