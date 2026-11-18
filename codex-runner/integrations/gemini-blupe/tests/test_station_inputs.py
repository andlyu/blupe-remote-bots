"""Actual SDK image construction and bounded canonical camera transport; no network."""
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

ROOT=Path(os.environ.get('GEMINI_TEST_RUNNER_ROOT',Path(__file__).resolve().parents[3]))
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from station_inputs import collect_station_inputs,sdk_prompt,API_ORIGIN
from remote_yam.cameras import CameraFrameSource


class Response(io.BytesIO):
    def __init__(self,data):
        super().__init__(data)
        from email.message import Message
        self.headers=Message();self.headers['Content-Type']='image/jpeg';self.headers['Content-Length']=str(len(data))
        self.headers['X-Captured-At']=str(time.time())
    def read1(self,n):return self.read(n)


class StationInputsTests(unittest.TestCase):
    def setUp(self):
        c=json.loads((Path(__file__).resolve().parent/'fixtures/yam1-calibration.json').read_text())
        c['schema_version']=1;c['private_email']='never-model@example.test'
        self.calibration=c
        self.observation=dict(jetson_id='yam-1',source='hardware',observed_at=time.time(),
            left_joints_deg=[.1,90,70,-50,.1,-1],right_joints_deg=[-.1,90,70,-50,-.1,1],
            left_gripper=.9992793312193716,right_gripper=.412345678,
            email='never-model@example.test',lease_id='secret-lease',session_capability='secret-capability',
            images={role:dict(url='/v1/robots/yam-1/cameras/'+role+'.jpg') for role in ('top','left','right')})
        outer=self
        class Api:
            def get_robot_observation(self,robot):
                assert robot=='yam-1';return deepcopy(outer.observation)
            def _request(self,method,path):
                assert method=='GET' and path=='/v1/robots/yam-1/calibration';return deepcopy(outer.calibration)
        self.api=Api()
        self.cameras=CameraFrameSource(API_ORIGIN,max_attempts=1,recovery_s=2)
        self.opened=[]
        class Opener:
            def open(_,request,**kwargs):
                outer.opened.append(request.full_url);return Response(b'\xff\xd8test-fixture\xff\xd9')
        self.patch=patch('remote_yam.cameras.request.build_opener',return_value=Opener());self.patch.start();self.addCleanup(self.patch.stop)

    def test_current_scene_uses_real_camera_parser_and_sdk_image_parts_without_contact_or_lease(self):
        station,frames=collect_station_inputs(api=self.api,cameras=self.cameras)
        self.assertEqual(len(frames),3);self.assertEqual(len(self.opened),3)
        text=json.dumps(station)
        for secret in ('never-model@example.test','secret-lease','secret-capability'):
            self.assertNotIn(secret,text)
        parts=sdk_prompt('Inspect the block',station,frames)
        self.assertEqual(parts[0],'Inspect the block')
        self.assertEqual(len(parts),5)
        self.assertTrue(all(p.mime_type=='image/jpeg' and p.data.startswith(b'\xff\xd8') for p in parts[2:]))
        self.assertEqual(station['calibration']['robot_id'],'yam-1')
        self.assertTrue(all('captured_at' in value for value in station['camera_frames'].values()))

    def test_stale_wrong_station_or_invalid_feedback_fails_before_image_requests(self):
        for field,value in (('observed_at',time.time()-11),('jetson_id','other-robot'),('left_gripper',-1e-16),('right_joints_deg',[True]*6)):
            original=deepcopy(self.observation);self.observation[field]=value
            with self.assertRaises(RuntimeError):collect_station_inputs(api=self.api,cameras=self.cameras)
            self.assertFalse(self.opened);self.observation=original

    def test_untrusted_image_origin_is_rejected_by_canonical_client_before_fetch(self):
        self.observation['images']['left']['url']='https://unrelated.invalid/private'
        with self.assertRaises(RuntimeError):collect_station_inputs(api=self.api,cameras=self.cameras)
        self.assertFalse(self.opened)
