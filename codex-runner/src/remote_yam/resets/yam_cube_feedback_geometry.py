"""Geometry-only grasp corrections shared by real and simulated cube runners.

Inputs are declared dimensions, camera estimates and measured joint state.
No simulator object pose or physical I/O is available here.
"""
from __future__ import annotations
import copy
import math
import numpy as np
from scipy.spatial.transform import Rotation
from remote_yam.mujoco_ik import IKConvergenceError
from .yam_cube_primitives import solve_endpoint
from .yam_cube_reset import ResetBlocked

def neighbor_side_arm(planner,color,scene):
    """Exploratory arm preference from observed free-space geometry only."""
    from .yam_cube_touch import scene_boxes
    from .yam_cube_scenes import box_separation
    boxes = scene_boxes(scene,planner.spacing)
    selected = boxes[color]
    neighbors = [(box_separation(selected['center'],selected['rotation'],selected['half_size'],
                                row['center'],row['rotation'],row['half_size']),row)
                 for other,row in boxes.items() if other!=color]
    if not neighbors:
        return None
    gap,nearest = min(neighbors,key=lambda row:row[0])
    if gap>=.004:
        return None
    direction = nearest['center'][:2]-selected['center'][:2]
    # The failed near-side grasp deflected away from its own base into the
    # neighbor during closure. Test the arm whose base lies toward that neighbor.
    return 'left' if direction[1]>=0 else 'right'


def retarget_source(planner, plan, nominal, observed, state, *, scene=None):
    """Retarget only the pickup and the start of transit, preserving final goals."""
    delta = planner.world(observed)-planner.world(nominal)
    delta[2] = 0.  # Source plans already use the declared edge on the table plane.
    yaw = (observed['yaw_rad']-nominal['yaw_rad']+math.pi/4)%(math.pi/2)-math.pi/4
    corrected = copy.deepcopy(plan)
    side = plan['arm']
    index = 0 if side=='left' else 1
    inactive = slice((1-index)*6,(2-index)*6)
    source_stages = ('align','descend','close','lift_clear','lift')
    peel = np.zeros(3)
    if scene is not None:
        from .yam_cube_touch import scene_boxes
        from .yam_cube_scenes import box_separation
        boxes = scene_boxes(scene,planner.spacing)
        selected = boxes[plan['color']]
        for color,neighbor in boxes.items():
            if color==plan['color']:
                continue
            gap = box_separation(selected['center'],selected['rotation'],selected['half_size'],
                                 neighbor['center'],neighbor['rotation'],neighbor['half_size'])
            direction = selected['center'][:2]-neighbor['center'][:2]
            if gap<.004 and np.linalg.norm(direction)>1e-9:
                peel[:2] += (.004-gap)*direction/np.linalg.norm(direction)
        if np.linalg.norm(peel)>1e-9:
            peel *= .003/np.linalg.norm(peel)
    has_lift_clear = any(s['name']=='lift_clear' for s in plan['stages'])
    previous_peel=np.asarray(plan.get('camera_source_correction',{}).get('initial_lift_separation_world_m',[0.,0.,0.]),float)
    peel_delta=peel-previous_peel
    close_rotation=np.asarray(next(s['expected_rotation'] for s in plan['stages'] if s['name']=='close'))
    yaw_rotation=Rotation.from_euler('z',yaw).as_matrix()
    offset_rotation=(yaw_rotation@close_rotation[:,0]-close_rotation[:,0])*float(plan.get('grasp_offset_native_x_m',0.))
    pickup_delta=delta+offset_rotation
    from .yam_cube_grasps import aperture_for_gap,pregrasp_aperture,grasp_aperture
    width = plan.get('contact_geometry',{}).get('projected_grasp_width_m',.030)
    minimum_release = aperture_for_gap(width+.010,planner.contact_reference)
    minimum_open = pregrasp_aperture(width,.010,planner.contact_reference,
        float(getattr(planner,'pregrasp_extra_open_gap_m',0.)))
    corrected['pregrasp_aperture']=max(float(plan.get('pregrasp_aperture',0.)),minimum_open)
    corrected['pregrasp_extra_open_gap_m']=float(getattr(planner,'pregrasp_extra_open_gap_m',0.))
    relief=float(getattr(planner,'grasp_gap_relief_m',0.))
    compression=float(getattr(planner,'grasp_compression_m',0.))
    contact_closed=grasp_aperture(width,planner.contact_reference,
                              compression_m=compression,gap_relief_m=relief)
    command_gap=getattr(planner,'grasp_command_gap_m',None)
    compressed=grasp_aperture(width,planner.contact_reference,
                              compression_m=compression,gap_relief_m=relief,command_gap_m=command_gap)
    corrected['grasp_compression_m']=compression
    corrected['grasp_gap_relief_m']=relief
    corrected['grasp_command_gap_m']=command_gap
    corrected['contact_geometry']['nominal_aperture']=contact_closed
    corrected['contact_geometry']['commanded_aperture']=compressed
    changed = 0
    for stage in corrected['stages']:
        name = stage['name']
        if name=='view_clear':
            continue  # The normal auditor regenerates the final Home return.
        if name=='open':
            stage['points_rad'] = [copy.deepcopy(state['joints'])]
            stage['grippers'][index] = max(stage['grippers'][index],minimum_open)
            stage['grippers'][1-index] = state['right_gripper' if index==0 else 'left_gripper']
            continue
        points = []
        for i, q in enumerate(stage['points_rad']):
            fraction = (i+1)/len(stage['points_rad'])
            weight = 1. if name in source_stages else fraction if name=='approach' else 1-fraction if name=='transfer' else 0.
            peel_weight = 1. if name=='lift_clear' or name=='lift' and not has_lift_clear else 1-fraction if name=='transfer' and not has_lift_clear else 0.
            seed = np.array(q, float)
            seed[inactive] = np.asarray(state['joints'])[inactive]
            if weight or peel_weight:
                planner.ik._forward(seed)
                old_p, old_r = planner.ik._poses()[index]
                wanted_p = old_p.copy()+weight*pickup_delta+peel_weight*peel_delta
                wanted_r = Rotation.from_euler('z',weight*yaw).as_matrix()@old_r
                try:
                    seed = solve_endpoint(planner,seed,side,wanted_p,wanted_r)
                except IKConvergenceError as exc:
                    raise ResetBlocked('Measured-source correction requires a new IK branch: '+str(exc)) from exc
                changed += 1
            points.append(seed.tolist())
        stage['points_rad'] = points
        if name in source_stages or name=='approach':
            terminal_peel = peel_delta if name=='lift_clear' or name=='lift' and not has_lift_clear else np.zeros(3)
            stage['expected_tip_world_m'] = (np.asarray(stage['expected_tip_world_m'])+pickup_delta+terminal_peel).tolist()
            stage['expected_rotation'] = (Rotation.from_euler('z',yaw).as_matrix()@np.asarray(stage['expected_rotation'])).tolist()
        stage['grippers'][1-index] = state['right_gripper' if index==0 else 'left_gripper']
        if name in ('approach','align','descend'):
            stage['grippers'][index] = max(stage['grippers'][index],minimum_open)
        if name in ('release','retreat_clear'):
            stage['grippers'][index] = max(stage['grippers'][index],minimum_release)
        if name=='close' or stage.get('carrying'):
            stage['grippers'][index]=compressed
    corrected['stages'] = [s for s in corrected['stages'] if s['name']!='view_clear']
    corrected['camera_source_correction'] = dict(delta_world_m=delta.tolist(),yaw_delta_rad=yaw,
        grasp_offset_rotation_world_m=offset_rotation.tolist(),
        initial_lift_separation_world_m=peel.tolist(),
        changed_waypoints=changed,source='calibrated RGB-D scene estimate; no simulator object state')
    if 'destination_yaw_offset_rad' in corrected:
        corrected['destination_yaw_offset_rad'] -= yaw
    if 'grasp_yaw_rad' in corrected:
        corrected['grasp_yaw_rad'] += yaw
    return corrected



def fit_scene_nonpenetration(scene, report, *, max_correction_m=.002):
    """Fit physical nonpenetration within a stated camera-error allowance.

    This uses only measured centers/headings and declared per-color cube dimensions.
    It never consults actual object positions, moves a physical body, clips a
    sampled perturbation or changes the goal tolerance.
    """
    import itertools
    from .yam_cube_scenes import rotation
    from .yam_cube_sizes import edge_m
    from .yam_cube_reset import ResetBlocked
    fitted = copy.deepcopy(scene)
    names = tuple(scene)
    original = {c: np.array(scene[c]['visible_top_center_by_arm']['left']['top_center_m'][:2],float) for c in names}
    centers = {c: p.copy() for c,p in original.items()}
    axes = {c: rotation(scene[c]['yaw_rad'])[:2,:2] for c in names}
    for _ in range(100):
        overlap = False
        for a,b in itertools.combinations(names,2):
            directions = np.concatenate([axes[a].T,axes[b].T])
            d = centers[b]-centers[a]
            gaps = np.abs(directions@d)-edge_m(scene[a])/2*np.abs(directions@axes[a]).sum(1)-edge_m(scene[b])/2*np.abs(directions@axes[b]).sum(1)
            best = int(np.argmax(gaps))
            if gaps[best] >= -1e-10:
                continue
            overlap = True
            normal = directions[best] * (1. if directions[best]@d>=0 else -1.)
            shift = -.5*gaps[best]*normal
            centers[a] -= shift
            centers[b] += shift
        if any(np.linalg.norm(centers[c]-original[c])>max_correction_m for c in names):
            raise ResetBlocked('Camera nonpenetration fit exceeds its2mm exploratory allowance')
        if not overlap:
            break
    else:
        raise ResetBlocked('Camera nonpenetration fit did not converge')
    camera = report['cameras']['top']['T_base_camera']
    left_inverse = np.linalg.inv(np.asarray(camera['left']))
    for color in names:
        for arm in ('left','right'):
            transform = np.asarray(camera[arm])@left_inverse
            translation=(transform@np.r_[centers[color]-original[color],0.,0.])[:3]
            for key,point in fitted[color]['visible_top_center_by_arm'][arm].items():
                if key in ('top_center_m','support_point_m','cube_center_m'):
                    fitted[color]['visible_top_center_by_arm'][arm][key]=(np.asarray(point)+translation).tolist()
        fitted[color]['camera_nonpenetration_fit'] = dict(raw_left_xy_m=original[color].tolist(),
            correction_xy_m=(centers[color]-original[color]).tolist(),max_correction_m=max_correction_m)
    return fitted
