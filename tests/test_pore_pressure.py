from dataclasses import replace
import math
from numbers import Real

import numpy as np
import pytest
import yaml

from p2mem.pore_pressure import (
    build_hydrostatic_nodes, build_pressure_data_inventory,
    derive_nct_readiness, effective_vertical_stress_pa,
    hydrostatic_reference_pressure_pa, load_pressure_config,
    make_effective_scenario, scenario_initial_stress_pa,
)
from p2mem.pore_pressure_models import (
    ASSURANCE_TIER, PRESSURE_DATA_TYPES, EffectiveStressScenario,
    HydrostaticReferenceNode, NctReadiness, PorePressureInputError,
    PressureDataAvailability,
)
from synthetic_inc8 import config, thickness_rows


INVALID_SCALARS = [True, False, "1", b"1", 1 + 0j, None, [1], np.array([1.0]),
                   float("nan"), float("inf"), float("-inf")]


@pytest.mark.parametrize("depth", [0.0, 1.0, 1000.0, np.float64(2000.0)])
@pytest.mark.parametrize("density", [1000.0, 1025.0, np.float64(1100.0)])
def test_hydrostatic_exact_identity(depth, density):
    got = hydrostatic_reference_pressure_pa(depth, density, 9.80665)
    assert got == pytest.approx(float(depth) * float(density) * 9.80665,
                                rel=1e-15, abs=1e-9)


@pytest.mark.parametrize("bad", INVALID_SCALARS)
def test_hydrostatic_rejects_invalid_depth(bad):
    with pytest.raises(PorePressureInputError):
        hydrostatic_reference_pressure_pa(bad, 1025.0, 9.80665)


@pytest.mark.parametrize("bad", INVALID_SCALARS)
def test_hydrostatic_rejects_invalid_density(bad):
    with pytest.raises(PorePressureInputError):
        hydrostatic_reference_pressure_pa(1000.0, bad, 9.80665)


@pytest.mark.parametrize("bad", INVALID_SCALARS)
def test_hydrostatic_rejects_invalid_gravity(bad):
    with pytest.raises(PorePressureInputError):
        hydrostatic_reference_pressure_pa(1000.0, 1025.0, bad)


@pytest.mark.parametrize("args", [(-1, 1025, 9.8), (1, -1, 9.8), (1, 1025, -1),
                                   (1, 0, 9.8), (1, 1025, 0)])
def test_hydrostatic_rejects_out_of_domain(args):
    with pytest.raises(PorePressureInputError):
        hydrostatic_reference_pressure_pa(*args)


@pytest.mark.parametrize("alpha,expected", [(0.0, 100.0), (0.5, 90.0), (1.0, 80.0)])
def test_effective_stress_equation(alpha, expected):
    assert effective_vertical_stress_pa(100.0, 20.0, alpha) == expected


def test_negative_effective_stress_is_retained_not_clipped():
    assert effective_vertical_stress_pa(10.0, 20.0, 1.0) == -10.0


@pytest.mark.parametrize("bad", INVALID_SCALARS)
@pytest.mark.parametrize("position", [0, 1, 2])
def test_effective_stress_rejects_invalid_scalar(bad, position):
    args = [100.0, 20.0, 1.0]
    args[position] = bad
    with pytest.raises(PorePressureInputError):
        effective_vertical_stress_pa(*args)


@pytest.mark.parametrize("args", [(-1, 0, 1), (1, -1, 1), (1, 0, -0.1), (1, 0, 1.1)])
def test_effective_stress_rejects_out_of_domain(args):
    with pytest.raises(PorePressureInputError):
        effective_vertical_stress_pa(*args)


def test_config_fixture_is_valid():
    c = config()
    assert c.schema_version == "8.0.1"
    assert c.pressure_calibration_types == PRESSURE_DATA_TYPES


@pytest.mark.parametrize("field,value", [
    ("schema_version", "8"), ("schema_version", "8.0.0"),
    ("assurance_tier", "calibrated"),
    ("gravity_m_s2", 0.0), ("gravity_m_s2", True),
    ("gravity_m_s2", 9.81),
    ("fluid_density_low_kg_m3", 1025.0),
    ("fluid_density_low_kg_m3", 1019.0),
    ("fluid_density_base_kg_m3", 1026.0),
    ("fluid_density_high_kg_m3", 1031.0),
    ("biot_alpha_scenarios", (0.8, 0.8)),
    ("biot_alpha_scenarios", (1.0, 0.8)),
    ("biot_alpha_scenarios", (1.1,)), ("profile_biot_alpha", -0.1),
    ("profile_biot_alpha", 0.8),
    ("profile_fluid_density_kg_m3", 1030.0),
    ("pressure_calibration_types", ("RFT",)),
    ("pressure_calibration_file_count", 1),
    ("pressure_calibration_file_count", 0.0),
    ("nct_fit_enabled", True), ("overpressure_transform_enabled", True),
    ("extrapolation_allowed", True), ("pressure_calibration_required", 1),
    ("pressure_calibration_required", False),
    ("independent_normal_interval_evidence_required", False),
    ("cross_well_transfer_allowed", True),
    ("sonic_checkshot_drift_correction_allowed", True),
    ("increment_9_started", True),
])
def test_config_invariants(field, value):
    with pytest.raises(PorePressureInputError):
        replace(config(), **{field: value})


def test_load_shipped_config(project_root):
    c = load_pressure_config(project_root / "config/pore_pressure.yml")
    assert c == config()


def test_load_config_missing(tmp_path):
    with pytest.raises(PorePressureInputError):
        load_pressure_config(tmp_path / "missing.yml")


def test_load_config_malformed(tmp_path):
    p = tmp_path / "x.yml"
    p.write_text("[not: valid", encoding="utf-8")
    with pytest.raises(PorePressureInputError):
        load_pressure_config(p)


def test_load_config_rejects_unknown_top_level_field(project_root, tmp_path):
    raw = yaml.safe_load((project_root / "config/pore_pressure.yml").read_text())
    raw["typo"] = 1
    p = tmp_path / "x.yml"; p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(PorePressureInputError, match="malformed"):
        load_pressure_config(p)


def test_load_config_rejects_unknown_nested_field(project_root, tmp_path):
    raw = yaml.safe_load((project_root / "config/pore_pressure.yml").read_text())
    raw["prediction_policy"]["silent_bypass"] = True
    p = tmp_path / "x.yml"; p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(PorePressureInputError, match="malformed"):
        load_pressure_config(p)


@pytest.mark.parametrize("needle", [
    'schema_version: "8.0.1"',
    "  gravity_m_s2: 9.80665",
])
def test_load_config_rejects_duplicate_key_at_any_depth(project_root, tmp_path, needle):
    text = (project_root / "config/pore_pressure.yml").read_text(encoding="utf-8")
    text = text.replace(needle, needle + "\n" + needle, 1)
    path = tmp_path / "duplicate.yml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(PorePressureInputError, match="malformed"):
        load_pressure_config(path)


def test_pressure_inventory_exact_four_wells():
    rows = build_pressure_data_inventory(("Poseidon_2", "Boreas_1"))
    assert [r.well_key for r in rows] == ["Boreas_1", "Poseidon_2"]
    assert all(r.availability_status == "NOT_AVAILABLE" for r in rows)


@pytest.mark.parametrize("field", ["rft_count", "mdt_count", "dst_count", "fit_count",
                                    "lot_count", "xlot_count", "dfit_count"])
@pytest.mark.parametrize("bad", [-1, 0.0, True, "0", float("nan")])
def test_pressure_availability_count_is_strict_integer(field, bad):
    good = PressureDataAvailability("Poseidon_2", 0, 0, 0, 0, 0, 0, 0, "NOT_AVAILABLE")
    with pytest.raises(PorePressureInputError):
        replace(good, **{field: bad})


def test_pressure_availability_cannot_claim_data():
    with pytest.raises(PorePressureInputError):
        PressureDataAvailability("Poseidon_2", 1, 0, 0, 0, 0, 0, 0, "NOT_AVAILABLE")


def test_nct_no_rows_means_not_eligible():
    r = derive_nct_readiness("Boreas_1", [])
    assert r.candidate_configurations == 0
    assert r.status == "NOT_ELIGIBLE_INPUT_QC_EXCLUSION"
    assert r.qualifying_thickness_min_tvd_m is None


def test_nct_candidate_sensitivity_is_measured():
    r = derive_nct_readiness("Poseidon_2", thickness_rows())
    assert r.candidate_configurations == 9
    assert r.qualifying_thickness_min_tvd_m == 50.0
    assert r.qualifying_thickness_max_tvd_m == 150.0
    assert r.thickness_sensitivity_factor == 3.0
    assert not r.nct_fit_performed and not r.overpressure_inferred


@pytest.mark.parametrize("value", ["", "nan", "inf", "0", "-1", True, 1.0])
def test_nct_rejects_invalid_qualifying_thickness(value):
    rows = thickness_rows()
    rows[0]["gross_qualifying_thickness_tvdss_m"] = value
    with pytest.raises(PorePressureInputError):
        derive_nct_readiness("Poseidon_2", rows)


def test_nct_rejects_duplicate_case():
    rows = thickness_rows(); rows[-1] = dict(rows[0])
    with pytest.raises(PorePressureInputError, match="exactly nine"):
        derive_nct_readiness("Poseidon_2", rows)


def test_nct_requires_complete_exact_strict_case_matrix():
    rows = thickness_rows()
    rows[0]["contiguity_policy"] = "configured_bridging"
    with pytest.raises(PorePressureInputError, match="exactly nine"):
        derive_nct_readiness("Poseidon_2", rows)


@pytest.mark.parametrize("field,value", [
    ("candidate_configurations", 0.0), ("candidate_configurations", True),
    ("pressure_calibration_available", 0), ("nct_fit_performed", True),
    ("overpressure_inferred", True), ("thickness_sensitivity_factor", 2.0),
])
def test_nct_record_invariants(field, value):
    good = derive_nct_readiness("Poseidon_2", thickness_rows())
    with pytest.raises(PorePressureInputError):
        replace(good, **{field: value})


def test_hydrostatic_node_constructor_checks_identity():
    with pytest.raises(PorePressureInputError):
        HydrostaticReferenceNode("Poseidon_2", 0, "base", 1000.0, 1025.0,
                                 9.80665, 1.0)


def test_build_hydrostatic_nodes_three_per_input_row():
    rows = [{"well_key": "Poseidon_2", "node_index": "0", "tvdss_m": "1000"}]
    out = build_hydrostatic_nodes(rows, config())
    assert len(out) == 3
    assert [r.fluid_scenario for r in out] == ["low", "base", "high"]


def test_hydrostatic_nodes_reject_duplicate_index():
    rows = [{"well_key": "Poseidon_2", "node_index": "0", "tvdss_m": "1000"}] * 2
    with pytest.raises(PorePressureInputError, match="duplicate"):
        build_hydrostatic_nodes(rows, config())


@pytest.mark.parametrize("field,value", [
    ("node_index", True), ("node_index", 0), ("node_index", 0.0),
    ("node_index", "0.0"), ("tvdss_m", True), ("tvdss_m", 1000.0),
])
def test_hydrostatic_nodes_require_canonical_csv_tokens(field, value):
    row = {"well_key": "Poseidon_2", "node_index": "0", "tvdss_m": "1000"}
    row[field] = value
    with pytest.raises(PorePressureInputError):
        build_hydrostatic_nodes([row], config())


@pytest.mark.parametrize("rows", [
    [{"well_key": "Poseidon_2", "node_index": "1", "tvdss_m": "1000"}],
    [{"well_key": "Poseidon_2", "node_index": "0", "tvdss_m": "1000"},
     {"well_key": "Poseidon_2", "node_index": "2", "tvdss_m": "1001"}],
    [{"well_key": "Poseidon_2", "node_index": "0", "tvdss_m": "1000"},
     {"well_key": "Poseidon_2", "node_index": "1", "tvdss_m": "999"}],
])
def test_hydrostatic_nodes_reject_noncontiguous_or_reversed(rows):
    with pytest.raises(PorePressureInputError):
        build_hydrostatic_nodes(rows, config())


def test_scenario_initial_stress_removes_measured_and_bridged_components():
    assert scenario_initial_stress_pa(100.0, 60.0, 10.0) == 30.0


def test_scenario_initial_stress_rejects_component_overrun():
    with pytest.raises(PorePressureInputError):
        scenario_initial_stress_pa(100.0, 95.0, 10.0)


def test_make_effective_scenario_sets_flag_and_identity():
    r = make_effective_scenario(
        well_key="Poseidon_2", sv_scenario="base", fluid_scenario="base",
        biot_alpha=1.0, evaluation_tvdss_m=1000.0,
        total_vertical_stress_pa=30e6, fluid_density_kg_m3=1025.0,
        gravity_m_s2=9.80665)
    assert r.effective_stress_nonnegative
    assert r.effective_vertical_stress_pa == 30e6 - 1025.0 * 9.80665 * 1000.0


def test_make_effective_scenario_retains_negative_and_flags():
    r = make_effective_scenario(
        well_key="Poseidon_2", sv_scenario="low", fluid_scenario="high",
        biot_alpha=1.0, evaluation_tvdss_m=1000.0,
        total_vertical_stress_pa=1.0, fluid_density_kg_m3=1030.0,
        gravity_m_s2=9.80665)
    assert r.effective_vertical_stress_pa < 0.0
    assert not r.effective_stress_nonnegative


@pytest.fixture
def project_root():
    from pathlib import Path
    return Path(__file__).resolve().parents[1]
