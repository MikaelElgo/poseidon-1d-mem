"""Conditional static/strength experiments, never a field calibration.

The field branch remains unavailable in this release. Numerical predictor
support is not evidence of lithology or transferable calibration.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from types import MappingProxyType
import json
import math
import numpy as np


class MechanicsInputError(ValueError):
    """A mechanics contract is violated."""


STATIC_METHOD = 'mahdi_alrazzaq_2024_eq8'
STRENGTH_METHOD = 'chang_2006_table1_eq8'
SOURCE_EDYN_RANGE = (17.90, 43.45)  # GPa; reported predictor span, not a field validity claim.
PROPERTIES = ('E_static_scenario_GPa', 'nu_static_assumed', 'G_static_scenario_GPa',
              'K_static_scenario_GPa', 'UCS_scenario_MPa', 'phi_assumed_deg',
              'mu_derived', 'cohesion_scenario_MPa', 'T0_assumed_MPa')
STATUS = ('upstream_dynamic_unavailable', 'outside_source_predictor_span',
          'conditional_analogue_only')


def require(ok, message):
    if not ok:
        raise MechanicsInputError(message)


def real(value, name, lower, upper, *, open_lower=False, open_upper=False):
    require(not isinstance(value, (bool, np.bool_)) and isinstance(value, (int, float)),
            name + ' must be a finite real scalar')
    require(math.isfinite(value), name + ' must be finite')
    require((value > lower if open_lower else value >= lower) and
            (value < upper if open_upper else value <= upper), name + ' is outside its domain')
    return float(value)


@dataclass(frozen=True)
class MechanicsCase:
    case_id: str
    nu_static: float
    phi_deg: float
    tensile_ratio: float

    def __post_init__(self):
        import re
        require(isinstance(self.case_id, str) and re.fullmatch('[a-z][a-z0-9_]{0,47}', self.case_id),
                'Invalid case_id')
        real(self.nu_static, 'nu_static', -1, .5, open_lower=True, open_upper=True)
        real(self.phi_deg, 'phi_deg', 0, 89, open_upper=True)
        real(self.tensile_ratio, 'tensile_ratio', 0, 1)
        q = (1 + math.sin(math.radians(self.phi_deg))) / (1 - math.sin(math.radians(self.phi_deg)))
        # A tensile cutoff above the MC uniaxial tensile intercept would be
        # inactive/inconsistent with the stated cutoff interpretation.
        require(self.tensile_ratio <= 1 / q, 'Tensile cutoff exceeds the MC tensile intercept')


DEFAULT_CASES = (
    MechanicsCase('reference_experiment', .25, 30., .05),
    MechanicsCase('nu_020', .20, 30., .05),
    MechanicsCase('nu_030', .30, 30., .05),
    MechanicsCase('phi_020', .25, 20., .05),
    MechanicsCase('phi_040', .25, 40., .05),
    MechanicsCase('tensile_zero', .25, 30., 0.),
    MechanicsCase('tensile_010', .25, 30., .10),
)


def default_config():
    return {'schema_version': '10.0.0', 'mode': 'conditional_analogue_only',
            'static_method': STATIC_METHOD, 'strength_method': STRENGTH_METHOD,
            'material_hypothesis': 'sandstone_analogue_not_interpreted_lithology',
            'cases': [asdict(c) for c in DEFAULT_CASES]}


def unique_object(pairs):
    out = {}
    for k, v in pairs:
        require(k not in out, 'Duplicate JSON key: ' + k)
        out[k] = v
    return out


def load_config(path):
    try:
        obj = json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique_object,
                         parse_constant=lambda x: (_ for _ in ()).throw(MechanicsInputError('Nonfinite JSON')))
    except (OSError, json.JSONDecodeError) as exc:
        raise MechanicsInputError('Cannot read mechanics config') from exc
    default = default_config()
    require(isinstance(obj, dict) and set(obj) == set(default), 'Config schema mismatch')
    require(all(obj[k] == default[k] for k in default if k != 'cases'), 'Unsupported mechanics mode/method')
    require(isinstance(obj['cases'], list) and 1 <= len(obj['cases']) <= 64, 'Invalid scenario inventory')
    cases = []
    for row in obj['cases']:
        require(isinstance(row, dict) and set(row) == set(asdict(DEFAULT_CASES[0])), 'Case schema mismatch')
        cases.append(MechanicsCase(**row))
    require(len({c.case_id for c in cases}) == len(cases), 'Duplicate case_id')
    require(cases[0].case_id == 'reference_experiment', 'First case must be reference_experiment')
    return obj, tuple(cases)


def _array(value, name):
    a = np.asarray(value)
    require(a.ndim == 1 and a.dtype.kind in 'iuf', name + ' must be a real 1-D array')
    return a.astype(float, copy=True)


def analogue_static_modulus(edyn_gpa):
    """Return a hypothetical transfer of Eq. 8, restricted to source Edyn span.

    Mahdi & Alrazzaq (2024): E_static[GPa] = 0.3655 E_dynamic[GPa]^1.0959.
    Returning a value never certifies a Poseidon material match.
    """
    e = _array(edyn_gpa, 'E_dynamic_GPa')
    mask = np.isfinite(e) & (e >= SOURCE_EDYN_RANGE[0]) & (e <= SOURCE_EDYN_RANGE[1])
    out = np.full(e.shape, np.nan)
    out[mask] = .3655 * e[mask] ** 1.0959
    return out


def analogue_strength(estatic_gpa):
    """Chang et al. (2006), Table 1 Eq. 8, as a hypothetical sandstone law.

    No region/original calibration is identified for this equation in that
    table. This limitation is mandatory in the registry and field gate.
    """
    e = _array(estatic_gpa, 'E_static_GPa')
    # Supported only on the output span of the selected static experiment.
    lower, upper = .3655 * np.asarray(SOURCE_EDYN_RANGE) ** 1.0959
    mask = np.isfinite(e) & (e >= lower) & (e <= upper)
    out = np.full(e.shape, np.nan)
    out[mask] = 46.2 * np.exp(.027 * e[mask])
    return out


def isotropic_moduli(e_gpa, nu):
    e = _array(e_gpa, 'E_GPa')
    nu = real(nu, 'nu', -1, .5, open_lower=True, open_upper=True)
    require(not np.any(np.isinf(e)) and not np.any(np.isfinite(e) & (e <= 0)), 'Invalid finite E')
    return e / (2 * (1 + nu)), e / (3 * (1 - 2 * nu))


def strength_parameters(ucs_mpa, phi_deg, tensile_ratio):
    u = _array(ucs_mpa, 'UCS_MPa')
    case = MechanicsCase('scalar_validation', .25, phi_deg, tensile_ratio)
    require(not np.any(np.isinf(u)) and not np.any(np.isfinite(u) & (u <= 0)), 'Invalid finite UCS')
    radians = math.radians(case.phi_deg)
    return (u * (1 - math.sin(radians)) / (2 * math.cos(radians)),
            math.tan(radians), u * case.tensile_ratio)


def evaluate_mechanics(edyn_gpa, upstream_valid, case):
    require(isinstance(case, MechanicsCase), 'Expected MechanicsCase')
    e = _array(edyn_gpa, 'E_dynamic_GPa')
    valid = np.asarray(upstream_valid)
    require(valid.ndim == 1 and valid.dtype.kind == 'b' and valid.shape == e.shape,
            'upstream_valid must be a matching boolean array')
    require(not np.any(valid & (~np.isfinite(e) | (e <= 0))), 'Valid upstream E must be positive and finite')
    est = analogue_static_modulus(np.where(valid, e, np.nan))
    keep = np.isfinite(est)
    ucs = analogue_strength(est)
    g, k = isotropic_moduli(est, case.nu_static)
    cohesion, mu, t0 = strength_parameters(ucs, case.phi_deg, case.tensile_ratio)
    const = lambda x: np.where(keep, x, np.nan)
    status = np.full(e.shape, STATUS[0], dtype='<U32')
    status[valid] = STATUS[1]
    status[keep] = STATUS[2]
    result = dict(zip(PROPERTIES, (est, const(case.nu_static), g, k, ucs,
                                  const(case.phi_deg), const(mu), cohesion, t0)))
    result.update(upstream_dynamic_valid=valid.copy(), scenario_numeric_supported=keep,
                  field_mechanics_eligible=np.zeros(len(e), dtype=bool), status=status)
    for a in result.values():
        a.flags.writeable = False
    return MappingProxyType(result)
