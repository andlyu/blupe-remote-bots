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
import threading
import uuid
from types import MethodType
import numpy as np

from .api_depth import rigid
from .roboharness_cameras import RoboHarnessCameras
from .codex_policy import CodexAdapter, codex_binary, codex_status
from .mujoco_ik import ROBOT_SHA256
from .providers import PolicyComplete, ResponsesAdapter
from .robocurve_policy import RoboCurveResponsesAdapter
from .roboharness_contract import SCHEMA, NAMES, INSTRUCTIONS, decision_response, instructions_for_camera
from .roboharness_control import RoboHarnessControl, InputRejected, vector
from .roboharness_tracking import KeypointTracker, StaleTrackingDepth
from .yam_gripper_reference import reference_for_model, nominal_tool_pose


INITIALIZATION_CARD_PNG_BASE64='iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAI0lEQVR4nGNsaGhgIAUwkaSaYVQDcYCJSHVwMKqBGEByKAEAyUwBoHKcrY0AAAAASUVORK5CYII='
INITIALIZATION_CARD_SHA256='5fc031e7b497a6cf7c4cb65d5685c12649ad48013f1a22a91200b764d3378225'


class RoboHarnessAdapter(RoboCurveResponsesAdapter):
    provider_name='roboharness'
    response_speed='standard'
    reasoning_effort='low'

    def __init__(self, api_origin, robot_id, report, *, expected_calibration_id,
                 expected_model_calibration_id, model='gpt-6-astra', recording_root=None,
                 camera_source=None, warm_model_session=False, grounding_camera='top'):
        if not isinstance(model,str) or not model.strip():raise ValueError('Select an exact underlying planning/vision model')
        self.robot_id=robot_id
        self._depth_joint_offsets_rad=None
        self._verify_calibration(report,expected_calibration_id,expected_model_calibration_id)
        self.model=model;self._api_key=''
        self._initialize_observation(camera_source or RoboHarnessCameras(api_origin,robot_id=robot_id))
        self._initialize_policy(recording_root)
        self._decision_schema=deepcopy(SCHEMA);self._decision_response=self._parse_decision
        self._decision_instructions=INSTRUCTIONS;self._system_prompt=INSTRUCTIONS
        self._tools=[];self._names=NAMES;self._expected_camera_count=3
        self.tracker=KeypointTracker();self._resolved_model=None
        self._tool_geometry_reference=reference_for_model(self._geometry.ik,self.robot_id)
        self._bound_calibration_id=expected_calibration_id
        self._model_calibration_id=expected_model_calibration_id
        self._calibration_warnings=deepcopy(report.get('quality',{}))
        self._timeout_s=120
        self._warm_model_session=bool(warm_model_session)
        self._preparation_done=None;self._preparation_error=None;self._model_preparation=None
        self.select_grounding_camera(grounding_camera)

    def _record_structured_decision(self,text):
        self._record('structured_decision',call=self._calls,final_text=text,
            sha256=hashlib.sha256(text.encode()).hexdigest())

    def _parse_decision(self,result):
        try:return decision_response(result)
        except InputRejected as exc:
            # Syntactically decoded but invalid fields have sent no movement.
            # Preserve strict validation and feed its rejection through the
            # existing bounded tool-feedback loop, not through motor dispatch.
            self._record('decision_validation_rejected',call=self._calls,error=str(exc))
            args=dict(ok=False,stage='decision_validation',error=str(exc),steps=0,dispatched=False,
                note='Planning decision failed validation; no movement sent.')
            return {'output':[dict(type='function_call',call_id='roboharness_'+uuid.uuid4().hex,
                name='decision_rejected',arguments=json.dumps(args,allow_nan=False))]}

    def select_grounding_camera(self,camera):
        if camera not in ('top','left','right'):raise ValueError('Select overhead, left wrist or right wrist depth')
        if self._history or self._calls or self._pending is not None or self._preparation_done is not None or self.tracker.snapshot is not None:
            raise ValueError('Changing the grounding camera requires a new run')
        self.grounding_camera=camera
        self._camera_source.grounding_camera=camera
        self.tracker=KeypointTracker(camera)
        self._decision_instructions=self._system_prompt=instructions_for_camera(camera)

    def start_preparation(self,cancelled):
        """Initialize the same model transport during normal queue admission.

        One explicitly synthetic non-robot initialization card is supplied to
        satisfy the existing broker protocol. No robot image/state/target or
        command is supplied. Actual policy
        observation and command construction wait for this single initialization.
        Queue/Home clocks remain the controller's original measured clocks.
        """
        if not self._warm_model_session:return
        if self._preparation_done is not None:return
        name=getattr(self,'runner_name',None)
        if not isinstance(name,str) or not name.strip():
            raise RuntimeError('Confirmed runner attribution is required before model initialization')
        self._preparation_done=threading.Event()
        self._model_preparation=dict(state='starting',started_at=time.time(),model=self.model,
            runner_name=name,execution_mode=getattr(self,'execution_mode','interactive'),model_calls=0,
            images=1,robot_images=0,initialization_card_sha256=INITIALIZATION_CARD_SHA256,robot_targets=0,actuator_submissions=0)
        self._interaction('model_preparation','Initializing the planning session while normal queue admission proceeds',
            preparation=dict(self._model_preparation))
        def initialize():
            started=time.monotonic();camera_count=self._expected_camera_count;inference_started=None
            try:
                if cancelled():raise RuntimeError('Planning session initialization cancelled')
                payload={'model':self.model,'tools':[],'store':False,
                    'instructions':'NON-ACTUATING TRANSPORT INITIALIZATION ONLY. The single solid-gray16x16PNG is a synthetic initialization card, not robot footage or state. Do not select a target or command movement. Return only give_up with all targets null and reason=non_actuating_session_ready.',
                    'input':[
                    {'role':'system','content':'Initialize model transport only. Do not command robot movement.'},
                    {'role':'user','content':[
                        {'type':'input_text','text':'This synthetic solid-gray initialization card carries no robot observation or target. Acknowledge transport readiness only: action=give_up, all targets null, reason=non_actuating_session_ready, empty summary/hindsight.'},
                        {'type':'input_image','image_url':'data:image/png;base64,'+INITIALIZATION_CARD_PNG_BASE64,'detail':'low'}]}]}
                self._record('model_preparation_request',runner_name=name,
                    execution_mode=getattr(self,'execution_mode','interactive'),request=payload)
                # The initialization acknowledgement has no robot observation.
                # The real policy waits for completion and still requires three
                # fresh images; restore this guard even on failure/cancellation.
                self._expected_camera_count=1
                self._model_preparation={**self._model_preparation,'model_calls':1}
                inference_started=time.monotonic()
                raw=self._post_json(payload)
                output=raw.get('output',[])
                if len(output)!=1 or output[0].get('type')!='function_call' or output[0].get('name')!='give_up':
                    raise RuntimeError('Model initialization did not return the non-actuating acknowledgement')
                if cancelled():raise RuntimeError('Planning session initialization cancelled')
                # Warm-up is not part of the policy's message list. Send the
                # complete real task context on the resumed, same transport.
                self._sent_items=0
                self._record('model_preparation_response',response=raw)
                self._model_preparation={**self._model_preparation,'state':'ready','model_calls':1,
                    'ready_at':time.time(),'duration_s':time.monotonic()-started}
                self._interaction('model_preparation_ready','Planning session initialized; fresh robot observations remain required',
                    preparation=dict(self._model_preparation))
            except Exception as exc:
                self._preparation_error=exc
                self._model_preparation={**self._model_preparation,'state':'failed',
                    'failed_at':time.time(),'duration_s':time.monotonic()-started,'error_type':type(exc).__name__}
                self._interaction('model_preparation_failed','Planning session initialization failed; stop this run before another attempt',
                    preparation=dict(self._model_preparation))
            finally:
                self._expected_camera_count=camera_count
                try:
                    if inference_started is not None:
                        self._interaction('model_timing','Planning session initialization inference completed',
                            elapsed_s=time.monotonic()-inference_started,phase='non_actuating_initialization')
                except Exception as exc:
                    self._preparation_error=exc
                    self._model_preparation={**self._model_preparation,'state':'failed','error_type':type(exc).__name__}
                finally:self._preparation_done.set()
        threading.Thread(target=initialize,daemon=True,name='roboharness-model-initialization').start()

    def _await_preparation(self):
        if self._preparation_done is None:return
        deadline=time.monotonic()+self._timeout_s
        while not self._preparation_done.wait(.05):
            if self.cancelled():raise RuntimeError('RoboHarness stopped during planning session initialization')
            if time.monotonic()>=deadline:raise RuntimeError('Planning session initialization timed out; stop without retry')
        if self._preparation_error is not None:
            raise RuntimeError('Planning session initialization failed; stop without retry') from self._preparation_error
        if self.cancelled():raise RuntimeError('RoboHarness stopped after planning session initialization')

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
            'api_key_configured':False,'model_preparation':deepcopy(self._model_preparation),'warm_model_session':self._warm_model_session,'model_calls':self._calls,'note':self._note,'outcome':self._outcome,
            'calibration_id':self._bound_calibration_id,'model_calibration_id':self._model_calibration_id,
            'calibration_quality':self._calibration_warnings,
            'controller_workspace':self._geometry.profile.summary(),
            'tracking':self.tracker.summary(),'tool_geometry_reference':self._tool_geometry_reference,'vision_roles':['top','left','right'],'grounding_camera':self.grounding_camera,'depth_grounding_roles':[self.grounding_camera],'recording_path':str(self._recorder.path) if self._recorder else None,
            'command_contract':'roboharness_yam_v1','simulation_rollout':False,
            'prompt_sha256':hashlib.sha256(self._system_prompt.encode()).hexdigest()}

    def _capture(self,observation):
        started=time.monotonic()
        role=self.grounding_camera
        self._interaction('camera_capture','Reading current '+role+' depth and all three camera views')
        frames=self._capture_frames(observation)
        snapshots=getattr(self._camera_source,'snapshots',{})
        if role not in snapshots or len(frames)!=3 or {f.name for f in frames}!={'top','left','right'}:
            raise RuntimeError('RoboHarness requires selected paired RGB-D and two RGB context views')
        if any(s.metadata.get('calibration_id')!=self._bound_calibration_id for s in snapshots.values()):
            raise RuntimeError('Camera calibration changed after model binding; stop and review')
        tracking_before=self.tracker.summary()
        self.tracker.update(snapshots[role])
        if self._recorder is not None:
            selected=next(frame for frame in frames if frame.name==role)
            snapshot=snapshots[role]
            self._record('tracking_frame',camera=role,captured_at=snapshot.metadata['captured_at'],
                calibration_id=snapshot.metadata['calibration_id'],sensor_serial=snapshot.metadata['sensor_serial'],
                image_url='data:image/png;base64,'+base64.b64encode(selected.jpeg).decode(),
                tracking_before=tracking_before,tracking_after=self.tracker.summary())
        self._interaction('camera_captured','Current robot camera views received',elapsed_s=time.monotonic()-started,grounding_camera=role,selected_depth_age_s=snapshots[role].age())
        return {f.name:f for f in frames}

    def _measure_points(self,observation):
        if self.grounding_camera=='top':return self.tracker.measure()
        role=self.grounding_camera
        # The mounting transform is never mistaken for a base pose. This uses
        # the same registered native grasp origin and selected joint offsets
        # as command FK. The capture must follow settled feedback; refresh is
        # bound to this lease/cursor, and observe validates current hardware.
        poses=self._geometry.pose_summary(observation)
        camera=self.tracker.snapshot.calibration['cameras'][role]
        if camera.get('parent_frame')!=role+'_grasp':
            raise InputRejected('Wrist mounting transform must name the registered native grasp frame')
        mount=rigid(camera['T_grasp_camera'])
        index=('left','right').index(role)
        position=np.array(poses[role]['position_m'])+self._geometry.bases[index]
        transforms={}
        for i,arm in enumerate(('left','right')):
            grasp=np.eye(4);grasp[:3,:3]=poses[role]['rotation_matrix']
            grasp[:3,3]=position-self._geometry.bases[i]
            transforms[arm]=grasp@mount
        return self.tracker.measure(camera_poses=transforms)

    def _refresh_feedback(self,observation,first_step_id):
        if callable(self.refresh_observation):
            observation=self.refresh_observation()
        if (not isinstance(observation,dict) or
                (observation.get('episode_id'),observation.get('lease_id'))!=self._episode or
                type(observation.get('step_id')) is not int or observation['step_id']!=first_step_id):
            raise RuntimeError('Run/lease/cursor identity changed during camera capture')
        return observation

    def _fresh_view(self,observation,first_step_id,*,metric=True):
        for attempt in range(2):
            frames=self._capture(observation)
            observation=self._refresh_feedback(observation,first_step_id)
            try:
                points=self._measure_points(observation) if metric else None
                return frames,observation,points
            except StaleTrackingDepth:
                if attempt:raise
                self._interaction('camera_reacquire','Depth aged during observation preparation; reading fresh cameras before inference or dispatch')
        raise RuntimeError('No fresh RoboHarness observation')

    def _observation_message(self,prompt,observation,first_step_id):
        self._await_preparation()
        # Reacquire only the read-only view if tracker/feedback processing aged
        # it; neither model inference nor an actuator request is retried.
        frames,observation,points=self._fresh_view(observation,first_step_id)
        poses=self._geometry.pose_summary(observation)
        content=[{'type':'input_text','text':json.dumps(dict(task=prompt,robot=self.robot_id,
            poses=poses,tracked_points=points,tracking=self.tracker.summary(),
            tool_geometry_reference=self._tool_geometry_reference,nominal_tool_pose=nominal_tool_pose(poses,self._tool_geometry_reference),
            calibration_quality=self._calibration_warnings,grounding_camera=self.grounding_camera,waypoint_cursor=first_step_id),allow_nan=False)}]
        self._vision_frames=[]
        for name in ('top','left','right'):
            frame=frames[name];self._vision_frames.append(frame.summary())
            mime='image/png' if frame.jpeg.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if frame.jpeg.startswith(b'\xff\xd8') else None
            if mime is None:raise RuntimeError('Unsupported camera image encoding')
            label='SELECT METRIC POINTS HERE; normalized coordinates 0..1000' if name==self.grounding_camera else 'RGB context only; do not select metric points here'
            content.extend([{'type':'input_text','text':f'{name} camera; {label}'},
                {'type':'input_image','image_url':'data:'+mime+';base64,'+base64.b64encode(frame.jpeg).decode(),'detail':'high'}])
        return {'role':'user','content':content}

    def build_trajectory(self,prompt,observation,first_step_id):
        self.last_step_model_s=0.
        if self._pending is not None:raise RuntimeError('Wait for matched measured packet completion')
        if self._outcome is not None:raise PolicyComplete(self._outcome['status'])
        identity=(observation.get('episode_id'),observation.get('lease_id'))
        if not self._history:
            self._prompt=prompt;self._episode=identity
            self._history=[{'role':'system','content':self._system_prompt}]
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
            if name=='decision_rejected':
                self._tool_result(call['call_id'],args)
                self._failures+=1
                if self._failures>=3:raise RuntimeError('Three local input rejections; stop and review')
                observation=self._refresh_feedback(observation,first_step_id)
                continue
            if name in ('done','give_up'):
                self._outcome={'status':name,**args};self._tool_result(call['call_id'],self._outcome)
                raise PolicyComplete(name)
            try:
                registrations=args.pop('registrations',None)
                if registrations is not None:
                    if name!='track_object':raise InputRejected('Batch inspection is read-only')
                    self.tracker.register_many(registrations)
                registration=args.pop('register',None)
                if registration is not None:self.tracker.register(args['point_ids'][0],**registration)
                observation=self._refresh_feedback(observation,first_step_id)
                metric=name in ('track_object','touch','align_line','plane_parallel')
                _,observation,measured_points=self._fresh_view(observation,first_step_id,metric=metric)
                if name=='track_object':
                    result={'ok':True,'tracking':self.tracker.summary(),'points':measured_points}
                    self._tool_result(call['call_id'],result)
                    continue
                # Resolve only newly tracked pixels and measured post-capture
                # feedback under the same lease/cursor; never retime a sample.
                if self.steering.pending():
                    self._tool_result(call['call_id'],{'ok':False,'error':'New run-owner guidance superseded this unsent decision'})
                    continue
                command={'kind':name,**args}
                points=self._geometry.build(command,observation,first_step_id,points=measured_points)
                self._pending={'call_id':call['call_id'],'waypoint_count':len(points),'last_step_id':points[-1]['step_id']}
                self._record('joint_packet',command=command,waypoints=points,tracking=self.tracker.summary())
                self._interaction('packet_ready',f'Validated {name}: {len(points)} waypoints at 10 Hz',command=command)
                return points
            except InputRejected as exc:
                self._tool_result(call['call_id'],{'ok':False,'stage':'local_validation','error':str(exc),'steps':0,'dispatched':False})
                self._failures+=1
                if self._failures>=3:raise RuntimeError('Three local input rejections; stop and review') from exc
                observation=self._refresh_feedback(observation,first_step_id)
        raise RuntimeError('RoboHarness model call budget exhausted')

    def trajectory_completed(self,observation,waypoint_count):
        pending=self._pending
        if (pending is None or waypoint_count!=pending['waypoint_count']
                or observation.get('step_id')!=pending['last_step_id']+1
                or tuple(observation.get(k) for k in ('episode_id','lease_id'))!=self._episode):
            raise RuntimeError('Measured completion does not match the pending RoboHarness packet')
        self._geometry.confirm_completed_trajectory(observation,
            first_step_id=pending['last_step_id']+1-waypoint_count,waypoint_count=waypoint_count)
        return super().trajectory_completed(observation,waypoint_count)

    def trajectory_failed(self,*args,**kwargs):
        # Even a settled-timeout recovery in the generic policy must not replay
        # a movement here. The explicit harness timeout rule takes precedence.
        raise RuntimeError('RoboHarness motion failed or timed out; stop and review, no automatic retry')

    def measured_step_displacement(self,start,end):
        import numpy as np
        # Controller path/elapsed telemetry also uses historical samples and
        # planned waypoints. FK must not establish or mutate motion authority.
        ik=self._geometry.ik
        def positions(sample):
            q=np.deg2rad(np.concatenate([vector(sample.get(arm+'_joints_deg'),6,arm+' telemetry joints') for arm in ('left','right')]))
            if np.any(q<ik.low) or np.any(q>ik.high):raise InputRejected('Telemetry joints outside calibrated limits')
            ik._forward(q)
            return [position.copy() for position,_ in ik._poses()]
        a=positions(start);b=positions(end)
        return {arm+'_displacement_m':float(np.linalg.norm(b[i]-a[i])) for i,arm in enumerate(('left','right'))}
