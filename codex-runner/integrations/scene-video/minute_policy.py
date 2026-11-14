"""The reviewed one-minute camera path through the ordinary trajectory runner."""
from copy import deepcopy
import json
from pathlib import Path
import time

import numpy as np

from remote_yam.providers import PolicyComplete
from remote_yam.session import _trajectory_waypoints
from scene_video import SweepPolicy
from viewpoint_sim import plan, guard_path

METHOD = 'Scene video · 60-second multi-view sweep'
TASK = 'Record a one-minute multi-view video of the scene.'


class MinutePolicy(SweepPolicy):
    provider_name = 'scene_video_minute'
    model = METHOD

    def __init__(self, report, directory=None, *, hardware_root, simulation=False):
        super().__init__(report,directory,simulation=simulation)
        self.hardware_root=Path(hardware_root)
        self.cursor=0
        self.route=None
        self.identity=None

    def public_config(self):
        return dict(provider=self.provider_name,model=METHOD,display_name=METHOD,task=TASK,
                    model_calls=0,execution_mode='simulation' if self.simulation else 'agent-operated',
                    duration_s=60,maximum_session_s=120,cadence_hz=10,waypoints=600,
                    packets=2,grippers='hold initial measured fractions',
                    camera_aim='shared center and near/far scene regions',
                    maximum_grasp_forward_m=.47,calibration_id=self.report.get('calibration_id'))

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
            route=plan(self,home,.47)
            samples=guard_path(route,home,self.hardware_root)
            if self.cancelled():raise RuntimeError('Capture cancelled before dispatch')
            self.route=route
            self.identity=identity
            if self.directory:
                self.directory.mkdir(parents=True,exist_ok=True)
                (self.directory/'minute-plan.json').write_text(json.dumps(dict(
                    config=self.public_config(),hardware_guard_swept_samples=samples,**route),indent=2))
        elif identity!=self.identity:raise RuntimeError('Episode/lease changed')
        points=deepcopy(self.route['waypoints'][self.cursor:self.cursor+300])
        if len(points)!=300:raise RuntimeError('Minute route is incomplete')
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
        self.complete=self.cursor==600
        if self.cursor not in (300,600):raise RuntimeError('Unexpected minute completion cursor')
