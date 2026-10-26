"""Hardware-shaped fake API; no real station writes in this suite."""
import importlib.util
import json
import math
from copy import deepcopy
from pathlib import Path
import threading
import time
import tempfile
import unittest
from unittest.mock import patch
from urllib import request, error

import numpy as np
from remote_yam.path_studio_policy import PathStudioPolicy, STATIONS, validate_sketch
from remote_yam.path_studio_service import PathStudioService, StudioSessionAPI, IdentifiedSessionAPI, validate_identity
from remote_yam.session import MockSessionAPI
from remote_yam.controller import RunnerController
from remote_yam.providers import PolicyComplete
from remote_yam.path_studio_geometry import DrawingGeometry
from remote_yam.path_studio_simulation import simulate_sketch, REFERENCE_JOINTS_RAD

ROOT = Path(__file__).resolve().parents[1]
HOME = np.rad2deg([-.024,.794,.645,-.375,-.021,-.012]*2).reshape(2,6)


def report(robot):
    from remote_yam.controller_workspace import workspace_for_robot, YAM1_CALIBRATION
    from remote_yam.mujoco_ik import ROBOT_SHA256
    w = workspace_for_robot(robot)
    return dict(robot_id=robot, base_geometry=dict(spacing_m=.5 if robot=='yam-1' else .62),
        native_joint_calibration=dict(calibration_id=YAM1_CALIBRATION,coordinate_convention='native_i2rt_updated') if robot=='yam-1' else None,
        model_joint_calibration=None if robot=='yam-1' else dict(calibration_id=w.calibration_id,
            coordinate_convention='original_i2rt_model_corrected',canonical_model_sha256=ROBOT_SHA256,
            offsets_rad=dict(left=list(w.joint_offsets_rad[:6]),right=list(w.joint_offsets_rad[6:]))))


def observation(robot='yam-1'):
    return dict(jetson_id=robot,source='hardware',mode='API_ACTIVE',observed_at=time.time(),
                homed=True,settled=True,safety=dict(ok=True,estop_engaged=False,contact_count=0),
                left_joints_deg=HOME[0].tolist(),right_joints_deg=HOME[1].tolist(),left_gripper=.5,right_gripper=.5)


class HardwareAPI(MockSessionAPI):
    def __init__(self, robot='yam-1', auto_activate=True, reject=False):
        self.robot=robot;self.measured=observation(robot);self.reject=reject
        super().__init__(observations=[self.measured],auto_activate=auto_activate)
    def _request(self, method, path):
        assert method=='GET'
        return report(self.robot)
    def get_robot_observation(self, robot):
        assert robot==self.robot
        return {**self.measured,'observed_at':time.time()}
    def get_session(self, sid):
        result=super().get_session(sid);r=self._sessions[sid]
        return {**result,'lease_id':r['lease_id'],'latest_observation_step':r['next_command_step'],'active_trajectory':r['active_trajectory']}
    def _event(self, record, kind, payload):
        payload=deepcopy(dict(payload))
        if kind=='observation':
            payload.update(jetson_id=self.robot,source='hardware')
            if payload.get('step_id',0)>0:
                # Real gateways use homed as startup state, not a persistent
                # readiness flag after the first completed packet.
                payload['homed']=False
            self.measured.update(payload)
        super()._event(record,kind,payload)
    def submit_trajectory(self, *args, **kwargs):
        if self.reject:
            raise RuntimeError('Gateway rejected test packet')
        return super().submit_trajectory(*args,**kwargs)


def sketch(robot='yam-1', assignment='left'):
    # Reachable 4 cm stroke near the measured rest pose.
    from remote_yam.mujoco_ik import BimanualRelativeIK
    from remote_yam.controller_workspace import workspace_for_robot
    ik=BimanualRelativeIK(base_spacing_m=.5 if robot=='yam-1' else .62,
        joint_offsets_rad=workspace_for_robot(robot).joint_offsets_rad)
    ik._forward(np.deg2rad(HOME.reshape(12)));p=ik._poses()[0][0].copy()
    return dict(station='yam-1' if robot=='yam-1' else 'robohouse',assignment=assignment,
                coordination='sequential',frame='yam_common',units='m',speed_m_s=.025,points=[p.tolist(),(p+[0,0,.04]).tolist()])


def wait_for(fn, seconds=4):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        result=fn()
        if result:return result
        time.sleep(.01)
    raise AssertionError('Timed out waiting for fake API')


class PlannerTests(unittest.TestCase):
    def test_measured_pose_miss_cannot_advance_drawing(self):
        p=PathStudioPolicy(sketch());a=HardwareAPI();p.validate_session_admission(a)
        o=observation();close=p.build_trajectory('',o,0);o['left_gripper']=0.
        p.trajectory_completed(o,len(close));o['homed']=False
        points=p.build_trajectory('',o,len(close))
        missed={**o,**points[-1]};missed['left_joints_deg']=missed['left_joints_deg'][:]
        missed['left_joints_deg'][0]+=10
        with self.assertRaisesRegex(ValueError,'Measured tool pose missed'):
            p.trajectory_completed(missed,len(points))
        self.assertEqual(p.cursor,0)
    def test_whole_path_and_pacing_on_both_calibrations(self):
        for robot in STATIONS.values():
            a=HardwareAPI(robot);p=PathStudioPolicy(sketch(robot));p.validate_session_admission(a)
            obs=a.get_robot_observation(robot);r=p.build_trajectory('',obs,0)
            self.assertGreater(p.preflight_points,1);self.assertEqual(p.cursor,0)
            for point in r:
                np.testing.assert_allclose(point['left_joints_deg'],HOME[0],atol=1e-12)
                self.assertNotIn('right_gripper',point)
            self.assertEqual(r[-1]['left_gripper'],0.)
            closed={**obs,'left_gripper':0.}
            p.trajectory_completed(closed,len(r))
            step=len(r);closed['homed']=False
            while p.cursor<len(p.targets):
                r=p.build_trajectory('',closed,step)
                q=np.array([closed['left_joints_deg']+closed['right_joints_deg']]+[x['left_joints_deg']+x['right_joints_deg'] for x in r])
                self.assertLessEqual(np.max(abs(np.diff(np.deg2rad(q),axis=0))),.03500001)
                for point in r:
                    np.testing.assert_allclose(point['right_joints_deg'],HOME[1],atol=1e-12)
                    self.assertEqual(point['left_gripper'],0.)
                    self.assertNotIn('right_gripper',point)
                step+=len(r);closed.update(r[-1],observed_at=time.time())
                p.trajectory_completed(closed,len(r))
            self.assertEqual(p.cursor,len(p.targets))
            with self.assertRaises(PolicyComplete):p.build_trajectory('',obs,len(r))
    def test_unconfirmed_gripper_closure_cannot_start_drawing(self):
        p=PathStudioPolicy(sketch());a=HardwareAPI();p.validate_session_admission(a)
        close=p.build_trajectory('',observation(),0)
        self.assertEqual(p.phase,'closing_grippers')
        self.assertEqual(p.cursor,0)
        self.assertTrue(all(p.step_phases[x['step_id']]=={} for x in close))
        with self.assertRaisesRegex(ValueError,'closure was not confirmed'):
            p.trajectory_completed(observation(),len(close))
        self.assertFalse(p.grippers_closed)
    def test_trace_phases_exclude_approach_and_retraction(self):
        p=PathStudioPolicy(sketch('yam-1','both'));a=HardwareAPI();p.validate_session_admission(a)
        _,_,poses=p._measured(observation())
        p._make_targets(poses)
        phases=[next(iter(x.values())) for x in p.target_phases]
        self.assertIn('approach',phases);self.assertIn('draw',phases);self.assertIn('retract',phases)
    def test_bad_station_stale_state_and_bounds_never_plan(self):
        p=PathStudioPolicy(sketch());a=HardwareAPI();p.validate_session_admission(a)
        for changes in [dict(jetson_id='other'),dict(source='simulation'),dict(observed_at=time.time()-20),dict(settled=False),dict(homed=False),dict(mode='DISABLED')]:
            with self.assertRaises(ValueError):p.build_trajectory('',{**observation(),**changes},0)
        bad=sketch();bad['points'][1]=[.8,.8,.8]
        with self.assertRaises(ValueError):PathStudioPolicy(bad).validate_session_admission(a)
    def test_invalid_requests(self):
        for changes in [dict(speed_m_s=True),dict(speed_m_s=float('nan')),dict(points=[[0,0,0],[0,float('inf'),0]]),dict(points=[[0,0,0]]),dict(station='other'),dict(frame='unknown')]:
            with self.assertRaises(ValueError):validate_sketch({**sketch(),**changes})
    def test_cancel_preflight(self):
        p=PathStudioPolicy(sketch());p.validate_session_admission(HardwareAPI());p.cancelled=lambda:True
        with self.assertRaisesRegex(RuntimeError,'cancelled'):p.build_trajectory('',observation(),0)


class ExecutionTests(unittest.TestCase):
    def make_service(self, **kwargs):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        api=HardwareAPI(**kwargs);service=PathStudioService(api_factory=lambda robot:api,poll_s=.05,identity_path=Path(directory.name)/'identity.json')
        service.identity=dict(runner_name='Andrew',email='andrew@example.test')
        self.addCleanup(service.close)
        return service,api
    def test_read_only_monitor_then_confirmed_execution(self):
        service,api=self.make_service()
        wait_for(lambda:service.status('yam-1')['observation'])
        self.assertEqual(api.create_requests,[])
        service.run(sketch());wait_for(lambda:service.status('yam-1')['run']['status']=='stopped')
        run=service.status('yam-1')['run'];self.assertIsNone(run['error']);self.assertEqual(run['progress']['phase'],'complete')
        self.assertGreater(run['run_metrics']['confirmed_waypoints'],1)
        self.assertEqual(len(api.create_requests),1)
        self.assertEqual(api.create_requests[0]['runner_name'],'Andrew')
        self.assertEqual(api.create_requests[0]['email'],'andrew@example.test')
        self.assertNotIn('email_run_video',api.create_requests[0])
        self.assertNotIn('session_capability',json.dumps(service.status('yam-1')))
    def test_simultaneous_heart_uses_shared_api_packets_and_measured_completion(self):
        for robot in STATIONS.values():
            service,api=self.make_service(robot=robot)
            data=ConstrainedSimulationTests().heart(robot);data['coordination']='together'
            expected=simulate_sketch(data,report(robot))
            # Match the same fully open reference baseline for exact packet parity.
            api.measured.update(left_gripper=1.,right_gripper=1.)
            service.run(data)
            wait_for(lambda:service.status(data['station'])['run']['status']=='stopped',seconds=20)
            run=service.status(data['station'])['run'];self.assertIsNone(run['error'])
            self.assertEqual(run['progress']['phase'],'complete')
            self.assertEqual(run['progress']['coordination'],'together')
            points=[p for packet in api.trajectory_log for p in packet['waypoints']]
            self.assertEqual(len(points),len(expected['frames'])-1)
            for point,frame in zip(points,expected['frames'][1:]):
                for side in ('left','right'):
                    np.testing.assert_allclose(point[side+'_joints_deg'],frame[side+'_joints_deg'],atol=1e-12)
            self.assertGreater(run['progress']['min_gripper_clearance_m'],.05)
    def test_entire_bimanual_heart_on_both_stations(self):
        for robot in STATIONS.values():
            service,api=self.make_service(robot=robot)
            data=sketch(robot,'both')
            data['speed_m_s']=.05
            data['points']=[[.34,.12*math.sin(t)**3,.31+.0075*(13*math.cos(t)-5*math.cos(2*t)-2*math.cos(3*t)-math.cos(4*t))]
                            for t in np.linspace(0,2*math.pi,97)]
            data['points'][-1]=data['points'][0].copy()
            service.run(data)
            wait_for(lambda:service.status(data['station'])['run']['status']=='stopped',seconds=20)
            run=service.status(data['station'])['run']
            self.assertIsNone(run['error']);self.assertEqual(run['progress']['phase'],'complete')
            self.assertGreater(len(api.trajectory_log),2)
            ids=[p['step_id'] for packet in api.trajectory_log for p in packet['waypoints']]
            self.assertEqual(ids,list(range(len(ids))))
            self.assertEqual(run['run_metrics']['confirmed_waypoints'],len(ids))
            self.assertFalse(api.measured['homed'])
            self.assertEqual(run['progress']['confirmed_draw_samples'],run['progress']['planned_draw_samples'])
            self.assertGreater(run['progress']['confirmed_draw_samples'],96)
            self.assertLess(run['progress']['max_tcp_error_m'],.003)
            self.assertGreater(run['progress']['geometry_samples_checked'],len(ids))
            # Independent FK of every drawing command must follow the actual
            # heart outline, not merely reach its final point.
            policy=service.policy
            for packet in api.trajectory_log:
                for point in packet['waypoints']:
                    phases=policy.step_phases[point['step_id']]
                    q=np.deg2rad(point['left_joints_deg']+point['right_joints_deg'])
                    policy.ik._forward(q)
                    for index,side in enumerate(('left','right')):
                        if phases.get(side)!='draw':continue
                        position,rotation=policy.ik._poses()[index]
                        path=policy.active[side];a,b=path[:-1],path[1:];d=b-a
                        den=np.sum(d*d,axis=1);t=np.clip(np.sum((position-a)*d,axis=1)/np.maximum(den,1e-20),0,1)
                        error=np.linalg.norm(position-(a+t[:,None]*d),axis=1).min()
                        self.assertLess(error,.001)
                        np.testing.assert_allclose(rotation[:,2],[1,0,0],atol=.0001)
                        if side=='right':np.testing.assert_allclose(rotation[:,1],[0,0,1],atol=.0001)
            # At shared endpoints, the other tool is back at its measured start.
            for target in service.policy.targets:
                self.assertGreater(np.linalg.norm(target[0]-target[1]),.05)
    def test_workspace_replacement_stops_the_drawing(self):
        policy=PathStudioPolicy(sketch())
        with self.assertRaisesRegex(RuntimeError,'adjusted'):
            policy.trajectory_adjusted({'workspace_recovery':'adjusted'})
        self.assertEqual(policy.cursor,0)
    def test_no_overlap_and_queue_stop(self):
        service,api=self.make_service(auto_activate=False)
        service.run(sketch());wait_for(lambda:service.status('yam-1')['run']['status']=='queued')
        with self.assertRaises(ValueError):service.run(sketch())
        service.stop();self.assertEqual(service.status('yam-1')['run']['status'],'stopped')
        self.assertEqual(api.trajectory_log,[])
    def test_rejection_does_not_advance_path(self):
        service,api=self.make_service(reject=True)
        service.run(sketch());wait_for(lambda:service.status('yam-1')['run']['status']=='stopped')
        run=service.status('yam-1')['run'];self.assertIn('rejected',run['error'])
        self.assertEqual(run['progress']['confirmed_samples'],0)
    def test_cancel_during_event_handshake_stops_new_session(self):
        api=HardwareAPI(auto_activate=False);entered=threading.Event();release=threading.Event()
        original=api.open_events
        def open_events(sid):
            entered.set();release.wait(2);return original(sid)
        api.open_events=open_events;c=RunnerController(api,robot_id='yam-1',share_conversation=False)
        p=PathStudioPolicy(sketch());c.join_and_run(p,'test');self.assertTrue(entered.wait(2))
        c.stop();release.set();c._worker.join(2)
        self.assertEqual(api.state(next(iter(api._sessions)))['status'],'stopped')
        self.assertEqual(api.trajectory_log,[])
    def test_stop_failure_is_retained(self):
        api=StudioSessionAPI('http://unused');api._session_capabilities['test']='secret'
        with patch.object(api,'_request',side_effect=ConnectionError('offline')):
            with self.assertRaises(ConnectionError):api.stop_session('test')
        self.assertTrue(api.stop_unconfirmed)
        self.assertEqual(api.stop_session_id,'test')
    def test_event_connection_failure_cancels_created_session(self):
        api=HardwareAPI(auto_activate=False)
        api.open_events=lambda sid: (_ for _ in ()).throw(ConnectionError('test handshake failure'))
        c=RunnerController(api,robot_id='yam-1',share_conversation=False)
        c.join_and_run(PathStudioPolicy(sketch()),'test');c._worker.join(2)
        self.assertEqual(api.state(next(iter(api._sessions)))['status'],'stopped')
        self.assertEqual(api.trajectory_log,[])


class HTTPTests(unittest.TestCase):
    def test_queue_identity_survives_session_creation(self):
        api=HardwareAPI(auto_activate=False)
        wrapped=IdentifiedSessionAPI(api,dict(runner_name='Andrew',email='andrew@example.test'))
        wrapped.create_session('draw a heart')
        self.assertEqual(api.create_requests[0]['runner_name'],'Andrew')
        self.assertEqual(api.create_requests[0]['email'],'andrew@example.test')
        for bad in ({'runner_name':3,'email':'bad'},{'runner_name':'','email':'a@b.c'},{'runner_name':'Andrew','email':'bad'}):
            with self.assertRaises(ValueError):validate_identity(bad)
    def test_observer_camera_and_fixed_stream_proxy(self):
        from unittest.mock import MagicMock
        service=PathStudioService()
        response=MagicMock();response.__enter__.return_value=response
        response.headers.get_content_type.return_value='image/jpeg';response.read.return_value=b'jpeg'
        with patch('remote_yam.path_studio_service.request.urlopen',return_value=response) as read:
            self.assertEqual(service.camera('robohouse','observer'),b'jpeg')
            self.assertTrue(read.call_args.args[0].endswith('/cameras/observer.jpg'))
        response.headers.get_content_type.return_value='application/vnd.apple.mpegurl'
        with patch('remote_yam.path_studio_service.request.urlopen',return_value=response) as read:
            service.video('robo-house/index.m3u8','session=public-viewer')
            req=read.call_args.args[0]
            self.assertEqual(req.full_url,'https://playground.blupe.io/robo-house/index.m3u8?session=public-viewer')
            self.assertIsNone(req.get_header('Authorization'));self.assertIsNone(req.get_header('Cookie'))
        for path in ('../secret','robo-house/../../secret','https://evil.example/x','robo-house/x.json'):
            with self.assertRaises(ValueError):service.video(path,'')
    def test_local_origin_token_and_static_allowlist(self):
        spec=importlib.util.spec_from_file_location('path_studio_server',ROOT/'path_studio.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        service=PathStudioService(api_factory=lambda robot:HardwareAPI(robot),poll_s=.05)
        service.identity=dict(runner_name='Andrew',email='andrew@example.test')
        server=module.create_server(0,service);threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown);self.addCleanup(service.close)
        base=f'http://127.0.0.1:{server.server_port}'
        with request.urlopen(base+'/api/path-studio/config') as r:token=json.load(r)['csrf_token']
        def post(headers, route='run'):
            return request.urlopen(request.Request(base+'/api/path-studio/'+route,data=json.dumps(sketch()).encode(),headers={'Content-Type':'application/json',**headers}))
        with post({'X-Path-Studio-Token':token,'Origin':base},'simulate') as r:
            self.assertTrue(json.load(r)['verification']['passed'])
        self.assertIsNone(service.controller)  # simulation did not acquire control
        for headers in [{},{'X-Path-Studio-Token':token,'Origin':'https://evil.example'},{'X-Path-Studio-Token':token,'Host':'evil.example'}]:
            with self.assertRaises(error.HTTPError) as e:post(headers)
            self.assertEqual(e.exception.code,403)
        with post({'X-Path-Studio-Token':token,'Origin':base}) as r:self.assertEqual(r.status,200)
        for path in ['/api/path-studio/unknown','/../.env']:
            with self.assertRaises(error.HTTPError):request.urlopen(base+path)
        with request.urlopen(base+'/path-studio-api.js') as r:
            self.assertIn("connect-src 'self'",r.headers['Content-Security-Policy'])


class GeometryTests(unittest.TestCase):
    def test_original_mesh_guard_has_real_table_and_wrist_collision_positives(self):
        from remote_yam.controller_workspace import workspace_for_robot
        from remote_yam.mujoco_ik import BimanualRelativeIK
        for robot,spacing in (('yam-1',.5),('robot-ba8413962083809c',.62)):
            w=workspace_for_robot(robot)
            g=DrawingGeometry(spacing,w.joint_offsets_rad,w._safety()['table_z_m'])
            q=np.deg2rad(HOME.reshape(12));g.check(q,dict(left=0.,right=0.))
            ik=BimanualRelativeIK(base_spacing_m=spacing,joint_offsets_rad=w.joint_offsets_rad);ik._forward(q)
            for side,(position,rotation) in zip(('left','right'),ik._poses()):
                np.testing.assert_allclose(g.data.body(side+'_grasp').xpos,position,atol=1e-12)
                np.testing.assert_allclose(g.data.body(side+'_grasp').xmat.reshape(3,3),rotation,atol=1e-12)
            raised=DrawingGeometry(spacing,w.joint_offsets_rad,.3)
            with self.assertRaisesRegex(ValueError,'clearance check failed'):raised.check(q,dict(left=0.,right=0.))
        g=DrawingGeometry(.62,workspace_for_robot('robot-ba8413962083809c').joint_offsets_rad,-.16)
        q=np.r_[np.deg2rad(HOME[0]),[.9418423,1.2778544,.7794714,.5109908,.9350521,0.]]
        with self.assertRaisesRegex(ValueError,'right_link4 / right_installed_gripper'):
            g.check(q,dict(left=0.,right=0.))


class ConstrainedSimulationTests(unittest.TestCase):
    def heart(self, robot):
        data=sketch(robot,'both');data['speed_m_s']=.05
        data['points']=[[.34,.12*math.sin(t)**3,.31+.0075*(13*math.cos(t)-5*math.cos(2*t)-2*math.cos(3*t)-math.cos(4*t))]
                        for t in np.linspace(0,2*math.pi,97)]
        data['points'][-1]=data['points'][0].copy()
        return data

    def test_simulation_is_read_only_and_matches_real_policy_packets_on_both_stations(self):
        for robot in STATIONS.values():
            api=HardwareAPI(robot)
            service=PathStudioService(api_factory=lambda _:api)
            result=service.simulate(self.heart(robot));v=result['verification']
            self.assertTrue(v['passed']);self.assertEqual(v['confirmed_draw_samples'],196)
            self.assertLess(v['max_draw_error_m'],.003)
            self.assertEqual(v['baseline']['source'],'simulation')
            self.assertEqual(api.create_requests,[]);self.assertEqual(api.trajectory_log,[])
            # Exact shared-planner parity, not merely a visual resemblance.
            real=PathStudioPolicy(self.heart(robot));real.configure_calibration(report(robot))
            joints=np.rad2deg(REFERENCE_JOINTS_RAD).reshape(2,6)
            obs={**observation(robot), 'left_joints_deg':joints[0].tolist(),
                 'right_joints_deg':joints[1].tolist(),'left_gripper':1.,'right_gripper':1.}
            step=0
            while True:
                try:packet=real.build_trajectory('',obs,step)
                except PolicyComplete:break
                for point in packet:
                    obs.update(point,observed_at=time.time())
                    frame=result['frames'][step+1]
                    for side in ('left','right'):
                        np.testing.assert_allclose(frame[side+'_joints_deg'],point[side+'_joints_deg'],atol=1e-12)
                        self.assertEqual(frame[side+'_gripper'],obs[side+'_gripper'])
                    self.assertEqual(frame['phases'],real.step_phases[step])
                    step+=1
                real.trajectory_completed(obs,len(packet));obs['homed']=False
            self.assertEqual(step,v['waypoint_count'])

    def test_invalid_calibration_and_unreachable_path_cannot_pass(self):
        data=self.heart('yam-1');wrong=report('yam-1');wrong['robot_id']='other'
        with self.assertRaises(ValueError):simulate_sketch(data,wrong)
        data['points'][30]=[.8,.8,.8]
        with self.assertRaises(ValueError):simulate_sketch(data,report('yam-1'))

    def recorded_alignment(self):
        fixture=json.loads((ROOT/'tests/fixtures/path_studio_alignment_residual.json').read_text())
        fixture['sketch']['coordination']='sequential'  # recorded pre-synchronization behavior
        p=PathStudioPolicy(fixture['sketch']);p.configure_calibration(report(STATIONS['robohouse']))
        obs={**observation(STATIONS['robohouse']),**fixture['initial']}
        close=p.build_trajectory('',obs,0)
        obs.update(fixture['after_close']);p.trajectory_completed(obs,len(close));obs['homed']=False
        obs.update(fixture['before_motion'],observed_at=time.time())
        packet=p.build_trajectory('',obs,len(close))
        self.assertEqual(packet[-1]['step_id'],64)  # original 59 + five endpoint holds
        obs.update(fixture['measured'],observed_at=time.time())
        return p,obs,packet

    def test_recorded_14mm_alignment_residual_retries_same_target_without_advancing(self):
        p,obs,packet=self.recorded_alignment()
        p.trajectory_completed(obs,len(packet))
        self.assertTrue(p.settling);self.assertEqual(p.cursor,0)
        self.assertAlmostEqual(p.max_observed_tcp_error_m,.014292,places=5)
        pending=p.pending_cursor;target=p.targets[pending-1].copy()
        retry=p.build_trajectory('',obs,65)
        q=np.deg2rad(obs['left_joints_deg']+obs['right_joints_deg'])
        for point in retry:
            next_q=np.deg2rad(point['left_joints_deg']+point['right_joints_deg'])
            self.assertLessEqual(float(np.max(abs(next_q-q))),.03500001);q=next_q
        np.testing.assert_array_equal(p.targets[pending-1],target)
        obs.update(retry[-1],observed_at=time.time());p.trajectory_completed(obs,len(retry))
        self.assertFalse(p.settling);self.assertEqual(p.cursor,pending)
        self.assertLess(p.max_tcp_error_m,.003)

    def test_persistent_or_drawing_tracking_error_still_stops(self):
        p,obs,packet=self.recorded_alignment();p.trajectory_completed(obs,len(packet))
        retry=p.build_trajectory('',obs,65)
        with self.assertRaisesRegex(ValueError,'Measured tool pose missed'):
            p.trajectory_completed(obs,len(retry))
        self.assertEqual(p.cursor,0)
        p,obs,packet=self.recorded_alignment()
        p.target_phases[p.pending_cursor-1]={'left':'draw'}
        with self.assertRaisesRegex(ValueError,'Measured tool pose missed'):
            p.trajectory_completed(obs,len(packet))
        self.assertEqual(p.cursor,0)

    def test_both_arms_draw_together_without_approximation_when_heart_has_clearance(self):
        for robot in STATIONS.values():
            data=self.heart(robot);data['coordination']='together'
            result=simulate_sketch(data,report(robot));v=result['verification']
            self.assertEqual(v['coordination'],'together')
            self.assertEqual(v['max_path_adjustment_m'],0.)
            self.assertLess(v['max_requested_path_deviation_m'],.003)
            self.assertGreater(v['min_gripper_clearance_m'],.05)
            self.assertGreater(v['simultaneous_draw_steps'],150)
            frames=result['frames'];moving_together=0
            for before,after in zip(frames,frames[1:]):
                if after['phases'].get('left')!='draw':continue
                self.assertEqual(after['phases'].get('right'),'draw')
                if all(np.max(abs(np.array(after[a+'_joints_deg'])-before[a+'_joints_deg']))>.0001 for a in ('left','right')):
                    moving_together+=1
            self.assertGreater(moving_together,.95*v['simultaneous_draw_steps'])
            # Independently check actual swept CAD and mesh distances on every
            # replay frame, including simultaneous alignment and approach.
            from remote_yam.controller_workspace import workspace_for_robot
            w=workspace_for_robot(robot)
            guard=DrawingGeometry(result['calibration']['spacing_m'],w.joint_offsets_rad,w._safety()['table_z_m'])
            guard.required_gripper_clearance_m=.02
            previous=np.array(REFERENCE_JOINTS_RAD)
            for frame in frames:
                q=np.deg2rad(frame['left_joints_deg']+frame['right_joints_deg'])
                guard.sweep(previous,q,{a:frame[a+'_gripper'] for a in ('left','right')});previous=q
            self.assertGreaterEqual(guard.min_gripper_clearance_m,.02)

    def test_close_short_stroke_is_adjusted_and_actual_trace_is_reported(self):
        for robot in STATIONS.values():
            data=self.heart(robot);data.update(coordination='together',points=[[.34,-.02,.31],[.34,.02,.31]])
            result=simulate_sketch(data,report(robot));v=result['verification']
            self.assertTrue(v['passed']);self.assertGreater(v['max_path_adjustment_m'],.04)
            self.assertLess(v['max_path_adjustment_m'],.1)
            self.assertGreaterEqual(v['min_gripper_clearance_m'],.02)
            self.assertGreater(v['max_requested_path_deviation_m'],.04)
            self.assertGreater(v['simultaneous_draw_steps'],0)
            self.assertGreater(result['paths_m']['left'][0][1],.04)

    def test_together_accepts_recorded_tracking_lag_only_with_measured_clearance(self):
        robot=STATIONS['robohouse'];data=self.heart(robot);data['coordination']='together'
        p=PathStudioPolicy(data);p.configure_calibration(report(robot));obs=observation(robot)
        close=p.build_trajectory('',obs,0);obs.update(close[-1]);p.trajectory_completed(obs,len(close));obs['homed']=False
        packet=p.build_trajectory('',obs,len(close));obs.update(packet[-1])
        f=json.loads((ROOT/'tests/fixtures/path_studio_alignment_residual.json').read_text())
        for a in ('left','right'):
            delta=np.array(f['measured'][a+'_joints_deg'])-f['commanded'][a+'_joints_deg']
            obs[a+'_joints_deg']=(np.array(obs[a+'_joints_deg'])+delta).tolist()
        p.trajectory_completed(obs,len(packet))
        self.assertGreater(p.max_tcp_error_m,.003);self.assertLess(p.max_tcp_error_m,.025)
        self.assertGreater(p.cursor,0);self.assertFalse(p.settling)
        next_packet=p.build_trajectory('',{**obs,'observed_at':time.time()},len(close)+len(packet))
        q=np.deg2rad(obs['left_joints_deg']+obs['right_joints_deg'])
        for point in next_packet:
            target=np.deg2rad(point['left_joints_deg']+point['right_joints_deg'])
            self.assertLessEqual(float(np.max(abs(target-q))),.03500001);q=target

    def test_small_tracking_error_cannot_override_measured_gripper_clearance(self):
        robot=STATIONS['robohouse'];data=self.heart(robot)
        data.update(coordination='together',points=[[.34,-.02,.31],[.34,.02,.31]])
        p=PathStudioPolicy(data);p.configure_calibration(report(robot));obs=observation(robot);step=0
        while True:
            packet=p.build_trajectory('',obs,step);step+=len(packet);obs.update(packet[-1],observed_at=time.time())
            if not p.closing_pending and p.pending_cursor==len(p.targets):break
            p.trajectory_completed(obs,len(packet));obs['homed']=False
        before=p.cursor
        obs['left_joints_deg']=obs['left_joints_deg'][:];obs['left_joints_deg'][0]-=math.degrees(.02)
        with self.assertRaisesRegex(ValueError,'Gripper clearance'):
            p.trajectory_completed(obs,len(packet))
        self.assertEqual(p.cursor,before)

if __name__=='__main__':unittest.main()
