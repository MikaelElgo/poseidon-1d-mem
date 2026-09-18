"""Exact-node stress/strength join and conditional wall-pressure envelopes."""
from pathlib import Path
import csv
import hashlib
import json
from collections import Counter
import numpy as np
from p2mem.mechanics import load_config as load_mechanics, evaluate_mechanics
from p2mem.wellbore_stability import rotate_stress, converged_envelope, WallModel, pressure_interval

DESTINATION = 'outputs/12_wellbore_stability'
CONFIG = 'config/wellbore_stability.json'
STRESS = 'outputs/11_horizontal_stress/stress_scenarios.csv'


def read_csv(path):
    with Path(path).open(newline='') as f: return list(csv.DictReader(f))


def write_csv(path, rows):
    if not rows: raise ValueError('Cannot publish empty table')
    with Path(path).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n'); w.writeheader()
        for row in rows:
            w.writerow({k:('true' if v else 'false') if isinstance(v,bool) else v for k,v in row.items()})


def config(root):
    c=json.loads((Path(root)/CONFIG).read_text())
    required={'schema_version','boundary','orientation_basis','pressure_datum','angular_tolerance_MPa','initial_step_deg','minimum_step_deg','orientations'}
    if set(c)!=required or c['schema_version']!='12.0.0' or c['boundary']!='sealed_wall_fixed_formation_pressure_alpha_1': raise ValueError('Unsupported WBS schema/boundary')
    if c['orientation_basis']!='hypothetical_relative_to_SHmax_no_geographic_azimuth' or c['pressure_datum']!='gauge_MSL_equivalent_column_using_TVDSS': raise ValueError('Unsupported orientation/datum')
    if not 0 < c['minimum_step_deg'] < c['initial_step_deg'] <= 10 or not 0 < c['angular_tolerance_MPa'] <= .02: raise ValueError('Invalid angular controls')
    if not c['orientations'] or len({r['id'] for r in c['orientations']})!=len(c['orientations']):raise ValueError('Invalid orientations')
    for row in c['orientations']:
        if set(row)!={'id','inclination_deg','relative_azimuth_deg'}:raise ValueError('Orientation schema')
        rotate_stress(2,1,3,row['inclination_deg'],row['relative_azimuth_deg'])
    return c


def inputs(root):
    root=Path(root); stress=read_csv(root/STRESS)
    _,cases=load_mechanics(root/'config/mechanics_scenarios.json'); cases={c.case_id:c for c in cases}
    mechanics={}; sources=[STRESS,CONFIG,'config/mechanics_scenarios.json']
    for well in sorted({r['well_key'] for r in stress}):
        rel=f'outputs/10_static_mechanics_strength/{well}_mechanics.csv';sources.append(rel)
        rows=read_csv(root/rel)
        for r in rows:
            key=(well,r['sample_index'])
            if key in mechanics:raise ValueError('Duplicate mechanics sample')
            mechanics[key]=r
    audit=[]; eligible=[];seen=set()
    for source in stress:
        key=(source['well_key'],source['scenario_id'],source['original_sample_index'])
        if key in seen:raise ValueError('Duplicate stress tuple')
        seen.add(key); row=dict(source); reasons=[]
        m=mechanics.get((source['well_key'],source['original_sample_index']))
        strength={k:None for k in ('UCS_MPa','phi_deg','T0_MPa','matched_E_static_GPa')}
        if source['numeric_stress_supported']!='true':reasons.append('numeric_stress_unavailable')
        if source['conditional_fault_admissible']!='true':reasons.append('far_field_fault_bound_not_passed')
        if float(source['biot_alpha'])!=1 or float(source['fault_pressure_coefficient'])!=1:reasons.append('unsupported_pressure_coefficient')
        if m is None or m['scenario_numeric_supported']!='true':reasons.append('exact_node_analogue_strength_unavailable')
        else:
            if any(abs(float(source[k])-float(m[k]))>1e-8 for k in ('MD_m','TVD_m','TVDSS_m')):raise ValueError('Depth mismatch at original sample index')
            case=cases[source['mechanics_case']]
            if float(source['nu_static_assumed'])!=case.nu_static:raise ValueError('Stress/strength nu mismatch')
            computed=evaluate_mechanics(np.array([float(m['E_dynamic_GPa'])]),np.array([True]),case)
            # Fixed analogue UCS law; case-dependent phi and T0 are evaluated together.
            strength.update(UCS_MPa=float(computed['UCS_scenario_MPa'][0]), phi_deg=case.phi_deg,
                            T0_MPa=float(computed['T0_assumed_MPa'][0]), matched_E_static_GPa=float(computed['E_static_scenario_GPa'][0]))
            if source['E_static_GPa'] and abs(float(source['E_static_GPa'])-strength['matched_E_static_GPa'])>1e-9:raise ValueError('Stress/strength E mismatch')
        row.update(strength)
        row.update(wbs_input_eligible=not reasons,wbs_input_reasons=';'.join(reasons) if reasons else 'conditional_inputs_supported',field_wbs_eligible=False)
        audit.append(row)
        if not reasons:eligible.append(row)
    return audit,eligible,sources


def publish(root, destination=None):
    root=Path(root);dest=Path(destination) if destination else root/DESTINATION;dest.mkdir(parents=True,exist_ok=True)
    c=config(root);audit,eligible,sources=inputs(root)
    envelopes=[];critical=[];cache={}
    for n,row in enumerate(eligible):
        for orientation in c['orientations']:
            args=tuple(float(row[k]) for k in ('SHmax_MPa','Shmin_MPa','Sv_MPa','Pp_reference_MPa','nu_static_assumed','UCS_MPa','phi_deg','T0_MPa'))
            key=args+(orientation['inclination_deg'],orientation['relative_azimuth_deg'])
            if key not in cache:
                h,l,v,pp,nu,u,phi,t=args
                s=rotate_stress(h,l,v,key[-2],key[-1])
                result,model=converged_envelope(s,pp,nu,u,phi,t,**{k:c[k] for k in ('angular_tolerance_MPa','initial_step_deg','minimum_step_deg')})
                cache[key]=(result,model)
            result,model=cache[key]
            base={k:row[k] for k in ('well_key','scenario_id','original_sample_index','MD_m','TVD_m','TVDSS_m','mechanics_case','SHmax_MPa','Shmin_MPa','Sv_MPa','Pp_reference_MPa','nu_static_assumed','biot_alpha','fault_mu_assumed','UCS_MPa','phi_deg','T0_MPa','assumed_fraction_Sv')}
            base.update(orientation_id=orientation['id'],inclination_deg=orientation['inclination_deg'],relative_azimuth_deg=orientation['relative_azimuth_deg'],orientation_basis=c['orientation_basis'],geographic_azimuth_deg='',field_wbs_eligible=False,calibration_status='uncalibrated',boundary=c['boundary'])
            out=dict(base);out.update({k:v for k,v in result.items() if k!='angular_history'})
            out['angular_history_json']=json.dumps(result['angular_history'],separators=(',',':'),allow_nan=False)
            # Candidate endpoints retained for diagnostic purposes; density only for converged intervals.
            for side in ('lower','upper'):
                value=result[side+'_MPa']
                out[side+'_MSL_equivalent_density_kg_m3']=(value*1e6/(9.80665*float(row['TVDSS_m'])) if result['screening_interval_supported'] and float(row['TVDSS_m'])>0 else None)
            out['density_basis']=c['pressure_datum']
            envelopes.append(out)
            points={'reference_Pw_equals_Pp':float(row['Pp_reference_MPa'])}
            if result['screening_interval_supported']:
                points.update(lower=result['lower_MPa'],midpoint=(result['lower_MPa']+result['upper_MPa'])/2,upper=result['upper_MPa'])
            for point,pw in points.items():
                for wall in model.critical(pw):critical.append(dict(base,pressure_point=point,**wall))
        if n and n%100==0:print(f'WBS: {n}/{len(eligible)} supported input tuples',flush=True)
    write_csv(dest/'wbs_input_eligibility.csv',audit);write_csv(dest/'pressure_envelopes.csv',envelopes);write_csv(dest/'critical_wall_states.csv',critical)
    coverage=[]
    for well in ('Boreas_1','Poseidon_2','Poseidon_North_1','Proteus_1ST2'):
        a=[r for r in audit if r['well_key']==well];e=[r for r in envelopes if r['well_key']==well]
        coverage.append(dict(well_key=well,stress_input_rows=len(a),eligible_input_rows=sum(r['wbs_input_eligible'] for r in a),exact_strength_nodes=len({r['original_sample_index'] for r in a if r['UCS_MPa'] is not None}),orientation_rows=len(e),supported_intervals=sum(r['screening_interval_supported'] for r in e),empty_intervals=sum(r['status']=='empty' for r in e),unconverged_rows=sum(not r['angular_converged'] for r in e),field_wbs_eligible=False,blocker='absolute_Sv_scenarios_unavailable' if not a else 'see_per_row_eligibility'))
    write_csv(dest/'coverage.csv',coverage)
    benchmark=[]
    model=WallModel(np.diag([60.,60.,60.]),20,.25,40,30,2)
    for pw in (25.,30.,60.,90.,95.):
        for state in model.critical(pw):benchmark.append(dict(case='isotropic_S60_Pp20_UCS40_phi30_T02',**state))
    write_csv(dest/'analytical_benchmark.csv',benchmark)
    figure(dest,envelopes)
    names=['wbs_input_eligibility.csv','pressure_envelopes.csv','critical_wall_states.csv','coverage.csv','analytical_benchmark.csv','wbs_qc.png']
    manifest={'schema_version':'12.0.0','coverage':coverage,'row_counts':{name:len(read_csv(dest/name)) for name in names if name.endswith('.csv')},'unique_numerical_models':len(cache),'angular_convergence_counts':dict(Counter(str(r['angular_converged']) for r in envelopes)), 'field_calibration_claim':False,'actual_trajectory_claim':False,'operational_mud_weight_claim':False,'source_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in sources},'output_sha256':{name:hashlib.sha256((dest/name).read_bytes()).hexdigest() for name in names}}
    (dest/'wbs_manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    return manifest


def figure(dest,envelopes):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for ax,well in zip(axes,('Boreas_1','Poseidon_2')):
        for orientation,color in [('vertical','#087e8b'),('i60_a45','#a03a22')]:
            rows=[r for r in envelopes if r['well_key']==well and r['scenario_id']=='base__reference' and r['orientation_id']==orientation and r['screening_interval_supported']]
            for r in rows:
                ax.plot([r['lower_MPa'],r['upper_MPa']],[float(r['TVDSS_m'])]*2,color=color,linewidth=2)
            ax.plot([],[],color=color,label=orientation+' (hypothetical)')
        ax.invert_yaxis();ax.set(title=well.replace('_',' '),xlabel='Conditional wall pressure Pw (MPa)',ylabel='TVDSS (m)');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Increment 12 | Analogue stability intervals at exact supported nodes\nUncalibrated; fixed Pp, sealed wall; no continuous depth interpolation',fontsize=12)
    fig.savefig(Path(dest)/'wbs_qc.png',dpi=140,metadata={'Software':'p2mem Increment 12'});plt.close(fig)


def validate(root,destination=None):
    root=Path(root);dest=Path(destination) if destination else root/DESTINATION
    manifest=json.loads((dest/'wbs_manifest.json').read_text())
    for name,digest in manifest['source_sha256'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('Changed WBS input: '+name)
    for name,digest in manifest['output_sha256'].items():
        if hashlib.sha256((dest/name).read_bytes()).hexdigest()!=digest:raise ValueError('Changed WBS output: '+name)
    for name,count in manifest['row_counts'].items():
        if len(read_csv(dest/name))!=count:raise ValueError('WBS row count mismatch')
    return manifest
