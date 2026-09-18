"""
p2mem.units - Explicit NumPy-based unit-conversion layer with no external
unit-registry dependency.

Design rationale
-----------------
The Poseidon 2 dataset mixes oilfield units (ft, us/ft, g/cc, psi, ppg) with
SI units (m, m/s, kg/m3, Pa) across different files and, in places, within
the same LAS curve header. Rather than adopting a general-purpose unit
library (e.g. Pint), this module implements every conversion this project
needs as a small, explicit, independently testable function. This is a
deliberate project decision (see Increment 1 specification): every
conversion factor is visible in source, has a stated origin, and can be
checked against an analytical reference value in ``tests/test_units.py``.

Internal unit convention
-------------------------
All downstream p2mem modules (Increment 2 onward) will store working
values in SI units, using explicit unit-suffixed column/variable names
(e.g. ``RHOB_kgm3``, ``DTCO_us_per_ft`` for the raw curve before
conversion, ``VP_m_s`` after). This module is the single boundary where
oilfield-unit inputs are converted to SI, and back again where an
oilfield-unit output is required (e.g. reporting mud weight in ppg).

Internal SI units used throughout this project:
    length              metres (m)
    velocity            metres per second (m/s)
    density             kilograms per cubic metre (kg/m3)
    pressure / stress   pascals (Pa)
    angle               radians (rad)
    time (seismic)      seconds (s), unless explicitly noted otherwise

Scope boundary
--------------
This module performs UNIT CONVERSION ONLY: exact, definitional,
non-empirical relationships (e.g. 1 ft = 0.3048 m exactly; a sonic
transit-time is the reciprocal of velocity by definition). It contains
NO empirical or correlation-based petrophysical/geomechanical
relationships (e.g. no Gardner density-from-velocity, no Eaton
pore-pressure exponent, no Castagna Vp/Vs). Those belong in later,
explicitly gated modules once their governing equations, applicability
ranges, and calibration status are recorded in the project's
method-and-citation register.

Input/output contract (applies to every public function in this module)
-------------------------------------------------------------------------
* Accepts a Python numeric scalar (``int``/``float``) or a NumPy numeric
  array (any shape, integer or floating dtype).
* Returns the same "shape" of object it was given: a scalar in yields a
  Python ``float`` out; an array in yields a NumPy array (``float64``) out
  of identical shape.
* ``NaN`` values are propagated element-wise and are NEVER treated as
  errors: a missing/null sample must remain missing after conversion.
* ``inf``/``-inf`` values are always rejected (never physically valid for
  any quantity handled here).
* Values that are finite but physically impossible for the quantity being
  converted (e.g. negative density, negative absolute transit time, zero
  or negative sonic velocity) raise ``ValueError`` naming the offending
  values. Nothing is ever silently clipped, floored, or coerced.
* Ambiguous input types are rejected outright rather than silently
  coerced: a Python/NumPy boolean (``True``/``False`` would otherwise be
  silently reinterpreted as ``1.0``/``0.0``), a string or bytes value
  (including a numeric-looking string such as ``"3.5"``, which NumPy
  would otherwise parse for you), a string array, and a complex value all
  raise ``TypeError``. Only genuine numeric scalars/arrays are accepted.
* All functions are pure (no I/O, no global mutable state).

A note on numerical precision
------------------------------
The base constants below (the international foot, inch, avoirdupois
pound, US liquid gallon, and CGPM standard gravity) are EXACT by
international definition. That does not mean every derived value printed
or stored in this module is exact in the mathematical sense: this module
stores numbers as IEEE-754 double-precision (``float64``) floats, and
several of the derived conversion factors (e.g. psi-to-pascal) are
repeating decimals when computed from the exact definitions - they cannot
be represented exactly in a finite number of decimal or binary digits.
Where this module's docstrings say a *definition* is exact, they mean the
definitional relationship is exact; the stored/derived numeric literal is
a finite-precision (``float64``) representation of that exact quantity,
not a claim that the printed digits are the complete, infinite decimal
expansion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

import numpy as np

ArrayLike = Union[int, float, np.ndarray]


# ---------------------------------------------------------------------------
# Physical / definitional constants (single controlled location)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Constants:
    """
    Centralized physical and definitional constants.

    Every numeric conversion factor used anywhere in this module is drawn
    from here so that (a) there is exactly one place to audit, and
    (b) no magic numbers are duplicated across functions.

    Sources
    -------
    FT_TO_M, IN_TO_M, LB_TO_KG, US_GALLON_TO_M3
        Exact definitions under the international yard-and-pound / US
        customary agreements (NIST Handbook 44, Appendix C). These four
        decimal literals equal their defining values exactly as written;
        note (see the module-level "numerical precision" section above)
        that Python still stores each as the nearest representable
        float64, which is standard IEEE-754 behaviour for any decimal
        literal and not specific to this module.
    STANDARD_GRAVITY
        CGPM standard gravity, exact by definition: 9.80665 m/s^2.
    PSI_TO_PA
        1 psi = 1 lbf/in^2, derived from LB_TO_KG and STANDARD_GRAVITY and
        the exact inch-to-metre definition (1 in = 0.0254 m exactly). The
        underlying rational number is a repeating decimal (its exact value
        begins 6894.757293168362...); it is NOT exactly representable in a
        finite number of decimal digits. The literal below is specified to
        13 significant figures, which is standard engineering precision
        for this conversion and differs from the fully IEEE-754-rounded
        double by roughly 3.6e-10 Pa per psi (a relative discrepancy of
        about 5e-14) - far below the resolution of any physical
        measurement used in this project, but a genuine finite-precision
        approximation rather than a mathematically exact value.
    """

    FT_TO_M: float = 0.3048  # exact by definition (international foot)
    IN_TO_M: float = 0.0254  # exact by definition (international inch)
    LB_TO_KG: float = 0.45359237  # exact by definition (international avoirdupois pound)
    US_GALLON_TO_M3: float = 0.003785411784  # exact by definition (US liquid gallon)
    STANDARD_GRAVITY: float = 9.80665  # m/s^2, exact by definition
    PSI_TO_PA: float = 6894.757293168  # derived from exact definitions; finite-precision (float64) approximation - see Sources above

    @property
    def PPG_TO_KGM3(self) -> float:
        """1 lb/US-gallon expressed in kg/m^3, computed at runtime from LB_TO_KG and US_GALLON_TO_M3 (finite-precision float64 result of an exact-definition ratio)."""
        return self.LB_TO_KG / self.US_GALLON_TO_M3


CONST = Constants()


# ---------------------------------------------------------------------------
# Internal helpers (not part of the public API)
# ---------------------------------------------------------------------------
def _reject_ambiguous_dtype(raw: np.ndarray, context: str) -> None:
    """
    Reject input kinds that are not genuine numeric scalars/arrays, before
    any float64 coercion is attempted.

    NumPy will silently coerce several input kinds into floats in ways
    that would hide a caller error rather than surface it:
    * A Python/NumPy boolean is a subtype of integer in both Python and
      NumPy, so ``np.asarray(True, dtype=float)`` silently becomes
      ``1.0``. A boolean is a logical flag, not a physical quantity, so
      it is rejected outright.
    * A numeric-looking string such as ``"3.5"`` (or a string array) would
      otherwise be silently parsed into a float by NumPy.
    * A complex value has no meaning for any physical quantity handled by
      this module and would otherwise silently lose its imaginary part.

    Only integer- or floating-dtype input is accepted; anything else
    (bool, string/bytes, complex, object, etc.) raises ``TypeError``.
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


def _to_array(value: ArrayLike) -> tuple[np.ndarray, bool]:
    """
    Convert input to a float64 ndarray; report whether input was scalar.

    Validates the input's dtype kind BEFORE coercion (see
    `_reject_ambiguous_dtype`) so that booleans, strings (including
    numeric-looking strings), and complex values raise `TypeError` rather
    than being silently coerced into a float.
    """
    raw = np.asarray(value)
    _reject_ambiguous_dtype(raw, "unit conversion input")
    arr = raw.astype(np.float64)
    is_scalar = arr.ndim == 0
    return arr, is_scalar


def _restore_shape(arr: np.ndarray, is_scalar: bool) -> Union[float, np.ndarray]:
    """Undo _to_array: return a Python float for scalar input, else the array."""
    if is_scalar:
        return float(arr)
    return arr


def _reject_non_finite_except_nan(arr: np.ndarray, name: str) -> None:
    """Raise ValueError if any element is +inf or -inf (NaN is allowed)."""
    inf_mask = np.isinf(arr)
    if np.any(inf_mask):
        bad = arr[inf_mask]
        raise ValueError(
            f"{name}: infinite value(s) are not physically valid: {bad.tolist()}"
        )


def _reject_where(mask: np.ndarray, arr: np.ndarray, name: str, reason: str) -> None:
    """Raise ValueError if `mask` selects any element, listing the bad values."""
    if np.any(mask):
        bad = arr[mask]
        raise ValueError(f"{name}: {reason}: {bad.tolist()}")


def _validate_strictly_positive(arr: np.ndarray, name: str) -> None:
    """Allow NaN; reject inf; reject values <= 0 among finite, non-NaN entries."""
    _reject_non_finite_except_nan(arr, name)
    finite_mask = ~np.isnan(arr)
    _reject_where(
        finite_mask & (arr <= 0.0), arr, name, "must be strictly positive (nonphysical value <= 0 found)"
    )


def _validate_non_negative(arr: np.ndarray, name: str) -> None:
    """Allow NaN; reject inf; reject values < 0 among finite, non-NaN entries."""
    _reject_non_finite_except_nan(arr, name)
    finite_mask = ~np.isnan(arr)
    _reject_where(
        finite_mask & (arr < 0.0), arr, name, "must be non-negative (nonphysical negative value found)"
    )


def _validate_finite(arr: np.ndarray, name: str) -> None:
    """Allow NaN; reject inf only (no sign/magnitude restriction)."""
    _reject_non_finite_except_nan(arr, name)


# ---------------------------------------------------------------------------
# Length: metres <-> feet
# ---------------------------------------------------------------------------
def feet_to_meters(value_ft: ArrayLike) -> Union[float, np.ndarray]:
    """
    Convert length/depth from feet to metres.

    Equation
    --------
    m = ft * 0.3048  (exact, international foot)

    Parameters
    ----------
    value_ft : scalar or ndarray
        Length or depth in feet. NaN preserved. No sign restriction, since
        depths/elevations may legitimately be referenced above a datum
        (negative) depending on the depth reference in use.

    Returns
    -------
    Same shape as input, in metres.

    Raises
    ------
    ValueError
        If any finite input is +/-inf.
    """
    arr, is_scalar = _to_array(value_ft)
    _validate_finite(arr, "feet_to_meters(value_ft)")
    out = arr * CONST.FT_TO_M
    return _restore_shape(out, is_scalar)


def meters_to_feet(value_m: ArrayLike) -> Union[float, np.ndarray]:
    """
    Convert length/depth from metres to feet.

    Equation
    --------
    ft = m / 0.3048  (exact, international foot)

    See `feet_to_meters` for parameter/return/NaN/validation conventions.
    """
    arr, is_scalar = _to_array(value_m)
    _validate_finite(arr, "meters_to_feet(value_m)")
    out = arr / CONST.FT_TO_M
    return _restore_shape(out, is_scalar)


# ---------------------------------------------------------------------------
# Sonic transit time (slowness) <-> velocity
# ---------------------------------------------------------------------------
def us_per_ft_to_m_per_s(slowness_us_per_ft: ArrayLike) -> Union[float, np.ndarray]:
    """
    Convert acoustic slowness (sonic transit time) in microseconds per foot
    to compressional/shear velocity in metres per second.

    This is a definitional reciprocal-and-unit-scaling relationship, not an
    empirical correlation:

        V [ft/s]  = 1e6 / DT [us/ft]        (definition of slowness)
        V [m/s]   = V [ft/s] * 0.3048       (length unit conversion)
                  = 0.3048e6 / DT [us/ft]
                  = 304800 / DT [us/ft]

    Parameters
    ----------
    slowness_us_per_ft : scalar or ndarray
        DTCO/DTSM-style sonic transit time, microseconds per foot.
        Must be strictly positive where not NaN (zero or negative
        transit time is nonphysical - it implies infinite or negative
        velocity).

    Returns
    -------
    Velocity in m/s, same shape as input.

    Raises
    ------
    ValueError
        If any finite input is <= 0, or +/-inf.
    """
    arr, is_scalar = _to_array(slowness_us_per_ft)
    _validate_strictly_positive(arr, "us_per_ft_to_m_per_s(slowness_us_per_ft)")
    out = (CONST.FT_TO_M * 1.0e6) / arr
    return _restore_shape(out, is_scalar)


def m_per_s_to_us_per_ft(velocity_m_s: ArrayLike) -> Union[float, np.ndarray]:
    """
    Convert velocity in metres per second to acoustic slowness in
    microseconds per foot (inverse of `us_per_ft_to_m_per_s`).

    Equation
    --------
    DT [us/ft] = 304800 / V [m/s]

    Parameters
    ----------
    velocity_m_s : scalar or ndarray
        Velocity, m/s. Must be strictly positive where not NaN (zero or
        negative velocity is nonphysical for an acoustic wave speed).

    Returns
    -------
    Slowness in us/ft, same shape as input.
    """
    arr, is_scalar = _to_array(velocity_m_s)
    _validate_strictly_positive(arr, "m_per_s_to_us_per_ft(velocity_m_s)")
    out = (CONST.FT_TO_M * 1.0e6) / arr
    return _restore_shape(out, is_scalar)


# ---------------------------------------------------------------------------
# Density: g/cc (= g/cm3) <-> kg/m3
# ---------------------------------------------------------------------------
def gcc_to_kgm3(density_gcc: ArrayLike) -> Union[float, np.ndarray]:
    """
    Convert bulk density from g/cc (g/cm^3) to kg/m^3.

    Equation
    --------
    kg/m3 = g/cc * 1000   (exact: 1 g/cm3 = 1000 kg/m3, from 1 cm3 = 1e-6 m3
                            and 1 g = 1e-3 kg)

    Parameters
    ----------
    density_gcc : scalar or ndarray
        Bulk density (e.g. RHOB), g/cc. Must be strictly positive where
        not NaN (zero/negative density is nonphysical).
    """
    arr, is_scalar = _to_array(density_gcc)
    _validate_strictly_positive(arr, "gcc_to_kgm3(density_gcc)")
    out = arr * 1000.0
    return _restore_shape(out, is_scalar)


def kgm3_to_gcc(density_kgm3: ArrayLike) -> Union[float, np.ndarray]:
    """
    Convert bulk density from kg/m^3 to g/cc (g/cm^3).

    Equation
    --------
    g/cc = kg/m3 / 1000

    See `gcc_to_kgm3` for validation conventions.
    """
    arr, is_scalar = _to_array(density_kgm3)
    _validate_strictly_positive(arr, "kgm3_to_gcc(density_kgm3)")
    out = arr / 1000.0
    return _restore_shape(out, is_scalar)


# ---------------------------------------------------------------------------
# Pressure / stress: Pa <-> MPa <-> psi
# ---------------------------------------------------------------------------
def pa_to_mpa(pressure_pa: ArrayLike) -> Union[float, np.ndarray]:
    """Convert pressure/stress from Pa to MPa (MPa = Pa / 1e6, exact). Non-negative required (NaN preserved)."""
    arr, is_scalar = _to_array(pressure_pa)
    _validate_non_negative(arr, "pa_to_mpa(pressure_pa)")
    return _restore_shape(arr / 1.0e6, is_scalar)


def mpa_to_pa(pressure_mpa: ArrayLike) -> Union[float, np.ndarray]:
    """Convert pressure/stress from MPa to Pa (Pa = MPa * 1e6, exact). Non-negative required (NaN preserved)."""
    arr, is_scalar = _to_array(pressure_mpa)
    _validate_non_negative(arr, "mpa_to_pa(pressure_mpa)")
    return _restore_shape(arr * 1.0e6, is_scalar)


def psi_to_pa(pressure_psi: ArrayLike) -> Union[float, np.ndarray]:
    """
    Convert pressure/stress from psi to Pa.

    Equation
    --------
    Pa = psi * 6894.757293168  (1 psi = 1 lbf/in^2, a definitional
    relationship derived from the exact pound, standard-gravity, and inch
    definitions; the numeric factor itself is a finite-precision float64
    approximation of that exact relationship - see Constants.PSI_TO_PA)

    Non-negative required (NaN preserved). Pressure/stress quantities in
    this project (formation pressure, overburden, mud weight equivalent,
    etc.) are treated as non-negative by convention; a negative pressure
    input is rejected as nonphysical for this project's use cases rather
    than silently accepted.
    """
    arr, is_scalar = _to_array(pressure_psi)
    _validate_non_negative(arr, "psi_to_pa(pressure_psi)")
    return _restore_shape(arr * CONST.PSI_TO_PA, is_scalar)


def pa_to_psi(pressure_pa: ArrayLike) -> Union[float, np.ndarray]:
    """Convert pressure/stress from Pa to psi (psi = Pa / 6894.757293168; see Constants.PSI_TO_PA for a note on its finite-precision derivation). Non-negative required."""
    arr, is_scalar = _to_array(pressure_pa)
    _validate_non_negative(arr, "pa_to_psi(pressure_pa)")
    return _restore_shape(arr / CONST.PSI_TO_PA, is_scalar)


def mpa_to_psi(pressure_mpa: ArrayLike) -> Union[float, np.ndarray]:
    """Convert pressure/stress from MPa to psi (composed from mpa_to_pa + pa_to_psi)."""
    return pa_to_psi(mpa_to_pa(pressure_mpa))


def psi_to_mpa(pressure_psi: ArrayLike) -> Union[float, np.ndarray]:
    """Convert pressure/stress from psi to MPa (composed from psi_to_pa + pa_to_mpa)."""
    return pa_to_mpa(psi_to_pa(pressure_psi))


# ---------------------------------------------------------------------------
# Angle: degrees <-> radians
# ---------------------------------------------------------------------------
def degrees_to_radians(angle_deg: ArrayLike) -> Union[float, np.ndarray]:
    """
    Convert angle from degrees to radians (rad = deg * pi / 180, exact).

    Used for deviation-survey inclination/azimuth and, later, stress
    azimuths. No sign or magnitude restriction is imposed here (azimuths
    and cumulative angles may exceed +/-360 depending on upstream
    convention); only +/-inf is rejected. Range normalization, if needed,
    is a survey-processing concern for a later increment, not a unit
    conversion concern.
    """
    arr, is_scalar = _to_array(angle_deg)
    _validate_finite(arr, "degrees_to_radians(angle_deg)")
    out = np.deg2rad(arr)
    return _restore_shape(out, is_scalar)


def radians_to_degrees(angle_rad: ArrayLike) -> Union[float, np.ndarray]:
    """Convert angle from radians to degrees (deg = rad * 180 / pi, exact). See `degrees_to_radians`."""
    arr, is_scalar = _to_array(angle_rad)
    _validate_finite(arr, "radians_to_degrees(angle_rad)")
    out = np.rad2deg(arr)
    return _restore_shape(out, is_scalar)


# ---------------------------------------------------------------------------
# Mud weight: ppg <-> kg/m3
# ---------------------------------------------------------------------------
def ppg_to_kgm3(density_ppg: ArrayLike) -> Union[float, np.ndarray]:
    """
    Convert mud weight from pounds per US gallon (ppg) to kg/m^3.

    Equation
    --------
    kg/m3 = ppg * (0.45359237 / 0.003785411784) = ppg * 119.82642731689663

    (the ratio is derived from the exact international pound and US liquid
    gallon definitions; the digits above are the float64 value computed at
    runtime by Constants.PPG_TO_KGM3, not a claim of infinite decimal
    exactness - see the module-level "numerical precision" note)

    Must be strictly positive where not NaN.
    """
    arr, is_scalar = _to_array(density_ppg)
    _validate_strictly_positive(arr, "ppg_to_kgm3(density_ppg)")
    out = arr * CONST.PPG_TO_KGM3
    return _restore_shape(out, is_scalar)


def kgm3_to_ppg(density_kgm3: ArrayLike) -> Union[float, np.ndarray]:
    """Convert mud weight from kg/m^3 to ppg (inverse of `ppg_to_kgm3`). Must be strictly positive where not NaN."""
    arr, is_scalar = _to_array(density_kgm3)
    _validate_strictly_positive(arr, "kgm3_to_ppg(density_kgm3)")
    out = arr / CONST.PPG_TO_KGM3
    return _restore_shape(out, is_scalar)


# ---------------------------------------------------------------------------
# Pressure gradient <-> equivalent fluid density, and equivalent mud weight
# ---------------------------------------------------------------------------
def pressure_gradient_to_density(
    gradient_pa_per_m: ArrayLike, gravity_m_s2: float = CONST.STANDARD_GRAVITY
) -> Union[float, np.ndarray]:
    """
    Convert a hydrostatic pressure gradient to an equivalent fluid density.

    Equation (hydrostatic definition, not an empirical correlation)
    -----------------------------------------------------------------
    dP/dz = rho * g   =>   rho = (dP/dz) / g

    Parameters
    ----------
    gradient_pa_per_m : scalar or ndarray
        Pressure gradient, Pa/m. Must be non-negative where not NaN.
    gravity_m_s2 : float, optional
        Gravitational acceleration, m/s^2. Defaults to standard gravity
        (9.80665 m/s^2). Exposed as a parameter (rather than hard-coded)
        so a project-specific local-gravity value can be substituted if
        one is ever measured/provided; absent such a value, standard
        gravity is used and this default must be reported alongside any
        result that depends on it.

    Returns
    -------
    Equivalent density, kg/m^3, same shape as gradient input.

    Raises
    ------
    ValueError
        If gravity_m_s2 is not strictly positive, or gradient is negative
        or non-finite (excluding NaN).
    """
    if isinstance(gravity_m_s2, (bool, np.bool_)):
        raise TypeError(
            "pressure_gradient_to_density: gravity_m_s2 must be a numeric value, "
            "not a boolean."
        )
    if not np.isfinite(gravity_m_s2) or gravity_m_s2 <= 0.0:
        raise ValueError(
            f"pressure_gradient_to_density: gravity_m_s2 must be a finite, "
            f"strictly positive value, got {gravity_m_s2}"
        )
    arr, is_scalar = _to_array(gradient_pa_per_m)
    _validate_non_negative(arr, "pressure_gradient_to_density(gradient_pa_per_m)")
    out = arr / gravity_m_s2
    return _restore_shape(out, is_scalar)


def density_to_pressure_gradient(
    density_kgm3: ArrayLike, gravity_m_s2: float = CONST.STANDARD_GRAVITY
) -> Union[float, np.ndarray]:
    """
    Convert a fluid density to its hydrostatic pressure gradient.

    Equation (hydrostatic definition): dP/dz = rho * g

    Parameters
    ----------
    density_kgm3 : scalar or ndarray
        Fluid density, kg/m^3. Must be strictly positive where not NaN.
    gravity_m_s2 : float, optional
        See `pressure_gradient_to_density`.

    Returns
    -------
    Pressure gradient, Pa/m, same shape as input.
    """
    if isinstance(gravity_m_s2, (bool, np.bool_)):
        raise TypeError(
            "density_to_pressure_gradient: gravity_m_s2 must be a numeric value, "
            "not a boolean."
        )
    if not np.isfinite(gravity_m_s2) or gravity_m_s2 <= 0.0:
        raise ValueError(
            f"density_to_pressure_gradient: gravity_m_s2 must be a finite, "
            f"strictly positive value, got {gravity_m_s2}"
        )
    arr, is_scalar = _to_array(density_kgm3)
    _validate_strictly_positive(arr, "density_to_pressure_gradient(density_kgm3)")
    out = arr * gravity_m_s2
    return _restore_shape(out, is_scalar)


def equivalent_mud_weight_kgm3(
    pressure_pa: ArrayLike, tvd_m: ArrayLike, gravity_m_s2: float = CONST.STANDARD_GRAVITY
) -> Union[float, np.ndarray]:
    """
    Compute the equivalent (static) mud weight required to hydrostatically
    balance a given pressure at a given true vertical depth.

    Equation (hydrostatic definition, not an empirical correlation)
    -----------------------------------------------------------------
    EMW [kg/m3] = P [Pa] / (g [m/s^2] * TVD [m])

    This is the standard "equivalent mud weight" (EMW) relationship used to
    express a pressure as a mud density. It assumes a single-fluid
    hydrostatic column from surface (TVD = 0) to the depth of interest and
    a vertical well path measured as TVD; it does NOT account for
    friction/ECD, non-vertical wellbore geometry beyond TVD itself, or a
    non-uniform fluid column - those are drilling-engineering
    considerations outside the scope of this unit-conversion module.

    Parameters
    ----------
    pressure_pa : scalar or ndarray
        Pressure, Pa. Must be non-negative where not NaN.
    tvd_m : scalar or ndarray
        True vertical depth, m, measured from the same datum as the
        pressure reference. Must be strictly positive where not NaN
        (TVD = 0 makes the equivalent density undefined - division by
        zero - and is rejected rather than silently producing inf).
    gravity_m_s2 : float, optional
        See `pressure_gradient_to_density`.

    Returns
    -------
    Equivalent mud weight, kg/m^3, broadcast to the common shape of
    `pressure_pa` and `tvd_m`.

    Raises
    ------
    ValueError
        If gravity is invalid, if any finite pressure is negative, or if
        any finite TVD is <= 0.
    """
    if isinstance(gravity_m_s2, (bool, np.bool_)):
        raise TypeError(
            "equivalent_mud_weight_kgm3: gravity_m_s2 must be a numeric value, "
            "not a boolean."
        )
    if not np.isfinite(gravity_m_s2) or gravity_m_s2 <= 0.0:
        raise ValueError(
            f"equivalent_mud_weight_kgm3: gravity_m_s2 must be a finite, "
            f"strictly positive value, got {gravity_m_s2}"
        )
    p_arr, p_scalar = _to_array(pressure_pa)
    z_arr, z_scalar = _to_array(tvd_m)
    _validate_non_negative(p_arr, "equivalent_mud_weight_kgm3(pressure_pa)")
    _validate_strictly_positive(z_arr, "equivalent_mud_weight_kgm3(tvd_m)")
    out = p_arr / (gravity_m_s2 * z_arr)
    is_scalar = p_scalar and z_scalar
    return _restore_shape(np.asarray(out, dtype=np.float64), is_scalar)


# ---------------------------------------------------------------------------
# Seismic time: one-way time (OWT) <-> two-way time (TWT)
# ---------------------------------------------------------------------------
def owt_to_twt(owt: ArrayLike) -> Union[float, np.ndarray]:
    """
    Convert one-way travel time to two-way travel time.

    Equation
    --------
    TWT = 2 * OWT

    This is a pure, unambiguous time-domain scaling (a checkshot/VSP OWT
    doubled to the TWT convention used by surface seismic). It does NOT
    perform any time-to-depth conversion (that requires a velocity model
    and is out of scope for this module). Input must be non-negative where
    not NaN (a negative travel time is nonphysical).
    """
    arr, is_scalar = _to_array(owt)
    _validate_non_negative(arr, "owt_to_twt(owt)")
    return _restore_shape(arr * 2.0, is_scalar)


def twt_to_owt(twt: ArrayLike) -> Union[float, np.ndarray]:
    """
    Convert two-way travel time to one-way travel time.

    Equation
    --------
    OWT = TWT / 2

    See `owt_to_twt` for scope and validation notes. As with `owt_to_twt`,
    this is only unambiguous because both quantities are being expressed
    in the same fixed 2x relationship for the same travel path; it should
    not be used to relate travel times measured along different paths
    (e.g. offset VSP vs. zero-offset checkshot) without survey-specific
    justification, which is outside this module's scope.
    """
    arr, is_scalar = _to_array(twt)
    _validate_non_negative(arr, "twt_to_owt(twt)")
    return _restore_shape(arr / 2.0, is_scalar)
