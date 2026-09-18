"""Dynamic isotropic estimates from co-located, contract-converted log samples.

No interpolation, static conversion, lithology assignment or strength model.
The primary ratio-dependent estimates retain the Increment 6 nonnegative-nu
screen. Stable negative nu is exposed only as a diagnostic, never described
as an impossible material. Shear modulus needs Vs and density, not Vp.
All array positions are preserved; invalid estimates are NaN.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from types import MappingProxyType

import numpy as np


class ElasticInputError(ValueError):
    """An elastic input violates its structural or policy contract."""


@dataclass(frozen=True)
class ElasticPolicy:
    """Reviewable screening bounds, not calibration or physical rock limits."""
    vp_min_m_s: float = 1000.0
    vp_max_m_s: float = 8000.0
    vs_min_m_s: float = 300.0
    vs_max_m_s: float = 5000.0
    rhob_min_kg_m3: float = 1000.0
    rhob_max_kg_m3: float = 3500.0
    ratio_max: float = 4.0

    def __post_init__(self):
        for name, value in asdict(self).items():
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float)):
                raise ElasticInputError(f'{name} must be a finite real number')
            if not math.isfinite(value) or value <= 0:
                raise ElasticInputError(f'{name} must be finite and positive')
        for curve in ('vp', 'vs', 'rhob'):
            unit = 'kg_m3' if curve == 'rhob' else 'm_s'
            if getattr(self, f'{curve}_min_{unit}') >= getattr(self, f'{curve}_max_{unit}'):
                raise ElasticInputError(f'{curve}: minimum must be below maximum')
        if self.ratio_max < math.sqrt(2):
            raise ElasticInputError('ratio_max must admit the nonnegative-nu boundary')


POSITIVE_BULK_BOUND = math.sqrt(4.0 / 3.0)
NONNEGATIVE_NU_BOUND = math.sqrt(2.0)
REGIMES = ('missing_velocity', 'velocity_out_of_bounds', 'nonpositive_bulk_ratio',
           'negative_poisson_ratio', 'ratio_above_policy', 'passes_ratio_screen')
PROPERTIES = ('nu_dynamic', 'G_dynamic_GPa', 'K_dynamic_GPa', 'E_dynamic_GPa')


def _unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ElasticInputError(f'Duplicate JSON key: {key}')
        out[key] = value
    return out


def load_elastic_policy(path):
    """Load exactly the versioned policy; reject unknown/duplicate keys."""
    try:
        obj = json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
        if not isinstance(obj, dict) or set(obj) != {'schema_version', 'bounds'}:
            raise ElasticInputError('Expected schema_version and bounds only')
        if obj['schema_version'] != '9.0.0':
            raise ElasticInputError('Unsupported elasticity policy version')
        if not isinstance(obj['bounds'], dict) or set(obj['bounds']) != set(asdict(ElasticPolicy())):
            raise ElasticInputError('Missing or unknown elasticity bound')
        return ElasticPolicy(**obj['bounds'])
    except (OSError, TypeError, json.JSONDecodeError) as exc:
        raise ElasticInputError('Cannot read valid elasticity policy') from exc


def _array(value, name, n):
    if value is None:
        return np.full(n, np.nan)
    try:
        arr = np.asarray(value)
        if arr.ndim != 1 or len(arr) != n or arr.dtype.kind not in 'iuf':
            raise ElasticInputError(f'{name} must be a real numeric 1-D array of length {n}')
        return arr.astype(np.float64, copy=True)
    except (TypeError, OverflowError) as exc:
        raise ElasticInputError(f'Invalid {name}') from exc


def compute_dynamic_elasticity(vp_m_s, vs_m_s, rhob_kg_m3, depth_valid, *, policy=None):
    """Return read-only arrays of estimates and explicit per-sample QC states.

    SI inputs: m/s, kg/m3. Moduli exported in GPa (Pa / 1e9).
    depth_valid must be boolean, one element per original LAS sample.
    None curves and nonfinite samples denote unavailable measurements.
    Mathematical stability requires positive K and G; the stricter primary
    screen r >= sqrt(2) and r <= ratio_max is an inherited project choice.
    nu_stable_diagnostic is density independent and can be negative.
    """
    if policy is None:
        policy = ElasticPolicy()
    if not isinstance(policy, ElasticPolicy):
        raise ElasticInputError('policy must be ElasticPolicy')
    depth = np.asarray(depth_valid)
    if depth.ndim != 1 or depth.dtype.kind != 'b':
        raise ElasticInputError('depth_valid must be a 1-D boolean array')
    depth = depth.copy()
    n = len(depth)
    vp, vs, rho = (_array(v, k, n) for v, k in
                   ((vp_m_s, 'Vp'), (vs_m_s, 'Vs'), (rhob_kg_m3, 'RHOB')))
    finite_vp, finite_vs, finite_rho = map(np.isfinite, (vp, vs, rho))
    vp_ok = finite_vp & (vp >= policy.vp_min_m_s) & (vp <= policy.vp_max_m_s)
    vs_ok = finite_vs & (vs >= policy.vs_min_m_s) & (vs <= policy.vs_max_m_s)
    rho_ok = finite_rho & (rho >= policy.rhob_min_kg_m3) & (rho <= policy.rhob_max_kg_m3)
    both = vp_ok & vs_ok
    r = np.full(n, np.nan)
    np.divide(vp, vs, out=r, where=both)
    regime = np.full(n, 'missing_velocity', dtype='<U25')
    regime[finite_vp & finite_vs & ~both] = 'velocity_out_of_bounds'
    regime[both & (r <= POSITIVE_BULK_BOUND)] = 'nonpositive_bulk_ratio'
    regime[both & (r > POSITIVE_BULK_BOUND) & (r < NONNEGATIVE_NU_BOUND)] = 'negative_poisson_ratio'
    regime[both & (r > policy.ratio_max)] = 'ratio_above_policy'
    ratio_ok = both & (r >= NONNEGATIVE_NU_BOUND) & (r <= policy.ratio_max)
    regime[ratio_ok] = 'passes_ratio_screen'
    stable = both & (r > POSITIVE_BULK_BOUND) & (r <= policy.ratio_max) & depth
    nu_diag = np.full(n, np.nan)
    q = r[stable] ** 2
    nu_diag[stable] = (q - 2.0) / (2.0 * (q - 1.0))
    nu_ok = ratio_ok & depth
    g_ok = vs_ok & rho_ok & depth
    full_ok = nu_ok & rho_ok
    nu, g, k, e = (np.full(n, np.nan) for _ in range(4))
    nu[nu_ok] = nu_diag[nu_ok]
    g[g_ok] = rho[g_ok] * vs[g_ok] ** 2 / 1e9
    k[full_ok] = rho[full_ok] * (vp[full_ok] ** 2 - (4.0 / 3.0) * vs[full_ok] ** 2) / 1e9
    e[full_ok] = 9.0 * k[full_ok] * g[full_ok] / (3.0 * k[full_ok] + g[full_ok])
    # This is an algebraic conditioning diagnostic, not an uncertainty bound.
    condition = np.full(n, np.nan)
    q = r[nu_ok] ** 2
    condition[nu_ok] = (2.0 * q + 8.0 / 3.0) / (q - 4.0 / 3.0)
    result = dict(depth_valid=depth, vp_available=finite_vp, vs_available=finite_vs,
                  rhob_available=finite_rho, vp_in_bounds=vp_ok, vs_in_bounds=vs_ok,
                  rhob_in_bounds=rho_ok, vp_vs_ratio=r, ratio_regime=regime,
                  nu_stable_diagnostic=nu_diag, nu_dynamic=nu, G_dynamic_GPa=g,
                  K_dynamic_GPa=k, E_dynamic_GPa=e, nu_valid=nu_ok, G_valid=g_ok,
                  K_valid=full_ok.copy(), E_valid=full_ok.copy(),
                  legacy_full_eligible=full_ok.copy(),
                  K_velocity_condition_number=condition)
    for arr in result.values():
        arr.flags.writeable = False
    return MappingProxyType(result)
