"""
Shared SYNTHETIC builders for the Increment 6 test modules.

Everything here is fictional and generated in memory. No real or private
project LAS, deviation, checkshot, or formation-top file is read,
referenced, copied, or packaged by this module or by any test that uses
it.

These builders construct the LOCKED prior increments' REAL dataclasses
(rather than mocks) so the Increment 6 tests stay honest about the actual
shapes those locked layers produce - a field renamed in a locked model
would break these builders loudly instead of letting a mock drift
silently out of step with reality.

`PROJECT_ROOT` is resolved from this file's own location so that every
test is independent of the process working directory.
"""

from pathlib import Path

import numpy as np

from p2mem.deviation_models import (
    DEPTH_BASIS_PETREL_SOURCE,
    DepthBasisSelection,
    DeviationHeaderInfo,
    DeviationStationData,
    DeviationWellResult,
)
from p2mem.models import CurveStats, FileContract, LasFileResult, LasHeaderInfo

__all__ = ["PROJECT_ROOT", "synthetic_survey", "synthetic_las"]

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def synthetic_survey(
    well_key="Synth_1",
    md=(0.0, 100.0, 200.0, 300.0, 400.0),
    tvd=(0.0, 100.0, 199.0, 297.0, 394.0),
    datum_elevation_m=25.0,
):
    """A minimal, fictional `DeviationWellResult` on the Petrel-source basis.

    Only the fields the depth layer and the well-frame layer actually read
    are meaningfully populated; the rest carry inert placeholders.
    """
    md = np.asarray(md, dtype=float)
    tvd = np.asarray(tvd, dtype=float)
    z = np.zeros(md.size)
    raw = DeviationStationData(
        MD_source_m=md,
        X_source_m=z.copy(),
        Y_source_m=z.copy(),
        Z_source_m=datum_elevation_m - tvd,
        TVD_source_m=tvd,
        DX_source_m=z.copy(),
        DY_source_m=z.copy(),
        AZIM_TN_source_deg=z.copy(),
        INCL_source_deg=z.copy(),
        DLS_source_deg_per_30m=z.copy(),
        AZIM_GN_source_deg=z.copy(),
    )
    header = DeviationHeaderInfo(
        source_path=f"/synthetic/{well_key}_dev.txt",
        source_filename=f"{well_key}_dev.txt",
        sha256="0" * 64,
        well_name=well_key,
        survey_name="synthetic",
        wellhead_x_m=0.0,
        wellhead_y_m=0.0,
        datum_elevation_m=datum_elevation_m,
        datum_reference="synthetic RT",
        well_type="synthetic",
        coordinate_reference_system="synthetic",
        depth_reference_statement="synthetic",
        angle_unit_statement="degrees",
        dx_dy_statement="synthetic",
        z_statement="synthetic",
        column_names=("MD", "X", "Y", "Z", "TVD", "DX", "DY", "AZIM_TN", "INCL", "DLS", "AZIM_GN"),
        header_line_count=0,
        data_line_offset=0,
    )
    basis = DepthBasisSelection(
        well_key=well_key,
        selected_basis=DEPTH_BASIS_PETREL_SOURCE,
        rationale="synthetic test fixture",
    )
    return DeviationWellResult(
        header=header, contract=None, raw=raw, mc=None,
        validation=None, depth_basis=basis, issues=(), contract_status="PASSED",
    )


def synthetic_las(canonical, well_name="Synth_1", source_filename="Synth_1_logs.las"):
    """A minimal, fictional `LasFileResult` carrying only what the
    well-frame layer reads: `canonical_data`, `curve_stats`, `contract`."""
    stats = tuple(
        CurveStats(
            source_curve_name=name.split("_")[0],
            raw_mnemonic=name.split("_")[0],
            raw_description=f"synthetic {name}",
            raw_unit="API" if ("GR" in name or "ECGR" in name) else "SYN",
            canonical_name=name,
            canonical_unit="API" if ("GR" in name or "ECGR" in name) else "SYN",
            conversion_function="identity",
            n_samples=int(np.asarray(arr).size),
            valid_count=int(np.count_nonzero(np.isfinite(arr))),
            null_count=int(np.count_nonzero(~np.isfinite(arr))),
            valid_fraction=float(np.count_nonzero(np.isfinite(arr)) / np.asarray(arr).size),
            raw_min=None, raw_max=None, canonical_min=None, canonical_max=None,
            statistics_basis="synthetic",
        )
        for name, arr in canonical.items()
    )
    header = LasHeaderInfo(
        source_path=f"/synthetic/{source_filename}",
        source_filename=source_filename,
        sha256="0" * 64,
        las_version="2.0",
        wrap="NO",
        well_name=well_name,
        declared_null=-999.25,
        declared_strt=None,
        declared_stop=None,
        declared_step=None,
        version_section=(),
        well_section=(),
        parameter_section=(),
        curve_headers=(),
        data_section_line_offset=0,
    )
    contract = FileContract(
        source_filename=source_filename, expected_sha256="0" * 64,
        expected_well_identifier=well_name, expected_las_version="2.0",
        expected_wrap="NO", expected_null_value=-999.25,
        expected_curve_count=len(canonical), expected_data_layout="ascii", curves=(),
    )
    return LasFileResult(
        header=header, contract=contract, resolutions=(), depth=None,
        curve_stats=stats, raw_data=np.zeros((1, 1)),
        canonical_data=dict(canonical), issues=(), contract_status="PASSED",
    )
