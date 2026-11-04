"""Real planner/serializer and visitor gate tests. No physical station writes."""
from copy import deepcopy
import json
from pathlib import Path
import time
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

from remote_yam.scene_capture_flow import DEFAULTS,validate_config,simulate_capture,binding
from remote_yam.scene_capture_policy import MinutePolicy,TASK
from remote_yam.path_studio_service import PathStudioService
from remote_yam.session import _trajectory_waypoints

DATA=Path(__file__).parents[1]/'scene-capture-data'
REPORT=json.loads((DATA/'yam1-calibration.json').read_text())
HOME=json.loads((DATA/'simulation-home.json').read_text())['home_pose']

class ReadOnly:
    def __init__(self):self.requests=[]
    def _request(self,method,path):
        self.requests.append((method,path));assert (method,path)==('GET','/v1/robots/yam-1/calibration');return deepcopy(REPORT)

class CaptureTests(unittest.TestCase):
    def test_real_default_planner_cad_and_packets(self):
        sim=simulate_capture(DEFAULTS,REPORT)
        self.assertTrue(sim['verification']['passed']);self.assertEqual(len(sim['frames']),600)
        self.assertGreater(sim['verification']['swept_samples'],600)
        for start in (0,300):self.assertEqual(len(_trajectory_waypoints(sim['frames'][start:start+300])),300)
        for cameras in sim['cameras']:
            for camera in cameras:
                rotation=np.asarray(camera['rotation']);self.assertTrue(np.allclose(rotation.T@rotation,np.eye(3),atol=1e-6))
                self.assertTrue(np.allclose(rotation[:,2],camera['optical_axis']))
        self.assertLessEqual(sim['verification']['max_joint_step_rad'],.035)

    def test_guided_settings_remain_bounded_and_have_actual_duration(self):
        for data in ({'duration_s':True},{'duration_s':61},{'reach_m':float('nan')},{'reach_m':.48},{'scan_width_m':.2},{'station':'robohouse'}):
            with self.assertRaises(ValueError):validate_config(data)
        for duration in (60,90,120):
            config=validate_config(dict(duration_s=duration,reach_m=.42,scan_width_m=.10,aim_x_m=.55))
            sim=simulate_capture(config,REPORT)
            self.assertEqual(len(sim['frames']),duration*10)

    def test_simulation_only_reads_calibration_and_does_not_create_session(self):
        with tempfile.TemporaryDirectory() as temp:
            api=ReadOnly();service=PathStudioService(api_factory=lambda _:api,identity_path=Path(temp)/'identity.json')
            service.simulate_capture(dict(config=DEFAULTS));service.capture_worker.join(5)
            self.assertEqual(service.capture['simulation']['status'],'passed')
            self.assertEqual(api.requests,[('GET','/v1/robots/yam-1/calibration')]);self.assertIsNone(service.controller)
            self.assertNotIn('frames',service.capture_status()['simulation'])

    def test_server_rejects_missing_changed_expired_foreign_and_stale_simulation(self):
        with tempfile.TemporaryDirectory() as temp:
            api=ReadOnly();service=PathStudioService(api_factory=lambda _:api,identity_path=Path(temp)/'identity.json')
            data=dict(config=DEFAULTS,identity=dict(runner_name='Test Operator',email='test@example.test'),simulation_token='wrong')
            with self.assertRaisesRegex(ValueError,'Simulate'):service.run_capture(data)
            service.simulate_capture(dict(config=DEFAULTS));service.capture_worker.join(5)
            data['simulation_token']=service.capture_receipt['token']
            with self.assertRaisesRegex(ValueError,'Simulate'):service.run_capture({**data,'config':{**DEFAULTS,'reach_m':.46}})
            with self.assertRaisesRegex(ValueError,'Simulate'):service.run_capture({**data,'simulation_token':'foreign'})
            service.capture_receipt['created']-=1801
            with self.assertRaisesRegex(ValueError,'Simulate'):service.run_capture(data)
            service.capture_receipt['created']=time.time()
            service.capture_receipt['sha256']='source changed'
            with self.assertRaisesRegex(ValueError,'Calibration or planner changed'):service.run_capture(data)
            self.assertIsNone(service.controller)

    def test_normal_runner_completes_two_packets_and_consumes_receipt(self):
        from test_path_studio_api import HardwareAPI,wait_for
        class API(HardwareAPI):
            def _request(self,method,path):return deepcopy(REPORT)
        with tempfile.TemporaryDirectory() as temp:
            api=API();service=PathStudioService(api_factory=lambda _:api,identity_path=Path(temp)/'identity.json')
            service.simulate_capture(dict(config=DEFAULTS));service.capture_worker.join(5)
            token=service.capture_receipt['token']
            request=dict(config=DEFAULTS,identity=dict(runner_name='Test Operator',email='test@example.test'),simulation_token=token)
            service.run_capture(request)
            wait_for(lambda: service.controller.status()['status'] not in ('preparing','queued','running'),seconds=10)
            status=service.status('yam-1')
            self.assertEqual(len(api.trajectory_log),2,status['run'])
            self.assertEqual(status['run']['next_step_id'],600,status['run'])
            self.assertEqual(service.policy.cursor,600)
            self.assertIsNone(service.capture_receipt)
            self.assertEqual(service.capture['simulation']['status'],'used')
            with self.assertRaisesRegex(ValueError,'Simulate'):service.run_capture(request)
            receipt=json.loads(next(service.capture_public_root.glob('*.json')).read_text())
            self.assertNotIn('email',json.dumps(receipt));service.close()

    def test_native_policy_uses_measured_grippers_no_uncertain_packet_retry(self):
        policy=MinutePolicy(REPORT,DEFAULTS,simulation=True)
        obs=dict(source='simulation',jetson_id='yam-1',homed=True,settled=True,safety=dict(ok=True),observed_at=time.time(),
            left_joints_deg=np.rad2deg(HOME[:6]).tolist(),right_joints_deg=np.rad2deg(HOME[7:13]).tolist(),left_gripper=.3,right_gripper=.7,episode_id='ep_test',lease_id='lease_test')
        packet=policy.build_trajectory(TASK,obs,0)
        self.assertEqual(len(packet),300);self.assertTrue(all(p['left_gripper']==.3 and p['right_gripper']==.7 for p in packet))
        with self.assertRaisesRegex(RuntimeError,'pending or uncertain'):policy.build_trajectory(TASK,obs,0)
        obs.update(packet[-1],step_id=300,observed_at=time.time(),homed=False)
        policy.validate_trajectory_final(obs);self.assertEqual(policy.cursor,300);self.assertFalse(policy.complete)
        second=policy.build_trajectory(TASK,obs,300);obs.update(second[-1],step_id=600,observed_at=time.time())
        policy.validate_trajectory_final(obs);self.assertTrue(policy.complete)

if __name__=='__main__':unittest.main()
