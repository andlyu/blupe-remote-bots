"""Hash-traced nominal installed gripper geometry; never changes robot targets."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import numpy as np

YAM1_TOOL_REFERENCE = dict(
    available=True,model='linear_4310',station='yam-1',frame='same tool frame as move_to rotation',
    jaw_opening_axis='Y',approach_axis='Z',physical_contact_calibration_measured=False,
    source_xml_sha256='1ae64edff48e7a1d1de727d90c2a77a98aa519796b72233a26f2c1ab1bf66652',
    tip_mesh_sha256=['03d94f53d7b5e9e1871ea6f3925c68d7a2f894b08e0c575fa0b9ed4024684ff7',
                    '8f620aae9c15e00e2ea4e5bf5e9a49e7edb2d23128b8955cfacc0da8da45c72f'],
    closed_nominal_gap_m=-.001,opening_travel_m=.095,per_jaw_travel_m=.0475,
    pad_opening_signs=[1,-1],pad_center_z_m=.0016706879354441567,
    pad_opening_axes_tool=[[-3.999999999948489e-6,.9999999999920002,7.99987853739026e-12],
                           [0.,-.9999999999910001,-4.242642374197025e-6]],
    max_tip_z_m=.010020504348689839,
    closed_pad_bounds_tool_m=[
        [[-.012440560852250203,-.0005197222644821231,-.006358460493411655],
         [.012629385470384388,-.0005038660947302822,.009498190908815318]],
        [[-.01263007267358724,.0005164451832254027,-.005955405143516168],
         [.012450771308468573,.0005194518015411266,.009498426469889132]]],
    scope='Nominal installed-reference CAD, not measured current gap/contact/force or a collision certificate. '
          'Fixed native grasp origin is retained; distal tip extends about10mm along tool+Z. '
          'max_tip_z includes the reference1micrometre arithmetic guard. '
          'Do not substitute upstream changed attachment/TCP or infer geometry from visual proxies.')

@lru_cache(maxsize=1)
def _installed_reference():
    data=json.loads((Path(__file__).resolve().parents[2]/'config/roboharness-linear4310-reference.json').read_text())
    if data['source_xml_sha256']!=YAM1_TOOL_REFERENCE['source_xml_sha256'] or set(data['parts'])!={'gripper','tip_left','tip_right'}:
        raise ValueError('Gripper reference source binding changed')
    for part in data['parts'].values():
        bounds=np.array(part['closed_bounds_tool_m']);axis=np.array(part['opening_axis_tool'])
        if bounds.shape!=(2,3) or axis.shape!=(3,) or not np.isfinite(bounds).all() or not np.isfinite(axis).all() or np.any(bounds[0]>bounds[1]):
            raise ValueError('Invalid nominal gripper geometry')
    return data


def reference_for_model(ik,robot_id):
    if robot_id not in ('yam-1','robot-ba8413962083809c'):
        return dict(available=False,scope='No registered nominal tool reference')
    data=deepcopy(_installed_reference())
    for body in ik.body_ids:
        if not np.allclose(ik.model.body_pos[body],[0,0,-.1347],atol=1e-9,rtol=0) or abs(float(np.dot(ik.model.body_quat[body],[0,1,0,0])))<1-1e-9:
            return dict(available=False,scope='Canonical grasp mount differs from the installed reference; no geometry substituted')
    ref=deepcopy(YAM1_TOOL_REFERENCE)
    ref.update(station=robot_id,frame='same fixed grasp frame as pose_summary rotation',
        nominal_cad=data,live_installation_verified=False)
    return ref


def _base_box(bounds,axis,travel,fraction,R,position):
    lo,hi=np.array(bounds,dtype=float)+np.array(axis,dtype=float)*travel*fraction
    corners=np.array([[x,y,z] for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])])
    world=corners@R.T+position
    return [world.min(0).tolist(),world.max(0).tolist()],((lo+hi)/2)


def nominal_tool_pose(poses,reference):
    if not reference.get('available'):return dict(available=False,scope='No matching nominal tool geometry')
    arms={}
    for arm in ('left','right'):
        pose=poses[arm];R=np.array(pose['rotation_matrix']);position=np.array(pose['position_m']);fraction=float(pose['gripper'])
        parts={name:_base_box(part['closed_bounds_tool_m'],part['opening_axis_tool'],part['travel_m'],fraction,R,position)[0]
            for name,part in reference['nominal_cad']['parts'].items()}
        pads=[];centers=[]
        for bounds,axis in zip(reference['closed_pad_bounds_tool_m'],reference['pad_opening_axes_tool']):
            box,center=_base_box(bounds,axis,.0475,fraction,R,position);pads.append(box);centers.append(center)
        midpoint=np.mean(centers,axis=0)
        whole=np.array(list(parts.values()))
        arms[arm]=dict(approach_axis_base=R[:,2].tolist(),opening_axis_base=R[:,1].tolist(),
            measured_gripper_fraction=fraction,nominal_gap_m=reference['closed_nominal_gap_m']+.095*fraction,
            pad_midpoint_tool_m=midpoint.tolist(),pad_midpoint_base_m=(position+R@midpoint).tolist(),
            pad_bounds_base_m=pads,part_bounds_base_m=parts,
            whole_tool_bounds_base_m=[whole[:,0].min(0).tolist(),whole[:,1].max(0).tolist()])
    return dict(available=True,coordinate_frame='per_arm_base',units='metres',arms=arms,
        scope='Nominal reference geometry at current measured pose/opening. Not measured contact, force, engagement, live installation, calibration accuracy or a collision certificate. Bounding boxes enclose the three reference gripper parts; attached camera/cables are not modeled. Preserve positive observed support/obstacle clearance and uncertainty.')
