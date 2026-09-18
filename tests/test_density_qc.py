"""
Increment 7 - configuration loading, unit/provenance confirmation, the twelve
explicit masks, screening-bound behaviour at EXACT boundaries, gap
classification, and gap conditioning.

Boundary tests here use the exact configured bound values, not values near
them: an inclusive/exclusive slip at a bound is a silent scientific change,
and only an exact-boundary test catches it.
"""

from __future__ import annotations

from dataclasses import replace
import math
import os

import numpy as np
import pytest
import yaml

from p2mem.density_qc import (
    DensityUnitError, build_density_masks, classify_density_gaps,
    compute_density_qc_stats, condition_density_gaps, load_overburden_config,
    resolve_density_slot,
)
from p2mem.overburden_models import (
    DENSITY_MASK_NAMES,
    GAP_CLASS_LONG_INTERNAL,
    GAP_CLASS_SHALLOW,
    GAP_CLASS_SHORT_INTERNAL,
    GAP_CLASS_TERMINAL,
    GAP_CLASS_UNMAPPED_DEPTH,
    GAP_DISPOSITION_BRIDGED,
    GAP_DISPOSITION_UNRESOLVED,
    SEABED_BASIS_LOCKED_MARKER,
    SEABED_BASIS_NOT_DETERMINABLE,
    DensityGapRecord,
    DensityMaskSet,
    GapConditioningResult,
    OverburdenConfigError,
    OverburdenInputError,
    readonly,
)

from helpers_inc7 import CONFIG_PATH, overburden_config, prepared  # noqa: E402
from synthetic_inc7 import (  # noqa: E402
    constant_density_frame, gap_frame, make_curve, make_frame,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def test_packaged_config_loads_and_declares_the_expected_policy(overburden_config):
    c = overburden_config
    assert c.increment == 7
    assert c.canonical_curve_name == "RHOB_kg_m3"
    assert c.accepted_canonical_unit == "kg/m3"
    assert c.expected_conversion_function == "gcc_to_kgm3"
    assert c.bounds_are_inclusive is True
    assert c.gravity_m_s2 == 9.80665
    assert c.scenario_names == ("low", "base", "high")
    assert c.scenario_high_percentile == 5.0
    assert c.short_gap_max_tvd_m in c.sensitivity_thresholds_tvd_m
    assert "vertical_depth" in c.integration_method


def _write_config(tmp_path, mutate):
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    mutate(raw)
    path = tmp_path / "overburden_stress.yml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return str(path)


def test_missing_config_file_is_a_typed_error(tmp_path):
    with pytest.raises(OverburdenConfigError, match="not found"):
        load_overburden_config(str(tmp_path / "nope.yml"))


def test_unknown_top_level_key_is_rejected_not_ignored(tmp_path):
    path = _write_config(tmp_path, lambda r: r.update({"surprise": 1}))
    with pytest.raises(OverburdenConfigError, match="unknown top-level key"):
        load_overburden_config(path)


def test_unknown_key_inside_a_known_section_is_rejected(tmp_path):
    path = _write_config(
        tmp_path, lambda r: r["screening_bounds"].update({"surprise": 1}))
    with pytest.raises(OverburdenConfigError, match="unknown key"):
        load_overburden_config(path)


def test_missing_required_section_key_is_rejected(tmp_path):
    path = _write_config(tmp_path, lambda r: r["integration"].pop("gravity_m_s2"))
    with pytest.raises(OverburdenConfigError, match="required key"):
        load_overburden_config(path)


@pytest.mark.parametrize("key", [
    "bridge_across_seabed_allowed", "bridge_outside_survey_coverage_allowed",
    "bridge_long_gaps_allowed", "shallow_gap_uses_internal_gap_rule",
])
def test_hard_scientific_invariants_cannot_be_switched_on(tmp_path, key):
    path = _write_config(tmp_path, lambda r: r["gap_conditioning"].update({key: True}))
    with pytest.raises(OverburdenConfigError, match="hard scientific invariant"):
        load_overburden_config(path)


def test_original_values_immutable_cannot_be_switched_off(tmp_path):
    path = _write_config(
        tmp_path,
        lambda r: r["density_source"].update({"original_values_immutable": False}))
    with pytest.raises(OverburdenConfigError, match="never modifies"):
        load_overburden_config(path)


def test_base_scenario_cannot_be_declared_a_best_estimate(tmp_path):
    path = _write_config(
        tmp_path,
        lambda r: r["shallow_column_scenarios"].update(
            {"base_is_not_a_best_estimate": False}))
    with pytest.raises(OverburdenConfigError, match="best estimate"):
        load_overburden_config(path)


def test_assumed_fraction_disclosure_cannot_be_switched_off(tmp_path):
    path = _write_config(
        tmp_path,
        lambda r: r["shallow_column_scenarios"].update(
            {"require_assumed_fraction_disclosure": False}))
    with pytest.raises(OverburdenConfigError, match="originates in the assumption"):
        load_overburden_config(path)


def test_cross_well_seabed_transfer_cannot_be_switched_on(tmp_path):
    path = _write_config(
        tmp_path,
        lambda r: r["water_column"].update({"cross_well_seabed_transfer_allowed": True}))
    with pytest.raises(OverburdenConfigError, match="belongs to the well"):
        load_overburden_config(path)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_configuration_value_is_rejected(tmp_path, value):
    path = _write_config(
        tmp_path, lambda r: r["integration"].update({"gravity_m_s2": value}))
    with pytest.raises(OverburdenConfigError):
        load_overburden_config(path)


@pytest.mark.parametrize("value", [True, "9.81", None, [9.81]])
def test_wrongly_typed_configuration_value_is_rejected(tmp_path, value):
    path = _write_config(
        tmp_path, lambda r: r["integration"].update({"gravity_m_s2": value}))
    with pytest.raises(OverburdenConfigError):
        load_overburden_config(path)


def test_inverted_screening_bounds_are_rejected(tmp_path):
    path = _write_config(
        tmp_path,
        lambda r: r["screening_bounds"].update(
            {"rhob_min_kg_m3": 3500.0, "rhob_max_kg_m3": 1000.0}))
    with pytest.raises(OverburdenConfigError, match="strictly less"):
        load_overburden_config(path)


def test_approved_threshold_must_appear_in_the_sensitivity_list(tmp_path):
    path = _write_config(
        tmp_path,
        lambda r: r["gap_conditioning"].update({"short_gap_max_tvd_m": 7.5}))
    with pytest.raises(OverburdenConfigError, match="must appear in"):
        load_overburden_config(path)


def test_duplicate_configuration_key_is_rejected(tmp_path):
    path = tmp_path / "dup.yml"
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        text = fh.read()
    path.write_text(text + "\nincrement: 7\n", encoding="utf-8")
    with pytest.raises(OverburdenConfigError, match="duplicate"):
        load_overburden_config(str(path))


def test_scenario_names_must_be_exactly_low_base_high(tmp_path):
    path = _write_config(
        tmp_path,
        lambda r: r["shallow_column_scenarios"].update({"scenario_names": ["base"]}))
    with pytest.raises(OverburdenConfigError, match="low/base/high"):
        load_overburden_config(path)


def test_schema_version_is_closed_not_merely_nonempty(tmp_path):
    path = _write_config(
        tmp_path, lambda r: r.update({"schema_version": "7.0.1-typo"}))
    with pytest.raises(OverburdenConfigError, match="exactly '7.0.1'"):
        load_overburden_config(path)


def test_fractional_minimum_sample_count_is_rejected_not_truncated(tmp_path):
    path = _write_config(
        tmp_path,
        lambda r: r["eligibility"].update(
            {"min_eligible_samples_for_increment": 2.9}))
    with pytest.raises(OverburdenConfigError, match="must be an integer"):
        load_overburden_config(path)


@pytest.mark.parametrize("value", [True, "2", 2.0, None])
def test_non_integer_minimum_sample_count_is_rejected(tmp_path, value):
    path = _write_config(
        tmp_path,
        lambda r: r["eligibility"].update(
            {"min_eligible_samples_for_increment": value}))
    with pytest.raises(OverburdenConfigError, match="must be an integer"):
        load_overburden_config(path)


def test_status_vocabulary_and_order_are_closed(tmp_path):
    path = _write_config(
        tmp_path,
        lambda r: r["eligibility"].update(
            {"statuses": ["a", "b", "c", "d"]}))
    with pytest.raises(OverburdenConfigError, match="must equal the four declared"):
        load_overburden_config(path)


def test_numeric_not_implemented_entry_is_rejected_not_coerced(tmp_path):
    path = _write_config(tmp_path, lambda r: r.update({"not_implemented": [1]}))
    with pytest.raises(OverburdenConfigError, match="not coerced"):
        load_overburden_config(path)


def test_duplicate_not_implemented_entry_is_rejected(tmp_path):
    def mutate(raw):
        raw["not_implemented"].append(raw["not_implemented"][0])

    path = _write_config(tmp_path, mutate)
    with pytest.raises(OverburdenConfigError, match="duplicate"):
        load_overburden_config(path)


@pytest.mark.parametrize("key", ["low_basis", "base_basis", "high_basis"])
def test_scenario_basis_tokens_are_closed(tmp_path, key):
    path = _write_config(
        tmp_path,
        lambda r: r["shallow_column_scenarios"].update({key: "unreviewed_basis"}))
    with pytest.raises(OverburdenConfigError, match=key):
        load_overburden_config(path)


@pytest.mark.parametrize("value", [0.1, 4.999, 50.0, 95.0, 99.9])
def test_loader_rejects_high_percentile_other_than_the_stored_p05(
        tmp_path, value):
    path = _write_config(
        tmp_path,
        lambda r: r["shallow_column_scenarios"].update(
            {"high_percentile": value}))
    with pytest.raises(OverburdenConfigError, match="exactly 5.0"):
        load_overburden_config(path)


def test_direct_config_replace_remains_the_supported_frozen_variant_path(
        overburden_config):
    changed = replace(overburden_config, bridge_short_internal_gaps=False)
    assert changed.bridge_short_internal_gaps is False
    assert overburden_config.bridge_short_internal_gaps is True


@pytest.mark.parametrize("value", [0.1, 4.999, 50.0, 95.0, 99.9])
def test_direct_config_constructor_rejects_high_percentile_other_than_p05(
        overburden_config, value):
    with pytest.raises(OverburdenConfigError, match="exactly 5.0"):
        replace(overburden_config, scenario_high_percentile=value)


@pytest.mark.parametrize("field_name,value", [
    ("schema_version", "anything"),
    ("increment", 7.0),
    ("increment", True),
    ("bridge_short_internal_gaps", "false"),
    ("bounds_are_inclusive", 1),
    ("scenarios_enabled", np.bool_(True)),
    ("absolute_requires_uninterrupted_column", "true"),
    ("min_eligible_samples_for_increment", 2.9),
    ("min_eligible_samples_for_increment", True),
])
def test_direct_config_constructor_rejects_closed_or_scalar_type_bypasses(
        overburden_config, field_name, value):
    with pytest.raises(OverburdenConfigError):
        replace(overburden_config, **{field_name: value})


@pytest.mark.parametrize("field_name", [
    "source_filename", "assurance_tier", "canonical_curve_name",
    "accepted_canonical_unit", "expected_conversion_function",
    "integration_method", "seabed_marker_name",
])
@pytest.mark.parametrize("value", ["", "   ", 1, None])
def test_direct_config_constructor_rejects_invalid_string_fields(
        overburden_config, field_name, value):
    with pytest.raises(OverburdenConfigError):
        replace(overburden_config, **{field_name: value})


@pytest.mark.parametrize("field_name", [
    "rhob_min_kg_m3", "rhob_max_kg_m3", "short_gap_max_tvd_m",
    "shallow_gap_tolerance_tvd_m", "gravity_m_s2",
    "profile_report_step_tvdss_m", "seawater_density_kg_m3",
    "seawater_density_low_kg_m3", "seawater_density_high_kg_m3",
    "scenario_high_percentile",
])
@pytest.mark.parametrize("value", [True, "1.0", 1 + 0j, None, float("nan"),
                                    float("inf"), float("-inf")])
def test_direct_config_constructor_rejects_non_numeric_or_non_finite_scalars(
        overburden_config, field_name, value):
    with pytest.raises(OverburdenConfigError):
        replace(overburden_config, **{field_name: value})


@pytest.mark.parametrize("value", [
    [0.0, 10.0],
    (),
    (0.0, 10.0, 10.0),
    (10.0, 0.0),
    (-1.0, 10.0),
    (0.0, float("nan"), 10.0),
    (0.0, "10.0"),
])
def test_direct_config_constructor_rejects_malformed_threshold_tuple(
        overburden_config, value):
    with pytest.raises(OverburdenConfigError):
        replace(overburden_config, sensitivity_thresholds_tvd_m=value)


@pytest.mark.parametrize("field_name,value", [
    ("integration_method", "trapezoidal_in_measured_depth"),
    ("scenario_names", ["low", "base", "high"]),
    ("scenario_names", ("base",)),
    ("not_implemented", ["pore_pressure_prediction"]),
    ("not_implemented", (1,)),
    ("not_implemented", ("",)),
    ("not_implemented", ("pore_pressure_prediction", "pore_pressure_prediction")),
    ("shallow_gap_tolerance_tvd_m", -1.0),
])
def test_direct_config_constructor_rejects_malformed_policy_values(
        overburden_config, field_name, value):
    with pytest.raises(OverburdenConfigError):
        replace(overburden_config, **{field_name: value})


# ---------------------------------------------------------------------------
# Unit and provenance confirmation
# ---------------------------------------------------------------------------

def test_a_well_without_a_density_curve_resolves_to_none(overburden_config):
    frame = make_frame(md=np.arange(1000.0, 1051.0, 10.0), curves={})
    slot, unit_ok, conv_ok = resolve_density_slot(frame, overburden_config)
    assert slot is None and unit_ok is False and conv_ok is False


def test_an_unexpected_canonical_unit_is_refused_not_rescaled(overburden_config):
    md = np.arange(1000.0, 1051.0, 10.0)
    frame = make_frame(md=md, curves={
        "RHOB_kg_m3": make_curve(np.full(md.size, 2.5), canonical_unit="g/cm3")})
    with pytest.raises(DensityUnitError, match="no unit conversion of its own"):
        resolve_density_slot(frame, overburden_config)


def test_density_unit_error_is_a_typeerror_subclass():
    assert issubclass(DensityUnitError, TypeError)


def test_an_unexpected_conversion_function_is_reported_not_corrected(
        overburden_config):
    md = np.arange(1000.0, 1051.0, 10.0)
    frame = make_frame(md=md, curves={
        "RHOB_kg_m3": make_curve(np.full(md.size, 2400.0),
                                 conversion_function="identity")})
    slot, unit_ok, conv_ok = resolve_density_slot(frame, overburden_config)
    assert slot is not None and unit_ok is True and conv_ok is False
    out = prepared(frame, overburden_config)
    assert out["stats"].conversion_confirmed is False
    # It is reported, not repaired: the curve is still eligible.
    assert out["stats"].n_eligible == md.size


@pytest.mark.parametrize("values", [
    np.array([True, False, True]),
    np.array(["2400", "2400", "2400"]),
    np.array([2400 + 0j, 2400 + 0j, 2400 + 0j]),
    np.array([object(), object(), object()], dtype=object),
])
def test_ambiguous_density_dtype_is_a_typeerror(overburden_config, values):
    md = np.arange(1000.0, 1030.0, 10.0)
    frame = make_frame(md=md, curves={
        "RHOB_kg_m3": make_curve.__wrapped__(values) if hasattr(make_curve, "__wrapped__")
        else _raw_curve(values)})
    with pytest.raises(TypeError):
        build_density_masks(frame, overburden_config)


def _raw_curve(values):
    """A CurveSlot holding a deliberately ambiguous dtype array.

    `make_curve` casts to float64 on purpose, so this helper bypasses it to
    reach the dtype gate that protects the production path.
    """
    from p2mem.wellframe_models import CurveSlot
    arr = np.asarray(values)
    view = arr.view()
    view.setflags(write=False)
    mask = np.zeros(arr.size, dtype=bool)
    mask.setflags(write=False)
    return CurveSlot(
        canonical_name="RHOB_kg_m3", source_curve_name="RHOB", raw_mnemonic="RHOB",
        raw_unit="g/cc", canonical_unit="kg/m3", conversion_function="gcc_to_kgm3",
        source_filename="synthetic.las", evidence_class="measured",
        values=view, valid_mask=mask, n_samples=int(arr.size), valid_count=0,
        valid_fraction=0.0)


# ---------------------------------------------------------------------------
# Masks
# ---------------------------------------------------------------------------

def test_all_twelve_masks_are_present_and_full_length(overburden_config):
    frame = constant_density_frame(n=17)
    masks = prepared(frame, overburden_config)["masks"]
    for name in DENSITY_MASK_NAMES:
        arr = getattr(masks, name)
        if name == "below_seabed_sample":
            assert arr is None            # no seabed supplied in this fixture
            continue
        assert arr.dtype == np.bool_
        assert arr.size == 17
        assert not arr.flags.writeable


def test_below_seabed_mask_is_none_when_the_seabed_is_not_determinable(
        overburden_config):
    masks = prepared(constant_density_frame(), overburden_config)["masks"]
    assert masks.below_seabed_sample is None
    assert masks.seabed_resolved is False
    assert masks.counts()["below_seabed_sample"] is None


def test_below_seabed_mask_exists_when_the_seabed_is_resolved(overburden_config):
    md = np.arange(400.0, 601.0, 10.0)
    frame = make_frame(md=md, density=np.full(md.size, 2000.0))
    masks = prepared(frame, overburden_config, seabed_mdrt_m=500.0,
                     seabed_tvd_m=500.0, seabed_tvdss_m=475.0)["masks"]
    assert masks.seabed_resolved is True
    assert int(np.count_nonzero(masks.below_seabed_sample)) == 11


def test_eligibility_mask_is_a_strict_conjunction(overburden_config):
    frame = gap_frame([slice(5, 8)], n=21, step=1.0)
    masks = prepared(frame, overburden_config)["masks"]
    elig = np.asarray(masks.eligible_for_measured_integration)
    for name in ("finite_numeric_density", "unit_resolved",
                 "screening_range_plausible", "depth_mapping_valid",
                 "within_survey_coverage"):
        assert not np.any(elig & ~np.asarray(getattr(masks, name)))


def test_a_bridged_sample_is_never_also_an_eligible_measured_sample(
        overburden_config):
    frame = gap_frame([slice(10, 13)], n=41, step=1.0)
    masks = prepared(frame, overburden_config)["masks"]
    assert not np.any(np.asarray(masks.bridged_short_gap)
                      & np.asarray(masks.eligible_for_measured_integration))


def test_mask_set_rejects_a_writable_mask():
    with pytest.raises(OverburdenInputError, match="read-only"):
        DensityMaskSet(
            well_key="X", n_samples=2, seabed_resolved=False,
            source_value_present=np.ones(2, dtype=bool),
            finite_numeric_density=readonly(np.ones(2, dtype=bool)),
            unit_resolved=readonly(np.ones(2, dtype=bool)),
            screening_range_plausible=readonly(np.ones(2, dtype=bool)),
            below_seabed_sample=None,
            depth_mapping_valid=readonly(np.ones(2, dtype=bool)),
            within_survey_coverage=readonly(np.ones(2, dtype=bool)),
            eligible_for_measured_integration=readonly(np.ones(2, dtype=bool)),
            bridged_short_gap=readonly(np.zeros(2, dtype=bool)),
            unresolved_long_gap=readonly(np.zeros(2, dtype=bool)),
            unresolved_shallow_column=readonly(np.zeros(2, dtype=bool)),
            unresolved_terminal_column=readonly(np.zeros(2, dtype=bool)))


def test_mask_set_rejects_an_eligibility_mask_that_is_not_a_conjunction():
    ones, zeros = readonly(np.ones(2, dtype=bool)), readonly(np.zeros(2, dtype=bool))
    with pytest.raises(OverburdenInputError, match="must be a conjunction"):
        DensityMaskSet(
            well_key="X", n_samples=2, seabed_resolved=False,
            source_value_present=ones, finite_numeric_density=zeros,
            unit_resolved=ones, screening_range_plausible=ones,
            below_seabed_sample=None, depth_mapping_valid=ones,
            within_survey_coverage=ones, eligible_for_measured_integration=ones,
            bridged_short_gap=zeros, unresolved_long_gap=zeros,
            unresolved_shallow_column=zeros, unresolved_terminal_column=zeros)


def test_mask_set_rejects_a_seabed_flag_that_disagrees_with_its_mask():
    ones, zeros = readonly(np.ones(2, dtype=bool)), readonly(np.zeros(2, dtype=bool))
    with pytest.raises(OverburdenInputError, match="seabed"):
        DensityMaskSet(
            well_key="X", n_samples=2, seabed_resolved=True,
            source_value_present=ones, finite_numeric_density=ones,
            unit_resolved=ones, screening_range_plausible=ones,
            below_seabed_sample=None, depth_mapping_valid=ones,
            within_survey_coverage=ones, eligible_for_measured_integration=ones,
            bridged_short_gap=zeros, unresolved_long_gap=zeros,
            unresolved_shallow_column=zeros, unresolved_terminal_column=zeros)


def test_mask_construction_does_not_mutate_the_source_density_array(
        overburden_config):
    frame = gap_frame([slice(5, 8)], n=21, step=1.0)
    before = np.array(frame.curve("RHOB_kg_m3").values, copy=True)
    build_density_masks(frame, overburden_config)
    after = np.asarray(frame.curve("RHOB_kg_m3").values)
    assert np.array_equal(np.isnan(before), np.isnan(after))
    assert np.array_equal(before[~np.isnan(before)], after[~np.isnan(after)])


# ---------------------------------------------------------------------------
# Screening bounds - EXACT boundary behaviour
# ---------------------------------------------------------------------------

def test_values_exactly_on_both_bounds_are_accepted(overburden_config):
    lo, hi = overburden_config.rhob_min_kg_m3, overburden_config.rhob_max_kg_m3
    md = np.arange(1000.0, 1030.0, 10.0)
    frame = make_frame(md=md, density=np.array([lo, 0.5 * (lo + hi), hi]))
    out = prepared(frame, overburden_config)
    assert out["stats"].n_in_screening_band == 3
    assert out["stats"].n_screening_bound_failures == 0


def test_values_just_outside_both_bounds_are_masked_out(overburden_config):
    lo, hi = overburden_config.rhob_min_kg_m3, overburden_config.rhob_max_kg_m3
    md = np.arange(1000.0, 1040.0, 10.0)
    frame = make_frame(md=md, density=np.array([
        np.nextafter(lo, -np.inf), lo, hi, np.nextafter(hi, np.inf)]))
    stats = prepared(frame, overburden_config)["stats"]
    assert stats.n_in_screening_band == 2
    assert stats.n_below_screening_min == 1
    assert stats.n_above_screening_max == 1
    assert stats.n_screening_bound_failures == 2


def test_non_positive_density_is_counted_as_a_bound_failure(overburden_config):
    md = np.arange(1000.0, 1040.0, 10.0)
    frame = make_frame(md=md, density=np.array([-1.0, 0.0, 2400.0, 2500.0]))
    stats = prepared(frame, overburden_config)["stats"]
    assert stats.n_non_positive == 2
    assert stats.n_screening_bound_failures == 2
    assert stats.n_in_screening_band == 2


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_non_finite_density_is_never_in_the_screening_band(overburden_config, bad):
    md = np.arange(1000.0, 1030.0, 10.0)
    frame = make_frame(md=md, density=np.array([2400.0, bad, 2400.0]))
    stats = prepared(frame, overburden_config)["stats"]
    assert stats.n_finite == 2
    assert stats.n_non_finite == 1
    assert stats.n_in_screening_band == 2


def test_screening_counts_partition_the_finite_samples(overburden_config):
    md = np.arange(1000.0, 1060.0, 10.0)
    frame = make_frame(md=md, density=np.array(
        [np.nan, -1.0, 500.0, 2400.0, 4000.0, np.inf]))
    s = prepared(frame, overburden_config)["stats"]
    assert s.n_in_screening_band + s.n_screening_bound_failures == s.n_finite
    assert s.n_finite + s.n_non_finite == s.n_samples


# ---------------------------------------------------------------------------
# Gaps
# ---------------------------------------------------------------------------

def test_shallow_gap_is_classified_and_never_bridged(overburden_config):
    md = np.arange(1000.0, 1101.0, 10.0)
    frame = make_frame(md=md, density=np.full(md.size, 2000.0))
    gr = prepared(frame, overburden_config, seabed_mdrt_m=500.0,
                  seabed_tvd_m=500.0, seabed_tvdss_m=475.0)["gaps"]
    shallow = [g for g in gr.gaps if g.gap_class == GAP_CLASS_SHALLOW]
    assert len(shallow) == 1
    assert shallow[0].disposition == GAP_DISPOSITION_UNRESOLVED
    assert math.isclose(shallow[0].thickness_tvd_m, 500.0)


def test_shallow_gap_is_not_bridged_at_any_threshold(overburden_config):
    md = np.arange(1000.0, 1101.0, 10.0)
    frame = make_frame(md=md, density=np.full(md.size, 2000.0))
    for threshold in (0.0, 10.0, 1000.0, 1.0e9):
        gr = prepared(frame, overburden_config, seabed_mdrt_m=500.0,
                      seabed_tvd_m=500.0, seabed_tvdss_m=475.0,
                      threshold_tvd_m=threshold)["gaps"]
        shallow = next(g for g in gr.gaps if g.gap_class == GAP_CLASS_SHALLOW)
        assert shallow.disposition == GAP_DISPOSITION_UNRESOLVED


def test_terminal_gap_is_classified_and_never_bridged(overburden_config):
    md = np.arange(1000.0, 1101.0, 10.0)
    rho = np.full(md.size, 2000.0)
    rho[-4:] = np.nan
    frame = make_frame(md=md, density=rho)
    gr = prepared(frame, overburden_config)["gaps"]
    terminal = [g for g in gr.gaps if g.gap_class == GAP_CLASS_TERMINAL]
    assert len(terminal) == 1
    assert terminal[0].n_samples == 4
    assert terminal[0].disposition == GAP_DISPOSITION_UNRESOLVED
    assert math.isclose(terminal[0].thickness_tvd_m, 40.0)


def test_a_gap_caused_only_by_missing_depth_mapping_is_its_own_class(
        overburden_config):
    md = np.arange(1000.0, 1041.0, 10.0)
    tvd = md.copy()
    tvd[2] = np.nan
    valid = np.isfinite(tvd)
    frame = make_frame(md=md, tvd=tvd, tvdss=tvd - 25.0,
                       density=np.full(md.size, 2000.0), depth_valid_mask=valid)
    gr = prepared(frame, overburden_config)["gaps"]
    classes = [g.gap_class for g in gr.gaps]
    assert GAP_CLASS_UNMAPPED_DEPTH in classes
    unmapped = next(g for g in gr.gaps if g.gap_class == GAP_CLASS_UNMAPPED_DEPTH)
    assert unmapped.disposition == GAP_DISPOSITION_UNRESOLVED


def test_gap_thicknesses_are_reported_in_both_md_and_tvd(overburden_config):
    """A deviated well: the MD gap is longer than the TVD gap."""
    md = np.arange(1000.0, 1026.0, 5.0)
    tvd = md * 0.8
    rho = np.full(md.size, 2000.0)
    rho[2] = np.nan
    frame = make_frame(md=md, tvd=tvd, density=rho)
    gr = prepared(frame, overburden_config)["gaps"]
    gap = next(g for g in gr.gaps if g.gap_class == GAP_CLASS_SHORT_INTERNAL)
    assert math.isclose(gap.thickness_md_m, 10.0)
    assert math.isclose(gap.thickness_tvd_m, 8.0)
    assert gap.thickness_tvd_m < gap.thickness_md_m


def test_gap_classification_is_deterministic(overburden_config):
    frame = gap_frame([slice(5, 7), slice(20, 24)], n=41, step=1.0)
    first = prepared(frame, overburden_config)["gaps"]
    for _ in range(3):
        again = prepared(frame, overburden_config)["gaps"]
        assert [(g.gap_index, g.gap_class, g.disposition, g.n_samples)
                for g in again.gaps] == [
            (g.gap_index, g.gap_class, g.disposition, g.n_samples)
            for g in first.gaps]


def test_bridging_is_refused_outside_locked_survey_coverage(overburden_config):
    """A gap whose samples fall outside survey MD coverage is not bridgeable."""
    md = np.arange(1000.0, 1041.0, 10.0)
    rho = np.full(md.size, 2000.0)
    rho[2] = np.nan
    frame = make_frame(md=md, density=rho,
                       survey_md_min_m=1000.0, survey_md_max_m=1015.0)
    gr = prepared(frame, overburden_config)["gaps"]
    assert gr.n_bridged_gaps == 0


@pytest.mark.parametrize("bad", [
    True, np.bool_(False), "10", 10 + 0j, np.nan, np.inf, -np.inf, -1.0,
])
@pytest.mark.parametrize("operation", ["classify", "condition"])
def test_public_gap_threshold_overrides_fail_closed_on_invalid_values(
        bad, operation, overburden_config):
    frame = gap_frame([slice(10, 20)], rho=2000.0, n=41, step=1.0)
    masks = build_density_masks(frame, overburden_config)
    fn = classify_density_gaps if operation == "classify" else condition_density_gaps
    with pytest.raises(OverburdenInputError, match="threshold_tvd_m"):
        fn(frame, masks, overburden_config, threshold_tvd_m=bad)


def test_infinite_threshold_cannot_turn_a_long_gap_into_a_bridged_gap(
        overburden_config):
    frame = gap_frame([slice(10, 30)], rho=2000.0, n=41, step=1.0)
    masks = build_density_masks(frame, overburden_config)
    with pytest.raises(OverburdenInputError, match="finite"):
        condition_density_gaps(
            frame, masks, overburden_config, threshold_tvd_m=float("inf"))


# ---------------------------------------------------------------------------
# Gap-record and conditioning invariants
# ---------------------------------------------------------------------------

def test_only_a_short_internal_gap_may_carry_a_bridged_disposition():
    for bad_class in (GAP_CLASS_SHALLOW, GAP_CLASS_TERMINAL, GAP_CLASS_LONG_INTERNAL,
                      GAP_CLASS_UNMAPPED_DEPTH):
        with pytest.raises(OverburdenInputError, match="may be bridged"):
            DensityGapRecord(
                well_key="X", gap_index=0, gap_class=bad_class,
                disposition=GAP_DISPOSITION_BRIDGED, n_samples=1,
                start_index=1, end_index=1, md_start_m=0.0, md_end_m=2.0,
                tvd_start_m=0.0, tvd_end_m=2.0, thickness_md_m=2.0,
                thickness_tvd_m=2.0, threshold_tvd_m=10.0,
                bounding_density_above_kg_m3=2000.0,
                bounding_density_below_kg_m3=2000.0)


def test_a_bridged_gap_must_record_both_bracketing_densities():
    with pytest.raises(OverburdenInputError, match="bracketing measured densities"):
        DensityGapRecord(
            well_key="X", gap_index=0, gap_class=GAP_CLASS_SHORT_INTERNAL,
            disposition=GAP_DISPOSITION_BRIDGED, n_samples=1, start_index=1,
            end_index=1, md_start_m=0.0, md_end_m=2.0, tvd_start_m=0.0,
            tvd_end_m=2.0, thickness_md_m=2.0, thickness_tvd_m=2.0,
            threshold_tvd_m=10.0, bounding_density_above_kg_m3=None,
            bounding_density_below_kg_m3=2000.0)


def test_a_gap_classified_short_may_not_exceed_its_threshold():
    with pytest.raises(OverburdenInputError, match="classified short"):
        DensityGapRecord(
            well_key="X", gap_index=0, gap_class=GAP_CLASS_SHORT_INTERNAL,
            disposition=GAP_DISPOSITION_UNRESOLVED, n_samples=1, start_index=1,
            end_index=1, md_start_m=0.0, md_end_m=99.0, tvd_start_m=0.0,
            tvd_end_m=99.0, thickness_md_m=99.0, thickness_tvd_m=99.0,
            threshold_tvd_m=10.0, bounding_density_above_kg_m3=None,
            bounding_density_below_kg_m3=None)


def test_a_gap_classified_long_must_exceed_its_threshold():
    with pytest.raises(OverburdenInputError, match="classified long"):
        DensityGapRecord(
            well_key="X", gap_index=0, gap_class=GAP_CLASS_LONG_INTERNAL,
            disposition=GAP_DISPOSITION_UNRESOLVED, n_samples=1, start_index=1,
            end_index=1, md_start_m=0.0, md_end_m=2.0, tvd_start_m=0.0,
            tvd_end_m=2.0, thickness_md_m=2.0, thickness_tvd_m=2.0,
            threshold_tvd_m=10.0, bounding_density_above_kg_m3=None,
            bounding_density_below_kg_m3=None)


@pytest.mark.parametrize("gaps,samples", [(1, 0), (0, 3)])
def test_conditioning_rejects_a_gap_count_that_disagrees_with_its_sample_count(
        gaps, samples):
    mask = np.zeros(4, dtype=bool)
    mask[:samples] = True
    with pytest.raises(OverburdenInputError):
        GapConditioningResult(
            well_key="X", threshold_tvd_m=10.0, bridging_enabled=True,
            conditioned_density_kg_m3=readonly(np.full(4, 2000.0)),
            bridged_mask=readonly(mask), n_bridged_gaps=gaps,
            n_bridged_samples=samples, bridged_thickness_md_m=0.0,
            bridged_thickness_tvd_m=0.0, n_long_gaps=0, n_long_gap_samples=0,
            long_gap_thickness_md_m=0.0, long_gap_thickness_tvd_m=0.0)


def test_conditioning_rejects_more_gaps_than_samples():
    mask = np.zeros(4, dtype=bool)
    mask[0] = True
    with pytest.raises(OverburdenInputError, match="cannot contain only"):
        GapConditioningResult(
            well_key="X", threshold_tvd_m=10.0, bridging_enabled=True,
            conditioned_density_kg_m3=readonly(np.full(4, 2000.0)),
            bridged_mask=readonly(mask), n_bridged_gaps=3, n_bridged_samples=1,
            bridged_thickness_md_m=0.0, bridged_thickness_tvd_m=0.0,
            n_long_gaps=0, n_long_gap_samples=0, long_gap_thickness_md_m=0.0,
            long_gap_thickness_tvd_m=0.0)


def test_conditioning_rejects_a_writable_conditioned_array():
    with pytest.raises(OverburdenInputError, match="read-only"):
        GapConditioningResult(
            well_key="X", threshold_tvd_m=10.0, bridging_enabled=True,
            conditioned_density_kg_m3=np.full(4, 2000.0),
            bridged_mask=readonly(np.zeros(4, dtype=bool)), n_bridged_gaps=0,
            n_bridged_samples=0, bridged_thickness_md_m=0.0,
            bridged_thickness_tvd_m=0.0, n_long_gaps=0, n_long_gap_samples=0,
            long_gap_thickness_md_m=0.0, long_gap_thickness_tvd_m=0.0)


def test_conditioning_rejects_bridged_gaps_while_bridging_is_disabled():
    mask = np.zeros(4, dtype=bool)
    mask[1] = True
    with pytest.raises(OverburdenInputError, match="bridging is disabled"):
        GapConditioningResult(
            well_key="X", threshold_tvd_m=10.0, bridging_enabled=False,
            conditioned_density_kg_m3=readonly(np.full(4, 2000.0)),
            bridged_mask=readonly(mask), n_bridged_gaps=1, n_bridged_samples=1,
            bridged_thickness_md_m=1.0, bridged_thickness_tvd_m=1.0,
            n_long_gaps=0, n_long_gap_samples=0, long_gap_thickness_md_m=0.0,
            long_gap_thickness_tvd_m=0.0)


@pytest.mark.parametrize("bad", [True, "10", 10 + 0j, np.nan, np.inf, -np.inf, -1.0])
def test_conditioning_result_constructor_rejects_invalid_thresholds(
        bad, overburden_config):
    frame = constant_density_frame()
    good = prepared(frame, overburden_config)["gaps"]
    with pytest.raises(OverburdenInputError, match="threshold_tvd_m"):
        replace(good, threshold_tvd_m=bad)


@pytest.mark.parametrize("bad", [True, "10", 10 + 0j, np.nan, np.inf, -np.inf, -1.0])
def test_density_gap_record_constructor_rejects_invalid_thresholds(bad):
    with pytest.raises(OverburdenInputError, match="threshold_tvd_m"):
        DensityGapRecord(
            well_key="X", gap_index=0, gap_class=GAP_CLASS_LONG_INTERNAL,
            disposition=GAP_DISPOSITION_UNRESOLVED, n_samples=1,
            start_index=1, end_index=1, md_start_m=0.0, md_end_m=20.0,
            tvd_start_m=0.0, tvd_end_m=20.0, thickness_md_m=20.0,
            thickness_tvd_m=20.0, threshold_tvd_m=bad,
            bounding_density_above_kg_m3=2000.0,
            bounding_density_below_kg_m3=2000.0)


# ---------------------------------------------------------------------------
# QC statistics
# ---------------------------------------------------------------------------

def test_qc_statistics_report_the_correct_seabed_basis(overburden_config):
    frame = constant_density_frame()
    assert (prepared(frame, overburden_config)["stats"].seabed_basis
            == SEABED_BASIS_NOT_DETERMINABLE)
    md = np.arange(400.0, 601.0, 10.0)
    frame2 = make_frame(md=md, density=np.full(md.size, 2000.0))
    stats = prepared(frame2, overburden_config, seabed_mdrt_m=500.0,
                     seabed_tvd_m=500.0, seabed_tvdss_m=475.0)["stats"]
    assert stats.seabed_basis == SEABED_BASIS_LOCKED_MARKER
    assert stats.seabed_mdrt_m == 500.0


def test_qc_statistics_are_deterministic(overburden_config):
    frame = gap_frame([slice(5, 8), slice(20, 24)], n=41, step=1.0)
    first = prepared(frame, overburden_config)["stats"]
    for _ in range(3):
        again = prepared(frame, overburden_config)["stats"]
        assert again == first


def test_percentiles_are_measured_over_finite_samples_only(overburden_config):
    md = np.arange(1000.0, 1050.0, 10.0)
    frame = make_frame(md=md, density=np.array([2000.0, np.nan, 2200.0, 2400.0,
                                                2600.0]))
    stats = prepared(frame, overburden_config)["stats"]
    assert stats.rhob_min_kg_m3 == 2000.0
    assert stats.rhob_max_kg_m3 == 2600.0
    assert stats.rhob_median_kg_m3 == 2300.0


def test_high_scenario_percentile_uses_only_eligible_density_samples(
        overburden_config):
    md = np.arange(0.0, 100.0, 1.0)
    rho = np.full(md.size, 2400.0)
    rho[:50] = 1100.0
    rho[50:60] = np.nan
    frame = make_frame(md=md, density=rho)
    out = prepared(
        frame, overburden_config, seabed_mdrt_m=50.0,
        seabed_tvd_m=50.0, seabed_tvdss_m=25.0)
    stats = out["stats"]
    assert stats.n_finite == 90
    assert stats.n_eligible == 40
    assert stats.rhob_p05_kg_m3 == 1100.0
    assert stats.rhob_eligible_p05_kg_m3 == 2400.0
