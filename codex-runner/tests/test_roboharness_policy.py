from copy import deepcopy
import io
import json
from pathlib import Path
import time
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
    return p,source


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.obs={**observation(),'episode_id':'ep_offline','lease_id':'lease_offline','step_id':0}

    def test_public_approach_and_underlying_model_are_separate(self):
        p,_=adapter();cfg=p.public_config()
        self.assertEqual(cfg['model'],'RoboHarness');self.assertEqual(cfg['underlying_models']['planning'],'gpt-6-astra')
        self.assertIsNone(cfg['underlying_models']['resolved']);self.assertFalse(cfg['api_key_configured'])

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
