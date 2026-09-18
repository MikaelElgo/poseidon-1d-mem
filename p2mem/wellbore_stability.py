"""Circular elastic well wall, compression positive, MPa, alpha = 1 only.

Sealed wall: formation pressure remains Pp; total radial traction is Pw.
No thermal stress, diffusion, plasticity, anisotropy or fracture propagation.
Angles are relative to the assumed horizontal major principal stress axis.
"""
import math
import numpy as np


def rotate_stress(shmax, shmin, sv, inclination_deg=0., relative_azimuth_deg=0.):
    values = np.asarray([shmax, shmin, sv, inclination_deg, relative_azimuth_deg], float)
    if not np.all(np.isfinite(values)) or not 0 <= inclination_deg <= 90:
        raise ValueError('Finite stresses and inclination in [0,90] required')
    if shmax < shmin:
        raise ValueError('SHmax must be >= Shmin')
    i, a = np.deg2rad([inclination_deg, relative_azimuth_deg])
    r = np.array([[np.cos(i)*np.cos(a), np.cos(i)*np.sin(a), -np.sin(i)],
                  [-np.sin(a), np.cos(a), 0.],
                  [np.sin(i)*np.cos(a), np.sin(i)*np.sin(a), np.cos(i)]])
    return r @ np.diag([shmax, shmin, sv]) @ r.T


class WallModel:
    """Precomputed angular elastic wall response for pressure-root searches."""
    def __init__(self, total_stress, pp, nu, ucs, phi_deg, tensile_strength,
                 angular_step_deg=1., alpha=1.):
        s = np.asarray(total_stress, float)
        params = np.asarray([pp, nu, ucs, phi_deg, tensile_strength, angular_step_deg, alpha], float)
        if s.shape != (3,3) or not np.all(np.isfinite(s)) or not np.allclose(s, s.T, atol=1e-10, rtol=0):
            raise ValueError('Finite symmetric 3x3 total stress required')
        if not np.all(np.isfinite(params)) or pp < 0 or not 0 <= nu < .5 or ucs <= 0 or not 0 <= phi_deg < 90 or tensile_strength < 0:
            raise ValueError('Invalid wall-model parameters')
        if alpha != 1.:
            raise ValueError('This sealed-wall implementation requires alpha=1')
        if not 0 < angular_step_deg <= 10:
            raise ValueError('Angular step must be in (0,10] degrees')
        self.s, self.pp, self.nu, self.ucs, self.t0 = s, float(pp), float(nu), float(ucs), float(tensile_strength)
        sn = math.sin(math.radians(phi_deg)); self.q = (1+sn)/(1-sn)
        self.angles = np.linspace(0, 360, int(math.ceil(360/angular_step_deg)), endpoint=False)
        t = np.deg2rad(self.angles)
        anis = (s[0,0]-s[1,1])*np.cos(2*t)+2*s[0,1]*np.sin(2*t)
        self.h0 = s[0,0]+s[1,1]-2*anis-pp
        self.axial = s[2,2]-2*nu*anis-pp
        self.shear = 2*(s[1,2]*np.cos(t)-s[0,2]*np.sin(t))

    def state(self, pw):
        if not np.isfinite(pw) or pw < 0:
            raise ValueError('Pw must be finite and nonnegative')
        radial = np.full_like(self.angles, pw-self.pp)
        hoop = self.h0-pw
        centre = (hoop+self.axial)/2
        radius = np.hypot((hoop-self.axial)/2, self.shear)
        minor = np.minimum(radial, centre-radius)
        major = np.maximum(radial, centre+radius)
        middle = radial+hoop+self.axial-minor-major
        return {'radial':radial, 'hoop':hoop, 'axial':self.axial, 'shear':self.shear,
                'sigma1':major, 'sigma2':middle, 'sigma3':minor,
                'mc_margin':self.ucs+self.q*minor-major, 'tensile_margin':minor+self.t0}

    def margins(self, pw):
        s = self.state(pw)
        return float(s['mc_margin'].min()), float(s['tensile_margin'].min())

    def critical(self, pw):
        state = self.state(pw)
        out = []
        for criterion, key in [('Mohr_Coulomb','mc_margin'), ('tensile','tensile_margin')]:
            j = int(np.argmin(state[key]))
            row = {'criterion':criterion, 'theta_deg':float(self.angles[j]), 'Pw_MPa':float(pw)}
            row.update({name+'_MPa':float(values[j]) for name, values in state.items()})
            row['radial_total_MPa'] = row['radial_MPa']+self.pp
            out.append(row)
        return out


def pressure_interval(model, criterion='combined', pressure_tolerance=1e-5):
    """Find the convex stable set on a finite pressure domain.

    Each margin is concave in Pw: min eigenvalue is concave, max convex.
    A golden-section maximum followed by two bisections avoids a coarse
    pressure grid missing a narrow interval. Angular sampling is still finite.
    """
    if criterion not in ('combined','mc','tensile') or pressure_tolerance <= 0:
        raise ValueError('Invalid criterion or pressure tolerance')
    def f(p):
        m, t = model.margins(p)
        return min(m,t) if criterion == 'combined' else (m if criterion == 'mc' else t)
    # Large domain, but never assume its upper endpoint brackets a failure.
    upper = max(1., 8*np.max(np.abs(model.s))+4*model.pp+4*model.ucs+4*model.t0)
    a, b = 0., float(upper); ratio = (math.sqrt(5)-1)/2
    c, d = b-ratio*(b-a), a+ratio*(b-a); fc, fd = f(c), f(d)
    for _ in range(100):
        if b-a <= pressure_tolerance/10: break
        if fc > fd:
            b, d, fd = d, c, fc; c = b-ratio*(b-a); fc = f(c)
        else:
            a, c, fc = c, d, fd; d = a+ratio*(b-a); fd = f(d)
    peak, peak_margin = max([(0.,f(0.)),(upper,f(upper)),((a+b)/2,f((a+b)/2))], key=lambda x:x[1])
    result = {'status':'empty', 'lower_MPa':None, 'upper_MPa':None,
              'peak_pressure_MPa':float(peak), 'peak_margin_MPa':float(peak_margin),
              'search_upper_MPa':float(upper), 'lower_boundary':None, 'upper_boundary':None,
              'lower_residual_MPa':None, 'upper_residual_MPa':None}
    if peak_margin < -1e-6: return result
    if peak_margin <= 1e-6:
        result.update(status='tangent_or_unresolved', lower_MPa=None, upper_MPa=None)
        return result
    def edge(outside, inside):
        for _ in range(100):
            if abs(inside-outside) <= pressure_tolerance: break
            mid = (inside+outside)/2
            if f(mid) >= 0: inside = mid
            else: outside = mid
        return float(inside)
    lo = 0. if f(0.) >= 0 else edge(0.,peak)
    hi = float(upper) if f(upper) >= 0 else edge(upper,peak)
    def label(p):
        m,t = model.margins(p)
        return 'Mohr_Coulomb' if criterion == 'mc' or (criterion == 'combined' and m <= t) else 'tensile'
    result.update(status='interval' if hi < upper else 'upper_unbracketed', lower_MPa=lo, upper_MPa=hi,
                  lower_boundary='domain_zero' if lo == 0 else label(lo),
                  upper_boundary='domain_limit' if hi == upper else label(hi),
                  lower_residual_MPa=f(lo), upper_residual_MPa=f(hi))
    return result


def converged_envelope(total_stress, pp, nu, ucs, phi_deg, tensile_strength,
                       angular_tolerance_MPa=.02, initial_step_deg=2., minimum_step_deg=.25):
    if not 0 < minimum_step_deg < initial_step_deg <= 10 or angular_tolerance_MPa <= 0:
        raise ValueError('Invalid convergence controls')
    args = (total_stress,pp,nu,ucs,phi_deg,tensile_strength)
    step = initial_step_deg
    coarse = pressure_interval(WallModel(*args, angular_step_deg=step))
    history = []
    while step > minimum_step_deg:
        step = max(minimum_step_deg, step/2)
        model = WallModel(*args, angular_step_deg=step)
        fine = pressure_interval(model)
        same = fine['status'] == coarse['status']
        if same and fine['status'] == 'interval':
            error = max(abs(fine[k]-coarse[k]) for k in ('lower_MPa','upper_MPa'))
        elif same and fine['status'] == 'empty':
            error = abs(fine['peak_margin_MPa']-coarse['peak_margin_MPa'])
        else: error = float('inf')
        history.append({'step_deg':step,'status':fine['status'], 'endpoint_or_empty_peak_change_MPa':error if math.isfinite(error) else None})
        if error <= angular_tolerance_MPa: break
        coarse = fine
    fine.update(angular_converged=bool(error <= angular_tolerance_MPa),
                angular_step_deg=step, angular_count=len(model.angles),
                angular_change_MPa=error if math.isfinite(error) else None,
                angular_history=history)
    fine['screening_interval_supported'] = fine['angular_converged'] and fine['status']=='interval'
    return fine, model
