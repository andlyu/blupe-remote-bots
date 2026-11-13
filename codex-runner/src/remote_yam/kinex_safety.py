"""Kinex's read-only Robo-house controller binding and canonical swept guard.

The controller's immutable safety/model snapshot is an additional local check.
Live queue/lease, Home, measured feedback and gateway validation remain required.
No encoder offsets are added to a command; the model's joint refs own correction.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
PROFILE_ROOT=ROOT/'integrations/kinex/runtime/robohouse'
ROBOHOUSE='robot-ba8413962083809c'


def admission(queue,observation,robot_id,*,now=None,wait_for_clock=False):
    """Queue admission only; never permits an actuator dispatch."""
    row=next((s for s in queue.get('stations',[]) if s.get('jetson_id')==robot_id),{})
    obs=observation.get('observation') or observation.get('payload') or observation
    if now is None and wait_for_clock:
        try:
            lead=max(float(obs['observed_at']),float(queue['generated_at']))-time.time()
            if 0<lead<=.5:time.sleep(lead+.002)
        except (KeyError,TypeError,ValueError):pass
    now=time.time() if now is None else now
    safety=obs.get('safety') or {}
    try:fresh=0<=now-float(obs['observed_at'])<=2 and 0<=now-float(queue['generated_at'])<=5
    except (KeyError,TypeError,ValueError):fresh=False
    if not row.get('connected'):return False,'Robot gateway is disconnected. Restore its connection before running.'
    if (obs.get('jetson_id',obs.get('robot_id'))!=robot_id or obs.get('source')!='hardware'
            or not fresh or safety.get('estop_engaged') is not False):
        return False,'Fresh station identity and safety feedback are required before queue admission.'
    if safety.get('contact_count') not in (None,0) or safety.get('active_contacts') not in (None,0,[]):
        return False,'Station reports contact; operator inspection is required.'
    parked=(row.get('queue_ready') is True and obs.get('queue_ready') is True
            and obs.get('mode')=='DISABLED' and safety.get('ok') is False
            and safety.get('reason')=='hardware_not_initialized')
    ready=(safety.get('ok') is True and obs.get('homed') is True and obs.get('settled') is True
           and row.get('available') is True)
    if parked:return True,'Robo-house is parked and ready for the normal queue. The controller will initialize and Home the arms before Kinex can move.'
    if ready:return True,'Robo-house is ready. Run joins the normal robot queue.'
    return False,'Waiting for operator-enabled queue readiness or safe settled robot feedback.'


class RoboHouseGuard:
    def __init__(self):
        self.profile=json.loads((PROFILE_ROOT/'profile.json').read_text())
        for name,expected in self.profile['sha256'].items():
            if hashlib.sha256((PROFILE_ROOT/name).read_bytes()).hexdigest()!=expected:
                raise ValueError('Robo-house controller snapshot changed: '+name)
        # Load the exact controller source snapshot as an isolated module.
        name='_kinex_controller_safety'
        spec=importlib.util.spec_from_file_location(name,PROFILE_ROOT/'hardware_safety.py')
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
        self.config=module.HardwareSafetyConfig.load(PROFILE_ROOT/'safety.json')
        scene=ET.fromstring((PROFILE_ROOT/'scene.xml').read_text());scene.remove(scene.find('include'))
        robot=ET.fromstring((PROFILE_ROOT/'model.xml').read_text());robot.find('compiler').set('meshdir','.')
        for child in robot:
            if child.tag in ('worldbody','asset'):scene.find(child.tag).extend(list(child))
            else:scene.append(child)
        assets={p.name:p.read_bytes() for p in (ROOT/'models/yam/assets').glob('*.stl')}
        # Enable group-0 contacts before compilation so MuJoCo also computes
        # body broad-phase masks. Mutating geom masks alone leaves cached body
        # masks zero on the inherited visual model. Group-1 markers stay inert.
        for geom in scene.findall('.//geom'):
            if geom.get('group','0')=='0':geom.set('contype','1');geom.set('conaffinity','1')
        # Meshes overlap by 6.1 mm at the fixed base/first-link bearings.
        # These are assembled adjacent bodies, not free collision pairs. Exclude
        # only the two root joints; all other robot, inter-arm and floor pairs stay on.
        contact=ET.SubElement(scene,'contact')
        for side in ('left','right'):ET.SubElement(contact,'exclude',body1='world',body2=side+'_link1')
        self.model=mujoco.MjModel.from_xml_string(ET.tostring(scene,encoding='unicode'),assets)
        self.data=mujoco.MjData(self.model)
        self.guard=module.BimanualHardwareGuard(self.config,forward_kinematics=self.positions,
                                               collision_check=self.clear)

    def validate_report(self,report):
        p=self.profile
        expected={k:p[k] for k in ('calibration_id','coordinate_convention','canonical_model_sha256','offsets_rad') if k in p}
        expected['calibration_id']=p['model_calibration_id']
        if (report.get('robot_id')!=ROBOHOUSE or report.get('native_joint_calibration') is not None
                or report.get('model_joint_calibration')!=expected
                or report.get('base_geometry',{}).get('spacing_m')!=p['base_spacing_m']):
            raise ValueError('Robo-house calibration/encoder binding changed; no command dispatched')
        hashes=(report.get('provenance') or {}).get('selected_file_sha256') or {}
        if hashes and (hashes.get('safety')!=p['sha256']['safety.json'] or hashes.get('model_include')!=p['sha256']['model.xml']):
            raise ValueError('Robo-house published controller provenance changed; no command dispatched')

    def forward(self,q):
        self.data.qpos[:]=q;self.data.qvel[:]=0;mujoco.mj_forward(self.model,self.data)

    def positions(self,q):
        self.forward(q)
        return {arm:tuple(float(v) for v in self.data.body(arm+'_grasp').xpos) for arm in ('left','right')}

    def clear(self,q):
        self.forward(q);return self.data.ncon==0

    def approve(self,start,points):
        q=[np.deg2rad(p['left_joints_deg']+p['right_joints_deg']).tolist() for p in points]
        return self.guard.approve(start,q,cadence_hz=10.)
