"""One deterministic, locked-output workflow for Increment 8."""

import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Dict
import uuid

from p2mem.pore_pressure import load_pressure_config
from p2mem.pore_pressure_models import PorePressureInputError
from p2mem.io.pore_pressure_inventory import (
    FIGURE_NAMES, OUTPUT_NAMES, build_payloads, export_payloads, read_locked_csv,
    render_figures, sha256_file,
)


LOCKED_PATHS = {
    "vertical_stress_profile.csv": "outputs/07_density_overburden/vertical_stress_profile.csv",
    "shallow_column_scenarios.csv": "outputs/07_density_overburden/shallow_column_scenarios.csv",
    "overburden_eligibility_summary.csv": "outputs/07_density_overburden/overburden_eligibility_summary.csv",
    "method_eligibility_summary.csv": "outputs/06_petrophysics_eligibility/method_eligibility_summary.csv",
    "thickness_sensitivity_summary.csv": "outputs/06_petrophysics_eligibility/thickness_sensitivity_summary.csv",
    "petrophysics_eligibility_manifest.json": "outputs/06_petrophysics_eligibility/petrophysics_eligibility_manifest.json",
    "sonic_checkshot_drift_summary.csv": "outputs/04_checkshot_time_depth/sonic_checkshot_drift_summary.csv",
}


def _publish_complete_bundle(payloads, destination: Path,
                             *, render_png: bool) -> tuple[str, ...]:
    """Stage data and figures together, then replace the official directory once.

    A serializer, plotting, or publication failure leaves the previous complete
    directory byte-for-byte intact and removes all temporary state.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(
        prefix=f".{destination.name}.bundle-", dir=str(destination.parent)))
    candidate = workspace / "candidate"
    backup = None
    try:
        export_payloads(payloads, candidate)
        figures = render_figures(payloads, candidate) if render_png else ()
        expected_files = set(OUTPUT_NAMES)
        if render_png:
            expected_files.update(f"figures/{name}" for name in FIGURE_NAMES)
        actual_files = {
            path.relative_to(candidate).as_posix()
            for path in candidate.rglob("*") if path.is_file()
        }
        if actual_files != expected_files:
            raise PorePressureInputError(
                "Complete Increment 8 output-bundle inventory is not exact.")
        if destination.exists():
            if not destination.is_dir():
                raise PorePressureInputError(
                    "Increment 8 output destination exists but is not a directory.")
            backup = destination.parent / (
                f".{destination.name}.backup-{uuid.uuid4().hex}")
            os.replace(destination, backup)
        try:
            os.replace(candidate, destination)
        except Exception:
            if backup is not None and backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        if backup is not None and backup.exists():
            shutil.rmtree(backup)
        return figures
    finally:
        if workspace.exists():
            shutil.rmtree(workspace)


def run_pore_pressure_workflow(project_root, *, render_png: bool = True) -> Dict[str, object]:
    """Build Increment 8 exclusively from packaged, locked upstream outputs."""
    root = Path(project_root)
    if not root.is_dir():
        raise PorePressureInputError("project_root must be an existing directory.")
    config_path = root / "config/pore_pressure.yml"
    config = load_pressure_config(config_path)
    paths = {name: root / rel for name, rel in LOCKED_PATHS.items()}
    for path in paths.values():
        if not path.is_file():
            raise PorePressureInputError(f"Locked source artifact is missing: {path.name!r}.")

    # Parse the upstream manifest too: a syntactically invalid locked record is
    # a hard failure even though no individual value is consumed from it.
    try:
        upstream_manifest = json.loads(
            paths["petrophysics_eligibility_manifest.json"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PorePressureInputError("Locked petrophysics manifest is malformed.") from exc
    calibration = upstream_manifest.get("calibration_data_available")
    required_flags = (
        "pressure_rft_mdt_dst", "stress_fit_lot_xlot_dfit",
        "independent_vp_vs_calibration",
    )
    if not isinstance(calibration, dict) or any(
            calibration.get(name) is not False for name in required_flags):
        raise PorePressureInputError(
            "Locked petrophysics manifest does not support the zero-calibration premise.")

    payloads = build_payloads(
        config=config,
        profile_rows=read_locked_csv(paths["vertical_stress_profile.csv"]),
        shallow_rows=read_locked_csv(paths["shallow_column_scenarios.csv"]),
        overburden_rows=read_locked_csv(paths["overburden_eligibility_summary.csv"]),
        method_rows=read_locked_csv(paths["method_eligibility_summary.csv"]),
        thickness_rows=read_locked_csv(paths["thickness_sensitivity_summary.csv"]),
        drift_rows=read_locked_csv(paths["sonic_checkshot_drift_summary.csv"]),
        source_hashes={name: sha256_file(path) for name, path in paths.items()},
    )
    output_dir = root / "outputs/08_pore_pressure_effective_stress"
    figures = _publish_complete_bundle(
        payloads, output_dir, render_png=render_png)
    return {"config": config, "payloads": payloads,
            "output_dir": output_dir, "figures": figures}
