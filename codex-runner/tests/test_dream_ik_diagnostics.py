import json
from pathlib import Path
import stat
import sys
import threading
import time
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from remote_yam.dream_sdk_trace import DreamSDKTrace


SECRET = 'private-prompt-image-secret-never-record'


def records(trace):
    trace.queue.join()
    return [json.loads(x) for x in trace.path.read_text().splitlines()]


def fake_sdk(monkeypatch, *, gate=None, failure=None):
    module = ModuleType('dream_ik.solver')
    compiler = ModuleType('jax._src.compiler')
    calls = []
    token = object()
    cache = [None, None]

    def cache_read(*args, **kwargs):
        calls.append('cache')
        return cache

    def backend(*args, **kwargs):
        calls.append('compile')
        return token

    def compile_or_cached(*args, **kwargs):
        value = compiler._cache_read()
        return value[0] if value[0] is not None else compiler.backend_compile_and_load()

    compiler._cache_read = cache_read
    compiler.backend_compile_and_load = backend
    compiler.compile_or_get_cached = compile_or_cached
    entered = threading.Event()

    def kernel(*args, **kwargs):
        calls.append(('kernel', args, kwargs))
        entered.set()
        if gate:
            gate.wait(2)
        if failure:
            raise failure
        assert compiler.compile_or_get_cached() is token
        return args[3]

    module._solve_traj = kernel
    module._interarm_distance = lambda *args: np.asarray(.1)

    class Solver:
        def solve(self, args):
            calls.append('seed')
            return args

        def solve_traj(self, args):
            self.solve(args)
            module._interarm_distance()
            return module._solve_traj(*args)

    Solver.__module__ = module.__name__
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setitem(sys.modules, compiler.__name__, compiler)
    arrays = tuple(np.ones((3, 6), dtype=np.float32) for _ in range(2))
    args = (SECRET, ({}, {}), ({'pos': np.asarray(50.)},)*2,
            arrays, arrays, arrays, arrays, arrays, arrays, arrays,
            np.ones((2, 3)), {'vel': np.asarray(5.)})
    # arms are opaque SDK geometry to diagnostics; only their count is needed.
    args = ((SECRET, SECRET), *args[1:])
    ik = SimpleNamespace(_solver=Solver())
    return SimpleNamespace(module=module, compiler=compiler, ik=ik, args=args,
        calls=calls, token=token, cache=cache, entered=entered, original=kernel)


def test_branch_stages_cache_and_exact_argument_result_identity(tmp_path, monkeypatch):
    sdk = fake_sdk(monkeypatch)
    trace = DreamSDKTrace(tmp_path, interval_s=100)
    try:
        trace.ik_diagnostics.install(sdk.ik)
        trace.ik_diagnostics.install(sdk.ik)
        with trace.prediction(48):
            assert sdk.ik._solver.solve_traj(sdk.args) is sdk.args[3]
        assert len([x for x in sdk.calls if isinstance(x, tuple)]) == 1
        sent = next(x for x in sdk.calls if isinstance(x, tuple))
        assert all(a is b for a, b in zip(sent[1], sdk.args))
        data = records(trace)
        assert [x['stage'] for x in data if x['state'] == 'started'] == [
            'prediction', 'ik_trajectory', 'ik_seed', 'ik_clearance', 'ik_kernel',
            'jax_compile_or_cache', 'jax_cache_read', 'jax_compile']
        kernels = [x for x in data if x['stage'] == 'ik_kernel']
        assert {x['branch'] for x in kernels} == {'coupled'}
        assert all(x['rows'] == 3 and x['arms'] == 2 for x in kernels)
        assert all(x['cpu_s'] >= 0 for x in data if x['state'] == 'completed' and 'duration_s' in x)
        assert any(x.get('cache_hit') == 0 for x in data)
        sdk.cache[0] = sdk.token
        args = (*sdk.args[:10], None, sdk.args[11])
        with trace.prediction(96):
            assert sdk.ik._solver.solve_traj(args) is args[3]
        data = records(trace)
        assert any(x.get('branch') == 'independent' for x in data)
        assert any(x.get('cache_hit') == 1 for x in data)
        assert sdk.calls.count('compile') == 1
        assert SECRET not in trace.path.read_text()
    finally:
        trace.close()
    assert sdk.module._solve_traj is sdk.original


def test_original_exception_is_not_retried_or_replaced(tmp_path, monkeypatch):
    error = RuntimeError(SECRET)
    sdk = fake_sdk(monkeypatch, failure=error)
    trace = DreamSDKTrace(tmp_path)
    try:
        trace.ik_diagnostics.install(sdk.ik)
        with pytest.raises(RuntimeError) as raised, trace.prediction():
            sdk.ik._solver.solve_traj(sdk.args)
        assert raised.value is error
        assert len([x for x in sdk.calls if isinstance(x, tuple)]) == 1
        assert SECRET not in trace.path.read_text() if trace.path.exists() else True
    finally:
        trace.close()


def test_slow_input_capture_is_private_numeric_bounded_and_once(tmp_path, monkeypatch):
    release = threading.Event()
    sdk = fake_sdk(monkeypatch, gate=release)
    trace = DreamSDKTrace(tmp_path, interval_s=.01)
    trace.ik_diagnostics.slow_s = .001
    trace.ik_diagnostics.install(sdk.ik)
    def prediction():
        with trace.prediction(144):
            sdk.ik._solver.solve_traj(sdk.args)
    thread = threading.Thread(target=prediction)
    try:
        thread.start()
        assert sdk.entered.wait(1)
        deadline = time.monotonic()+1.5
        meta = tmp_path/'ik-replay.json'
        while not meta.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert meta.exists() and thread.is_alive()
        trace.ik_diagnostics.jobs.join()
        replay = tmp_path/'ik-replay.npz'
        assert replay.stat().st_size < trace.ik_diagnostics.replay_bytes
        assert stat.S_IMODE(replay.stat().st_mode) == stat.S_IMODE(meta.stat().st_mode) == 0o600
        info = json.loads(meta.read_text())
        assert info['prediction'] == 1 and info['branch'] == 'coupled'
        with np.load(replay, allow_pickle=False) as arrays:
            assert len(arrays.files) == info['array_count']
            assert all(arrays[key].dtype.kind in 'biuf' for key in arrays.files)
            targets = info['structure']['targets']
            assert np.array_equal(arrays[targets[0]], sdk.args[3][0])
        assert all(SECRET.encode() not in p.read_bytes() for p in tmp_path.iterdir())
        assert any(x['state'] == 'waiting' and 'cpu_s' in x for x in records(trace))
        original_bytes = replay.read_bytes()
        release.set()
        thread.join(1)
        with trace.prediction():
            sdk.ik._solver.solve_traj(sdk.args)
        assert replay.read_bytes() == original_bytes
    finally:
        release.set()
        thread.join(2)
        trace.close()


def test_replay_rejects_text_and_oversized_values_without_model_failure(tmp_path):
    trace = DreamSDKTrace(tmp_path)
    try:
        with pytest.raises(ValueError):
            trace.ik_diagnostics._save_replay(1,
                ((), {}, {}, np.asarray([SECRET]), (), (), (), (), (), (), None, {}), {})
        with pytest.raises(ValueError):
            trace.ik_diagnostics._save_replay(1,
                ((), {}, {}, np.zeros(300000), (), (), (), (), (), (), None, {}), {})
        with pytest.raises(ValueError):
            trace.ik_diagnostics._save_replay(1,
                ((), {}, {'private_prompt': np.asarray(1.)}, (), (), (), (), (), (), (), None, {}), {})
        assert not (tmp_path/'ik-replay.npz').exists()
    finally:
        trace.close()


def test_replay_writer_failure_cannot_fail_or_retry_the_prediction(tmp_path, monkeypatch):
    sdk = fake_sdk(monkeypatch)
    trace = DreamSDKTrace(tmp_path)
    def broken(*args):
        raise OSError(SECRET)
    monkeypatch.setattr(trace.ik_diagnostics, '_save_replay', broken)
    try:
        trace.ik_diagnostics.install(sdk.ik)
        trace.ik_diagnostics.jobs.put_nowait((1, sdk.args, {}))
        trace.ik_diagnostics.jobs.join()
        with trace.prediction():
            assert sdk.ik._solver.solve_traj(sdk.args) is sdk.args[3]
        assert trace.ik_diagnostics.replay_errors == 1
        assert len([x for x in sdk.calls if isinstance(x, tuple)]) == 1
        assert SECRET not in json.dumps(records(trace))
    finally:
        trace.close()


def test_os_probe_failures_do_not_change_predictions_or_run_on_prediction_thread(tmp_path, monkeypatch):
    sdk = fake_sdk(monkeypatch)
    trace = DreamSDKTrace(tmp_path, interval_s=100)
    owner = threading.get_ident()
    called = []
    def blocked(*args, **kwargs):
        called.append(threading.get_ident())
        raise OSError(SECRET)
    monkeypatch.setattr(trace.ik_diagnostics, '_text', blocked)
    try:
        trace.ik_diagnostics.install(sdk.ik)
        with trace.prediction():
            assert sdk.ik._solver.solve_traj(sdk.args) is sdk.args[3]
        assert called == []
        values = []
        thread = threading.Thread(target=lambda: values.append(trace.ik_diagnostics.sample(None)))
        thread.start(); thread.join(1)
        assert values and called and owner not in called
        assert SECRET not in json.dumps(values)
    finally:
        trace.close()


def test_non_prediction_setup_is_not_traced_and_replaced_hooks_are_preserved(tmp_path, monkeypatch):
    sdk = fake_sdk(monkeypatch)
    trace = DreamSDKTrace(tmp_path)
    trace.ik_diagnostics.install(sdk.ik)
    assert sdk.ik._solver.solve_traj(sdk.args) is sdk.args[3]
    assert not trace.path.exists()
    replacement = lambda *args: sdk.token
    sdk.module._solve_traj = replacement
    trace.close()
    assert sdk.module._solve_traj is replacement


def test_resource_reading_parses_only_fixed_numeric_fields(tmp_path, monkeypatch):
    trace = DreamSDKTrace(tmp_path)
    data = {
        '/proc/self/status': 'Name: '+SECRET+'\nVmRSS: 2048 kB\n',
        '/proc/meminfo': 'MemAvailable: 4096 kB\n',
        '/proc/stat': 'cpu 10 0 10 70 0 0 0 10\n',
        '/proc/pressure/cpu': 'some avg10=1.5 avg60=0.0 avg300=0.0 total=100\n',
        '/proc/pressure/memory': 'some avg10=2.5 avg60=0.0 avg300=0.0 total=100\n',
        '/proc/self/cgroup': '0::/system.slice/yam-web.service\n',
        '/sys/fs/cgroup/system.slice/yam-web.service/cpu.stat': 'nr_throttled 2\nthrottled_usec 123\n'}
    monkeypatch.setattr(trace.ik_diagnostics, '_text', lambda p, *args: data[p])
    try:
        a = trace.ik_diagnostics.sample(None)
        data['/proc/stat'] = 'cpu 20 0 20 140 0 0 0 20\n'
        b = trace.ik_diagnostics.sample(None)
        assert a['process_rss_mb'] == 2 and a['memory_available_mb'] == 4
        assert b['system_busy_ratio'] == pytest.approx(.3)
        assert b['system_steal_ratio'] == pytest.approx(.1)
        assert b['cpu_pressure_avg10'] == 1.5 and b['memory_pressure_avg10'] == 2.5
        assert b['cgroup_throttled_us'] == 123
        assert SECRET not in json.dumps(b)
        data['/sys/fs/cgroup/system.slice/yam-web.service/cpu.stat'] = 'usage_usec 10\n'
        assert 'cgroup_throttled_us' not in trace.ik_diagnostics.sample(None)
        data['/proc/self/cgroup'] = '0::/../'+SECRET+'\n'
        assert 'cgroup_throttled_us' not in trace.ik_diagnostics.sample(None)
    finally:
        trace.close()
