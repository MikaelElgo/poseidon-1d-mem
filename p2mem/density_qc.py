"""
p2mem.density_qc - RHOB availability, unit/provenance confirmation, explicit
validity masks, gap classification, and gap conditioning (Increment 7).

What this module does
---------------------
* Loads and validates `config/overburden_stress.yml`.
* Confirms, per well, that the locked Increment 2.1.1 curve contract resolved
  a density curve, under the accepted canonical unit, by the expected
  conversion function.
* Builds twelve explicit, separately auditable per-sample masks.
* Measures factual density QC statistics.
* Classifies every gap in the density column into the structurally distinct
  cases Increment 7 requires to be kept apart.
* Applies the configured gap-conditioning policy, producing a SEPARATELY
  NAMED conditioned array.

What this module never does
---------------------------
It never clips, rescales, smooths, despikes, replaces, or extrapolates RHOB.
The resolved density array handed in by the locked well frame is read and
never written. Bridging writes only into a new array, only inside the
bracketed interior of the measured column, only across gaps at or below the
configured TVD threshold, and never across the seabed or outside locked survey
coverage.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import yaml

from p2mem.overburden_models import (
    GAP_CLASS_LONG_INTERNAL,
    GAP_CLASS_SHALLOW,
    GAP_CLASS_SHORT_INTERNAL,
    GAP_CLASS_TERMINAL,
    GAP_CLASS_UNMAPPED_DEPTH,
    GAP_DISPOSITION_BRIDGED,
    GAP_DISPOSITION_UNRESOLVED,
    SCENARIO_BASIS_BASE,
    SCENARIO_BASIS_HIGH,
    SCENARIO_BASIS_LOW,
    SEABED_BASIS_LOCKED_MARKER,
    SEABED_BASIS_NOT_DETERMINABLE,
    DensityGapRecord,
    DensityMaskSet,
    DensityQcStats,
    GapConditioningResult,
    OverburdenConfig,
    OverburdenConfigError,
    OverburdenInputError,
    VALID_OVERBURDEN_STATUSES,
    readonly,
)

__all__ = [
    "load_overburden_config",
    "resolve_density_slot",
    "build_density_masks",
    "compute_density_qc_stats",
    "classify_density_gaps",
    "condition_density_gaps",
    "DensityUnitError",
]


class DensityUnitError(TypeError):
    """Raised when a density curve's canonical unit is not the accepted unit.

    A `TypeError` subclass because an unexpected unit is a type-class defect
    in the quantity, not a value defect: Increment 7 performs no conversion of
    its own and will not integrate a quantity whose unit it cannot confirm.
    """


def _validated_gap_threshold(value, context: str) -> float:
    """Return one public gap-threshold override as a finite non-negative float.

    Configuration values already pass the frozen ``OverburdenConfig`` gate.
    Public per-call overrides require the same safety: no coercion from text,
    booleans or complex values, and no NaN/Inf value that could silently alter
    the short/long classification.
    """
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))):
        raise OverburdenInputError(
            f"{context}: threshold_tvd_m must be a finite non-negative real number, "
            f"got {type(value).__name__} {value!r}.")
    out = float(value)
    if not np.isfinite(out) or out < 0.0:
        raise OverburdenInputError(
            f"{context}: threshold_tvd_m must be finite and >= 0, got {out!r}.")
    return out


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------

def _reject_ambiguous_dtype(raw: np.ndarray, context: str) -> None:
    """Reject boolean, string/bytes, complex and otherwise non-numeric dtype
    input with `TypeError` before any numeric use.

    Documented local copy of the identical check established in the LOCKED
    `p2mem.units`, `p2mem.time_depth`, `p2mem.io.tops` and `p2mem.petrophysics`
    modules. Those modules remain unmodified; duplicating ~10 lines here is
    deliberately preferred over editing a locked module to export a private
    helper.
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


class _NoDuplicateKeySafeLoader(yaml.SafeLoader):
    """A SafeLoader that refuses duplicate mapping keys.

    Documented local copy of the loader the locked configuration modules
    already use. PyYAML's default silently keeps the last duplicate, which
    would let an edited config change a screening bound without any visible
    diff at the point of use.
    """


def _no_duplicate_keys(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise OverburdenConfigError(
                f"duplicate configuration key {key!r} at line "
                f"{key_node.start_mark.line + 1}; a duplicate key silently overrides an "
                f"earlier reviewed value.")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_NoDuplicateKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys)


_REQUIRED_TOP_KEYS = (
    "schema_version", "increment", "assurance_tier", "density_source",
    "screening_bounds", "gap_conditioning", "integration", "water_column",
    "shallow_column_scenarios", "eligibility", "not_implemented",
)
_KNOWN_TOP_KEYS = frozenset(_REQUIRED_TOP_KEYS)

_SECTION_KEYS = {
    "density_source": ("canonical_curve_name", "accepted_canonical_unit",
                       "expected_conversion_function", "original_values_immutable"),
    "screening_bounds": ("rhob_min_kg_m3", "rhob_max_kg_m3", "bounds_are_inclusive"),
    "gap_conditioning": ("bridge_short_internal_gaps", "short_gap_max_tvd_m",
                         "bridge_across_seabed_allowed",
                         "bridge_outside_survey_coverage_allowed",
                         "bridge_long_gaps_allowed",
                         "shallow_gap_uses_internal_gap_rule",
                         "shallow_gap_tolerance_tvd_m",
                         "sensitivity_thresholds_tvd_m"),
    "integration": ("method", "gravity_m_s2", "zero_increment_contribution",
                    "negative_increment_policy", "profile_report_step_tvdss_m"),
    "water_column": ("seawater_density_kg_m3", "seawater_density_low_kg_m3",
                     "seawater_density_high_kg_m3", "seabed_source",
                     "seabed_marker_name", "cross_well_seabed_transfer_allowed"),
    "shallow_column_scenarios": ("enabled", "low_basis", "high_basis", "high_percentile",
                                 "base_basis", "base_is_not_a_best_estimate",
                                 "scenario_names",
                                 "require_assumed_fraction_disclosure"),
    "eligibility": ("statuses", "absolute_requires_uninterrupted_column",
                    "min_eligible_samples_for_increment"),
}


def _require_number(section: str, key: str, value, filename: str) -> float:
    if isinstance(value, bool):
        raise OverburdenConfigError(
            f"{filename}: {section}.{key} must be a number, not a boolean.")
    if not isinstance(value, (int, float)):
        raise OverburdenConfigError(
            f"{filename}: {section}.{key} must be a number, got "
            f"{type(value).__name__} {value!r}.")
    out = float(value)
    if out != out or out in (float("inf"), float("-inf")):
        raise OverburdenConfigError(
            f"{filename}: {section}.{key} must be finite, got {value!r}.")
    return out


def _require_bool(section: str, key: str, value, filename: str) -> bool:
    if not isinstance(value, bool):
        raise OverburdenConfigError(
            f"{filename}: {section}.{key} must be a boolean, got "
            f"{type(value).__name__} {value!r}.")
    return value


def _require_str(section: str, key: str, value, filename: str) -> str:
    if not isinstance(value, str) or not value:
        raise OverburdenConfigError(
            f"{filename}: {section}.{key} must be a non-empty string, got "
            f"{type(value).__name__} {value!r}.")
    return value


def _require_integer(section: str, key: str, value, filename: str) -> int:
    """Require a genuine integer; never truncate a floating-point policy value."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise OverburdenConfigError(
            f"{filename}: {section}.{key} must be an integer, got "
            f"{type(value).__name__} {value!r}.")
    return value


def load_overburden_config(yaml_path: str) -> OverburdenConfig:
    """Load and validate `config/overburden_stress.yml`.

    Every required key is checked here so that a typo fails at load time
    rather than deep inside an integral, and every unknown top-level key or
    unknown key inside a known section is REJECTED rather than ignored - an
    ignored key is an unreviewed policy change.

    Four policy invariants are enforced as hard errors because violating any
    of them would silently cross an Increment 7 scientific boundary:

      * `bridge_across_seabed_allowed` must be false;
      * `bridge_outside_survey_coverage_allowed` must be false;
      * `bridge_long_gaps_allowed` must be false;
      * `shallow_gap_uses_internal_gap_rule` must be false - the unmeasured
        seabed-to-log column is not a dropout and must never be filled by the
        internal-gap rule.
    """
    path = Path(yaml_path)
    if not path.is_file():
        raise OverburdenConfigError(f"Overburden stress config not found: {yaml_path!r}.")
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.load(fh, Loader=_NoDuplicateKeySafeLoader)
    if not isinstance(raw, dict):
        raise OverburdenConfigError(f"{path.name}: top level must be a mapping.")
    if raw.get("schema_version") != "7.0.1":
        raise OverburdenConfigError(
            f"{path.name}: schema_version must be exactly '7.0.1', got "
            f"{raw.get('schema_version')!r}.")

    for key in _REQUIRED_TOP_KEYS:
        if key not in raw:
            raise OverburdenConfigError(
                f"{path.name}: required top-level key {key!r} is missing.")
    unknown_top = sorted(set(raw) - _KNOWN_TOP_KEYS)
    if unknown_top:
        raise OverburdenConfigError(
            f"{path.name}: unknown top-level key(s) {unknown_top}. An unrecognised key is "
            f"rejected rather than ignored, because an ignored key is an unreviewed policy "
            f"change.")

    for section, keys in _SECTION_KEYS.items():
        block = raw[section]
        if not isinstance(block, dict):
            raise OverburdenConfigError(f"{path.name}: {section!r} must be a mapping.")
        missing = [k for k in keys if k not in block]
        if missing:
            raise OverburdenConfigError(
                f"{path.name}: {section} is missing required key(s) {missing}.")
        unknown = sorted(set(block) - set(keys))
        if unknown:
            raise OverburdenConfigError(
                f"{path.name}: {section} contains unknown key(s) {unknown}.")

    ds = raw["density_source"]
    sb = raw["screening_bounds"]
    gc = raw["gap_conditioning"]
    ig = raw["integration"]
    wc = raw["water_column"]
    sc = raw["shallow_column_scenarios"]
    el = raw["eligibility"]

    if not _require_bool("density_source", "original_values_immutable",
                         ds["original_values_immutable"], path.name):
        raise OverburdenConfigError(
            f"{path.name}: density_source.original_values_immutable must be true. Increment 7 "
            f"never modifies a resolved density array.")
    for key in ("bridge_across_seabed_allowed", "bridge_outside_survey_coverage_allowed",
                "bridge_long_gaps_allowed", "shallow_gap_uses_internal_gap_rule"):
        if _require_bool("gap_conditioning", key, gc[key], path.name):
            raise OverburdenConfigError(
                f"{path.name}: gap_conditioning.{key} must be false. This is a hard "
                f"scientific invariant of Increment 7, not tunable behaviour.")
    if _require_bool("water_column", "cross_well_seabed_transfer_allowed",
                     wc["cross_well_seabed_transfer_allowed"], path.name):
        raise OverburdenConfigError(
            f"{path.name}: water_column.cross_well_seabed_transfer_allowed must be false. A "
            f"seabed marker belongs to the well it was picked in.")
    if not _require_bool("shallow_column_scenarios", "base_is_not_a_best_estimate",
                         sc["base_is_not_a_best_estimate"], path.name):
        raise OverburdenConfigError(
            f"{path.name}: shallow_column_scenarios.base_is_not_a_best_estimate must be true. "
            f"The base scenario is an arithmetic midpoint with no evidentiary support and "
            f"must never be declared a best estimate.")
    if not _require_bool("shallow_column_scenarios", "require_assumed_fraction_disclosure",
                         sc["require_assumed_fraction_disclosure"], path.name):
        raise OverburdenConfigError(
            f"{path.name}: shallow_column_scenarios.require_assumed_fraction_disclosure must "
            f"be true. A scenario total may not be published without stating how much of it "
            f"originates in the assumption.")

    method = _require_str("integration", "method", ig["method"], path.name)
    if "vertical_depth" not in method:
        raise OverburdenConfigError(
            f"{path.name}: integration.method {method!r} does not declare a vertical-depth "
            f"formulation. Increment 7 integrates in true vertical depth only.")

    thresholds = gc["sensitivity_thresholds_tvd_m"]
    if not isinstance(thresholds, list) or not thresholds:
        raise OverburdenConfigError(
            f"{path.name}: gap_conditioning.sensitivity_thresholds_tvd_m must be a non-empty "
            f"list.")
    threshold_values = tuple(
        _require_number("gap_conditioning", "sensitivity_thresholds_tvd_m", t, path.name)
        for t in thresholds)
    if any(t < 0.0 for t in threshold_values):
        raise OverburdenConfigError(
            f"{path.name}: gap_conditioning.sensitivity_thresholds_tvd_m must all be >= 0.")
    if len(set(threshold_values)) != len(threshold_values):
        raise OverburdenConfigError(
            f"{path.name}: gap_conditioning.sensitivity_thresholds_tvd_m contains duplicates.")

    statuses = el["statuses"]
    if not isinstance(statuses, list) or tuple(statuses) != VALID_OVERBURDEN_STATUSES:
        raise OverburdenConfigError(
            f"{path.name}: eligibility.statuses must equal the four declared status codes "
            f"in their required order: {list(VALID_OVERBURDEN_STATUSES)!r}.")
    scenario_names = sc["scenario_names"]
    if (not isinstance(scenario_names, list)
            or [str(s) for s in scenario_names] != ["low", "base", "high"]):
        raise OverburdenConfigError(
            f"{path.name}: shallow_column_scenarios.scenario_names must be exactly "
            f"['low', 'base', 'high']; low/base/high reporting is mandatory.")

    not_impl = raw["not_implemented"]
    if not isinstance(not_impl, list) or not not_impl:
        raise OverburdenConfigError(
            f"{path.name}: 'not_implemented' must be a non-empty list.")
    if any(not isinstance(item, str) or not item for item in not_impl):
        raise OverburdenConfigError(
            f"{path.name}: every 'not_implemented' entry must be a non-empty string; "
            f"numeric and other values are not coerced.")
    if len(set(not_impl)) != len(not_impl):
        raise OverburdenConfigError(
            f"{path.name}: 'not_implemented' contains duplicate entries.")

    expected_bases = {
        "low_basis": SCENARIO_BASIS_LOW,
        "base_basis": SCENARIO_BASIS_BASE,
        "high_basis": SCENARIO_BASIS_HIGH,
    }
    for key, expected in expected_bases.items():
        if sc[key] != expected:
            raise OverburdenConfigError(
                f"{path.name}: shallow_column_scenarios.{key} must be exactly "
                f"{expected!r}, got {sc[key]!r}.")

    increment = raw["increment"]
    if not isinstance(increment, int) or isinstance(increment, bool) or increment != 7:
        raise OverburdenConfigError(
            f"{path.name}: 'increment' must be the integer 7, got {increment!r}.")

    scenario_high_percentile = _require_number(
        "shallow_column_scenarios", "high_percentile",
        sc["high_percentile"], path.name)
    if scenario_high_percentile != 5.0:
        raise OverburdenConfigError(
            f"{path.name}: shallow_column_scenarios.high_percentile must be exactly "
            f"5.0 because Increment 7 stores and uses P05, got "
            f"{scenario_high_percentile!r}.")

    return OverburdenConfig(
        source_filename=path.name,
        schema_version=_require_str("", "schema_version", raw["schema_version"], path.name),
        increment=increment,
        assurance_tier=_require_str("", "assurance_tier", raw["assurance_tier"], path.name),
        canonical_curve_name=_require_str(
            "density_source", "canonical_curve_name", ds["canonical_curve_name"], path.name),
        accepted_canonical_unit=_require_str(
            "density_source", "accepted_canonical_unit", ds["accepted_canonical_unit"],
            path.name),
        expected_conversion_function=_require_str(
            "density_source", "expected_conversion_function",
            ds["expected_conversion_function"], path.name),
        rhob_min_kg_m3=_require_number("screening_bounds", "rhob_min_kg_m3",
                                       sb["rhob_min_kg_m3"], path.name),
        rhob_max_kg_m3=_require_number("screening_bounds", "rhob_max_kg_m3",
                                       sb["rhob_max_kg_m3"], path.name),
        bounds_are_inclusive=_require_bool("screening_bounds", "bounds_are_inclusive",
                                           sb["bounds_are_inclusive"], path.name),
        bridge_short_internal_gaps=_require_bool(
            "gap_conditioning", "bridge_short_internal_gaps",
            gc["bridge_short_internal_gaps"], path.name),
        short_gap_max_tvd_m=_require_number(
            "gap_conditioning", "short_gap_max_tvd_m", gc["short_gap_max_tvd_m"], path.name),
        shallow_gap_tolerance_tvd_m=_require_number(
            "gap_conditioning", "shallow_gap_tolerance_tvd_m",
            gc["shallow_gap_tolerance_tvd_m"], path.name),
        sensitivity_thresholds_tvd_m=tuple(sorted(threshold_values)),
        integration_method=method,
        gravity_m_s2=_require_number("integration", "gravity_m_s2", ig["gravity_m_s2"],
                                     path.name),
        profile_report_step_tvdss_m=_require_number(
            "integration", "profile_report_step_tvdss_m",
            ig["profile_report_step_tvdss_m"], path.name),
        seawater_density_kg_m3=_require_number(
            "water_column", "seawater_density_kg_m3", wc["seawater_density_kg_m3"],
            path.name),
        seawater_density_low_kg_m3=_require_number(
            "water_column", "seawater_density_low_kg_m3", wc["seawater_density_low_kg_m3"],
            path.name),
        seawater_density_high_kg_m3=_require_number(
            "water_column", "seawater_density_high_kg_m3", wc["seawater_density_high_kg_m3"],
            path.name),
        seabed_marker_name=_require_str(
            "water_column", "seabed_marker_name", wc["seabed_marker_name"], path.name),
        scenarios_enabled=_require_bool("shallow_column_scenarios", "enabled",
                                        sc["enabled"], path.name),
        scenario_high_percentile=scenario_high_percentile,
        scenario_names=tuple(str(s) for s in scenario_names),
        min_eligible_samples_for_increment=_require_integer(
            "eligibility", "min_eligible_samples_for_increment",
            el["min_eligible_samples_for_increment"], path.name),
        absolute_requires_uninterrupted_column=_require_bool(
            "eligibility", "absolute_requires_uninterrupted_column",
            el["absolute_requires_uninterrupted_column"], path.name),
        not_implemented=tuple(not_impl),
    )


# ---------------------------------------------------------------------------
# Curve resolution and unit confirmation
# ---------------------------------------------------------------------------

def resolve_density_slot(well_frame, config: OverburdenConfig):
    """Return `(slot, unit_resolved, conversion_confirmed)` for one well.

    `slot` is the locked well frame's own `CurveSlot` for the configured
    canonical density curve, or `None` when the well's locked contract
    resolved no such curve. A missing density curve is a factual data gap, not
    an error - the caller reports `rhob_not_available`.

    A curve that EXISTS but carries an unexpected canonical unit is a
    different matter: it is rejected with `DensityUnitError`, because
    Increment 7 performs no conversion of its own and must never integrate a
    quantity whose unit it cannot confirm.
    """
    slot = well_frame.curve(config.canonical_curve_name)
    if slot is None:
        return None, False, False
    if slot.canonical_unit != config.accepted_canonical_unit:
        raise DensityUnitError(
            f"{well_frame.well_key}: density curve "
            f"{config.canonical_curve_name!r} carries canonical unit "
            f"{slot.canonical_unit!r}, but Increment 7 accepts only "
            f"{config.accepted_canonical_unit!r}. Increment 7 performs no unit conversion of "
            f"its own; a curve whose unit cannot be confirmed is refused rather than "
            f"rescaled.")
    conversion_confirmed = (slot.conversion_function == config.expected_conversion_function)
    return slot, True, conversion_confirmed


# ---------------------------------------------------------------------------
# Masks
# ---------------------------------------------------------------------------

def _screening_mask(values: np.ndarray, config: OverburdenConfig) -> np.ndarray:
    finite = np.isfinite(values)
    if config.bounds_are_inclusive:
        band = (values >= config.rhob_min_kg_m3) & (values <= config.rhob_max_kg_m3)
    else:
        band = (values > config.rhob_min_kg_m3) & (values < config.rhob_max_kg_m3)
    return finite & band


def build_density_masks(
    well_frame,
    config: OverburdenConfig,
    *,
    seabed_mdrt_m: Optional[float] = None,
    gap_result: Optional[GapConditioningResult] = None,
) -> DensityMaskSet:
    """Construct the twelve explicit per-sample masks for ONE well.

    The masks are built in dependency order and every one is retained; none is
    collapsed into another. `eligible_for_measured_integration` is the explicit
    conjunction

        finite AND unit_resolved AND screening_range_plausible
        AND depth_mapping_valid AND within_survey_coverage
        [AND below_seabed_sample, when the seabed is resolved]

    and it is deliberately NOT extended with a bridged sample: a bridged value
    is conditioned, not measured, and travels in its own mask.

    `gap_result`, when supplied, contributes the three unresolved-region masks
    and the bridged mask. When it is omitted, those four masks are all-False -
    a state that means "gap conditioning has not been applied yet", and which
    the caller resolves by passing the result of `condition_density_gaps`.
    """
    n = int(well_frame.n_samples)
    slot, unit_ok, _ = resolve_density_slot(well_frame, config)

    if slot is None:
        values = np.full(n, np.nan, dtype=np.float64)
        present = np.zeros(n, dtype=bool)
    else:
        values = np.asarray(slot.values)
        _reject_ambiguous_dtype(values, f"{well_frame.well_key}: RHOB values")
        values = values.astype(np.float64, copy=True)
        # "Source value present" is a CURVE-LEVEL fact expressed per sample:
        # this well's locked contract resolved a density column, so a value
        # slot exists at every depth. It is deliberately NOT the same mask as
        # `finite_numeric_density`. The locked Increment 2.1.1 loader has
        # already substituted each file's NULL sentinel with NaN, so an
        # absent token and a recorded NULL are indistinguishable downstream;
        # claiming to separate them per sample would assert a distinction the
        # data no longer carry. The distinction that IS available - a well
        # with no density column at all - is exactly what this mask records.
        present = np.ones(n, dtype=bool)

    finite = np.isfinite(values)
    unit_resolved = np.full(n, bool(unit_ok), dtype=bool)
    screening = _screening_mask(values, config) & unit_resolved
    depth_valid = np.asarray(well_frame.depth_valid_mask, dtype=bool)

    md = np.asarray(well_frame.MD_m, dtype=np.float64)
    within_survey = (md >= float(well_frame.survey_md_min_m)) & (
        md <= float(well_frame.survey_md_max_m))

    if seabed_mdrt_m is None:
        below_seabed: Optional[np.ndarray] = None
        seabed_resolved = False
    else:
        seabed_resolved = True
        below_seabed = md >= float(seabed_mdrt_m)

    eligible = finite & unit_resolved & screening & depth_valid & within_survey
    if below_seabed is not None:
        eligible = eligible & below_seabed

    if gap_result is None:
        bridged = np.zeros(n, dtype=bool)
        long_gap = np.zeros(n, dtype=bool)
        shallow = np.zeros(n, dtype=bool)
        terminal = np.zeros(n, dtype=bool)
    else:
        bridged = np.asarray(gap_result.bridged_mask, dtype=bool).copy()
        long_gap = np.zeros(n, dtype=bool)
        shallow = np.zeros(n, dtype=bool)
        terminal = np.zeros(n, dtype=bool)
        for gap in gap_result.gaps:
            if gap.start_index is None or gap.end_index is None:
                continue
            lo, hi = int(gap.start_index), int(gap.end_index)
            if gap.gap_class == GAP_CLASS_LONG_INTERNAL:
                long_gap[lo:hi + 1] = True
            elif gap.gap_class == GAP_CLASS_SHALLOW:
                shallow[lo:hi + 1] = True
            elif gap.gap_class == GAP_CLASS_TERMINAL:
                terminal[lo:hi + 1] = True

    return DensityMaskSet(
        well_key=well_frame.well_key,
        n_samples=n,
        seabed_resolved=seabed_resolved,
        source_value_present=readonly(present),
        finite_numeric_density=readonly(finite),
        unit_resolved=readonly(unit_resolved),
        screening_range_plausible=readonly(screening),
        below_seabed_sample=None if below_seabed is None else readonly(below_seabed),
        depth_mapping_valid=readonly(depth_valid),
        within_survey_coverage=readonly(within_survey),
        eligible_for_measured_integration=readonly(eligible),
        bridged_short_gap=readonly(bridged),
        unresolved_long_gap=readonly(long_gap),
        unresolved_shallow_column=readonly(shallow),
        unresolved_terminal_column=readonly(terminal),
    )


# ---------------------------------------------------------------------------
# Gap classification
# ---------------------------------------------------------------------------

def _runs_of_false(mask: np.ndarray, lo: int, hi: int) -> List[Tuple[int, int]]:
    """Return inclusive `(start, end)` index pairs of False runs in `mask[lo:hi+1]`."""
    runs: List[Tuple[int, int]] = []
    i = lo
    while i <= hi:
        if not mask[i]:
            j = i
            while j <= hi and not mask[j]:
                j += 1
            runs.append((i, j - 1))
            i = j
        else:
            i += 1
    return runs


def classify_density_gaps(
    well_frame,
    masks: DensityMaskSet,
    config: OverburdenConfig,
    *,
    seabed_tvd_m: Optional[float] = None,
    threshold_tvd_m: Optional[float] = None,
) -> Tuple[DensityGapRecord, ...]:
    """Classify every gap in ONE well's density column.

    Five structurally distinct cases are kept apart, exactly as the Increment 7
    policy requires:

      * an internal gap at or below the threshold  -> short_internal_gap
      * an internal gap above the threshold        -> long_internal_gap
      * seabed to first eligible sample            -> shallow gap
      * below the last eligible sample             -> terminal gap
      * a run rendered ineligible only by missing depth mapping
                                                   -> unmapped-depth gap

    An isolated invalid sample is not a separate class in the emitted record:
    it is an internal gap of one sample, and its `n_samples` field says so.
    The distinction the policy asks for is preserved in the count, not
    duplicated as a third internal category that would have to be kept
    consistent with the other two.

    The shallow gap is classified here and is NEVER a candidate for bridging.
    Its disposition is always `unresolved_not_bridged`, at any threshold.
    """
    threshold = _validated_gap_threshold(
        config.short_gap_max_tvd_m if threshold_tvd_m is None else threshold_tvd_m,
        "classify_density_gaps")
    elig = np.asarray(masks.eligible_for_measured_integration, dtype=bool)
    md = np.asarray(well_frame.MD_m, dtype=np.float64)
    tvd = np.asarray(well_frame.TVD_m, dtype=np.float64)
    depth_valid = np.asarray(well_frame.depth_valid_mask, dtype=bool)
    values = None
    slot = well_frame.curve(config.canonical_curve_name)
    if slot is not None:
        values = np.asarray(slot.values, dtype=np.float64)

    records: List[DensityGapRecord] = []
    idx = np.flatnonzero(elig)

    def _depth(arr, i):
        v = float(arr[i])
        return v if np.isfinite(v) else None

    if idx.size == 0:
        # No eligible sample at all: the whole column below the seabed is an
        # unresolved shallow gap when the seabed is known, and otherwise there
        # is no determinable datum to measure a shallow gap from.
        if seabed_tvd_m is not None:
            below_seabed = masks.below_seabed_sample
            spanned = (np.flatnonzero(np.asarray(below_seabed, dtype=bool))
                       if below_seabed is not None else np.array([], dtype=int))
            records.append(DensityGapRecord(
                well_key=well_frame.well_key, gap_index=0, gap_class=GAP_CLASS_SHALLOW,
                disposition=GAP_DISPOSITION_UNRESOLVED, n_samples=int(spanned.size),
                start_index=(int(spanned[0]) if spanned.size else None),
                end_index=(int(spanned[-1]) if spanned.size else None),
                md_start_m=None, md_end_m=None,
                tvd_start_m=float(seabed_tvd_m), tvd_end_m=None,
                thickness_md_m=None, thickness_tvd_m=None, threshold_tvd_m=threshold,
                bounding_density_above_kg_m3=None, bounding_density_below_kg_m3=None))
        return tuple(records)

    first, last = int(idx[0]), int(idx[-1])
    gap_index = 0

    if seabed_tvd_m is not None:
        top_tvd = _depth(tvd, first)
        thickness = (None if top_tvd is None else max(0.0, top_tvd - float(seabed_tvd_m)))
        # The shallow unresolved column runs from the seabed down to the first
        # eligible sample. Its THICKNESS is measured between those two depths,
        # which is the quantity that matters. Its LAS sample range covers only
        # the part of that column the log actually spans: a log starting below
        # the seabed leaves the interval above its own first sample with no
        # LAS row at all, and no mask can represent a sample that does not
        # exist. Both facts are recorded, and they are deliberately not
        # conflated.
        below_seabed = masks.below_seabed_sample
        if below_seabed is not None:
            in_column = np.zeros(int(md.size), dtype=bool)
            in_column[:first] = True
            in_column &= np.asarray(below_seabed, dtype=bool)
            spanned = np.flatnonzero(in_column)
        else:  # pragma: no cover - a seabed TVD without a seabed mask
            spanned = np.array([], dtype=int)
        records.append(DensityGapRecord(
            well_key=well_frame.well_key, gap_index=gap_index, gap_class=GAP_CLASS_SHALLOW,
            disposition=GAP_DISPOSITION_UNRESOLVED, n_samples=int(spanned.size),
            start_index=(int(spanned[0]) if spanned.size else None),
            end_index=(int(spanned[-1]) if spanned.size else None),
            md_start_m=None, md_end_m=float(md[first]),
            tvd_start_m=float(seabed_tvd_m), tvd_end_m=top_tvd,
            thickness_md_m=None, thickness_tvd_m=thickness, threshold_tvd_m=threshold,
            bounding_density_above_kg_m3=None, bounding_density_below_kg_m3=None))
        gap_index += 1

    for lo, hi in _runs_of_false(elig, first, last):
        above, below = lo - 1, hi + 1
        t_above, t_below = _depth(tvd, above), _depth(tvd, below)
        thickness_tvd = (None if (t_above is None or t_below is None)
                         else max(0.0, t_below - t_above))
        thickness_md = float(md[below] - md[above])
        # A run that is ineligible ONLY because its depth mapping is missing
        # is a different physical situation from a missing density reading,
        # and it is never bridgeable: there is no defensible vertical
        # coordinate to interpolate against.
        run_unmapped = bool(np.all(~depth_valid[lo:hi + 1]))
        if run_unmapped:
            gap_class = GAP_CLASS_UNMAPPED_DEPTH
            disposition = GAP_DISPOSITION_UNRESOLVED
        elif thickness_tvd is not None and thickness_tvd <= threshold:
            gap_class = GAP_CLASS_SHORT_INTERNAL
            disposition = (GAP_DISPOSITION_BRIDGED if config.bridge_short_internal_gaps
                           else GAP_DISPOSITION_UNRESOLVED)
        else:
            gap_class = GAP_CLASS_LONG_INTERNAL
            disposition = GAP_DISPOSITION_UNRESOLVED
        records.append(DensityGapRecord(
            well_key=well_frame.well_key, gap_index=gap_index, gap_class=gap_class,
            disposition=disposition, n_samples=hi - lo + 1,
            start_index=lo, end_index=hi,
            md_start_m=float(md[above]), md_end_m=float(md[below]),
            tvd_start_m=t_above, tvd_end_m=t_below,
            thickness_md_m=thickness_md, thickness_tvd_m=thickness_tvd,
            threshold_tvd_m=threshold,
            bounding_density_above_kg_m3=(
                None if values is None else float(values[above])),
            bounding_density_below_kg_m3=(
                None if values is None else float(values[below]))))
        gap_index += 1

    n_terminal = int(md.size) - last - 1
    if n_terminal > 0:
        t_last = _depth(tvd, last)
        t_end = _depth(tvd, int(md.size) - 1)
        records.append(DensityGapRecord(
            well_key=well_frame.well_key, gap_index=gap_index, gap_class=GAP_CLASS_TERMINAL,
            disposition=GAP_DISPOSITION_UNRESOLVED, n_samples=n_terminal,
            start_index=last + 1, end_index=int(md.size) - 1,
            md_start_m=float(md[last]), md_end_m=float(md[-1]),
            tvd_start_m=t_last, tvd_end_m=t_end,
            thickness_md_m=float(md[-1] - md[last]),
            thickness_tvd_m=(None if (t_last is None or t_end is None)
                             else max(0.0, t_end - t_last)),
            threshold_tvd_m=threshold,
            bounding_density_above_kg_m3=(None if values is None else float(values[last])),
            bounding_density_below_kg_m3=None))

    return tuple(records)


# ---------------------------------------------------------------------------
# Gap conditioning
# ---------------------------------------------------------------------------

def condition_density_gaps(
    well_frame,
    masks: DensityMaskSet,
    config: OverburdenConfig,
    *,
    seabed_tvd_m: Optional[float] = None,
    threshold_tvd_m: Optional[float] = None,
) -> GapConditioningResult:
    """Apply the configured gap-conditioning policy to ONE well.

    Bridging is linear interpolation of density against TRUE VERTICAL DEPTH -
    the coordinate the stress integral is taken in - between the two
    bracketing eligible samples. It writes ONLY into a new array; the well
    frame's own resolved density array is never touched.

    A gap is bridged only if ALL of the following hold:
      * bridging is enabled in configuration;
      * the gap is an internal gap, strictly inside the bracketed measured
        column (so it can never reach the seabed or the terminal column);
      * its TVD thickness is at or below the approved threshold;
      * every sample in it has a valid locked depth mapping and lies within
        locked survey coverage;
      * both bracketing samples carry finite, in-band measured density.
    """
    threshold = _validated_gap_threshold(
        config.short_gap_max_tvd_m if threshold_tvd_m is None else threshold_tvd_m,
        "condition_density_gaps")
    gaps = classify_density_gaps(
        well_frame, masks, config, seabed_tvd_m=seabed_tvd_m, threshold_tvd_m=threshold)

    slot = well_frame.curve(config.canonical_curve_name)
    n = int(well_frame.n_samples)
    if slot is None:
        conditioned = np.full(n, np.nan, dtype=np.float64)
    else:
        # An explicit copy. The locked CurveSlot array is read-only by
        # construction; this makes the separation of the conditioned
        # representation from the original an observable property of the code,
        # not a consequence of someone else's flag.
        conditioned = np.array(slot.values, dtype=np.float64, copy=True)

    tvd = np.asarray(well_frame.TVD_m, dtype=np.float64)
    md = np.asarray(well_frame.MD_m, dtype=np.float64)
    within_survey = np.asarray(masks.within_survey_coverage, dtype=bool)
    depth_valid = np.asarray(masks.depth_mapping_valid, dtype=bool)

    bridged = np.zeros(n, dtype=bool)
    n_bridged_gaps = 0
    n_bridged_samples = 0
    bridged_md = 0.0
    bridged_tvd = 0.0
    n_long_gaps = 0
    n_long_samples = 0
    long_md = 0.0
    long_tvd = 0.0
    emitted: List[DensityGapRecord] = []

    for gap in gaps:
        if gap.gap_class == GAP_CLASS_LONG_INTERNAL:
            n_long_gaps += 1
            n_long_samples += gap.n_samples
            long_md += float(gap.thickness_md_m or 0.0)
            long_tvd += float(gap.thickness_tvd_m or 0.0)
            emitted.append(gap)
            continue
        if gap.gap_class != GAP_CLASS_SHORT_INTERNAL:
            emitted.append(gap)
            continue
        lo, hi = int(gap.start_index), int(gap.end_index)
        above, below = lo - 1, hi + 1
        can_bridge = (
            config.bridge_short_internal_gaps
            and bool(np.all(depth_valid[lo:hi + 1]))
            and bool(np.all(within_survey[lo:hi + 1]))
            and np.isfinite(tvd[above]) and np.isfinite(tvd[below])
            and np.isfinite(conditioned[above]) and np.isfinite(conditioned[below])
            and float(tvd[below]) > float(tvd[above])
        )
        if not can_bridge:
            emitted.append(DensityGapRecord(
                well_key=gap.well_key, gap_index=gap.gap_index,
                gap_class=gap.gap_class, disposition=GAP_DISPOSITION_UNRESOLVED,
                n_samples=gap.n_samples, start_index=gap.start_index,
                end_index=gap.end_index, md_start_m=gap.md_start_m,
                md_end_m=gap.md_end_m, tvd_start_m=gap.tvd_start_m,
                tvd_end_m=gap.tvd_end_m, thickness_md_m=gap.thickness_md_m,
                thickness_tvd_m=gap.thickness_tvd_m, threshold_tvd_m=gap.threshold_tvd_m,
                bounding_density_above_kg_m3=gap.bounding_density_above_kg_m3,
                bounding_density_below_kg_m3=gap.bounding_density_below_kg_m3))
            continue
        z0, z1 = float(tvd[above]), float(tvd[below])
        r0, r1 = float(conditioned[above]), float(conditioned[below])
        z = tvd[lo:hi + 1]
        conditioned[lo:hi + 1] = r0 + (r1 - r0) * (z - z0) / (z1 - z0)
        bridged[lo:hi + 1] = True
        n_bridged_gaps += 1
        n_bridged_samples += gap.n_samples
        bridged_md += float(md[below] - md[above])
        bridged_tvd += (z1 - z0)
        emitted.append(DensityGapRecord(
            well_key=gap.well_key, gap_index=gap.gap_index, gap_class=gap.gap_class,
            disposition=GAP_DISPOSITION_BRIDGED, n_samples=gap.n_samples,
            start_index=gap.start_index, end_index=gap.end_index,
            md_start_m=gap.md_start_m, md_end_m=gap.md_end_m,
            tvd_start_m=gap.tvd_start_m, tvd_end_m=gap.tvd_end_m,
            thickness_md_m=gap.thickness_md_m, thickness_tvd_m=gap.thickness_tvd_m,
            threshold_tvd_m=gap.threshold_tvd_m,
            bounding_density_above_kg_m3=r0, bounding_density_below_kg_m3=r1))

    return GapConditioningResult(
        well_key=well_frame.well_key,
        threshold_tvd_m=threshold,
        bridging_enabled=bool(config.bridge_short_internal_gaps),
        conditioned_density_kg_m3=readonly(conditioned),
        bridged_mask=readonly(bridged),
        n_bridged_gaps=n_bridged_gaps,
        n_bridged_samples=n_bridged_samples,
        bridged_thickness_md_m=bridged_md,
        bridged_thickness_tvd_m=bridged_tvd,
        n_long_gaps=n_long_gaps,
        n_long_gap_samples=n_long_samples,
        long_gap_thickness_md_m=long_md,
        long_gap_thickness_tvd_m=long_tvd,
        gaps=tuple(emitted),
    )


# ---------------------------------------------------------------------------
# QC statistics
# ---------------------------------------------------------------------------

def compute_density_qc_stats(
    well_frame,
    masks: DensityMaskSet,
    config: OverburdenConfig,
    *,
    seabed_mdrt_m: Optional[float] = None,
    seabed_tvd_m: Optional[float] = None,
    seabed_tvdss_m: Optional[float] = None,
    gaps: Tuple[DensityGapRecord, ...] = (),
) -> DensityQcStats:
    """Measure factual density QC statistics for ONE well.

    Every number returned is a measurement about the curve as recorded or a
    count of samples failing an explicitly configured screening criterion.
    Nothing here modifies, corrects, or interprets the curve.
    """
    n = int(well_frame.n_samples)
    slot, unit_ok, conversion_confirmed = resolve_density_slot(well_frame, config)

    md = np.asarray(well_frame.MD_m, dtype=np.float64)
    tvd = np.asarray(well_frame.TVD_m, dtype=np.float64)
    tvdss = np.asarray(well_frame.TVDSS_m, dtype=np.float64)

    if slot is None:
        values = np.full(n, np.nan, dtype=np.float64)
    else:
        values = np.asarray(slot.values, dtype=np.float64)

    finite = np.asarray(masks.finite_numeric_density, dtype=bool)
    in_band = np.asarray(masks.screening_range_plausible, dtype=bool)
    elig = np.asarray(masks.eligible_for_measured_integration, dtype=bool)
    depth_valid = np.asarray(masks.depth_mapping_valid, dtype=bool)
    within_survey = np.asarray(masks.within_survey_coverage, dtype=bool)

    n_non_positive = int(np.count_nonzero(finite & (values <= 0.0)))
    below_min = finite & (values > 0.0) & (
        values < config.rhob_min_kg_m3 if config.bounds_are_inclusive
        else values <= config.rhob_min_kg_m3)
    above_max = finite & (
        values > config.rhob_max_kg_m3 if config.bounds_are_inclusive
        else values >= config.rhob_max_kg_m3)
    n_below = int(np.count_nonzero(below_min))
    n_above = int(np.count_nonzero(above_max))

    fv = values[finite]
    eligible_values = values[elig]
    idx = np.flatnonzero(elig)

    def _at(arr, i):
        v = float(arr[i])
        return v if np.isfinite(v) else None

    if idx.size:
        first, last = int(idx[0]), int(idx[-1])
        first_md, last_md = float(md[first]), float(md[last])
        first_tvd, last_tvd = _at(tvd, first), _at(tvd, last)
        first_tvdss, last_tvdss = _at(tvdss, first), _at(tvdss, last)
        gross_md = last_md - first_md
        gross_tvd = (None if (first_tvd is None or last_tvd is None)
                     else last_tvd - first_tvd)
    else:
        first_md = last_md = first_tvd = last_tvd = None
        first_tvdss = last_tvdss = gross_md = gross_tvd = None

    internal = [g for g in gaps if g.gap_class in (
        GAP_CLASS_SHORT_INTERNAL, GAP_CLASS_LONG_INTERNAL, GAP_CLASS_UNMAPPED_DEPTH)]
    shallow = next((g for g in gaps if g.gap_class == GAP_CLASS_SHALLOW), None)
    terminal = next((g for g in gaps if g.gap_class == GAP_CLASS_TERMINAL), None)

    return DensityQcStats(
        well_key=well_frame.well_key,
        source_las_filename=well_frame.source_las_filename,
        curve_present=slot is not None,
        canonical_curve_name=(None if slot is None else slot.canonical_name),
        source_curve_name=(None if slot is None else slot.source_curve_name),
        raw_mnemonic=(None if slot is None else slot.raw_mnemonic),
        raw_unit=(None if slot is None else slot.raw_unit),
        canonical_unit=(None if slot is None else slot.canonical_unit),
        conversion_function=(None if slot is None else slot.conversion_function),
        unit_resolved=bool(unit_ok),
        conversion_confirmed=bool(conversion_confirmed),
        n_samples=n,
        n_source_present=int(np.count_nonzero(masks.source_value_present)),
        n_finite=int(np.count_nonzero(finite)),
        n_non_finite=int(n - np.count_nonzero(finite)),
        n_non_positive=n_non_positive,
        n_below_screening_min=n_below,
        n_above_screening_max=n_above,
        n_screening_bound_failures=n_non_positive + n_below + n_above,
        n_in_screening_band=int(np.count_nonzero(in_band)),
        n_depth_mapped=int(np.count_nonzero(depth_valid)),
        n_depth_unmapped=int(n - np.count_nonzero(depth_valid)),
        n_eligible=int(np.count_nonzero(elig)),
        rhob_min_kg_m3=(float(np.min(fv)) if fv.size else None),
        rhob_max_kg_m3=(float(np.max(fv)) if fv.size else None),
        rhob_median_kg_m3=(float(np.median(fv)) if fv.size else None),
        rhob_p05_kg_m3=(float(np.percentile(fv, 5.0)) if fv.size else None),
        rhob_p95_kg_m3=(float(np.percentile(fv, 95.0)) if fv.size else None),
        rhob_eligible_p05_kg_m3=(
            float(np.percentile(eligible_values, config.scenario_high_percentile))
            if eligible_values.size else None),
        first_valid_md_m=first_md,
        last_valid_md_m=last_md,
        first_valid_tvd_m=first_tvd,
        last_valid_tvd_m=last_tvd,
        first_valid_tvdss_m=first_tvdss,
        last_valid_tvdss_m=last_tvdss,
        gross_coverage_md_m=gross_md,
        gross_coverage_tvd_m=gross_tvd,
        median_md_step_m=(float(np.median(np.diff(md))) if md.size > 1 else None),
        seabed_basis=(SEABED_BASIS_LOCKED_MARKER if seabed_mdrt_m is not None
                      else SEABED_BASIS_NOT_DETERMINABLE),
        seabed_mdrt_m=(None if seabed_mdrt_m is None else float(seabed_mdrt_m)),
        seabed_tvd_m=(None if seabed_tvd_m is None else float(seabed_tvd_m)),
        seabed_tvdss_m=(None if seabed_tvdss_m is None else float(seabed_tvdss_m)),
        shallow_gap_md_m=(None if shallow is None or first_md is None or seabed_mdrt_m is None
                          else float(first_md - float(seabed_mdrt_m))),
        shallow_gap_tvd_m=(None if shallow is None else shallow.thickness_tvd_m),
        terminal_gap_md_m=(None if terminal is None else terminal.thickness_md_m),
        terminal_gap_tvd_m=(None if terminal is None else terminal.thickness_tvd_m),
        n_internal_gaps=len(internal),
        n_internal_gap_samples=sum(g.n_samples for g in internal),
        longest_internal_gap_md_m=(
            max((g.thickness_md_m for g in internal if g.thickness_md_m is not None),
                default=None)),
        longest_internal_gap_tvd_m=(
            max((g.thickness_tvd_m for g in internal if g.thickness_tvd_m is not None),
                default=None)),
        depth_basis_used=well_frame.depth_basis_used,
        depth_map_status=well_frame.depth_map_status,
        survey_md_min_m=float(well_frame.survey_md_min_m),
        survey_md_max_m=float(well_frame.survey_md_max_m),
        n_samples_outside_survey_coverage=int(n - np.count_nonzero(within_survey)),
    )
