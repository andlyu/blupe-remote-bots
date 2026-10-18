"""Declared cube geometry for offline size qualification; no simulator-state input."""
from __future__ import annotations
import copy
import numpy as np
from .yam_cube_reset import COLORS, ResetBlocked, digest


def validate_edges(edges):
    if set(edges)!=set(COLORS):
        raise ResetBlocked('Cube size case must specify all three colors')
    values={c:float(edges[c]) for c in COLORS}
    if any(not np.isfinite(v) or not .025<=v<=.030 for v in values.values()):
        raise ResetBlocked('Qualification cube edges must be25–30mm')
    return values


def edge_m(row):
    """Use declared cube edge, falling back to the established30mm task."""
    value=float(row.get('declared_height_m',.030))
    if not np.isfinite(value) or value<=0:
        raise ResetBlocked('Invalid declared cube edge')
    return value


def resize_row(row, edge, report):
    """Keep XY/support/yaw fixed; recompute top, center and pixel from size."""
    result=copy.deepcopy(row)
    camera=report['cameras']['top']
    left=np.asarray(camera['T_base_camera']['left'])
    inverse=np.linalg.inv(left)
    support=np.array(row['visible_top_center_by_arm']['left']['support_point_m'],float)
    xy=np.asarray(row['visible_top_center_by_arm']['left']['top_center_m'])[:2]
    floor=float(support[2])
    for arm in ('left','right'):
        transform=np.asarray(camera['T_base_camera'][arm])@inverse
        for key,z in (('top_center_m',floor+edge),('support_point_m',floor),('cube_center_m',floor+edge/2)):
            result['visible_top_center_by_arm'][arm][key]=[float(xy[0]),float(xy[1]),z] if arm=='left' else (transform@np.r_[xy,z,1])[:3].tolist()
    top=np.r_[xy,floor+edge]
    cam=(inverse@np.r_[top,1])[:3];k=camera['depth_intrinsics']
    result.update(dimensions_m=[edge,edge],declared_height_m=edge,estimated_height_m=edge,
                  pixel_center=[k['fx']*cam[0]/cam[2]+k['ppx'],k['fy']*cam[1]/cam[2]+k['ppy']])
    result['geometry_source']='Explicit declared cube size qualification; fixed XY and support'
    return result


def resize_scene(scene, edges, report):
    edges=validate_edges(edges)
    return {c:(copy.deepcopy(row) if edge_m(row)==edges[c] else resize_row(row,edges[c],report)) for c,row in scene.items()}


def resize_targets(targets, edges, report):
    edges=validate_edges(edges)
    if targets.get('qualification_cube_edges_m')==edges:
        return copy.deepcopy(targets)
    # Preserve byte-identical30mm baseline goals and their existing bindings.
    if all(v==.030 for v in edges.values()):
        return copy.deepcopy(targets)
    result=copy.deepcopy(targets)
    original=result.pop('content_sha256')
    result['source_task_goals_sha256']=original
    result['qualification_cube_edges_m']=edges
    result['task_geometry']['cube_edges_by_color_m']=edges
    for key in ('cube_edge_m','cube_center_z_m','cube_top_z_m'):result['task_geometry'].pop(key,None)
    result['targets']=resize_scene(result['targets'],edges,report)
    result['content_sha256']=digest(result)
    return result


def size_cases(names):
    """Known dimensions, independent of the hidden10mm positional offsets."""
    cases={'30mm':dict.fromkeys(COLORS,.030),'27.5mm':dict.fromkeys(COLORS,.0275),
           '25mm':dict.fromkeys(COLORS,.025)}
    import itertools
    for i,values in enumerate(itertools.permutations((.025,.0275,.030)),1):
        cases[f'mixed-{i:02}']=dict(zip(COLORS,values))
    if not names or set(names)-set(cases):
        raise ResetBlocked('Unknown or empty cube size case')
    return {name:cases[name] for name in names}
