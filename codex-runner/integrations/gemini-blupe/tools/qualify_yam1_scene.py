"""Offline engineering rollout, not a model run or a physical qualification."""
import argparse
import json
from pathlib import Path
import sys
import time

import imageio.v2 as imageio
import mujoco
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from yam1_scene import Yam1Scene, FINGER_TRAVEL_M
from yam1_kinematics import Yam1Kinematics


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--runner-root', type=Path, required=True)
    p.add_argument('--skills-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--integration', type=Path, default=Path(__file__).resolve().parents[1])
    a = p.parse_args()
    started = time.monotonic()
    c = json.loads((a.integration / 'tests/fixtures/yam1-calibration.json').read_text())
    s = Yam1Scene(a.runner_root, a.integration / 'assets/linear4310', c)
    helper = Yam1Kinematics(s, a.skills_root).google
    initial = {'left': np.array([.2, 1.6, 1.2, -.8, .1, -.2]),
               'right': np.array([-.2, 1.5, 1.3, -.9, -.1, .3])}
    s.set_configuration(initial, {'left': 1., 'right': 1.})
    a.output.mkdir(parents=True, exist_ok=True)
    renderer = mujoco.Renderer(s.model, height=360, width=640)
    writer = imageio.get_writer(str(a.output / 'yam1-engineering.mp4'), fps=10, macro_block_size=2)
    rows = []
    try:
        # Source-visible, handwritten actuation: slight arm deflection and full
        # jaw travel, no object, no hidden weld and no success metric substitute.
        for frame in range(60):
            phase = frame / 59
            grip = 1 - 2*phase if phase <= .5 else 2*phase - 1
            offset = .05 * np.sin(2*np.pi*phase)
            for arm, sign in (('left', 1), ('right', -1)):
                target = initial[arm].copy(); target[0] += sign * offset
                s.data.ctrl[s.actuators[arm]] = target
                s.data.ctrl[s.model.actuator(arm + '_gripper').id] = grip * FINGER_TRAVEL_M
            for _ in range(50):
                mujoco.mj_step(s.model, s.data)
            images = []
            for camera in ('top', 'left', 'right'):
                renderer.update_scene(s.data, camera=camera)
                images.append(renderer.render().copy())
            composite = np.concatenate(images, axis=1)
            writer.append_data(composite)
            if frame == 0:
                imageio.imwrite(a.output / 'yam1-engineering.png', composite)
            rows.append(dict(sim_time_s=float(s.data.time), commanded_gripper=grip,
                             arm_positions={arm:s.data.qpos[s.arm_qpos[arm]].tolist() for arm in ('left','right')},
                             finger_positions_m={arm:s.data.qpos[s.finger_qpos[arm]].tolist() for arm in ('left','right')}))
            if not np.isfinite(s.data.qpos).all() or not np.isfinite(s.data.qvel).all():
                raise RuntimeError('Offline dynamics became nonfinite')
    finally:
        writer.close(); renderer.close()
    receipt = s.receipt()
    receipt.update(controller='Handwritten engineering rollout; not Hydrogen generated',
                   frames=len(rows), simulated_seconds=float(s.data.time),
                   wall_seconds=round(time.monotonic()-started, 3),
                   mujoco_version=mujoco.__version__,
                   warning_counts={str(i):int(w.number) for i,w in enumerate(s.data.warning) if w.number},
                   video='yam1-engineering.mp4', camera_order=['top','left','right'])
    receipt['pinhole_K_error_max_px'] = max(float(np.max(np.abs(
        helper.camera_intrinsics_from_model(s.model, s.model.camera(name).id, 640, 360)[0]
        - np.asarray(c['cameras'][name]['K'])))) for name in ('top','left','right'))
    (a.output / 'yam1-scene-proof.json').write_text(json.dumps(receipt, indent=2)+'\n')
    (a.output / 'yam1-engineering-trajectory.json').write_text(json.dumps(rows)+'\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
