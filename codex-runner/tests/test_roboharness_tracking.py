from pathlib import Path
from copy import deepcopy
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
import cv2

from remote_yam.roboharness_tracking import KeypointTracker
from remote_yam.roboharness_control import InputRejected


def snapshot(captured_at=100,calibration='calibration',scope=True,age=.2):
    rng=np.random.default_rng(4)
    s=SimpleNamespace(rgb=rng.integers(0,256,(80,100,3),dtype=np.uint8),
        metadata=dict(camera='top',calibration_id=calibration,sensor_serial='synthetic',captured_at=captured_at),
        age=lambda:age)
    def measure(u,v,*,arm):
        if scope:return {'point_base_m':[u*.001,v*.001,.2]}
        return {'point_camera_m':[u*.001,v*.001,.2]}
    s.measure=measure;return s


class TrackingTests(unittest.TestCase):
    def test_normalized_endpoints_and_both_arm_projection(self):
        t=KeypointTracker();t.update(snapshot());t.register('point_0',1000,0)
        np.testing.assert_allclose(t.points['point_0'],[99,0])
        p=t.measure();self.assertEqual(p['point_0']['left'],[.099,0,.2]);self.assertEqual(p['point_0']['right'],[.099,0,.2])

    def test_lost_flow_is_not_silently_reacquired_or_guessed(self):
        t=KeypointTracker();t.update(snapshot());t.register('point_0',500,500)
        with patch('remote_yam.roboharness_tracking.cv2.calcOpticalFlowPyrLK',return_value=(None,None,None)):
            t.update(snapshot(captured_at=101))
        self.assertEqual(t.measure(),{});self.assertIn('point_0',t.errors)

    def test_bidirectional_flow_preserves_identity_and_updates_pixel(self):
        t=KeypointTracker();t.update(snapshot());t.register('point_0',500,500)
        original=t.points['point_0'].copy();moved=original+np.array([1,0])
        with patch('remote_yam.roboharness_tracking.cv2.calcOpticalFlowPyrLK',side_effect=[
            (moved.astype('float32').reshape(1,1,2),np.ones((1,1),dtype='uint8'),None),
            (original.reshape(1,1,2),np.ones((1,1),dtype='uint8'),None)]):t.update(snapshot(captured_at=101))
        np.testing.assert_allclose(t.points['point_0'],moved);self.assertIn('point_0',t.measure())

    def test_changed_calibration_stale_depth_and_optical_only_cannot_target_arm(self):
        t=KeypointTracker();t.update(snapshot());t.register('point_0',100,100)
        with self.assertRaises(InputRejected):t.update(snapshot(calibration='changed'))
        self.assertEqual(t.points,{})
        for sample in (snapshot(age=3),snapshot(scope=False)):
            t=KeypointTracker();t.update(sample);t.register('point_0',100,100)
            if sample.age()>2:
                with self.assertRaises(InputRejected):t.measure()
            else:self.assertEqual(t.measure(),{});self.assertIn('No calibrated arm-base',t.errors['point_0'])

    def test_actual_low_texture_block_survives_camera_codec_variation(self):
        fixtures=Path(__file__).parent/'fixtures'
        before=snapshot();before.rgb=cv2.cvtColor(cv2.imread(str(fixtures/'roboharness-hover003-initial.png')),cv2.COLOR_BGR2RGB)
        after=snapshot(captured_at=101);after.rgb=cv2.cvtColor(cv2.imread(str(fixtures/'roboharness-hover003-near-rejection.png')),cv2.COLOR_BGR2RGB)
        t=KeypointTracker();t.update(before);t.register('point_0',454,647)
        original=t.points['point_0'].copy();t.update(after)
        self.assertIn('point_0',t.points)
        np.testing.assert_allclose(t.points['point_0'],original,atol=1.)
        self.assertIn('point_0',t.measure())

    def test_occluded_actual_block_is_rejected_without_reacquisition(self):
        fixtures=Path(__file__).parent/'fixtures'
        before=snapshot();before.rgb=cv2.cvtColor(cv2.imread(str(fixtures/'roboharness-hover003-initial.png')),cv2.COLOR_BGR2RGB)
        after=snapshot(captured_at=101);after.rgb=before.rgb.copy();after.rgb[250:370,230:350]=0
        t=KeypointTracker();t.update(before);t.register('point_0',454,647);t.update(after)
        self.assertEqual(t.points,{})
        self.assertEqual(t.measure(),{})
        self.assertIn('point_0',t.errors)

    def test_invalid_point_ids_and_pixels_are_strict(self):
        t=KeypointTracker();t.update(snapshot())
        for point,u,v in [('point_16',0,0),('x',0,0),('point_0',-1e-15,0),('point_0',1000+1e-10,0),('point_0',True,0)]:
            with self.subTest(point=point,u=u,v=v),self.assertRaises(InputRejected):t.register(point,u,v)


if __name__=='__main__':unittest.main()
