"""Measured face orientation, including the actual wrong-face selection."""
from pathlib import Path
import importlib.util,json
from unittest import TestCase,skipUnless
from unittest.mock import patch
import numpy as np
from remote_yam import roboskills_perception as perception
import test_roboskills_perception as fixtures

RECORDED=json.loads((Path(__file__).parent/'fixtures/roboskills-measured-faces.json').read_text())
OUTLIERS=json.loads((Path(__file__).parent/'fixtures/roboskills-plane-outliers.json').read_text())

class SurfaceGeometry(TestCase):
    def test_actual_bad_depth_pixels_do_not_rotate_the_dominant_face(self):
        points=np.array(OUTLIERS['points_base_m']);fit=perception._surface_plane(points)
        # Preserve the exact raw result, including its misleading normal.
        np.testing.assert_allclose(fit['normal_base'],OUTLIERS['raw_fit']['normal_base'],atol=1e-12)
        self.assertGreater(fit['abs_residual_95_m'],.006)
        dominant=fit['dominant_plane'];self.assertTrue(dominant['available'])
        self.assertGreater(dominant['inlier_fraction'],.9)
        self.assertLess(dominant['rms_residual_m'],.0015)
        self.assertGreater(abs(np.array(dominant['normal_base'])@OUTLIERS['same_view_table_normal_base']),.95)
        self.assertEqual(dominant['inlier_count']+dominant['outlier_count'],len(points))
        self.assertEqual(dominant['distance_threshold_m'],.002)
        residual=np.abs((points-np.array(dominant['center_m']))@dominant['normal_base'])
        self.assertEqual(np.flatnonzero(residual>.002).tolist(),dominant['outlier_indices'])
        bad=set(np.flatnonzero(points[:,2]<-.01))
        self.assertTrue(bad.issubset(dominant['outlier_indices']))
        self.assertIn('not',dominant['scope'])

    def test_dominant_plane_is_rigid_invariant_and_retains_outlier_indices(self):
        points=np.array(OUTLIERS['points_base_m']);a=.73
        R=np.array([[np.cos(a),0,np.sin(a)],[0,1,0],[-np.sin(a),0,np.cos(a)]])
        original=perception._surface_plane(points)['dominant_plane']
        changed=perception._surface_plane(points@R.T+[.4,-.3,.2])['dominant_plane']
        self.assertEqual(original['outlier_indices'],changed['outlier_indices'])
        self.assertAlmostEqual(original['rms_residual_m'],changed['rms_residual_m'],places=12)
        self.assertAlmostEqual(abs(np.array(changed['normal_base'])@(R@np.array(original['normal_base']))),1.,places=10)

    def test_two_equal_surfaces_do_not_pass_dominant_coverage(self):
        x,y=np.meshgrid(np.linspace(-.015,.015,16),np.linspace(-.01,.01,8))
        plane=np.column_stack((x.ravel(),y.ravel(),np.zeros(x.size)))
        points=np.vstack((plane,plane+[0,0,.01]))
        fit=perception._surface_plane(points);dominant=fit['dominant_plane']
        self.assertFalse(dominant['available'])
        self.assertLess(dominant['inlier_fraction'],.75)
        self.assertNotIn('normal_base',dominant)
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

    def test_tool_reports_actual_excluded_pixels_without_changing_depth_coverage(self):
        self.capture();self.source.snapshots['top'].depth[1,1]=1.2
        with patch.object(self.policy,'_execute') as execute:
            result=self.bot.localize_object('plane with one bad depth',np.ones((6,8),bool))
        execute.assert_not_called();self.assertEqual(result['valid_depth_count'],48)
        for arm in ('left','right'):
            fit=result['surfaces_in_arm_bases'][arm]['plane_fit']['dominant_plane']
            self.assertTrue(fit['available']);self.assertEqual(fit['outlier_count'],1)
            self.assertEqual(fit['outlier_pixels'],[[1,1]])

    def test_shape_does_not_bypass_mask_cursor_or_stop_checks(self):
        self.capture()
        with patch.object(self.policy,'_execute') as execute:
            with self.assertRaises(ValueError):self.bot.localize_object('bad',np.ones((1,1),bool))
            self.policy._state['step_id']+=1
            with self.assertRaises(ValueError):self.bot.localize_object('stale',np.ones((6,8),bool))
            self.policy._state['step_id']-=1;self.policy._failure='Native Stop retained'
            with self.assertRaisesRegex(RuntimeError,'Stop'):self.bot.localize_object('stopped',np.ones((6,8),bool))
            execute.assert_not_called()
