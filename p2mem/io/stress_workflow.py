"""Increment 11: exact-node joins and immutable upstream scenario provenance."""
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from collections import Counter
from p2mem.horizontal_stress import StressInputError, evaluate_stress, load_cases, friction_polygon
from p2mem.io.mechanics_workflow import intervals

DESTINATION='outputs/11_horizontal_stress'
BASELINE='INCREMENT_10_SHA256SUMS.txt'
BASELINE_HASH='1bdab84d6dc36a15f87b28f837d72f22140eeebad27a4a2f7aa0d26a755602c3'
WELLS=('Boreas_1','Poseidon_2','Poseidon_North_1','Proteus_1ST2')
METADATA_CHANGES={'README.md','pyproject.toml','p2mem/__init__.py'}
SOURCE7='outputs/07_density_overburden/'
SOURCE8='outputs/08_pore_pressure_effective_stress/'
SOURCE10='outputs/10_static_mechanics_strength/'
EVIDENCE='conditional_uncalibrated_stress_experiment'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(ok, message):
    if not ok:raise StressInputError(message)


def close(a,b):return math.isclose(float(a),float(b),rel_tol=1e-10,abs_tol=1e-7)


def read_csv(path):
    with Path(path).open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')


def verify_baseline(root):
    from pathlib import PurePosixPath
    root=Path(root)
    check(sha(root/BASELINE)==BASELINE_HASH,'Increment 10 ledger identity changed')
    result={}
    for line in (root/BASELINE).read_text().splitlines():
        digest,name=line.split('  ',1);p=PurePosixPath(name)
        check(not p.is_absolute() and '..' not in p.parts and '\\' not in name and ':' not in name and name not in result,'Unsafe baseline ledger')
        target=root/name
        check(target.is_file() and not any(root.joinpath(*p.parts[:i]).is_symlink() for i in range(1,len(p.parts)+1)), 'Missing or symbolic baseline file: '+name)
        if name not in METADATA_CHANGES:check(sha(target)==digest,'Changed baseline file: '+name)
        result[name]=digest
    check(len(result)==313,'Unexpected Increment 10 baseline inventory')
    return result


def exact_join(nodes, mechanics):
    """Join by identical source MD, then independently verify TVD and TVDSS.

    node_index is a report-node index, not a LAS sample index. No nearest join,
    interpolation, resampling or crossing an unresolved interval is allowed.
    """
    index={}
    for r in mechanics:
        md=float(r['MD_m'])
        check(math.isfinite(md) and md not in index,'Duplicate/nonfinite mechanics MD')
        index[md]=r
    joined=[];seen=set();last=None
    for n in nodes:
        md=float(n['md_m']);key=n['node_index']
        check(key not in seen and (last is None or float(n['tvdss_m'])>last),'Repeated/nonmonotonic stress node')
        seen.add(key);last=float(n['tvdss_m'])
        check(md in index,'No exact original MD match for stress node')
        m=index[md]
        check(n['well_key']==m['well_key'],'Well identity mismatch')
        check(close(n['tvd_m'],m['TVD_m']) and close(n['tvdss_m'],m['TVDSS_m']),'Depth datum mismatch')
        joined.append((n,m))
    return joined


def build(root):
    root=Path(root);baseline=verify_baseline(root)
    cases=load_cases(root/'config/horizontal_stress_scenarios.json')
    mech_cfg=json.loads((root/'config/mechanics_scenarios.json').read_text())
    for case in cases:
        mc=next((c for c in mech_cfg['cases'] if c['case_id']==case.mechanics_case),None)
        check(mc is not None and mc['nu_static']==case.nu,'Static Poisson scenario lineage mismatch')
    vrows=read_csv(root/SOURCE7/'vertical_stress_profile.csv')
    shallow=read_csv(root/SOURCE7/'shallow_column_scenarios.csv')
    upstream=read_csv(root/SOURCE8/'effective_stress_profile.csv')
    inventory=read_csv(root/SOURCE8/'pressure_data_inventory.csv')
    check(all(r['availability_status']=='NOT_AVAILABLE' for r in inventory),'New calibration requires evidence review')
    up={}
    for r in upstream:
        k=(r['well_key'],r['node_index'],r['sv_scenario'])
        check(k not in up,'Duplicate pressure scenario key');up[k]=r
    rows=[];coverage=[];alignment=[];blockers=[];polygons=[];formation=[]
    consumed=[SOURCE7+'vertical_stress_profile.csv',SOURCE7+'shallow_column_scenarios.csv',
        SOURCE8+'effective_stress_profile.csv',SOURCE8+'pressure_data_inventory.csv',
        'config/mechanics_scenarios.json','outputs/05_formation_tops/top_survey_corrected_markers.csv']
    for well in WELLS:
        nodes=[r for r in vrows if r['well_key']==well]
        supported_up=[r for r in upstream if r['well_key']==well]
        if not supported_up:
            coverage.append(dict(well_key=well,upstream_report_nodes=len(nodes),stress_nodes=0,
                exact_mechanics_nodes=0,static_E_supported_nodes=0,stress_rows=0,numeric_rows=0,
                conditional_admissible_rows=0,field_eligible_rows=0,status='blocked_absolute_Sv_scenarios_unavailable'))
            blockers.append(dict(well_key=well,method='horizontal_stress',field_eligible=False,
                blocker='No accepted absolute Sv/Pp scenario profile; no cross-well loading transfer'))
            continue
        mechanics=read_csv(root/SOURCE10/(well+'_mechanics.csv'))
        consumed.append(SOURCE10+well+'_mechanics.csv')
        joined=exact_join(nodes,mechanics)
        scenario_names=sorted(set(r['sv_scenario'] for r in supported_up))
        sh={r['scenario_name']:r for r in shallow if r['well_key']==well}
        check(set(scenario_names)=={'low','base','high'},'Missing upstream Sv case')
        for n,m in joined:
            alignment.append(dict(well_key=well,upstream_node_index=int(n['node_index']),
                original_sample_index=int(m['sample_index']),MD_m=float(n['md_m']),
                TVD_m=float(n['tvd_m']),TVDSS_m=float(n['tvdss_m']),
                depth_basis='petrel_source_trace',well_identity_status='inferred_unverified',
                join_method='exact_original_MD_with_TVD_and_TVDSS_check',
                E_static_GPa=float(m['E_static_scenario_GPa']) if m['E_static_scenario_GPa'] else None,
                E_status=m['status']))
            for sv_case in scenario_names:
                u=up[(well,n['node_index'],sv_case)];s=sh[sv_case]
                check(close(u['tvdss_m'],n['tvdss_m']),'Upstream pressure node depth mismatch')
                # Current source7 nodes contain only measured cumulative increments;
                # conditioned contribution is explicitly zero, never fabricated.
                check(n['density_source']=='measured_rhob' and float(s['bridged_gap_stress_pa'])==0,'Partition model requires review for conditioned integrals')
                water=float(s['water_column_stress_pa'])/1e6
                unlogged=float(s['unresolved_shallow_stress_pa'])/1e6
                measured=float(n['cumulative_measured_increment_pa'])/1e6
                sv=water+unlogged+measured
                check(close(sv,u['total_vertical_stress_mpa']),'Sv partition sum differs from Increment 8')
                check(close(float(s['gravity_m_s2'])*float(n['tvdss_m'])*float(u['fluid_density_kg_m3'])/1e6,u['pore_pressure_reference_mpa']),'Hydrostatic datum mismatch')
                for case in cases:
                    pp=float(s['gravity_m_s2'])*case.fluid_density_kg_m3*float(n['tvdss_m'])/1e6
                    E=float(m['E_static_scenario_GPa']) if m['E_static_scenario_GPa'] else None
                    result=evaluate_stress(sv,pp,case,E)
                    if case.case_id=='reference':check(close(result['Sv_biot_effective_MPa'],u['effective_vertical_stress_mpa']),'Reference effective stress differs from Increment 8')
                    row=dict(well_key=well,scenario_id=sv_case+'__'+case.case_id,
                        upstream_node_index=int(n['node_index']),original_sample_index=int(m['sample_index']),
                        MD_m=float(n['md_m']),TVD_m=float(n['tvd_m']),TVDSS_m=float(n['tvdss_m']),
                        sv_scenario=sv_case,parameter_case=case.case_id,mechanics_case=case.mechanics_case,
                        E_static_GPa=E,static_E_status=m['status'],nu_static_assumed=case.nu,
                        biot_alpha=case.alpha,fault_pressure_coefficient=1.,fault_mu_assumed=case.fault_mu,
                        fluid_density_kg_m3=case.fluid_density_kg_m3,epsilon_x=case.epsilon_x,epsilon_y=case.epsilon_y,
                        water_assumed_MPa=water,shallow_assumed_MPa=unlogged,measured_integral_MPa=measured,
                        conditioned_integral_MPa=0.,assumed_fraction_Sv=(water+unlogged)/sv,
                        pressure_basis='hydrostatic_reference_not_predicted_field_pressure',
                        mechanics_basis='assumed_static_nu__analogue_E_only_for_nonzero_strain',
                        depth_basis='petrel_source_trace',well_identity_status='inferred_unverified',
                        evidence_class=EVIDENCE,calibration_status='uncalibrated',**result)
                    rows.append(row)
        wr=[r for r in rows if r['well_key']==well]
        coverage.append(dict(well_key=well,upstream_report_nodes=len(nodes),stress_nodes=len(joined),
            exact_mechanics_nodes=len(joined),static_E_supported_nodes=sum(bool(m['E_static_scenario_GPa']) for n,m in joined),
            stress_rows=len(wr),numeric_rows=sum(r['numeric_stress_supported'] for r in wr),
            conditional_admissible_rows=sum(r['conditional_fault_admissible'] for r in wr),
            field_eligible_rows=0,status='conditional_experiments_only'))
        blockers.append(dict(well_key=well,method='calibrated_field_stress_and_geographic_orientation',field_eligible=False,
            blocker='Uncalibrated Sv; hydrostatic reference; no stress calibration or geographic SHmax evidence'))
        # One explicitly identified terminal node per supported well for diagrams.
        terminal=int(nodes[-1]['node_index'])
        for r in wr:
            if r['upstream_node_index']!=terminal or r['parameter_case'] not in ('reference','fault_mu_040','fault_mu_080'):continue
            if r['Sv_MPa']<=r['Pp_reference_MPa']:continue
            for i,(h,H) in enumerate(friction_polygon(r['Sv_MPa'],r['Pp_reference_MPa'],r['fault_mu_assumed'])):
                polygons.append(dict(well_key=well,scenario_id=r['scenario_id'],upstream_node_index=terminal,
                    TVDSS_m=r['TVDSS_m'],Sv_MPa=r['Sv_MPa'],Pp_reference_MPa=r['Pp_reference_MPa'],
                    fault_mu_assumed=r['fault_mu_assumed'],vertex_index=i,Shmin_MPa=h,SHmax_MPa=H,
                    field_stress_eligible=False))
        for a,b in intervals(root,well):
            lo=float(a['MDRT_reconciled_m']);hi=float(b['MDRT_reconciled_m'])
            for sid in sorted(set(r['scenario_id'] for r in wr)):
                rr=[r for r in wr if r['scenario_id']==sid and lo<=r['MD_m']<hi]
                if not rr:continue
                for prop in ('Sv_MPa','Pp_reference_MPa','Shmin_MPa','SHmax_MPa'):
                    vals=sorted(r[prop] for r in rr if r[prop] is not None)
                    import statistics
                    formation.append(dict(well_key=well,scenario_id=sid,top_MD_m=lo,base_MD_m=hi,
                        top_marker=a['canonical_marker_name'],
                        base_marker=b['canonical_marker_name'],
                        property=prop,n_report_nodes=len(rr),n_numeric=len(vals),
                        n_conditional_admissible=sum(r['conditional_fault_admissible'] for r in rr),
                        min=min(vals) if vals else None,median=statistics.median(vals) if vals else None,
                        max=max(vals) if vals else None,statistics_basis='unweighted_selected_report_nodes_including_flagged_cases',
                        depth_basis='petrel_source_trace',well_identity_status='inferred_unverified'))
    summary=[]
    for (w,s,status,regime),n in sorted(Counter((r['well_key'],r['scenario_id'],r['status'],r['regime']) for r in rows).items()):
        summary.append(dict(well_key=w,scenario_id=s,status=status,regime=regime,n_rows=n,field_stress_eligible=False))
    tables={'stress_scenarios.csv':rows,'depth_alignment.csv':alignment,'stress_coverage.csv':coverage,
        'stress_case_summary.csv':summary,'method_blockers.csv':blockers,'stress_polygon_vertices.csv':polygons,
        'formation_stress_summary.csv':formation}
    sources={p:baseline[p] for p in consumed}
    sources[BASELINE]=BASELINE_HASH
    for p in ('config/horizontal_stress_scenarios.json','config/horizontal_stress_methods.json'):sources[p]=sha(root/p)
    return tables,sources


def serialize(tables,destination):
    for name,rows in tables.items():
        check(bool(rows),'Unexpected empty table: '+name)
        with (Path(destination)/name).open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader()
            for r in rows:
                writer.writerow({k:('true' if v else 'false') if isinstance(v,bool) else '' if v is None else v for k,v in r.items()})


def render(tables,destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    files=[]
    for well in ('Boreas_1','Poseidon_2'):
        fig,axs=plt.subplots(1,3,figsize=(13,6),layout='constrained')
        for svcase,col in [('low','#239690'),('base','#2563a6'),('high','#cf7d32')]:
            rr=[r for r in tables['stress_scenarios.csv'] if r['well_key']==well and r['sv_scenario']==svcase and r['parameter_case']=='reference']
            z=[r['TVDSS_m'] for r in rr]
            # Points deliberately avoid implying continuous full-depth profiles.
            axs[0].scatter([r['Sv_MPa'] for r in rr],z,s=8,label=svcase,color=col)
            axs[1].scatter([r['Shmin_MPa'] for r in rr],z,s=8,label=svcase,color=col)
            poly=[r for r in tables['stress_polygon_vertices.csv'] if r['well_key']==well and r['scenario_id']==svcase+'__reference']
            if poly:
                axs[2].add_patch(Polygon([(r['Shmin_MPa'],r['SHmax_MPa']) for r in poly],closed=True,fill=False,edgecolor=col,label=svcase))
                terminal=rr[-1];axs[2].plot(terminal['Shmin_MPa'],terminal['SHmax_MPa'],'o',color=col)
        axs[0].set(title='Scenario vertical stress',xlabel='Sv (MPa)',ylabel='TVDSS (m; positive downward)')
        axs[1].set(title='Zero horizontal strain: Shmin = SHmax',xlabel='Horizontal stress (MPa)')
        for ax in axs[:2]:ax.invert_yaxis();ax.legend(title='Shallow Sv case')
        axs[2].autoscale_view();axs[2].set(title='Terminal-node conditional polygons',xlabel='Shmin (MPa)',ylabel='SHmax (MPa)');axs[2].legend(title='Sv case; fault mu = 0.6')
        for ax in axs:ax.grid(alpha=.2)
        fig.suptitle(well.replace('_',' ')+' | Conditional stress experiments; field eligibility withheld',fontsize=13)
        name=well+'_stress_qc.png';fig.savefig(Path(destination)/name,dpi=150,metadata={'Software':'Poseidon Increment 11'});plt.close(fig);files.append(name)
    return files


def publish(root,destination=None):
    root=Path(root);destination=Path(destination) if destination else root/DESTINATION
    # No output may overwrite source, source subdirectories, or the project root.
    allowed=root/'outputs'
    check(destination.parent.resolve()==allowed.resolve() and destination.name.startswith('11_'),'Output must be an outputs/11_* directory')
    check(not destination.is_symlink(),'Symbolic output destination rejected')
    destination.parent.mkdir(parents=True,exist_ok=True)
    lock=destination.parent/(destination.name+'.lock')
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
    stage=None;backup=None
    try:
        tables,sources=build(root)
        stage=Path(tempfile.mkdtemp(prefix='.inc11_',dir=destination.parent))
        serialize(tables,stage);figs=render(tables,stage)
        manifest=dict(schema_version='11.0.0',evidence=EVIDENCE,field_eligible_rows=0,
            source_hashes=sources,row_counts={k:len(v) for k,v in tables.items()},
            coverage=tables['stress_coverage.csv'],files={p.name:sha(p) for p in sorted(stage.iterdir())},
            reproduction_scope='packaged_derived_inputs_not_raw_source_regeneration',
            geographic_SHmax_azimuth=None,join='exact_original_MD_checked_TVD_TVDSS_no_interpolation',
            figures=figs)
        write_json(stage/'stress_manifest.json',manifest)
        if destination.exists():
            backup=stage.parent/(stage.name+'_backup');os.replace(destination,backup)
        try:os.replace(stage,destination)
        except BaseException:
            if backup is not None:os.replace(backup,destination)
            raise
        if backup is not None:shutil.rmtree(backup)
        return manifest
    finally:
        if stage is not None and stage.exists():shutil.rmtree(stage)
        lock.unlink(missing_ok=True)


def validate(root,destination=None):
    root=Path(root);destination=Path(destination) if destination else root/DESTINATION
    tables,sources=build(root)
    manifest=json.loads((destination/'stress_manifest.json').read_text())
    check(manifest['source_hashes']==sources and manifest['field_eligible_rows']==0,'Manifest provenance/eligibility mismatch')
    check(manifest['coverage']==tables['stress_coverage.csv'],'Manifest coverage mismatch')
    check(manifest['row_counts']=={k:len(v) for k,v in tables.items()},'Manifest row counts mismatch')
    expected=set(tables)|{'Boreas_1_stress_qc.png','Poseidon_2_stress_qc.png'}
    check(set(manifest['files'])==expected,'Manifest file inventory mismatch')
    check({p.name for p in destination.iterdir()}==expected|{'stress_manifest.json'},'Output inventory mismatch')
    for name,digest in manifest['files'].items():check(sha(destination/name)==digest,'Changed output: '+name)
    with tempfile.TemporaryDirectory() as d:
        serialize(tables,Path(d))
        for name in tables:check((Path(d)/name).read_bytes()==(destination/name).read_bytes(),'Scientific table differs from input-derived result: '+name)
    return manifest
