"""Geometry-directed, partially open and tilted offline grasp candidates.

Every returned program still requires the complete installed-CAD sweep audit.
This module never constructs hardware I/O or changes the task destinations.
"""
import copy
import math
import numpy as np
from scipy.spatial.transform import Rotation
from .yam_cube_reset import ResetBlocked,plain
from .yam_cube_contact import contact_for_cube
from .yam_cube_sizes import edge_m
from .yam_cube_scenes import box_separation,rotation as cube_rotation


def aperture_for_gap(gap,reference):
    value=(gap-reference['closed_gap_m'])/reference['opening_travel_m']
    if not math.isfinite(value) or not 0<=value<=1:
        raise ResetBlocked('Requested jaw gap exceeds the reference gripper travel')
    return float(value)


def pregrasp_aperture(width,clearance,reference,extra_gap_m=0.):
    """Add total jaw separation, bounded by calibrated native travel."""
    if not math.isfinite(extra_gap_m) or extra_gap_m<0:
        raise ResetBlocked('Additional pregrasp gap must be finite and nonnegative')
    maximum=reference['closed_gap_m']+reference['opening_travel_m']
    gap=min(maximum,width+clearance+extra_gap_m)
    return aperture_for_gap(gap,reference)


def grasp_seeds(planner,color,scene):
    """Offset tangentially away from nearby blocks while preserving pad overlap."""
    source=scene[color];center=planner.world(source);seeds=[]
    displacement=float(getattr(planner,'grasp_offset_m',.008))
    if not math.isfinite(displacement) or not 0<=displacement<=.015:raise ResetBlocked('Grasp offset exceeds15mm pad-overlap bound')
    for j in range(8):
        if j%2 and not getattr(planner,'allow_corner_grasps',True):continue
        yaw=source['yaw_rad']+j*math.pi/4
        required=getattr(planner,'required_grasp_yaw_rad',None)
        if required is not None and abs(math.sin(yaw-required))>1e-6:continue
        axis=np.array([math.cos(yaw),math.sin(yaw)])
        neighbors=[planner.world(row)[:2]-center[:2] for other,row in scene.items()
                   if other!=color and np.linalg.norm(planner.world(row)[:2]-center[:2])<.075]
        offsets=[0.]
        if neighbors:
            nearest=min(neighbors,key=np.linalg.norm)
            away=-math.copysign(1.,float(nearest@axis))
            # Pads span25mm along X: the15mm bound retains12.5mm overlap
            # with a30mm cube. The full mesh audit resolves every neighbor.
            amount=min(displacement,.01) if j%2 else displacement
            amounts=getattr(planner,'grasp_offset_candidates_m',None) or (amount,0.)
            if any(not math.isfinite(a) or not 0<=a<=.015 for a in amounts):raise ResetBlocked('Invalid grasp offset candidate')
            offsets=list(dict.fromkeys(v for a in amounts for v in (away*min(a,.01) if j%2 else away*a,-away*min(a,.01) if j%2 else -away*a)))
        for offset in offsets:
            point=center[:2]+axis*offset
            clearance=min((np.linalg.norm(point-(center[:2]+n)) for n in neighbors),default=1.)
            seeds.append(dict(yaw=yaw,offset=offset,clearance=float(clearance),
                              projected_width_m=edge_m(source)*(abs(math.cos(j*math.pi/4))+abs(math.sin(j*math.pi/4))),
                              corner_grasp=bool(j%2)))
    preferred=getattr(planner,'grasp_offset_candidates_m',None)
    if preferred:
        return sorted(seeds,key=lambda seed:(seed['corner_grasp'],min(range(len(preferred)),key=lambda i:abs(abs(seed['offset'])-preferred[i])),-seed['clearance']))
    if getattr(planner,'prefer_centered_grasps',False):
        return sorted(seeds,key=lambda seed:(seed['corner_grasp'],abs(seed['offset']),-seed['clearance']))
    return sorted(seeds,key=lambda seed:(seed['corner_grasp'],-seed['clearance'],abs(seed['offset'])))


def placement_is_clear(planner,color,scene,destination,yaw):
    """Reject an occupied destination before spending any time on arm IK."""
    center=planner.world(destination).copy()
    half=edge_m(scene[color])/2
    center[2]=destination['visible_top_center_by_arm']['left']['support_point_m'][2]+half
    for other,row in scene.items():
        if other==color:continue
        neighbor=planner.world(row).copy()
        neighbor_half=edge_m(row)/2
        neighbor[2]=row['visible_top_center_by_arm']['left']['support_point_m'][2]+neighbor_half
        if box_separation(center,cube_rotation(yaw),[half]*3,neighbor,cube_rotation(row['yaw_rad']),[neighbor_half]*3)<-1e-8:
            return False
    return True


def geometry_plan_cube(planner,color,scene,targets,joints,grippers,validator):
    if validator is None:
        raise ResetBlocked('Geometry-directed grasps require full installed geometry validation')
    joints=np.asarray(joints,float);grippers=np.asarray(grippers,float)
    if (joints.shape!=(12,) or not np.isfinite(joints).all() or np.any(joints<planner.ik.low)
            or np.any(joints>planner.ik.high) or grippers.shape!=(2,)
            or not np.isfinite(grippers).all() or np.any(grippers<0) or np.any(grippers>1)):
        raise ResetBlocked('Invalid bounded planning start')
    source=scene[color];destination=targets['targets'][color]
    src=planner.world(source);dst=planner.world(destination)
    top_src,top_dst=src[2],dst[2]
    floor_src=source['visible_top_center_by_arm']['left']['support_point_m'][2]
    floor_dst=destination['visible_top_center_by_arm']['left']['support_point_m'][2]
    geometry=contact_for_cube(top_src-floor_src,planner.contact_reference)
    destination_geometry=contact_for_cube(top_dst-floor_dst,planner.contact_reference)
    src[2]=floor_src+geometry['tcp_height_above_support_m']
    dst[2]=floor_dst+destination_geometry['tcp_height_above_support_m']
    release_clearance=.0001
    dst[2]+=release_clearance
    seeds=grasp_seeds(planner,color,scene);failures=[];rank=0;blocked_grasps=set()
    pregrasp_clearance=float(getattr(planner,'pregrasp_clearance_m',.010))
    uncertainty=float(getattr(planner,'position_uncertainty_xy_m',0.))
    if not math.isfinite(uncertainty) or uncertainty<0:raise ResetBlocked('Invalid planar planning uncertainty')
    if not math.isfinite(pregrasp_clearance) or not .002<=pregrasp_clearance<=max(.020,.002+2*uncertainty):
        raise ResetBlocked('Pregrasp gap clearance must be between2 and20mm')
    pregrasp_clearance=max(pregrasp_clearance,.002+2*uncertainty)
    if source.get('planning_goal_kind')=='staging':pregrasp_clearance=max(pregrasp_clearance,.010)
    preferred_arm=getattr(planner,'preferred_pick_arm',None)
    arms=sorted(('left','right'),key=lambda side:(preferred_arm is not None and side!=preferred_arm,
                abs(src[1]-(planner.spacing/2 if side=='left' else -planner.spacing/2))))
    yaws=getattr(planner,'destination_grasp_yaws',(0.,math.pi/2,-math.pi/2,math.pi))
    feasible={}
    for seed in seeds:
        choices=tuple(dict.fromkeys((seed['yaw'],*yaws))) if getattr(planner,'preserve_carry_orientation',False) else yaws
        if getattr(planner,'preserve_carry_orientation',False):
            choices=sorted(choices,key=lambda value:abs(math.atan2(math.sin(value-seed['yaw']),math.cos(value-seed['yaw']))))
        feasible[seed['yaw']]=tuple(yaw for yaw in choices if placement_is_clear(planner,color,scene,destination,source['yaw_rad']+yaw-seed['yaw']))
    if not any(feasible.values()):raise ResetBlocked('Destination is occupied by another cube; move that cube first')
    heights=getattr(planner,'transfer_height_margins',(.08,.05,.12))
    tilts=getattr(planner,'approach_tilts_rad',(0.,math.pi/4,-math.pi/4))
    for tilt in tilts:
      if not math.isfinite(tilt) or abs(tilt)>math.pi/4+1e-10:
        raise ResetBlocked('Approach tilt exceeds45degrees')
      for margin in heights:
       if not math.isfinite(margin) or not .05<=margin<=.20:
        raise ResetBlocked('Invalid transfer height margin')
       height=max(top_dst,max(planner.world(row)[2] for row in scene.values()))+margin
       if height>.40:raise ResetBlocked('Transfer height exceeds existing workspace')
       for side in arms:
        idx=0 if side=='left' else 1
        base=np.array([0.,planner.spacing/2 if idx==0 else -planner.spacing/2])
        for seed in seeds:
         yaw,offset=seed['yaw'],seed['offset'];key=(side,round(yaw,9),offset,tilt)
         if key in blocked_grasps or not feasible[yaw]:continue
         compression=float(getattr(planner,'grasp_compression_m',0.))
         if not math.isfinite(compression) or not 0<=compression<=.002:raise ResetBlocked('Invalid exploratory grasp compression')
         relief=float(getattr(planner,'grasp_gap_relief_m',0.))
         if not math.isfinite(relief) or not 0<=relief<=.0002:raise ResetBlocked('Invalid exploratory grasp relief')
         closed=aperture_for_gap(seed['projected_width_m']-compression+relief,planner.contact_reference)
         extra_open_gap=float(getattr(planner,'pregrasp_extra_open_gap_m',0.))
         opened=pregrasp_aperture(seed['projected_width_m'],pregrasp_clearance,planner.contact_reference,extra_open_gap)
         released=aperture_for_gap(seed['projected_width_m']+(.010 if destination.get('planning_goal_kind')=='staging' else pregrasp_clearance),planner.contact_reference)
         rotation=Rotation.from_euler('z',yaw).as_matrix()@np.diag([1.,-1.,-1.])
         approach_rotation=rotation@Rotation.from_euler('y',tilt).as_matrix()
         point_src=src+rotation[:,0]*offset
         low_src=point_src.copy();low_src[2]=top_src+.04
         approach_low=low_src.copy()
         if tilt:approach_low+=rotation[:,0]*math.copysign(low_src[2]-point_src[2],tilt)
         for retract in (.04,.06,.02,0.):
          high_src=point_src.copy();high_src[2]=height
          radial=high_src[:2]-base;high_src[:2]-=retract*radial/np.linalg.norm(radial)
          q=joints.copy();g=grippers.tolist();g[idx]=opened
          stages=[dict(name='open',arm=side,points_rad=[q.copy()],grippers=list(g))]
          def motion(name,point,r,grip,carry,contact,cartesian=True,points=None):
            nonlocal q
            if points is None:
              points=planner.path(q,side,point,r,scene,color,carrying=carry,contact=contact,
                                  cartesian=cartesian,defer_object_clearance=True)
            g[idx]=grip
            stages.append(dict(name=name,arm=side,points_rad=points,grippers=list(g),
                expected_tip_world_m=point,expected_rotation=r,carrying=carry,intended_selected_contact=contact))
            q=points[-1].copy()
          try:
            reverse=None
            if getattr(planner,'bidirectional_primitives',False):
              from .yam_cube_primitives import reverse_approach
              try:reverse=reverse_approach(planner,joints,side,scene,color,point_src,approach_low,high_src,rotation,approach_rotation)
              except (ValueError,RuntimeError):pass
            motion('approach',high_src,approach_rotation,opened,False,False,False,points=reverse[0] if reverse else None)
            motion('align',approach_low,approach_rotation,opened,False,True,points=reverse[1] if reverse else None)
            motion('descend',point_src,rotation,opened,False,True,points=reverse[2] if reverse else None)
            motion('close',point_src,rotation,closed,False,True,points=[reverse[3]] if reverse else None)
            motion('lift_clear',low_src,rotation,closed,True,True)
            motion('lift',high_src,rotation,closed,True,True)
          except (ValueError,RuntimeError) as exc:
            failures.append(f'{side}/offset{offset:.3f}/tilt{tilt:.2f}/source: {exc}');continue
          prefix=copy.deepcopy(stages);prefix_q=q.copy();prefix_g=list(g)
          source_blocked=False
          for destination_yaw in feasible[yaw]:
            if not math.isfinite(destination_yaw):raise ResetBlocked('Nonfinite destination yaw')
            stages=copy.deepcopy(prefix);q=prefix_q.copy();g=list(prefix_g)
            target_rotation=Rotation.from_euler('z',destination_yaw).as_matrix()@np.diag([1.,-1.,-1.])
            point_dst=dst+target_rotation[:,0]*offset
            high_dst=point_dst.copy();high_dst[2]=height
            radial=high_dst[:2]-base;high_dst[:2]-=retract*radial/np.linalg.norm(radial)
            low_dst=point_dst.copy();low_dst[2]=top_dst+.04
            try:
              bridge=None
              if getattr(planner,'bidirectional_primitives',False):
                from .yam_cube_primitives import destination_transit,joint_bridge
                try:
                  target_q=destination_transit(planner,joints,side,scene,color,point_dst,low_dst,high_dst,target_rotation)
                  bridge=joint_bridge(planner,q,target_q,side,scene,color,carrying=True)
                except (ValueError,RuntimeError):pass
              motion('transfer',high_dst,target_rotation,closed,True,False,points=bridge)
              motion('place_align',low_dst,target_rotation,closed,True,True)
              motion('place',point_dst,target_rotation,closed,True,True)
              motion('release',point_dst,target_rotation,released,False,True)
              motion('retreat_clear',low_dst,target_rotation,released,False,True)
              motion('retreat',high_dst,target_rotation,1.,False,True)
              rank+=1
              plan=plain(dict(color=color,arm=side,stages=stages,destination_scene_row=copy.deepcopy(destination),
                planning_uncertainty_xy_m=uncertainty,grasp_compression_m=compression,grasp_gap_relief_m=relief,
                grasp_offset_native_x_m=offset,grasp_yaw_rad=yaw,approach_tilt_rad=tilt,
                pregrasp_aperture=opened,pregrasp_extra_open_gap_m=extra_open_gap,
                release_aperture=released,release_clearance_m=release_clearance,retract_m=retract,transfer_height_m=height,
                destination_yaw_offset_rad=destination_yaw-yaw,contact_geometry=dict(geometry,nominal_aperture=closed,projected_grasp_width_m=seed['projected_width_m']),
                contact_pose_status='Reference CAD candidate; physical contact unverified',
                candidate_selection=dict(rank=rank,method='geometry-directed source-prefix reuse with full installed-CAD validation',bidirectional_primitives=bool(getattr(planner,'bidirectional_primitives',False))),
                final_joints=q,final_grippers=g,limitations=['Offline CAD audit does not establish physical contact readiness']))
              accepted=validator(plan)
              if not isinstance(accepted,dict):raise ResetBlocked('Validator did not return an audited plan')
              return accepted
            except (ValueError,RuntimeError) as exc:
              failures.append(f'{side}/offset{offset:.3f}/tilt{tilt:.2f}/destination{destination_yaw:.2f}: {exc}')
              rejected=getattr(exc,'audit_failure_stages',[])
              if any(name in ('descend','close','lift_clear') for name in rejected):
                blocked_grasps.add(key);source_blocked=True;break
          if source_blocked:break
    raise ResetBlocked('No complete geometry-directed grasp/transfer: '+' | '.join(failures[-40:]))
