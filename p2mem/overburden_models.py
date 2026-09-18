"""
p2mem.overburden_models - typed Increment 7 structures, controlled vocabularies,
and constructor-level invariants for density QC and vertical overburden stress.

Scope
-----
This module holds DATA STRUCTURES and VOCABULARIES only. It reads no file,
computes no statistic, and integrates nothing. It exists so that every
Increment 7 record is constructed through a type that refuses to hold an
incoherent state, and so that every enumerated code this increment can emit is
declared in exactly one place.

Why the vocabularies live here rather than in `p2mem.wellframe_models`
----------------------------------------------------------------------
`p2mem.wellframe_models` is LOCKED Increment 6.1.7 content. Its
`APPROVED_LABELS`, `REGISTERED_STATEMENTS` and `REGISTERED_TEMPLATES`
registries were enumerated from the ACTUAL persisted Increment 6 export, and
their provenance strings say exactly that. Appending Increment 7 vocabulary to
those registries would (a) modify a locked file and (b) falsify the provenance
of the registry as a whole. Increment 7 therefore declares its own registries
here, and the Increment 7 output policy carries them in its own policy bundle.
The locked registries and the locked export path are untouched and continue to
govern the Increment 6 artifacts exactly as before.

Sign convention (verified, not assumed)
---------------------------------------
The locked `p2mem.depth_mapping` module documents and independently tests the
project's depth convention:

    MD and TVD are zero at the well datum (rotary table) and increase
    DOWNWARD; the datum elevation is referenced to mean sea level, positive
    UPWARD; therefore TVDSS_m = TVD_m - DatumElevation_m, and TVDSS is
    positive DOWNWARD from mean sea level.

Both TVD and TVDSS therefore increase downward, and a downward interval has a
POSITIVE increment in either coordinate. `dTVD == dTVDSS` exactly, because they
differ by a per-well constant. Increment 7 integrates in this convention and
re-verifies it at run time against the locked well frame rather than inferring
it from a variable name: see `p2mem.overburden.verify_depth_sign_convention`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import numpy as np

__all__ = [
    "OverburdenConfigError",
    "OverburdenInputError",
    "OverburdenEligibilityError",
    "DENSITY_MASK_NAMES",
    "GAP_CLASS_ISOLATED_SAMPLE",
    "GAP_CLASS_SHORT_INTERNAL",
    "GAP_CLASS_LONG_INTERNAL",
    "GAP_CLASS_SHALLOW",
    "GAP_CLASS_TERMINAL",
    "GAP_CLASS_UNMAPPED_DEPTH",
    "VALID_GAP_CLASSES",
    "GAP_DISPOSITION_BRIDGED",
    "GAP_DISPOSITION_UNRESOLVED",
    "GAP_DISPOSITION_NOT_APPLICABLE",
    "VALID_GAP_DISPOSITIONS",
    "STATUS_ABSOLUTE",
    "STATUS_SENSITIVITY_ONLY",
    "STATUS_PARTIAL_ONLY",
    "STATUS_NOT_ELIGIBLE",
    "VALID_OVERBURDEN_STATUSES",
    "REASON_RHOB_NOT_AVAILABLE",
    "REASON_RHOB_ALL_INVALID",
    "REASON_SHALLOW_COLUMN_UNRESOLVED",
    "REASON_SEABED_DATUM_UNRESOLVED",
    "REASON_INTERNAL_GAP_EXCEEDS_LIMIT",
    "REASON_INTERNAL_GAP_UNRESOLVED",
    "REASON_TERMINAL_COLUMN_UNRESOLVED",
    "REASON_DEPTH_MAPPING_INCOMPLETE",
    "REASON_SCREENING_BOUND_FAILURES",
    "REASON_SURVEY_COVERAGE_INSUFFICIENT",
    "REASON_NON_MONOTONIC_VERTICAL_DEPTH",
    "REASON_INSUFFICIENT_ELIGIBLE_SAMPLES",
    "REASON_UNIT_NOT_RESOLVED",
    "VALID_LIMITING_REASONS",
    "SEABED_BASIS_LOCKED_MARKER",
    "SEABED_BASIS_NOT_DETERMINABLE",
    "VALID_SEABED_BASES",
    "SCENARIO_LOW",
    "SCENARIO_BASE",
    "SCENARIO_HIGH",
    "SCENARIO_BASE_SEAWATER_LOW",
    "SCENARIO_BASE_SEAWATER_HIGH",
    "VALID_SCENARIO_NAMES",
    "SCENARIO_BASIS_LOW",
    "SCENARIO_BASIS_BASE",
    "SCENARIO_BASIS_HIGH",
    "VALID_SCENARIO_BASES",
    "OverburdenConfig",
    "DensityMaskSet",
    "DensityQcStats",
    "DensityGapRecord",
    "GapConditioningResult",
    "StressPartition",
    "VerticalStressProfile",
    "ShallowColumnScenario",
    "GapThresholdSensitivity",
    "OverburdenEligibility",
    "OverburdenIssue",
    "readonly",
]


# ---------------------------------------------------------------------------
# Typed exceptions
# ---------------------------------------------------------------------------

class OverburdenConfigError(ValueError):
    """Raised when `config/overburden_stress.yml` is missing, malformed,
    internally inconsistent, or missing a required key. A configuration
    problem is never silently defaulted."""


class OverburdenInputError(ValueError):
    """Raised for a structural or value defect in caller-supplied in-memory
    data: wrong dimensionality, length mismatch, non-finite or mis-ordered
    vertical coordinates, negative vertical increments, or an incoherent
    record. Deliberately distinct from `TypeError`, which this increment
    reserves for type-class defects (boolean, string, complex, object)."""


class OverburdenEligibilityError(RuntimeError):
    """Raised when a stress calculation is attempted for a well whose derived
    eligibility status forbids it. A hard scientific boundary, enforced as an
    exception rather than a silent empty result so that a caller cannot
    mistake 'nothing was computed' for 'zero stress'."""


# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------

#: The explicit, separately auditable per-sample masks Increment 7 constructs.
#: Every one of these is a full-length boolean array aligned sample-for-sample
#: with the well's canonical `MD_m`; none of them modifies a density value.
DENSITY_MASK_NAMES: Tuple[str, ...] = (
    "source_value_present",
    "finite_numeric_density",
    "unit_resolved",
    "screening_range_plausible",
    "below_seabed_sample",
    "depth_mapping_valid",
    "within_survey_coverage",
    "eligible_for_measured_integration",
    "bridged_short_gap",
    "unresolved_long_gap",
    "unresolved_shallow_column",
    "unresolved_terminal_column",
)

GAP_CLASS_ISOLATED_SAMPLE = "isolated_invalid_sample"
GAP_CLASS_SHORT_INTERNAL = "short_internal_gap"
GAP_CLASS_LONG_INTERNAL = "long_internal_gap"
GAP_CLASS_SHALLOW = "shallow_seabed_to_first_valid_gap"
GAP_CLASS_TERMINAL = "terminal_below_last_valid_gap"
GAP_CLASS_UNMAPPED_DEPTH = "gap_caused_by_missing_depth_mapping"
VALID_GAP_CLASSES: Tuple[str, ...] = (
    GAP_CLASS_ISOLATED_SAMPLE, GAP_CLASS_SHORT_INTERNAL, GAP_CLASS_LONG_INTERNAL,
    GAP_CLASS_SHALLOW, GAP_CLASS_TERMINAL, GAP_CLASS_UNMAPPED_DEPTH,
)

GAP_DISPOSITION_BRIDGED = "bridged_linear_in_tvd"
GAP_DISPOSITION_UNRESOLVED = "unresolved_not_bridged"
GAP_DISPOSITION_NOT_APPLICABLE = "not_applicable"
VALID_GAP_DISPOSITIONS: Tuple[str, ...] = (
    GAP_DISPOSITION_BRIDGED, GAP_DISPOSITION_UNRESOLVED, GAP_DISPOSITION_NOT_APPLICABLE,
)

STATUS_ABSOLUTE = "absolute_overburden_supported"
STATUS_SENSITIVITY_ONLY = "screening_sensitivity_only"
STATUS_PARTIAL_ONLY = "partial_measured_increment_only"
STATUS_NOT_ELIGIBLE = "not_eligible"
VALID_OVERBURDEN_STATUSES: Tuple[str, ...] = (
    STATUS_ABSOLUTE, STATUS_SENSITIVITY_ONLY, STATUS_PARTIAL_ONLY, STATUS_NOT_ELIGIBLE,
)

REASON_RHOB_NOT_AVAILABLE = "rhob_not_available"
REASON_RHOB_ALL_INVALID = "rhob_all_invalid"
REASON_SHALLOW_COLUMN_UNRESOLVED = "shallow_density_column_unresolved"
REASON_SEABED_DATUM_UNRESOLVED = "seabed_datum_unresolved"
REASON_INTERNAL_GAP_EXCEEDS_LIMIT = "internal_gap_exceeds_limit"
REASON_INTERNAL_GAP_UNRESOLVED = "internal_gap_unresolved"
REASON_TERMINAL_COLUMN_UNRESOLVED = "terminal_density_column_unresolved"
REASON_DEPTH_MAPPING_INCOMPLETE = "depth_mapping_incomplete"
REASON_SCREENING_BOUND_FAILURES = "screening_bound_failures"
REASON_SURVEY_COVERAGE_INSUFFICIENT = "survey_coverage_insufficient"
REASON_NON_MONOTONIC_VERTICAL_DEPTH = "non_monotonic_vertical_depth"
REASON_INSUFFICIENT_ELIGIBLE_SAMPLES = "insufficient_eligible_samples"
REASON_UNIT_NOT_RESOLVED = "density_unit_not_resolved"
VALID_LIMITING_REASONS: Tuple[str, ...] = (
    REASON_DEPTH_MAPPING_INCOMPLETE,
    REASON_INSUFFICIENT_ELIGIBLE_SAMPLES,
    REASON_INTERNAL_GAP_EXCEEDS_LIMIT,
    REASON_INTERNAL_GAP_UNRESOLVED,
    REASON_NON_MONOTONIC_VERTICAL_DEPTH,
    REASON_RHOB_ALL_INVALID,
    REASON_RHOB_NOT_AVAILABLE,
    REASON_SCREENING_BOUND_FAILURES,
    REASON_SEABED_DATUM_UNRESOLVED,
    REASON_SHALLOW_COLUMN_UNRESOLVED,
    REASON_SURVEY_COVERAGE_INSUFFICIENT,
    REASON_TERMINAL_COLUMN_UNRESOLVED,
    REASON_UNIT_NOT_RESOLVED,
)

SEABED_BASIS_LOCKED_MARKER = "locked_increment5_survey_corrected_sea_bed_marker"
SEABED_BASIS_NOT_DETERMINABLE = "not_determinable_no_approved_formation_tops"
VALID_SEABED_BASES: Tuple[str, ...] = (
    SEABED_BASIS_LOCKED_MARKER, SEABED_BASIS_NOT_DETERMINABLE,
)

SCENARIO_LOW = "low"
SCENARIO_BASE = "base"
SCENARIO_HIGH = "high"
SCENARIO_BASE_SEAWATER_LOW = "base_seawater_low"
SCENARIO_BASE_SEAWATER_HIGH = "base_seawater_high"
VALID_SCENARIO_NAMES: Tuple[str, ...] = (
    SCENARIO_LOW, SCENARIO_BASE, SCENARIO_HIGH,
    SCENARIO_BASE_SEAWATER_LOW, SCENARIO_BASE_SEAWATER_HIGH,
)

# These tokens deliberately say "scenario", not "floor", "ceiling" or
# "bound".  The shallow interval is unmeasured, so its two endpoint densities
# are transparent sensitivity assumptions rather than rigorous physical
# limits on the unknown depth-averaged density.
SCENARIO_BASIS_LOW = "configured_seawater_density_conditional_low_scenario"
SCENARIO_BASIS_BASE = "arithmetic_midpoint_of_low_and_high_no_evidentiary_support"
SCENARIO_BASIS_HIGH = "own_well_measured_p05_illustrative_upper_scenario"
VALID_SCENARIO_BASES: Tuple[str, ...] = (
    SCENARIO_BASIS_LOW, SCENARIO_BASIS_BASE, SCENARIO_BASIS_HIGH,
)


# ---------------------------------------------------------------------------
# Shared validation helpers
# ---------------------------------------------------------------------------

def readonly(arr: np.ndarray) -> np.ndarray:
    """Return a read-only view of `arr`.

    Every mask and derived array this increment publishes is handed out
    read-only so that one consumer cannot mutate a shared object and silently
    change another consumer's result. Mirrors the locked well-frame
    `_readonly` precedent; a ~4-line local copy is deliberately preferred over
    editing a locked module to export a private helper.
    """
    view = np.asarray(arr)
    view = view.view()
    view.setflags(write=False)
    return view


def _require_exact_int(value, context: str) -> int:
    """Accept only a genuine Python `int`.

    `True` is an `int` in Python and `1.0` compares equal to `1`; both are
    rejected. A count that arrived as a float is a defect in the caller, not
    something to round.
    """
    if isinstance(value, (bool, np.bool_)):
        raise OverburdenInputError(f"{context}: boolean is not an integer count.")
    if isinstance(value, (np.integer,)):
        return int(value)
    if type(value) is not int:
        raise OverburdenInputError(
            f"{context}: expected an int count, got {type(value).__name__} {value!r}.")
    return value


def _require_nonneg_int(value, context: str) -> int:
    out = _require_exact_int(value, context)
    if out < 0:
        raise OverburdenInputError(f"{context}: count must be >= 0, got {out}.")
    return out


def _require_finite_float(value, context: str, allow_none: bool = False) -> Optional[float]:
    if value is None:
        if allow_none:
            return None
        raise OverburdenInputError(f"{context}: a finite number is required, got None.")
    if isinstance(value, (bool, np.bool_)):
        raise OverburdenInputError(f"{context}: boolean is not a numeric quantity.")
    if isinstance(value, complex) or isinstance(value, np.complexfloating):
        raise OverburdenInputError(f"{context}: complex is not a numeric quantity.")
    if isinstance(value, str) or isinstance(value, bytes):
        raise OverburdenInputError(f"{context}: string/bytes is not a numeric quantity.")
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise OverburdenInputError(
            f"{context}: value {value!r} is not convertible to a float.") from exc
    if not math.isfinite(out):
        raise OverburdenInputError(f"{context}: value must be finite, got {out!r}.")
    return out


def _require_in(value, allowed: Tuple[str, ...], context: str) -> str:
    if value not in allowed:
        raise OverburdenInputError(
            f"{context}: {value!r} is not one of {list(allowed)}.")
    return value


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OverburdenConfig:
    """The validated contents of `config/overburden_stress.yml`.

    Frozen: a configuration value must not change between the moment a result
    is computed and the moment its assumption register is exported, or the
    exported register would not describe the run that produced the numbers.
    """

    source_filename: str
    schema_version: str
    increment: int
    assurance_tier: str

    canonical_curve_name: str
    accepted_canonical_unit: str
    expected_conversion_function: str

    rhob_min_kg_m3: float
    rhob_max_kg_m3: float
    bounds_are_inclusive: bool

    bridge_short_internal_gaps: bool
    short_gap_max_tvd_m: float
    shallow_gap_tolerance_tvd_m: float
    sensitivity_thresholds_tvd_m: Tuple[float, ...]

    integration_method: str
    gravity_m_s2: float
    profile_report_step_tvdss_m: float

    seawater_density_kg_m3: float
    seawater_density_low_kg_m3: float
    seawater_density_high_kg_m3: float
    seabed_marker_name: str

    scenarios_enabled: bool
    scenario_high_percentile: float
    scenario_names: Tuple[str, ...]

    min_eligible_samples_for_increment: int
    absolute_requires_uninterrupted_column: bool
    not_implemented: Tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate the public constructor as strictly as the YAML loader.

        ``dataclasses.replace`` calls this constructor, and is the supported
        way tests and sensitivity runs derive one frozen configuration from
        another.  The constructor must therefore reject the same ambiguous
        types and malformed closed vocabularies as ``load_overburden_config``;
        validation only in the loader would leave a second, weaker public
        entry point into the numerical workflow.
        """
        def require_string(field_name: str, value: object) -> str:
            if not isinstance(value, str) or not value.strip():
                raise OverburdenConfigError(
                    f"{field_name} must be a non-empty string, got "
                    f"{type(value).__name__} {value!r}.")
            return value

        def require_bool(field_name: str, value: object) -> bool:
            if type(value) is not bool:
                raise OverburdenConfigError(
                    f"{field_name} must be a boolean, got "
                    f"{type(value).__name__} {value!r}.")
            return value

        def require_number(field_name: str, value: object) -> float:
            if (isinstance(value, (bool, np.bool_))
                    or not isinstance(value, (int, float, np.integer, np.floating))):
                raise OverburdenConfigError(
                    f"{field_name} must be a finite real number, got "
                    f"{type(value).__name__} {value!r}.")
            try:
                out = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise OverburdenConfigError(
                    f"{field_name} must be a finite real number, got "
                    f"{type(value).__name__} {value!r}.") from exc
            if not math.isfinite(out):
                raise OverburdenConfigError(
                    f"{field_name} must be finite, got {value!r}.")
            return out

        for field_name in (
            "source_filename", "schema_version", "assurance_tier",
            "canonical_curve_name", "accepted_canonical_unit",
            "expected_conversion_function", "integration_method",
            "seabed_marker_name",
        ):
            require_string(field_name, getattr(self, field_name))

        if self.schema_version != "7.0.1":
            raise OverburdenConfigError(
                f"schema_version must be exactly '7.0.1', got {self.schema_version!r}.")
        if type(self.increment) is not int or self.increment != 7:
            raise OverburdenConfigError(
                f"increment must be the integer 7, got {self.increment!r}.")
        if "vertical_depth" not in self.integration_method:
            raise OverburdenConfigError(
                "integration_method must declare a vertical-depth formulation.")

        for field_name in (
            "bounds_are_inclusive", "bridge_short_internal_gaps",
            "scenarios_enabled", "absolute_requires_uninterrupted_column",
        ):
            require_bool(field_name, getattr(self, field_name))

        for field_name in (
            "rhob_min_kg_m3", "rhob_max_kg_m3", "short_gap_max_tvd_m",
            "shallow_gap_tolerance_tvd_m", "gravity_m_s2",
            "profile_report_step_tvdss_m", "seawater_density_kg_m3",
            "seawater_density_low_kg_m3", "seawater_density_high_kg_m3",
            "scenario_high_percentile",
        ):
            object.__setattr__(
                self, field_name, require_number(field_name, getattr(self, field_name)))

        if type(self.sensitivity_thresholds_tvd_m) is not tuple:
            raise OverburdenConfigError(
                "sensitivity_thresholds_tvd_m must be a non-empty tuple of finite "
                "non-negative numbers in strictly increasing order.")
        if not self.sensitivity_thresholds_tvd_m:
            raise OverburdenConfigError(
                "sensitivity_thresholds_tvd_m must be a non-empty tuple.")
        thresholds = tuple(
            require_number("sensitivity_thresholds_tvd_m", value)
            for value in self.sensitivity_thresholds_tvd_m)
        if any(value < 0.0 for value in thresholds):
            raise OverburdenConfigError(
                "sensitivity_thresholds_tvd_m values must all be >= 0.")
        if any(right <= left for left, right in zip(thresholds, thresholds[1:])):
            raise OverburdenConfigError(
                "sensitivity_thresholds_tvd_m must be unique and strictly increasing.")
        object.__setattr__(self, "sensitivity_thresholds_tvd_m", thresholds)

        if type(self.scenario_names) is not tuple or self.scenario_names != (
                SCENARIO_LOW, SCENARIO_BASE, SCENARIO_HIGH):
            raise OverburdenConfigError(
                "scenario_names must be exactly ('low', 'base', 'high').")
        if (type(self.min_eligible_samples_for_increment) is not int
                or isinstance(self.min_eligible_samples_for_increment, bool)):
            raise OverburdenConfigError(
                "min_eligible_samples_for_increment must be a genuine integer, "
                f"got {type(self.min_eligible_samples_for_increment).__name__} "
                f"{self.min_eligible_samples_for_increment!r}.")
        if type(self.not_implemented) is not tuple or not self.not_implemented:
            raise OverburdenConfigError(
                "not_implemented must be a non-empty tuple of non-empty strings.")
        if any(not isinstance(value, str) or not value.strip()
               for value in self.not_implemented):
            raise OverburdenConfigError(
                "not_implemented entries must all be non-empty strings.")
        if len(set(self.not_implemented)) != len(self.not_implemented):
            raise OverburdenConfigError("not_implemented contains duplicate entries.")

        if self.rhob_min_kg_m3 >= self.rhob_max_kg_m3:
            raise OverburdenConfigError(
                f"screening_bounds: rhob_min_kg_m3 ({self.rhob_min_kg_m3}) must be strictly "
                f"less than rhob_max_kg_m3 ({self.rhob_max_kg_m3}).")
        if self.short_gap_max_tvd_m < 0.0:
            raise OverburdenConfigError(
                "gap_conditioning: short_gap_max_tvd_m must be >= 0.")
        if self.shallow_gap_tolerance_tvd_m < 0.0:
            raise OverburdenConfigError(
                "gap_conditioning: shallow_gap_tolerance_tvd_m must be >= 0.")
        if self.short_gap_max_tvd_m not in self.sensitivity_thresholds_tvd_m:
            raise OverburdenConfigError(
                f"gap_conditioning: the approved short_gap_max_tvd_m "
                f"({self.short_gap_max_tvd_m}) must appear in "
                f"sensitivity_thresholds_tvd_m {list(self.sensitivity_thresholds_tvd_m)}, "
                f"so that the approved case is always one of the reported cases.")
        if self.gravity_m_s2 <= 0.0:
            raise OverburdenConfigError("integration: gravity_m_s2 must be > 0.")
        if not (self.seawater_density_low_kg_m3
                <= self.seawater_density_kg_m3
                <= self.seawater_density_high_kg_m3):
            raise OverburdenConfigError(
                "water_column: seawater_density_kg_m3 must lie within "
                "[seawater_density_low_kg_m3, seawater_density_high_kg_m3].")
        if self.scenario_high_percentile != 5.0:
            raise OverburdenConfigError(
                "shallow_column_scenarios: high_percentile must be exactly 5.0, "
                "because Increment 7 stores and uses the measured P05 statistic; "
                "accepting another value would misstate which percentile supplied "
                "the high scenario.")
        if self.min_eligible_samples_for_increment < 2:
            raise OverburdenConfigError(
                "eligibility: min_eligible_samples_for_increment must be >= 2 (two samples "
                "is the arithmetic minimum for one trapezoid).")
        if self.profile_report_step_tvdss_m <= 0.0:
            raise OverburdenConfigError(
                "integration: profile_report_step_tvdss_m must be > 0.")


# ---------------------------------------------------------------------------
# Per-sample masks
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DensityMaskSet:
    """The complete set of explicit, separately auditable per-sample masks.

    Every mask is a full-length read-only boolean array aligned
    sample-for-sample with the well's canonical `MD_m`, in original file
    order. NOTHING in this structure holds a density value: a mask records
    what is true about a sample, never a substitute for it.

    `below_seabed_sample` is `None` - not an all-False or all-True array -
    when the well has no approved formation-top file and therefore no seabed
    marker. `None` means NOT DETERMINABLE. An all-False array would mean
    "every sample is above the seabed", and an all-True array would mean
    "every sample is below it"; both would be assertions this project cannot
    make, and the eligibility conjunction would silently absorb either.
    """

    well_key: str
    n_samples: int
    seabed_resolved: bool

    source_value_present: np.ndarray
    finite_numeric_density: np.ndarray
    unit_resolved: np.ndarray
    screening_range_plausible: np.ndarray
    below_seabed_sample: Optional[np.ndarray]
    depth_mapping_valid: np.ndarray
    within_survey_coverage: np.ndarray
    eligible_for_measured_integration: np.ndarray
    bridged_short_gap: np.ndarray
    unresolved_long_gap: np.ndarray
    unresolved_shallow_column: np.ndarray
    unresolved_terminal_column: np.ndarray

    def __post_init__(self) -> None:
        n = _require_nonneg_int(self.n_samples, f"DensityMaskSet {self.well_key!r}: n_samples")
        for name in DENSITY_MASK_NAMES:
            arr = getattr(self, name)
            if arr is None:
                if name != "below_seabed_sample":
                    raise OverburdenInputError(
                        f"DensityMaskSet {self.well_key!r}: mask {name!r} may not be None.")
                if self.seabed_resolved:
                    raise OverburdenInputError(
                        f"DensityMaskSet {self.well_key!r}: below_seabed_sample is None but "
                        f"seabed_resolved is True; a resolved seabed must produce a mask.")
                continue
            if not isinstance(arr, np.ndarray) or arr.dtype != np.bool_:
                raise OverburdenInputError(
                    f"DensityMaskSet {self.well_key!r}: mask {name!r} must be a boolean "
                    f"numpy array, got {type(arr).__name__} dtype "
                    f"{getattr(arr, 'dtype', None)!r}.")
            if arr.ndim != 1 or arr.size != n:
                raise OverburdenInputError(
                    f"DensityMaskSet {self.well_key!r}: mask {name!r} has shape {arr.shape}, "
                    f"expected a 1-D array of {n} sample(s).")
            if arr.flags.writeable:
                raise OverburdenInputError(
                    f"DensityMaskSet {self.well_key!r}: mask {name!r} must be read-only.")
        if self.below_seabed_sample is None and self.seabed_resolved:
            raise OverburdenInputError(
                f"DensityMaskSet {self.well_key!r}: seabed_resolved/below_seabed_sample "
                f"disagree.")
        if self.below_seabed_sample is not None and not self.seabed_resolved:
            raise OverburdenInputError(
                f"DensityMaskSet {self.well_key!r}: below_seabed_sample is present but "
                f"seabed_resolved is False.")

        # The eligibility mask is a CONJUNCTION. It can never be true where a
        # constituent condition is false, and it can never be true for a
        # sample that is simultaneously declared unresolved.
        elig = self.eligible_for_measured_integration
        for name in ("finite_numeric_density", "unit_resolved",
                     "screening_range_plausible", "depth_mapping_valid",
                     "within_survey_coverage"):
            if bool(np.any(elig & ~getattr(self, name))):
                raise OverburdenInputError(
                    f"DensityMaskSet {self.well_key!r}: eligible_for_measured_integration is "
                    f"True where {name} is False; the eligibility mask must be a conjunction "
                    f"of its declared constituents.")
        if self.below_seabed_sample is not None and bool(
                np.any(elig & ~self.below_seabed_sample)):
            raise OverburdenInputError(
                f"DensityMaskSet {self.well_key!r}: eligible_for_measured_integration is True "
                f"above the resolved seabed.")
        for name in ("unresolved_long_gap", "unresolved_shallow_column",
                     "unresolved_terminal_column"):
            if bool(np.any(elig & getattr(self, name))):
                raise OverburdenInputError(
                    f"DensityMaskSet {self.well_key!r}: a sample is both eligible and "
                    f"{name}; these are mutually exclusive by construction.")
        if bool(np.any(self.bridged_short_gap & elig)):
            raise OverburdenInputError(
                f"DensityMaskSet {self.well_key!r}: a bridged sample is also marked as an "
                f"eligible MEASURED sample; a bridged value is conditioned, not measured.")
        if bool(np.any(self.bridged_short_gap & self.unresolved_long_gap)):
            raise OverburdenInputError(
                f"DensityMaskSet {self.well_key!r}: a sample is both bridged and inside an "
                f"unresolved long gap.")
        if bool(np.any(self.finite_numeric_density & ~self.source_value_present)):
            raise OverburdenInputError(
                f"DensityMaskSet {self.well_key!r}: a finite density exists where no source "
                f"value is present.")

    def counts(self) -> Dict[str, Optional[int]]:
        """Return `{mask_name: n_true}`, with `None` for a not-determinable mask."""
        out: Dict[str, Optional[int]] = {}
        for name in DENSITY_MASK_NAMES:
            arr = getattr(self, name)
            out[name] = None if arr is None else int(np.count_nonzero(arr))
        return out


# ---------------------------------------------------------------------------
# QC statistics
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DensityQcStats:
    """Factual, descriptive density QC for ONE well.

    Every field is a MEASUREMENT about the curve as recorded, or a count of
    samples failing an explicitly configured screening criterion. Nothing here
    is an interpretation, and nothing here modifies the curve.
    """

    well_key: str
    source_las_filename: str
    curve_present: bool
    canonical_curve_name: Optional[str]
    source_curve_name: Optional[str]
    raw_mnemonic: Optional[str]
    raw_unit: Optional[str]
    canonical_unit: Optional[str]
    conversion_function: Optional[str]
    unit_resolved: bool
    conversion_confirmed: bool

    n_samples: int
    n_source_present: int
    n_finite: int
    n_non_finite: int
    n_non_positive: int
    n_below_screening_min: int
    n_above_screening_max: int
    n_screening_bound_failures: int
    n_in_screening_band: int
    n_depth_mapped: int
    n_depth_unmapped: int
    n_eligible: int

    rhob_min_kg_m3: Optional[float]
    rhob_max_kg_m3: Optional[float]
    rhob_median_kg_m3: Optional[float]
    rhob_p05_kg_m3: Optional[float]
    rhob_p95_kg_m3: Optional[float]
    rhob_eligible_p05_kg_m3: Optional[float]

    first_valid_md_m: Optional[float]
    last_valid_md_m: Optional[float]
    first_valid_tvd_m: Optional[float]
    last_valid_tvd_m: Optional[float]
    first_valid_tvdss_m: Optional[float]
    last_valid_tvdss_m: Optional[float]
    gross_coverage_md_m: Optional[float]
    gross_coverage_tvd_m: Optional[float]
    median_md_step_m: Optional[float]

    seabed_basis: str
    seabed_mdrt_m: Optional[float]
    seabed_tvd_m: Optional[float]
    seabed_tvdss_m: Optional[float]
    shallow_gap_md_m: Optional[float]
    shallow_gap_tvd_m: Optional[float]
    terminal_gap_md_m: Optional[float]
    terminal_gap_tvd_m: Optional[float]

    n_internal_gaps: int
    n_internal_gap_samples: int
    longest_internal_gap_md_m: Optional[float]
    longest_internal_gap_tvd_m: Optional[float]

    depth_basis_used: str
    depth_map_status: str
    survey_md_min_m: float
    survey_md_max_m: float
    n_samples_outside_survey_coverage: int

    def __post_init__(self) -> None:
        _require_in(self.seabed_basis, VALID_SEABED_BASES,
                    f"DensityQcStats {self.well_key!r}: seabed_basis")
        for name in ("n_samples", "n_source_present", "n_finite", "n_non_finite",
                     "n_non_positive", "n_below_screening_min", "n_above_screening_max",
                     "n_screening_bound_failures", "n_in_screening_band", "n_depth_mapped",
                     "n_depth_unmapped", "n_eligible", "n_internal_gaps",
                     "n_internal_gap_samples", "n_samples_outside_survey_coverage"):
            _require_nonneg_int(getattr(self, name),
                                f"DensityQcStats {self.well_key!r}: {name}")
        if self.n_finite + self.n_non_finite != self.n_samples:
            raise OverburdenInputError(
                f"DensityQcStats {self.well_key!r}: n_finite + n_non_finite "
                f"({self.n_finite} + {self.n_non_finite}) must equal n_samples "
                f"({self.n_samples}).")
        if self.n_depth_mapped + self.n_depth_unmapped != self.n_samples:
            raise OverburdenInputError(
                f"DensityQcStats {self.well_key!r}: n_depth_mapped + n_depth_unmapped must "
                f"equal n_samples.")
        expected_failures = (self.n_below_screening_min + self.n_above_screening_max
                             + self.n_non_positive)
        if self.n_screening_bound_failures != expected_failures:
            raise OverburdenInputError(
                f"DensityQcStats {self.well_key!r}: n_screening_bound_failures "
                f"({self.n_screening_bound_failures}) must equal n_below_screening_min + "
                f"n_above_screening_max + n_non_positive ({expected_failures}).")
        if self.n_in_screening_band + self.n_screening_bound_failures != self.n_finite:
            raise OverburdenInputError(
                f"DensityQcStats {self.well_key!r}: in-band and bound-failure counts must "
                f"partition the finite samples.")
        if self.n_eligible > self.n_in_screening_band:
            raise OverburdenInputError(
                f"DensityQcStats {self.well_key!r}: n_eligible ({self.n_eligible}) cannot "
                f"exceed n_in_screening_band ({self.n_in_screening_band}).")
        if self.curve_present and self.canonical_curve_name is None:
            raise OverburdenInputError(
                f"DensityQcStats {self.well_key!r}: curve_present is True but "
                f"canonical_curve_name is None.")
        if not self.curve_present and self.n_finite != 0:
            raise OverburdenInputError(
                f"DensityQcStats {self.well_key!r}: curve_present is False but "
                f"n_finite is {self.n_finite}.")
        finite_stats = (
            self.rhob_min_kg_m3, self.rhob_max_kg_m3, self.rhob_median_kg_m3,
            self.rhob_p05_kg_m3, self.rhob_p95_kg_m3,
        )
        if self.n_finite == 0 and any(v is not None for v in finite_stats):
            raise OverburdenInputError(
                f"DensityQcStats {self.well_key!r}: finite-population statistics must "
                f"all be None when n_finite is zero.")
        if self.n_finite > 0:
            for name in ("rhob_min_kg_m3", "rhob_max_kg_m3", "rhob_median_kg_m3",
                         "rhob_p05_kg_m3", "rhob_p95_kg_m3"):
                _require_finite_float(
                    getattr(self, name), f"DensityQcStats {self.well_key!r}: {name}")
        if self.n_eligible == 0 and self.rhob_eligible_p05_kg_m3 is not None:
            raise OverburdenInputError(
                f"DensityQcStats {self.well_key!r}: rhob_eligible_p05_kg_m3 must be "
                f"None when n_eligible is zero.")
        if self.n_eligible > 0:
            _require_finite_float(
                self.rhob_eligible_p05_kg_m3,
                f"DensityQcStats {self.well_key!r}: rhob_eligible_p05_kg_m3")
        if (self.seabed_basis == SEABED_BASIS_NOT_DETERMINABLE
                and self.seabed_mdrt_m is not None):
            raise OverburdenInputError(
                f"DensityQcStats {self.well_key!r}: seabed_basis says not determinable but a "
                f"seabed depth is present.")
        if (self.seabed_basis == SEABED_BASIS_LOCKED_MARKER
                and self.seabed_mdrt_m is None):
            raise OverburdenInputError(
                f"DensityQcStats {self.well_key!r}: seabed_basis cites the locked marker but "
                f"no seabed depth is present.")


# ---------------------------------------------------------------------------
# Gaps
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DensityGapRecord:
    """ONE classified density gap in ONE well.

    A gap is a factual description of an interval with no eligible measured
    density. `gap_class` distinguishes the five structurally different cases
    the Increment 7 policy requires to be kept apart, plus the depth-mapping
    case; `disposition` records what was actually done about it.
    """

    well_key: str
    gap_index: int
    gap_class: str
    disposition: str
    n_samples: int
    start_index: Optional[int]
    end_index: Optional[int]
    md_start_m: Optional[float]
    md_end_m: Optional[float]
    tvd_start_m: Optional[float]
    tvd_end_m: Optional[float]
    thickness_md_m: Optional[float]
    thickness_tvd_m: Optional[float]
    threshold_tvd_m: Optional[float]
    bounding_density_above_kg_m3: Optional[float]
    bounding_density_below_kg_m3: Optional[float]

    def __post_init__(self) -> None:
        _require_in(self.gap_class, VALID_GAP_CLASSES,
                    f"DensityGapRecord {self.well_key!r}: gap_class")
        _require_in(self.disposition, VALID_GAP_DISPOSITIONS,
                    f"DensityGapRecord {self.well_key!r}: disposition")
        _require_nonneg_int(self.gap_index, f"DensityGapRecord {self.well_key!r}: gap_index")
        _require_nonneg_int(self.n_samples, f"DensityGapRecord {self.well_key!r}: n_samples")
        if self.threshold_tvd_m is not None:
            threshold = _require_finite_float(
                self.threshold_tvd_m,
                f"DensityGapRecord {self.well_key!r}: threshold_tvd_m")
            if threshold < 0.0:
                raise OverburdenInputError(
                    f"DensityGapRecord {self.well_key!r}: threshold_tvd_m must be >= 0, "
                    f"got {threshold}.")
        for name in ("thickness_md_m", "thickness_tvd_m"):
            value = getattr(self, name)
            if value is not None and value < 0.0:
                raise OverburdenInputError(
                    f"DensityGapRecord {self.well_key!r}: {name} must be >= 0, got {value}.")
        if self.disposition == GAP_DISPOSITION_BRIDGED:
            if self.gap_class != GAP_CLASS_SHORT_INTERNAL:
                raise OverburdenInputError(
                    f"DensityGapRecord {self.well_key!r}: only a "
                    f"{GAP_CLASS_SHORT_INTERNAL!r} may be bridged, not {self.gap_class!r}. "
                    f"Bridging a shallow, terminal, long or unmapped gap is prohibited.")
            if self.n_samples < 1:
                raise OverburdenInputError(
                    f"DensityGapRecord {self.well_key!r}: a bridged gap must contain at "
                    f"least one conditioned sample.")
            if (self.bounding_density_above_kg_m3 is None
                    or self.bounding_density_below_kg_m3 is None):
                raise OverburdenInputError(
                    f"DensityGapRecord {self.well_key!r}: a bridged gap must record both "
                    f"bracketing measured densities.")
        if (self.gap_class == GAP_CLASS_SHORT_INTERNAL
                and self.threshold_tvd_m is not None
                and self.thickness_tvd_m is not None
                and self.thickness_tvd_m > self.threshold_tvd_m):
            raise OverburdenInputError(
                f"DensityGapRecord {self.well_key!r}: a gap classified short "
                f"({self.thickness_tvd_m} m TVD) exceeds the threshold "
                f"({self.threshold_tvd_m} m TVD).")
        if (self.gap_class == GAP_CLASS_LONG_INTERNAL
                and self.threshold_tvd_m is not None
                and self.thickness_tvd_m is not None
                and self.thickness_tvd_m <= self.threshold_tvd_m):
            raise OverburdenInputError(
                f"DensityGapRecord {self.well_key!r}: a gap classified long "
                f"({self.thickness_tvd_m} m TVD) does not exceed the threshold "
                f"({self.threshold_tvd_m} m TVD).")


@dataclass(frozen=True)
class GapConditioningResult:
    """The outcome of applying the configured gap-conditioning policy to ONE well.

    `conditioned_density_kg_m3` is a SEPARATELY NAMED array. The original
    resolved RHOB array is never touched; a caller holding both can diff them
    and see exactly which samples were conditioned, and `bridged_mask` names
    those samples independently.
    """

    well_key: str
    threshold_tvd_m: float
    bridging_enabled: bool
    conditioned_density_kg_m3: np.ndarray
    bridged_mask: np.ndarray
    n_bridged_gaps: int
    n_bridged_samples: int
    bridged_thickness_md_m: float
    bridged_thickness_tvd_m: float
    n_long_gaps: int
    n_long_gap_samples: int
    long_gap_thickness_md_m: float
    long_gap_thickness_tvd_m: float
    gaps: Tuple[DensityGapRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        threshold = _require_finite_float(
            self.threshold_tvd_m,
            f"GapConditioningResult {self.well_key!r}: threshold_tvd_m")
        if threshold < 0.0:
            raise OverburdenInputError(
                f"GapConditioningResult {self.well_key!r}: threshold_tvd_m must be >= 0, "
                f"got {threshold}.")
        if type(self.bridging_enabled) is not bool:
            raise OverburdenInputError(
                f"GapConditioningResult {self.well_key!r}: bridging_enabled must be a "
                f"boolean, got {type(self.bridging_enabled).__name__}.")
        for name in ("n_bridged_gaps", "n_bridged_samples", "n_long_gaps",
                     "n_long_gap_samples"):
            _require_nonneg_int(getattr(self, name),
                                f"GapConditioningResult {self.well_key!r}: {name}")
        if not isinstance(self.conditioned_density_kg_m3, np.ndarray):
            raise OverburdenInputError(
                f"GapConditioningResult {self.well_key!r}: conditioned density must be a "
                f"numpy array.")
        if self.conditioned_density_kg_m3.flags.writeable:
            raise OverburdenInputError(
                f"GapConditioningResult {self.well_key!r}: conditioned density array must be "
                f"read-only.")
        if self.bridged_mask.dtype != np.bool_:
            raise OverburdenInputError(
                f"GapConditioningResult {self.well_key!r}: bridged_mask must be boolean.")
        if self.bridged_mask.size != self.conditioned_density_kg_m3.size:
            raise OverburdenInputError(
                f"GapConditioningResult {self.well_key!r}: bridged_mask and conditioned "
                f"density lengths differ.")
        if int(np.count_nonzero(self.bridged_mask)) != self.n_bridged_samples:
            raise OverburdenInputError(
                f"GapConditioningResult {self.well_key!r}: n_bridged_samples "
                f"({self.n_bridged_samples}) disagrees with bridged_mask "
                f"({int(np.count_nonzero(self.bridged_mask))}).")
        # A gap count and a sample count must move together: n gaps with zero
        # samples, or zero gaps with n samples, is an incoherent record.
        if (self.n_bridged_gaps == 0) != (self.n_bridged_samples == 0):
            raise OverburdenInputError(
                f"GapConditioningResult {self.well_key!r}: n_bridged_gaps "
                f"({self.n_bridged_gaps}) and n_bridged_samples "
                f"({self.n_bridged_samples}) must both be zero or both be non-zero.")
        if self.n_bridged_gaps and self.n_bridged_samples < self.n_bridged_gaps:
            raise OverburdenInputError(
                f"GapConditioningResult {self.well_key!r}: {self.n_bridged_gaps} bridged "
                f"gap(s) cannot contain only {self.n_bridged_samples} sample(s).")
        if (self.n_long_gaps == 0) != (self.n_long_gap_samples == 0):
            raise OverburdenInputError(
                f"GapConditioningResult {self.well_key!r}: n_long_gaps and "
                f"n_long_gap_samples must both be zero or both be non-zero.")
        if self.n_long_gaps and self.n_long_gap_samples < self.n_long_gaps:
            raise OverburdenInputError(
                f"GapConditioningResult {self.well_key!r}: {self.n_long_gaps} long gap(s) "
                f"cannot contain only {self.n_long_gap_samples} sample(s).")
        if not self.bridging_enabled and self.n_bridged_gaps:
            raise OverburdenInputError(
                f"GapConditioningResult {self.well_key!r}: bridging is disabled but "
                f"{self.n_bridged_gaps} gap(s) were bridged.")
        for name in ("bridged_thickness_md_m", "bridged_thickness_tvd_m",
                     "long_gap_thickness_md_m", "long_gap_thickness_tvd_m"):
            value = _require_finite_float(
                getattr(self, name), f"GapConditioningResult {self.well_key!r}: {name}")
            if value < 0.0:
                raise OverburdenInputError(
                    f"GapConditioningResult {self.well_key!r}: {name} must be >= 0.")
        n_bridged_records = sum(1 for g in self.gaps
                                if g.disposition == GAP_DISPOSITION_BRIDGED)
        if n_bridged_records != self.n_bridged_gaps:
            raise OverburdenInputError(
                f"GapConditioningResult {self.well_key!r}: {n_bridged_records} bridged gap "
                f"record(s) but n_bridged_gaps is {self.n_bridged_gaps}.")


# ---------------------------------------------------------------------------
# Stress
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StressPartition:
    """The separated contributions to a reported vertical stress, in pascals.

    The partition exists so that a reader can always see how much of a number
    is measurement and how much is assumption. `measured_formation_pa` is the
    only component derived exclusively from recorded density; every other
    component depends on a configured assumption, an interpolation, or both.
    """

    water_column_pa: Optional[float]
    measured_formation_pa: float
    bridged_gap_pa: float
    unresolved_shallow_pa: Optional[float]
    total_pa: Optional[float]

    def __post_init__(self) -> None:
        _require_finite_float(self.water_column_pa, "StressPartition: water_column_pa",
                              allow_none=True)
        _require_finite_float(self.measured_formation_pa,
                              "StressPartition: measured_formation_pa")
        _require_finite_float(self.bridged_gap_pa, "StressPartition: bridged_gap_pa")
        _require_finite_float(self.unresolved_shallow_pa,
                              "StressPartition: unresolved_shallow_pa", allow_none=True)
        _require_finite_float(self.total_pa, "StressPartition: total_pa", allow_none=True)
        for name in ("water_column_pa", "measured_formation_pa", "bridged_gap_pa",
                     "unresolved_shallow_pa", "total_pa"):
            value = getattr(self, name)
            if value is not None and value < 0.0:
                raise OverburdenInputError(
                    f"StressPartition: {name} must be >= 0 (a downward column cannot remove "
                    f"vertical stress), got {value}.")
        if self.total_pa is not None:
            parts = [self.water_column_pa, self.measured_formation_pa, self.bridged_gap_pa,
                     self.unresolved_shallow_pa]
            if any(p is None for p in parts):
                raise OverburdenInputError(
                    "StressPartition: a total may not be reported while any component is "
                    "unresolved; an unresolved component is not zero.")
            expected = sum(parts)  # type: ignore[arg-type]
            if not math.isclose(expected, self.total_pa, rel_tol=1e-12, abs_tol=1e-6):
                raise OverburdenInputError(
                    f"StressPartition: components sum to {expected} Pa but total_pa is "
                    f"{self.total_pa} Pa.")


@dataclass(frozen=True)
class VerticalStressProfile:
    """The measured vertical-stress increment profile for ONE well.

    `tvdss_m` is the vertical coordinate the integral was actually taken in.
    `cumulative_measured_increment_pa[i]` is the integral of rho*g*dz from the
    FIRST eligible sample down to sample `i`; it is an INCREMENT, not an
    absolute stress, and it is zero at the first node by definition.
    """

    well_key: str
    n_nodes: int
    integration_coordinate: str
    gravity_m_s2: float
    md_m: np.ndarray
    tvd_m: np.ndarray
    tvdss_m: np.ndarray
    density_kg_m3: np.ndarray
    bridged_mask: np.ndarray
    cumulative_measured_increment_pa: np.ndarray
    total_measured_increment_pa: float
    total_bridged_increment_pa: float
    n_zero_thickness_intervals: int
    n_intervals: int
    top_tvd_m: float
    base_tvd_m: float
    top_tvdss_m: float
    base_tvdss_m: float
    #: True when the integrable column was cut short at an unresolved long
    #: gap, so the profile's base is ABOVE the well's deepest eligible
    #: density sample. Increment 7 never integrates through an unresolved
    #: gap, and never silently joins two columns that are not adjacent.
    column_truncated_at_unresolved_gap: bool
    #: Eligible density samples that exist BELOW the truncation and were
    #: therefore excluded from this profile. Zero when nothing was truncated.
    n_eligible_samples_below_truncation: int

    def __post_init__(self) -> None:
        n = _require_nonneg_int(self.n_nodes,
                                f"VerticalStressProfile {self.well_key!r}: n_nodes")
        if n < 2:
            raise OverburdenInputError(
                f"VerticalStressProfile {self.well_key!r}: a profile requires at least two "
                f"nodes, got {n}.")
        for name in ("md_m", "tvd_m", "tvdss_m", "density_kg_m3", "bridged_mask",
                     "cumulative_measured_increment_pa"):
            arr = getattr(self, name)
            if not isinstance(arr, np.ndarray) or arr.ndim != 1 or arr.size != n:
                raise OverburdenInputError(
                    f"VerticalStressProfile {self.well_key!r}: {name} must be a 1-D array of "
                    f"{n} element(s).")
            if arr.flags.writeable:
                raise OverburdenInputError(
                    f"VerticalStressProfile {self.well_key!r}: {name} must be read-only.")
        if self.integration_coordinate != "tvdss_m":
            raise OverburdenInputError(
                f"VerticalStressProfile {self.well_key!r}: integration_coordinate must be "
                f"'tvdss_m'; measured-depth integration is not representable here.")
        if int(self.n_intervals) != n - 1:
            raise OverburdenInputError(
                f"VerticalStressProfile {self.well_key!r}: n_intervals must equal n_nodes-1.")
        _require_nonneg_int(self.n_zero_thickness_intervals,
                            f"VerticalStressProfile {self.well_key!r}: "
                            f"n_zero_thickness_intervals")
        if self.n_zero_thickness_intervals > self.n_intervals:
            raise OverburdenInputError(
                f"VerticalStressProfile {self.well_key!r}: more zero-thickness intervals "
                f"than intervals.")
        cum = self.cumulative_measured_increment_pa
        if float(cum[0]) != 0.0:
            raise OverburdenInputError(
                f"VerticalStressProfile {self.well_key!r}: the cumulative increment must be "
                f"exactly zero at the first node, got {float(cum[0])!r}.")
        if bool(np.any(np.diff(cum) < 0.0)):
            raise OverburdenInputError(
                f"VerticalStressProfile {self.well_key!r}: the cumulative increment must be "
                f"non-decreasing downward.")
        if not math.isclose(float(cum[-1]), float(self.total_measured_increment_pa),
                            rel_tol=1e-12, abs_tol=1e-6):
            raise OverburdenInputError(
                f"VerticalStressProfile {self.well_key!r}: total_measured_increment_pa does "
                f"not equal the final cumulative value.")
        if self.total_bridged_increment_pa < 0.0:
            raise OverburdenInputError(
                f"VerticalStressProfile {self.well_key!r}: total_bridged_increment_pa must "
                f"be >= 0.")
        if self.total_bridged_increment_pa > self.total_measured_increment_pa + 1e-6:
            raise OverburdenInputError(
                f"VerticalStressProfile {self.well_key!r}: the bridged contribution cannot "
                f"exceed the whole integrated increment.")
        _require_nonneg_int(
            self.n_eligible_samples_below_truncation,
            f"VerticalStressProfile {self.well_key!r}: n_eligible_samples_below_truncation")
        if not isinstance(self.column_truncated_at_unresolved_gap, bool):
            raise OverburdenInputError(
                f"VerticalStressProfile {self.well_key!r}: "
                f"column_truncated_at_unresolved_gap must be a bool.")
        if (self.n_eligible_samples_below_truncation > 0
                and not self.column_truncated_at_unresolved_gap):
            raise OverburdenInputError(
                f"VerticalStressProfile {self.well_key!r}: eligible samples are reported "
                f"below a truncation that is not declared.")


@dataclass(frozen=True)
class ShallowColumnScenario:
    """ONE transparent screening scenario for the UNMEASURED shallow column.

    This is not an estimate of the true stress. It is a statement of the form
    "if the depth-averaged bulk density of the unmeasured column were X, the
    total would be Y, of which fraction F originates in the assumption".
    """

    well_key: str
    scenario_name: str
    assumed_shallow_density_kg_m3: float
    assumed_density_basis: str
    seawater_density_kg_m3: float
    gravity_m_s2: float
    unresolved_thickness_tvd_m: float
    water_column_thickness_tvd_m: float
    measured_thickness_tvd_m: float
    partition: StressPartition
    assumed_fraction_of_total: float
    conditioned_fraction_of_total: float
    measured_fraction_of_total: float

    def __post_init__(self) -> None:
        _require_in(self.scenario_name, VALID_SCENARIO_NAMES,
                    f"ShallowColumnScenario {self.well_key!r}: scenario_name")
        for name in ("assumed_shallow_density_kg_m3", "seawater_density_kg_m3",
                     "gravity_m_s2"):
            value = _require_finite_float(
                getattr(self, name), f"ShallowColumnScenario {self.well_key!r}: {name}")
            if value <= 0.0:
                raise OverburdenInputError(
                    f"ShallowColumnScenario {self.well_key!r}: {name} must be > 0.")
        for name in ("unresolved_thickness_tvd_m", "water_column_thickness_tvd_m",
                     "measured_thickness_tvd_m"):
            value = _require_finite_float(
                getattr(self, name), f"ShallowColumnScenario {self.well_key!r}: {name}")
            if value < 0.0:
                raise OverburdenInputError(
                    f"ShallowColumnScenario {self.well_key!r}: {name} must be >= 0.")
        if self.partition.total_pa is None:
            raise OverburdenInputError(
                f"ShallowColumnScenario {self.well_key!r}: a scenario must produce a total; "
                f"if a component is unresolved the well is not scenario-eligible.")
        for name in ("assumed_fraction_of_total", "conditioned_fraction_of_total",
                     "measured_fraction_of_total"):
            value = _require_finite_float(
                getattr(self, name), f"ShallowColumnScenario {self.well_key!r}: {name}")
            if not (0.0 <= value <= 1.0):
                raise OverburdenInputError(
                    f"ShallowColumnScenario {self.well_key!r}: {name} must lie in [0, 1], "
                    f"got {value}.")
        fraction_sum = (self.assumed_fraction_of_total
                        + self.conditioned_fraction_of_total
                        + self.measured_fraction_of_total)
        if not math.isclose(fraction_sum, 1.0, rel_tol=1e-12, abs_tol=1e-12):
            raise OverburdenInputError(
                f"ShallowColumnScenario {self.well_key!r}: assumed, conditioned and "
                f"measured fractions must sum to 1, got {fraction_sum!r}.")


@dataclass(frozen=True)
class GapThresholdSensitivity:
    """What the approved gap threshold actually changed, for ONE well."""

    well_key: str
    threshold_tvd_m: float
    is_approved_threshold: bool
    n_bridged_gaps: int
    n_bridged_samples: int
    bridged_thickness_tvd_m: float
    n_long_gaps: int
    long_gap_thickness_tvd_m: float
    n_eligible_or_bridged_samples: int
    total_measured_increment_pa: Optional[float]
    bridged_increment_pa: Optional[float]
    derived_status: str

    def __post_init__(self) -> None:
        _require_in(self.derived_status, VALID_OVERBURDEN_STATUSES,
                    f"GapThresholdSensitivity {self.well_key!r}: derived_status")
        for name in ("n_bridged_gaps", "n_bridged_samples", "n_long_gaps",
                     "n_eligible_or_bridged_samples"):
            _require_nonneg_int(getattr(self, name),
                                f"GapThresholdSensitivity {self.well_key!r}: {name}")
        if (self.n_bridged_gaps == 0) != (self.n_bridged_samples == 0):
            raise OverburdenInputError(
                f"GapThresholdSensitivity {self.well_key!r}: bridged gap and sample counts "
                f"must both be zero or both be non-zero.")
        threshold = _require_finite_float(
            self.threshold_tvd_m,
            f"GapThresholdSensitivity {self.well_key!r}: threshold_tvd_m")
        if threshold < 0.0:
            raise OverburdenInputError(
                f"GapThresholdSensitivity {self.well_key!r}: threshold_tvd_m must be >= 0, "
                f"got {threshold}.")
        if type(self.is_approved_threshold) is not bool:
            raise OverburdenInputError(
                f"GapThresholdSensitivity {self.well_key!r}: is_approved_threshold must "
                f"be a boolean, got {type(self.is_approved_threshold).__name__}.")
        for name in ("bridged_thickness_tvd_m", "long_gap_thickness_tvd_m"):
            value = _require_finite_float(
                getattr(self, name), f"GapThresholdSensitivity {self.well_key!r}: {name}")
            if value < 0.0:
                raise OverburdenInputError(
                    f"GapThresholdSensitivity {self.well_key!r}: {name} must be >= 0, "
                    f"got {value}.")


@dataclass(frozen=True)
class OverburdenEligibility:
    """The DERIVED overburden method-eligibility verdict for ONE well.

    `status` is computed from measured coverage and QC results. No well name
    participates in the derivation, and no configuration key names a well.
    `limiting_reasons` is an ordered tuple of enumerated codes - never prose.
    """

    well_key: str
    status: str
    limiting_reasons: Tuple[str, ...]
    seabed_resolved: bool
    seabed_basis: str
    n_eligible_samples: int
    n_bridged_samples: int
    eligible_top_tvd_m: Optional[float]
    eligible_base_tvd_m: Optional[float]
    eligible_top_tvdss_m: Optional[float]
    eligible_base_tvdss_m: Optional[float]
    measured_thickness_tvd_m: Optional[float]
    shallow_unresolved_thickness_tvd_m: Optional[float]
    terminal_unresolved_thickness_tvd_m: Optional[float]
    water_column_thickness_tvd_m: Optional[float]
    n_unresolved_internal_gaps: int
    n_unresolved_long_gaps: int
    unresolved_long_gap_thickness_tvd_m: float
    column_uninterrupted: bool
    measured_increment_pa: Optional[float]
    bridged_increment_pa: Optional[float]
    absolute_stress_supported: bool

    def __post_init__(self) -> None:
        _require_in(self.status, VALID_OVERBURDEN_STATUSES,
                    f"OverburdenEligibility {self.well_key!r}: status")
        _require_in(self.seabed_basis, VALID_SEABED_BASES,
                    f"OverburdenEligibility {self.well_key!r}: seabed_basis")
        if not isinstance(self.limiting_reasons, tuple):
            raise OverburdenInputError(
                f"OverburdenEligibility {self.well_key!r}: limiting_reasons must be a tuple.")
        for reason in self.limiting_reasons:
            _require_in(reason, VALID_LIMITING_REASONS,
                        f"OverburdenEligibility {self.well_key!r}: limiting reason")
        if len(set(self.limiting_reasons)) != len(self.limiting_reasons):
            raise OverburdenInputError(
                f"OverburdenEligibility {self.well_key!r}: limiting_reasons contains "
                f"duplicates: {list(self.limiting_reasons)}.")
        if list(self.limiting_reasons) != sorted(self.limiting_reasons):
            raise OverburdenInputError(
                f"OverburdenEligibility {self.well_key!r}: limiting_reasons must be sorted "
                f"for determinism, got {list(self.limiting_reasons)}.")
        for name in ("n_eligible_samples", "n_bridged_samples",
                     "n_unresolved_internal_gaps", "n_unresolved_long_gaps"):
            _require_nonneg_int(getattr(self, name),
                                f"OverburdenEligibility {self.well_key!r}: {name}")

        if self.status == STATUS_ABSOLUTE:
            if self.limiting_reasons:
                raise OverburdenInputError(
                    f"OverburdenEligibility {self.well_key!r}: status {STATUS_ABSOLUTE!r} "
                    f"cannot carry limiting reason(s) {list(self.limiting_reasons)}.")
            if not self.absolute_stress_supported:
                raise OverburdenInputError(
                    f"OverburdenEligibility {self.well_key!r}: status {STATUS_ABSOLUTE!r} "
                    f"requires absolute_stress_supported to be True.")
            if not self.seabed_resolved or not self.column_uninterrupted:
                raise OverburdenInputError(
                    f"OverburdenEligibility {self.well_key!r}: an absolute status requires a "
                    f"resolved seabed and an uninterrupted column.")
        else:
            if self.absolute_stress_supported:
                raise OverburdenInputError(
                    f"OverburdenEligibility {self.well_key!r}: absolute_stress_supported is "
                    f"True but status is {self.status!r}.")
            if not self.limiting_reasons:
                raise OverburdenInputError(
                    f"OverburdenEligibility {self.well_key!r}: status {self.status!r} must "
                    f"state at least one enumerated limiting reason.")
        if self.status == STATUS_SENSITIVITY_ONLY and not self.seabed_resolved:
            raise OverburdenInputError(
                f"OverburdenEligibility {self.well_key!r}: {STATUS_SENSITIVITY_ONLY!r} "
                f"requires a resolved seabed, because the unresolved column's thickness must "
                f"be known before it can be bracketed.")
        # `not_eligible` is a statement about the INTEGRABLE column, not about
        # the raw eligible-sample count. A well can hold many eligible samples
        # and still support no measured increment - for example when an
        # unresolved long gap sits immediately below the shallowest eligible
        # sample, leaving fewer than two samples in the only column that could
        # ever be tied to the section above it. The coherent invariant is
        # therefore that no increment was produced.
        if self.status == STATUS_NOT_ELIGIBLE and self.measured_increment_pa is not None:
            raise OverburdenInputError(
                f"OverburdenEligibility {self.well_key!r}: {STATUS_NOT_ELIGIBLE!r} is "
                f"inconsistent with a reported measured increment of "
                f"{self.measured_increment_pa} Pa.")
        if self.status != STATUS_NOT_ELIGIBLE and self.measured_increment_pa is None:
            raise OverburdenInputError(
                f"OverburdenEligibility {self.well_key!r}: status {self.status!r} claims a "
                f"measured column but no increment was produced.")
        if self.seabed_resolved != (self.seabed_basis == SEABED_BASIS_LOCKED_MARKER):
            raise OverburdenInputError(
                f"OverburdenEligibility {self.well_key!r}: seabed_resolved and seabed_basis "
                f"disagree.")
        if self.n_unresolved_long_gaps > self.n_unresolved_internal_gaps:
            raise OverburdenInputError(
                f"OverburdenEligibility {self.well_key!r}: n_unresolved_long_gaps "
                f"({self.n_unresolved_long_gaps}) exceeds n_unresolved_internal_gaps "
                f"({self.n_unresolved_internal_gaps}).")
        if (self.n_unresolved_internal_gaps == 0) != self.column_uninterrupted:
            raise OverburdenInputError(
                f"OverburdenEligibility {self.well_key!r}: column_uninterrupted "
                f"({self.column_uninterrupted}) disagrees with "
                f"n_unresolved_internal_gaps ({self.n_unresolved_internal_gaps}).")


@dataclass(frozen=True)
class OverburdenIssue:
    """One operator-facing QC issue raised by the Increment 7 workflow."""

    severity: str
    code: str
    context: str
    message: str

    def __post_init__(self) -> None:
        _require_in(self.severity, ("INFO", "WARNING", "ERROR"),
                    "OverburdenIssue: severity")
        if not self.code or not self.code.replace("_", "").isalnum():
            raise OverburdenInputError(
                f"OverburdenIssue: code {self.code!r} must be a non-empty alphanumeric/"
                f"underscore token.")
