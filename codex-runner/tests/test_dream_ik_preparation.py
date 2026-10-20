from types import SimpleNamespace
import numpy as np
import pytest
from remote_yam.dream_ik_preparation import prepare_trajectory_variants

_solve_traj = None


class Solver:
    sides = ('right', 'left')
    side_rest = np.zeros((2, 6))
    side_base = np.zeros((2, 3))
    def fk(self, q, side):
        return np.eye(4)
    def solve_traj(self, targets, rest, history, speed, serve):
        assert targets.shape == (2, 48, 4, 4)
        assert history.shape == (2, 2, 6)
        return _solve_traj(*range(10), None, {'unchanged': True})


def test_both_kernel_structures_finish_without_changing_runtime_binding(monkeypatch):
    calls = []
    def kernel(*args):
        calls.append(args)
        return [np.zeros((48, 6)), np.zeros((48, 6))]
    monkeypatch.setitem(globals(), '_solve_traj', kernel)
    solver = Solver()
    client = SimpleNamespace(_solver=solver, _solve_spec=lambda: SimpleNamespace(solve='traj'))
    assert prepare_trajectory_variants(client) == ['independent', 'coupled']
    assert calls[-2][-2] is None
    np.testing.assert_array_equal(calls[-1][-2], solver.side_base)
    assert all(call[-1] == {'unchanged': True} for call in calls)
    assert globals()['_solve_traj'] is kernel


@pytest.mark.parametrize('failed_variant', ['independent', 'coupled'])
def test_preparation_error_restores_kernel_and_cannot_report_ready(monkeypatch, failed_variant):
    def kernel(*args):
        variant = 'independent' if args[-2] is None else 'coupled'
        if variant != failed_variant:
            return [np.zeros((48, 6)), np.zeros((48, 6))]
        raise RuntimeError('synthetic compilation failure')
    monkeypatch.setitem(globals(), '_solve_traj', kernel)
    client = SimpleNamespace(_solver=Solver(), _solve_spec=lambda: SimpleNamespace(solve='traj'))
    with pytest.raises(RuntimeError, match='compilation failure'):
        prepare_trajectory_variants(client)
    assert globals()['_solve_traj'] is kernel
