"""Bounded, model-free forward camera sweep through the normal runner."""
from copy import deepcopy
import json
import math
from pathlib import Path
import time

import numpy as np
from remote_yam.mujoco_ik import BimanualRelativeIK
from remote_yam.providers import PolicyComplete
from remote_yam.session import _trajectory_waypoints, MAX_COMMANDS
from remote_yam.controller_workspace import workspace_for_robot

TASK = 'Record a forward camera sweep over the 3D scene.'
METHOD = 'Forward scene video · 12 cm / 12 seconds'
ARMS = ('left', 'right')


class SweepPolicy:
    provider_name = 'scene_video'
    model = METHOD
    # Match RunnerController's existing generic measured-endpoint tolerance.
    # Hardware guard, settling and dispatch limits remain independent.
    final_joint_tolerance_deg = math.degrees(.05)

    def __init__(self, report, directory=None, *, simulation=False):
        self.report = deepcopy(report)
        self.robot_id = report['robot_id']
        self.simulation = simulation
        self.directory = Path(directory) if directory else None
        self.cancelled = lambda: False
        self.complete = False
        self.pending = None
        self.distance_m = .12
        self.samples = 120
        profile = workspace_for_robot(self.robot_id)
        if profile is None:
            raise ValueError('Unregistered station')
        profile.validate_report(report)
        self.bounds = [np.array([np.maximum([.15, -.5, .03], profile.bounds(a)[0]),
                                 np.minimum([.48, .5, .4], profile.bounds(a)[1])]) for a in ARMS]
        self.spacing = .5 if self.robot_id == 'yam-1' else .62
        offsets = report.get('model_joint_calibration', {}).get('offsets_rad')
        offsets = offsets['left'] + offsets['right'] if offsets else None
        self.ik = BimanualRelativeIK(base_spacing_m=self.spacing, joint_offsets_rad=offsets)
        safety = profile._safety()
        self.ik.constrain_joint_limits(dict(lower_rad=safety['joint_lower_rad'], upper_rad=safety['joint_upper_rad']))
        self.bases = np.array([[0, self.spacing/2, 0], [0, -self.spacing/2, 0]])
        self.cameras = [np.asarray(report['cameras'][a]['T_grasp_camera'], float) for a in ARMS]
        for transform in self.cameras:
            if (transform.shape != (4, 4) or not np.isfinite(transform).all()
                    or not np.allclose(transform[3], [0, 0, 0, 1])
                    or not np.allclose(transform[:3, :3].T @ transform[:3, :3], np.eye(3), atol=1e-5)):
                raise ValueError('Invalid wrist camera transform')

    def public_config(self):
        return dict(provider=self.provider_name, model=self.model, display_name=METHOD,
                    task=TASK, model_calls=0, execution_mode='simulation' if self.simulation else 'agent-operated',
                    distance_m=self.distance_m, duration_s=12, cadence_hz=10,
                    grippers='hold measured fractions', orientation='hold measured camera attitude',
                    recording_path=str(self.directory) if self.directory else None,
                    calibration_id=self.report.get('calibration_id'))

    def _read(self, observation, *, require_home=True):
        expected = 'simulation' if self.simulation else 'hardware'
        if (observation.get('source') != expected or observation.get('settled') is not True
                or (require_home and observation.get('homed') is not True)
                or observation.get('safety', {}).get('ok') is not True
                or observation.get('robot_id', observation.get('jetson_id')) != self.robot_id):
            raise ValueError('Requires matching, homed, settled, safe feedback')
        age = time.time() - observation.get('observed_at', 0)
        if not 0 <= age <= 2:
            raise ValueError('Feedback is stale')
        q = np.asarray(observation['left_joints_deg'] + observation['right_joints_deg'], float)
        if q.shape != (12,) or not np.isfinite(q).all():
            raise ValueError('Invalid measured joints')
        q = np.deg2rad(q)
        if np.any(q < self.ik.low) or np.any(q > self.ik.high):
            raise ValueError('Measured joints exceed existing limits')
        for a in ARMS:
            value = observation[a+'_gripper']
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('Invalid measured gripper fraction')
        self.ik._forward(q)
        return q, self.ik._poses()

    def camera_geometry(self, poses):
        result = []
        for i, (p, rotation) in enumerate(poses):
            t = self.cameras[i]
            position = p + rotation @ t[:3, 3]
            axis = rotation @ t[:3, 2]
            if axis[2] >= -.35 or position[2] < .12:
                raise ValueError('Wrist camera is not directed down over the scene')
            hit = position - position[2] / axis[2] * axis
            local_hit = hit - self.bases[i]
            if not .15 <= local_hit[0] <= .85 or abs(local_hit[1]) > .45:
                raise ValueError('Wrist camera optical axis misses the tabletop scene')
            result.append(dict(position_m=position.tolist(), optical_axis=axis.tolist(),
                               table_intersection_m=hit.tolist()))
        return result

    def build_trajectory(self, prompt, observation, first_step_id):
        if prompt.strip() != TASK:
            raise ValueError('This policy only records a forward scene sweep')
        if self.complete:
            raise PolicyComplete('Forward sweep completed; verify matching dataset recording')
        if self.pending is not None:
            raise RuntimeError('No replay of a pending or uncertain movement')
        if type(first_step_id) is not int or first_step_id < 0 or first_step_id+self.samples > MAX_COMMANDS:
            raise ValueError('Invalid/exhausted command cursor')
        seed, start = self._read(observation)
        self.camera_geometry(start)
        points, evidence = [], []
        previous = seed.copy()
        for index in range(1, self.samples+1):
            if self.cancelled():
                raise RuntimeError('Sweep cancelled before dispatch')
            delta = self.distance_m if index == self.samples else self.distance_m * index/self.samples
            targets = tuple((p+np.array([delta, 0, 0]), r) for p, r in start)
            seed = self.ik._solve(previous, targets)
            if np.any(seed < self.ik.low) or np.any(seed > self.ik.high):
                raise ValueError('Generated joints exceed existing limits')
            if np.max(np.abs(seed-previous)) > .035:
                raise ValueError('Forward sweep exceeds existing joint pacing')
            self.ik._forward(seed)
            actual = self.ik._poses()
            for arm, (p, r) in enumerate(actual):
                local = p-self.bases[arm]
                if np.any(local < self.bounds[arm][0]) or np.any(local > self.bounds[arm][1]):
                    raise ValueError('Sweep leaves existing workspace')
                if np.linalg.norm(p-targets[arm][0]) > 2e-6 or np.max(np.abs(r-targets[arm][1])) > 2e-5:
                    raise ValueError('Sweep did not preserve position/attitude')
            point = dict(step_id=first_step_id+index-1,
                         left_joints_deg=np.rad2deg(seed[:6]).tolist(),
                         right_joints_deg=np.rad2deg(seed[6:]).tolist(),
                         left_gripper=observation['left_gripper'], right_gripper=observation['right_gripper'])
            points.append(point)
            evidence.append(dict(step_id=point['step_id'], cameras=self.camera_geometry(actual)))
            previous = seed.copy()
        points = _trajectory_waypoints(points)
        self.pending = dict(last=points[-1], start=[p.tolist() for p, _ in start],
                            identity=[observation.get(k) for k in ('episode_id', 'lease_id')])
        if self.directory:
            self.directory.mkdir(parents=True, exist_ok=True)
            (self.directory/'sweep-plan.json').write_text(json.dumps(dict(config=self.public_config(),
                waypoints=points, geometry=evidence), indent=2))
        return points

    def validate_trajectory_final(self, observation):
        self._read(observation, require_home=False)
        if self.pending is None:
            raise RuntimeError('No pending movement')
        if [observation.get(k) for k in ('episode_id', 'lease_id')] != self.pending['identity']:
            raise RuntimeError('Episode/lease changed')
        if observation.get('step_id') != self.pending['last']['step_id']+1:
            raise RuntimeError('Sweep completion cursor mismatch')
        for a in ARMS:
            if np.max(np.abs(np.deg2rad(np.array(observation[a+'_joints_deg'])-
                          self.pending['last'][a+'_joints_deg']))) > math.radians(self.final_joint_tolerance_deg):
                raise RuntimeError('Measured sweep endpoint was not reached')
        self.complete = True
        self.pending = None

    def infer(self, *args):
        raise RuntimeError('Use the validated trajectory path')
