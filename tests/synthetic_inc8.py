"""Small fictional Increment 8 fixtures; no private project data."""

from p2mem.pore_pressure_models import PressureConfig


def config() -> PressureConfig:
    return PressureConfig(
        schema_version="8.0.1",
        assurance_tier="Tier C - Screening-Level / Uncalibrated Educational",
        gravity_m_s2=9.80665,
        fluid_density_low_kg_m3=1020.0,
        fluid_density_base_kg_m3=1025.0,
        fluid_density_high_kg_m3=1030.0,
        biot_alpha_scenarios=(0.8, 1.0),
        profile_biot_alpha=1.0,
        profile_fluid_density_kg_m3=1025.0,
        pressure_calibration_types=("RFT", "MDT", "DST", "FIT", "LOT", "XLOT", "DFIT"),
        pressure_calibration_file_count=0,
        cross_well_transfer_allowed=False,
        nct_fit_enabled=False,
        overpressure_transform_enabled=False,
        pressure_calibration_required=True,
        independent_normal_interval_evidence_required=True,
        sonic_checkshot_drift_correction_allowed=False,
        extrapolation_allowed=False,
        increment_9_started=False,
    )


def thickness_rows(well="Poseidon_2"):
    rows = []
    for scenario, values in {
        "low": (100.0, 120.0, 150.0),
        "base": (80.0, 110.0, 140.0),
        "high": (50.0, 70.0, 90.0),
    }.items():
        for threshold, thickness in zip(("0.5", "0.6", "0.7"), values):
            rows.append({
                "well_key": well,
                "mask_name": "eligible_sonic_nct_candidate",
                "contiguity_policy": "strict_no_gap",
                "scenario_name": scenario,
                "proxy_threshold": threshold,
                "gross_qualifying_thickness_tvdss_m": str(thickness),
            })
    return rows
