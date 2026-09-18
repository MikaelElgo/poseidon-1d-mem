"""
p2mem.io.overburden_workflow - the ONE Increment 7 real-data workflow.

Exists so that the notebook, the completion gate, the determinism check and
the integration tests all execute the SAME code path. A workflow that the
notebook re-implements inline is a workflow whose tests prove nothing about
the notebook.

This module reads approved input FILES through the LOCKED loaders and the
LOCKED Increment 5 marker table. It contains no science of its own: every
number it returns comes from `p2mem.density_qc` or `p2mem.overburden`.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import math
import os
from typing import Dict

from p2mem.density_qc import (
    build_density_masks, compute_density_qc_stats, condition_density_gaps,
)
from p2mem.overburden import (
    build_gap_threshold_sensitivity, build_shallow_column_scenarios,
    build_stress_profile, derive_overburden_eligibility, verify_depth_sign_convention,
)
from p2mem.overburden_models import OverburdenConfig, OverburdenInputError

__all__ = [
    "LOCKED_MARKER_TABLE", "SeabedMarker", "SeabedMarkerError",
    "read_locked_seabed_markers",
    "OverburdenRun", "run_overburden_workflow", "build_overburden_payloads",
]

LOCKED_MARKER_TABLE = os.path.join(
    "outputs", "05_formation_tops", "top_survey_corrected_markers.csv")


class SeabedMarkerError(OverburdenInputError):
    """The locked seabed table is missing, malformed, ambiguous or non-finite."""


@dataclass(frozen=True)
class SeabedMarker:
    """One well's seabed datum, read from the LOCKED Increment 5 output only."""

    well_key: str
    mdrt_m: float
    tvd_m: float
    tvdss_m: float

    def __post_init__(self) -> None:
        if not isinstance(self.well_key, str) or not self.well_key.strip():
            raise SeabedMarkerError("SeabedMarker: well_key must be a non-empty string.")
        for name in ("mdrt_m", "tvd_m", "tvdss_m"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise SeabedMarkerError(
                    f"SeabedMarker {self.well_key!r}: {name} must be a finite real number.")
            if not math.isfinite(float(value)) or float(value) < 0.0:
                raise SeabedMarkerError(
                    f"SeabedMarker {self.well_key!r}: {name} must be finite and >= 0, "
                    f"got {value!r}.")


def read_locked_seabed_markers(
    marker_table_path: str, marker_name: str
) -> Dict[str, SeabedMarker]:
    """Read the seabed marker for each well from the LOCKED Increment 5 table.

    A well absent from that table has NO seabed datum in this project. It is
    omitted from the returned mapping - never defaulted to zero, never
    inferred from the log start, and never borrowed from another well.
    """
    if not isinstance(marker_name, str) or not marker_name.strip():
        raise SeabedMarkerError("marker_name must be a non-empty string.")
    if not os.path.isfile(marker_table_path):
        raise SeabedMarkerError(
            f"Locked seabed marker table is missing or not a file: "
            f"{os.path.basename(str(marker_table_path))!r}.")
    out: Dict[str, SeabedMarker] = {}
    wanted = marker_name.strip().lower()
    with open(marker_table_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        required = (
            "well_key", "canonical_marker_name", "MDRT_reconciled_m",
            "TVD_survey_m", "TVDSS_survey_corrected_m",
        )
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)):
            raise SeabedMarkerError("Locked seabed marker table has duplicate columns.")
        missing = [name for name in required if name not in fields]
        if missing:
            raise SeabedMarkerError(
                f"Locked seabed marker table is missing required column(s): {missing}.")
        for row_number, row in enumerate(reader, start=2):
            if row.get("canonical_marker_name", "").strip().lower() != wanted:
                continue
            try:
                well_key = row["well_key"].strip()
                marker = SeabedMarker(
                    well_key=well_key,
                    mdrt_m=float(row["MDRT_reconciled_m"]),
                    tvd_m=float(row["TVD_survey_m"]),
                    tvdss_m=float(row["TVDSS_survey_corrected_m"]),
                )
            except (KeyError, AttributeError, TypeError, ValueError,
                    SeabedMarkerError) as exc:
                raise SeabedMarkerError(
                    f"Locked seabed marker row {row_number} is malformed for the "
                    f"requested marker {marker_name!r}.") from exc
            if well_key in out:
                raise SeabedMarkerError(
                    f"Locked seabed marker table contains duplicate {marker_name!r} "
                    f"rows for well {well_key!r}.")
            out[well_key] = marker
    return out


class OverburdenRun:
    """Everything one Increment 7 run produced, per well and in aggregate."""

    __slots__ = ("config", "frames", "seabed", "sign_convention", "masks", "gaps",
                 "gap_results", "stats", "profiles", "eligibility", "scenarios",
                 "sensitivity", "issues")

    def __init__(self, **kw):
        for slot in self.__slots__:
            setattr(self, slot, kw.get(slot))

    @property
    def depth_convention_verified(self) -> bool:
        return bool(self.sign_convention) and all(
            ev.get("verified") is True for ev in self.sign_convention.values())


def run_overburden_workflow(
    frames: Dict[str, object],
    config: OverburdenConfig,
    *,
    marker_table_path: str = LOCKED_MARKER_TABLE,
) -> OverburdenRun:
    """Execute the complete Increment 7 workflow for a set of well frames.

    Deterministic: wells are processed in sorted key order, and every result
    is a function of the frames, the configuration, and the locked marker
    table.
    """
    seabed = read_locked_seabed_markers(marker_table_path, config.seabed_marker_name)

    sign_convention: Dict[str, dict] = {}
    masks: Dict[str, object] = {}
    gap_results: Dict[str, object] = {}
    gaps: Dict[str, tuple] = {}
    stats: Dict[str, object] = {}
    profiles: Dict[str, object] = {}
    eligibility: Dict[str, object] = {}
    scenarios: Dict[str, tuple] = {}
    sensitivity: Dict[str, tuple] = {}

    for wk in sorted(frames):
        frame = frames[wk]
        sign_convention[wk] = verify_depth_sign_convention(frame)
        marker = seabed.get(wk)
        mdrt = None if marker is None else marker.mdrt_m
        tvd = None if marker is None else marker.tvd_m
        tvdss = None if marker is None else marker.tvdss_m

        # Two passes, and the order matters. The masks that feed gap
        # classification cannot themselves depend on the gap result, so the
        # first pass builds the eligibility mask, the gap pass consumes it,
        # and the second pass folds the resulting unresolved-region masks back
        # in. The eligibility mask is identical in both passes: gap
        # conditioning never adds or removes an ELIGIBLE MEASURED sample.
        provisional = build_density_masks(frame, config, seabed_mdrt_m=mdrt)
        gap_result = condition_density_gaps(
            frame, provisional, config, seabed_tvd_m=tvd)
        final_masks = build_density_masks(
            frame, config, seabed_mdrt_m=mdrt, gap_result=gap_result)

        well_stats = compute_density_qc_stats(
            frame, final_masks, config, seabed_mdrt_m=mdrt, seabed_tvd_m=tvd,
            seabed_tvdss_m=tvdss, gaps=gap_result.gaps)
        profile = build_stress_profile(frame, final_masks, gap_result, config)
        elig = derive_overburden_eligibility(
            well_stats, final_masks, gap_result, profile, config)

        masks[wk] = final_masks
        gap_results[wk] = gap_result
        gaps[wk] = gap_result.gaps
        stats[wk] = well_stats
        profiles[wk] = profile
        eligibility[wk] = elig
        scenarios[wk] = build_shallow_column_scenarios(
            well_stats, elig, profile, config)
        sensitivity[wk] = build_gap_threshold_sensitivity(
            frame, final_masks, well_stats, config, seabed_tvd_m=tvd)

    from p2mem.io.overburden_inventory import derive_overburden_issues
    issues = derive_overburden_issues(
        stats, eligibility, gap_results, profiles, config)

    return OverburdenRun(
        config=config, frames=frames, seabed=seabed, sign_convention=sign_convention,
        masks=masks, gaps=gaps, gap_results=gap_results, stats=stats,
        profiles=profiles, eligibility=eligibility, scenarios=scenarios,
        sensitivity=sensitivity, issues=issues)


def build_overburden_payloads(run: OverburdenRun) -> Dict[str, list]:
    """Build the complete, ordered Increment 7 payload set for export.

    The manifest is built LAST, from the CSV payloads this function has
    already produced, so its coverage block describes the records that are
    actually serialized rather than a reconstruction of them.
    """
    from p2mem.io.overburden_inventory import (
        build_density_availability_rows, build_density_gap_rows, build_density_qc_rows,
        build_gap_threshold_sensitivity_rows, build_overburden_eligibility_rows,
        build_overburden_issue_rows, build_overburden_manifest,
        build_shallow_column_scenario_rows, build_vertical_stress_profile_rows,
    )
    from p2mem.io.overburden_registry import (
        AVAILABILITY, ELIGIBILITY, GAPS, ISSUES, OVERBURDEN_MANIFEST_ARTIFACT,
        PROFILE, QC, SCENARIOS, SENSITIVITY,
    )

    payloads: Dict[str, list] = {
        AVAILABILITY: build_density_availability_rows(run.stats, run.frames),
        QC: build_density_qc_rows(run.stats, run.masks, run.config),
        GAPS: build_density_gap_rows(run.gaps),
        ELIGIBILITY: build_overburden_eligibility_rows(
            run.eligibility, run.profiles, run.config),
        PROFILE: build_vertical_stress_profile_rows(run.profiles, run.config),
        SCENARIOS: build_shallow_column_scenario_rows(run.scenarios),
        SENSITIVITY: build_gap_threshold_sensitivity_rows(run.sensitivity),
        ISSUES: build_overburden_issue_rows(run.issues),
    }
    manifest = build_overburden_manifest(
        run.stats, run.eligibility, run.gap_results, run.profiles, run.scenarios,
        run.sensitivity, run.issues, run.frames, run.config,
        depth_convention_verified=run.depth_convention_verified,
        output_payloads=payloads)
    payloads[OVERBURDEN_MANIFEST_ARTIFACT] = manifest
    return payloads
