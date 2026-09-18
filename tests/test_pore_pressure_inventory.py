import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil

import pytest

from p2mem.io import pore_pressure_inventory as inv
from p2mem.io.pore_pressure_workflow import LOCKED_PATHS, run_pore_pressure_workflow
from p2mem.pore_pressure_models import PorePressureInputError, WELL_KEYS
from p2mem.wellframe_models import find_prohibited_lithology_terms


@pytest.fixture(scope="module")
def project_root():
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def run(project_root):
    return run_pore_pressure_workflow(project_root, render_png=True)


def test_real_output_row_counts(run):
    p = run["payloads"]
    assert len(p["pressure_data_inventory.csv"]) == 4
    assert len(p["nct_readiness_summary.csv"]) == 4
    assert len(p["hydrostatic_reference_profile.csv"]) == 1053
    assert len(p["effective_stress_scenarios.csv"]) == 36
    assert len(p["effective_stress_profile.csv"]) == 606
    assert len(p["pore_pressure_issues.csv"]) == 11


def test_real_nct_readiness_values(run):
    rows = {r["well_key"]: r for r in run["payloads"]["nct_readiness_summary.csv"]}
    assert rows["Boreas_1"]["candidate_configurations"] == 0
    expected = {
        "Poseidon_2": (140.00288306447783, 1110.2406141181677, 7.930126793223611),
        "Poseidon_North_1": (341.53500002135024, 1198.155163071352, 3.508147519277533),
        "Proteus_1ST2": (350.1931358785905, 861.8933646094738, 2.461194341936748),
    }
    for wk, values in expected.items():
        row = rows[wk]
        assert row["candidate_configurations"] == 9
        assert row["qualifying_thickness_min_tvd_m"] == pytest.approx(values[0])
        assert row["qualifying_thickness_max_tvd_m"] == pytest.approx(values[1])
        assert row["thickness_sensitivity_factor"] == pytest.approx(values[2])
        assert row["nct_fit_performed"] == "false"
        assert row["overpressure_inferred"] == "false"


def test_terminal_effective_stress_reference_values(run):
    rows = run["payloads"]["effective_stress_scenarios.csv"]
    selected = {(r["well_key"], r["sv_scenario"]): r for r in rows
                if r["fluid_scenario"] == "base" and r["biot_alpha"] == 1.0}
    expected = {
        ("Boreas_1", "low"): 12.006014395007833,
        ("Boreas_1", "base"): 35.386034009776054,
        ("Boreas_1", "high"): 58.76605362454429,
        ("Poseidon_2", "low"): 18.463263937047348,
        ("Poseidon_2", "base"): 43.13105927689639,
        ("Poseidon_2", "high"): 67.79885461674543,
    }
    assert set(selected) == set(expected)
    for key, value in expected.items():
        assert selected[key]["effective_vertical_stress_mpa"] == pytest.approx(value)


def test_effective_stress_only_where_increment7_has_sv_scenarios(run):
    wells = {r["well_key"] for r in run["payloads"]["effective_stress_scenarios.csv"]}
    assert wells == {"Boreas_1", "Poseidon_2"}


def test_hydrostatic_reference_covers_all_locked_profile_nodes(run):
    rows = run["payloads"]["hydrostatic_reference_profile.csv"]
    assert {r["well_key"] for r in rows} == set(WELL_KEYS)
    for row in rows:
        assert row["pressure_pa"] == pytest.approx(
            row["fluid_density_kg_m3"] * row["gravity_m_s2"] * row["tvdss_m"])


def test_all_effective_records_satisfy_identity(run):
    for name in ("effective_stress_scenarios.csv", "effective_stress_profile.csv"):
        for row in run["payloads"][name]:
            assert row["effective_vertical_stress_pa"] == pytest.approx(
                row["total_vertical_stress_pa"]
                - row["biot_alpha"] * row["pore_pressure_reference_pa"])
            assert row["effective_stress_nonnegative"] == "true"


def test_manifest_prediction_gate_is_all_false(run):
    gate = run["payloads"]["pore_pressure_manifest.json"]["prediction_gate"]
    assert gate == {"nct_fit_performed": False,
                    "overpressure_transform_performed": False,
                    "overpressure_inferred": False,
                    "extrapolated_samples": 0}


def test_manifest_source_hashes_are_real(run, project_root):
    recorded = run["payloads"]["pore_pressure_manifest.json"]["source_artifact_sha256"]
    assert set(recorded) == set(LOCKED_PATHS)
    for name, rel in LOCKED_PATHS.items():
        assert recorded[name] == hashlib.sha256((project_root / rel).read_bytes()).hexdigest()
    assert recorded == inv.EXPECTED_LOCKED_SOURCE_SHA256


def test_output_strings_contain_no_prohibited_named_lithology(run):
    def strings(value):
        if isinstance(value, str): yield value
        elif isinstance(value, dict):
            for k, v in value.items(): yield from strings(k); yield from strings(v)
        elif isinstance(value, (list, tuple)):
            for v in value: yield from strings(v)
    violations = []
    for artifact, payload in run["payloads"].items():
        for text in strings(payload):
            terms = find_prohibited_lithology_terms(text)
            if terms: violations.append((artifact, text, terms))
    assert violations == []


def test_every_csv_has_exact_declared_column_order(run):
    for name, columns in inv.CSV_COLUMNS.items():
        for row in run["payloads"][name]:
            assert tuple(row) == columns


def test_export_is_byte_deterministic(run, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    inv.export_payloads(run["payloads"], a)
    inv.export_payloads(run["payloads"], b)
    for name in inv.OUTPUT_NAMES:
        assert (a / name).read_bytes() == (b / name).read_bytes()


def test_export_uses_lf_only(run, tmp_path):
    out = tmp_path / "out"
    inv.export_payloads(run["payloads"], out)
    for name in inv.OUTPUT_NAMES:
        data = (out / name).read_bytes()
        assert b"\r" not in data
        assert data.endswith(b"\n")


def test_export_rollback_is_byte_exact(run, tmp_path, monkeypatch):
    out = tmp_path / "official"
    out.mkdir()
    sentinel = out / "sentinel.bin"
    sentinel.write_bytes(b"LOCKED")
    real_replace = inv.os.replace
    calls = {"n": 0}
    def fail_second(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("injected publication failure")
        return real_replace(src, dst)
    monkeypatch.setattr(inv.os, "replace", fail_second)
    with pytest.raises(OSError, match="injected"):
        inv.export_payloads(run["payloads"], out)
    assert sentinel.read_bytes() == b"LOCKED"
    assert list(out.iterdir()) == [sentinel]
    assert not list(tmp_path.glob(".official.*"))


def test_missing_field_fails_before_export(run, tmp_path):
    payloads = dict(run["payloads"])
    rows = [dict(r) for r in payloads["pressure_data_inventory.csv"]]
    rows[0].pop("rft_count")
    payloads["pressure_data_inventory.csv"] = rows
    with pytest.raises(PorePressureInputError):
        inv.export_payloads(payloads, tmp_path / "x")


def test_unknown_field_fails_before_export(run, tmp_path):
    payloads = dict(run["payloads"])
    rows = [dict(r) for r in payloads["pressure_data_inventory.csv"]]
    rows[0]["typo"] = "silent"
    payloads["pressure_data_inventory.csv"] = rows
    with pytest.raises(PorePressureInputError):
        inv.export_payloads(payloads, tmp_path / "x")


def test_unauthorized_string_fails_before_export(run, tmp_path):
    payloads = dict(run["payloads"])
    rows = [dict(r) for r in payloads["pressure_data_inventory.csv"]]
    rows[0]["calibration_status"] = "calibrated"
    payloads["pressure_data_inventory.csv"] = rows
    with pytest.raises(PorePressureInputError, match="unauthorized"):
        inv.export_payloads(payloads, tmp_path / "x")


def test_nonfinite_fails_before_export(run, tmp_path):
    payloads = dict(run["payloads"])
    rows = [dict(r) for r in payloads["hydrostatic_reference_profile.csv"]]
    rows[0]["pressure_pa"] = float("nan")
    payloads["hydrostatic_reference_profile.csv"] = rows
    with pytest.raises(PorePressureInputError):
        inv.export_payloads(payloads, tmp_path / "x")


def test_hydrostatic_identity_mutation_fails_before_export(run, tmp_path):
    payloads = dict(run["payloads"])
    rows = [dict(r) for r in payloads["hydrostatic_reference_profile.csv"]]
    rows[0]["pressure_pa"] += 1.0
    payloads["hydrostatic_reference_profile.csv"] = rows
    with pytest.raises(PorePressureInputError, match="identity"):
        inv.export_payloads(payloads, tmp_path / "x")


def test_effective_identity_mutation_fails_before_export(run, tmp_path):
    payloads = dict(run["payloads"])
    rows = [dict(r) for r in payloads["effective_stress_scenarios.csv"]]
    rows[0]["effective_vertical_stress_pa"] += 1.0
    payloads["effective_stress_scenarios.csv"] = rows
    with pytest.raises(PorePressureInputError, match="identity"):
        inv.export_payloads(payloads, tmp_path / "x")


def test_duplicate_primary_key_fails_before_export(run, tmp_path):
    payloads = dict(run["payloads"])
    rows = [dict(r) for r in payloads["pressure_data_inventory.csv"]]
    rows[1] = dict(rows[0])
    payloads["pressure_data_inventory.csv"] = rows
    with pytest.raises(PorePressureInputError, match="duplicate primary"):
        inv.export_payloads(payloads, tmp_path / "x")


def test_manifest_count_mismatch_fails(run, tmp_path):
    payloads = dict(run["payloads"])
    manifest = json.loads(json.dumps(payloads["pore_pressure_manifest.json"]))
    manifest["row_counts"]["pressure_data_inventory.csv"] = 999
    payloads["pore_pressure_manifest.json"] = manifest
    with pytest.raises(PorePressureInputError):
        inv.export_payloads(payloads, tmp_path / "x")


def test_manifest_prose_mutation_fails(run, tmp_path):
    payloads = dict(run["payloads"])
    manifest = json.loads(json.dumps(payloads["pore_pressure_manifest.json"]))
    manifest["limitations"][0] = "Everything is calibrated."
    payloads["pore_pressure_manifest.json"] = manifest
    with pytest.raises(PorePressureInputError, match="identity or limitation"):
        inv.export_payloads(payloads, tmp_path / "x")


def test_manifest_hash_type_fails(run, tmp_path):
    payloads = dict(run["payloads"])
    manifest = json.loads(json.dumps(payloads["pore_pressure_manifest.json"]))
    first = next(iter(manifest["source_artifact_sha256"]))
    manifest["source_artifact_sha256"][first] = None
    payloads["pore_pressure_manifest.json"] = manifest
    with pytest.raises(PorePressureInputError, match="hashes"):
        inv.export_payloads(payloads, tmp_path / "x")


def test_coordinated_row_removal_and_count_edit_still_fail_closed(run, tmp_path):
    payloads = dict(run["payloads"])
    payloads["pressure_data_inventory.csv"] = [
        dict(r) for r in payloads["pressure_data_inventory.csv"][:-1]
    ]
    manifest = json.loads(json.dumps(payloads["pore_pressure_manifest.json"]))
    manifest["row_counts"]["pressure_data_inventory.csv"] -= 1
    payloads["pore_pressure_manifest.json"] = manifest
    with pytest.raises(PorePressureInputError, match="locked Increment 8 inventory"):
        inv.export_payloads(payloads, tmp_path / "x")


def test_manifest_nct_record_must_equal_csv_record(run, tmp_path):
    payloads = dict(run["payloads"])
    manifest = json.loads(json.dumps(payloads["pore_pressure_manifest.json"]))
    manifest["nct_readiness"][1]["qualifying_thickness_min_tvd_m"] *= 2.0
    manifest["nct_readiness"][1]["qualifying_thickness_max_tvd_m"] *= 2.0
    payloads["pore_pressure_manifest.json"] = manifest
    with pytest.raises(PorePressureInputError, match="Manifest and CSV"):
        inv.export_payloads(payloads, tmp_path / "x")


def test_hydrostatic_density_must_match_named_scenario(run, tmp_path):
    payloads = dict(run["payloads"])
    rows = [dict(r) for r in payloads["hydrostatic_reference_profile.csv"]]
    rows[0]["fluid_density_kg_m3"] = 1019.0
    rows[0]["pressure_pa"] = (
        rows[0]["fluid_density_kg_m3"] * rows[0]["gravity_m_s2"] * rows[0]["tvdss_m"])
    rows[0]["pressure_mpa"] = rows[0]["pressure_pa"] / 1e6
    payloads["hydrostatic_reference_profile.csv"] = rows
    with pytest.raises(PorePressureInputError, match="approved density"):
        inv.export_payloads(payloads, tmp_path / "x")


def test_effective_profile_must_match_hydrostatic_profile(run, tmp_path):
    payloads = dict(run["payloads"])
    rows = [dict(r) for r in payloads["effective_stress_profile.csv"]]
    rows[0]["pore_pressure_reference_pa"] += 1.0
    rows[0]["pore_pressure_reference_mpa"] = rows[0]["pore_pressure_reference_pa"] / 1e6
    rows[0]["effective_vertical_stress_pa"] = (
        rows[0]["total_vertical_stress_pa"]
        - rows[0]["biot_alpha"] * rows[0]["pore_pressure_reference_pa"])
    rows[0]["effective_vertical_stress_mpa"] = rows[0]["effective_vertical_stress_pa"] / 1e6
    payloads["effective_stress_profile.csv"] = rows
    with pytest.raises(PorePressureInputError, match="hydrostatic profiles disagree"):
        inv.export_payloads(payloads, tmp_path / "x")


def test_direct_figure_render_failure_preserves_previous_figures(
        run, tmp_path, monkeypatch):
    out = tmp_path / "official"
    inv.export_payloads(run["payloads"], out)
    inv.render_figures(run["payloads"], out)
    before = {
        p.name: p.read_bytes() for p in (out / "figures").iterdir() if p.is_file()
    }

    def fail_candidate(payloads, candidate_output):
        root = Path(candidate_output) / "figures"
        root.mkdir(parents=True)
        (root / "partial.png").write_bytes(b"partial")
        raise RuntimeError("injected direct render failure")

    monkeypatch.setattr(inv, "_render_figures_unpublished", fail_candidate)
    with pytest.raises(RuntimeError, match="injected direct render failure"):
        inv.render_figures(run["payloads"], out)
    after = {
        p.name: p.read_bytes() for p in (out / "figures").iterdir() if p.is_file()
    }
    assert after == before
    assert not list(out.glob(".figures.*"))


@pytest.mark.parametrize("name", inv.OUTPUT_NAMES)
def test_exported_artifact_exists_and_nonempty(project_root, name):
    path = project_root / "outputs/08_pore_pressure_effective_stress" / name
    assert path.is_file() and path.stat().st_size > 0


@pytest.mark.parametrize("figure", inv.FIGURE_NAMES)
def test_figure_exists(project_root, figure):
    path = project_root / "outputs/08_pore_pressure_effective_stress/figures" / figure
    assert path.is_file() and path.stat().st_size > 1000


def test_read_locked_csv_missing(tmp_path):
    with pytest.raises(PorePressureInputError):
        inv.read_locked_csv(tmp_path / "missing.csv")


def test_read_locked_csv_duplicate_header(tmp_path):
    p = tmp_path / "vertical_stress_profile.csv"
    p.write_text("well_key,well_key,node_index,tvdss_m,cumulative_measured_increment_pa\n",
                 encoding="utf-8")
    with pytest.raises(PorePressureInputError):
        inv.read_locked_csv(p)


def test_read_locked_csv_missing_required_column(tmp_path):
    p = tmp_path / "vertical_stress_profile.csv"
    p.write_text("well_key,node_index,tvdss_m\n", encoding="utf-8")
    with pytest.raises(PorePressureInputError):
        inv.read_locked_csv(p)


def test_read_locked_csv_wrong_row_width(tmp_path):
    p = tmp_path / "vertical_stress_profile.csv"
    p.write_text("well_key,node_index,tvdss_m,cumulative_measured_increment_pa\nA,0,1\n",
                 encoding="utf-8")
    with pytest.raises(PorePressureInputError):
        inv.read_locked_csv(p)


def test_read_locked_csv_rejects_header_only_file(tmp_path):
    path = tmp_path / "vertical_stress_profile.csv"
    path.write_text(
        "well_key,node_index,tvdss_m,cumulative_measured_increment_pa\n",
        encoding="utf-8")
    with pytest.raises(PorePressureInputError, match="empty"):
        inv.read_locked_csv(path)
