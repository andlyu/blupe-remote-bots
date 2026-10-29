"""Lease-bound Dream loop inside the existing physical operator process.

The installed operator still owns validation, execution, recording and Stop.
Only direct trajectory acknowledgements are consumed here; observations and
all station/session messages continue through its existing Session API client.
"""
from copy import deepcopy
from collections import deque
import math
import threading
import time

from .controller_dream import NativeControllerDream
from .controller_executor import ROBOHOUSE
from .dream_worker_pool import DreamWorkerPool

CONTEXT = ('session_id', 'episode_id', 'lease_id')
TERMINAL = {'completed', 'cancelled', 'failed'}
NATIVE_FAILURE_CODES = {
    'operator_not_authorized', 'authority_revoked', 'command_in_flight',
    'trajectory_id_conflict', 'position_fetch_busy', 'safety_guardrails_unavailable',
    'workspace_return_failed', 'left_tip_outside_workspace', 'right_tip_outside_workspace',
    'adjacent_delta_limit', 'joint_velocity_limit', 'joint_settle_timeout',
    'predicted_collision', 'collision_checker_failed', 'collision_checker_unavailable',
    'forward_kinematics_failed', 'forward_kinematics_unavailable', 'physical_execution_failure',
    'invalid_dispatched_at', 'invalid_gateway_time', 'invalid_trajectory_cadence',
    'invalid_trajectory_id', 'invalid_trajectory_payload', 'invalid_trajectory_type',
    'invalid_waypoint', 'lease_mismatch', 'missing_trajectory_fields', 'missing_waypoint_fields',
    'noncontiguous_step_id', 'stale_trajectory', 'future_trajectory', 'empty_trajectory',
    'trajectory_too_long', 'unexpected_trajectory_fields', 'unexpected_waypoint_fields',
    'unsupported_trajectory_cadence', 'unsupported_trajectory_schema',
    *{f'{prefix}joint_{joint}_outside_limits' for prefix in ('', 'start_') for joint in range(12)},
    *{f'{side}_gripper_delta_limit' for side in ('left', 'right')},
    *{f'invalid_{side}_{field}' for side in ('left', 'right') for field in ('joints', 'gripper', 'gripper_start')},
}


class DreamControllerExecutor:
    def __init__(self, operator, *, robot_id, credentials, python, directory,
                 pool_factory=DreamWorkerPool, native_factory=NativeControllerDream,
                 **adapter_settings):
        if robot_id != ROBOHOUSE or operator.api_client.jetson_id != robot_id:
            raise ValueError('Dream executor requires the installed RoboHouse identity')
        self.operator = operator
        self.settings = dict(robot_id=robot_id, credentials=credentials, python=python,
                             directory=directory, **adapter_settings)
        self.native_factory = native_factory
        self.pool = pool_factory(python, credentials, directory)
        self.lock = threading.RLock()
        self.cancelled = threading.Event()
        self.thread = None
        self.native = None
        self.prepared = None
        self.context = None
        self.state = 'idle'
        self.packets = self.waypoints = 0
        self.predictions = self.predicted_waypoints = 0
        self.trajectory = None
        self.failure = None
        self.owned_receipts = deque(maxlen=8192)
        self._send = operator.api_client.send
        operator.api_client.send = self.send
        self.preparation_done = threading.Event()
        threading.Thread(target=self._prime, daemon=True, name='controller-dream-prepare').start()

    def _prime(self):
        try:
            self.pool.prime()
        except Exception:
            pass  # Readiness is exposed by pool.status(), without raw SDK errors.
        finally:
            self.preparation_done.set()

    def prepare(self, payload):
        """Call only after the original operator accepts prepare_session."""
        self.cancel()
        with self.lock:
            self.prepared = deepcopy(payload)

    def _owns(self, context):
        op = self.operator
        with op.lock:
            return (tuple(getattr(op, 'api_' + key) for key in CONTEXT) == context
                    and op.api_authorized and op.mode == 'API_ACTIVE')

    def status(self):
        with self.lock:
            return dict(state=self.state, packets=self.packets, waypoints=self.waypoints,
                        predictions=self.predictions, predicted_waypoints=self.predicted_waypoints,
                        failure=deepcopy(self.failure),
                        worker=self.pool.status())

    def request(self, payload):
        if (payload.get('executor') != 'dream_one' or payload.get('payload') != {}
                or payload.get('operation') not in {'start', 'predict', 'status'}):
            raise ValueError('Unsupported Dream request')
        context = tuple(payload.get(key) for key in CONTEXT)
        expiry = payload.get('expires_at')
        if (not all(isinstance(v, str) and v for v in context)
                or type(expiry) not in (float, int) or not math.isfinite(expiry)
                or expiry <= time.time() or not self._owns(context)):
            raise ValueError('Dream request has no current controller lease')
        with self.lock:
            already_started = self.context == context
        if payload['operation'] == 'start' and not already_started:
            with self.operator.lock:
                observation = self.operator._api_observation_locked()
            if observation.get('homed') is not True or observation.get('settled') is not True:
                raise ValueError('Wait for the normal settled Home observation')
        with self.lock:
            if payload['operation'] == 'status':
                if self.context != context:
                    raise ValueError('Dream has not started for this lease')
                return self.status()
            if self.context == context:
                # A new HTTP request ID must not start a second policy loop.
                return self.status()
            if self.thread and self.thread.is_alive():
                raise ValueError('Previous Dream worker is still releasing its lease')
            prepared = self.prepared
            if (not prepared or tuple(prepared.get(k) for k in CONTEXT) != context
                    or not isinstance(prepared.get('task'), str) or not prepared['task'].strip()
                    or prepared.get('provider') not in (None, '', 'dream')):
                raise ValueError('Dream requires the current session task')
            self.context = context
            self.cancelled = threading.Event()
            self.state = 'preparing'
            self.packets = self.waypoints = 0
            self.predictions = self.predicted_waypoints = 0
            self.failure = None
            self.thread = threading.Thread(target=self._run,
                args=(deepcopy(prepared), payload['operation'] == 'predict'),
                daemon=True, name='controller-dream')
            self.thread.start()
            return self.status()

    def cancel(self):
        # Stop never waits for an HTTP/SDK request or worker cleanup.
        with self.lock:
            self.cancelled.set()
            if self.native:
                self.native.cancel.set()

    def _cancelled(self):
        return self.cancelled.is_set() or not self._owns(self.context)

    def _run(self, prepared, predict_only):
        native = None
        try:
            while not self.preparation_done.wait(.05):
                if self._cancelled():
                    return
            if self._cancelled():
                return
            if not self.pool.status()['ready']:
                raise RuntimeError('Dream worker preparation failed')
            native = self.native_factory(self.operator, **self.settings,
                worker_factory=self.pool.factory, dispatch=self._dispatch)
            with self.lock:
                self.native = native
            native.adapter.configure_run_duration(prepared.get('run_duration_s', 120))
            while not self._cancelled():
                with self.operator.lock:
                    budget_reached = self.operator.api_last_step + 1 >= native.adapter._max_commands
                if budget_reached:
                    with self.lock:
                        self.state = 'completed'
                    return
                with self.lock:
                    self.state = 'predicting'
                points = native.predict(prepared['task'])
                if self._cancelled():
                    return
                with self.lock:
                    self.predictions += 1
                    self.predicted_waypoints += len(points)
                if predict_only or not points:
                    with self.lock:
                        self.state = 'completed'
                    return
                with self.lock:
                    self.state = 'executing'
                native.submit()
                with self.lock:
                    self.packets += 1
                executed = self._wait_trajectory(native)
                if self._cancelled():
                    return
                with self.lock:
                    self.waypoints += executed
        except Exception as error:
            if not self._cancelled():
                with self.lock:
                    result = (self.trajectory or {}).get('result') or {}
                    self.failure = dict(stage=self.state,
                        error_type=type(error).__name__ if type(error) in
                            (RuntimeError, ValueError, TypeError, KeyError, AttributeError) else 'other',
                        native_status=result.get('status') if result.get('status') in
                            {'rejected', 'aborted', 'completed'} else None,
                        native_code=result.get('code') if result.get('code') in NATIVE_FAILURE_CODES else None)
                    self.state = 'failed'
                # Native Stop is immediate even if the runner disconnects before
                # polling this failure. Its normal notification closes the lease.
                context = dict(zip(CONTEXT, self.context))
                try:
                    self._send(dict(schema_version=1, type='safety_abort', **context,
                        code='controller_executor_failed', message='Controller Dream execution failed',
                        step_id=max(0, self.operator.api_last_step), observed_at=time.time(), details=self.failure))
                except Exception:
                    pass
                # Local cleanup must still run if notification delivery fails.
                self.operator.api_handle_stop(dict(context, reason='controller_executor_failed'))
        finally:
            with self.lock:
                if self.state not in TERMINAL:
                    self.state = 'cancelled'
            if native:
                native.close()
            with self.lock:
                self.native = None

    def _dispatch(self, payload):
        with self.lock:
            self.trajectory = dict(payload=deepcopy(payload), accepted=False, progress=0,
                                   result=None, observation=None, adjustment=None, error=False)
            self.owned_receipts.append(tuple(payload[k] for k in CONTEXT) + (payload['trajectory_id'],))
        responses = self.operator.api_handle_joint_trajectory(payload)
        for response in responses or []:
            self.send(response)
        return responses

    def send(self, payload):
        """Consume only our native packet receipts, before their cloud transport."""
        with self.lock:
            row = self.trajectory
            same = row and all(payload.get(k) == row['payload'][k] for k in CONTEXT)
            kind = payload.get('type')
            if same and kind == 'observation':
                if payload.get('step_id') == row['payload']['waypoints'][-1]['step_id'] + 1:
                    if (not row['accepted'] or row['progress'] != len(row['payload']['waypoints'])
                            or payload.get('settled') is not True):
                        row['error'] = True
                    row['observation'] = deepcopy(payload)
            if (same and kind in {'trajectory_progress', 'trajectory_result'}
                    and payload.get('trajectory_id') == row['payload']['trajectory_id']):
                points = row['payload']['waypoints']
                if kind == 'trajectory_progress':
                    i = row['progress']
                    if not row['accepted'] or i >= len(points) or payload.get('step_id') != points[i]['step_id']:
                        row['error'] = True
                    else:
                        row['progress'] += 1
                elif payload.get('status') == 'accepted':
                    row['accepted'] = True
                    details = payload.get('details') or {}
                    if details.get('workspace_recovery') == 'adjusted':
                        if row['adjustment'] is not None and row['adjustment'] != details:
                            row['error'] = True
                        row['adjustment'] = deepcopy(details)
                else:
                    if payload.get('status') == 'completed' and (
                            not row['accepted'] or row['progress'] != len(points) or not row['observation']):
                        row['error'] = True
                    row['result'] = deepcopy(payload)
                return
            if kind in {'trajectory_progress', 'trajectory_result'} and (
                    tuple(payload.get(k) for k in CONTEXT) + (payload.get('trajectory_id'),)
                    in self.owned_receipts):
                return  # Late direct receipts never become unknown cloud packets.
        return self._send(payload)

    def _wait_trajectory(self, native):
        with self.lock:
            duration = len(self.trajectory['payload']['waypoints']) / 10
        deadline = time.monotonic() + duration + 60
        while not self._cancelled():
            with self.lock:
                row = deepcopy(self.trajectory)
            if row['error']:
                raise RuntimeError('Invalid native Dream receipt order')
            result = row['result']
            if result:
                points = row['payload']['waypoints']
                count, last = len(points), points[-1]['step_id']
                details = result.get('details') or {}
                if result.get('status') == 'completed':
                    obs = row['observation']
                    if (not row['accepted'] or row['progress'] != count or not obs
                            or obs.get('settled') is not True or result.get('step_id') != last):
                        raise RuntimeError('Incomplete native Dream execution evidence')
                    target = row['adjustment'] or points[-1]
                    if row['adjustment']:
                        if type(target.get('changed_waypoints')) is not int or not 1 <= target['changed_waypoints'] <= count:
                            raise RuntimeError('Invalid native workspace replacement')
                        native.trajectory_adjusted(target)
                    mismatch = False
                    for side in ('left', 'right'):
                        key = side + '_joints_deg'
                        for values in (obs.get(key), target.get(key)):
                            if (not isinstance(values, list) or len(values) != 6
                                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)):
                                raise RuntimeError('Missing finite native final joints')
                        mismatch |= any(abs(a-b) > math.degrees(.05) for a,b in zip(obs[key], target[key]))
                    if mismatch:
                        native.trajectory_failed('final_position_mismatch', 'Measured final target mismatch', count)
                    else:
                        native.trajectory_completed(obs, count)
                    return count
                code = result.get('code')
                held = (code in {'left_tip_outside_workspace', 'right_tip_outside_workspace'}
                    and details.get('workspace_recovery') == 'held' and details.get('hold') == 'measured_position'
                    and details.get('next_step_id') == last + 1
                    and type(details.get('executed_waypoints')) is int
                    and details['executed_waypoints'] == row['progress']
                    and ((result.get('status') == 'rejected' and not row['accepted'] and row['progress'] == 0)
                         or (result.get('status') == 'aborted' and row['accepted']
                             and result.get('step_id') == min(points[0]['step_id'] + row['progress'], last))))
                settling = (code == 'joint_settle_timeout' and result.get('status') == 'aborted'
                    and row['accepted'] and row['progress'] == count and result.get('step_id') == last)
                if details.get('recoverable') is True and (held or settling):
                    native.trajectory_failed(code, 'Native controller held the packet', row['progress'], feedback=details)
                    self.cancelled.wait(.25)
                    return row['progress']
                raise RuntimeError('Native controller rejected Dream packet')
            if time.monotonic() > deadline:
                raise RuntimeError('Native Dream completion timed out')
            self.cancelled.wait(.02)


def install(hardware, **settings):
    """Compose after the station's existing calibration and recovery wrappers."""
    class DreamOperator(hardware.base.OperatorSimulator):
        def attach_api_client(self, client):
            # Native main constructs the operator first, attaches its client,
            # then starts HTTP/transport threads. Bind at that lifecycle hook.
            if hasattr(self, 'dream_executor'):
                if self.api_client is not client:
                    raise ValueError('Dream operator API client cannot be replaced')
                return
            super().attach_api_client(client)
            self.dream_executor = DreamControllerExecutor(self, **settings)

        def api_prepare_session(self, payload):
            observation = super().api_prepare_session(payload)
            if observation is not None:
                self.dream_executor.prepare(payload)
            return observation

        def api_handle_execution(self, payload):
            if payload.get('executor') == 'dream_one':
                return self.dream_executor.request(payload)
            if self.dream_executor.context == tuple(getattr(self, 'api_' + k) for k in CONTEXT):
                raise ValueError('This lease belongs to Dream')
            handler = getattr(super(), 'api_handle_execution', None)
            if handler is None:
                raise ValueError('Unsupported executor')
            return handler(payload)

        def api_handle_stop(self, payload):
            executor = getattr(self, 'dream_executor', None)
            if executor and all(payload.get(k) == getattr(self, 'api_' + k) for k in ('session_id', 'lease_id')):
                executor.cancel()
            return super().api_handle_stop(payload)

        def api_connection_changed(self, connected, error=None):
            if not connected and hasattr(self, 'dream_executor'):
                self.dream_executor.cancel()
            return super().api_connection_changed(connected, error)

        def action(self, action, *args, **kwargs):
            if action == 'stop' and hasattr(self, 'dream_executor'):
                self.dream_executor.cancel()
            return super().action(action, *args, **kwargs)

        def status(self):
            status = super().status()
            if hasattr(self, 'dream_executor'):
                status['controller_executors'] = {'dream_one': self.dream_executor.status()}
            return status

        def stop(self):
            executor = getattr(self, 'dream_executor', None)
            if executor:
                executor.cancel()
            result = super().stop()
            if executor:
                executor.pool.close()
            return result

    hardware.PhysicalOperator = hardware.base.OperatorSimulator = DreamOperator
    return DreamOperator
