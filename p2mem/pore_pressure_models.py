"""Typed records and invariants for Increment 8.

The records distinguish measured/locked inputs, configured assumptions,
hydrostatic references, and derived screening scenarios.  None represents a
calibrated formation-pressure measurement or an overpressure prediction.
"""

from dataclasses import dataclass
import math
from numbers import Integral, Real
from typing import Optional, Tuple


class PorePressureInputError(ValueError):
    """Raised when an Increment 8 public input violates its contract."""


ASSURANCE_TIER = "Tier C - Screening-Level / Uncalibrated Educational"
PACKAGE_VERSION = "0.8.1"
CONFIG_SCHEMA_VERSION = "8.0.1"
APPROVED_GRAVITY_M_S2 = 9.80665
APPROVED_FLUID_DENSITIES_KG_M3: Tuple[float, ...] = (1020.0, 1025.0, 1030.0)
APPROVED_BIOT_ALPHA_SCENARIOS: Tuple[float, ...] = (0.8, 1.0)
APPROVED_PROFILE_BIOT_ALPHA = 1.0
APPROVED_PROFILE_FLUID_DENSITY_KG_M3 = 1025.0
WELL_KEYS: Tuple[str, ...] = (
    "Boreas_1", "Poseidon_2", "Poseidon_North_1", "Proteus_1ST2",
)
PRESSURE_DATA_TYPES: Tuple[str, ...] = (
    "RFT", "MDT", "DST", "FIT", "LOT", "XLOT", "DFIT",
)
NCT_STATUSES: Tuple[str, ...] = (
    "NOT_ELIGIBLE_INPUT_QC_EXCLUSION",
    "WITHHELD_NO_PRESSURE_CALIBRATION_OR_INDEPENDENT_NORMAL_INTERVAL",
)
OVERBURDEN_STATUSES: Tuple[str, ...] = (
    "screening_sensitivity_only", "partial_measured_increment_only",
    "not_eligible",
)
SV_SCENARIOS: Tuple[str, ...] = ("low", "base", "high")
FLUID_SCENARIOS: Tuple[str, ...] = ("low", "base", "high")


def finite_real(value, name: str, *, minimum: Optional[float] = None,
                maximum: Optional[float] = None) -> float:
    """Return a strict finite real, rejecting bool, strings and complex."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise PorePressureInputError(f"{name} must be a finite real number.")
    out = float(value)
    if not math.isfinite(out):
        raise PorePressureInputError(f"{name} must be finite.")
    if minimum is not None and out < minimum:
        raise PorePressureInputError(f"{name} must be >= {minimum}.")
    if maximum is not None and out > maximum:
        raise PorePressureInputError(f"{name} must be <= {maximum}.")
    return out


def strict_int(value, name: str, *, minimum: int = 0) -> int:
    """Return an integer without coercion; bool is never an integer here."""
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise PorePressureInputError(f"{name} must be an integer.")
    out = int(value)
    if out < minimum:
        raise PorePressureInputError(f"{name} must be >= {minimum}.")
    return out


def exact_bool(value, name: str) -> bool:
    if type(value) is not bool:
        raise PorePressureInputError(f"{name} must be exactly bool.")
    return value


def enum(value, name: str, allowed: Tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise PorePressureInputError(f"{name} must be one of {allowed!r}.")
    return value


@dataclass(frozen=True)
class PressureConfig:
    schema_version: str
    assurance_tier: str
    gravity_m_s2: float
    fluid_density_low_kg_m3: float
    fluid_density_base_kg_m3: float
    fluid_density_high_kg_m3: float
    biot_alpha_scenarios: Tuple[float, ...]
    profile_biot_alpha: float
    profile_fluid_density_kg_m3: float
    pressure_calibration_types: Tuple[str, ...]
    pressure_calibration_file_count: int
    cross_well_transfer_allowed: bool
    nct_fit_enabled: bool
    overpressure_transform_enabled: bool
    pressure_calibration_required: bool
    independent_normal_interval_evidence_required: bool
    sonic_checkshot_drift_correction_allowed: bool
    extrapolation_allowed: bool
    increment_9_started: bool

    def __post_init__(self) -> None:
        if self.schema_version != CONFIG_SCHEMA_VERSION:
            raise PorePressureInputError(
                f"schema_version must be {CONFIG_SCHEMA_VERSION!r}.")
        if self.assurance_tier != ASSURANCE_TIER:
            raise PorePressureInputError("Unexpected assurance_tier.")
        g = finite_real(self.gravity_m_s2, "gravity_m_s2", minimum=0.0)
        if g == 0.0:
            raise PorePressureInputError("gravity_m_s2 must be > 0.")
        lo = finite_real(self.fluid_density_low_kg_m3, "fluid_density_low_kg_m3", minimum=0.0)
        base = finite_real(self.fluid_density_base_kg_m3, "fluid_density_base_kg_m3", minimum=0.0)
        hi = finite_real(self.fluid_density_high_kg_m3, "fluid_density_high_kg_m3", minimum=0.0)
        if not lo < base < hi:
            raise PorePressureInputError("Fluid-density scenarios must satisfy low < base < high.")
        if not isinstance(self.biot_alpha_scenarios, tuple) or not self.biot_alpha_scenarios:
            raise PorePressureInputError("biot_alpha_scenarios must be a non-empty tuple.")
        alphas = tuple(finite_real(v, "biot_alpha", minimum=0.0, maximum=1.0)
                       for v in self.biot_alpha_scenarios)
        if len(set(alphas)) != len(alphas):
            raise PorePressureInputError("biot_alpha_scenarios must be unique.")
        finite_real(self.profile_biot_alpha, "profile_biot_alpha", minimum=0.0, maximum=1.0)
        finite_real(self.profile_fluid_density_kg_m3, "profile_fluid_density_kg_m3", minimum=0.0)
        if g != APPROVED_GRAVITY_M_S2:
            raise PorePressureInputError(
                "gravity_m_s2 must equal the approved Increment 8 value.")
        if (lo, base, hi) != APPROVED_FLUID_DENSITIES_KG_M3:
            raise PorePressureInputError(
                "Fluid-density scenarios must equal the approved Increment 8 values.")
        if alphas != APPROVED_BIOT_ALPHA_SCENARIOS:
            raise PorePressureInputError(
                "biot_alpha_scenarios must equal the approved Increment 8 values.")
        if self.profile_biot_alpha != APPROVED_PROFILE_BIOT_ALPHA:
            raise PorePressureInputError(
                "profile_biot_alpha must equal the approved Increment 8 value.")
        if self.profile_fluid_density_kg_m3 != APPROVED_PROFILE_FLUID_DENSITY_KG_M3:
            raise PorePressureInputError(
                "profile_fluid_density_kg_m3 must equal the approved Increment 8 value.")
        if tuple(self.pressure_calibration_types) != PRESSURE_DATA_TYPES:
            raise PorePressureInputError("pressure_calibration_types must match the closed required set.")
        strict_int(self.pressure_calibration_file_count, "pressure_calibration_file_count")
        for name in (
            "nct_fit_enabled", "overpressure_transform_enabled",
            "pressure_calibration_required",
            "independent_normal_interval_evidence_required",
            "cross_well_transfer_allowed",
            "sonic_checkshot_drift_correction_allowed",
            "extrapolation_allowed",
            "increment_9_started",
        ):
            exact_bool(getattr(self, name), name)
        if self.pressure_calibration_file_count != 0:
            raise PorePressureInputError("Increment 8 has no approved pressure-calibration file.")
        if (self.nct_fit_enabled or self.overpressure_transform_enabled
                or self.cross_well_transfer_allowed
                or self.sonic_checkshot_drift_correction_allowed
                or self.extrapolation_allowed or self.increment_9_started):
            raise PorePressureInputError("Prediction and extrapolation must remain disabled in Increment 8.")
        if not self.pressure_calibration_required or not self.independent_normal_interval_evidence_required:
            raise PorePressureInputError("Both prediction evidence requirements must remain enabled.")


@dataclass(frozen=True)
class PressureDataAvailability:
    well_key: str
    rft_count: int
    mdt_count: int
    dst_count: int
    fit_count: int
    lot_count: int
    xlot_count: int
    dfit_count: int
    availability_status: str

    def __post_init__(self) -> None:
        enum(self.well_key, "well_key", WELL_KEYS)
        counts = [strict_int(getattr(self, f), f) for f in (
            "rft_count", "mdt_count", "dst_count", "fit_count",
            "lot_count", "xlot_count", "dfit_count",
        )]
        if self.availability_status != "NOT_AVAILABLE" or any(counts):
            raise PorePressureInputError(
                "No approved pressure-calibration measurement is available in Increment 8.")


@dataclass(frozen=True)
class NctReadiness:
    well_key: str
    status: str
    candidate_configurations: int
    qualifying_thickness_min_tvd_m: Optional[float]
    qualifying_thickness_max_tvd_m: Optional[float]
    thickness_sensitivity_factor: Optional[float]
    pressure_calibration_available: bool
    independent_normal_interval_evidence_available: bool
    nct_fit_performed: bool
    overpressure_inferred: bool

    def __post_init__(self) -> None:
        enum(self.well_key, "well_key", WELL_KEYS)
        enum(self.status, "status", NCT_STATUSES)
        n = strict_int(self.candidate_configurations, "candidate_configurations")
        for f in (
            "pressure_calibration_available", "independent_normal_interval_evidence_available",
            "nct_fit_performed", "overpressure_inferred",
        ):
            exact_bool(getattr(self, f), f)
        if any((self.pressure_calibration_available,
                self.independent_normal_interval_evidence_available,
                self.nct_fit_performed, self.overpressure_inferred)):
            raise PorePressureInputError("Increment 8 readiness flags must all remain false.")
        values = (self.qualifying_thickness_min_tvd_m,
                  self.qualifying_thickness_max_tvd_m,
                  self.thickness_sensitivity_factor)
        if n == 0:
            if self.status != NCT_STATUSES[0] or any(v is not None for v in values):
                raise PorePressureInputError("No-candidate readiness record is inconsistent.")
        else:
            if self.status != NCT_STATUSES[1] or any(v is None for v in values):
                raise PorePressureInputError("Candidate readiness record is incomplete.")
            lo = finite_real(values[0], "qualifying_thickness_min_tvd_m", minimum=0.0)
            hi = finite_real(values[1], "qualifying_thickness_max_tvd_m", minimum=0.0)
            factor = finite_real(values[2], "thickness_sensitivity_factor", minimum=1.0)
            if lo <= 0.0 or hi < lo or not math.isclose(factor, hi / lo, rel_tol=1e-12):
                raise PorePressureInputError("NCT thickness sensitivity values are inconsistent.")


@dataclass(frozen=True)
class HydrostaticReferenceNode:
    well_key: str
    node_index: int
    fluid_scenario: str
    tvdss_m: float
    fluid_density_kg_m3: float
    gravity_m_s2: float
    pressure_pa: float

    def __post_init__(self) -> None:
        enum(self.well_key, "well_key", WELL_KEYS)
        strict_int(self.node_index, "node_index")
        enum(self.fluid_scenario, "fluid_scenario", FLUID_SCENARIOS)
        z = finite_real(self.tvdss_m, "tvdss_m", minimum=0.0)
        rho = finite_real(self.fluid_density_kg_m3, "fluid_density_kg_m3", minimum=0.0)
        g = finite_real(self.gravity_m_s2, "gravity_m_s2", minimum=0.0)
        p = finite_real(self.pressure_pa, "pressure_pa", minimum=0.0)
        if not math.isclose(p, rho * g * z, rel_tol=1e-12, abs_tol=1e-8):
            raise PorePressureInputError("Hydrostatic reference identity failed.")


@dataclass(frozen=True)
class EffectiveStressScenario:
    well_key: str
    sv_scenario: str
    fluid_scenario: str
    biot_alpha: float
    evaluation_tvdss_m: float
    total_vertical_stress_pa: float
    pore_pressure_reference_pa: float
    effective_vertical_stress_pa: float
    effective_stress_nonnegative: bool

    def __post_init__(self) -> None:
        enum(self.well_key, "well_key", WELL_KEYS)
        enum(self.sv_scenario, "sv_scenario", SV_SCENARIOS)
        enum(self.fluid_scenario, "fluid_scenario", FLUID_SCENARIOS)
        alpha = finite_real(self.biot_alpha, "biot_alpha", minimum=0.0, maximum=1.0)
        finite_real(self.evaluation_tvdss_m, "evaluation_tvdss_m", minimum=0.0)
        sv = finite_real(self.total_vertical_stress_pa, "total_vertical_stress_pa", minimum=0.0)
        pp = finite_real(self.pore_pressure_reference_pa, "pore_pressure_reference_pa", minimum=0.0)
        eff = finite_real(self.effective_vertical_stress_pa, "effective_vertical_stress_pa")
        flag = exact_bool(self.effective_stress_nonnegative, "effective_stress_nonnegative")
        expected = sv - alpha * pp
        if not math.isclose(eff, expected, rel_tol=1e-12, abs_tol=1e-8):
            raise PorePressureInputError("Effective-stress identity failed.")
        if flag != (eff >= 0.0):
            raise PorePressureInputError("effective_stress_nonnegative flag is inconsistent.")
