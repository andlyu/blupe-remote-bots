"""YAM1-only MolmoAct2 comparison. Queue/controller remains sole robot writer."""
import base64
import json
import math
import re
import threading
import time
from urllib import request
from urllib.parse import urlsplit
from .cameras import NoRedirect
from .molmoact_protocol import (MODEL, REVISION, CAMERAS, GRIPPER_UNITS,
                               identity, validate_actions, finite_vector, valid_grippers)
from .session import MAX_COMMANDS, MAX_WAYPOINTS_PER_PACKET

VARIANT = 'cag-inspired-molmoact2-v1'


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
        self._warm_state, self._failure = 'waiting_for_queue', None
        self._opener = request.build_opener(NoRedirect)

    def public_config(self):
        return dict(provider=self.provider_name, model=MODEL, revision=REVISION,
            variant=VARIANT, mode=self.mode, guidance_strength=self.strength, seed=0,
            num_steps=10, dtype='bfloat16', enable_cuda_graph=False, robot_id='yam-1',
            warmup=self._warm_state, display_name=('MolmoAct2 baseline' if self.mode == 'baseline'
                else 'MolmoAct2 + CAG-inspired guidance'), approach=('MolmoAct2 baseline' if self.mode == 'baseline'
                else 'MolmoAct2 + CAG-inspired guidance'), run_context=self.run_context)

    def _json(self, path, payload=None):
        req = request.Request(self._endpoint+path,
            data=None if payload is None else json.dumps(payload, allow_nan=False).encode(),
            headers={'Authorization':'Bearer '+self._api_key, 'Content-Type':'application/json'})
        try:
            with self._opener.open(req, timeout=30) as response:
                return json.loads(response.read(8*1024*1024))
        except Exception as exc:
            raise RuntimeError('MolmoAct2 request failed ('+type(exc).__name__+')') from None

    @staticmethod
    def _identity(value):
        if any(value.get(k) != v for k,v in identity().items()) or not value.get('ok') or value.get('device') != 'cuda:0' or not value.get('cuda_available'):
            raise ValueError('MolmoAct2 model/robot contract mismatch')

    def start_preparation(self, cancelled):
        if self._thread is None:
            self._warm_state='warming'
            self._thread=threading.Thread(target=self._keep_ready,args=(cancelled,),daemon=True)
            self._thread.start()

    def _keep_ready(self, cancelled):
        deadline=time.monotonic()+600
        while not cancelled():
            try:
                h=self._json('/health'); self._identity(h)
                verification=h.get('verification') or {}
                if h.get('variant') != VARIANT or not all(verification.get(k) is True for k in ('pristine_baseline_equal','zero_strength_exact_equal','nonzero_text_kv_changed','non_goal_kv_unchanged')):
                    raise ValueError('Comparison self-checks are missing')
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
            if cancelled(): raise RuntimeError('MolmoAct2 preparation cancelled')
            if self._failure: raise RuntimeError(self._failure)
        if cancelled(): raise RuntimeError('MolmoAct2 preparation cancelled')
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
        frames=self._camera_source.capture_for_policy(observation,cancelled=self.cancelled)
        if len(frames)!=3 or {f.name for f in frames}!=set(CAMERAS):
            raise ValueError('MolmoAct2 needs top and both wrist cameras')
        if self.cancelled(): raise RuntimeError('MolmoAct2 cancelled')
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
        self.interaction_sink('model_timing', 'MolmoAct2 prediction', elapsed_s=result.get('inference_seconds'), experiment=experiment)
        targets=rows[2::3]  # 30 Hz absolute targets -> ten 10 Hz gateway samples.
        if len(targets)>min(MAX_WAYPOINTS_PER_PACKET,MAX_COMMANDS-first_step_id):
            raise ValueError('MolmoAct2 trajectory exceeds gateway budget; entire chunk rejected')
        return [dict(step_id=first_step_id+i,
            left_joints_deg=[math.degrees(v) for v in row[:6]],
            right_joints_deg=[math.degrees(v) for v in row[7:13]],
            left_gripper=row[6],right_gripper=row[13]) for i,row in enumerate(targets)]

    def trajectory_completed(self, observation, waypoint_count):
        pass
