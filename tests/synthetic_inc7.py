"""
Small, fictional, fully synthetic fixtures for the Increment 7 tests.

NOTHING here is derived from, or resembles, an approved project file. Every
array is hand-written so that the expected answer can be computed by hand and
compared against the implementation, which is the only way an analytical test
proves anything.

The well frames built here are real `p2mem.wellframe_models.WellFrame` /
`CurveSlot` objects, not stand-ins: a test that passes against a mock proves
nothing about the locked structure the production path actually receives.
"""

from __future__ import annotations

import numpy as np

from p2mem.wellframe_models import CurveSlot, WellFrame

__all__ = [
    "readonly", "make_curve", "make_frame", "constant_density_frame",
    "two_layer_frame", "gap_frame", "STANDARD_G",
]

#: The exact gravity every analytical expectation in these tests is computed
#: with. Kept here so that a change to the configured value cannot silently
#: move an "analytical" expectation with it.
STANDARD_G = 9.80665


def readonly(arr):
    view = np.asarray(arr).view()
    view.setflags(write=False)
    return view


def make_curve(values, *, canonical_name="RHOB_kg_m3", canonical_unit="kg/m3",
               conversion_function="gcc_to_kgm3", source_curve_name="RHOB",
               raw_mnemonic="RHOB", raw_unit="g/cc",
               source_filename="synthetic.las"):
    values = np.asarray(values, dtype=np.float64)
    valid = np.isfinite(values)
    return CurveSlot(
        canonical_name=canonical_name,
        source_curve_name=source_curve_name,
        raw_mnemonic=raw_mnemonic,
        raw_unit=raw_unit,
        canonical_unit=canonical_unit,
        conversion_function=conversion_function,
        source_filename=source_filename,
        evidence_class="measured",
        values=readonly(values),
        valid_mask=readonly(valid),
        n_samples=int(values.size),
        valid_count=int(np.count_nonzero(valid)),
        valid_fraction=(float(np.count_nonzero(valid)) / values.size
                        if values.size else 0.0),
    )


def make_frame(*, well_key="SYNTH_1", md, tvd=None, tvdss=None, density=None,
               datum_elevation_m=25.0, depth_valid_mask=None,
               survey_md_min_m=None, survey_md_max_m=None,
               depth_map_status="fully_mapped_within_survey_coverage",
               curves=None, extra_curves=None):
    """Build one synthetic `WellFrame`.

    `tvd` defaults to `md` (a vertical well). `tvdss` is always derived as
    `tvd - datum_elevation_m`, matching the project convention exactly, so a
    test that wants to violate the convention must say so explicitly by
    passing `tvdss`.
    """
    md = np.asarray(md, dtype=np.float64)
    tvd = md.copy() if tvd is None else np.asarray(tvd, dtype=np.float64)
    tvdss = (tvd - datum_elevation_m) if tvdss is None else np.asarray(
        tvdss, dtype=np.float64)
    n = int(md.size)
    if depth_valid_mask is None:
        depth_valid_mask = np.isfinite(tvd) & np.isfinite(tvdss)
    depth_valid_mask = np.asarray(depth_valid_mask, dtype=bool)

    slots = {}
    if curves is None and density is not None:
        slots["RHOB_kg_m3"] = make_curve(density)
    elif curves is not None:
        slots.update(curves)
    if extra_curves:
        slots.update(extra_curves)

    finite_md = md[np.isfinite(md)]
    return WellFrame(
        well_key=well_key,
        source_las_filename="synthetic.las",
        source_survey_filename="synthetic_dev.txt",
        n_samples=n,
        MD_m=readonly(md),
        TVD_m=readonly(tvd),
        TVDSS_m=readonly(tvdss),
        depth_valid_mask=readonly(depth_valid_mask),
        depth_basis_used="petrel_source_trace",
        interpolation_method="piecewise_linear_station_interpolation",
        datum_elevation_m=float(datum_elevation_m),
        depth_map_status=depth_map_status,
        survey_md_min_m=(float(np.min(finite_md)) if survey_md_min_m is None
                         else float(survey_md_min_m)),
        survey_md_max_m=(float(np.max(finite_md)) if survey_md_max_m is None
                         else float(survey_md_max_m)),
        las_md_min_m=float(np.min(finite_md)) if finite_md.size else 0.0,
        las_md_max_m=float(np.max(finite_md)) if finite_md.size else 0.0,
        n_depth_unmapped=int(n - np.count_nonzero(depth_valid_mask)),
        n_extrapolated=0,
        curves=slots,
    )


def constant_density_frame(rho=2000.0, n=11, step=10.0, top=1000.0,
                           datum_elevation_m=25.0, **kw):
    """A vertical well with CONSTANT density over a uniform depth grid.

    Analytical expectation: sigma_v increment over the whole column is
    `rho * g * (n - 1) * step`, exactly, because trapezoidal quadrature is
    exact for a constant integrand.
    """
    md = top + step * np.arange(n, dtype=np.float64)
    return make_frame(md=md, density=np.full(n, float(rho)),
                      datum_elevation_m=datum_elevation_m, **kw)


def two_layer_frame(rho_upper=2000.0, rho_lower=2500.0, n_upper=6, n_lower=6,
                    step=10.0, top=1000.0, datum_elevation_m=25.0, **kw):
    """Two constant-density layers meeting at one shared node.

    Analytical expectation: the total increment is the sum of the two layers'
    `rho * g * h`, because each layer is a constant integrand and the shared
    node contributes no interval of its own.
    """
    n = n_upper + n_lower - 1
    md = top + step * np.arange(n, dtype=np.float64)
    rho = np.concatenate([
        np.full(n_upper, float(rho_upper)),
        np.full(n_lower - 1, float(rho_lower)),
    ])
    return make_frame(md=md, density=rho, datum_elevation_m=datum_elevation_m, **kw)


def gap_frame(gap_slices, rho=2000.0, n=41, step=1.0, top=1000.0,
              datum_elevation_m=25.0, **kw):
    """A constant-density well with NaN density over the given index slices."""
    md = top + step * np.arange(n, dtype=np.float64)
    density = np.full(n, float(rho))
    for sl in gap_slices:
        density[sl] = np.nan
    return make_frame(md=md, density=density,
                      datum_elevation_m=datum_elevation_m, **kw)
