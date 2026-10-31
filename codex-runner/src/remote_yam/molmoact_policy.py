"""YAM1-only MolmoAct2 comparison. Queue/controller remains sole robot writer."""
import base64
import json
import http.client
import math
import re
import threading
import time
from urllib.parse import urlsplit
from .molmoact_protocol import (MODEL, REVISION, CAMERAS, GRIPPER_UNITS,
                               identity, validate_actions, finite_vector, valid_grippers)
from .session import MAX_COMMANDS, MAX_WAYPOINTS_PER_PACKET

VARIANT = 'cag-inspired-molmoact2-v1'
# At10Hz,0.03rad/step is0.3rad/s, below the configured YAM limits.
GATEWAY_JOINT_STEP_RAD = .03


def comparison_options(mode, strength):
    if mode not in ('baseline', 'guided'):
        raise ValueError('Choose MolmoAct2 baseline or guided')
    if isinstance(strength, bool) or not isinstance(strength, (int,float)) or not math.isfinite(strength) or not 0 <= strength <= .30:
        raise ValueError('Guidance strength must be between 0 and 0.30')
    return mode, float(strength) if mode == 'guided' else 0.0


class MolmoActAdapter:
    model = MODEL

    def __init__(self, api_key, *, camera_source, endpoint, robot_id='yam-1', mode='baseline', strength=0.15):
        url = urlsplit(endpoint)
        if (url.scheme != 'https' or not re.fullmatch(r'[a-z0-9]+\.api\.runpod\.ai', url.netloc)
                or url.path not in ('','/') or url.query or url.fragment):
            raise ValueError('Configure a RunPod HTTPS endpoint')
        if robot_id != 'yam-1':
            raise ValueError('This checkpoint is calibrated only for YAM1')
        if not api_key.strip():
            raise ValueError('Backend RunPod credential is missing')
        self._api_key, self._endpoint = api_key.strip(), endpoint.rstrip('/')
        self._camera_source = camera_source
        self.mode, self.strength = comparison_options(mode, strength)
        self.provider_name = 'molmoact_' + self.mode
        self.run_context = None
        self.cancelled = lambda: False
        self.interaction_sink = lambda *args, **kwargs: None
        self._ready, self._thread = threading.Event(), None
        self._warm_state, self._failure = 'idle', None
        self._warm_started_at = None
        self._warm_started_epoch = self._warm_ready_epoch = None
        self._launch_started_epoch = None
        self._capacity = dict(available=None, checked_at=None, workers=[])
        self._startup_home = None
        self._startup_queue = {}
        self._connection = None
        self._http_lock = threading.Lock()
        self._prefetch = None

    def public_config(self):
        return dict(provider=self.provider_name, model=MODEL, revision=REVISION,
            variant=VARIANT, mode=self.mode, guidance_strength=self.strength, seed=0,
            num_steps=10, dtype='bfloat16', enable_cuda_graph=False, robot_id='yam-1',
            trajectory_pacing=dict(cadence_hz=10,max_joint_step_rad=GATEWAY_JOINT_STEP_RAD,preserve_targets=True),
            gpu_startup=dict(requested_at=self._warm_started_epoch,ready_at=self._warm_ready_epoch,
                elapsed_s=(self._warm_ready_epoch-self._warm_started_epoch) if self._warm_ready_epoch and self._warm_started_epoch else None,
                launch_required=None if self._capacity['available'] is None else not self._capacity['available'],
                launch_started_at=self._launch_started_epoch, capacity_before=self._capacity,
                launch_elapsed_s=(self._warm_ready_epoch-self._launch_started_epoch) if self._warm_ready_epoch and self._launch_started_epoch else None),
            startup_home=self._startup_home, startup_queue=dict(self._startup_queue),
            warmup=self._warm_state,
            warmup_elapsed_s=round(time.monotonic()-self._warm_started_at, 1) if self._warm_started_at else 0,
            display_name=('MolmoAct2 baseline' if self.mode == 'baseline'
                else 'MolmoAct2 + CAG-inspired guidance'), approach=('MolmoAct2 baseline' if self.mode == 'baseline'
                else 'MolmoAct2 + CAG-inspired guidance'), run_context=self.run_context)

    def _json(self, path, payload=None):
        # Reuse the verified endpoint connection across health and inference.
        # Never follow redirects or retry an inference after an ambiguous reply.
        with self._http_lock:
            try:
                if self._connection is None:
                    self._connection = http.client.HTTPSConnection(urlsplit(self._endpoint).hostname, timeout=30)
                self._connection.request('GET' if payload is None else 'POST', path,
                    body=None if payload is None else json.dumps(payload, allow_nan=False).encode(),
                    headers={'Authorization':'Bearer '+self._api_key, 'Content-Type':'application/json'})
                response = self._connection.getresponse()
                body = response.read(8*1024*1024+1)
                if response.status != 200 or len(body) > 8*1024*1024:
                    raise ValueError('Invalid inference response')
                return json.loads(body)
            except Exception as exc:
                if self._connection is not None: self._connection.close()
                self._connection = None
                raise RuntimeError('MolmoAct2 request failed ('+type(exc).__name__+')') from None

    def prefetch_observation(self, observation):
        # Camera reads do not use the robot command capability. Overlap the
        # initial fresh image set with the controller's unchanged feedback gate.
        if self._prefetch is not None or self.cancelled(): return
        job = dict(observed_at=observation.get('observed_at'), done=threading.Event())
        self._prefetch = job
        def capture():
            try: job['frames'] = self._camera_source.capture_for_policy(observation, cancelled=self.cancelled)
            except Exception: pass  # The normal fresh read remains the fallback.
            finally: job['done'].set()
        threading.Thread(target=capture, daemon=True, name='molmoact-first-cameras').start()

    def _frames(self, observation):
        job, self._prefetch = self._prefetch, None
        if job and job['observed_at'] == observation.get('observed_at'):
            while not job['done'].wait(.05):
                if self.cancelled(): raise RuntimeError('MolmoAct2 camera preparation cancelled')
            frames = job.get('frames', [])
            stamps = [getattr(frame, 'source_captured_at', None) for frame in frames]
            observed = observation.get('observed_at')
            if (len(frames) == 3 and type(observed) in (int,float)
                    and all(type(stamp) in (int,float) and 0 <= time.time()-stamp <= 2.
                            and stamp >= observed-.15 for stamp in stamps)):
                return frames
        return self._camera_source.capture_for_policy(observation, cancelled=self.cancelled)

    @staticmethod
    def _identity(value):
        if any(value.get(k) != v for k,v in identity().items()) or not value.get('ok') or value.get('device') != 'cuda:0' or not value.get('cuda_available'):
            raise ValueError('MolmoAct2 model/robot contract mismatch')

    def prepare_before_session(self, prompt):
        # Wake the serverless worker before reserving/launching the robot.
        self.interaction_sink('gpu_check', 'Checking RunPod GPU availability')
        self.start_preparation(self.cancelled)
        self.wait_ready(self.cancelled)
        self.interaction_sink('gpu_ready', 'MolmoAct2 is ready; joining the robot queue')

    def start_preparation(self, cancelled):
        if self._thread is None:
            self._warm_started_at=time.monotonic()
            self._warm_started_epoch=time.time()
            self._warm_state='checking'
            self._thread=threading.Thread(target=self._keep_ready,args=(cancelled,),daemon=True)
            self._thread.start()

    def _capacity_snapshot(self):
        from .runpod_capacity import capacity_snapshot
        return capacity_snapshot(urlsplit(self._endpoint).hostname.split('.')[0], self._api_key)

    def note_queue(self, created):
        # Assignment only: never extend the session-registration/Stop window
        # with another network request. Reuse the normal queue monitor below.
        self._startup_queue = dict(session_id=str(created['session_id']),
            entered_at=created.get('created_at'),
            admitted_at=created.get('run_started_at') if created.get('lease_id') else None,
            observed_at=time.time())

    def note_queue_snapshot(self, snapshot):
        session_id = self._startup_queue.get('session_id')
        if not session_id or self._startup_queue.get('entered_at') is not None:
            return
        entry = next((v for v in snapshot.get('entries', []) if v.get('session_id') == session_id), {})
        stamp = entry.get('created_at')
        if type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp <= 0:
            return
        self._startup_queue = dict(self._startup_queue, entered_at=stamp,
            entry_source='native_queue_snapshot')
        self.interaction_sink('startup_queue', 'Robot queue entry confirmed', **self._startup_queue)

    def note_admission(self, event, payload):
        if self._startup_queue.get('admitted_at') is not None:
            return
        stamp = payload.get('timestamp', event.get('timestamp'))
        if type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp <= 0:
            return
        self._startup_queue = dict(self._startup_queue, admitted_at=stamp,
            episode_id=event.get('episode_id'), source='native_lease_lifecycle')
        self.interaction_sink('startup_admission', 'Robot admission confirmed', **self._startup_queue)

    def note_startup_home(self, observation):
        stamp = observation.get('observed_at')
        if (self._startup_home is not None or observation.get('step_id') != 0
                or observation.get('homed') is not True or observation.get('settled') is not True
                or type(stamp) not in (int,float) or not math.isfinite(stamp) or stamp <= 0):
            return
        self._startup_home = dict(completed_at=stamp, received_at=time.time(),
            episode_id=observation.get('episode_id'), step_id=0,
            source='native_settled_home_observation', visually_verified=False)
        self.interaction_sink('startup_home', 'Both arms confirmed settled at Home', **self._startup_home)

    def _keep_ready(self, cancelled):
        self._capacity = self._capacity_snapshot()
        if cancelled():
            self._warm_state='released'; return
        self._launch_started_epoch = time.time() if self._capacity['available'] is False else None
        self._warm_state='warming' if self._launch_started_epoch else 'checking'
        self.interaction_sink('gpu_startup' if self._launch_started_epoch else 'gpu_check',
            'Starting RunPod GPU and loading MolmoAct2' if self._launch_started_epoch else 'Checking existing RunPod GPU readiness',
            launch_started_at=self._launch_started_epoch, capacity_before=self._capacity)
        deadline=time.monotonic()+600
        while not cancelled():
            try:
                h=self._json('/health'); self._identity(h)
                verification=h.get('verification') or {}
                if h.get('variant') != VARIANT or not all(verification.get(k) is True for k in ('pristine_baseline_equal','zero_strength_exact_equal','nonzero_text_kv_changed','non_goal_kv_unchanged')):
                    raise ValueError('Comparison self-checks are missing')
                self._warm_ready_epoch=self._warm_ready_epoch or time.time()
                self._ready.set(); self._warm_state='ready'; deadline=time.monotonic()+600
                delay=30
            except (RuntimeError,ValueError):
                self._ready.clear(); self._warm_state='warming'; delay=2
                if time.monotonic()>=deadline:
                    self._failure='MolmoAct2 did not become ready within ten minutes'
                    self._warm_state='failed'; return
            until=time.monotonic()+delay
            while not cancelled() and time.monotonic()<until: time.sleep(.1)
        self._ready.clear(); self._warm_state='released'

    def wait_ready(self, cancelled):
        waited=not self._ready.is_set()
        while not self._ready.wait(.1):
            if cancelled() or self.cancelled(): raise RuntimeError('MolmoAct2 preparation cancelled')
            if self._failure: raise RuntimeError(self._failure)
        if cancelled() or self.cancelled(): raise RuntimeError('MolmoAct2 preparation cancelled')
        return waited

    def build_trajectory(self, prompt, observation, first_step_id):
        if not self._ready.is_set(): raise RuntimeError('MolmoAct2 is not ready')
        state=[]
        for arm in ('left','right'):
            q=finite_vector(observation[arm+'_joints_deg'],6)
            g=observation[arm+'_gripper']
            if isinstance(g,bool) or not isinstance(g,(int,float)) or not math.isfinite(g) or not 0<=g<=1:
                raise ValueError('MolmoAct2 needs measured normalized grippers')
            state.extend(math.radians(v) for v in q); state.append(g)
        capture_started=time.monotonic()
        frames=self._frames(observation)
        self.interaction_sink('camera_timing', 'Fresh MolmoAct2 camera set ready', elapsed_s=time.monotonic()-capture_started)
        if len(frames)!=3 or {f.name for f in frames}!=set(CAMERAS):
            raise ValueError('MolmoAct2 needs top and both wrist cameras')
        if self.cancelled(): raise RuntimeError('MolmoAct2 cancelled')
        request_started=time.monotonic()
        result=self._json('/act',dict(robot_id='yam-1', instruction=prompt, state=state,
            images={f.name:base64.b64encode(f.jpeg).decode() for f in frames},
            action_units='radians',gripper_units=GRIPPER_UNITS,
            mode=self.mode,guidance_strength=self.strength,seed=0))
        self._identity(result)
        experiment=result.get('experiment') or {}
        if any(experiment.get(k)!=v for k,v in dict(variant=VARIANT,mode=self.mode,effective_strength=self.strength,seed=0,num_steps=10,revision=REVISION,dtype='bfloat16',enable_cuda_graph=False).items()):
            raise ValueError('MolmoAct2 intervention receipt mismatch')
        rows=validate_actions(result.get('actions'))
        if self.cancelled(): raise RuntimeError('MolmoAct2 cancelled')
        self.interaction_sink('model_timing', 'MolmoAct2 prediction', elapsed_s=result.get('inference_seconds'), request_s=time.monotonic()-request_started, experiment=experiment)
        return self._gateway_trajectory(rows, state, first_step_id)

    def _gateway_trajectory(self, rows, measured_state, first_step_id):
        # Preserve every selected absolute target and the complete path. Add
        # linear samples where30Hz->10Hz sampling exceeds gateway pacing.
        # The robot still validates the entire packet before any motion.
        targets=rows[2::3]
        capacity=min(MAX_WAYPOINTS_PER_PACKET,MAX_COMMANDS-first_step_id)
        joints=tuple(range(6))+tuple(range(7,13))
        previous=list(measured_state);points=[]
        for target in targets:
            count=max(1,math.ceil(max(abs(target[i]-previous[i]) for i in joints)/GATEWAY_JOINT_STEP_RAD))
            if len(points)+count>capacity:
                raise ValueError('MolmoAct2 paced trajectory exceeds gateway budget; entire chunk rejected')
            for index in range(1,count+1):
                row=list(target) if index==count else [a+(b-a)*index/count for a,b in zip(previous,target)]
                points.append(dict(step_id=first_step_id+len(points),
                    left_joints_deg=[math.degrees(v) for v in row[:6]],
                    right_joints_deg=[math.degrees(v) for v in row[7:13]],
                    left_gripper=row[6],right_gripper=row[13]))
            previous=list(target)
        self.interaction_sink('trajectory_pacing','Paced MolmoAct2 targets for the existing gateway',
            predicted_waypoints=len(targets),gateway_waypoints=len(points),max_joint_step_rad=GATEWAY_JOINT_STEP_RAD)
        return points

    def trajectory_completed(self, observation, waypoint_count):
        pass
