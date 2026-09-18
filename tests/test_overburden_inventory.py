"""
Increment 7 - export builders, manifest construction, issue derivation, and
end-to-end determinism of the workflow.

All fixtures here are synthetic. The tests assert on the records that the
export path actually serializes.
"""

from __future__ import annotations

import copy
import json
import math

import numpy as np
import pytest

from p2mem.density_qc import load_overburden_config
from p2mem.io.overburden_inventory import (
    build_density_availability_rows, build_density_gap_rows, build_density_qc_rows,
    build_gap_threshold_sensitivity_rows, build_overburden_eligibility_rows,
    build_overburden_issue_rows, build_shallow_column_scenario_rows,
    build_vertical_stress_profile_rows, derive_overburden_issues,
)
from p2mem.io.overburden_policy import (
    export_authorized_outputs, validate_emitted_records,
)
from p2mem.io.overburden_registry import (
    AVAILABILITY, ELIGIBILITY, GAPS, ISSUE_CODES, ISSUES, NOT_IMPLEMENTED_TOKENS,
    OVERBURDEN_ARTIFACTS, OVERBURDEN_BUNDLE, OVERBURDEN_CSV_SCHEMAS,
    OVERBURDEN_MANIFEST_ARTIFACT, PROFILE, QC, SCENARIOS, SENSITIVITY,
)
from p2mem.io.overburden_workflow import (
    SeabedMarkerError, build_overburden_payloads, read_locked_seabed_markers,
    run_overburden_workflow,
)
from p2mem.overburden_models import (
    STATUS_ABSOLUTE, STATUS_PARTIAL_ONLY, STATUS_SENSITIVITY_ONLY,
)

from helpers_inc7 import CONFIG_PATH, overburden_config  # noqa: E402
from synthetic_inc7 import make_frame  # noqa: E402


# ---------------------------------------------------------------------------
# A small synthetic four-well set exercising three different statuses
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def synthetic_project(tmp_path_factory):
    """Four synthetic wells and a synthetic locked-marker table.

    Two wells carry a seabed marker (one reaching it, one far below it) and
    two do not, so the derived-status ladder is exercised end to end without
    touching any approved project data.
    """
    config = load_overburden_config(CONFIG_PATH)
    root = tmp_path_factory.mktemp("synthetic_project")
    markers = root / "markers.csv"
    markers.write_text(
        "well_key,canonical_marker_name,MDRT_reconciled_m,TVD_survey_m,"
        "TVDSS_survey_corrected_m\n"
        "Boreas_1,Sea Bed,500.0,500.0,475.0\n"
        "Poseidon_2,Sea Bed,500.0,500.0,475.0\n",
        encoding="utf-8")

    frames = {}
    # Reaches its own seabed: the only configuration supporting an absolute curve.
    md = np.arange(500.0, 1001.0, 10.0)
    frames["Boreas_1"] = make_frame(
        well_key="Boreas_1", md=md, density=np.full(md.size, 2000.0),
        datum_elevation_m=25.0)
    # Seabed known, log starts far below it: sensitivity-only.
    md = np.arange(2000.0, 2501.0, 10.0)
    frames["Poseidon_2"] = make_frame(
        well_key="Poseidon_2", md=md, density=np.full(md.size, 2300.0),
        datum_elevation_m=25.0)
    # No seabed marker: partial measured increment only.
    md = np.arange(1500.0, 2001.0, 10.0)
    rho = np.full(md.size, 2400.0)
    rho[10:12] = np.nan                     # a bridgeable short gap
    frames["Poseidon_North_1"] = make_frame(
        well_key="Poseidon_North_1", md=md, density=rho, datum_elevation_m=22.0)
    # No seabed marker, and a long internal gap.
    md = np.arange(1500.0, 2001.0, 10.0)
    rho = np.full(md.size, 2500.0)
    rho[20:25] = np.nan                     # 60 m TVD: far beyond the threshold
    frames["Proteus_1ST2"] = make_frame(
        well_key="Proteus_1ST2", md=md, density=rho, datum_elevation_m=21.8)

    run = run_overburden_workflow(frames, config, marker_table_path=str(markers))
    payloads = build_overburden_payloads(run)
    return {"config": config, "frames": frames, "run": run, "payloads": payloads,
            "root": root, "markers": str(markers)}


def test_the_synthetic_set_exercises_three_derived_statuses(synthetic_project):
    statuses = {wk: e.status
                for wk, e in synthetic_project["run"].eligibility.items()}
    assert statuses["Boreas_1"] == STATUS_ABSOLUTE
    assert statuses["Poseidon_2"] == STATUS_SENSITIVITY_ONLY
    assert statuses["Poseidon_North_1"] == STATUS_PARTIAL_ONLY
    assert statuses["Proteus_1ST2"] == STATUS_PARTIAL_ONLY


# ---------------------------------------------------------------------------
# Seabed marker reading
# ---------------------------------------------------------------------------

def test_a_missing_locked_marker_table_fails_closed(tmp_path):
    with pytest.raises(SeabedMarkerError, match="missing or not a file"):
        read_locked_seabed_markers(str(tmp_path / "absent.csv"), "Sea Bed")


def test_a_well_absent_from_the_marker_table_gets_no_seabed(synthetic_project):
    markers = read_locked_seabed_markers(synthetic_project["markers"], "Sea Bed")
    assert set(markers) == {"Boreas_1", "Poseidon_2"}
    assert "Poseidon_North_1" not in markers


def test_a_malformed_matching_marker_row_fails_closed(tmp_path):
    path = tmp_path / "markers.csv"
    path.write_text(
        "well_key,canonical_marker_name,MDRT_reconciled_m,TVD_survey_m,"
        "TVDSS_survey_corrected_m\n"
        "A_1,Sea Bed,not_a_number,500.0,475.0\n"
        "B_1,Sea Bed,500.0,500.0,475.0\n",
        encoding="utf-8")
    with pytest.raises(SeabedMarkerError, match="row 2 is malformed"):
        read_locked_seabed_markers(str(path), "Sea Bed")


def test_duplicate_matching_marker_rows_fail_closed(tmp_path):
    path = tmp_path / "markers.csv"
    path.write_text(
        "well_key,canonical_marker_name,MDRT_reconciled_m,TVD_survey_m,"
        "TVDSS_survey_corrected_m\n"
        "A_1,Sea Bed,500.0,500.0,475.0\n"
        "A_1,Sea Bed,501.0,501.0,476.0\n",
        encoding="utf-8")
    with pytest.raises(SeabedMarkerError, match="duplicate"):
        read_locked_seabed_markers(str(path), "Sea Bed")


@pytest.mark.parametrize("bad", ["NaN", "Inf", "-Inf"])
def test_non_finite_matching_marker_values_fail_closed(tmp_path, bad):
    path = tmp_path / "markers.csv"
    path.write_text(
        "well_key,canonical_marker_name,MDRT_reconciled_m,TVD_survey_m,"
        "TVDSS_survey_corrected_m\n"
        f"A_1,Sea Bed,{bad},500.0,475.0\n",
        encoding="utf-8")
    with pytest.raises(SeabedMarkerError, match="row 2 is malformed"):
        read_locked_seabed_markers(str(path), "Sea Bed")


def test_header_only_valid_marker_table_is_an_explicit_empty_mapping(tmp_path):
    path = tmp_path / "markers.csv"
    path.write_text(
        "well_key,canonical_marker_name,MDRT_reconciled_m,TVD_survey_m,"
        "TVDSS_survey_corrected_m\n",
        encoding="utf-8")
    assert read_locked_seabed_markers(str(path), "Sea Bed") == {}


def test_locked_seabed_reader_preserves_small_survey_roundoff(tmp_path):
    path = tmp_path / "markers.csv"
    path.write_text(
        "well_key,canonical_marker_name,MDRT_reconciled_m,TVD_survey_m,"
        "TVDSS_survey_corrected_m\n"
        "Boreas_1,Sea Bed,513.7,513.7000114393325,491.9000114393325\n",
        encoding="utf-8")
    marker = read_locked_seabed_markers(str(path), "Sea Bed")["Boreas_1"]
    assert marker.mdrt_m == 513.7
    assert marker.tvd_m == 513.7000114393325


# ---------------------------------------------------------------------------
# Row builders: shape, order, and content
# ---------------------------------------------------------------------------

def test_every_csv_payload_has_exactly_its_schemas_ordered_columns(
        synthetic_project):
    payloads = synthetic_project["payloads"]
    for name, schema in OVERBURDEN_CSV_SCHEMAS.items():
        for row in payloads[name]:
            assert tuple(row.keys()) == schema.columns, name


def test_rows_are_ordered_by_well_key_then_by_index(synthetic_project):
    payloads = synthetic_project["payloads"]
    for name in (AVAILABILITY, QC, ELIGIBILITY):
        keys = [row["well_key"] for row in payloads[name]]
        assert keys == sorted(keys), name
    gap_keys = [(r["well_key"], r["gap_index"]) for r in payloads[GAPS]]
    assert gap_keys == sorted(gap_keys)
    prof_keys = [(r["well_key"], r["node_index"]) for r in payloads[PROFILE]]
    assert prof_keys == sorted(prof_keys)


def test_scenario_rows_appear_in_declared_scenario_order(synthetic_project):
    from p2mem.overburden_models import VALID_SCENARIO_NAMES
    order = {n: i for i, n in enumerate(VALID_SCENARIO_NAMES)}
    rows = synthetic_project["payloads"][SCENARIOS]
    assert rows, "the synthetic set must produce at least one scenario"
    positions = [order[r["scenario_name"]] for r in rows]
    assert positions == sorted(positions)


def test_scenarios_are_produced_only_for_the_sensitivity_only_well(
        synthetic_project):
    rows = synthetic_project["payloads"][SCENARIOS]
    assert {r["well_key"] for r in rows} == {"Poseidon_2"}
    assert len(rows) == 5


def test_qc_and_manifest_export_the_eligible_population_p05(synthetic_project):
    run = synthetic_project["run"]
    payloads = synthetic_project["payloads"]
    qc_by_well = {row["well_key"]: row for row in payloads[QC]}
    manifest = payloads[OVERBURDEN_MANIFEST_ARTIFACT]
    for well_key, stats in run.stats.items():
        assert (qc_by_well[well_key]["rhob_eligible_p05_kg_m3"]
                == stats.rhob_eligible_p05_kg_m3)
        assert (manifest["wells"][well_key]["rhob_eligible_p05_kg_m3"]
                == stats.rhob_eligible_p05_kg_m3)


def test_scenario_csv_and_manifest_export_identical_fraction_triplets(
        synthetic_project):
    payloads = synthetic_project["payloads"]
    rows = payloads[SCENARIOS]
    manifest_rows = payloads[OVERBURDEN_MANIFEST_ARTIFACT]["wells"][
        "Poseidon_2"]["shallow_column_scenarios"]
    assert len(rows) == len(manifest_rows)
    for row, manifest_row in zip(rows, manifest_rows):
        for field in ("assumed_fraction_of_total", "conditioned_fraction_of_total",
                      "measured_fraction_of_total"):
            assert row[field] == manifest_row[field]


def test_profile_nodes_are_selected_existing_samples_never_interpolated(
        synthetic_project):
    run = synthetic_project["run"]
    for row in synthetic_project["payloads"][PROFILE]:
        profile = run.profiles[row["well_key"]]
        tvdss = np.asarray(profile.tvdss_m)
        rho = np.asarray(profile.density_kg_m3)
        hits = np.flatnonzero(tvdss == row["tvdss_m"])
        assert hits.size >= 1
        assert float(rho[hits[0]]) == row["rhob_kg_m3"]


def test_profile_reporting_always_includes_the_first_and_last_node(
        synthetic_project):
    run = synthetic_project["run"]
    rows = synthetic_project["payloads"][PROFILE]
    for wk, profile in run.profiles.items():
        if profile is None:
            continue
        mine = [r for r in rows if r["well_key"] == wk]
        assert mine[0]["tvdss_m"] == profile.top_tvdss_m
        assert mine[-1]["tvdss_m"] == profile.base_tvdss_m
        assert mine[0]["cumulative_measured_increment_pa"] == 0.0
        assert math.isclose(mine[-1]["cumulative_measured_increment_pa"],
                            profile.total_measured_increment_pa, rel_tol=1e-12)


def test_a_bridged_profile_node_is_labelled_as_conditioned_not_measured(
        synthetic_project):
    rows = synthetic_project["payloads"][PROFILE]
    sources = {r["density_source"] for r in rows}
    assert sources <= {"measured_rhob", "bridged_linear_in_tvd"}
    for r in rows:
        if r["density_source"] == "bridged_linear_in_tvd":
            assert r["evidence_class"] == "assumed_configured"
        else:
            assert r["evidence_class"] == "measured"


def test_megapascal_columns_are_exactly_the_pascal_columns_over_1e6(
        synthetic_project):
    for row in synthetic_project["payloads"][ELIGIBILITY]:
        if row["measured_increment_pa"] is not None:
            assert math.isclose(row["measured_increment_mpa"],
                                row["measured_increment_pa"] / 1.0e6, rel_tol=1e-15)
    for row in synthetic_project["payloads"][SCENARIOS]:
        assert math.isclose(row["total_stress_mpa"],
                            row["total_stress_pa"] / 1.0e6, rel_tol=1e-15)


def test_scenario_rows_disclose_all_three_fractions_in_their_basis_text(
        synthetic_project):
    for row in synthetic_project["payloads"][SCENARIOS]:
        for field in ("assumed_fraction_of_total", "conditioned_fraction_of_total",
                      "measured_fraction_of_total"):
            pct = f"{100.0 * row[field]:.2f}"
            assert pct in row["scenario_basis"]
        assert math.isclose(
            row["assumed_fraction_of_total"]
            + row["conditioned_fraction_of_total"]
            + row["measured_fraction_of_total"], 1.0,
            rel_tol=1e-12, abs_tol=1e-12)
        assert "not a calibrated value" in row["scenario_basis"]


def test_every_sensitivity_threshold_appears_for_every_well(synthetic_project):
    config = synthetic_project["config"]
    rows = synthetic_project["payloads"][SENSITIVITY]
    for wk in synthetic_project["frames"]:
        mine = [r for r in rows if r["well_key"] == wk]
        assert [r["threshold_tvd_m"] for r in mine] == list(
            config.sensitivity_thresholds_tvd_m)
        assert sum(1 for r in mine if r["is_approved_threshold"]) == 1


def test_no_numpy_scalar_reaches_a_payload(synthetic_project):
    """The schema's pre-serialization type check accepts only exact int/float."""
    for name, schema in OVERBURDEN_CSV_SCHEMAS.items():
        for row in synthetic_project["payloads"][name]:
            for field in schema.integer_fields:
                assert row[field] is None or type(row[field]) is int, (name, field)
            for field in schema.number_fields:
                assert row[field] is None or type(row[field]) is float, (name, field)
            for field in schema.boolean_fields:
                assert type(row[field]) is bool, (name, field)


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

def test_every_derived_issue_code_is_declared(synthetic_project):
    for row in synthetic_project["payloads"][ISSUES]:
        assert row["code"] in ISSUE_CODES
        assert row["severity"] in ("INFO", "WARNING", "ERROR")


def test_issue_rows_are_deterministically_sorted(synthetic_project):
    rows = synthetic_project["payloads"][ISSUES]
    keys = [(r["severity"], r["code"], r["context"]) for r in rows]
    assert keys == sorted(keys)


def test_issues_are_derived_from_measurements_not_from_well_names(
        synthetic_project):
    codes = {(r["context"], r["code"]) for r in synthetic_project["payloads"][ISSUES]}
    assert ("Poseidon_2", "SHALLOW_DENSITY_COLUMN_UNRESOLVED") in codes
    assert ("Poseidon_North_1", "SEABED_DATUM_UNRESOLVED") in codes
    assert ("Proteus_1ST2", "LONG_INTERNAL_GAP_PRESENT") in codes
    # The well that reaches its seabed raises none of those.
    assert ("Boreas_1", "SHALLOW_DENSITY_COLUMN_UNRESOLVED") not in codes
    assert ("Boreas_1", "ABSOLUTE_OVERBURDEN_NOT_SUPPORTED") not in codes


def test_an_absent_density_curve_raises_an_error_issue(tmp_path, overburden_config):
    md = np.arange(1000.0, 1101.0, 10.0)
    frames = {"Boreas_1": make_frame(well_key="Boreas_1", md=md, curves={})}
    marker_table = tmp_path / "markers.csv"
    marker_table.write_text(
        "well_key,canonical_marker_name,MDRT_reconciled_m,TVD_survey_m,"
        "TVDSS_survey_corrected_m\n", encoding="utf-8")
    run = run_overburden_workflow(frames, overburden_config,
                                  marker_table_path=str(marker_table))
    codes = {i.code for i in run.issues}
    assert "DENSITY_CURVE_ABSENT" in codes


def test_issue_text_carries_no_path_separator_or_newline(synthetic_project):
    for row in synthetic_project["payloads"][ISSUES]:
        for field in ("context", "message"):
            assert "\n" not in row[field]
            assert "\\" not in row[field]
            assert "://" not in row[field]


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def test_manifest_counts_agree_with_the_derived_statuses(synthetic_project):
    m = synthetic_project["payloads"][OVERBURDEN_MANIFEST_ARTIFACT]
    assert m["n_wells_evaluated"] == 4
    assert m["n_wells_absolute_supported"] == 1
    assert m["n_wells_screening_sensitivity_only"] == 1
    assert m["n_wells_partial_measured_only"] == 2
    assert m["n_wells_not_eligible"] == 0
    total = (m["n_wells_absolute_supported"] + m["n_wells_screening_sensitivity_only"]
             + m["n_wells_partial_measured_only"] + m["n_wells_not_eligible"])
    assert total == m["n_wells_evaluated"]


def test_manifest_declares_every_assumption_explicitly(synthetic_project):
    m = synthetic_project["payloads"][OVERBURDEN_MANIFEST_ARTIFACT]
    config = synthetic_project["config"]
    reg = m["assumption_register"]
    assert reg["seawater_density_kg_m3"] == config.seawater_density_kg_m3
    assert reg["rhob_min_kg_m3"] == config.rhob_min_kg_m3
    assert reg["rhob_max_kg_m3"] == config.rhob_max_kg_m3
    assert reg["short_gap_max_tvd_m"] == config.short_gap_max_tvd_m
    assert m["gravity_m_s2"] == config.gravity_m_s2
    assert m["depth_convention_verified"] is True


def test_manifest_declares_that_no_calibration_data_exist(synthetic_project):
    cal = synthetic_project["payloads"][OVERBURDEN_MANIFEST_ARTIFACT][
        "calibration_data_available"]
    for key, value in cal.items():
        if key == "statement":
            continue
        assert value is False, key


def test_manifest_named_lithology_flag_is_derived_from_the_actual_records(
        synthetic_project):
    m = synthetic_project["payloads"][OVERBURDEN_MANIFEST_ARTIFACT]
    cov = m["lithology_validation"]["emitted_field_coverage"]
    assert m["named_lithology_assigned"] is False
    assert cov["n_string_field_occurrences"] > 0
    assert cov["n_unclassified_fields"] == 0
    assert cov["n_unauthorized_controlled_fields"] == 0
    assert cov["violations"] == 0
    assert m["lithology_validation"]["violations"] == []
    # The coverage block describes the CSV records, so the manifest itself is
    # correctly absent from the inspected set at that point.
    assert set(cov["artifacts_inspected"]) == set(OVERBURDEN_CSV_SCHEMAS)


def test_manifest_lists_every_not_implemented_method(synthetic_project):
    m = synthetic_project["payloads"][OVERBURDEN_MANIFEST_ARTIFACT]
    assert list(m["methods_not_implemented"]) == list(NOT_IMPLEMENTED_TOKENS)
    for token in ("pore_pressure_prediction", "eaton_method", "bowers_method",
                  "effective_stress_calculation", "horizontal_stress_calculation",
                  "wellbore_stability_analysis", "named_lithology_assignment"):
        assert token in m["methods_not_implemented"]


def test_manifest_well_entries_match_the_eligibility_table(synthetic_project):
    m = synthetic_project["payloads"][OVERBURDEN_MANIFEST_ARTIFACT]
    rows = {r["well_key"]: r for r in synthetic_project["payloads"][ELIGIBILITY]}
    assert set(m["wells"]) == set(rows)
    for wk, entry in m["wells"].items():
        assert entry["overburden_status"] == rows[wk]["overburden_status"]
        assert entry["n_eligible"] == rows[wk]["n_eligible_samples"]
        expected = rows[wk]["limiting_reasons"]
        actual = ";".join(entry["limiting_reasons"]) or "none"
        assert actual == expected


# ---------------------------------------------------------------------------
# Determinism and non-mutation
# ---------------------------------------------------------------------------

def test_the_whole_workflow_is_deterministic(synthetic_project):
    config, frames = synthetic_project["config"], synthetic_project["frames"]
    first = json.dumps(synthetic_project["payloads"], sort_keys=True, default=str)
    for _ in range(2):
        run = run_overburden_workflow(
            frames, config, marker_table_path=synthetic_project["markers"])
        again = json.dumps(build_overburden_payloads(run), sort_keys=True, default=str)
        assert again == first


def test_the_workflow_does_not_mutate_the_input_frames(synthetic_project):
    frames = synthetic_project["frames"]
    snapshot = {
        wk: (np.array(fr.MD_m, copy=True), np.array(fr.TVD_m, copy=True),
             np.array(fr.TVDSS_m, copy=True),
             np.array(fr.curve("RHOB_kg_m3").values, copy=True)
             if fr.curve("RHOB_kg_m3") else None)
        for wk, fr in frames.items()}
    run = run_overburden_workflow(
        frames, synthetic_project["config"],
        marker_table_path=synthetic_project["markers"])
    build_overburden_payloads(run)
    for wk, fr in frames.items():
        md, tvd, tvdss, rho = snapshot[wk]
        assert np.array_equal(np.asarray(fr.MD_m), md)
        assert np.array_equal(np.asarray(fr.TVD_m), tvd)
        assert np.array_equal(np.asarray(fr.TVDSS_m), tvdss)
        if rho is not None:
            after = np.asarray(fr.curve("RHOB_kg_m3").values)
            assert np.array_equal(np.isnan(after), np.isnan(rho))
            assert np.array_equal(after[~np.isnan(after)], rho[~np.isnan(rho)])


def test_two_independent_roots_produce_byte_identical_artifacts(
        tmp_path, synthetic_project):
    payloads = synthetic_project["payloads"]
    wells = set(synthetic_project["frames"])
    a, b = tmp_path / "root_a" / "out", tmp_path / "root_b" / "out"
    export_authorized_outputs(OVERBURDEN_BUNDLE, a, payloads, well_keys=wells)
    export_authorized_outputs(OVERBURDEN_BUNDLE, b, payloads, well_keys=wells)
    for name in OVERBURDEN_ARTIFACTS:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_building_the_payloads_twice_does_not_change_them(synthetic_project):
    run = run_overburden_workflow(
        synthetic_project["frames"], synthetic_project["config"],
        marker_table_path=synthetic_project["markers"])
    first = build_overburden_payloads(run)
    snapshot = copy.deepcopy(first)
    second = build_overburden_payloads(run)
    assert first == snapshot
    assert second == snapshot
