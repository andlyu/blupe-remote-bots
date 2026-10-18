"""Explicit metric goal offsets from an immutable captured YAM1 baseline."""
from __future__ import annotations

import copy
from datetime import datetime, timezone

import cv2
import numpy as np

from .yam_cube_reset import COLORS, ResetBlocked, color_mask, digest, plain, require_binding


def declared_table_frame(report):
    """User's horizontal z=0 support, oriented using the saved camera transform."""
    normal=np.array([0.,0.,1.])
    transform=np.array(report["cameras"]["top"]["T_base_camera"]["left"])
    right=transform[:3,0].copy();right[2]=0
    if np.linalg.norm(right)<.2:
        raise ResetBlocked("Image right is ambiguous in the declared table plane")
    right/=np.linalg.norm(right)
    forward=np.cross(normal,right)
    up=-transform[:3,1].copy();up[2]=0;up/=np.linalg.norm(up)
    if np.dot(forward,up)<.85:
        raise ResetBlocked("Image top is ambiguous in the declared table plane")
    return plain(dict(frame="left_arm_base",support_plane=[0.,0.,0.],normal=normal,
        forward=forward,right=right,source="user-provided table at arm-base mounting z=0",
        definition="Task origin/axes use left base; +Z up. Right is camera +X projected into z=0; forward is normal cross right, toward image top/box.",
        forward_alignment_with_image_up=float(np.dot(forward,up))))


def apply_task_geometry(scene, geometry, report):
    """Keep observed XY; express declared cube/support heights in both bases.

    Raw depth and footprint evidence are retained. This is an explicit planning
    hypothesis from operator facts, not a correction or validation of extrinsics.
    """
    if geometry.get("source")!="user-provided" or geometry.get("task_frame")!="left_arm_base":
        raise ResetBlocked("Unsupported declared task geometry provenance/frame")
    from .yam_cube_sizes import validate_edges
    edges=validate_edges(geometry.get("cube_edges_by_color_m") or dict.fromkeys(COLORS,geometry["cube_edge_m"]))
    z=float(geometry["support_z_m"])
    if z!=0.:
        raise ResetBlocked("This task's declared support remains z=0")
    transforms={arm:np.asarray(report["cameras"]["top"]["T_base_camera"][arm]) for arm in ("left","right")}
    left_to_right=transforms["right"]@np.linalg.inv(transforms["left"])
    result=copy.deepcopy(scene)
    for color,row in result.items():
        edge=edges[color]
        raw=row.setdefault("raw_visible_top_center_by_arm",copy.deepcopy(row["visible_top_center_by_arm"]))
        row.setdefault("raw_dimensions_m",copy.deepcopy(row["dimensions_m"]))
        row.setdefault("raw_support_plane_left",copy.deepcopy(row["support_plane_left"]))
        left=np.array(raw["left"]["top_center_m"])
        right=np.array(raw["right"]["top_center_m"])
        if not np.allclose((left_to_right@np.r_[left,1])[:3],right,atol=1e-7):
            raise ResetBlocked("Observed arm-frame positions disagree with calibration transforms")
        row["dimensions_m"]=[edge,edge]
        row["declared_height_m"]=edge
        row["support_plane_left"]=[0.,0.,z]
        row["geometry_source"]="user-provided; XY retained from original observation"
        for key,height in (("top_center_m",z+edge),("support_point_m",z),("cube_center_m",z+edge/2)):
            point=np.r_[left[:2],height]
            row["visible_top_center_by_arm"]["left"][key]=point.tolist()
            row["visible_top_center_by_arm"]["right"][key]=(left_to_right@np.r_[point,1])[:3].tolist()
    return result


def declared_baseline(baseline, report):
    require_binding(baseline,report)
    result=copy.deepcopy(baseline);result.pop("content_sha256")
    result["captured_baseline_content_sha256"]=baseline["content_sha256"]
    result["task_geometry"]=dict(source="user-provided",cube_edge_m=.030,support_z_m=0.,
        task_frame="left_arm_base",cube_center_z_m=.015,cube_top_z_m=.030,
        physical_accuracy="UNVERIFIED; dimensions/height do not validate camera extrinsics or tool contact")
    result["targets"]=apply_task_geometry(baseline["targets"],result["task_geometry"],report)
    return dict(result,content_sha256=digest(result))


def table_frame(snapshots, baseline):
    """Fit observed white support; define orthonormal image-aligned table axes."""
    from remote_yam.block_placement import TopSurface, fit_plane
    clouds=[]
    for snapshot in snapshots:
        require_binding(baseline,snapshot.calibration)
        surface=TopSurface(snapshot,"left")
        rgb=snapshot.rgb
        white=(rgb.min(2)>95)&(rgb.max(2).astype(int)-rgb.min(2)<75)
        colors=np.logical_or.reduce([color_mask(rgb,c) for c in COLORS])
        rings=np.zeros(rgb.shape[:2],bool)
        excluded=np.zeros_like(rings)
        for row in baseline["targets"].values():
            x,y,w,h=row["bbox_px"]
            rings[max(0,y-20):y+h+20,max(0,x-20):x+w+20]=True
            excluded[max(0,y-5):y+h+5,max(0,x-5):x+w+5]=True
        mask=rings&~excluded&white&~colors&surface.valid
        clouds.append(surface.cloud[mask])
    cloud=np.concatenate(clouds)
    plane=fit_plane(cloud)
    normal=np.r_[-plane[:2],1.];normal/=np.linalg.norm(normal)
    camera_right=surface.transform[:3,0]
    right=camera_right-normal*np.dot(normal,camera_right)
    if np.linalg.norm(right)<.2:
        raise ResetBlocked("Camera right is nearly normal to the table; direction is ambiguous")
    right/=np.linalg.norm(right)
    forward=np.cross(normal,right);forward/=np.linalg.norm(forward)
    camera_up=-surface.transform[:3,1]
    camera_up-=normal*np.dot(normal,camera_up);camera_up/=np.linalg.norm(camera_up)
    if np.dot(forward,camera_up)<.85:
        raise ResetBlocked("Table forward does not unambiguously point toward the top of the reference image")
    errors=cloud[:,2]-(cloud[:,:2]@plane[:2]+plane[2])
    return plain(dict(frame="left_arm_base",support_plane=plane,normal=normal,
        forward=forward,right=right,support_samples=len(cloud),
        support_residual_p90_m=float(np.quantile(abs(errors),.9)),
        forward_alignment_with_image_up=float(np.dot(forward,camera_up)),
        definition="Right = camera +X projected onto measured table; forward = table normal cross right, verified toward image top/box"))


def shifted_goals(baseline, report, frame, *, forward_m, right_m):
    """Translate every color by one common physical vector, in each arm frame."""
    require_binding(baseline,report)
    if not np.isfinite([forward_m,right_m]).all():
        raise ValueError("Goal offsets must be finite metres")
    f,r,n=(np.asarray(frame[k],float) for k in ("forward","right","normal"))
    basis=np.column_stack([f,r,n])
    if not np.allclose(basis.T@basis,np.eye(3),atol=1e-8):
        raise ResetBlocked("Goal directions must be an orthonormal table frame")
    delta=forward_m*f+right_m*r
    transforms={arm:np.asarray(report["cameras"]["top"]["T_base_camera"][arm])
                for arm in ("left","right")}
    by_arm={arm:(transforms[arm]@np.linalg.inv(transforms["left"]))[:3,:3]@delta
            for arm in ("left","right")}
    camera=report["cameras"]["top"]
    if any(camera["depth_intrinsics"]["coeffs"]):
        raise ResetBlocked("Goal projection needs the supported zero-distortion factory profile")
    profile=camera["depth_intrinsics"];transform=transforms["left"]
    def project(point):
        point=(np.asarray(point)-transform[:3,3])@transform[:3,:3]
        if point[2]<=0:raise ResetBlocked("Goal projects behind the camera")
        return point[:2]/point[2]*[profile["fx"],profile["fy"]]+[profile["ppx"],profile["ppy"]]
    goals=copy.deepcopy(baseline);goals.pop("content_sha256")
    goals["created_at"]=datetime.now(timezone.utc).isoformat()
    goals["destination_source"]="Explicit user revision: translate immutable baseline in the declared table plane"
    goals["goal_definition"]=dict(baseline_content_sha256=baseline.get("captured_baseline_content_sha256",baseline["content_sha256"]),
        planning_baseline_content_sha256=baseline["content_sha256"],
        offsets_m=dict(forward=forward_m,right=right_m),table_frame=frame,
        displacement_left_base_m=delta.tolist(),displacement_by_arm_m=plain(by_arm),
        displacement_length_m=float(np.linalg.norm(delta)),
        physical_accuracy="UNVERIFIED; derived metric preview inherits initial calibration limits")
    for color in COLORS:
        before=baseline["targets"][color];after=goals["targets"][color]
        for arm in ("left","right"):
            for key in before["visible_top_center_by_arm"][arm]:
                after["visible_top_center_by_arm"][arm][key]=(
                    np.array(before["visible_top_center_by_arm"][arm][key])+by_arm[arm]).tolist()
        old_pixel=project(before["visible_top_center_by_arm"]["left"]["top_center_m"])
        new_pixel=project(after["visible_top_center_by_arm"]["left"]["top_center_m"])
        # Preserve the observed silhouette-vs-top-patch offset. Each color's
        # projected pixel change is computed from its metric goal and own depth.
        after["pixel_center"]=(np.array(before["pixel_center"])+new_pixel-old_pixel).tolist()
        after["projected_top_pixel"]=new_pixel.tolist()
        after["observation_kind"]="derived_goal_from_immutable_baseline"
    return plain(dict(goals,content_sha256=digest(goals)))


def goal_preview(rgb, baseline, goals):
    """Diagnostic overlay and enlarged arrows; no destination pixel guessing."""
    image=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
    for color in COLORS:
        a=np.rint(baseline["targets"][color]["pixel_center"]).astype(int)
        b=np.rint(goals["targets"][color]["pixel_center"]).astype(int)
        cv2.arrowedLine(image,tuple(a),tuple(b),(0,210,60),1,cv2.LINE_AA,tipLength=.35)
        cv2.circle(image,tuple(a),3,(255,255,255),1,cv2.LINE_AA)
        cv2.drawMarker(image,tuple(b),(0,210,60),cv2.MARKER_CROSS,8,1,cv2.LINE_AA)
    points=np.array([baseline["targets"][c]["pixel_center"] for c in COLORS]+[goals["targets"][c]["pixel_center"] for c in COLORS])
    lo=np.maximum(np.floor(points.min(0)).astype(int)-25,0)
    hi=np.minimum(np.ceil(points.max(0)).astype(int)+25,[image.shape[1],image.shape[0]])
    crop=image[lo[1]:hi[1],lo[0]:hi[0]]
    scale=min(3.,600/crop.shape[1]);zoom=cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_NEAREST)
    canvas=np.full((460+zoom.shape[0],640,3),245,np.uint8);canvas[:360]=image
    cv2.putText(canvas,"White circle: baseline   Green cross: goal",(18,389),cv2.FONT_HERSHEY_SIMPLEX,.52,(20,20,20),1,cv2.LINE_AA)
    cv2.putText(canvas,"+10 mm forward AND +10 mm right (table plane)",(18,415),cv2.FONT_HERSHEY_SIMPLEX,.51,(20,20,20),1,cv2.LINE_AA)
    x=(640-zoom.shape[1])//2;canvas[435:435+zoom.shape[0],x:x+zoom.shape[1]]=zoom
    for color in COLORS:
        a=np.array(baseline["targets"][color]["pixel_center"])
        label=(int(x+(a[0]-lo[0])*scale)-24,int(435+(a[1]-lo[1])*scale)-27)
        cv2.putText(canvas,color,label,cv2.FONT_HERSHEY_SIMPLEX,.48,(255,255,255),2,cv2.LINE_AA)
        cv2.putText(canvas,color,label,cv2.FONT_HERSHEY_SIMPLEX,.48,(15,15,15),1,cv2.LINE_AA)
    return canvas
