"""Offline, sequential YAM cube-reset IK with explicit planning limitations."""
from __future__ import annotations
from .station import resource

import math
import copy
import json
import hashlib
import importlib.util
from pathlib import Path
import numpy as np

from .yam_cube_reset import COLORS, ResetBlocked, plain


def enable_collision_masks(model):
    """Keep MuJoCo body broad-phase masks consistent with enabled geometry.

    See vendored MuJoCo simulation.rst, runtime model changes. Setting only
    geom masks silently leaves robot bodies filtered out of collision checks.
    """
    enabled = model.geom_group == 0
    model.geom_contype[enabled] = 1
    model.geom_conaffinity[enabled] = 1
    for geom_field, body_field in (("geom_contype", "body_contype"),
                                    ("geom_conaffinity", "body_conaffinity")):
        masks = np.zeros(model.nbody, dtype=int)
        np.bitwise_or.at(masks, model.geom_bodyid, getattr(model, geom_field))
        getattr(model, body_field)[:] = masks


class CubePlanner:
    def __init__(self, report, *, contact_reference, collision_model_loader=None):
        import mujoco
        from remote_yam.mujoco_ik import BimanualRelativeIK
        from remote_yam.resets.kinematics import arm_pose
        self.report = report
        self.contact_reference = contact_reference
        station = resource('station_geometry')
        native = report["native_joint_calibration"]
        if (native["coordinate_convention"] != "native_i2rt_updated"
                or native["calibration_id"] != station["joint_limits"]["calibration_id"]
                or any(native["additional_offsets_rad"][arm] != [0.]*6 for arm in ("left","right"))):
            raise ResetBlocked("Native joint calibration does not match the existing planner")
        self.spacing = report["base_geometry"]["spacing_m"]
        if not np.isclose(self.spacing, station["base_spacing_m"]):
            raise ResetBlocked("Camera and station base spacing disagree")
        self.ik = BimanualRelativeIK(base_spacing_m=self.spacing,
                                     joint_limits=station["joint_limits"])
        if collision_model_loader is None:
            raise ResetBlocked("A validated collision-model loader is required; legacy masks/assembly are unsafe")
        # Compile static-base ownership and spacing before forward kinematics.
        # Keep canonical source/hash checks and the existing bounds in the IK.
        self.ik.model = collision_model_loader(self.ik.scene_path, base_spacing_m=self.spacing)
        self.ik.data = mujoco.MjData(self.ik.model)
        self.ik.body_ids = tuple(self.ik.model.body(side+"_grasp").id for side in ("left","right"))
        names=[f"{side}_joint{i}" for side in ("left","right") for i in range(1,7)]
        qpos=np.array([self.ik.model.joint(name).qposadr[0] for name in names])
        dofs=np.array([self.ik.model.joint(name).dofadr[0] for name in names])
        if not np.array_equal(qpos,self.ik.qpos_indices) or not np.array_equal(dofs,self.ik.dof_indices):
            raise ResetBlocked("Collision model changed native joint indexing")
        # Compare both sides of the geometry contract; no extra encoder shift.
        for q in (np.zeros(12), (self.ik.low+self.ik.high)*.4):
            self.ik._forward(q)
            for i, arm in enumerate(("left","right")):
                expected = arm_pose(report,{arm+"_joints_deg":np.rad2deg(q[i*6:i*6+6])},arm)
                position, rotation = self.ik._poses()[i]
                if (np.linalg.norm(position-expected[:3,3]) > 1e-5
                        or np.linalg.norm(rotation-expected[:3,:3]) > 1e-5):
                    raise ResetBlocked("Published camera FK and planner model disagree")

    def world(self, row):
        point = np.array(row["visible_top_center_by_arm"]["left"]["top_center_m"])
        point[1] += self.spacing/2
        return point

    def path(self,q,arm,goal,rotation,scene,selected,**flags):
        cache=getattr(self,'_path_cache',None)
        if cache is None:return self._path(q,arm,goal,rotation,scene,selected,**flags)
        context=hashlib.sha256(json.dumps(plain(scene),sort_keys=True).encode()).digest()
        key=(context,np.asarray(q).tobytes(),arm,np.asarray(goal).tobytes(),np.asarray(rotation).tobytes(),selected,tuple(sorted(flags.items())))
        if key in cache:
            ok,value=cache[key]
            if not ok:raise value[0](*value[1])
            return copy.deepcopy(value)
        try:value=self._path(q,arm,goal,rotation,scene,selected,**flags)
        except (ValueError,RuntimeError) as exc:
            cache[key]=(False,(type(exc),exc.args));raise
        cache[key]=(True,copy.deepcopy(value));return value

    def _path(self, q, arm, goal, rotation, scene, selected, *, carrying=False, contact=False, cartesian=True, defer_object_clearance=False):
        from scipy.spatial.transform import Rotation, Slerp
        self.ik._forward(q)
        i = 0 if arm == "left" else 1
        active, other = slice(i*6,i*6+6), slice((1-i)*6,(1-i)*6+6)
        poses = self.ik._poses()
        start, initial_rotation = poses[i]
        angle = Rotation.from_matrix(rotation@initial_rotation.T).magnitude()
        steps = max(1,math.ceil(np.linalg.norm(goal-start)/.008),math.ceil(angle/.10)) if cartesian else 1
        interpolate = Slerp([0,1],Rotation.from_matrix([initial_rotation,rotation]))
        points=[]
        previous=q.copy()
        for alpha in np.linspace(1/steps,1,steps):
            target=list(poses)
            wanted=start+alpha*(goal-start)
            wanted_r=interpolate(alpha).as_matrix()
            target[i]=(wanted,wanted_r)
            solved=self.ik._solve(previous,tuple(target))
            solved[other]=q[other]  # The inactive arm is held, never used to help IK.
            self.ik._forward(solved)
            tip, actual_r=self.ik._poses()[i]
            if np.linalg.norm(tip-wanted)>.002 or Rotation.from_matrix(wanted_r@actual_r.T).magnitude()>.01:
                raise ResetBlocked("IK position/orientation residual exceeds tolerance")
            # Check the full joint interpolation used by the local pose endpoint,
            # including intermediate arm-arm, arm-floor and model self contacts.
            subdivisions=max(1,math.ceil(np.max(abs(solved-previous))/.005))
            for beta in np.linspace(0,1,subdivisions+1):
                sample=previous+beta*(solved-previous)
                self.ik._forward(sample)
                if self.ik.data.ncon:
                    raise ResetBlocked("Swept robot collision in canonical model")
                sample_tip=self.ik._poses()[i][0]
                self.check_cube_clearance(sample_tip,scene,selected,carrying=carrying,contact=contact,
                                          defer_object_clearance=defer_object_clearance)
            points.append(solved.copy());previous=solved
        return points

    def check_cube_clearance(self, tip, scene, selected, *, carrying, contact, defer_object_clearance=False):
        source=scene[selected]
        uncertainty=float(getattr(self,'position_uncertainty_xy_m',0.))
        if not math.isfinite(uncertainty) or uncertainty<0:raise ResetBlocked('Invalid planar planning uncertainty')
        radius=max(.035,float(np.linalg.norm(source["dimensions_m"])/2)+.006)+uncertainty
        for color,row in scene.items():
            # The circle is a conservative broad phase, not evidence that a
            # particular jaw orientation collides. A mandatory installed-CAD
            # candidate validator can resolve this ambiguity before selection.
            if defer_object_clearance:
                continue
            center=self.world(row)
            if color==selected and (contact or carrying):
                continue
            # Conservative footprint for jaws plus carried block, at every sweep.
            separation=radius+np.linalg.norm(row["dimensions_m"])/2+.008+uncertainty
            if np.linalg.norm(tip[:2]-center[:2]) < separation and tip[2] < center[2]+.07:
                raise ResetBlocked(f"Transfer/gripper envelope intersects {color}")
        if carrying and not contact:
            support=np.array(source["visible_top_center_by_arm"]["left"]["support_point_m"])
            from .yam_cube_contact import contact_for_cube
            height=self.world(source)[2]-support[2]
            offset=contact_for_cube(height,self.contact_reference)["tcp_height_above_support_m"]
            # Under the provisional rigid grasp, the cube bottom is below the
            # API grasp origin. Preserve the 4mm carried-object clearance gate.
            if tip[2]-offset<support[2]+.004:
                raise ResetBlocked("Held cube path lacks measured table clearance")

    def plan_cube(self, color, scene, targets, joints, grippers, *, candidate_validator=None):
        """Try explicitly enabled destination orientations without changing goals.

        Default is the original fixed-orientation search. The simulation study
        enables quarter turns of the carried square cube; every attempted path
        still passes the same IK, joint, sweep, clearance and installed-CAD audit.
        """
        # This cache lives for one immutable scene/goal/start call only. It
        # reuses identical source prefixes across destination searches, never
        # bypassing a selected candidate's complete installed-CAD audit.
        shared=getattr(self,'shared_path_cache',None)
        self._path_cache=(shared if shared is not None else {}) if getattr(self,'cache_paths',False) else None
        try:return self._search_cube(color,scene,targets,joints,grippers,candidate_validator=candidate_validator)
        finally:self._path_cache=None

    def _search_cube(self,color,scene,targets,joints,grippers,*,candidate_validator):
        if getattr(self,'geometry_grasps',False):
            from .yam_cube_grasps import geometry_plan_cube
            return geometry_plan_cube(self,color,scene,targets,joints,grippers,candidate_validator)
        failures=[]
        free_yaws=getattr(self,'destination_grasp_yaws',None)
        if free_yaws is not None:
            if candidate_validator is None:raise ResetBlocked('Free destination yaw requires full installed geometry validation')
            for margin in getattr(self,'transfer_height_margins',(.12,)):
                if not math.isfinite(margin) or not .05<=margin<=.20:
                    raise ResetBlocked('Transfer height margin must be between50 and200mm')
                for yaw in free_yaws:
                    if not math.isfinite(yaw):raise ResetBlocked('Destination grasp yaw must be finite')
                    try:
                        return self._plan_cube(color,scene,targets,joints,grippers,candidate_validator=candidate_validator,
                            destination_grasp_yaw_rad=yaw,transfer_height_margin_m=margin)
                    except ResetBlocked as exc:failures.append(f'height{margin:.3f}/destination yaw{yaw:.3f}: {exc}')
            raise ResetBlocked('No complete free-yaw cube path: '+' | '.join(failures))
        for turn in getattr(self,'destination_yaw_offsets',(0.,)):
            if not math.isfinite(turn) or min(abs(turn-v) for v in (0.,math.pi/2,-math.pi/2,math.pi))>1e-9:
                raise ResetBlocked('Destination turns must preserve the square footprint (quarter turns only)')
            try:
                return self._plan_cube(color,scene,targets,joints,grippers,
                    candidate_validator=candidate_validator,destination_yaw_offset_rad=turn)
            except ResetBlocked as exc:
                failures.append(f'destination turn{turn:.3f}: {exc}')
        raise ResetBlocked('No complete cube path: '+' | '.join(failures))

    def _plan_cube(self, color, scene, targets, joints, grippers, *, candidate_validator=None,
                   destination_yaw_offset_rad=0.,destination_grasp_yaw_rad=None,transfer_height_margin_m=.12):
        """Select a complete path; optional validator must return its audited plan.

        Without a validator, retain the conservative object envelope. When a
        validator is supplied, it owns exact object/jaw clearance for every
        candidate; canonical robot sweeps and carried-table clearance stay on.
        """
        from scipy.spatial.transform import Rotation
        joints=np.asarray(joints,float)
        if (joints.shape!=(12,) or not np.isfinite(joints).all()
                or np.any(joints<self.ik.low) or np.any(joints>self.ik.high)):
            raise ResetBlocked("Planning start is outside existing joint bounds")
        grippers=np.asarray(grippers,float)
        if grippers.shape!=(2,) or not np.isfinite(grippers).all() or any(g<0 or g>1 for g in grippers):
            raise ResetBlocked("Planning requires two finite normalized gripper states")
        source=scene[color];dest=targets["targets"][color]
        src=self.world(source);dst=self.world(dest)
        src_top, dst_top = src[2], dst[2]
        src_floor=source["visible_top_center_by_arm"]["left"]["support_point_m"][2]
        dst_floor=dest["visible_top_center_by_arm"]["left"]["support_point_m"][2]
        from .yam_cube_contact import contact_for_cube
        contact_geometry=contact_for_cube(src_top-src_floor,self.contact_reference)
        destination_contact=contact_for_cube(dst_top-dst_floor,self.contact_reference)
        src[2]=src_floor+contact_geometry["tcp_height_above_support_m"]
        dst[2]=dst_floor+destination_contact["tcp_height_above_support_m"]
        closed=contact_geometry["nominal_aperture"]
        height=max(max(self.world(row)[2] for row in scene.values()),dst_top)+transfer_height_margin_m
        if height>.40:raise ResetBlocked("No clear transfer height in the existing workspace")
        failures=[];options=[]
        for arm in ("left","right"):
            i=0 if arm=="left" else 1
            base=np.array([0.,self.spacing/2 if i==0 else -self.spacing/2])
            # A high pose directly above a distant cube can hit the wrist bound
            # although its low grasp is reachable. Search bounded retraction at
            # the SAME transfer height; retain a vertical 40mm terminal approach.
            for retract in (0.,.02,.04,.06):
                high_src=src.copy();high_src[2]=height
                high_dst=dst.copy();high_dst[2]=height
                for point in (high_src,high_dst):
                    radial=point[:2]-base
                    if np.linalg.norm(radial)<=retract:
                        raise ResetBlocked("Retracted waypoint crosses the arm base")
                    point[:2]-=retract*radial/np.linalg.norm(radial)
                low_src=src.copy();low_src[2]=src_top+.04
                low_dst=dst.copy();low_dst[2]=dst_top+.04
                for yaw in (source["yaw_rad"]+j*math.pi/2 for j in range(4)):
                    rotation=Rotation.from_euler("z",yaw).as_matrix()@np.diag([1.,-1.,-1.])
                    actual_turn=destination_yaw_offset_rad if destination_grasp_yaw_rad is None else destination_grasp_yaw_rad-yaw
                    destination_rotation=Rotation.from_euler('z',actual_turn).as_matrix()@rotation
                    q=np.array(joints,float);g=list(grippers);g[i]=1.
                    stages=[dict(name="open",arm=arm,points_rad=[q.copy()],grippers=list(g))]
                    travel=[("approach",high_src,1.,False,False)]
                    if retract:travel.append(("align",low_src,1.,False,True))
                    travel.extend([("descend",src,1.,False,True),
                                   ("close",src,closed,False,True)])
                    if retract:travel.append(("lift_clear",low_src,closed,True,True))
                    travel.extend([("lift",high_src,closed,True,True),
                                   ("transfer",high_dst,closed,True,False)])
                    if retract:travel.append(("place_align",low_dst,closed,True,True))
                    travel.extend([("place",dst,closed,True,True),
                                   ("release",dst,1.,False,True)])
                    if retract:travel.append(("retreat_clear",low_dst,1.,False,True))
                    travel.append(("retreat",high_dst,1.,False,True))
                    try:
                        for name,point,grip,carry,contact in travel:
                            wanted_rotation=destination_rotation if name in ('transfer','place_align','place','release','retreat_clear','retreat') else rotation
                            points=self.path(q,arm,point,wanted_rotation,scene,color,carrying=carry,
                                             contact=contact,cartesian=name!="approach",
                                             defer_object_clearance=candidate_validator is not None)
                            g[i]=grip
                            stages.append(dict(name=name,arm=arm,points_rad=points,grippers=list(g),
                                               expected_tip_world_m=point,expected_rotation=wanted_rotation,
                                               carrying=carry,intended_selected_contact=contact))
                            q=points[-1].copy()
                        options.append(dict(color=color,arm=arm,stages=stages,
                            destination_scene_row=copy.deepcopy(dest),
                            retract_m=retract,grasp_yaw_rad=float(yaw),transfer_height_m=height,
                            destination_yaw_offset_rad=float(actual_turn),
                            contact_geometry=contact_geometry,
                            contact_pose_status="UNVERIFIED installed contact; reference CAD candidate",
                            cost=sum(np.linalg.norm(np.diff(np.vstack([joints]+[p for s in stages for p in s["points_rad"]]),axis=0),axis=1)),
                            final_joints=q,final_grippers=g))
                    except (ValueError,RuntimeError) as exc:
                        failures.append(f"{arm}/retract{retract:.2f}/yaw{yaw:.2f}/{name}: {exc}")
        if not options:
            raise ResetBlocked(f"No collision-checked same-arm return for {color}: "+" | ".join(failures))
        for rank,result in enumerate(sorted(options,key=lambda option:option["cost"]),1):
            result["limitations"]=["Canonical fixed-jaw model, not independently validated physical gripper geometry",
                "Object/jaw clearance requires installed-CAD candidate validation" if candidate_validator else "Other cubes use conservative tool/held-object footprint envelopes",
                "No cross-arm handoff, stacked cubes, or occupied-target cycle resolution",
                "Unknown objects and occluded space require a separate complete collision model"]
            if candidate_validator is None:
                return plain(result)
            result["candidate_selection"]=dict(rank=rank,kinematic_candidates=len(options),method="cost-ordered installed-CAD validation")
            try:
                validated=candidate_validator(plain(result))
                if not isinstance(validated,dict):
                    raise ResetBlocked("Candidate validator did not return an audited plan")
                return plain(validated)
            except ResetBlocked as exc:
                failures.append(f"{result['arm']}/retract{result['retract_m']:.2f}/yaw{result['grasp_yaw_rad']:.2f}/installed-audit: {exc}")
        raise ResetBlocked(f"No installed-geometry-valid return for {color}: "+" | ".join(failures))


def collision_loader_reference(runtime_root):
    """Load controller-owned preparation code directly; never copy shared source."""
    source=Path(resource('collision_model_source'))
    if not source.is_file():
        raise ResetBlocked("Controller-owned collision repair is unavailable")
    spec=importlib.util.spec_from_file_location("yam_cube_collision_model",source)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.collision_enabled_model,dict(path=str(source.resolve()),sha256=hashlib.sha256(source.read_bytes()).hexdigest())


def motion_blockers(targets, status):
    blockers=[]
    if targets.get("physical_accuracy") != "VERIFIED":
        blockers.append("Independent camera/depth accuracy and tool-contact calibration are unverified")
    if status.get("joint_calibration",{}).get("calibration_id")!=targets["native_joint_calibration_id"]:
        blockers.append("Live native joint calibration differs from saved targets")
    queue=status.get("auto_queue",{});api=status.get("api",{})
    if queue.get("enabled") or queue.get("running") or api.get("authorized") or api.get("session_id"):
        blockers.append("Queue/session owns the robot")
    if status.get("adapter_fault"):
        blockers.append("Controller reports an adapter fault")
    # Deliberately no switch to assert this away. The current planning model has
    # placeholder jaws and no complete measured environment. It is a preview.
    blockers.append("Physical execution adapter is not commissioned: actual jaw/held-cube collision geometry and contact verification must be validated")
    return blockers
