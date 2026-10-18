"""Deterministic synthetic cube layouts; never reads or controls hardware."""
from __future__ import annotations

import itertools
import math
import numpy as np

COLORS=('blue','orange','yellow')
EDGE=.030


def rotation(yaw):
    c,s=math.cos(yaw),math.sin(yaw)
    return np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])


def box_separation(a,ra,ha,b,rb,hb):
    """Maximum separating-axis gap of two oriented boxes, in metres.

    Positive means separated, zero means touching, negative means penetration.
    This is a SAT certificate, not a Euclidean surface distance.
    """
    a,b,ra,rb,ha,hb=map(np.asarray,(a,b,ra,rb,ha,hb))
    axes=np.concatenate((ra.T,rb.T,np.cross(ra.T[:,None,:],rb.T[None,:,:]).reshape(-1,3)))
    norms=np.linalg.norm(axes,axis=1);axes=axes[norms>1e-10]/norms[norms>1e-10,None]
    gaps=np.abs(axes@(b-a))-np.abs(axes@ra)@ha-np.abs(axes@rb)@hb
    return float(np.max(gaps))


def pairs(objects):
    result=[]
    for a,b in itertools.combinations(objects,2):
        gap=box_separation(a['center_world_m'],rotation(a['yaw_rad']),[EDGE/2]*3,
                           b['center_world_m'],rotation(b['yaw_rad']),[EDGE/2]*3)
        result.append(dict(colors=sorted([a['color'],b['color']]),separation_m=gap,
                           touching=abs(gap)<=1e-8))
    return result


def generate_layouts(seed=20261017,count=50):
    """Sample a bounded tabletop workspace, including exact face contacts.

    Bounds are scene-generation bounds, not a claim of IK reachability. Color
    assignment is shuffled, so crossed-arm transfers remain part of the test.
    Touching layouts share yaw within each pair/cluster; the third separate
    cube and the separated layouts include independent orientations.
    """
    if count!=50:raise ValueError('This qualification set contains exactly50 layouts')
    rng=np.random.default_rng(seed);layouts=[]
    for index in range(count):
        category='separated' if index<20 else 'touching_pair' if index<40 else 'touching_cluster'
        for attempt in range(10000):
            yaw=float(rng.uniform(-math.pi/2,math.pi/2))
            if category=='separated':
                xy=rng.uniform([.23,-.17],[.39,.17],size=(3,2))
                yaws=rng.uniform(-math.pi/2,math.pi/2,size=3)
            else:
                origin=rng.uniform([.26,-.12],[.36,.12])
                basis=rotation(yaw)[:2,:2]
                offsets=np.array([[0.,0.],[EDGE,0.],[0.,EDGE] if index%2 else [2*EDGE,0.]])
                xy=origin+offsets@basis.T;yaws=np.full(3,yaw)
                if category=='touching_pair':
                    xy[2]=rng.uniform([.23,-.17],[.39,.17]);yaws[2]=rng.uniform(-math.pi/2,math.pi/2)
            if np.any(xy<np.array([.23,-.17])) or np.any(xy>np.array([.39,.17])):continue
            order=rng.permutation(COLORS)
            objects=[dict(color=str(c),center_world_m=[float(p[0]),float(p[1]),EDGE/2],yaw_rad=float(angle))
                     for c,p,angle in zip(order,xy,yaws)]
            contacts=pairs(objects)
            if min(p['separation_m'] for p in contacts)<-1e-9:continue
            touching=sum(p['touching'] for p in contacts)
            if category=='separated' and min(p['separation_m'] for p in contacts)<.008:continue
            if category=='touching_pair' and touching!=1:continue
            if category=='touching_cluster' and touching<2:continue
            layouts.append(dict(id=f'layout-{index+1:02}',category=category,objects=objects,
                                pairs=contacts,touching_pairs=[p['colors'] for p in contacts if p['touching']],
                                generation_attempt=attempt+1))
            break
        else:raise RuntimeError('Could not generate a nonpenetrating layout')
    return layouts


def synthetic_scene(layout,report):
    """Express exact synthetic geometry in the established camera/arm schema."""
    camera=report['cameras']['top'];profile=camera['depth_intrinsics']
    if any(profile['coeffs']):raise ValueError('Synthetic projection requires the established zero-distortion profile')
    transforms={s:np.asarray(camera['T_base_camera'][s]) for s in ('left','right')}
    left_to_right=transforms['right']@np.linalg.inv(transforms['left'])
    camera_from_left=np.linalg.inv(transforms['left'])
    spacing=report['base_geometry']['spacing_m']
    scene={}
    for obj in layout['objects']:
        c=obj['color'];center=np.asarray(obj['center_world_m']);edge=float(obj.get('edge_m',EDGE))
        top=np.array([center[0],center[1]-spacing/2,edge])
        by_arm={s:{} for s in ('left','right')}
        for key,z in [('top_center_m',edge),('support_point_m',0.),('cube_center_m',edge/2)]:
            point=np.r_[top[:2],z];by_arm['left'][key]=point.tolist()
            by_arm['right'][key]=(left_to_right@np.r_[point,1])[:3].tolist()
        cam=(camera_from_left@np.r_[top,1])[:3]
        pixel=[profile['fx']*cam[0]/cam[2]+profile['ppx'],profile['fy']*cam[1]/cam[2]+profile['ppy']]
        scene[c]=dict(color=c,visible_top_center_by_arm=by_arm,pixel_center=pixel,
                      dimensions_m=[edge,edge],declared_height_m=edge,estimated_height_m=edge,
                      yaw_rad=obj['yaw_rad'],support_plane_left=[0.,0.,0.],frame_count=0,
                      spread_xyz_m=[0.,0.,0.],warnings=[],
                      observation_kind='synthetic_exact_geometry_not_live_sensor_data',
                      geometry_source='synthetic qualification: declared cube size,tablez0')
    return scene
