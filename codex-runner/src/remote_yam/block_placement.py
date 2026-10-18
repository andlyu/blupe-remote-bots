"""Measured, rotated rectangular placements for the black-block example.

All lengths are metres in the selected arm base. Missing depth remains unknown.
This tests block support, not swept robot/gripper collision geometry.
"""
import math

import numpy as np


class SceneError(ValueError):
    pass


class UnreliableBlockDepth(SceneError):
    """A block silhouette exists, but its measured depth cannot support a pick."""


PLACEMENT_MARGIN = .010
SUPPORT_TOLERANCE = .008
GRID_RESOLUTION = .002


def fit_plane(points):
    points = np.asarray(points)
    points = points[np.isfinite(points).all(1)]
    if len(points) < 20:
        raise SceneError('Too little measured depth to fit a support plane')
    design = np.column_stack([points[:, :2], np.ones(len(points))])
    keep = np.ones(len(points), bool)
    for _ in range(4):
        plane, _, rank, _ = np.linalg.lstsq(design[keep], points[keep, 2], rcond=None)
        if rank != 3:
            raise SceneError('Measured support plane is degenerate')
        error = abs(design @ plane-points[:, 2])
        keep = error <= max(.003, float(np.quantile(error, .8)))
    if np.quantile(error, .9) > .006 or np.linalg.norm(plane[:2]) > .25:
        raise SceneError('Measured support plane is too uneven or tilted')
    return plane


def plane_z(plane, xy):
    return np.asarray(xy) @ plane[:2] + plane[2]


class TopSurface:
    def __init__(self, snapshot, arm):
        camera = snapshot.calibration['cameras']['top']
        self.profile = camera['depth_intrinsics']
        # The existing RoboHouse top-camera profile is zero-distortion. Do not
        # apply this inverse pinhole projection to an unsupported lens profile.
        if any(self.profile['coeffs']):
            raise SceneError('Rotated placement requires a zero-distortion depth profile')
        self.transform = np.asarray(camera['T_base_camera'][arm])
        self.origin = self.transform[:3, 3]
        self.h, self.w = snapshot.depth.shape
        v, u = np.mgrid[:self.h, :self.w]
        self.directions = self.rays(np.stack([u, v], -1))
        self.cloud = self.directions*snapshot.depth[..., None]+self.origin
        self.valid = np.isfinite(snapshot.depth) & (snapshot.depth > 0)

    def rays(self, pixels):
        p = self.profile
        u, v = np.moveaxis(np.asarray(pixels), -1, 0)
        rays = np.stack([(u-p['ppx'])/p['fx'], (v-p['ppy'])/p['fy'], np.ones_like(u)], -1)
        return rays @ self.transform[:3, :3].T

    def intersect(self, pixels, plane):
        rays = self.rays(pixels)
        denominator = rays[..., 2]-rays[..., :2] @ plane[:2]
        if np.any(abs(denominator) < 1e-6):
            raise SceneError('Camera rays do not intersect the measured surface')
        scale = (plane_z(plane, self.origin[:2])-self.origin[2])/denominator
        if np.any(scale <= 0):
            raise SceneError('Measured surface is behind the camera')
        return self.origin+rays*scale[..., None]

    def project(self, points):
        camera = (np.asarray(points)-self.origin) @ self.transform[:3, :3]
        if np.any(camera[..., 2] <= 0):
            raise SceneError('Placement is behind the camera')
        p = self.profile
        return camera[..., :2]/camera[..., 2, None]*[p['fx'], p['fy']]+[p['ppx'], p['ppy']]

    def support_at(self, xy, plane, cloth):
        checks = self.support_checks(xy, plane, cloth)
        return np.logical_and.reduce(list(checks.values()))

    def support_checks(self, xy, plane, cloth):
        xyz = np.concatenate([xy, plane_z(plane, xy)[..., None]], -1)
        uv = np.rint(self.project(xyz)).astype(int)
        u, v = uv[..., 0], uv[..., 1]
        inside = (u >= 0) & (u < self.w) & (v >= 0) & (v < self.h)
        u, v = np.clip(u, 0, self.w-1), np.clip(v, 0, self.h-1)
        measured = self.cloud[v, u]
        error = abs(measured[..., 2]-plane_z(plane, measured[..., :2]))
        return dict(in_image=inside, towel=cloth[v, u], measured_depth=self.valid[v, u],
                    plane_height=np.isfinite(error) & (error <= SUPPORT_TOLERANCE))


def rectangle_offsets(dimensions, yaw, margin, spacing):
    # dimensions are [short, long]; yaw is the long-axis heading in the arm base.
    half = np.asarray(dimensions)[::-1]/2+margin
    x, y = np.meshgrid(*[np.linspace(-r, r, math.ceil(2*r/spacing)+1) for r in half])
    c, s = math.cos(yaw), math.sin(yaw)
    return np.stack([c*x-s*y, s*x+c*y], -1).reshape(-1, 2)


def footprint_kernel(dimensions, yaw, margin, resolution):
    half = np.asarray(dimensions)[::-1]/2+margin+resolution/math.sqrt(2)
    extent = math.ceil(np.linalg.norm(half)/resolution)
    y, x = np.mgrid[-extent:extent+1, -extent:extent+1]*resolution
    c, s = math.cos(yaw), math.sin(yaw)
    return (abs(c*x+s*y) <= half[0]) & (abs(-s*x+c*y) <= half[1])


def erode_kernel(mask, kernel):
    shape = tuple(a+b-1 for a, b in zip(mask.shape, kernel.shape))
    sums = np.fft.irfft2(np.fft.rfft2(mask, s=shape)*np.fft.rfft2(kernel, s=shape), s=shape)
    y, x = np.array(kernel.shape)//2
    return sums[y:y+mask.shape[0], x:x+mask.shape[1]] > kernel.sum()-.25


def verify_support(surface, cloth, plane, destination, dimensions, yaw, margin=PLACEMENT_MARGIN):
    """Dense independent check, plus every image pixel covered by the footprint.

    Dense metric samples catch image-boundary gaps; the pixel test prevents a
    tiny interior hole/obstacle from disappearing between metric grid samples.
    """
    offsets = rectangle_offsets(dimensions, yaw, margin, .0005)
    checks = surface.support_checks(destination[:2]+offsets, plane, cloth)
    if not np.logical_and.reduce(list(checks.values())).all():
        counts = ', '.join(f'{key}={int((~good).sum())}/{good.size}'
                           for key, good in checks.items() if not good.all())
        raise SceneError('Placement footprint lacks clear measured towel support: failed '+counts)
    v, u = np.mgrid[:surface.h, :surface.w]
    on_plane = surface.intersect(np.stack([u, v], -1), plane)
    delta = on_plane[..., :2]-destination[:2]
    c, s = math.cos(yaw), math.sin(yaw)
    half = np.asarray(dimensions)[::-1]/2+margin
    covered = (abs(delta[..., 0]*c+delta[..., 1]*s) <= half[0]) & (abs(-delta[..., 0]*s+delta[..., 1]*c) <= half[1])
    measured = surface.cloud
    good = cloth & surface.valid & (abs(measured[..., 2]-plane_z(plane, measured[..., :2])) <= SUPPORT_TOLERANCE)
    if not covered.any() or not good[covered].all():
        raise SceneError('Placement footprint contains an obstacle or missing depth')


def placement_choices(surface, cloth, block, workspace=None, *, preferred_xy=None):
    """Check a flat placement patch, without requiring the whole towel to be flat.

    Local fits retain the same residual/slope limits. Search is restricted to
    their measured patch, and every footprint still undergoes the independent
    dense depth/obstacle check below. No depth values or holes are filled.
    """
    measured = surface.cloud[cloth & surface.valid]
    preferred=np.asarray(block['center'][:2] if preferred_xy is None else preferred_xy,dtype=float)
    if preferred.shape!=(2,) or not np.isfinite(preferred).all():
        raise SceneError('Preferred placement position must be a finite XY point')
    try:
        plane = fit_plane(measured)
        return _placement_choices(surface, cloth, block, plane, workspace,preferred_xy=preferred)
    except SceneError as global_error:
        if len(measured) < 200:
            raise global_error
    # Include the complete rotated footprint plus room for the plane fit.
    radius = float(np.linalg.norm(np.asarray(block['dimensions'])/2+PLACEMENT_MARGIN)+.02)
    low, high = measured[:,:2].min(0), measured[:,:2].max(0)
    patches = []
    for x in np.arange(low[0]+radius/2, high[0], .035):
        for y in np.arange(low[1]+radius/2, high[1], .035):
            center = np.array([x,y])
            inside = np.all(abs(measured[:,:2]-center) <= radius, axis=1)
            if inside.sum() < 200:
                continue
            try:
                plane = fit_plane(measured[inside])
            except SceneError:
                continue
            patches.append((float(np.linalg.norm(center-preferred)), center, plane))
    for _, center, plane in sorted(patches, key=lambda item:item[0])[:12]:
        try:
            return _placement_choices(surface, cloth, block, plane, workspace,
                                      patch_bounds=np.array([center-radius,center+radius]),preferred_xy=preferred)
        except SceneError:
            continue
    raise SceneError('No reachable local towel patch passes plane, full-footprint and depth checks')


def _placement_choices(surface, cloth, block, plane, workspace=None, patch_bounds=None,preferred_xy=None):
    measured = surface.cloud[cloth & surface.valid]
    res = GRID_RESOLUTION
    if workspace is None:
        xs = np.arange(.17, .46+res/2, res)
        ys = np.arange(-.47, .47+res/2, res)
    else:
        bounds = np.asarray(workspace, dtype=float)
        if bounds.shape != (2,3) or not np.isfinite(bounds).all() or np.any(bounds[0] >= bounds[1]):
            raise SceneError('Invalid placement workspace')
        # Only search the measured cloth extent inside the configured box.
        low = np.maximum(bounds[0,:2], measured[:,:2].min(axis=0))
        high = np.minimum(bounds[1,:2], measured[:,:2].max(axis=0))
        if np.any(low >= high):
            raise SceneError('Measured green towel is outside the configured placement workspace')
        xs = np.arange(low[0], high[0]+1e-12, res)
        ys = np.arange(low[1], high[1]+1e-12, res)
    x, y = np.meshgrid(xs, ys)
    xy = np.stack([x, y], -1)
    support = surface.support_at(xy, plane, cloth)
    if patch_bounds is not None:
        support &= np.all((xy >= patch_bounds[0]) & (xy <= patch_bounds[1]), axis=-1)
    heading = math.atan2(block['closing_axis'][1], block['closing_axis'][0])+math.pi/2
    choices = []
    preferred=np.asarray(block['center'][:2] if preferred_xy is None else preferred_xy)
    for angle in range(-90, 90, 15):
        yaw = heading+math.radians(angle)
        clear = erode_kernel(support, footprint_kernel(block['dimensions'], yaw, PLACEMENT_MARGIN, res))
        centers = xy[clear]
        order = np.argsort(np.linalg.norm(centers-preferred, axis=1))
        # Keep several spatially distinct alternatives for full-route IK checks.
        selected = []
        for index in order:
            center = centers[index]
            if any(np.linalg.norm(center-other) < .008 for other in selected):
                continue
            point = np.r_[center, plane_z(plane, center)]
            try:
                verify_support(surface, cloth, plane, point, block['dimensions'], yaw)
            except SceneError:
                continue
            score = float(np.linalg.norm(center-preferred)+.015*abs(math.radians(angle)))
            choices.append(dict(destination=point, destination_pixel=np.rint(surface.project(point)).astype(int),
                                placement_yaw=yaw, rotation_rad=math.radians(angle),
                                placement_margin_m=PLACEMENT_MARGIN, towel_plane=plane, score=score))
            selected.append(center)
            if len(selected) == 3:
                break
    if not choices:
        raise SceneError('No reachable, flat, measured destination on the green towel at any checked rotation')
    return sorted(choices, key=lambda choice: choice['score'])
