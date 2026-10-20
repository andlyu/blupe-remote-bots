"""Bounded, payload-free checkpoints for the pinned Dream SDK (see refs/dreamlabs).

All filesystem work runs on a daemon. Prediction threads enqueue fixed labels
and numbers only; slow diagnostics drop records instead of delaying inference.
"""
from contextlib import contextmanager
from functools import wraps
import json
import math
import os
from pathlib import Path
import queue
import sys
import threading
import time


STAGES = frozenset({'prediction', 'http_exchange', 'http_connect', 'http_send',
                    'http_headers', 'http_body', 'observation_fk', 'ik_solve', 'smoothing',
                    'ik_seed', 'ik_trajectory', 'ik_clearance', 'ik_kernel',
                    'jax_compile_or_cache', 'jax_compile', 'jax_cache_read', 'ik_replay'})
NUMBERS = frozenset({'duration_s', 'elapsed_s', 'first_step_id', 'cpu_s', 'rows', 'arms',
    'cache_hit', 'process_rss_mb', 'memory_available_mb', 'load_1m', 'system_busy_ratio',
    'system_steal_ratio', 'cpu_pressure_avg10', 'memory_pressure_avg10',
    'cgroup_throttled_us', 'resource_window_s', 'array_bytes', 'array_count', 'replay_errors'})
STACK = {
    'dream.facade': {'get_action'},
    'dream.client': {'get_action', '_post'},
    'dream.client_ik': {'observe', 'solve', '_fk'},
    'dream.transport': {'request', '_exchange', '_connect', 'decode', 'connect'},
    'http.client': {'request', '_send_request', 'endheaders', '_send_output', 'send',
                    'connect', 'getresponse', 'begin', '_read_status', '_read_headers',
                    'read', 'readinto', '_safe_read', '_read_chunked'},
    'socket': {'create_connection', 'getaddrinfo', 'readinto'},
    'ssl': {'read', 'write', 'send', 'sendall', 'recv', 'recv_into', 'do_handshake'},
}


class DreamSDKTrace:
    def __init__(self, directory, *, interval_s=5., max_bytes=2 * 1024 * 1024):
        self.path = Path(directory) / 'sdk-trace.jsonl'
        self.worker_pid = os.getpid()
        self.max_bytes = max_bytes
        self.interval_s = interval_s
        self.queue = queue.Queue(maxsize=128)
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.active = None
        self.sequence = 0
        self.dropped = 0
        self.write_errors = 0
        try:
            from .dream_ik_diagnostics import DreamIKDiagnostics
        except ImportError:
            from dream_ik_diagnostics import DreamIKDiagnostics
        self.ik_diagnostics = DreamIKDiagnostics(self)
        self.writer = threading.Thread(target=self._writer, name='dream-trace-writer', daemon=True)
        self.monitor = threading.Thread(target=self._monitor, name='dream-trace-monitor', daemon=True)
        self.writer.start()
        self.monitor.start()

    def _emit(self, stage, state, *, prediction=None, **numbers):
        if stage not in STAGES or state not in {'started', 'completed', 'error', 'waiting', 'unsupported'}:
            return
        row = dict(stage=stage, state=state, timestamp=time.time(), worker_pid=self.worker_pid,
                   dropped=self.dropped, write_errors=self.write_errors)
        if prediction is not None:
            row['prediction'] = prediction
        for key in NUMBERS:
            value = numbers.get(key)
            if type(value) in (float, int) and math.isfinite(value) and 0 <= value < 1e12:
                row[key] = value
        if numbers.get('branch') in {'independent', 'coupled'}:
            row['branch'] = numbers['branch']
        if 'stack' in numbers:
            row['stack'] = numbers['stack']
        try:
            self.queue.put_nowait(row)
        except queue.Full:
            self.dropped += 1

    @contextmanager
    def prediction(self, first_step_id=None):
        with self.lock:
            self.sequence += 1
            self.active = dict(prediction=self.sequence, thread=threading.get_ident(),
                               started=time.monotonic(), cpu_started=time.process_time(), spans=[])
        try:
            with self.span('prediction', first_step_id=first_step_id):
                yield
        finally:
            with self.lock:
                self.active = None

    @contextmanager
    def span(self, stage, **numbers):
        # Installed hooks also see reset/release. Only predictions are tracked.
        with self.lock:
            active = self.active
            enabled = active is not None and active['thread'] == threading.get_ident()
            started = time.monotonic()
            cpu_started = time.process_time()
            if enabled:
                active['spans'].append((stage, started, cpu_started, numbers))
        if not enabled:
            yield None
            return
        self._emit(stage, 'started', prediction=active['prediction'], **numbers)
        state = 'completed'
        try:
            yield numbers
        except BaseException:
            state = 'error'
            raise
        finally:
            self._emit(stage, state, prediction=active['prediction'], duration_s=time.monotonic() - started,
                       cpu_s=time.process_time()-cpu_started, **numbers)
            with self.lock:
                active['spans'].pop()

    def _wrap(self, obj, method, stage, after=None):
        original = getattr(obj, method, None)
        if not callable(original):
            self._emit(stage, 'unsupported')
            return

        @wraps(original)
        def tracked(*args, **kwargs):
            with self.span(stage):
                result = original(*args, **kwargs)
            if after is not None:
                after(result)
            return result
        setattr(obj, method, tracked)

    def _response(self, response):
        self._wrap(response, 'read', 'http_body')

    def _connection(self, connection):
        if getattr(connection, '_dream_sdk_traced', False):
            return
        connection._dream_sdk_traced = True
        self._wrap(connection, 'connect', 'http_connect')
        self._wrap(connection, 'request', 'http_send')
        self._wrap(connection, 'getresponse', 'http_headers', self._response)

    def install(self, client):
        """Observe existing methods; preserve their arguments, return and exceptions.

        SDK1.0.0 Transport._connect constructs the HTTP object; its connect is
        lazy inside request. Hooks therefore follow each newly created channel.
        """
        policy = getattr(client, '_policy', None)
        if policy is None or getattr(policy, '_dream_sdk_traced', False):
            return
        policy._dream_sdk_traced = True
        transport = getattr(policy, '_transport', None)
        if transport is not None:
            connect = getattr(transport, '_connect', None)
            if callable(connect):
                @wraps(connect)
                def connected(*args, **kwargs):
                    connection = connect(*args, **kwargs)
                    self._connection(connection)
                    return connection
                transport._connect = connected
            else:
                self._emit('http_connect', 'unsupported')
            self._wrap(transport, 'request', 'http_exchange')
        else:
            self._emit('http_exchange', 'unsupported')
        ik = getattr(policy, '_ik', None)
        if ik is not None:
            self._wrap(ik, 'observe', 'observation_fk')
            self._wrap(ik, 'solve', 'ik_solve')
            try:
                self.ik_diagnostics.install(ik)
            except Exception:
                self._emit('ik_kernel', 'unsupported')
        smoother = getattr(policy, '_smoother', None)
        if smoother is not None:
            self._wrap(smoother, 'smooth', 'smoothing')

    @staticmethod
    def _stack(thread):
        result = []
        frame = sys._current_frames().get(thread)
        try:
            while frame is not None:
                module, function = frame.f_globals.get('__name__'), frame.f_code.co_name
                if function in STACK.get(module, ()):
                    result.append(dict(module=module, function=function, line=frame.f_lineno))
                frame = frame.f_back
            return list(reversed(result[:8]))
        finally:
            del frame  # Never retain frames or their locals.

    def _monitor(self):
        while not self.stopped.wait(self.interval_s):
            with self.lock:
                active = self.active
                if active is None or not active['spans']:
                    continue
                span = active['spans'][-1]
                stage, started, cpu_started, metadata = span
                thread, since = active['thread'], active['started']
            stack = self._stack(thread)
            try:
                resources = self.ik_diagnostics.sample(active)
            except Exception:
                resources = {}
            with self.lock:
                if self.active is not active or not active['spans'] or active['spans'][-1] is not span:
                    continue
            self._emit(stage, 'waiting', prediction=active['prediction'],
                       duration_s=time.monotonic() - started, cpu_s=time.process_time()-cpu_started,
                       **metadata, **resources,
                       elapsed_s=time.monotonic() - since, stack=stack)

    def _write(self, row):
        data = (json.dumps(row, allow_nan=False, separators=(',', ':')) + '\n').encode()
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size + len(data) > self.max_bytes:
            self.path.replace(self.path.with_suffix('.jsonl.1'))
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, 'ab') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(data)

    def _writer(self):
        while not self.stopped.is_set() or not self.queue.empty():
            try:
                row = self.queue.get(timeout=.05)
            except queue.Empty:
                continue
            try:
                self._write(row)
            except Exception:
                self.write_errors += 1
            finally:
                self.queue.task_done()

    def close(self):
        self.stopped.set()
        self.ik_diagnostics.close()
        self.writer.join(.1)  # Best effort; shutdown never waits on a blocked sink.
