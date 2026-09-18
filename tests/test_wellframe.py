"""
Increment 6 - well-frame assembly tests.

SYNTHETIC ONLY. Every LAS result, deviation result, and curve array in
this file is fabricated in-memory from fictional numbers. No real or
private project file is read, referenced, or packaged.
"""

import numpy as np
import pytest

from p2mem.depth_mapping import DepthMappingError
from p2mem.wellframe import (
    QC_FLAG_DEPTH_COVERAGE_LIMITED,
    QC_FLAG_GR_FAMILY_ABSENT,
    QC_FLAG_NO_DEPTH_COVERAGE,
    WellFrameAssemblyError,
    assemble_well_frame,
    assemble_well_frames,
)
from p2mem.wellframe_models import (
    DEPTH_MAP_STATUS_FULL,
    DEPTH_MAP_STATUS_NONE,
    DEPTH_MAP_STATUS_PARTIAL,
    PROHIBITED_LITHOLOGY_TERMS,
    assert_no_lithology_vocabulary,
)


# ---------------------------------------------------------------------------
# Synthetic builders (shared, cwd-independent - see tests/synthetic_inc6.py)
# ---------------------------------------------------------------------------

from synthetic_inc6 import synthetic_las as _synthetic_las  # noqa: E402
from synthetic_inc6 import synthetic_survey as _synthetic_survey  # noqa: E402


def _basic_frame(**kw):
    md = np.array([50.0, 100.0, 150.0, 200.0, 250.0, 300.0])
    las = _synthetic_las({"MD_m": md, "GR_api": np.array([10.0, 20.0, np.nan, 40.0, 50.0, 60.0])})
    dev = _synthetic_survey()
    return assemble_well_frame(
        "Synth_1", las, dev, las_path="/synthetic/Synth_1_logs.las",
        survey_path="/synthetic/Synth_1_dev.txt", gr_family_canonical_name="GR_api", **kw
    )


# ---------------------------------------------------------------------------
# Sample/order preservation
# ---------------------------------------------------------------------------

def test_well_frame_preserves_sample_count_and_order():
    """A well frame never truncates, pads, resamples, sorts, or reorders."""
    md = np.array([50.0, 100.0, 150.0, 200.0, 250.0, 300.0])
    gr = np.array([10.0, 20.0, np.nan, 40.0, 50.0, 60.0])
    frame = _basic_frame()
    assert frame.n_samples == md.size
    np.testing.assert_array_equal(frame.MD_m, md)
    np.testing.assert_array_equal(frame.curve("GR_api").values, gr)
    assert frame.TVD_m.size == md.size
    assert frame.TVDSS_m.size == md.size


def test_well_frame_never_deletes_failed_samples():
    """An invalid sample stays in place as NaN and is expressed only in the
    mask - never dropped, filled, or interpolated."""
    frame = _basic_frame()
    slot = frame.curve("GR_api")
    assert slot.n_samples == 6
    assert slot.valid_count == 5
    assert np.isnan(slot.values[2])
    assert slot.valid_mask[2] is np.False_ or slot.valid_mask[2] == False  # noqa: E712
    assert np.count_nonzero(slot.valid_mask) == 5


def test_well_frame_arrays_are_read_only():
    """Downstream consumers cannot mutate a frame's arrays in place."""
    frame = _basic_frame()
    assert not frame.MD_m.flags.writeable
    assert not frame.TVDSS_m.flags.writeable
    assert not frame.curve("GR_api").values.flags.writeable
    with pytest.raises(ValueError):
        frame.MD_m[0] = 1.0


def test_well_frame_length_mismatch_rejected_with_typed_error():
    """A curve whose length disagrees with MD_m is a structural defect and
    is never reconciled by truncation or padding."""
    las = _synthetic_las(
        {"MD_m": np.array([50.0, 100.0, 150.0]), "GR_api": np.array([1.0, 2.0])}
    )
    with pytest.raises(WellFrameAssemblyError, match="never truncates, pads, or resamples"):
        assemble_well_frame(
            "Synth_1", las, _synthetic_survey(),
            las_path="/synthetic/a.las", survey_path="/synthetic/a_dev.txt",
        )


def test_well_frame_missing_md_rejected():
    las = _synthetic_las({"GR_api": np.array([1.0, 2.0, 3.0])})
    with pytest.raises(WellFrameAssemblyError, match="no canonical 'MD_m'"):
        assemble_well_frame(
            "Synth_1", las, _synthetic_survey(),
            las_path="/synthetic/a.las", survey_path="/synthetic/a_dev.txt",
        )


# ---------------------------------------------------------------------------
# Depth mapping: no extrapolation, ever
# ---------------------------------------------------------------------------

def test_no_extrapolation_all_samples_within_coverage():
    frame = _basic_frame()
    assert frame.depth_map_status == DEPTH_MAP_STATUS_FULL
    assert frame.n_extrapolated == 0
    assert frame.n_depth_unmapped == 0
    assert bool(np.all(frame.depth_valid_mask))


def test_samples_beyond_survey_coverage_are_unmapped_never_extrapolated():
    """A LAS sample past the last survey station gets NaN depth and a False
    mask - never a clamped or held-constant TVD."""
    md = np.array([100.0, 200.0, 300.0, 400.0, 500.0, 900.0])  # last two beyond 400 m coverage
    las = _synthetic_las({"MD_m": md, "GR_api": np.full(6, 30.0)})
    frame = assemble_well_frame(
        "Synth_1", las, _synthetic_survey(),
        las_path="/s/a.las", survey_path="/s/a_dev.txt", gr_family_canonical_name="GR_api",
    )
    assert frame.depth_map_status == DEPTH_MAP_STATUS_PARTIAL
    assert frame.n_extrapolated == 0
    assert frame.n_depth_unmapped == 2
    assert np.isnan(frame.TVD_m[-1]) and np.isnan(frame.TVDSS_m[-1])
    assert not frame.depth_valid_mask[-1]
    # The in-coverage samples still carry genuine, locked-mapper values.
    assert np.isfinite(frame.TVD_m[0]) and np.isfinite(frame.TVDSS_m[3])
    assert any(f.startswith(QC_FLAG_DEPTH_COVERAGE_LIMITED) for f in frame.qc_flags)


def test_sample_below_survey_start_is_unmapped():
    md = np.array([-50.0, 100.0, 200.0])
    las = _synthetic_las({"MD_m": md, "GR_api": np.full(3, 30.0)})
    frame = assemble_well_frame(
        "Synth_1", las, _synthetic_survey(md=(0.0, 100.0, 200.0), tvd=(0.0, 100.0, 199.0)),
        las_path="/s/a.las", survey_path="/s/a_dev.txt",
    )
    assert frame.n_depth_unmapped == 1
    assert np.isnan(frame.TVD_m[0])
    assert frame.n_extrapolated == 0


def test_zero_coverage_overlap_reports_none_status():
    md = np.array([9000.0, 9100.0, 9200.0])
    las = _synthetic_las({"MD_m": md, "GR_api": np.full(3, 30.0)})
    frame = assemble_well_frame(
        "Synth_1", las, _synthetic_survey(),
        las_path="/s/a.las", survey_path="/s/a_dev.txt",
    )
    assert frame.depth_map_status == DEPTH_MAP_STATUS_NONE
    assert frame.n_depth_unmapped == 3
    assert frame.n_extrapolated == 0
    assert QC_FLAG_NO_DEPTH_COVERAGE in frame.qc_flags
    assert bool(np.all(np.isnan(frame.TVDSS_m)))


def test_tvdss_equals_tvd_minus_datum_elevation():
    """The locked depth-reference convention is reproduced exactly, not
    re-derived with a different sign."""
    frame = _basic_frame()
    finite = np.isfinite(frame.TVD_m)
    np.testing.assert_allclose(
        frame.TVDSS_m[finite], frame.TVD_m[finite] - frame.datum_elevation_m
    )


def test_single_station_survey_rejected():
    las = _synthetic_las({"MD_m": np.array([10.0, 20.0]), "GR_api": np.array([1.0, 2.0])})
    dev = _synthetic_survey(md=(0.0,), tvd=(0.0,))
    with pytest.raises(DepthMappingError):
        assemble_well_frame(
            "Synth_1", las, dev, las_path="/s/a.las", survey_path="/s/a_dev.txt"
        )


# ---------------------------------------------------------------------------
# Per-file GR identity preservation
# ---------------------------------------------------------------------------

def test_gr_family_identity_is_recorded_never_guessed():
    """The GR-family curve is the one the caller names, and its per-file
    source identity is preserved."""
    md = np.arange(5, dtype=float) * 50.0 + 50.0
    las = _synthetic_las({"MD_m": md, "ECGR_api": np.full(5, 8.0)}, source_filename="B_logs.las")
    frame = assemble_well_frame(
        "B_1", las, _synthetic_survey(), las_path="/s/B_logs.las",
        survey_path="/s/B_dev.txt", gr_family_canonical_name="ECGR_api",
    )
    assert frame.gr_family_canonical_name == "ECGR_api"
    assert frame.gr_family_source_curve_name == "ECGR"
    assert frame.curve("ECGR_api").source_filename == "B_logs.las"


def test_absent_gr_family_curve_is_flagged_never_substituted():
    """A well missing its declared GR-family curve is flagged as a data
    gap - another curve is never silently used instead."""
    md = np.arange(5, dtype=float) * 50.0 + 50.0
    las = _synthetic_las({"MD_m": md, "RHOB_kg_m3": np.full(5, 2400.0)})
    frame = assemble_well_frame(
        "Synth_1", las, _synthetic_survey(), las_path="/s/a.las",
        survey_path="/s/a_dev.txt", gr_family_canonical_name="GRD_api",
    )
    assert frame.gr_family_canonical_name is None
    assert any(f.startswith(QC_FLAG_GR_FAMILY_ABSENT) for f in frame.qc_flags)
    assert frame.curve("GRD_api") is None


def test_two_wells_sharing_canonical_gr_name_stay_distinct():
    """Two wells whose contracts both canonicalize to GR_api remain
    separate frames with separate provenance - never merged."""
    md = np.arange(5, dtype=float) * 50.0 + 50.0
    a = _synthetic_las({"MD_m": md, "GR_api": np.full(5, 30.0)},
                       well_name="A_1", source_filename="A_1_logs.las")
    b = _synthetic_las({"MD_m": md, "GR_api": np.full(5, 90.0)},
                       well_name="B_1", source_filename="B_1_logs.las")
    frames, failures = assemble_well_frames(
        {"A_1": a, "B_1": b},
        {"A_1": _synthetic_survey("A_1"), "B_1": _synthetic_survey("B_1")},
        las_paths={"A_1": "/s/A_1_logs.las", "B_1": "/s/B_1_logs.las"},
        survey_paths={"A_1": "/s/A_1_dev.txt", "B_1": "/s/B_1_dev.txt"},
        gr_family_by_well={"A_1": "GR_api", "B_1": "GR_api"},
    )
    assert not failures
    assert frames["A_1"].curve("GR_api").source_filename == "A_1_logs.las"
    assert frames["B_1"].curve("GR_api").source_filename == "B_1_logs.las"
    assert frames["A_1"].curve("GR_api").values[0] != frames["B_1"].curve("GR_api").values[0]


# ---------------------------------------------------------------------------
# Batch failure isolation
# ---------------------------------------------------------------------------

def test_batch_failure_isolation_missing_survey():
    md = np.arange(5, dtype=float) * 50.0 + 50.0
    good = _synthetic_las({"MD_m": md, "GR_api": np.full(5, 30.0)}, well_name="G_1")
    bad = _synthetic_las({"MD_m": md, "GR_api": np.full(5, 30.0)}, well_name="B_1")
    frames, failures = assemble_well_frames(
        {"G_1": good, "B_1": bad},
        {"G_1": _synthetic_survey("G_1")},
        las_paths={"G_1": "/s/G.las", "B_1": "/s/B.las"},
        survey_paths={"G_1": "/s/G_dev.txt", "B_1": "/s/B_dev.txt"},
    )
    assert set(frames) == {"G_1"}
    assert set(failures) == {"B_1"}
    assert failures["B_1"].failure_origin == "survey"
    assert "never assembled against another well's trajectory" in failures["B_1"].message


def test_batch_failure_isolation_missing_las():
    frames, failures = assemble_well_frames(
        {}, {"X_1": _synthetic_survey("X_1")},
        las_paths={}, survey_paths={"X_1": "/s/X_dev.txt"},
    )
    assert frames == {}
    assert failures["X_1"].failure_origin == "las"


def test_batch_failure_isolation_bad_curve_length():
    md = np.arange(5, dtype=float) * 50.0 + 50.0
    good = _synthetic_las({"MD_m": md, "GR_api": np.full(5, 30.0)}, well_name="G_1")
    bad = _synthetic_las({"MD_m": md, "GR_api": np.full(3, 30.0)}, well_name="B_1")
    frames, failures = assemble_well_frames(
        {"G_1": good, "B_1": bad},
        {"G_1": _synthetic_survey("G_1"), "B_1": _synthetic_survey("B_1")},
        las_paths={"G_1": "/s/G.las", "B_1": "/s/B.las"},
        survey_paths={"G_1": "/s/G_dev.txt", "B_1": "/s/B_dev.txt"},
    )
    assert set(frames) == {"G_1"}
    assert failures["B_1"].failure_origin == "curve_assembly"
    assert "B_1" not in frames


def test_batch_results_are_deterministically_ordered():
    md = np.arange(5, dtype=float) * 50.0 + 50.0
    las = {k: _synthetic_las({"MD_m": md, "GR_api": np.full(5, 30.0)}, well_name=k)
           for k in ("Z_1", "A_1", "M_1")}
    dev = {k: _synthetic_survey(k) for k in ("Z_1", "A_1", "M_1")}
    frames, _ = assemble_well_frames(
        las, dev,
        las_paths={k: f"/s/{k}.las" for k in las},
        survey_paths={k: f"/s/{k}_dev.txt" for k in las},
    )
    assert list(frames) == ["A_1", "M_1", "Z_1"]


# ---------------------------------------------------------------------------
# Prohibited named-lithology vocabulary guard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad", ["shale", "SAND", "probable-sandstone", "carbonate_zone", "net pay",
            "limestone", "MARL", "reservoir rock"],
)
def test_lithology_vocabulary_guard_rejects_rock_names(bad):
    with pytest.raises(ValueError, match="prohibited named-lithology term"):
        assert_no_lithology_vocabulary(bad, "test")


@pytest.mark.parametrize(
    "ok", ["GR_PROXY_HIGH", "GR_PROXY_INTERMEDIATE", "GR_PROXY_LOW",
           "GR_NOT_AVAILABLE", "GR_EXCLUDED_UNRESOLVED_SCALE",
           "VSH_GR_linear_proxy_frac", "eligible_sonic_nct_candidate",
           "a thousand samples"],
)
def test_lithology_vocabulary_guard_accepts_confidence_and_proxy_names(ok):
    assert_no_lithology_vocabulary(ok, "test")


def test_lithology_guard_rejects_non_string():
    with pytest.raises(TypeError):
        assert_no_lithology_vocabulary(123, "test")


def test_prohibited_vocabulary_covers_the_specified_rock_names():
    """Every rock name the Increment 6 specification names as prohibited is
    actually in the enforced vocabulary."""
    for required in ("shale", "sand", "sandstone", "carbonate", "limestone", "marl"):
        assert required in PROHIBITED_LITHOLOGY_TERMS
