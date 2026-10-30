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
    health_mismatch = 'YAM1 checkpoint contract/CUDA mismatch'
    readiness_timeout = 'YAM1 GPU did not become ready within twenty minutes'

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
        self._initialize(api_key, provider, MODELS[provider], endpoint, camera_source)

    def _initialize(self, api_key, provider, spec, endpoint, camera_source):
        self.provider_name = provider
        self.spec = spec
        self.model = self.spec['model']
        self._endpoint = endpoint.rstrip('/')
        self._api_key = api_key.strip()
        self._camera_source = camera_source
        self._robot_id = 'yam-1'
        self._profile_label = 'YAM1'
        self._joint_counts = (6, 6)
        self._camera_names = ('top', 'left', 'right')
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

    def _device_valid(self, value):
        return value.get('device') == 'cuda:0'

    def _health_matches(self, health):
        return (self._identity(health) and health.get('ok') and health.get('cuda_available')
                and self._device_valid(health) and health.get('action_dim') == 14
                and health.get('num_actions') == self.spec['num_actions']
                and health.get('norm_tag') == self.spec['norm_tag'])

    def start_preparation(self, cancelled):
        if self._thread is not None:
            return
        self._warm_state = 'warming'
        self._thread = threading.Thread(target=self._keep_ready, args=(cancelled,), daemon=True)
        self._thread.start()

    def prepare_before_session(self, prompt):
        # RunnerController's existing pre-session hook keeps cold GPU loading
        # outside the Jetson's selected-duration lease and hardware timer.
        if self.cancelled():
            raise RuntimeError('YAM1 policy preparation cancelled')
        self.interaction_sink('model_progress', 'Preparing ' + self.spec['label']
            + ' GPU before joining the robot queue; the run timer has not started')
        self.start_preparation(self.cancelled)
        self.wait_ready(self.cancelled)
        self.interaction_sink('model_progress', self.spec['label'] + ' GPU ready; joining the robot queue')

    def _keep_ready(self, cancelled):
        # The first prepared DreamZero cold launch took 14m53s. Warm before
        # controller dispatch; never replay an observation across this wait.
        deadline = time.monotonic() + 1200
        while not cancelled():
            try:
                health = self._json('/health')
                if not self._health_matches(health):
                    if health.get('ok'):
                        self._ready.clear()
                        self._failure = self.health_mismatch
                        self._warm_state = 'failed'
                        return
                    raise RuntimeError('YAM1 checkpoint is preparing')
                self._warm_state = 'ready'
                self._ready.set()
                deadline = time.monotonic() + 1200
                delay = 30
            except RuntimeError:
                self._ready.clear()
                if self._failure:
                    return
                self._warm_state = 'warming'
                delay = 5
                if time.monotonic() >= deadline:
                    self._failure = self.readiness_timeout
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
        if observation.get('robot_id', observation.get('jetson_id')) != self._robot_id:
            raise ValueError('This policy requires ' + self._profile_label + ' observations')
        if not self._ready.is_set():
            raise RuntimeError('YAM1 policy is not ready')
        state = []
        gripper_indices = []
        for arm, count in zip(('left', 'right'), self._joint_counts):
            if not count:
                continue
            joints, gripper = observation[arm + '_joints_deg'], observation[arm + '_gripper']
            if (len(joints) != count or not all(self._number(v) for v in joints)
                    or not self._number(gripper) or not 0 <= gripper <= 1):
                raise ValueError('Policy requires measured joints and normalized grippers for the selected robot')
            state.extend(math.radians(v) for v in joints)
            gripper_indices.append(len(state))
            state.append(gripper)
        frames = self._capture_policy_frames(observation)
        if len(frames) != len(self._camera_names) or {f.name for f in frames} != set(self._camera_names):
            raise ValueError('Policy requires all configured cameras for the selected robot')
        from PIL import Image
        images = {}
        for frame in frames:
            output = io.BytesIO()
            with Image.open(io.BytesIO(frame.jpeg)) as image:
                image.convert('RGB').resize((640, 360)).save(output, format='JPEG')
            images[frame.name] = base64.b64encode(output.getvalue()).decode()
        if self.cancelled():
            raise RuntimeError('YAM1 policy cancelled')
        started = time.monotonic()
        try:
            result = self._json('/act', dict(robot_id=self._robot_id, instruction=prompt, state=state,
                images=images, action_units='radians', gripper_units=GRIPPER_UNITS))
        finally:
            self.interaction_sink('model_timing', 'YAM1 policy request finished',
                elapsed_s=time.monotonic() - started)
        if self.cancelled():
            raise RuntimeError('YAM1 policy cancelled')
        rows = result.get('actions')
        reason = None
        if not self._identity(result):
            reason = 'checkpoint_identity_or_units'
        elif not self._device_valid(result):
            reason = 'cuda_device'
        elif not isinstance(rows, list) or len(rows) != self.spec['num_actions']:
            reason = 'action_horizon'
        elif any(not isinstance(row, list) or len(row) != len(state) for row in rows):
            reason = 'action_width'
        elif any(not all(self._number(v) for v in row) for row in rows):
            reason = 'nonfinite_or_nonnumeric_action'
        if reason is None:
            grips = [row[i] for row in rows for i in gripper_indices]
            projected = sum(not 0 <= value <= 1 for value in grips)
            if self.provider_name == 'dreamzero':
                # The pinned release decodes continuous relative gripper actions
                # by adding measured state. They can overshoot normalized ends.
                # Match dream_policy.action_waypoints' bounded actuator mapping;
                # keep the raw model result intact and never clip arm joints.
                rows = [list(row) for row in rows]
                for row in rows:
                    for index in gripper_indices:
                        row[index] = min(1., max(0., row[index]))
                self.interaction_sink('model_response', 'DreamZero action chunk decoded',
                    raw_gripper_min=min(grips), raw_gripper_max=max(grips),
                    gripper_values_clipped=projected, action_count=len(rows))
            elif projected:
                reason = 'gripper_out_of_range'
        if reason:
            details = dict(reason=reason)
            if reason == 'gripper_out_of_range':
                for side, index in zip((side for side, count in zip(('left', 'right'), self._joint_counts) if count), gripper_indices):
                    values = [row[index] for row in rows]
                    details[side + '_gripper_min'] = min(values)
                    details[side + '_gripper_max'] = max(values)
            self.interaction_sink('model_failure', 'YAM1 action chunk rejected before dispatch', **details)
            raise ValueError('Invalid YAM1 action chunk (' + reason + '); no targets dispatched')
        # Match the GR00T gateway contract: select every third 30 Hz target.
        # DreamZero keeps eight 10 Hz waypoints (0.8s), MolmoAct2 ten (1s).
        targets = rows[2::3]
        if len(targets) > min(MAX_WAYPOINTS_PER_PACKET, MAX_COMMANDS - first_step_id):
            raise ValueError('YAM1 trajectory exceeds gateway budget; chunk rejected')
        points = []
        for target in targets:
            if self.cancelled():
                raise RuntimeError('YAM1 policy cancelled')
            point = dict(step_id=first_step_id + len(points))
            offset = 0
            for side, count in zip(('left', 'right'), self._joint_counts):
                joints = [math.degrees(v) for v in target[offset:offset + count]]
                if not all(math.isfinite(v) for v in joints):
                    raise ValueError('Targets must convert to finite gateway angles')
                point[side + '_joints_deg'] = joints
                if count:
                    point[side + '_gripper'] = target[offset + count]
                    offset += count + 1
            points.append(point)
        return points

    def _capture_policy_frames(self, observation):
        return self._camera_source.capture_for_policy(observation, cancelled=self.cancelled)

    @staticmethod
    def _number(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

    def trajectory_completed(self, observation, waypoint_count):
        pass
