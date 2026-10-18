"""Measured fixed-color RGB-D cube perception and immutable target records.

Calibration, workspace and saved goals are supplied by the station.
This module contains no hardware commands.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

COLORS = ("blue", "orange", "yellow")
HSV = {
    "blue": ((90, 110, 60), (130, 255, 255)),
    "orange": ((4, 180, 90), (18, 255, 255)),
    "yellow": ((19, 150, 110), (35, 255, 255)),
}


class ResetBlocked(RuntimeError):
    pass


def plain(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    return value


def digest(value):
    return hashlib.sha256(json.dumps(plain(value), sort_keys=True,
                                    allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def write_new(path, value):
    """Exclusive creation: reset must never silently redefine a destination."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(plain(value), stream, indent=2, allow_nan=False)
        stream.write("\n")


def color_mask(rgb, color):
    low, high = HSV[color]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    return cv2.inRange(hsv, np.array(low), np.array(high)) > 0


def load_workspace(path, report):
    """Map the selected planner-world XY rectangle into the measured left frame."""
    workspace = json.loads(Path(path).read_text())
    if workspace.get('schema') != 'yam-cube-workspace-v1' or workspace.get('frame') != 'planner_world':
        raise ResetBlocked('Unsupported cube workspace schema or frame')
    bounds = _workspace_bounds([workspace['center_bounds_m'][axis] for axis in ('x', 'y')])
    spacing = float(report['base_geometry']['spacing_m'])
    if not np.isfinite(spacing) or spacing <= 0:
        raise ResetBlocked('Invalid workspace base spacing')
    bounds[1] -= spacing / 2
    return bounds


def _workspace_bounds(value):
    bounds = np.asarray(value, dtype=float).copy()
    if bounds.shape != (2, 2) or not np.isfinite(bounds).all() or np.any(bounds[:, 0] >= bounds[:, 1]):
        raise ResetBlocked('Workspace requires finite increasing X and Y bounds')
    return bounds


def partial_color_occlusion(component, other_colors, area, rectangle):
    """Admit a mostly convex visible cube fragment touching another cube color.

    Keep isolated irregular orange objects rejected. A real touching pair can
    hide a corner while leaving enough colored top/depth for the same metric
    estimate; a complete rectangular silhouette is not required in that case.
    """
    fraction=area/max(1.,(rectangle[1][0]+1)*(rectangle[1][1]+1))
    if fraction<.5:return False
    contours,_=cv2.findContours(component.astype('uint8'),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not contours:return False
    hull=cv2.convexHull(np.concatenate(contours))
    if area/max(1.,cv2.contourArea(hull))<.85:return False
    nearby=cv2.dilate(other_colors.astype('uint8'),np.ones((5,5),'uint8'))>0
    return int(np.count_nonzero(component&nearby))>=5


def measured_top_face(surface, component, top_z):
    """Fit the visible top from measured depth, excluding colored side faces.

    No declared top plane, object heading, or simulator state enters this fit.
    Incomplete/noisy faces retain the ordinary detector estimate.
    """
    from remote_yam.block_placement import fit_plane,plane_z
    cloud=surface.cloud[component & surface.valid]
    high=cloud[abs(cloud[:,2]-top_z)<=.002]
    try:
        plane=fit_plane(high)
        error=abs(cloud[:,2]-plane_z(plane,cloud[:,:2]))
        face=cloud[error<=.0015]
        if len(face)<30:return None
        footprint=cv2.minAreaRect(face[:,:2].astype('float32'))
        dimensions=np.array(footprint[1])
        # A truncated face cannot locate both opposite edges. Keep the prior
        # detector center rather than assuming which unseen edge is missing.
        if dimensions.min()<.8*dimensions.max():return None
        xy=np.asarray(footprint[0])
        center=np.r_[xy,plane_z(plane,xy)]
        return dict(center=center,dimensions=dimensions,yaw_rad=float(np.deg2rad(footprint[2])),
                    measured_plane_left=plane,top_points=len(face),
                    depth_residual_p90_m=float(np.quantile(error[error<=.0015],.9)))
    except (ValueError,np.linalg.LinAlgError):return None


def detect(snapshot, *, support_plane_left=None, workspace_left_xy_m=None, allow_partial_color_occlusion=False,
           refine_measured_top=False,fit_cube_edges_m=None):
    """Measure colored raised regions and their surrounding support plane.

    The visible top patch (not the side/shadow silhouette) supplies XYZ.
    Reports retain depth/shape diagnostics; these do not certify accuracy.
    An optional calibrated workspace filters candidate centers before resolving
    color identity. It does not change measured positions or destination goals.
    """
    from remote_yam.block_placement import TopSurface, fit_plane, plane_z

    surface = TopSurface(snapshot, "left")
    workspace = None if workspace_left_xy_m is None else _workspace_bounds(workspace_left_xy_m)
    selected_plane = None
    if support_plane_left is not None:
        selected_plane = np.asarray(support_plane_left, dtype=float)
        if selected_plane.shape != (3,) or not np.isfinite(selected_plane).all():
            raise ResetBlocked("Selected support plane must be finite in the left-arm-base frame")
    rgb = snapshot.rgb
    white = (rgb.min(2) > 95) & (rgb.max(2).astype(int) - rgb.min(2) < 75)
    masks = {c: color_mask(rgb, c) for c in COLORS}
    all_colors = np.logical_or.reduce(list(masks.values()))
    results = {}
    for color, mask in masks.items():
        count, labels, stats, centers = cv2.connectedComponentsWithStats(mask.astype("uint8"))
        candidates, rejections = [], []
        for i in range(1, count):
            x, y, width, height, area = map(int, stats[i])
            if not (100 <= area <= 2400 and 10 <= min(width, height)
                    and max(width, height) <= 70 and .5 <= width / height <= 2):
                continue
            component = labels == i
            pixels = np.column_stack(np.nonzero(component)[::-1])
            rect = cv2.minAreaRect(pixels.astype("float32"))
            partial=False
            if area / max(1., (rect[1][0]+1)*(rect[1][1]+1)) < .68:
                partial=bool(allow_partial_color_occlusion and partial_color_occlusion(component,all_colors&~mask,area,rect))
                if not partial:continue
            core = cv2.erode(component.astype("uint8"), np.ones((3, 3), "uint8")) > 0
            valid = core & surface.valid
            if valid.sum() < 35 or valid.sum() < .85 * core.sum():
                rejections.append(f"{color}: missing interior depth")
                continue
            cloud = surface.cloud[valid]
            top_z = float(np.quantile(cloud[:, 2], .8))
            top = cloud[abs(cloud[:, 2] - top_z) <= .006]
            if len(top) < 30 or len(top) < .3 * len(cloud):
                rejections.append(f"{color}: no consistent top patch")
                continue
            # Use the task's declared table when supplied. The measured cube
            # cloud stays unchanged; a selected reference is not a new survey.
            ring = np.zeros(mask.shape, bool)
            ring[max(0,y-20):y+height+20, max(0,x-20):x+width+20] = True
            ring[max(0,y-5):y+height+5, max(0,x-5):x+width+5] = False
            support = ring & white & ~all_colors & surface.valid
            if selected_plane is not None:
                plane = selected_plane
            else:
                try:
                    plane = fit_plane(surface.cloud[support])
                except ValueError as exc:
                    rejections.append(f"{color}: {exc}")
                    continue
            center = np.median(top, axis=0)
            if workspace is not None and (np.any(center[:2] < workspace[:, 0])
                                          or np.any(center[:2] > workspace[:, 1])):
                continue
            floor = float(plane_z(plane, center[:2]))
            block_height = float(center[2]-floor)
            if not .015 <= block_height <= .075:
                continue
            # Project silhouette onto the measured top for a conservative extent.
            projected = surface.intersect(pixels, np.array([0., 0., center[2]]))
            footprint = cv2.minAreaRect(projected[:, :2].astype("float32"))
            dimensions = np.asarray(footprint[1])
            heading=float(np.deg2rad(footprint[2]))
            refinement=measured_top_face(surface,component,top_z) if refine_measured_top and not partial else None
            if refinement is not None:
                center=refinement['center'];dimensions=refinement['dimensions'];heading=refinement['yaw_rad']
                floor=float(plane_z(plane,center[:2]));block_height=float(center[2]-floor)
            if selected_plane is None and not .020 <= dimensions.min() <= dimensions.max() <= .075:
                continue
            by_arm = {}
            for arm in ("left", "right"):
                t = np.asarray(snapshot.calibration["cameras"]["top"]["T_base_camera"][arm])
                left = surface.transform
                change = t @ np.linalg.inv(left)
                arm_center = (change @ np.r_[center, 1])[:3]
                arm_support = (change @ np.r_[center[:2], floor, 1])[:3]
                by_arm[arm] = dict(top_center_m=arm_center, support_point_m=arm_support)
            candidate=dict(color=color, pixel_center=centers[i], bbox_px=[x,y,width,height],
                area_px=area, visible_top_center_by_arm=by_arm,
                support_plane_left=plane, support_plane_measured=selected_plane is None,
                support_reference="selected_task_table" if selected_plane is not None else "local_depth_fit",
                estimated_height_m=block_height,
                partial_color_occlusion=partial,
                dimensions_m=dimensions, top_samples=len(top),
                top_spread_m=float(np.ptp(top[:, 2])),
                yaw_rad=heading,
                measured_top_refinement=refinement,
                depth_valid_fraction=float(valid.sum()/core.sum()))
            if fit_cube_edges_m is not None:
                from .yam_cube_pose_fit import fit_cube
                try:
                    fitted=fit_cube(snapshot,component,candidate,float(fit_cube_edges_m[color]))
                    fitted_top=np.asarray(fitted['top_center_left_m'])
                    fitted_floor=float(plane_z(plane,fitted_top[:2]))
                    for arm in ('left','right'):
                        change=np.asarray(snapshot.calibration['cameras']['top']['T_base_camera'][arm])@np.linalg.inv(surface.transform)
                        candidate['visible_top_center_by_arm'][arm]=dict(
                            top_center_m=(change@np.r_[fitted_top,1])[:3],
                            support_point_m=(change@np.r_[fitted_top[:2],fitted_floor,1])[:3])
                    candidate.update(yaw_rad=fitted['yaw_rad'],estimated_height_m=float(fitted_top[2]-fitted_floor),
                        cube_pose_fit=fitted,heading_source='Full known-size RGB-D cube silhouette/surface fit')
                except (ValueError,np.linalg.LinAlgError) as exc:
                    candidate.update(cube_pose_fit_unavailable=str(exc),heading_source='Ordinary measured silhouette fallback')
            candidates.append(candidate)
        if len(candidates) != 1:
            raise ResetBlocked(f"{color}: expected one raised cube, found {len(candidates)}; "
                               + "; ".join(rejections[:3]))
        results[color] = plain(candidates[0])
    return results


def stable_scene(snapshots, *, min_frames=3, support_plane_left=None, workspace_left_xy_m=None, allow_partial_color_occlusion=False,
                 refine_measured_top=False,fit_cube_edges_m=None):
    unique = {}
    for snapshot in snapshots:
        identity = (snapshot.metadata["captured_at"], snapshot.metadata.get("sequence"))
        unique[identity] = snapshot
    if len(unique) < min_frames:
        raise ResetBlocked(f"Need {min_frames} distinct frames, received {len(unique)}")
    reports = [s.calibration for s in unique.values()]
    if len({r["calibration_id"] for r in reports}) != 1:
        raise ResetBlocked("Calibration changed between captures")
    detections = [detect(s,support_plane_left=support_plane_left,
                         workspace_left_xy_m=workspace_left_xy_m,
                         allow_partial_color_occlusion=allow_partial_color_occlusion,
                         refine_measured_top=refine_measured_top,fit_cube_edges_m=fit_cube_edges_m) for s in unique.values()]
    result = {}
    for color in COLORS:
        rows = [d[color] for d in detections]
        px = np.array([r["pixel_center"] for r in rows])
        xyz = np.array([r["visible_top_center_by_arm"]["left"]["top_center_m"] for r in rows])
        position_varies = np.ptp(px, axis=0).max() > 3 or np.ptp(xyz, axis=0).max() > .008
        if position_varies and support_plane_left is None:
            raise ResetBlocked(f"{color}: unstable RGB-D position")
        row = dict(rows[-1], pixel_center=np.median(px, axis=0),
                   frame_count=len(rows), spread_xyz_m=np.ptp(xyz, axis=0),
                   warnings=['RGB-D position varies; using median of fresh observations'] if position_varies else [],
                   estimated_height_m=float(np.median([r["estimated_height_m"] for r in rows])),
                   dimensions_m=np.median([r["dimensions_m"] for r in rows], axis=0))
        row["visible_top_center_by_arm"] = {
            arm: {key: np.median([r["visible_top_center_by_arm"][arm][key] for r in rows], axis=0)
                  for key in ("top_center_m", "support_point_m")}
            for arm in ("left", "right")}
        result[color] = plain(row)
    return result


def geometry_digest(report):
    camera = report["cameras"]["top"]
    return digest(dict(camera={k:v for k,v in camera.items() if k != "depth"},
                       kinematics=report["kinematics"], base_geometry=report["base_geometry"],
                       native_joint_calibration=report["native_joint_calibration"]))


def make_targets(scene, report, references, capture_times=()):
    if set(scene) != set(COLORS) or not references:
        raise ResetBlocked("All three colors and immutable image evidence are required")
    payload = dict(schema="yam1-color-reset-targets-v1", robot_id="yam-1",
        created_at=datetime.now(timezone.utc).isoformat(),
        destination_source="User-selected current physical positions; never recaptured by reset",
        calibration_id=report["calibration_id"],
        calibration_geometry_sha256=geometry_digest(report),
        capture_times_unix=sorted(set(capture_times)),
        native_joint_calibration_id=report["native_joint_calibration"]["calibration_id"],
        calibration_quality=report["quality"], reference_files=references,
        targets=scene, position_tolerance_m=.008, pixel_tolerance=3.,
        physical_accuracy="UNVERIFIED", physical_return_demonstrated=False)
    return dict(payload, content_sha256=digest(payload))


def require_binding(targets, report):
    if (targets["calibration_id"] != report["calibration_id"]
            or targets["calibration_geometry_sha256"] != geometry_digest(report)):
        raise ResetBlocked("Saved target geometry differs from current calibration; preserve the original reference")


def load_targets(path):
    result = json.loads(Path(path).read_text())
    expected = result.pop("content_sha256", None)
    if result.get("schema") != "yam1-color-reset-targets-v1" or digest(result) != expected:
        raise ResetBlocked("Target configuration changed or has an invalid checksum")
    if result.get("robot_id") != "yam-1" or set(result["targets"]) != set(COLORS):
        raise ResetBlocked("Invalid robot or color target set")
    return dict(result, content_sha256=expected)


def compare(scene, targets, calibration_id):
    if calibration_id != targets["calibration_id"]:
        raise ResetBlocked("Camera calibration changed; reproject the ORIGINAL reference explicitly")
    result = {}
    declared = targets.get("task_geometry", {}).get("source") == "user-provided"
    for color in COLORS:
        current, target = scene[color], targets["targets"][color]
        pixel_error = float(np.linalg.norm(np.array(current["pixel_center"])-target["pixel_center"]))
        a = current["visible_top_center_by_arm"]["left"]["top_center_m"]
        b = target["visible_top_center_by_arm"]["left"]["top_center_m"]
        error = float(np.linalg.norm(np.array(a)-b))
        # Declared cubes use known geometry; apparent dimensions and pixels
        # remain diagnostics, not additional metric destination admission.
        current_size=current.get("raw_dimensions_m",current["dimensions_m"])
        target_size=target.get("raw_dimensions_m",target["dimensions_m"])
        size_changed = np.max(abs(np.sort(current_size)-np.sort(target_size))) > .015
        if not declared and size_changed:
            raise ResetBlocked(f"{color}: dimensions changed; identity or depth is uncertain")
        raw_vertical_error=0.
        if "raw_visible_top_center_by_arm" in current and "raw_visible_top_center_by_arm" in target:
            raw_vertical_error=abs(current["raw_visible_top_center_by_arm"]["left"]["top_center_m"][2]
                -target["raw_visible_top_center_by_arm"]["left"]["top_center_m"][2])
            if not declared and raw_vertical_error>targets["position_tolerance_m"]:
                raise ResetBlocked(f"{color}: observed height changed; declared table cannot flatten a lifted/stacked cube")
        warnings = []
        if declared:
            if size_changed:warnings.append('Apparent dimensions changed; using declared 30mm cube')
            if raw_vertical_error>targets['position_tolerance_m']:warnings.append('Raw depth height differs; using declared table0 geometry')
            if pixel_error>targets['pixel_tolerance']:warnings.append('Pixel position differs; metric goal comparison is authoritative')
        result[color] = dict(pixel_error=pixel_error, position_error_m=error, warnings=warnings,
            raw_vertical_change_m=raw_vertical_error,
            state="already_correct" if error <= targets["position_tolerance_m"]
                  and (declared or (pixel_error <= targets["pixel_tolerance"]
                  and raw_vertical_error <= targets["position_tolerance_m"])) else "displaced")
    return result


def annotate(rgb, scene):
    result = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    for color, row in scene.items():
        x,y,w,h = row["bbox_px"]
        cv2.rectangle(result, (x,y), (x+w,y+h), (255,255,255), 1)
        cv2.putText(result, color, (x-10,y-9), cv2.FONT_HERSHEY_SIMPLEX, .45, (20,20,20), 2)
        cv2.putText(result, color, (x-10,y-9), cv2.FONT_HERSHEY_SIMPLEX, .45, (255,255,255), 1)
    return result
