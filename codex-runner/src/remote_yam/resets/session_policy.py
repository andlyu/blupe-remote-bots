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
RESET_SEQUENCE = ['recorded_box_replay', 'camera_clear_home', 'cube_reset']


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
            state = self.require_session(self.camera.read('state'))
            if self.motion_completed_robot_wall is None:
                # This first same-robot receipt follows the queue's Home. It
                # excludes a still-buffered image from before that handoff.
                self.motion_completed_robot_wall = self.camera.last_robot_wall
            return state
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
            result = self._execution(operation, body)
            if operation == 'wait' and result.get('state') == 'holding':
                # HTTP completion came through the coordinator, while camera
                # timestamps originate on the robot. Obtain the same-host
                # post-completion clock receipt used by the former SSH wait.
                self.require_session(self.camera.read('state'))
                self.motion_completed_robot_wall = self.camera.last_robot_wall
            return result
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

    def captures(self, report, count=3, *, after_robot_wall=None, camera='top'):
        # Reuse distinct-frame selection through OUR capture method, so every
        # frame retains the lease/Stop check and post-motion clock receipt.
        return RobotIO.captures(self, report, count=count,
                                after_robot_wall=after_robot_wall, camera=camera)

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

    def sequence_motion(self, kind, *, recipe=None, request_id=None, timeout_s=720):
        """Execute one existing native plan once; never retry an uncertain POST."""
        payload = dict(motion_kind=kind, execution_policy=self.execution_policy)
        if recipe is not None:
            payload.update(recipe=recipe, replay_request_id=request_id)
        plan = self._execution('preview', payload)
        plan_id = plan['plan_id']
        self._execution('execute', dict(plan_id=plan_id))
        deadline = time.monotonic()+timeout_s
        while True:
            result = self._execution('wait', dict(plan_id=plan_id, timeout_s=2))
            if result.get('state') == 'holding':
                self.require_session(self.camera.read('state'))
                self.motion_completed_robot_wall = self.camera.last_robot_wall
                return result
            if result.get('state') in ('failed', 'interrupted'):
                raise ResetBlocked('Reset sequence motion did not complete; no next stage')
            if time.monotonic() >= deadline:
                raise TimeoutError('Reset sequence completion uncertain; no retry or next stage')


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
        self.sequence = spec.get('sequence', ['cube_reset'])
        if self.sequence not in (['cube_reset'], RESET_SEQUENCE):
            raise ValueError('Unknown reset sequence')
        if self.sequence == RESET_SEQUENCE:
            recipe = self.config.get('recipe', {})
            if (recipe.get('schema') != 'abc-replay-edit-v1' or recipe.get('return_home') is not False
                    or not recipe.get('source_sha256') or not recipe.get('calibration_id')):
                raise ValueError('Reset requires its immutable recorded box Replay recipe')

    def public_config(self):
        progress = None
        try:
            progress = json.loads((self.output/'status.json').read_text())
        except (OSError, ValueError):
            try:
                progress = json.loads((self.directory/'sequence/status.json').read_text())
            except (OSError, ValueError):
                pass
        return dict(provider=self.provider_name, model=self.model, display_name=self.spec['label'],
            model_calls=0, recording_path=str(self.directory), execution_owner='session_api',
            sequence=list(self.sequence),
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
                if self.sequence == RESET_SEQUENCE:
                    self.run_recorded_box_stage(io)
                io.check_cancelled()
                self._result = self.cube_runner(self.config, self.output,
                    request_id=self.request_id, shared_io=io)
                if self.sequence == RESET_SEQUENCE:
                    from .cube_runner import save
                    self._result.update(sequence=list(self.sequence), replay_requested=True)
                    save(self.output/'result.json', self._result)
            if is_cancelled() or self._result.get('state') == 'cancelled':
                self._phase = 'cancelled'
                return deepcopy(self._result)
            if self._result.get('goals_reached') is not True:
                self._phase = 'failed'
                raise RuntimeError(self._result.get('error') or 'Reset goals were not reached')
            self._phase = 'complete'
            return deepcopy(self._result)
        except KeyboardInterrupt:
            self._phase = 'cancelled'
            self._result = self._result or dict(state='cancelled', goals_reached=False,
                                                request_id=self.request_id)
            return deepcopy(self._result)
        except Exception:
            self._phase = 'failed'
            raise

    def run_recorded_box_stage(self, io):
        from .cube_runner import save
        from .yam_tabletop_reset import require_replay_complete
        receipt = self.directory/'sequence'
        receipt.mkdir(exist_ok=False)
        recipe = deepcopy(self.config['recipe'])
        save(receipt/'request.json', dict(request_id=self.request_id, sequence=self.sequence,
            recipe=recipe, motor_owner='session_api', movement_retry=False))
        state = io.call('state')
        if state['cube_reset_session'].get('recorded_replay_supported') is not True:
            raise ResetBlocked('Native session executor lacks recorded Replay support')
        try:
            self._phase = 'recorded_box_replay'
            save(receipt/'status.json', dict(phase=self._phase))
            result = io.sequence_motion('recorded_replay', recipe=recipe, request_id=self.request_id)
            save(receipt/'replay-result.json', result)
            require_replay_complete(result.get('replay_result', {}), self.request_id)
            io.call('state')  # A Stop during the handoff prevents Home/cube.
            self._phase = 'camera_clear_home'
            save(receipt/'status.json', dict(phase=self._phase))
            home = io.sequence_motion('camera_clear_home')
            save(receipt/'home-result.json', home)
            state = io.call('state')
            if home.get('reached_target') is not True or not (state.get('homed') and state.get('settled')):
                raise ResetBlocked('Camera-clear Home did not complete; no cube stage')
            self._phase = 'cube_reset'
            save(receipt/'status.json', dict(phase=self._phase, replay_complete=True, home_complete=True))
        except BaseException as exc:
            # Use the same normal session Stop for failure/uncertain Replay.
            # No manual owner, Park, torque cycle or initialization is inserted.
            failure = dict(error=str(exc), phase=self._phase, next_stage_started=False)
            try:
                io.api.stop_session(io.context['session_id'], reason='user_requested')
            except Exception as stop_error:
                failure['stop_error'] = str(stop_error)
            save(receipt/'failure.json', failure)
            raise
