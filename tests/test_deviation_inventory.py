"""
tests/test_deviation_inventory.py - Validation suite for
p2mem.io.deviation_inventory (Increment 3.1 addition).

Portable, synthetic-data unit tests only - no real project file required.

These tests exist specifically to guard the Increment 3.1 corrective-patch
fix: no row built by this module (for a successful well OR a failed one)
may embed a full, environment-dependent filesystem path (a Colab Drive
mount path, a local development build path, a CI temp directory) - only
a file's basename may appear, in `source_filename` and `context` fields,
and any embedded exception message must have its own copy of the path
reduced to a basename too.
"""

import dataclasses

import numpy as np

from p2mem.deviation_models import (
    DepthBasisSelection,
    DeviationFileContract,
    DeviationHeaderInfo,
    DeviationIngestionFailure,
    DeviationIngestionIssue,
    DeviationStationData,
    DeviationWellResult,
    TrajectoryValidationResult,
)
from p2mem.io.deviation_inventory import (
    build_deviation_depth_manifest,
    build_deviation_file_inventory_rows,
    build_deviation_issues_rows,
    build_depth_reference_register_rows,
    build_trajectory_validation_rows,
)
from p2mem.trajectory import compute_minimum_curvature_trajectory

# A deliberately absolute, environment-looking path - mirrors what a real
# build (or a real Colab Drive mount) would embed if not sanitized.
_FAKE_ABSOLUTE_DIR = "/home/fake_build_env/p2mem_build/data/raw/deviation"
_FAKE_BASENAME = "Poseidon 2_dev.txt"
_FAKE_ABSOLUTE_PATH = f"{_FAKE_ABSOLUTE_DIR}/{_FAKE_BASENAME}"


def _make_well_result(source_path: str, source_filename: str) -> DeviationWellResult:
    md = np.array([0.0, 100.0, 200.0])
    incl = np.array([0.0, 5.0, 10.0])
    azim = np.array([0.0, 30.0, 30.0])
    mc = compute_minimum_curvature_trajectory(
        md, incl, azim, tvd_origin_m=0.0, northing_origin_m=0.0, easting_origin_m=0.0
    )
    stations = DeviationStationData(
        MD_source_m=md,
        X_source_m=np.zeros_like(md),
        Y_source_m=np.zeros_like(md),
        Z_source_m=20.0 - mc.tvd_mc_m,
        TVD_source_m=mc.tvd_mc_m.copy(),
        DX_source_m=mc.easting_offset_mc_m.copy(),
        DY_source_m=mc.northing_offset_mc_m.copy(),
        AZIM_TN_source_deg=azim.copy(),
        INCL_source_deg=incl,
        DLS_source_deg_per_30m=mc.dls_deg_per_30m,
        AZIM_GN_source_deg=azim,
    )
    header = DeviationHeaderInfo(
        source_path=source_path,
        source_filename=source_filename,
        sha256="0" * 64,
        well_name="Poseidon 2",
        survey_name="Explicit survey 1",
        wellhead_x_m=0.0,
        wellhead_y_m=0.0,
        datum_elevation_m=20.0,
        datum_reference="RT, Rotary table, from MSL",
        well_type="GAS",
        coordinate_reference_system="TEST",
        depth_reference_statement="test",
        angle_unit_statement="DEGREES",
        dx_dy_statement="m-UNITS",
        z_statement="m-UNITS",
        column_names=("MD", "X", "Y", "Z", "TVD", "DX", "DY", "AZIM_TN", "INCL", "DLS", "AZIM_GN"),
        header_line_count=16,
        data_line_offset=17,
    )
    contract = DeviationFileContract(
        source_filename=source_filename,
        expected_sha256="0" * 64,
        expected_well_identifier="Poseidon 2",
        expected_survey_identifier="Explicit survey 1",
        expected_coordinate_reference_system="TEST",
        expected_wellhead_x_m=0.0,
        expected_wellhead_y_m=0.0,
        expected_datum_m=20.0,
        expected_datum_reference="RT, Rotary table, from MSL",
        expected_column_count=11,
        expected_column_order=("MD", "X", "Y", "Z", "TVD", "DX", "DY", "AZIM_TN", "INCL", "DLS", "AZIM_GN"),
        expected_units={},
        expected_station_count=int(md.size),
        expected_md_min_m=float(md[0]),
        expected_md_max_m=float(md[-1]),
        azimuth_reference_for_grid_coordinates="AZIM_GN",
        source_depth_convention="test",
        header_tolerance_m=0.001,
        residual_tolerance_tvd_m=0.01,
        residual_tolerance_horizontal_m=0.01,
        residual_fail_threshold_m=5.0,
        depth_basis_policy="petrel_source_trace",
        notes="synthetic",
    )
    validation = TrajectoryValidationResult(
        well_key="Poseidon 2",
        comparison_basis="synthetic self-consistent fixture",
        tvd_max_abs_residual_m=0.0, tvd_mean_residual_m=0.0, tvd_rmse_m=0.0,
        tvd_endpoint_residual_m=0.0, tvd_tolerance_m=0.01, tvd_status="PASS",
        easting_max_abs_residual_m=0.0, easting_mean_residual_m=0.0, easting_rmse_m=0.0,
        easting_endpoint_residual_m=0.0, easting_tolerance_m=0.01, easting_status="PASS",
        northing_max_abs_residual_m=0.0, northing_mean_residual_m=0.0, northing_rmse_m=0.0,
        northing_endpoint_residual_m=0.0, northing_tolerance_m=0.01, northing_status="PASS",
        x_consistency_max_abs_residual_m=0.0, x_consistency_status="PASS",
        y_consistency_max_abs_residual_m=0.0, y_consistency_status="PASS",
        z_consistency_max_abs_residual_m=0.0, z_consistency_status="PASS",
        overall_status="PASS",
        origin_initialization_note="synthetic",
    )
    depth_basis_sel = DepthBasisSelection(
        well_key="Poseidon 2", selected_basis="petrel_source_trace", rationale="test"
    )
    issues = (
        DeviationIngestionIssue("WARNING", "MD_UNIT_NOT_EXPLICITLY_DECLARED", "test warning", source_filename),
    )
    return DeviationWellResult(
        header=header, contract=contract, raw=stations, mc=mc,
        validation=validation, depth_basis=depth_basis_sel, issues=issues,
    )


def _flatten_values(obj):
    """Recursively yield every string value found in a dict/list/scalar tree."""
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _flatten_values(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _flatten_values(v)
    elif isinstance(obj, str):
        yield obj


# ---------------------------------------------------------------------------
# Successful wells: source_filename / context must be basenames only
# ---------------------------------------------------------------------------
def test_successful_well_file_inventory_row_has_no_absolute_path():
    well = _make_well_result(_FAKE_ABSOLUTE_PATH, _FAKE_BASENAME)
    rows = build_deviation_file_inventory_rows({"Poseidon_2": well}, {})
    assert len(rows) == 1
    assert rows[0]["source_filename"] == _FAKE_BASENAME
    for value in _flatten_values(rows):
        assert _FAKE_ABSOLUTE_DIR not in value
        assert "/home" not in value


def test_successful_well_issues_row_context_has_no_absolute_path():
    well = _make_well_result(_FAKE_ABSOLUTE_PATH, _FAKE_BASENAME)
    rows = build_deviation_issues_rows({"Poseidon_2": well}, {})
    assert len(rows) == 1
    assert rows[0]["context"] == _FAKE_BASENAME
    for value in _flatten_values(rows):
        assert _FAKE_ABSOLUTE_DIR not in value


def test_manifest_and_register_rows_have_no_absolute_path():
    well = _make_well_result(_FAKE_ABSOLUTE_PATH, _FAKE_BASENAME)
    manifest = build_deviation_depth_manifest({"Poseidon_2": well}, {}, {})
    register_rows = build_depth_reference_register_rows({"Poseidon_2": well})
    validation_rows = build_trajectory_validation_rows({"Poseidon_2": well})
    for value in _flatten_values(manifest):
        assert _FAKE_ABSOLUTE_DIR not in value
    for value in _flatten_values(register_rows):
        assert _FAKE_ABSOLUTE_DIR not in value
    for value in _flatten_values(validation_rows):
        assert _FAKE_ABSOLUTE_DIR not in value


# ---------------------------------------------------------------------------
# Failed wells: source_filename / context / error_message must all be
# sanitized to a basename, even though the underlying exception message
# embeds the full path.
# ---------------------------------------------------------------------------
def _make_failure() -> DeviationIngestionFailure:
    return DeviationIngestionFailure(
        well_key="Poseidon_2",
        source_path=_FAKE_ABSOLUTE_PATH,
        error_type="file_not_found",
        message=f"Deviation-survey file not found: {_FAKE_ABSOLUTE_PATH}",
        exception=FileNotFoundError(_FAKE_ABSOLUTE_PATH),
    )


def test_failed_well_file_inventory_row_sanitizes_path_and_message():
    failure = _make_failure()
    rows = build_deviation_file_inventory_rows({}, {"Poseidon_2": failure})
    assert len(rows) == 1
    row = rows[0]
    assert row["source_filename"] == _FAKE_BASENAME
    assert _FAKE_ABSOLUTE_DIR not in row["error_message"]
    assert _FAKE_BASENAME in row["error_message"]  # basename preserved, path scrubbed


def test_failed_well_issues_row_sanitizes_path_and_message():
    failure = _make_failure()
    rows = build_deviation_issues_rows({}, {"Poseidon_2": failure})
    assert len(rows) == 1
    row = rows[0]
    assert row["source_filename"] == _FAKE_BASENAME
    assert row["context"] == _FAKE_BASENAME
    assert _FAKE_ABSOLUTE_DIR not in row["message"]
    assert _FAKE_BASENAME in row["message"]


def test_failed_well_manifest_sanitizes_message():
    failure = _make_failure()
    manifest = build_deviation_depth_manifest({}, {"Poseidon_2": failure}, {})
    assert "Poseidon_2" in manifest["failed_wells"]
    entry = manifest["failed_wells"]["Poseidon_2"]
    assert _FAKE_ABSOLUTE_DIR not in entry["message"]
    assert _FAKE_BASENAME in entry["message"]
