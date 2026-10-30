"""Bind SDK 1.0.0 trajectory IK to the native guard's calibrated limits.

The SDK shares geometry between YAM arms. Keep that shared group: its hard
inter-arm fence requires it. Only trajectory-side limit arrays are copied;
the nominal tick solve remains a warm start, and the trajectory solve and
post-seam decode use the calibrated bounds. Install before SDK IK warmup.
"""
from copy import copy
from dataclasses import replace
from functools import wraps
import hashlib
import json
import math

import numpy as np


def joint_bounds(lower, upper):
    def vector(values):
        values = list(values)
        if len(values) != 12 or any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError('Expected twelve finite native joint bounds')
        return [float(v) for v in values]
    lower, upper = vector(lower), vector(upper)
    if any(lo >= hi for lo, hi in zip(lower, upper)):
        raise ValueError('Native joint bounds must have nonempty intervals')
    return dict(lower_rad=lower, upper_rad=upper)


def bounds_sha256(bounds):
    return hashlib.sha256(json.dumps(bounds, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bind_solver_bounds(solver, bounds, *, margin, array=np.asarray):
    """Pinned ChunkIK contract; preserve geometry, costs, speeds and fences."""
    bounds = joint_bounds(bounds['lower_rad'], bounds['upper_rad'])
    if (set(solver.sides) != {'left', 'right'} or len(solver._groups) != 1
            or len(solver._side_groups) != 2
            or any(g is not solver._groups[0] for g in solver._side_groups)):
        raise RuntimeError('Unsupported Dream shared YAM geometry contract')
    groups, lower, upper = [], [], []
    for i, side in enumerate(solver.sides):
        group = copy(solver._side_groups[i])
        arm = group.arm
        start = 0 if side == 'left' else 6  # Native bimanual order.
        lo = np.maximum(solver.side_lo[i], np.asarray(bounds['lower_rad'][start:start+6]) + margin)
        hi = np.minimum(solver.side_hi[i], np.asarray(bounds['upper_rad'][start:start+6]) - margin)
        if lo.shape != (6,) or hi.shape != (6,) or np.any(lo >= hi):
            raise ValueError('Native bounds and Dream margins have no common interval')
        order = list(arm.to_pyroki)
        group.arm = replace(arm, lo=array(lo[order]), hi=array(hi[order]))
        groups.append(group)
        lower.append(lo)
        upper.append(hi)
    solver._side_groups = groups
    solver.side_lo, solver.side_hi = np.stack(lower), np.stack(upper)


def install_trajectory_bounds(bounds):
    """Process-local startup hook; no SDK files or model proprioception change."""
    from dream_ik import solver, specs
    import jax.numpy as jnp
    bounds = joint_bounds(bounds['lower_rad'], bounds['upper_rad'])
    digest = bounds_sha256(bounds)
    cls = solver.ChunkIK
    previous = getattr(cls, '_blupe_native_bounds', None)
    if previous is not None:
        if previous != digest:
            raise RuntimeError('Dream native bounds cannot change after preparation')
        return digest
    spec = specs.EMBODIMENTS['yam']
    if (isinstance(spec.arm, dict) or spec.arm.joints != tuple(f'joint{i}' for i in range(1, 7))):
        raise RuntimeError('Unsupported Dream YAM joint ordering')
    original = cls.__init__

    @wraps(original)
    def initialize(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if (args[0] if args else kwargs.get('embodiment')) == 'yam':
            bind_solver_bounds(self, bounds, margin=spec.arm.limit_margin, array=jnp.asarray)

    cls.__init__ = initialize
    cls._blupe_native_bounds = digest
    return digest
