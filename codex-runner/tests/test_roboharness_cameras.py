"""Camera aggregation uses only overhead depth and fails closed on source ages."""
import json
import time
import unittest
from unittest.mock import Mock,patch

from remote_yam.cameras import CameraFrame,CameraUnavailable
from remote_yam.roboharness_cameras import RoboHarnessCameras
from test_roboharness_control import observation
from test_roboharness_policy import Snapshot,REPORT

API='https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com'
ROBOT='robot-ba8413962083809c'


class CameraSetTests(unittest.TestCase):
    def source(self,*,depth_age=0,wrist_stamp='fresh',feedback_age=.5):
        source=RoboHarnessCameras(API,robot_id=ROBOT)
        obs={**observation(),'observed_at':time.time()-feedback_age,'mode':'READY'}
        snapshot=Snapshot('top',{})
        snapshot.metadata['captured_at']=time.time()-depth_age
        source.apis['top'].read=Mock(return_value=json.dumps(REPORT).encode())
        source.apis['top'].capture=Mock(return_value=snapshot)
        for role in ('left','right'):source.apis[role].capture=Mock(side_effect=AssertionError('Unused wrist depth was fetched'))
        def wrist(role,url):
            self.assertEqual(url,API+'/v1/robots/'+ROBOT+'/cameras/'+role+'.jpg')
            stamp=time.time()-.01 if wrist_stamp=='fresh' else None if wrist_stamp is None else time.time()-wrist_stamp
            return CameraFrame(role,b'\xff\xd8synthetic\xff\xd9',time.time(),source_captured_at=stamp)
        source.wrist_rgb.fetch=Mock(side_effect=wrist)
        return source,obs

    def test_only_overhead_rgbd_and_both_timestamped_wrist_rgb_views(self):
        source,obs=self.source();frames=source.capture(obs)
        self.assertEqual([f.name for f in frames],['top','left','right'])
        self.assertEqual(set(source.snapshots),{'top'})
        self.assertTrue(frames[0].summary()['paired_with_depth'])
        self.assertEqual(source.wrist_rgb.fetch.call_count,2)
        for role in ('left','right'):source.apis[role].capture.assert_not_called()

    def test_two_second_source_limit_and_post_settle_cutoff_remain_enforced(self):
        for kwargs in ({'depth_age':2.01,'feedback_age':5},{'wrist_stamp':2.01,'feedback_age':5},
                       {'wrist_stamp':None},{'depth_age':1,'feedback_age':.5}):
            with self.subTest(kwargs=kwargs):
                source,obs=self.source(**kwargs)
                with self.assertRaises(CameraUnavailable):source.capture(obs)
                self.assertEqual(source.snapshots,{})

    def test_robot_mismatch_is_zero_reads_and_cancelled_set_is_not_retained(self):
        source,obs=self.source()
        with self.assertRaises(ValueError):source.capture({**obs,'robot_id':'other'})
        source.apis['top'].read.assert_not_called();source.wrist_rgb.fetch.assert_not_called()
        source._cancelled=lambda:True
        with self.assertRaisesRegex(RuntimeError,'cancelled'):source.capture(obs)
        self.assertEqual(source.snapshots,{})


if __name__=='__main__':unittest.main()
