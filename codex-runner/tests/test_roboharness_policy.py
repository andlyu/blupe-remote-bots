from copy import deepcopy
import io
import json
from pathlib import Path
import time
import tempfile
import unittest
from unittest.mock import patch,Mock

import numpy as np
from PIL import Image

from remote_yam.cameras import CameraFrame
from remote_yam.roboharness_contract import decision_response
from remote_yam.roboharness_policy import RoboHarnessAdapter
from remote_yam.session import HttpSessionAPI
from test_roboharness_control import observation
from test_roboharness_contract import decision

API='https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com'
REPORT=json.loads((Path(__file__).parent/'fixtures/roboharness-robohouse-calibration.json').read_text())


class Snapshot:
    def __init__(self,role,position):
        self.rgb=np.random.default_rng(7).integers(0,256,(80,100,3),dtype=np.uint8)
        self.metadata=dict(camera=role,captured_at=time.time(),sensor_serial='synthetic-'+role,calibration_id=REPORT['calibration_id'])
        self.calibration=REPORT;self.position=position
    def age(self):return time.time()-self.metadata['captured_at']
    def image(self):
        b=io.BytesIO();Image.fromarray(self.rgb).save(b,format='PNG');return b.getvalue()
    def measure(self,u,v,*,arm):return {'point_base_m':self.position[arm]}


class Cameras:
    def __init__(self):self.snapshots={};self.position=None;self.calls=0
    def capture_for_policy(self,obs,**kwargs):
        self.calls+=1
        self.snapshots={role:Snapshot(role,self.position) for role in ('top','left','right')}
        return [CameraFrame(role,s.image(),time.time()) for role,s in self.snapshots.items()]


def adapter():
    source=Cameras()
    p=RoboHarnessAdapter(API,'robot-ba8413962083809c',REPORT,
        expected_calibration_id=REPORT['calibration_id'],expected_model_calibration_id=REPORT['model_joint_calibration']['calibration_id'],camera_source=source)
    p._geometry.clock=lambda:time.time()
    return p,source


class PolicyTests(unittest.TestCase):
    def setUp(self):
        # Synthetic feedback/cameras use a controlled clock, independent of
        # model initialization and CPU speed. Freshness tests advance their own
        # nested clock explicitly; production still uses the real clock.
        clock=patch('time.time',return_value=1000.)
        clock.start();self.addCleanup(clock.stop)
        self.obs={**observation(),'episode_id':'ep_offline','lease_id':'lease_offline','step_id':0}

    def test_public_approach_and_underlying_model_are_separate(self):
        p,_=adapter();cfg=p.public_config()
        self.assertEqual(cfg['model'],'RoboHarness');self.assertEqual(cfg['underlying_models']['planning'],'gpt-6-astra')
        self.assertIsNone(cfg['underlying_models']['resolved']);self.assertFalse(cfg['api_key_configured'])

    def test_every_tracking_capture_retains_exact_image_and_source_clock(self):
        from remote_yam.robocurve_policy import CallRecorder
        with tempfile.TemporaryDirectory() as directory:
            p,source=adapter();p._recorder=CallRecorder(directory)
            p._capture(self.obs);p.tracker.register('point_0',500,500);p._capture(self.obs)
            rows=[json.loads(line) for line in (p._recorder.path/'calls.jsonl').read_text().splitlines()]
            self.assertEqual([r['kind'] for r in rows],['tracking_frame','tracking_frame'])
            for row in rows:
                self.assertEqual(row['camera'],'top')
                self.assertEqual(row['calibration_id'],REPORT['calibration_id'])
                self.assertIn('captured_at',row)
                digest=row['image_url'].split('$blob:')[1]
                raw=(p._recorder.path/'blobs'/digest).read_bytes()
                self.assertEqual(raw,source.snapshots['top'].image())
            self.assertIn('point_0',rows[1]['tracking_before']['pixels'])
            self.assertEqual(rows[1]['tracking_after']['captured_at'],source.snapshots['top'].metadata['captured_at'])

    def test_planner_receives_station_bound_nominal_tip_geometry_and_actual_axes(self):
        p,source=adapter();source.position={a:v['position_m'] for a,v in p._geometry.pose_summary(self.obs).items()}
        p._episode=tuple(self.obs[k] for k in ('episode_id','lease_id'))
        message=p._observation_message('Offline gripper geometry context',self.obs,0)
        context=json.loads(message['content'][0]['text'])
        ref=context['tool_geometry_reference']
        self.assertTrue(ref['available']);self.assertFalse(ref['physical_contact_calibration_measured'])
        self.assertEqual(ref['jaw_opening_axis'],'Y');self.assertEqual(ref['approach_axis'],'Z')
        self.assertGreater(ref['max_tip_z_m'],.010)
        self.assertTrue(context['nominal_tool_pose']['available'])
        for arm in ('left','right'):
            pose=context['poses'][arm];tool=context['nominal_tool_pose']['arms'][arm]
            np.testing.assert_allclose(tool['approach_axis_base'],np.array(pose['rotation_matrix'])[:,2])
            np.testing.assert_allclose(tool['opening_axis_base'],np.array(pose['rotation_matrix'])[:,1])
            self.assertIn('whole_tool_bounds_base_m',tool)

    def test_stale_acquisition_reacquires_only_needed_depth_without_another_model_call(self):
        for primitive in (2,5,6):
            with self.subTest(primitive=primitive):
                clock=[1000.]
                with patch('time.time',side_effect=lambda:clock[0]):
                    p,source=adapter();p._geometry.clock=lambda:clock[0]
                    obs={**self.obs,'observed_at':clock[0]}
                    source.position={a:v['position_m'] for a,v in p._geometry.pose_summary(obs).items()}
                    capture=source.capture_for_policy
                    def delayed_capture(observation,**kwargs):
                        frames=capture(observation,**kwargs)
                        if source.calls==2:source.snapshots['top'].metadata['captured_at']-=2.1
                        return frames
                    source.capture_for_policy=delayed_capture
                    p.refresh_observation=lambda:{**obs,'observed_at':clock[0]}
                    target=decision(primitive=2,arm=0,point_a=0,u=500,v=500,x=0,y=0,z=.005) if primitive==2 else decision(primitive=5,arm=0,x=0,y=0,z=.005,rx=0,ry=0,rz=0) if primitive==5 else decision(primitive=6,arm=0,gripper=0)
                    def model(payload):clock[0]+=3;return decision_response(target)
                    p._post_json=Mock(side_effect=model)
                    packet=p.build_trajectory('Offline stale acquisition',obs,0)
                    self.assertEqual(p._post_json.call_count,1)
                    self.assertEqual(source.calls,3 if primitive==2 else 2)
                    self.assertTrue(packet)
                    self.assertEqual(packet[-1]['right_joints_deg'],obs['right_joints_deg'])

    def test_model_observation_reacquires_depth_aged_during_feedback_once_before_inference(self):
        from remote_yam.roboharness_tracking import StaleTrackingDepth
        for always_stale in (False,True):
            with self.subTest(always_stale=always_stale):
                p,source=adapter();p._episode=tuple(self.obs[k] for k in ('episode_id','lease_id'))
                source.position={a:v['position_m'] for a,v in p._geometry.pose_summary(self.obs).items()}
                original=source.capture_for_policy
                def capture(observation,**kwargs):
                    frames=original(observation,**kwargs)
                    if always_stale or source.calls==1:
                        # Actual cup-run age after processing: 2.003347 seconds.
                        source.snapshots['top'].metadata['captured_at']-=2.003347158432007
                    return frames
                source.capture_for_policy=capture;p._post_json=Mock()
                with patch('remote_yam.session.request.urlopen') as outbound:
                    if always_stale:
                        with self.assertRaises(StaleTrackingDepth):p._observation_message('Offline fresh model view',self.obs,0)
                    else:
                        message=p._observation_message('Offline fresh model view',self.obs,0)
                        self.assertEqual(message['role'],'user')
                    self.assertEqual(source.calls,2);p._post_json.assert_not_called();outbound.assert_not_called()

    def test_queue_model_initialization_has_no_robot_targets_and_preserves_real_task_context(self):
        p,source=adapter();p._warm_model_session=True;p.runner_name='Synthetic offline runner';p.execution_mode='offline_contract'
        source.position={a:v['position_m'] for a,v in p._geometry.pose_summary(self.obs).items()}
        requests=[]
        def model(payload):
            requests.append(deepcopy(payload))
            if len(requests)==1:
                self.assertEqual(source.calls,0);p._sent_items=2
                target={**decision(),'action':'give_up','reason':'non_actuating_session_ready'}
            else:
                self.assertEqual(p._sent_items,0)
                target=decision(primitive=6,arm=1,gripper=.5)
            return decision_response(target)
        p._post_json=Mock(side_effect=model);p.refresh_observation=lambda:dict(self.obs)
        with patch('remote_yam.session.request.urlopen') as outbound:
            p.start_preparation(lambda:False);p._await_preparation()
            p.start_preparation(lambda:False) # The same queue hook cannot initialize twice.
            self.assertEqual(p._post_json.call_count,1);self.assertEqual(p._calls,0)
            self.assertIsNone(p._outcome);self.assertEqual(p._history,[])
            packet=p.build_trajectory('Actual offline task after initialization',self.obs,0)
            self.assertTrue(packet);outbound.assert_not_called()
        self.assertEqual(len(requests),2);self.assertEqual(p._calls,1)
        self.assertEqual(requests[0]['input'][1]['content'][1]['type'],'input_image')
        self.assertIn('synthetic',requests[0]['instructions'])
        self.assertIn('Actual offline task after initialization',str(requests[1]['input']))
        config=p.public_config()['model_preparation']
        self.assertEqual(config['state'],'ready');self.assertEqual(config['runner_name'],'Synthetic offline runner')
        self.assertEqual(config['robot_targets'],0);self.assertEqual(config['actuator_submissions'],0)
        self.assertEqual(packet[-1]['left_gripper'],self.obs['left_gripper'])

    def test_model_initialization_and_three_image_policy_use_actual_codex_transport_parser(self):
        import uuid
        from remote_yam.codex_policy import use_codex_executor
        p,source=adapter();p._warm_model_session=True;p.runner_name='Synthetic offline runner'
        source.position={a:v['position_m'] for a,v in p._geometry.pose_summary(self.obs).items()}
        p.refresh_observation=lambda:dict(self.obs)
        thread=str(uuid.uuid4());requests=[]
        def executor(**request):
            requests.append(request)
            if len(requests)==1:
                self.assertEqual(len(request['images']),1);self.assertIsNone(request['thread_id'])
                import hashlib
                self.assertEqual(hashlib.sha256(request['images'][0]).hexdigest(),'5fc031e7b497a6cf7c4cb65d5685c12649ad48013f1a22a91200b764d3378225')
                self.assertIn('not robot footage',request['prompt'])
                target={**decision(),'action':'give_up','reason':'non_actuating_session_ready'}
            else:
                self.assertEqual(len(request['images']),3);self.assertEqual(request['thread_id'],thread)
                self.assertIn('Actual task through transport',request['prompt'])
                target=decision(primitive=6,arm=1,gripper=.5)
            return [{'type':'thread.started','thread_id':thread},
                {'type':'item.completed','item':{'type':'agent_message','text':json.dumps(target)}},
                {'type':'turn.completed'}]
        use_codex_executor(p,executor);self.addCleanup(p.close_transport)
        with patch('remote_yam.session.request.urlopen') as outbound:
            p.start_preparation(lambda:False);p._await_preparation()
            self.assertEqual(p._expected_camera_count,3)
            self.assertTrue(p.build_trajectory('Actual task through transport',self.obs,0))
            outbound.assert_not_called()
        self.assertEqual(len(requests),2);self.assertEqual(p._calls,1)
        self.assertIsNone(p._outcome)

    def test_failed_cancelled_or_unattributed_model_initialization_never_retries_or_dispatches(self):
        for fault in ('transport','cancelled','identity'):
            with self.subTest(fault=fault):
                p,source=adapter();p._warm_model_session=True
                if fault!='identity':p.runner_name='Synthetic offline runner'
                p._post_json=Mock(side_effect=TimeoutError('Offline synthetic model timeout'))
                with patch('remote_yam.session.request.urlopen') as outbound:
                    if fault=='identity':
                        with self.assertRaisesRegex(RuntimeError,'attribution'):p.start_preparation(lambda:False)
                    else:
                        p.start_preparation(lambda:fault=='cancelled')
                        with self.assertRaisesRegex(RuntimeError,'initialization failed'):p._await_preparation()
                        p.start_preparation(lambda:False)
                    self.assertEqual(p._post_json.call_count,1 if fault=='transport' else 0)
                    self.assertEqual(source.calls,0);self.assertIsNone(p._pending);self.assertEqual(p._expected_camera_count,3);outbound.assert_not_called()

    def test_changed_tool_mount_has_no_nominal_reference_or_hidden_tcp_shift(self):
        from remote_yam.yam_gripper_reference import reference_for_model
        p,_=adapter();ik=p._geometry.ik;body=ik.body_ids[0]
        original=ik.model.body_pos[body].copy();ik.model.body_pos[body,2]-=.001
        self.assertFalse(reference_for_model(ik,p.robot_id)['available'])
        np.testing.assert_allclose(ik.model.body_pos[body],original+[0,0,-.001])
        self.assertFalse(reference_for_model(ik,'another-robot')['available'])

    def test_calibration_changes_native_double_offsets_and_optical_scope_reject(self):
        for change in ({'calibration_id':'changed'},{'robot_id':'other'},{'measurement_scope':'camera_optical_only'}):
            r={**deepcopy(REPORT),**change}
            with self.subTest(change=change),self.assertRaises(ValueError):
                RoboHarnessAdapter(API,'robot-ba8413962083809c',r,expected_calibration_id=REPORT['calibration_id'],expected_model_calibration_id=REPORT['model_joint_calibration']['calibration_id'])

    def test_runtime_parser_to_generator_to_wire_gripper_and_touch(self):
        for decoded in [decision(primitive=6,arm=0,gripper=0),decision(primitive=2,arm=0,point_a=0,u=500,v=500,x=0,y=0,z=.005)]:
            with self.subTest(decoded=decoded):
                p,source=adapter();positions=p._geometry.pose_summary(self.obs)
                source.position={a:positions[a]['position_m'] for a in ('left','right')}
                p._post_json=lambda payload:decision_response(decoded)
                p.refresh_observation=lambda:{**self.obs,'observed_at':time.time()}
                packet=p.build_trajectory('Offline synthetic task',self.obs,0)
                self.assertGreaterEqual(source.calls,2)
                api=HttpSessionAPI('https://offline.invalid',supports_trajectories=True)
                api._session_capabilities['offline']='synthetic';sent=[]
                def wire(req,**kwargs):sent.append(json.loads(req.data));return io.BytesIO(b'{"accepted":true}')
                with patch('remote_yam.session.request.urlopen',side_effect=wire):
                    api.submit_trajectory('offline','ep_offline','lease_offline','traj_offline',10,packet)
                self.assertEqual(len(sent),1)
                self.assertEqual(sent[0]['waypoints'][-1]['left_gripper'],0 if decoded['targets']['primitive']==6 else self.obs['left_gripper'])
                final={**self.obs,**packet[-1],'step_id':packet[-1]['step_id']+1,'observed_at':time.time()}
                p.trajectory_completed(final,len(packet));self.assertIsNone(p._pending)

    def test_yam1_native_calibration_has_no_second_offset_and_both_grippers_validate(self):
        report=json.loads((Path(__file__).parent/'fixtures/roboharness-yam1-calibration.json').read_text())
        p=RoboHarnessAdapter(API,'yam-1',report,expected_calibration_id=report['calibration_id'],expected_model_calibration_id=report['native_joint_calibration']['calibration_id'])
        p._geometry.clock=lambda:time.time()
        self.assertIsNone(p._depth_joint_offsets_rad)
        obs={**observation(),'robot_id':'yam-1'}
        for arm in ('left','right'):
            for target in (0,1,.37):
                packet=p._geometry.build(dict(kind='gripper',arm=arm,value=target),obs,0)
                api=HttpSessionAPI('https://offline.invalid',supports_trajectories=True,robot_id='yam-1')
                api._session_capabilities['offline']='synthetic';sent=[]
                def wire(req,**kwargs):sent.append(json.loads(req.data));return io.BytesIO(b'{"accepted":true}')
                with patch('remote_yam.session.request.urlopen',side_effect=wire):api.submit_trajectory('offline','ep_offline','lease_offline','traj_offline',10,packet)
                self.assertEqual(sent[0]['waypoints'][-1][arm+'_gripper'],target)
        changed=deepcopy(report);changed['native_joint_calibration']['additional_offsets_rad']['left'][0]=.1
        with self.assertRaisesRegex(ValueError,'twice'):
            RoboHarnessAdapter(API,'yam-1',changed,expected_calibration_id=report['calibration_id'],expected_model_calibration_id=report['native_joint_calibration']['calibration_id'])

    def test_camera_delay_refreshes_actual_feedback_before_model_and_wire(self):
        # Reproduces the 3.598 s capture span from failed run ep_d758914999e442e6.
        fixture=json.loads((Path(__file__).parent/'fixtures/roboharness-stale-home-feedback.json').read_text())
        clock=[fixture['checked_at']]
        with patch('time.time',side_effect=lambda:clock[0]):
            p,source=adapter();p._geometry.clock=lambda:clock[0]
            obs=fixture['observation']
            source.position={a:v['position_m'] for a,v in p._geometry.pose_summary(obs).items()}
            original=source.capture_for_policy
            def delayed(observation,**kwargs):
                clock[0]+=fixture['camera_acquisition_s']
                return original(observation,**kwargs)
            source.capture_for_policy=delayed
            p.refresh_observation=Mock(side_effect=lambda:{**obs,'observed_at':clock[0]})
            p._post_json=Mock(return_value=decision_response(decision(primitive=6,arm=0,gripper=0)))
            packet=p.build_trajectory('Synthetic delayed camera regression',obs,0)
            self.assertGreaterEqual(p.refresh_observation.call_count,3)
            self.assertEqual(packet[-1]['left_gripper'],0)
            api=HttpSessionAPI('https://offline.invalid',supports_trajectories=True);api._session_capabilities['offline']='synthetic'
            sent=[]
            def wire(req,**kwargs):sent.append(json.loads(req.data));return io.BytesIO(b'{"accepted":true}')
            with patch('remote_yam.session.request.urlopen',side_effect=wire):api.submit_trajectory('offline','ep_offline','lease_offline','traj_offline',10,packet)
            self.assertEqual(len(sent),1)

    def test_post_capture_refresh_cannot_forge_freshness_or_change_session(self):
        for change in ({'observed_at':1000.},{'lease_id':'different-lease'}):
            clock=[1000.]
            with self.subTest(change=change),patch('time.time',side_effect=lambda:clock[0]):
                p,source=adapter();p._geometry.clock=lambda:clock[0]
                obs={**self.obs,'observed_at':clock[0]}
                source.position={a:v['position_m'] for a,v in p._geometry.pose_summary(obs).items()}
                original=source.capture_for_policy
                def delayed(observation,**kwargs):clock[0]+=3.598;return original(observation,**kwargs)
                source.capture_for_policy=delayed
                p.refresh_observation=lambda:{**obs,'observed_at':clock[0],**change}
                with patch.object(p,'_post_json') as model,patch('remote_yam.session.request.urlopen') as wire:
                    with self.assertRaises((ValueError,RuntimeError)):p.build_trajectory('Synthetic invalid refresh',obs,0)
                    model.assert_not_called();wire.assert_not_called()

    def completed_hover(self, *, establish_home=True):
        f=json.loads((Path(__file__).parent/'fixtures/roboharness-post-home-feedback.json').read_text())
        clock=[f['clock_home']];p,source=adapter();p._geometry.clock=lambda:clock[0]
        if establish_home:p._geometry.pose_summary(f['home'])
        p._episode=('ep_offline','lease_offline');p._prompt='Post-Home measured feedback regression'
        p._history=[{'role':'system','content':'Offline regression'}]
        p._pending={'call_id':'fixture_hover','waypoint_count':67,'last_step_id':66}
        clock[0]=f['clock_post']
        return p,source,f

    def test_measured_completed_hover_can_leave_home_before_next_real_packet(self):
        p,source,f=self.completed_hover()
        with patch('time.time',return_value=f['clock_post']):
            p.trajectory_completed(f['post_motion'],67)
            source.position={a:v['position_m'] for a,v in p._geometry.pose_summary(f['post_motion']).items()}
            p.refresh_observation=lambda:deepcopy(f['post_motion'])
            p._post_json=Mock(return_value=decision_response(decision(primitive=5,arm=0,x=0,y=0,z=.03,rx=0,ry=0,rz=0)))
            packet=p.build_trajectory(p._prompt,f['post_motion'],67)
            self.assertEqual(packet[0]['step_id'],67)
            self.assertEqual(packet[-1]['right_joints_deg'],f['post_motion']['right_joints_deg'])
            api=HttpSessionAPI('https://offline.invalid',supports_trajectories=True);api._session_capabilities['offline']='synthetic'
            sent=[]
            def wire(req,**kwargs):sent.append(json.loads(req.data));return io.BytesIO(b'{"accepted":true}')
            with patch('remote_yam.session.request.urlopen',side_effect=wire):api.submit_trajectory('offline','ep_offline','lease_offline','traj_next',10,packet)
            self.assertEqual(len(sent),1)

    def test_non_home_feedback_requires_exact_confirmed_home_and_completion(self):
        for change in ({'lease_id':'other'},{'episode_id':'other'},{'step_id':68},{'settled':False},
                       {'safety':{'ok':False}},{'source':'simulated'},{'observed_at':1.}):
            with self.subTest(change=change):
                p,source,f=self.completed_hover()
                with patch.object(p,'_post_json') as model,patch('remote_yam.session.request.urlopen') as wire:
                    with self.assertRaises((RuntimeError,ValueError)):p.trajectory_completed({**f['post_motion'],**change},67)
                    with self.assertRaises(ValueError):p._geometry.pose_summary(f['post_motion'])
                    model.assert_not_called();wire.assert_not_called()
        p,_,f=self.completed_hover(establish_home=False)
        with self.assertRaises((RuntimeError,ValueError)):p.trajectory_completed(f['post_motion'],67)
        p,_,f=self.completed_hover()
        with self.assertRaises((RuntimeError,ValueError)):p.trajectory_completed(f['post_motion'],66)
        with self.assertRaises(ValueError):p._geometry.pose_summary(f['post_motion'])

    def test_timeout_requires_stop_without_model_or_packet_retry(self):
        p,_=adapter()
        with patch.object(p,'_post_json') as model,patch('remote_yam.session.request.urlopen') as wire:
            with self.assertRaisesRegex(RuntimeError,'no automatic retry'):p.trajectory_failed('joint_settle_timeout','timeout',1)
            model.assert_not_called();wire.assert_not_called()

    def test_unattached_model_has_no_api_fallback(self):
        p,_=adapter()
        with patch('remote_yam.session.request.urlopen') as wire:
            with self.assertRaisesRegex(RuntimeError,'no model fallback'):p._post_json({})
            wire.assert_not_called()


if __name__=='__main__':unittest.main()
