"""Prepare both SDK1.0.0 trajectory kernel structures before visitor use.

Pinned source contract: dream_ik/solver.py ChunkIK.solve_traj passes either
None or side_base to _solve_traj. These have different JAX pytree structures.
No robot observation, model request, solver setting or session is changed.
"""
from inspect import unwrap
import numpy as np


def prepare_trajectory_variants(client_ik, rows=48):
    solver = client_ik._solver
    serve = client_ik._solve_spec()
    if serve.solve != 'traj' or len(solver.sides) != 2:
        raise RuntimeError('Unsupported Dream trajectory preparation contract')
    rest = np.asarray(solver.side_rest, dtype=np.float64)
    base = np.asarray(solver.side_base, dtype=np.float64)
    if rest.ndim != 2 or base.shape != (2, 3):
        raise RuntimeError('Unsupported Dream trajectory preparation shape')
    targets = np.stack([np.repeat(solver.fk(rest[i], side)[None], rows, axis=0)
                        for i, side in enumerate(solver.sides)])
    history = np.repeat(rest[:, None], 2, axis=1)
    # Capture the SDK's exact kernel arguments, including its arm specs and
    # weights. This runs during exclusive startup after traj_ready; restore the
    # binding even on error. All returned trajectories are discarded.
    # Passive tracing uses functools.wraps on the bound method. Resolve its
    # original definition before finding the SDK module's kernel binding.
    bindings = unwrap(solver.solve_traj).__func__.__globals__
    original = bindings['_solve_traj']
    captured = []
    def capture(*args, **kwargs):
        if kwargs or len(args) != 12:
            raise RuntimeError('Unsupported Dream trajectory kernel signature')
        captured.append(args)
        return original(*args)
    try:
        bindings['_solve_traj'] = capture
        solver.solve_traj(targets, rest, history, np.inf, serve)
    finally:
        bindings['_solve_traj'] = original
    if len(captured) != 1:
        raise RuntimeError('Dream trajectory kernel preparation was not captured')
    for variant in (None, base):
        args = list(captured[0])
        args[-2] = variant
        result = original(*args)
        # Materialization waits for JAX compilation AND execution to finish.
        for arm in result:
            np.asarray(arm)
    return ['independent', 'coupled']
