"""Coordinate/observation regressions; synthetic data, no physical qualification."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch
import time
import importlib.util
import numpy as np

from remote_yam.api_depth import DepthSnapshot
from remote_yam.api_depth_set import ApiDepthSet, PairedDepthFrame
from remote_yam.roboskills_policy import RoboSkillsPolicy, RobotTools
from test_roboskills_policy import observation


@skipUnless(importlib.util.find_spec('roboskills'),'Install the optional pinned RoboSkills runtime')
class Tests(TestCase):
    def setUp(self):
        self.root=TemporaryDirectory()
        self.source=ApiDepthSet('https://api.example','https://api.example')
        left=np.eye(4);left[:3,3]=[.1,.2,.3]
        right=left.copy();right[1,3]+=.5
        camera=dict(image_size=[8,6],K=[[100.,0,4],[0,100.,3],[0,0,1]],
                    distortion=[0.]*5,distortion_model='opencv_brown_conrady')
        self.report=dict(schema_version=1,robot_id='yam-1',calibration_id='test',
            base_geometry=dict(spacing_m=.5),quality=dict(status='experimental',extrinsics_provisional=True),
            cameras={r:dict(deepcopy(camera),**(dict(T_base_camera=dict(left=left.tolist(),right=right.tolist()))
                         if r=='top' else dict(T_grasp_camera=np.eye(4).tolist()))) for r in ('top','left','right')})
        self.policy=RoboSkillsPolicy(camera_source=self.source,recording_root=self.root.name,llm=lambda s,m:'')
        self.policy.configure_perception(self.source,self.report)
        self.policy._state=observation();self.policy._identity=('ep_unit','lease_unit')
        self.bot=RobotTools(self.policy,'Stack blocks')

    def tearDown(self):self.root.cleanup()

    def capture(self, report=None):
        report=self.report if report is None else report
        self.source.snapshots={r:DepthSnapshot(np.zeros((6,8,3),np.uint8),np.full((6,8),.6,np.float32),
            dict(camera=r,captured_at=time.time(),calibration_id='test'),report,b'fixture') for r in ('top','left','right')}
        frames=[PairedDepthFrame(r,s.image(),time.time(),s.metadata['captured_at'],'sensor','test')
                for r,s in self.source.snapshots.items()]
        with patch.object(self.source,'capture_for_policy',return_value=frames):return self.bot.observe()

    def test_paired_pixels_and_arm_frames_with_measured_wrist_fk(self):
        images=self.capture()
        self.assertEqual(set(images),{'top','left','right'})
        q=self.bot.measure_depth(4,3,radius=0)
        np.testing.assert_allclose(q['points_base_m']['left'],[.1,.2,.9],atol=1e-7)
        np.testing.assert_allclose(q['points_base_m']['right'],[.1,.7,.9],atol=1e-7)
        self.assertEqual(q['calibration_id'],'test')
        self.assertEqual(self.policy._geometry.ik.base_spacing_m,.5)
        xyz,rotation=self.policy._geometry.ik._poses()[0]
        expected=xyz-self.policy._geometry.bases[1]+rotation @ [0,0,.6]
        np.testing.assert_allclose(self.bot.measure_depth(4,3,'left',0,'right')['point_base_m'],expected,atol=1e-7)
        self.assertEqual(len(list(Path(self.root.name).rglob('rgbd-*.npz'))),3)

    def test_arrays_are_copies_and_mask_localization_uses_real_depth(self):
        self.capture()
        self.bot.rgbd()['depth_m'][:]=10
        mask=np.zeros((6,8),bool);mask[2:5,3:6]=True
        location=self.bot.localize_object('test object',mask)
        np.testing.assert_allclose(location['surfaces_in_arm_bases']['left']['center_m'],[.1,.2,.9],atol=1e-7)
        self.assertEqual(location['valid_depth_count'],9)
        self.assertTrue(location['quality']['extrinsics_provisional'])
        with self.assertRaisesRegex(ValueError,'boolean'):self.bot.localize_object('object',mask.astype(int))
        self.source.snapshots['top'].depth[:]=0
        with self.assertRaisesRegex(ValueError,'little measured'):self.bot.localize_object('object',mask)

    def test_motion_or_cursor_change_invalidates_measurements(self):
        self.capture();self.policy._state['step_id']+=1
        with self.assertRaisesRegex(ValueError,'observe'):self.bot.measure_depth(4,3)
        self.policy._state['step_id']-=1
        self.policy._perception.invalidate()
        with self.assertRaisesRegex(ValueError,'observe'):self.bot.measure_depth(4,3)

    def test_changed_calibration_rejects_entire_observation(self):
        self.capture()
        changed=deepcopy(self.report);changed['calibration_id']='replacement'
        with self.assertRaisesRegex(ValueError,'changed'):self.capture(changed)
        with self.assertRaisesRegex(ValueError,'observe'):self.bot.measure_depth(4,3)

    def test_terminal_explanation_and_visual_assessment_are_not_native_score(self):
        result=self.bot.finish('No stable grasp was observed.',False)
        self.assertEqual(result['reason'],'No stable grasp was observed.')
        self.assertEqual(result['task_status'],'reported_failure')
        self.assertIsNone(result['success'])
        self.assertFalse(result['task_success_reported'])

    def test_finish_without_motion_is_explicit(self):
        self.assertEqual(self.bot.finish()['task_status'],'not_attempted')
