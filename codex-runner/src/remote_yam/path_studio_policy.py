"""Deterministic Cartesian sketches, planned from leased hardware feedback.

Browser IK is never accepted as a command. All points are in the station's
calibrated common frame, in metres. Gateway validation remains authoritative.
"""
import math
import time

import numpy as np

from .controller_workspace import workspace_for_robot
from .feedback import feedback_decision
from .mujoco_ik import BimanualRelativeIK, IKConvergenceError
from .providers import PolicyComplete
from .session import MAX_COMMANDS
from .path_studio_geometry import DrawingGeometry, rotation_mix, rotation_angle

STATIONS = {'robohouse': 'robot-ba8413962083809c', 'yam-1': 'yam-1'}
ARMS = ('left', 'right')
PACKET_SIZE = 50
JOINT_STEP = .035  # 0.35 rad/s at the API's 10 Hz cadence
SETTLE_HOLD_STEPS = 5
MAX_SETTLE_RETRIES = 2
GRIPPER_CLEARANCE_M = .020
MAX_PATH_ADJUSTMENT_M = .100
APPROXIMATE_TRACKING_TOLERANCE_M = .025


def validate_sketch(data):
    if not isinstance(data, dict):
        raise ValueError('Expected a Path Studio request')
    station, assignment = data.get('station'), data.get('assignment')
    if station not in STATIONS or assignment not in ('both', *ARMS):
        raise ValueError('Choose a supported station and arm assignment')
    if data.get('frame') != 'yam_common' or data.get('units') != 'm':
        raise ValueError('Use the shared YAM frame and metres')
    coordination = data.get('coordination', 'together')
    if coordination not in ('together','sequential'):
        raise ValueError('Choose together or sequential arm coordination')
    speed = data.get('speed_m_s')
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not .005 <= speed <= .1:
        raise ValueError('Tool speed must be between 5 and 100 mm/s')
    raw = data.get('points')
    if not isinstance(raw, list) or not 2 <= len(raw) <= 2000:
        raise ValueError('A path needs 2–2,000 XYZ points')
    for point in raw:
        if not isinstance(point, list) or len(point) != 3 or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                or abs(v) > .8 for v in point):
            raise ValueError('Every point must contain three finite coordinates within ±800 mm')
    points = np.asarray(raw, dtype=float)
    if np.linalg.norm(np.diff(points, axis=0), axis=1).sum() < .001:
        raise ValueError('Draw a path at least 1 mm long')
    return dict(station=station, assignment=assignment, speed_m_s=float(speed),
                points=points.tolist(), frame='yam_common', units='m',coordination=coordination)


def arc_path(points, distance):
    """Interpolate without dropping corners or short segments."""
    lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    cumulative = np.r_[0., np.cumsum(lengths)]
    if distance <= 0:
        return points[0].copy()
    if distance >= cumulative[-1]:
        return points[-1].copy()
    i = min(int(np.searchsorted(cumulative, distance, side='right')-1), len(points)-2)
    return points[i] + (points[i+1]-points[i])*(distance-cumulative[i])/lengths[i]


def split_path(points, assignment):
    if assignment != 'both':
        return {assignment: points}
    cumulative = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    half = cumulative[-1]/2
    middle = arc_path(points, half)
    left = np.vstack([points[cumulative < half-1e-9], middle])
    right = np.vstack([points[cumulative > half+1e-9][::-1], middle])
    if np.mean(left[:, 1]) < np.mean(right[:, 1]):
        left, right = right, left
    return dict(left=left, right=right)


class PathStudioPolicy:
    provider_name = 'path_studio'
    model = 'calibrated-cartesian-path-v1'

    def __init__(self, sketch):
        self.sketch = validate_sketch(sketch)
        self.robot_id = STATIONS[self.sketch['station']]
        self.workspace = workspace_for_robot(self.robot_id)
        self.cancelled = lambda: False
        self.refresh_observation = None
        self.ik = None
        self.targets = None
        self.rotations = None
        self.target_rotations = []
        self.grips = {}
        self.confirmed_draw_samples = 0
        self.max_tcp_error_m = 0.
        self.max_observed_tcp_error_m = 0.
        self.settling = False
        self.settle_retries = self.settle_attempts_total = 0
        self.last_settle_error = float('inf')
        forward = np.array([[0.,0.,1.], [0.,1.,0.], [-1.,0.,0.]])
        # Keep the right housing clear of its wrist along the inward lobe.
        self.tool_rotations = (forward, forward@np.array([[0.,-1.,0.], [1.,0.,0.], [0.,0.,1.]]))
        self.cursor = self.pending_cursor = 0
        self.preflight_points = 0
        self.preflight_validated = False
        self.phase = 'waiting_for_lease'
        self.failure = None
        self.target_phases = []
        self.step_phases = {}
        self.grippers_closed = False
        self.closing_pending = False
        self.active = split_path(np.asarray(self.sketch['points']), self.sketch['assignment'])
        self.together = len(self.active)==2 and self.sketch['coordination']=='together'
        if self.together:
            # Start at opposite shared endpoints rather than occupying the same
            # notch/tip at once. Both halves finish at the opposite endpoint.
            self.active['right'] = self.active['right'][::-1].copy()
        self.requested_paths = {a:path.copy() for a,path in self.active.items()}
        self.max_path_adjustment_m = 0.

    def configure_robot_workspace(self, robot_id):
        if robot_id != self.robot_id:
            raise ValueError('Sketch station does not match the API station')

    def prepare_before_session(self, prompt):
        # Use the runner's cancellable admission worker rather than blocking HTTP.
        self._check_cancelled()

    def validate_session_admission(self, api):
        report = api._request('GET', f'/v1/robots/{self.robot_id}/calibration')
        self.configure_calibration(report)

    def configure_calibration(self, report):
        """Shared binding for physical execution and isolated simulation."""
        self.workspace.validate_report(report)
        spacing = report.get('base_geometry', {}).get('spacing_m')
        if not isinstance(spacing, (int, float)) or not .3 <= spacing <= 1:
            raise ValueError('The API must report calibrated base spacing')
        # Binding validation above prevents applying model offsets to native encoders.
        offsets = self.workspace.joint_offsets_rad
        cfg = self.workspace._safety()
        self.ik = BimanualRelativeIK(base_spacing_m=spacing, joint_offsets_rad=offsets,
            joint_limits=dict(lower_rad=cfg['joint_lower_rad'], upper_rad=cfg['joint_upper_rad']))
        self.guard = DrawingGeometry(spacing, offsets, cfg['table_z_m'])
        if self.together:self.guard.required_gripper_clearance_m = GRIPPER_CLEARANCE_M
        self.spacing = spacing
        self.bases = tuple(np.array([0., sign*spacing/2, 0.]) for sign in (1, -1))
        for side, path in self.active.items():
            low, high = self.workspace.bounds(side)
            local = path-self.bases[ARMS.index(side)]
            if np.any(local < low) or np.any(local > high):
                raise ValueError(f'The {side} path exceeds the controller workspace. Move or shrink the sketch.')

    def public_config(self):
        return dict(provider=self.provider_name, model=self.model,
                    path_progress=dict(phase=self.phase, confirmed_samples=self.cursor,
                        total_samples=len(self.targets) if self.targets is not None else 0,
                        preflight_waypoints=self.preflight_points, failure=self.failure,
                        confirmed_draw_samples=self.confirmed_draw_samples,
                        planned_draw_samples=sum('draw' in p.values() for p in self.target_phases),
                        preflight_validated=self.preflight_validated,
                        max_tcp_error_m=self.max_tcp_error_m,
                        max_observed_tcp_error_m=self.max_observed_tcp_error_m,
                        settling_retries=self.settle_attempts_total,
                        tracking_tolerance_m=APPROXIMATE_TRACKING_TOLERANCE_M if self.together else .003,
                        coordination='together' if self.together else 'sequential',
                        max_path_adjustment_m=self.max_path_adjustment_m,
                        required_gripper_clearance_m=GRIPPER_CLEARANCE_M if self.together else 0.,
                        min_gripper_clearance_m=(self.guard.min_gripper_clearance_m
                            if self.together and math.isfinite(getattr(getattr(self,'guard',None),'min_gripper_clearance_m',float('inf'))) else None),
                        orientation='level_forward_right_roll_90', geometry_samples_checked=getattr(getattr(self, 'guard', None), 'samples_checked', 0)))

    def _check_cancelled(self):
        if self.cancelled():
            raise RuntimeError('Path planning cancelled')

    def _measured(self, observation, *, require_home=False):
        if observation.get('jetson_id') != self.robot_id or observation.get('source') != 'hardware':
            raise ValueError('Real-arm planning requires feedback from the selected hardware station')
        decision, reason = feedback_decision(observation, observation, now=time.time(), require_home=require_home)
        if decision != 'ready':
            raise ValueError(f'Hardware feedback is not ready: {reason}')
        return self._joint_state(observation)

    def _joint_state(self, observation):
        measured = np.deg2rad(np.concatenate([observation[f'{a}_joints_deg'] for a in ARMS]))
        self.ik._safe_baseline(*(observation[f'{a}_joints_deg'] for a in ARMS))
        self.ik._forward(measured)
        poses = tuple((p.copy(), r.copy()) for p, r in self.ik._poses())
        # The first speed comparison must use actual encoders, including small
        # tolerated baseline excursions, rather than the limit-clipped IK seed.
        return measured.copy(), measured, poses

    def _make_targets(self, poses):
        """Orient each tool forward/level, then approach and trace its outline."""
        if self.together:return self._make_synchronized_targets(poses)
        start = np.array([p for p, _ in poses])
        current = start.copy()
        rotations = [r.copy() for _, r in poses]
        # Grasp +Z points forward; jaws close along world Y, with no downward
        # tilt. The full mesh guard checks alignment, travel and every stroke.
        forward = np.array([[0., 0., 1.], [0., 1., 0.], [-1., 0., 0.]])
        targets = []
        step = self.sketch['speed_m_s']/10

        def move(side, endpoint, rotation, phase):
            nonlocal current, rotations
            i = ARMS.index(side)
            count = max(1, math.ceil(np.linalg.norm(endpoint-current[i])/step),
                        math.ceil(rotation_angle(rotations[i], rotation)/.025))
            if count+len(targets) > MAX_COMMANDS:
                raise ValueError('This drawing exceeds the session budget; increase speed or shorten it')
            origin, original_r = current.copy(), rotations[i].copy()
            for k in range(1, count+1):
                target = origin.copy();target[i] += (endpoint-origin[i])*(k/count)
                target_r = [r.copy() for r in rotations]
                target_r[i] = rotation_mix(original_r, rotation, k/count)
                targets.append(target)
                self.target_rotations.append(tuple(target_r))
                self.target_phases.append({side: phase})
            current = targets[-1].copy()
            rotations = list(self.target_rotations[-1])

        for side, path in self.active.items():
            i = ARMS.index(side)
            forward = self.tool_rotations[i]
            move(side, current[i], forward, 'orient')
            move(side, path[0], forward, 'approach')
            for endpoint in path[1:]:
                move(side, endpoint, forward, 'draw')
            if side == 'left' and len(self.active) == 2:
                for endpoint in path[-2::-1]:
                    move(side, endpoint, forward, 'retract')
                move(side, start[i], forward, 'retract')
                move(side, start[i], poses[i][1], 'retract')
        return targets

    def _closest_separated_pair(self, requested, seed):
        """Keep exact targets when feasible, otherwise minimize outward Y shift.

        A bounded one-dimensional search, not a global trajectory optimum.
        Every candidate still needs full arm/gripper CAD and workspace checks.
        Swept motion is independently checked during the whole-path preflight.
        """
        self._check_cancelled()
        def candidate(shift):
            self._check_cancelled()
            target=requested.copy();target[:,1] += [shift,-shift]
            for i,a in enumerate(ARMS):
                low,high=self.workspace.bounds(a)
                if np.any(target[i]-self.bases[i]<low) or np.any(target[i]-self.bases[i]>high):
                    raise ValueError('Adjusted drawing leaves the controller workspace')
            q=self.ik._solve(seed,tuple(zip(target,self.tool_rotations)))
            self.guard.check(q,self.drawing_grips)
            # Reserve 1 mm above the hard mesh gap for interpolated sweeps.
            if self.guard.last_gripper_clearance_m < GRIPPER_CLEARANCE_M+.001:
                raise ValueError('Drawing needs additional gripper clearance')
            return target,q
        try:return candidate(0.)
        except (ValueError,RuntimeError):pass
        previous=0.
        for shift in np.arange(.005,MAX_PATH_ADJUSTMENT_M+.0001,.005):
            self._check_cancelled()
            try:best=candidate(float(shift))
            except (ValueError,RuntimeError):previous=float(shift);continue
            low,high=previous,float(shift)
            while high-low>.0005:
                self._check_cancelled()
                middle=(low+high)/2
                try:result=candidate(middle)
                except (ValueError,RuntimeError):low=middle
                else:high=middle;best=result
            self.max_path_adjustment_m=max(self.max_path_adjustment_m,high)
            return best
        raise ValueError('No simultaneous path found within 100 mm of the outline. Move the drawing or choose Take turns.')

    def _make_synchronized_targets(self, poses):
        paths=[self.active[a] for a in ARMS]
        distances=[np.r_[0.,np.cumsum(np.linalg.norm(np.diff(path,axis=0),axis=1))] for path in paths]
        # Include every original corner and sample both arms at the same shared
        # progress. Opposite traversal directions avoid endpoint convergence.
        fractions=set(np.linspace(0.,1.,max(2,math.ceil(max(d[-1] for d in distances)/.0025)+1)))
        for d in distances:fractions.update(d/d[-1])
        seed=self.hold_joints.copy()
        paired=[]
        for t in sorted(fractions):
            requested=np.array([arc_path(path,t*d[-1]) for path,d in zip(paths,distances)])
            adjusted,seed=self._closest_separated_pair(requested,seed)
            paired.append(adjusted)
        self.active={a:np.array([pair[i] for pair in paired]) for i,a in enumerate(ARMS)}
        targets=[];current=np.array([p.copy() for p,_ in poses]);rotations=tuple(r.copy() for _,r in poses)
        def move(endpoint,end_rotations,phase):
            nonlocal current,rotations
            count=max(1,math.ceil(np.max(np.linalg.norm(endpoint-current,axis=1))/(self.sketch['speed_m_s']/10)),
                      math.ceil(max(rotation_angle(a,b) for a,b in zip(rotations,end_rotations))/.025))
            if len(targets)+count>MAX_COMMANDS:raise ValueError('Simultaneous drawing exceeds the session budget')
            origin=current.copy();original_r=rotations
            for k in range(1,count+1):
                t=k/count;targets.append(origin+(endpoint-origin)*t)
                self.target_rotations.append(tuple(rotation_mix(a,b,t) for a,b in zip(original_r,end_rotations)))
                self.target_phases.append({a:phase for a in ARMS})
            current=targets[-1].copy();rotations=self.target_rotations[-1]
        move(current,self.tool_rotations,'orient')
        move(paired[0],self.tool_rotations,'approach')
        for endpoint in paired[1:]:move(endpoint,self.tool_rotations,'draw')
        return targets

    def _segment(self, previous, target, seed, held, target_rotations, depth=0):
        self._check_cancelled()
        for side in self.active:
            i = ARMS.index(side)
            low, high = self.workspace.bounds(side)
            if np.any(target[i]-self.bases[i] < low) or np.any(target[i]-self.bases[i] > high):
                raise ValueError(f'The {side} approach leaves the controller workspace')
        # Rebase each packet on measured state, including tracking discrepancies.
        distance = np.linalg.norm(target-previous, axis=1).max()
        self.ik._forward(seed)
        previous_rotations = tuple(r.copy() for _, r in self.ik._poses())
        angle = max(rotation_angle(a,b) for a,b in zip(previous_rotations,target_rotations))
        if distance > self.sketch['speed_m_s']/10 + 1e-9 or angle > .035:
            if depth >= 12:
                raise ValueError('Cannot meet Cartesian pacing from measured feedback')
            mid = (previous+target)/2
            mid_r = tuple(rotation_mix(a,b,.5) for a,b in zip(previous_rotations,target_rotations))
            first = self._segment(previous, mid, seed, held, mid_r, depth+1)
            return first + self._segment(mid, target, first[-1], held, target_rotations, depth+1)
        rotations = tuple(target_rotations[i] if a in self.active else held[i][1] for i, a in enumerate(ARMS))
        positions = tuple(target[i] if a in self.active else held[i][0] for i, a in enumerate(ARMS))
        try:
            solved = self.ik._solve(seed, tuple(zip(positions, rotations)))
        except IKConvergenceError as exc:
            raise ValueError('Path is unreachable with the measured tool orientation; move or shrink the sketch') from exc
        for i, side in enumerate(ARMS):
            if side not in self.active:
                solved[i*6:i*6+6] = self.hold_joints[i*6:i*6+6]
        if np.max(np.abs(solved-seed)) > JOINT_STEP + 1e-12:
            if depth >= 12:
                raise ValueError('Path cannot meet joint speed limits')
            mid = (previous+target)/2
            mid_r = tuple(rotation_mix(a,b,.5) for a,b in zip(previous_rotations,target_rotations))
            first = self._segment(previous, mid, seed, held, mid_r, depth+1)
            return first + self._segment(mid, target, first[-1], held, target_rotations, depth+1)
        self.guard.sweep(seed, solved, self.drawing_grips)
        return [solved]

    def build_trajectory(self, prompt, observation, first_step_id):
        if self.targets is not None and self.cursor == len(self.targets):
            self.phase = 'complete'
            raise PolicyComplete('Drawing confirmed by measured feedback')
        seed, measured, poses = self._measured(observation, require_home=first_step_id == 0)
        self.hold_joints = measured.copy()
        if self.targets is None:
            self.phase = 'checking_entire_path'
            journal=getattr(self,'interaction_sink',None)
            if callable(journal):
                journal('path_requested','Drawing input and measured starting joints',
                        sketch=self.sketch,baseline_joints_deg={a:observation[a+'_joints_deg'] for a in ARMS})
            for side in ARMS:
                value = observation.get(side+'_gripper')
                if type(value) not in (int,float) or not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError('Both measured gripper openings are required for geometry checks')
                self.grips[side] = value
            self.drawing_grips = {a: 0. if a in self.active else self.grips[a] for a in ARMS}
            for t in np.linspace(0,1,11):
                self.guard.check(measured, {a:self.grips[a]*(1-t) if a in self.active else self.grips[a] for a in ARMS})
            self.rotations = tuple(r.copy() for _, r in poses)
            self.targets = self._make_targets(poses)
            previous = np.array([p for p, _ in poses])
            preflight_seed = seed.copy()
            # Validate the entire drawing before the first motion packet.
            for index, target in enumerate(self.targets):
                segment = self._segment(previous, target, preflight_seed, poses, self.target_rotations[index])
                self.preflight_points += len(segment)
                if self.preflight_points > MAX_COMMANDS:
                    raise ValueError('Joint pacing makes this path exceed the session budget')
                preflight_seed = segment[-1]
                previous = target
            if self.preflight_points+math.ceil(self.preflight_points/PACKET_SIZE)*SETTLE_HOLD_STEPS+10 > MAX_COMMANDS:
                raise ValueError('Full drawing and endpoint settling exceed the session budget')
            self.preflight_validated = True
            if callable(journal):
                journal('path_validated','Full drawing, approach and retreat pass swept CAD checks',
                        waypoint_count=self.preflight_points,geometry_samples=self.guard.samples_checked,
                        right_gripper_roll_deg=90,tool_axis_world=[1,0,0],
                        closed_grippers=list(self.active),base_spacing_m=self.spacing)
        # Long preflight must not dispatch from old measurements or an expired lease.
        if callable(self.refresh_observation):
            observation = self.refresh_observation()
            seed, measured, poses = self._measured(observation, require_home=first_step_id == 0)
            self.hold_joints = measured.copy()
        # Close the selected drawing grippers while holding measured arm joints.
        # Motion begins only after this packet completes with closed feedback.
        if not self.grippers_closed:
            grips = {}
            for side in self.active:
                value = observation.get(side+'_gripper')
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError('Measured gripper feedback is required before drawing')
                grips[side] = value
            count = max(1, math.ceil(max(grips.values())/.1))
            if self.preflight_points+count > MAX_COMMANDS or first_step_id+count > MAX_COMMANDS:
                raise ValueError('Drawing and gripper closure exceed the session budget')
            result = []
            for i in range(1, count+1):
                point = dict(step_id=first_step_id+len(result),
                    left_joints_deg=observation['left_joints_deg'][:],
                    right_joints_deg=observation['right_joints_deg'][:])
                point.update({a+'_gripper': max(0., g*(1-i/count)) for a, g in grips.items()})
                self.step_phases[point['step_id']] = {}
                result.append(point)
            self.closing_pending = True
            self.phase = 'closing_grippers'
            return result
        for side in self.active:
            value = observation.get(side+'_gripper')
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= .05:
                raise ValueError('Drawing gripper is not confirmed closed; motion stopped')
        if self.settling:
            # The controller's 0.1 rad completion tolerance can report settled
            # before our 3 mm Cartesian tolerance is met. Re-approach the SAME
            # non-drawing target from fresh encoders, then hold; never advance
            # the drawing cursor or compensate by overshooting the target.
            self.guard.check(seed, self.drawing_grips)
            final = self.pending_cursor-1
            segment = self._segment(np.array([p for p, _ in poses]), self.targets[final],
                                    seed, poses, self.target_rotations[final])
            result = []
            for q in segment:
                degrees = np.rad2deg(q).reshape(2,6)
                point = dict(step_id=first_step_id+len(result),
                             left_joints_deg=degrees[0].tolist(), right_joints_deg=degrees[1].tolist())
                point.update({a+'_gripper':0. for a in self.active})
                self.step_phases[point['step_id']] = {a:'settle' for a in self.active}
                result.append(point)
            self.phase = 'settling_pose'
            return self._hold_endpoint(result, first_step_id)
        self.phase = 'following_path'
        previous = np.array([p for p, _ in poses])
        result = []
        index = self.cursor
        while index < len(self.targets) and len(result) < PACKET_SIZE:
            segment = self._segment(previous, self.targets[index], seed, poses, self.target_rotations[index])
            if len(result)+len(segment) > 300:
                if result:
                    break
                raise ValueError('Measured position diverged too far from the path')
            if first_step_id+len(result)+len(segment) > MAX_COMMANDS:
                raise ValueError('Session waypoint budget exhausted')
            for q in segment:
                degrees = np.rad2deg(q).reshape(2, 6)
                point = dict(step_id=first_step_id+len(result),
                    left_joints_deg=degrees[0].tolist(), right_joints_deg=degrees[1].tolist())
                point.update({a+'_gripper': 0. for a in self.active})
                self.step_phases[point['step_id']] = self.target_phases[index]
                result.append(point)
            seed, previous = segment[-1], self.targets[index]
            index += 1
        self.pending_cursor = index
        return self._hold_endpoint(result, first_step_id)

    def _hold_endpoint(self, result, first_step_id):
        if len(result)+SETTLE_HOLD_STEPS > 300 or first_step_id+len(result)+SETTLE_HOLD_STEPS > MAX_COMMANDS:
            raise ValueError('Drawing and settling exceed the API waypoint budget')
        self.pending_joints = np.deg2rad(result[-1]['left_joints_deg']+result[-1]['right_joints_deg'])
        for _ in range(SETTLE_HOLD_STEPS):
            point = {**result[-1], 'step_id':first_step_id+len(result)}
            self.step_phases[point['step_id']] = {a:'settle' for a in self.active}
            result.append(point)
        return result

    def trajectory_completed(self, observation, waypoint_count):
        if self.closing_pending:
            for side in self.active:
                value = observation.get(side+'_gripper')
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= .05:
                    raise ValueError('Gripper closure was not confirmed; no drawing motion sent')
            self.closing_pending = False
            self.grippers_closed = True
            return
        q = np.deg2rad(np.concatenate([observation[a+'_joints_deg'] for a in ARMS]))
        if self.together:
            # Shape accuracy is soft, measured collision clearance is not.
            # Validate actual encoders and actual jaw openings before accepting
            # a tracking deviation. The next packet rebases from this state.
            self.ik._safe_baseline(*(observation[a+'_joints_deg'] for a in ARMS))
            actual_grips={a:observation.get(a+'_gripper') for a in ARMS}
            if any(type(g) not in (int,float) or not math.isfinite(g) or not 0<=g<=.05 for g in actual_grips.values()):
                raise ValueError('Measured drawing grippers must remain closed')
            self.guard.check(q,actual_grips)
        self.ik._forward(q)
        final = self.pending_cursor-1
        errors, angles = [], []
        for i, (position, rotation) in enumerate(self.ik._poses()):
            error = float(np.linalg.norm(position-self.targets[final][i]))
            errors.append(error)
            angles.append(rotation_angle(rotation,self.target_rotations[final][i]))
        error, angle = max(errors), max(angles)
        self.max_observed_tcp_error_m = max(self.max_observed_tcp_error_m, error)
        tolerance=APPROXIMATE_TRACKING_TOLERANCE_M if self.together else .003
        angle_tolerance=.08 if self.together else .035
        if error > tolerance or angle > angle_tolerance:
            # Strict tracking remains mandatory during a drawing stroke. Small
            # preparation/return errors may settle with bounded, checked retries.
            can_settle = ('draw' not in self.target_phases[final].values()
                          and error <= .025 and angle <= .08
                          and np.max(abs(q-self.pending_joints)) <= .05
                          and self.settle_retries < MAX_SETTLE_RETRIES
                          and error < self.last_settle_error-.0001)
            if not can_settle:
                stage = ', '.join(f'{a} '+dict(orient='alignment',approach='approach',draw='drawing',retract='retreat').get(p,p)
                                  for a,p in self.target_phases[final].items())
                self.failure = f'Measured tool pose missed the drawing target ({error*1000:.1f} mm / {math.degrees(angle):.1f}° during {stage}); drawing stopped'
                self.phase = 'tracking_stopped'
                raise ValueError(self.failure)
            self.settling = True
            self.settle_retries += 1
            self.settle_attempts_total += 1
            self.last_settle_error = error
            self.phase = 'settling_pose'
            return
        self.max_tcp_error_m = max(self.max_tcp_error_m, error)
        self.settling = False
        self.settle_retries = 0
        self.last_settle_error = float('inf')
        self.confirmed_draw_samples += sum('draw' in p.values() for p in self.target_phases[self.cursor:self.pending_cursor])
        self.cursor = self.pending_cursor

    def trajectory_adjusted(self, details):
        # A workspace replacement may be safe, but it no longer draws this path.
        self.failure = 'The station adjusted the requested path; drawing stopped'
        self.phase = 'rejected'
        raise RuntimeError(self.failure)

    def trajectory_failed(self, code, message, waypoint_count, **kwargs):
        # Never reinterpret a gateway rejection as an opportunity to skip a point.
        self.failure = f'{code}: {message}'
        self.phase = 'rejected'
        raise RuntimeError(self.failure)
