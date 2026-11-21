"""Offline release preflight: real packet serializer, FK, cameras and MP4."""
import argparse
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

import cv2
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
from remote_yam.session import HttpSessionAPI
from remote_yam.mujoco_ik import default_scene_path
from remote_yam.providers import PolicyComplete
from scene_video import SweepPolicy, TASK, ARMS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--calibration', type=Path, required=True)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--hardware-root', type=Path, required=True)
    args = parser.parse_args()
    began = time.time()
    args.output.mkdir(parents=True, exist_ok=True)
    report = json.loads(args.calibration.read_text())
    home = json.loads(args.home.read_text())['home_pose']
    obs = dict(source='simulation', robot_id='yam-1', homed=True, settled=True,
               safety=dict(ok=True), observed_at=time.time(), episode_id='offline-scene-video',
               lease_id='offline-only', step_id=0, left_joints_deg=np.rad2deg(home[:6]).tolist(),
               right_joints_deg=np.rad2deg(home[7:13]).tolist(),
               left_gripper=.9992793312193716, right_gripper=.9947321472782467)
    policy = SweepPolicy(report, args.output, simulation=True)
    initial = policy._read(obs)[1]
    points = policy.build_trajectory(TASK, obs, 0)
    api = HttpSessionAPI('https://offline.invalid', supports_trajectories=True, robot_id='yam-1')
    api._session_capabilities['offline'] = 'offline-only'
    sent = []
    def wire(req, **kwargs):
        assert req.full_url == 'https://offline.invalid/v1/sessions/offline/trajectories'
        sent.append(json.loads(req.data))
        return io.BytesIO(b'{"accepted":true}')
    with patch('remote_yam.session.request.urlopen', side_effect=wire):
        api.submit_trajectory('offline', obs['episode_id'], obs['lease_id'], 'offline-sweep', 10., points)
        assert len(sent) == 1 and sent[0]['waypoints'] == points
        # Reject malformed/stale feedback, invalid fractions, wrong task and
        # out-of-envelope starting states before any outbound submission.
        rejected = 0
        mutations = [dict(observed_at=0), dict(homed=False), dict(source='hardware'),
                     dict(left_gripper=-1e-16), dict(right_gripper=1+1e-15),
                     dict(left_gripper=float('nan')), dict(right_gripper=float('inf')),
                     dict(left_joints_deg=[float('nan')]*6), dict(robot_id='other')]
        for mutation in mutations:
            candidate = {**obs, **mutation, 'observed_at': mutation.get('observed_at', time.time())}
            try:
                ps = SweepPolicy(report, simulation=True).build_trajectory(TASK, candidate, 0)
                api.submit_trajectory('offline', obs['episode_id'], obs['lease_id'], 'invalid', 10., ps)
                raise AssertionError('Invalid request accepted')
            except (ValueError, RuntimeError):
                rejected += 1
            assert len(sent) == 1
        # Boundary fractions and fractional measured starts all remain exact.
        for value in (0., 1., .37):
            o = {**obs, 'observed_at':time.time(), 'left_gripper':value, 'right_gripper':value}
            ps = SweepPolicy(report, simulation=True).build_trajectory(TASK, o, 0)
            api.submit_trajectory('offline', obs['episode_id'], obs['lease_id'], 'fraction-'+str(value), 10., ps)
            assert all(p[a+'_gripper'] == value for p in ps for a in ARMS)
    assert [p['step_id'] for p in points] == list(range(120))
    previous = np.deg2rad(obs['left_joints_deg']+obs['right_joints_deg'])
    max_step = 0.
    for point in points:
        q = np.deg2rad(point['left_joints_deg']+point['right_joints_deg'])
        max_step = max(max_step, float(np.max(np.abs(q-previous))))
        policy.ik._forward(q)
        for a in ARMS:
            assert point[a+'_gripper'] == obs[a+'_gripper']
        previous = q
    final = policy.ik._poses()
    distances = [float((p-initial[i][0])[0]) for i, (p, _) in enumerate(final)]
    np.testing.assert_allclose(distances, [.12, .12], atol=2e-6)
    # The normal controller reports the NEXT command cursor, and Home is
    # false after the requested movement. Exercise completion in preflight.
    completed={**obs, **points[-1], 'homed':False,
               'step_id':points[-1]['step_id']+1, 'observed_at':time.time()}
    policy.validate_trajectory_final(completed)
    assert policy.complete
    try:
        policy.build_trajectory(TASK,completed,completed['step_id'])
        raise AssertionError('Completed sweep generated another movement')
    except PolicyComplete:
        pass
    # Run the same safety guard and collision-enabled robot model as the
    # station. Importing these utilities opens no driver or hardware channel.
    sys.path.insert(0,str(args.hardware_root))
    from YAM_control.ruckig_waypath import collision_enabled_model
    from YAM_control.hardware_safety import HardwareSafetyConfig, BimanualHardwareGuard
    guard_model=collision_enabled_model(args.hardware_root/'assets/yam_bimanual/scene.xml')
    guard_data=mujoco.MjData(guard_model)
    def fk(q):
        guard_data.qpos[:12]=q; mujoco.mj_forward(guard_model,guard_data)
        return {a:guard_data.body(a+'_grasp').xpos.copy() for a in ARMS}
    def clear(q):
        fk(q);return guard_data.ncon==0
    guard=BimanualHardwareGuard(HardwareSafetyConfig.load(args.hardware_root/'config/yam_hardware_safety.json'),
        forward_kinematics=fk,collision_check=clear)
    approved=guard.approve(home[:6]+home[7:13],
        [np.deg2rad(p['left_joints_deg']+p['right_joints_deg']) for p in points],cadence_hz=10)
    # A separate render model adds a synthetic tabletop scene and calibrated
    # wrist views; canonical planner assets are never modified.
    spec = mujoco.MjSpec.from_file(str(default_scene_path()))
    for i, a in enumerate(ARMS):
        root = spec.body(a+'_link1')
        pos = root.pos.copy(); pos[1] = (1 if i == 0 else -1)*.25; root.pos = pos
        t = policy.cameras[i]
        rotation = t[:3,:3] @ np.diag([1,-1,-1])
        xyzw = Rotation.from_matrix(rotation).as_quat()
        spec.body(a+'_grasp').add_camera(name=a+'_wrist', pos=t[:3,3],
            quat=xyzw[[3,0,1,2]], fovy=57.)
        for j, color in enumerate(([.9,.25,.16,1], [.2,.75,.35,1], [.25,.4,.9,1])):
            spec.worldbody.add_geom(name=f'scene_{a}_{j}', type=mujoco.mjtGeom.mjGEOM_BOX,
                pos=[.47+.075*j, (1 if i == 0 else -1)*.25 + (j-1)*.05, .025+.01*j],
                size=[.025,.025,.025+.01*j], rgba=color)
    model = spec.compile()
    data = mujoco.MjData(model)
    renderer = mujoco.Renderer(model, height=360, width=640)
    overview = mujoco.MjvCamera()
    overview.azimuth=115; overview.elevation=-35; overview.distance=1.55
    overview.lookat[:]=[.32,0,.16]
    option=mujoco.MjvOption(); option.geomgroup[1]=0
    target=args.output/'simulation.mp4'
    encoder=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','bgr24',
        '-s','1920x360','-r','10','-i','-','-an','-c:v','libx264','-preset','fast','-crf','20',
        '-pix_fmt','yuv420p','-movflags','+faststart',str(target)],stdin=subprocess.PIPE)
    try:
        for index, point in enumerate(points):
            data.qpos[:12]=np.deg2rad(point['left_joints_deg']+point['right_joints_deg'])
            mujoco.mj_forward(model,data)
            frames=[]
            for label, camera in [('LEFT WRIST','left_wrist'),('SIMULATION - OVERVIEW',overview),('RIGHT WRIST','right_wrist')]:
                renderer.update_scene(data,camera=camera,scene_option=option)
                frame=cv2.cvtColor(renderer.render(),cv2.COLOR_RGB2BGR)
                cv2.rectangle(frame,(0,0),(640,44),(20,24,30),-1)
                cv2.putText(frame,label,(12,28),cv2.FONT_HERSHEY_SIMPLEX,.65,(255,255,255),1,cv2.LINE_AA)
                cv2.putText(frame,f'Forward {index+1:3d} mm / 120 mm',(12,343),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1,cv2.LINE_AA)
                frames.append(frame)
            frame=np.concatenate(frames,axis=1)
            if index in (0,60,119):cv2.imwrite(str(args.output/f'frame-{index:03d}.jpg'),frame)
            encoder.stdin.write(frame.tobytes())
    finally:
        encoder.stdin.close(); encoder.wait(timeout=30); renderer.close()
    assert encoder.returncode == 0
    cap=cv2.VideoCapture(str(target)); assert cap.isOpened()
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 120
    assert cap.read()[0]
    cap.set(cv2.CAP_PROP_POS_FRAMES,90); assert cap.read()[0]; cap.release()
    receipt=dict(status='PASS', physical_connection=False, actuator_submissions=0,
        policy_sha256=hashlib.sha256(Path(__file__).with_name('scene_video.py').read_bytes()).hexdigest(),
        calibration_id=report['calibration_id'], mujoco_version=mujoco.__version__,
        canonical_validator_sha256=hashlib.sha256(Path(sys.modules['remote_yam.session'].__file__).read_bytes()).hexdigest(),
        hardware_guard_swept_samples=approved.swept_samples,
        away_from_home_completion=True, next_command_cursor_verified=True,
        completed_sweep_dispatches_again=False,
        serializer_spy_packets=len(sent), invalid_zero_dispatch_cases=rejected,
        waypoints=len(points), duration_s=12, fps=10, camera_views=3, distance_m=distances,
        max_joint_step_rad=max_step, grippers_held_exactly=True,
        camera_orientation='down/forward over tabletop throughout', video=str(target),
        video_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        elapsed_s=time.time()-began, limitations=['Synthetic scene, not a current physical-scene collision survey',
        'Kinematic rendering, not dynamic motor tracking; physical gateway swept collision checks remain required'])
    (args.output/'verification.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
