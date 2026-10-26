"""Replay the hardware drawing policy without a session, lease or motor API.

Only measured-state admission is replaced. Calibration binding, targets, IK,
gripper sequencing, CAD sweeps, packet pacing and endpoint checks are shared.
This is kinematic verification; it does not simulate actuator dynamics.
"""
import time

import numpy as np

from .path_studio_policy import PathStudioPolicy, ARMS, JOINT_STEP
from .path_studio_geometry import rotation_angle
from .providers import PolicyComplete
from .session import MAX_COMMANDS, MAX_WAYPOINTS_PER_PACKET

# A reproducible, collision-checked reference pose, not a claim about the
# physical station's current/home position. Coordinates are native encoders.
REFERENCE_JOINTS_RAD = [-.024, .794, .645, -.375, -.021, -.012] * 2


class SimulatedPathPolicy(PathStudioPolicy):
    def _measured(self, observation, *, require_home=False):
        if observation.get('source') != 'simulation' or observation.get('jetson_id') != self.robot_id:
            raise ValueError('Simulation requires its own isolated state')
        return self._joint_state(observation)


def simulate_sketch(sketch, calibration):
    policy = SimulatedPathPolicy(sketch)
    policy.configure_calibration(calibration)
    joints = np.rad2deg(REFERENCE_JOINTS_RAD).reshape(2, 6)
    obs = dict(source='simulation', jetson_id=policy.robot_id, observed_at=time.time(),
               left_joints_deg=joints[0].tolist(), right_joints_deg=joints[1].tolist(),
               left_gripper=1., right_gripper=1.)
    initial = dict(obs)
    frames = [dict(left_joints_deg=obs['left_joints_deg'], right_joints_deg=obs['right_joints_deg'],
                   left_gripper=1., right_gripper=1., phases={})]
    packet_sizes = []
    max_draw_error = max_rotation_error = max_joint_step = max_tool_speed = max_requested_deviation = 0.
    simultaneous_draw_steps=0
    cfg = policy.workspace._safety()
    previous_q = np.array(REFERENCE_JOINTS_RAD)
    policy.ik._forward(previous_q)
    previous_positions = np.array([p.copy() for p, _ in policy.ik._poses()])
    while True:
        try:
            packet = policy.build_trajectory('', obs, len(frames)-1)
        except PolicyComplete:
            break
        if not 1 <= len(packet) <= MAX_WAYPOINTS_PER_PACKET:
            raise ValueError('Simulation packet exceeds the API limit')
        packet_sizes.append(len(packet))
        for point in packet:
            if point['step_id'] != len(frames)-1 or len(frames)-1 >= MAX_COMMANDS:
                raise ValueError('Simulation violates the API step budget')
            q = np.deg2rad(point['left_joints_deg']+point['right_joints_deg'])
            delta = float(np.max(abs(q-previous_q)))
            max_joint_step = max(max_joint_step, delta)
            if delta > JOINT_STEP+1e-9 or np.any(q < np.array(cfg['joint_lower_rad'])-1e-9) or np.any(q > np.array(cfg['joint_upper_rad'])+1e-9):
                raise ValueError('Simulation violates joint limits or pacing')
            moving = delta > 1e-9
            for side in ARMS:
                grip = point.get(side+'_gripper', obs[side+'_gripper'])
                if abs(grip-obs[side+'_gripper']) > .10000001:
                    raise ValueError('Simulation violates gripper pacing')
                if moving and side in policy.active and grip > .05:
                    raise ValueError('Simulation moved before gripper closure')
            obs.update(point, observed_at=time.time())
            phases = policy.step_phases[point['step_id']]
            if all(phases.get(a)=='draw' for a in ARMS):simultaneous_draw_steps+=1
            policy.ik._forward(q)
            poses = policy.ik._poses()
            positions = np.array([p.copy() for p, _ in poses])
            speed = float(np.max(np.linalg.norm(positions-previous_positions, axis=1)))*10
            max_tool_speed = max(max_tool_speed, speed)
            # IK converges numerically: allow 0.1 mm/step of residual error.
            if speed > policy.sketch['speed_m_s']+.001:
                raise ValueError('Simulation violates Cartesian speed pacing')
            for i, side in enumerate(ARMS):
                if phases.get(side) != 'draw':
                    continue
                position, rotation = poses[i]
                path = policy.active[side]
                a, d = path[:-1], np.diff(path, axis=0)
                t = np.clip(np.sum((position-a)*d, axis=1)/np.maximum(np.sum(d*d, axis=1), 1e-20), 0, 1)
                error = float(np.linalg.norm(position-(a+t[:, None]*d), axis=1).min())
                angle = rotation_angle(rotation, policy.tool_rotations[i])
                max_draw_error = max(max_draw_error, error)
                max_rotation_error = max(max_rotation_error, angle)
                requested=policy.requested_paths[side]
                ra,rd=requested[:-1],np.diff(requested,axis=0)
                rt=np.clip(np.sum((position-ra)*rd,axis=1)/np.maximum(np.sum(rd*rd,axis=1),1e-20),0,1)
                max_requested_deviation=max(max_requested_deviation,float(np.linalg.norm(position-(ra+rt[:,None]*rd),axis=1).min()))
                if error > .003 or angle > .035:
                    raise ValueError('Simulated tool left the drawing or orientation tolerance')
            frames.append({k: obs[k] for k in ('left_joints_deg', 'right_joints_deg', 'left_gripper', 'right_gripper')} | dict(phases=phases))
            previous_q, previous_positions = q, positions
        policy.trajectory_completed(obs, len(packet))
    offsets = policy.workspace.joint_offsets_rad or [0.]*12
    return dict(schema='blupe.constrained-simulation.v1', station=policy.sketch['station'],
        cadence_hz=10, duration_s=(len(frames)-1)/10, frames=frames,
        paths_m={a:path.tolist() for a,path in policy.active.items()},
        calibration=dict(spacing_m=policy.spacing, joint_offsets_rad={a:list(offsets[i*6:i*6+6]) for i,a in enumerate(ARMS)}),
        verification=dict(passed=True, source='shared_hardware_planner',
            starting_state='reference_pose_fully_open_grippers', baseline=initial,
            calibration_source='read_only_station_api', controller_profile=policy.workspace.profile,
            live_controller_configuration_verified=bool((calibration.get('provenance') or {}).get('selected_file_sha256')),
            waypoint_count=len(frames)-1, packet_sizes=packet_sizes,
            simultaneous_draw_steps=simultaneous_draw_steps, max_requested_path_deviation_m=max_requested_deviation,
            max_draw_error_m=max_draw_error, max_orientation_error_rad=max_rotation_error,
            max_joint_step_rad=max_joint_step, max_tool_speed_m_s=max_tool_speed,
            checks=['joint_limits', 'workspace', 'tool_orientation', 'gripper_closure',
                    'arm_and_gripper_cad', 'table_clearance', 'swept_collisions',
                    'cartesian_speed', 'joint_speed', 'api_packet_and_session_limits', 'drawing_tracking'],
            **policy.public_config()['path_progress']))
