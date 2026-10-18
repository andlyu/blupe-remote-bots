"""Size-aware planning shared with the live native-API cube runner.

Real execution retains the existing measured RGB-D perception, controller
ownership, timing, motor protections and selected execution policy. It does not
use the simulator's perfect top-plane fit, known initial yaw, or object state.
"""
from __future__ import annotations
import copy
import hashlib
import json
import time
from .yam_cube_contact import contact_for_cube
from .yam_cube_feedback_geometry import neighbor_side_arm,retarget_source,fit_scene_nonpenetration
from .yam_cube_program import CubeProgram,save
from .yam_cube_reset import ResetBlocked
from .yam_cube_sizes import resize_targets,resize_scene,validate_edges


def configure_size_aware(program,edges):
    program.cube_edges_m=validate_edges(edges)
    program.allow_partial_color_occlusion=True
    program.refine_measured_top=False
    program.cube_pose_fit_edges_m=program.cube_edges_m.copy()
    program.targets=resize_targets(program.targets,program.cube_edges_m,program.report)
    planner=program.planner
    program.ref['candidate_vertical_error_bound_m']=getattr(program.args,'feedback_vertical_error_mm',2.)/1000
    original=copy.deepcopy(program.ref);original['candidate_vertical_error_bound_m']=.007
    # Retain the established30mm grip depth. Smaller cubes lower the TCP until
    # the same native tip/floor clearance is reached, instead of raising pads
    # above the25mm cube or unnecessarily lowering a successful30mm grasp.
    program.ref['preferred_tcp_depth_below_top_m']=.030-contact_for_cube(.030,original)['tcp_height_above_support_m']
    planner.pregrasp_clearance_m=.010
    planner.pregrasp_extra_open_gap_m=getattr(program.args,'feedback_extra_open_gap_mm',20.)/1000
    planner.grasp_offset_m=.008
    planner.prefer_centered_grasps=True
    # Native close/carry position target. The separate bounded CAD contact
    # hypothesis models object-blocked jaws; it is not force calibration.
    planner.grasp_command_gap_m=getattr(program.args,'feedback_close_gap_mm',20.)/1000
    planner.grasp_compression_m=.0005
    planner.grasp_gap_relief_m=getattr(program.args,'feedback_grip_relief_mm',0.)/1000
    planner.preserve_carry_orientation=True
    planner.allow_corner_grasps=False
    planner.preserve_pickup_clearance_m=.075
    planner.allow_goal_blocker_staging=True
    planner.proactive_staging=False


class SizeAwarePlanning:
    def run_pickup_feedback(self,nominal_scene,reference_plans):
        """Sense each pickup, solve/audit its correction, then verify placement.

        References only warm-start IK. All observations use ordinary RGB-D;
        acknowledged placement misses can receive a newly sensed corrective
        leg. The physical CLI does not select this opt-in entrypoint.
        """
        root=self.out
        records=[]
        latest_estimate=copy.deepcopy(nominal_scene)

        def observe(name):
            measured=self.scene(name)
            if measured is None:return None
            # Resolve subpixel RGB-D overlap in the estimate, not in physics.
            # Measured headings and heights remain inputs; no ideal pose/yaw.
            return fit_scene_nonpenetration(measured,self.report)

        def deliver_to_selected_target(color,reference=None):
            nonlocal latest_estimate
            number=len(records)+1
            observed=observe(f'feedback-{number:02d}-before')
            state=self.state()
            if observed is None:
                observed=copy.deepcopy(latest_estimate)
                self.event('pickup_feedback_unavailable',color=color,action='Use existing estimated scene; no privileged correction')
            else:latest_estimate=copy.deepcopy(observed)
            save(root/f'feedback-{number:02d}-scene.json',observed)
            folder=root/f'feedback-{number:02d}-{color}-plan'
            planning_started=time.monotonic()
            try:
                plan=None
                if reference is not None:
                    try:
                        reference_source=reference.get('source_scene_row',nominal_scene[color])
                        corrected=retarget_source(self.planner,reference,reference_source,observed[color],state,scene=observed)
                        corrected['pickup_feedback']=dict(source='ordinary calibrated RGB-D scene',
                            reference_plan_sha256=hashlib.sha256(json.dumps(reference,sort_keys=True).encode()).hexdigest())
                        plan=self._audit_candidate(color,observed,state,corrected,folder)
                        strategy='reference pickup corrected by measured RGB-D and IK'
                    except ResetBlocked as exc:
                        self.event('corrected_reference_rejected',color=color,error=str(exc),action='Search existing planner from the fresh observed scene')
                if plan is None:
                    self.out=root/f'feedback-{number:02d}-{color}-search'
                    self.out.mkdir()
                    try:plan=self.make_plan(color,observed,state)
                    finally:self.out=root
                    strategy='existing planner from measured RGB-D'
            finally:
                self.event('planning_timing',color=color,wall_s=time.monotonic()-planning_started)
            self.out=root/f'feedback-{number:02d}-{color}-execution'
            self.out.mkdir()
            self.event('pickup_feedback_selected',leg_id=number,color=color,strategy=strategy)
            try:self.execute_plan(plan)
            finally:self.out=root
            records.append(dict(leg_id=number,color=color,strategy=strategy,
                correction=plan.get('camera_source_correction')))

        def deliver(color,reference=None):
            original_targets=self.targets
            edges=getattr(self,'cube_edges_m',dict.fromkeys(('blue','orange','yellow'),.030))
            destination={} if reference is None else reference.get('destination_scene_row',{})
            if 'visible_top_center_by_arm' in destination:
                self.targets=copy.deepcopy(original_targets)
                self.targets['targets'][color]=resize_scene({color:destination},edges,self.report)[color]
            try:
                # A30mm reference is not a25mm grasp. Rebuild its contact and
                # placement geometry from the current measured, declared size.
                reference_edge=.030 if reference is None else reference.get('qualification_cube_edges_m',{}).get(color,.030)
                reusable=bool(reference and reference.get('stages') and abs(reference_edge-edges[color])<1e-12)
                deliver_to_selected_target(color,reference if reusable else None)
            finally:self.targets=original_targets

        for reference in reference_plans:
            deliver(reference['color'],reference)
        final=observe('feedback-final')
        comparisons=[]
        # Regrasp only observed misses of the original task tolerance. These
        # are newly observed, fully audited moves after completed
        # commands, never retries of a pending or timed-out movement.
        for correction_number in range(3):
            if final is None:break
            latest_estimate=copy.deepcopy(final)
            comparison=self.compare_qualified_scene(final,self.targets)
            comparisons.append(comparison)
            tolerance_m=self.targets['position_tolerance_m']
            remaining=[c for c,row in comparison.items() if row['position_error_m']>tolerance_m]
            if not remaining:break
            color=max(remaining,key=lambda c:comparison[c]['position_error_m'])
            self.event('placement_correction_planned',color=color,
                observed_error_m=comparison[color]['position_error_m'],controller_arrival_band_m=tolerance_m,
                original_goal_tolerance_m=self.targets['position_tolerance_m'])
            deliver(color)
            final=observe(f'feedback-final-correction-{correction_number+1:02d}')
        save(root/'pickup-feedback.json',dict(legs=records,final_scene=final,comparisons=comparisons,
             source='Rendered or real RGB-D through the same detector; no object-state correction'))
        return records

    def _audit_candidate(self,color,scene,state,plan,folder):
        plan['qualification_cube_edges_m']=self.cube_edges_m.copy()
        if 'camera_source_correction' not in plan:
            plan=retarget_source(self.planner,plan,scene[color],scene[color],state,scene=scene)
        clearance_m=getattr(self.args,'feedback_robot_clearance_mm',1.)/1000
        plan['candidate_robot_clearance_xy_m']=clearance_m
        audited=super()._audit_candidate(color,scene,state,plan,folder)
        from .yam_cube_uncertainty import audit_planning_envelope
        arm_clearance_m=getattr(self.args,'feedback_inactive_arm_clearance_mm',2.)/1000
        passed,clearance=audit_planning_envelope(self.args.runtime_root,folder,self.args.parts,clearance_m,
                                               inactive_arm_clearance_m=arm_clearance_m)
        if not passed:
            error=ResetBlocked(f'Additional{clearance_m*1000:g}mm robot clearance blocked '+color)
            error.audit_failure_stages=[row['stage'] for row in clearance['rows'] if row['state']!='PASS']
            raise error
        self.event('robot_clearance_audited',color=color,clearance_xy_m=clearance_m,
                   inactive_arm_clearance_m=arm_clearance_m)
        return audited

    def make_plan(self,color,scene,state,resume=None):
        previous=getattr(self.planner,'preferred_pick_arm',None)
        old_centered=self.planner.prefer_centered_grasps
        old_offset=self.planner.grasp_offset_m
        old_candidates=getattr(self.planner,'grasp_offset_candidates_m',None)
        from .yam_cube_touch import scene_boxes
        from .yam_cube_scenes import box_separation
        boxes=scene_boxes(scene,self.planner.spacing);selected=boxes[color]
        crowded=any(box_separation(selected['center'],selected['rotation'],selected['half_size'],row['center'],row['rotation'],row['half_size'])<.004 for other,row in boxes.items() if other!=color)
        if crowded:
            offset_m=getattr(self.args,'feedback_crowded_offset_mm',0.)/1000
            self.planner.prefer_centered_grasps=offset_m==0.
            self.planner.grasp_offset_m=offset_m
            self.planner.grasp_offset_candidates_m=tuple(dict.fromkeys((offset_m,.003,.006,.008,0.)))
        if getattr(self.args,'feedback_arm_policy','neighbor-side')=='neighbor-side':
            self.planner.preferred_pick_arm=neighbor_side_arm(self.planner,color,scene)
        try:return super().make_plan(color,scene,state,resume=resume)
        finally:
            self.planner.preferred_pick_arm=previous
            self.planner.prefer_centered_grasps=old_centered
            self.planner.grasp_offset_m=old_offset
            self.planner.grasp_offset_candidates_m=old_candidates


class SizeAwareCubeProgram(SizeAwarePlanning,CubeProgram):
    def __init__(self,args):
        super().__init__(args)
        edges=getattr(args,'cube_edges_m',dict.fromkeys(('blue','orange','yellow'),.030))
        configure_size_aware(self,edges)
        save(self.out/'size-aware-profile.json',dict(cube_edges_m=self.cube_edges_m,
            pregrasp_clearance_m=.010,pregrasp_extra_open_gap_m=self.planner.pregrasp_extra_open_gap_m,
            pregrasp_gap_for30mm_m=.040+self.planner.pregrasp_extra_open_gap_m,grasp_compression_m=self.planner.grasp_compression_m,
            grasp_gap_relief_m=self.planner.grasp_gap_relief_m,
            commanded_close_gap_m=self.planner.grasp_command_gap_m,
            modeled_contact_gap_by_color_m={c:edge-self.planner.grasp_compression_m+self.planner.grasp_gap_relief_m for c,edge in self.cube_edges_m.items()},
            closure_semantics='20mm native position command; separate object-blocked CAD contact hypothesis; no measured grip force',
            preferred_tcp_depth_below_top_m=self.ref['preferred_tcp_depth_below_top_m'],
            vertical_planning_reserve_m=self.ref['candidate_vertical_error_bound_m'],
            minimum_installed_tip_floor_clearance_m=.005,
            perception='Known-size full RGB-D silhouette/surface fit in native factory projection; measuredXYZ/yaw, no ideal top-plane or supplied heading',
            execution_policy=args.execution_policy,timing_profile=args.timing_profile,
            qualification='Targeted nominal simulation only; complete50-layout/10mm robustness unfinished'))


class PickupFeedbackCubeProgram(SizeAwareCubeProgram):
    """Explicit live entrypoint using the existing startup/owner/Stop handling."""
    def __init__(self,args):
        super().__init__(args)
        save(self.out/'live-feedback-route.json',dict(profile='pickup-feedback',
            entrypoint='PickupFeedbackCubeProgram.run_qualified_scene -> SizeAwarePlanning.run_pickup_feedback',
            lifecycle='Existing CubeProgram.run startup, reservation, native dispatch, Stop/fault handling and release',
            sensor='Real calibrated RGB-D; no simulator pose or supplied heading'))

    def staged_feedback_references(self,scene,remaining):
        """Reuse the existing scheduler; every reference keeps its own source.

        A central placement/regrasp can join source and goal regions that lack
        a complete same-arm path. References remain warm starts: ordinary fresh
        RGB-D and the unchanged candidate audits still determine each move.
        """
        from .yam_cube_rearrangement import plan_rearrangement
        root=self.out;targets=self.targets
        previous=getattr(self.planner,'proactive_staging',False)
        folder=root/'staging-feedback-planning';folder.mkdir()
        started=time.monotonic()
        try:
            self.planner.proactive_staging=True
            sequence=plan_rearrangement(self,self.state(),scene,folder,remaining_colors=remaining)
        finally:
            self.out=root;self.targets=targets;self.planner.proactive_staging=previous
            self.event('planning_timing',phase='staging_program',wall_s=time.monotonic()-started)
        plans=[]
        for entry in sequence:
            leg=folder/entry['directory']
            plan=copy.deepcopy(self.load_audited_leg(leg))
            source=json.loads((leg/'planning-scene.json').read_text())
            plan['source_scene_row']=source[plan['color']]
            plans.append(plan)
        save(root/'staging-feedback-sequence.json',sequence)
        return plans

    def run_qualified_scene(self,scene):
        comparison=self.compare_qualified_scene(scene,self.targets)
        remaining=[c for c in ('blue','orange','yellow') if comparison[c]['state']!='already_correct']
        if not remaining:return comparison
        root=getattr(self.args,'feedback_reference_root',None)
        nominal=scene
        plans=[dict(color=c) for c in remaining]
        if getattr(self.args,'staging_feedback',False):
            plans=self.staged_feedback_references(scene,remaining)
            root=None
        elif root is not None:
            nominal=json.loads((root/'initial-scene.json').read_text())
            references=json.loads((root/'original-plans.json').read_text())
            plans=[p for p in references if p['color'] in remaining]
            save(self.out/'feedback-reference.json',dict(root=str(root),
                inputs_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest()
                    for name in ('initial-scene.json','original-plans.json')},
                use='IK warm start only; fresh measured scene and joint state, nominal and extra path audits required'))
        self.observations_optional=True
        self.event('pickup_feedback_live_selected',remaining_colors=remaining,
                   reference_warm_start=root is not None,execution_policy=self.args.execution_policy)
        self.run_pickup_feedback(nominal,plans)
        result=json.loads((self.out/'pickup-feedback.json').read_text())
        if result['final_scene'] is None:
            return {c:dict(state='unverified',reason='Final camera observation unavailable') for c in comparison}
        return self.compare_qualified_scene(result['final_scene'],self.targets)
