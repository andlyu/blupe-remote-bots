"""Trusted generated-controller adapter for the canonical RunnerController.

Generated code owns neither a session capability nor a transport. It requests
DeviceLayer commands on a bounded JSON channel; this adapter compiles them and
the unchanged RunnerController owns queue/Home/dispatch/feedback/Stop.
"""
from copy import deepcopy
import json
import re

from remote_yam.providers import PolicyComplete
from yam_commands import YamCommands, CommandRejected, unique_fields, SAFETY_SHA256


class BridgeProtocolError(RuntimeError):
    pass


def packet(raw):
    if not isinstance(raw, str) or len(raw.encode()) > 16000:
        raise BridgeProtocolError('Controller channel requires bounded JSON lines')
    try:
        value = json.loads(raw, object_pairs_hook=unique_fields)
    except ValueError as exc:
        raise BridgeProtocolError('Controller channel returned invalid JSON') from exc
    if not isinstance(value, dict) or type(value.get('request_id')) is not int:
        raise BridgeProtocolError('Controller channel requires an integer request_id')
    return value


def public_feedback(observation):
    # Explicit allowlist excludes lease/capability/identity fields and URLs.
    keys = ('source', 'observed_at', 'settled', 'homed', 'left_joints_deg',
            'right_joints_deg', 'left_gripper', 'right_gripper')
    return {key:deepcopy(observation[key]) for key in keys if key in observation}


class GeneratedControllerProvider:
    provider_name = 'gemini_robotics'
    trajectory_cadence_hz = 10
    supports_workspace_replanning = False

    def __init__(self, runner_root, channel, *, controller_sha256, capture=None):
        if not isinstance(controller_sha256, str) or re.fullmatch(r'[a-f0-9]{64}', controller_sha256) is None:
            raise ValueError('An exact generated-controller SHA256 is required')
        self.compiler = YamCommands(runner_root)
        self.channel, self.controller_sha256 = channel, controller_sha256
        self.capture = capture
        self.cancelled = lambda: False
        self.refresh_observation = None
        self.interaction_sink = None
        self.initialized = False
        self.next_request = 0
        self.pending = None
        self.completed = False

    def public_config(self):
        return dict(provider=self.provider_name, model='Gemini Robotics',
                    display_name='Gemini Robotics', coding_model='gemini-4-hydrogen',
                    controller_sha256=self.controller_sha256,
                    native_safety_sha256=SAFETY_SHA256,
                    execution='Isolated generated controller via canonical RunnerController',
                    api_key_configured=False)

    def infer(self, *_):
        raise BridgeProtocolError('Generated controllers require the canonical trajectory transport')

    def prepare_before_session(self, prompt):
        del prompt
        self._event('controller_preparing', 'Starting the isolated controller runtime before queue admission',
                    state='in_progress')
        self.channel.start(lambda:self.cancelled())
        self._event('controller_ready', 'Isolated controller runtime confirmed ready', state='completed')

    def _event(self, kind, message, **details):
        if callable(self.interaction_sink):
            self.interaction_sink(kind, message, **details)

    def _snapshot(self, observation):
        result = dict(observation=public_feedback(observation))
        if self.capture is not None:
            # The trusted source supplies bounded fresh bytes/metadata; no URL
            # chosen by generated code is ever fetched by this adapter.
            result['cameras'] = self.capture(observation)
        return result

    def _send(self, value):
        if self.cancelled():
            raise BridgeProtocolError('Controller stopped; no new command sent')
        self.channel.send(value)

    def build_trajectory(self, prompt, observation, first_step_id):
        del prompt
        if self.completed:
            raise PolicyComplete('Generated controller finished')
        if self.pending is not None:
            raise BridgeProtocolError('Previous controller packet has no measured completion')
        if not self.initialized:
            self._send(dict(kind='begin', **self._snapshot(observation)))
            self.initialized = True
        while not self.cancelled():
            value = packet(self.channel.receive(self.cancelled))
            if self.cancelled():
                raise BridgeProtocolError('Controller stopped during generation; no motion sent')
            if value['request_id'] != self.next_request:
                raise BridgeProtocolError('Controller request cursor changed; no packet replayed')
            self.next_request += 1
            kind = value.get('kind')
            if kind == 'complete' and set(value) == {'kind', 'request_id'}:
                self.completed = True
                raise PolicyComplete('Generated controller finished; object outcome requires visual verification')
            if kind == 'observe' and set(value) == {'kind', 'request_id'}:
                if not callable(self.refresh_observation):
                    raise BridgeProtocolError('Fresh observation requires the canonical controller context')
                observation = self.refresh_observation()
                self._send(dict(kind='observation', request_id=value['request_id'], **self._snapshot(observation)))
                continue
            if kind != 'command' or set(value) != {'kind', 'request_id', 'payload'}:
                raise BridgeProtocolError('Unsupported controller operation; no motion sent')
            try:
                points = self.compiler.compile(value['payload'], observation, first_step_id)
            except CommandRejected as exc:
                self._event('controller_rejected', str(exc), stage='local_validation', dispatched=False,
                            request_id=value['request_id'])
                self._send(dict(kind='rejected', request_id=value['request_id'],
                                stage='local_validation', dispatched=False, message=str(exc)))
                # A generated controller may explicitly revise a local input
                # error using a new request and freshly reconciled feedback.
                if not callable(self.refresh_observation):
                    raise BridgeProtocolError('Fresh feedback unavailable after local rejection') from exc
                observation = self.refresh_observation()
                self._send(dict(kind='observation', request_id=value['request_id'], **self._snapshot(observation)))
                continue
            if self.cancelled():
                raise BridgeProtocolError('Controller stopped after local validation; no motion sent')
            self.pending = dict(request_id=value['request_id'], count=len(points), last_step=points[-1]['step_id'])
            self._event('controller_compiled', 'Controller command passed local packet validation',
                        stage='local_validation', dispatched=False, request_id=value['request_id'],
                        first_step_id=first_step_id, waypoint_count=len(points))
            return points
        raise BridgeProtocolError('Controller stopped; no motion sent')

    def trajectory_completed(self, observation, count):
        if (self.pending is None or type(count) is not int or count != self.pending['count']
                or observation.get('settled') is not True
                or observation.get('step_id') != self.pending['last_step'] + 1):
            raise BridgeProtocolError('Measured completion does not match the pending controller request')
        request = self.pending['request_id']
        self.pending = None
        self._send(dict(kind='completed', request_id=request, **self._snapshot(observation)))

    def trajectory_failed(self, code, message, count, **kwargs):
        # Do not automatically replay failures or unknown physical outcomes.
        self.pending = None
        self._event('controller_execution_failed', 'Canonical execution ended without matching completion',
                    code=code, executed_waypoints=count)
        raise BridgeProtocolError('Canonical execution failed: ' + str(code) + '; stop and review, no automatic retry')

    def close(self):
        self.channel.close()
