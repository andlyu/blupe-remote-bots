"""Pinned isolated SDK tests: start Python with JAX_ENABLE_X64=1; no networking."""
from types import SimpleNamespace
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest
from remote_yam import dream_ik_blockwise as patch

jax = pytest.importorskip('jax')
jnp = pytest.importorskip('jax.numpy')
sparse = pytest.importorskip('jaxls._sparse_matrices')
pytestmark = pytest.mark.skipif(not jax.config.x64_enabled,
    reason='Run this isolated worker integration suite with JAX_ENABLE_X64=1')


@pytest.mark.parametrize('seed', range(4))
@pytest.mark.parametrize('overlap', [False, True])
def test_real_batched_blocks_match_dense_gram(seed, overlap):
    rng = np.random.default_rng(seed)
    rows = []
    for batch, residuals, widths in [(5, 9, (2, 3)), (3, 4, (1, 2, 2))]:
        starts = (tuple(jnp.full((batch,), x, dtype=jnp.int32) for x in
                        ([0, 1] if len(widths) == 2 else [0, 0, 1])) if overlap else
                  tuple(jnp.full((batch,), x, dtype=jnp.int32) for x in
                        ([0, 4] if len(widths) == 2 else [0, 2, 5])))
        rows.append(sparse.SparseBlockRow(num_cols=8, start_cols=starts,
                    block_num_cols=widths, blocks_concat=jnp.asarray(
                        rng.normal(size=(batch, residuals, sum(widths))), dtype=jnp.float64)))
    matrix = sparse.BlockRowSparseMatrix(tuple(rows), shape=(57, 8))
    dense = matrix.to_dense()
    actual = jax.jit(patch.blockwise_gram)(matrix)
    np.testing.assert_allclose(actual, dense.T @ dense, rtol=2e-6, atol=3e-6)


def test_install_is_idempotent_and_does_not_write_sdk_source(monkeypatch):
    import jaxls._solvers as solvers
    original = solvers.NonlinearSolver.lm_inner_step
    monkeypatch.setattr(solvers.NonlinearSolver, 'lm_inner_step', original)
    assert patch.install_blockwise_gram() == patch.IMPLEMENTATION
    installed = solvers.NonlinearSolver.lm_inner_step
    assert installed is not original and installed.__wrapped__ is original
    assert patch.install_blockwise_gram() == patch.IMPLEMENTATION
    assert solvers.NonlinearSolver.lm_inner_step is installed


def test_sparse_step_quality_and_other_operations_are_delegated():
    matrix = SimpleNamespace(multiply=lambda x: x * 3, shape=(7, 2))
    proxy = patch._BlockMatrix(matrix)
    np.testing.assert_array_equal(proxy.multiply(np.array([1., 2.])), [3., 6.])
    assert proxy.shape == (7, 2)


def test_incompatible_source_fails_before_installing(monkeypatch):
    import jaxls._solvers as solvers
    original = solvers.NonlinearSolver.lm_inner_step
    monkeypatch.setattr(patch, 'SOURCE_HASHES', {'jaxls._solvers': '0' * 64})
    with pytest.raises(RuntimeError, match='source'):
        patch.install_blockwise_gram()
    assert solvers.NonlinearSolver.lm_inner_step is original


def test_incompatible_jax_fails_before_installing(monkeypatch):
    monkeypatch.setattr(jax, '__version__', 'unsupported')
    with pytest.raises(RuntimeError, match='runtime'):
        patch.install_blockwise_gram()


def test_float32_runtime_fails_before_installing(monkeypatch):
    import jaxls._solvers as solvers
    original = solvers.NonlinearSolver.lm_inner_step
    # Read-only property normally follows the global startup configuration.
    monkeypatch.setattr(type(jax.config), 'x64_enabled', property(lambda _: False))
    with pytest.raises(RuntimeError, match='float64 worker startup'):
        patch.install_blockwise_gram()
    assert solvers.NonlinearSolver.lm_inner_step is original


def test_gram_keeps_float64_accumulation_for_float32_blocks():
    if not jax.config.x64_enabled:
        pytest.skip('requires the isolated float64 startup test environment')
    row = sparse.SparseBlockRow(num_cols=2, start_cols=(jnp.zeros(3, dtype=jnp.int32),),
        block_num_cols=(2,), blocks_concat=jnp.array(
            [[[1e4, 1e4]], [[1., 1.]], [[1e4, -1e4]]], dtype=jnp.float32))
    matrix = sparse.BlockRowSparseMatrix((row,), shape=(3, 2))
    actual = jax.jit(patch.blockwise_gram)(matrix)
    assert actual.dtype == jnp.float64
    assert float(actual[0, 1]) == 1.


@pytest.mark.parametrize('enabled', [False, True])
def test_worker_sets_precision_before_sdk_import(tmp_path, enabled):
    # A fresh process catches late configuration that an already-imported JAX
    # fixture cannot detect. The fake SDK exits before any model/client setup.
    (tmp_path / 'dream.py').write_text(
        'import jax\n'
        f'assert jax.config.x64_enabled is {enabled!r}\n'
        'print("precision checked")\nraise SystemExit(0)\n')
    env = dict(os.environ, DREAM_WORK_DIR=str(tmp_path / 'work'),
               YAM_DREAM_BLOCKWISE_IK='1' if enabled else '0', JAX_ENABLE_X64='0',
               PYTHONPATH=str(tmp_path))
    result = subprocess.run([sys.executable, str(Path(patch.__file__).with_name('dream_worker.py'))],
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'precision checked'


@pytest.mark.parametrize('linear_solver,schur,uses_blockwise', [
    ('dense_cholesky', None, True), ('dense_cholesky', object(), False),
    ('conjugate_gradient', None, False), ('cholmod', None, False)])
def test_adapter_only_changes_the_dense_gram_branch(monkeypatch, linear_solver, schur, uses_blockwise):
    import jaxls._solvers as solvers
    def capture(*args):
        return args
    monkeypatch.setattr(solvers.NonlinearSolver, 'lm_inner_step', capture)
    patch.install_blockwise_gram()
    matrix = object()
    result = solvers.NonlinearSolver.lm_inner_step(SimpleNamespace(linear_solver=linear_solver),
              'problem', 'inner', 'solution', 'scaler', matrix, 'multiply', 'transpose', 'rhs', schur)
    assert result[:5] == (result[0], 'problem', 'inner', 'solution', 'scaler')
    assert result[6:] == ('multiply', 'transpose', 'rhs', schur)
    assert isinstance(result[5], patch._BlockMatrix) is uses_blockwise
    assert (result[5].matrix if uses_blockwise else result[5]) is matrix
