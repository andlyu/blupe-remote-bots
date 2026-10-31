"""Measured native forward kinematics shared by reset perception and planning."""
import math
import numpy as np
from remote_yam.camera_calibration import rigid

class KinematicsNotReady(ValueError):pass

def vector(value, size, label):
    # numpy casts None to NaN; reject absent feedback explicitly.
    data = np.asarray(value, dtype=float)
    if data.shape != (size,) or not np.isfinite(data).all():
        raise KinematicsNotReady(f'{label}: expected {size} finite measured values')
    return data


def arm_pose(report, observation, side):
    """Published POE chain already includes model offsets; never add twice.

    Return a grasp pose in BluPe's base-midpoint frame, metres, Z=base height.
    This frame is relative to the robot bases, not a calibrated floor frame.
    """
    from scipy.spatial.transform import Rotation

    kin = report['kinematics']
    if kin['joint_units'] != 'degrees':
        raise KinematicsNotReady('Unrecognized published kinematic units')
    q = np.deg2rad(vector(observation[side+'_joints_deg'], 6, side+' joints'))
    chain = kin[side]
    if len(chain['joints']) != 6:
        raise KinematicsNotReady('Expected six published joint axes')
    result = np.eye(4)
    for angle, joint in zip(q, chain['joints']):
        axis = vector(joint['axis'], 3, 'joint axis')
        if not np.isclose(np.linalg.norm(axis), 1, atol=1e-5):
            raise KinematicsNotReady('Non-unit published joint axis')
        center = vector(joint['position_m'], 3, 'joint position')
        rotation = Rotation.from_rotvec(axis*angle).as_matrix()
        transform = np.eye(4)
        transform[:3, :3] = rotation
        transform[:3, 3] = center-rotation@center
        result = result@transform
    result = result@rigid(chain['T_base_grasp_zero'])
    spacing = float(report['base_geometry']['spacing_m'])
    if not math.isfinite(spacing) or spacing <= 0:
        raise KinematicsNotReady('Invalid base spacing')
    result[1, 3] += spacing/2 if side == 'left' else -spacing/2
    return result
