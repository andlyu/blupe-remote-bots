"""Read-only YAM1 observations/calibration/cameras for the selected SDK agent.

Uses the canonical public Session API and bounded camera client. No session is
created, no queue is joined, and no human contact field enters the model input.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from urllib.parse import urljoin

API_ORIGIN = 'https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com'


def runner_root():
    packaged = Path(__file__).resolve().parents[1] / 'runner'
    root = Path(os.environ.get('GEMINI_RUNNER_ROOT', packaged if packaged.is_dir() else Path(__file__).resolve().parents[3]))
    if not (root/'src/remote_yam/session.py').is_file():
        raise RuntimeError('Canonical station transport is not installed')
    return root


def transport_classes():
    root=runner_root()
    sys.path.insert(0,str(root/'src'))
    from remote_yam.session import HttpSessionAPI
    from remote_yam.cameras import CameraFrameSource
    return HttpSessionAPI, CameraFrameSource


def calibration_subset(value):
    if value.get('robot_id')!='yam-1' or value.get('schema_version')!=1:
        raise RuntimeError('Station calibration identity/schema mismatch')
    result={k:deepcopy(value[k]) for k in ('robot_id','calibration_id','base_geometry','native_joint_calibration','quality')}
    result['kinematics']={k:value['kinematics'][k] for k in ('model','robot_model_sha256','scene_sha256')}
    result['cameras']={}
    for role in ('top','left','right'):
        keys=('K','image_size','distortion','distortion_model')+(('T_base_camera',) if role=='top' else ('T_grasp_camera','parent_frame'))
        result['cameras'][role]={k:deepcopy(value['cameras'][role][k]) for k in keys}
    return result


def collect_station_inputs(*, api=None, cameras=None, origin=API_ORIGIN):
    if api is None or cameras is None:
        Api, Cameras = transport_classes()
        api = api or Api(origin,timeout_s=5,robot_id='yam-1')
        cameras = cameras or Cameras(origin,timeout_s=2,max_attempts=1,recovery_s=2)
    started=time.time()
    with ThreadPoolExecutor(max_workers=2) as pool:
        observation=pool.submit(api.get_robot_observation,'yam-1')
        calibration=pool.submit(api._request,'GET','/v1/robots/yam-1/calibration')
        raw=observation.result();report=calibration.result()
    raw=raw.get('observation') or raw.get('payload') or raw
    if raw.get('jetson_id')!='yam-1':raise RuntimeError('Station observation identity mismatch')
    timestamp=raw.get('observed_at')
    if type(timestamp) not in (float,int) or not math.isfinite(timestamp) or not -2<=time.time()-timestamp<=10:
        raise RuntimeError('Station feedback is stale; current joints are required')
    observation={k:deepcopy(raw[k]) for k in ('source','observed_at','left_joints_deg','right_joints_deg','left_gripper','right_gripper')}
    for arm in ('left','right'):
        q=observation[arm+'_joints_deg'];g=observation[arm+'_gripper']
        if (not isinstance(q,list) or len(q)!=6 or any(type(v) not in (float,int) or not math.isfinite(v) for v in q)
                or type(g) not in (float,int) or not math.isfinite(g) or not 0<=g<=1):
            raise RuntimeError('Station feedback requires finite joints and normalized grippers')
    metadata={'images':{}}
    for role in ('top','left','right'):
        image=raw.get('images',{}).get(role,{})
        url=image.get('url') if isinstance(image,dict) else None
        if not isinstance(url,str):raise RuntimeError('Station camera URL is missing')
        metadata['images'][role]={'url':urljoin(origin+'/',url)}
    frames=cameras.capture(metadata)
    if {frame.name for frame in frames}!={'top','left','right'}:
        raise RuntimeError('Station camera set is incomplete')
    station=dict(calibration=calibration_subset(report),observation=observation,
                 captured_context_at=time.time(),capture_started_at=started,
                 camera_frames={f.name:f.summary() for f in frames},
                 task_scene_status='Live views and robot geometry; object/contact reconstruction is pending')
    return station,frames


def sdk_prompt(prompt, station, frames):
    # google-antigravity0.1.23 README Multimodal Ingestion, pinned75ba22bd.
    from google.antigravity.types import Image
    metadata=dict(observation=station['observation'],calibration=station['calibration'],
                  camera_frames=station['camera_frames'],task_scene_status=station['task_scene_status'])
    result=[prompt,'Current YAM1 scene and robot configuration:\n'+json.dumps(metadata,separators=(',',':'))]
    for frame in frames:
        result.append(Image(data=frame.jpeg,mime_type='image/jpeg',description='Current '+frame.name+' YAM1 camera view'))
    return result
