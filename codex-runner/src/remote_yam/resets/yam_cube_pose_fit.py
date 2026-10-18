"""Measured RGB-D cube pose from full projected silhouette and depth surfaces.

The cube edge is declared. XYZ/yaw are fitted from observations; no object
heading, simulator state or ideal top-plane height is supplied. The native
factory color/depth projection stays in the existing planner coordinate frame.
API references: docs/refs/scipy/1.18.0/{least-squares,ckdtree-query}.txt and
docs/refs/opencv/5.0.0/project-points-api.txt. Contour matching follows the
earlier read-only full-silhouette prototype
from the coordinating chat, adding measured Z/depth and factory-ray consistency.
"""
from __future__ import annotations
import math,time
import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import cKDTree
from remote_yam.api_depth import factory_ray


def wrap_yaw(angle):return (angle+math.pi/4)%(math.pi/2)-math.pi/4


def project_factory(points,profile):
    """Invert the existing calibrated SDK ray, including its distortion model."""
    points=np.asarray(points,float)
    ray=points[:,:2]/points[:,2,None]
    uv=ray*[profile['fx'],profile['fy']]+[profile['ppx'],profile['ppy']]
    if not any(profile['coeffs']):return uv
    for i,target in enumerate(ray):
        for _ in range(8):
            base=factory_ray(profile,*uv[i])[:2]
            delta=base-target
            if np.linalg.norm(delta)<1e-11:break
            j=np.column_stack([(factory_ray(profile,*(uv[i]+axis))[:2]-base)/.001
                               for axis in (np.array([.001,0.]),np.array([0.,.001]))])
            uv[i]-=np.linalg.solve(j,delta)
    return uv


def cube_polygon(params,camera,edge_m,projection='factory'):
    """Parameters are center XYZ in mm and tabletop yaw in radians."""
    x,y,yaw,z=params;c,s=np.cos(yaw),np.sin(yaw)
    rotation=np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])
    local=np.array([[a,b,h] for h in (-.5,.5) for a in (-.5,.5) for b in (-.5,.5)])*edge_m
    left=local@rotation.T+np.array([x,y,z])/1000
    transform=np.linalg.inv(np.asarray(camera['T_base_camera']['left']))
    cam=np.c_[left,np.ones(8)]@transform.T
    if projection=='factory':uv=project_factory(cam[:,:3],camera['depth_intrinsics'])
    elif projection=='board-rgb':
        uv=cv2.projectPoints(np.ascontiguousarray(cam[:,:3]),np.zeros(3),np.zeros(3),
                             np.asarray(camera['K']),np.asarray(camera['distortion']))[0].reshape(-1,2)
    else:raise ValueError('Unknown projection convention')
    # Hull topology needs float32, but keep float64 coordinates for numerical
    # optimizer derivatives; otherwise rounding can erase small angle changes.
    indices=cv2.convexHull(uv.astype('float32'),returnPoints=False).ravel()
    return uv[indices]


def boundary_samples(poly,count=72):
    delta=np.roll(poly,-1,axis=0)-poly;length=np.linalg.norm(delta,axis=1)
    cumulative=np.r_[0.,np.cumsum(length)];where=np.linspace(0,cumulative[-1],count,endpoint=False)
    i=np.minimum(np.searchsorted(cumulative,where,side='right')-1,len(poly)-1)
    return poly[i]+((where-cumulative[i])/np.maximum(length[i],1e-12))[:,None]*delta[i]


def segment_distances(points,poly):
    a=poly[None,:,:];delta=(np.roll(poly,-1,axis=0)-poly)[None,:,:];offset=points[:,None,:]-a
    amount=np.clip(np.sum(offset*delta,axis=2)/np.maximum(np.sum(delta*delta,axis=2),1e-12),0,1)
    return np.min(np.linalg.norm(offset-amount[:,:,None]*delta,axis=2),axis=1)


def box_surface_distance(points,params,edge_m):
    x,y,yaw,z=params;c,s=np.cos(yaw),np.sin(yaw)
    rotation=np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])
    local=(points-np.array([x,y,z])/1000)@rotation
    distance=np.abs(local)-edge_m/2
    return np.linalg.norm(np.maximum(distance,0.),axis=1)+np.minimum(np.max(distance,axis=1),0.)


def mask_iou(poly,mask):
    model=np.zeros(mask.shape,np.uint8);cv2.fillConvexPoly(model,np.rint(poly).astype('int32'),1)
    return float(np.count_nonzero(model.astype(bool)&mask)/max(1,np.count_nonzero(model.astype(bool)|mask)))


def fit_cube(snapshot,component,initial_row,edge_m,*,projection='factory',depth_weight=1.):
    """Pure measured-data fit; callers decide how to use diagnostics/fallbacks.

    Fixed observation scales:0.75pixel contour /2mm depth. These are fitting
    assumptions, not measured sensor accuracy or new execution admission gates.
    """
    began=time.perf_counter();camera=snapshot.calibration['cameras']['top'];profile=camera['depth_intrinsics']
    contours=cv2.findContours(component.astype('uint8'),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)[0]
    contour=max(contours,key=cv2.contourArea).reshape(-1,2).astype(float);tree=cKDTree(contour)
    core=cv2.erode(component.astype('uint8'),np.ones((3,3),'uint8'))>0
    valid=core&np.isfinite(snapshot.depth)&(snapshot.depth>0);v,u=np.nonzero(valid)
    if len(u)<20:raise ValueError('Insufficient measured cube depth for pose fitting')
    take=np.linspace(0,len(u)-1,min(180,len(u)),dtype=int);u,v=u[take],v[take]
    rays=np.array([factory_ray(profile,float(a),float(b)) for a,b in zip(u,v)])
    transform=np.asarray(camera['T_base_camera']['left']);cloud=(rays*snapshot.depth[v,u,None])@transform[:3,:3].T+transform[:3,3]
    top=np.asarray(initial_row['visible_top_center_by_arm']['left']['top_center_m'])
    initial=np.r_[top[:2]*1000,initial_row['yaw_rad'],1000*(top[2]-edge_m/2)]
    lower=initial+[-20.,-20.,-10.,-10.];upper=initial+[20.,20.,10.,10.]
    lower[2],upper[2]=-math.pi,math.pi
    def residual(params):
        poly=cube_polygon(params,camera,edge_m,projection)
        rgb=np.r_[tree.query(boundary_samples(poly))[0],segment_distances(contour,poly)]/.75
        measured=box_surface_distance(cloud,params,edge_m)/.002
        return np.r_[rgb,depth_weight*math.sqrt(len(rgb)/len(measured))*measured]
    candidates=[]
    for yaw in np.radians([-45.,-30.,-15.,0.,15.,30.,45.]):
        start=initial.copy();start[2]=yaw
        result=least_squares(residual,start,bounds=(lower,upper),loss='soft_l1',f_scale=1.,
            x_scale=[10.,10.,.4,5.],max_nfev=70,diff_step=1e-4,xtol=1e-6,ftol=1e-6,gtol=1e-6)
        candidates.append(result)
    best=min(candidates,key=lambda r:r.cost);params=best.x.copy();params[2]=wrap_yaw(params[2])
    poly=cube_polygon(params,camera,edge_m,projection);depth=np.abs(box_surface_distance(cloud,params,edge_m))
    return dict(center_left_m=(params[[0,1,3]]/1000).tolist(),
        top_center_left_m=(params[[0,1,3]]/1000+[0.,0.,edge_m/2]).tolist(),yaw_rad=float(params[2]),
        model_edge_m=edge_m,projection=projection,depth_weight=depth_weight,params=params.tolist(),
        polygon_px=poly.tolist(),mask_iou=mask_iou(poly,component),
        contour_rms_px=float(np.sqrt(np.mean(segment_distances(contour,poly)**2))),
        depth_surface_median_mm=float(1000*np.median(depth)),depth_surface_p90_mm=float(1000*np.quantile(depth,.9)),
        initial_center_left_m=top.tolist(),delta_xy_m=(params[:2]/1000-top[:2]).tolist(),
        measured_points=len(cloud),optimizer_cost=float(best.cost),evaluations=sum(r.nfev for r in candidates),
        wall_s=time.perf_counter()-began,method='Known-size upright cube; full color silhouette and measured depth; fittedXYZ/yaw; no ideal top plane')
