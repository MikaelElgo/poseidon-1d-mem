"""Hydrostatic-reference and effective-stress calculations for Increment 8.

The module intentionally implements no NCT fit and no overpressure transform.
Hydrostatic pressure is a configured reference, not a measured formation
pressure. Effective stress is reported only as a scenario paired with the
Increment 7 vertical-stress scenarios.
"""

import math
from pathlib import Path
from typing import Iterable, Mapping, Sequence, Tuple

import yaml

from p2mem.pore_pressure_models import (
    ASSURANCE_TIER, PRESSURE_DATA_TYPES, EffectiveStressScenario,
    HydrostaticReferenceNode, NctReadiness, PorePressureInputError,
    PressureConfig, PressureDataAvailability,
)


class _NoDuplicateKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that refuses silent duplicate-key overwrites."""


def _construct_mapping_no_duplicates(loader, node, deep=False):
    loader.flatten_mapping(node)
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(
                f"duplicate configuration key {key!r} at line "
                f"{key_node.start_mark.line + 1}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_NoDuplicateKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_no_duplicates,
)


def _locked_float_token(row: Mapping[str, str], field: str, context: str) -> float:
    try:
        token = row[field]
        if not isinstance(token, str) or not token.strip():
            raise ValueError("required non-empty string token")
        value = float(token)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise PorePressureInputError(
            f"{context}: {field!r} must be a finite numeric token.") from exc
    if not math.isfinite(value):
        raise PorePressureInputError(
            f"{context}: {field!r} must be finite.")
    return value


def _locked_int_token(row: Mapping[str, str], field: str, context: str) -> int:
    try:
        token = row[field]
        if not isinstance(token, str) or not token.isdigit():
            raise ValueError("canonical non-negative integer token required")
        return int(token)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise PorePressureInputError(
            f"{context}: {field!r} must be a canonical integer token.") from exc


def load_pressure_config(path) -> PressureConfig:
    """Load and strictly validate the human-authored Increment 8 policy."""
    p = Path(path)
    if not p.is_file():
        raise PorePressureInputError(f"Pressure policy is missing: {p.name!r}.")
    try:
        raw = yaml.load(
            p.read_text(encoding="utf-8"), Loader=_NoDuplicateKeySafeLoader)
        if not isinstance(raw, dict):
            raise TypeError("top-level mapping required")
        expected_top = {
            "schema_version", "increment", "assurance_tier", "locked_inputs",
            "hydrostatic_reference", "effective_stress", "pressure_calibration",
            "prediction_policy", "reporting",
        }
        if set(raw) != expected_top:
            raise KeyError("unknown or missing top-level field")
        locked = raw["locked_inputs"]
        h = raw["hydrostatic_reference"]
        e = raw["effective_stress"]
        c = raw["pressure_calibration"]
        pred = raw["prediction_policy"]
        reporting = raw["reporting"]
        if any(not isinstance(section, dict) for section in (locked, h, e, c, pred, reporting)):
            raise TypeError("all policy sections must be mappings")
        expected_locked = {
            "vertical_stress_profile": "outputs/07_density_overburden/vertical_stress_profile.csv",
            "shallow_column_scenarios": "outputs/07_density_overburden/shallow_column_scenarios.csv",
            "overburden_eligibility": "outputs/07_density_overburden/overburden_eligibility_summary.csv",
            "method_eligibility": "outputs/06_petrophysics_eligibility/method_eligibility_summary.csv",
            "thickness_sensitivity": "outputs/06_petrophysics_eligibility/thickness_sensitivity_summary.csv",
            "petrophysics_manifest": "outputs/06_petrophysics_eligibility/petrophysics_eligibility_manifest.json",
            "sonic_checkshot_drift": "outputs/04_checkshot_time_depth/sonic_checkshot_drift_summary.csv",
        }
        if locked != expected_locked:
            raise KeyError("locked input registry changed")
        if set(h) != {"gravity_m_s2", "fluid_density_low_kg_m3",
                      "fluid_density_base_kg_m3", "fluid_density_high_kg_m3",
                      "pressure_datum", "depth_coordinate"}:
            raise KeyError("hydrostatic policy fields changed")
        if (h["pressure_datum"] != "mean_sea_level_gauge_zero"
                or h["depth_coordinate"] != "tvdss_m_positive_downward"):
            raise ValueError("hydrostatic datum or coordinate changed")
        if set(e) != {"equation", "biot_alpha_scenarios", "profile_biot_alpha",
                      "profile_fluid_density_kg_m3", "negative_values_policy"}:
            raise KeyError("effective-stress policy fields changed")
        if (e["equation"] != "sigma_v_effective_pa = sigma_v_total_pa - biot_alpha * pore_pressure_pa"
                or e["negative_values_policy"] != "retain_and_flag_never_clip"):
            raise ValueError("effective-stress equation or negative-value policy changed")
        if set(c) != {"required_types", "available_file_count", "cross_well_transfer_allowed"}:
            raise KeyError("calibration policy fields changed")
        if set(pred) != {"nct_fit_enabled", "overpressure_transform_enabled",
                         "pressure_calibration_required",
                         "independent_normal_interval_evidence_required",
                         "sonic_checkshot_drift_correction_allowed", "extrapolation_allowed"}:
            raise KeyError("prediction policy fields changed")
        if set(reporting) != {"output_directory", "increment_9_started"}:
            raise KeyError("reporting policy fields changed")
        if reporting["output_directory"] != "outputs/08_pore_pressure_effective_stress":
            raise ValueError("output directory changed")
    except (OSError, TypeError, KeyError, ValueError, yaml.YAMLError) as exc:
        raise PorePressureInputError("Pressure policy is malformed.") from exc
    if not isinstance(raw, dict) or raw.get("increment") != 8:
        raise PorePressureInputError("Pressure policy must declare increment: 8.")
    return PressureConfig(
        schema_version=raw.get("schema_version"),
        assurance_tier=raw.get("assurance_tier"),
        gravity_m_s2=h.get("gravity_m_s2"),
        fluid_density_low_kg_m3=h.get("fluid_density_low_kg_m3"),
        fluid_density_base_kg_m3=h.get("fluid_density_base_kg_m3"),
        fluid_density_high_kg_m3=h.get("fluid_density_high_kg_m3"),
        biot_alpha_scenarios=tuple(e.get("biot_alpha_scenarios", ())),
        profile_biot_alpha=e.get("profile_biot_alpha"),
        profile_fluid_density_kg_m3=e.get("profile_fluid_density_kg_m3"),
        pressure_calibration_types=tuple(c.get("required_types", ())),
        pressure_calibration_file_count=c.get("available_file_count"),
        cross_well_transfer_allowed=c.get("cross_well_transfer_allowed"),
        nct_fit_enabled=pred.get("nct_fit_enabled"),
        overpressure_transform_enabled=pred.get("overpressure_transform_enabled"),
        pressure_calibration_required=pred.get("pressure_calibration_required"),
        independent_normal_interval_evidence_required=pred.get(
            "independent_normal_interval_evidence_required"),
        sonic_checkshot_drift_correction_allowed=pred.get(
            "sonic_checkshot_drift_correction_allowed"),
        extrapolation_allowed=pred.get("extrapolation_allowed"),
        increment_9_started=reporting.get("increment_9_started"),
    )


def hydrostatic_reference_pressure_pa(tvdss_m, fluid_density_kg_m3,
                                      gravity_m_s2) -> float:
    """Return gauge pressure from MSL: ``rho * g * TVDSS``.

    The domain is at or below mean sea level (TVDSS >= 0). Inputs are strict
    finite real scalars; booleans, strings, complex values, NaN and infinities
    are rejected with :class:`PorePressureInputError`.
    """
    from p2mem.pore_pressure_models import finite_real
    z = finite_real(tvdss_m, "tvdss_m", minimum=0.0)
    rho = finite_real(fluid_density_kg_m3, "fluid_density_kg_m3", minimum=0.0)
    g = finite_real(gravity_m_s2, "gravity_m_s2", minimum=0.0)
    if rho == 0.0 or g == 0.0:
        raise PorePressureInputError("fluid density and gravity must be > 0.")
    return rho * g * z


def effective_vertical_stress_pa(total_vertical_stress_pa,
                                 pore_pressure_pa, biot_alpha) -> float:
    """Return ``Sv - alpha*Pp`` without clipping negative scenario values."""
    from p2mem.pore_pressure_models import finite_real
    sv = finite_real(total_vertical_stress_pa, "total_vertical_stress_pa", minimum=0.0)
    pp = finite_real(pore_pressure_pa, "pore_pressure_pa", minimum=0.0)
    alpha = finite_real(biot_alpha, "biot_alpha", minimum=0.0, maximum=1.0)
    return sv - alpha * pp


def build_pressure_data_inventory(well_keys: Iterable[str]) -> Tuple[PressureDataAvailability, ...]:
    """Return the explicit zero-count *approved-input* inventory for each well."""
    return tuple(PressureDataAvailability(
        well_key=wk, rft_count=0, mdt_count=0, dst_count=0, fit_count=0,
        lot_count=0, xlot_count=0, dfit_count=0,
        availability_status="NOT_AVAILABLE",
    ) for wk in sorted(well_keys))


def derive_nct_readiness(well_key: str, thickness_rows: Sequence[Mapping[str, str]]) -> NctReadiness:
    """Derive whether a real NCT fit is defensible from locked sensitivity rows.

    Candidate configurations are data-eligibility cases, not independent
    measurements. Even when they exist, fitting is withheld because the
    project has neither pressure calibration nor an independently established
    normally compacted reference interval.
    """
    selected = [r for r in thickness_rows
                if r.get("well_key") == well_key
                and r.get("mask_name") == "eligible_sonic_nct_candidate"
                and r.get("contiguity_policy") == "strict_no_gap"]
    if not selected:
        return NctReadiness(
            well_key=well_key, status="NOT_ELIGIBLE_INPUT_QC_EXCLUSION",
            candidate_configurations=0,
            qualifying_thickness_min_tvd_m=None,
            qualifying_thickness_max_tvd_m=None,
            thickness_sensitivity_factor=None,
            pressure_calibration_available=False,
            independent_normal_interval_evidence_available=False,
            nct_fit_performed=False, overpressure_inferred=False,
        )
    expected_cases = {(scenario, threshold) for scenario in ("low", "base", "high")
                      for threshold in ("0.5", "0.6", "0.7")}
    cases = [(r.get("scenario_name"), r.get("proxy_threshold")) for r in selected]
    if len(cases) != len(set(cases)) or set(cases) != expected_cases:
        raise PorePressureInputError(
            "Locked strict-no-gap NCT sensitivity must contain exactly nine unique cases.")
    thickness = [
        _locked_float_token(
            r, "gross_qualifying_thickness_tvdss_m",
            "Locked thickness-sensitivity row")
        for r in selected
    ]
    if any(not math.isfinite(v) or v <= 0.0 for v in thickness):
        raise PorePressureInputError("Locked qualifying thickness must be finite and > 0.")
    lo, hi = min(thickness), max(thickness)
    return NctReadiness(
        well_key=well_key,
        status="WITHHELD_NO_PRESSURE_CALIBRATION_OR_INDEPENDENT_NORMAL_INTERVAL",
        candidate_configurations=len(selected),
        qualifying_thickness_min_tvd_m=lo,
        qualifying_thickness_max_tvd_m=hi,
        thickness_sensitivity_factor=hi / lo,
        pressure_calibration_available=False,
        independent_normal_interval_evidence_available=False,
        nct_fit_performed=False, overpressure_inferred=False,
    )


def build_hydrostatic_nodes(profile_rows: Sequence[Mapping[str, str]],
                            config: PressureConfig) -> Tuple[HydrostaticReferenceNode, ...]:
    """Build low/base/high hydrostatic references at locked profile nodes."""
    densities = (
        ("low", config.fluid_density_low_kg_m3),
        ("base", config.fluid_density_base_kg_m3),
        ("high", config.fluid_density_high_kg_m3),
    )
    out = []
    seen = set()
    last_by_well = {}
    for row in profile_rows:
        try:
            wk = row["well_key"]
        except (KeyError, TypeError) as exc:
            raise PorePressureInputError(
                "Locked vertical-stress profile row has no well key.") from exc
        if not isinstance(wk, str):
            raise PorePressureInputError(
                "Locked vertical-stress profile well key must be a string.")
        idx = _locked_int_token(
            row, "node_index", "Locked vertical-stress profile row")
        z = _locked_float_token(
            row, "tvdss_m", "Locked vertical-stress profile row")
        key = (wk, idx)
        if key in seen:
            raise PorePressureInputError("Locked profile contains a duplicate well/node index.")
        seen.add(key)
        previous = last_by_well.get(wk)
        if previous is None:
            if idx != 0:
                raise PorePressureInputError("Locked profile node index must begin at zero.")
        elif idx != previous[0] + 1 or z <= previous[1]:
            raise PorePressureInputError(
                "Locked profile indices must be contiguous and TVDSS strictly increasing.")
        last_by_well[wk] = (idx, z)
        for scenario, rho in densities:
            p = hydrostatic_reference_pressure_pa(z, rho, config.gravity_m_s2)
            out.append(HydrostaticReferenceNode(
                well_key=wk, node_index=idx, fluid_scenario=scenario,
                tvdss_m=z, fluid_density_kg_m3=rho,
                gravity_m_s2=config.gravity_m_s2, pressure_pa=p,
            ))
    return tuple(out)


def make_effective_scenario(*, well_key: str, sv_scenario: str,
                            fluid_scenario: str, biot_alpha: float,
                            evaluation_tvdss_m: float,
                            total_vertical_stress_pa: float,
                            fluid_density_kg_m3: float,
                            gravity_m_s2: float) -> EffectiveStressScenario:
    pp = hydrostatic_reference_pressure_pa(
        evaluation_tvdss_m, fluid_density_kg_m3, gravity_m_s2)
    eff = effective_vertical_stress_pa(total_vertical_stress_pa, pp, biot_alpha)
    return EffectiveStressScenario(
        well_key=well_key, sv_scenario=sv_scenario,
        fluid_scenario=fluid_scenario, biot_alpha=biot_alpha,
        evaluation_tvdss_m=evaluation_tvdss_m,
        total_vertical_stress_pa=total_vertical_stress_pa,
        pore_pressure_reference_pa=pp,
        effective_vertical_stress_pa=eff,
        effective_stress_nonnegative=eff >= 0.0,
    )


def scenario_initial_stress_pa(total_stress_pa, measured_only_stress_pa,
                               bridged_stress_pa) -> float:
    """Return the scenario stress above the first profile node.

    Increment 7's cumulative profile contains measured plus conditioned
    (bridged) density. Both components must therefore be removed from the
    terminal total before that cumulative profile is added back node by node.
    """
    from p2mem.pore_pressure_models import finite_real
    total = finite_real(total_stress_pa, "total_stress_pa", minimum=0.0)
    measured = finite_real(measured_only_stress_pa, "measured_only_stress_pa", minimum=0.0)
    bridged = finite_real(bridged_stress_pa, "bridged_stress_pa", minimum=0.0)
    initial = total - measured - bridged
    if initial < 0.0:
        raise PorePressureInputError("Scenario components exceed total stress.")
    return initial
