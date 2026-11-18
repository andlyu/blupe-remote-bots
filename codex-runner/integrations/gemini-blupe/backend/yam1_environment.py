"""Bimanual controller API over Google's DeviceLayer keys and generic IK.

An adapted YAM1 variant, not the stock single-YAM-Pro PlaygroundSim2Real.
Both backends expose the same run(env), arm methods and normalized units.
"""
import base64
import io
import json
import math

from dm_env import specs
import imageio.v2 as imageio
import numpy as np

from yam1_scene import ARMS
from yam1_kinematics import Yam1Kinematics


class LocalCommandRejected(ValueError):
    stage = 'local_validation'
    dispatched = False


def measurements(snapshot):
    o = snapshot['observation']
    result = dict(observed_at=o.get('observed_at'), source=o.get('source'))
    for arm in ARMS:
        for j, value in enumerate(o[arm + '_joints_deg'], 1):
            result[f'{arm}/follower/joint_position/joint{j}'] = np.float64(math.radians(value))
        result[f'{arm}/follower/joint_position/gripper'] = np.float64(o[arm + '_gripper'])
    for name, frame in snapshot.get('cameras', {}).items():
        raw = base64.b64decode(frame['jpeg_base64'], validate=True)
        if len(raw) > 2*1024*1024:
            raise ValueError('Camera frame exceeds the image bound')
        rgb = imageio.imread(io.BytesIO(raw))
        if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.size > 640*480*3:
            raise ValueError('Expected bounded RGB8 camera frame')
        result[name] = rgb
        result[name + '/captured_at'] = frame['captured_at']
    return result


class RpcDeviceLayer:
    """Container side of a host-validated DeviceLayer, without network access."""
    def __init__(self, source, sink, safety):
        self.source, self.sink, self.safety = source, sink, safety
        self.request_id = 0
        self._closed = False
        self.snapshot = self._read()
        if self.snapshot.get('kind') != 'begin':
            raise ValueError('Canonical controller must provide the first measured observation')

    def _read(self):
        line = self.source.readline(8*1024*1024+1)
        if not line.endswith('\n') or len(line.encode()) > 8*1024*1024:
            raise RuntimeError('Controller observation missing or oversized')
        return json.loads(line)

    def _request(self, kind, **fields):
        if self._closed: raise RuntimeError('DeviceLayer has ended')
        request = self.request_id; self.request_id += 1
        self.sink.write(json.dumps(dict(kind=kind, request_id=request, **fields), allow_nan=False) + '\n')
        self.sink.flush()
        return request

    def measurements_spec(self):
        return {f'{arm}/follower/joint_position/{j}':specs.Array((), np.float64)
                for arm in ARMS for j in [*[f'joint{i}' for i in range(1,7)],'gripper']}

    def commands_spec(self):
        result = {}
        for i, arm in enumerate(ARMS):
            for j in range(7):
                name = f'joint{j+1}' if j < 6 else 'gripper'
                low = self.safety['joint_lower_rad'][i*6+j] if j < 6 else 0.
                high = self.safety['joint_upper_rad'][i*6+j] if j < 6 else 1.
                result[f'{arm}/follower/goal_position/{name}'] = specs.BoundedArray((), np.float64, low, high)
        return result

    def begin_stepping(self): return measurements(self.snapshot)

    def apply(self, commands, duration_s):
        request = self._request('command', payload=dict(commands=commands, duration_s=duration_s))
        value = self._read()
        if value.get('request_id') != request:
            raise RuntimeError('Controller feedback request identity changed')
        if value.get('kind') == 'rejected' and value.get('dispatched') is False:
            fresh = self._read()
            if fresh.get('kind') != 'observation' or fresh.get('request_id') != request:
                raise RuntimeError('Local rejection was not followed by fresh canonical feedback')
            self.snapshot = fresh
            raise LocalCommandRejected(value['message'])
        if value.get('kind') != 'completed':
            raise RuntimeError('Controller has no matched measured completion; do not replay')
        self.snapshot = value
        return measurements(value)

    def step(self, commands): return self.apply(commands, .1)

    def observe(self):
        request = self._request('observe')
        value = self._read()
        if value.get('kind') != 'observation' or value.get('request_id') != request:
            raise RuntimeError('Fresh observation identity changed')
        self.snapshot = value
        return measurements(value)

    def end_stepping(self):
        if not self._closed:
            self._request('complete')
            self._closed = True


class Arm:
    def __init__(self, environment, name): self.env, self.name = environment, name

    @property
    def q_arm(self):
        return np.array([self.env.measurements[f'{self.name}/follower/joint_position/joint{i}'] for i in range(1,7)])

    @property
    def gripper(self): return float(self.env.measurements[f'{self.name}/follower/joint_position/gripper'])

    def move_joint(self, q_arm, gripper=None, *, duration_s=1.):
        q = np.asarray(q_arm)
        if q.shape != (6,) or q.dtype.kind not in 'fi' or not np.isfinite(q).all():
            raise LocalCommandRejected('move_joint needs six finite native radian targets')
        commands = {f'{self.name}/follower/goal_position/joint{i+1}':float(value) for i,value in enumerate(q)}
        if gripper is not None:
            if type(gripper) not in (float,int) or not math.isfinite(gripper) or not 0<=gripper<=1:
                raise LocalCommandRejected('gripper target must be a finite normalized number in [0,1]')
            commands[f'{self.name}/follower/goal_position/gripper'] = gripper
        self.env._measurements = self.env.device_layer.apply(commands, duration_s)
        return self.env.measurements

    def set_gripper(self, value, *, duration_s=.5):
        if type(value) not in (float,int) or not math.isfinite(value) or not 0<=value<=1:
            raise LocalCommandRejected('gripper target must be a finite normalized number in [0,1]')
        self.env._measurements = self.env.device_layer.apply(
            {f'{self.name}/follower/goal_position/gripper':value}, duration_s)
        return self.env.measurements

    def solve_arm_ik(self, pos_world, *, target_rot_world=None):
        self.env._sync_fk()
        return self.env.kinematics.solve(self.name, pos_world, target_rot_world=target_rot_world)


class Yam1Environment:
    def __init__(self, scene, device_layer, skills_root):
        self.scene, self.device_layer = scene, device_layer
        self.kinematics = Yam1Kinematics(scene, skills_root)
        self._measurements = device_layer.begin_stepping()
        self.left, self.right = Arm(self,'left'), Arm(self,'right')

    @property
    def measurements(self): return self._measurements

    def observe(self):
        self._measurements = self.device_layer.observe()
        return self.measurements

    def _sync_fk(self):
        arms = {side:getattr(self,side).q_arm for side in ARMS}
        grippers = {side:getattr(self,side).gripper for side in ARMS}
        self.scene.set_configuration(arms, grippers)

    def close(self): self.device_layer.end_stepping()
