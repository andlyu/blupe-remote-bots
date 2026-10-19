import json
from pathlib import Path
import stat
import threading
import time
from types import SimpleNamespace

import pytest

from remote_yam.dream_sdk_trace import DreamSDKTrace


SECRET = 'synthetic-private-marker-never-log'


def rows(trace):
    trace.queue.join()
    return [json.loads(line) for line in trace.path.read_text().splitlines()]


def fake_client(*, block=None, failure=None):
    calls = []

    class Connection:
        def connect(self):
            calls.append('connect')

        def request(self, *args, **kwargs):
            self.connect()
            calls.append('send')

        def getresponse(self):
            calls.append('headers')
            return SimpleNamespace(read=self.read)

        def read(self):
            calls.append('body')
            if block:
                block.wait(2)
            if failure:
                raise failure
            return SECRET

    class Transport:
        def _connect(self):
            return Connection()

        def request(self, *args, **kwargs):
            connection = self._connect()
            connection.request(*args, **kwargs)
            return connection.getresponse().read()

    ik = SimpleNamespace(observe=lambda value: value, solve=lambda value: value)
    return SimpleNamespace(_policy=SimpleNamespace(_transport=Transport(), _ik=ik,
        _smoother=SimpleNamespace(smooth=lambda value: value))), calls


def test_exact_values_order_and_exception_identity_are_preserved(tmp_path):
    trace = DreamSDKTrace(tmp_path)
    client, calls = fake_client()
    try:
        trace.install(client)
        trace.install(client)  # Resident reuse must not double-wrap.
        policy = client._policy
        with trace.prediction(72):
            assert policy._ik.observe(SECRET) == SECRET
            assert policy._transport.request(SECRET, key=SECRET) == SECRET
            assert policy._ik.solve(SECRET) == SECRET
            assert policy._smoother.smooth(SECRET) == SECRET
        data = rows(trace)
        assert calls == ['connect', 'send', 'headers', 'body']
        assert [x['stage'] for x in data if x['state'] == 'started'] == [
            'prediction', 'observation_fk', 'http_exchange', 'http_send',
            'http_connect', 'http_headers', 'http_body', 'ik_solve', 'smoothing']
        assert all(x['prediction'] == 1 for x in data)
        assert data[0]['first_step_id'] == 72
        assert SECRET not in trace.path.read_text()
        assert stat.S_IMODE(trace.path.stat().st_mode) == 0o600
        error = RuntimeError(SECRET)
        failed, failed_calls = fake_client(failure=error)
        trace.install(failed)
        with pytest.raises(RuntimeError) as raised, trace.prediction():
            failed._policy._transport.request(SECRET)
        assert raised.value is error
        assert failed_calls == ['connect', 'send', 'headers', 'body']
        assert [x['stage'] for x in rows(trace) if x['state'] == 'error'] == ['http_body', 'http_exchange', 'prediction']
        assert SECRET not in trace.path.read_text()
    finally:
        trace.close()


@pytest.mark.parametrize('stage', ['http_body', 'ik_solve'])
def test_blocked_stage_is_durable_before_prediction_returns(tmp_path, stage):
    trace = DreamSDKTrace(tmp_path, interval_s=.01)
    release = threading.Event()
    entered = threading.Event()
    try:
        def run():
            with trace.prediction(96):
                with trace.span(stage):
                    entered.set()
                    release.wait(2)
        thread = threading.Thread(target=run)
        thread.start()
        assert entered.wait(1)
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            if trace.path.exists() and any(x['state'] == 'waiting' for x in rows(trace)):
                break
            time.sleep(.01)
        data = rows(trace)
        assert thread.is_alive()
        waiting = [x for x in data if x['state'] == 'waiting']
        assert waiting and all(x['stage'] == stage for x in waiting)
        assert all(x['prediction'] == 1 and x['elapsed_s'] >= x['duration_s'] for x in waiting)
        assert not any(x['state'] == 'completed' for x in data)
    finally:
        release.set()
        thread.join(2)
        trace.close()


def test_stalled_sink_drops_diagnostics_without_blocking_inference(tmp_path):
    trace = DreamSDKTrace(tmp_path, interval_s=100)
    entered, release = threading.Event(), threading.Event()
    original = trace._write
    def blocked(row):
        entered.set()
        release.wait(2)
        original(row)
    trace._write = blocked
    try:
        with trace.prediction():
            assert entered.wait(1)
            began = time.monotonic()
            for _ in range(500):
                with trace.span('http_body'):
                    pass
            assert time.monotonic() - began < .2
        assert trace.dropped > 0 and trace.queue.qsize() <= 128
    finally:
        release.set()
        trace.queue.join()
        trace.close()


def test_rotation_and_failed_writer_are_bounded(tmp_path):
    trace = DreamSDKTrace(tmp_path, max_bytes=500)
    try:
        for _ in range(20):
            with trace.prediction():
                pass
            trace.queue.join()
        assert trace.path.stat().st_size <= 500
        assert trace.path.with_suffix('.jsonl.1').stat().st_size <= 500
        assert len(list(tmp_path.iterdir())) == 2
        def broken(row):
            raise OSError(SECRET)
        trace._write = broken
        with trace.prediction():
            pass
        trace.queue.join()
        assert trace.write_errors == 2
        assert SECRET not in ''.join(p.read_text() for p in tmp_path.iterdir())
    finally:
        trace.close()


def test_only_allowlisted_static_stack_frames_are_retained():
    namespace = dict(__name__='dream.client', trace=DreamSDKTrace, threading=threading, private=SECRET)
    exec(compile('def get_action():\n return trace._stack(threading.get_ident())', SECRET, 'exec'), namespace)
    result = namespace['get_action']()
    assert result == [dict(module='dream.client', function='get_action', line=2)]
    assert SECRET not in json.dumps(result)


def test_reset_is_not_recorded_and_missing_optional_hooks_do_not_block(tmp_path):
    trace = DreamSDKTrace(tmp_path)
    client, _ = fake_client()
    try:
        trace.install(client)
        assert client._policy._transport.request(SECRET) == SECRET
        trace.queue.join()
        assert not trace.path.exists()
        trace.install(SimpleNamespace(_policy=SimpleNamespace(_transport=object())))
        assert {x['state'] for x in rows(trace)} == {'unsupported'}
    finally:
        trace.close()
