"""Conditional isotropic stress experiments; MPa, compression positive.

Biot effective stress governs intact poroelastic deformation. Fault-friction
bounds use S-Pp (unit fault pressure coefficient), independently of Biot alpha.
No function establishes a measured stress, azimuth, or operational window.
"""
from dataclasses import dataclass, asdict
import json
import math
from numbers import Real


class StressInputError(ValueError):
    pass


def finite(name, value):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise StressInputError(name + ' must be finite numeric')
    return float(value)


@dataclass(frozen=True)
class StressCase:
    case_id: str = 'reference'
    mechanics_case: str = 'reference_experiment'
    nu: float = 0.25
    alpha: float = 1.0
    fluid_density_kg_m3: float = 1025.0
    fault_mu: float = 0.6
    epsilon_x: float = 0.0
    epsilon_y: float = 0.0

    def __post_init__(self):
        if not isinstance(self.case_id, str) or not self.case_id or not all(c.isalnum() or c=='_' for c in self.case_id):
            raise StressInputError('Invalid case_id')
        if not isinstance(self.mechanics_case, str) or not self.mechanics_case:
            raise StressInputError('Invalid mechanics_case')
        for key in ('nu','alpha','fluid_density_kg_m3','fault_mu','epsilon_x','epsilon_y'):
            finite(key,getattr(self,key))
        if not 0 < self.nu < 0.5: raise StressInputError('This experiment requires 0 < nu < 0.5')
        if not 0 <= self.alpha <= 1: raise StressInputError('alpha outside [0,1]')
        if self.fluid_density_kg_m3 <= 0 or self.fault_mu <= 0: raise StressInputError('density and friction must be positive')
        if max(abs(self.epsilon_x),abs(self.epsilon_y)) > 0.01: raise StressInputError('Strain exceeds small-strain experiment limit')


def default_config():
    anchor=asdict(StressCase())
    changes=[{}, {'case_id':'nu_020','nu':.20,'mechanics_case':'nu_020'},
        {'case_id':'nu_030','nu':.30,'mechanics_case':'nu_030'},
        {'case_id':'alpha_080','alpha':.8},
        {'case_id':'fluid_1020','fluid_density_kg_m3':1020.},
        {'case_id':'fluid_1030','fluid_density_kg_m3':1030.},
        {'case_id':'fault_mu_040','fault_mu':.4},
        {'case_id':'fault_mu_080','fault_mu':.8},
        {'case_id':'strain_x_0500','epsilon_x':.0005},
        {'case_id':'strain_equal_0500','epsilon_x':.0005,'epsilon_y':.0005},
        {'case_id':'strain_x_minus0500','epsilon_x':-.0005}]
    return {'schema_version':'11.0.0','assurance':'conditional_uncalibrated',
        'pressure_datum':'mean_sea_level_gauge_zero','fault_pressure_coefficient':1.0,
        'geographic_azimuth_deg':None,'cases':[dict(anchor,**c) for c in changes]}


def unique_object(pairs):
    result={}
    for k,v in pairs:
        if k in result: raise StressInputError('Duplicate JSON key: '+k)
        result[k]=v
    return result


def load_cases(path):
    with open(path,encoding='utf-8') as f: cfg=json.load(f,object_pairs_hook=unique_object)
    # Release experiments are locked; new cases require a new reviewed release.
    if json.dumps(cfg,sort_keys=True,allow_nan=False) != json.dumps(default_config(),sort_keys=True):
        raise StressInputError('Scenario configuration differs from reviewed release')
    return [StressCase(**r) for r in cfg['cases']]


def stress_regime(sv, sh, SH):
    tol=1e-9 * max(1,abs(sv),abs(sh),abs(SH))
    if abs(SH-sh)<=tol:
        if abs(sv-sh)<=tol:return 'isotropic_degenerate'
        return 'normal_axisymmetric' if sv>SH else 'reverse_axisymmetric'
    if abs(sv-SH)<=tol:return 'normal_strike_slip_boundary'
    if abs(sv-sh)<=tol:return 'strike_slip_reverse_boundary'
    if sv>SH:return 'normal'
    if sv<sh:return 'reverse'
    return 'strike_slip'


def friction_polygon(sv_mpa, pp_mpa, mu):
    """Vertices in (Shmin, SHmax); no unique stress solution implied."""
    sv=finite('Sv',sv_mpa);p=finite('Pp',pp_mpa);mu=finite('fault_mu',mu)
    if mu<=0 or p<0:raise StressInputError('Invalid friction/pressure')
    v=sv-p
    if v<=0:raise StressInputError('Friction polygon requires Sv-Pp > 0')
    q=(math.hypot(1,mu)+mu)**2
    return [(p+v/q,p+v/q),(p+v/q,sv),(sv,p+q*v),(p+q*v,p+q*v)]


def evaluate_stress(sv_mpa, pp_mpa, case, E_static_GPa=None):
    sv=finite('Sv',sv_mpa);pp=finite('Pp',pp_mpa)
    if sv<0 or pp<0:raise StressInputError('Total stress and pressure must be nonnegative')
    if not isinstance(case,StressCase):raise StressInputError('Expected StressCase')
    has_strain=case.epsilon_x!=0 or case.epsilon_y!=0
    effective_v=sv-case.alpha*pp
    baseline=case.nu/(1-case.nu)*effective_v+case.alpha*pp
    out={'Sv_MPa':sv,'Pp_reference_MPa':pp,'Sv_biot_effective_MPa':effective_v,
        'horizontal_zero_strain_MPa':baseline,'Sx_MPa':None,'Sy_MPa':None,
        'Shmin_MPa':None,'SHmax_MPa':None,'Shmin_biot_effective_MPa':None,
        'SHmax_biot_effective_MPa':None,'delta_Sx_strain_MPa':None,'delta_Sy_strain_MPa':None,
        'fault_ratio_limit':(math.hypot(1,case.fault_mu)+case.fault_mu)**2,
        'fault_effective_min_MPa':None,'fault_effective_max_MPa':None,
        'fault_ratio':None,'SHmax_conditional_lower_MPa':None,'SHmax_conditional_upper_MPa':None,
        'regime':'unavailable','SHmax_relative_axis':'unavailable',
        'status':'missing_static_E_for_strain','numeric_stress_supported':False,
        'conditional_fault_admissible':False,'field_stress_eligible':False,
        'geographic_SHmax_azimuth_deg':None}
    if has_strain and E_static_GPa is None:return out
    dx=dy=0.
    if has_strain:
        E=finite('E_static_GPa',E_static_GPa)
        if E<=0:raise StressInputError('E must be positive')
        factor=1000*E/(1-case.nu**2)
        dx=factor*(case.epsilon_x+case.nu*case.epsilon_y)
        dy=factor*(case.epsilon_y+case.nu*case.epsilon_x)
    sx=baseline+dx;sy=baseline+dy;sh=min(sx,sy);SH=max(sx,sy)
    fmin=min(sv,sh)-pp;fmax=max(sv,SH)-pp;q=out['fault_ratio_limit']
    tol=1e-9*max(1,abs(sv),abs(sh),abs(SH))
    out.update(Sx_MPa=sx,Sy_MPa=sy,Shmin_MPa=sh,SHmax_MPa=SH,
        Shmin_biot_effective_MPa=sh-case.alpha*pp,SHmax_biot_effective_MPa=SH-case.alpha*pp,
        delta_Sx_strain_MPa=dx,delta_Sy_strain_MPa=dy,
        fault_effective_min_MPa=fmin,fault_effective_max_MPa=fmax,
        regime=stress_regime(sv,sh,SH),numeric_stress_supported=True,
        SHmax_relative_axis=('undetermined_equal_horizontal' if abs(sx-sy)<=tol else ('x' if sx>sy else 'y')))
    if effective_v<0:out['status']='negative_biot_effective_vertical_stress'
    elif fmin<=0:out['status']='nonpositive_fault_effective_stress'
    else:
        ratio=fmax/fmin
        out['fault_ratio']=ratio
        # For fixed h'=Sh-Pp, vertical v'=Sv-Pp, all pairwise ratios <= q.
        v=sv-pp;h=sh-pp
        low=max(h,v/q);high=q*min(h,v)
        if low<=high+tol:
            out['SHmax_conditional_lower_MPa']=pp+low
            out['SHmax_conditional_upper_MPa']=pp+high
        allowed=ratio<=q+1e-10
        out['conditional_fault_admissible']=allowed
        out['status']='conditional_admissible' if allowed else 'outside_conditional_fault_bound'
    return out
