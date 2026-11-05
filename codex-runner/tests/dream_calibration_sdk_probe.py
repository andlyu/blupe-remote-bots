"""Run with the pinned Dream SDK Python: real FK/trajectory IK, no network/model/robot.

Input is generated from the selected, hash-checked controller geometry in the
UI environment. This probe consumes actual SDK ClientIK and encoder outputs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

for name in ('OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS'):
    os.environ.setdefault(name, '1')
os.environ.setdefault('LOGURU_LEVEL', 'WARNING')

import numpy as np
import dream
from dream.client_ik import ClientIK, POSE_KEYS
from dream.models import Model
from dream.smoothing import SeamSmoother
from dream_ik import decode
from dream_ik.specs import EMBODIMENTS
from shared.datasets.embodiments import YAM_BODY

from remote_yam.dream_calibration import install_sdk_kinematics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--runner-name', required=True, help='Confirmed person requesting this offline test')
    args = parser.parse_args()
    source = json.loads(args.input.read_text())
    stock = EMBODIMENTS['yam'].arm.urdf
    before = hashlib.sha256(stock.read_bytes()).hexdigest()
    started = time.perf_counter()
    binding = install_sdk_kinematics(source['description'], args.output.parent / 'sdk-geometry')
    assert install_sdk_kinematics(source['description'], args.output.parent / 'sdk-geometry') == binding
    print('Selected geometry installed; constructing actual Dream ClientIK', flush=True)
    checkpoint = 'dreamlabs/dream-1-beta'
    model = Model(checkpoint, 'public', checkpoint, YAM_BODY, True, None,
                  cameras=['overhead', 'wrist_l', 'wrist_r'])
    parts = {'right_arm':[0,6], 'right_gripper':[6,7], 'left_arm':[7,13], 'left_gripper':[13,14]}
    body = {'state':parts, 'action':dict(parts), 'video':{role:'observation.images.'+role
            for role in ('overhead','wrist_l','wrist_r')}}
    client = ClientIK({'arm':'yam','head':'eef','solve':'traj'}, 20, body, model)
    if not client.traj_ready.wait(120):
        raise RuntimeError('Actual SDK trajectory solver did not become ready')
    print('Actual trajectory IK ready; checking FK/state/encoder round trips', flush=True)
    checks = []
    for case in source['cases']:
        observation = {'state.'+side+'_arm':np.asarray(case['q'][side], dtype=float)
                       for side in ('left','right')}
        observation.update({'state.left_gripper':np.array([.2]), 'state.right_gripper':np.array([.8])})
        # ClientIK checks camera-role presence but does not decode images. These
        # marked fixtures never leave this offline numerical probe.
        observation.update({'video.'+role:'offline-camera-fixture' for role in ('overhead','wrist_l','wrist_r')})
        observed = client.observe(observation)
        per_key = {}
        for side in ('left','right'):
            target = np.asarray(case['tcp'][side])
            np.testing.assert_allclose(observed['state.'+side+'_eef_xyz'], target[:3,3], atol=2e-6, rtol=0)
            np.testing.assert_allclose(observed['state.'+side+'_eef_rot6'],
                decode.mat_to_rot6d(target[:3,:3]), atol=5e-6, rtol=0)
            np.testing.assert_array_equal(observed['state.'+side+'_arm'], observation['state.'+side+'_arm'])
            per_key['action.'+side+'_eef_xyz'] = np.repeat(target[None,:3,3], 48, axis=0)
            per_key['action.'+side+'_eef_rot6'] = np.repeat(decode.mat_to_rot6d(target[:3,:3])[None], 48, axis=0)
            per_key['action.'+side+'_grip'] = np.full((48,1), .2 if side=='left' else .8)
        result = client.solve({'per_key':per_key}, observation, SeamSmoother(20,pose_keys=POSE_KEYS), 0., None)
        for side, key in [('left','q_l_chunk'), ('right','q_r_chunk')]:
            rows = np.asarray(result[key])
            assert rows.shape == (48,7) and np.isfinite(rows).all()
            final = client._solver.fk(rows[-1,:6], side)
            target = np.asarray(case['tcp'][side])
            miss = float(np.linalg.norm(final[:3,3] - target[:3,3]))
            angle = float(np.arccos(np.clip((np.trace(final[:3,:3].T @ target[:3,:3])-1)/2,-1,1)))
            encoder_error = float(np.max(np.abs(rows[-1,:6] - case['q'][side])))
            assert miss < .0005, (side, miss)
            assert angle < .005, (side, angle)
            assert encoder_error < .005, (side, encoder_error)
            checks.append(dict(side=side,position_error_m=miss,orientation_error_rad=angle,
                               encoder_roundtrip_error_rad=encoder_error))
    assert hashlib.sha256(stock.read_bytes()).hexdigest() == before
    import jax
    receipt = dict(sdk_version=dream.__version__, checkpoint=checkpoint,
        runner_name=args.runner_name, execution_mode='offline SDK FK/trajectory IK with synthetic targets',
        calibration=binding, sdk_package_urdf_unchanged=True, sdk_package_urdf_sha256=before,
        jax_enable_x64=bool(jax.config.jax_enable_x64), actual_trajectory_solver_ready=True,
        model_requests=0, physical_commands=0, synthetic_ik_targets=True,
        elapsed_s=time.perf_counter()-started, checks=checks)
    args.output.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
