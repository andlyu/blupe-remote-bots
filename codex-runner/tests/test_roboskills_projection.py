"""Cached same-ray evidence, never a calibration certificate or hardware run."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from unittest import TestCase,skipUnless
from unittest.mock import patch
import numpy as np
from remote_yam.api_depth import DepthSnapshot,factory_ray
from remote_yam.api_depth_set import ApiDepthSet,PairedDepthFrame
from remote_yam.roboskills_policy import RoboSkillsPolicy,RobotTools
from remote_yam.roboskills_perception import _project_factory

FIXTURE=json.loads((Path(__file__).parent/'fixtures/roboskills-point-correspondence.json').read_text())


class FactoryProjectionTests(TestCase):
    def test_inverse_matches_pinned_installed_sdk_deprojection_oracle(self):
        oracle=json.loads((Path(__file__).parent/'fixtures/realsense-deprojection-2.58.1.json').read_text())
        for row in oracle['rows']:
            with self.subTest(role=row['role'],pixel=row['pixel']):
                # Oracle rays are stored SDK float32 values. This arithmetic
                # tolerance is0.001pixel, not metric calibration accuracy.
                uv=_project_factory(row['profile'],np.array(row['ray'])*.3)
                np.testing.assert_allclose(uv,row['pixel'],atol=.001,rtol=0)


@skipUnless(importlib.util.find_spec('roboskills'),'Install the pinned runtime; required RoboSkills CI does so')
class ProjectionContract(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.source=ApiDepthSet('https://api.example','https://api.example')
        self.p=RoboSkillsPolicy(camera_source=None,recording_root=self.tmp.name,llm=lambda s,m:'')
        self.p.configure_perception(self.source,deepcopy(FIXTURE['calibration']))
        self.p._state={**deepcopy(FIXTURE['observation']),'episode_id':'offline','lease_id':'offline','settled':True}
        self.p._identity=('offline','offline');self.bot=RobotTools(self.p,'offline ray correspondence')
        now=time.time();report=self.p._perception.report;self.snapshots={}
        for role,cam in report['cameras'].items():
            w,h=cam['image_size'];depth=np.zeros((h,w),np.float32)
            if role in FIXTURE['patches']:
                q=FIXTURE['patches'][role];u,v=q['pixel'];depth[v-2:v+3,u-2:u+3]=q['depth_m']
            self.snapshots[role]=DepthSnapshot(np.zeros((h,w,3),np.uint8),depth,
                dict(camera=role,captured_at=now,calibration_id=report['calibration_id']),report,b'unit')
        self.source.snapshots=self.snapshots
        frames=[PairedDepthFrame(role,s.image(),now,now,'unit',report['calibration_id']) for role,s in self.snapshots.items()]
        with patch.object(self.source,'capture_for_policy',return_value=frames):self.bot.observe()

    def tearDown(self):self.tmp.cleanup()

    def test_actual_distinct_pixels_and_raw_foreground_background_evidence(self):
        for sample in FIXTURE['samples']:
            with self.subTest(camera=sample['to_camera']),patch.object(self.p,'_execute') as execute,patch.object(self.source,'capture_for_policy') as capture:
                result=self.bot.project_point(sample['point_right_base_m'],arm='right',camera=sample['to_camera'])
                np.testing.assert_allclose(result['pixel'],sample['projected_pixel'],atol=1e-5)
                self.assertEqual(result['nearest_pixel'],sample['nearest_pixel'])
                self.assertAlmostEqual(result['expected_optical_z_m'],sample['expected_optical_z_m'],places=10)
                self.assertTrue(result['depth_sample']['available'])
                observed=sample['retained_patch_median_optical_z_m']
                self.assertAlmostEqual(result['depth_sample']['optical_z_m'],observed,places=8)
                self.assertAlmostEqual(result['measured_minus_expected_optical_z_m'],observed-sample['expected_optical_z_m'],places=8)
                self.assertNotIn('calibration_valid',result);self.assertNotIn('object_visible',result)
                execute.assert_not_called();capture.assert_not_called()

    def test_both_arm_frames_describe_the_same_optical_ray(self):
        point=np.array(FIXTURE['samples'][0]['point_right_base_m']);left=point.copy();left[1]-=.5
        for camera in ('top','left','right'):
            with self.subTest(camera=camera):
                a=self.bot.project_point(point,arm='right',camera=camera)
                b=self.bot.project_point(left,arm='left',camera=camera)
                np.testing.assert_allclose(a['pixel'],b['pixel'],atol=1e-6)
                self.assertAlmostEqual(a['expected_optical_z_m'],b['expected_optical_z_m'],places=10)

    def test_factory_ray_roundtrip_endpoints_interior_and_outside(self):
        for camera in ('top','left','right'):
            cam=self.p._perception.report['cameras'][camera];profile=cam['depth_intrinsics']
            T=self.p._perception.transforms[camera]['right'];w,h=cam['image_size']
            for u,v in ((0,0),(w-1,h-1),(0,h-1),(w-1,0),(w/2,h/2),(-1,0),(w,h/2),(0,h)):
                with self.subTest(camera=camera,pixel=(u,v)):
                    point=(T@np.r_[factory_ray(profile,u,v)*.4,1])[:3]
                    result=self.bot.project_point(point,arm='right',camera=camera)
                    np.testing.assert_allclose(result['pixel'],[u,v],atol=1e-4)
                    inside=0<=u<w and 0<=v<h
                    self.assertEqual(result['inside_image'],inside)
                    self.assertEqual(result['nearest_pixel'],[int(u),int(v)] if inside else None)

    def test_missing_or_noisy_depth_does_not_invent_visibility(self):
        point=FIXTURE['samples'][0]['point_right_base_m'];depth=self.snapshots['right'].depth
        for kind in ('missing','mixed_surfaces'):
            with self.subTest(kind=kind):
                depth[:]=0
                if kind=='mixed_surfaces':depth[229:234,317:322]=np.where(np.indices((5,5))[0]%2,.1,.2)
                result=self.bot.project_point(point,arm='right',camera='right')
                self.assertFalse(result['depth_sample']['available'])
                self.assertIsNone(result['measured_minus_expected_optical_z_m'])
                self.assertIn('reason',result['depth_sample'])

    def test_invalid_point_and_frame_inputs_never_dispatch(self):
        bad=([],[1,2],[1,2,3,4],[True,0,1],['1',0,1],[np.nan,0,1],[0,np.inf,1],None,{'x':1})
        for point in bad:
            with self.subTest(point=str(point)),patch.object(self.p,'_execute') as execute:
                with self.assertRaises(ValueError):self.bot.project_point(point,arm='right')
                execute.assert_not_called()
        for kwargs in ({'arm':'other'},{'arm':None},{'arm':True},{'arm':[]},
                       {'arm':'right','camera':'other'},{'arm':'right','camera':[]}):
            with self.subTest(kwargs=kwargs),patch.object(self.p,'_execute') as execute:
                with self.assertRaises(ValueError):self.bot.project_point([0,0,1],**kwargs)
                execute.assert_not_called()

    def test_behind_camera_and_unsupported_profile_are_explicit(self):
        T=self.p._perception.transforms['right']['right']
        for z in (0.,-.1):
            with self.subTest(z=z):
                point=(T@np.array([0,0,z,1]))[:3]
                with self.assertRaises(ValueError):self.bot.project_point(point,arm='right',camera='right')
        del self.p._perception.report['cameras']['right']['depth_intrinsics']
        with self.assertRaisesRegex(ValueError,'factory'):self.bot.project_point(FIXTURE['samples'][0]['point_right_base_m'],arm='right',camera='right')

    def test_numerical_near_plane_exact_boundary_and_neighbours(self):
        # Synthetic identity isolates perspective arithmetic from rigid-transform
        # roundoff at a1nanometre boundary; no physical range claim is made.
        self.p._perception.transforms['top']['right']=np.eye(4)
        for z in (0.,-1.,np.nextafter(1e-9,0),1e-9):
            with self.subTest(z=z):
                with self.assertRaises(ValueError):self.bot.project_point([0.,0.,z],arm='right')
        for z in (np.nextafter(1e-9,np.inf),1e-8):
            with self.subTest(z=z):
                self.assertEqual(self.bot.project_point([0.,0.,z],arm='right')['expected_optical_z_m'],z)

    def test_result_is_serializable_and_cannot_mutate_pose_or_quality(self):
        state=deepcopy(self.p._state);quality=deepcopy(self.p._perception.report['quality'])
        before=self.p._geometry.ik.data.qpos.copy()
        result=self.bot.project_point(FIXTURE['samples'][0]['point_right_base_m'],arm='right',camera='right')
        json.dumps(result,allow_nan=False)
        self.assertEqual(result['captured_at'],self.snapshots['right'].metadata['captured_at'])
        self.assertEqual(self.p._state,state)
        np.testing.assert_array_equal(before,self.p._geometry.ik.data.qpos)
        result['quality']['status']='changed by caller'
        self.assertEqual(self.p._perception.report['quality'],quality)

    def remember_source(self,pixel=None):
        sample=FIXTURE['samples'][0]
        result=dict(camera='top',pixel=pixel or sample['from_pixel'],
            captured_at=123.,points_base_m={'right':sample['point_right_base_m'].copy()})
        with patch.object(self.p._perception,'measure',return_value=result):
            self.bot.measure_depth(*result['pixel'])
        return result

    def recapture(self):
        now=time.time()
        for snapshot in self.snapshots.values():snapshot.metadata['captured_at']=now
        self.source.snapshots=self.snapshots
        frames=[PairedDepthFrame(role,s.image(),now,now,'unit',self.p._perception.report['calibration_id']) for role,s in self.snapshots.items()]
        with patch.object(self.source,'capture_for_policy',return_value=frames):self.bot.observe()

    def test_next_observation_exposes_historical_correspondence_without_motion(self):
        reference=self.remember_source();reference['points_base_m']['right'][0]=999.
        self.p._perception.invalidate();self.p._state['step_id']+=1
        self.assertNotIn('surface_references',self.p._perception.summary())
        with patch.object(self.p,'_execute') as execute:self.recapture()
        execute.assert_not_called()
        summary=self.bot.status()['perception'];row=summary['surface_references'][0]
        self.assertEqual(row['source_step_id'],56)
        self.assertEqual(row['source_captured_at'],123.)
        self.assertEqual(row['source_pixel'],[310,83])
        projected=row['projections']['right']
        np.testing.assert_allclose(projected['pixel'],[318.6812800446739,231.26023722496032],atol=1e-5)
        self.assertLess(projected['measured_minus_expected_optical_z_m'],-.015)
        self.assertIn('NOT tracked',summary['reference_scope'])
        self.assertFalse(self.bot.motion_failure)

    def test_reference_history_is_bounded_distinct_and_does_not_cross_lease(self):
        for i in range(7):self.remember_source([10+i,20])
        rows=self.p._perception.summary()['surface_references']
        self.assertEqual(len(rows),4)
        self.assertEqual([r['source_pixel'] for r in rows],[[13,20],[14,20],[15,20],[16,20]])
        self.remember_source([16,20]);self.assertEqual(len(self.p._perception.references),4)
        self.p._identity=('next_episode','next_lease')
        self.p._state.update(episode_id='next_episode',lease_id='next_lease')
        self.recapture()
        self.assertNotIn('surface_references',self.p._perception.summary())
        self.assertFalse(self.p._perception.references)

    def test_stale_cursor_invalidation_stop_and_terminal_motion_remain_enforced(self):
        point=FIXTURE['samples'][0]['point_right_base_m']
        self.p._state['step_id']+=1
        with self.assertRaisesRegex(ValueError,'observe'):self.bot.project_point(point,arm='right',camera='right')
        self.p._state['step_id']-=1
        self.bot.motion_failure='Physical execution uncertain'
        with self.assertRaisesRegex(RuntimeError,'uncertain'):self.bot.project_point(point,arm='right')
        self.bot.motion_failure=None
        with patch.object(self.p,'_check_cancelled',side_effect=RuntimeError('stopped')):
            with self.assertRaisesRegex(RuntimeError,'stopped'):self.bot.project_point(point,arm='right')
        self.p._perception.invalidate()
        with self.assertRaisesRegex(ValueError,'observe'):self.bot.project_point(point,arm='right')
