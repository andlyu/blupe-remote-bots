"""Speculative first plans. Saved home observations never count as live feedback."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import threading
import time

from .cameras import CameraFrame

MAX_AGE_S = 120.0
CAMERAS = {'left', 'top', 'right'}


def profile_key(provider):
    config = provider.public_config()
    fields = {k: config.get(k) for k in ('provider', 'model', 'prompt_sha256',
              'prompt_version', 'response_speed', 'reasoning_effort', 'controller_workspace')}
    fields['system_prompt'] = getattr(provider, '_system_prompt', '')
    fields['endpoint'] = getattr(provider, '_endpoint', 'codex_exec')
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def eligible(provider):
    # Other embodiments and depth/session policies have additional observation
    # contracts and are deliberately excluded until they implement this protocol.
    return (type(provider).__module__ in {'remote_yam.robocurve_policy', 'remote_yam.codex_policy'}
            and provider.provider_name in {'openai', 'astra', 'codex'}
            and callable(getattr(provider, 'build_trajectory', None)))


def decode_scene(scene, robot_id, now=None):
    now = time.time() if now is None else now
    if not isinstance(scene, dict) or scene.get('version') != 1:
        raise ValueError('unsupported_scene')
    if scene.get('robot_id') != robot_id:
        raise ValueError('wrong_robot')
    for key in ('scene_id', 'config_sha256', 'boot_id'):
        if not isinstance(scene.get(key), str) or not scene[key]:
            raise ValueError('missing_provenance')
    if not re.fullmatch('[a-f0-9]{64}', scene['config_sha256']):
        raise ValueError('invalid_configuration_digest')
    captured = scene.get('captured_at')
    if type(captured) not in (int, float) or not math.isfinite(captured) or not 0 <= now-captured <= MAX_AGE_S:
        raise ValueError('stale_scene')
    observation = dict(scene['observation'])
    measured = observation.get('observed_at')
    if type(measured) not in (int,float) or not math.isfinite(measured) or abs(measured-captured) > .25:
        raise ValueError('incoherent_pose_timestamp')
    if (observation.get('source') != 'hardware' or observation.get('homed') is not True
            or observation.get('settled') is not True):
        raise ValueError('unconfirmed_home')
    if observation.get('jetson_id') != robot_id:
        raise ValueError('wrong_observation_robot')
    for arm in ('left', 'right'):
        joints = observation.get(arm+'_joints_deg')
        if not isinstance(joints, list) or len(joints) != 6 or any(type(v) not in (int,float) or not math.isfinite(v) for v in joints):
            raise ValueError('invalid_pose')
        grip = observation.get(arm+'_gripper')
        if type(grip) not in (int,float) or not math.isfinite(grip) or abs(grip-1.) > .02:
            raise ValueError('unconfirmed_grippers')
    raw_frames = scene.get('frames', {})
    if set(raw_frames) != CAMERAS:
        raise ValueError('missing_views')
    frames = []
    stamps = []
    for name, raw in raw_frames.items():
        encoded = raw['jpeg_base64']
        if not isinstance(encoded, str) or len(encoded) > 4*1024*1024:
            raise ValueError('oversized_frame')
        data = base64.b64decode(encoded, validate=True)
        if not data.startswith(b'\xff\xd8') or hashlib.sha256(data).hexdigest() != raw['sha256']:
            raise ValueError('invalid_frame')
        stamp = raw['captured_at']
        if type(stamp) not in (int,float) or not math.isfinite(stamp) or abs(stamp-captured) > .25:
            raise ValueError('incoherent_frames')
        stamps.append(stamp)
        frames.append(CameraFrame(name, data, captured, source_captured_at=stamp))
    if max(stamps)-min(stamps) > .15:
        raise ValueError('incoherent_frames')
    observation.update(_home_scene_frames=frames, planning_scene={
        'kind':'saved_home', 'scene_id':scene['scene_id'], 'captured_at':captured,
        'meaning':'Planned future home starting state; not current live robot feedback.'})
    return observation


class HomePlan:
    """One run-owned worker; caller must join it before reuse or run teardown."""
    def __init__(self, provider, prompt, scene, robot_id, session_id, cancelled):
        self.provider = provider
        self.scene = scene
        self.session_id = session_id
        self.cancel = threading.Event()
        self.done = threading.Event()
        self.result = None
        self.error = None
        self.elapsed_s = None
        self.started = time.monotonic()
        observation = decode_scene(scene, robot_id)
        observation.update(episode_id='home-plan:'+session_id, lease_id='unleased', step_id=0)
        provider._home_plan_request = True
        self.previous_cancelled = provider.cancelled
        provider.cancelled = lambda: self.cancel.is_set() or cancelled()
        def work():
            try:
                self.result = provider.build_trajectory(prompt, observation, 0)
                if self.result and not provider.cancelled():
                    self.elapsed_s = time.monotonic()-self.started
            except Exception as exc:
                self.error = exc
            finally:
                self.done.set()
        self.thread = threading.Thread(target=work, name='yam-home-plan', daemon=True)
        self.thread.start()

    def close(self, *, cancel=False):
        if cancel:
            self.cancel.set()
            interrupt = getattr(self.provider, "cancel_pending_request", None)
            if callable(interrupt):
                interrupt()
        self.thread.join()
        self.provider.cancelled = self.previous_cancelled
        self.provider._home_plan_request = False

    def bind(self, observation):
        self.provider._episode = tuple(observation.get(k) for k in ('episode_id', 'lease_id'))

    def discard(self):
        self.close(cancel=True)
        provider = self.provider
        # Discard the entire speculative conversation, including Codex resume
        # state, so failed/stale scene reasoning cannot influence fresh planning.
        provider._history = []
        provider._pending = None
        provider._outcome = None
        provider._episode = None
        provider._prompt = None
        provider._failures = 0
        provider._geometry.start_rotations = None
        provider._note = None
        if hasattr(provider, '_thread_id'):
            provider._thread_id = None
            provider._sent_items = 0
