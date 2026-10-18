"""Plan from both low contact poses, then connect their clear transit poses."""
import copy
import math
import numpy as np
from scipy.spatial.transform import Rotation
from .yam_cube_reset import ResetBlocked


def solve_endpoint(planner,seed,side,point,rotation):
    cache=getattr(planner,'_endpoint_cache',None)
    if cache is None:cache=planner._endpoint_cache={}
    key=(np.asarray(seed).tobytes(),side,np.asarray(point).tobytes(),np.asarray(rotation).tobytes())
    if key in cache:
        ok,value=cache[key]
        if not ok:raise value[0](*value[1])
        return value.copy()
    idx=0 if side=='left' else 1;inactive=slice(6,12) if idx==0 else slice(0,6)
    try:
        planner.ik._forward(seed);poses=list(planner.ik._poses());poses[idx]=(point,rotation)
        solved=planner.ik._solve(seed,tuple(poses));solved[inactive]=seed[inactive]
        planner.ik._forward(solved);actual,r=planner.ik._poses()[idx]
        if (not np.isfinite(solved).all() or np.any(solved<planner.ik.low) or np.any(solved>planner.ik.high)
                or np.linalg.norm(actual-point)>.002 or Rotation.from_matrix(rotation@r.T).magnitude()>.01
                or planner.ik.data.ncon):
            raise ResetBlocked('Contact endpoint violates existing IK/bounds/collision gates')
    except (ValueError,RuntimeError) as exc:
        cache[key]=(False,(type(exc),exc.args));raise
    cache[key]=(True,solved.copy());return solved


def joint_bridge(planner,start,end,side,scene,color,*,carrying=False,contact=False):
    start=np.asarray(start);end=np.asarray(end);idx=0 if side=='left' else 1
    inactive=slice(6,12) if idx==0 else slice(0,6)
    if (not np.isfinite(end).all() or not np.array_equal(start[inactive],end[inactive])
            or np.any(end<planner.ik.low) or np.any(end>planner.ik.high)):
        raise ResetBlocked('Joint bridge changes inactive arm or existing bounds')
    count=max(1,math.ceil(np.max(abs(end-start))/.005))
    for fraction in np.linspace(0,1,count+1):
        planner.ik._forward(start+fraction*(end-start))
        if planner.ik.data.ncon:raise ResetBlocked('Canonical collision along joint bridge')
        planner.check_cube_clearance(planner.ik._poses()[idx][0],scene,color,carrying=carrying,contact=contact,defer_object_clearance=True)
    return [end.copy()]


def reverse_approach(planner,start,side,scene,color,close,low,high,rotation,approach_rotation):
    closed=solve_endpoint(planner,start,side,close,rotation)
    to_low=planner.path(closed,side,low,approach_rotation,scene,color,contact=True,defer_object_clearance=True)
    to_high=planner.path(to_low[-1],side,high,approach_rotation,scene,color,contact=True,defer_object_clearance=True)
    approach=joint_bridge(planner,start,to_high[-1],side,scene,color)
    align=list(reversed([to_low[-1],*to_high]))[1:]
    descend=list(reversed([closed,*to_low]))[1:]
    return approach,copy.deepcopy(align),copy.deepcopy(descend),closed


def destination_transit(planner,start,side,scene,color,close,low,high,rotation):
    closed=solve_endpoint(planner,start,side,close,rotation)
    to_low=planner.path(closed,side,low,rotation,scene,color,contact=True,defer_object_clearance=True)
    to_high=planner.path(to_low[-1],side,high,rotation,scene,color,contact=True,defer_object_clearance=True)
    return to_high[-1].copy()
