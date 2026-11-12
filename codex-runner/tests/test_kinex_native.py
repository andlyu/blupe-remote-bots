"""Native Kinex MCP -> JSONL driver -> bridge -> controller -> wire validator.

All feedback is explicitly synthetic; the only network listener is loopback.
The real HttpSessionAPI serializer terminates at a wire spy, never hardware.
"""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from remote_yam.controller import RunnerController
from remote_yam.kinex_policy import KinexAdapter, KinexAPI, RUNTIME
from remote_yam.session import HttpSessionAPI
from test_kinex import observation


@unittest.skipUnless(os.environ.get('KINEX_SOURCE'), 'Required native release gate supplies KINEX_SOURCE')
class NativeCommandContract(unittest.TestCase):
    def test_native_tools_and_complete_packet_path(self):
        with tempfile.TemporaryDirectory(prefix='kinex-native-contract-') as directory:
            base=HttpSessionAPI('https://offline.invalid',supports_trajectories=True)
            base._session_capabilities['offline']='offline-only-capability'
            api=KinexAPI(base,'Offline fixture','fixture@example.test');api.session_id='offline'
            feedback=observation();feedback['episode_id']='ep_offline'
            base.get_session=lambda *a,**k:dict(dict(status='running',episode_id='ep_offline',lease_id='lease_offline'),**active_case.get('session_patch',{}))
            base.get_robot_observation=lambda *a,**k:deepcopy(feedback)
            stopped=[];base.stop_session=lambda *a,**k:(stopped.append(True) or {'status':'stopped'})
            stream=io.BytesIO();Image.new('RGB',(4,3),(28,45,62)).save(stream,format='JPEG')
            from types import SimpleNamespace
            cameras=SimpleNamespace(capture=lambda _: [SimpleNamespace(name=n,jpeg=stream.getvalue(),received_at=time.time()) for n in ('top','left','right')])
            policy=KinexAdapter(os.environ['KINEX_SOURCE'],directory,api,cameras)
            policy._thread=object();policy._lease='lease_offline';policy._latest=deepcopy(feedback)
            controller=RunnerController(api,share_conversation=False)
            controller._status='running';controller._provider=policy
            controller._session_id='offline';controller._episode_id='ep_offline';controller._lease_id='lease_offline'
            policy._start_bridge()
            self.addCleanup(policy._server.server_close);self.addCleanup(policy._server.shutdown)
            sent=[];failures=[];active_case={};finish=threading.Event()
            def wire(request,**kwargs):
                self.assertTrue(request.full_url.startswith('https://offline.invalid/v1/sessions/offline/'))
                packet=json.loads(request.data);points=packet['waypoints']
                arguments=active_case['arguments'];device=arguments.get('deviceID',arguments.get('device'))
                side=device.split('_')[0];other='right' if side=='left' else 'left'
                target=arguments.get('joints') if active_case.get('tool')=='servo' else arguments['args']['actions'][-1]
                self.assertEqual([p['step_id'] for p in points],list(range(len(points))))
                previous=deepcopy(feedback)
                for point in points:
                    self.assertEqual(point[other+'_joints_deg'],feedback[other+'_joints_deg'])
                    self.assertEqual(point[other+'_gripper'],feedback[other+'_gripper'])
                    for arm in ('left','right'):
                        self.assertTrue(np.isfinite(point[arm+'_joints_deg']).all())
                        self.assertLessEqual(np.max(np.abs(np.deg2rad(np.array(point[arm+'_joints_deg'])-previous[arm+'_joints_deg']))),.035+1e-10)
                        self.assertTrue(0<=point[arm+'_gripper']<=1)
                        self.assertLessEqual(abs(point[arm+'_gripper']-previous[arm+'_gripper']),.1+1e-10)
                    previous=point
                if device.endswith('_gripper'):
                    self.assertEqual(points[-1][side+'_gripper'],target)
                    self.assertEqual(points[-1][side+'_joints_deg'],feedback[side+'_joints_deg'])
                else:
                    np.testing.assert_allclose(np.deg2rad(points[-1][side+'_joints_deg']),target,rtol=0,atol=1e-14)
                    self.assertEqual(points[-1][side+'_gripper'],feedback[side+'_gripper'])
                sent.append(packet)
                receipt=dict(schema_version=1,accepted=True,duplicate=False,session_id='offline',episode_id='ep_offline',lease_id='lease_offline',trajectory_id=packet['trajectory_id'],first_step_id=points[0]['step_id'],last_step_id=points[-1]['step_id'],waypoint_count=len(points),dispatched_at=time.time())
                return io.BytesIO(json.dumps(receipt).encode())
            def dispatch():
                while not finish.is_set():
                    if policy._queue.empty():time.sleep(.002);continue
                    try:
                        controller._dispatch_trajectory(policy.build_trajectory,policy,'Synthetic offline fixture',deepcopy(feedback),'offline','ep_offline','lease_offline',0)
                        target=deepcopy(sent[-1]['waypoints'][-1]);feedback.update(target,observed_at=time.time())
                        policy.trajectory_completed(deepcopy(feedback),len(sent[-1]['waypoints']))
                        controller._trajectory=None
                    except Exception as exc:failures.append(repr(exc));policy.request_stop();break
            # Separate fixture controls only exist in this test, outside the real bridge.
            # Native requests still use the production authenticated bridge handler.
            class Fixture(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_POST(handler):
                    try:
                        self.assertEqual(handler.headers.get('Authorization'),'Bearer '+policy._token)
                        data=json.loads(handler.rfile.read(int(handler.headers['Content-Length'])))
                        deadline=time.monotonic()+2
                        while (policy._active or policy._pending) and time.monotonic()<deadline:time.sleep(.002)
                        if data.get('observation'):
                            feedback.clear();feedback.update(data['observation'],observed_at=time.time()-data.get('age_s',0))
                            active_case.clear();active_case.update(data)
                        result={'dispatches':len(sent),'errors':failures}
                        body=json.dumps(result).encode();handler.send_response(200);handler.end_headers();handler.wfile.write(body)
                    except Exception:handler.send_error(500)
            fixture=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
            self.addCleanup(fixture.server_close);self.addCleanup(fixture.shutdown)
            threading.Thread(target=fixture.serve_forever,daemon=True).start()
            # Node fixture calls use a distinct loopback port; drivers use the actual bridge.
            env=dict(os.environ,BLUPE_KINEX_PYTHON=sys.executable,BLUPE_KINEX_BRIDGE='http://127.0.0.1:'+str(policy._server.server_port),BLUPE_KINEX_TOKEN=policy._token,KINEX_FIXTURE='http://127.0.0.1:'+str(fixture.server_port))
            config=dict(directory=directory,limits=policy.packets.limits,cameras={n:dict(width=4,height=3) for n in ('top','left','right')})
            setup=subprocess.run(['node',str(RUNTIME/'workspace.mjs')],input=json.dumps(config),text=True,capture_output=True,env=env,timeout=30)
            self.assertEqual(setup.returncode,0,setup.stderr)
            # Use the already installed interpreter; avoid network/setup in the gate.
            python_dir=Path(directory)/'.kinex/python';python_dir.mkdir(parents=True,exist_ok=True)
            (python_dir/'.venv').symlink_to(sys.prefix,target_is_directory=True)
            forward=geometry_forward=policy.packets.geometry._forward
            def with_contact_fault(q):
                forward(q)
                if active_case.get('inject_contact'):policy.packets.geometry.data.ncon=1
            policy.packets.geometry._forward=with_contact_fault
            cases=[]
            def case(label,args,obs=None,**extra):cases.append(dict(label=label,arguments=args,observation=deepcopy(obs or feedback),**extra))
            for device in ('left_arm','right_arm','left_gripper','right_gripper','top_camera','left_camera','right_camera','world'):
                case('read '+device,dict(deviceID=device,action='read'))
            for camera in ('top','left','right'):
                case('camera file '+camera,dict(deviceID=camera+'_camera',action='read',args={'output':'file'}),image=True)
            case('world wait',dict(deviceID='world',action='wait',args={'duration_s':.01}))
            case('concurrent reads',dict(calls=[dict(deviceID=n,action='read') for n in ('left_arm','right_arm')]),tool='devices')
            for side in ('left','right'):
                device=side+'_gripper'
                for value in (0.,1.,.37,1e-15,1-1e-15):case(f'{device} target {value}',dict(deviceID=device,action='write',args=dict(actions=[value],duration_s=1)),writes=1)
                for value in (-1e-16,1+1e-15,-1,2,True,None,'0'):
                    case(f'{device} rejects {value}',dict(deviceID=device,action='write',args=dict(actions=[value],duration_s=1)),reject=True)
                target=np.deg2rad(feedback[side+'_joints_deg']).tolist();target[-1]+=.03
                case('servo '+side,dict(device=side+'_arm',joints=target,block=False),tool='servo',writes=1)
                case('Cartesian unsupported '+side,dict(device=side+'_arm',pose=[0,0,.2,0,0,0,1],block=False),tool='servo',reject=True)
                case('malformed joints '+side,dict(deviceID=side+'_arm',action='write',args=dict(actions=[[1,2]],duration_s=1)),reject=True)
            # Every joint's legal endpoints and adjacent in/out-of-range values.
            # Find contact-free synthetic configurations; the real geometry check stays on.
            rng=np.random.default_rng(7051);geometry=policy.packets.geometry
            for side in ('left','right'):
                offset=0 if side=='left' else 6
                for joint in range(6):
                    for bound,direction in ((geometry.low[offset+joint],1),(geometry.high[offset+joint],-1)):
                        for attempt in range(1000):
                            q=np.deg2rad(feedback['left_joints_deg']+feedback['right_joints_deg']) if attempt==0 else rng.uniform(geometry.low+.001,geometry.high-.001)
                            q[offset+joint]=bound+direction*.0001
                            geometry._forward(q)
                            if geometry.data.ncon:continue
                            goal=q.copy();goal[offset+joint]=bound;geometry._forward(goal)
                            if not geometry.data.ncon:break
                        else:self.fail('No contact-free endpoint fixture found')
                        obs=deepcopy(feedback);obs.update(left_joints_deg=np.rad2deg(q[:6]).tolist(),right_joints_deg=np.rad2deg(q[6:]).tolist())
                        for delta in (0,direction*1e-12,-direction*1e-10):
                            target=q[offset:offset+6].tolist();target[joint]=bound+delta
                            case(f'{side} joint {joint+1} bound {bound} delta {delta}',dict(deviceID=side+'_arm',action='write',args=dict(actions=[target],duration_s=.1)),obs=obs,writes=0 if delta*direction<0 else 1,reject=delta*direction<0)
            for changed in ({'safety':{'ok':False}},{'settled':False},{'homed':False},{'source':'simulation'},{'jetson_id':'other'}):
                case('unsafe feedback '+str(changed),dict(deviceID='left_gripper',action='write',args=dict(actions=[0],duration_s=1)),obs=dict(feedback,**changed),reject=True)
            case('stale feedback',dict(deviceID='left_gripper',action='write',args=dict(actions=[0],duration_s=1)),age_s=3,reject=True)
            case('injected contact rejection',dict(deviceID='left_gripper',action='write',args=dict(actions=[.37],duration_s=1)),inject_contact=True,reject=True)
            case('changed lease' ,dict(deviceID='left_gripper',action='write',args=dict(actions=[0],duration_s=1)),session_patch={'lease_id':'lease_other'},reject=True)
            case('native Stop' ,dict(deviceID='left_arm'),tool='device_stop')
            plan=Path(directory)/'cases.json';plan.write_text(json.dumps(cases))
            with patch('remote_yam.session.request.urlopen',side_effect=wire):
                thread=threading.Thread(target=dispatch,daemon=True);thread.start()
                try:result=subprocess.run(['node',str(RUNTIME/'native-contract.mjs'),directory,str(plan)],env=env,text=True,capture_output=True,timeout=100)
                finally:finish.set();thread.join(3)
            self.assertEqual(failures,[])
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(len(sent),sum(c.get('writes',0) for c in cases))
            self.assertTrue(stopped)
            print('Native MCP/driver/controller contract:',result.stdout.strip())
