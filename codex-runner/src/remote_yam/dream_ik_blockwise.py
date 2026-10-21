"""Block-local normal equations for the pinned Dream SDK1.0.0/JAX0.7.1.

See docs/refs/dreamlabs/BLOCKWISE-GRAM.md. Only the dense Gram product is
replaced; costs, damping, factorization and convergence remain with the SDK.
Install once before configuring any client or compiling its IK kernels.
"""
from functools import wraps
import hashlib
from pathlib import Path

IMPLEMENTATION = 'blockwise_gram_f64_v2'
SOURCE_HASHES = {
    'jaxls._solvers': 'c0c261dbcbef43fd99cf215cc23259e8a6bcb945115b4d3e7a58c19f33afebb8',
    'jaxls._problem': '50de2b85664d2e770c3d83ee7c35fcf3341dcd16adccec0728f8bfe3fccd52c5',
    'jaxls._sparse_matrices': 'ba7396ddf127ad582bae318fc84d1ecf7dc2ff0ed28087900f4ddca7a64aa5c9',
}


def blockwise_gram(matrix):
    import jax.numpy as jnp
    # Keep the normal equations and their Cholesky solve in float64. Rounding
    # a more accurate sum back to float32 still changes difficult LM steps.
    out = jnp.zeros((matrix.shape[1], matrix.shape[1]), dtype=jnp.float64)
    for row in matrix.block_rows:
        blocks = row.blocks_concat.astype(jnp.float64)
        indices = jnp.concatenate([start[:, None] + jnp.arange(width)[None, :]
                                   for start, width in zip(row.start_cols, row.block_num_cols)], axis=1)
        # SparseBlockRow.to_dense writes later blocks over earlier ones. Keep
        # that contract even for overlapping columns; real IK rows are disjoint.
        columns = jnp.arange(blocks.shape[-1])
        later = columns[:, None] < columns[None, :]
        overwritten = jnp.any((indices[:, :, None] == indices[:, None, :]) & later[None], axis=-1)
        blocks = jnp.where(overwritten[:, None, :], 0, blocks)
        local = jnp.einsum('bri,brj->bij', blocks, blocks)
        out = out.at[indices[:, :, None], indices[:, None, :]].add(local)
    return out


class _GramOperand:
    def __init__(self, matrix):
        self.matrix = matrix

    @property
    def T(self):
        return self

    def __matmul__(self, other):
        if other is not self:
            raise RuntimeError('Unsupported Dream Gram operand')
        return blockwise_gram(self.matrix)


class _BlockMatrix:
    def __init__(self, matrix):
        self.matrix = matrix

    def to_dense(self):
        # The verified lm_inner_step consumes this only as A_dense.T @ A_dense.
        return _GramOperand(self.matrix)

    def __getattr__(self, name):
        # The SDK also uses sparse multiply for its unchanged step-quality
        # calculation. Delegate everything except the verified dense operand.
        return getattr(self.matrix, name)


def install_blockwise_gram():
    import importlib
    import jax
    import jaxlib
    if jax.__version__ != '0.7.1' or jaxlib.__version__ != '0.7.1':
        raise RuntimeError('Unsupported Dream linear algebra runtime')
    if not jax.config.x64_enabled:
        raise RuntimeError('Dream blockwise IK requires float64 worker startup')
    modules = {name: importlib.import_module(name) for name in SOURCE_HASHES}
    for name, expected in SOURCE_HASHES.items():
        if hashlib.sha256(Path(modules[name].__file__).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Unsupported Dream linear algebra source')
    solver = modules['jaxls._solvers'].NonlinearSolver
    original = solver.lm_inner_step
    if getattr(original, '_dream_blockwise_gram', False):
        return IMPLEMENTATION

    @wraps(original)
    def inner_step(self, problem, inner_state, sol_prev, jacobian_scaler,
                   A_blocksparse, A_multiply, AT_multiply, ATb, schur_factors=None):
        selected = (_BlockMatrix(A_blocksparse)
                    if self.linear_solver == 'dense_cholesky' and schur_factors is None
                    else A_blocksparse)
        return original(self, problem, inner_state, sol_prev, jacobian_scaler,
                        selected, A_multiply, AT_multiply, ATb, schur_factors)

    inner_step._dream_blockwise_gram = True
    solver.lm_inner_step = inner_step
    return IMPLEMENTATION
