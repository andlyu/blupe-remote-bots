"""Queued GR00T inference. Only the leased controller submits robot commands."""
import base64
import io
import json
import math
import threading
import time
from urllib import request
from .cameras import NoRedirect
from .session import MAX_COMMANDS, MAX_WAYPOINTS_PER_PACKET

MODEL = 'groot-reviewed-step10000'
ENDPOINT = 'https://3xjhrdbhwcnux3.api.runpod.ai'
MAX_JOINT_STEP_RAD = .01


class GrootAdapter:
    provider_name = 'groot'
    model = MODEL

    def __init__(self, api_key, *, camera_source):
        if not api_key.strip():
            raise ValueError('GR00T service credential is missing')
        self._api_key = api_key.strip()
        self._camera_source = camera_source
        self.cancelled = lambda: False
        self.interaction_sink = lambda *args, **kwargs: None
        self._ready = threading.Event()
        self._failure = None
        self._warm_state = 'waiting_for_queue'
        self._thread = None
        self._opener = request.build_opener(NoRedirect)

    def public_config(self):
        return {'provider': self.provider_name, 'model': self.model,
                'warmup': self._warm_state, 'api_key_configured': bool(self._api_key)}

    def _json(self, path, payload=None):
        req = request.Request(ENDPOINT + path, data=None if payload is None else json.dumps(payload).encode(),
                              headers={'Authorization': 'Bearer '+self._api_key, 'Content-Type':'application/json'})
        try:
            with self._opener.open(req, timeout=12) as response:
                return json.loads(response.read(8*1024*1024))
        except Exception as exc:
            # No exception text or credential-bearing request objects escape.
            raise RuntimeError('GR00T request failed ('+type(exc).__name__+')') from None

    def start_preparation(self, cancelled):
        if self._thread is not None:
            return
        self._warm_state = 'warming'
        self._thread = threading.Thread(target=self._keep_ready, args=(cancelled,), daemon=True)
        self._thread.start()

    def _keep_ready(self, cancelled):
        deadline = time.monotonic()+600
        while not cancelled():
            try:
                h = self._json('/health')
                if not (h.get('ok') and h.get('cuda_available') and h.get('device') == 'cuda:0'
                        and h.get('checkpoint_step') == 10000 and h.get('action_dim') == 14
                        and h.get('num_actions') == 30 and h.get('norm_tag') == 'yam_reviewed_groot'):
                    raise RuntimeError('GR00T checkpoint contract mismatch')
                self._warm_state = 'ready'; self._ready.set(); deadline = time.monotonic()+600
                delay = 30
            except RuntimeError:
                self._ready.clear(); self._warm_state = 'warming'; delay = 2
                if time.monotonic() >= deadline:
                    self._failure = 'GR00T did not become ready within ten minutes'
                    self._warm_state = 'failed'; return
            until = time.monotonic()+delay
            while not cancelled() and time.monotonic() < until:
                time.sleep(.1)
        self._warm_state = 'released'

    def wait_ready(self, cancelled):
        waited = not self._ready.is_set()
        while not self._ready.wait(.1):
            if cancelled(): raise RuntimeError('GR00T preparation cancelled')
            if self._failure: raise RuntimeError(self._failure)
        if cancelled(): raise RuntimeError('GR00T preparation cancelled')
        return waited

    def build_trajectory(self, prompt, observation, first_step_id):
        if not self._ready.is_set():
            raise RuntimeError('GR00T is not ready')
        state = []
        for arm in ('left','right'):
            q = observation[arm+'_joints_deg']; g = observation[arm+'_gripper']
            if len(q)!=6 or not all(math.isfinite(v) for v in q) or not isinstance(g,(int,float)) or not 0<=g<=1:
                raise ValueError('GR00T requires measured 6+6 joints and both grippers')
            state.extend(math.radians(v) for v in q); state.append(g)
        frames = self._camera_source.capture_for_policy(observation, cancelled=self.cancelled)
        if {f.name for f in frames} != {'top','left','right'}:
            raise ValueError('GR00T requires top and both wrist cameras')
        from PIL import Image
        images = {}
        for frame in frames:
            output = io.BytesIO()
            with Image.open(io.BytesIO(frame.jpeg)) as image:
                image.convert('RGB').resize((640,360)).save(output,format='JPEG')
            images[frame.name+'_cam'] = {'encoding':'jpeg_base64','data':base64.b64encode(output.getvalue()).decode()}
        if self.cancelled(): raise RuntimeError('GR00T cancelled')
        result = self._json('/act', {'model':MODEL,'instruction':prompt,'state':state,'images':images,'action_units':'radians'})
        rows = result.get('actions')
        if (result.get('model') != MODEL or result.get('checkpoint_step') != 10000
                or result.get('action_units') != 'radians' or not isinstance(rows,list) or len(rows)!=30
                or any(not isinstance(r,list) or len(r)!=14 or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in r) for r in rows)
                or any(not 0<=r[i]<=1 for r in rows for i in (6,13))):
            raise ValueError('Invalid GR00T action chunk')
        if self.cancelled(): raise RuntimeError('GR00T cancelled')
        return self._bounded_trajectory(state, rows, first_step_id)

    def _bounded_trajectory(self, state, rows, first_step_id):
        # Retain the existing 30 Hz -> 10 Hz sampling. If the learned targets
        # exceed the runner's conservative step bound, dilate the WHOLE chunk
        # by one factor. Independent per-target ramps change the relative timing
        # of the learned movement. Both arms and grippers use the same clock.
        targets = rows[2::3]
        joints = (0,1,2,3,4,5,7,8,9,10,11,12)
        previous = state
        max_delta = 0.
        for target in targets:
            max_delta = max(max_delta, max(abs(target[j]-previous[j]) for j in joints))
            previous = target
        capacity = min(MAX_WAYPOINTS_PER_PACKET, MAX_COMMANDS-first_step_id)
        max_scale = capacity // len(targets)
        # Check before ceil/allocation, including finite inputs whose subtraction
        # overflows. Never truncate an oversized chunk to fit the packet budget.
        if max_scale < 1 or max_delta > MAX_JOINT_STEP_RAD*max_scale+1e-12:
            raise ValueError('GR00T trajectory exceeds gateway budget at the joint-step limit '
                             f'(largest sampled change {max_delta:.4g} rad; {capacity} waypoints available)')
        scale = max(1, math.ceil((max_delta-1e-12)/MAX_JOINT_STEP_RAD))
        points = []
        previous = state
        for target in targets:
            for tick in range(1, scale+1):
                if self.cancelled(): raise RuntimeError('GR00T cancelled')
                values = target if tick == scale else [a+(b-a)*tick/scale for a,b in zip(previous,target)]
                points.append({'step_id':first_step_id+len(points),
                    'left_joints_deg':[math.degrees(v) for v in values[:6]],
                    'right_joints_deg':[math.degrees(v) for v in values[7:13]],
                    'left_gripper':values[6], 'right_gripper':values[13]})
            previous = target
        if scale > 1:
            self.interaction_sink('trajectory_timing', 'GR00T motion slowed to stay within joint limits',
                source_duration_s=1., playback_duration_s=len(points)/10,
                time_scale=scale, max_sampled_joint_delta_rad=max_delta,
                max_joint_step_rad=MAX_JOINT_STEP_RAD, waypoint_count=len(points))
        return points

    def trajectory_completed(self, observation, waypoint_count):
        pass
