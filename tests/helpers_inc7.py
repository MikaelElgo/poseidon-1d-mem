"""
Shared Increment 7 test helpers: the loaded configuration and the ONE
mask/gap/stats/profile/eligibility pipeline the production workflow uses.

`prepared` deliberately calls the SAME sequence as
`p2mem.io.overburden_workflow.run_overburden_workflow`. A test helper that
assembled the pieces in a different order would let the tests pass while the
production path did something else.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from p2mem.density_qc import (
    build_density_masks, compute_density_qc_stats, condition_density_gaps,
    load_overburden_config,
)
from p2mem.overburden import build_stress_profile, derive_overburden_eligibility

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = str(PROJECT_ROOT / "config" / "overburden_stress.yml")


@pytest.fixture(scope="session")
def overburden_config():
    """The real, packaged Increment 7 configuration.

    Session-scoped and frozen: the tests exercise the SHIPPED policy, not a
    convenient one invented for testing.
    """
    return load_overburden_config(CONFIG_PATH)


def prepared(frame, config, *, seabed_mdrt_m=None, seabed_tvd_m=None,
             seabed_tvdss_m=None, threshold_tvd_m=None):
    """Run the production pipeline for one frame and return every stage."""
    provisional = build_density_masks(frame, config, seabed_mdrt_m=seabed_mdrt_m)
    gaps = condition_density_gaps(
        frame, provisional, config, seabed_tvd_m=seabed_tvd_m,
        threshold_tvd_m=threshold_tvd_m)
    masks = build_density_masks(
        frame, config, seabed_mdrt_m=seabed_mdrt_m, gap_result=gaps)
    stats = compute_density_qc_stats(
        frame, masks, config, seabed_mdrt_m=seabed_mdrt_m,
        seabed_tvd_m=seabed_tvd_m, seabed_tvdss_m=seabed_tvdss_m,
        gaps=gaps.gaps)
    profile = build_stress_profile(frame, masks, gaps, config)
    eligibility = derive_overburden_eligibility(stats, masks, gaps, profile, config)
    return {
        "masks": masks, "gaps": gaps, "stats": stats,
        "profile": profile, "eligibility": eligibility,
    }
