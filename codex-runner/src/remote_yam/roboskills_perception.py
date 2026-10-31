"""Measured RoboSkills views; no detector, guessed geometry or robot access.

The Python agent selects image pixels/masks. Existing ApiDepth validates paired
RGB-D, sensor identity, age and calibration. Surface samples remain observations,
not automatically executable grasp poses or ground-truth object models.
"""
from copy import deepcopy
import hashlib
import numpy as np

from .api_depth_set import ApiDepthSet
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
        for api in source.apis.values():
            api.calibration_id = report['calibration_id']

    @staticmethod
    def key(state):
        return tuple(state.get(k) for k in ('episode_id', 'lease_id', 'step_id'))

    def invalidate(self):
        self.snapshots, self.transforms, self.cursor = {}, {}, None

    def capture(self, policy):
        self.invalidate()
        state = deepcopy(policy._state)
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
                upper_m=np.quantile(points,.95,axis=0).tolist())
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
                    quality=quality_summary(self.report['quality']) if concise else deepcopy(self.report['quality']))
