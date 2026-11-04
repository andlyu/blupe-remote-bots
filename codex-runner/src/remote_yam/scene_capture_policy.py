"""The reviewed one-minute camera path through the ordinary trajectory runner."""
from copy import deepcopy
import json
from pathlib import Path
import time

import numpy as np

from remote_yam.providers import PolicyComplete
from remote_yam.session import _trajectory_waypoints
from .scene_capture_base import SweepPolicy
from .scene_capture_path import plan, guard_path

METHOD = 'Scene capture · multi-view sweep'
TASK = 'Record a multi-view scene episode with the guided capture preset.'


class MinutePolicy(SweepPolicy):
    provider_name = 'scene_video_minute'
    model = METHOD

    def __init__(self, report, config, directory=None, *, simulation=False):
        super().__init__(report,directory,simulation=simulation)
        self.config=config
        self.total=config['duration_s']*10
        self.cursor=0
        self.route=None
        self.identity=None

    def public_config(self):
        return dict(provider=self.provider_name,model=METHOD,display_name=METHOD,task=TASK,
                    model_calls=0,execution_mode='simulation' if self.simulation else 'agent-operated',
                    duration_s=self.config['duration_s'],maximum_session_s=240,cadence_hz=10,waypoints=self.total,
                    packets=(self.total+299)//300,grippers='hold initial measured fractions',
                    camera_aim='shared center and near/far scene regions',
                    maximum_grasp_forward_m=self.config['reach_m'],capture_config=self.config,
                    path_progress=dict(confirmed=self.cursor,total=self.total),calibration_id=self.report.get('calibration_id'))

    def build_trajectory(self,prompt,observation,first_step_id):
        if prompt.strip()!=TASK:raise ValueError('Select the one-minute scene capture task')
        if self.complete:raise PolicyComplete('Minute capture completed; matching recording retained')
        if self.pending is not None:raise RuntimeError('No replay of a pending or uncertain movement')
        if type(first_step_id) is not int or first_step_id!=self.cursor:
            raise ValueError('Minute trajectory cursor mismatch')
        q,_=self._read(observation,require_home=self.cursor==0)
        identity=[observation.get(k) for k in ('episode_id','lease_id')]
        if not all(isinstance(x,str) and x for x in identity):raise ValueError('Missing episode/lease identity')
        if self.cancelled():raise RuntimeError('Capture cancelled before planning')
        if self.route is None:
            home=q[:6].tolist()+[observation['left_gripper']]+q[6:].tolist()+[observation['right_gripper']]
            route=plan(self,home,self.config['reach_m'],self.config['scan_width_m'],self.config['aim_x_m'],self.config['duration_s'])
            samples=guard_path(route,home,self)
            if self.cancelled():raise RuntimeError('Capture cancelled before dispatch')
            self.route=route
            self.identity=identity
            if self.directory:
                self.directory.mkdir(parents=True,exist_ok=True)
                (self.directory/'minute-plan.json').write_text(json.dumps(dict(
                    config=self.public_config(),hardware_guard_swept_samples=samples,**route),indent=2))
        elif identity!=self.identity:raise RuntimeError('Episode/lease changed')
        points=deepcopy(self.route['waypoints'][self.cursor:self.cursor+300])
        if len(points)!=min(300,self.total-self.cursor):raise RuntimeError('Minute route is incomplete')
        # Fresh measured feedback must also safely join the next packet.
        previous=q
        for point in points:
            target=np.deg2rad(point['left_joints_deg']+point['right_joints_deg'])
            if np.max(np.abs(target-previous))>.035:
                raise ValueError('Measured state cannot join the verified path within joint pacing')
            previous=target
        points=_trajectory_waypoints(points)
        if self.cancelled():raise RuntimeError('Capture cancelled before dispatch')
        self.pending=dict(last=points[-1],identity=identity)
        return points

    def validate_trajectory_final(self,observation):
        # Reuse the measured endpoint, safety, freshness, lease and next-cursor
        # checks. Home is required only before the first packet.
        super().validate_trajectory_final(observation)
        self.cursor=observation['step_id']
        self.complete=self.cursor==self.total
        if self.cursor not in range(300,self.total+300,300) and self.cursor!=self.total:raise RuntimeError('Unexpected minute completion cursor')
