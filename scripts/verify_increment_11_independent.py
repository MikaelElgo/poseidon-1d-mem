"""Independent Decimal compliance-system and Mohr geometry verification.

No p2mem or numpy imports. Checks every numeric exported tuple. This verifies
arithmetic and invariants, not field calibration or material transferability.
"""
import csv
from decimal import Decimal, localcontext
from pathlib import Path
import json
import sys


def verify(destination):
    checked=0;worst=0.;missing=0
    def d(x):return Decimal(str(x))
    def assert_close(actual,expected,label):
        nonlocal worst
        err=abs(float(actual)-float(expected));worst=max(worst,err)
        if err>1e-8:raise AssertionError(label+': independent mismatch '+str(err))
    with localcontext() as ctx:
        ctx.prec=50
        with (Path(destination)/'stress_scenarios.csv').open() as f:
            for r in csv.DictReader(f):
                if r['field_stress_eligible']!='false' or r['geographic_SHmax_azimuth_deg']!='':raise AssertionError('Unsupported field claim')
                if r['numeric_stress_supported']!='true':
                    missing+=1
                    assert r['status']=='missing_static_E_for_strain' and r['Sx_MPa']==r['Sy_MPa']==''
                    continue
                sv,p,a,n=map(d,(r['Sv_MPa'],r['Pp_reference_MPa'],r['biot_alpha'],r['nu_static_assumed']))
                v=sv-a*p
                # Solve effective compliance system by elimination:
                # x - nu*y = E*ex + nu*v; y - nu*x = E*ey + nu*v.
                ex,ey=map(d,(r['epsilon_x'],r['epsilon_y']))
                E=d(r['E_static_GPa'])*1000 if ex or ey else d(0)
                rhsx=E*ex+n*v;rhsy=E*ey+n*v
                y=(rhsy+n*rhsx)/(1-n*n);x=rhsx+n*y
                assert_close(r['Sx_MPa'],x+a*p,'Sx')
                assert_close(r['Sy_MPa'],y+a*p,'Sy')
                assert_close(r['Shmin_MPa'],min(x,y)+a*p,'Shmin')
                assert_close(r['SHmax_MPa'],max(x,y)+a*p,'SHmax')
                assert_close(r['Sv_MPa'],sum(d(r[k]) for k in ('water_assumed_MPa','shallow_assumed_MPa','measured_integral_MPa','conditioned_integral_MPa')),'Sv partitions')
                hi=max(sv,x+a*p,y+a*p)-p;lo=min(sv,x+a*p,y+a*p)-p
                mu=d(r['fault_mu_assumed'])
                # Mohr circle tangent slope: radius / sqrt(center^2-radius^2).
                expected=False
                if lo>0 and v>=0:
                    center=(hi+lo)/2;radius=(hi-lo)/2
                    slope=radius/(center*center-radius*radius).sqrt()
                    expected=slope<=mu+d('1e-10')
                if (r['conditional_fault_admissible']=='true')!=expected:raise AssertionError('Friction geometry mismatch')
                checked+=1
    return {'checked_numeric_rows':checked,'checked_withheld_rows':missing,
        'maximum_absolute_stress_residual_MPa':worst,'passed':True,
        'method':'50-digit Decimal compliance elimination and Mohr-circle tangent slope',
        'field_calibration_claim':False}

if __name__=='__main__':print(json.dumps(verify(sys.argv[1]),indent=2))
