"""Authentic Kinex MCP/Codex tools behind the existing BluPe trajectory controller.

Native Kinex joint/gripper buffers are serialized at the gateway's fixed 10 Hz.
One buffer owns the gateway at a time; superseding and Cartesian goals are not
advertised. No model-generated shell or unrestricted Python is exposed.
"""
from copy import deepcopy
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import math
import os
from pathlib import Path
import queue
import secrets
import signal
import subprocess
import sys
import threading
import time

import numpy as np
from PIL import Image

from .mujoco_ik import BimanualRelativeIK
from .providers import PolicyComplete
from .session import MAX_COMMANDS, MAX_WAYPOINTS_PER_PACKET, _trajectory_waypoints, SessionAPIError

RUNTIME = Path(__file__).resolve().parents[2] / 'integrations/kinex/runtime'
YAM1_JOINT_LIMITS = json.loads((RUNTIME/'yam1-limits.json').read_text())


def finite(value, name, lo=-math.inf, hi=math.inf):
    if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f'{name} must be finite and in [{lo}, {hi}]; nothing dispatched')
    return float(value)


class KinexPackets:
    def __init__(self):
        self.geometry = BimanualRelativeIK(base_spacing_m=.50)
        self.geometry.low = np.maximum(self.geometry.low, YAM1_JOINT_LIMITS['lower_rad'])
        self.geometry.high = np.minimum(self.geometry.high, YAM1_JOINT_LIMITS['upper_rad'])
        self.limits = {'lower_rad':self.geometry.low.tolist(),'upper_rad':self.geometry.high.tolist()}

    def build(self, device, args, observation, step):
        if device not in ('left_arm','right_arm','left_gripper','right_gripper'):
            raise ValueError('Unsupported actuator')
        if not isinstance(args,dict) or set(args) != {'actions','duration_s'}:
            raise ValueError('Actuation requires only actions and duration_s')
        if (observation.get('source') != 'hardware' or observation.get('settled') is not True
                or observation.get('homed') is not True or observation.get('safety',{}).get('ok') is not True
                or observation.get('jetson_id',observation.get('robot_id')) != 'yam-1'
                or not 0 <= time.time()-finite(observation.get('observed_at'),'feedback timestamp') <= 2):
            raise ValueError('Fresh, homed, settled YAM1 feedback with safety OK is required')
        duration = finite(args['duration_s'],'duration_s',.1,6)
        count = math.ceil(duration*10)
        if count > MAX_WAYPOINTS_PER_PACKET or step+count > MAX_COMMANDS:
            raise ValueError('Packet/session budget exceeded')
        side = device.split('_')[0]; index = 0 if side == 'left' else 6
        joint = device.endswith('_arm')
        actions = args['actions']
        if not isinstance(actions,list) or not 1 <= len(actions) <= 600:
            raise ValueError('actions must contain 1..600 samples')
        q0 = np.deg2rad(observation['left_joints_deg']+observation['right_joints_deg'])
        if q0.shape != (12,) or not np.isfinite(q0).all() or np.any(q0 < self.geometry.low) or np.any(q0 > self.geometry.high):
            raise ValueError('Measured joints outside calibrated bounds')
        grips = {arm:finite(observation.get(arm+'_gripper'),arm+' gripper',0,1) for arm in ('left','right')}
        if joint:
            values = []
            for row in actions:
                if not isinstance(row,list) or len(row) != 6:raise ValueError('Joint samples require six absolute radians')
                values.append([finite(v,'joint',self.geometry.low[index+i],self.geometry.high[index+i]) for i,v in enumerate(row)])
            start = q0[index:index+6].tolist()
        else:
            values = [finite(v,'gripper fraction',0,1) for v in actions]; start = grips[side]
        # Validate the original samples as well as the resampled wire path.
        previous = np.asarray(start)
        for value in values:
            if np.max(np.abs(np.asarray(value)-previous)) > (.35 if joint else 1.0)*duration/len(values)+1e-10:
                raise ValueError('Requested sample velocity exceeds existing limits')
            previous = np.asarray(value)
        samples = [start]+values
        points=[]; previous=q0.copy(); previous_grip=grips[side]
        for i in range(1,count+1):
            location = i/count*len(values)
            lower=min(int(location),len(values)-1); fraction=location-lower
            target = np.asarray(values[-1]).copy() if i==count else np.asarray(samples[lower])+(np.asarray(samples[lower+1])-np.asarray(samples[lower]))*fraction
            q=q0.copy(); point={'step_id':step+i-1}
            if joint:q[index:index+6]=target
            if np.max(np.abs(q-previous)) > .035+1e-10:raise ValueError('Generated joint pacing exceeds 0.35 rad/s')
            self.geometry._forward(q)
            if self.geometry.data.ncon:raise ValueError('Predictive model contact rejected the buffer')
            for arm in ('left','right'):
                offset=0 if arm=='left' else 6
                point[arm+'_joints_deg'] = np.rad2deg(q[offset:offset+6]).tolist() if joint and arm==side else deepcopy(observation[arm+'_joints_deg'])
                point[arm+'_gripper'] = float(target) if not joint and arm==side else grips[arm]
            if not joint and abs(point[side+'_gripper']-previous_grip) > .1+1e-10:raise ValueError('Generated gripper pacing exceeds existing limit')
            previous_grip=point[side+'_gripper']; previous=q;points.append(point)
        return _trajectory_waypoints(points)


class KinexAPI:
    """Identity-preserving API facade and dispatch acknowledgement hook."""
    def __init__(self, api, name, email):
        self.api=api;self.name=name;self.email=email;self.policy=None;self.session_id=None

    def __getattr__(self,name):return getattr(self.api,name)

    def create_session(self,prompt,run_duration_s=300):
        # Keep attribution even on shared client revisions predating identity kwargs.
        import websocket  # Validate the control transport before queue admission.
        result=self.api._request('POST','/v1/sessions',dict(schema_version=1,robot_id='yam-1',prompt=prompt,run_duration_s=run_duration_s,runner_name=self.name,email=self.email,model='Kinex'))
        capability=result.get('session_capability');self.session_id=result.get('session_id')
        if not self.session_id or not isinstance(capability,str) or not capability:raise RuntimeError('Session creation omitted its capability')
        self.api._session_capabilities[self.session_id]=capability
        return result

    def submit_trajectory(self,session_id,episode_id,lease_id,trajectory_id,cadence_hz,waypoints):
        if self.policy._stop.is_set() or self.policy.cancelled():
            raise SessionAPIError('Kinex cancelled before dispatch',code='kinex_cancelled')
        receipt=self.api.submit_trajectory(session_id,episode_id,lease_id,trajectory_id,cadence_hz,waypoints)
        keys={'schema_version','accepted','duplicate','session_id','episode_id','lease_id','trajectory_id',
              'first_step_id','last_step_id','waypoint_count','dispatched_at'}
        if (not isinstance(receipt,dict) or set(receipt)!=keys or receipt.get('schema_version')!=1
                or receipt.get('accepted') is not True or type(receipt.get('duplicate')) is not bool
                or receipt.get('session_id')!=session_id or receipt.get('episode_id')!=episode_id
                or receipt.get('lease_id')!=lease_id or receipt.get('trajectory_id')!=trajectory_id
                or receipt.get('first_step_id')!=waypoints[0]['step_id']
                or receipt.get('last_step_id')!=waypoints[-1]['step_id']
                or receipt.get('waypoint_count')!=len(waypoints)
                or type(receipt.get('dispatched_at')) not in (int,float)
                or not math.isfinite(receipt['dispatched_at'])):
            # Dispatch may have occurred. SessionAPIError prevents controller replay.
            raise SessionAPIError('Kinex dispatch acknowledgement mismatch; execution outcome unknown; stop without replay',code='kinex_ack_mismatch')
        self.policy.accepted(receipt)
        return receipt


class KinexAdapter:
    provider_name='kinex'
    supports_runtime_steering=False
    last_step_model_s=0

    def __init__(self,upstream,workspace,api,cameras,model='gpt-6-astra',evidence_root=None):
        self.model=model;self.upstream=Path(upstream).resolve();self.workspace=Path(workspace).resolve()
        self.api=api;api.policy=self;self.cameras=cameras;self.packets=KinexPackets()
        self.cancelled=lambda:False;self.interaction_sink=None
        self._queue=queue.Queue();self._pending=None;self._active=False;self._latest=None
        self._process=None;self._thread=None;self._error=None;self._done=False
        self._stop=threading.Event();self._lock=threading.RLock();self._token=secrets.token_urlsafe(32)
        self._calls=0;self._server=None;self._bridge_thread=None;self._events=[]
        self._stop_error=None;self._finished_normally=False;self._target=None
        self.directory=Path(evidence_root) if evidence_root else self.workspace/'evidence';self.directory.mkdir(parents=True,exist_ok=True)

    def public_config(self):
        return dict(provider='kinex',model='Kinex',display_name='Kinex',policy='kinex_native_device_tools',
            underlying_models={'planning':self.model,'vision':self.model,'resolved':None,'reasoning_effort':'low'},
            host='Codex 0.162.1 + official Kinex MCP/core 1.0.0',model_calls=self._calls,
            recording_path=str(self.directory),capabilities=['joint servo','normalized grippers','RGB cameras','measured feedback'],
            exclusions=['Cartesian goals','unrestricted Python','arbitrary shell','simultaneous/superseding actuator buffers'],
            runner_name=getattr(self,'runner_name',None),execution_mode=getattr(self,'execution_mode','interactive'),
            kinex_upstream_revision='f68a8d7f1ddcae2b096f171b817c232d8730f3ec',
            agent_finished=self._finished_normally,task_success='unverified',stop_error=self._stop_error)

    def emit(self,kind,message,**details):
        if callable(self.interaction_sink):self.interaction_sink(kind,message,**details)

    def _read(self):
        if self._stop.is_set() or self.cancelled():raise RuntimeError('Kinex cancelled')
        session=self.api.get_session(self.api.session_id)
        if (session.get('status')!='running' or session.get('episode_id')!=self._latest.get('episode_id')
                or session.get('lease_id')!=self._lease):raise RuntimeError('Robot lease changed; stopping Kinex')
        result=self.api.get_robot_observation('yam-1')
        obs=result.get('observation') or result.get('payload') or result
        if (obs.get('jetson_id',obs.get('robot_id'))!='yam-1' or obs.get('source')!='hardware'
                or not 0<=time.time()-finite(obs.get('observed_at'),'feedback time')<=2
                or obs.get('safety',{}).get('ok') is not True):raise RuntimeError('Fresh safe robot feedback unavailable')
        return obs

    def _device(self,data):
        name,action,args=data['device'],data['action'],data.get('args',{})
        if action=='stop':
            self.request_stop(strict=True,terminate_agent=False);return {'ok':True}
        obs=self._read()
        side=name.split('_')[0]
        if name.endswith('_camera'):
            if action!='read':raise ValueError('Camera supports read only')
            frames=self.cameras.capture(obs);frame=next(f for f in frames if f.name==side)
            image=Image.open(io.BytesIO(frame.jpeg)).convert('RGB');stream=io.BytesIO();image.save(stream,format='PNG')
            return {'ok':True,'timestamp':frame.received_at,'width':image.width,'height':image.height,'color':base64.b64encode(stream.getvalue()).decode()}
        state=({'positions':np.deg2rad(obs[side+'_joints_deg']).tolist(),'velocities':[],'efforts':[],'faults':[],'timestamp':obs['observed_at']}
               if name.endswith('_arm') else {'aperture_m':None,'faults':[],'timestamp':obs['observed_at']})
        if action=='read':return {'ok':True,**state}
        if action!='write':raise ValueError('Unsupported device action')
        with self._lock:
            if self._active or self._pending:raise ValueError('A buffer owns the gateway. Wait for measured completion; superseding is unsupported.')
            item={'device':name,'args':args,'event':threading.Event(),'state':state,'result':None,'error':None}
            # Validate before enqueue, then again against controller planning feedback.
            self.packets.build(name,args,obs,0)
            self._pending=item;self._queue.put(item)
        deadline=time.monotonic()+15
        while not item['event'].wait(.05):
            if self._stop.is_set() or self.cancelled() or time.monotonic()>deadline:
                self.request_stop();raise RuntimeError('Dispatch acknowledgement unavailable; stopping, never replaying')
        if item['error']:raise RuntimeError(item['error'])
        return item['result']

    def accepted(self,receipt):
        with self._lock:
            item=self._pending
            if self._stop.is_set() or self.cancelled():raise SessionAPIError('Kinex stopped before acknowledgement; no success reported',code='kinex_cancelled')
            if item is None:raise SessionAPIError('Unexpected Kinex dispatch acknowledgement',code='kinex_ack_mismatch')
            self._active=True
            item['result']={'ok':True,'execution_id':receipt['trajectory_id'],'state':item['state']}
            item['event'].set()

    def trajectory_completed(self,observation,waypoint_count):
        self.validate_trajectory_final(observation)
        with self._lock:self._latest=deepcopy(observation);self._active=False;self._pending=None
        self.emit('kinex_feedback','Kinex buffer completed with measured robot feedback',waypoints=waypoint_count)

    def validate_trajectory_final(self,observation):
        if self._target is None:raise RuntimeError('No Kinex final target is recorded')
        if observation.get('settled') is not True or observation.get('source')!='hardware':
            raise RuntimeError('Kinex final feedback must be settled hardware')
        for arm in ('left','right'):
            values=observation.get(arm+'_joints_deg')
            if not isinstance(values,(list,tuple)) or len(values)!=6:raise RuntimeError('Missing final joint feedback')
            for actual,target in zip(values,self._target[arm+'_joints_deg']):
                if abs(finite(actual,'final joint')-target)>math.degrees(.05):raise RuntimeError('Kinex final joint target was not reached')
            # Additional conservative normalized-position check, not grasp proof.
            if abs(finite(observation.get(arm+'_gripper'),'measured gripper',0,1)-self._target[arm+'_gripper'])>.02:
                raise RuntimeError('Kinex final gripper target was not reached (0.02 fraction tolerance)')

    def trajectory_failed(self,*args,**kwargs):
        self._error='Physical trajectory did not complete; automatic retry is disabled';self.request_stop()

    def build_trajectory(self,prompt,observation,first_step_id):
        self._latest=deepcopy(observation)
        if self._thread is None:
            self._lease=self.api.get_session(self.api.session_id).get('lease_id')
            self._thread=threading.Thread(target=self._agent,args=(prompt,),daemon=True);self._thread.start()
        while not self.cancelled() and not self._stop.is_set():
            if self._error:raise RuntimeError(self._error)
            try:item=self._queue.get(timeout=.1)
            except queue.Empty:
                if self._done:raise PolicyComplete('Kinex agent finished')
                continue
            try:
                obs=self._read()
                points=self.packets.build(item['device'],item['args'],obs,first_step_id)
                if self._stop.is_set() or self.cancelled():raise RuntimeError('Kinex cancelled before buffer dispatch')
                self._target=deepcopy(points[-1])
                self.emit('kinex_command','Kinex requested a validated device buffer',device=item['device'],waypoints=len(points))
                return points
            except Exception as exc:
                with self._lock:self._pending=None
                item['error']=str(exc);item['event'].set()
        raise RuntimeError(self._error or 'Kinex stopped')

    def _agent(self,prompt):
        try:self._run_agent(prompt)
        except Exception as exc:self._error=str(exc);self.emit('model_error',self._error)
        finally:self._done=True

    def _run_agent(self,prompt):
        if self._stop.is_set() or self.cancelled():raise RuntimeError('Kinex cancelled before startup')
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                if not secrets.compare_digest(self.headers.get('Authorization',''),'Bearer '+owner._token):
                    self.send_error(403);return
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=200000:raise ValueError('Invalid bridge request size')
                    result=owner._device(json.loads(self.rfile.read(size)))
                except Exception as exc:result={'error':str(exc)}
                body=json.dumps(result,allow_nan=False).encode();self.send_response(200)
                self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        self._server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self._bridge_thread=threading.Thread(target=self._server.serve_forever,daemon=True);self._bridge_thread.start()
        env=dict(os.environ,KINEX_SOURCE=str(self.upstream),BLUPE_KINEX_PYTHON=sys.executable,BLUPE_KINEX_BRIDGE='http://127.0.0.1:'+str(self._server.server_port),BLUPE_KINEX_TOKEN=self._token)
        for key in ('OPENAI_API_KEY','ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN'):env.pop(key,None)
        frames=self.cameras.capture(self._read());sizes={}
        for frame in frames:
            image=Image.open(io.BytesIO(frame.jpeg));sizes[frame.name]={'width':image.width,'height':image.height}
        setup={'directory':str(self.workspace),'limits':self.packets.limits,'cameras':sizes}
        self.emit('kinex_startup','Preparing Kinex device profiles and loading the robotics runtime')
        subprocess.run(['node',str(RUNTIME/'workspace.mjs')],input=json.dumps(setup),text=True,env=env,check=True,capture_output=True,timeout=30)
        binary=self.upstream/'node_modules/.bin/codex'
        command=[str(binary),'exec','--ignore-user-config','--skip-git-repo-check','--json','--model',self.model,'--sandbox','read-only','-C',str(self.workspace)]
        settings={'forced_login_method':'chatgpt','model_provider':'openai','model_reasoning_effort':'low','approval_policy':'on-request',
            'web_search':'disabled','features.shell_tool':False,'features.apps':False,'features.multi_agent':False,'features.hooks':False,
            'mcp_servers.kinex.command':'node','mcp_servers.kinex.args':[str(RUNTIME/'mcp.mjs')],
            'mcp_servers.kinex.env_vars':['KINEX_SOURCE','BLUPE_KINEX_PYTHON','BLUPE_KINEX_BRIDGE','BLUPE_KINEX_TOKEN'],
            'mcp_servers.kinex.required':True,'mcp_servers.kinex.startup_timeout_sec':30,
            'mcp_servers.kinex.tool_timeout_sec':60,'mcp_servers.kinex.default_tools_approval_mode':'approve'}
        for key,value in settings.items():command+=['-c',key+'='+json.dumps(value)]
        command+=['-']
        instructions=('Use the official Kinex MCP tools for this physical YAM1 task. First explicitly call kinex_start, '
            'then inspect Kinex context and schemas. Use only the registered device, devices, servo and device_stop tools. '
            'Arms have six absolute joints in radians; grippers use fractions 0 closed to 1 open. '
            'Cartesian kinematics and arbitrary Python are unavailable in this initial integration. '
            'Use measured camera images and joint feedback. Keep motions small, within all declared limits, '
            'and verify measured completion before another actuator write. Never retry a timed-out/uncertain motion. '
            'When another buffer is active, read feedback and wait with the world device. '
            'Finish with an honest task result; do not stop the gateway just to finish normally.\nTask: '+prompt)
        self.emit('model_request','Starting Astra with Kinex tools through the Codex subscription',model=self.model)
        with (self.directory/'codex-events.jsonl').open('w') as log,(self.directory/'codex-stderr.log').open('w') as errors:
            self._spawn(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True,env=env,start_new_session=True)
            self._process.stdin.write(instructions);self._process.stdin.close()
            for line in self._process.stdout:
                log.write(line);log.flush()
                try:event=json.loads(line)
                except ValueError:continue
                item=event.get('item') or {}
                if event.get('type')=='turn.started':self._calls+=1
                if event.get('type') in ('item.started','item.completed') and item.get('type')=='mcp_tool_call':
                    self.emit('kinex_tool',str(item.get('tool') or 'Kinex tool'),status=item.get('status'),server=item.get('server'))
                elif item.get('type')=='agent_message' and item.get('text'):
                    self.emit('model_response',item['text'][:6000])
                elif event.get('type') in ('error','turn.failed'):
                    self._error='Codex/Kinex model request failed; inspect the private runtime log'
            code=self._process.wait()
            self._finished_normally=code==0 and not self._stop.is_set() and self._error is None
            if code and not self._stop.is_set():raise RuntimeError('Kinex agent exited with code '+str(code)+'; no automatic fallback or retry')

    def _spawn(self,command,**kwargs):
        with self._lock:
            if self._stop.is_set() or self.cancelled():raise RuntimeError('Kinex cancelled before model spawn')
            self._process=subprocess.Popen(command,**kwargs)
            return self._process

    def request_stop(self,*,strict=False,terminate_agent=True):
        self._stop.set()
        with self._lock:
            if self._pending:self._pending['error']='Stopped';self._pending['event'].set()
            process=self._process
        error=None
        if self.api.session_id:
            try:
                result=self.api.stop_session(self.api.session_id,reason='user_requested')
                if result.get('status') not in ('stopped','completed','timed_out','failed','cancelled'):
                    raise RuntimeError('Gateway did not acknowledge a terminal stop state')
            except Exception as exc:
                error=RuntimeError('stop_failed: Gateway stop acknowledgement unavailable ('+type(exc).__name__+')')
                self._stop_error=str(error);self.emit('stop_failed',self._stop_error)
        if terminate_agent and process and process.poll() is None:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
        if strict and error:raise error

    def close_transport(self):
        self.request_stop()
        process=self._process
        if process:
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait(timeout=5)
        if self._server:self._server.shutdown();self._server.server_close()
        if self._stop_error:raise RuntimeError(self._stop_error)
