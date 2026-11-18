"""Real MuJoCo FK, articulated fingers, calibration and Google IK; no I/O."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import mujoco
import numpy as np

ROOT = Path(os.environ.get('GEMINI_TEST_RUNNER_ROOT', Path(__file__).resolve().parents[3]))
INTEGRATION = Path(__file__).resolve().parents[1]
SKILLS = Path(os.environ.get('GEMINI_SKILLS_ROOT', '/opt/robotics/plugins/robotics/skills'))
sys.path.insert(0, str(INTEGRATION / 'backend'))
from yam1_scene import Yam1Scene, build_xml, checked_bytes, INSTALLED_SHA256
from yam1_kinematics import Yam1Kinematics


class Yam1SceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calibration = json.loads((INTEGRATION / 'tests/fixtures/yam1-calibration.json').read_text())
        cls.assets = INTEGRATION / 'assets/linear4310'
        cls.scene = Yam1Scene(ROOT, cls.assets, cls.calibration)
        cls.reference = mujoco.MjModel.from_xml_path(str(ROOT / 'models/yam_bimanual/scene.xml'))
        for arm, sign in (('left', 1), ('right', -1)):
            cls.reference.body_pos[cls.reference.body(arm + '_link1').id, 1] = sign * .25
        cls.google = Yam1Kinematics(cls.scene, SKILLS).google

    def setUp(self):
        self.scene.set_configuration({'left': [.2, 1.6, 1.2, -.8, .1, -.2],
                                      'right': [-.2, 1.5, 1.3, -.9, -.1, .3]},
                                     {'left': .9992793312193716, 'right': .412345678})

    def test_native_fk_both_arms_and_named_indices_match_canonical(self):
        rng = np.random.default_rng(4301)
        low = np.asarray(self.scene.safety['joint_lower_rad'])
        high = np.asarray(self.scene.safety['joint_upper_rad'])
        self.assertEqual(self.scene.model.nq, 16)
        self.assertEqual(self.scene.arm_qpos['right'], list(range(8, 14)))
        for _ in range(40):
            q = rng.uniform(low, high)
            self.scene.set_configuration({'left': q[:6], 'right': q[6:]},
                                         {'left': float(rng.uniform()), 'right': float(rng.uniform())})
            d = mujoco.MjData(self.reference); d.qpos[:] = q
            mujoco.mj_forward(self.reference, d)
            for arm in ('left', 'right'):
                site = self.scene.model.site(arm + '_installed_grasp_site').id
                body = self.reference.body(arm + '_grasp').id
                np.testing.assert_allclose(self.scene.data.site_xpos[site], d.xpos[body], atol=2e-12, rtol=0)
                np.testing.assert_allclose(self.scene.data.site_xmat[site], d.xmat[body], atol=2e-12, rtol=0)
        # No robot transport exists in this scene adapter.
        self.assertFalse(self.scene.receipt()['physical'])

    def test_articulated_finger_travel_axis_and_tcp_are_exact(self):
        q = {arm: self.scene.data.qpos[self.scene.arm_qpos[arm]].copy() for arm in ('left', 'right')}
        samples = {}
        for g in (0., .375, .9992793312193716, 1.):
            self.scene.set_configuration(q, {'left': g, 'right': g})
            for arm in ('left', 'right'):
                site = self.scene.model.site(arm + '_installed_grasp_site').id
                rotation = self.scene.data.site_xmat[site].reshape(3, 3)
                fingers = [self.scene.data.xpos[self.scene.model.body(arm + '_installed_tip_' + finger).id].copy()
                           for finger in ('left', 'right')]
                if g == 0:
                    samples[arm] = (self.scene.data.site_xpos[site].copy(), fingers)
                else:
                    np.testing.assert_allclose(self.scene.data.site_xpos[site], samples[arm][0], atol=1e-12, rtol=0)
                    for current, initial in zip(fingers, samples[arm][1]):
                        travel = rotation.T @ (current - initial)
                        self.assertAlmostEqual(float(np.linalg.norm(travel)), g * .0475, places=10)
                        self.assertLess(abs(travel[0]), 3e-7)
                        self.assertLess(abs(travel[2]), 3e-7)
                        self.assertAlmostEqual(abs(travel[1]), g * .0475, places=8)

    def test_pinhole_intrinsics_and_cv_camera_poses_match_calibration(self):
        m, d = self.scene.model, self.scene.data
        for name in ('top', 'left', 'right'):
            camera = self.calibration['cameras'][name]
            cid = m.camera(name).id
            k, *_ = self.google.camera_intrinsics_from_model(m, cid, *camera['image_size'])
            np.testing.assert_allclose(k, camera['K'], atol=4e-5, rtol=0)
            actual = self.google.camera_world_pose_opencv(d, cid)
            if name == 'top':
                expected = np.array(camera['T_base_camera']['left']); expected[1, 3] += .25
            else:
                grasp = m.body(name + '_grasp').id
                transform = np.eye(4); transform[:3, :3] = d.xmat[grasp].reshape(3, 3); transform[:3, 3] = d.xpos[grasp]
                expected = transform @ np.asarray(camera['T_grasp_camera'])
            np.testing.assert_allclose(actual, expected, atol=2e-12, rtol=0)

    def test_installed_variant_and_calibration_drift_reject_before_compile(self):
        checked_bytes(self.assets / 'linear_4310.xml', INSTALLED_SHA256)
        for update in ('offset', 'model', 'top'):
            c = deepcopy(self.calibration)
            if update == 'offset': c['native_joint_calibration']['additional_offsets_rad']['left'][0] = 1e-10
            elif update == 'model': c['kinematics']['robot_model_sha256'] = 'wrong-model'
            else: c['cameras']['top']['T_base_camera']['right'][0][3] += .001
            with self.assertRaises(ValueError): build_xml(ROOT, self.assets, c)
        before = self.scene.data.qpos.copy()
        with self.assertRaises(ValueError):
            self.scene.set_configuration({'left': [float('nan')] * 6, 'right': [0] * 6}, {'left': 0., 'right': 0.})
        np.testing.assert_array_equal(before, self.scene.data.qpos)

    def test_google_generic_ik_uses_correct_arm_and_checks_residuals(self):
        adapter = Yam1Kinematics(self.scene, SKILLS)
        for arm in ('left', 'right'):
            context = self.scene.data.qpos.copy()
            target_data = mujoco.MjData(self.scene.model); target_data.qpos[:] = context
            target_data.qpos[self.scene.arm_qpos[arm][0]] += .02
            mujoco.mj_forward(self.scene.model, target_data)
            site = self.scene.model.site(arm + '_installed_grasp_site').id
            p = target_data.site_xpos[site].copy(); r = target_data.site_xmat[site].reshape(3, 3).copy()
            solved = adapter.solve(arm, p, target_rot_world=r)
            self.assertEqual(solved.shape, (6,))
            np.testing.assert_array_equal(self.scene.data.qpos, context)
            # Exercise the upstream best-effort-return boundary: a returned
            # vector is not accepted without checking achieved constraints.
            with patch.object(adapter.google, 'solve_site_ik', return_value=context[self.scene.arm_qpos[arm]]):
                with self.assertRaisesRegex(ValueError, 'constraints unmet'):
                    adapter.solve(arm, p + [.1, 0, 0], target_rot_world=r)
            with self.assertRaises(ValueError): adapter.solve(arm, [float('nan'), 0, 0])
            with self.assertRaises(ValueError): adapter.solve(arm, p, target_rot_world=np.diag([1, 1, -1]))


if __name__ == '__main__':
    unittest.main()
