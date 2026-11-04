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

import mujoco
import numpy as np
from .path_studio_geometry import rotation_mix, DrawingGeometry

from .scene_capture_base import SweepPolicy, ARMS
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
            axis = cross/sine
            skew = np.array([[0,-axis[2],axis[1]],[axis[2],0,-axis[0]],[-axis[1],axis[0],0]])
            rotation = (np.eye(3)+np.sin(angle)*skew+(1-np.cos(angle))*(skew@skew)) @ rotation
    center = position + rotation @ extrinsic[:3, 3]
    assert np.dot(rotation @ extrinsic[:3, 2], (target-center)/np.linalg.norm(target-center)) > .999999
    return rotation


def stages(start, policy, reach, scan_width=.15, aim_x=.55, duration_s=60):
    current = list(deepcopy(start))
    result = []
    def add(label, seconds, changes):
        nonlocal current
        target = deepcopy(current)
        for arm, (position, aim) in changes.items():
            position, aim = np.asarray(position,float), np.asarray(aim,float)
            position[1] = np.sign(position[1])*(.25-(.25-abs(position[1]))*scan_width/.15)
            aim[0] += aim_x-.55
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
    scale = duration_s/60
    result = [(label,round(seconds*10*scale),a,b) for label,seconds,a,b in result]
    return result


def plan(policy, home, reach, scan_width=.15, aim_x=.55, duration_s=60):
    q = np.asarray(home[:6]+home[7:13])
    policy.ik._forward(q)
    initial = policy.ik._poses()
    points,geometry,labels,positions,visibility = [],[],[],[],[]
    max_step = 0.
    for label, ticks, start, end in stages(initial,policy,reach,scan_width,aim_x,duration_s):
        for sample in range(1,ticks+1):
            t = sample/ticks
            s = t*t*(3-2*t)
            targets = tuple((start[a][0]*(1-s)+end[a][0]*s,
                             rotation_mix(start[a][1],end[a][1],s)) for a in range(2))
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
            positions.append([g['position_m'] for g in geometry[-1]])
            points.append(dict(step_id=len(points),left_joints_deg=np.rad2deg(nxt[:6]).tolist(),
                               right_joints_deg=np.rad2deg(nxt[6:]).tolist(),
                               left_gripper=home[6],right_gripper=home[13]))
            labels.append(label)
            q=nxt
    for start in range(0,len(points),300):_trajectory_waypoints(points[start:start+300])
    return dict(waypoints=points,geometry=geometry,labels=labels,camera_positions_m=positions,
                max_joint_step_rad=max_step,
                grasp_forward_max_m=reach,duration_s=duration_s,cadence_hz=10)


def guard_path(result, home, policy):
    offsets=policy.report.get('model_joint_calibration',{}).get('offsets_rad')
    offsets=offsets['left']+offsets['right'] if offsets else [0.]*12
    guard=DrawingGeometry(policy.spacing,offsets,0.)
    grips=dict(left=home[6],right=home[13])
    previous=np.asarray(home[:6]+home[7:13])
    guard.check(previous,grips)
    for point in result['waypoints']:
        target=np.deg2rad(point['left_joints_deg']+point['right_joints_deg'])
        guard.sweep(previous,target,grips)
        previous=target
    return guard.samples_checked
