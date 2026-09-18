"""
Increment 6 - GR QC, endpoint-sensitivity, and screening-proxy tests.

SYNTHETIC ONLY. Every array, disposition, and config in this file is
fabricated in-memory. No real or private project file is read or packaged.
"""

import json

import numpy as np
import pytest

from p2mem.petrophysics import (
    PetrophysicsConfigError,
    PetrophysicsExclusionError,
    PetrophysicsInputError,
    classify_gr_proxy_confidence,
    compute_gr_family_qc_stats,
    compute_gr_index,
    compute_gr_proxy,
    find_contiguous_blocks,
    load_petrophysics_eligibility_config,
)
from p2mem.petrophysics_models import (
    EXCLUSION_REASON_BOREAS_ECGR,
    GR_EXCLUDED_UNRESOLVED_SCALE,
    GR_NOT_AVAILABLE,
    GR_PROXY_HIGH,
    GR_PROXY_INTERMEDIATE,
    GR_PROXY_LOW,
    USE_STATUS_PROXY_ALLOWED,
    USE_STATUS_QC_ONLY_EXCLUDED,
    GrEndpointScenario,
    GrFamilyDisposition,
    PetrophysicsEligibilityConfig,
)
from p2mem.wellframe_models import assert_no_lithology_vocabulary

from synthetic_inc6 import PROJECT_ROOT  # noqa: E402
from synthetic_inc6 import synthetic_las as _synthetic_las  # noqa: E402
from synthetic_inc6 import synthetic_survey as _synthetic_survey  # noqa: E402
from p2mem.wellframe import assemble_well_frame  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic helpers
# ---------------------------------------------------------------------------

def _frame_with_gr(gr_values, canonical="GR_api", well_key="Synth_1", md=None):
    gr = np.asarray(gr_values, dtype=float)
    if md is None:
        md = np.linspace(50.0, 350.0, gr.size)
    las = _synthetic_las({"MD_m": np.asarray(md, dtype=float), canonical: gr}, well_name=well_key)
    dev = _synthetic_survey(well_key, md=(0.0, 200.0, 400.0), tvd=(0.0, 199.0, 396.0))
    return assemble_well_frame(
        well_key, las, dev, las_path=f"/s/{well_key}.las", survey_path=f"/s/{well_key}_dev.txt",
        gr_family_canonical_name=canonical,
    )


def _disposition(well_key="Synth_1", canonical="GR_api", status=USE_STATUS_PROXY_ALLOWED,
                 reason=None, tops=True):
    return GrFamilyDisposition(
        well_key=well_key, source_las_filename=f"{well_key}_logs.las",
        gr_family_canonical_name=canonical, gr_family_source_curve_name=canonical.split("_")[0],
        use_status=status, exclusion_reason=reason, evidence_class="measured",
        has_approved_formation_tops=tops, notes="synthetic",
    )


def _config(**policy_overrides) -> PetrophysicsEligibilityConfig:
    policy = {
        "endpoint_estimation_method": "per_well_percentile_of_own_valid_samples",
        "cross_well_shared_endpoints_allowed": False,
        "endpoint_sample_basis": "finite_and_depth_mapped_samples_only",
        "clipping_policy": "retain_unclipped_and_clipped_side_by_side",
        "clip_lower": 0.0, "clip_upper": 1.0,
        "min_endpoint_separation_api": 1.0,
        "shale_proxy_transform": "linear_identity_of_clipped_igr",
        "nonlinear_vsh_transforms_enabled": False,
        "contiguity": {"max_gap_samples": 2, "max_gap_depth_m": 1.0,
                       "min_block_samples": 2, "min_block_thickness_m": 1.0},
        "nct_candidate_proxy_thresholds": [0.5, 0.6, 0.7],
        "physical_bounds": {
            "rhob_min_kg_m3": 1000.0, "rhob_max_kg_m3": 3500.0,
            "vp_min_m_s": 1000.0, "vp_max_m_s": 8000.0,
            "vs_min_m_s": 300.0, "vs_max_m_s": 5000.0,
            "vp_vs_ratio_nonnegative_poisson_min_inclusive": np.sqrt(2.0),
            "vp_vs_ratio_positive_bulk_modulus_min_exclusive": np.sqrt(4.0 / 3.0),
            "vp_vs_ratio_plausibility_max": 4.0,
        },
    }
    policy.update(policy_overrides)
    return PetrophysicsEligibilityConfig(
        schema_version="6.0", increment=6, assurance_tier="Tier C", policy=policy,
        endpoint_scenarios=(
            {"scenario_name": "low", "low_percentile": 10.0, "high_percentile": 85.0,
             "description": "narrow"},
            {"scenario_name": "base", "low_percentile": 5.0, "high_percentile": 95.0,
             "description": "mid"},
            {"scenario_name": "high", "low_percentile": 1.0, "high_percentile": 99.0,
             "description": "wide"},
        ),
        wells={},
        method_eligibility={
            "eligible_density_for_sv": {"purpose": "synthetic purpose"},
            "eligible_dynamic_elastic": {"purpose": "synthetic purpose"},
            "eligible_sonic_nct_candidate": {"purpose": "synthetic purpose"},
        },
        gr_proxy_confidence={"classes": [], "rules": {
            "high": {"min_valid_fraction": 0.90, "min_dynamic_range_api": 60.0,
                     "max_proxy_median_spread_across_scenarios": 0.10},
            "intermediate": {"min_valid_fraction": 0.70, "min_dynamic_range_api": 40.0,
                             "max_proxy_median_spread_across_scenarios": 0.20},
        }},
        source_filename="synthetic.yml",
    )


def _registered_endpoint_description():
    """Increment 6.1.6: the endpoint description is a CONTROLLED emitted field,
    so a synthetic one is correctly refused by the builder."""
    from p2mem.io.output_policy import OUTPUT_STATEMENTS
    return sorted(st.text for st in OUTPUT_STATEMENTS.values()
                  if st.statement_id.startswith("gr_endpoint_scenarios_description"))[0]


def _scenario(low=10.0, high=110.0, well_key="Synth_1", name="base"):
    return GrEndpointScenario(
        well_key=well_key, scenario_name=name, low_percentile=5.0, high_percentile=95.0,
        gr_low_endpoint_api=low, gr_high_endpoint_api=high,
        endpoint_separation_api=high - low, n_samples_used_for_endpoints=100,
        endpoint_sample_basis="finite_and_depth_mapped_samples_only",
        description=_registered_endpoint_description(),
    )


# ---------------------------------------------------------------------------
# GR index arithmetic
# ---------------------------------------------------------------------------

def test_gr_index_basic_arithmetic():
    gr = np.array([0.0, 50.0, 100.0])
    unc, clip, valid = compute_gr_index(gr, 0.0, 100.0)
    np.testing.assert_allclose(unc, [0.0, 0.5, 1.0])
    np.testing.assert_allclose(clip, [0.0, 0.5, 1.0])
    assert bool(np.all(valid))


def test_clipped_and_unclipped_differ_outside_endpoints():
    """Both results are retained; the unclipped one preserves the honest
    signal that data ran past the assumed bracket."""
    gr = np.array([-20.0, 50.0, 200.0])
    unc, clip, _ = compute_gr_index(gr, 0.0, 100.0)
    np.testing.assert_allclose(unc, [-0.2, 0.5, 2.0])
    np.testing.assert_allclose(clip, [0.0, 0.5, 1.0])
    assert unc[0] < 0.0 and unc[2] > 1.0
    assert clip.min() >= 0.0 and clip.max() <= 1.0


def test_nan_input_stays_masked_and_nan_in_both_outputs():
    """A NaN is never coerced to 0, to an endpoint, or to a neighbour."""
    gr = np.array([10.0, np.nan, 90.0])
    unc, clip, valid = compute_gr_index(gr, 0.0, 100.0)
    assert np.isnan(unc[1]) and np.isnan(clip[1])
    assert not valid[1]
    assert valid[0] and valid[2]


@pytest.mark.parametrize("bad", [np.inf, -np.inf])
def test_infinite_input_is_explicitly_invalidated(bad):
    """An infinite GR sample is not a measurement: it is masked out and set
    to NaN, never normalized into a plus/minus-infinity IGR that clipping
    would quietly turn into a clean-looking 0 or 1."""
    gr = np.array([10.0, bad, 90.0])
    unc, clip, valid = compute_gr_index(gr, 0.0, 100.0)
    assert not valid[1]
    assert np.isnan(unc[1]) and np.isnan(clip[1])
    assert np.count_nonzero(valid) == 2


def test_valid_mask_argument_is_anded_with_finiteness():
    gr = np.array([10.0, 50.0, 90.0])
    extra = np.array([True, False, True])
    _, _, valid = compute_gr_index(gr, 0.0, 100.0, valid_mask=extra)
    np.testing.assert_array_equal(valid, [True, False, True])


# ---------------------------------------------------------------------------
# Endpoint validation
# ---------------------------------------------------------------------------

def test_identical_endpoints_rejected():
    with pytest.raises(PetrophysicsInputError, match="identical"):
        compute_gr_index(np.array([1.0, 2.0]), 50.0, 50.0)


def test_reversed_endpoints_rejected():
    with pytest.raises(PetrophysicsInputError, match="strictly greater"):
        compute_gr_index(np.array([1.0, 2.0]), 100.0, 10.0)


def test_endpoint_separation_below_minimum_rejected():
    with pytest.raises(PetrophysicsInputError, match="below the configured minimum"):
        compute_gr_index(np.array([1.0, 2.0]), 10.0, 10.5, min_endpoint_separation_api=1.0)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_non_finite_endpoints_rejected(bad):
    with pytest.raises(PetrophysicsInputError, match="finite"):
        compute_gr_index(np.array([1.0, 2.0]), 0.0, bad)


@pytest.mark.parametrize("bad", [True, False, "50", b"50", complex(1, 2)])
def test_endpoint_type_class_defects_raise_typeerror(bad):
    with pytest.raises(TypeError):
        compute_gr_index(np.array([1.0, 2.0]), bad, 100.0)


# ---------------------------------------------------------------------------
# Input array validation
# ---------------------------------------------------------------------------

def test_boolean_array_input_rejected_with_typeerror():
    with pytest.raises(TypeError, match="boolean"):
        compute_gr_index(np.array([True, False]), 0.0, 100.0)


def test_string_array_input_rejected_with_typeerror():
    with pytest.raises(TypeError, match="string/bytes"):
        compute_gr_index(np.array(["10", "20"]), 0.0, 100.0)


def test_bytes_array_input_rejected_with_typeerror():
    with pytest.raises(TypeError, match="string/bytes"):
        compute_gr_index(np.array([b"10", b"20"]), 0.0, 100.0)


def test_complex_array_input_rejected_with_typeerror():
    with pytest.raises(TypeError, match="complex"):
        compute_gr_index(np.array([1 + 2j, 3 + 4j]), 0.0, 100.0)


def test_object_array_input_rejected_with_typeerror():
    with pytest.raises(TypeError, match="unsupported array dtype"):
        compute_gr_index(np.array([{"a": 1}, {"b": 2}], dtype=object), 0.0, 100.0)


@pytest.mark.parametrize("shape", [(2, 3), (2, 2, 2)])
def test_multidimensional_array_rejected(shape):
    """A multidimensional array is never silently ravelled - that would
    destroy sample-position alignment with the well frame."""
    with pytest.raises(PetrophysicsInputError, match="never silently flattened"):
        compute_gr_index(np.zeros(shape), 0.0, 100.0)


def test_length_mismatch_between_values_and_mask_rejected():
    with pytest.raises(PetrophysicsInputError, match="never reconciled by truncation or padding"):
        compute_gr_index(np.array([1.0, 2.0, 3.0]), 0.0, 100.0,
                         valid_mask=np.array([True, False]))


def test_non_boolean_mask_rejected():
    with pytest.raises(TypeError, match="boolean array"):
        compute_gr_index(np.array([1.0, 2.0]), 0.0, 100.0, valid_mask=np.array([1, 0]))


# ---------------------------------------------------------------------------
# Boreas-style exclusion
# ---------------------------------------------------------------------------

def test_excluded_well_gets_no_endpoint_scenarios():
    from p2mem.petrophysics import resolve_endpoint_scenarios
    frame = _frame_with_gr(np.linspace(1.0, 500.0, 20), canonical="ECGR_api", well_key="Boreas_1")
    d = _disposition("Boreas_1", "ECGR_api", USE_STATUS_QC_ONLY_EXCLUDED,
                     EXCLUSION_REASON_BOREAS_ECGR)
    with pytest.raises(PetrophysicsExclusionError, match=EXCLUSION_REASON_BOREAS_ECGR):
        resolve_endpoint_scenarios(frame, d, _config())


def test_excluded_well_gets_no_proxy():
    frame = _frame_with_gr(np.linspace(1.0, 500.0, 20), canonical="ECGR_api", well_key="Boreas_1")
    d = _disposition("Boreas_1", "ECGR_api", USE_STATUS_QC_ONLY_EXCLUDED,
                     EXCLUSION_REASON_BOREAS_ECGR)
    with pytest.raises(PetrophysicsExclusionError):
        compute_gr_proxy(frame, d, _scenario(well_key="Boreas_1"), _config())


def test_excluded_well_still_gets_factual_qc_statistics():
    """Exclusion removes GR-DERIVED work, not factual QC reporting - the
    numbers justifying the exclusion must themselves be published."""
    gr = np.array([0.0, -0.001, 8.4, 519.2, 3.3, np.nan])
    frame = _frame_with_gr(gr, canonical="ECGR_api", well_key="Boreas_1")
    d = _disposition("Boreas_1", "ECGR_api", USE_STATUS_QC_ONLY_EXCLUDED,
                     EXCLUSION_REASON_BOREAS_ECGR)
    st = compute_gr_family_qc_stats(frame, d)
    assert st.valid_count == 5
    assert st.n_negative_samples == 1
    assert st.n_zero_samples == 1
    assert st.max_api == pytest.approx(519.2)


def test_excluded_well_classified_as_excluded_not_by_coverage():
    """Good coverage never overrides an unresolved-scale exclusion."""
    frame = _frame_with_gr(np.linspace(1.0, 200.0, 50), canonical="ECGR_api", well_key="Boreas_1")
    d = _disposition("Boreas_1", "ECGR_api", USE_STATUS_QC_ONLY_EXCLUDED,
                     EXCLUSION_REASON_BOREAS_ECGR)
    st = compute_gr_family_qc_stats(frame, d)
    assert st.valid_fraction == 1.0  # perfect coverage
    cls, why = classify_gr_proxy_confidence(st, d, [], _config())
    assert cls == GR_EXCLUDED_UNRESOLVED_SCALE
    assert "does not resolve an unresolved scale" in why


def test_qc_only_disposition_requires_machine_readable_reason():
    with pytest.raises(ValueError, match="machine-readable exclusion_reason"):
        GrFamilyDisposition(
            well_key="X", source_las_filename="x.las", gr_family_canonical_name="ECGR_api",
            gr_family_source_curve_name="ECGR", use_status=USE_STATUS_QC_ONLY_EXCLUDED,
            exclusion_reason=None, evidence_class="measured", has_approved_formation_tops=False,
        )


def test_unknown_use_status_rejected():
    with pytest.raises(ValueError, match="use_status"):
        GrFamilyDisposition(
            well_key="X", source_las_filename="x.las", gr_family_canonical_name="GR_api",
            gr_family_source_curve_name="GR", use_status="do_whatever_you_like",
            exclusion_reason=None, evidence_class="measured", has_approved_formation_tops=False,
        )


# ---------------------------------------------------------------------------
# Scenario resolution
# ---------------------------------------------------------------------------

def test_low_base_high_scenarios_all_computed_with_measured_endpoints():
    from p2mem.petrophysics import resolve_endpoint_scenarios
    frame = _frame_with_gr(np.linspace(5.0, 205.0, 201))
    scenarios = resolve_endpoint_scenarios(frame, _disposition(), _config())
    assert [s.scenario_name for s in scenarios] == ["low", "base", "high"]
    for s in scenarios:
        assert np.isfinite(s.gr_low_endpoint_api) and np.isfinite(s.gr_high_endpoint_api)
        assert s.gr_high_endpoint_api > s.gr_low_endpoint_api
        assert s.evidence_class == "assumed_configured"
        assert "uncalibrated" in s.calibration_status
    # The wide "high" scenario must bracket the narrow "low" one.
    lo, base, hi = scenarios
    assert hi.gr_low_endpoint_api < lo.gr_low_endpoint_api
    assert hi.gr_high_endpoint_api > lo.gr_high_endpoint_api
    assert hi.endpoint_separation_api > base.endpoint_separation_api > lo.endpoint_separation_api


def test_endpoint_scenario_is_never_calibrated():
    s = _scenario()
    assert s.evidence_class == "assumed_configured"
    assert "uncalibrated" in s.calibration_status


def test_zero_valid_coverage_rejected_for_endpoints():
    from p2mem.petrophysics import resolve_endpoint_scenarios
    frame = _frame_with_gr(np.full(10, np.nan))
    with pytest.raises(PetrophysicsInputError, match="zero valid coverage"):
        resolve_endpoint_scenarios(frame, _disposition(), _config())


def test_absent_gr_curve_rejected_for_endpoints_never_borrowed():
    from p2mem.petrophysics import resolve_endpoint_scenarios
    frame = _frame_with_gr(np.linspace(5.0, 105.0, 20), canonical="GR_api")
    d = _disposition(canonical="GRD_api")  # names a curve this well does not have
    with pytest.raises(PetrophysicsInputError, match="never borrowed from another well"):
        resolve_endpoint_scenarios(frame, d, _config())


def test_proxy_from_another_wells_scenario_rejected():
    frame = _frame_with_gr(np.linspace(5.0, 105.0, 20), well_key="A_1")
    other = _scenario(well_key="B_1")
    with pytest.raises(PetrophysicsInputError, match="never transferred between wells"):
        compute_gr_proxy(frame, _disposition("A_1"), other, _config())


# ---------------------------------------------------------------------------
# Proxy behavior and threshold sensitivity
# ---------------------------------------------------------------------------

def test_proxy_equals_clipped_igr_under_linear_identity():
    frame = _frame_with_gr(np.linspace(0.0, 200.0, 41))
    p = compute_gr_proxy(frame, _disposition(), _scenario(10.0, 110.0), _config())
    np.testing.assert_array_equal(
        p.VSH_GR_linear_proxy_frac[p.valid_mask], p.igr_clipped_frac[p.valid_mask]
    )
    assert p.transform_name == "linear_identity_of_clipped_igr"
    assert "not_a_shale_volume" in p.calibration_status


def test_proxy_clipping_counts_are_reported():
    frame = _frame_with_gr(np.array([0.0, 50.0, 60.0, 200.0]))
    p = compute_gr_proxy(frame, _disposition(), _scenario(10.0, 110.0), _config())
    assert p.n_clipped_low == 1   # 0 API is below the low endpoint
    assert p.n_clipped_high == 1  # 200 API is above the high endpoint
    assert p.clipped_fraction == pytest.approx(0.5)


def test_wider_endpoints_damp_the_proxy():
    """Endpoint sensitivity is real and measurable, not cosmetic."""
    gr = np.linspace(5.0, 205.0, 201)
    frame = _frame_with_gr(gr)
    narrow = compute_gr_proxy(frame, _disposition(), _scenario(50.0, 100.0, name="narrow"), _config())
    wide = compute_gr_proxy(frame, _disposition(), _scenario(5.0, 205.0, name="wide"), _config())
    assert narrow.clipped_fraction > wide.clipped_fraction
    assert narrow.proxy_median != wide.proxy_median


def test_threshold_sensitivity_is_monotonic():
    """Raising a proxy threshold can only reduce (never increase) the count
    of samples at or above it."""
    frame = _frame_with_gr(np.linspace(0.0, 200.0, 201))
    p = compute_gr_proxy(frame, _disposition(), _scenario(10.0, 110.0), _config())
    counts = [
        int(np.count_nonzero(np.isfinite(p.VSH_GR_linear_proxy_frac)
                             & (p.VSH_GR_linear_proxy_frac >= t)))
        for t in (0.5, 0.6, 0.7)
    ]
    assert counts[0] >= counts[1] >= counts[2]


def test_unmapped_depth_samples_are_excluded_from_the_proxy():
    """A sample with no defensible depth cannot contribute to a
    depth-resolved proxy."""
    gr = np.full(6, 50.0)
    md = np.array([50.0, 100.0, 200.0, 300.0, 380.0, 900.0])  # last beyond coverage
    frame = _frame_with_gr(gr, md=md)
    p = compute_gr_proxy(frame, _disposition(), _scenario(10.0, 110.0), _config())
    assert not p.valid_mask[-1]
    assert np.isnan(p.VSH_GR_linear_proxy_frac[-1])
    assert p.n_valid == 5


# ---------------------------------------------------------------------------
# QC statistics
# ---------------------------------------------------------------------------

def test_qc_stats_percentiles_and_dynamic_range():
    frame = _frame_with_gr(np.linspace(0.0, 100.0, 101))
    st = compute_gr_family_qc_stats(frame, _disposition())
    assert st.min_api == pytest.approx(0.0)
    assert st.max_api == pytest.approx(100.0)
    assert st.median_api == pytest.approx(50.0)
    assert st.dynamic_range_p05_p95_api == pytest.approx(90.0)


def test_qc_stats_samples_above_seabed_is_none_when_not_determinable():
    """A well with no approved tops reports None (unknown), never 0, which
    would falsely assert that no such samples exist."""
    frame = _frame_with_gr(np.linspace(10.0, 100.0, 10))
    st = compute_gr_family_qc_stats(frame, _disposition(tops=False), seabed_mdrt_m=None)
    assert st.n_samples_above_seabed is None
    assert "never as 0" in st.seabed_basis


def test_qc_stats_counts_samples_above_seabed_when_determinable():
    md = np.array([100.0, 200.0, 300.0, 380.0])
    frame = _frame_with_gr(np.full(4, 20.0), md=md)
    st = compute_gr_family_qc_stats(frame, _disposition(), seabed_mdrt_m=250.0)
    assert st.n_samples_above_seabed == 2


def test_qc_stats_zero_valid_coverage():
    frame = _frame_with_gr(np.full(8, np.nan))
    st = compute_gr_family_qc_stats(frame, _disposition())
    assert st.valid_count == 0
    assert st.valid_fraction == 0.0
    assert st.median_api is None
    assert st.dynamic_range_p05_p95_api is None
    assert st.longest_missing_block_samples == 8


def test_qc_stats_absent_curve_is_a_factual_gap():
    frame = _frame_with_gr(np.linspace(1.0, 10.0, 5), canonical="GR_api")
    st = compute_gr_family_qc_stats(frame, _disposition(canonical="GRD_api"))
    assert st.valid_count == 0
    assert "never substituted from another well" in st.statistics_basis


def test_qc_stats_reports_valid_and_missing_blocks():
    gr = np.array([1.0, 2.0, np.nan, np.nan, np.nan, 6.0, 7.0])
    frame = _frame_with_gr(gr)
    st = compute_gr_family_qc_stats(frame, _disposition())
    assert st.n_valid_blocks == 2
    assert st.longest_valid_block_samples == 2
    assert st.longest_missing_block_samples == 3


# ---------------------------------------------------------------------------
# Confidence classification
# ---------------------------------------------------------------------------

def test_confidence_class_never_contains_lithology_vocabulary():
    for cls in (GR_PROXY_HIGH, GR_PROXY_INTERMEDIATE, GR_PROXY_LOW,
                GR_NOT_AVAILABLE, GR_EXCLUDED_UNRESOLVED_SCALE):
        assert_no_lithology_vocabulary(cls, "test")


def test_confidence_not_available_when_no_valid_samples():
    frame = _frame_with_gr(np.full(8, np.nan))
    st = compute_gr_family_qc_stats(frame, _disposition())
    cls, _ = classify_gr_proxy_confidence(st, _disposition(), [], _config())
    assert cls == GR_NOT_AVAILABLE


def test_confidence_low_when_dynamic_range_is_poor():
    frame = _frame_with_gr(np.linspace(40.0, 45.0, 50))  # 5 API of range
    st = compute_gr_family_qc_stats(frame, _disposition())
    cls, why = classify_gr_proxy_confidence(st, _disposition(), [], _config())
    assert cls == GR_PROXY_LOW
    assert "dynamic_range" in why


def test_confidence_high_for_well_covered_wide_range_stable_proxy():
    from p2mem.petrophysics import resolve_endpoint_scenarios
    frame = _frame_with_gr(np.linspace(5.0, 205.0, 401))
    d = _disposition()
    cfg = _config()
    st = compute_gr_family_qc_stats(frame, d)
    proxies = [compute_gr_proxy(frame, d, s, cfg) for s in resolve_endpoint_scenarios(frame, d, cfg)]
    cls, _ = classify_gr_proxy_confidence(st, d, proxies, cfg)
    assert cls in (GR_PROXY_HIGH, GR_PROXY_INTERMEDIATE)


# ---------------------------------------------------------------------------
# Contiguous blocks and gap tolerance
# ---------------------------------------------------------------------------

def test_contiguous_blocks_no_bridging_by_default():
    mask = np.array([True, True, False, True, True])
    assert find_contiguous_blocks(mask) == [(0, 1), (3, 4)]


def test_contiguous_blocks_bridges_small_gap_when_both_rules_permit():
    mask = np.array([True, True, False, True, True])
    depth = np.array([0.0, 0.5, 1.0, 1.5, 2.0])
    assert find_contiguous_blocks(mask, depth, max_gap_samples=2, max_gap_depth_m=2.0) == [(0, 4)]


def test_contiguous_blocks_does_not_bridge_large_physical_gap():
    """Sample-count continuity is not physical-depth continuity: a 1-sample
    gap spanning 400 m must start a new block."""
    mask = np.array([True, True, False, True, True])
    depth = np.array([0.0, 0.5, 200.0, 400.0, 400.5])
    assert find_contiguous_blocks(mask, depth, max_gap_samples=2, max_gap_depth_m=1.0) == [(0, 1), (3, 4)]


def test_contiguous_blocks_gap_exactly_at_sample_tolerance_is_bridged():
    mask = np.array([True, False, False, True])
    depth = np.array([0.0, 0.2, 0.4, 0.6])
    assert find_contiguous_blocks(mask, depth, max_gap_samples=2, max_gap_depth_m=1.0) == [(0, 3)]


def test_contiguous_blocks_gap_one_beyond_sample_tolerance_is_not_bridged():
    mask = np.array([True, False, False, False, True])
    depth = np.linspace(0.0, 0.8, 5)
    assert find_contiguous_blocks(mask, depth, max_gap_samples=2, max_gap_depth_m=1.0) == [(0, 0), (4, 4)]


def test_contiguous_blocks_depth_exactly_at_tolerance_is_bridged():
    mask = np.array([True, False, True])
    depth = np.array([0.0, 0.5, 1.0])
    assert find_contiguous_blocks(mask, depth, max_gap_samples=1, max_gap_depth_m=1.0) == [(0, 2)]


def test_contiguous_blocks_empty_mask():
    assert find_contiguous_blocks(np.zeros(5, dtype=bool)) == []


def test_contiguous_blocks_all_true():
    assert find_contiguous_blocks(np.ones(5, dtype=bool)) == [(0, 4)]


def test_contiguous_blocks_rejects_2d_mask():
    with pytest.raises(PetrophysicsInputError, match="1-D"):
        find_contiguous_blocks(np.ones((2, 2), dtype=bool))


def test_contiguous_blocks_rejects_depth_shape_mismatch():
    with pytest.raises(PetrophysicsInputError, match="does not match mask shape"):
        find_contiguous_blocks(np.ones(3, dtype=bool), np.zeros(2))


# ---------------------------------------------------------------------------
# Configuration loading
# ---------------------------------------------------------------------------

def _write_cfg(tmp_path, mutate=None):
    import yaml
    base = {
        "schema_version": "6.0", "increment": 6, "assurance_tier": "Tier C",
        "policy": {
            "endpoint_estimation_method": "per_well_percentile_of_own_valid_samples",
            "cross_well_shared_endpoints_allowed": False,
            "endpoint_sample_basis": "finite_and_depth_mapped_samples_only",
            "clipping_policy": "retain", "clip_lower": 0.0, "clip_upper": 1.0,
            "min_endpoint_separation_api": 1.0,
            "shale_proxy_transform": "linear_identity_of_clipped_igr",
            "nonlinear_vsh_transforms_enabled": False,
            "contiguity": {"max_gap_samples": 2, "max_gap_depth_m": 1.0,
                           "min_block_samples": 20, "min_block_thickness_m": 5.0},
            "nct_candidate_proxy_thresholds": [0.5, 0.6, 0.7],
            "physical_bounds": {"rhob_min_kg_m3": 1000.0, "rhob_max_kg_m3": 3500.0,
                                "vp_min_m_s": 1000.0, "vp_max_m_s": 8000.0,
                                "vs_min_m_s": 300.0, "vs_max_m_s": 5000.0,
                                "vp_vs_ratio_nonnegative_poisson_min_inclusive": 1.4142135623730951,
                                "vp_vs_ratio_positive_bulk_modulus_min_exclusive": 1.1547005383792515,
                                "vp_vs_ratio_plausibility_max": 4.0},
        },
        "endpoint_scenarios": [
            {"scenario_name": "low", "low_percentile": 10.0, "high_percentile": 85.0, "description": "n"},
            {"scenario_name": "base", "low_percentile": 5.0, "high_percentile": 95.0, "description": "m"},
            {"scenario_name": "high", "low_percentile": 1.0, "high_percentile": 99.0, "description": "w"},
        ],
        "wells": {
            "W_1": {"source_las_filename": "W_1.las", "gr_family_canonical_name": "GR_api",
                    "gr_family_source_curve_name": "GR", "use_status": "screening_proxy_allowed",
                    "exclusion_reason": None, "evidence_class": "measured",
                    "has_approved_formation_tops": True, "notes": "n"},
        },
        "gr_proxy_confidence": {"classes": [], "rules": {
            "high": {"min_valid_fraction": 0.9, "min_dynamic_range_api": 60.0,
                     "max_proxy_median_spread_across_scenarios": 0.1},
            "intermediate": {"min_valid_fraction": 0.7, "min_dynamic_range_api": 40.0,
                             "max_proxy_median_spread_across_scenarios": 0.2}}},
        "method_eligibility": {
            "eligible_density_for_sv": {"purpose": "p"},
            "eligible_dynamic_elastic": {"purpose": "p"},
            "eligible_sonic_nct_candidate": {"purpose": "p"},
        },
    }
    if mutate:
        mutate(base)
    p = tmp_path / "cfg.yml"
    p.write_text(yaml.safe_dump(base), encoding="utf-8")
    return str(p)


def test_config_loads_and_validates(tmp_path):
    cfg = load_petrophysics_eligibility_config(_write_cfg(tmp_path))
    assert cfg.schema_version == "6.0"
    assert cfg.scenario_names == ("low", "base", "high")
    assert cfg.wells["W_1"].proxy_permitted


def test_config_missing_file_rejected():
    with pytest.raises(PetrophysicsConfigError, match="not found"):
        load_petrophysics_eligibility_config("/nonexistent/nope.yml")


def test_config_rejects_shared_cross_well_endpoints(tmp_path):
    def m(b):
        b["policy"]["cross_well_shared_endpoints_allowed"] = True
    with pytest.raises(PetrophysicsConfigError, match="cross_well_shared_endpoints_allowed"):
        load_petrophysics_eligibility_config(_write_cfg(tmp_path, m))


def test_config_rejects_enabled_nonlinear_vsh(tmp_path):
    def m(b):
        b["policy"]["nonlinear_vsh_transforms_enabled"] = True
    with pytest.raises(PetrophysicsConfigError, match="nonlinear Vsh transform"):
        load_petrophysics_eligibility_config(_write_cfg(tmp_path, m))


def test_config_rejects_fewer_than_three_scenarios(tmp_path):
    def m(b):
        b["endpoint_scenarios"] = b["endpoint_scenarios"][:2]
    with pytest.raises(PetrophysicsConfigError, match="at least three scenarios"):
        load_petrophysics_eligibility_config(_write_cfg(tmp_path, m))


def test_config_rejects_reversed_scenario_percentiles(tmp_path):
    def m(b):
        b["endpoint_scenarios"][0]["low_percentile"] = 99.0
    with pytest.raises(PetrophysicsConfigError, match="low_percentile < high_percentile"):
        load_petrophysics_eligibility_config(_write_cfg(tmp_path, m))


def test_config_rejects_missing_required_well_key(tmp_path):
    def m(b):
        del b["wells"]["W_1"]["use_status"]
    with pytest.raises(PetrophysicsConfigError, match="missing required key 'use_status'"):
        load_petrophysics_eligibility_config(_write_cfg(tmp_path, m))


def test_config_rejects_duplicate_keys(tmp_path):
    p = tmp_path / "dup.yml"
    p.write_text("schema_version: '6.0'\nschema_version: '6.1'\n", encoding="utf-8")
    with pytest.raises(PetrophysicsConfigError, match="Duplicate key"):
        load_petrophysics_eligibility_config(str(p))


def test_real_project_config_is_valid_and_excludes_boreas():
    """The packaged, human-authored config must itself parse and must carry
    the required dispositions."""
    cfg = load_petrophysics_eligibility_config(str(PROJECT_ROOT / "config" / "petrophysics_eligibility.yml"))
    assert cfg.wells["Boreas_1"].use_status == USE_STATUS_QC_ONLY_EXCLUDED
    assert cfg.wells["Boreas_1"].exclusion_reason == EXCLUSION_REASON_BOREAS_ECGR
    assert not cfg.wells["Boreas_1"].proxy_permitted
    assert cfg.wells["Poseidon_2"].use_status == "screening_proxy_allowed"
    # Increment 6.1 (Finding 2): no approved tops -> must be the depth-tied status.
    assert cfg.wells["Poseidon_North_1"].use_status == "screening_proxy_allowed_depth_tied"
    assert cfg.wells["Poseidon_North_1"].has_approved_formation_tops is False
    assert cfg.wells["Proteus_1ST2"].use_status == "screening_proxy_allowed_depth_tied"
    # Four distinct GR-family curve names, never merged.
    assert cfg.wells["Poseidon_2"].gr_family_canonical_name == "GR_api"
    assert cfg.wells["Boreas_1"].gr_family_canonical_name == "ECGR_api"
    assert cfg.wells["Poseidon_North_1"].gr_family_canonical_name == "GRD_api"
    assert cfg.wells["Proteus_1ST2"].gr_family_canonical_name == "GR_api"


def test_real_project_config_declares_no_named_lithology():
    """No key or value anywhere in the packaged config asserts a rock
    type."""
    import yaml
    with open(PROJECT_ROOT / "config" / "petrophysics_eligibility.yml", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    for well_key, spec in raw["wells"].items():
        for field in ("use_status", "evidence_class", "gr_family_canonical_name"):
            assert_no_lithology_vocabulary(str(spec[field]), f"{well_key}.{field}")
    for cls in raw["gr_proxy_confidence"]["classes"]:
        assert_no_lithology_vocabulary(str(cls), "confidence class")


def test_config_rejects_missing_required_eligibility_mask(tmp_path):
    """All three Increment 6 masks must be declared in the config; an
    undeclared mask is a configuration defect, not a silent default."""
    def m(b):
        del b["method_eligibility"]["eligible_sonic_nct_candidate"]
    with pytest.raises(PetrophysicsConfigError, match="eligible_sonic_nct_candidate"):
        load_petrophysics_eligibility_config(_write_cfg(tmp_path, m))


def test_config_rejects_undocumented_eligibility_mask(tmp_path):
    """An eligibility mask with no stated purpose is not auditable."""
    def m(b):
        b["method_eligibility"]["eligible_density_for_sv"] = {}
    with pytest.raises(PetrophysicsConfigError, match="not auditable"):
        load_petrophysics_eligibility_config(_write_cfg(tmp_path, m))


def test_real_project_config_documents_all_three_masks():
    cfg = load_petrophysics_eligibility_config(
        str(PROJECT_ROOT / "config" / "petrophysics_eligibility.yml")
    )
    for mask in ("eligible_density_for_sv", "eligible_dynamic_elastic",
                 "eligible_sonic_nct_candidate"):
        assert cfg.method_eligibility[mask]["purpose"].strip()
    # The lithology-dependent mask must be the ONLY one flagged as such, and
    # must not apply to a GR-excluded well.
    assert cfg.method_eligibility["eligible_sonic_nct_candidate"]["lithology_dependent"] is True
    assert cfg.method_eligibility["eligible_sonic_nct_candidate"][
        "applies_to_excluded_gr_wells"] is False
    assert cfg.method_eligibility["eligible_density_for_sv"]["lithology_dependent"] is False
    assert cfg.method_eligibility["eligible_dynamic_elastic"]["lithology_dependent"] is False


# ---------------------------------------------------------------------------
# Increment 6.1 (Finding 2): no-tops / depth-tied config invariant
# ---------------------------------------------------------------------------

def test_config_rejects_proxy_allowed_without_approved_tops(tmp_path):
    """A proxy-permitted well with NO approved formation tops must use the
    depth-tied status. The plain status asserts a stratigraphic tie the well
    does not have, and the contradiction must fail loudly."""
    def m(b):
        b["wells"]["W_1"]["has_approved_formation_tops"] = False
        b["wells"]["W_1"]["use_status"] = "screening_proxy_allowed"
    with pytest.raises(PetrophysicsConfigError, match="screening_proxy_allowed_depth_tied"):
        load_petrophysics_eligibility_config(_write_cfg(tmp_path, m))


def test_config_rejects_depth_tied_when_tops_actually_exist(tmp_path):
    """The converse contradiction is equally a config/reality mismatch."""
    def m(b):
        b["wells"]["W_1"]["has_approved_formation_tops"] = True
        b["wells"]["W_1"]["use_status"] = "screening_proxy_allowed_depth_tied"
    with pytest.raises(PetrophysicsConfigError, match="reserved for wells with NO approved"):
        load_petrophysics_eligibility_config(_write_cfg(tmp_path, m))


def test_config_accepts_the_two_consistent_combinations(tmp_path):
    """Both self-consistent pairings load cleanly."""
    def has_tops(b):
        b["wells"]["W_1"]["has_approved_formation_tops"] = True
        b["wells"]["W_1"]["use_status"] = "screening_proxy_allowed"
    def no_tops(b):
        b["wells"]["W_1"]["has_approved_formation_tops"] = False
        b["wells"]["W_1"]["use_status"] = "screening_proxy_allowed_depth_tied"
    for mut, expected in ((has_tops, "screening_proxy_allowed"),
                          (no_tops, "screening_proxy_allowed_depth_tied")):
        cfg = load_petrophysics_eligibility_config(_write_cfg(tmp_path, mut))
        assert cfg.wells["W_1"].use_status == expected


def test_excluded_well_without_tops_is_not_forced_to_depth_tied(tmp_path):
    """The invariant applies only to PROXY-PERMITTED wells: an excluded well
    keeps its qc_only status regardless of whether it has tops."""
    def m(b):
        b["wells"]["W_1"]["has_approved_formation_tops"] = False
        b["wells"]["W_1"]["use_status"] = "qc_only_excluded"
        b["wells"]["W_1"]["exclusion_reason"] = "SOME_REASON"
    cfg = load_petrophysics_eligibility_config(_write_cfg(tmp_path, m))
    assert cfg.wells["W_1"].use_status == "qc_only_excluded"


def test_real_project_config_poseidon_north_1_is_depth_tied():
    """The real config must satisfy the invariant it now enforces."""
    cfg = load_petrophysics_eligibility_config(
        str(PROJECT_ROOT / "config" / "petrophysics_eligibility.yml")
    )
    for wk, d in cfg.wells.items():
        if d.proxy_permitted:
            assert d.has_approved_formation_tops == (
                d.use_status == "screening_proxy_allowed"
            ), f"{wk}: use_status and has_approved_formation_tops disagree"
    assert cfg.wells["Poseidon_North_1"].use_status == "screening_proxy_allowed_depth_tied"
    assert cfg.wells["Proteus_1ST2"].use_status == "screening_proxy_allowed_depth_tied"
    assert cfg.wells["Poseidon_2"].use_status == "screening_proxy_allowed"


# ---------------------------------------------------------------------------
# Increment 6.1 (Finding 1): the corrected Vp/Vs bound names in the real config
# ---------------------------------------------------------------------------

def test_real_config_declares_the_three_separated_vp_vs_bounds():
    cfg = load_petrophysics_eligibility_config(
        str(PROJECT_ROOT / "config" / "petrophysics_eligibility.yml")
    )
    b = cfg.policy["physical_bounds"]
    assert b["vp_vs_ratio_nonnegative_poisson_min_inclusive"] == pytest.approx(np.sqrt(2.0))
    assert b["vp_vs_ratio_positive_bulk_modulus_min_exclusive"] == pytest.approx(np.sqrt(4.0 / 3.0))
    assert b["vp_vs_ratio_plausibility_max"] == pytest.approx(4.0)
    # The old, conflating key must be gone.
    assert "vp_vs_ratio_min_exclusive" not in b


# ---------------------------------------------------------------------------
# Increment 6.1 (Finding 3): the prohibited vocabulary and scope model
# ---------------------------------------------------------------------------

def test_clastic_and_rock_class_terms_are_prohibited():
    from p2mem.wellframe_models import PROHIBITED_LITHOLOGY_TERMS
    for term in ("clastic", "siliciclastic", "volcanic", "basement"):
        assert term in PROHIBITED_LITHOLOGY_TERMS


def test_unknown_validation_scope_rejected():
    from p2mem.wellframe_models import validate_no_prohibited_interpretation
    with pytest.raises(ValueError, match="unknown validation scope"):
        validate_no_prohibited_interpretation([("c", "text", "whatever")])

# ---------------------------------------------------------------------------
# Increment 6.1.5: POSITIVE AUTHORIZATION.
#
# Increments 6.1 through 6.1.4 asked "does this text contain a geological
# assertion?" and were defeated four times, finally by `chalk` - a word no
# recognizer had been given. These tests assert the inverted contract: nothing
# is acceptable by default, and rejection never depends on recognizing a rock.
# ---------------------------------------------------------------------------

import p2mem.wellframe_models as _wm


def _V(text, scope, auth=None, context="audit.field"):
    entry = (context, text, scope, auth) if auth is not None else (context, text, scope)
    return _wm.validate_no_prohibited_interpretation([entry])


def _scope(name):
    return {"label": _wm.SCOPE_LABEL, "interpretive": _wm.SCOPE_INTERPRETIVE,
            "method": _wm.SCOPE_METHOD, "explanatory": _wm.SCOPE_EXPLANATORY}[name]


CONTROLLED = ["label", "interpretive", "explanatory", "method"]

# The lithologies the Increment 6.1.5 audit named, plus a fabricated word.
# NONE of these is in PROHIBITED_LITHOLOGY_TERMS - that is the point.
UNKNOWN_LITHOLOGY_ASSERTIONS = [
    "The interval is chalk.", "The interval is halite.", "The interval is gypsum.",
    "The interval is conglomerate.", "The interval is chert.", "The interval is tuff.",
    "The interval is basalt.", "The interval is dolostone.", "The interval is lignite.",
    "The interval is calcareous.", "The interval is argillaceous.",
    "The interval is arenaceous.",
]
FABRICATED_ASSERTIONS = ["The interval is qxzite.", "The interval is zzqqworp."]
INNOCENT_UNREGISTERED = [
    "Everything looks fine.", "The operator was competent.",
    "Data coverage is good in the deep section.",
]


@pytest.mark.parametrize("scope_name", CONTROLLED)
@pytest.mark.parametrize("text", UNKNOWN_LITHOLOGY_ASSERTIONS)
def test_unknown_lithology_assertions_are_rejected_in_every_controlled_scope(text, scope_name):
    assert _V(text, _scope(scope_name)), f"{text!r} in {scope_name}"


@pytest.mark.parametrize("scope_name", CONTROLLED)
@pytest.mark.parametrize("text", FABRICATED_ASSERTIONS)
def test_fabricated_words_are_rejected_because_nothing_authorized_them(text, scope_name):
    assert _V(text, _scope(scope_name)), f"{text!r} in {scope_name}"


@pytest.mark.parametrize("scope_name", CONTROLLED)
@pytest.mark.parametrize("text", INNOCENT_UNREGISTERED)
def test_innocent_unregistered_text_is_rejected_too(text, scope_name):
    """THE decisive test. These contain no rock word at all, so a detector has
    nothing to detect. They are rejected because the rule is positive
    authorization, not hidden semantic detection."""
    assert _V(text, _scope(scope_name)), f"{text!r} in {scope_name}"


@pytest.mark.parametrize(
    "text", UNKNOWN_LITHOLOGY_ASSERTIONS + FABRICATED_ASSERTIONS + INNOCENT_UNREGISTERED)
def test_the_linter_recognizes_nothing_in_any_of_these(text):
    """Proves the rejections above owe nothing to the blacklist: it is empty
    for every one of them."""
    assert _wm.find_prohibited_lithology_terms(text) == (), text


def test_the_blacklist_is_documented_as_a_linter_and_authorizes_nothing():
    doc = " ".join((_wm.find_prohibited_lithology_terms.__doc__ or "").split())
    assert "AUTHORIZES NOTHING" in doc
    assert "not exhaustive" in doc.lower()


# --- LABEL scope: typed, enumerated values only ----------------------------

def test_every_approved_label_passes_under_its_own_field_kind():
    for field_kind, bucket in _wm.APPROVED_LABELS.items():
        for value, lab in bucket.items():
            auth = _wm.Authorization(field_kind=field_kind)
            assert _V(value, _scope("label"), auth) == (), (field_kind, value)
            assert lab.field_kind == field_kind and lab.purpose
            assert len(lab.provenance) > 40


def test_every_label_fails_under_every_other_field_kind():
    """Requirement 3: a complete cross-product across all registered labels and
    field kinds. A value approved under one kind authorizes nothing elsewhere."""
    kinds = _wm.APPROVED_LABEL_FIELD_KINDS
    checked = 0
    for own_kind, bucket in _wm.APPROVED_LABELS.items():
        for value in bucket:
            for other in kinds:
                if other == own_kind or value in _wm.APPROVED_LABELS[other]:
                    continue
                checked += 1
                assert _V(value, _scope("label"), _wm.Authorization(field_kind=other)), (
                    f"{value!r} wrongly accepted as {other!r}")
    assert checked >= 100, f"cross-product must be substantive, checked {checked}"


def test_unknown_field_kind_and_missing_field_kind_fail():
    assert _V("measured", _scope("label"), _wm.Authorization(field_kind="no_such_kind"))
    assert _V("measured", _scope("label"))


def test_the_audited_field_kind_mismatches_fail():
    assert _V("GR", _scope("label"), _wm.Authorization(field_kind="use_status"))
    assert _V("measured", _scope("label"), _wm.Authorization(field_kind="mask_name"))
    assert _V("screening_proxy_allowed", _scope("label"),
              _wm.Authorization(field_kind="use_status")) == ()
    assert _V("GR", _scope("label"),
              _wm.Authorization(field_kind="gr_family_source_curve_name")) == ()


@pytest.mark.parametrize("value", [
    "screening_proxy_allowed_v2", "SCREENING_PROXY_ALLOWED", "measured ",
    "GR_PROXY_MEDIUM", "arbitrary_label", "chalk_proxy_high",
])
def test_unapproved_label_values_are_rejected(value):
    assert _V(value, _scope("label"), _wm.Authorization(field_kind="use_status")), value


# --- Registered statements: id and text validated together -----------------

def test_every_registered_statement_passes_under_its_own_id():
    for sid, st in _wm.REGISTERED_STATEMENTS.items():
        auth = _wm.Authorization(statement_id=sid)
        assert _V(st.text, st.scope, auth) == (), sid
        assert st.purpose and len(st.provenance) > 40


def _a_method_statement():
    """The longest registered method statement, so every mutation below is a
    genuine near-miss rather than a no-op."""
    sid = max((k for k, v in _wm.REGISTERED_STATEMENTS.items()
               if v.scope == _wm.SCOPE_METHOD),
              key=lambda k: len(_wm.REGISTERED_STATEMENTS[k].text))
    return sid, _wm.REGISTERED_STATEMENTS[sid]


@pytest.mark.parametrize("mutate,label", [
    (lambda t: t.upper(), "case change"),
    (lambda t: t + " ", "trailing space"),
    (lambda t: t + " Additional clause.", "added clause"),
    (lambda t: t[:-1], "truncated"),
    (lambda t: t.replace(".", ""), "punctuation removed"),
])
def test_near_miss_text_fails_against_its_registered_id(mutate, label):
    sid, st = _a_method_statement()
    mutated = mutate(st.text)
    assert mutated != st.text, f"{label} must actually mutate the statement"
    assert _V(mutated, st.scope, _wm.Authorization(statement_id=sid)), label


@pytest.mark.parametrize("sid", sorted(
    k for k, v in _wm.REGISTERED_STATEMENTS.items() if v.scope == _wm.SCOPE_METHOD))
def test_every_method_statement_rejects_a_case_change(sid):
    """Applied to EVERY method statement, so no single statement carries the
    exact-equality guarantee alone."""
    st = _wm.REGISTERED_STATEMENTS[sid]
    if st.text.upper() == st.text:
        pytest.skip("statement has no case to change")
    assert _V(st.text.upper(), st.scope, _wm.Authorization(statement_id=sid))


def test_unknown_statement_id_fails():
    sid, st = _a_method_statement()
    assert _V(st.text, st.scope, _wm.Authorization(statement_id="no_such_statement"))


def test_id_text_mismatch_fails():
    sid, st = _a_method_statement()
    other = [v for k, v in _wm.REGISTERED_STATEMENTS.items()
             if v.scope == st.scope and k != sid][0]
    assert _V(other.text, st.scope, _wm.Authorization(statement_id=sid))


def test_statement_cannot_authorize_a_different_scope():
    sid, st = _a_method_statement()
    other = _wm.SCOPE_INTERPRETIVE if st.scope != _wm.SCOPE_INTERPRETIVE else _wm.SCOPE_METHOD
    assert _V(st.text, other, _wm.Authorization(statement_id=sid))


def test_presenting_both_a_statement_id_and_a_template_id_fails():
    sid, st = _a_method_statement()
    auth = _wm.Authorization(statement_id=sid, template_id="gr_proxy_confidence_rationale")
    assert _V(st.text, st.scope, auth)


def test_registry_ids_are_unique():
    assert _wm._duplicate_registry_ids() == []


# --- Templates: controlled prose, strictly typed substitutions -------------

def _tpl():
    return _wm.REGISTERED_TEMPLATES["gr_proxy_confidence_rationale"]


GOOD_FIELDS = {"valid_fraction": "0.8131", "dynamic_range_p05_p95": "135.761",
               "proxy_median_spread": "0.1184"}


def test_template_renders_and_passes_with_typed_substitutions():
    t = _tpl()
    auth = _wm.Authorization(template_id=t.template_id, fields=GOOD_FIELDS)
    assert _V(t.render(GOOD_FIELDS), t.scope, auth) == ()


@pytest.mark.parametrize("value", ["high", "very high", "0.1.2", "", "1e5", "NaN", "abc"])
def test_template_substitution_must_satisfy_its_declared_type(value):
    """A substitution slot is restricted to a decimal literal, so a template
    can never become a channel for prose."""
    t = _tpl()
    fields = dict(GOOD_FIELDS, proxy_median_spread=value)
    text = t.template.replace("{proxy_median_spread}", value).format(
        **{k: v for k, v in fields.items() if k != "proxy_median_spread"})
    assert _V(text, t.scope, _wm.Authorization(template_id=t.template_id, fields=fields))


def test_undeclared_or_missing_template_fields_fail():
    t = _tpl()
    extra = dict(GOOD_FIELDS, sneaky="1.0")
    assert _V(t.render(GOOD_FIELDS), t.scope,
              _wm.Authorization(template_id=t.template_id, fields=extra))
    missing = {k: v for k, v in GOOD_FIELDS.items() if k != "valid_fraction"}
    assert _V(t.render(GOOD_FIELDS), t.scope,
              _wm.Authorization(template_id=t.template_id, fields=missing))


def test_unknown_template_id_fails():
    t = _tpl()
    assert _V(t.render(GOOD_FIELDS), t.scope,
              _wm.Authorization(template_id="no_such_template", fields=GOOD_FIELDS))


def test_text_not_matching_the_rendered_template_fails():
    t = _tpl()
    auth = _wm.Authorization(template_id=t.template_id, fields=GOOD_FIELDS)
    assert _V(t.render(GOOD_FIELDS) + " Extra.", t.scope, auth)


# --- The legitimate limitation statements, routed properly -----------------

@pytest.mark.parametrize("text", [
    "The well contains no shale volume estimate.",
    "This method for the interval contains a shale proxy calculation.",
])
def test_legitimate_sounding_limitations_still_need_a_registered_id(text):
    """These read as reasonable method/limitation prose. They are rejected in
    every controlled scope because no registered statement authorizes them -
    NOT by a grammar-based interpretive exemption, which no longer exists."""
    for scope_name in CONTROLLED:
        assert _V(text, _scope(scope_name)), f"{text!r} in {scope_name}"


def test_the_projects_real_limitation_statement_passes_through_its_id():
    """The need those sentences express is real, and is met by the registered
    limitation statement the project actually persists."""
    st = _wm.REGISTERED_STATEMENTS["proxy_limitations"]
    assert _V(st.text, st.scope, _wm.Authorization(statement_id=st.statement_id)) == ()
    assert "not a calibrated shale volume" in st.text.lower()


# --- No fallback path ------------------------------------------------------

def test_no_scope_accepts_text_merely_because_no_rock_term_was_found():
    """Sweep every controlled scope with text the linter cannot fault. If any
    scope accepted it, an unknown lithology would have a way in."""
    accepted = []
    for scope_name in CONTROLLED:
        for text in INNOCENT_UNREGISTERED + FABRICATED_ASSERTIONS:
            assert _wm.find_prohibited_lithology_terms(text) == ()
            if not _V(text, _scope(scope_name)):
                accepted.append((scope_name, text))
    assert not accepted, f"fallback acceptance path found: {accepted}"


def test_an_entry_without_authorization_is_rejected_in_prose_scopes():
    for scope_name in ("interpretive", "method", "explanatory"):
        v = _V("Any text at all.", _scope(scope_name))
        assert v and "authorization" in v[0]["reason"].lower()


def test_malformed_scope_entry_is_rejected_loudly():
    with pytest.raises(ValueError, match="context, text, scope"):
        _wm.validate_no_prohibited_interpretation([("a", "b")])
    with pytest.raises(ValueError, match="unknown validation scope"):
        _wm.validate_no_prohibited_interpretation([("a", "b", "nonsense")])


# --- Real packaged content is fully accounted for --------------------------

def test_every_real_persisted_field_is_positively_authorized():
    """Requirement 7/12: every real per-well note resolves to an authorization
    and every real label is approved UNDER ITS OWN FIELD KIND."""
    from p2mem.io.petrophysics_inventory import _authorized
    from p2mem.petrophysics import load_petrophysics_eligibility_config
    cfg = load_petrophysics_eligibility_config(
        str(PROJECT_ROOT / "config" / "petrophysics_eligibility.yml"))
    entries = [(f"{wk}.config_notes", d.notes, _wm.SCOPE_INTERPRETIVE)
               for wk, d in cfg.wells.items()]
    authorized = [_authorized(c, t, s) for c, t, s in entries]
    assert all(len(e) == 4 for e in authorized)
    assert _wm.validate_no_prohibited_interpretation(authorized) == ()
    for wk, d in cfg.wells.items():
        for kind, value in (("use_status", d.use_status),
                            ("evidence_class", d.evidence_class),
                            ("gr_family_canonical_name", d.gr_family_canonical_name),
                            ("gr_family_source_curve_name", d.gr_family_source_curve_name)):
            assert _wm.approved_label(kind, value) is not None, f"{wk}: {kind}={value!r}"
