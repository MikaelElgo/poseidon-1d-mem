import csv
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from p2mem.io import pore_pressure_workflow as workflow_module
from p2mem.io.pore_pressure_inventory import EXPECTED_LOCKED_SOURCE_SHA256
from p2mem.io.pore_pressure_workflow import LOCKED_PATHS, run_pore_pressure_workflow
from p2mem.pore_pressure_models import PorePressureInputError


@pytest.fixture(scope="module")
def project_root():
    return Path(__file__).resolve().parents[1]


def copy_minimal_project(source: Path, target: Path) -> Path:
    (target / "config").mkdir(parents=True)
    shutil.copy2(source / "config/pore_pressure.yml", target / "config/pore_pressure.yml")
    for rel in LOCKED_PATHS.values():
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / rel, dst)
    return target


def test_workflow_runs_without_private_raw_inputs(project_root, tmp_path):
    root = copy_minimal_project(project_root, tmp_path / "project")
    result = run_pore_pressure_workflow(root, render_png=False)
    assert result["payloads"]["pore_pressure_manifest.json"]["increment"] == 8
    assert not (root / "private_inputs").exists()


def test_missing_locked_source_fails_closed(project_root, tmp_path):
    root = copy_minimal_project(project_root, tmp_path / "project")
    (root / LOCKED_PATHS["vertical_stress_profile.csv"]).unlink()
    with pytest.raises(PorePressureInputError, match="missing"):
        run_pore_pressure_workflow(root, render_png=False)


def test_malformed_upstream_manifest_fails_closed(project_root, tmp_path):
    root = copy_minimal_project(project_root, tmp_path / "project")
    (root / LOCKED_PATHS["petrophysics_eligibility_manifest.json"]).write_text("{", encoding="utf-8")
    with pytest.raises(PorePressureInputError, match="malformed"):
        run_pore_pressure_workflow(root, render_png=False)


def test_upstream_calibration_premise_must_remain_false(project_root, tmp_path):
    root = copy_minimal_project(project_root, tmp_path / "project")
    p = root / LOCKED_PATHS["petrophysics_eligibility_manifest.json"]
    data = json.loads(p.read_text())
    data["calibration_data_available"]["pressure_rft_mdt_dst"] = True
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PorePressureInputError, match="zero-calibration"):
        run_pore_pressure_workflow(root, render_png=False)


def test_method_and_thickness_candidate_wells_must_agree(project_root, tmp_path):
    root = copy_minimal_project(project_root, tmp_path / "project")
    p = root / LOCKED_PATHS["method_eligibility_summary.csv"]
    rows = list(csv.DictReader(p.open(newline="", encoding="utf-8")))
    fields = list(rows[0])
    for row in rows:
        if row["well_key"] == "Poseidon_2" and row["mask_name"] == "eligible_sonic_nct_candidate":
            row["n_eligible"] = "0"
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    with pytest.raises(PorePressureInputError, match="disagree"):
        run_pore_pressure_workflow(root, render_png=False)


def test_unknown_overburden_well_fails(project_root, tmp_path):
    root = copy_minimal_project(project_root, tmp_path / "project")
    p = root / LOCKED_PATHS["overburden_eligibility_summary.csv"]
    rows = list(csv.DictReader(p.open(newline="", encoding="utf-8")))
    fields = list(rows[0]); rows[0]["well_key"] = "Unknown"
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    with pytest.raises(PorePressureInputError, match="unknown"):
        run_pore_pressure_workflow(root, render_png=False)


def test_absolute_stress_claim_change_fails(project_root, tmp_path):
    root = copy_minimal_project(project_root, tmp_path / "project")
    p = root / LOCKED_PATHS["overburden_eligibility_summary.csv"]
    rows = list(csv.DictReader(p.open(newline="", encoding="utf-8")))
    fields = list(rows[0]); rows[0]["absolute_stress_supported"] = "True"
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    with pytest.raises(PorePressureInputError, match="expects no well"):
        run_pore_pressure_workflow(root, render_png=False)


def test_duplicate_drift_record_fails(project_root, tmp_path):
    root = copy_minimal_project(project_root, tmp_path / "project")
    p = root / LOCKED_PATHS["sonic_checkshot_drift_summary.csv"]
    text = p.read_text(encoding="utf-8")
    header, row = text.strip().splitlines()
    p.write_text(header + "\n" + row + "\n" + row + "\n", encoding="utf-8")
    with pytest.raises(PorePressureInputError, match="one Poseidon 2"):
        run_pore_pressure_workflow(root, render_png=False)


def test_workflow_is_repeatable_in_place(project_root, tmp_path):
    root = copy_minimal_project(project_root, tmp_path / "project")
    run_pore_pressure_workflow(root, render_png=False)
    first = {p.name: p.read_bytes() for p in (root / "outputs/08_pore_pressure_effective_stress").iterdir()}
    run_pore_pressure_workflow(root, render_png=False)
    second = {p.name: p.read_bytes() for p in (root / "outputs/08_pore_pressure_effective_stress").iterdir()}
    assert first == second


@pytest.mark.parametrize("source_name", tuple(LOCKED_PATHS))
def test_every_locked_source_is_bound_to_its_exact_approved_hash(
        project_root, tmp_path, source_name):
    root = copy_minimal_project(project_root, tmp_path / "project")
    path = root / LOCKED_PATHS[source_name]
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(PorePressureInputError, match="exact approved locked inputs"):
        run_pore_pressure_workflow(root, render_png=False)
    assert not (root / "outputs/08_pore_pressure_effective_stress").exists()


def test_expected_hash_registry_matches_packaged_sources(project_root):
    observed = {
        name: hashlib.sha256((project_root / relative).read_bytes()).hexdigest()
        for name, relative in LOCKED_PATHS.items()
    }
    assert observed == EXPECTED_LOCKED_SOURCE_SHA256


def test_default_figure_runtime_dependency_is_declared(project_root):
    text = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    assert '"matplotlib>=3.7"' in text


def test_drift_identity_mutation_is_rejected_before_publication(project_root, tmp_path):
    root = copy_minimal_project(project_root, tmp_path / "project")
    path = root / LOCKED_PATHS["sonic_checkshot_drift_summary.csv"]
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    fields = list(rows[0])
    rows[0]["sonic_minus_checkshot_ms"] = "16.0"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    with pytest.raises(PorePressureInputError, match="drift identities"):
        run_pore_pressure_workflow(root, render_png=False)
    assert not (root / "outputs/08_pore_pressure_effective_stress").exists()


def test_shallow_component_mutation_is_rejected_before_publication(project_root, tmp_path):
    root = copy_minimal_project(project_root, tmp_path / "project")
    path = root / LOCKED_PATHS["shallow_column_scenarios.csv"]
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    fields = list(rows[0])
    rows[0]["water_column_stress_pa"] = str(
        float(rows[0]["water_column_stress_pa"]) + 1.0)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    with pytest.raises(PorePressureInputError, match="components do not sum"):
        run_pore_pressure_workflow(root, render_png=False)


def test_profile_cumulative_decrease_is_rejected_before_publication(project_root, tmp_path):
    root = copy_minimal_project(project_root, tmp_path / "project")
    path = root / LOCKED_PATHS["vertical_stress_profile.csv"]
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    fields = list(rows[0])
    rows[1]["cumulative_measured_increment_pa"] = "-1"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    with pytest.raises(PorePressureInputError, match="finite numeric domain"):
        run_pore_pressure_workflow(root, render_png=False)


def _snapshot_files(root: Path):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*") if path.is_file()
    }


def test_figure_failure_leaves_previous_complete_bundle_byte_identical(
        project_root, tmp_path, monkeypatch):
    root = copy_minimal_project(project_root, tmp_path / "project")
    result = run_pore_pressure_workflow(root, render_png=True)
    before = _snapshot_files(result["output_dir"])

    def fail_render(*_args, **_kwargs):
        raise RuntimeError("injected figure failure")

    monkeypatch.setattr(workflow_module, "render_figures", fail_render)
    with pytest.raises(RuntimeError, match="injected figure failure"):
        run_pore_pressure_workflow(root, render_png=True)
    assert _snapshot_files(result["output_dir"]) == before
    assert not list(result["output_dir"].parent.glob(
        ".08_pore_pressure_effective_stress.bundle-*"))


def test_bundle_publication_failure_rolls_back_without_residue(
        project_root, tmp_path, monkeypatch):
    root = copy_minimal_project(project_root, tmp_path / "project")
    result = run_pore_pressure_workflow(root, render_png=True)
    before = _snapshot_files(result["output_dir"])
    real_replace = workflow_module.os.replace

    def fail_candidate_publish(source, destination):
        if Path(source).name == "candidate" and Path(destination) == result["output_dir"]:
            raise OSError("injected bundle publication failure")
        return real_replace(source, destination)

    monkeypatch.setattr(workflow_module.os, "replace", fail_candidate_publish)
    with pytest.raises(OSError, match="injected bundle publication failure"):
        run_pore_pressure_workflow(root, render_png=True)
    assert _snapshot_files(result["output_dir"]) == before
    parent = result["output_dir"].parent
    assert not list(parent.glob(".08_pore_pressure_effective_stress.bundle-*"))
    assert not list(parent.glob(".08_pore_pressure_effective_stress.backup-*"))
