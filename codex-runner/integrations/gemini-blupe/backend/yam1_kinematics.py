"""Google's published generic site IK on the installed bimanual YAM1 model."""
import hashlib
import importlib.util
from pathlib import Path

import mujoco
import numpy as np

from yam1_scene import ARMS

HELPER_SHA256 = '95a7a25ef14ec0e46480bd254f871981675e7c17168e4d2458048311f6a20961'


def robotics_helper(skills_root):
    path = Path(skills_root) / 'mujoco-playground/scripts/playground_sim2real.py'
    if hashlib.sha256(path.read_bytes()).hexdigest() != HELPER_SHA256:
        raise ValueError('Published Robotics helper changed from pinned 9cb7f624')
    spec = importlib.util.spec_from_file_location('gemini_pinned_playground', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Yam1Kinematics:
    def __init__(self, scene, skills_root):
        self.scene = scene
        self.google = robotics_helper(skills_root)

    def solve(self, arm, pos_world, *, target_rot_world=None):
        """Return native radians only after checking actual position/orientation.

        Google's generic solver's best-effort fallback can return a position
        within 15mm without satisfying orientation. Do not treat that return as
        proof the requested constraint succeeded. Native command/workspace/
        predictive-contact validation still applies at the host dispatch path.
        """
        if arm not in ARMS:
            raise ValueError('Choose left or right arm')
        p = np.asarray(pos_world, dtype=float)
        if p.shape != (3,) or not np.isfinite(p).all():
            raise ValueError('IK position must have three finite world metres')
        r = None if target_rot_world is None else np.asarray(target_rot_world, dtype=float)
        if r is not None and (r.shape != (3, 3) or not np.isfinite(r).all()
                              or not np.allclose(r.T @ r, np.eye(3), atol=1e-8, rtol=0)
                              or not np.isclose(np.linalg.det(r), 1, atol=1e-8, rtol=0)):
            raise ValueError('IK orientation must be a proper rotation')
        m, context = self.scene.model, self.scene.data.qpos.copy()
        i = ARMS.index(arm) * 6
        q_min = np.asarray(self.scene.safety['joint_lower_rad'][i:i+6])
        q_max = np.asarray(self.scene.safety['joint_upper_rad'][i:i+6])
        qids, dids = self.scene.arm_qpos[arm], self.scene.arm_dof[arm]
        site = int(m.site(arm + '_installed_grasp_site').id)
        result = self.google.solve_site_ik(
            m, site, qids, dids, q_min, q_max, p, q_seed=context[qids],
            q_posture=context[qids], context_qpos=context,
            approach_dir_world=None, target_rot_world=r,
            pos_tol_m=.0015, ori_tol_rad=.02)
        result = np.asarray(result, dtype=float)
        if (result.shape != (6,) or not np.isfinite(result).all()
                or np.any(result < q_min) or np.any(result > q_max)):
            raise ValueError('Published IK produced invalid native joint targets; no command constructed')
        check = mujoco.MjData(m)
        check.qpos[:] = context; check.qpos[qids] = result
        mujoco.mj_forward(m, check)
        pos_error = float(np.linalg.norm(check.site_xpos[site] - p))
        rot_error = 0. if r is None else float(np.arccos(np.clip(
            (np.trace(check.site_xmat[site].reshape(3, 3).T @ r) - 1) / 2, -1., 1.)))
        if pos_error > .0015 or rot_error > .02:
            raise ValueError(f'IK constraints unmet: position {pos_error:.6f}m, rotation {rot_error:.6f}rad; no command constructed')
        return result.copy()
