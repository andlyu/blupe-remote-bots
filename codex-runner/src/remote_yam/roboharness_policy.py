"""RoboHarness visual-geometric tool loop over the existing checked controller.

Underlying model IDs are separate from Model=RoboHarness. A transport must be
attached explicitly: the existing private Codex broker or local Codex login.
There is no API-key or alternate-model fallback.
"""
import base64
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import time
from types import MethodType

from .api_depth_set import ApiDepthSet
from .codex_policy import CodexAdapter, codex_binary, codex_status
from .mujoco_ik import ROBOT_SHA256
from .providers import PolicyComplete, ResponsesAdapter
from .robocurve_policy import RoboCurveResponsesAdapter
from .roboharness_contract import SCHEMA, NAMES, INSTRUCTIONS, decision_response
from .roboharness_control import RoboHarnessControl, InputRejected
from .roboharness_tracking import KeypointTracker


class RoboHarnessAdapter(RoboCurveResponsesAdapter):
    provider_name='roboharness'
    response_speed='standard'
    reasoning_effort='low'

    def __init__(self, api_origin, robot_id, report, *, expected_calibration_id,
                 expected_model_calibration_id, model='gpt-6-astra', recording_root=None,
                 camera_source=None):
        if not isinstance(model,str) or not model.strip():raise ValueError('Select an exact underlying planning/vision model')
        self.robot_id=robot_id
        self._depth_joint_offsets_rad=None
        self._verify_calibration(report,expected_calibration_id,expected_model_calibration_id)
        self.model=model;self._api_key=''
        self._initialize_observation(camera_source or ApiDepthSet(api_origin,api_origin,robot_id=robot_id))
        self._initialize_policy(recording_root)
        self._decision_schema=deepcopy(SCHEMA);self._decision_response=decision_response
        self._decision_instructions=INSTRUCTIONS;self._system_prompt=INSTRUCTIONS
        self._tools=[];self._names=NAMES;self._expected_camera_count=3
        self.tracker=KeypointTracker();self._resolved_model=None
        self._bound_calibration_id=expected_calibration_id
        self._model_calibration_id=expected_model_calibration_id
        self._calibration_warnings=deepcopy(report.get('quality',{}))
        self._timeout_s=120

    def _verify_calibration(self,report,expected,model_expected):
        if (not isinstance(report,dict) or report.get('robot_id')!=self.robot_id
                or report.get('calibration_id')!=expected
                or not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected)
                or report.get('measurement_scope')=='camera_optical_only'
                or report.get('quality',{}).get('failures')):
            raise ValueError('Bind the selected robot and exact usable RGB-D calibration before inference')
        binding=report.get('model_joint_calibration');native=report.get('native_joint_calibration')
        if (binding is None)==(native is None):raise ValueError('One explicit model/native coordinate convention is required')
        selected=binding if binding is not None else native
        if selected.get('calibration_id')!=model_expected:raise ValueError('Model calibration identity mismatch')
        if binding is not None:
            if (binding.get('coordinate_convention')!='original_i2rt_model_corrected'
                    or binding.get('canonical_model_sha256')!=ROBOT_SHA256):raise ValueError('Unsupported corrected-model coordinates')
            offsets=binding.get('offsets_rad')
            if not isinstance(offsets,dict) or set(offsets)!={'left','right'}:raise ValueError('Missing model offsets')
            values=[]
            for arm in ('left','right'):
                raw=offsets[arm]
                if not isinstance(raw,list) or len(raw)!=6 or any(type(v) not in (int,float) or not math.isfinite(v) for v in raw):raise ValueError('Invalid model offsets')
                values+=raw
            self._depth_joint_offsets_rad=values
        else:
            if (native.get('coordinate_convention')!='native_i2rt_updated'
                    or report.get('kinematics',{}).get('robot_model_sha256')!=ROBOT_SHA256
                    or native.get('additional_offsets_rad')!={'left':[0]*6,'right':[0]*6}):raise ValueError('Native coordinates must not receive model offsets twice')
        spacing=.5 if self.robot_id=='yam-1' else .62
        if report.get('base_geometry',{}).get('spacing_m')!=spacing:raise ValueError('Selected station base spacing mismatch')
        if not report.get('cameras',{}).get('top',{}).get('T_base_camera'):raise ValueError('Overhead arm-base extrinsics are required')

    def _make_geometry(self):
        return RoboHarnessControl(self.robot_id,joint_offsets_rad=self._depth_joint_offsets_rad)

    def use_local_codex(self):
        setup=codex_status()
        if not setup.get('ready'):raise RuntimeError(setup.get('message','Codex subscription is unavailable'))
        self._workspace=tempfile.TemporaryDirectory(prefix='yam-roboharness-codex-')
        self._thread_id=None;self._sent_items=0;self._binary=codex_binary()
        self._post_json=MethodType(CodexAdapter._post_json,self)
        self._execute=MethodType(CodexAdapter._execute,self)
        self.close_transport=self._workspace.cleanup
        return self

    def _post_json(self,payload):
        raise RuntimeError('Attach the selected Codex subscription transport explicitly; no model fallback')

    def public_config(self):
        return {'provider':self.provider_name,'model':'RoboHarness','display_name':'RoboHarness',
            'policy':'roboharness_visual_geometric_yam','variant':'replacement_planner_stationary_yam',
            'underlying_models':{'planning':self.model,'vision':self.model,'resolved':self._resolved_model,
                                 'reasoning_effort':self.reasoning_effort},
            'runner_name':getattr(self,'runner_name',None),'execution_mode':getattr(self,'execution_mode','interactive'),
            'reasoning_effort':self.reasoning_effort,
            'api_key_configured':False,'model_calls':self._calls,'note':self._note,'outcome':self._outcome,
            'calibration_id':self._bound_calibration_id,'model_calibration_id':self._model_calibration_id,
            'calibration_quality':self._calibration_warnings,
            'controller_workspace':self._geometry.profile.summary(),
            'tracking':self.tracker.summary(),'recording_path':str(self._recorder.path) if self._recorder else None,
            'command_contract':'roboharness_yam_v1','simulation_rollout':False,
            'prompt_sha256':hashlib.sha256(INSTRUCTIONS.encode()).hexdigest()}

    def _capture(self,observation):
        frames=self._capture_frames(observation)
        snapshots=getattr(self._camera_source,'snapshots',{})
        if set(snapshots)!={'top','left','right'}:raise RuntimeError('RoboHarness requires three fresh paired RGB-D captures')
        if any(s.metadata.get('calibration_id')!=self._bound_calibration_id for s in snapshots.values()):
            raise RuntimeError('Camera calibration changed after model binding; stop and review')
        self.tracker.update(snapshots['top'])
        return {f.name:f for f in frames}

    def _observation_message(self,prompt,observation,first_step_id):
        frames=self._capture(observation)
        poses=self._geometry.pose_summary(observation)
        points=self.tracker.measure()
        content=[{'type':'input_text','text':json.dumps(dict(task=prompt,robot=self.robot_id,
            poses=poses,tracked_points=points,tracking=self.tracker.summary(),
            calibration_quality=self._calibration_warnings,waypoint_cursor=first_step_id),allow_nan=False)}]
        self._vision_frames=[]
        for name in ('top','left','right'):
            frame=frames[name];self._vision_frames.append(frame.summary())
            content.extend([{'type':'input_text','text':f'{name} camera; overhead selection coordinates 0..1000'},
                {'type':'input_image','image_url':'data:image/png;base64,'+base64.b64encode(frame.jpeg).decode(),'detail':'high'}])
        return {'role':'user','content':content}

    def build_trajectory(self,prompt,observation,first_step_id):
        self.last_step_model_s=0.
        if self._pending is not None:raise RuntimeError('Wait for matched measured packet completion')
        if self._outcome is not None:raise PolicyComplete(self._outcome['status'])
        identity=(observation.get('episode_id'),observation.get('lease_id'))
        if not self._history:
            self._prompt=prompt;self._episode=identity
            self._history=[{'role':'system','content':INSTRUCTIONS}]
        elif self._prompt!=prompt or self._episode!=identity:raise RuntimeError('New task/lease needs a fresh RoboHarness conversation')
        while self._calls<64:
            if self.cancelled():raise RuntimeError('RoboHarness stopped; no new motion sent')
            message=self._observation_message(prompt,observation,first_step_id)
            self._history.append(message);self.steering.include(self._history)
            payload={'model':self.model,'input':deepcopy(self._history),'tools':[],'store':False}
            self._calls+=1;self._record('request',call=self._calls,request=payload)
            self._interaction('model_request','RoboHarness is interpreting the cameras and geometric tools',model=self.model)
            started=time.monotonic()
            try:raw=self._post_json(payload)
            finally:
                elapsed=time.monotonic()-started;self.last_step_model_s+=elapsed
                self._interaction('model_timing',f'Planning and vision: {elapsed:.2f}s',elapsed_s=elapsed)
            self._record('response',call=self._calls,response=raw)
            calls=raw.get('output',[])
            if len(calls)!=1 or calls[0].get('type')!='function_call':raise RuntimeError('Expected one validated RoboHarness tool')
            call=calls[0];self._history.extend(deepcopy(calls))
            args=json.loads(call['arguments']);name=call['name'];note=args.pop('note','')
            self._note=note
            self._interaction('model_response',note or name,tools=[{'name':name,'arguments':args}])
            if self.cancelled():raise RuntimeError('RoboHarness stopped during inference; no motion sent')
            if name in ('done','give_up'):
                self._outcome={'status':name,**args};self._tool_result(call['call_id'],self._outcome)
                raise PolicyComplete(name)
            try:
                registration=args.pop('register',None)
                if registration is not None:self.tracker.register(args['point_ids'][0],**registration)
                if callable(self.refresh_observation):observation=self.refresh_observation()
                self._capture(observation)
                if name=='track_object':
                    result={'ok':True,'tracking':self.tracker.summary(),'points':self.tracker.measure()}
                    self._tool_result(call['call_id'],result)
                    if callable(self.refresh_observation):observation=self.refresh_observation()
                    continue
                # Reconcile fresh feedback/images after inference. Track image
                # points into the new frames before resolving any robot target.
                if callable(self.refresh_observation):observation=self.refresh_observation()
                if self.steering.pending():
                    self._tool_result(call['call_id'],{'ok':False,'error':'New run-owner guidance superseded this unsent decision'})
                    continue
                command={'kind':name,**args}
                points=self._geometry.build(command,observation,first_step_id,points=self.tracker.measure())
                self._pending={'call_id':call['call_id'],'waypoint_count':len(points),'last_step_id':points[-1]['step_id']}
                self._record('joint_packet',command=command,waypoints=points,tracking=self.tracker.summary())
                self._interaction('packet_ready',f'Validated {name}: {len(points)} waypoints at 10 Hz',command=command)
                return points
            except InputRejected as exc:
                self._tool_result(call['call_id'],{'ok':False,'stage':'local_validation','error':str(exc),'steps':0,'dispatched':False})
                self._failures+=1
                if self._failures>=3:raise RuntimeError('Three local input rejections; stop and review') from exc
                if callable(self.refresh_observation):observation=self.refresh_observation()
        raise RuntimeError('RoboHarness model call budget exhausted')

    def trajectory_failed(self,*args,**kwargs):
        # Even a settled-timeout recovery in the generic policy must not replay
        # a movement here. The explicit harness timeout rule takes precedence.
        raise RuntimeError('RoboHarness motion failed or timed out; stop and review, no automatic retry')

    def measured_step_displacement(self,start,end):
        import numpy as np
        a=self._geometry.pose_summary(start);b=self._geometry.pose_summary(end)
        return {arm+'_displacement_m':float(np.linalg.norm(np.array(b[arm]['position_m'])-a[arm]['position_m'])) for arm in ('left','right')}
