"""RoboCurve per-arm Cartesian move_to -> canonical YAM joint packets.

Conventions and pacing: docs/refs/robocurve/INDEX.md, inspect-robots-agent
0.26.0 _tools.py and inspect-robots-yam 0.36.0 kinematics.py.
"""
import math
import numpy as np

from .session import MAX_COMMANDS, MAX_WAYPOINTS_PER_PACKET
from .mujoco_ik import BimanualRelativeIK, IKConvergenceError

ARMS = ('left', 'right')
AXES = ('x', 'y', 'z', 'yaw', 'pitch', 'roll', 'gripper')
NAMES = tuple(f'{arm}_{axis}' for arm in ARMS for axis in AXES)
LOW = np.tile([.15, -.50, .03, -math.pi, 0, 0, 0], 2)
HIGH = np.tile([.48, .50, .4, math.pi, 0, 0, 1], 2)
TRAJECTORY_SPEED = 4.0
# Retain the gateway's 0.35 rad/s joint ceiling at 10 Hz.
MAX_JOINT_STEP_RAD = min(.01 * TRAJECTORY_SPEED, .035)
# Physical increments are independent of the selected controller envelope.
# Preserve the existing 10 Hz pacing: 13.2 mm X, 20 mm Y, 14.8 mm Z per step.
STEP = np.tile([.01 * TRAJECTORY_SPEED * (.48 - .15), .005 * TRAJECTORY_SPEED,
                .01 * TRAJECTORY_SPEED * (.4 - .03), .01 * TRAJECTORY_SPEED * (2 * math.pi),
                0, 0, .1], 2)
BASES = (np.array([0., .35, 0.]), np.array([0., -.35, 0.]))


class InvalidMove(ValueError):
    """A model target that can be corrected without sending any arm command."""
    def __init__(self, message, code='invalid_tool'):
        super().__init__(message)
        self.code = code


def relative_rotation(yaw, pitch, roll):
    cy, sy, cp, sp, cr, sr = (math.cos(yaw), math.sin(yaw), math.cos(pitch),
                             math.sin(pitch), math.cos(roll), math.sin(roll))
    return (np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
            @ np.array([[cp, 0, -sp], [0, 1, 0], [sp, 0, cp]])
            @ np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]]))


class RoboCurveTrajectory:
    speed_multiplier = TRAJECTORY_SPEED
    def __init__(self, *, base_spacing_m=None, joint_offsets_rad=None, preserve_uninstructed=False):
        self.ik = BimanualRelativeIK(base_spacing_m=base_spacing_m, joint_offsets_rad=joint_offsets_rad)
        self.bases = tuple(np.array([0., sign*self.ik.base_spacing_m/2, 0.]) for sign in (1, -1))
        self.low, self.high = LOW.copy(), HIGH.copy()
        self.start_rotations = None
        self.attitude_references = dict.fromkeys(ARMS,'observed')
        self.preserve_uninstructed = preserve_uninstructed

    def observe(self, observation):
        if observation.get('settled') is not True:
            raise RuntimeError('RoboCurve policy requires measured settled feedback')
        q = self.ik._safe_baseline(*(observation[f'{arm}_joints_deg'] for arm in ARMS))
        # FK/reference use the actual measurement, not its limit-clipped IK seed.
        measured = np.deg2rad(np.concatenate([observation[f'{arm}_joints_deg'] for arm in ARMS]))
        self.ik._forward(measured)
        poses = self.ik._poses()
        if self.start_rotations is None:
            self.start_rotations = tuple(r.copy() for _, r in poses)
        state, joints = [], []
        for i, (p, r) in enumerate(poses):
            grip = observation.get(f'{ARMS[i]}_gripper')
            if isinstance(grip, bool) or not isinstance(grip, (int, float)) or not math.isfinite(grip) or not 0 <= grip <= 1:
                raise RuntimeError('RoboCurve policy requires measured normalized gripper feedback')
            d = r @ self.start_rotations[i].T
            state.extend([*(p - self.bases[i]), math.atan2(d[1, 0], d[0, 0]),
                          math.asin(float(np.clip(d[2, 0], -1, 1))),
                          math.atan2(d[2, 1], d[2, 2]), grip])
            joints.extend([*measured[i*6:i*6+6], grip])
        return q, np.asarray(state), joints

    def build(self, targets, observation, first_step_id, *, attitude=None):
        if attitude is None:return self._build(targets,observation,first_step_id)
        if attitude!='base_vertical':
            raise InvalidMove('attitude must be base_vertical or omitted','invalid_attitude')
        if not isinstance(targets,dict) or not targets:
            raise InvalidMove('targets must be a nonempty map of named dimensions')
        arms={arm for i,arm in enumerate(ARMS) if any(n in targets for n in NAMES[i*7:i*7+6])}
        if not arms:
            raise InvalidMove('Vertical alignment needs a named Cartesian arm target; gripper-only moves hold joints','invalid_attitude')
        self.observe(observation)
        previous=self.start_rotations
        modes=self.attitude_references
        # Explicit per-arm reference transition. Native joint/workspace/pacing
        # guards still validate every generated waypoint; inactive arms hold.
        self.start_rotations=tuple(np.diag([-1.,1.,-1.]) if arm in arms else previous[i] for i,arm in enumerate(ARMS))
        self.attitude_references={arm:'base_vertical' if arm in arms else modes[arm] for arm in ARMS}
        try:return self._build(targets,observation,first_step_id)
        except Exception:
            self.start_rotations,self.attitude_references=previous,modes
            raise

    def _build(self, targets, observation, first_step_id):
        if not isinstance(targets, dict) or not targets:
            raise InvalidMove('targets must be a nonempty map of named dimensions')
        seed, start, _ = self.observe(observation)
        held_poses=tuple((p.copy(),r.copy()) for p,r in self.ik._poses())
        measured_start = np.deg2rad(np.concatenate([observation[f'{arm}_joints_deg'] for arm in ARMS]))
        goal = start.copy()
        named = []
        for name, value in targets.items():
            if name not in NAMES:
                raise InvalidMove(f'Unknown target dimension: {name}', 'unknown_dimension')
            i = NAMES.index(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise InvalidMove(f'{name} must be a finite number', 'invalid_target_type')
            if not self.low[i] <= value <= self.high[i]:
                raise InvalidMove(f'{name} must be in [{self.low[i]}, {self.high[i]}]', 'target_out_of_bounds')
            goal[i] = value
            named.append(i)
        # Pin the endpoint, not every intermediate sample. Measured tracking
        # error on a fixed pitch/roll axis must converge gradually; clipping each
        # sample makes an instantaneous correction that subdivision cannot shrink.
        goal = np.clip(goal, self.low, self.high)
        cartesian_arms = {i for i,arm in enumerate(ARMS)
                          if any(n.startswith(arm+'_') and n != arm+'_gripper' for n in targets)}
        if not self.preserve_uninstructed:
            cartesian_arms={0,1}  # Preserve the established other-policy drift correction contract.
        ratio = max((abs(goal[i]-start[i])/STEP[i] for i in named if STEP[i] > 0), default=0)
        ratio /= 1 - 1e-6  # RoboCurve's numerical headroom
        remaining = max(0, MAX_COMMANDS-first_step_id)

        def budget_error():
            if remaining < MAX_WAYPOINTS_PER_PACKET:
                return InvalidMove(
                    f'This move exceeds the remaining session waypoint budget of {remaining}. '
                    'No motion was sent. Request a smaller intermediate target.',
                    'session_waypoint_budget')
            return InvalidMove(
                f'This move exceeds the per-packet waypoint budget of {MAX_WAYPOINTS_PER_PACKET}. '
                f'The session still has {remaining} waypoints available. '
                'No motion was sent. Request a smaller intermediate target; '
                'the remaining session budget can be used across multiple packets.',
                'packet_waypoint_budget')

        if ratio > MAX_WAYPOINTS_PER_PACKET:
            raise budget_error()
        count = max(1, math.ceil(ratio))
        points = []
        limit = min(MAX_WAYPOINTS_PER_PACKET, remaining)
        if limit < 1:
            raise InvalidMove('Session waypoint budget exhausted', 'session_waypoint_budget')

        def state_at(alpha):
            # Keep validated numeric endpoints exact, especially close=0 from
            # measured fractional starts (subtraction can produce -1.11e-16).
            return goal.copy() if alpha == 1.0 else start + alpha*(goal-start)

        def extend(a, b, previous, depth=0):
            state = state_at(b)
            poses = tuple(((state[i*7:i*7+3] + self.bases[i],
                            relative_rotation(*state[i*7+3:i*7+6]) @ self.start_rotations[i])
                           if i in cartesian_arms else held_poses[i]) for i in range(2))
            try:
                solved = self.ik._solve(previous, poses) if cartesian_arms else previous.copy()
                for index in range(2):
                    if index not in cartesian_arms:
                        solved[index*6:index*6+6] = measured_start[index*6:index*6+6]
            except IKConvergenceError as exc:
                raise InvalidMove('Cartesian target is unreachable; request a smaller move', 'unreachable_target') from exc
            previous_command = previous if points else measured_start
            if np.max(np.abs(solved-previous_command)) > MAX_JOINT_STEP_RAD + 1e-12:
                if depth >= 10:
                    raise InvalidMove('Cartesian path cannot meet joint pacing; request a smaller move', 'joint_pacing_limit')
                mid = (a+b)/2
                return extend(mid, b, extend(a, mid, previous, depth+1), depth+1)
            if len(points) >= limit:
                raise budget_error()
            degrees = np.rad2deg(solved).reshape(2, 6)
            # An uninstructed arm retains the measured joint values verbatim,
            # avoiding an unnecessary IK or degrees/radians round trip.
            joint_values = [degrees[i].tolist() if i in cartesian_arms else
                            list(observation[arm+'_joints_deg']) for i,arm in enumerate(ARMS)]
            points.append({'step_id': first_step_id+len(points),
                           'left_joints_deg': joint_values[0],
                           'right_joints_deg': joint_values[1],
                           'left_gripper': float(state[6]), 'right_gripper': float(state[13])})
            return solved

        for i in range(count):
            seed = extend(i/count, (i+1)/count, seed)
        self.validate_joint_limits(points)
        return points

    def validate_joint_limits(self, points):
        """Final command-space check also covers measured uninstructed joints."""
        for point in points:
            joints=np.deg2rad(point['left_joints_deg']+point['right_joints_deg'])
            # 1e-10rad covers degrees/radians serialization roundoff only;
            # it is not an expanded actuator target or hardware tolerance.
            invalid=np.flatnonzero(~np.isfinite(joints) | (joints<self.ik.low-1e-10)
                                   | (joints>self.ik.high+1e-10))
            if len(invalid):
                i=int(invalid[0])
                raise InvalidMove(
                    f'{ARMS[i//6]} joint {i%6+1} target {point[ARMS[i//6]+"_joints_deg"][i%6]:.6f} degrees '
                    f'is outside configured limits [{math.degrees(self.ik.low[i]):.6f}, '
                    f'{math.degrees(self.ik.high[i]):.6f}]. No motion was sent.', 'joint_limit')
