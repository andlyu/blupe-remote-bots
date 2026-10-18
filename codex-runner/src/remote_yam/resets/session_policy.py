"""Configured cube program using the normal queue's existing Session API lease."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import threading
import time
from urllib.parse import quote
import uuid

from .cube_runner import run_cube_reset
from .station import configured
from .yam_cube_reset import ResetBlocked
from .yam_cube_reset_io import RobotIO, check_controller_fault

PROTOCOL = 'cube-session-pose-v1'


class SessionResetIO:
    """Camera reads use SSH; every motor request uses the current queue lease.

    reserve/release here refer to this program's use of its existing lease.
    They never reserve LocalPoseControl, pause the queue or create a session.
    """
    session_owned = True

    def __init__(self, camera, api, context, *, cancelled, execution_policy):
        self.camera, self.api, self.context = camera, api, dict(context)
        self.cancelled, self.execution_policy = cancelled, execution_policy
        self.motion_completed_robot_wall = None
        self.reset_replay_handoff = {}
        self._reserved = False
        self.camera.before_request = self.check_cancelled

    @property
    def last_robot_wall(self):
        return self.camera.last_robot_wall

    @property
    def needs_reconnect(self):
        return self.camera.needs_reconnect

    def check_cancelled(self):
        if self.cancelled():
            raise KeyboardInterrupt('Operator stopped the reset session')

    def require_session(self, state):
        self.check_cancelled()
        check_controller_fault(state)
        api = state.get('api', {})
        executor = state.get('cube_reset_session', {})
        if (state.get('mode') != 'API_ACTIVE' or api.get('authorized') is not True
                or any(api.get(k) != self.context[k] for k in ('session_id', 'episode_id'))
                or executor.get('lease_id') != self.context['lease_id']):
            raise KeyboardInterrupt('Reset Session API lease was stopped or replaced')
        if (executor.get('enabled') is not True or executor.get('protocol') != PROTOCOL
                or executor.get('execution_policy') != self.execution_policy):
            raise ResetBlocked('Native controller lacks the selected reset session executor')
        if state.get('safety', {}).get('drives_enabled') is not True:
            raise KeyboardInterrupt('Reset session motor power was disabled')
        return state

    def _execution(self, operation, payload):
        self.check_cancelled()
        sid = self.context['session_id']
        path = '/v1/sessions/'+quote(sid, safe='')+'/executions'
        request_id = uuid.uuid4().hex
        body = dict(schema_version=1, episode_id=self.context['episode_id'],
            lease_id=self.context['lease_id'], request_id=request_id,
            executor='yam_cube_reset', operation=operation, payload=payload)
        capability = self.api._capability(sid)
        # POST once. If the reply is lost, execute_pose reconciles the SAME
        # native plan by status; a second execute is never submitted.
        self.api._request('POST', path, body, bearer=capability)
        deadline = time.monotonic()+120
        while True:
            self.check_cancelled()
            result = self.api._request('GET', path+'/'+request_id, bearer=capability)
            if result.get('status') == 'completed':
                return result['result']
            if result.get('status') == 'failed':
                raise ResetBlocked(result.get('error') or 'Native reset session executor failed')
            if time.monotonic() >= deadline:
                raise TimeoutError('Reset executor outcome uncertain; execution was not retried')
            time.sleep(.1)

    def call(self, operation, payload=None):
        self.check_cancelled()
        if operation == 'state':
            return self.require_session(self.camera.read('state'))
        if operation == 'pose_status':
            return self._execution('status', {})
        if operation == 'reserve':
            if self._reserved or (payload or {}).get('execution_policy') != self.execution_policy:
                raise ResetBlocked('Reset session profile or lease use differs')
            self.call('state')
            self._reserved = True
            return dict(owner_token=self.context['lease_id'], motor_owner='session_api')
        if operation == 'release':
            self._owner(payload)
            self._reserved = False
            return dict(state='released', motor_owner='session_api')
        if operation in ('preview', 'execute', 'wait'):
            self._owner(payload)
            body = {k:v for k,v in payload.items() if k != 'owner_token'}
            if operation == 'preview':
                body['execution_policy'] = self.execution_policy
            return self._execution(operation, body)
        raise ValueError('Unsupported session reset operation')

    def _owner(self, payload):
        if not self._reserved or (payload or {}).get('owner_token') != self.context['lease_id']:
            raise ResetBlocked('Reset no longer owns this Session API lease')

    def read(self, operation):
        if operation not in ('state', 'pose_status'):
            raise ValueError('Continuation reads are limited to controller status')
        return self.call(operation)

    def capture(self, *args, **kwargs):
        self.check_cancelled()
        self.require_session(self.camera.read('state'))
        self.camera.motion_completed_robot_wall = self.motion_completed_robot_wall
        return self.camera.capture(*args, **kwargs)

    def continuation_event(self, *args, **kwargs):
        self.camera.continuation_event(*args, **kwargs)

    def reconnect(self):
        self.check_cancelled()
        self.camera.reconnect()

    def emergency_hold(self):
        # Use normal session Stop, never another owner's local Hold endpoint.
        self.api.stop_session(self.context['session_id'], reason='user_requested')
        before = self.camera.before_request
        try:
            self.camera.before_request = None
            state = self.camera.call('state')
        finally:
            self.camera.before_request = before
        mode = state.get('mode')
        return dict(state='disabled' if mode == 'DISABLED' and state.get('safety', {}).get('torque_off_verified')
            else 'held' if mode in ('STOPPED', 'READY') else 'stopping', mode=mode,
            motor_owner='session_api')


class CubeSessionPolicy:
    def __init__(self, name, spec, directory, *, io_factory=RobotIO, cube_runner=run_cube_reset):
        self.provider_name, self.spec = name, deepcopy(spec)
        self.model = spec['model']
        self.request_id = uuid.uuid4().hex
        self.directory = Path(spec.get('recording_root') or directory)/('session-'+self.request_id)
        self.output = self.directory/'evidence'
        self.cancelled = lambda: False
        self.interaction_sink = None
        self._stop = threading.Event()
        self._phase, self._result = 'queued', None
        self.io_factory, self.cube_runner = io_factory, cube_runner
        for path, expected in spec.get('sha256', {}).items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
                raise ValueError('Configured reset source changed before queue admission')
        self.config = json.loads(Path(spec['session_config']).read_text())
        self.execution_policy = spec.get('execution_policy', 'validated')
        if self.execution_policy not in ('validated', 'controller-faults'):
            raise ValueError('Unknown reset execution policy')

    def public_config(self):
        progress = None
        try:
            progress = json.loads((self.output/'status.json').read_text())
        except (OSError, ValueError):
            pass
        return dict(provider=self.provider_name, model=self.model, display_name=self.spec['label'],
            model_calls=0, recording_path=str(self.directory), execution_owner='session_api',
            managed_execution=dict(request_id=self.request_id, phase=self._phase,
                                   progress=progress, result=deepcopy(self._result)))

    def close_transport(self):
        self._stop.set()

    def run_session(self, prompt, observation, api, context, cancelled):
        if prompt.strip() != self.spec['task']:
            raise ValueError('Configured reset task differs')
        is_cancelled = lambda: cancelled() or self.cancelled() or self._stop.is_set()
        if is_cancelled():
            self._phase = 'cancelled'
            return
        # RunnerController already opens this request's interaction journal.
        # The executable evidence itself must still be a fresh, unused output.
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.output.exists():
            raise RuntimeError('This reset session already has evidence; it is never rerun')
        resources = dict(self.config['resources'], io_routes=self.config['io_routes'])
        transport = self.config['transport']
        self._phase = 'running'
        try:
            with configured(resources), self.io_factory(transport['ssh'], transport.get('identity'),
                    self.directory/'camera-transport', accept_late_frames=True) as camera:
                io = SessionResetIO(camera, api, context, cancelled=is_cancelled,
                                    execution_policy=self.execution_policy)
                self._result = self.cube_runner(self.config, self.output,
                    request_id=self.request_id, shared_io=io)
            if is_cancelled() or self._result.get('state') == 'cancelled':
                self._phase = 'cancelled'
                return
            if self._result.get('goals_reached') is not True:
                self._phase = 'failed'
                raise RuntimeError(self._result.get('error') or 'Reset goals were not reached')
            self._phase = 'complete'
        except KeyboardInterrupt:
            self._phase = 'cancelled'
        except Exception:
            self._phase = 'failed'
            raise
