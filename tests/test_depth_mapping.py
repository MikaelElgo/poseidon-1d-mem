"""
tests/test_depth_mapping.py - Validation suite for p2mem.depth_mapping
(Increment 3: MD-to-TVD/TVDSS interpolation and coverage checks).

Portable, synthetic-data unit tests only - no real project file required.
"""

import numpy as np
import pytest

from p2mem.deviation_models import (
    DEPTH_BASIS_MINIMUM_CURVATURE,
    DEPTH_BASIS_PETREL_SOURCE,
    DepthBasisSelection,
    DeviationFileContract,
    DeviationHeaderInfo,
    DeviationStationData,
    DeviationWellResult,
    TrajectoryValidationResult,
)
from p2mem.depth_mapping import (
    DepthMappingError,
    ExtrapolationRejectedError,
    INTERPOLATION_METHOD,
    map_las_md_to_tvd_tvdss,
    select_survey_trajectory_for_mapping,
)
from p2mem.trajectory import compute_minimum_curvature_trajectory


def _make_well_result(
    md, incl, azim_gn, datum_elevation_m=20.0, depth_basis=DEPTH_BASIS_PETREL_SOURCE
) -> DeviationWellResult:
    md = np.asarray(md, dtype=np.float64)
    incl = np.asarray(incl, dtype=np.float64)
    azim_gn = np.asarray(azim_gn, dtype=np.float64)

    mc = compute_minimum_curvature_trajectory(
        md, incl, azim_gn, tvd_origin_m=float(md[0]), northing_origin_m=0.0, easting_origin_m=0.0
    )
    # Use the MC trajectory itself as the "source" TVD too, for a
    # self-consistent synthetic fixture (depth-mapping tests do not need
    # to exercise the trajectory-residual comparison - that's covered in
    # test_deviation.py).
    stations = DeviationStationData(
        MD_source_m=md,
        X_source_m=np.zeros_like(md),
        Y_source_m=np.zeros_like(md),
        Z_source_m=datum_elevation_m - mc.tvd_mc_m,
        TVD_source_m=mc.tvd_mc_m.copy(),
        DX_source_m=mc.easting_offset_mc_m.copy(),
        DY_source_m=mc.northing_offset_mc_m.copy(),
        AZIM_TN_source_deg=azim_gn.copy(),
        INCL_source_deg=incl,
        DLS_source_deg_per_30m=mc.dls_deg_per_30m,
        AZIM_GN_source_deg=azim_gn,
    )
    header = DeviationHeaderInfo(
        source_path="synthetic",
        source_filename="synthetic_dev.txt",
        sha256="0" * 64,
        well_name="Synthetic Well",
        survey_name="Synthetic survey",
        wellhead_x_m=0.0,
        wellhead_y_m=0.0,
        datum_elevation_m=datum_elevation_m,
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
        source_filename="synthetic_dev.txt",
        expected_sha256="0" * 64,
        expected_well_identifier="Synthetic Well",
        expected_survey_identifier="Synthetic survey",
        expected_coordinate_reference_system="TEST",
        expected_wellhead_x_m=0.0,
        expected_wellhead_y_m=0.0,
        expected_datum_m=datum_elevation_m,
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
        depth_basis_policy=depth_basis,
        notes="synthetic",
    )
    validation = TrajectoryValidationResult(
        well_key="Synthetic Well",
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
        well_key="Synthetic Well", selected_basis=depth_basis, rationale="test"
    )
    return DeviationWellResult(
        header=header, contract=contract, raw=stations, mc=mc,
        validation=validation, depth_basis=depth_basis_sel,
    )


# ---------------------------------------------------------------------------
# Basis selection
# ---------------------------------------------------------------------------
def test_select_petrel_source_basis_returns_source_arrays():
    well = _make_well_result([0.0, 100.0, 500.0], [0.0, 5.0, 10.0], [0.0, 30.0, 30.0])
    md, tvd, basis = select_survey_trajectory_for_mapping(well)
    assert basis == DEPTH_BASIS_PETREL_SOURCE
    assert np.array_equal(md, well.raw.MD_source_m)
    assert np.array_equal(tvd, well.raw.TVD_source_m)


def test_select_minimum_curvature_basis_returns_mc_arrays():
    well = _make_well_result(
        [0.0, 100.0, 500.0], [0.0, 5.0, 10.0], [0.0, 30.0, 30.0],
        depth_basis=DEPTH_BASIS_MINIMUM_CURVATURE,
    )
    md, tvd, basis = select_survey_trajectory_for_mapping(well)
    assert basis == DEPTH_BASIS_MINIMUM_CURVATURE
    assert np.array_equal(tvd, well.mc.tvd_mc_m)


# ---------------------------------------------------------------------------
# Mapping correctness
# ---------------------------------------------------------------------------
def test_exact_preservation_at_survey_stations():
    well = _make_well_result([0.0, 200.0, 400.0, 600.0], [0.0, 10.0, 15.0, 15.0], [0.0, 45.0, 45.0, 45.0])
    las_md = well.raw.MD_source_m.copy()  # sample exactly at the survey stations
    mapping = map_las_md_to_tvd_tvdss("WELL_A", las_md, well)
    assert np.allclose(mapping.tvd_mapped_m, well.raw.TVD_source_m, atol=1e-9)


def test_deterministic_interpolation_repeated_calls_agree():
    well = _make_well_result([0.0, 200.0, 400.0, 600.0], [0.0, 10.0, 15.0, 15.0], [0.0, 45.0, 45.0, 45.0])
    las_md = np.linspace(10.0, 590.0, 50)
    m1 = map_las_md_to_tvd_tvdss("WELL_A", las_md, well)
    m2 = map_las_md_to_tvd_tvdss("WELL_A", las_md, well)
    assert np.array_equal(m1.tvd_mapped_m, m2.tvd_mapped_m)


def test_monotonic_mapped_tvd_for_monotonic_survey():
    well = _make_well_result([0.0, 200.0, 400.0, 600.0], [0.0, 10.0, 15.0, 15.0], [0.0, 45.0, 45.0, 45.0])
    las_md = np.linspace(1.0, 599.0, 100)
    mapping = map_las_md_to_tvd_tvdss("WELL_A", las_md, well)
    assert np.all(np.diff(mapping.tvd_mapped_m) >= 0.0)


def test_exact_sample_count_preservation():
    well = _make_well_result([0.0, 200.0, 400.0], [0.0, 10.0, 10.0], [0.0, 45.0, 45.0])
    las_md = np.linspace(5.0, 395.0, 137)
    mapping = map_las_md_to_tvd_tvdss("WELL_A", las_md, well)
    assert mapping.n_samples == 137
    assert mapping.tvd_mapped_m.shape == (137,)
    assert mapping.tvdss_mapped_m.shape == (137,)


def test_selected_depth_basis_recorded_in_result():
    well = _make_well_result(
        [0.0, 200.0], [0.0, 10.0], [0.0, 45.0], depth_basis=DEPTH_BASIS_MINIMUM_CURVATURE
    )
    mapping = map_las_md_to_tvd_tvdss("WELL_A", np.array([100.0]), well)
    assert mapping.depth_basis_used == DEPTH_BASIS_MINIMUM_CURVATURE
    assert mapping.interpolation_method == INTERPOLATION_METHOD


def test_las_md_source_never_modified():
    well = _make_well_result([0.0, 200.0, 400.0], [0.0, 10.0, 10.0], [0.0, 45.0, 45.0])
    las_md = np.array([50.0, 150.0, 350.0])
    original = las_md.copy()
    mapping = map_las_md_to_tvd_tvdss("WELL_A", las_md, well)
    assert np.array_equal(las_md, original)
    assert np.array_equal(mapping.las_md_source_m, original)


# ---------------------------------------------------------------------------
# Extrapolation rejection
# ---------------------------------------------------------------------------
def test_upper_bound_extrapolation_rejected():
    well = _make_well_result([0.0, 200.0, 400.0], [0.0, 10.0, 10.0], [0.0, 45.0, 45.0])
    las_md = np.array([100.0, 450.0])  # 450 > survey max of 400
    with pytest.raises(ExtrapolationRejectedError, match="above-coverage margin"):
        map_las_md_to_tvd_tvdss("WELL_A", las_md, well)


def test_lower_bound_extrapolation_rejected():
    well = _make_well_result([50.0, 200.0, 400.0], [0.0, 10.0, 10.0], [0.0, 45.0, 45.0])
    las_md = np.array([10.0, 100.0])  # 10 < survey min of 50
    with pytest.raises(ExtrapolationRejectedError, match="below-coverage margin"):
        map_las_md_to_tvd_tvdss("WELL_A", las_md, well)


def test_no_extrapolation_when_fully_inside_coverage():
    well = _make_well_result([0.0, 200.0, 400.0], [0.0, 10.0, 10.0], [0.0, 45.0, 45.0])
    las_md = np.array([50.0, 150.0, 350.0])
    mapping = map_las_md_to_tvd_tvdss("WELL_A", las_md, well)
    assert mapping.n_extrapolated == 0
    assert mapping.coverage_margin_lower_m >= 0.0
    assert mapping.coverage_margin_upper_m >= 0.0


def test_exact_boundary_md_is_not_extrapolation():
    well = _make_well_result([0.0, 200.0, 400.0], [0.0, 10.0, 10.0], [0.0, 45.0, 45.0])
    las_md = np.array([0.0, 400.0])  # exactly at survey bounds
    mapping = map_las_md_to_tvd_tvdss("WELL_A", las_md, well)
    assert mapping.n_extrapolated == 0


# ---------------------------------------------------------------------------
# Depth-reference sign convention (TVDSS)
# ---------------------------------------------------------------------------
def test_tvdss_sign_convention_tvd_minus_datum():
    well = _make_well_result([0.0, 200.0, 400.0], [0.0, 10.0, 10.0], [0.0, 45.0, 45.0], datum_elevation_m=25.0)
    las_md = np.array([100.0, 300.0])
    mapping = map_las_md_to_tvd_tvdss("WELL_A", las_md, well)
    assert np.allclose(mapping.tvdss_mapped_m, mapping.tvd_mapped_m - 25.0, atol=1e-9)


def test_tvdss_equals_negative_z_for_source_basis():
    # Z_m = DatumElevation_m - TVD_m  =>  TVDSS_m = TVD_m - DatumElevation_m = -Z_m
    well = _make_well_result([0.0, 200.0, 400.0], [0.0, 10.0, 10.0], [0.0, 45.0, 45.0], datum_elevation_m=18.5)
    las_md = well.raw.MD_source_m.copy()
    mapping = map_las_md_to_tvd_tvdss("WELL_A", las_md, well)
    z_at_stations = well.raw.Z_source_m
    assert np.allclose(mapping.tvdss_mapped_m, -z_at_stations, atol=1e-9)


def test_positive_and_negative_tvdss_near_wellhead():
    # A shallow LAS sample above the datum-referenced sea-level crossing
    # point yields negative TVDSS (above MSL); a deep sample yields
    # positive TVDSS (below MSL).
    datum = 20.0  # 20 m above MSL
    well = _make_well_result([0.0, 15.0, 100.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], datum_elevation_m=datum)
    las_md = np.array([5.0, 50.0])  # TVD == MD here (vertical well)
    mapping = map_las_md_to_tvd_tvdss("WELL_A", las_md, well)
    assert mapping.tvdss_mapped_m[0] < 0.0  # 5 m TVD - 20 m datum = -15 m (above MSL)
    assert mapping.tvdss_mapped_m[1] > 0.0  # 50 m TVD - 20 m datum = +30 m (below MSL)


# ---------------------------------------------------------------------------
# Structural failure handling
# ---------------------------------------------------------------------------
def test_non_increasing_survey_md_raises_depth_mapping_error():
    well = _make_well_result([0.0, 200.0, 400.0], [0.0, 10.0, 10.0], [0.0, 45.0, 45.0])
    # Corrupt the survey MD post-construction to simulate a non-increasing basis.
    import dataclasses

    bad_stations = dataclasses.replace(well.raw, MD_source_m=np.array([0.0, 400.0, 200.0]))
    bad_well = dataclasses.replace(well, raw=bad_stations)
    with pytest.raises(DepthMappingError, match="strictly increasing"):
        map_las_md_to_tvd_tvdss("WELL_A", np.array([100.0]), bad_well)


def test_empty_las_md_rejected():
    well = _make_well_result([0.0, 200.0, 400.0], [0.0, 10.0, 10.0], [0.0, 45.0, 45.0])
    with pytest.raises(DepthMappingError, match="non-empty"):
        map_las_md_to_tvd_tvdss("WELL_A", np.array([]), well)


def test_non_finite_las_md_rejected():
    well = _make_well_result([0.0, 200.0, 400.0], [0.0, 10.0, 10.0], [0.0, 45.0, 45.0])
    with pytest.raises(DepthMappingError, match="non-finite"):
        map_las_md_to_tvd_tvdss("WELL_A", np.array([100.0, np.nan]), well)
