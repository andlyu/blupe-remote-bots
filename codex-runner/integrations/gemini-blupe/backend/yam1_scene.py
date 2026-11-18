"""YAM1 geometry adapter for Google's generic MuJoCo robotics helpers.

The installed linear4310 XML differs from upstream 120c3c8 in mount/TCP.
Use the captured installed file, not the current upstream mount. Arm dynamics
are the canonical runner's nominal values; finger gains are Google's YAM Pro
simulation values, not a measured YAM1 contact/force calibration.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

ARMS = ('left', 'right')
MODEL_SHA256 = '273d44b2829b433f8913abaf883419ca88170762bda3d50faa33fe886b73b42c'
SCENE_SHA256 = '7f82c3ff37df703978064b74c0dfb637449613640211e2e27a25dc6b10072f1b'
SAFETY_SHA256 = '9a305c10a44e1093ebd21d138e992443263edb8dc5c06c3004c62371f2d3c69f'
INSTALLED_SHA256 = '1ae64edff48e7a1d1de727d90c2a77a98aa519796b72233a26f2c1ab1bf66652'
ARM_ASSETS = {
    'base.stl': '7d57efce4cd31db5e461e1bc83362943a7dbe0e8e101cdb94c29de0a72f3ff0f',
    'link1.stl': '2283bab1300cfdd1a04aaf09503093d7d6d19bf2144abf3429d563b596920903',
    'link2.stl': '4fd4df2916be71391c6c6ea6ffbdb3c270ce67c71c2bb7d42d44736c0be2af98',
    'link3.stl': '5b51658509771514738d0f2271df5f271cd8ae0b6a4bf3787d8463d5ab582593',
    'link4.stl': 'f6e980b8064a1396b17e87065de50286abf616f94b55e1ccff92e889218de220',
    'link5.stl': 'b32ece2e963cd028d68290a904223826070be52ce8f0988e3ad36bf75be3582f',
}
GRIPPER_ASSETS = {
    'gripper.stl': 'd949c401186197d842ca8f9b23bfcbf24bed8461b421df06093c65e4ead21f5d',
    'tip_left.stl': '03d94f53d7b5e9e1871ea6f3925c68d7a2f894b08e0c575fa0b9ed4024684ff7',
    'tip_right.stl': '8f620aae9c15e00e2ea4e5bf5e9a49e7edb2d23128b8955cfacc0da8da45c72f',
}
CV_FROM_MJ = np.diag([1., -1., -1.])
FINGER_TRAVEL_M = .0475


def checked_bytes(path, expected):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f'Scene input hash changed: {Path(path).name}')
    return data


def words(values):
    return ' '.join(format(float(v), '.17g') for v in values)


def rigid(value):
    a = np.asarray(value, dtype=np.float64)
    if (a.shape != (4, 4) or not np.isfinite(a).all()
            or not np.allclose(a[3], [0, 0, 0, 1], rtol=0, atol=1e-9)
            or not np.allclose(a[:3, :3].T @ a[:3, :3], np.eye(3), rtol=0, atol=1e-6)
            or not np.isclose(np.linalg.det(a[:3, :3]), 1., rtol=0, atol=1e-6)):
        raise ValueError('Camera calibration requires a finite rigid transform')
    return a


def add_camera(parent, name, camera, transform_cv):
    """MJCF pinhole calibration; no claim of matching Brown lens distortion.

    MuJoCo XMLreference body/camera: principalpixel is an offset from centre.
    Google's camera_intrinsics_from_model / camera_world_pose_opencv at
    robotics-antigravity-plugin 9cb7f624 define these exact sign conventions.
    """
    t = rigid(transform_cv)
    k = np.asarray(camera['K'], dtype=np.float64)
    w, h = camera['image_size']
    if (k.shape != (3, 3) or not np.isfinite(k).all()
            or k[0, 0] <= 0 or k[1, 1] <= 0
            or not np.allclose(k[2], [0, 0, 1], atol=1e-12, rtol=0)
            or k[0, 1] != 0 or k[1, 0] != 0
            or type(w) is not int or type(h) is not int or min(w, h) <= 0):
        raise ValueError('Camera requires calibrated zero-skew pinhole K and image size')
    quat = np.zeros(4)
    mujoco.mju_mat2Quat(quat, (t[:3, :3] @ CV_FROM_MJ).reshape(-1))
    ET.SubElement(parent, 'camera', name=name, pos=words(t[:3, 3]), quat=words(quat),
                  resolution=f'{w} {h}', sensorsize='1 1',
                  focalpixel=words([k[0, 0], k[1, 1]]),
                  principalpixel=words([w / 2 - k[0, 2], k[1, 2] - h / 2]))


def build_xml(runner_root, gripper_dir, calibration):
    runner_root, gripper_dir = Path(runner_root), Path(gripper_dir)
    root = ET.fromstring(checked_bytes(runner_root / 'models/yam_bimanual/yam_bimanual.xml', MODEL_SHA256))
    checked_bytes(runner_root / 'models/yam_bimanual/scene.xml', SCENE_SHA256)
    safety = json.loads(checked_bytes(runner_root / 'config/controller-workspaces/native-both-20260929.safety.json', SAFETY_SHA256))
    stock = ET.fromstring(checked_bytes(gripper_dir / 'linear_4310.xml', INSTALLED_SHA256))
    mount = stock.find('worldbody/body')
    if mount.get('pos') != '0 0 0' or mount.get('quat') != '1 0 0 0':
        raise ValueError('Installed tool mount must match canonical link6 frame')
    if (calibration['robot_id'] != 'yam-1'
            or calibration['native_joint_calibration']['coordinate_convention'] != 'native_i2rt_updated'
            or any(v != 0 for side in ARMS for v in calibration['native_joint_calibration']['additional_offsets_rad'][side])):
        raise ValueError('YAM1 scene expects already-corrected native angles with no additional offsets')
    spacing = calibration['base_geometry']['spacing_m']
    if type(spacing) not in (int, float) or not np.isfinite(spacing) or not .3 <= spacing <= 1.:
        raise ValueError('Calibrated base spacing must be between .3 and 1 metre')
    kinematics = calibration['kinematics']
    if (kinematics['robot_model_sha256'] != MODEL_SHA256
            or kinematics['scene_sha256'] != SCENE_SHA256):
        raise ValueError('Camera calibration belongs to different robot geometry')
    root.set('model', 'gemini_yam1_installed_geometry')
    root.find('compiler').set('meshdir', str((runner_root / 'models/yam/assets').resolve()))
    root.remove(root.find('keyframe'))
    root.remove(root.find('size'))
    ET.SubElement(root, 'option', timestep='.002', integrator='implicitfast')
    ET.SubElement(root, 'statistic', center='.25 0 .25', extent='1.4')
    visual = ET.SubElement(root, 'visual')
    ET.SubElement(visual, 'global', offwidth='640', offheight='360')
    ET.SubElement(visual, 'headlight', ambient='.35 .35 .35', diffuse='.65 .65 .65')
    assets = root.find('asset')
    for mesh in assets.findall('mesh'):
        file = mesh.get('file')
        checked_bytes(runner_root / 'models/yam/assets' / file, ARM_ASSETS[file])
        mesh.set('file', str((runner_root / 'models/yam/assets' / file).resolve()))
    for mesh in stock.findall('asset/mesh'):
        file = mesh.get('file')
        checked_bytes(gripper_dir / file, GRIPPER_ASSETS[file])
        ET.SubElement(assets, 'mesh', name='installed_' + mesh.get('name'), file=str((gripper_dir / file).resolve()))
    world, actuator = root.find('worldbody'), root.find('actuator')
    contact, equality = ET.SubElement(root, 'contact'), ET.SubElement(root, 'equality')
    ET.SubElement(world, 'light', pos='.2 0 1.5', dir='0 0 -1', directional='true')
    # Visible support plane from the camera-calibration base convention, not
    # the native guard's separate table_z=-.16 frame. Never rewrite that guard.
    ET.SubElement(world, 'geom', name='support', type='plane', size='2 2 .01', rgba='.22 .25 .28 1')
    for i, (side, sign) in enumerate((('left', 1), ('right', -1))):
        base = root.find(f".//body[@name='{side}_link1']")
        pos = np.fromstring(base.get('pos'), sep=' ')
        delta = sign * spacing / 2 - pos[1]
        pos[1] += delta
        base.set('pos', words(pos))
        for geom in world.findall('geom'):
            if geom.get('mesh') == side + '_base':
                p = np.fromstring(geom.get('pos'), sep=' '); p[1] += delta
                geom.set('pos', words(p))
        for j in range(6):
            root.find(f".//joint[@name='{side}_joint{j+1}']").set(
                'range', words([safety['joint_lower_rad'][i*6+j], safety['joint_upper_rad'][i*6+j]]))
        link = root.find(f".//body[@name='{side}_link6']")
        # Replace both dummy tool masses and static proxy fingers. The source
        # gripper's actual inertial belongs in the same identity-mounted frame.
        link.remove(link.find('inertial'))
        grasp = link.find(f"body[@name='{side}_grasp']")
        for child in list(grasp):
            grasp.remove(child)
        for child in mount:
            node = deepcopy(child)
            for element in node.iter():
                for key in ('name', 'joint', 'body1', 'body2'):
                    if key in element.attrib:
                        element.set(key, side + '_installed_' + element.get(key))
                if 'mesh' in element.attrib:
                    element.set('mesh', 'installed_' + element.get('mesh'))
                if element.tag == 'joint':
                    # Google Playground's published nominal finger dynamics.
                    element.set('armature', '.1'); element.set('damping', '150')
                    element.set('frictionloss', '.1')
                if element.tag == 'site':
                    # Calibration/IK markers are frames, not visible objects
                    # in the task images supplied to generated controllers.
                    element.set('rgba', '0 0 0 0')
            link.append(node)
        for source in stock.findall('contact/exclude'):
            names = {key: side + '_link6' if source.get(key) == 'gripper'
                     else side + '_installed_' + source.get(key) for key in ('body1', 'body2')}
            ET.SubElement(contact, 'exclude', **names)
        ET.SubElement(equality, 'joint', name=side + '_finger_coupling',
                      joint1=side + '_installed_joint7', joint2=side + '_installed_joint8', polycoef='0 1 0 0 0')
        ET.SubElement(actuator, 'position', name=side + '_gripper', joint=side + '_installed_joint7',
                      kp='2000', kv='150', ctrlrange='-.005 .0475', ctrllimited='true')
        camera = calibration['cameras'][side]
        if camera['parent_frame'] != side + '_grasp':
            raise ValueError('Wrist camera must use the canonical native grasp frame')
        add_camera(grasp, side, camera, camera['T_grasp_camera'])
    top = calibration['cameras']['top']
    poses = []
    for side, sign in (('left', 1), ('right', -1)):
        t = rigid(top['T_base_camera'][side]).copy(); t[1, 3] += sign * spacing / 2
        poses.append(t)
    if not np.allclose(poses[0], poses[1], atol=1e-8, rtol=0):
        raise ValueError('Overhead camera arm-relative transforms disagree in common world')
    add_camera(world, 'top', top, poses[0])
    return ET.tostring(root, encoding='unicode'), safety


class Yam1Scene:
    def __init__(self, runner_root, gripper_dir, calibration):
        self.calibration = deepcopy(calibration)
        self.xml, self.safety = build_xml(runner_root, gripper_dir, calibration)
        self.model = mujoco.MjModel.from_xml_string(self.xml)
        self.data = mujoco.MjData(self.model)
        self.arm_qpos, self.arm_dof, self.finger_qpos, self.actuators = {}, {}, {}, {}
        for side in ARMS:
            joints = [self.model.joint(f'{side}_joint{j}') for j in range(1, 7)]
            self.arm_qpos[side] = [int(j.qposadr[0]) for j in joints]
            self.arm_dof[side] = [int(j.dofadr[0]) for j in joints]
            self.finger_qpos[side] = [int(self.model.joint(f'{side}_installed_joint{j}').qposadr[0]) for j in (7, 8)]
            self.actuators[side] = [int(self.model.actuator(f'{side}_joint{j}').id) for j in range(1, 7)]
        self.model_revision = hashlib.sha256(self.xml.encode()).hexdigest()

    def set_configuration(self, arms_rad, grippers):
        # Validate the whole configuration before mutating simulation state.
        q = self.data.qpos.copy()
        for i, side in enumerate(ARMS):
            joints = np.asarray(arms_rad[side], dtype=float)
            g = grippers[side]
            if (joints.shape != (6,) or not np.isfinite(joints).all()
                    or np.any(joints < self.safety['joint_lower_rad'][i*6:(i+1)*6])
                    or np.any(joints > self.safety['joint_upper_rad'][i*6:(i+1)*6])
                    or type(g) not in (float, int) or not np.isfinite(g) or not 0 <= g <= 1):
                raise ValueError('Scene configuration must be within native joint and normalized gripper limits')
            q[self.arm_qpos[side]] = joints
            q[self.finger_qpos[side]] = float(g) * FINGER_TRAVEL_M
        self.data.qpos[:] = q
        self.data.qvel[:] = 0
        for side in ARMS:
            self.data.ctrl[self.actuators[side]] = q[self.arm_qpos[side]]
            self.data.ctrl[self.model.actuator(side + '_gripper').id] = -.005 + float(grippers[side]) * .0525
        mujoco.mj_forward(self.model, self.data)

    def receipt(self):
        return dict(scope='Installed bimanual YAM1 kinematics, articulated fingers and provisional pinhole camera transforms',
                    physical=False, task_success_verified=False, geometry_qualified=False,
                    robot_model_sha256=MODEL_SHA256, scene_source_sha256=SCENE_SHA256,
                    installed_tool_sha256=INSTALLED_SHA256, native_safety_sha256=SAFETY_SHA256,
                    calibration_id=self.calibration['calibration_id'],
                    native_joint_calibration_id=self.calibration['native_joint_calibration']['calibration_id'],
                    base_geometry=self.calibration['base_geometry'], model_nq=self.model.nq,
                    arm_qpos_indices=self.arm_qpos, finger_qpos_indices=self.finger_qpos,
                    limitations=['Camera extrinsics retain source provisional accuracy; no new physical calibration.',
                                 'Pinhole images do not reproduce captured Brown lens distortion.',
                                 'Arm inertias/gains are nominal canonical values; finger gains are the Google YAM Pro simulation assumption.',
                                 'Arm visuals remain collision-disabled and finger meshes use convex contacts; this is not a qualified manipulation collision model.',
                                 'Support plane is illustrative; native workspace/contact guards are unchanged.'])
