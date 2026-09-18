"""Independent verification: no p2mem imports.

Vertical intervals: direct intersection of linear failure inequalities at
cos(2 theta)=+/-1, without pressure search or principal-order assumptions.
Inclined checks: numpy full 3x3 eigensolve on a separate 0.25 degree grid.
"""
from pathlib import Path
import csv
import json
import math
import numpy as np


def rows(path):
    with Path(path).open(newline='') as f:return list(csv.DictReader(f))


def vertical_interval(h,l,v,p,nu,u,phi,t):
    q=(1+math.sin(math.radians(phi)))/(1-math.sin(math.radians(phi)))
    lower,upper=0.,float('inf')
    for c in (-1,1):
        offset=np.array([-p,h+l-2*(h-l)*c-p,v-2*nu*(h-l)*c-p])
        slope=np.array([1.,-1.,0.])
        inequalities=[(offset[j]+t,slope[j]) for j in range(3)]
        inequalities += [(u+q*offset[j]-offset[i],q*slope[j]-slope[i]) for i in range(3) for j in range(3)]
        for b,a in inequalities:
            if abs(a)<1e-15:
                if b<0:return None
            elif a>0:lower=max(lower,-b/a)
            else:upper=min(upper,-b/a)
    return (lower,upper) if upper>=lower else None


def independent_tensor(row,pw,theta):
    i,a=np.deg2rad([float(row['inclination_deg']),float(row['relative_azimuth_deg'])])
    axis=np.array([np.sin(i)*np.cos(a),np.sin(i)*np.sin(a),np.cos(i)])
    ey=np.array([-np.sin(a),np.cos(a),0.]);ex=np.cross(ey,axis)
    basis=np.stack((ex,ey,axis))
    far=basis@np.diag([float(row['SHmax_MPa']),float(row['Shmin_MPa']),float(row['Sv_MPa'])])@basis.T
    p=float(row['Pp_reference_MPa']);nu=float(row['nu_static_assumed'])
    theta=np.asarray(theta,float);z=np.zeros(theta.shape+(3,3))
    cos,sin=np.cos(theta),np.sin(theta)
    anis=(far[0,0]-far[1,1])*(cos*cos-sin*sin)+4*far[0,1]*sin*cos
    z[...,0,0]=pw-p
    z[...,1,1]=far[0,0]+far[1,1]-2*anis-pw-p
    z[...,2,2]=far[2,2]-2*nu*anis-p
    z[...,1,2]=z[...,2,1]=2*(far[1,2]*cos-far[0,2]*sin)
    return z


def verify(destination):
    dest=Path(destination);envelopes=rows(dest/'pressure_envelopes.csv');walls=rows(dest/'critical_wall_states.csv')
    maximum_tensor_error=0.
    for row in walls:
        tensor=independent_tensor(row,float(row['Pw_MPa']),np.deg2rad(float(row['theta_deg'])))
        eig=np.linalg.eigvalsh(tensor)
        expected=np.array([float(row[k]) for k in ('sigma3_MPa','sigma2_MPa','sigma1_MPa')])
        error=float(np.max(np.abs(eig-expected)));maximum_tensor_error=max(maximum_tensor_error,error)
        assert error<1e-9,'Principal stress mismatch'
        for (i,j),key in [((0,0),'radial_MPa'),((1,1),'hoop_MPa'),((2,2),'axial_MPa'),((1,2),'shear_MPa')]:assert abs(tensor[i,j]-float(row[key]))<1e-9
        assert abs(float(row['radial_total_MPa'])-float(row['Pw_MPa']))<1e-10
        sn=math.sin(math.radians(float(row['phi_deg'])));q=(1+sn)/(1-sn)
        assert abs(float(row['mc_margin_MPa'])-(float(row['UCS_MPa'])+q*eig[0]-eig[-1]))<1e-9
        assert abs(float(row['tensile_margin_MPa'])-(eig[0]+float(row['T0_MPa'])))<1e-9
        assert row['field_wbs_eligible']=='false' and row['geographic_azimuth_deg']==''
    vertical_count=0;grid_count=0;cache={};worst_grid_margin=0.
    theta=np.deg2rad(np.arange(0,360,.25))
    for row in envelopes:
        args=[float(row[k]) for k in ('SHmax_MPa','Shmin_MPa','Sv_MPa','Pp_reference_MPa','nu_static_assumed','UCS_MPa','phi_deg','T0_MPa')]
        if row['orientation_id']=='vertical':
            exact=vertical_interval(*args);vertical_count+=1
            if exact is None:assert row['status']=='empty'
            else:
                assert row['status']=='interval'
                assert max(abs(float(row[k])-v) for k,v in zip(('lower_MPa','upper_MPa'),exact))<2e-5
        if row['screening_interval_supported']!='true':continue
        assert row['angular_converged']=='true' and float(row['lower_MPa'])<float(row['upper_MPa'])
        key=tuple(args+[float(row['inclination_deg']),float(row['relative_azimuth_deg'])])
        lo,hi=float(row['lower_MPa']),float(row['upper_MPa'])
        if key not in cache:
            sn=math.sin(math.radians(args[6]));q=(1+sn)/(1-sn)
            def margin(pw):
                e=np.linalg.eigvalsh(independent_tensor(row,pw,theta))
                return min(float(np.min(args[5]+q*e[:,0]-e[:,-1])),float(np.min(e[:,0]+args[7])))
            vals=[margin(p) for p in (lo,(lo+hi)/2,hi)]
            assert min(vals)>-.03,'Independent angular-grid failure beyond tolerance'
            assert margin(hi+.05)<0,'Upper endpoint not a failure boundary'
            if lo>.05:assert margin(lo-.05)<0,'Lower endpoint not a failure boundary'
            cache[key]=min(vals)
        worst_grid_margin=min(worst_grid_margin,cache[key]);grid_count+=1
        for side in ('lower','upper'):
            rho=float(row[side+'_MSL_equivalent_density_kg_m3'])
            assert abs(rho*9.80665*float(row['TVDSS_m'])/1e6-float(row[side+'_MPa']))<1e-9
    return {'passed':True,'wall_rows_checked':len(walls),'vertical_exact_intervals_checked':vertical_count,
            'inclined_and_vertical_grid_rows_checked':grid_count,'unique_grid_checks':len(cache),
            'independent_grid_step_deg':.25,'worst_endpoint_margin_MPa':worst_grid_margin,
            'max_principal_stress_error_MPa':maximum_tensor_error}

if __name__=='__main__':
    print(json.dumps(verify(Path(__file__).resolve().parents[1]/'outputs/12_wellbore_stability'),indent=2))
