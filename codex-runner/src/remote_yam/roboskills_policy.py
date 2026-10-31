"""RoboSkills' Python agent loop with measured BluPe tools.

The upstream agent runs Python in a persistent REPL. This adapter replaces the
simulator tools with BluPe cameras and checked Cartesian packet generation.
RunnerController alone owns queue admission, leases, dispatch and Stop.
"""
from copy import deepcopy
import base64
import hashlib
import io
import json
from pathlib import Path
from queue import Empty
import threading
import time

import numpy as np

from .codex_policy import codex_environment
from .program_packet_bridge import ProgramPacketBridge
from .providers import PolicyComplete, ResponsesAdapter
from .robocurve_policy import CallRecorder, RoboCurveResponsesAdapter
from .robocurve_trajectory import NAMES, RoboCurveTrajectory
from .roboskills_perception import RoboSkillsPerception
from .session import _trajectory_waypoints

REVISION = '8a2860234768b4bec981994d1c14fa380a2c8c7f'
APPROACH = 'RoboSkills'


def _tracking_offset(history, axes):
    """Bounded false-position step when completed feedback brackets an axis.

    Full residual accumulation can oscillate across actuator deadband. Retain
    the measured bracket rather than integrating through it again. This is
    command planning after confirmed completion, never dispatch reconciliation.
    """
    current,error=history[-1]
    result=current.copy()
    for j in axes:
        candidate=current[j]-error[j]
        opposite=[(offset[j],residual[j]) for offset,residual in history[:-1]
                  if residual[j]*error[j]<0 and abs(offset[j]-current[j])>1e-9]
        if opposite:
            old_offset,old_error=min(opposite,key=lambda value:abs(value[0]-current[j]))
            candidate=(current[j]*old_error-old_offset*error[j])/(old_error-error[j])
        result[j]=np.clip(candidate,-.008,.008)
    return result

PROMPT = """You control physical bimanual YAM arms through a BluPe adapter to
RoboSkills' persistent Python agent loop. Return exactly one fenced python block
per turn. The external REPL executes it with write access; your model transport
has no tools and its read-only sandbox does not restrict this external REPL.
The parent host already maintains the required three-step timing record for
this task. This nested source-generation call is part of that measured task,
not a new task: do not create another timing file. Use bot, np, show and finish.
The initial receipt already contains fresh measured status and camera images.
Use those observations without capturing them again before the first move.
Return a short Python program, without prose or custom verification functions.
Chain dependent actions in one turn when their measured checks allow it.
move_to already checks measured Cartesian accuracy (3 mm), latches any failed
move, using bounded measured-feedback tracking corrections after confirmed completion.
For a lift/hold/return, save the starting coordinates, move, wait, move back,
then finish. Do not duplicate the tool's verification code.

{api}

The initial receipt includes the actual camera images; inspect them before
manipulating objects. bot.status() gives the latest measured per-arm coordinates
in metres and rotations in radians, grippers 0 closed to 1 open. Dimensions are
left_x/y/z/yaw/pitch/roll/gripper and right_x/y/z/yaw/pitch/roll/gripper.
Use bot.move_to(left_z=..., right_z=..., ...) for coordinated changes. Omitted
dimensions hold their current values. Each move is resolved by the existing
BluPe IK, workspace, pacing, gateway and measured completion checks. A rejected
move sends nothing; correct the stated cause. Never replay simulation joints.
Inspect measured feedback after movement. A camera is an observation, not proof
of a grasp. Do not invent object locations or success. finish() ends the agent
episode, without claiming a native physical success score. If the object or
required capability is absent, explain it and finish. A failed/uncertain physical
move is terminal; do not retry it. Respect Stop and the run duration.

Metric perception is supplied when status.perception.available is true. Every
camera RGB is paired pixel-for-pixel with measured optical-Z depth. Use
bot.measure_depth(u,v,camera='top') for a visible object's interior pixel; it
returns points_base_m for both arms in the SAME per-arm frames as move_to.
Each point is a LIST [x,y,z], not a dict: use
px,py,pz = measurement['points_base_m']['right'] (integer indexing also works).
The points_base_m mapping ALWAYS exists, even with arm='right' or arm='left';
then it contains just that arm. Missing/noisy depth raises a descriptive error,
not None. A single-arm call also has point_base_m as a convenience alias.
For the first approach, a measured interior pixel is sufficient; prefer the
short pixel-query program over a separate segmentation/printing-only turn.
Assign source/destination measurements to variables and use the returned
coordinates for an above-object approach in the SAME first Python block. Keep
that first program to about4–8 lines: measure source and destination, unpack the
selected source point, move above it, then show a fresh observation. move_to
already validates bounds/IK/packets; do not duplicate bounds checks, nested
result checks or custom safety functions. Missing measurements/local rejection
raise descriptive exceptions before dispatch for you to resolve. Do not spend
turns printing raw tool dictionaries to learn their values; Python already has
those values. If required measurements are unavailable,
explain that result instead of inventing a point. For object extent/centroid use
bot.rgbd(camera)['rgb'] to compute a boolean mask
in Python and bot.localize_object(label,mask,camera). These are real depth
measurements, not guessed positions or simulator ground truth. You may measure
and approach in the same Python turn. status.bounds documents the validated envelope.
Surface points are not grasp targets: account for visible object height, finger
clearance, the grasp frame and surrounding objects. Do not close on a surface
point. Calibration quality is experimental; use visual feedback and reobserve
after movement. The cached view is invalidated by every move; query observe()
again when measuring a new state. Wrist poses use measured settled FK and camera
mounts. The left/right cameras MOVE WITH THEIR ARMS: perspective and pixel
locations change after an arm move even when the block stays still. Normal
occlusion or uncertain object position is a perception problem: use a fresh
view, another camera and measured pixels to resolve it. It is not an uncertain
motion outcome. Only a rejected/failed/unknown physical dispatch or completion
is terminal without retry. Do not infer object displacement from moving-camera
pixels alone. If a block is still visible in a wrist view, measure it there
instead of ending just because the overhead view is occluded.
Retain the stated calibration limitations, without claiming exact depth
accuracy. Verify object retention after lifting, support before release and
stable placement after withdrawing. Finish with finish(reason='what happened',
task_success=True/False/None). task_success is your visual assessment, not a
native score; use None if unverified. Explain missing objects or failed grasps.
"""


class RobotTools:
    def __init__(self, policy, instruction):
        self.policy, self.instruction = policy, instruction
        self.result = None
        self.motion_failure = None

    def status(self):
        """Measured state, current step, task, allowed target bounds and Stop."""
        p = self.policy
        p._check_cancelled()
        # The controller installs correlated measured feedback. Reading status
        # must not perform another network fetch on every print in a Python turn.
        _, state, _ = p._geometry.observe(p._state)
        return dict(instruction=self.instruction, step=p._state['step_id'],
                    coordinates=dict(zip(NAMES, state.tolist())),
                    bounds={n:[float(p._geometry.low[i]),float(p._geometry.high[i])]
                            for i,n in enumerate(NAMES)}, ended=self.result is not None,
                    perception=p._perception.summary(concise=True) if p._perception else dict(available=False))

    def observe(self):
        """Current RGB camera images as {camera: uint8 RGB}; call show(result)."""
        from PIL import Image
        p = self.policy
        p._check_cancelled()
        if p._perception:
            p._vision_state='capturing'
            images=p._perception.capture(p)
            p._vision_state='observed'
            return images
        content = p._observation_input(p._state)[0]['content']
        images, name = {}, 'camera'
        for item in content:
            if item['type']=='input_text' and item['text'].startswith('Camera view:'):
                name=item['text'].split(': ',1)[1].split('.',1)[0]
            elif item['type']=='input_image':
                data=base64.b64decode(item['image_url'].split(',',1)[1])
                images[name]=np.asarray(Image.open(io.BytesIO(data)).convert('RGB'))
        return images

    def rgbd(self, camera='top'):
        """Cached paired rgb/depth_m arrays, calibration and measured camera poses. No new capture."""
        self.policy._check_cancelled()
        if not self.policy._perception:raise ValueError('Metric perception is not configured')
        return self.policy._perception.rgbd(self.policy._state,camera)

    def measure_depth(self, u, v, camera='top', radius=2, arm=None):
        """Pixel -> points_base_m mapping arm names to [x,y,z] metre lists. ALWAYS that shape; arm optionally selects its only entry. Missing depth raises ValueError."""
        self.policy._check_cancelled()
        if not self.policy._perception:raise ValueError('Metric perception is not configured')
        result=self.policy._perception.measure(self.policy._state,u,v,camera,radius,arm)
        self.policy._record('depth_query',result=result)
        return result

    def localize_object(self, label, mask, camera='top', arm=None):
        """Ground an agent-selected boolean RGB mask in measured depth; visible surface centroid/extents only."""
        self.policy._check_cancelled()
        if not self.policy._perception:raise ValueError('Metric perception is not configured')
        result=self.policy._perception.localize(self.policy._state,label,mask,camera,arm)
        self.policy._record('object_localization',result=result)
        return result

    def move_to(self, **targets):
        """Checked coordinated Cartesian move; returns measured completion."""
        p=self.policy
        p._check_cancelled()
        if self.motion_failure:
            raise RuntimeError(self.motion_failure)
        state=p._feedback()
        points=p._prepare_move(targets,state)
        _, expected, _ = p._geometry.observe({**state,**points[-1],'settled':True})
        offset=np.zeros_like(expected)
        pose_arms=[arm for arm,i in (('left',0),('right',7)) if any(n in targets for n in NAMES[i:i+6])]
        axes=[j for arm,i in (('left',0),('right',7)) if arm in pose_arms for j in range(i,i+3)]
        history=[]
        for correction in range(4):
            p._interaction('packet_ready',f'RoboSkills prepared {len(points)} checked waypoints',
                           waypoint_count=len(points),targets=targets,tracking_correction=correction)
            try:
                if p._perception:p._perception.invalidate()
                measured=p._execute(points)
                p._completed_moves+=1
            except Exception as exc:
                # No second dispatch after any rejected, failed or uncertain
                # packet. A correction requires matched measured completion.
                self.motion_failure='Physical move failed or became uncertain: '+str(exc)
                self.result=dict(status='failed',success=None,reason=self.motion_failure)
                raise
            p._state=deepcopy(measured)
            _, actual, _ = p._geometry.observe(measured)
            errors={arm:float(np.linalg.norm(actual[i:i+3]-expected[i:i+3]))
                    for arm,i in (('left',0),('right',7))}
            p._last_move=dict(targets=targets,position_error_m=errors,
                              tracking_corrections=correction,
                              pose_target_arms=pose_arms,
                              measured_coordinates=dict(zip(NAMES,actual.tolist())))
            if all(errors[arm] <= .003 for arm in pose_arms):
                return self.status()
            history.append((offset.copy(),actual-expected))
            if correction==3:break
            # Outer position feedback compensates bounded static tracking
            # residuals. Do not alter motor gains, limits, or gateway settle criteria.
            # Each Cartesian axis stays within8mm of the original goal and
            # still passes the existing IK/workspace/pacing checks.
            offset=_tracking_offset(history,axes)
            corrected=dict(targets)
            for i in (0,7):
                if not any(n in targets for n in NAMES[i:i+6]):continue
                for j in range(i,i+3):
                    corrected[NAMES[j]]=float(np.clip(expected[j]+offset[j],
                                                       p._geometry.low[j],p._geometry.high[j]))
                    offset[j]=corrected[NAMES[j]]-expected[j]
            try:
                state=p._feedback()
                points=p._prepare_move(corrected,state)
            except Exception as exc:
                self.motion_failure='Tracking correction was not safe to prepare: '+str(exc)
                self.result=dict(status='failed',success=None,reason=self.motion_failure)
                raise
            p._interaction('tracking_correction','Correcting a measured tracking residual after confirmed completion',
                           correction=correction+1,position_error_m=errors,max_offset_m=.008,
                           command_offset_m={NAMES[j]:float(offset[j]) for j in axes},
                           maximum_packets=4)
        self.motion_failure=('Measured move did not reach its target within3mm after bounded tracking correction: '+
            ', '.join(f'{arm} {error*1000:.2f}mm' for arm,error in errors.items()))
        self.result=dict(status='failed',success=None,reason=self.motion_failure)
        raise RuntimeError(self.motion_failure)

    def wait(self, seconds):
        """Wait up to five seconds, while retaining Stop responsiveness."""
        if type(seconds) not in (int,float) or not 0<=seconds<=5:
            raise ValueError('Wait must be between zero and five seconds')
        self.policy._wait(seconds)

    def finish(self, reason='', task_success=None):
        """End with an explanation and optional visual task assessment; no native physical score."""
        if not isinstance(reason,str) or len(reason)>1500:
            raise ValueError('Finish reason must be text up to1500 characters')
        if task_success is not None and type(task_success) is not bool:
            raise ValueError('task_success must be True, False or None')
        if self.result is None:
            moved=self.policy._completed_moves>0
            self.result=dict(status='done',success=None,
                task_status=('reported_success' if task_success else 'reported_failure')
                            if task_success is not None else 'unverified' if moved else 'not_attempted',
                task_success_reported=task_success,assessment_source='agent_visual_report_unscored',
                completed_moves=self.policy._completed_moves,
                reason=reason.strip() or ('Agent ended; task result was not verified.' if moved
                                         else 'Agent ended without submitting task motion.'))
        return self.result


class RoboSkillsPolicy(ProgramPacketBridge, ResponsesAdapter):
    provider_name='roboskills'
    supports_runtime_steering=False

    def __init__(self, *, camera_source, recording_root, inference_model='gpt-6-sol', llm=None):
        try:
            import roboskills.core.agent
        except ImportError as exc:
            raise RuntimeError('Install requirements-roboskills.txt before joining the robot queue') from exc
        # Reuse geometry and transport components, without inheriting another
        # policy's function-call lifecycle or speculative Home behavior.
        super().__init__('local-subscription',APPROACH,'https://api.openai.com/v1/responses',
                         camera_source=camera_source)
        self._geometry=RoboCurveTrajectory(preserve_uninstructed=True)
        self._workspace_profile=None
        self._recorder=CallRecorder(recording_root)
        self._calls=0
        self._outcome=None
        self.refresh_observation=None
        self.interaction_sink=None
        self.inference_model=inference_model
        self._llm=llm
        self._init_packet_bridge()
        self._state=None
        self._identity=None
        self._finished=False
        self._last_move=None
        self.last_step_model_s=0.
        self._perception=None
        self._completed_moves=0
        self._local_rejection=None

    def configure_robot_workspace(self,robot_id,*,report=None):
        from .controller_workspace import workspace_for_robot
        if self._thread is not None:raise ValueError('Bind the station before starting the agent')
        profile=workspace_for_robot(robot_id)
        if profile and report is not None:profile.validate_report(report)
        if self._perception:
            report=self._perception.report
            if report['robot_id']!=robot_id:raise ValueError('Perception station mismatch')
            if profile:profile.validate_report(report)
        geometry=profile.rgb_geometry_kwargs() if profile else {}
        if report is not None and self._perception:
            geometry['base_spacing_m']=report['base_geometry']['spacing_m']
        self._geometry=RoboCurveTrajectory(**geometry,preserve_uninstructed=True)
        if profile:profile.configure_geometry(self._geometry)
        self._workspace_profile=profile

    def configure_perception(self, source, report):
        """Pin validated station calibration before queue admission and the first model call."""
        if self._thread is not None:raise ValueError('Bind perception before starting the agent')
        self._perception=RoboSkillsPerception(source,report)
        self.configure_robot_workspace(report['robot_id'],report=report)

    def _interaction(self,kind,message,**details):
        if self.interaction_sink:self.interaction_sink(kind,message,call=self._calls,**details)

    def _record(self,kind,**details):
        self._recorder.write(kind,**details)

    def _prepare_move(self,targets,state):
        try:
            # Same complete canonical serializer/validator as HttpSessionAPI,
            # before the bridge can hand anything to RunnerController.
            points=_trajectory_waypoints(self._geometry.build(targets,state,state['step_id']))
        except ValueError as exc:
            reason='Local command rejected before dispatch: '+str(exc)
            self._local_rejection=dict(reason=reason,dispatched=False)
            self._interaction('local_packet_rejected',reason,dispatched=False)
            self._record('local_packet_rejected',reason=reason,dispatched=False)
            raise ValueError(reason) from exc
        self._local_rejection=None
        return points

    def measured_step_displacement(self,start,end):
        return RoboCurveResponsesAdapter.measured_step_displacement(self,start,end)

    def trajectory_adjusted(self,details):
        if (not self._pending or details.get('workspace_recovery')!='adjusted'
                or type(details.get('changed_waypoints')) is not int
                or not 1<=details['changed_waypoints']<=self._pending['waypoint_count']):
            raise RuntimeError('Workspace replacement does not match the pending RoboSkills packet')
        self._pending['workspace_recovery']=deepcopy(details)
        self._interaction('workspace_recovery','BluPe adjusted the requested target; inspect measured completion.',feedback=details)

    def public_config(self):
        return {**ResponsesAdapter.public_config(self), 'model':APPROACH,
                'api_key_configured':False,'authentication':'local ChatGPT subscription',
                'policy':'roboskills_python_agent','model_calls':self._calls,
                'outcome':self._outcome,'pending_packet':deepcopy(self._pending),
                'last_move':deepcopy(self._last_move),
                'local_rejection':deepcopy(self._local_rejection),
                'perception':self._perception.summary() if self._perception else dict(available=False),
                'system_prompt_sha256':hashlib.sha256(PROMPT.encode()).hexdigest(),
                'recording_path':str(self._recorder.path) if self._recorder else None,
                **({'controller_workspace':self._workspace_profile.summary()} if self._workspace_profile else {}),
                'display_name':'RoboSkills · Python agent',
                'inference_model':self.inference_model, 'upstream_revision':REVISION,
                'workflow':'core.agent.run with BluPe physical tools',
                'execution':'physical', 'native_success_score':False}

    def _feedback(self):
        self._check_cancelled()
        state=deepcopy(self._state)
        if callable(self.refresh_observation):
            state=self.refresh_observation()
        if tuple(state.get(k) for k in ('episode_id','lease_id'))!=self._identity:
            raise RuntimeError('RoboSkills feedback changed episode or lease')
        if state.get('source')!='hardware' or state.get('settled') is not True:
            raise RuntimeError('RoboSkills requires measured settled hardware feedback')
        if state.get('step_id')!=self._state['step_id']:
            raise RuntimeError('Feedback changed the command cursor')
        self._state=deepcopy(state)
        return state

    def _call(self, system, messages):
        from roboskills.core import llm
        self._check_cancelled()
        self._calls+=1
        self._vision_state='requesting'
        self._interaction('model_request','RoboSkills is choosing its next Python action',
                          model=APPROACH,inference_model=self.inference_model)
        started=time.monotonic()
        fn=self._llm or (lambda s,m:llm.codex(s,m,model=self.inference_model,
                            effort='low',timeout=180,env=codex_environment()))
        reply=fn(system,messages)
        elapsed=time.monotonic()-started
        self.last_step_model_s+=elapsed
        self._interaction('model_timing','RoboSkills Python decision received',elapsed_s=elapsed)
        self._check_cancelled()
        self._vision_state='response_received'
        self._interaction('model_response',reply[:8000],model=APPROACH)
        return reply

    def _run_agent(self,prompt):
        tools=RobotTools(self,prompt)
        try:
            from roboskills.core import agent
            repl=agent.Repl(tools,tools)
            directory=self._recorder.path/'roboskills'
            done,turns=agent.run(repl,prompt,directory,self._call,max_turns=32,max_bad=3,
                prompt=PROMPT,initial_code='show(bot.observe()); print(bot.status())',
                context=('Full published calibration quality (not an accuracy certificate): '+
                         json.dumps(self._perception.report['quality'])) if self._perception else '',
                status_code='print(bot.status())')
            self._outcome={**(tools.result or dict(status='give_up',success=None,
                            reason='Agent turn budget ended')), 'turns':turns}
        except Exception as exc:
            self._outcome=dict(status='give_up',success=None,reason=type(exc).__name__+': '+str(exc))
        finally:
            self._vision_state='finished'
            self._record('roboskills_finished',outcome=self._outcome,upstream_revision=REVISION)
            self._finished=True

    def build_trajectory(self,prompt,observation,first_step_id):
        self._check_cancelled()
        identity=tuple(observation.get(k) for k in ('episode_id','lease_id'))
        if self._identity is None:self._identity=identity
        if identity!=self._identity or observation.get('source')!='hardware' or observation.get('settled') is not True:
            raise RuntimeError('RoboSkills needs the same measured hardware lease')
        if observation.get('step_id')!=first_step_id or self._pending is not None:
            raise RuntimeError('Wait for matched measured completion')
        self.last_step_model_s=0.
        self._state=deepcopy(observation)
        if self._completed is not None:
            if observation['step_id']!=self._completed['step_id']:
                raise RuntimeError('Measured completion cursor changed')
            self._replies.put_nowait(deepcopy(observation));self._completed=None
        if self._thread is None:
            self._thread=threading.Thread(target=self._run_agent,args=(prompt,),daemon=True)
            self._thread.start()
        while True:
            self._check_cancelled()
            if self._finished and self._packets.empty():raise PolicyComplete(self._outcome['status'])
            try:points=self._packets.get(timeout=.05)
            except Empty:continue
            self._check_cancelled()
            if not points or points[0]['step_id']!=first_step_id:
                raise RuntimeError('RoboSkills packet changed its command cursor')
            self._pending=dict(waypoint_count=len(points),last_step_id=points[-1]['step_id'])
            self._record('joint_packet',waypoints=points,approach=APPROACH)
            return points

    def request_stop(self):
        self._failure='RoboSkills stopped by the runner'

    close_transport=request_stop

    def trajectory_failed(self,*args,**kwargs):
        self._failure='Physical execution failed or became uncertain; no automatic retry'
