"""Dream-1 YAM chunks through the existing leased Session API controller."""
import base64
from collections import deque
import io
import json
import math
import os
from pathlib import Path
import selectors
import subprocess
import threading
import time

from .session import MAX_COMMANDS, MAX_WAYPOINTS_PER_PACKET
from .latency_spans import journal_span

MODELS = {'dream': ('dreamlabs/dream-1-beta', 'Dream-1 beta'),
          'dream_flash': ('dreamlabs/dream-1-beta-flash', 'Dream-1 beta Flash')}
CAMERAS = {'top': 'overhead', 'left': 'wrist_l', 'right': 'wrist_r'}
OBSERVATION_RECOVERY_S = 5.


class DreamWorkerUnavailable(RuntimeError):
    """The prepared process was discarded; its prediction must never be reused."""
    def __init__(self, message, *, reason='worker_failure'):
        super().__init__(message)
        self.reason = reason


class DreamObservationError(ValueError):
    """Only locally authored diagnostics may be exposed in the run log."""
    def __init__(self, message, *, field, retryable=False):
        super().__init__(message)
        self.field, self.retryable = field, retryable


def motion_limited_waypoints(points, observation, max_step_deg):
    """Retain every paired target; add 100 ms steps instead of clipping the path."""
    state_input(observation, '')
    previous = [*observation['left_joints_deg'], observation['left_gripper'],
                *observation['right_joints_deg'], observation['right_gripper']]
    first_step_id = points[0]['step_id']
    capacity = min(MAX_WAYPOINTS_PER_PACKET, MAX_COMMANDS - first_step_id)
    result = []
    for point in points:
        target = [*point['left_joints_deg'], point['left_gripper'],
                  *point['right_joints_deg'], point['right_gripper']]
        if not all(math.isfinite(value) for value in target):
            raise ValueError('Dream targets must convert to finite gateway angles')
        joint_delta = max(abs(target[i]-previous[i]) for i in (*range(6), *range(7, 13)))
        grip_delta = max(abs(target[i]-previous[i]) for i in (6, 13))
        steps = max(1, math.ceil(joint_delta / max_step_deg), math.ceil(grip_delta / .3))
        if len(result) + steps > capacity:
            raise ValueError('Motion-limited Dream path exceeds the session waypoint budget')
        for step in range(1, steps + 1):
            row = target if step == steps else [a+(b-a)*step/steps for a,b in zip(previous,target)]
            result.append(dict(step_id=first_step_id+len(result),
                left_joints_deg=row[:6], left_gripper=row[6],
                right_joints_deg=row[7:13], right_gripper=row[13]))
        previous = target
    return result


def state_input(observation, prompt):
    result = {'prompt': prompt}
    for side in ('left', 'right'):
        joints, grip = observation.get(side + '_joints_deg'), observation.get(side + '_gripper')
        field = side + '_joints_deg'
        if joints is None:
            raise DreamObservationError('Measured ' + field + ' is unavailable', field=field, retryable=True)
        if (not isinstance(joints, (list, tuple)) or len(joints) != 6
                or any(type(x) not in (float, int) or not math.isfinite(x) for x in joints)):
            raise DreamObservationError('Measured ' + field + ' must contain six finite numbers', field=field)
        field = side + '_gripper'
        if grip is None:
            raise DreamObservationError('Measured ' + field + ' is unavailable', field=field, retryable=True)
        if type(grip) not in (float, int) or not math.isfinite(grip) or not 0 <= grip <= 1:
            raise DreamObservationError('Measured ' + field + ' must be finite and within 0..1', field=field)
        result['state.' + side + '_arm'] = [math.radians(x) for x in joints]
        result['state.' + side + '_gripper'] = [grip]
    return result


def action_waypoints(action, first_step_id):
    """20 Hz endpoint sampling at 10 Hz preserves the predicted duration."""
    chunks = [action.get(key) for key in ('q_l_chunk', 'q_r_chunk')]
    if (any(not isinstance(rows, list) or not rows or len(rows) % 2 for rows in chunks)
            or len(chunks[0]) != len(chunks[1])):
        raise ValueError('Dream returned mismatched or incomplete joint chunks')
    count = len(chunks[0]) // 2
    if (type(first_step_id) is not int or first_step_id < 0 or count > MAX_WAYPOINTS_PER_PACKET
            or first_step_id + count > MAX_COMMANDS):
        raise ValueError('Dream chunk exceeds the session waypoint budget')
    for rows in chunks:
        if any(not isinstance(row, list) or len(row) != 7
               or any(type(x) not in (float, int) or not math.isfinite(x) for x in row)
               for row in rows):
            raise ValueError('Dream returned invalid joints or grippers')
    return [dict(step_id=first_step_id + n,
                 left_joints_deg=[math.degrees(x) for x in chunks[0][i][:6]],
                 right_joints_deg=[math.degrees(x) for x in chunks[1][i][:6]],
                 # Match Dream's robots.adapter._arm_command: smoothed grips
                 # can overshoot their normalized endpoints; physical commands cannot.
                 left_gripper=min(1., max(0., chunks[0][i][6])),
                 right_gripper=min(1., max(0., chunks[1][i][6])))
            for n, i in enumerate(range(1, len(chunks[0]), 2))]


class DreamWorker:
    def __init__(self, python, credentials, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        env = {k: v for k, v in os.environ.items() if not k.startswith('DREAM_')}
        env.update(DREAM_CREDENTIALS=str(Path(credentials).expanduser().resolve()),
                   DREAM_WORK_DIR=str(directory.resolve()), DREAM_LOG='off',
                   PYTHONUNBUFFERED='1')
        # Honor a trusted service-owned persistent cache across visitor workers.
        # Unconfigured local runs retain their private cache directory.
        env.setdefault('JAX_COMPILATION_CACHE_DIR', str((directory / 'jax').resolve()))
        self.process = subprocess.Popen([str(python), str(Path(__file__).with_name('dream_worker.py'))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1, env=env)
        self.lock = threading.Lock()
        self.close_lock = threading.Lock()
        self.closed = threading.Event()

    def call(self, command, *, cancelled=lambda: False, timeout=30, **payload):
        with self.lock:
            if self.closed.is_set() or cancelled():
                raise RuntimeError('Dream request cancelled')
            try:
                self.process.stdin.write(json.dumps(dict(command=command, **payload), allow_nan=False) + '\n')
                self.process.stdin.flush()
                deadline = time.monotonic() + timeout
                with selectors.DefaultSelector() as selector:
                    selector.register(self.process.stdout, selectors.EVENT_READ)
                    while not self.closed.is_set() and not cancelled():
                        if time.monotonic() >= deadline:
                            raise RuntimeError('Dream worker timed out')
                        if selector.select(.1):
                            line = self.process.stdout.readline(2_000_001)
                            if not line or len(line) > 2_000_000:
                                raise RuntimeError('Dream worker ended or returned an invalid response')
                            response = json.loads(line)
                            if not isinstance(response, dict) or type(response.get('ok')) is not bool:
                                raise RuntimeError('Dream worker returned an invalid response')
                            return response
                raise RuntimeError('Dream request cancelled')
            except (OSError, ValueError) as error:
                raise RuntimeError('Dream worker transport failed (' + type(error).__name__ + ')') from None

    def close(self):
        with self.close_lock:
            if self.closed.is_set():
                return
            self.closed.set()
            if self.process.poll() is None:
                self.process.terminate()  # Worker releases its Dream session on SIGTERM.
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            for stream in (self.process.stdin, self.process.stdout):
                try:
                    stream.close()
                except OSError:
                    pass  # A dead child may reject a buffered stdin flush.


class DreamAdapter:
    supports_runtime_steering = True

    def __init__(self, *, provider, model, credentials, python, directory,
                 camera_source, observation_source, robot_id, worker_factory=DreamWorker,
                 gateway_max_step_deg=None, worker_pool=None):
        if provider not in MODELS or model != MODELS[provider][0]:
            raise ValueError('Unknown Dream checkpoint')
        self.provider_name, self.model = provider, model
        self.credentials, self.python, self.directory = credentials, python, directory
        self.camera_source, self.observation_source, self.robot_id = camera_source, observation_source, robot_id
        self.worker_factory = worker_factory
        self.worker_pool = worker_pool
        self._worker_slot = False
        self._transport_lock = threading.RLock()
        self.gateway_max_step_deg = gateway_max_step_deg
        self.max_joint_step_deg = 20.
        self.effective_joint_step_deg = min(self.max_joint_step_deg, gateway_max_step_deg) \
            if gateway_max_step_deg is not None else self.max_joint_step_deg
        self.cancelled = lambda: False
        self.refresh_observation = None
        self.interaction_sink = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._changed = threading.Condition()
        self._history = deque(maxlen=9)
        self._worker = None
        self._preparation = None
        self._collector = None
        self._failure = None
        self._prompt = None
        self._task_prompt = None
        from .steering import SteeringInbox
        self.steering = SteeringInbox(self._interaction)
        self._commanded = None
        self._pending_commanded = None
        self.last_probe = None
        self._capture_sequence = 0
        self._history_generation = 0
        self._worker_recoveries = 0
        self._workspace_reset_pending = False
        self._workspace_feedback = None

    def _interaction(self, kind, message, **details):
        if self.interaction_sink:
            self.interaction_sink(kind, message, **details)

    def public_config(self):
        return dict(provider=self.provider_name, model=self.model, cadence_hz=10,
                    model_action_hz=20, observation_fps=5, observation_window=9,
                    api_key_configured=True, sdk_background_recording=False,
                    execution_mode='sequential_chunks', action_space='eef', ik_solve='traj',
                    max_joint_step_deg=self.max_joint_step_deg,
                    effective_joint_step_deg=self.effective_joint_step_deg,
                    gateway_profile_step_deg=self.gateway_max_step_deg)

    def _cancelled(self):
        return self._stop.is_set() or self.cancelled()

    def start_preparation(self, cancelled):
        self.cancelled = cancelled
        # A hosted fleet may bound heavy SDK/IK processes. Do not reserve one
        # for a queued visitor. The controller activates it after lease grant,
        # allowing SDK preparation to overlap Home without occupying a queued slot.
        if self.worker_pool is None:
            self._start_preparation()

    def prepare_after_lease(self, cancelled):
        self.cancelled = cancelled
        self._start_preparation()

    def _worker_timings(self, reply):
        allowed = {'sdk_import', 'sdk_client_init', 'sdk_configure',
                   'sdk_observation_update', 'sdk_get_action', 'sdk_reset'}
        for row in reply.get('stage_timings') or []:
            if not isinstance(row, dict) or row.get('stage') not in allowed:
                continue
            values = [row.get('started_at'), row.get('duration_s')]
            if (row.get('status') not in {'ok', 'error'} or
                    any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in values)):
                continue
            if self.interaction_sink:
                try:
                    self.interaction_sink('policy_timing', 'Dream SDK stage: '+row['stage'],
                        stage=row['stage'], state='completed' if row['status']=='ok' else 'error',
                        started_at=values[0], duration_s=values[1], clock_source='sdk_worker')
                except Exception:
                    pass

    def _start_preparation(self):
        if self._preparation is not None:
            return

        def prepare():
            try:
                if self.worker_pool is not None:
                    with journal_span(self.interaction_sink, 'worker_acquisition'):
                        while not self._cancelled():
                            if self.worker_pool.acquire(timeout=.1):
                                with self._transport_lock:
                                    self._worker_slot = True
                                    if self._cancelled():
                                        self._close_worker()
                                        return
                                break
                        else:
                            return
                with self._transport_lock:
                    if self._cancelled():
                        self._close_worker()
                        return
                    with journal_span(self.interaction_sink, 'worker_start'):
                        worker = self.worker_factory(self.python, self.credentials, self.directory)
                    self._worker = worker
                with journal_span(self.interaction_sink, 'worker_configure'):
                    reply = worker.call('configure', checkpoint=self.model, cancelled=self._cancelled, timeout=180)
                self._worker_timings(reply)
                if not reply['ok']:
                    self._failure = 'Dream SDK setup failed (' + reply.get('error_type', 'unknown') + ')'
                    return
                self._ready.set()
            except Exception as error:
                self._failure = 'Dream SDK setup failed (' + type(error).__name__ + ')'
            finally:
                if self._cancelled() or self._failure:
                    self._close_worker()

        def watch():
            while not self._stop.wait(.1):
                if self.cancelled():
                    self.close_transport()
                    return

        self._preparation = threading.Thread(target=prepare, daemon=True, name='dream-sdk-setup')
        self._preparation.start()
        threading.Thread(target=watch, daemon=True, name='dream-session-cleanup').start()

    def wait_ready(self, cancelled):
        with journal_span(self.interaction_sink, 'adapter_wait_ready'):
            if self._preparation is None:
                self._start_preparation()
            waited = not self._ready.is_set()
            while not self._ready.wait(.1):
                if self._failure:
                    raise RuntimeError(self._failure)
                if cancelled() or self._cancelled():
                    raise RuntimeError('Dream preparation cancelled')
            if cancelled() or self._cancelled():
                raise RuntimeError('Dream preparation cancelled')
            return waited

    def _read_observation(self, prompt):
        try:
            raw = self.observation_source()
        except Exception as error:
            raise DreamObservationError('Station observation read failed (' + type(error).__name__ + ')',
                field='observation_source', retryable=isinstance(error, (OSError, TimeoutError, ConnectionError))) from None
        if not isinstance(raw, dict):
            raise DreamObservationError('Station observation must be an object', field='observation')
        observation = raw.get('observation') or raw.get('payload') or raw
        if not isinstance(observation, dict):
            raise DreamObservationError('Station observation must be an object', field='observation')
        if observation.get('jetson_id') != self.robot_id:
            raise DreamObservationError('Dream camera/state robot identity changed', field='jetson_id')
        observed_at = observation.get('observed_at')
        if observed_at is None:
            raise DreamObservationError('Measured observed_at is unavailable', field='observed_at', retryable=True)
        if type(observed_at) not in (float, int) or not math.isfinite(observed_at):
            raise DreamObservationError('Measured observed_at must be a finite timestamp', field='observed_at')
        age = time.time() - observed_at
        if age < -2:
            raise DreamObservationError('Measured observed_at is ahead of the local clock', field='observed_at')
        if age > 5:
            raise DreamObservationError('Dream requires fresh measured YAM state (observed_at expired)',
                                        field='observed_at', retryable=True)
        return observation, state_input(observation, prompt)

    def _capture_tick(self):
        capture_started_at, capture_started = time.time(), time.perf_counter()
        self._capture_sequence += 1
        capture_id = self._capture_sequence
        # Boundary events only for the first capture, not every 5 Hz sample.
        # The selected sample's numeric timings are retained per prediction.
        sink = self.interaction_sink if capture_id == 1 else None
        with self._changed:
            prompt = self._prompt
        state_began = time.perf_counter()
        with journal_span(sink, 'observation_read', capture_id=capture_id):
            observation, state = self._read_observation(prompt)
        state_read_s = time.perf_counter()-state_began
        observed_at = observation['observed_at']
        camera_began = time.monotonic()
        last_failure = {}
        def camera_event(kind, message, details):
            if kind == 'camera_failure':
                last_failure.update(details)
            if self.interaction_sink:
                self.interaction_sink(kind, message, **details)
        try:
            with journal_span(sink, 'camera_acquisition', capture_id=capture_id):
                frames = self.camera_source.capture_for_policy(observation, cancelled=self._cancelled,
                                                               on_event=camera_event)
        except Exception as error:
            role = last_failure.get('camera')
            detail = last_failure.get('cause')
            message = 'Dream ' + (role + ' ' if role in CAMERAS else '') + 'camera capture failed'
            message += ' (' + (str(detail) if detail else type(error).__name__) + ')'
            raise DreamObservationError(message, field='camera_' + role if role in CAMERAS else 'camera_capture') from None
        camera_capture_s = time.monotonic()-camera_began
        if len(frames) != 3 or {frame.name for frame in frames} != set(CAMERAS):
            raise DreamObservationError('Dream requires overhead and both wrist cameras', field='camera_roles')
        if time.time() - observed_at > 5:
            # Camera retries return a NEW complete set. Pair it with newly read
            # measured feedback instead of discarding those images with an old pose.
            state_began = time.perf_counter()
            with journal_span(sink, 'observation_refresh', capture_id=capture_id):
                observation, state = self._read_observation(prompt)
            state_read_s += time.perf_counter()-state_began
            observed_at = observation['observed_at']
            if self.interaction_sink:
                self.interaction_sink('observation_refreshed',
                    'Fresh measured feedback paired after camera recovery',
                    camera_capture_s=time.monotonic() - camera_began)
        now = time.time()
        for frame in frames:
            captured = frame.source_captured_at if frame.source_captured_at is not None else frame.received_at
            if now - captured > 5:
                raise DreamObservationError('Dream ' + frame.name + ' camera frame expired during capture',
                                            field='camera_' + frame.name, retryable=True)
            if now - captured < -2:
                raise DreamObservationError('Dream ' + frame.name + ' camera timestamp is ahead of the local clock',
                                            field='camera_' + frame.name)
        encoding_began = time.perf_counter()
        from PIL import Image
        encoded = {}
        for frame in frames:
            output = io.BytesIO()
            try:
                with Image.open(io.BytesIO(frame.jpeg)) as image:
                    image.convert('RGB').resize((320, 176), Image.Resampling.LANCZOS).save(output, format='JPEG', quality=85)
            except Exception as error:
                raise DreamObservationError('Dream ' + frame.name + ' camera image decoding failed ('
                    + type(error).__name__ + ')', field='camera_' + frame.name) from None
            encoded['video.' + CAMERAS[frame.name]] = base64.b64encode(output.getvalue()).decode()
        return dict(timestamp=time.monotonic(), observed_at=observed_at, frames=encoded, observation=state,
                    capture_timing=dict(capture_id=capture_id, started_at=capture_started_at,
                        duration_s=time.perf_counter()-capture_started, state_read_s=state_read_s,
                        camera_capture_s=camera_capture_s, encoding_s=time.perf_counter()-encoding_began))

    def _collect(self):
        unavailable_since = None
        while not self._cancelled():
            started = time.monotonic()
            try:
                with self._changed:
                    generation = self._history_generation
                tick = self._capture_tick()
                with self._changed:
                    if (generation == self._history_generation and
                            tick['observation']['prompt'] == self._prompt and not self._cancelled()):
                        self._history.append(tick)
                        self._changed.notify_all()
                if unavailable_since is not None and self.interaction_sink:
                    self.interaction_sink('observation_recovered', 'Dream observation feed recovered')
                unavailable_since = None
            except DreamObservationError as error:
                if self._cancelled():
                    return
                first_failure = unavailable_since is None
                if first_failure:
                    unavailable_since = time.monotonic()
                retrying = error.retryable and time.monotonic() - unavailable_since < OBSERVATION_RECOVERY_S
                with self._changed:
                    # Never use a prior sample while current feedback is unavailable.
                    self._history.clear()
                    if not retrying:
                        self._failure = 'Dream observation capture failed: ' + str(error)
                        if error.retryable:
                            self._failure += ' (recovery timed out)'
                    self._changed.notify_all()
                if self.interaction_sink and (first_failure or not retrying):
                    self.interaction_sink('observation_retry' if retrying else 'observation_failure',
                        'Dream observation unavailable: ' + str(error),
                        field=error.field, retrying=retrying, recovery_window_s=OBSERVATION_RECOVERY_S)
                if not retrying:
                    return
            except Exception as error:
                if not self._cancelled():
                    with self._changed:
                        self._history.clear()
                        self._failure = 'Dream observation capture failed (' + type(error).__name__ + ')'
                        self._changed.notify_all()
                return
            self._stop.wait(max(0, .2 - (time.monotonic() - started)))

    def _wait_for_ticks(self, not_before=None, observed_after=None):
        with self._changed:
            while True:
                if self._failure:
                    raise RuntimeError(self._failure)
                if self._cancelled():
                    raise RuntimeError('Dream cancelled')
                ticks = [tick for tick in self._history
                         if observed_after is None or tick['observed_at'] >= observed_after]
                if (ticks and time.time() - ticks[-1]['observed_at'] <= 5
                        and (not_before is None or ticks[-1]['timestamp'] >= not_before)):
                    return ticks
                self._changed.wait(.1)

    def _recover_worker(self, first_step_id, reason):
        recover = getattr(self._worker, 'recover', None)
        if self._worker_recoveries or not callable(recover) or self._cancelled():
            raise DreamWorkerUnavailable('Dream worker recovery is unavailable')
        self._worker_recoveries += 1
        if self.interaction_sink:
            self.interaction_sink('worker_recovery', 'Dream worker is recovering; motion is paused',
                                  state='started', attempt=1, first_step_id=first_step_id, reason=reason)
            self.interaction_sink('model_progress', 'Dream worker is recovering; motion is paused',
                                  progress_type='status')
        try:
            recover(checkpoint=self.model, cancelled=self._cancelled)
            if self._cancelled():
                raise RuntimeError('Dream worker recovery cancelled')
            # Revalidate the SAME lease, completed step and idle executor before
            # requesting another prediction. No failed request/action is replayed.
            if callable(self.refresh_observation):
                self.refresh_observation()
            fresh, _ = self._read_observation(self._prompt)
            with self._changed:
                self._history_generation += 1
                self._history.clear()
                self._commanded = self._pending_commanded = None
                # Compare feedback timestamps only with that same source's
                # watermark, never order a robot clock against the server clock.
                observed_after = fresh['observed_at']
            if self.interaction_sink:
                self.interaction_sink('worker_recovery', 'Dream worker recovered; collecting fresh inputs',
                                      state='completed', attempt=1, first_step_id=first_step_id)
                self.interaction_sink('model_progress', 'Dream worker recovered; collecting fresh inputs',
                                      progress_type='status')
            return observed_after
        except Exception:
            if self.interaction_sink:
                self.interaction_sink('worker_recovery', 'Dream worker recovery ended',
                                      state='failed', attempt=1, first_step_id=first_step_id)
            raise

    def build_trajectory(self, prompt, observation, first_step_id):
        if self._cancelled():
            raise RuntimeError('Dream cancelled')
        if self._preparation is None:
            self.start_preparation(self.cancelled)
        self.wait_ready(self._cancelled)
        with self._changed:
            changed = self._task_prompt is not None and self._task_prompt != prompt
            if self._task_prompt != prompt:
                self._history.clear()
                self._task_prompt = prompt
                self._prompt = prompt
        if changed:
            self._worker.call('reset', cancelled=self._cancelled)
            self._commanded = self._pending_commanded = None
            self._workspace_reset_pending = False
            self._workspace_feedback = None
        if self._workspace_reset_pending:
            # SDK 1.0.0 reset_episode clears its action smoother and frame window
            # (docs/refs/dreamlabs/client.md). Run between predictions, never in
            # the controller event callback or concurrently with get_action.
            reset = self._worker.call('reset', cancelled=self._cancelled)
            if reset.get('ok') is not True:
                raise RuntimeError('Dream could not reset workspace-recovery action history')
            with self._changed:
                self._history_generation += 1
                self._history.clear()
                self._commanded = self._pending_commanded = None
                self._workspace_reset_pending = False
            if callable(self.refresh_observation):
                self.refresh_observation()
        if self._collector is None:
            self._collector = threading.Thread(target=self._collect, daemon=True, name='dream-camera-history')
            self._collector.start()
        began = time.monotonic()
        deadline = began + 600
        session_recoveries = 0
        observed_after = None
        while True:
            # Require a new camera tick for this decision; never reuse an old snapshot.
            with journal_span(self.interaction_sink, 'observation_wait', first_step_id=first_step_id):
                ticks = self._wait_for_ticks(began, observed_after)
            if self._cancelled():
                raise RuntimeError('Dream cancelled')
            update = self.steering.include_prompt(prompt)
            with self._changed:
                if update is not None:
                    self._prompt = update
                active_prompt = self._prompt
                if self._workspace_feedback:
                    active_prompt += '\nController workspace feedback: ' + self._workspace_feedback
            # SDK 1.0.0 set_observation replaces the prompt without resetting
            # its session or frame window (docs/refs/dreamlabs/client.md).
            # Copy ticks: the collector and previous request receipts retain
            # their actual capture-time values while this request gets guidance.
            ticks = [dict(tick, observation=dict(tick['observation'], prompt=active_prompt))
                     for tick in ticks]
            capture_timing = ticks[-1].get('capture_timing')
            if self.interaction_sink and capture_timing:
                try:
                    self.interaction_sink('policy_timing', 'Dream input capture timing',
                        stage='selected_observation_capture', state='completed', **capture_timing)
                except Exception:
                    pass
            try:
                with journal_span(self.interaction_sink, 'worker_predict', first_step_id=first_step_id):
                    reply = self._worker.call('predict', ticks=ticks, commanded=self._commanded,
                                              first_step_id=first_step_id,
                                              cancelled=self._cancelled)
            except DreamWorkerUnavailable as error:
                observed_after = self._recover_worker(first_step_id, error.reason)
                began = time.monotonic()
                continue
            self._worker_timings(reply)
            if self._cancelled():
                raise RuntimeError('Dream prediction cancelled; result discarded')
            if reply['ok']:
                # A collection failure during inference must not dispatch a late reply.
                latest = self._wait_for_ticks()[-1]
                if self.steering.pending():
                    # Nothing from this prediction was dispatched. Keep the
                    # completed command anchor, or measured pose on the first
                    # decision, so an unused prediction cannot anchor smoothing.
                    if self._commanded is None:
                        measured = latest['observation']
                        self._commanded = {
                            key: list(measured['state.' + side + '_arm'])
                                 + list(measured['state.' + side + '_gripper'])
                            for key, side in (('q_l_chunk', 'left'), ('q_r_chunk', 'right'))}
                    self._interaction('model_progress',
                        'Dream prediction discarded; requesting a fresh prediction with newer steering',
                        progress_type='status', first_step_id=first_step_id)
                    if callable(self.refresh_observation):
                        self.refresh_observation()
                    began = time.monotonic()
                    continue
                result = reply['result']
                nominal = action_waypoints(result['action'], first_step_id)
                measured = latest['observation']
                baseline = {side+'_joints_deg': [math.degrees(value) for value in measured['state.'+side+'_arm']]
                            for side in ('left', 'right')}
                baseline.update({side+'_gripper': measured['state.'+side+'_gripper'][0] for side in ('left','right')})
                points = motion_limited_waypoints(nominal, baseline, self.effective_joint_step_deg)
                self._pending_commanded = {
                    key: [math.radians(value) for value in points[-1][side + '_joints_deg']]
                         + [points[-1][side + '_gripper']]
                    for key, side in (('q_l_chunk', 'left'), ('q_r_chunk', 'right'))}
                grippers = [row[6] for key in ('q_l_chunk', 'q_r_chunk') for row in result['action'][key]]
                self.last_probe = dict(timing=result.get('timing'), frame_window=len(ticks),
                    model_rows=len(result['action']['q_l_chunk']), waypoint_count=len(points),
                    nominal_waypoint_count=len(nominal), inserted_waypoints=len(points)-len(nominal),
                    motion_cap_deg_per_100ms=self.max_joint_step_deg,
                    effective_motion_cap_deg_per_100ms=self.effective_joint_step_deg,
                    raw_gripper_range=[min(grippers), max(grippers)],
                    gripper_values_clipped=sum(not 0 <= grip <= 1 for grip in grippers))
                if self.interaction_sink:
                    self.interaction_sink('model_timing', 'Dream joint chunk received', **self.last_probe)
                return points
            diagnostics = {key: reply.get(key) for key in ('error_type', 'code', 'reason', 'retryable',
                           'phase', 'protocol_category', 'http_status', 'cause_type', 'cause_family',
                           'cause_errno', 'cause_reason', 'transport_stage', 'protocol_trace',
                           'http_connection_policy', 'timing')}
            if (reply.get('error_type') == 'DreamSessionExpired' and reply.get('code') == 'DA-0001'
                    and session_recoveries == 0):
                # The SDK adopted the replacement and discarded its action.
                # Request once from NEW input; keep robot lease, Home and step IDs.
                session_recoveries += 1
                if self.interaction_sink:
                    self.interaction_sink('model_progress',
                        'Dream model session was replaced; requesting a fresh prediction',
                        progress_type='status', recovery_attempt=session_recoveries, **diagnostics)
                began = time.monotonic()
                continue
            if reply.get('reason') != 'pool_warming' or time.monotonic() >= deadline:
                if self.interaction_sink:
                    self.interaction_sink('model_failure', 'Dream prediction request failed', **diagnostics)
                detail = '; '.join(str(diagnostics[key]) for key in
                                   ('code', 'error_type', 'reason', 'protocol_category') if diagnostics[key])
                if diagnostics['http_status'] is not None:
                    detail += '; HTTP ' + str(diagnostics['http_status'])
                for key in ('cause_type', 'transport_stage'):
                    if diagnostics[key]:
                        detail += '; ' + diagnostics[key]
                raise RuntimeError('Dream request failed (' + (detail or 'unknown error') + ')')
            delay = reply.get('retry_after_s')
            delay = max(1, float(delay)) if type(delay) in (int, float) and math.isfinite(delay) else 5
            if self.interaction_sink:
                self.interaction_sink('model_progress', 'Dream model is warming', progress_type='status')
            until = time.monotonic() + delay
            while time.monotonic() < until:
                if self._cancelled():
                    raise RuntimeError('Dream warming cancelled')
                self._stop.wait(min(.1, until - time.monotonic()))
            began = time.monotonic()

    def trajectory_completed(self, observation, waypoint_count):
        # The runner calls this only after gateway completion. Measured lag can
        # resemble an earlier noisy row; the SDK needs the actual final target.
        self._commanded, self._pending_commanded = self._pending_commanded, None

    def trajectory_adjusted(self, details):
        # Acceptance is not completion: keep the corrected anchor pending until
        # measured completion, and discard the SDK's nominal blending next time.
        self._pending_commanded = {
            key: [math.radians(value) for value in details[side + '_joints_deg']]
                 + [details[side + '_gripper']]
            for key, side in (('q_l_chunk', 'left'), ('q_r_chunk', 'right'))}
        self._workspace_reset_pending = True
        self._workspace_feedback = ('Reached ' + ', '.join(details.get('boundary_limits') or details.get('boundaries') or ['workspace boundary'])
            + '; controller executed a validated replacement inside the existing boundary. '
              'Use fresh measured state and choose an in-bounds target.'
            + (' Requested orientation was relaxed.' if details.get('orientation_relaxed') else ''))

    def trajectory_failed(self, code, message, waypoint_count, *, feedback=None):
        self._commanded = self._pending_commanded = None
        self._workspace_reset_pending = True
        boundaries = ', '.join((feedback or {}).get('boundary_limits') or (feedback or {}).get('boundaries') or [code])
        self._workspace_feedback = (f'{boundaries}: {message}. Packet stopped after {waypoint_count} waypoints; '
            'remaining actions were discarded. Use fresh measured state and revise the target; do not replay the packet.')

    def close_transport(self):
        self._stop.set()
        with self._changed:
            self._changed.notify_all()
        self._close_worker()

    def _close_worker(self):
        with self._transport_lock:
            if self._worker:
                self._worker.close()
            if self._worker_slot:
                self._worker_slot = False
                self.worker_pool.release()
