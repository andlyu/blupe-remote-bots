"""Passive boundaries for pinned SDK1.0.0/JAX0.7.1, never a different solve.

Source contract: dream_ik/solver.py solve_traj/_solve_traj and installed
jax/_src/compiler.py. Existing NumPy materialization immediately after the
trajectory kernel already waits for these arrays. No graph, weights, arguments
or returned objects are changed by the synchronization below.
"""
from functools import wraps
import hashlib
import math
import os
from pathlib import Path
import queue
import sys
import threading
import time

REPLAY_KEYS = frozenset({'pos', 'ori', 'limit', 'last_pose', 'collision', 'collision_margin',
    'vel', 'acc', 'hist', 'jerk', 'jerk0', 'interarm', 'margin', 'hand_margin',
    'capsule', 'box', 'region'})


class DreamIKDiagnostics:
    def __init__(self, trace, *, slow_s=5., replay_bytes=2 * 1024 * 1024):
        self.trace = trace
        self.slow_s = slow_s
        self.replay_bytes = replay_bytes
        self.patches = []
        self.kernel = None
        self.replay_reserved = False
        self.replay_errors = 0
        self.jobs = queue.Queue(maxsize=1)
        self.stopped = threading.Event()
        self.previous_cpu = None
        self.previous_cpu_at = None
        self.writer = threading.Thread(target=self._replay_writer, daemon=True,
                                       name='dream-ik-replay-writer')
        self.writer.start()

    def active(self):
        with self.trace.lock:
            item = self.trace.active
            return item is not None and item['thread'] == threading.get_ident()

    @staticmethod
    def _ready(value):
        # No new JAX operation or optimizer output: wait on existing arrays.
        if isinstance(value, (tuple, list)):
            for leaf in value:
                DreamIKDiagnostics._ready(leaf)
        else:
            ready = getattr(value, 'block_until_ready', None)
            if callable(ready):
                ready()

    def _patch(self, obj, name, stage, *, kernel=False, ready=False, cache=False):
        original = getattr(obj, name, None)
        if not callable(original) or getattr(original, '_dream_ik_diagnostic', False):
            return

        @wraps(original)
        def observed(*args, **kwargs):
            if not self.active():
                return original(*args, **kwargs)
            metadata = {}
            if kernel:
                try:
                    if kwargs or len(args) != 12:
                        raise ValueError()
                    metadata = dict(branch='independent' if args[10] is None else 'coupled',
                                    rows=int(args[3][0].shape[0]), arms=len(args[0]))
                except Exception:
                    self.trace._emit(stage, 'unsupported')
                    return original(*args, **kwargs)
            with self.trace.span(stage, **metadata) as completion:
                if kernel:
                    with self.trace.lock:
                        self.kernel = (self.trace.active, args, time.monotonic(), metadata)
                try:
                    result = original(*args, **kwargs)
                    if ready:
                        try:
                            self._ready(result)
                        except Exception:
                            # Preserve the original result. Its existing consumer
                            # remains responsible for any asynchronous error.
                            self.trace._emit(stage, 'unsupported')
                    if cache:
                        completion['cache_hit'] = int(result[0] is not None)
                    return result
                finally:
                    if kernel:
                        with self.trace.lock:
                            self.kernel = None

        observed._dream_ik_diagnostic = True
        setattr(obj, name, observed)
        self.patches.append((obj, name, original, observed))

    def install(self, client_ik):
        solver = getattr(client_ik, '_solver', None)
        if solver is None or getattr(solver, '_dream_ik_diagnostic', False):
            return
        module = sys.modules.get(type(solver).__module__)
        if module is None or module.__name__ != 'dream_ik.solver':
            return
        solver._dream_ik_diagnostic = True
        self._patch(solver, 'solve', 'ik_seed')
        self._patch(solver, 'solve_traj', 'ik_trajectory')
        self._patch(module, '_interarm_distance', 'ik_clearance', ready=True)
        self._patch(module, '_solve_traj', 'ik_kernel', kernel=True, ready=True)
        compiler = sys.modules.get('jax._src.compiler')
        if compiler is not None:
            self._patch(compiler, 'compile_or_get_cached', 'jax_compile_or_cache')
            self._patch(compiler, 'backend_compile_and_load', 'jax_compile')
            self._patch(compiler, '_cache_read', 'jax_cache_read', cache=True)

    @staticmethod
    def _text(path, limit=16384):
        with open(path, encoding='ascii') as stream:
            return stream.read(limit)

    def sample(self, active):
        """Only the existing five-second monitor calls filesystem/OS probes."""
        data = {}
        try:
            data['load_1m'] = os.getloadavg()[0]
        except (AttributeError, OSError):
            pass
        try:
            for line in self._text('/proc/self/status').splitlines():
                if line.startswith('VmRSS:'):
                    data['process_rss_mb'] = int(line.split()[1]) / 1024
            for line in self._text('/proc/meminfo').splitlines():
                if line.startswith('MemAvailable:'):
                    data['memory_available_mb'] = int(line.split()[1]) / 1024
            cpu = [int(x) for x in self._text('/proc/stat').splitlines()[0].split()[1:9]]
            sampled_at = time.monotonic()
            if self.previous_cpu is not None:
                delta = [a-b for a, b in zip(cpu, self.previous_cpu)]
                total = sum(delta)
                if total > 0:
                    data['system_busy_ratio'] = max(0., min(1., 1-(delta[3]+delta[4])/total))
                    data['system_steal_ratio'] = max(0., min(1., delta[7]/total))
                    data['resource_window_s'] = sampled_at-self.previous_cpu_at
            self.previous_cpu = cpu
            self.previous_cpu_at = sampled_at
        except (OSError, ValueError, IndexError):
            pass
        for name in ('cpu', 'memory'):
            try:
                line = next(x for x in self._text('/proc/pressure/'+name, 1024).splitlines()
                            if x.startswith('some '))
                data[name+'_pressure_avg10'] = float(dict(x.split('=') for x in line.split()[1:])['avg10'])
            except (OSError, ValueError, KeyError, StopIteration):
                pass
        try:
            values = dict(x.split() for x in self._text('/sys/fs/cgroup/cpu.stat', 1024).splitlines())
            data['cgroup_throttled_us'] = int(values.get('throttled_usec', '0'))
        except (OSError, ValueError):
            pass
        with self.trace.lock:
            kernel = self.kernel
            if (not self.replay_reserved and kernel is not None and kernel[0] is active
                    and time.monotonic()-kernel[2] >= self.slow_s):
                # One case per worker lifetime; no growing ring of visitor data.
                self.replay_reserved = True
                try:
                    self.jobs.put_nowait((active['prediction'], kernel[1], dict(kernel[3])))
                except queue.Full:
                    self.replay_errors += 1
        data['replay_errors'] = self.replay_errors
        return data

    def _save_replay(self, prediction, args, metadata):
        import json
        import numpy as np
        fields = ('obstacles', 'weights', 'targets', 'init', 'last', 'before',
                  'before2', 'lo', 'hi', 'base', 'trajectory_weights')
        values = (args[1], *args[2:])
        arrays, structure, weak_types = {}, {}, {}
        total = 0

        def copy_numeric(value):
            nonlocal total
            if value is None:
                return None
            if isinstance(value, (tuple, list)):
                return [copy_numeric(x) for x in value]
            if isinstance(value, dict):
                # Only fixed SDK numeric field names, never arbitrary text.
                if any(k not in REPLAY_KEYS for k in value):
                    raise ValueError('Unsupported replay field')
                return {k: copy_numeric(v) for k, v in value.items()}
            dtype = np.dtype(value.dtype) if hasattr(value, 'dtype') else np.asarray(value).dtype
            shape = tuple(value.shape) if hasattr(value, 'shape') else np.asarray(value).shape
            size = math.prod(shape) * dtype.itemsize
            total += size
            if dtype.kind not in 'biuf' or total > self.replay_bytes:
                raise ValueError('Unsupported replay size/type')
            key = 'array_'+str(len(arrays))
            arrays[key] = np.asarray(value).copy()
            weak_types[key] = bool(getattr(value, 'weak_type', False))
            if len(arrays) > 128:
                raise ValueError('Too many replay arrays')
            return key

        for key, value in zip(fields, values):
            structure[key] = copy_numeric(value)
        root = self.trace.path.parent
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        data_path, meta_path = root/'ik-replay.npz', root/'ik-replay.json'
        if data_path.exists() or meta_path.exists():
            return
        # No pickle, prompts, images, credentials, names or source archives.
        # Reconstruct static arm geometry from the exact pinned SDK/hash.
        fd = os.open(data_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            np.savez(stream, **arrays)
        if data_path.stat().st_size > self.replay_bytes:
            data_path.unlink()
            raise ValueError('Replay archive exceeds size limit')
        hashes = {}
        for name in ('dream_ik.solver', 'dream_ik.decode', 'dream_ik.specs',
                     'jaxls._problem', 'jaxls._solvers'):
            source = getattr(sys.modules.get(name), '__file__', None)
            if source:
                with open(source, 'rb') as stream:
                    hashes[name] = hashlib.sha256(stream.read(1024 * 1024)).hexdigest()
        meta = dict(schema=1, prediction=prediction, worker_pid=self.trace.worker_pid,
                    captured_at=time.time(), sdk='1.0.0', arm='yam', tool='tcp',
                    action_hz=20, **metadata, structure=structure, array_bytes=total,
                    array_count=len(arrays), source_hashes=hashes,
                    weak_types=weak_types,
                    jax_enable_x64=bool(getattr(getattr(sys.modules.get('jax'), 'config', None),
                                               'jax_enable_x64', False)),
                    jax=getattr(sys.modules.get('jax'), '__version__', None))
        fd = os.open(meta_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(meta, stream, allow_nan=False)
        self.trace._emit('ik_replay', 'completed', prediction=prediction,
                         array_bytes=total, array_count=len(arrays))

    def _replay_writer(self):
        while not self.stopped.is_set() or not self.jobs.empty():
            try:
                job = self.jobs.get(timeout=.1)
            except queue.Empty:
                continue
            try:
                self._save_replay(*job)
            except Exception:
                self.replay_errors += 1
                self.trace._emit('ik_replay', 'error', prediction=job[0], replay_errors=self.replay_errors)
            finally:
                self.jobs.task_done()
                job = None  # Do not retain original visitor inputs while idle.

    def close(self):
        self.stopped.set()
        for obj, name, original, observed in reversed(self.patches):
            if getattr(obj, name, None) is observed:
                setattr(obj, name, original)
        self.writer.join(.1)
