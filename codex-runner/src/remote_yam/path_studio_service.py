"""Path Studio service. Robot session capabilities never leave this process."""
import threading
import time
import re
import json
from pathlib import Path
from urllib import request

from .controller import RunnerController
from .path_studio_policy import PathStudioPolicy, STATIONS, validate_sketch
from .session import HttpSessionAPI

API_ORIGIN = 'https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com'
ACTIVE = {'preparing', 'queued', 'running'}
OBS_FIELDS = ('jetson_id', 'source', 'mode', 'observed_at', 'left_joints_deg',
              'right_joints_deg', 'left_gripper', 'right_gripper', 'homed', 'settled', 'safety')
IDENTITY_PATH = Path(__file__).resolve().parents[3]/'.local/path-studio-identity.json'


def validate_identity(value):
    if not isinstance(value, dict):
        raise ValueError('Enter your queue name and email')
    if not all(isinstance(value.get(k),str) for k in ('runner_name','email')):
        raise ValueError('Enter your queue name and email')
    name, email = value['runner_name'].strip(), value['email'].strip()
    if not name or len(name)>32 or any(ord(c)<32 or ord(c)==127 for c in name):
        raise ValueError('Queue name must contain 1–32 visible characters')
    if len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
        raise ValueError('Enter a valid queue email address')
    return dict(runner_name=name,email=email)


class IdentifiedSessionAPI:
    def __init__(self, api, identity):
        self.api, self.identity = api, dict(identity)

    def __getattr__(self, name):
        return getattr(self.api,name)

    def create_session(self, prompt, run_duration_s=300, **kwargs):
        return self.api.create_session(prompt,run_duration_s,
            **{**kwargs,**self.identity,'email_run_video':False})


class StudioSessionAPI(HttpSessionAPI):
    """Retain failed stop acknowledgements even if the shared worker terminates."""
    stop_unconfirmed = False

    def stop_session(self, session_id, *, reason='user_requested'):
        self.stop_session_id = session_id
        self.stop_unconfirmed = True
        result = super().stop_session(session_id, reason=reason)
        if result.get('status') not in ('stopped', 'resetting', 'timed_out', 'safety_aborted', 'disconnected'):
            raise RuntimeError('Stop was not acknowledged as terminal')
        self.stop_unconfirmed = False
        return result


class PathStudioService:
    def __init__(self, api_factory=None, poll_s=.5, identity_path=None):
        self.api_factory = api_factory or (lambda robot_id: StudioSessionAPI(
            API_ORIGIN, timeout_s=5, supports_trajectories=True, robot_id=robot_id))
        self.poll_s = poll_s
        self.lock = threading.RLock()
        self.closed = threading.Event()
        self.monitors = {}
        self.controller = None
        self.policy = None
        self.run_station = None
        self.stop_error = None
        self.identity_path = Path(identity_path) if identity_path else IDENTITY_PATH
        try:
            self.identity = validate_identity(json.loads(self.identity_path.read_text()))
        except (OSError,ValueError,TypeError):
            self.identity = dict(runner_name='Andrew', email='')

    def _monitor(self, station):
        with self.lock:
            if station not in STATIONS:
                raise ValueError('Unknown station')
            if station not in self.monitors:
                state = dict(observation=None, calibration=None, queue=None, received_at=None, error=None)
                self.monitors[station] = state
                threading.Thread(target=self._poll, args=(station, state), daemon=True).start()
            return self.monitors[station]

    def _poll(self, station, state):
        api = self.api_factory(STATIONS[station])
        calibration_at = 0
        queue_at = 0
        queue = {}
        while not self.closed.is_set():
            try:
                raw = api.get_robot_observation(STATIONS[station])
                obs = raw.get('observation') or raw.get('payload') or raw
                if obs.get('jetson_id') != STATIONS[station]:
                    raise ValueError('API returned another station')
                if time.monotonic()-queue_at > 2 or not queue:
                    queue = api.get_queue_snapshot()
                    queue_at = time.monotonic()
                calibration = state['calibration']
                if time.monotonic()-calibration_at > 60 or calibration is None:
                    report = api._request('GET', f'/v1/robots/{STATIONS[station]}/calibration')
                    from .controller_workspace import workspace_for_robot
                    workspace_for_robot(STATIONS[station]).validate_report(report)
                    offsets = (report.get('model_joint_calibration') or {}).get('offsets_rad')
                    calibration = dict(spacing_m=report.get('base_geometry', {}).get('spacing_m'),
                        joint_offsets_rad=offsets or dict(left=[0.]*6, right=[0.]*6))
                    calibration_at = time.monotonic()
                with self.lock:
                    state.update(observation={k: obs.get(k) for k in OBS_FIELDS},
                        calibration=calibration,
                        queue=dict(waiting=len(queue.get('entries', [])), stations=queue.get('stations', [])),
                        received_at=time.time(), error=None)
                    controller = self.controller if self.run_station == station else None
                if controller:
                    controller.update_monitor_observation(raw)
                    controller.update_queue_snapshot(queue)
            except Exception as exc:
                with self.lock:
                    state['error'] = f'API monitoring unavailable ({type(exc).__name__})'
            self.closed.wait(self.poll_s)

    def _run_status(self):
        if self.controller is None:
            return None
        raw = self.controller.status()
        keys = ('status', 'queue_position', 'session_id', 'next_step_id', 'packets_submitted',
                'run_elapsed_s', 'error', 'execution_blocked_reason', 'feedback_warning', 'trajectory', 'run_metrics')
        result = {k: raw.get(k) for k in keys}
        result.update(station=self.run_station, progress=self.policy.public_config()['path_progress'],
                      stop_error=self.stop_error)
        step = (raw.get('trajectory') or {}).get('last_progress_step_id')
        result['drawing'] = dict(step_id=step, arms=self.policy.step_phases.get(step, {}),
                               paths_m={a:path.tolist() for a,path in self.policy.active.items()})
        if getattr(self.controller._session_api, 'stop_unconfirmed', False):
            result['stop_error'] = 'Stop acknowledgement unavailable. Retry Stop; check the station.'
        # Explicit allowlist above excludes session capabilities and interaction logs.
        caps = getattr(self.controller._session_api, '_session_capabilities', {})
        for key in ('error', 'execution_blocked_reason', 'feedback_warning'):
            if isinstance(result[key], str):
                for capability in caps.values():
                    if isinstance(capability, str) and capability:
                        result[key] = result[key].replace(capability, '[redacted]')
        return result

    def status(self, station):
        state = self._monitor(station)
        with self.lock:
            return dict(station=station, robot_id=STATIONS[station], **state, run=self._run_status())

    def run(self, data):
        sketch = validate_sketch(data)
        identity = validate_identity(data.get('identity',self.identity))
        with self.lock:
            if self.controller and (self.stop_error or getattr(self.controller._session_api, 'stop_unconfirmed', False)
                                    or self.controller.status()['status'] in ACTIVE
                                    or (self.controller._worker and self.controller._worker.is_alive())):
                raise ValueError('A run is already active. Stop it before starting another.')
            self.policy = PathStudioPolicy(sketch)
            self.identity = identity
            if 'identity' in data:
                self.identity_path.parent.mkdir(parents=True,exist_ok=True)
                self.identity_path.write_text(json.dumps(identity)+'\n')
            api = IdentifiedSessionAPI(self.api_factory(STATIONS[sketch['station']]),identity)
            self.controller = RunnerController(api, robot_id=STATIONS[sketch['station']],
                                              hardware_control_enabled=True, share_conversation=False,
                                              recording_root=self.identity_path.parent/'path-studio-runs')
            self.run_station = sketch['station']
            self.stop_error = None
            self.controller.join_and_run(self.policy, 'Path Studio: follow the user-drawn 3D path', run_duration_s=600)
        return self.status(sketch['station'])

    def simulate(self, data):
        # This path can read calibration only; it never creates a session or
        # invokes RunnerController, even when a physical station is disabled.
        from .path_studio_simulation import simulate_sketch
        sketch = validate_sketch(data)
        api = self.api_factory(STATIONS[sketch['station']])
        report = api._request('GET', f'/v1/robots/{STATIONS[sketch["station"]]}/calibration')
        return simulate_sketch(sketch, report)

    def stop(self):
        with self.lock:
            controller = self.controller
        if controller:
            try:
                if getattr(controller._session_api, 'stop_unconfirmed', False):
                    controller._session_api.stop_session(controller._session_api.stop_session_id, reason='path_studio_retry_stop')
                else:
                    controller.stop('path_studio_user_stop')
                self.stop_error = None
            except Exception:
                self.stop_error = 'Stop acknowledgement unavailable. Retry Stop; check the station.'
                raise RuntimeError(self.stop_error)
        return dict(run=self._run_status())

    def camera(self, station, role):
        if station not in STATIONS or role not in ('left', 'top', 'right', 'observer'):
            raise ValueError('Unknown camera')
        # A fixed origin/route prevents this endpoint from being an arbitrary proxy.
        url = f'{API_ORIGIN}/v1/robots/{STATIONS[station]}/cameras/{role}.jpg'
        with request.urlopen(url, timeout=5) as response:
            if response.headers.get_content_type() != 'image/jpeg':
                raise ValueError('Camera did not return a JPEG')
            body = response.read(8*1024*1024+1)
            if len(body) > 8*1024*1024:
                raise ValueError('Camera frame is too large')
            return body

    def video(self, path, query):
        # Same public viewer source used by the local playground. Read-only,
        # fixed streams and bounded filenames; no cookies or control authority.
        if not re.fullmatch(r'(robo-house|synchronized-hd)/[A-Za-z0-9_-]+\.(m3u8|mp4|m4s|ts)', path) or len(query) > 2048:
            raise ValueError('Unknown observer stream route')
        url = 'https://playground.blupe.io/'+path+('?' + query if query else '')
        req = request.Request(url, headers={'Origin':'https://playground.blupe.io'})
        with request.urlopen(req, timeout=12) as response:
            body = response.read(8_000_001)
            if len(body) > 8_000_000:
                raise ValueError('Video response is too large')
            return body, response.headers.get_content_type()

    def close(self):
        self.closed.set()
        self.stop()
