"""Deterministic Increment 8 inventory builders and transactional export."""

from dataclasses import asdict
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import uuid
from typing import Dict, Iterable, Mapping, Sequence, Tuple

from p2mem.pore_pressure import (
    build_hydrostatic_nodes, build_pressure_data_inventory,
    derive_nct_readiness, hydrostatic_reference_pressure_pa,
    make_effective_scenario, scenario_initial_stress_pa,
)
from p2mem.pore_pressure_models import (
    APPROVED_BIOT_ALPHA_SCENARIOS, APPROVED_FLUID_DENSITIES_KG_M3,
    APPROVED_GRAVITY_M_S2, APPROVED_PROFILE_BIOT_ALPHA,
    APPROVED_PROFILE_FLUID_DENSITY_KG_M3, ASSURANCE_TIER, PACKAGE_VERSION,
    PRESSURE_DATA_TYPES, SV_SCENARIOS, WELL_KEYS,
    EffectiveStressScenario, HydrostaticReferenceNode, NctReadiness,
    PorePressureInputError, PressureConfig, PressureDataAvailability,
)


OUTPUT_NAMES = (
    "pressure_data_inventory.csv",
    "nct_readiness_summary.csv",
    "hydrostatic_reference_profile.csv",
    "effective_stress_scenarios.csv",
    "effective_stress_profile.csv",
    "pore_pressure_issues.csv",
    "pore_pressure_manifest.json",
)

LOCKED_SOURCE_NAMES = (
    "vertical_stress_profile.csv", "shallow_column_scenarios.csv",
    "overburden_eligibility_summary.csv", "method_eligibility_summary.csv",
    "thickness_sensitivity_summary.csv", "petrophysics_eligibility_manifest.json",
    "sonic_checkshot_drift_summary.csv",
)

# These hashes identify the exact approved Increment 6.1.7 / 7.0.4 artifacts.
# A syntactically valid but altered upstream file is not a locked source.
EXPECTED_LOCKED_SOURCE_SHA256 = {
    "vertical_stress_profile.csv":
        "bfe2bd37d31793285f06db34fda6e3e715dd8f085a6685620bca08167941ad52",
    "shallow_column_scenarios.csv":
        "356a5e83bca131ed1046c83d0c27d5624bafe8b2510cdff8a500871514aca7a8",
    "overburden_eligibility_summary.csv":
        "8bd03850d1ea8a58b620810f65af18c1d4115b3cd385c542949d7ba22e45cf12",
    "method_eligibility_summary.csv":
        "7fa715459de2eaa2007cdffe1af30a9c3eb424c78650f618ba34738d9a5c64b9",
    "thickness_sensitivity_summary.csv":
        "0c953df792a474960760e4bc491a05e2ffa448a8909589accadc14c78f2aec3e",
    "petrophysics_eligibility_manifest.json":
        "00e05aaa35454aef62bb7541adfbccca5a348ff8ccb2ecbc26b9a8093877a58e",
    "sonic_checkshot_drift_summary.csv":
        "17c84fcf9c9c320d9de665023d5d19ab6c5112bdf0d408378a289c9250886874",
}

FIGURE_NAMES = (
    "fig01_hydrostatic_reference_profile.png",
    "fig02_nct_readiness_and_sensitivity.png",
    "fig03_terminal_effective_stress_scenarios.png",
    "fig04_pressure_calibration_data_gap.png",
)

SHALLOW_SCENARIOS = (
    "low", "base", "high", "base_seawater_low", "base_seawater_high",
)

EFFECTIVE_STRESS_WELLS = ("Boreas_1", "Poseidon_2")
PROFILE_NODE_COUNTS = {
    "Boreas_1": 80,
    "Poseidon_2": 122,
    "Poseidon_North_1": 116,
    "Proteus_1ST2": 33,
}
EXPECTED_ROW_COUNTS = {
    "pressure_data_inventory.csv": 4,
    "nct_readiness_summary.csv": 4,
    "hydrostatic_reference_profile.csv": 1053,
    "effective_stress_scenarios.csv": 36,
    "effective_stress_profile.csv": 606,
    "pore_pressure_issues.csv": 11,
}
FLUID_DENSITY_BY_SCENARIO = dict(
    zip(("low", "base", "high"), APPROVED_FLUID_DENSITIES_KG_M3))

MANIFEST_TITLE = "Pore-Pressure Data-Gap, Hydrostatic Reference, and Effective-Stress Screening Framework"
MANIFEST_LIMITATIONS = (
    "Hydrostatic values use one configured constant-density gradient from mean sea level; they are references, not measured formation pressures or a separately modelled seawater-plus-formation-fluid column.",
    "Vertical-stress inputs are Increment 7 screening scenarios, not calibrated absolute stress measurements.",
    "Biot coefficients are configured sensitivity values; no laboratory measurement is available.",
    "Candidate sonic intervals do not establish normal compaction; no NCT was selected or fitted.",
    "No overpressure transform was run and no overpressure is inferred.",
    "No value is extrapolated beyond a locked source profile node.",
    "The zero-count pressure-data inventory describes approved packaged project inputs; it does not prove that no unprovided field data exist.",
)

CSV_COLUMNS = {
    "pressure_data_inventory.csv": (
        "well_key", "rft_count", "mdt_count", "dst_count", "fit_count",
        "lot_count", "xlot_count", "dfit_count", "availability_status",
        "evidence_class", "calibration_status", "assurance_tier",
    ),
    "nct_readiness_summary.csv": (
        "well_key", "status", "candidate_configurations",
        "qualifying_thickness_min_tvd_m", "qualifying_thickness_max_tvd_m",
        "thickness_sensitivity_factor", "pressure_calibration_available",
        "independent_normal_interval_evidence_available", "nct_fit_performed",
        "overpressure_inferred", "evidence_class", "calibration_status",
        "assurance_tier",
    ),
    "hydrostatic_reference_profile.csv": (
        "well_key", "node_index", "fluid_scenario", "tvdss_m",
        "fluid_density_kg_m3", "gravity_m_s2", "pressure_pa", "pressure_mpa",
        "pressure_basis", "evidence_class", "calibration_status", "assurance_tier",
    ),
    "effective_stress_scenarios.csv": (
        "well_key", "sv_scenario", "fluid_scenario", "biot_alpha",
        "evaluation_tvdss_m", "total_vertical_stress_pa",
        "total_vertical_stress_mpa", "pore_pressure_reference_pa",
        "pore_pressure_reference_mpa", "effective_vertical_stress_pa",
        "effective_vertical_stress_mpa", "effective_stress_nonnegative",
        "equation", "evidence_class", "calibration_status", "assurance_tier",
    ),
    "effective_stress_profile.csv": (
        "well_key", "node_index", "sv_scenario", "tvdss_m", "biot_alpha",
        "fluid_density_kg_m3", "total_vertical_stress_pa",
        "pore_pressure_reference_pa", "effective_vertical_stress_pa",
        "total_vertical_stress_mpa", "pore_pressure_reference_mpa",
        "effective_vertical_stress_mpa", "effective_stress_nonnegative",
        "evidence_class", "calibration_status", "assurance_tier",
    ),
    "pore_pressure_issues.csv": (
        "well_key", "severity", "issue_code", "measured_value", "unit",
        "disposition", "assurance_tier",
    ),
}

CSV_INTEGER_FIELDS = {
    "pressure_data_inventory.csv": {
        "rft_count", "mdt_count", "dst_count", "fit_count", "lot_count",
        "xlot_count", "dfit_count",
    },
    "nct_readiness_summary.csv": {"candidate_configurations"},
    "hydrostatic_reference_profile.csv": {"node_index"},
    "effective_stress_scenarios.csv": set(),
    "effective_stress_profile.csv": {"node_index"},
    "pore_pressure_issues.csv": set(),
}

CSV_NUMERIC_FIELDS = {
    "pressure_data_inventory.csv": set(),
    "nct_readiness_summary.csv": {
        "qualifying_thickness_min_tvd_m", "qualifying_thickness_max_tvd_m",
        "thickness_sensitivity_factor",
    },
    "hydrostatic_reference_profile.csv": {
        "tvdss_m", "fluid_density_kg_m3", "gravity_m_s2", "pressure_pa", "pressure_mpa",
    },
    "effective_stress_scenarios.csv": {
        "biot_alpha", "evaluation_tvdss_m", "total_vertical_stress_pa",
        "total_vertical_stress_mpa", "pore_pressure_reference_pa",
        "pore_pressure_reference_mpa", "effective_vertical_stress_pa",
        "effective_vertical_stress_mpa",
    },
    "effective_stress_profile.csv": {
        "tvdss_m", "biot_alpha", "fluid_density_kg_m3",
        "total_vertical_stress_pa", "pore_pressure_reference_pa",
        "effective_vertical_stress_pa", "total_vertical_stress_mpa",
        "pore_pressure_reference_mpa", "effective_vertical_stress_mpa",
    },
    "pore_pressure_issues.csv": {"measured_value"},
}

ALLOWED_STRING_VALUES = {
    ("pressure_data_inventory.csv", "well_key"): set(WELL_KEYS),
    ("pressure_data_inventory.csv", "availability_status"): {"NOT_AVAILABLE"},
    ("pressure_data_inventory.csv", "evidence_class"): {
        "factual_approved_input_absence_inventory"},
    ("pressure_data_inventory.csv", "calibration_status"): {
        "uncalibrated_no_approved_pressure_measurements"},
    ("nct_readiness_summary.csv", "well_key"): set(WELL_KEYS),
    ("nct_readiness_summary.csv", "status"): {
        "NOT_ELIGIBLE_INPUT_QC_EXCLUSION",
        "WITHHELD_NO_PRESSURE_CALIBRATION_OR_INDEPENDENT_NORMAL_INTERVAL",
    },
    ("nct_readiness_summary.csv", "pressure_calibration_available"): {"false"},
    ("nct_readiness_summary.csv", "independent_normal_interval_evidence_available"): {"false"},
    ("nct_readiness_summary.csv", "nct_fit_performed"): {"false"},
    ("nct_readiness_summary.csv", "overpressure_inferred"): {"false"},
    ("nct_readiness_summary.csv", "evidence_class"): {"eligibility_derived_not_prediction"},
    ("nct_readiness_summary.csv", "calibration_status"): {"uncalibrated_fit_withheld"},
    ("hydrostatic_reference_profile.csv", "well_key"): set(WELL_KEYS),
    ("hydrostatic_reference_profile.csv", "fluid_scenario"): {"low", "base", "high"},
    ("hydrostatic_reference_profile.csv", "pressure_basis"): {"configured_hydrostatic_reference_from_msl"},
    ("hydrostatic_reference_profile.csv", "evidence_class"): {"assumed_reference_not_measurement"},
    ("hydrostatic_reference_profile.csv", "calibration_status"): {"uncalibrated_reference_only"},
    ("effective_stress_scenarios.csv", "well_key"): {"Boreas_1", "Poseidon_2"},
    ("effective_stress_scenarios.csv", "sv_scenario"): {"low", "base", "high"},
    ("effective_stress_scenarios.csv", "fluid_scenario"): {"low", "base", "high"},
    ("effective_stress_scenarios.csv", "effective_stress_nonnegative"): {"true", "false"},
    ("effective_stress_scenarios.csv", "equation"): {
        "sigma_v_effective_equals_sigma_v_total_minus_alpha_times_pressure"},
    ("effective_stress_scenarios.csv", "evidence_class"): {"derived_screening_scenario"},
    ("effective_stress_scenarios.csv", "calibration_status"): {"uncalibrated_sensitivity_only"},
    ("effective_stress_profile.csv", "well_key"): {"Boreas_1", "Poseidon_2"},
    ("effective_stress_profile.csv", "sv_scenario"): {"low", "base", "high"},
    ("effective_stress_profile.csv", "effective_stress_nonnegative"): {"true", "false"},
    ("effective_stress_profile.csv", "evidence_class"): {"derived_screening_scenario"},
    ("effective_stress_profile.csv", "calibration_status"): {"uncalibrated_sensitivity_only"},
    ("pore_pressure_issues.csv", "well_key"): set(WELL_KEYS),
    ("pore_pressure_issues.csv", "severity"): {"WARNING"},
    ("pore_pressure_issues.csv", "issue_code"): {
        "PRESSURE_CALIBRATION_NOT_AVAILABLE", "NCT_AND_OVERPRESSURE_MODEL_NOT_RUN",
        "ABSOLUTE_VERTICAL_STRESS_SCENARIO_NOT_AVAILABLE",
        "SONIC_CHECKSHOT_DRIFT_DIAGNOSTIC_UNCORRECTED",
    },
    ("pore_pressure_issues.csv", "unit"): {"approved_files", "not_applicable", "percent"},
    ("pore_pressure_issues.csv", "disposition"): {
        "prediction_withheld", "effective_stress_not_computed",
        "diagnostic_only_no_curve_correction",
    },
}
for _artifact in CSV_COLUMNS:
    ALLOWED_STRING_VALUES[(_artifact, "assurance_tier")] = {ASSURANCE_TIER}


REQUIRED_LOCKED_COLUMNS = {
    "vertical_stress_profile.csv": (
        "well_key", "node_index", "tvdss_m", "cumulative_measured_increment_pa",
    ),
    "shallow_column_scenarios.csv": (
        "well_key", "scenario_name", "measured_formation_stress_pa",
        "bridged_gap_stress_pa", "water_column_stress_pa",
        "unresolved_shallow_stress_pa", "total_stress_pa",
    ),
    "overburden_eligibility_summary.csv": (
        "well_key", "overburden_status", "absolute_stress_supported",
    ),
    "method_eligibility_summary.csv": (
        "well_key", "mask_name", "use_status", "n_eligible",
    ),
    "thickness_sensitivity_summary.csv": (
        "well_key", "mask_name", "contiguity_policy", "scenario_name",
        "proxy_threshold", "gross_qualifying_thickness_tvdss_m",
    ),
    "sonic_checkshot_drift_summary.csv": (
        "well_key", "sonic_transit_time_s", "checkshot_owt_increment_s",
        "sonic_minus_checkshot_ms", "checkshot_minus_sonic_ms",
        "sonic_minus_checkshot_percent",
    ),
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_locked_csv(path) -> Tuple[dict, ...]:
    """Read a locked CSV fail-closed: exact header uniqueness and row width."""
    p = Path(path)
    if not p.is_file():
        raise PorePressureInputError(f"Locked input is missing: {p.name!r}.")
    with p.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        if not fields or len(fields) != len(set(fields)):
            raise PorePressureInputError(f"Locked input has invalid header: {p.name!r}.")
        required = REQUIRED_LOCKED_COLUMNS.get(p.name, ())
        missing = [name for name in required if name not in fields]
        if missing:
            raise PorePressureInputError(
                f"Locked input {p.name!r} is missing required columns: {missing!r}.")
        rows = []
        for number, row in enumerate(reader, start=2):
            if None in row or any(v is None for v in row.values()):
                raise PorePressureInputError(
                    f"Locked input {p.name!r} row {number} has wrong width.")
            rows.append(dict(row))
    if not rows:
        raise PorePressureInputError(f"Locked input is empty: {p.name!r}.")
    return tuple(rows)


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _clean_record(record: Mapping[str, object]) -> dict:
    out = {}
    for key, value in record.items():
        if value is None:
            out[key] = ""
        elif type(value) is bool:
            out[key] = _bool_text(value)
        else:
            out[key] = value
    return out


def _csv_float(row: Mapping[str, str], field: str, context: str,
               *, minimum=None) -> float:
    """Parse one required CSV scalar without accepting blanks or non-finite values."""
    try:
        token = row[field]
        if not isinstance(token, str) or not token.strip():
            raise ValueError("required non-empty string token")
        value = float(token)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise PorePressureInputError(
            f"{context}: {field!r} must be a finite numeric token.") from exc
    if not math.isfinite(value) or (minimum is not None and value < minimum):
        raise PorePressureInputError(
            f"{context}: {field!r} is outside its finite numeric domain.")
    return value


def _csv_int(row: Mapping[str, str], field: str, context: str,
             *, minimum=0) -> int:
    """Parse one required canonical non-negative integer CSV token."""
    try:
        token = row[field]
        if not isinstance(token, str) or not token.isdigit():
            raise ValueError("canonical integer token required")
        value = int(token)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise PorePressureInputError(
            f"{context}: {field!r} must be a canonical integer token.") from exc
    if value < minimum:
        raise PorePressureInputError(
            f"{context}: {field!r} must be >= {minimum}.")
    return value


def _validate_source_hashes(source_hashes: Mapping[str, str]) -> None:
    if not isinstance(source_hashes, Mapping):
        raise PorePressureInputError("Source-artifact hash inventory is not a mapping.")
    if dict(source_hashes) != EXPECTED_LOCKED_SOURCE_SHA256:
        raise PorePressureInputError(
            "Source-artifact hashes do not match the exact approved locked inputs.")


def build_payloads(*, config: PressureConfig,
                   profile_rows: Sequence[Mapping[str, str]],
                   shallow_rows: Sequence[Mapping[str, str]],
                   overburden_rows: Sequence[Mapping[str, str]],
                   method_rows: Sequence[Mapping[str, str]],
                   thickness_rows: Sequence[Mapping[str, str]],
                   drift_rows: Sequence[Mapping[str, str]],
                   source_hashes: Mapping[str, str]) -> Dict[str, object]:
    """Build the complete deterministic Increment 8 payload set."""
    if (not isinstance(source_hashes, Mapping)
            or set(source_hashes) != set(LOCKED_SOURCE_NAMES) or any(
            not isinstance(value, str) or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
             for value in source_hashes.values())):
        raise PorePressureInputError("Source-artifact hash inventory is not exact.")
    method_candidate_wells = set()
    for row in method_rows:
        if row.get("mask_name") != "eligible_sonic_nct_candidate":
            continue
        try:
            eligible = _csv_int(
                row, "n_eligible", "Locked method-eligibility row")
        except PorePressureInputError:
            raise
        if eligible > 0:
            method_candidate_wells.add(row.get("well_key"))
    thickness_candidate_wells = {
        row.get("well_key") for row in thickness_rows
        if row.get("mask_name") == "eligible_sonic_nct_candidate"
        and row.get("contiguity_policy") == "strict_no_gap"
    }
    if method_candidate_wells != thickness_candidate_wells:
        raise PorePressureInputError(
            "Locked method eligibility and thickness sensitivity disagree on candidate wells.")
    if not method_candidate_wells.issubset(WELL_KEYS):
        raise PorePressureInputError("Locked candidate data contain an unknown well key.")

    inventory = build_pressure_data_inventory(WELL_KEYS)
    readiness = tuple(derive_nct_readiness(wk, thickness_rows) for wk in WELL_KEYS)
    hydro = build_hydrostatic_nodes(profile_rows, config)

    availability_rows = []
    for rec in inventory:
        row = asdict(rec)
        row.update(evidence_class="factual_approved_input_absence_inventory",
                   calibration_status="uncalibrated_no_approved_pressure_measurements",
                   assurance_tier=ASSURANCE_TIER)
        availability_rows.append(_clean_record(row))

    readiness_rows = []
    for rec in readiness:
        row = asdict(rec)
        row.update(evidence_class="eligibility_derived_not_prediction",
                   calibration_status="uncalibrated_fit_withheld",
                   assurance_tier=ASSURANCE_TIER)
        readiness_rows.append(_clean_record(row))

    hydro_rows = []
    for rec in hydro:
        row = asdict(rec)
        row.update(
            pressure_mpa=rec.pressure_pa / 1e6,
            pressure_basis="configured_hydrostatic_reference_from_msl",
            evidence_class="assumed_reference_not_measurement",
            calibration_status="uncalibrated_reference_only",
            assurance_tier=ASSURANCE_TIER,
        )
        hydro_rows.append(_clean_record(row))

    by_profile: Dict[str, list] = {wk: [] for wk in WELL_KEYS}
    for row in profile_rows:
        if row.get("well_key") not in by_profile:
            raise PorePressureInputError("Locked vertical-stress profile contains an unknown well.")
        by_profile[row["well_key"]].append(row)
    for wk in by_profile:
        by_profile[wk].sort(
            key=lambda r: _csv_int(r, "node_index", "Locked vertical-stress profile"))
        cumulative_values = [
            _csv_float(r, "cumulative_measured_increment_pa",
                       "Locked vertical-stress profile", minimum=0.0)
            for r in by_profile[wk]
        ]
        if cumulative_values and not math.isclose(
                cumulative_values[0], 0.0, rel_tol=0.0, abs_tol=1e-12):
            raise PorePressureInputError(
                "Locked vertical-stress cumulative profile must begin at zero.")
        if any(b < a for a, b in zip(cumulative_values, cumulative_values[1:])):
            raise PorePressureInputError(
                "Locked vertical-stress cumulative profile must be non-decreasing.")
    if any(not rows for rows in by_profile.values()):
        raise PorePressureInputError("Locked vertical-stress profile is missing a well.")

    base_shallow = {}
    shallow_seen = set()
    for row in shallow_rows:
        wk, scenario = row.get("well_key"), row.get("scenario_name")
        if wk not in WELL_KEYS or scenario not in SHALLOW_SCENARIOS:
            raise PorePressureInputError(
                "Locked shallow-scenario inventory has an unknown well or scenario.")
        key = (wk, scenario)
        if key in shallow_seen:
            raise PorePressureInputError(f"Duplicate shallow scenario {key!r}.")
        shallow_seen.add(key)
        components = tuple(_csv_float(
            row, field, "Locked shallow-scenario row", minimum=0.0)
            for field in (
                "water_column_stress_pa", "unresolved_shallow_stress_pa",
                "measured_formation_stress_pa", "bridged_gap_stress_pa",
            ))
        total = _csv_float(
            row, "total_stress_pa", "Locked shallow-scenario row", minimum=0.0)
        if not math.isclose(total, sum(components), rel_tol=1e-12, abs_tol=1e-5):
            raise PorePressureInputError(
                "Locked shallow-scenario stress components do not sum to total stress.")
        if scenario in SV_SCENARIOS:
            base_shallow[key] = row

    terminal_records = []
    profile_out = []
    density_scenarios = (
        ("low", config.fluid_density_low_kg_m3),
        ("base", config.fluid_density_base_kg_m3),
        ("high", config.fluid_density_high_kg_m3),
    )
    for wk in WELL_KEYS:
        rows = by_profile[wk]
        has_all = all((wk, s) in base_shallow for s in SV_SCENARIOS)
        if not rows or not has_all:
            continue
        terminal = rows[-1]
        z_terminal = _csv_float(
            terminal, "tvdss_m", "Locked terminal profile", minimum=0.0)
        cumulative_terminal = _csv_float(
            terminal, "cumulative_measured_increment_pa",
            "Locked terminal profile", minimum=0.0)
        for sv_scenario in SV_SCENARIOS:
            source = base_shallow[(wk, sv_scenario)]
            measured = _csv_float(
                source, "measured_formation_stress_pa",
                "Locked shallow-scenario row", minimum=0.0)
            bridged = _csv_float(
                source, "bridged_gap_stress_pa",
                "Locked shallow-scenario row", minimum=0.0)
            total = _csv_float(
                source, "total_stress_pa", "Locked shallow-scenario row", minimum=0.0)
            if not math.isclose(cumulative_terminal, measured + bridged,
                                rel_tol=1e-10, abs_tol=1e-5):
                raise PorePressureInputError(
                    f"Locked terminal profile and scenario disagree for {wk!r}.")
            for fluid_scenario, rho in density_scenarios:
                for alpha in config.biot_alpha_scenarios:
                    rec = make_effective_scenario(
                        well_key=wk, sv_scenario=sv_scenario,
                        fluid_scenario=fluid_scenario, biot_alpha=alpha,
                        evaluation_tvdss_m=z_terminal,
                        total_vertical_stress_pa=total,
                        fluid_density_kg_m3=rho,
                        gravity_m_s2=config.gravity_m_s2,
                    )
                    row = asdict(rec)
                    row.update(
                        total_vertical_stress_mpa=rec.total_vertical_stress_pa / 1e6,
                        pore_pressure_reference_mpa=rec.pore_pressure_reference_pa / 1e6,
                        effective_vertical_stress_mpa=rec.effective_vertical_stress_pa / 1e6,
                        equation="sigma_v_effective_equals_sigma_v_total_minus_alpha_times_pressure",
                        evidence_class="derived_screening_scenario",
                        calibration_status="uncalibrated_sensitivity_only",
                        assurance_tier=ASSURANCE_TIER,
                    )
                    terminal_records.append(_clean_record(row))

            initial = scenario_initial_stress_pa(total, measured, bridged)
            for node in rows:
                idx = _csv_int(node, "node_index", "Locked vertical-stress profile")
                z = _csv_float(
                    node, "tvdss_m", "Locked vertical-stress profile", minimum=0.0)
                cumulative = _csv_float(
                    node, "cumulative_measured_increment_pa",
                    "Locked vertical-stress profile", minimum=0.0)
                sv = initial + cumulative
                pp = hydrostatic_reference_pressure_pa(
                    z, config.profile_fluid_density_kg_m3, config.gravity_m_s2)
                eff = sv - config.profile_biot_alpha * pp
                profile_out.append(_clean_record({
                    "well_key": wk, "node_index": idx, "sv_scenario": sv_scenario,
                    "tvdss_m": z, "biot_alpha": config.profile_biot_alpha,
                    "fluid_density_kg_m3": config.profile_fluid_density_kg_m3,
                    "total_vertical_stress_pa": sv,
                    "pore_pressure_reference_pa": pp,
                    "effective_vertical_stress_pa": eff,
                    "total_vertical_stress_mpa": sv / 1e6,
                    "pore_pressure_reference_mpa": pp / 1e6,
                    "effective_vertical_stress_mpa": eff / 1e6,
                    "effective_stress_nonnegative": eff >= 0.0,
                    "evidence_class": "derived_screening_scenario",
                    "calibration_status": "uncalibrated_sensitivity_only",
                    "assurance_tier": ASSURANCE_TIER,
                }))

    overburden_status = {}
    for row in overburden_rows:
        wk = row.get("well_key")
        if wk not in WELL_KEYS or wk in overburden_status:
            raise PorePressureInputError("Locked overburden inventory has an unknown or duplicate well.")
        if row.get("absolute_stress_supported") not in ("False", "false"):
            raise PorePressureInputError(
                "Increment 8 expects no well to support measured absolute vertical stress.")
        status = row.get("overburden_status")
        if status not in {"screening_sensitivity_only", "partial_measured_increment_only", "not_eligible"}:
            raise PorePressureInputError("Locked overburden status is outside the closed vocabulary.")
        overburden_status[wk] = status
    if set(overburden_status) != set(WELL_KEYS):
        raise PorePressureInputError("Locked overburden inventory is incomplete.")
    for wk, status in overburden_status.items():
        expected_scenarios = (set(SHALLOW_SCENARIOS)
                              if status == "screening_sensitivity_only" else set())
        observed_scenarios = {scenario for well, scenario in shallow_seen if well == wk}
        if observed_scenarios != expected_scenarios:
            raise PorePressureInputError(
                "Locked overburden status and exact shallow-scenario inventory disagree.")
        has_scenarios = all((wk, s) in base_shallow for s in SV_SCENARIOS)
        if has_scenarios != (status == "screening_sensitivity_only"):
            raise PorePressureInputError(
                "Locked overburden status and shallow-scenario availability disagree.")
    issues = []
    for wk in WELL_KEYS:
        issues.extend((
            {"well_key": wk, "severity": "WARNING",
             "issue_code": "PRESSURE_CALIBRATION_NOT_AVAILABLE",
             "measured_value": 0, "unit": "approved_files",
             "disposition": "prediction_withheld", "assurance_tier": ASSURANCE_TIER},
            {"well_key": wk, "severity": "WARNING",
             "issue_code": "NCT_AND_OVERPRESSURE_MODEL_NOT_RUN",
             "measured_value": "", "unit": "not_applicable",
             "disposition": "prediction_withheld", "assurance_tier": ASSURANCE_TIER},
        ))
        if overburden_status.get(wk) != "screening_sensitivity_only":
            issues.append({"well_key": wk, "severity": "WARNING",
                           "issue_code": "ABSOLUTE_VERTICAL_STRESS_SCENARIO_NOT_AVAILABLE",
                           "measured_value": "", "unit": "not_applicable",
                           "disposition": "effective_stress_not_computed",
                           "assurance_tier": ASSURANCE_TIER})
    poseidon_drift = [row for row in drift_rows if row.get("well_key") == "Poseidon_2"]
    if len(poseidon_drift) != 1 or len(drift_rows) != 1:
        raise PorePressureInputError("Locked sonic-checkshot drift inventory must contain one Poseidon 2 row.")
    for row in poseidon_drift:
        sonic_s = _csv_float(
            row, "sonic_transit_time_s", "Locked sonic-checkshot drift", minimum=0.0)
        checkshot_s = _csv_float(
            row, "checkshot_owt_increment_s", "Locked sonic-checkshot drift", minimum=0.0)
        drift_ms = _csv_float(
            row, "sonic_minus_checkshot_ms", "Locked sonic-checkshot drift")
        reverse_ms = _csv_float(
            row, "checkshot_minus_sonic_ms", "Locked sonic-checkshot drift")
        drift_percent = _csv_float(
            row, "sonic_minus_checkshot_percent", "Locked sonic-checkshot drift")
        if sonic_s <= 0.0 or checkshot_s <= 0.0:
            raise PorePressureInputError(
                "Locked sonic and checkshot transit times must be positive.")
        if (not math.isclose(drift_ms, (sonic_s - checkshot_s) * 1000.0,
                             rel_tol=1e-12, abs_tol=1e-12)
                or not math.isclose(reverse_ms, -drift_ms,
                                    rel_tol=1e-12, abs_tol=1e-12)
                or not math.isclose(
                    drift_percent, (sonic_s - checkshot_s) / checkshot_s * 100.0,
                    rel_tol=1e-12, abs_tol=1e-12)):
            raise PorePressureInputError(
                "Locked sonic-checkshot drift identities are inconsistent.")
        if row.get("well_key") == "Poseidon_2":
            issues.append({"well_key": "Poseidon_2", "severity": "WARNING",
                           "issue_code": "SONIC_CHECKSHOT_DRIFT_DIAGNOSTIC_UNCORRECTED",
                           "measured_value": drift_percent,
                           "unit": "percent",
                           "disposition": "diagnostic_only_no_curve_correction",
                           "assurance_tier": ASSURANCE_TIER})

    raw_csv = {
        "pressure_data_inventory.csv": availability_rows,
        "nct_readiness_summary.csv": readiness_rows,
        "hydrostatic_reference_profile.csv": hydro_rows,
        "effective_stress_scenarios.csv": terminal_records,
        "effective_stress_profile.csv": profile_out,
        "pore_pressure_issues.csv": issues,
    }
    ordered_csv = {}
    for name, rows in raw_csv.items():
        columns = CSV_COLUMNS[name]
        ordered = []
        for index, row in enumerate(rows):
            if set(row) != set(columns):
                raise PorePressureInputError(
                    f"{name} row {index} has unknown or missing fields.")
            ordered.append({column: row[column] for column in columns})
        ordered_csv[name] = ordered

    row_counts = {
        name: len(rows) for name, rows in ordered_csv.items()
    }
    _validate_source_hashes(source_hashes)
    manifest = {
        "package_version": PACKAGE_VERSION,
        "increment": 8,
        "increment_title": MANIFEST_TITLE,
        "assurance_tier": ASSURANCE_TIER,
        "source_artifact_sha256": dict(sorted(source_hashes.items())),
        "row_counts": row_counts,
        "pressure_calibration": {
            "approved_file_count": 0,
            "required_types": list(config.pressure_calibration_types),
            "cross_well_transfer_performed": False,
        },
        "prediction_gate": {
            "nct_fit_performed": False,
            "overpressure_transform_performed": False,
            "overpressure_inferred": False,
            "extrapolated_samples": 0,
        },
        "hydrostatic_reference": {
            "pressure_datum": "mean_sea_level_gauge_zero",
            "equation": "pressure_pa = fluid_density_kg_m3 * gravity_m_s2 * tvdss_m",
            "fluid_density_scenarios_kg_m3": [
                config.fluid_density_low_kg_m3,
                config.fluid_density_base_kg_m3,
                config.fluid_density_high_kg_m3,
            ],
            "status": "configured_reference_not_measured_formation_pressure",
        },
        "effective_stress": {
            "equation": "sigma_v_effective_pa = sigma_v_total_pa - biot_alpha * pore_pressure_pa",
            "biot_alpha_scenarios": list(config.biot_alpha_scenarios),
            "wells_with_scenarios": sorted({r["well_key"] for r in terminal_records}),
            "negative_values_clipped": 0,
        },
        "nct_readiness": [asdict(r) for r in readiness],
        "limitations": list(MANIFEST_LIMITATIONS),
        "increment_9_started": False,
    }
    return {
        **ordered_csv,
        "pore_pressure_manifest.json": manifest,
    }


def validate_payloads(payloads: Mapping[str, object]) -> None:
    if tuple(payloads) != OUTPUT_NAMES:
        raise PorePressureInputError("Increment 8 output inventory is not exact.")
    for name, columns in CSV_COLUMNS.items():
        rows = payloads[name]
        if not isinstance(rows, list):
            raise PorePressureInputError(f"{name} payload must be a list.")
        for index, row in enumerate(rows):
            if tuple(row) != columns:
                raise PorePressureInputError(
                    f"{name} row {index} has unknown, missing, or misordered fields.")
            for field, value in row.items():
                if field in CSV_INTEGER_FIELDS[name]:
                    if isinstance(value, bool) or not isinstance(value, int):
                        raise PorePressureInputError(f"{name}:{field} must be a strict integer.")
                    if value < 0:
                        raise PorePressureInputError(f"{name}:{field} must be non-negative.")
                elif field in CSV_NUMERIC_FIELDS[name]:
                    if value == "" and name in {"nct_readiness_summary.csv", "pore_pressure_issues.csv"}:
                        continue
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        raise PorePressureInputError(f"{name}:{field} must be numeric.")
                    if not math.isfinite(float(value)):
                        raise PorePressureInputError(f"{name}:{field} must be finite.")
                else:
                    if not isinstance(value, str):
                        raise PorePressureInputError(f"{name}:{field} must be a string.")
                    allowed = ALLOWED_STRING_VALUES.get((name, field))
                    if allowed is None or value not in allowed:
                        raise PorePressureInputError(
                            f"{name}:{field} contains an unauthorized value.")
    manifest = payloads["pore_pressure_manifest.json"]
    expected_top = {
        "package_version", "increment", "increment_title", "assurance_tier",
        "source_artifact_sha256", "row_counts", "pressure_calibration",
        "prediction_gate", "hydrostatic_reference", "effective_stress",
        "nct_readiness", "limitations", "increment_9_started",
    }
    if not isinstance(manifest, dict) or set(manifest) != expected_top:
        raise PorePressureInputError("Increment 8 manifest payload is malformed.")
    if (manifest.get("package_version") != PACKAGE_VERSION or manifest.get("increment") != 8
            or manifest.get("increment_title") != MANIFEST_TITLE
            or manifest.get("assurance_tier") != ASSURANCE_TIER
            or manifest.get("limitations") != list(MANIFEST_LIMITATIONS)
            or manifest.get("increment_9_started") is not False):
        raise PorePressureInputError("Increment 8 manifest identity or limitation text changed.")
    hashes = manifest.get("source_artifact_sha256")
    _validate_source_hashes(hashes)
    if manifest.get("prediction_gate") != {
            "nct_fit_performed": False, "overpressure_transform_performed": False,
            "overpressure_inferred": False, "extrapolated_samples": 0}:
        raise PorePressureInputError("Manifest prediction gate is not closed.")
    if manifest.get("pressure_calibration") != {
            "approved_file_count": 0, "required_types": list(PRESSURE_DATA_TYPES),
            "cross_well_transfer_performed": False}:
        raise PorePressureInputError("Manifest calibration inventory is inconsistent.")
    if manifest.get("hydrostatic_reference") != {
            "pressure_datum": "mean_sea_level_gauge_zero",
            "equation": "pressure_pa = fluid_density_kg_m3 * gravity_m_s2 * tvdss_m",
            "fluid_density_scenarios_kg_m3": list(APPROVED_FLUID_DENSITIES_KG_M3),
            "status": "configured_reference_not_measured_formation_pressure"}:
        raise PorePressureInputError("Manifest hydrostatic-reference policy changed.")
    if manifest.get("effective_stress") != {
            "equation": "sigma_v_effective_pa = sigma_v_total_pa - biot_alpha * pore_pressure_pa",
            "biot_alpha_scenarios": list(APPROVED_BIOT_ALPHA_SCENARIOS),
            "wells_with_scenarios": ["Boreas_1", "Poseidon_2"],
            "negative_values_clipped": 0}:
        raise PorePressureInputError("Manifest effective-stress policy changed.")
    counts = manifest.get("row_counts")
    if (not isinstance(counts, dict) or set(counts) != set(CSV_COLUMNS)
            or any(isinstance(v, bool) or not isinstance(v, int) or v < 0
                   for v in counts.values())):
        raise PorePressureInputError("Manifest row-count registry is malformed.")
    if counts != EXPECTED_ROW_COUNTS:
        raise PorePressureInputError(
            "Manifest row counts do not match the locked Increment 8 inventory.")
    nct_manifest = manifest.get("nct_readiness")
    if not isinstance(nct_manifest, list) or len(nct_manifest) != 4:
        raise PorePressureInputError("Manifest NCT-readiness registry is malformed.")
    nct_keys = set(NctReadiness.__dataclass_fields__)
    if any(not isinstance(row, dict) or set(row) != nct_keys for row in nct_manifest):
        raise PorePressureInputError("Manifest NCT-readiness record shape changed.")
    if {row["well_key"] for row in nct_manifest} != set(WELL_KEYS):
        raise PorePressureInputError("Manifest NCT-readiness well inventory changed.")
    for row in nct_manifest:
        NctReadiness(**row)
    for name in CSV_COLUMNS:
        if manifest["row_counts"].get(name) != len(payloads[name]):
            raise PorePressureInputError(f"Manifest count disagrees for {name}.")

    primary_keys = {
        "pressure_data_inventory.csv": ("well_key",),
        "nct_readiness_summary.csv": ("well_key",),
        "hydrostatic_reference_profile.csv": ("well_key", "node_index", "fluid_scenario"),
        "effective_stress_scenarios.csv": ("well_key", "sv_scenario", "fluid_scenario", "biot_alpha"),
        "effective_stress_profile.csv": ("well_key", "node_index", "sv_scenario"),
        "pore_pressure_issues.csv": ("well_key", "issue_code"),
    }
    for name, keys in primary_keys.items():
        seen = set()
        for row in payloads[name]:
            key = tuple(row[k] for k in keys)
            if key in seen:
                raise PorePressureInputError(f"{name} contains a duplicate primary key.")
            seen.add(key)

    if {row["well_key"] for row in payloads["pressure_data_inventory.csv"]} != set(WELL_KEYS):
        raise PorePressureInputError("Pressure-data well inventory is incomplete.")
    if {row["well_key"] for row in payloads["nct_readiness_summary.csv"]} != set(WELL_KEYS):
        raise PorePressureInputError("NCT-readiness well inventory is incomplete.")

    nct_csv_as_records = []
    for row in payloads["nct_readiness_summary.csv"]:
        nct_csv_as_records.append({
            "well_key": row["well_key"],
            "status": row["status"],
            "candidate_configurations": row["candidate_configurations"],
            "qualifying_thickness_min_tvd_m": (
                None if row["qualifying_thickness_min_tvd_m"] == ""
                else row["qualifying_thickness_min_tvd_m"]),
            "qualifying_thickness_max_tvd_m": (
                None if row["qualifying_thickness_max_tvd_m"] == ""
                else row["qualifying_thickness_max_tvd_m"]),
            "thickness_sensitivity_factor": (
                None if row["thickness_sensitivity_factor"] == ""
                else row["thickness_sensitivity_factor"]),
            "pressure_calibration_available":
                row["pressure_calibration_available"] == "true",
            "independent_normal_interval_evidence_available":
                row["independent_normal_interval_evidence_available"] == "true",
            "nct_fit_performed": row["nct_fit_performed"] == "true",
            "overpressure_inferred": row["overpressure_inferred"] == "true",
        })
    if sorted(nct_csv_as_records, key=lambda r: r["well_key"]) != sorted(
            nct_manifest, key=lambda r: r["well_key"]):
        raise PorePressureInputError(
            "Manifest and CSV NCT-readiness records disagree.")

    hydro_by_key = {}
    for row in payloads["hydrostatic_reference_profile.csv"]:
        key = (row["well_key"], row["node_index"], row["fluid_scenario"])
        hydro_by_key[key] = row
        expected_density = FLUID_DENSITY_BY_SCENARIO[row["fluid_scenario"]]
        if (row["fluid_density_kg_m3"] != expected_density
                or row["gravity_m_s2"] != APPROVED_GRAVITY_M_S2):
            raise PorePressureInputError(
                "Hydrostatic profile does not use the approved density and gravity.")
    for well_key, count in PROFILE_NODE_COUNTS.items():
        reference_depths = None
        for scenario in ("low", "base", "high"):
            rows = sorted(
                (r for r in payloads["hydrostatic_reference_profile.csv"]
                 if r["well_key"] == well_key and r["fluid_scenario"] == scenario),
                key=lambda r: r["node_index"],
            )
            if [r["node_index"] for r in rows] != list(range(count)):
                raise PorePressureInputError(
                    "Hydrostatic profile node inventory is not contiguous and complete.")
            depths = [r["tvdss_m"] for r in rows]
            if any(b <= a for a, b in zip(depths, depths[1:])):
                raise PorePressureInputError(
                    "Hydrostatic profile TVDSS must be strictly increasing.")
            if reference_depths is None:
                reference_depths = depths
            elif depths != reference_depths:
                raise PorePressureInputError(
                    "Hydrostatic fluid scenarios do not share identical profile nodes.")

    expected_scenario_keys = {
        (well, sv, fluid, alpha)
        for well in EFFECTIVE_STRESS_WELLS
        for sv in SV_SCENARIOS
        for fluid in ("low", "base", "high")
        for alpha in APPROVED_BIOT_ALPHA_SCENARIOS
    }
    scenario_rows = payloads["effective_stress_scenarios.csv"]
    if {(r["well_key"], r["sv_scenario"], r["fluid_scenario"], r["biot_alpha"])
            for r in scenario_rows} != expected_scenario_keys:
        raise PorePressureInputError(
            "Effective-stress terminal scenario matrix is incomplete.")
    scenario_total_by_key = {}
    for row in scenario_rows:
        density = FLUID_DENSITY_BY_SCENARIO[row["fluid_scenario"]]
        expected_pressure = (
            density * APPROVED_GRAVITY_M_S2 * row["evaluation_tvdss_m"])
        if not math.isclose(
                row["pore_pressure_reference_pa"], expected_pressure,
                rel_tol=1e-12, abs_tol=1e-8):
            raise PorePressureInputError(
                "Effective-stress scenario hydrostatic identity failed.")
        key = (row["well_key"], row["sv_scenario"])
        identity = (row["evaluation_tvdss_m"], row["total_vertical_stress_pa"])
        if key in scenario_total_by_key and scenario_total_by_key[key] != identity:
            raise PorePressureInputError(
                "Effective-stress scenario total stress changes across pressure sensitivities.")
        scenario_total_by_key[key] = identity

    expected_profile_keys = {
        (well, node, sv)
        for well in EFFECTIVE_STRESS_WELLS
        for node in range(PROFILE_NODE_COUNTS[well])
        for sv in SV_SCENARIOS
    }
    profile_rows = payloads["effective_stress_profile.csv"]
    if {(r["well_key"], r["node_index"], r["sv_scenario"])
            for r in profile_rows} != expected_profile_keys:
        raise PorePressureInputError(
            "Effective-stress profile scenario/node inventory is incomplete.")
    for row in profile_rows:
        if (row["biot_alpha"] != APPROVED_PROFILE_BIOT_ALPHA
                or row["fluid_density_kg_m3"]
                != APPROVED_PROFILE_FLUID_DENSITY_KG_M3):
            raise PorePressureInputError(
                "Effective-stress profile does not use its approved reference scenario.")
        hydro_row = hydro_by_key[
            (row["well_key"], row["node_index"], "base")]
        if (row["tvdss_m"] != hydro_row["tvdss_m"]
                or not math.isclose(
                    row["pore_pressure_reference_pa"], hydro_row["pressure_pa"],
                    rel_tol=1e-12, abs_tol=1e-8)):
            raise PorePressureInputError(
                "Effective-stress and hydrostatic profiles disagree.")
    for well in EFFECTIVE_STRESS_WELLS:
        terminal_index = PROFILE_NODE_COUNTS[well] - 1
        for sv in SV_SCENARIOS:
            terminal_profile = next(
                r for r in profile_rows
                if r["well_key"] == well and r["node_index"] == terminal_index
                and r["sv_scenario"] == sv)
            terminal_scenario = scenario_total_by_key[(well, sv)]
            if (terminal_profile["tvdss_m"] != terminal_scenario[0]
                    or not math.isclose(
                        terminal_profile["total_vertical_stress_pa"],
                        terminal_scenario[1], rel_tol=1e-12, abs_tol=1e-8)):
                raise PorePressureInputError(
                    "Effective-stress profile and terminal scenario disagree.")

    expected_issue_keys = {
        *((well, "PRESSURE_CALIBRATION_NOT_AVAILABLE") for well in WELL_KEYS),
        *((well, "NCT_AND_OVERPRESSURE_MODEL_NOT_RUN") for well in WELL_KEYS),
        ("Poseidon_North_1", "ABSOLUTE_VERTICAL_STRESS_SCENARIO_NOT_AVAILABLE"),
        ("Proteus_1ST2", "ABSOLUTE_VERTICAL_STRESS_SCENARIO_NOT_AVAILABLE"),
        ("Poseidon_2", "SONIC_CHECKSHOT_DRIFT_DIAGNOSTIC_UNCORRECTED"),
    }
    if {(r["well_key"], r["issue_code"])
            for r in payloads["pore_pressure_issues.csv"]} != expected_issue_keys:
        raise PorePressureInputError("Pore-pressure issue inventory is incomplete.")

    for row in payloads["pressure_data_inventory.csv"]:
        PressureDataAvailability(
            row["well_key"], row["rft_count"], row["mdt_count"], row["dst_count"],
            row["fit_count"], row["lot_count"], row["xlot_count"], row["dfit_count"],
            row["availability_status"])
    for row in payloads["nct_readiness_summary.csv"]:
        NctReadiness(
            well_key=row["well_key"], status=row["status"],
            candidate_configurations=row["candidate_configurations"],
            qualifying_thickness_min_tvd_m=(None if row["qualifying_thickness_min_tvd_m"] == "" else row["qualifying_thickness_min_tvd_m"]),
            qualifying_thickness_max_tvd_m=(None if row["qualifying_thickness_max_tvd_m"] == "" else row["qualifying_thickness_max_tvd_m"]),
            thickness_sensitivity_factor=(None if row["thickness_sensitivity_factor"] == "" else row["thickness_sensitivity_factor"]),
            pressure_calibration_available=row["pressure_calibration_available"] == "true",
            independent_normal_interval_evidence_available=row["independent_normal_interval_evidence_available"] == "true",
            nct_fit_performed=row["nct_fit_performed"] == "true",
            overpressure_inferred=row["overpressure_inferred"] == "true")
    for row in payloads["hydrostatic_reference_profile.csv"]:
        HydrostaticReferenceNode(
            row["well_key"], row["node_index"], row["fluid_scenario"], row["tvdss_m"],
            row["fluid_density_kg_m3"], row["gravity_m_s2"], row["pressure_pa"])
        if not math.isclose(row["pressure_mpa"], row["pressure_pa"] / 1e6,
                            rel_tol=1e-12, abs_tol=1e-12):
            raise PorePressureInputError("Hydrostatic Pa/MPa identity failed.")
    for row in payloads["effective_stress_scenarios.csv"]:
        EffectiveStressScenario(
            row["well_key"], row["sv_scenario"], row["fluid_scenario"],
            row["biot_alpha"], row["evaluation_tvdss_m"],
            row["total_vertical_stress_pa"], row["pore_pressure_reference_pa"],
            row["effective_vertical_stress_pa"],
            row["effective_stress_nonnegative"] == "true")
        for pa_name, mpa_name in (
                ("total_vertical_stress_pa", "total_vertical_stress_mpa"),
                ("pore_pressure_reference_pa", "pore_pressure_reference_mpa"),
                ("effective_vertical_stress_pa", "effective_vertical_stress_mpa")):
            if not math.isclose(row[mpa_name], row[pa_name] / 1e6,
                                rel_tol=1e-12, abs_tol=1e-12):
                raise PorePressureInputError("Effective-scenario Pa/MPa identity failed.")
    for row in payloads["effective_stress_profile.csv"]:
        expected = row["total_vertical_stress_pa"] - row["biot_alpha"] * row["pore_pressure_reference_pa"]
        if (row["total_vertical_stress_pa"] < 0 or row["pore_pressure_reference_pa"] < 0
                or not 0 <= row["biot_alpha"] <= 1
                or not math.isclose(row["effective_vertical_stress_pa"], expected,
                                    rel_tol=1e-12, abs_tol=1e-8)
                or (row["effective_stress_nonnegative"] == "true") != (expected >= 0)):
            raise PorePressureInputError("Effective-profile identity failed.")
        for pa_name, mpa_name in (
                ("total_vertical_stress_pa", "total_vertical_stress_mpa"),
                ("pore_pressure_reference_pa", "pore_pressure_reference_mpa"),
                ("effective_vertical_stress_pa", "effective_vertical_stress_mpa")):
            if not math.isclose(row[mpa_name], row[pa_name] / 1e6,
                                rel_tol=1e-12, abs_tol=1e-12):
                raise PorePressureInputError("Effective-profile Pa/MPa identity failed.")


def _csv_bytes(columns: Sequence[str], rows: Sequence[Mapping[str, object]]) -> bytes:
    import io
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def export_payloads(payloads: Mapping[str, object], output_dir) -> None:
    """Validate, serialize in isolation, then atomically publish the set."""
    validate_payloads(payloads)
    destination = Path(output_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.candidate-",
                                    dir=str(destination.parent)))
    backup = None
    try:
        for name in OUTPUT_NAMES:
            value = payloads[name]
            data = (_csv_bytes(CSV_COLUMNS[name], value) if name.endswith(".csv")
                    else (json.dumps(value, indent=2, sort_keys=True,
                                     ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8"))
            (staging / name).write_bytes(data)
        # Re-read every staged artifact before it becomes official.
        for name in CSV_COLUMNS:
            with (staging / name).open(newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                if tuple(reader.fieldnames or ()) != CSV_COLUMNS[name]:
                    raise PorePressureInputError(f"Serialized {name} header changed.")
                observed = list(reader)
            expected = [{k: str(v) for k, v in row.items()} for row in payloads[name]]
            if observed != expected:
                raise PorePressureInputError(f"Serialized {name} records changed.")
        json.loads((staging / "pore_pressure_manifest.json").read_text(encoding="utf-8"))
        if destination.exists():
            backup = destination.parent / f".{destination.name}.backup-{uuid.uuid4().hex}"
            os.replace(destination, backup)
        try:
            os.replace(staging, destination)
        except Exception:
            if backup is not None and backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        if backup is not None and backup.exists():
            shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _render_figures_unpublished(
        payloads: Mapping[str, object], output_dir) -> Tuple[str, ...]:
    """Render and verify figures below an unpublished candidate directory."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    validate_payloads(payloads)
    root = Path(output_dir) / "figures"
    root.mkdir(parents=True, exist_ok=True)
    metadata = {"Software": f"p2mem {PACKAGE_VERSION}"}

    hydro = [r for r in payloads["hydrostatic_reference_profile.csv"]
             if r["fluid_scenario"] == "base"]
    fig, ax = plt.subplots(figsize=(7, 6))
    for wk in WELL_KEYS:
        rows = [r for r in hydro if r["well_key"] == wk]
        ax.plot([r["pressure_mpa"] for r in rows], [r["tvdss_m"] for r in rows], label=wk)
    ax.invert_yaxis(); ax.grid(True, alpha=.25); ax.legend(fontsize=8)
    ax.set(xlabel="Hydrostatic reference pressure (MPa)", ylabel="TVDSS (m)",
           title="Configured hydrostatic reference — not measured pressure")
    fig.tight_layout(); fig.savefig(root / "fig01_hydrostatic_reference_profile.png", dpi=150, metadata=metadata); plt.close(fig)

    ready = payloads["nct_readiness_summary.csv"]
    fig, ax = plt.subplots(figsize=(8, 4))
    x = list(range(len(ready)))
    mins = [float(r["qualifying_thickness_min_tvd_m"] or 0.0) for r in ready]
    maxs = [float(r["qualifying_thickness_max_tvd_m"] or 0.0) for r in ready]
    ax.bar(x, maxs, color="#9ecae1", label="maximum")
    ax.bar(x, mins, color="#2171b5", label="minimum")
    ax.set_xticks(x, [r["well_key"] for r in ready], rotation=20, ha="right")
    ax.set(ylabel="Strict-no-gap qualifying thickness (m TVD)",
           title="NCT-candidate sensitivity; no NCT fitted")
    ax.legend(); ax.grid(True, axis="y", alpha=.25); fig.tight_layout()
    fig.savefig(root / "fig02_nct_readiness_and_sensitivity.png", dpi=150, metadata=metadata); plt.close(fig)

    term = [r for r in payloads["effective_stress_scenarios.csv"]
            if r["fluid_scenario"] == "base" and float(r["biot_alpha"]) == 1.0]
    fig, ax = plt.subplots(figsize=(8, 4))
    labels = [f"{r['well_key']}\n{r['sv_scenario']}" for r in term]
    vals = [r["effective_vertical_stress_mpa"] for r in term]
    ax.bar(range(len(vals)), vals, color="#31a354")
    ax.set_xticks(range(len(vals)), labels, rotation=25, ha="right")
    ax.set(ylabel="Effective vertical stress scenario (MPa)",
           title="Terminal sensitivity — hydrostatic reference, α=1.0")
    ax.grid(True, axis="y", alpha=.25); fig.tight_layout()
    fig.savefig(root / "fig03_terminal_effective_stress_scenarios.png", dpi=150, metadata=metadata); plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 3.5))
    rows = payloads["pressure_data_inventory.csv"]
    ax.imshow([[0] * 7 for _ in rows], cmap="Greys", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(7), ["RFT", "MDT", "DST", "FIT", "LOT", "XLOT", "DFIT"])
    ax.set_yticks(range(4), [r["well_key"] for r in rows])
    for i in range(4):
        for j in range(7): ax.text(j, i, "0", ha="center", va="center")
    ax.set_title("Approved pressure-calibration measurements — factual inventory")
    fig.tight_layout(); fig.savefig(root / "fig04_pressure_calibration_data_gap.png", dpi=150, metadata=metadata); plt.close(fig)
    observed = tuple(p.name for p in sorted(root.glob("*.png")))
    if set(observed) != set(FIGURE_NAMES) or len(observed) != len(FIGURE_NAMES):
        raise PorePressureInputError("Rendered figure inventory is not exact.")
    return FIGURE_NAMES


def render_figures(payloads: Mapping[str, object], output_dir) -> Tuple[str, ...]:
    """Render four PNGs transactionally; preserve any prior complete set on failure."""
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / "figures"
    workspace = Path(tempfile.mkdtemp(
        prefix=".figures.candidate-", dir=str(output_root)))
    candidate_output = workspace / "output"
    backup = None
    try:
        names = _render_figures_unpublished(payloads, candidate_output)
        candidate = candidate_output / "figures"
        if destination.exists():
            if not destination.is_dir():
                raise PorePressureInputError(
                    "Figure destination exists but is not a directory.")
            backup = output_root / f".figures.backup-{uuid.uuid4().hex}"
            os.replace(destination, backup)
        try:
            os.replace(candidate, destination)
        except Exception:
            if backup is not None and backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        if backup is not None and backup.exists():
            shutil.rmtree(backup)
        return names
    finally:
        if workspace.exists():
            shutil.rmtree(workspace)
