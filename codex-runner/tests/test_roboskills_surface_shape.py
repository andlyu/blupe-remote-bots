"""Measured face orientation, including the actual wrong-face selection."""
from pathlib import Path
import importlib.util,json
from unittest import TestCase,skipUnless
from unittest.mock import patch
import numpy as np
from remote_yam import roboskills_perception as perception
import test_roboskills_perception as fixtures

RECORDED=json.loads((Path(__file__).parent/'fixtures/roboskills-measured-faces.json').read_text())

class SurfaceGeometry(TestCase):
    def test_actual_image_top_face_is_not_table_parallel(self):
        fits={k:perception._surface_plane(np.array(v)) for k,v in RECORDED['points_right_base_m'].items()}
        normal=lambda label:np.array(fits[label]['normal_base'])
        angle=lambda a,b:np.rad2deg(np.arccos(np.clip(abs(normal(a)@normal(b)),0,1)))
        self.assertGreater(angle('table','top'),75)
        self.assertLess(angle('table','front'),20)
        for label in ('top','front'):
            self.assertTrue(fits[label]['available'])
            self.assertLess(fits[label]['rms_residual_m'],.002)
        self.assertIn('not',fits['top']['scope'])

    def test_common_rigid_transform_preserves_relative_geometry(self):
        clouds=RECORDED['points_right_base_m'];a=.73
        R=np.array([[np.cos(a),0,np.sin(a)],[0,1,0],[-np.sin(a),0,np.cos(a)]])
        original={k:perception._surface_plane(np.array(v)) for k,v in clouds.items()}
        changed={k:perception._surface_plane(np.array(v)@R.T+[.4,-.3,.2]) for k,v in clouds.items()}
        for label in clouds:
            np.testing.assert_allclose(abs(np.array(changed[label]['normal_base'])@(R@np.array(original[label]['normal_base']))),1.,atol=1e-10)
            self.assertAlmostEqual(original[label]['rms_residual_m'],changed[label]['rms_residual_m'],places=12)

    def test_line_point_or_too_few_samples_do_not_invent_normal(self):
        for points in (np.zeros((12,3)),np.column_stack((np.arange(12),np.zeros((12,2)))),np.zeros((8,3))):
            with self.subTest(shape=points.shape):
                fit=perception._surface_plane(points)
                self.assertFalse(fit['available']);self.assertNotIn('normal_base',fit)

    def test_nonplanar_cloud_retains_residual_instead_of_certifying_flatness(self):
        points=np.array([[x,y,z] for x in (-.01,.01) for y in (-.01,.01) for z in (-.01,.01)]*2)
        fit=perception._surface_plane(points)
        self.assertGreater(fit['rms_residual_m'],.005)
        self.assertIn('not',fit['scope'])

@skipUnless(importlib.util.find_spec('roboskills'),'Install the pinned RoboSkills runtime')
class SurfaceToolPath(TestCase):
    setUp=fixtures.Tests.setUp
    tearDown=fixtures.Tests.tearDown
    capture=fixtures.Tests.capture

    def test_existing_localize_returns_shape_from_paired_depth_both_arms_without_motion(self):
        self.capture();mask=np.ones((6,8),bool)
        with patch.object(self.policy,'_execute') as execute:
            result=self.bot.localize_object('visible plane',mask)
        execute.assert_not_called()
        for arm in ('left','right'):
            fit=result['surfaces_in_arm_bases'][arm]['plane_fit']
            self.assertTrue(fit['available']);self.assertLess(fit['rms_residual_m'],1e-10)
            np.testing.assert_allclose(abs(np.array(fit['normal_base'])),[0,0,1],atol=1e-10)
            self.assertEqual(fit['sample_count'],48)

    def test_shape_does_not_bypass_mask_cursor_or_stop_checks(self):
        self.capture()
        with patch.object(self.policy,'_execute') as execute:
            with self.assertRaises(ValueError):self.bot.localize_object('bad',np.ones((1,1),bool))
            self.policy._state['step_id']+=1
            with self.assertRaises(ValueError):self.bot.localize_object('stale',np.ones((6,8),bool))
            self.policy._state['step_id']-=1;self.policy._failure='Native Stop retained'
            with self.assertRaisesRegex(RuntimeError,'Stop'):self.bot.localize_object('stopped',np.ones((6,8),bool))
            execute.assert_not_called()
