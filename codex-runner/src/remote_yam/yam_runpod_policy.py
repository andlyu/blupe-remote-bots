"""Pinned joint policies for YAM1; the leased controller owns all robot IO.

Contracts: MolmoAct2 BimanualYAM model card (8dcbed66), and DreamZero's
merged YAM release evaluator (f9b72b8d). Both use 30 Hz absolute arm radians
and normalized grippers, but their chunk lengths are different.
"""
import base64
import io
import json
import math
import re
import threading
import time
from urllib import request
from urllib.parse import urlsplit

from .cameras import NoRedirect
from .session import MAX_COMMANDS, MAX_WAYPOINTS_PER_PACKET

GRIPPER_UNITS = 'normalized_0_closed_1_open'
MODELS = {
    'molmoact2': dict(label='MolmoAct2 · YAM1', model='allenai/MolmoAct2-BimanualYAM',
        revision='8dcbed66f2380e4393189c303ea72488eb9e63c2', num_actions=30,
        norm_tag='yam_dual_molmoact2'),
    'dreamzero': dict(label='DreamZero · MolmoAct2 YAM1', model='robocurve/dreamzero-yam-molmoact2',
        revision='f9b72b8dfa124f7283c5b1d467ce2ff9253c737a', num_actions=24,
        norm_tag='yam_dreamzero_molmoact2'),
}


class YAMRunpodAdapter:
    def __init__(self, api_key, *, provider, endpoint, camera_source, robot_id):
        if robot_id != 'yam-1':
            raise ValueError('This checkpoint is configured only for YAM1')
        if provider not in MODELS:
            raise ValueError('Unknown YAM1 checkpoint')
        if not api_key.strip():
            raise ValueError('RunPod service credential is missing')
        location = urlsplit(endpoint)
        if (location.scheme != 'https' or not re.fullmatch(r'[a-z0-9]+\.api\.runpod\.ai', location.netloc)
                or location.path not in ('', '/') or location.query or location.fragment):
            raise ValueError('A configured RunPod endpoint is required')
        self.provider_name = provider
        self.spec = MODELS[provider]
        self.model = self.spec['model']
        self._endpoint = endpoint.rstrip('/')
        self._api_key = api_key.strip()
        self._camera_source = camera_source
        self.cancelled = lambda: False
        self.interaction_sink = lambda *args, **kwargs: None
        self._ready = threading.Event()
        self._failure = None
        self._warm_state = 'waiting_for_queue'
        self._thread = None
        self._opener = request.build_opener(NoRedirect)

    def public_config(self):
        return dict(provider=self.provider_name, model=self.model, revision=self.spec['revision'],
                    warmup=self._warm_state, api_key_configured=bool(self._api_key))

    def _json(self, path, payload=None):
        req = request.Request(self._endpoint + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={'Authorization': 'Bearer ' + self._api_key, 'Content-Type': 'application/json'})
        try:
            with self._opener.open(req, timeout=30 if payload is None else 12) as response:
                value = json.loads(response.read(8 * 1024 * 1024))
                if not isinstance(value, dict):
                    raise ValueError('Expected a policy object')
                return value
        except Exception as exc:
            raise RuntimeError('RunPod request failed (' + type(exc).__name__ + ')') from None

    def _identity(self, value):
        return (value.get('robot_id') == 'yam-1' and value.get('model') == self.model
                and value.get('revision') == self.spec['revision']
                and value.get('action_units') == 'radians'
                and value.get('gripper_units') == GRIPPER_UNITS)

    def start_preparation(self, cancelled):
        if self._thread is not None:
            return
        self._warm_state = 'warming'
        self._thread = threading.Thread(target=self._keep_ready, args=(cancelled,), daemon=True)
        self._thread.start()

    def _keep_ready(self, cancelled):
        # The first prepared DreamZero cold launch took 14m53s. Warm before
        # controller dispatch; never replay an observation across this wait.
        deadline = time.monotonic() + 1200
        while not cancelled():
            try:
                health = self._json('/health')
                if not (self._identity(health) and health.get('ok') and health.get('cuda_available')
                        and health.get('device') == 'cuda:0' and health.get('action_dim') == 14
                        and health.get('num_actions') == self.spec['num_actions']
                        and health.get('norm_tag') == self.spec['norm_tag']):
                    if health.get('ok'):
                        self._ready.clear()
                        self._failure = 'YAM1 checkpoint contract/CUDA mismatch'
                        self._warm_state = 'failed'
                        return
                    raise RuntimeError('YAM1 checkpoint is preparing')
                self._warm_state = 'ready'
                self._ready.set()
                deadline = time.monotonic() + 1200
                delay = 30
            except RuntimeError:
                self._ready.clear()
                self._warm_state = 'warming'
                delay = 5
                if time.monotonic() >= deadline:
                    self._failure = 'YAM1 GPU did not become ready within twenty minutes'
                    self._warm_state = 'failed'
                    return
            until = time.monotonic() + delay
            while not cancelled() and time.monotonic() < until:
                time.sleep(.1)
        self._ready.clear()
        self._warm_state = 'released'

    def wait_ready(self, cancelled):
        waited = not self._ready.is_set()
        while not self._ready.wait(.1):
            if cancelled():
                raise RuntimeError('YAM1 policy preparation cancelled')
            if self._failure:
                raise RuntimeError(self._failure)
        if cancelled():
            raise RuntimeError('YAM1 policy preparation cancelled')
        return waited

    def build_trajectory(self, prompt, observation, first_step_id):
        if observation.get('robot_id', observation.get('jetson_id')) != 'yam-1':
            raise ValueError('This checkpoint requires YAM1 observations')
        if not self._ready.is_set():
            raise RuntimeError('YAM1 policy is not ready')
        state = []
        for arm in ('left', 'right'):
            joints, gripper = observation[arm + '_joints_deg'], observation[arm + '_gripper']
            if (len(joints) != 6 or not all(self._number(v) for v in joints)
                    or not self._number(gripper) or not 0 <= gripper <= 1):
                raise ValueError('YAM1 requires measured six-joint arms and normalized grippers')
            state.extend(math.radians(v) for v in joints)
            state.append(gripper)
        frames = self._camera_source.capture_for_policy(observation, cancelled=self.cancelled)
        if len(frames) != 3 or {f.name for f in frames} != {'top', 'left', 'right'}:
            raise ValueError('YAM1 requires top and both wrist cameras')
        from PIL import Image
        images = {}
        for frame in frames:
            output = io.BytesIO()
            with Image.open(io.BytesIO(frame.jpeg)) as image:
                image.convert('RGB').resize((640, 360)).save(output, format='JPEG')
            images[frame.name] = base64.b64encode(output.getvalue()).decode()
        if self.cancelled():
            raise RuntimeError('YAM1 policy cancelled')
        result = self._json('/act', dict(robot_id='yam-1', instruction=prompt, state=state,
            images=images, action_units='radians', gripper_units=GRIPPER_UNITS))
        if self.cancelled():
            raise RuntimeError('YAM1 policy cancelled')
        rows = result.get('actions')
        if (not self._identity(result) or result.get('device') != 'cuda:0'
                or not isinstance(rows, list) or len(rows) != self.spec['num_actions']
                or any(not isinstance(row, list) or len(row) != 14
                       or not all(self._number(v) for v in row) for row in rows)
                or any(not 0 <= row[i] <= 1 for row in rows for i in (6, 13))):
            raise ValueError('Invalid YAM1 action chunk; no targets dispatched')
        # Match the GR00T gateway contract: select every third 30 Hz target.
        # DreamZero keeps eight 10 Hz waypoints (0.8s), MolmoAct2 ten (1s).
        targets = rows[2::3]
        if len(targets) > min(MAX_WAYPOINTS_PER_PACKET, MAX_COMMANDS - first_step_id):
            raise ValueError('YAM1 trajectory exceeds gateway budget; chunk rejected')
        points = []
        for target in targets:
            if self.cancelled():
                raise RuntimeError('YAM1 policy cancelled')
            left = [math.degrees(v) for v in target[:6]]
            right = [math.degrees(v) for v in target[7:13]]
            if not all(math.isfinite(v) for v in left + right):
                raise ValueError('Targets must convert to finite gateway angles')
            points.append(dict(step_id=first_step_id + len(points), left_joints_deg=left,
                right_joints_deg=right, left_gripper=target[6], right_gripper=target[13]))
        return points

    @staticmethod
    def _number(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

    def trajectory_completed(self, observation, waypoint_count):
        pass
