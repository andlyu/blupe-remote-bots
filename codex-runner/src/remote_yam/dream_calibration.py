"""Selected controller geometry for Dream's local FK/IK; wire angles stay encoders.

The SDK's joint_units describes checkpoint units, not FK corrections. Generate
per-arm URDF geometry instead: T_origin * R_axis(offset) * R_axis(q_encoder).
The worker registers it before constructing ClientIK, without editing the SDK.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import numpy as np

ROBOHOUSE = 'robot-ba8413962083809c'
TCP_OFFSET_M = .1347


def binding_from_report(report, robot_id):
    from .mujoco_ik import ROBOT_SHA256
    model = report.get('model_joint_calibration') or {}
    if (report.get('schema_version') != 1 or report.get('robot_id') != robot_id or report.get('measurement_scope') != 'calibrated_arm_base'
            or report.get('native_joint_calibration') is not None
            or model.get('coordinate_convention') != 'original_i2rt_model_corrected'
            or model.get('canonical_model_sha256') != ROBOT_SHA256):
        raise ValueError('Dream calibration robot, geometry or encoder convention mismatch')
    for value in (report.get('calibration_id'), model.get('calibration_id')):
        if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
            raise ValueError('Dream requires explicit camera and model calibration IDs')
    spacing = report.get('base_geometry', {}).get('spacing_m')
    if type(spacing) not in (float, int) or not math.isfinite(spacing) or not .3 <= spacing <= 1.:
        raise ValueError('Dream calibration requires measured base spacing')
    arms = model.get('offsets_rad') or {}
    if set(arms) != {'left', 'right'}:
        raise ValueError('Dream calibration requires both arms')
    for values in arms.values():
        if (not isinstance(values, list) or len(values) != 6 or any(type(x) not in (float, int)
                or not math.isfinite(x) for x in values)):
            raise ValueError('Invalid fitted Dream joint corrections')
    result = dict(robot_id=robot_id, model_calibration_id=model['calibration_id'],
                  camera_calibration_id=report['calibration_id'], canonical_model_sha256=ROBOT_SHA256,
                  coordinate_convention=model['coordinate_convention'],
                  wire_coordinates='original encoder radians', base_spacing_m=float(spacing),
                  offsets_rad={side:list(arms[side]) for side in ('left', 'right')},
                  application='geometry only; offsets are not added to feedback or commands',
                  tcp_convention='Dream YAM TCP; native grasp orientation followed by +90deg local Z')
    result['fingerprint'] = hashlib.sha256(json.dumps(result, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return result


def rotation(axis, angle):
    axis = np.asarray(axis, dtype=float)
    axis = axis / np.linalg.norm(axis)
    x, y, z = axis
    skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3) + math.sin(angle)*skew + (1-math.cos(angle))*(skew@skew)


def rpy(matrix):
    # Rz(yaw) Ry(pitch) Rx(roll), including the URDF gimbal-lock boundary.
    pitch = math.atan2(-matrix[2, 0], math.hypot(matrix[0, 0], matrix[1, 0]))
    if abs(math.cos(pitch)) > 1e-12:
        roll, yaw = math.atan2(matrix[2, 1], matrix[2, 2]), math.atan2(matrix[1, 0], matrix[0, 0])
    else:
        roll, yaw = math.atan2(-matrix[1, 2], matrix[1, 1]), 0.
    return ' '.join(format(value, '.17g') for value in (roll, pitch, yaw))


def kinematic_description(binding):
    import mujoco
    from .mujoco_ik import BimanualRelativeIK
    source = BimanualRelativeIK(base_spacing_m=binding['base_spacing_m'],
        joint_offsets_rad=binding['offsets_rad']['left'] + binding['offsets_rad']['right'])
    model, urdfs = source.model, {}
    for side, sign in (('left', 1), ('right', -1)):
        root = ET.Element('robot', name='calibrated_yam_' + side)
        ET.SubElement(root, 'link', name='base_link')
        for index in range(1, 7):
            name = f'{side}_joint{index}'
            joint_id, body_id = model.joint(name).id, model.body(f'{side}_link{index}').id
            parent_id = 0 if index == 1 else model.body(f'{side}_link{index-1}').id
            if (model.jnt_type[joint_id] != mujoco.mjtJoint.mjJNT_HINGE
                    or model.jnt_bodyid[joint_id] != body_id or model.body_parentid[body_id] != parent_id
                    or np.any(model.jnt_pos[joint_id] != 0)):
                raise ValueError('Unsupported canonical YAM joint chain')
            child = f'link_{index}' if index < 6 else 'link_6_native'
            parent = 'base_link' if index == 1 else f'link_{index-1}'
            ET.SubElement(root, 'link', name=child)
            joint = ET.SubElement(root, 'joint', name=f'joint{index}', type='revolute')
            ET.SubElement(joint, 'parent', link=parent); ET.SubElement(joint, 'child', link=child)
            position = model.body_pos[body_id].copy()
            if index == 1:
                position -= [0, sign*binding['base_spacing_m']/2, 0]
            matrix = np.empty(9); mujoco.mju_quat2Mat(matrix, model.body_quat[body_id])
            axis = model.jnt_axis[joint_id]
            matrix = matrix.reshape(3, 3) @ rotation(axis, -model.qpos0[model.jnt_qposadr[joint_id]])
            ET.SubElement(joint, 'origin', xyz=' '.join(map(str, position)), rpy=rpy(matrix))
            ET.SubElement(joint, 'axis', xyz=' '.join(map(str, axis)))
            low, high = model.jnt_range[joint_id]
            ET.SubElement(joint, 'limit', lower=str(low), upper=str(high), effort='100', velocity='3')
        # Native link6 axes differ from the SDK's flange. Preserve the model's
        # trained TCP frame, not an apparent sign flip in motor angle six.
        grasp = model.body(side + '_grasp').id
        matrix = np.empty(9); mujoco.mju_quat2Mat(matrix, model.body_quat[grasp])
        flange = matrix.reshape(3, 3) @ rotation([0, 0, 1], math.pi/2)
        if not np.allclose(flange @ [0, 0, TCP_OFFSET_M], model.body_pos[grasp], atol=1e-12):
            raise ValueError('Canonical grasp and Dream TCP do not agree')
        ET.SubElement(root, 'link', name='link_6')
        fixed = ET.SubElement(root, 'joint', name='sdk_flange', type='fixed')
        ET.SubElement(fixed, 'parent', link='link_6_native'); ET.SubElement(fixed, 'child', link='link_6')
        ET.SubElement(fixed, 'origin', xyz='0 0 0', rpy=rpy(flange))
        urdfs[side] = ET.tostring(root, encoding='unicode')
    return dict(binding=binding, urdfs=urdfs,
        urdf_sha256={side:hashlib.sha256(xml.encode()).hexdigest() for side, xml in urdfs.items()})


_installed = None


def install_sdk_kinematics(description, directory):
    """Private worker only; one selected profile for its complete lifetime."""
    global _installed
    from dream_ik.specs import EMBODIMENTS, TCP_OFFSET_M as sdk_tcp
    identity = description['binding']['fingerprint']
    if _installed is not None:
        if identity != _installed[0] or EMBODIMENTS['yam'] is not _installed[1]:
            raise ValueError('Dream worker calibration cannot change after construction')
        return description['binding']
    if sdk_tcp != TCP_OFFSET_M:
        raise ValueError('Unsupported Dream TCP convention')
    stock = EMBODIMENTS['yam']
    if isinstance(stock.arm, dict) or stock.arm.joint_units is not None:
        raise ValueError('Dream YAM geometry was already changed')
    folder = Path(directory) / 'kinematics' / identity
    folder.mkdir(parents=True, exist_ok=True)
    arms = {}
    for side in ('left', 'right'):
        xml = description['urdfs'][side]
        if hashlib.sha256(xml.encode()).hexdigest() != description['urdf_sha256'][side]:
            raise ValueError('Dream kinematics payload changed')
        path = folder / (side + '.urdf')
        if path.exists() and path.read_text() != xml:
            raise ValueError('Dream kinematics file changed')
        path.write_text(xml)
        arms[side] = stock.arm.model_copy(update={'urdf':path})
    spacing = description['binding']['base_spacing_m']
    obstacles = {side:tuple(obstacle.model_copy(update={'center':(0., sign*spacing/2, 0.)})
                           for obstacle in stock.obstacles[side])
                 for side, sign in (('right', 1), ('left', -1))}
    selected = stock.model_copy(update={'arm':arms, 'obstacles':obstacles,
        'side_base':{'right':(0., 0., 0.), 'left':(0., spacing, 0.)}})
    EMBODIMENTS['yam'] = selected
    _installed = (identity, selected)
    return description['binding']
