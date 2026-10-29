"""Dream One instances using controller-local inputs and native execution.

SDK/encoding/action semantics stay in DreamAdapter; see
docs/refs/dreamlabs/{client,STARTUP-CONTRACT}.md (SDK 1.0.0).
This module starts no web server, motor driver, recorder, or video publisher.
"""
from __future__ import annotations

import json
import math
import threading
import time
from urllib.request import ProxyHandler, Request, build_opener
from urllib.parse import urlsplit
import uuid

from .cameras import CameraFrameSource, NoRedirect, trusted_origin
from .dream_policy import DreamAdapter, DreamWorker, MODELS, state_input


def loopback_origin(value):
    trusted_origin(value)
    if urlsplit(value).hostname not in {'127.0.0.1', '::1', 'localhost'}:
        raise ValueError('Controller inputs require a loopback origin')
    return value.rstrip('/')


class LoopbackControllerInputs:
    """Read-only smoke-test inputs from the existing physical operator.

    status() obtains a new native snapshot only in initialized states. Reject
    all other states before interpreting its cached display joints. The request
    start is a conservative lower bound on snapshot time, not a motor timestamp.
    """
    def __init__(self, *, robot_id, cameras, operator_origin='http://127.0.0.1:8096',
                 camera_origin='http://127.0.0.1:8089'):
        if set(cameras) != {'left', 'top', 'right'} or any(
                type(v) is not int or v < 0 for v in cameras.values()):
            raise ValueError('Require the controller profile camera aliases')
        self.robot_id, self.cameras = robot_id, dict(cameras)
        self.operator_origin = loopback_origin(operator_origin)
        self.camera_origin = loopback_origin(camera_origin)
        self.opener = build_opener(ProxyHandler({}), NoRedirect)
        self.last_read = None

    def __call__(self):
        started_at, began = time.time(), time.monotonic()
        with self.opener.open(Request(self.operator_origin + '/api/status', method='GET'), timeout=2) as response:
            status = json.load(response)
        ended_at = time.time()
        if (status.get('backend') != 'physical_i2rt'
                or status.get('mode') not in {'READY', 'STOPPED', 'API_ACTIVE'}
                or status.get('feedback_available') is not True or status.get('adapter_fault')):
            raise RuntimeError('Live probe requires initialized physical feedback')
        identity = status.get('robot_id') or (status.get('dataset') or {}).get('robot_id')
        if identity != self.robot_id:
            raise ValueError('Controller robot identity is unavailable or changed')
        joints = status.get('joints')
        if (not isinstance(joints, list) or len(joints) != 12 or any(
                type(v) not in (int, float) or not math.isfinite(v) for v in joints)):
            raise ValueError('Controller measured joints are unavailable')
        elapsed = time.monotonic() - began
        if elapsed > 1 or ended_at < started_at:
            raise RuntimeError('Controller feedback read is stale')
        observation = dict(jetson_id=self.robot_id, observed_at=started_at,
            left_joints_deg=[math.degrees(v) for v in joints[:6]],
            right_joints_deg=[math.degrees(v) for v in joints[6:]],
            left_gripper=status.get('left_gripper'), right_gripper=status.get('right_gripper'),
            images={role: {'url': f'{self.camera_origin}/{device}/snapshot.jpg'}
                    for role, device in self.cameras.items()})
        state_input(observation, '')
        self.last_read = dict(source='native_status_snapshot', duration_s=elapsed,
            bracket_started_at=started_at, bracket_ended_at=ended_at,
            controller_mode=status['mode'], existing_session_present=bool(status.get('api', {}).get('session_id')))
        return observation


class NativeControllerDream:
    """An in-process adapter instance; the existing operator owns all execution.

    Call predict() for the current lease, then submit() once for its result.
    The existing controller still handles Home, trajectory validation/completion,
    workspace recovery, lease expiry and Stop. No background motion loop is added.
    """
    def __init__(self, operator, *, robot_id, credentials, python, directory,
                 provider='dream', camera_origin='http://127.0.0.1:8089',
                 cameras=None,
                 gateway_max_step_deg=9, adapter_factory=DreamAdapter,
                 worker_factory=DreamWorker, dispatch=None):
        self.operator, self.robot_id = operator, robot_id
        self.cancel = threading.Event()
        self.operation = threading.RLock()
        self.pending = None
        self.camera_origin = loopback_origin(camera_origin)
        if cameras is not None and (set(cameras) != {'left', 'top', 'right'} or any(
                type(v) is not int or v < 0 for v in cameras.values())):
            raise ValueError('Require the controller profile camera aliases')
        self.cameras = dict(cameras) if cameras is not None else None
        self.dispatch = dispatch or operator.api_handle_joint_trajectory
        self.adapter = adapter_factory(provider=provider, model=MODELS[provider][0],
            credentials=credentials, python=python, directory=directory,
            robot_id=robot_id, observation_source=self.observation,
            camera_source=CameraFrameSource(self.camera_origin),
            gateway_max_step_deg=gateway_max_step_deg, worker_factory=worker_factory)

    def context(self):
        op = self.operator
        with op.lock:
            context = (op.api_session_id, op.api_episode_id, op.api_lease_id)
            if (not all(context) or not op.api_authorized or op.mode != 'API_ACTIVE'
                    or self.cancel.is_set()):
                raise RuntimeError('Dream does not own an active controller lease')
            return context

    def observation(self):
        op = self.operator
        with op.lock:
            if op.api_client.jetson_id != self.robot_id:
                raise RuntimeError('Dream controller identity changed')
            observation = dict(op._api_observation_locked())
            observation['jetson_id'] = self.robot_id
            # A wrapper can import the native module before its profile sets
            # camera globals. Keep direct inference on the explicit profile's
            # existing relay aliases, independent of public observation URLs.
            if self.cameras is not None:
                observation['images'] = {role: {'url': f'{self.camera_origin}/{device}/snapshot.jpg'}
                    for role, device in self.cameras.items()}
            return observation

    def predict(self, prompt):
        with self.operation:
            return self._predict(prompt)

    def _predict(self, prompt):
        self.pending = None
        context = self.context()
        self.adapter.cancelled = lambda: self.cancel.is_set() or self._context_changed(context)
        with self.operator.lock:
            first_step_id = self.operator.api_last_step + 1
        points = self.adapter.build_trajectory(prompt, self.observation(), first_step_id)
        if self.context() != context:
            raise RuntimeError('Dream lease changed during prediction; result discarded')
        # Keep our own copy; a caller cannot substitute a different path at submit.
        self.pending = (context, json.loads(json.dumps(points, allow_nan=False)))
        return points

    def _context_changed(self, expected):
        try:
            return self.context() != expected
        except RuntimeError:
            return True

    def submit(self):
        with self.operation:
            return self._submit()

    def _submit(self):
        pending, self.pending = self.pending, None
        if pending is None:
            raise RuntimeError('No unused Dream prediction')
        context, points = pending
        op = self.operator
        with op.lock:
            if self.context() != context:
                raise RuntimeError('Dream lease changed; prediction discarded')
            payload = dict(schema_version=1, type='joint_trajectory',
                session_id=context[0], episode_id=context[1], lease_id=context[2],
                trajectory_id='dream-' + uuid.uuid4().hex, dispatched_at=time.time(),
                cadence_hz=10, waypoints=points)
        # The physical handler acquires its hardware lock before op.lock and
        # revalidates the lease itself. Never invert that order around dispatch.
        return self.dispatch(payload)

    def trajectory_completed(self, observation, waypoint_count):
        callback = getattr(self.adapter, 'trajectory_completed', None)
        if callable(callback):
            callback(observation, waypoint_count)

    def trajectory_adjusted(self, details):
        callback = getattr(self.adapter, 'trajectory_adjusted', None)
        if callable(callback):
            callback(details)

    def trajectory_failed(self, *args, **kwargs):
        callback = getattr(self.adapter, 'trajectory_failed', None)
        if callable(callback):
            callback(*args, **kwargs)

    def close(self):
        self.cancel.set()
        self.pending = None
        close = getattr(self.adapter, 'close_transport', None)
        if callable(close):
            close()
        workspace = getattr(self.adapter, '_workspace', None)
        if workspace is not None and callable(getattr(workspace, 'cleanup', None)):
            workspace.cleanup()
        if hasattr(self.adapter, '_api_key'):
            self.adapter._api_key = ''
