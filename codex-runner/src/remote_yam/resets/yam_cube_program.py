"""One-process YAM cube sequence; all motor writes are one-shot and journaled."""
from __future__ import annotations
from .station import resource
import copy,hashlib,json,math,os,shutil,subprocess,sys,time
from contextlib import nullcontext
from pathlib import Path
import cv2
import numpy as np
from .yam_cube_reset import ResetBlocked,plain,detect,stable_scene,color_mask,compare,load_targets,require_binding,load_workspace
from .yam_cube_reset_io import RobotIO,execute_pose,CUBE_TIMING_PROFILE,ControllerFault,check_controller_fault
from .yam_cube_reset_planner import CubePlanner,collision_loader_reference
from .yam_cube_contact import reference_contact
from .yam_cube_goals import apply_task_geometry

# Goal identity is supplied by the station; no robot targets are bundled.
GOALS_SHA=None


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.writing');temporary.write_text(json.dumps(plain(value),indent=2)+'\n');os.replace(temporary,path)


def require(condition,message):
    if not condition:raise ResetBlocked(message)


def verify_pickup(before,after):
    """Report motion of the observed cube; never veto on a vision threshold."""
    a=np.median([r['cube_top_center_grasp_m'] for r in before],axis=0)
    b=np.array([r['cube_top_center_grasp_m'] for r in after])
    shift=float(np.max(np.linalg.norm(b-a,axis=1)))
    old=np.median([r['cube_top_center_world_m'][2] for r in before])
    rise=float(min(r['cube_top_center_world_m'][2] for r in after)-old)
    warnings=[]
    if shift>.008:warnings.append('Observed grasp-relative shift; jaw centering is not proof of slip')
    if rise<.030:warnings.append('Observed rise below nominal 30mm; pickup outcome uncertain')
    return dict(grasp_relative_shift_m=shift,observed_world_rise_m=rise,warnings=warnings)


def verify_carry(reference,rows):
    center=np.median([r['cube_top_center_grasp_m'] for r in reference],axis=0)
    shift=float(max(np.linalg.norm(np.array(r['cube_top_center_grasp_m'])-center) for r in rows))
    return dict(grasp_relative_shift_m=shift,warnings=['Observed carried-cube shift; placement may differ'] if shift>.008 else [])


def verify_release(before,after):
    a=np.median([r['cube_top_center_world_m'] for r in before],axis=0)
    movement=float(max(np.linalg.norm(np.array(r['cube_top_center_world_m'])-a) for r in after))
    z0=np.median([r['cube_top_center_grasp_m'][2] for r in before])
    separation=float(min(r['cube_top_center_grasp_m'][2] for r in after)-z0)
    return dict(observed_world_movement_m=movement,gripper_separation_m=separation,
        warnings=['Release observation differs; inspect final placement report'] if movement>.008 or separation<.025 else [])


def resume_checkpoint(resume,audit_path,state):
    """Continue the existing immutable plan after its last confirmed stage."""
    resume=Path(resume);run=resume.parent
    old=json.loads((resume/'result.json').read_text());audit=json.loads(Path(audit_path).read_text())
    digest=hashlib.sha256((resume/'result.json').read_bytes()).hexdigest()
    require(audit['complete'] and audit['preview_result_sha256']==digest and old['targets_sha256']==resource('goals_sha'),'Resume audit/goal binding failed')
    progress=json.loads((run/'progress.json').read_text());result=json.loads((run/'result.json').read_text())
    require(not progress.get('pending') and not result.get('pending'),'Pending/uncertain movement cannot be resumed')
    original=next(p for p in old['plans'] if p['color']=='blue')
    confirmed=[r['stage'] for r in progress['confirmed'] if r['color']=='blue'];names=[r['name'] for r in original['stages']]
    require(confirmed and confirmed==names[:len(confirmed)] and confirmed[-1] in ('close','lift_clear','lift','transfer','place_align','place'),'Unsupported confirmed continuation checkpoint')
    last=original['stages'][len(confirmed)-1]
    receipt=json.loads(sorted(run.glob('motion-*.json'))[-1].read_text())
    require(receipt['pending']['color']=='blue' and receipt['pending']['stage']==last['name'] and receipt['result']['state']=='holding' and not receipt['result']['active'],'Last motion was not positively confirmed')
    require(np.allclose(receipt['result']['target_rad'],last['points_rad'][-1],atol=1e-10,rtol=0),'Motion receipt differs from audited plan')
    # Compare with measured completion feedback, not the commanded target:
    # the native controller already accepted its ordinary tracking residual.
    require(np.max(abs(np.array(state['joints'])-receipt['result']['measured_rad']))<=.01,'Arms moved away from measured confirmed checkpoint')
    plan=copy.deepcopy(original);plan['stages']=plan['stages'][len(confirmed):];plan['resume_after']=last['name'];plan['resumed_plan_sha256']=digest
    return plan


def select_wrist_component(candidates,reference=None):
    """Associate a visible surface with the grasp track, never estimate size."""
    require(bool(candidates),'No valid wrist cube surface')
    expected=None if reference is None else np.median([r['cube_top_center_grasp_m'] for r in reference],axis=0)
    return min(candidates,key=lambda row:float(np.linalg.norm(row['center'][:2] if expected is None else row['center']-expected)))


def wrist_rows(io,report,color,side,out,*,reference=None,count=3):
    """Associate the colored cube using factory depth and measured FK."""
    from remote_yam.api_depth import factory_ray
    from remote_yam.resets.kinematics import arm_pose
    out=Path(out);out.mkdir(parents=True,exist_ok=False);state=io.call('state');save(out/'state-before.json',state)
    idx=0 if side=='left' else 1;T=np.array(report['cameras'][side]['T_grasp_camera']);profile=report['cameras'][side]['depth_intrinsics']
    fk=arm_pose(report,{side+'_joints_deg':np.rad2deg(state['joints'][idx*6:idx*6+6])},side)
    def cloud(frame,mask):
        v,u=np.nonzero(mask & np.isfinite(frame.depth) & (frame.depth>0));require(len(u)>=20,'Insufficient wrist depth')
        take=np.linspace(0,len(u)-1,min(2500,len(u)),dtype=int);u,v=u[take],v[take]
        rays=np.array([factory_ray(profile,int(x),int(y)) for x,y in zip(u,v)])
        return (rays*frame.depth[v,u,None])@T[:3,:3].T+T[:3,3]
    rows=[]
    for i,f in enumerate(io.captures(report,count=count,camera=side)):
        cv2.imwrite(str(out/f'{side}-{i}.jpg'),cv2.cvtColor(f.rgb,cv2.COLOR_RGB2BGR))
        count,labels,stats,centers=cv2.connectedComponentsWithStats(color_mask(f.rgb,color).astype('uint8'))
        candidates=[j for j in range(1,count) if stats[j,cv2.CC_STAT_AREA]>80]
        require(bool(candidates),f'{color}: absent wrist cube; hold and inspect')
        surfaces=[]
        for label in candidates:
            core=cv2.erode((labels==label).astype('uint8'),np.ones((3,3),'uint8'))>0
            try:points=cloud(f,core)
            except ResetBlocked:continue
            if len(points)<35:continue
            z=np.quantile(points[:,2],.2);top=points[abs(points[:,2]-z)<=.004]
            if len(top)>=30:surfaces.append(dict(label=label,center=np.median(top,axis=0)))
        selected=select_wrist_component(surfaces,reference);label=selected['label'];center=selected['center'];pixel_center=centers[label]
        row=dict(sequence=f.metadata['sequence'],robot_captured_at=f.metadata['captured_at'],age_upper_s=f.age_upper_s,cube_top_center_grasp_m=center,cube_top_center_world_m=(fk@np.r_[center,1])[:3],tcp_world_m=fk[:3,3],pixel_center=pixel_center,visible_fragments=len(candidates),selected_component=int(label),ignored_components=len(candidates)-1)
        rows.append(plain(row));save(out/'observations.json',rows)
    after=io.call('state');save(out/'state-after.json',after)
    require(np.max(abs(np.array(after['joints'])-state['joints']))<.01,'Arms moved during wrist observation')
    return rows,after


class CubeProgram:
    @property
    def goals_sha(self):
        return self.__dict__.get('_goals_sha') or resource('goals_sha')

    @goals_sha.setter
    def goals_sha(self,value):
        self._goals_sha=value

    @property
    def controller_only(self):
        return getattr(getattr(self,'args',None),'execution_policy','validated')=='controller-faults'

    def __init__(self,args):
        self.goals_sha=getattr(args,'goals_sha',None) or resource('goals_sha');self.args=args;self.out=Path(args.output);self.report=json.loads(Path(args.calibration).read_text());self.targets=load_targets(args.targets)
        require(self.targets['content_sha256']==self.goals_sha,'The immutable cube goal digest differs');require_binding(self.targets,self.report)
        table=self.targets['task_geometry']
        require(table['source']=='user-provided' and table['task_frame']=='left_arm_base' and table['support_z_m']==0.,'Selected task table reference is not the established left-base z=0 plane')
        self.table_plane_left=[0.,0.,float(table['support_z_m'])]
        workspace_file=getattr(args,'workspace_config',None)
        self.workspace_left_xy_m=load_workspace(workspace_file,self.report) if workspace_file else None
        if workspace_file:
            save(self.out/'workspace-selection.json',dict(config=str(workspace_file),
                config_sha256=hashlib.sha256(Path(workspace_file).read_bytes()).hexdigest(),
                left_xy_bounds_m=self.workspace_left_xy_m,scope='Task cube identification only'))
        self.ref=reference_contact(args.runtime_root);self.ref['candidate_vertical_error_bound_m']=.007
        loader,source=collision_loader_reference(args.runtime_root);self.planner=CubePlanner(self.report,contact_reference=self.ref,collision_model_loader=loader)
        if getattr(args,'planning_profile','legacy')=='qualified':
            self.configure_qualified_planner()
        self.io=None;self.token=None;self.pending=None;self.completed=[];self.events=[];self.motion_count=0;self.startup_in_flight=False;self.startup_completed=False
        save(self.out/'execution-policy.json',dict(execution_policy='controller-faults' if self.controller_only else 'validated',
            observation_failures_advisory=self.controller_only, runtime_geometry_checks=not self.controller_only,
            native_motor_guards=True, explicit_stop=True, movement_retry=False))
        if getattr(args,'accept_late_frames',False) or self.controller_only:
            save(self.out/'frame-policy.json',dict(operator_authorized=True,per_frame_receipt_age_limit_s=5.,
                stability_window='Three distinct exposures while measured arms hold; retained frames may age during sequential transfer',
                require_capture_after_completed_motion=True,native_joint_limits_changed=False,
                runtime_geometry_checks=not self.controller_only))

    def configure_qualified_planner(self):
        """Select the same end-grasp-v11 strategy used in the offline qualification."""
        self.args.allow_staging=True;self.args.allow_initial_object_touch=True;self.args.in_process_geometry_audit=True
        self.planner.destination_yaw_offsets=(0.,math.pi/2,-math.pi/2,math.pi)
        self.planner.geometry_grasps=True;self.planner.bidirectional_primitives=True
        self.planner.pregrasp_clearance_m=.002;self.planner.grasp_offset_m=.015
        self.planner.least_contact_first=True;self.planner.proactive_staging=True

    def plan_remaining(self,state,scene,planning,remaining):
        from .yam_cube_rearrangement import plan_rearrangement
        return plan_rearrangement(self,state,scene,planning,remaining_colors=remaining)

    def compare_qualified_scene(self,scene,targets):
        return compare(scene,targets,self.report['calibration_id'])

    def accept_qualified_placement(self,color,kind,placement):
        require(placement[color]['state']=='already_correct',
            f'{color} did not reach the audited {kind} destination; holding before any further leg')

    def run_qualified_scene(self,scene):
        """Replan from fresh feedback after every audited staging or goal delivery.

        Complete future programs are audited offline, but only their first leg
        is executed. Subsequent legs are replanned from actual camera feedback.
        """
        if self.controller_only:return self.run_controller_only_scene(scene)
        root=self.out;staged={};staging_count=0
        for number in range(1,getattr(self,'live_leg_budget',9)+1):
            comparison=self.compare_qualified_scene(scene,self.targets)
            remaining=[c for c in ('blue','orange','yellow') if comparison[c]['state']!='already_correct']
            if not remaining:return comparison
            # Remember only confirmed staging positions. The camera still
            # supplies every measured coordinate for the next planning round.
            for color,target in staged.items():
                if np.linalg.norm(self.planner.world(scene[color])[:2]-self.planner.world(target)[:2])<=self.targets['position_tolerance_m']:
                    scene[color]['planning_goal_kind']='staging'
            state=self.state();planning=root/f'planning-round-{number:02d}';planning.mkdir()
            try:
                sequence=self.plan_remaining(state,scene,planning,remaining)
            finally:self.out=root
            require(bool(sequence),'Qualified planner returned no complete program for remaining cubes')
            selected=sequence[0];folder=planning/selected['directory']
            plan=self.load_audited_leg(folder)
            color=plan['color'];target=plan['destination_scene_row'];kind=selected['goal_kind']
            if kind=='staging':
                require(staging_count<6,'Live staging budget exhausted; holding without another move')
            # The current controller must still match the plan's measured start.
            now=self.state()
            require(np.max(abs(np.asarray(now['joints'])-state['joints']))<=.01,
                'Arms changed while planning; no trajectory dispatched')
            require(max(abs(now['left_gripper']-state['left_gripper']),abs(now['right_gripper']-state['right_gripper']))<=.02,
                'Grippers changed while planning; no trajectory dispatched')
            latest=self.scene(f'before-leg-{number:02d}')
            for other in ('blue','orange','yellow'):
                require(np.linalg.norm(self.planner.world(latest[other])[:2]-self.planner.world(scene[other])[:2])<=.004,
                    f'{other} moved while planning; no trajectory dispatched')
                yaw=(latest[other]['yaw_rad']-scene[other]['yaw_rad']+math.pi/4)%(math.pi/2)-math.pi/4
                require(abs(yaw)<=math.radians(5),f'{other} rotated while planning; no trajectory dispatched')
            execution=root/f'execution-leg-{number:02d}-{color}';execution.mkdir()
            self.event('qualified_leg_selected',leg_id=number,color=color,goal_kind=kind,audited_plan=str(folder))
            self.out=execution
            try:
                self.execute_plan(plan)
                scene=self.scene('after');save(execution/'planning-scene-after.json',scene)
                expected=copy.deepcopy(self.targets);expected['targets'][color]=target
                placement=self.compare_qualified_scene(scene,expected);save(execution/'placement.json',placement)
                self.accept_qualified_placement(color,kind,placement)
            finally:self.out=root
            if kind=='staging':staged[color]=copy.deepcopy(target);staging_count+=1
            else:staged.pop(color,None)
            self.event('qualified_leg_verified' if placement[color]['state']=='already_correct' else 'qualified_leg_needs_correction',leg_id=number,color=color,goal_kind=kind)
        final=self.compare_qualified_scene(scene,self.targets)
        require(all(r['state']=='already_correct' for r in final.values()),'Live leg budget exhausted; holding')
        return final

    def run_controller_only_scene(self,scene):
        """Execute the complete planned program; observations report outcomes."""
        root=self.out;comparison=compare(scene,self.targets,self.report['calibration_id'])
        remaining=[c for c,row in comparison.items() if row['state']!='already_correct']
        if not remaining:return comparison
        state=self.state();planning=root/'planning-round-01';planning.mkdir()
        try:sequence=self.plan_remaining(state,scene,planning,remaining)
        finally:self.out=root
        require(bool(sequence),'Planner returned no executable program')
        # Load/bind every leg before execution, rather than requiring camera
        # observations to construct the rest of an already running program.
        plans=[self.load_audited_leg(planning/entry['directory']) for entry in sequence]
        self.observations_optional=True
        final={c:dict(state='unverified',reason='No final observation yet') for c in comparison}
        for number,(entry,plan) in enumerate(zip(sequence,plans),1):
            now=self.state()
            if number==1:
                delta=float(np.max(abs(np.asarray(now['joints'])-state['joints'])))
                if delta>.01:self.event('state_warning',joint_change_rad=delta,action='Controller rebases each pose from measured joints')
            color=plan['color'];execution=root/f'execution-leg-{number:02d}-{color}';execution.mkdir()
            self.event('qualified_leg_selected',leg_id=number,color=color,goal_kind=entry['goal_kind'],execution_policy='controller-faults')
            self.out=execution
            try:
                self.execute_plan(plan)
                observed=self.scene('after')
                if observed is not None:
                    save(execution/'planning-scene-after.json',observed)
                    try:
                        final=compare(observed,self.targets,self.report['calibration_id'])
                        save(execution/'placement.json',final)
                        expected=copy.deepcopy(self.targets);expected['targets'][color]=plan['destination_scene_row']
                        placement=compare(observed,expected,self.report['calibration_id'])
                        self.event('placement_observed',color=color,goal_kind=entry['goal_kind'],result=placement[color])
                    except (ResetBlocked,ValueError) as exc:
                        observed=None
                        self.event('placement_warning',color=color,error=str(exc),action='Continue remaining planned legs')
                if observed is None:
                    final={c:dict(state='unverified',reason='Final camera observation unavailable') for c in comparison}
                    self.event('placement_unverified',color=color,action='Continue remaining planned legs')
            finally:self.out=root
        return final

    def load_audited_leg(self,folder):
        """Require the complete current installed-CAD audit and unchanged inputs."""
        audit=json.loads((folder/'installed-audit.json').read_text())
        bindings=audit.get('input_sha256',{})
        required={'result.json','planning-scene.json','controller-state.json','calibration.json','planning-targets.json'}
        auditor=Path(resource('auditor'))
        require(audit.get('complete') is True and audit.get('targets_sha256')==self.goals_sha,
            'Selected live leg lacks a complete audit for the immutable goals')
        require(audit.get('auditor_source_sha256')==hashlib.sha256(auditor.read_bytes()).hexdigest(),
            'Selected live leg was checked by another auditor version')
        require(set(bindings)==required and all(hashlib.sha256((folder/name).read_bytes()).hexdigest()==bindings[name] for name in required),
            'Selected live leg changed after its geometry audit')
        require(audit.get('preview_result_sha256')==bindings['result.json'],'Live preview/audit binding differs')
        record=json.loads((folder/'result.json').read_text())
        require(record['targets_sha256']==self.goals_sha and len(record['plans'])==1,'Unexpected selected live leg')
        return record['plans'][0]

    def event(self,event,**data):
        row=dict(event=event,at=time.time(),**plain(data));self.events.append(row);save(self.out/'events.json',self.events);print(json.dumps(row),flush=True)

    def initialize(self):
        """Use native Home to clear the cameras before a fresh table capture."""
        read=self.io.read if self.controller_only else self.io.call
        initial=read('state');pose=read('pose_status');save(self.out/'startup-before.json',dict(controller=initial,local_pose=pose))
        if getattr(self.args,'after_replay',None):
            from .yam_tabletop_reset import require_replay_handoff
            context=getattr(self.io,'reset_replay_handoff',{})
            previous=context.get('previous_pose') if context.get('request_id')==self.args.after_replay else None
            require_replay_handoff(initial,pose,self.args.after_replay,previous_pose=previous)
            initial=read('state')
            require_replay_handoff(initial,pose,self.args.after_replay,previous_pose=previous)
        if self.controller_only:
            require('controller-faults' in pose.get('supported_execution_policies',[]),
                'Native controller needs the controller-faults policy update; no startup or cube movement submitted')
            check_controller_fault(initial)
        if getattr(self.args,'timing_profile','native') in ('sim-qualified','sim-free'):
            require(pose.get('cube_timing_profile')==CUBE_TIMING_PROFILE and pose.get('completion_wait_supported') is True,'Controller lacks the simulation-qualified timing option; no startup or cube motion requested')
        if self.args.resume_plan:
            require(initial['mode']!='DISABLED','A disabled controller cannot resume a previously held cube')
            return
        if self.controller_only and initial.get('mode') in ('READY','STOPPED') and initial.get('safety',{}).get('drives_enabled') is True:
            q=np.asarray(initial.get('joints',[]),float)
            self.startup_needs_planning_home=(q.shape==(12,) and np.isfinite(q).all()
                and (np.any(q<self.planner.ik.low) or np.any(q>self.planner.ik.high)))
            self.event('startup_current_pose',action='Existing controller enabled; bounded planning start needs Home' if self.startup_needs_planning_home else 'Use current measured pose without automatic Home')
            return
        if initial.get('homed') and initial.get('settled') and initial['mode']=='READY':return
        require(not pose['active'] and not pose['sequence_reserved'],'Existing local-pose owner blocks initialization')
        require(pose['collision_masks_valid'],'Collision model invalid; native startup not requested')
        require(not initial['auto_queue']['enabled'] and not initial['auto_queue']['running'] and not initial['api']['session_id'] and not initial['api']['authorized'],'Queue/API owner blocks initialization')
        require(not initial.get('adapter_fault'),'Controller fault blocks initialization: '+str(initial.get('adapter_fault')))
        command=list(resource('startup_command'))+['launch' if self.controller_only else 'home','--ssh',self.args.ssh,'--identity',self.args.identity,'--json']
        self.event('native_startup',operation='Initialize holding observed pose; Home follows under selected native policy' if self.controller_only else 'Existing guarded Home clears the top-camera view; initializes disabled arms first when needed')
        self.startup_in_flight=True;began=time.monotonic()
        result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=105)
        save(self.out/'startup-harness.json',dict(command=command,exit_code=result.returncode,elapsed_s=time.monotonic()-began,output=result.stdout))
        try:receipt=json.loads(result.stdout)
        except ValueError as exc:raise ResetBlocked('Native startup result uncertain; no retry. See startup-harness.json') from exc
        require(result.returncode==0 and receipt.get('ok') is True,'Native initialization/Home failed; no retry: '+str(receipt.get('error',result.stdout)))
        state=self.state();q=np.asarray(state['joints'],float)
        if self.controller_only:
            self.startup_needs_planning_home=True
            self.startup_in_flight=False;self.startup_completed=True
            save(self.out/'startup-after.json',dict(controller=state,home_pending=True))
            self.event('native_startup_ready',mode=state['mode'],settled=state.get('settled'),home_pending=True)
            return
        require(q.shape==(12,) and np.isfinite(q).all() and np.all(q>=self.planner.ik.low) and np.all(q<=self.planner.ik.high),'Fresh initialized joints exceed unchanged planner bounds')
        self.planner.ik._forward(q)
        contacts=[dict(bodies=[self.planner.ik.model.body(self.planner.ik.model.geom_bodyid[c.geom1]).name,self.planner.ik.model.body(self.planner.ik.model.geom_bodyid[c.geom2]).name],distance_m=float(c.dist)) for c in self.planner.ik.data.contact]
        save(self.out/'startup-after.json',dict(controller=state,contacts=contacts))
        if contacts and self.controller_only:self.event('geometry_warning',contacts=contacts,action='Continue under native motor guards')
        else:require(not contacts,'Fresh initialized pose collides: '+json.dumps(contacts)+'; holding, no cube move')
        self.startup_in_flight=False;self.startup_completed=True;self.event('native_startup_ready',mode=state['mode'],settled=state['settled'],collision_contacts=0)
        if getattr(self.args,'accept_late_frames',False):self.io.motion_completed_robot_wall=self.io.last_robot_wall

    def prepare_planning_start(self):
        """Move to the existing Home when startup feedback cannot seed bounded IK.

        The native controller owns measured-start tolerance and command limits.
        Never clip feedback or expand IK bounds to conceal an invalid start.
        """
        if not self.controller_only or self.args.resume_plan:return
        state=self.state();q=np.asarray(state['joints'],float)
        bounded=(q.shape==(12,) and np.isfinite(q).all()
            and np.all(q>=self.planner.ik.low) and np.all(q<=self.planner.ik.high))
        replay_home=(getattr(self.args,'home_after_replay',False) and getattr(self.args,'after_replay',None)
                     and not getattr(self,'replay_home_completed',False))
        if bounded and not getattr(self,'startup_needs_planning_home',False) and not replay_home:return
        target=np.asarray(state['home_target'],float)
        require(target.shape==(12,) and np.isfinite(target).all()
            and np.all(target>=self.planner.ik.low) and np.all(target<=self.planner.ik.high),
            'Existing calibrated Home is outside unchanged planning bounds')
        self.event('startup_planning_home',reason='User-selected single Home after box replay, before fresh cube scene' if replay_home else 'Native startup or measured start outside bounded IK',
            measured_joints=q.tolist(),home_target=target.tolist(),execution_policy='controller-faults')
        self.startup_in_flight=True
        self.motion('startup',dict(name='home',points_rad=[target.tolist()],
            grippers=[state['left_gripper'],state['right_gripper']]))
        if replay_home:self.replay_home_completed=True
        self.startup_needs_planning_home=False;self.startup_in_flight=False;self.startup_completed=True

    def state(self):
        if self.controller_only:
            s=self.io.read('state');p=self.io.read('pose_status');check_controller_fault(s);check_controller_fault(p)
            if self.token is not None and (s.get('mode') in ('DISABLED','STOPPING') or p.get('cancelled')):
                raise KeyboardInterrupt('Operator stopped or released the local sequence')
            warnings=[name for name,ok in (('feedback unavailable',s.get('feedback_available')),('not settled',s.get('settled')),
                ('collision masks unavailable',p.get('collision_masks_valid'))) if not ok]
            if warnings:self.event('state_warning',warnings=warnings,action='Native controller uses measured feedback for dispatch')
            return s
        s=self.io.call('state');p=self.io.call('pose_status');require(s['mode'] in ('READY','STOPPED','LOCAL_POSE_RESERVED') and s['settled'] and s['feedback_available'],f"Startup admission failed: mode={s['mode']}, settled={s['settled']}, feedback_available={s['feedback_available']}, drives_enabled={s['safety']['drives_enabled']}, controller_ok={s['safety']['controller_ok']}; see startup-before/after/harness receipts")
        require(s['safety']['drives_enabled'] and s['safety']['controller_ok'] and not s.get('adapter_fault'),'Motor health/enable check failed')
        require(not s['auto_queue']['enabled'] and not s['auto_queue']['running'] and not s['api']['session_id'] and not s['api']['authorized'],'Queue/API owner conflicts with cube program')
        require(not p['active'] and p['collision_masks_valid'],'Pose active or collision masks invalid')
        if self.token is None and not self.args.resume_plan:
            require(not p['sequence_reserved'],'Another local-pose sequence owns the robot')
        require(s['joint_calibration']['calibration_id']==self.targets['native_joint_calibration_id'],'Native calibration changed')
        require(s.get('dataset',{}).get('status')=='idle','Recording must remain idle')
        if self.token is not None:require(p['sequence_reserved'],'Sequence ownership lost; no next motion')
        return s

    def scene(self,name):
        started=time.monotonic()
        try:return self._scene_with_policy(name)
        finally:self.event('scene_timing',label=name,wall_s=time.monotonic()-started)

    def _scene_with_policy(self,name):
        if not self.controller_only:return self._scene(name)
        while True:
            self.state()
            try:return self._scene(name)
            except ControllerFault:raise
            except (ResetBlocked,ValueError,OSError,TimeoutError) as exc:
                self.event('observation_unavailable',camera='top',error=str(exc),action='Continue existing program' if getattr(self,'observations_optional',False) else 'Wait for initial planning observation')
                if getattr(self,'observations_optional',False):return None
                time.sleep(.2)

    def _scene(self,name):
        frames=[];history=[];seen=set()
        late = getattr(getattr(self,'args',None),'accept_late_frames',False) or self.controller_only
        before = self.state() if late else None
        for attempt in range(48):
            f=self.io.capture(self.report)
            key=(f.metadata['captured_at'],f.metadata['sequence'])
            if key in seen:
                history.append(dict(attempt=attempt,sequence=key[1],state='DUPLICATE_WAIT'))
                time.sleep(.05)
                continue
            seen.add(key)
            try:
                workspace=getattr(self,'workspace_left_xy_m',None)
                detect(f,support_plane_left=self.table_plane_left,workspace_left_xy_m=workspace,allow_partial_color_occlusion=getattr(self,'allow_partial_color_occlusion',False),refine_measured_top=getattr(self,'refine_measured_top',False),fit_cube_edges_m=getattr(self,'cube_pose_fit_edges_m',None))
                fresh=frames if late else [old for old in frames if 0<=old.age()<2]
                if len(fresh)!=len(frames):history.append(dict(attempt=attempt,state='WINDOW_EXPIRED'))
                frames=(fresh+[f])[-3:]
                scene=stable_scene(frames,support_plane_left=self.table_plane_left,workspace_left_xy_m=workspace,allow_partial_color_occlusion=getattr(self,'allow_partial_color_occlusion',False),refine_measured_top=getattr(self,'refine_measured_top',False),fit_cube_edges_m=getattr(self,'cube_pose_fit_edges_m',None)) if len(frames)==3 else None;history.append(dict(attempt=attempt,sequence=key[1],state='PASS'))
                if scene is not None:
                    if not late and not all(0<=old.age()<2 for old in frames):
                        frames=[old for old in frames if 0<=old.age()<2];history.append(dict(attempt=attempt,state='WINDOW_EXPIRED'));continue
                    save(self.out/(name+'-captures.json'),history);cv2.imwrite(str(self.out/(name+'.jpg')),cv2.cvtColor(f.rgb,cv2.COLOR_RGB2BGR))
                    for color,row in scene.items():
                        if isinstance(row,dict) and row.get('warnings'):self.event('perception_warning',color=color,warnings=row['warnings'])
                    if late:
                        after=self.state()
                        if np.max(abs(np.asarray(after['joints'])-before['joints']))>.01 or max(abs(after[k]-before[k]) for k in ('left_gripper','right_gripper'))>.02:
                            if self.controller_only:self.event('state_warning',action='Arms changed during observation; continue planned program')
                            else:raise RuntimeError('Arms changed during delayed scene capture; no next motion')
                        save(self.out/(name+'-frame-ages.json'),dict(ages_at_scene_completion_s=[f.age() for f in frames],
                            policy='Operator-authorized stationary observations; individual receipt limit5s'))
                    return apply_task_geometry(scene,self.targets['task_geometry'],self.report)
            except (ValueError,ResetBlocked) as exc:frames=[];history.append(dict(attempt=attempt,state='REJECTED',error=str(exc)))
        save(self.out/(name+'-captures.json'),history)
        reason=next((row['error'] for row in reversed(history) if 'error' in row),'Not enough distinct fresh frames')
        raise ResetBlocked('Initial table capture unavailable: '+reason+'; see '+name+'-captures.json')

    def observe(self,color,side,label,*,reference=None):
        started=time.monotonic()
        try:return self._observe_with_policy(color,side,label,reference=reference)
        finally:self.event('wrist_timing',color=color,label=label,wall_s=time.monotonic()-started)

    def _observe_with_policy(self,color,side,label,*,reference=None):
        # Wrist diagnostics already bracket capture with measured state. Native
        # motion admission/fault/Stop stay in the controller; do not repeat
        # client admission for advisory-only observations.
        if not self.controller_only:self.state()
        folder=self.out/(color+'-'+label);attempt=1
        while self.controller_only and folder.exists():
            attempt+=1;folder=self.out/f'{color}-{label}-{attempt:02d}'
        try:return wrist_rows(self.io,self.report,color,side,folder,reference=reference,
            count=1 if self.controller_only else 3)[0]
        except ControllerFault:raise
        except (ResetBlocked,ValueError,OSError,TimeoutError) as exc:
            if not self.controller_only:raise
            self.event('observation_unavailable',camera=side,label=label,color=color,error=str(exc),action='Continue planned stages')
            return None

    def make_plan(self,color,scene,state,resume=None):
        if resume and (resume.parent/'progress.json').exists():
            plan=resume_checkpoint(resume,self.args.resume_audit,state)
            folder=self.out/(color+'-plan');folder.mkdir()
            save(folder/'result.json',dict(plans=[plan],targets_sha256=self.goals_sha))
            save(folder/'planning-scene.json',scene);save(folder/'controller-state.json',state);save(folder/'calibration.json',self.report)
            save(folder/'reused-audit.json',dict(source=str(self.args.resume_audit),original_plan_sha256=plan['resumed_plan_sha256']))
            self.event('confirmed_checkpoint_resumed',color=color,after=plan['resume_after'],next_stage=plan['stages'][0]['name'])
            return plan
        if resume:
            old=json.loads((resume/'result.json').read_text());audit=json.loads(Path(self.args.resume_audit).read_text());digest=hashlib.sha256((resume/'result.json').read_bytes()).hexdigest();progress=json.loads((resume/'execution-blue.json').read_text())
            require(audit['complete'] and audit['preview_result_sha256']==digest and old['targets_sha256']==self.goals_sha,'Resume audit/goal binding failed')
            require(progress['plan_sha256']==digest and progress['next_stage']==5 and not progress.get('pending'),'Resume requires a positively confirmed blue closure, no pending write')
            original=next(p for p in old['plans'] if p['color']=='blue');closed=original['stages'][4];require(closed['name']=='close','Unexpected resume checkpoint')
            require(np.max(abs(np.array(state['joints'])-closed['points_rad'][-1]))<=.01,'Arms moved away from confirmed close checkpoint')
            plan=copy.deepcopy(original);plan['stages']=copy.deepcopy(original['stages'][5:]);idx=0 if plan['arm']=='left' else 1;other=slice(6,12) if idx==0 else slice(0,6)
            for stage in plan['stages']:
                for q in stage['points_rad']:q[other]=state['joints'][other]
                stage['grippers'][1-idx]=[state['left_gripper'],state['right_gripper']][1-idx]
            from remote_yam.resets.kinematics import arm_pose
            pose=arm_pose(self.report,{plan['arm']+'_joints_deg':np.rad2deg(state['joints'][idx*6:idx*6+6])},plan['arm'])
            dummy=dict(name='close',arm=plan['arm'],points_rad=[state['joints']],grippers=[state['left_gripper'],state['right_gripper']],expected_rotation=pose[:3,:3],intended_selected_contact=True,already_confirmed=True)
            plan['stages'].insert(0,dummy)
            return self._audit_candidate(color,scene,state,plan,self.out/(color+'-plan'))
        attempt=0
        def validate(candidate):
            nonlocal attempt
            attempt+=1
            folder=self.out/(color+'-candidates')/f'{attempt:03d}'
            try:
                audited=self._audit_candidate(color,scene,state,candidate,folder)
            except ResetBlocked as exc:
                self.event('candidate_rejected',color=color,attempt=attempt,error=str(exc))
                raise
            # Preserve the exact bytes bound by the successful audit. Downstream
            # checkpoints continue using the ordinary <color>-plan directory.
            shutil.copytree(folder,self.out/(color+'-plan'))
            return audited
        return self.planner.plan_cube(color,scene,self.targets,state['joints'],
            [state['left_gripper'],state['right_gripper']],candidate_validator=validate)

    def _audit_candidate(self,color,scene,state,plan,folder):
        # Compress only paths whose full native-linear sweeps retain all checks.
        q=np.array(state['joints']);idx=0 if plan['arm']=='left' else 1;initial=q.copy();other=slice(6,12) if idx==0 else slice(0,6)
        for stage in plan['stages']:
            original=copy.deepcopy(stage['points_rad']);end=np.array(original[-1]);count=max(1,math.ceil(np.max(abs(end-q))/.005));self.planner.ik._forward(q);startxyz=self.planner.ik._poses()[idx][0].copy();ok=True
            for t in np.linspace(0,1,count+1):
                sample=q+t*(end-q);self.planner.ik._forward(sample)
                try:
                    require(np.array_equal(sample[other],initial[other]) and np.all(sample>=self.planner.ik.low) and np.all(sample<=self.planner.ik.high) and not self.planner.ik.data.ncon,'Direct sweep blocked')
                    tip=self.planner.ik._poses()[idx][0];self.planner.check_cube_clearance(tip,scene,color,carrying=stage.get('carrying',False),contact=stage.get('intended_selected_contact',False),defer_object_clearance=True)
                    if stage['name'] in ('descend','lift_clear','place','retreat_clear'):require(np.linalg.norm(tip[:2]-(startxyz+t*(np.array(stage['expected_tip_world_m'])-startxyz))[:2])<=.002,'Terminal line exceeds2mm')
                except (ValueError,RuntimeError):ok=False;break
            stage['points_rad']=[end.tolist()] if ok else original;q=end
        final_scene=copy.deepcopy(scene);final_scene[color]=self.targets['targets'][color];end=q.copy();end[idx*6:idx*6+6]=state['home_target'][idx*6:idx*6+6];g=list(plan['stages'][-1]['grippers']);g[idx]=1.
        for t in np.linspace(0,1,max(2,math.ceil(np.max(abs(end-q))/.005)+1)):
            self.planner.ik._forward(q+t*(end-q));require(not self.planner.ik.data.ncon,'View-clear return collision');self.planner.check_cube_clearance(self.planner.ik._poses()[idx][0],final_scene,color,carrying=False,contact=False,defer_object_clearance=True)
        plan['stages'].append(dict(name='view_clear',arm=plan['arm'],points_rad=[end.tolist()],grippers=g,carrying=False,intended_selected_contact=False));plan['final_joints']=end.tolist();plan['final_grippers']=g
        folder.mkdir(parents=True);save(folder/'result.json',dict(plans=[plan],targets_sha256=self.goals_sha));save(folder/'planning-scene.json',scene);save(folder/'controller-state.json',state);save(folder/'calibration.json',self.report);save(folder/'contact-reference.json',self.ref)
        if getattr(self.args,'allow_staging',False):
            save(folder/'planning-targets.json',dict(final_task_targets_sha256=self.goals_sha,
                 planning_only=True,targets=self.targets['targets']))
        command=[sys.executable,str(Path(resource('auditor'))),'--runtime-root',str(self.args.runtime_root),'--preview',str(folder),'--parts',str(self.args.parts),'--output',str(folder/'installed-audit.json')]
        if getattr(self.args,'allow_initial_object_touch',False):command.append('--allow-initial-object-touch')
        if getattr(self.args,'allow_staging',False):command.append('--allow-staging')
        if getattr(self.args,'in_process_geometry_audit',False):
            from .yam_cube_study import run_audit
            result=run_audit(command[1],command[2:]+['--reuse-model','--stop-on-failure'])
        else:result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        (folder/'audit-command.txt').write_text(result.stdout)
        if result.returncode not in (0,2):raise RuntimeError('Installed geometry audit unavailable: '+result.stdout[-2000:])
        audit=json.loads((folder/'installed-audit.json').read_text())
        if result.returncode!=0 or not audit['complete']:
            failure=ResetBlocked('Installed geometry audit blocked '+color+': '+result.stdout[-2000:])
            failure.audit_failure_stages=[row['stage'] for row in audit['rows'] if row['state']!='PASS']
            raise failure
        self.event('plan_audited',color=color,audit=audit['summary']);return plan

    def motion(self,color,stage):
        # The selected native policy admits preview/execute from measured
        # feedback and reports faults/Stop through the bound completion wait.
        # Keep the original client admission for validated execution.
        if not self.controller_only:self.state()
        timing={};reached=True
        if self.controller_only:timing.update(execution_policy='controller-faults',wait_for_completion=True)
        if getattr(getattr(self,'args',None),'timing_profile','native')=='sim-qualified' and color!='startup':
            timing.update(duration_floor_s=.8 if stage.get('intended_selected_contact') or stage.get('carrying') else .1,
                        wait_for_completion=True)
        elif getattr(getattr(self,'args',None),'timing_profile','native')=='sim-free':
            timing['wait_for_completion']=True
            # Preserve native Home/contact/carry timing. Only free moves use
            # the same0.1s floor as the fifty-scene qualification.
            if color!='startup' and not stage.get('intended_selected_contact') and not stage.get('carrying'):
                timing['duration_floor_s']=.1
        for index,q in enumerate(stage['points_rad']):
            self.pending=dict(color=color,stage=stage['name'],point=index);save(self.out/'progress.json',dict(pending=self.pending,confirmed=self.completed))
            began=time.monotonic()
            result=execute_pose(self.io,q,stage['grippers'],owner_token=self.token,**timing);self.motion_count+=1;save(self.out/f'motion-{self.motion_count:03d}.json',dict(pending=self.pending,result=result,timing=timing,command_wall_s=time.monotonic()-began));self.pending=None;save(self.out/'progress.json',dict(pending=None,confirmed=self.completed))
            if result.get('reached_target') is False:
                reached=False;self.event('motion_warning',color=color,stage=stage['name'],result=result)
        row=dict(color=color,stage=stage['name'],at=time.time())
        if self.controller_only:row['reached_target']=reached
        self.completed.append(row);save(self.out/'progress.json',dict(pending=None,confirmed=self.completed));self.event('stage_confirmed' if reached else 'stage_finished_with_warning',color=color,stage=stage['name'])

    def execute_plan(self,plan,resume=False):
        # Initial RGB-D + declared 30mm/table0 supply the geometry. Wrist
        # observations verify pickup/carry outcomes, not pregrasp admission.
        color=plan['color'];side=plan['arm'];before=None;pickup=None
        if resume:
            before=self.observe(color,side,'resume-contact')
            if plan.get('resume_after') in ('lift_clear','lift','transfer','place_align','place'):pickup=before
        for stage in plan['stages']:
            name=stage['name']
            if stage.get('already_confirmed'):continue
            if name in ('transfer','place_align','place') and not self.controller_only:require(pickup is not None,'Pickup must be verified before transfer')
            self.motion(color,stage)
            if name=='close':before=self.observe(color,side,'closed')
            if name in ('lift_clear','lift') and pickup is None:
                if not self.controller_only:require(before is not None,'Missing pre-lift observation')
                rows=self.observe(color,side,'pickup',reference=before);pickup=rows
                if before is not None and rows is not None:self.event('pickup_observed',color=color,**verify_pickup(before,rows))
            if name=='transfer':
                rows=self.observe(color,side,'after-transfer',reference=pickup)
                if pickup is not None and rows is not None:self.event('carry_observed',color=color,**verify_carry(pickup,rows))
            if name=='release':
                aperture=self.state()[side+'_gripper'];requested=stage.get('grippers',[1.,1.])[0 if side=='left' else 1]
                self.event('release_observed',color=color,gripper_aperture=aperture,requested_aperture=requested,
                    warnings=['Jaws did not reach the planned release opening; release outcome uncertain'] if aperture<requested-.05 else [])

    def run(self,io=None):
        connection=RobotIO(self.args.ssh,self.args.identity,self.out/'transport',accept_late_frames=getattr(self.args,'accept_late_frames',False) or self.controller_only) if io is None else nullcontext(io)
        with connection as io:
            self.io=io
            try:
                self.initialize()
                s=self.state();tokenfile=Path(self.args.owner_file) if self.args.owner_file else self.out/'.sequence-owner.json'
                if self.args.resume_plan and tokenfile.exists():
                    self.token=json.loads(tokenfile.read_text())['owner_token'];self.state()
                else:
                    response=io.call('reserve',{'execution_policy':'controller-faults'} if self.controller_only else {});self.token=response['owner_token'];fd=os.open(tokenfile,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                    with os.fdopen(fd,'w') as stream:json.dump({'owner_token':self.token},stream)
                if getattr(self.args,'after_replay',None):
                    # reserve resets its old cancellation Event, but preserves
                    # command_source/event. A Stop just before reserve must
                    # therefore still block Home; a later Stop revokes token.
                    from .yam_tabletop_reset import require_replay_handoff
                    reserved_state=io.call('state');reserved_pose=io.call('pose_status')
                    save(self.out/'replay-reserved.json',dict(controller=reserved_state,local_pose=reserved_pose))
                    require_replay_handoff(reserved_state,reserved_pose,self.args.after_replay,reserved=True)
                self.prepare_planning_start()
                scene=None if self.args.resume_plan else self.scene('initial')
                if getattr(self.args,'planning_profile','legacy')=='qualified':
                    final=self.run_qualified_scene(scene)
                else:
                    for color in ('blue','orange','yellow'):
                        resume=Path(self.args.resume_plan) if color=='blue' and self.args.resume_plan else None
                        if resume:scene=json.loads((resume/'planning-scene.json').read_text())
                        else:
                            comparison=compare(scene,self.targets,self.report['calibration_id'])
                            if comparison[color]['state']=='already_correct':self.event('already_correct',color=color);continue
                        plan=self.make_plan(color,scene,self.state(),resume=resume);self.state();self.execute_plan(plan,resume=bool(resume));scene=self.scene(color+'-after');comparison=compare(scene,self.targets,self.report['calibration_id']);save(self.out/(color+'-placement.json'),comparison)
                        self.event('placement_verified' if comparison[color]['state']=='already_correct' else 'placement_warning',color=color,result=comparison[color])
                    final=compare(scene,self.targets,self.report['calibration_id'])
                goals_reached=all(r['state']=='already_correct' for r in final.values())
                outcome='complete' if goals_reached else 'completed_unverified' if any(r['state']=='unverified' for r in final.values()) else 'completed_with_deviations'
                io.call('release',{'owner_token':self.token});self.token=None;tokenfile.unlink(missing_ok=True);save(self.out/'result.json',dict(state=outcome,goals_reached=goals_reached,goals_sha256=self.goals_sha,comparison=final,motion_commands=self.motion_count,execution_policy='controller-faults' if self.controller_only else 'validated',terminal='Torque hold following selected execution policy; queue paused'));self.event(outcome,motion_commands=self.motion_count,comparison=final);return 0
            except BaseException as exc:
                hold=None
                if self.token is not None or self.motion_count or self.pending is not None or getattr(self,'startup_in_flight',False):
                    try:hold=io.emergency_hold()
                    except Exception as hold_error:hold={'unconfirmed':str(hold_error)}
                else:hold={'not_requested':'No cube sequence owned or cube pose submitted; native startup completed and is holding' if getattr(self,'startup_completed',False) else 'No sequence owned and no motor write dispatched; existing robot state unchanged'}
                if hold.get('state')=='held' and 'tokenfile' in locals():tokenfile.unlink(missing_ok=True)
                save(self.out/'result.json',dict(state='cancelled' if isinstance(exc,KeyboardInterrupt) else 'failed',error=str(exc),pending=self.pending,motion_commands=self.motion_count,hold=hold,action='Inspect retained evidence and supported robot pose. Do not resend a pending/uncertain movement. No torque-off or Park was commanded.'))
                self.event('failed_holding' if hold.get('state')=='held' else 'failed_before_motion' if not self.motion_count and self.pending is None else 'hold_unconfirmed',error=str(exc),hold=hold);return 130 if isinstance(exc,KeyboardInterrupt) else 2

    def sense_only(self):
        """Read current state and scene; never initialize, reserve or move."""
        with RobotIO(self.args.ssh,self.args.identity,self.out/'transport',accept_late_frames=getattr(self.args,'accept_late_frames',False) or self.controller_only) as io:
            self.io=io
            save(self.out/'controller-state.json',io.call('state'))
            save(self.out/'pose-status.json',io.call('pose_status'))
            scene=self.scene('initial');save(self.out/'planning-scene.json',scene)
            save(self.out/'result.json',dict(state='sensed',physical_motion_sent=False,goals_sha256=self.goals_sha,
                comparison=compare(scene,self.targets,self.report['calibration_id'])))
        self.event('sensed',physical_motion_sent=False);return 0

    def dry_run(self,state,scene):
        if getattr(self.args,'planning_profile','legacy')=='qualified':
            from .yam_cube_rearrangement import plan_rearrangement
            root=self.out
            try:sequence=plan_rearrangement(self,copy.deepcopy(state),copy.deepcopy(scene),root)
            finally:self.out=root
            save(root/'planning-result.json',dict(passed=True,planning_sequence=sequence,hardware_commands=0))
            save(root/'result.json',dict(state='dry_run_passed',physical_motion_sent=False,planning_sequence=sequence,
                scope='Offline geometry and orchestration; live execution must Home, sense and replan'))
            return 0
        for color in ('blue','orange','yellow'):
            resume=Path(self.args.resume_plan) if color=='blue' and self.args.resume_plan else None
            plan=self.make_plan(color,scene,state,resume=resume);state=copy.deepcopy(state);state['joints']=plan['final_joints'];state['left_gripper'],state['right_gripper']=plan['final_grippers'];scene=copy.deepcopy(scene);scene[color]=self.targets['targets'][color]
        save(self.out/'result.json',dict(state='dry_run_passed',physical_motion_sent=False,scope='Recorded geometry and orchestration only; live runtime sensing remains required'));return 0
