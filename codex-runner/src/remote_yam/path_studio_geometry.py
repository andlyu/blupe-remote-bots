"""Local CAD collision guard for drawing, independent of gateway acceptance.

Uses the canonical encoder chain, original arm STLs, and hash-checked installed
I2RT gripper meshes. Only the manufacturer's jaw assembly and the controller's
own-base/first-link adjacency are excluded. No dynamics or motor operations.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from .mujoco_ik import ROBOT_SHA256

ROOT = Path(__file__).resolve().parents[2]


def rotation_mix(a, b, fraction):
    qa, qb = np.empty(4), np.empty(4)
    mujoco.mju_mat2Quat(qa, np.asarray(a).reshape(9))
    mujoco.mju_mat2Quat(qb, np.asarray(b).reshape(9))
    dot = float(qa@qb)
    if dot < 0:
        qb = -qb;dot = -dot
    angle = np.arccos(np.clip(dot, -1., 1.))
    q = ((1-fraction)*qa+fraction*qb if angle < 1e-8 else
         (np.sin((1-fraction)*angle)*qa+np.sin(fraction*angle)*qb)/np.sin(angle))
    q /= np.linalg.norm(q)
    matrix = np.empty(9);mujoco.mju_quat2Mat(matrix, q)
    return matrix.reshape(3, 3)


def rotation_angle(a, b):
    return float(np.arccos(np.clip((np.trace(a@b.T)-1)/2, -1., 1.)))


class DrawingGeometry:
    def __init__(self, spacing, offsets, table_z):
        path = ROOT/'models/yam_bimanual/yam_bimanual.xml'
        if hashlib.sha256(path.read_bytes()).hexdigest() != ROBOT_SHA256:
            raise ValueError('Drawing geometry canonical joint model hash mismatch')
        root = ET.parse(path).getroot()
        root.find('compiler').set('meshdir', str(ROOT/'models/yam/assets'))
        for node in list(root.findall('keyframe')):
            root.remove(node)
        assets, world = root.find('asset'), root.find('worldbody')
        contact = ET.SubElement(root, 'contact')
        profile = json.loads((ROOT/'aspire/robohouse-linear4310.json').read_text())
        grip_path = ROOT/'aspire'/profile['model_xml']
        if hashlib.sha256(grip_path.read_bytes()).hexdigest() != profile['model_xml_sha256']:
            raise ValueError('Drawing gripper XML hash mismatch')
        grip = ET.parse(grip_path).getroot()
        for asset in grip.findall('./asset/mesh'):
            spec = profile['mesh_files'][asset.get('name')]
            mesh_path = ROOT/'aspire'/spec['path']
            if hashlib.sha256(mesh_path.read_bytes()).hexdigest() != spec['sha256']:
                raise ValueError('Drawing gripper mesh hash mismatch')
            asset = deepcopy(asset)
            asset.set('name', 'installed_'+asset.get('name'))
            asset.set('file', str(mesh_path))
            assets.append(asset)
        for index, (side, sign) in enumerate((('left', 1), ('right', -1))):
            base = next(g for g in world.findall('geom') if g.get('mesh') == side+'_base')
            link = world.find(f"body[@name='{side}_link1']")
            delta = sign*(spacing-.7)/2
            for node in (base, link):
                pos = np.fromstring(node.get('pos'), sep=' ');pos[1] += delta
                node.set('pos', ' '.join(map(str, pos)))
            body = ET.SubElement(world, 'body', name=side+'_static_base')
            world.remove(base);body.append(base)
            ET.SubElement(contact, 'exclude', body1=side+'_static_base', body2=side+'_link1')
            for j in range(6):
                node = root.find(f".//joint[@name='{side}_joint{j+1}']")
                node.set('ref', str(-(offsets or [0.]*12)[index*6+j]))
            # Replace the old illustrative boxes with the actual installed CAD.
            grasp = root.find(f".//body[@name='{side}_grasp']")
            for geom in list(grasp.findall('geom')):
                grasp.remove(geom)
            mounted = deepcopy(grip.find('./worldbody/body'))
            for node in mounted.iter():
                if node.get('name'):
                    node.set('name', side+'_installed_'+node.get('name'))
                if node.tag == 'geom':
                    node.set('mesh', 'installed_'+node.get('mesh'))
            root.find(f".//body[@name='{side}_link6']").append(mounted)
            for a, b in (('gripper','tip_left'),('gripper','tip_right'),('tip_left','tip_right')):
                ET.SubElement(contact, 'exclude', body1=side+'_installed_'+a, body2=side+'_installed_'+b)
        # Retain the canonical scene's z=0 floor as well as any higher declared
        # table. A lower controller workspace bound must not relax mesh checks.
        ET.SubElement(world, 'geom', name='drawing_table', type='plane', size='2 2 .01', pos=f'0 0 {max(0.,table_z)}')
        for geom in root.findall('.//geom'):
            geom.set('contype', '1');geom.set('conaffinity', '1')
            # A small CAD clearance margin; gateway checks still apply.
            geom.set('margin', '.0025')
        self.model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding='unicode'))
        self.data = mujoco.MjData(self.model)
        self.arm_qpos = [self.model.joint(f'{s}_joint{j+1}').qposadr[0]
                         for s in ('left','right') for j in range(6)]
        self.jaw_qpos = {s:[self.model.joint(s+'_installed_joint'+str(j)).qposadr[0] for j in (7,8)]
                         for s in ('left','right')}
        self.samples_checked = 0
        self.required_gripper_clearance_m = 0.
        self.min_gripper_clearance_m = float('inf')
        self.last_gripper_clearance_m = None
        self.gripper_geoms = {s:[i for i in range(self.model.ngeom)
            if self.model.body(self.model.geom_bodyid[i]).name.startswith(s+'_installed_')]
            for s in ('left','right')}

    def check(self, q, grips):
        self.data.qpos[self.arm_qpos] = q
        for side, indices in self.jaw_qpos.items():
            self.data.qpos[indices] = .0475*grips[side]
        mujoco.mj_forward(self.model, self.data)
        self.samples_checked += 1
        if self.data.ncon:
            c = self.data.contact[0]
            def label(gid):
                geom = self.model.geom(gid)
                return geom.name or self.model.body(geom.bodyid[0]).name
            raise ValueError(f'Drawing clearance check failed: {label(c.geom1)} / {label(c.geom2)}. No unvalidated path is sent.')
        if self.required_gripper_clearance_m:
            gap = min(mujoco.mj_geomDistance(self.model,self.data,a,b,1.,None)
                      for a in self.gripper_geoms['left'] for b in self.gripper_geoms['right'])
            self.last_gripper_clearance_m = gap
            if gap < self.required_gripper_clearance_m-1e-8:
                raise ValueError(f'Gripper clearance is {gap*1000:.1f} mm; keep at least {self.required_gripper_clearance_m*1000:.0f} mm')
            self.min_gripper_clearance_m = min(self.min_gripper_clearance_m,gap)

    def sweep(self, start, end, grips):
        count = max(1, int(np.ceil(np.max(abs(end-start))/.01)))
        for k in range(1, count+1):
            self.check(start+(end-start)*k/count, grips)
