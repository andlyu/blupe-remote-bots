"""RoboHarness YAM point/axis constraints and endpoint-safe physical packets.

No session, model or motor ownership. Units: metres in each arm's calibrated
base frame, rotations in radians, grippers in [0,1], wire joints in degrees.
MuJoCo is used for numerical FK/IK/contact checks, not dynamics rollouts.
"""
from copy import deepcopy
import math
import time

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from .mujoco_ik import BimanualRelativeIK, IKConvergenceError
from .session import MAX_COMMANDS, MAX_WAYPOINTS_PER_PACKET, _trajectory_waypoints
from .controller_workspace import workspace_for_robot

ARMS = ('left', 'right')
MAX_JOINT_STEP_RAD = .03
LOW_M = np.array([.15, -.50, .03])
HIGH_M = np.array([.48, .50, .40])


class InputRejected(ValueError):
    """Proven local rejection: no packet has been handed to a transport."""
    stage = 'local_validation'
    dispatched = False


def number(value, label, low=-math.inf, high=math.inf):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise InputRejected(f'{label} must be finite and in [{low}, {high}]; no motion sent')
    return float(value)


def vector(value, size, label):
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise InputRejected(f'{label} requires {size} numbers; no motion sent')
    return np.array([number(v, label) for v in value])


def fields(value, required):
    if not isinstance(value, dict) or set(value) != set(required):
        raise InputRejected('Expected fields: ' + ', '.join(required) + '; no motion sent')


def aligned_rotation(before, axis, direction):
    """Minimal rotation aligning a named intrinsic gripper axis to a scene line."""
    if axis not in ('x', 'y', 'z'):
        raise InputRejected('axis must be x, y or z; no motion sent')
    # Internal NumPy results become ordinary scalars before the strict external
    # JSON numeric validator; bool/NaN/out-of-range requests stay rejected.
    target = vector(np.asarray(direction).tolist(), 3, 'line direction')
    length = np.linalg.norm(target)
    if length < .002:
        raise InputRejected('Constraint points are less than 2 mm apart; no motion sent')
    target /= length
    source = before[:, ('x', 'y', 'z').index(axis)]
    cross, dot = np.cross(source, target), float(np.dot(source, target))
    if np.linalg.norm(cross) < 1e-10:
        if dot > 0: return before.copy()
        # Deterministic perpendicular axis for a 180-degree relation.
        basis = np.eye(3)[int(np.argmin(np.abs(source)))]
        cross = np.cross(source, basis)
    cross /= np.linalg.norm(cross)
    return Rotation.from_rotvec(cross * math.acos(float(np.clip(dot, -1, 1)))).as_matrix() @ before


class RoboHarnessControl:
    def __init__(self, robot_id, *, clock=time.time, joint_offsets_rad=None):
        profile = workspace_for_robot(robot_id)
        if profile is None:
            raise InputRejected('RoboHarness supports only registered YAM stations')
        self.robot_id, self.profile, self.clock = robot_id, profile, clock
        self._home_identity=None;self._completed_cursor=0
        # Model/camera spacing is distinct from the guard's common-frame origin.
        spacing = .50 if robot_id == 'yam-1' else .62
        safety = profile._safety()  # Hash-pinned canonical controller snapshot.
        self.ik = BimanualRelativeIK(base_spacing_m=spacing,
                                    joint_limits={'lower_rad':safety['joint_lower_rad'],'upper_rad':safety['joint_upper_rad']},
                                    joint_offsets_rad=joint_offsets_rad)
        self.bases = np.array([[0, spacing/2, 0], [0, -spacing/2, 0]])
        self.bounds = [np.array([np.maximum(LOW_M,profile.bounds(a)[0]),np.minimum(HIGH_M,profile.bounds(a)[1])]) for a in ARMS]

    def observe(self, observation):
        identity=tuple(observation.get(k) for k in ('episode_id','lease_id'))
        # `homed` reports the current pose, not historical startup readiness.
        # Leaving Home is permitted only after this instance checked Home and
        # received matched measured completion at this exact lease/cursor.
        after_motion=(self._home_identity is not None and identity==self._home_identity
            and type(observation.get('step_id')) is int
            and observation['step_id']==self._completed_cursor and self._completed_cursor>0)
        result=self._observe(observation,require_home=not after_motion)
        if (observation.get('homed') is True and observation.get('step_id')==0
                and all(isinstance(v,str) and v for v in identity)):
            self._home_identity=identity
        return result

    def confirm_completed_trajectory(self,observation,*,first_step_id,waypoint_count):
        identity=tuple(observation.get(k) for k in ('episode_id','lease_id'))
        if (self._home_identity is None or identity!=self._home_identity
                or type(first_step_id) is not int or first_step_id!=self._completed_cursor
                or type(waypoint_count) is not int or not 1<=waypoint_count<=MAX_WAYPOINTS_PER_PACKET
                or type(observation.get('step_id')) is not int
                or observation['step_id']!=first_step_id+waypoint_count):
            raise InputRejected('Measured completion does not match confirmed Home/lease/cursor; no motion sent')
        self._observe(observation,require_home=False)
        self._completed_cursor=observation['step_id']

    def _observe(self,observation,*,require_home):
        if (observation.get('source') != 'hardware' or observation.get('settled') is not True
                or (require_home and observation.get('homed') is not True) or observation.get('safety', {}).get('ok') is not True
                or observation.get('robot_id', observation.get('jetson_id')) != self.robot_id):
            raise InputRejected('Fresh, homed, settled hardware feedback with safety OK is required; no motion sent')
        observed = number(observation.get('observed_at'), 'feedback timestamp', 0)
        if not 0 <= self.clock() - observed <= 2:
            raise InputRejected('Measured hardware feedback is stale; no motion sent')
        joints = [vector(observation.get(a + '_joints_deg'), 6, a + ' joints') for a in ARMS]
        q = np.deg2rad(np.concatenate(joints))
        # Never clamp an invalid measurement or preserve an out-of-range joint.
        if np.any(q < self.ik.low) or np.any(q > self.ik.high):
            raise InputRejected('Measured joint state is outside calibrated limits; no motion sent')
        grips = [number(observation.get(a + '_gripper'), a + ' measured gripper', 0, 1) for a in ARMS]
        self.ik._forward(q)
        poses = self.ik._poses()
        return q, grips, poses

    def pose_summary(self, observation):
        _, grips, poses = self.observe(observation)
        return {a: dict(position_m=(p-self.bases[i]).tolist(), rotation_matrix=r.tolist(), gripper=grips[i])
                for i, (a, (p, r)) in enumerate(zip(ARMS, poses))}

    def target(self, command, observation, *, points=None):
        """Resolve geometric constraints before interpolation; unknown modes fail."""
        _, grips, poses = self.observe(observation)
        if not isinstance(command, dict) or command.get('arm') not in ARMS:
            raise InputRejected('Choose left or right arm; no motion sent')
        arm = command['arm']; index = ARMS.index(arm)
        p, r = poses[index]; local = p-self.bases[index]
        kind = command.get('kind')
        gripper = grips[index]
        if kind == 'gripper':
            fields(command, ('kind', 'arm', 'value'))
            gripper = number(command['value'], 'requested gripper', 0, 1)
        elif kind == 'adjust_pose':
            fields(command, ('kind', 'arm', 'delta_m', 'rotation_vector_rad'))
            delta = vector(command['delta_m'], 3, 'delta_m')
            rotation = vector(command['rotation_vector_rad'], 3, 'rotation_vector_rad')
            if np.linalg.norm(delta) > .1 or np.linalg.norm(rotation) > .5:
                raise InputRejected('Adjustment exceeds 10 cm or 0.5 rad; request a smaller step, no motion sent')
            local = local+delta
            r = Rotation.from_rotvec(rotation).as_matrix() @ r
        elif kind in ('touch', 'align_line', 'plane_parallel'):
            required = ('kind', 'arm', 'point_ids', 'offset_m') if kind == 'touch' else ('kind', 'arm', 'point_ids', 'axis')
            fields(command, required)
            ids = command['point_ids']; count = {'touch': 1, 'align_line': 2, 'plane_parallel': 3}[kind]
            if (not isinstance(ids, list) or len(ids) != count
                    or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != count):
                raise InputRejected(f'{kind} requires {count} distinct tracked point IDs; no motion sent')
            if points is None:
                raise InputRejected('Constraint needs current tracked RGB-D points; no motion sent')
            coords = [vector(points.get(point, {}).get(arm), 3, 'tracked point') for point in ids]
            if kind == 'touch':
                # Offset is explicit: a measured surface point is not silently
                # treated as a collision-free grasp pose.
                offset = vector(command['offset_m'], 3, 'offset_m')
                if np.linalg.norm(offset) > .15:
                    raise InputRejected('Surface offset exceeds 15 cm; no motion sent')
                local = coords[0]+offset
            else:
                direction = coords[1]-coords[0]
                if kind == 'plane_parallel':
                    other = coords[2]-coords[0]
                    cross = np.cross(direction, other)
                    if np.linalg.norm(cross) < 1e-5:
                        raise InputRejected('Plane points are collinear or too close; no motion sent')
                    direction = cross / np.linalg.norm(cross)
                    # Plane parallelism has two normal signs; preserve the
                    # closest orientation rather than flip the gripper.
                    axis = command['axis']
                    if axis not in ('x','y','z'): raise InputRejected('Unknown gripper axis; no motion sent')
                    if np.dot(direction, r[:, ('x','y','z').index(axis)]) < 0: direction = -direction
                r = aligned_rotation(r, command['axis'], direction)
        else:
            raise InputRejected('Unsupported RoboHarness primitive; no motion sent')
        if kind != 'gripper' and (np.any(local < self.bounds[index][0]) or np.any(local > self.bounds[index][1])):
            raise InputRejected('Requested end-effector target is outside the existing YAM workspace; no motion sent')
        return index, local+self.bases[index], r, gripper

    def build(self, command, observation, first_step_id, *, points=None):
        if type(first_step_id) is not int or not 0 <= first_step_id < MAX_COMMANDS:
            raise InputRejected('Invalid or exhausted waypoint cursor; no motion sent')
        measured, grips, poses = self.observe(observation)
        arm, target_p, target_r, target_grip = self.target(command, observation, points=points)
        start_p, start_r = poses[arm]
        distance = float(np.linalg.norm(target_p-start_p))
        angle = float(Rotation.from_matrix(target_r @ start_r.T).magnitude())
        count = max(1, math.ceil(distance/.005), math.ceil(angle/.025), math.ceil(abs(target_grip-grips[arm])/.1))
        budget = min(MAX_WAYPOINTS_PER_PACKET, MAX_COMMANDS-first_step_id)
        if count > budget: raise InputRejected('Motion exceeds packet/session budget; no motion sent')
        interpolation = Slerp([0, 1], Rotation.from_matrix([start_r, target_r]))
        packets = []; previous = measured.copy()
        def extend(left, right, depth=0):
            nonlocal previous
            p = target_p.copy() if right == 1 else start_p+(target_p-start_p)*right
            r = target_r.copy() if right == 1 else interpolation(right).as_matrix()
            selected = list(poses); selected[arm] = (p, r)
            if command['kind'] == 'gripper': solved = measured.copy()
            else:
                try: solved = self.ik._solve(previous, tuple(selected))
                except IKConvergenceError as exc: raise InputRejected('Geometric target is unreachable; no motion sent') from exc
                # Preserve the other arm's exact measured encoder commands.
                other = 1-arm; solved[other*6:other*6+6] = measured[other*6:other*6+6]
            if np.max(np.abs(solved-previous)) > MAX_JOINT_STEP_RAD:
                if depth >= 10: raise InputRejected('Joint pacing could not be satisfied; no motion sent')
                mid=(left+right)/2; extend(left,mid,depth+1); extend(mid,right,depth+1); return
            if len(packets) >= budget: raise InputRejected('Adaptive path exceeds packet/session budget; no motion sent')
            if np.any(solved < self.ik.low) or np.any(solved > self.ik.high) or not np.isfinite(solved).all():
                raise InputRejected('Generated joints violate calibrated limits; no motion sent')
            self.ik._forward(solved)
            if self.ik.data.ncon:
                raise InputRejected('Predictive model contact rejected this path; no motion sent')
            actual_p,actual_r=self.ik._poses()[arm]
            if np.linalg.norm(actual_p-p) > .002 or Rotation.from_matrix(actual_r @ r.T).magnitude() > .01:
                raise InputRejected('IK constraint residual exceeds 2 mm / 0.01 rad; no motion sent')
            point = {'step_id':first_step_id+len(packets)}
            for i,a in enumerate(ARMS):
                # Reuse measured lists on all untouched joints; no roundtrip
                # degree/radian conversion changes an uninstructed arm.
                point[a+'_joints_deg'] = (np.rad2deg(solved[i*6:i*6+6]).tolist()
                    if i==arm and command['kind']!='gripper' else deepcopy(observation[a+'_joints_deg']))
                point[a+'_gripper'] = (target_grip if right==1 else grips[i]+(target_grip-grips[i])*right) if i==arm else grips[i]
            packets.append(point); previous=solved
        for i in range(count): extend(i/count,(i+1)/count)
        # The same canonical client validator used before actual serialization.
        return _trajectory_waypoints(packets)
