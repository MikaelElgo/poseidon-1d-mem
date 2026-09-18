"""Package-free Decimal and Mohr-circle checks on the exported reference cases."""
from decimal import Decimal as D, localcontext
import csv
import json
import math
from pathlib import Path


def verify(directory):
    errors={k:0. for k in ('E_static_GPa','UCS_MPa','G_GPa','K_GPa','MC_tangency_MPa','T0_MPa')}
    checked=0
    for path in sorted(Path(directory).glob('*_mechanics.csv')):
        with path.open(newline='') as f:
            supported=[r for r in csv.DictReader(f) if r['scenario_numeric_supported']=='true']
        if not supported:continue
        # Independent values across the full available support, not just one easy case.
        indices=sorted({round(j*(len(supported)-1)/19) for j in range(20)})
        for index in indices:
            r=supported[index]
            with localcontext() as ctx:
                ctx.prec=60
                ed=D(r['E_dynamic_GPa']);nu=D(r['nu_static_assumed'])
                es=D('0.3655')*(D('1.0959')*ed.ln()).exp()
                u=D('46.2')*(D('.027')*es).exp()
                expected={'E_static_GPa':float(es),'UCS_MPa':float(u),
                    'G_GPa':float(es/(2*(1+nu))),'K_GPa':float(es/(3*(1-2*nu))),
                    'T0_MPa':float(u*D('.05'))}
            for key,field in [('E_static_GPa','E_static_scenario_GPa'),('UCS_MPa','UCS_scenario_MPa'),
                              ('G_GPa','G_static_scenario_GPa'),('K_GPa','K_static_scenario_GPa'),
                              ('T0_MPa','T0_assumed_MPa')]:
                diff=abs(expected[key]-float(r[field]));errors[key]=max(errors[key],diff)
                if not math.isclose(expected[key],float(r[field]),rel_tol=1e-11,abs_tol=1e-11):
                    raise AssertionError(f'Independent check failed {path.name}:{index}:{key}')
            ucs=float(r['UCS_scenario_MPa']);cohesion=float(r['cohesion_scenario_MPa']);mu=float(r['mu_derived'])
            distance=(cohesion+mu*ucs/2)/math.hypot(1,mu)
            residual=abs(distance-ucs/2);errors['MC_tangency_MPa']=max(errors['MC_tangency_MPa'],residual)
            if residual>1e-10:raise AssertionError('Mohr circle is not tangent')
            if r['field_mechanics_eligible']!='false':raise AssertionError('Field claim leaked')
            checked+=1
    if not checked:raise AssertionError('No independently checked supported rows')
    return {'method':'60-digit Decimal exp/ln; Mohr-circle geometry; no p2mem or numpy imports',
            'checked_rows':checked,'maximum_absolute_residuals':errors,'passed':True,
            'calibration_claim':False}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('directory');args=parser.parse_args()
    print(json.dumps(verify(args.directory),indent=2))
