"""Measured RoboSkills views; no detector, guessed geometry or robot access.

The Python agent selects image pixels/masks. Existing ApiDepth validates paired
RGB-D, sensor identity, age and calibration. Surface samples remain observations,
not automatically executable grasp poses or ground-truth object models.
"""
from copy import deepcopy
import hashlib
import numpy as np

from .api_depth_set import ApiDepthSet
from .api_depth import factory_ray
from .camera_calibration import rigid


def calibration_geometry(report):
    """Pin calibration semantics, excluding explicitly live delivery status."""
    value=deepcopy(report)
    for camera in value['cameras'].values():
        depth=camera.get('depth')
        if isinstance(depth,dict):
            # Public /calibration includes the current bundle's capture time
            # and availability. These change every frame, not the extrinsics.
            depth.pop('captured_at',None)
            depth.pop('available',None)
    return value


def quality_summary(quality):
    return {k:deepcopy(quality[k]) for k in ('status','operator_selected','extrinsics_provisional',
            'failures','unverified','limitations') if k in quality}


def _surface_plane(points):
    """Least-squares shape of selected measured points, not semantic face truth."""
    points=np.asarray(points,dtype=float)
    scope=('Best-fit plane of sampled visible depth, not proof of a planar face, '
           'physical top, contact clearance or calibration accuracy. Normal sign '
           'is arbitrary: compare abs(dot(unit normals)) within the SAME camera '
           'and state, checking residuals and principal spans; mixed surfaces can '
           'have no meaningful single normal.')
    result=dict(available=False,sample_count=len(points),scope=scope)
    if points.ndim!=2 or points.shape[1]!=3 or len(points)<9 or not np.isfinite(points).all():
        return dict(result,reason='At least nine finite measured3D points are required')
    center=np.mean(points,axis=0)
    _,singular,axes=np.linalg.svd(points-center,full_matrices=False)
    principal=singular/np.sqrt(len(points))
    # One nanometre is a numerical degeneracy guard, not sensor accuracy or a
    # motion/contact tolerance. A point/line cannot define a surface normal.
    if principal[1]<=1e-9:return dict(result,reason='Measured points do not span a surface')
    normal=axes[-1].copy()
    if normal[np.argmax(np.abs(normal))]<0:normal=-normal
    residual=(points-center)@normal
    return dict(result,available=True,center_m=center.tolist(),normal_base=normal.tolist(),
                rms_residual_m=float(np.sqrt(np.mean(residual**2))),
                abs_residual_95_m=float(np.quantile(np.abs(residual),.95)),
                principal_rms_m=principal.tolist())


def _project_factory(profile, optical):
    """Invert the SDK-oracle-tested ray convention, as factory hand-eye does.

    Convergence1e-10, final acceptance1e-7 in normalized ray coordinates;
    arithmetic tolerances, not calibration accuracy or hardware-limit changes.
    """
    target=optical[:2]/optical[2]
    focal=np.array([profile['fx'],profile['fy']])
    pixel=target*focal+[profile['ppx'],profile['ppy']]
    for _ in range(15):
        error=target-factory_ray(profile,*pixel)[:2]
        pixel+=error*focal
        if np.isfinite(pixel).all() and np.max(np.abs(error))<1e-10:
            return pixel
    if (not np.isfinite(pixel).all()
            or np.max(np.abs(target-factory_ray(profile,*pixel)[:2]))>1e-7):
        raise ValueError('Factory projection did not converge')
    return pixel


class MeasuredResult(dict):
    """Full quality data retained, with a concise REPL representation."""
    def __repr__(self):
        value=dict(self)
        if 'quality' in value:
            value['quality']=quality_summary(value['quality'])
            value['full_quality']='result["quality"] or bot.rgbd(camera)["quality"]'
        return repr(value)


class RoboSkillsPerception:
    def __init__(self, source, report):
        if not isinstance(source, ApiDepthSet):
            raise TypeError('RoboSkills metric perception requires ApiDepthSet')
        self.source, self.report = source, deepcopy(report)
        self.snapshots, self.transforms, self.cursor = {}, {}, None
        self.reference_identity=None
        self.references=[]
        self.projected_references=[]
        for api in source.apis.values():
            api.calibration_id = report['calibration_id']

    @staticmethod
    def key(state):
        return tuple(state.get(k) for k in ('episode_id', 'lease_id', 'step_id'))

    def invalidate(self):
        self.snapshots, self.transforms, self.cursor = {}, {}, None
        self.projected_references=[]

    def _bind_references(self,state):
        identity=self.key(state)[:2]
        if identity!=self.reference_identity:
            self.reference_identity=identity
            self.references=[]
            self.projected_references=[]

    def remember(self,result,state):
        """Keep at most four distinct public pixel queries as untracked history."""
        self._bind_references(state)
        reference=dict(source_camera=result['camera'],source_pixel=list(result['pixel']),
            source_step_id=state['step_id'],source_captured_at=result['captured_at'],
            points_base_m=deepcopy(result['points_base_m']))
        self.references=[r for r in self.references if
            (r['source_camera'],r['source_pixel'])!=(reference['source_camera'],reference['source_pixel'])]
        self.references=(self.references+[reference])[-4:]
        if self.snapshots and self.cursor==self.key(state):self._project_references(state)

    def _project_references(self,state):
        rows=[]
        for reference in self.references:
            arm=next(iter(reference['points_base_m']))
            point=np.array(reference['points_base_m'][arm],dtype=float)
            row=deepcopy(reference);row['projections']={}
            for camera in self.snapshots:
                try:
                    projected=self.project(state,point,arm=arm,camera=camera)
                    fields=('pixel','nearest_pixel','inside_image','expected_optical_z_m',
                            'measured_minus_expected_optical_z_m','captured_at')
                    value={k:projected[k] for k in fields}
                    value['depth_sample']={k:v for k,v in projected['depth_sample'].items()
                        if k in ('available','reason','radius','optical_z_m','valid_samples','patch_spread_m')}
                    row['projections'][camera]=dict(projection_available=True,**value)
                except ValueError as exc:
                    row['projections'][camera]=dict(projection_available=False,reason=str(exc))
            rows.append(row)
        self.projected_references=rows

    def capture(self, policy):
        self.invalidate()
        state = deepcopy(policy._state)
        self._bind_references(state)
        frames = self.source.capture_for_policy(state, cancelled=policy.cancelled,
                                                on_event=policy._camera_event)
        snapshots = self.source.snapshots
        for snapshot in snapshots.values():
            if calibration_geometry(snapshot.calibration) != calibration_geometry(self.report):
                raise ValueError('RGB-D calibration changed after station binding')
        policy._geometry.observe(state)
        poses = policy._geometry.ik._poses()
        transforms = {}
        for role in ('top', 'left', 'right'):
            camera = self.report['cameras'][role]
            if role == 'top':
                transforms[role] = {arm:rigid(t) for arm,t in camera['T_base_camera'].items()}
            else:
                position, rotation = poses[('left', 'right').index(role)]
                transforms[role] = {}
                for index, arm in enumerate(('left', 'right')):
                    grasp = np.eye(4)
                    grasp[:3,:3], grasp[:3,3] = rotation, position-policy._geometry.bases[index]
                    transforms[role][arm] = grasp @ rigid(camera['T_grasp_camera'])
        self.source.require_fresh(snapshots, stopped=True)
        self.snapshots, self.transforms, self.cursor = snapshots, transforms, self.key(state)
        self._project_references(state)
        for role, snapshot in snapshots.items():
            path = policy._recorder.path / f'rgbd-{state["step_id"]}-{role}.npz'
            path.write_bytes(snapshot.recording_bundle())
        policy._vision_frames = [f.summary() for f in frames]
        policy._record('rgbd_observation', **self.summary())
        return {role:snapshot.rgb.copy() for role,snapshot in snapshots.items()}

    def require(self, state, camera):
        if camera not in self.snapshots or self.cursor != self.key(state):
            raise ValueError('Call show(bot.observe()) after movement before querying RGB-D')
        return self.snapshots[camera]

    def rgbd(self, state, camera):
        snapshot = self.require(state, camera)
        return dict(rgb=snapshot.rgb.copy(), depth_m=snapshot.depth.copy(),
                    metadata=deepcopy(snapshot.metadata),
                    calibration=deepcopy(self.report['cameras'][camera]),
                    quality=deepcopy(self.report['quality']),
                    T_base_camera={a:t.copy() for a,t in self.transforms[camera].items()})

    def measure(self, state, u, v, camera='top', radius=2, arm=None):
        snapshot = self.require(state, camera)
        if arm not in (None, 'left', 'right'):
            raise ValueError('arm must be left, right or None for both')
        values = {a:snapshot.measure(u, v, radius, a, T_base_camera=self.transforms[camera][a])
                  for a in (('left', 'right') if arm is None else (arm,))}
        result = dict(next(iter(values.values())))
        # A selected arm must not change the primary result schema. Agents
        # compose these calls in Python and should not mistake a missing alias
        # for unavailable sensor data.
        result['points_base_m'] = {a:v['point_base_m'] for a,v in values.items()}
        if arm is None:
            del result['arm'], result['point_base_m']
        return MeasuredResult(result)

    def project(self, state, point, *, arm, camera='top'):
        if not isinstance(camera,str) or camera not in ('top','left','right'):
            raise ValueError('Projection camera must be top, left or right')
        if not isinstance(arm,str) or arm not in ('left','right'):
            raise ValueError('Projection arm must name the input point base: left or right')
        snapshot=self.require(state,camera)
        profile=self.report['cameras'][camera].get('depth_intrinsics')
        if profile is None:
            raise ValueError('Projection requires the bound aligned-color factory profile')
        T=self.transforms[camera][arm]
        optical=T[:3,:3].T@(point-T[:3,3])
        # Numerical near-plane guard,1nanometre: not a workspace/range change.
        if not np.isfinite(optical).all() or optical[2]<=1e-9:
            raise ValueError('Point must be more than1e-9metres in front of the camera plane')
        pixel=_project_factory(profile,optical)
        nearest=[int(np.floor(float(x)+.5)) for x in pixel]
        h,w=snapshot.depth.shape
        inside=0<=nearest[0]<w and 0<=nearest[1]<h
        sample=dict(available=False,radius=2,reason='Projected ray is outside the image pixel footprint')
        delta=None
        if inside:
            try:
                measured=snapshot.measure(*nearest,2,arm,T_base_camera=T)
                sample=dict(available=True,radius=2,**{k:measured[k] for k in
                    ('pixel','optical_z_m','valid_samples','patch_spread_m','point_base_m',
                     'depth_quantization_m','depth_max_error_m')})
                delta=measured['optical_z_m']-float(optical[2])
            except ValueError as exc:
                sample=dict(available=False,radius=2,reason=str(exc))
        return MeasuredResult(camera=camera,arm=arm,point_base_m=point.tolist(),
            point_camera_m=optical.tolist(),pixel=pixel.tolist(),
            nearest_pixel=nearest if inside else None,inside_image=bool(inside),
            expected_optical_z_m=float(optical[2]),depth_sample=sample,
            measured_minus_expected_optical_z_m=delta,
            captured_at=snapshot.metadata['captured_at'],calibration_id=self.report['calibration_id'],
            quality=deepcopy(self.report['quality']),
            warning='Cached-frame model projection and optional nearest-ray depth patch, not '
                    'object identity/visibility, a grasp target or calibration validation. '
                    'A nearer surface may occlude the reference point; a farther surface or '
                    'missing/noisy depth may reflect an edge, hole or model error. '
                    'Inspect RGB correspondence and retain calibration uncertainty.')

    def localize(self, state, label, mask, camera='top', arm=None):
        snapshot = self.require(state, camera)
        mask = np.asarray(mask)
        if not isinstance(label, str) or not label.strip() or len(label)>100:
            raise ValueError('Give a short visual object label')
        if mask.dtype != np.bool_ or mask.shape != snapshot.depth.shape:
            raise ValueError('Object mask must be boolean on the original paired RGB pixel grid')
        selected = int(mask.sum())
        good = mask & np.isfinite(snapshot.depth) & (snapshot.depth>0)
        ys,xs = np.where(good)
        if len(xs)<9 or len(xs)<selected*.5:
            raise ValueError('Object mask has too little measured depth; no object location available')
        indices = np.linspace(0, len(xs)-1, min(256,len(xs))).astype(int)
        samples = [self.measure(state,int(xs[i]),int(ys[i]),camera,0,arm) for i in indices]
        arms = ('left','right') if arm is None else (arm,)
        surfaces = {}
        for a in arms:
            points = np.array([v['points_base_m'][a] if arm is None else v['point_base_m'] for v in samples])
            surfaces[a] = dict(center_m=np.median(points,axis=0).tolist(),
                lower_m=np.quantile(points,.05,axis=0).tolist(),
                upper_m=np.quantile(points,.95,axis=0).tolist(),plane_fit=_surface_plane(points))
        return MeasuredResult(label=label, camera=camera, captured_at=snapshot.metadata['captured_at'],
                    calibration_id=self.report['calibration_id'], pixel_count=selected,
                    valid_depth_count=len(xs), mask_sha256=hashlib.sha256(mask.tobytes()).hexdigest(),
                    surfaces_in_arm_bases=surfaces, quality=deepcopy(self.report['quality']),
                    warning='Agent-selected mask, measured visible surface only; not a full object pose, '
                            'grasp target, object height or proof of grasp. Calibration remains experimental.')

    def summary(self, concise=False):
        return dict(available=bool(self.snapshots), calibration_id=self.report['calibration_id'],
                    coordinate_frame='per_arm_base', units='metres',
                    captures={r:dict(captured_at=s.metadata['captured_at'],shape=list(s.rgb.shape),
                        rgb_sha256=hashlib.sha256(s.rgb.tobytes()).hexdigest()) for r,s in self.snapshots.items()},
                    quality=quality_summary(self.report['quality']) if concise else deepcopy(self.report['quality']),
                    **(dict(surface_references=deepcopy(self.projected_references),
                        reference_scope='Last four distinct historical pixel queries, NOT tracked objects '
                            'or current poses. Source pixel/step/time are retained. Projections and '
                            'nearest-ray depth patches use the current captured views; inspect RGB '
                            'correspondence/occlusion and calibration uncertainty.')
                       if self.projected_references else {}))
