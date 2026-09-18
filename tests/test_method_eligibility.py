"""
Increment 6 - method-eligibility mask, interval-register, and export tests.

SYNTHETIC ONLY. No real or private project file is read or packaged.
"""

import json

import numpy as np
from p2mem.wellframe_models import Authorization
import pytest

from p2mem.io.petrophysics_inventory import (
    build_eligibility_interval_rows,
    build_gr_endpoint_scenario_rows,
    build_gr_family_qc_rows,
    build_gr_proxy_sensitivity_rows,
    build_method_eligibility_rows,
    build_petrophysics_issue_rows,
    build_petrophysics_manifest,
    build_thickness_sensitivity_rows,
)
from p2mem.method_eligibility import (
    MASK_DENSITY_FOR_SV,
    MASK_DYNAMIC_ELASTIC,
    MASK_SONIC_NCT_CANDIDATE,
    build_eligibility_intervals,
    compute_density_eligibility,
    compute_dynamic_elastic_eligibility,
    compute_sonic_nct_candidate_eligibility,
)
from p2mem.petrophysics import (
    PetrophysicsInputError,
    compute_gr_family_qc_stats,
    compute_gr_proxy,
)
from p2mem.petrophysics_models import (
    EXCLUSION_REASON_BOREAS_ECGR,
    USE_STATUS_QC_ONLY_EXCLUDED,
    GrFamilyDisposition,
    PetrophysicsIssue,
)
from p2mem.wellframe import assemble_well_frame
from p2mem.wellframe_models import (
    WellFrameAssemblyFailure,
    assert_no_lithology_vocabulary,
)

from synthetic_inc6 import synthetic_las as _synthetic_las  # noqa: E402
from synthetic_inc6 import synthetic_survey as _synthetic_survey  # noqa: E402
from test_petrophysics import _config, _disposition, _scenario  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic frame builder with the full curve set
# ---------------------------------------------------------------------------

def _full_frame(
    n=10, rhob=2400.0, vp=4000.0, vs=2200.0, gr=50.0, well_key="Synth_1", md=None,
):
    """A frame carrying RHOB/VP/VS/GR. Scalars broadcast to length n;
    arrays are used verbatim."""
    def arr(x):
        return np.asarray(x, dtype=float) if np.ndim(x) else np.full(n, float(x))

    md = np.linspace(50.0, 350.0, n) if md is None else np.asarray(md, dtype=float)
    las = _synthetic_las(
        {"MD_m": md, "RHOB_kg_m3": arr(rhob), "VP_m_s": arr(vp),
         "VS_m_s": arr(vs), "GR_api": arr(gr)},
        well_name=well_key,
    )
    dev = _synthetic_survey(well_key, md=(0.0, 200.0, 400.0), tvd=(0.0, 199.0, 396.0))
    return assemble_well_frame(
        well_key, las, dev, las_path=f"/private/build/{well_key}.las",
        survey_path=f"/private/build/{well_key}_dev.txt", gr_family_canonical_name="GR_api",
    )


# ---------------------------------------------------------------------------
# Density eligibility
# ---------------------------------------------------------------------------

def test_density_mask_all_eligible_when_valid():
    m = compute_density_eligibility(_full_frame(), _config())
    assert m.mask_name == MASK_DENSITY_FOR_SV
    assert m.n_eligible == 10
    assert m.eligible_fraction == pytest.approx(1.0)
    assert not m.lithology_dependent


def test_density_mask_rejects_nan_density():
    rhob = np.full(10, 2400.0)
    rhob[3] = np.nan
    m = compute_density_eligibility(_full_frame(rhob=rhob), _config())
    assert m.n_eligible == 9
    assert not m.mask[3]


@pytest.mark.parametrize("bad", [-2400.0, 0.0, 100.0, 9000.0, np.inf, -np.inf])
def test_density_mask_rejects_non_physical_density(bad):
    """Non-physical density is excluded from the mask - never repaired."""
    rhob = np.full(10, 2400.0)
    rhob[5] = bad
    m = compute_density_eligibility(_full_frame(rhob=rhob), _config())
    assert not m.mask[5]
    assert m.n_eligible == 9


def test_density_mask_absent_curve_yields_all_false_not_implicit_pass():
    md = np.linspace(50.0, 350.0, 5)
    las = _synthetic_las({"MD_m": md, "GR_api": np.full(5, 40.0)})
    frame = assemble_well_frame(
        "Synth_1", las, _synthetic_survey(md=(0.0, 200.0, 400.0), tvd=(0.0, 199.0, 396.0)),
        las_path="/s/a.las", survey_path="/s/a_dev.txt",
    )
    m = compute_density_eligibility(frame, _config())
    assert m.n_eligible == 0
    assert not m.mask.any()


def test_density_mask_requires_mapped_depth():
    md = np.array([50.0, 100.0, 200.0, 300.0, 900.0])  # last beyond coverage
    m = compute_density_eligibility(_full_frame(n=5, md=md), _config())
    assert not m.mask[-1]
    assert m.n_eligible == 4


def test_density_mask_computed_for_gr_excluded_well():
    """GR exclusion is about the GR curve, not about density: a
    lithology-independent mask is still computed for an excluded well."""
    m = compute_density_eligibility(_full_frame(well_key="Boreas_1"), _config())
    assert m.n_eligible == 10


# ---------------------------------------------------------------------------
# Dynamic-elastic eligibility
# ---------------------------------------------------------------------------

def test_dynamic_elastic_mask_all_eligible_when_physical():
    m = compute_dynamic_elastic_eligibility(_full_frame(vp=4000.0, vs=2200.0), _config())
    assert m.mask_name == MASK_DYNAMIC_ELASTIC
    assert m.n_eligible == 10


def test_dynamic_elastic_rejects_vp_not_greater_than_vs():
    vp = np.full(10, 4000.0)
    vp[2] = 2000.0  # below VS
    m = compute_dynamic_elastic_eligibility(_full_frame(vp=vp, vs=2200.0), _config())
    assert not m.mask[2]


# ---------------------------------------------------------------------------
# Increment 6.1 (Finding 1): Vp/Vs regimes, stated correctly
#
#     nu = (r^2 - 2) / (2 * (r^2 - 1)),  r = Vp/Vs
#     K  = rho * (Vp^2 - (4/3) * Vs^2)
#
# r = sqrt(2)          -> nu = 0 exactly            -> MUST PASS a
#                                                     non-negative-nu screen
# sqrt(4/3) < r < sqrt(2) -> K > 0, nu < 0          -> excluded by POLICY,
#                                                     NOT "non-physical"
# r <= sqrt(4/3)       -> K <= 0                    -> genuinely outside the
#                                                     isotropic elastic model
# r > 4                -> ordinary nu (~0.467)      -> configured PLAUSIBILITY
#                                                     limit only
# ---------------------------------------------------------------------------

def _nu(r):
    """Dynamic Poisson's ratio for an isotropic elastic solid."""
    return (r ** 2 - 2.0) / (2.0 * (r ** 2 - 1.0))


def _bulk_modulus(rho, vp, vs):
    """K = rho * (Vp^2 - 4/3 Vs^2)."""
    return rho * (vp ** 2 - (4.0 / 3.0) * vs ** 2)


def test_poisson_ratio_is_exactly_zero_at_sqrt2():
    """The analytic anchor for the inclusive bound."""
    assert _nu(np.sqrt(2.0)) == pytest.approx(0.0, abs=1e-12)
    assert _nu(4.0) == pytest.approx(7.0 / 15.0)  # ~0.4667: an ordinary ratio


def test_vp_vs_exactly_sqrt2_passes_nonnegative_poisson_screen():
    """r = sqrt(2) gives nu = 0, which a NON-NEGATIVE-nu policy must ACCEPT.
    Increment 6 used an exclusive bound and wrongly rejected it."""
    vs = np.full(10, 2200.0)
    vp = np.full(10, 4000.0)
    vp[4] = 2200.0 * np.sqrt(2.0)  # r == sqrt(2) exactly
    frame = _full_frame(vp=vp, vs=vs)
    m = compute_dynamic_elastic_eligibility(frame, _config())
    assert _nu(vp[4] / vs[4]) == pytest.approx(0.0, abs=1e-12)
    assert m.mask[4], "nu = 0 must pass a non-negative-Poisson-ratio screen"
    assert m.n_eligible == 10
    assert m.diagnostic_counts["n_ratio_positive_bulk_but_negative_poisson"] == 0
    assert m.diagnostic_counts["n_ratio_nonpositive_bulk_modulus"] == 0


def test_positive_bulk_modulus_with_negative_poisson_is_diagnosed_separately():
    """sqrt(4/3) < r < sqrt(2): K > 0 and nu < 0. Excluded by POLICY, and
    NEVER counted as non-positive-bulk-modulus or called non-physical."""
    vs = np.full(10, 2200.0)
    vp = np.full(10, 4000.0)
    vp[3] = 2200.0 * 1.30  # sqrt(4/3)=1.1547 < 1.30 < sqrt(2)=1.41421
    frame = _full_frame(vp=vp, vs=vs)
    r = vp[3] / vs[3]
    assert np.sqrt(4.0 / 3.0) < r < np.sqrt(2.0)
    assert _bulk_modulus(2400.0, vp[3], vs[3]) > 0.0, "K must be positive here"
    assert _nu(r) < 0.0, "nu must be negative here"
    m = compute_dynamic_elastic_eligibility(frame, _config())
    assert not m.mask[3]
    assert m.diagnostic_counts["n_ratio_positive_bulk_but_negative_poisson"] == 1
    assert m.diagnostic_counts["n_ratio_nonpositive_bulk_modulus"] == 0
    assert m.n_eligible == 9


def test_nonpositive_bulk_modulus_is_diagnosed_separately():
    """r <= sqrt(4/3) implies K <= 0 - genuinely outside the isotropic
    elastic model, and the ONLY regime that warrants that description."""
    vs = np.full(10, 2200.0)
    vp = np.full(10, 4000.0)
    vp[2] = 2200.0 * np.sqrt(4.0 / 3.0)  # r == sqrt(4/3) exactly -> K == 0
    vp[6] = 2200.0 * 1.10                # r < sqrt(4/3)         -> K < 0
    frame = _full_frame(vp=vp, vs=vs)
    # K here is O(1e10), so compare relative to the rho*Vp^2 scale rather than
    # against a meaningless absolute tolerance.
    _scale = 2400.0 * vp[2] ** 2
    assert abs(_bulk_modulus(2400.0, vp[2], vs[2])) < 1e-12 * _scale
    assert _bulk_modulus(2400.0, vp[6], vs[6]) < 0.0
    m = compute_dynamic_elastic_eligibility(frame, _config())
    assert not m.mask[2] and not m.mask[6]
    assert m.diagnostic_counts["n_ratio_nonpositive_bulk_modulus"] == 2
    assert m.diagnostic_counts["n_ratio_positive_bulk_but_negative_poisson"] == 0
    assert m.n_eligible == 8


def test_ratio_above_configured_plausibility_max_is_diagnosed_separately():
    """r > 4 has an ordinary Poisson's ratio; it is outside a CONFIGURED
    plausibility limit, not outside the mathematical Poisson domain."""
    vs = np.full(10, 700.0)
    vp = np.full(10, 2800.0)   # r = 4.0 exactly -> inside the inclusive max
    vp[8] = 700.0 * 5.0        # r = 5.0 -> above the configured max
    frame = _full_frame(vp=vp, vs=vs)
    assert 0.0 < _nu(5.0) < 0.5, "r = 5 still gives an ordinary Poisson ratio"
    m = compute_dynamic_elastic_eligibility(frame, _config())
    assert m.mask[0], "r = 4.0 is at the inclusive configured maximum"
    assert not m.mask[8]
    assert m.diagnostic_counts["n_ratio_above_configured_plausibility_max"] == 1
    assert m.diagnostic_counts["n_ratio_nonpositive_bulk_modulus"] == 0
    assert m.diagnostic_counts["n_ratio_positive_bulk_but_negative_poisson"] == 0


def test_vp_vs_regime_diagnostics_are_mutually_exclusive_and_exhaustive():
    """Every both-velocities-valid sample lands in exactly one regime."""
    # VS = 1000 m/s keeps every VP below the 8000 m/s plausibility bound, so
    # each sample genuinely reaches the both-velocities-valid subset.
    vs = np.full(12, 1000.0)
    vp = np.full(12, 3000.0)
    vp[0] = 1000.0 * 1.10               # K <= 0
    vp[1] = 1000.0 * np.sqrt(4.0 / 3.0) # K == 0
    vp[2] = 1000.0 * 1.30               # K > 0, nu < 0
    vp[3] = 1000.0 * np.sqrt(2.0)       # nu == 0 -> passes
    vp[4] = 1000.0 * 5.0                # above configured max
    m = compute_dynamic_elastic_eligibility(_full_frame(n=12, vp=vp, vs=vs), _config())
    d = m.diagnostic_counts
    total = (d["n_ratio_nonpositive_bulk_modulus"]
             + d["n_ratio_positive_bulk_but_negative_poisson"]
             + d["n_ratio_above_configured_plausibility_max"]
             + d["n_passes_nonnegative_poisson_screen"])
    assert total == d["n_vp_and_vs_both_valid"] == 12
    assert d["n_ratio_nonpositive_bulk_modulus"] == 2
    assert d["n_ratio_positive_bulk_but_negative_poisson"] == 1
    assert d["n_ratio_above_configured_plausibility_max"] == 1
    assert d["n_passes_nonnegative_poisson_screen"] == 8


def test_no_diagnostic_or_note_aggregates_regimes_as_non_physical():
    """The phrase must not reappear as a blanket label over all excluded
    ratios - that conflation is exactly what Increment 6.1 corrects."""
    m = compute_dynamic_elastic_eligibility(_full_frame(), _config())
    for key in m.diagnostic_counts:
        assert "non_physical" not in key.lower()
        assert "nonphysical" not in key.lower()
    low = m.notes.lower()
    assert "never aggregated" in low
    assert "not non-physical" in low or "not a test of physical possibility" in low


def test_dynamic_elastic_rejects_nan_in_any_of_the_three_inputs():
    for curve in ("vp", "vs", "rhob"):
        kwargs = {"vp": 4000.0, "vs": 2200.0, "rhob": 2400.0}
        arr = np.full(10, kwargs[curve])
        arr[7] = np.nan
        kwargs[curve] = arr
        m = compute_dynamic_elastic_eligibility(_full_frame(**kwargs), _config())
        assert not m.mask[7], f"{curve} NaN should disqualify the sample"
        assert m.n_eligible == 9


def test_dynamic_elastic_reports_limiting_criterion():
    vs = np.full(10, 2200.0)
    vs[:6] = np.nan  # VS is by far the most limiting input
    m = compute_dynamic_elastic_eligibility(_full_frame(vs=vs), _config())
    assert m.limiting_criterion == "vs_finite_positive_in_bounds"
    assert m.n_eligible == 4


def test_dynamic_elastic_does_not_compute_any_elastic_property():
    """The result exposes only a mask and counts - no modulus, no Poisson
    ratio, no elastic curve of any kind."""
    m = compute_dynamic_elastic_eligibility(_full_frame(), _config())
    exposed = set(m.__slots__)
    for forbidden in ("youngs_modulus", "poisson_ratio", "bulk_modulus", "shear_modulus",
                      "vp_vs_ratio", "elastic"):
        assert not any(forbidden in name for name in exposed)


# ---------------------------------------------------------------------------
# Sonic-NCT candidate eligibility
# ---------------------------------------------------------------------------

def _proxy_for(frame, cfg=None, low=10.0, high=110.0):
    cfg = cfg or _config()
    return compute_gr_proxy(
        frame, _disposition(frame.well_key), _scenario(low, high, well_key=frame.well_key), cfg
    )


def test_nct_candidate_mask_basic():
    frame = _full_frame(gr=np.linspace(10.0, 110.0, 10))
    p = _proxy_for(frame)
    m = compute_sonic_nct_candidate_eligibility(
        frame, _disposition(), p, 0.5, _config()
    )
    assert m.mask_name == MASK_SONIC_NCT_CANDIDATE
    assert m.lithology_dependent
    assert m.proxy_threshold == 0.5
    assert m.scenario_name == p.scenario_name
    assert 0 < m.n_eligible < 10


def test_nct_candidate_threshold_sensitivity_is_monotonic():
    frame = _full_frame(n=101, gr=np.linspace(0.0, 200.0, 101))
    p = _proxy_for(frame)
    counts = [
        compute_sonic_nct_candidate_eligibility(frame, _disposition(), p, t, _config()).n_eligible
        for t in (0.5, 0.6, 0.7)
    ]
    assert counts[0] >= counts[1] >= counts[2]
    assert counts[0] > counts[2]  # the threshold genuinely bites


def test_nct_candidate_forbidden_for_gr_excluded_well():
    """A lithology-dependent mask can never exist for a GR-excluded well."""
    frame = _full_frame(well_key="Boreas_1")
    d = _disposition("Boreas_1", "ECGR_api", USE_STATUS_QC_ONLY_EXCLUDED,
                     EXCLUSION_REASON_BOREAS_ECGR)
    p = _proxy_for(_full_frame(well_key="Boreas_1"))
    with pytest.raises(PetrophysicsInputError, match="lithology-dependent"):
        compute_sonic_nct_candidate_eligibility(frame, d, p, 0.5, _config())


def test_nct_candidate_rejects_proxy_from_another_well():
    frame = _full_frame(well_key="A_1")
    p = _proxy_for(_full_frame(well_key="B_1"))
    with pytest.raises(PetrophysicsInputError, match="never transferred between wells"):
        compute_sonic_nct_candidate_eligibility(frame, _disposition("A_1"), p, 0.5, _config())


def test_nct_candidate_rejects_non_finite_threshold():
    frame = _full_frame()
    p = _proxy_for(frame)
    with pytest.raises(PetrophysicsInputError, match="must be finite"):
        compute_sonic_nct_candidate_eligibility(frame, _disposition(), p, np.nan, _config())


def test_nct_candidate_notes_disclaim_normal_compaction():
    frame = _full_frame(gr=np.linspace(10.0, 110.0, 10))
    m = compute_sonic_nct_candidate_eligibility(
        frame, _disposition(), _proxy_for(frame), 0.5, _config()
    )
    low = m.notes.lower()
    assert "candidate data only" in low
    assert "no nct fitted" in low
    assert "not proof" in low


def test_nct_candidate_requires_finite_vp():
    vp = np.full(10, 4000.0)
    vp[1] = np.nan
    frame = _full_frame(vp=vp, gr=np.full(10, 100.0))
    m = compute_sonic_nct_candidate_eligibility(
        frame, _disposition(), _proxy_for(frame), 0.5, _config()
    )
    assert not m.mask[1]


# ---------------------------------------------------------------------------
# Contiguous interval registers
# ---------------------------------------------------------------------------

def test_intervals_report_md_tvd_and_tvdss():
    frame = _full_frame(n=30)
    m = compute_density_eligibility(frame, _config())
    ivs = build_eligibility_intervals(frame, m, _config())
    assert len(ivs) == 1
    iv = ivs[0]
    assert iv.md_start_m is not None and iv.md_end_m is not None
    assert iv.tvd_start_m is not None and iv.tvdss_start_m is not None
    assert iv.gross_thickness_md_m > 0 and iv.gross_thickness_tvdss_m > 0
    # With no bridging, gross and net coincide.
    assert iv.net_thickness_tvdss_m == pytest.approx(iv.gross_thickness_tvdss_m)
    assert iv.contiguity_policy == "configured_bridging"
    assert iv.meets_configured_minimums is True
    assert iv.n_samples == 30
    assert iv.n_eligible_samples == 30
    assert iv.n_bridged_samples == 0
    assert iv.depth_basis_used == frame.depth_basis_used


def test_intervals_split_on_large_gap():
    rhob = np.full(30, 2400.0)
    rhob[10:20] = np.nan
    frame = _full_frame(n=30, rhob=rhob)
    m = compute_density_eligibility(frame, _config())
    ivs = build_eligibility_intervals(frame, m, _config())
    assert len(ivs) == 2
    assert ivs[0].end_index == 9
    assert ivs[1].start_index == 20


def test_intervals_bridge_small_gap_and_disclose_it():
    """A bridged gap is always disclosed via n_bridged_samples - eligible
    sample count and block span are reported separately."""
    rhob = np.full(30, 2400.0)
    rhob[10] = np.nan  # single-sample gap, small physical span
    frame = _full_frame(n=30, rhob=rhob)
    cfg = _config(contiguity={"max_gap_samples": 2, "max_gap_depth_m": 100.0,
                              "min_block_samples": 2, "min_block_thickness_m": 1.0})
    ivs = build_eligibility_intervals(frame, compute_density_eligibility(frame, cfg), cfg)
    assert len(ivs) == 1
    assert ivs[0].n_samples == 30
    assert ivs[0].n_eligible_samples == 29
    assert ivs[0].n_bridged_samples == 1
    assert ivs[0].n_bridged_gaps == 1
    assert ivs[0].n_eligible_subruns == 2


def test_intervals_record_limiting_reason_for_short_blocks():
    rhob = np.full(30, np.nan)
    rhob[0:3] = 2400.0  # a 3-sample block, under the 20-sample minimum
    frame = _full_frame(n=30, rhob=rhob)
    cfg = _config(contiguity={"max_gap_samples": 0, "max_gap_depth_m": 0.0,
                              "min_block_samples": 20, "min_block_thickness_m": 5.0})
    ivs = build_eligibility_intervals(frame, compute_density_eligibility(frame, cfg), cfg)
    assert len(ivs) == 1  # disclosed, not silently dropped
    assert "below_min_block_samples" in ivs[0].limiting_reason


def test_intervals_empty_when_nothing_eligible():
    frame = _full_frame(n=10, rhob=np.full(10, np.nan))
    m = compute_density_eligibility(frame, _config())
    assert build_eligibility_intervals(frame, m, _config()) == []


def test_intervals_thickness_none_when_depth_unmapped_at_edge():
    """Physical thickness is None (unknown) when an endpoint has no mapped
    depth - never 0, and never silently replaced by the MD span."""
    md = np.array([50.0, 100.0, 200.0, 300.0, 900.0])
    frame = _full_frame(n=5, md=md)
    m = compute_density_eligibility(frame, _config())
    ivs = build_eligibility_intervals(frame, m, _config())
    assert all(iv.end_index < 4 for iv in ivs)  # unmapped sample never inside a block


# ---------------------------------------------------------------------------
# Export layer: determinism, sanitization, JSON-serializability
# ---------------------------------------------------------------------------

def _export_bundle():
    frames = {}
    stats = {}
    conf = {}
    rationale = {}
    scen = {}
    proxies = {}
    masks = []
    for wk in ("Z_1", "A_1"):
        fr = _full_frame(n=20, gr=np.linspace(10.0, 110.0, 20), well_key=wk)
        frames[wk] = fr
        d = _disposition(wk)
        stats[wk] = compute_gr_family_qc_stats(fr, d)
        conf[wk] = "GR_PROXY_INTERMEDIATE"
        rationale[wk] = "synthetic"
        s = _scenario(well_key=wk)
        scen[wk] = [s]
        p = compute_gr_proxy(fr, d, s, _config())
        proxies[wk] = [p]
        masks.append(compute_density_eligibility(fr, _config()))
        masks.append(compute_dynamic_elastic_eligibility(fr, _config()))
        masks.append(compute_sonic_nct_candidate_eligibility(fr, d, p, 0.5, _config()))
    disp = {wk: _disposition(wk) for wk in frames}
    return frames, stats, conf, rationale, scen, proxies, masks, disp


def test_export_rows_are_deterministically_ordered():
    frames, stats, conf, rationale, scen, proxies, masks, disp = _export_bundle()
    qc = build_gr_family_qc_rows(stats, disp, conf)
    assert [r["well_key"] for r in qc] == ["A_1", "Z_1"]
    el = build_method_eligibility_rows(masks, frames, disp)
    keys = [(r["well_key"], r["mask_name"], r["scenario_name"], r["proxy_threshold"]) for r in el]
    assert keys == sorted(keys, key=lambda k: (k[0], k[1], k[2], -1e18 if k[3] is None else k[3]))


def test_export_rows_contain_no_absolute_paths():
    """Every path-shaped field is reduced to a basename, so a private build
    directory can never leak into a deliverable."""
    frames, stats, conf, rationale, scen, proxies, masks, disp = _export_bundle()
    blob = json.dumps(
        build_gr_family_qc_rows(stats, disp, conf)
        + build_gr_endpoint_scenario_rows(scen)
        + build_gr_proxy_sensitivity_rows(proxies, disp)
        + build_method_eligibility_rows(masks, frames, disp)
    )
    assert "/private/build" not in blob
    assert "/home/" not in blob and "/root/" not in blob and "/content/" not in blob


def test_failure_message_is_sanitized_against_both_candidate_paths():
    """A well-frame failure may originate from either file, so BOTH paths
    are sanitized - never only one."""
    f = WellFrameAssemblyFailure(
        well_key="X_1", failure_origin="depth_mapping", error_type="depth_mapping_failure",
        message=("X_1: failed using /home/user/secret/X_1_logs.las against "
                 "/home/user/secret/X_1_dev.txt"),
        las_path="/home/user/secret/X_1_logs.las",
        survey_path="/home/user/secret/X_1_dev.txt",
    )
    rows = build_petrophysics_issue_rows([], {"X_1": f})
    assert len(rows) == 1
    assert "/home/user/secret" not in rows[0]["message"]
    assert "X_1_logs.las" in rows[0]["message"]
    assert "X_1_dev.txt" in rows[0]["message"]
    assert "/home/user/secret" not in rows[0]["context"]


def test_issue_rows_carry_severity_and_code():
    rows = build_petrophysics_issue_rows(
        [PetrophysicsIssue("WARNING", "SOME_CODE", "a message", "ctx")], {}
    )
    assert rows[0]["severity"] == "WARNING"
    assert rows[0]["code"] == "SOME_CODE"


def test_manifest_is_json_serializable_and_has_no_numpy_scalars():
    frames, stats, conf, rationale, scen, proxies, masks, disp = _export_bundle()
    man = build_petrophysics_manifest(
        frames, disp, stats, conf, rationale, scen, masks, {}, [],
        config_filename="petrophysics_eligibility.yml", config_schema_version="6.0",
        nct_candidate_thresholds=[0.5, 0.6, 0.7],
    )
    text = json.dumps(man)  # raises TypeError on any NumPy scalar
    assert json.loads(text)["increment"] == 6
    assert "/private/build" not in text


def test_manifest_declares_no_named_lithology():
    frames, stats, conf, rationale, scen, proxies, masks, disp = _export_bundle()
    man = build_petrophysics_manifest(
        frames, disp, stats, conf, rationale, scen, masks, {}, [],
        config_filename="c.yml", config_schema_version="6.0",
        nct_candidate_thresholds=[0.5],
    )
    # Increment 6.1.5: this bundle's prose is SYNTHETIC and therefore
    # unauthorized, so the derived flag is True here. That is the contract
    # working - the assertions below are about the manifest's other declared
    # facts, which are unaffected. The clean/authorized path is covered by
    # test_unchanged_real_packaged_content_keeps_the_gate_passing.
    assert man["named_lithology_assigned"] is True
    assert all(v["terms"] == [] for v in man["lithology_validation"]["violations"]), (
        "synthetic prose contains no rock word; it fails for lack of authorization"
    )
    assert man["nonlinear_vsh_transforms_implemented"] is False
    assert man["total_samples_extrapolated"] == 0
    assert man["calibration_data_available"]["pressure_rft_mdt_dst"] is False
    assert man["calibration_data_available"]["stress_fit_lot_xlot_dfit"] is False
    for method in ("normal_compaction_trend_fitting", "eaton_sonic_pore_pressure",
                   "dynamic_elastic_property_calculation", "wellbore_stability_analysis",
                   "named_lithology_interpretation"):
        assert method in man["methods_not_implemented"]


def test_no_export_row_contains_named_lithology_vocabulary():
    """Every generated classification string in every export is checked
    against the prohibited rock-name vocabulary."""
    frames, stats, conf, rationale, scen, proxies, masks, disp = _export_bundle()
    rows = (
        build_gr_family_qc_rows(stats, disp, conf)
        + build_gr_endpoint_scenario_rows(scen)
        + build_gr_proxy_sensitivity_rows(proxies, disp)
        + build_method_eligibility_rows(masks, frames, disp)
    )
    for r in rows:
        for field in ("gr_proxy_confidence_class", "use_status", "evidence_class",
                      "mask_name", "scenario_name", "gr_family_canonical_name"):
            if r.get(field):
                assert_no_lithology_vocabulary(str(r[field]), f"{field}")


def test_export_never_contains_per_sample_arrays():
    """No exported row or manifest value is an array-like of sample values -
    packaging one would effectively reproduce the private source log."""
    frames, stats, conf, rationale, scen, proxies, masks, disp = _export_bundle()
    rows = (
        build_gr_family_qc_rows(stats, disp, conf)
        + build_gr_proxy_sensitivity_rows(proxies, disp)
        + build_method_eligibility_rows(masks, frames, disp)
        + build_eligibility_interval_rows(
            build_eligibility_intervals(frames["A_1"], masks[0], _config())
        )
    )
    for r in rows:
        for k, v in r.items():
            assert not isinstance(v, (list, tuple, np.ndarray)), f"{k} exports an array"


def test_interval_rows_are_json_safe_and_sorted():
    frame = _full_frame(n=30)
    ivs = build_eligibility_intervals(frame, compute_density_eligibility(frame, _config()), _config())
    rows = build_eligibility_interval_rows(ivs)
    json.dumps(rows)
    assert rows[0]["unit"] == "metres"
    assert "not proof of normal compaction" in rows[0]["limitations"].lower() or \
           "not evidence" in rows[0]["limitations"].lower()


def test_dynamic_elastic_limiting_criterion_is_not_confounded_by_vs_sparsity():
    """The Vp/Vs criteria are only meaningful where both velocities exist, so
    their raw pass counts are structurally bounded by VS availability. They
    must NOT be allowed to win the limiting-criterion comparison and report a
    DATA-COVERAGE problem as a PHYSICS problem."""
    vs = np.full(20, 2200.0)
    vs[:15] = np.nan          # VS is by far the scarcest curve
    vp = np.full(20, 4000.0)  # every surviving ratio is comfortably physical
    m = compute_dynamic_elastic_eligibility(_full_frame(n=20, vp=vp, vs=vs), _config())
    assert m.limiting_criterion == "vs_finite_positive_in_bounds"
    assert "vp_vs_ratio_in_poisson_domain" not in m.criteria_counts
    assert m.n_eligible == 5


def test_dynamic_elastic_reports_each_excluded_regime_as_its_own_count():
    """Each exclusion regime is reported separately, under a name that says
    what it actually is."""
    vs = np.full(10, 2200.0)
    vp = np.full(10, 4000.0)
    vp[3] = 2200.0 * 1.20  # sqrt(4/3) < r < sqrt(2): K > 0, nu < 0
    vp[7] = 2000.0         # VP below VS entirely
    m = compute_dynamic_elastic_eligibility(_full_frame(vp=vp, vs=vs), _config())
    d = m.diagnostic_counts
    assert d["n_vp_and_vs_both_valid"] == 10
    assert d["n_vp_not_greater_than_vs"] == 1
    assert d["n_ratio_positive_bulk_but_negative_poisson"] == 1
    # The VP<VS sample has r < 1, so it is ALSO a non-positive-K ratio; the
    # regime counts describe the RATIO, the vp_gt_vs count describes the
    # ordering. Both are reported; neither is merged into the other.
    assert d["n_ratio_nonpositive_bulk_modulus"] == 1
    assert m.n_eligible == 8


def test_diagnostic_counts_are_exported_and_json_safe():
    frames, stats, conf, rationale, scen, proxies, masks, disp = _export_bundle()
    rows = build_method_eligibility_rows(masks, frames, disp)
    elastic = [r for r in rows if r["mask_name"] == MASK_DYNAMIC_ELASTIC]
    assert elastic and all("diagnostic_counts" in r for r in elastic)
    assert all("n_vp_and_vs_both_valid" in r["diagnostic_counts"] for r in elastic)
    json.dumps(rows)


# ---------------------------------------------------------------------------
# Increment 6.1 (Finding 4): gross vs net vs strict-no-gap thickness
# ---------------------------------------------------------------------------

def _bridging_frame():
    """30 samples with a single-sample ineligible gap at index 10, small
    enough in both sample count and depth span to be bridged."""
    rhob = np.full(30, 2400.0)
    rhob[10] = np.nan
    return _full_frame(n=30, rhob=rhob)


def _bridging_config():
    return _config(contiguity={"max_gap_samples": 2, "max_gap_depth_m": 100.0,
                               "min_block_samples": 2, "min_block_thickness_m": 1.0})


def test_gross_exceeds_net_by_exactly_the_bridged_gap_span():
    """The gross endpoint span minus the net sum of strictly-contiguous
    sub-run spans must equal the bridged gap's own depth span."""
    frame, cfg = _bridging_frame(), _bridging_config()
    ivs = build_eligibility_intervals(frame, compute_density_eligibility(frame, cfg), cfg)
    assert len(ivs) == 1
    iv = ivs[0]
    assert iv.n_bridged_samples == 1
    assert iv.n_bridged_gaps == 1
    assert iv.n_eligible_subruns == 2
    y = np.asarray(frame.TVDSS_m, dtype=float)
    # Identity: with sub-runs [s, p-1] and [p+g, e] around a gap of length g
    # starting at p, gross - net = y[p+g] - y[p-1] - the span from the last
    # eligible sample before the gap to the first eligible sample after it.
    gap_span = abs(float(y[11]) - float(y[9]))
    assert iv.gross_thickness_tvdss_m > iv.net_thickness_tvdss_m
    assert iv.gross_thickness_tvdss_m - iv.net_thickness_tvdss_m == pytest.approx(
        gap_span, abs=1e-9
    )


def test_strict_policy_produces_no_bridged_samples_and_gross_equals_net():
    frame, cfg = _bridging_frame(), _bridging_config()
    m = compute_density_eligibility(frame, cfg)
    strict = build_eligibility_intervals(frame, m, cfg, contiguity_policy="strict_no_gap")
    assert len(strict) == 2, "the gap must split the block under a strict policy"
    for iv in strict:
        assert iv.contiguity_policy == "strict_no_gap"
        assert iv.n_bridged_samples == 0
        assert iv.n_bridged_gaps == 0
        assert iv.n_eligible_subruns == 1
        assert iv.net_thickness_tvdss_m == pytest.approx(iv.gross_thickness_tvdss_m)


def test_strict_total_never_exceeds_configured_gross_total():
    """A strict decomposition can only be shorter than, or equal to, the
    bridged one - it removes span, never adds it."""
    frame, cfg = _bridging_frame(), _bridging_config()
    m = compute_density_eligibility(frame, cfg)
    conf = build_eligibility_intervals(frame, m, cfg)
    strict = build_eligibility_intervals(frame, m, cfg, contiguity_policy="strict_no_gap")
    g = sum(iv.gross_thickness_tvdss_m for iv in conf)
    s = sum(iv.gross_thickness_tvdss_m for iv in strict)
    assert s <= g


def test_unknown_contiguity_policy_rejected():
    frame, cfg = _bridging_frame(), _bridging_config()
    with pytest.raises(PetrophysicsInputError, match="Unknown contiguity_policy"):
        build_eligibility_intervals(frame, compute_density_eligibility(frame, cfg), cfg,
                                    contiguity_policy="whatever")


def test_sensitivity_rows_state_their_population_and_bridging():
    """Every sensitivity case must report how many blocks it covers, how
    many qualify, and how much bridging the gross figure absorbed."""
    from p2mem.io.petrophysics_inventory import build_thickness_sensitivity_rows
    frame, cfg = _bridging_frame(), _bridging_config()
    ivs = build_eligibility_intervals(frame, compute_density_eligibility(frame, cfg), cfg)
    rows = build_thickness_sensitivity_rows(ivs)
    assert len(rows) == 1
    r = rows[0]
    assert r["n_blocks_all"] == 1
    assert r["n_blocks_qualifying"] == 1
    assert r["n_bridged_samples_in_qualifying_blocks"] == 1
    assert r["n_interrupted_qualifying_blocks"] == 1
    assert r["gross_qualifying_thickness_tvdss_m"] > r["net_qualifying_thickness_tvdss_m"]
    assert "GROSS" in r["population_statement"] and "NET" in r["population_statement"]
    assert r["contiguity_policy"] == "configured_bridging"


def test_sensitivity_rows_separate_qualifying_from_rejected_blocks():
    """The qualifying total must exclude sub-threshold blocks, and the
    rejected count must be reported rather than hidden."""
    from p2mem.io.petrophysics_inventory import build_thickness_sensitivity_rows
    rhob = np.full(40, np.nan)
    rhob[0:25] = 2400.0   # a qualifying block
    rhob[35:38] = 2400.0  # a 3-sample block, below the 20-sample minimum
    frame = _full_frame(n=40, rhob=rhob)
    cfg = _config(contiguity={"max_gap_samples": 0, "max_gap_depth_m": 0.0,
                              "min_block_samples": 20, "min_block_thickness_m": 5.0})
    ivs = build_eligibility_intervals(frame, compute_density_eligibility(frame, cfg), cfg)
    rows = build_thickness_sensitivity_rows(ivs)
    r = rows[0]
    assert r["n_blocks_all"] == 2
    assert r["n_blocks_qualifying"] == 1
    assert r["n_blocks_rejected_below_minimums"] == 1
    assert r["gross_qualifying_thickness_tvdss_m"] < r["gross_all_block_thickness_tvdss_m"]


def test_interval_rows_never_export_an_unqualified_thickness_field():
    """No exported column may be called simply 'thickness_*' - the whole
    point of Finding 4 is that the qualifier is mandatory."""
    frame, cfg = _bridging_frame(), _bridging_config()
    ivs = build_eligibility_intervals(frame, compute_density_eligibility(frame, cfg), cfg)
    rows = build_eligibility_interval_rows(ivs)
    for r in rows:
        for key in r:
            if "thickness" in key:
                assert key.startswith("gross_") or key.startswith("net_"), key


# ---------------------------------------------------------------------------
# Increment 6.1 (Finding 3): the completion gate is DERIVED, not hardcoded
# ---------------------------------------------------------------------------

def _registered_note():
    """A REGISTERED interpretive statement. Increment 6.1.5: synthetic prose is
    no longer authorized, so a helper that means to build a CLEAN manifest must
    use content the project has actually registered."""
    from p2mem.wellframe_models import REGISTERED_STATEMENTS, SCOPE_INTERPRETIVE
    return sorted(s.text for s in REGISTERED_STATEMENTS.values()
                  if s.scope == SCOPE_INTERPRETIVE)[0]


def _registered_rationale():
    """The registered rationale TEMPLATE rendered with typed decimal values."""
    from p2mem.wellframe_models import REGISTERED_TEMPLATES
    tpl = REGISTERED_TEMPLATES["gr_proxy_confidence_rationale"]
    return tpl.render({"valid_fraction": "0.9000",
                       "dynamic_range_p05_p95": "100.000",
                       "proxy_median_spread": "0.1000"})


def _output_registered_mask(mask):
    """Set the mask's persisted prose to the statements the OUTPUT policy
    declares for method_eligibility_summary.csv, so a builder-produced payload
    carries the same controlled values the real artifact does."""
    from p2mem.io.output_policy import OUTPUT_STATEMENTS
    def _pick(prefix):
        return sorted(st.text for st in OUTPUT_STATEMENTS.values()
                      if st.statement_id.startswith(prefix))
    purposes = _pick("method_eligibility_summary_purpose")
    idx = {"eligible_density_for_sv": 0, "eligible_dynamic_elastic": 1,
           "eligible_sonic_nct_candidate": 2}.get(mask.mask_name, 0)
    object.__setattr__(mask, "purpose", purposes[min(idx, len(purposes) - 1)])
    object.__setattr__(mask, "notes", _registered_note())
    return mask


def _registered_mask(mask):
    """Increment 6.1.5: a mask's notes and purpose are persisted interpretive
    fields, so the synthetic config's "synthetic purpose" is - correctly -
    unauthorized. A helper that means to build a CLEAN manifest substitutes the
    registered mask prose the real project actually persists."""
    from p2mem.wellframe_models import REGISTERED_STATEMENTS, SCOPE_INTERPRETIVE
    registered = sorted(s.text for s in REGISTERED_STATEMENTS.values()
                        if s.scope == SCOPE_INTERPRETIVE)
    object.__setattr__(mask, "notes", registered[0])
    object.__setattr__(mask, "purpose", registered[1])
    return mask


def _clean_disposition():
    return GrFamilyDisposition(
        well_key="W_1", source_las_filename="W_1.las", gr_family_canonical_name="GR_api",
        gr_family_source_curve_name="GR", use_status="screening_proxy_allowed",
        exclusion_reason=None, evidence_class="measured", has_approved_formation_tops=True,
        notes=_registered_note(),
    )


def _manifest_with(disposition=None, confidence="GR_PROXY_INTERMEDIATE"):
    """Build a real manifest from real builders, so the gate under test is the
    one the deliverable actually uses."""
    d = disposition or _clean_disposition()
    frame = _full_frame(n=20, gr=np.linspace(10.0, 110.0, 20), well_key="W_1")
    stats = compute_gr_family_qc_stats(frame, d)
    mask = _registered_mask(compute_density_eligibility(frame, _config()))
    return build_petrophysics_manifest(
        {"W_1": frame}, {"W_1": d}, {"W_1": stats}, {"W_1": confidence},
        {"W_1": _registered_rationale()}, {"W_1": []}, [mask], {}, [],
        config_filename="c.yml", config_schema_version="6.0",
        nct_candidate_thresholds=[0.5],
    )


def _registered_endpoint_description():
    """Increment 6.1.6: an endpoint description is a CONTROLLED emitted field.
    A synthetic one is correctly refused by the builder, so a test that means to
    exercise the happy path uses a registered description."""
    from p2mem.io.output_policy import OUTPUT_STATEMENTS
    return sorted(st.text for st in OUTPUT_STATEMENTS.values()
                  if st.statement_id.startswith("gr_endpoint_scenarios_description"))[0]


def _n_viol(manifest):
    """Increment 6.1.6: violations are the union of the scope-object pass and
    the emission-boundary pass, so tests count the list itself."""
    return len(manifest["lithology_validation"]["violations"])


def _gate_passes(manifest):
    """The completion-gate condition as the notebook evaluates it: DERIVED
    from the validation result, never from a constant."""
    lv = manifest["lithology_validation"]
    return (manifest["named_lithology_assigned"] is False) and (len(lv["violations"]) == 0)


def test_manifest_lithology_flag_is_derived_from_a_real_validation_pass():
    man = _manifest_with()
    lv = man["lithology_validation"]
    assert lv["scope_object_fields_checked"] > 0, "the validation must actually inspect content"
    assert _n_viol(man) == 0
    assert man["named_lithology_assigned"] is False
    assert _gate_passes(man)
    assert "DERIVED" in lv["derivation"] or "derived" in lv["derivation"]


def test_injected_prohibited_term_in_a_per_well_note_fails_gate():
    """Injecting a prohibited interpretation must make the validation, the
    manifest flag, AND the completion gate all fail together."""
    dirty = GrFamilyDisposition(
        well_key="W_1", source_las_filename="W_1.las", gr_family_canonical_name="GR_api",
        gr_family_source_curve_name="GR", use_status="screening_proxy_allowed",
        exclusion_reason=None, evidence_class="measured", has_approved_formation_tops=True,
        notes="Distribution is consistent with a clastic-dominated section.",
    )
    man = _manifest_with(disposition=dirty)
    assert man["named_lithology_assigned"] is True
    assert _n_viol(man) == 1
    assert man["lithology_validation"]["violations"][0]["terms"] == ["clastic"]
    assert not _gate_passes(man)


def test_injected_prohibited_term_in_a_persisted_classification_fails_gate():
    man = _manifest_with(confidence="SHALE_PROXY_HIGH")
    assert man["named_lithology_assigned"] is True
    assert not _gate_passes(man)
    ctxs = [v["context"] for v in man["lithology_validation"]["violations"]]
    assert any("gr_proxy_confidence_class" in c for c in ctxs)


def test_gate_cannot_be_satisfied_by_a_constant():
    """A hardcoded `False` would keep the gate passing under injection; the
    derived flag must move with the evidence."""
    clean = _manifest_with()
    dirty = _manifest_with(confidence="LIMESTONE_PROXY_HIGH")
    assert clean["named_lithology_assigned"] != dirty["named_lithology_assigned"]
    assert _gate_passes(clean) and not _gate_passes(dirty)


def test_validation_scope_covers_labels_notes_and_manifest_statement():
    man = _manifest_with()
    # The scope is rebuilt here from the same builder the manifest uses.
    from p2mem.io.petrophysics_inventory import build_lithology_validation_scope
    scope = build_lithology_validation_scope(
        {"W_1": _clean_disposition()}, {"W_1": "GR_PROXY_HIGH"},
        {"W_1": _registered_rationale()},
        [compute_density_eligibility(_full_frame(), _config())],
    )
    contexts = {e[0] for e in scope}
    assert any("use_status" in c for c in contexts)
    assert any("config_notes" in c for c in contexts)
    assert any("gr_proxy_confidence_class" in c for c in contexts)
    assert any("mask_name" in c for c in contexts)
    # The manifest additionally folds in its own explanatory statement.
    assert man["lithology_validation"]["scope_object_fields_checked"] > len(scope) - 1


# ---------------------------------------------------------------------------
# Increment 6.1 (Finding 4): Figure 4 totals must match their stated population
# ---------------------------------------------------------------------------

def test_figure4_totals_match_the_qualifying_population_they_state():
    """The number a Figure-4 annotation prints must equal the sum over the
    blocks it says it covers - the qualifying ones - and must exclude the
    rejected sub-threshold blocks drawn separately."""
    from p2mem.io.petrophysics_inventory import build_thickness_sensitivity_rows
    rhob = np.full(40, np.nan)
    rhob[0:25] = 2400.0   # qualifying
    rhob[35:38] = 2400.0  # sub-threshold
    frame = _full_frame(n=40, rhob=rhob)
    cfg = _config(contiguity={"max_gap_samples": 0, "max_gap_depth_m": 0.0,
                              "min_block_samples": 20, "min_block_thickness_m": 5.0})
    ivs = build_eligibility_intervals(frame, compute_density_eligibility(frame, cfg), cfg)
    qual = [iv for iv in ivs if iv.meets_configured_minimums]
    rej = [iv for iv in ivs if not iv.meets_configured_minimums]
    assert len(qual) == 1 and len(rej) == 1

    # What the figure annotates:
    fig_gross = sum(float(iv.gross_thickness_tvdss_m or 0.0) for iv in qual)
    fig_net = sum(float(iv.net_thickness_tvdss_m or 0.0) for iv in qual)
    # What the exported sensitivity table reports for the same population:
    row = build_thickness_sensitivity_rows(ivs)[0]
    assert row["gross_qualifying_thickness_tvdss_m"] == pytest.approx(fig_gross)
    assert row["net_qualifying_thickness_tvdss_m"] == pytest.approx(fig_net)
    assert row["n_blocks_qualifying"] == len(qual)
    assert row["n_blocks_rejected_below_minimums"] == len(rej)
    # And the all-block figure is strictly larger, so the two populations can
    # never be silently interchanged.
    assert row["gross_all_block_thickness_tvdss_m"] > row["gross_qualifying_thickness_tvdss_m"]


# ---------------------------------------------------------------------------
# Increment 6.1.1 (Finding 2): the ACTIVE module documentation must not
# reintroduce the exclusive-boundary wording
# ---------------------------------------------------------------------------

def test_active_module_docstring_uses_corrected_vp_vs_language():
    """The Increment 6.1 implementation fix left the module's own top-level
    docstring saying "inside the Poisson domain (Vp/Vs > sqrt(2), i.e. Poisson
    ratio > 0)". Documentation that contradicts the code it documents is a real
    defect: a reader trusts the docstring. This test pins the corrected
    wording so the exclusive boundary cannot return."""
    import p2mem.method_eligibility as me
    raw = me.__doc__ or ""
    assert raw.strip(), "the module must retain a top-level docstring"
    # Compare on whitespace-normalized text: these assertions are about
    # CONTENT, and a docstring's line wrapping must not decide the outcome.
    doc = " ".join(raw.split())

    forbidden = [
        "inside the Poisson domain",
        "in the Poisson domain",
        "Vp/Vs > sqrt(2)",
        "ratio > sqrt(2)",
        "Poisson ratio > 0",
        "Poisson's ratio is non-negative only when",
    ]
    for phrase in forbidden:
        assert phrase not in doc, (
            f"active module docstring reintroduces stale exclusive-boundary wording: {phrase!r}"
        )

    required = [
        "NON-NEGATIVE-POISSON-RATIO APPLICABILITY SCREEN",
        "Vp/Vs >= sqrt(2)",
    ]
    for phrase in required:
        assert phrase in doc, f"active module docstring is missing {phrase!r}"
    low = doc.lower()
    assert "inclusive" in low
    assert "not a physical-possibility test" in low
    assert "not a boundary of the mathematical poisson domain" in low


def test_active_function_docstring_matches_the_implementation():
    """The mask function's own docstring must agree with the inclusive bound
    it actually implements."""
    from p2mem.method_eligibility import compute_dynamic_elastic_eligibility as f
    doc = " ".join((f.__doc__ or "").split())
    assert "sqrt(2)" in doc and "INCLUSIVE" in doc.upper()
    assert "inside the Poisson domain" not in doc
    assert "nu = 0" in doc or "nu = 0 EXACTLY" in doc


def test_no_active_source_file_reintroduces_the_exclusive_bound():
    """Sweep the packaged, ACTIVE p2mem sources. Historical/superseded records
    and negative assertions are out of scope by construction (this scans
    modules only, not manifests or tests)."""
    import pathlib
    import p2mem
    root = pathlib.Path(p2mem.__file__).resolve().parent
    forbidden = ["inside the Poisson domain", "Vp/Vs > sqrt(2)", "Poisson ratio > 0"]
    offenders = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            if phrase in text:
                offenders.append(f"{path.name}: {phrase!r}")
    assert not offenders, f"stale exclusive-boundary wording in active source: {offenders}"


# ---------------------------------------------------------------------------
# Increment 6.1.1 (Finding 1): the allowlist cannot hide a geological assertion
# from the DERIVED completion gate
# ---------------------------------------------------------------------------

def test_injected_shale_gas_note_fails_the_derived_gate():
    """Audited bypass case 1, injected into real manifest-building content:
    ("Poseidon_2.config_notes", "This interval contains shale gas.",
    SCOPE_INTERPRETIVE). Before Increment 6.1.1 this produced zero violations
    and the gate passed."""
    dirty = GrFamilyDisposition(
        well_key="W_1", source_las_filename="W_1.las", gr_family_canonical_name="GR_api",
        gr_family_source_curve_name="GR", use_status="screening_proxy_allowed",
        exclusion_reason=None, evidence_class="measured", has_approved_formation_tops=True,
        notes="This interval contains shale gas.",
    )
    man = _manifest_with(disposition=dirty)
    assert man["named_lithology_assigned"] is True
    assert _n_viol(man) > 0
    assert "shale" in man["lithology_validation"]["violations"][0]["terms"]
    assert not _gate_passes(man)


def test_injected_shale_gas_manifest_statement_fails_the_derived_gate():
    """Audited bypass case 2, injected into the manifest's own explanatory
    scope: ("manifest.statement", "Poseidon 2 contains shale gas.",
    SCOPE_EXPLANATORY)."""
    from p2mem.io.petrophysics_inventory import build_lithology_validation_scope
    from p2mem.wellframe_models import (
        SCOPE_EXPLANATORY, validate_no_prohibited_interpretation)
    scope = build_lithology_validation_scope(
        {"W_1": _disposition("W_1")}, {"W_1": "GR_PROXY_INTERMEDIATE"}, {"W_1": "r"},
        [compute_density_eligibility(_full_frame(), _config())],
        extra_entries=[
            ("manifest.statement", "Poseidon 2 contains shale gas.", SCOPE_EXPLANATORY),
        ],
    )
    violations = validate_no_prohibited_interpretation(scope)
    # The manifest derives its flag and its gate from exactly this call.
    named_lithology_assigned = bool(violations)
    assert named_lithology_assigned is True
    assert len(violations) > 0
    assert any(v["context"] == "manifest.statement" for v in violations)
    assert not _gate_passes({
        "named_lithology_assigned": named_lithology_assigned,
        "lithology_validation": {"violations": list(violations)},
    })


def test_clean_manifest_still_passes_after_the_allowlist_correction():
    """The correction must tighten the validator without breaking the real,
    legitimate content the manifest already carries."""
    man = _manifest_with()
    assert _n_viol(man) == 0
    assert man["named_lithology_assigned"] is False
    assert _gate_passes(man)


# ---------------------------------------------------------------------------
# Increment 6.1.1 (Finding 3): explicit, unambiguous interruption counts
# ---------------------------------------------------------------------------

def test_no_gap_block_reports_zero_gaps_and_one_subrun():
    """Identity: no gap -> 0 bridged samples, 0 bridged gaps, 1 eligible
    sub-run."""
    frame, cfg = _full_frame(n=30), _bridging_config()
    ivs = build_eligibility_intervals(frame, compute_density_eligibility(frame, cfg), cfg)
    assert len(ivs) == 1
    iv = ivs[0]
    assert iv.n_bridged_samples == 0
    assert iv.n_bridged_gaps == 0
    assert iv.n_eligible_subruns == 1


def test_two_separate_bridged_gaps_in_one_configured_block():
    """Identity: two distinct bridged gaps -> n_bridged_gaps == 2 and
    n_eligible_subruns == 3, inside a SINGLE configured block."""
    rhob = np.full(30, 2400.0)
    rhob[10] = np.nan          # gap 1: one sample
    rhob[20:22] = np.nan       # gap 2: two samples
    frame = _full_frame(n=30, rhob=rhob)
    cfg = _bridging_config()
    ivs = build_eligibility_intervals(frame, compute_density_eligibility(frame, cfg), cfg)
    assert len(ivs) == 1, "both gaps are within tolerance, so one gross block"
    iv = ivs[0]
    assert iv.n_bridged_samples == 3      # 1 + 2 samples absorbed
    assert iv.n_bridged_gaps == 2         # two DISTINCT False runs
    assert iv.n_eligible_subruns == 3     # 0..9, 11..19, 22..29
    assert iv.n_eligible_samples == 27
    assert iv.n_samples == 30


def test_bridged_gaps_and_subruns_identity_holds_generally():
    """Whenever n_eligible_subruns > 0, n_bridged_gaps == n_eligible_subruns - 1."""
    for gap_positions in ([10], [10, 20], [5, 12, 19, 26]):
        rhob = np.full(32, 2400.0)
        for g in gap_positions:
            rhob[g] = np.nan
        frame = _full_frame(n=32, rhob=rhob)
        cfg = _bridging_config()
        ivs = build_eligibility_intervals(frame, compute_density_eligibility(frame, cfg), cfg)
        assert len(ivs) == 1
        iv = ivs[0]
        assert iv.n_eligible_subruns > 0
        assert iv.n_bridged_gaps == iv.n_eligible_subruns - 1
        assert iv.n_bridged_gaps == len(gap_positions)
        assert iv.n_bridged_samples == len(gap_positions)


def test_one_gap_may_absorb_several_samples_so_gaps_and_samples_differ():
    """Samples and gaps are different magnitudes: a single gap can absorb
    several samples. Reporting only one of them was the ambiguity."""
    rhob = np.full(30, 2400.0)
    rhob[10:12] = np.nan  # ONE gap, TWO samples
    frame = _full_frame(n=30, rhob=rhob)
    cfg = _bridging_config()
    iv = build_eligibility_intervals(frame, compute_density_eligibility(frame, cfg), cfg)[0]
    assert iv.n_bridged_samples == 2
    assert iv.n_bridged_gaps == 1
    assert iv.n_eligible_subruns == 2


def test_inconsistent_interval_record_is_rejected_at_construction():
    """The gap/sub-run relationship is structural; an inconsistent record must
    not be constructible.

    Increment 6.1.2 (Finding 2): all three counts are now supplied, because a
    record that omits one is rejected earlier, by the missing-field rule. The
    mismatch under test here is therefore the ONLY defect in this record."""
    from p2mem.method_eligibility import EligibilityInterval
    with pytest.raises(PetrophysicsInputError, match="inconsistent interval record"):
        EligibilityInterval(well_key="W", mask_name=MASK_DENSITY_FOR_SV,
                            n_bridged_samples=5, n_bridged_gaps=5,
                            n_eligible_subruns=3)


def test_ambiguous_interruption_aliases_are_gone_from_active_exports():
    """No ambiguous alias may survive in an active CSV export."""
    frame, cfg = _bridging_frame(), _bridging_config()
    ivs = build_eligibility_intervals(frame, compute_density_eligibility(frame, cfg), cfg)
    rows = build_eligibility_interval_rows(ivs)
    for r in rows:
        assert "n_interruptions" not in r
        assert "n_interrupted_subruns" not in r
        assert "n_bridged_samples" in r
        assert "n_bridged_gaps" in r
        assert "n_eligible_subruns" in r
    from p2mem.method_eligibility import EligibilityInterval
    assert "n_interruptions" not in EligibilityInterval.__slots__
    assert "n_interrupted_subruns" not in EligibilityInterval.__slots__


def test_sensitivity_row_separates_samples_gaps_and_affected_blocks():
    """thickness_sensitivity_summary must distinguish all three quantities."""
    from p2mem.io.petrophysics_inventory import build_thickness_sensitivity_rows
    rhob = np.full(30, 2400.0)
    rhob[10] = np.nan
    rhob[20:22] = np.nan
    frame = _full_frame(n=30, rhob=rhob)
    cfg = _bridging_config()
    ivs = build_eligibility_intervals(frame, compute_density_eligibility(frame, cfg), cfg)
    r = build_thickness_sensitivity_rows(ivs)[0]
    assert r["n_bridged_samples_in_qualifying_blocks"] == 3
    assert r["n_bridged_gaps_in_qualifying_blocks"] == 2
    assert r["n_interrupted_qualifying_blocks"] == 1   # one block, containing both gaps
    assert "bridged gap(s)" in r["population_statement"]


# ---------------------------------------------------------------------------
# Increment 6.1.2 (Finding 2): the three interruption counts are validated as
# ONE coherent record at construction. Table-driven, both directions.
# ---------------------------------------------------------------------------

def _interval(**counts):
    from p2mem.method_eligibility import EligibilityInterval
    return EligibilityInterval(well_key="W", mask_name=MASK_DENSITY_FOR_SV, **counts)


# (label, kwargs) - every one of these MUST construct.
INTERVAL_VALID_MATRIX = [
    ("no gap: 0 samples / 0 gaps / 1 sub-run",
     dict(n_bridged_samples=0, n_bridged_gaps=0, n_eligible_subruns=1)),
    ("one gap holding two samples: 2 / 1 / 2",
     dict(n_bridged_samples=2, n_bridged_gaps=1, n_eligible_subruns=2)),
    ("two gaps holding three samples: 3 / 2 / 3",
     dict(n_bridged_samples=3, n_bridged_gaps=2, n_eligible_subruns=3)),
    ("one sample per gap is the minimum: 2 / 2 / 3",
     dict(n_bridged_samples=2, n_bridged_gaps=2, n_eligible_subruns=3)),
    ("whole-valued numpy integers are accepted",
     dict(n_bridged_samples=np.int64(2), n_bridged_gaps=np.int64(1),
          n_eligible_subruns=np.int64(2))),
]

# (label, kwargs, expected_message_fragment) - every one MUST raise.
INTERVAL_INVALID_MATRIX = [
    ("negative samples",
     dict(n_bridged_samples=-1, n_bridged_gaps=-1, n_eligible_subruns=0), "negative"),
    ("negative gaps only",
     dict(n_bridged_samples=0, n_bridged_gaps=-1, n_eligible_subruns=1), "negative"),
    ("negative sub-runs",
     dict(n_bridged_samples=0, n_bridged_gaps=0, n_eligible_subruns=-1), "negative"),
    ("zero sub-runs with gaps",
     dict(n_bridged_samples=0, n_bridged_gaps=2, n_eligible_subruns=0),
     "at least one"),
    ("zero sub-runs without gaps",
     dict(n_bridged_samples=0, n_bridged_gaps=0, n_eligible_subruns=0),
     "at least one"),
    ("samples without gaps",
     dict(n_bridged_samples=5, n_bridged_gaps=0, n_eligible_subruns=1), "disagree"),
    ("gaps without samples",
     dict(n_bridged_samples=0, n_bridged_gaps=1, n_eligible_subruns=2), "disagree"),
    ("more gaps than bridged samples",
     dict(n_bridged_samples=1, n_bridged_gaps=2, n_eligible_subruns=3), "fewer than"),
    ("gap/sub-run mismatch",
     dict(n_bridged_samples=2, n_bridged_gaps=1, n_eligible_subruns=3),
     "inconsistent interval record"),
    ("all three missing", dict(), "missing required count"),
    ("samples missing",
     dict(n_bridged_gaps=0, n_eligible_subruns=1), "missing required count"),
    ("gaps missing",
     dict(n_bridged_samples=0, n_eligible_subruns=1), "missing required count"),
    ("sub-runs missing",
     dict(n_bridged_samples=0, n_bridged_gaps=0), "missing required count"),
    ("explicit None",
     dict(n_bridged_samples=None, n_bridged_gaps=0, n_eligible_subruns=1),
     "missing required count"),
    ("boolean counts",
     dict(n_bridged_samples=True, n_bridged_gaps=False, n_eligible_subruns=True),
     "boolean"),
    ("boolean sub-runs only",
     dict(n_bridged_samples=0, n_bridged_gaps=0, n_eligible_subruns=True), "boolean"),
    ("numeric strings",
     dict(n_bridged_samples="0", n_bridged_gaps="0", n_eligible_subruns="1"),
     "integer count is required"),
    ("non-integral float",
     dict(n_bridged_samples=0.0, n_bridged_gaps=0.5, n_eligible_subruns=1.0),
     "is a float"),
    ("fractional sample count",
     dict(n_bridged_samples=2.5, n_bridged_gaps=1, n_eligible_subruns=2),
     "is a float"),
    # Increment 6.1.3: whole-valued floats are rejected too. The contract is an
    # integer count; 0.0 is not 0, and accepting it would make the type gate
    # depend on the value.
    ("whole-valued floats",
     dict(n_bridged_samples=0.0, n_bridged_gaps=0.0, n_eligible_subruns=1.0),
     "is a float"),
    ("NaN",
     dict(n_bridged_samples=float("nan"), n_bridged_gaps=0, n_eligible_subruns=1),
     "not finite"),
    ("positive infinity",
     dict(n_bridged_samples=float("inf"), n_bridged_gaps=1, n_eligible_subruns=2),
     "not finite"),
    ("negative infinity",
     dict(n_bridged_samples=float("-inf"), n_bridged_gaps=0, n_eligible_subruns=1),
     "not finite"),
    ("numpy NaN",
     dict(n_bridged_samples=np.nan, n_bridged_gaps=0, n_eligible_subruns=1),
     "not finite"),
    ("misspelled count keyword",
     dict(n_bridged_samples=0, n_bridged_gaps=0, n_eligible_subruns=1,
          n_bridged_sample=99), "unknown field"),
    ("entirely unknown keyword",
     dict(n_bridged_samples=0, n_bridged_gaps=0, n_eligible_subruns=1, zzz=1),
     "unknown field"),
    ("complex value",
     dict(n_bridged_samples=complex(0, 0), n_bridged_gaps=0, n_eligible_subruns=1),
     "integer count is required"),
    ("legacy alias n_interruptions",
     dict(n_bridged_samples=0, n_bridged_gaps=0, n_eligible_subruns=1,
          n_interruptions=1), "removed in Increment 6.1.1"),
    ("legacy alias n_interrupted_subruns",
     dict(n_bridged_samples=0, n_bridged_gaps=0, n_eligible_subruns=1,
          n_interrupted_subruns=2), "removed in Increment 6.1.1"),
]


@pytest.mark.parametrize(
    "label,counts", INTERVAL_VALID_MATRIX, ids=[r[0] for r in INTERVAL_VALID_MATRIX])
def test_interval_valid_count_records_construct(label, counts):
    iv = _interval(**counts)
    assert iv.n_bridged_gaps == iv.n_eligible_subruns - 1
    assert (iv.n_bridged_samples == 0) == (iv.n_bridged_gaps == 0)
    assert iv.n_bridged_gaps == 0 or iv.n_bridged_samples >= iv.n_bridged_gaps


@pytest.mark.parametrize(
    "label,counts,fragment", INTERVAL_INVALID_MATRIX,
    ids=[r[0] for r in INTERVAL_INVALID_MATRIX])
def test_interval_invalid_count_records_are_rejected(label, counts, fragment):
    with pytest.raises(PetrophysicsInputError, match=fragment):
        _interval(**counts)


def test_the_three_audited_invalid_records_are_now_rejected():
    """The exact records the Increment 6.1.2 audit showed were constructible
    under Increment 6.1.1."""
    audited = [
        dict(n_bridged_samples=5, n_bridged_gaps=0, n_eligible_subruns=1),
        dict(n_bridged_samples=0, n_bridged_gaps=2, n_eligible_subruns=0),
        dict(n_bridged_samples=-1, n_bridged_gaps=-1, n_eligible_subruns=0),
    ]
    for counts in audited:
        with pytest.raises(PetrophysicsInputError):
            _interval(**counts)


def test_every_error_message_names_the_field_or_the_relationship():
    """A validation error that does not say WHAT is wrong is not enforcement."""
    for label, counts, fragment in INTERVAL_INVALID_MATRIX:
        try:
            _interval(**counts)
        except PetrophysicsInputError as exc:
            msg = str(exc)
            assert "W/" in msg and MASK_DENSITY_FOR_SV in msg, label
            assert fragment in msg, f"{label}: {msg}"
        else:  # pragma: no cover - the parametrized test above would fail first
            raise AssertionError(f"{label} was accepted")


def test_real_block_builder_emits_only_valid_records():
    """The invariants must describe what the builder actually produces, not an
    aspiration the builder violates."""
    rhob = np.full(60, 2400.0)
    rhob[10:12] = np.nan
    rhob[30:31] = np.nan
    frame = _full_frame(n=60, rhob=rhob)
    cfg = _bridging_config()
    ivs = build_eligibility_intervals(frame, compute_density_eligibility(frame, cfg), cfg)
    assert ivs
    for iv in ivs:
        assert iv.n_eligible_subruns >= 1
        assert iv.n_bridged_gaps == iv.n_eligible_subruns - 1
        assert (iv.n_bridged_samples == 0) == (iv.n_bridged_gaps == 0)
        if iv.n_bridged_gaps:
            assert iv.n_bridged_samples >= iv.n_bridged_gaps


# ---------------------------------------------------------------------------
# Increment 6.1.2 (Finding 1): every audited case, driven through the REAL
# manifest-building path and the DERIVED completion gate - not a helper.
# ---------------------------------------------------------------------------

def _disposition_with_note(note):
    return GrFamilyDisposition(
        well_key="W_1", source_las_filename="W_1.las", gr_family_canonical_name="GR_api",
        gr_family_source_curve_name="GR", use_status="screening_proxy_allowed",
        exclusion_reason=None, evidence_class="measured", has_approved_formation_tops=True,
        notes=note,
    )


GATE_INJECTIONS_THAT_MUST_FAIL = [
    "Poseidon 2's shale volume is high.",
    "Poseidon 2's shale volume is 70 percent.",
    "The interval's shale volume is high.",
    "The interval's shale volume exceeds 60 percent.",
    "This interval contains shale gas.",
    "This interval has a high shale volume.",
]

# Increment 6.1.3 CONTRACT CHANGE: method wording in a per-well note is no
# longer permitted either. A per-well note is project-specific prose and has
# zero allowance; the project states its boundaries through registered METHOD
# statements instead. Asserted here so the change can never happen silently.
GATE_NOTES_THAT_MUST_ALSO_FAIL = [
    "This method contains a shale proxy calculation.",
    "The analysis shows no shale volume was computed.",
    "Excluded from every shale-proxy calculation; this is not a calibrated shale volume.",
]

# Increment 6.1.5: a note passes ONLY when it is a registered interpretive
# statement. "Sensible-looking" prose is no longer a category - the previous
# entries here were plausible sentences nobody had registered.
def _all_registered_interpretive_notes():
    from p2mem.wellframe_models import REGISTERED_STATEMENTS, SCOPE_INTERPRETIVE
    return sorted(s.text for s in REGISTERED_STATEMENTS.values()
                  if s.scope == SCOPE_INTERPRETIVE)


GATE_NOTES_THAT_MUST_PASS = _all_registered_interpretive_notes()

# Plausible, innocent, unregistered prose. Each must FAIL, which is what
# distinguishes positive authorization from semantic detection.
GATE_NOTES_UNREGISTERED_BUT_INNOCENT = [
    "The screening proxy is dimensionless and uncalibrated.",
    "This well has no approved formation tops, so results are depth-tied.",
    "Everything looks fine.",
]


@pytest.mark.parametrize("note", GATE_NOTES_UNREGISTERED_BUT_INNOCENT)
def test_innocent_unregistered_note_still_fails_the_derived_gate(note):
    """No prohibited term appears in any of these. They fail because nothing
    authorized them."""
    from p2mem.wellframe_models import find_prohibited_lithology_terms
    assert find_prohibited_lithology_terms(note) == (), note
    man = _manifest_with(disposition=_disposition_with_note(note))
    assert man["named_lithology_assigned"] is True, note
    assert _n_viol(man) > 0, note
    assert not _gate_passes(man), note


@pytest.mark.parametrize("note", GATE_INJECTIONS_THAT_MUST_FAIL
                         + GATE_NOTES_THAT_MUST_ALSO_FAIL)
def test_injected_assertion_fails_the_derived_gate(note):
    """The full derived path: real manifest builder -> real validation ->
    `named_lithology_assigned` -> completion gate."""
    man = _manifest_with(disposition=_disposition_with_note(note))
    assert man["named_lithology_assigned"] is True, note
    assert _n_viol(man) > 0, note
    assert not _gate_passes(man), note


@pytest.mark.parametrize("note", GATE_NOTES_THAT_MUST_PASS)
def test_legitimate_note_keeps_the_derived_gate_passing(note):
    """Notes that carry no rock name at all - which is what a per-well note
    must now look like - keep the gate passing."""
    man = _manifest_with(disposition=_disposition_with_note(note))
    assert man["named_lithology_assigned"] is False, note
    assert _n_viol(man) == 0, note
    assert _gate_passes(man), note


def test_registered_method_and_explanatory_statements_are_in_scope_and_pass():
    """Every registered method and explanatory statement is emitted by the real
    scope builder WITH its authorization, and all of them pass."""
    from p2mem.io.petrophysics_inventory import build_lithology_validation_scope
    from p2mem.wellframe_models import (
        REGISTERED_STATEMENTS, SCOPE_METHOD, SCOPE_EXPLANATORY,
        validate_no_prohibited_interpretation)
    scope = build_lithology_validation_scope(
        {"W_1": _clean_disposition()}, {"W_1": "GR_PROXY_INTERMEDIATE"},
        {"W_1": _registered_rationale()},
        [compute_density_eligibility(_full_frame(), _config())],
    )
    controlled = [e for e in scope if e[2] in (SCOPE_METHOD, SCOPE_EXPLANATORY)]
    expected = [s for s in REGISTERED_STATEMENTS.values()
                if s.scope in (SCOPE_METHOD, SCOPE_EXPLANATORY)]
    assert len(controlled) == len(expected)
    assert all(len(e) == 4 for e in controlled), "each must carry an Authorization"
    assert validate_no_prohibited_interpretation(controlled) == ()


def test_an_unregistered_method_statement_fails_the_derived_gate():
    """If a future edit changes a persisted method string without registering
    it, the gate must fail rather than silently ship the new wording."""
    from p2mem.io.petrophysics_inventory import build_lithology_validation_scope
    from p2mem.wellframe_models import (
        SCOPE_METHOD, validate_no_prohibited_interpretation)
    scope = build_lithology_validation_scope(
        {"W_1": _clean_disposition()}, {"W_1": "GR_PROXY_INTERMEDIATE"},
        {"W_1": _registered_rationale()},
        [compute_density_eligibility(_full_frame(), _config())],
        extra_entries=[
            ("proxy.limitations", "The proxy is not a calibrated shale volume.",
             SCOPE_METHOD),
        ],
    )
    violations = validate_no_prohibited_interpretation(scope)
    assert violations
    assert not _gate_passes({
        "named_lithology_assigned": bool(violations),
        "lithology_validation": {"violations": list(violations)},
    })


def test_explanatory_assertion_in_the_manifest_scope_fails_the_gate():
    """The manifest's own explanatory statement is inside the validated scope;
    a project-well assertion there must fail the derived gate."""
    from p2mem.io.petrophysics_inventory import build_lithology_validation_scope
    from p2mem.wellframe_models import (
        SCOPE_EXPLANATORY, validate_no_prohibited_interpretation)
    scope = build_lithology_validation_scope(
        {"W_1": _disposition("W_1")}, {"W_1": "GR_PROXY_INTERMEDIATE"}, {"W_1": "r"},
        [compute_density_eligibility(_full_frame(), _config())],
        extra_entries=[
            ("manifest.statement", "Poseidon 2's shale volume is high.", SCOPE_EXPLANATORY),
        ],
    )
    violations = validate_no_prohibited_interpretation(scope)
    assert violations and any(v["context"] == "manifest.statement" for v in violations)
    assert not _gate_passes({
        "named_lithology_assigned": bool(violations),
        "lithology_validation": {"violations": list(violations)},
    })


def test_unchanged_real_packaged_content_keeps_the_gate_passing():
    """The clean baseline must be unaffected by both corrections."""
    man = _manifest_with()
    assert man["lithology_validation"]["scope_object_fields_checked"] > 0
    assert _n_viol(man) == 0
    assert man["named_lithology_assigned"] is False
    assert _gate_passes(man)


# ---------------------------------------------------------------------------
# Increment 6.1.6: EMISSION-BOUNDARY authorization.
#
# Increment 6.1.5 closed the unit validator and left the export path open: a
# GrEndpointScenario carrying description="The interval is chalk." was persisted
# verbatim while never entering the 143-field scope. These tests run against the
# OUTPUT BUILDERS and the COMPLETE EXPORT, not against
# validate_no_prohibited_interpretation().
# ---------------------------------------------------------------------------

import copy as _copy
import json as _json
import pathlib as _pathlib

from p2mem.io import output_policy as _op
from p2mem.io.output_policy import (
    CSV_SCHEMAS, OUTPUT_FIELD_POLICY, OUTPUT_STATEMENTS, OUTPUT_TEMPLATES,
    OUTPUT_ARTIFACTS, OutputAuthorizationError, canonicalize_emitted_records,
    export_authorized_outputs, validate_emitted_records,
)

_PROJECT_ROOT = _pathlib.Path(__file__).resolve().parents[1]
_OUT = _PROJECT_ROOT / "outputs" / "06_petrophysics_eligibility"


def _real_payloads():
    """The ACTUAL packaged records when they are present, otherwise the SAME
    records produced by the SAME builders from the synthetic bundle.

    The notebook runs pytest before it writes any output, so the packaged
    artifacts do not exist at that point. Falling back to builder-produced
    records keeps every emission-boundary test genuinely executing there rather
    than silently skipping - the objects under test are real builder output
    either way.
    """
    import csv as _csv
    manifest_path = _OUT / "petrophysics_eligibility_manifest.json"
    if manifest_path.exists():
        payloads = {}
        for p in sorted(_OUT.glob("*.csv")):
            with open(p, newline="", encoding="utf-8") as fh:
                payloads[p.name] = list(_csv.DictReader(fh))
        payloads["petrophysics_eligibility_manifest.json"] = _json.loads(
            manifest_path.read_text(encoding="utf-8"))
        return payloads
    return _builder_payloads()


def _builder_payloads():
    """Every artifact, built by the REAL builders using APPROVED identifiers.

    The identifiers must be approved ones because a well key is itself a
    policy-classified emitted field - which is the point of the policy.
    """
    from p2mem.petrophysics_models import GrFamilyDisposition
    frames, stats, disp, conf, rationale, scen, proxies, masks = {}, {}, {}, {}, {}, {}, {}, []
    for wk in ("Poseidon_2", "Proteus_1ST2"):
        fr = _full_frame(n=20, gr=np.linspace(10.0, 110.0, 20), well_key=wk)
        frames[wk] = fr
        d = GrFamilyDisposition(
            well_key=wk, source_las_filename=f"{wk}_logs.las",
            gr_family_canonical_name="GR_api", gr_family_source_curve_name="GR",
            use_status="screening_proxy_allowed", exclusion_reason=None,
            evidence_class="measured", has_approved_formation_tops=True,
            notes=_registered_note())
        disp[wk] = d
        stats[wk] = compute_gr_family_qc_stats(fr, d)
        conf[wk] = "GR_PROXY_INTERMEDIATE"
        rationale[wk] = _registered_rationale()
        sc = _scenario(well_key=wk, name="base")
        scen[wk] = [sc]
        proxies[wk] = [compute_gr_proxy(fr, d, sc, _config())]
        for m in (compute_density_eligibility(fr, _config()),
                  compute_dynamic_elastic_eligibility(fr, _config())):
            masks.append(_output_registered_mask(m))
    intervals = []
    for m in masks:
        intervals.extend(build_eligibility_intervals(frames[m.well_key], m, _config()))
    payloads = {
        "gr_family_qc_summary.csv": build_gr_family_qc_rows(stats, disp, conf),
        "gr_endpoint_scenarios.csv": build_gr_endpoint_scenario_rows(scen),
        "gr_proxy_sensitivity_summary.csv": build_gr_proxy_sensitivity_rows(proxies, disp),
        "method_eligibility_summary.csv": build_method_eligibility_rows(masks, frames, disp),
        "eligibility_interval_register.csv": build_eligibility_interval_rows(intervals),
        "thickness_sensitivity_summary.csv": build_thickness_sensitivity_rows(intervals),
        "petrophysics_eligibility_issues.csv": build_petrophysics_issue_rows([], {}),
    }
    payloads["petrophysics_eligibility_manifest.json"] = build_petrophysics_manifest(
        frames, disp, stats, conf, rationale, scen, masks, {}, [],
        config_filename="petrophysics_eligibility.yml", config_schema_version="6.0",
        nct_candidate_thresholds=[0.5], output_payloads=payloads)
    return payloads


def _well_keys(payloads):
    return set(payloads["petrophysics_eligibility_manifest.json"]["wells"])


NOVEL_TOKENS = ["qxzite", "zzqqworp", "vundrelic", "morbaquin", "tesqualor"]


# --- 1-3. the builder must refuse an unauthorized description ---------------

@pytest.mark.parametrize("description", [
    "The interval is chalk.",                     # unknown lithology (test 1)
    "Everything looks fine.",                      # innocent prose      (test 2)
    "The interval is qxzite.",                     # generated novel     (test 3)
    "zzqqworp", "vundrelic sands of the upper member",
])
def test_endpoint_row_builder_rejects_unauthorized_description(description):
    sc = _scenario_for_export(description)
    with pytest.raises(PetrophysicsInputError, match="not authorized for emission"):
        build_gr_endpoint_scenario_rows({"Poseidon_2": [sc]})


def test_rejection_does_not_depend_on_lithology_recognition():
    """The decisive framing: the linter sees nothing in any of these."""
    from p2mem.wellframe_models import find_prohibited_lithology_terms
    for d in ["Everything looks fine.", "The interval is qxzite.", "zzqqworp"]:
        assert find_prohibited_lithology_terms(d) == (), d
        with pytest.raises(PetrophysicsInputError):
            build_gr_endpoint_scenario_rows({"Poseidon_2": [_scenario_for_export(d)]})


def _scenario_for_export(description):
    from p2mem.petrophysics_models import GrEndpointScenario
    return GrEndpointScenario(
        well_key="Poseidon_2", scenario_name="base", low_percentile=5.0,
        high_percentile=95.0, gr_low_endpoint_api=10.0, gr_high_endpoint_api=110.0,
        endpoint_separation_api=100.0, n_samples_used_for_endpoints=100,
        endpoint_sample_basis="finite_and_depth_mapped_samples_only",
        description=description, evidence_class="assumed_configured",
        calibration_status="uncalibrated_assumed_no_calibration_data_exists")


def test_a_registered_endpoint_description_is_accepted():
    rows = build_gr_endpoint_scenario_rows(
        {"Poseidon_2": [_scenario_for_export(_registered_endpoint_description())]})
    assert rows and rows[0]["description"] == _registered_endpoint_description()


# --- 4. mutate every controlled prose field of every builder ---------------

def _controlled_fields():
    return sorted(
        (k for k, p in OUTPUT_FIELD_POLICY.items()
         if p.category in ("registered_statement", "controlled_template")),
        key=lambda k: (k[0], k[1]))


@pytest.mark.parametrize("artifact,field", _controlled_fields())
def test_mutating_any_controlled_prose_field_is_rejected(artifact, field):
    """Requirement 4: mutate every controlled prose field produced by every
    output builder and prove the emitted artifact is rejected."""
    payloads = _real_payloads()
    wk = _well_keys(payloads)
    mutated, done = _copy.deepcopy(payloads), False
    if artifact.endswith(".json"):
        done = _mutate_json_path(mutated[artifact], field, wk)
    else:
        for row in mutated[artifact]:
            if isinstance(row.get(field), str) and row[field]:
                row[field] = row[field] + " Additional clause."
                done = True
                break
    if not done:
        pytest.skip(f"{artifact}:{field} has no occurrence in the packaged records")
    rep = validate_emitted_records(mutated, well_keys=wk)
    assert not rep.ok and rep.n_unauthorized_controlled_fields >= 1, (artifact, field)


def _mutate_json_path(node, target, well_keys, prefix="", value=None):
    """Replace the first occurrence of `target` with `value`, or - when no
    value is given - with the original text plus an extra clause."""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str) and v and _op._normalize_json_path(
                    f"{prefix}/{k}", well_keys) == target:
                node[k] = v + " Additional clause." if value is None else value
                return True
            if _mutate_json_path(v, target, well_keys, f"{prefix}/{k}", value):
                return True
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str) and v and _op._normalize_json_path(
                    f"{prefix}[{i}]", well_keys) == target:
                node[i] = v + " Additional clause." if value is None else value
                return True
            if _mutate_json_path(v, target, well_keys, f"{prefix}[{i}]", value):
                return True
    return False


# --- 5. cross-field label substitution -------------------------------------

def test_every_cross_field_label_substitution_is_rejected():
    """Requirement 5: replace each typed label with a valid label from a
    DIFFERENT field_kind; every substitution must fail."""
    from p2mem.wellframe_models import APPROVED_LABELS
    payloads = _real_payloads()
    wk = _well_keys(payloads)
    tried = 0
    for (artifact, field), pol in sorted(OUTPUT_FIELD_POLICY.items()):
        if pol.category != "typed_label" or artifact.endswith(".json"):
            continue
        others = [v for k, b in APPROVED_LABELS.items() if k != pol.field_kind
                  for v in b if v not in APPROVED_LABELS[pol.field_kind]]
        if not others:
            continue
        mutated = _copy.deepcopy(payloads)
        hit = False
        for row in mutated[artifact]:
            if isinstance(row.get(field), str) and row[field]:
                row[field] = others[0]
                hit = True
                break
        if not hit:
            continue
        tried += 1
        rep = validate_emitted_records(mutated, well_keys=wk)
        assert rep.n_field_kind_mismatches >= 1, (artifact, field, others[0])
    assert tried >= 5, f"cross-field substitution must be substantive, tried {tried}"


# --- 6-8. coverage must fail closed ----------------------------------------

def test_an_unknown_output_column_fails_coverage():
    payloads = _real_payloads()
    payloads["gr_family_qc_summary.csv"][0]["editorial_note"] = "Everything looks fine."
    rep = validate_emitted_records(payloads, well_keys=_well_keys(payloads))
    assert not rep.ok and rep.n_schema_violations >= 1


def test_an_unknown_json_path_fails_coverage():
    payloads = _real_payloads()
    payloads["petrophysics_eligibility_manifest.json"]["editorial_note"] = "zzqqworp"
    rep = validate_emitted_records(payloads, well_keys=_well_keys(payloads))
    assert not rep.ok and rep.n_schema_violations >= 1


def test_an_unknown_artifact_fails_coverage():
    payloads = _real_payloads()
    payloads["surprise_extra_output.csv"] = [{"note": "Everything looks fine."}]
    rep = validate_emitted_records(payloads, well_keys=_well_keys(payloads))
    assert not rep.ok


def test_removing_a_required_policy_entry_fails_the_gate(monkeypatch):
    """Requirement 8: remove a required field-policy entry; the gate must fail."""
    payloads = _real_payloads()
    reduced = dict(OUTPUT_FIELD_POLICY)
    victim = ("gr_family_qc_summary.csv", "limitations")
    assert victim in reduced
    del reduced[victim]
    monkeypatch.setattr(_op, "OUTPUT_FIELD_POLICY", reduced)
    rep = validate_emitted_records(payloads, well_keys=_well_keys(payloads))
    assert not rep.ok and rep.n_unclassified_fields >= 1


def test_a_missing_declared_artifact_fails_the_gate():
    payloads = _real_payloads()
    payloads.pop("thickness_sensitivity_summary.csv")
    rep = validate_emitted_records(payloads, well_keys=_well_keys(payloads))
    assert not rep.ok


# --- 9-10. the manifest statement is canonical, and immutable after auth ----

def test_manifest_uses_the_canonical_registered_statement(monkeypatch):
    """Requirement 9: change the registered text and prove the manifest follows
    it rather than a duplicated literal."""
    import p2mem.wellframe_models as wm
    original = wm.REGISTERED_STATEMENTS["named_lithology_statement"]
    altered = wm.RegisteredStatement(
        statement_id=original.statement_id, scope=original.scope,
        text="CANONICAL SENTINEL VALUE FOR THIS TEST.",
        purpose=original.purpose, provenance=original.provenance)
    monkeypatch.setitem(wm.REGISTERED_STATEMENTS, "named_lithology_statement", altered)
    man = _manifest_with()
    assert man["named_lithology_statement"] == "CANONICAL SENTINEL VALUE FOR THIS TEST."


def test_post_authorization_mutation_of_the_manifest_statement_is_caught(tmp_path):
    """Requirement 10: change the final emitted statement AFTER authorization and
    prove validation fails."""
    payloads = _builder_payloads()
    wk = _well_keys(payloads)
    assert validate_emitted_records(payloads, well_keys=wk).ok

    def _tampering_writer(target, payload):
        if str(target).endswith(".json"):
            tampered = _copy.deepcopy(payload)
            tampered["named_lithology_statement"] = "The interval is chalk."
            target.write_text(_json.dumps(tampered, indent=2, sort_keys=True) + "\n",
                              encoding="utf-8")
        else:
            import csv as _csv
            with open(target, "w", encoding="utf-8", newline="") as fh:
                if payload:
                    w = _csv.DictWriter(fh, fieldnames=list(payload[0].keys()))
                    w.writeheader()
                    w.writerows(payload)

    with pytest.raises(OutputAuthorizationError, match="post-serialization"):
        export_authorized_outputs(tmp_path, payloads, well_keys=wk,
                                  writer=_tampering_writer)


def test_export_refuses_to_write_anything_when_a_field_is_unauthorized(tmp_path):
    payloads = _builder_payloads()
    payloads["gr_endpoint_scenarios.csv"][0]["description"] = "The interval is chalk."
    with pytest.raises(OutputAuthorizationError, match="refusing to write"):
        export_authorized_outputs(tmp_path, payloads, well_keys=_well_keys(payloads))
    assert not list(tmp_path.glob("*")), "nothing may be written when authorization fails"


# --- 11-12. coverage and occurrence counting -------------------------------

def test_every_emitted_string_field_has_exactly_one_policy_classification():
    """Requirement 11."""
    payloads = _real_payloads()
    wk = _well_keys(payloads)
    seen = set()
    for artifact, payload in payloads.items():
        for occ in _op.collect_string_fields(artifact, payload, wk):
            key = (occ.artifact, occ.field)
            assert key in OUTPUT_FIELD_POLICY, f"unclassified {key}"
            seen.add(key)
    assert len(seen) >= 40
    # exactly one: the mapping is a dict, and duplicates raise at import
    assert len(OUTPUT_FIELD_POLICY) == len(set(OUTPUT_FIELD_POLICY))


def test_every_occurrence_is_validated_not_merely_each_registry_entry():
    """Requirement 12: occurrences, not distinct values."""
    payloads = _real_payloads()
    rep = validate_emitted_records(payloads, well_keys=_well_keys(payloads))
    assert rep.ok
    assert rep.n_string_field_occurrences > 200, rep.n_string_field_occurrences
    assert rep.n_controlled_occurrences > 50
    # far more occurrences than distinct registry entries - proving occurrences
    assert rep.n_controlled_occurrences > 3 * rep.distinct_statements_used


def test_coverage_counters_are_internally_consistent():
    payloads = _real_payloads()
    rep = validate_emitted_records(payloads, well_keys=_well_keys(payloads))
    assert (rep.n_controlled_occurrences + rep.n_structural_occurrences
            + rep.n_unguaranteed_occurrences) == rep.n_string_field_occurrences
    assert rep.n_unclassified_fields == 0
    assert rep.n_unauthorized_controlled_fields == 0
    assert rep.n_field_kind_mismatches == 0


# --- 13. the derived gate moves with the emitted records -------------------

def test_gate_fails_when_a_final_emitted_controlled_field_is_unauthorized():
    """Requirement 13."""
    payloads = {k: v for k, v in _real_payloads().items() if k.endswith(".csv")}
    payloads["gr_endpoint_scenarios.csv"][0]["description"] = "The interval is chalk."
    man = _manifest_with_output_payloads(payloads)
    assert man["named_lithology_assigned"] is True
    assert len(man["lithology_validation"]["violations"]) >= 1
    assert not _gate_passes(man)


def _manifest_with_output_payloads(payloads):
    d = _clean_disposition()
    frame = _full_frame(n=20, gr=np.linspace(10.0, 110.0, 20), well_key="W_1")
    stats = compute_gr_family_qc_stats(frame, d)
    mask = _registered_mask(compute_density_eligibility(frame, _config()))
    return build_petrophysics_manifest(
        {"W_1": frame}, {"W_1": d}, {"W_1": stats}, {"W_1": "GR_PROXY_INTERMEDIATE"},
        {"W_1": _registered_rationale()}, {"W_1": []}, [mask], {}, [],
        config_filename="c.yml", config_schema_version="6.0",
        nct_candidate_thresholds=[0.5], output_payloads=payloads)


def test_the_real_packaged_records_keep_the_gate_passing():
    payloads = {k: v for k, v in _real_payloads().items() if k.endswith(".csv")}
    man = _manifest_with_output_payloads(payloads)
    cov = man["lithology_validation"]["emitted_field_coverage"]
    assert cov["n_unclassified_fields"] == 0
    assert cov["n_unauthorized_controlled_fields"] == 0
    assert cov["n_field_kind_mismatches"] == 0
    assert man["named_lithology_assigned"] is False and _gate_passes(man)


def test_the_manifest_no_longer_reports_a_count_that_overstates_what_it_checked():
    """Requirement 6: `n_fields_checked=143` is gone; the counts say what they
    count, and the emitted coverage is reported separately."""
    payloads = {k: v for k, v in _real_payloads().items() if k.endswith(".csv")}
    lv = _manifest_with_output_payloads(payloads)["lithology_validation"]
    assert "n_fields_checked" not in lv
    assert lv["scope_object_fields_checked"] > 0
    assert lv["emitted_field_coverage"]["n_string_field_occurrences"] > 100
    assert lv["model"] == (
        "schema_driven_transactional_authorization_at_emission_boundary")


def test_the_derivation_describes_the_emission_boundary_model():
    """Finding 4: the stale 6.1.5 wording must be gone from the live builder."""
    lv = _manifest_with()["lithology_validation"]
    assert "Interpretive fields admit no prohibited term at all" not in lv["derivation"]
    assert "EMISSION BOUNDARY" in lv["derivation"]
    assert lv["derivation"] == OUTPUT_STATEMENTS["lithology_validation_derivation"].text


def test_no_duplicated_manifest_statement_literal_remains():
    """Finding 5: one source of truth."""
    import inspect
    import p2mem.io.petrophysics_inventory as inv
    src = inspect.getsource(inv.build_petrophysics_manifest)
    assert "NO named lithology is assigned anywhere in Increment 6." not in src
    assert 'REGISTERED_STATEMENTS["named_lithology_statement"].text' in src


# ---------------------------------------------------------------------------
# The diagnostic contract, tested SEPARATELY from the controlled guarantee
# ---------------------------------------------------------------------------
# `sanitized_diagnostic` is the one category whose content originates outside
# this package (caught exception text, file-level QC messages). It therefore
# cannot be enumerated in advance and is deliberately NOT covered by the
# controlled-interpretation guarantee. What it does carry is an explicit
# safety/provenance contract, and that contract is what these tests exercise.


def _sanitized_field():
    """A real (artifact, field) pair whose declared category is sanitized."""
    for key, pol in sorted(OUTPUT_FIELD_POLICY.items()):
        if pol.category == "sanitized_diagnostic":
            return key
    raise AssertionError("no sanitized_diagnostic field is declared")


def test_the_sanitized_diagnostic_contract_bounds_length():
    """Contract clause 1: bounded length."""
    from p2mem.io.output_policy import (
        FieldOccurrence, authorize_occurrence, SANITIZED_DIAGNOSTIC_MAX_LEN)
    artifact, field = _sanitized_field()
    at_limit = "a" * SANITIZED_DIAGNOSTIC_MAX_LEN
    over = "a" * (SANITIZED_DIAGNOSTIC_MAX_LEN + 1)
    ok_at, _, _ = authorize_occurrence(
        FieldOccurrence(artifact, field, at_limit, "probe"))
    ok_over, _, why = authorize_occurrence(
        FieldOccurrence(artifact, field, over, "probe"))
    assert ok_at is True
    assert ok_over is False and "length" in why


def test_the_sanitized_diagnostic_contract_rejects_control_and_path_sequences():
    """Contract clause 2: no newline, carriage return, tab, backslash or
    URL-ish scheme separator may survive into a written diagnostic field."""
    from p2mem.io.output_policy import FieldOccurrence, authorize_occurrence
    artifact, field = _sanitized_field()
    for bad in ("line one\nline two", "carriage\rreturn", "tab\there",
                "C:\\Users\\someone\\secret.las", "see https://example.invalid/x",
                "file:///home/someone/private"):
        ok, _, why = authorize_occurrence(
            FieldOccurrence(artifact, field, bad, "probe"))
        assert ok is False, f"{bad!r} must be refused by the diagnostic contract"
        assert why


def test_the_sanitized_diagnostic_contract_restricts_the_charset():
    """Contract clause 3: printable-ASCII subset only."""
    from p2mem.io.output_policy import FieldOccurrence, authorize_occurrence
    artifact, field = _sanitized_field()
    for bad in ("curve \u2013 missing", "temperature 25\u00b0C", "\u0000null"):
        ok, _, why = authorize_occurrence(
            FieldOccurrence(artifact, field, bad, "probe"))
        assert ok is False and "charset" in why


def test_a_sanitized_diagnostic_is_not_counted_as_a_controlled_field():
    """The claim boundary itself: a diagnostic field that PASSES its contract
    must still be counted OUTSIDE the controlled-interpretation guarantee.

    This is the test that would fail if the sanitized category were ever
    quietly folded into the controlled bucket to make a coverage number
    look better."""
    from p2mem.io.output_policy import (
        CONTROLLED_CATEGORIES, UNGUARANTEED_CATEGORIES,
        FieldOccurrence, authorize_occurrence)
    artifact, field = _sanitized_field()
    assert "sanitized_diagnostic" in UNGUARANTEED_CATEGORIES
    assert "sanitized_diagnostic" not in CONTROLLED_CATEGORIES
    assert "structured_diagnostic" in UNGUARANTEED_CATEGORIES
    assert "structured_diagnostic" not in CONTROLLED_CATEGORIES

    # An arbitrary sentence PASSES the sanitized contract - by design.
    prose = "The interval is chalk and the operator was competent."
    ok, _auth, _why = authorize_occurrence(
        FieldOccurrence(artifact, field, prose, "probe"))
    assert ok is True, ("the diagnostic contract is a safety contract, not an "
                        "interpretation guarantee - this must pass")

    # ... and passing it must move the counter that is EXCLUDED from the
    # guarantee, never the controlled counter.
    payloads = _real_payloads()
    wk = _well_keys(payloads)
    base = validate_emitted_records(payloads, well_keys=wk)
    mutated = _copy.deepcopy(payloads)
    done = False
    if artifact.endswith(".json"):
        done = _mutate_json_path(mutated[artifact], field, wk, value=prose)
    else:
        for row in mutated[artifact]:
            if isinstance(row.get(field), str) and row[field]:
                row[field] = prose
                done = True
                break
    if done:
        after = validate_emitted_records(mutated, well_keys=wk)
        assert after.ok is True, (
            "replacing a diagnostic value with prose must NOT fail the gate - "
            "the diagnostic contract makes no interpretation claim")
        assert after.n_controlled_occurrences == base.n_controlled_occurrences
        assert after.n_unguaranteed_occurrences == base.n_unguaranteed_occurrences


def test_the_structured_diagnostic_grammar_admits_no_sentence():
    """The other unguaranteed category is far tighter: it is a machine grammar
    and cannot express prose at all, which is why it needs no length bound."""
    from p2mem.io.output_policy import FieldOccurrence, authorize_occurrence
    artifact, field = next(
        k for k, p in sorted(OUTPUT_FIELD_POLICY.items())
        if p.category == "structured_diagnostic")
    for prose in ("The interval is chalk.",
                  "Everything looks fine.",
                  "gaps=3; the operator was competent",
                  "The interval is qxzite."):
        ok, _, why = authorize_occurrence(
            FieldOccurrence(artifact, field, prose, "probe"))
        assert ok is False, f"{prose!r} must not parse as a structured diagnostic"
        assert why


# ---------------------------------------------------------------------------
# Increment 6.1.7: closed schemas and transactional round-trip integrity.
# ---------------------------------------------------------------------------

def _write_payload_for_gate(target, payload, mutate=None):
    """Test serializer with the production schema's exact column order."""
    import csv as _csv
    value = _copy.deepcopy(payload)
    if mutate is not None:
        value = mutate(target.name, value)
    if target.suffix == ".json":
        target.write_text(_json.dumps(value, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
    else:
        with open(target, "w", encoding="utf-8", newline="") as fh:
            writer = _csv.DictWriter(fh, fieldnames=list(CSV_SCHEMAS[target.name].columns))
            writer.writeheader()
            writer.writerows(value)


def test_removing_a_required_column_from_every_row_fails_schema():
    payloads = _real_payloads()
    for row in payloads["gr_endpoint_scenarios.csv"]:
        row.pop("description")
    rep = validate_emitted_records(payloads, well_keys=_well_keys(payloads))
    assert not rep.ok and rep.n_schema_violations >= 1


@pytest.mark.parametrize("bad", ["", None, 123, "123"])
def test_controlled_csv_field_cannot_disappear_by_value_or_type(bad):
    payloads = _real_payloads()
    payloads["gr_endpoint_scenarios.csv"][0]["description"] = bad
    rep = validate_emitted_records(payloads, well_keys=_well_keys(payloads))
    assert not rep.ok
    assert rep.n_schema_violations + rep.n_unauthorized_controlled_fields >= 1


@pytest.mark.parametrize("bad", ["", "123", None])
def test_unknown_csv_column_fails_independently_of_its_value(bad):
    payloads = _real_payloads()
    for row in payloads["gr_endpoint_scenarios.csv"]:
        row["rogue_column"] = bad
    rep = validate_emitted_records(payloads, well_keys=_well_keys(payloads))
    assert not rep.ok and rep.n_schema_violations >= 1


@pytest.mark.parametrize("bad", ["", 123, None])
def test_unknown_json_path_fails_independently_of_its_value(bad):
    payloads = _real_payloads()
    payloads["petrophysics_eligibility_manifest.json"]["rogue_path"] = bad
    rep = validate_emitted_records(payloads, well_keys=_well_keys(payloads))
    assert not rep.ok and rep.n_schema_violations >= 1


@pytest.mark.parametrize("bad", ["", None, 123, "123"])
def test_controlled_json_statement_requires_nonempty_registered_text(bad):
    payloads = _real_payloads()
    payloads["petrophysics_eligibility_manifest.json"][
        "named_lithology_statement"] = bad
    rep = validate_emitted_records(payloads, well_keys=_well_keys(payloads))
    assert not rep.ok
    assert rep.n_schema_violations + rep.n_unauthorized_controlled_fields >= 1


def test_authorized_to_authorized_writer_mutation_is_detected_transactionally(tmp_path):
    payloads = _builder_payloads()
    wk = _well_keys(payloads)
    target = tmp_path / "gr_endpoint_scenarios.csv"
    sentinel = b"approved baseline bytes\n"
    target.write_bytes(sentinel)
    replacement = OUTPUT_STATEMENTS["gr_endpoint_scenarios_description_2"].text

    def mutate(name, value):
        if name == "gr_endpoint_scenarios.csv":
            value[0]["description"] = replacement
        return value

    def writer(path, value):
        _write_payload_for_gate(path, value, mutate=mutate)

    with pytest.raises(OutputAuthorizationError, match="canonical record mismatch"):
        export_authorized_outputs(tmp_path, payloads, well_keys=wk, writer=writer)
    assert target.read_bytes() == sentinel
    assert {p.name for p in tmp_path.iterdir()} == {target.name}


def test_unauthorized_post_serialization_mutation_leaves_destination_unchanged(tmp_path):
    payloads = _builder_payloads()
    wk = _well_keys(payloads)
    target = tmp_path / "gr_endpoint_scenarios.csv"
    sentinel = b"approved baseline bytes\n"
    target.write_bytes(sentinel)

    def mutate(name, value):
        if name == "gr_endpoint_scenarios.csv":
            value[0]["description"] = "The interval is chalk."
        return value

    def writer(path, value):
        _write_payload_for_gate(path, value, mutate=mutate)

    with pytest.raises(OutputAuthorizationError, match="post-serialization"):
        export_authorized_outputs(tmp_path, payloads, well_keys=wk, writer=writer)
    assert target.read_bytes() == sentinel
    assert {p.name for p in tmp_path.iterdir()} == {target.name}


def test_undeclared_stale_destination_artifact_is_rejected(tmp_path):
    payloads = _builder_payloads()
    rogue = tmp_path / "rogue_stale.csv"
    rogue.write_text("claim\nThe interval is chalk.\n", encoding="utf-8")
    with pytest.raises(OutputAuthorizationError, match="undeclared stale"):
        export_authorized_outputs(tmp_path, payloads, well_keys=_well_keys(payloads))
    assert rogue.exists()


def test_successful_export_round_trips_every_canonical_value(tmp_path):
    payloads = _builder_payloads()
    before, after = export_authorized_outputs(
        tmp_path, payloads, well_keys=_well_keys(payloads))
    assert before.ok and after.ok
    assert before.n_schema_violations == after.n_schema_violations == 0
    assert before.n_string_field_occurrences == after.n_string_field_occurrences
    assert before.n_controlled_occurrences == after.n_controlled_occurrences
    assert {p.name for p in tmp_path.iterdir()} == set(OUTPUT_ARTIFACTS)


def test_csv_schema_string_partition_matches_authorization_policy():
    for artifact, schema in CSV_SCHEMAS.items():
        policy_fields = {
            field for (name, field) in OUTPUT_FIELD_POLICY if name == artifact
        }
        assert policy_fields == set(schema.string_fields)


def test_unapproved_dynamic_well_key_fails_closed():
    payloads = _real_payloads()
    manifest = payloads["petrophysics_eligibility_manifest.json"]
    first = next(iter(manifest["wells"].values()))
    manifest["wells"]["Rogue_Well"] = _copy.deepcopy(first)
    rep = validate_emitted_records(
        payloads, well_keys=tuple(manifest["wells"]))
    assert not rep.ok and rep.n_schema_violations >= 1
    assert any("unapproved identifier" in v["reason"] for v in rep.violations)


def test_numeric_schema_rejects_boolean_and_nonfinite_values_before_write():
    for bad in (True, float("nan"), float("inf"), float("-inf")):
        payloads = _builder_payloads()
        payloads["gr_endpoint_scenarios.csv"][0]["low_percentile"] = bad
        rep = validate_emitted_records(
            payloads, well_keys=_well_keys(payloads), serialization_stage="pre")
        assert not rep.ok and rep.n_schema_violations >= 1


@pytest.mark.parametrize("mutation", [
    "missing_header", "unknown_header", "numeric_controlled", "row_reordered",
])
def test_every_post_serialization_shape_or_value_mutation_is_rejected_without_publish(
        tmp_path, mutation):
    """The post-write gate checks schema AND complete values, never counts."""
    import csv as _csv
    payloads = _builder_payloads()
    wk = _well_keys(payloads)
    sentinel = tmp_path / "gr_endpoint_scenarios.csv"
    sentinel.write_bytes(b"official bytes remain unchanged\n")

    def writer(path, value):
        if path.suffix == ".json":
            path.write_text(_json.dumps(value, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
            return
        columns = list(CSV_SCHEMAS[path.name].columns)
        rows = _copy.deepcopy(value)
        if path.name == "gr_endpoint_scenarios.csv":
            if mutation == "missing_header":
                columns.remove("description")
            elif mutation == "unknown_header":
                columns.append("rogue_column")
                for row in rows:
                    row["rogue_column"] = ""
            elif mutation == "numeric_controlled":
                rows[0]["description"] = "123"
            elif mutation == "row_reordered":
                rows.reverse()
        with open(path, "w", encoding="utf-8", newline="") as fh:
            out = _csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
            out.writeheader()
            out.writerows(rows)

    with pytest.raises(OutputAuthorizationError):
        export_authorized_outputs(tmp_path, payloads, well_keys=wk, writer=writer)
    assert sentinel.read_bytes() == b"official bytes remain unchanged\n"
    assert {p.name for p in tmp_path.iterdir()} == {sentinel.name}


def test_serializer_exception_is_typed_and_leaves_destination_unchanged(tmp_path):
    payloads = _builder_payloads()
    sentinel = tmp_path / "gr_endpoint_scenarios.csv"
    sentinel.write_bytes(b"unchanged\n")

    def writer(_path, _value):
        raise RuntimeError("simulated serializer failure")

    with pytest.raises(OutputAuthorizationError, match="serializer failed"):
        export_authorized_outputs(
            tmp_path, payloads, well_keys=_well_keys(payloads), writer=writer)
    assert sentinel.read_bytes() == b"unchanged\n"
    assert {p.name for p in tmp_path.iterdir()} == {sentinel.name}


def test_mid_publication_replace_failure_rolls_back_every_official_file(
        tmp_path, monkeypatch):
    """Handled process failure during publication restores the complete set."""
    import os as _os
    payloads = _builder_payloads()
    original = {}
    for i, name in enumerate(sorted(OUTPUT_ARTIFACTS)):
        data = f"official-{i}-{name}\n".encode()
        (tmp_path / name).write_bytes(data)
        original[name] = data

    real_replace = _os.replace
    published = 0

    def fail_second_publication(src, dst):
        nonlocal published
        src_path, dst_path = _pathlib.Path(src), _pathlib.Path(dst)
        if ".stage-" in src_path.parent.name and dst_path.parent == tmp_path:
            published += 1
            if published == 2:
                raise OSError("simulated mid-publication failure")
        return real_replace(src, dst)

    monkeypatch.setattr(_os, "replace", fail_second_publication)
    with pytest.raises(OSError, match="mid-publication"):
        export_authorized_outputs(
            tmp_path, payloads, well_keys=_well_keys(payloads))
    assert {p.name for p in tmp_path.iterdir()} == set(OUTPUT_ARTIFACTS)
    assert {name: (tmp_path / name).read_bytes() for name in original} == original
