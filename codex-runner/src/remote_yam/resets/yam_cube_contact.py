"""Read existing reference CAD for a provisional contact pose; never edit it."""
from __future__ import annotations
from .station import resource

import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from .yam_cube_reset import ResetBlocked,plain


def reference_contact(runtime_root):
    """Use I2RT reference meshes and native grasp_site, not cube center as TCP.

    Reference: docs/refs/i2rt-gripper-occlusion/INDEX.md; upstream I2RT
    120c3c81400171174604e503943f8d1ebc891058. Mesh transforms follow the
    native API grasp frame (jaw opening Y).
    """
    import mujoco
    root=Path(resource('gripper_assets'))
    manifest=json.loads((root/'manifest.json').read_text())
    hashes={row['file']:row['sha256'] for row in manifest['files']}
    hashes['linear_4310.xml']=manifest['xml_sha256']
    for filename,expected in hashes.items():
        if hashlib.sha256((root/filename).read_bytes()).hexdigest()!=expected:
            raise ResetBlocked('Reference gripper asset hash changed: '+filename)
    tree=ET.parse(root/'linear_4310.xml').getroot()
    tree.find('compiler').set('meshdir',str(root))
    model=mujoco.MjModel.from_xml_string(ET.tostring(tree,encoding='unicode'))
    data=mujoco.MjData(model);mujoco.mj_forward(model,data)
    site=model.site('grasp_site').id;rotation=data.site_xmat[site].reshape(3,3)
    tips=[]
    for name in ('tip_left','tip_right'):
        gid=next(i for i in range(model.ngeom) if model.geom_bodyid[i]==model.body(name).id)
        mesh=model.geom_dataid[gid];start,count=model.mesh_vertadr[mesh],model.mesh_vertnum[mesh]
        vertices=model.mesh_vert[start:start+count]
        world=vertices@data.geom_xmat[gid].reshape(3,3).T+data.geom_xpos[gid]
        points=(world-data.site_xpos[site])@rotation
        start,count=model.mesh_faceadr[mesh],model.mesh_facenum[mesh]
        triangles=points[model.mesh_face[start:start+count]]
        normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
        area=np.linalg.norm(normals,axis=1);normals/=np.maximum(area[:,None],1e-20)
        selected=(abs(normals[:,1])>.9999)&(triangles.mean(1)[:,2]>-.04)
        groups={}
        for face,weight in zip(triangles[selected],area[selected]):
            y=round(float(face[:,1].mean()),4)
            group=groups.setdefault(y,dict(area=0.,points=[]))
            group['area']+=float(weight/2);group['points'].extend(face.tolist())
        if not groups:raise ResetBlocked('No near-tip opening-axis reference face')
        y,face=max(groups.items(),key=lambda item:item[1]['area'])
        if face['area']<.0002:raise ResetBlocked('Reference pad candidate area is insufficient')
        bounds=np.array([np.min(face['points'],0),np.max(face['points'],0)])
        tips.append(dict(name=name,pad_y_m=y,pad_bounds_native_grasp_m=bounds,
                         pad_area_m2=face['area'],max_tip_z_native_grasp_m=points[:,2].max()))
    pad_center_z=float(np.mean([np.mean(t['pad_bounds_native_grasp_m'][:,2]) for t in tips]))
    closed_gap=tips[0]['pad_y_m']-tips[1]['pad_y_m']
    return plain(dict(source='existing I2RT reference CAD; installed YAM1 contact UNVERIFIED',
        upstream_commit=manifest['upstream_commit'],asset_directory=str(root),asset_sha256=hashes,
        frame='native_api_grasp',jaw_opening_axis='Y',pad_center_z_m=pad_center_z,
        max_tip_z_m=max(t['max_tip_z_native_grasp_m'] for t in tips)+.000001,
        closed_gap_m=closed_gap,opening_travel_m=.095,tips=tips,
        physical_contact_calibration_measured=False))


def contact_for_cube(height, reference):
    """Align CAD pad center with cube center, subject to 5mm tip-floor clearance."""
    error=float(reference.get('candidate_vertical_error_bound_m',0.))
    if not np.isfinite(error) or error<0:
        raise ResetBlocked('Invalid candidate vertical error bound')
    tcp=max(height/2+reference['pad_center_z_m'],reference['max_tip_z_m']+.005+error)
    depth=reference.get('preferred_tcp_depth_below_top_m')
    if depth is not None:
        if not np.isfinite(depth) or not 0<=depth<=.015:
            raise ResetBlocked('Invalid reference-derived grip depth')
        tcp=max(tcp,height-depth)
    spans=[]
    for tip in reference['tips']:
        bounds=np.array(tip['pad_bounds_native_grasp_m'])
        lower,upper=tcp-bounds[1,2],tcp-bounds[0,2]
        overlap=min(min(height,upper+dz)-max(0.,lower+dz) for dz in (-error,error))
        if overlap<.01:raise ResetBlocked('Insufficient reference pad/cube overlap')
        spans.append(dict(pad_world_z_above_support_m=[lower,upper],overlap_m=overlap))
    aperture=(height-reference['closed_gap_m'])/reference['opening_travel_m']
    if not 0<=aperture<=1:raise ResetBlocked('Cube exceeds reference jaw travel')
    return plain(dict(tcp_height_above_support_m=tcp,minimum_reference_tip_clearance_m=tcp-reference['max_tip_z_m'],
        worst_case_tip_clearance_m=tcp-reference['max_tip_z_m']-error,
        candidate_vertical_error_bound_m=error,nominal_aperture=aperture,pads=spans,
        status='CAD candidate only; installed pads, compliance and force/contact remain unverified'))
