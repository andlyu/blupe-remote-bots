"""Locally configured, one-shot executables using the runner's Run/status/Stop.

Commands come from an operator-owned startup file, never an HTTP payload.
The executable retains robot ownership, native checks and cancellation duties.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import threading
import uuid

from .runner_failures import failure_from_error


def load_policies(path, robot_id):
    if not path:
        return {}
    config = json.loads(Path(path).read_text())
    if config.get('schema') != 'blupe-managed-policies-v1':
        raise ValueError('Unsupported managed policy configuration')
    policies = {}
    for key, raw in config.get('policies', {}).items():
        if raw.get('robot_id') != robot_id:
            continue
        spec = deepcopy(raw)
        if spec.get('execution') not in (None, 'session_cube'):
            raise ValueError('Unknown configured policy execution mode')
        if spec.get('execution') == 'session_cube' and (
                not isinstance(spec.get('session_config'), str)
                or not Path(spec['session_config']).is_absolute()):
            raise ValueError('Session reset requires an absolute station configuration')
        command = spec.get('command')
        if (not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command)
                or not Path(command[0]).is_absolute() or '{output}' not in command
                or '{request_id}' not in command or not spec.get('model') or not spec.get('label')):
            raise ValueError('Managed policy requires an absolute command, output and request identity')
        policies[key] = spec
    return policies


class ManagedCommandPolicy:
    def __init__(self, name, spec, directory):
        self.provider_name, self.spec = name, deepcopy(spec)
        self.model = spec['model']
        self.request_id = uuid.uuid4().hex
        self.directory = Path(spec.get('recording_root') or directory)/('managed-'+self.request_id)
        self.output = self.directory/'evidence'
        self.cancelled = lambda: False
        self.interaction_sink = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._process = None
        self._phase = 'preparing'
        self._result = None
        self._failure = None

    def public_config(self):
        progress = None
        try:
            progress = json.loads((self.output/'status.json').read_text())
            if not isinstance(progress, dict) or progress.get('request_id') != self.request_id:
                progress = None
        except (OSError, ValueError):
            pass
        return dict(provider=self.provider_name, model=self.model, display_name=self.spec['label'],
                    model_calls=0, recording_path=str(self.directory),
                    managed_execution=dict(request_id=self.request_id, phase=self._phase,
                                           progress=progress, result=deepcopy(self._result),
                                           failure=deepcopy(self._failure)))

    def _emit(self, message, **details):
        if callable(self.interaction_sink):
            try:
                self.interaction_sink('runner', message, **details)
            except Exception:
                pass  # Journaling must never detach a running executable.

    def request_stop(self):
        # Setting the latch and spawning share a lock. Stop before spawn cannot
        # be lost; Stop after spawn signals only this orchestrator, exactly once.
        with self._lock:
            if self._stop.is_set():
                return
            self._stop.set()
            if self._phase in ('preparing', 'running'):
                self._phase = 'cancelling'
            if self._process is not None and self._process.poll() is None:
                try:
                    self._process.send_signal(signal.SIGTERM)
                except ProcessLookupError:
                    pass

    close_transport = request_stop

    def run_managed(self, prompt):
        try:
            return self._execute(prompt)
        except Exception as exc:
            self._phase = 'failed'
            self._failure = failure_from_error(str(exc))
            raise

    def _execute(self, prompt):
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.output.exists():
            raise RuntimeError('This executable request already has evidence; do not retry it')
        for path, expected in self.spec.get('sha256', {}).items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
                raise RuntimeError('Configured policy source changed: '+path)
        if self.cancelled():
            self.request_stop()
        argv = [value.replace('{output}', str(self.output)).replace('{request_id}', self.request_id)
                for value in self.spec['command']]
        with (self.directory/'command.log').open('w') as stream:
            with self._lock:
                if self._stop.is_set():
                    self._phase = 'cancelled'
                    self._result = dict(state='cancelled', request_id=self.request_id, goals_reached=False)
                    return self._result
                self._process = subprocess.Popen(argv, stdout=stream, stderr=subprocess.STDOUT,
                                                 cwd=self.spec.get('cwd'))
                self._phase = 'running'
            self._emit(self.spec['label']+' started', request_id=self.request_id)
            while True:
                if self.cancelled():
                    self.request_stop()
                progress = self.public_config()['managed_execution']['progress'] or {}
                stage = progress.get('state') or progress.get('phase')
                if stage and stage != getattr(self, '_last_stage', None):
                    self._last_stage = stage
                    self._emit(self.spec['label']+': '+str(stage), progress=progress)
                try:
                    code = self._process.wait(timeout=.1)
                    break
                except subprocess.TimeoutExpired:
                    continue
        # Never kill/retry an uncertain command. Remain busy until the owning
        # executable exits, even if its cancellation takes time.
        # A completed program can return nonzero with measured goal errors in
        # result.json. Keep that outcome instead of replacing it with a generic
        # missing-failure-file error.
        path = self.output/'result.json'
        if not path.exists():
            path = self.output/'failure.json'
        try:
            result = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise RuntimeError('Executable exited without a terminal receipt; inspect command.log') from exc
        if result.get('request_id') != self.request_id:
            raise RuntimeError('Executable receipt does not match this request')
        self._result = result
        self._phase = 'cancelled' if self._stop.is_set() else 'complete' if code == 0 and result.get('goals_reached') is True else 'failed'
        if self._phase == 'failed':
            raise RuntimeError(result.get('error') or 'Reset goals were not reached; inspect terminal receipt')
        return result
