"""Offline-only, one-minute camera-viewpoint iteration. Never opens hardware."""
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
from scipy.spatial.transform import Rotation, Slerp

from scene_video import SweepPolicy, ARMS
from remote_yam.session import HttpSessionAPI, _trajectory_waypoints
from remote_yam.mujoco_ik import default_scene_path


def aimed_rotation(position, target, extrinsic, initial):
    """Aim the calibrated camera, accounting for its offset from the wrist."""
    rotation = initial.copy()
    for _ in range(30):
        center = position + rotation @ extrinsic[:3, 3]
        z = target-center
        z /= np.linalg.norm(z)
        previous_axis = rotation @ extrinsic[:3, 2]
        cross = np.cross(previous_axis,z)
        sine = np.linalg.norm(cross)
        if sine > 1e-12:
            angle = np.arctan2(sine,np.dot(previous_axis,z))
            rotation = Rotation.from_rotvec(cross/sine*angle).as_matrix() @ rotation
    center = position + rotation @ extrinsic[:3, 3]
    assert np.dot(rotation @ extrinsic[:3, 2], (target-center)/np.linalg.norm(target-center)) > .999999
    return rotation


def stages(start, policy, reach):
    current = list(deepcopy(start))
    result = []
    def add(label, seconds, changes):
        nonlocal current
        target = deepcopy(current)
        for arm, (position, aim) in changes.items():
            position, aim = np.asarray(position), np.asarray(aim)
            target[arm] = (position, aimed_rotation(position, aim, policy.cameras[arm], current[arm][1]))
        result.append((label, seconds, deepcopy(current), target))
        current = deepcopy(target)
    add('Raise and aim at shared center', 6, {
        0:([.30,.25,.30],[.55,0,.025]), 1:([.30,-.25,.30],[.55,0,.025])})
    add('Right forward view', 8, {1:([reach,-.20,.30],[.58,0,.025])})
    add('Right scans across scene', 6, {1:([reach-.03,-.10,.32],[.48,.10,.025])})
    add('Right returns to wide view', 8, {1:([.30,-.25,.30],[.55,0,.025])})
    add('Left forward view', 8, {0:([reach,.20,.30],[.58,0,.025])})
    add('Left scans across scene', 6, {0:([reach-.03,.10,.32],[.48,-.10,.025])})
    add('Left returns to wide view', 8, {0:([.30,.25,.30],[.55,0,.025])})
    add('Both cover near and far scene', 10, {
        0:([reach-.04,.24,.32],[.52,.08,.025]),
        1:([reach-.04,-.24,.32],[.68,-.08,.025])})
    assert sum(s[1] for s in result) == 60
    return result


def project(policy, poses, points):
    """Calibrated distorted RGB projection of an explicit synthetic scene grid."""
    visible = []
    for arm, (position, rotation) in enumerate(poses):
        ext = policy.cameras[arm]
        center = position + rotation @ ext[:3, 3]
        camera_r = rotation @ ext[:3,:3]
        local = (points-center) @ camera_r
        c = policy.report['cameras'][ARMS[arm]]
        pixels,_ = cv2.projectPoints(local, np.zeros(3), np.zeros(3),
                                    np.asarray(c['K']), np.asarray(c['distortion']))
        pixels = pixels[:,0]
        width,height = c['image_size']
        visible.append(((local[:,2]>.02) & (pixels[:,0]>=8) & (pixels[:,0]<width-8)
                        & (pixels[:,1]>=8) & (pixels[:,1]<height-8)).tolist())
    return visible


def plan(policy, home, reach):
    q = np.asarray(home[:6]+home[7:13])
    policy.ik._forward(q)
    initial = policy.ik._poses()
    grid = np.asarray([[x,y,z] for x in np.linspace(.32,.72,9)
                       for y in np.linspace(-.30,.30,9) for z in (0.025,.08)])
    points,geometry,labels,positions,visibility = [],[],[],[],[]
    max_step = 0.
    for label, seconds, start, end in stages(initial,policy,reach):
        interpolators = [Slerp([0,1],Rotation.from_matrix([start[a][1],end[a][1]])) for a in range(2)]
        for sample in range(1,seconds*10+1):
            t = sample/(seconds*10)
            s = t*t*(3-2*t)
            targets = tuple((start[a][0]*(1-s)+end[a][0]*s,
                             interpolators[a]([s]).as_matrix()[0]) for a in range(2))
            try: nxt=policy.ik._solve(q, targets)
            except Exception as error:
                raise RuntimeError(f'{label}, sample {sample}: {error}') from error
            delta = float(np.max(np.abs(nxt-q)))
            if delta > .035:raise ValueError(f'{label}: joint pacing {delta}')
            max_step=max(max_step,delta)
            policy.ik._forward(nxt)
            poses=policy.ik._poses()
            for arm,(p,r) in enumerate(poses):
                local=p-policy.bases[arm]
                if np.any(local<policy.bounds[arm][0]) or np.any(local>policy.bounds[arm][1]):
                    raise ValueError(f'{label}: existing workspace boundary')
                assert np.linalg.norm(p-targets[arm][0]) < 2e-6
                assert np.max(np.abs(r-targets[arm][1])) < 2e-5
            geometry.append(policy.camera_geometry(poses))
            visibility.append(project(policy,poses,grid))
            positions.append([g['position_m'] for g in geometry[-1]])
            points.append(dict(step_id=len(points),left_joints_deg=np.rad2deg(nxt[:6]).tolist(),
                               right_joints_deg=np.rad2deg(nxt[6:]).tolist(),
                               left_gripper=home[6],right_gripper=home[13]))
            labels.append(label)
            q=nxt
    for start in range(0,len(points),300):_trajectory_waypoints(points[start:start+300])
    return dict(waypoints=points,geometry=geometry,labels=labels,camera_positions_m=positions,
                visible_grid=visibility,scene_grid_m=grid.tolist(),max_joint_step_rad=max_step,
                grasp_forward_max_m=reach,duration_s=60,cadence_hz=10)


def guard_path(result, home, hardware_root):
    sys.path.insert(0,str(hardware_root))
    from YAM_control.ruckig_waypath import collision_enabled_model
    from YAM_control.hardware_safety import HardwareSafetyConfig, BimanualHardwareGuard
    model=collision_enabled_model(hardware_root/'assets/yam_bimanual/scene.xml')
    data=mujoco.MjData(model)
    def fk(q):
        data.qpos[:12]=q;mujoco.mj_forward(model,data)
        return {a:data.body(a+'_grasp').xpos.copy() for a in ARMS}
    def clear(q):fk(q);return data.ncon==0
    guard=BimanualHardwareGuard(HardwareSafetyConfig.load(hardware_root/'config/yam_hardware_safety.json'),
                                forward_kinematics=fk,collision_check=clear)
    approved=guard.approve(home[:6]+home[7:13],
        [np.deg2rad(p['left_joints_deg']+p['right_joints_deg']) for p in result['waypoints']],cadence_hz=10)
    return approved.swept_samples


def render(result, policy, output):
    spec=mujoco.MjSpec.from_file(str(default_scene_path()))
    for i,a in enumerate(ARMS):
        root=spec.body(a+'_link1');p=root.pos.copy();p[1]=(1 if i==0 else -1)*.25;root.pos=p
        ext=policy.cameras[i];rotation=ext[:3,:3]@np.diag([1,-1,-1])
        xyzw=Rotation.from_matrix(rotation).as_quat()
        c=policy.report['cameras'][a]
        fovy=np.rad2deg(2*np.arctan(c['image_size'][1]/(2*c['K'][1][1])))
        spec.body(a+'_grasp').add_camera(name=a+'_wrist',pos=ext[:3,3],quat=xyzw[[3,0,1,2]],fovy=fovy)
    spec.worldbody.add_geom(name='scene_table',type=mujoco.mjtGeom.mjGEOM_BOX,
        pos=[.53,0,-.025],size=[.27,.40,.025],rgba=[.85,.85,.82,1])
    colors=[[.85,.16,.14,1],[.15,.65,.3,1],[.2,.3,.85,1],[.85,.65,.1,1]]
    for i,x in enumerate([.36,.48,.60,.70]):
        for j,y in enumerate([-.25,0,.25]):
            h=.025+.012*((i+j)%3)
            spec.worldbody.add_geom(name=f'object_{i}_{j}',type=mujoco.mjtGeom.mjGEOM_BOX,
                pos=[x,y,h],size=[.022,.022,h],rgba=colors[(i+j)%4])
    model=spec.compile();data=mujoco.MjData(model)
    # Apply the same calibrated encoder reference as the planner.
    model.qpos0[:12]=-policy.ik.joint_offsets_rad
    renderer=mujoco.Renderer(model,height=360,width=640)
    overview=mujoco.MjvCamera();overview.azimuth=115;overview.elevation=-40
    overview.distance=1.75;overview.lookat[:]=[.35,0,.18]
    option=mujoco.MjvOption();option.geomgroup[1]=0
    video=output/'viewpoint-simulation.mp4'
    encoder=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','bgr24',
        '-s','1920x360','-r','10','-i','-','-an','-c:v','libx264','-preset','fast','-crf','20',
        '-pix_fmt','yuv420p','-movflags','+faststart',str(video)],stdin=subprocess.PIPE)
    try:
        for i,point in enumerate(result['waypoints']):
            data.qpos[:12]=np.deg2rad(point['left_joints_deg']+point['right_joints_deg'])
            mujoco.mj_forward(model,data);frames=[]
            for label,camera in [('LEFT WRIST','left_wrist'),('SIMULATION - OVERVIEW',overview),('RIGHT WRIST','right_wrist')]:
                renderer.update_scene(data,camera=camera,scene_option=option)
                frame=cv2.cvtColor(renderer.render(),cv2.COLOR_RGB2BGR)
                cv2.rectangle(frame,(0,0),(640,43),(20,24,30),-1)
                cv2.putText(frame,label,(12,28),cv2.FONT_HERSHEY_SIMPLEX,.65,(255,255,255),1,cv2.LINE_AA)
                cv2.rectangle(frame,(0,312),(640,360),(20,24,30),-1)
                cv2.putText(frame,f'{(i+1)/10:.1f}s / 60s | '+result['labels'][i],(10,338),cv2.FONT_HERSHEY_SIMPLEX,.46,(255,255,255),1,cv2.LINE_AA)
                frames.append(frame)
            combined=np.concatenate(frames,axis=1)
            if i in [0,59,159,219,279,379,439,499,599]:cv2.imwrite(str(output/f'view-{i+1:03d}.jpg'),combined)
            encoder.stdin.write(combined.tobytes())
    finally:
        encoder.stdin.close();encoder.wait(timeout=30);renderer.close()
    assert encoder.returncode==0
    cap=cv2.VideoCapture(str(video));n=0
    while cap.read()[0]:n+=1
    assert n==600
    for frame in [0,150,300,599]:
        cap.set(cv2.CAP_PROP_POS_FRAMES,frame);assert cap.read()[0]
    cap.release()
    return video


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--hardware-root',type=Path,required=True)
    parser.add_argument('--plan-only',action='store_true')
    parser.add_argument('--reach',type=float,default=.47)
    args=parser.parse_args();started=time.monotonic();args.output.mkdir(parents=True,exist_ok=True)
    base=Path(__file__).parent
    report=json.loads((base/'data/yam1-calibration.json').read_text())
    home=json.loads((base/'data/simulation-home.json').read_text())['home_pose']
    policy=SweepPolicy(report,simulation=True)
    result=plan(policy,home,args.reach)
    samples=guard_path(result,home,args.hardware_root)
    # Exercise the real serializer with a zero-network wire spy.
    api=HttpSessionAPI('https://offline.invalid',supports_trajectories=True,robot_id='yam-1')
    api._session_capabilities['offline']='offline-only';sent=[]
    def wire(req,**kwargs):
        assert req.full_url=='https://offline.invalid/v1/sessions/offline/trajectories'
        sent.append(json.loads(req.data));return io.BytesIO(b'{"accepted":true}')
    with patch('remote_yam.session.request.urlopen',side_effect=wire):
        for start in range(0,len(result['waypoints']),300):
            api.submit_trajectory('offline','offline-viewpoints','offline-only','one-minute-'+str(start),
                                  10.,result['waypoints'][start:start+300])
    assert len(sent)==2 and [p for packet in sent for p in packet['waypoints']]==result['waypoints']
    (args.output/'plan.json').write_text(json.dumps(result,indent=2)+'\n')
    visible=np.asarray(result['visible_grid']);union=np.any(visible,axis=0)
    centers=np.asarray(result['camera_positions_m'])
    metrics=dict(status='PASS',physical_connection=False,actuator_submissions=0,duration_s=60,
        frames=600,cadence_hz=10,forward_reach_m=args.reach,forward_extension_from_home_m=args.reach-.299971,
        max_joint_step_rad=result['max_joint_step_rad'],hardware_guard_swept_samples=samples,
        canonical_serializer_packets=len(sent),grippers_held=True,
        projected_in_frame_grid_fraction_per_arm=union.mean(axis=1).tolist(),
        camera_position_span_m=np.ptp(centers,axis=0).tolist(),
        calibration_id=report['calibration_id'],source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitations=['Synthetic grid projection ignores occlusion; current physical obstacles/coverage not verified',
                     'Pinhole render approximates calibrated intrinsics; distortion included in visibility metrics',
                     'Kinematic simulation, not a motor-tracking or reconstruction-quality certificate'])
    if not args.plan_only:
        video=render(result,policy,args.output)
        metrics.update(video=str(video.resolve()),video_sha256=hashlib.sha256(video.read_bytes()).hexdigest(),decoded_frames=600,seek_verified=True)
    metrics['elapsed_s']=time.monotonic()-started
    (args.output/'verification.json').write_text(json.dumps(metrics,indent=2)+'\n')
    print(json.dumps(metrics,indent=2))

if __name__=='__main__':main()
