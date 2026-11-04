"""Visitor-scoped, simulation-gated scene capture; public saved-episode lookup."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import secrets
import threading
import time
from urllib.request import urlopen

import numpy as np
from .scene_capture_policy import MinutePolicy, TASK
from .scene_capture_path import plan, guard_path

DEFAULTS=dict(duration_s=60,reach_m=.47,scan_width_m=.15,aim_x_m=.55)
DATA=Path(__file__).resolve().parents[2]/'scene-capture-data'
REPO='andlyu/Public-YAM-runs'
_SIM_SLOTS=threading.BoundedSemaphore(2)


def validate_config(data):
    if not isinstance(data,dict) or set(data)-set(DEFAULTS):
        raise ValueError('Use the guided scene-capture settings')
    result={**DEFAULTS,**data}
    limits=dict(duration_s=(60,120),reach_m=(.38,.47),scan_width_m=(.05,.15),aim_x_m=(.50,.60))
    for key,(low,high) in limits.items():
        value=result[key]
        if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError(f'{key} must be between {low} and {high}')
    if result['duration_s'] not in (60,90,120):
        raise ValueError('Choose 60, 90 or 120 seconds')
    result['duration_s']=int(result['duration_s'])
    return result


def binding(config,report):
    h=hashlib.sha256(json.dumps(dict(config=config,calibration=report),sort_keys=True).encode())
    for name in ('scene_capture_flow.py','scene_capture_policy.py','scene_capture_path.py','scene_capture_base.py',
                 'path_studio_geometry.py','mujoco_ik.py','controller_workspace.py','controller.py','session.py'):
        h.update((Path(__file__).parent/name).read_bytes())
    return h.hexdigest()


def simulate_capture(config,report):
    policy=MinutePolicy(report,config,simulation=True)
    home=json.loads((DATA/'simulation-home.json').read_text())['home_pose']
    started=time.monotonic()
    route=plan(policy,home,config['reach_m'],config['scan_width_m'],config['aim_x_m'],config['duration_s'])
    checked=guard_path(route,home,policy)
    # Full camera rotation is essential: optical axis alone hides image roll.
    for point,geometry in zip(route['waypoints'],route['geometry']):
        policy.ik._forward(np.deg2rad(point['left_joints_deg']+point['right_joints_deg']))
        for i,(_,rotation) in enumerate(policy.ik._poses()):
            geometry[i]['rotation']=(rotation@policy.cameras[i][:3,:3]).tolist()
    return dict(config=config,frames=route['waypoints'],cameras=route['geometry'],labels=route['labels'],
        intrinsics={a:dict(K=report['cameras'][a]['K'],image_size=report['cameras'][a]['image_size']) for a in ('left','right')},
        verification=dict(passed=True,sha256=binding(config,report),calibration_id=report.get('calibration_id'),
            duration_s=config['duration_s'],waypoints=len(route['waypoints']),swept_samples=checked,
            max_joint_step_rad=route['max_joint_step_rad'],computation_s=time.monotonic()-started,
            starting_state='documented reference Home; real run replans from fresh measured Home',
            camera_roll='minimum-rotation aim; image horizon can tilt',
            limits='joint, workspace, camera aim, installed gripper/arm CAD, table, swept clearance, pacing and packet limits',
            environment='Illustrative scene markers; no live object or dynamics model'))


class CaptureFlow:
    def _init_capture(self):
        self.capture=dict(simulation=dict(status='not_run'),run_kind=None)
        self.capture_receipt=None
        self.capture_worker=None
        self.capture_public_root=(self.monitor_service or self).identity_path.parent/'scene-capture-public'
        self.capture_report=None
        self.capture_persisted=None

    def capture_status(self):
        with self.lock:
            state=deepcopy(self.capture)
            sim=state['simulation']
            state['simulation']={k:v for k,v in sim.items() if k in ('status','config','token','verification','message')}
            raw=self.controller.status() if self.controller and state['run_kind']=='capture' else {}
            if raw.get('episode_id'):
                state['episode_id']=raw['episode_id']
                self.capture['episode_id']=raw['episode_id']
                if self.capture_report and self.capture_persisted!=raw['episode_id']:
                    receipt=dict(episode_id=raw['episode_id'],config=self.policy.config,calibration=self.capture_report,simulation=self.capture['simulation']['verification'])
                    self.capture_public_root.mkdir(parents=True,exist_ok=True)
                    (self.capture_public_root/(raw['episode_id']+'.json')).write_text(json.dumps(receipt)+'\n')
                    self.capture_persisted=raw['episode_id']
            return state

    def simulate_capture(self,data):
        config=validate_config(data.get('config'))
        with self.lock:
            if self.capture_worker and self.capture_worker.is_alive():
                raise ValueError('Simulation is still checking the path')
            if self.controller and self.controller.status()['status'] in ('preparing','queued','running'):
                raise ValueError('Wait for your run to end before changing the path')
            self.capture_receipt=None
            self.capture['simulation']=dict(status='planning',config=config,message='Checking the full path and camera views…')
            def work():
                _SIM_SLOTS.acquire()
                try:
                    api=self.api_factory('yam-1')
                    report=api._request('GET','/v1/robots/yam-1/calibration')
                    result=simulate_capture(config,report)
                    token=secrets.token_urlsafe(32)
                    with self.lock:
                        self.capture_receipt=dict(token=token,config=config,report=report,created=time.time(),sha256=result['verification']['sha256'])
                        self.capture['simulation']=dict(status='passed',token=token,**result)
                except Exception as exc:
                    with self.lock:
                        self.capture['simulation']=dict(status='failed',config=config,message=str(exc)[:500])
                finally:
                    _SIM_SLOTS.release()
            self.capture_worker=threading.Thread(target=work,daemon=True)
            self.capture_worker.start()
        return self.capture_status()

    def run_capture(self,data):
        from .path_studio_service import validate_identity,IdentifiedSessionAPI,ACTIVE
        from .controller import RunnerController
        config=validate_config(data.get('config'))
        identity=validate_identity(data.get('identity',self.identity))
        with self.lock:
            receipt=self.capture_receipt
            if (not receipt or not secrets.compare_digest(str(data.get('simulation_token','')),receipt['token'])
                    or config!=receipt['config'] or time.time()-receipt['created']>1800):
                raise ValueError('Simulate these settings again before running the real arms')
            if self.controller and (self.stop_error or getattr(self.controller._session_api,'stop_unconfirmed',False)
                    or self.controller.status()['status'] in ACTIVE
                    or self.controller._worker and self.controller._worker.is_alive()):
                raise ValueError('A run or unconfirmed Stop is still active')
            api=self.api_factory('yam-1')
            report=api._request('GET','/v1/robots/yam-1/calibration')
            if binding(config,report)!=receipt['sha256']:
                self.capture_receipt=None
                raise ValueError('Calibration or planner changed. Simulate again')
            self.identity=identity
            self.identity_path.parent.mkdir(parents=True,exist_ok=True)
            self.identity_path.write_text(json.dumps(identity)+'\n')
            self.policy=MinutePolicy(report,config)
            self.controller=RunnerController(IdentifiedSessionAPI(api,identity),robot_id='yam-1',
                hardware_control_enabled=True,share_conversation=False,recording_root=self.identity_path.parent/'scene-capture-runs')
            self.run_station='yam-1';self.stop_error=None
            self.capture['run_kind']='capture'
            self.capture_report=report
            self.capture['simulation']['status']='used'
            self.capture['simulation']['token']=None
            # Single-use receipt also prevents double-click/reconnection replay.
            self.capture_receipt=None
            self.controller.join_and_run(self.policy,TASK,run_duration_s=240)
            controller=self.controller
            def retain_receipt():
                while self.controller is controller:
                    self.capture_status()
                    if controller.status()['status'] not in ACTIVE:break
                    time.sleep(.5)
            threading.Thread(target=retain_receipt,daemon=True).start()
        return self.status('yam-1')
