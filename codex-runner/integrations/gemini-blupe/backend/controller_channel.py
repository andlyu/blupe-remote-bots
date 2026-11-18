"""Rootless stdio transport; generated code never executes in the API process."""
import json
import hashlib
import re
from simulation_artifacts import read_regular
import os
import selectors
import subprocess
import time

from executor import SimulationExecutor


class RootlessControllerChannel:
    def __init__(self, workspace, *, deadline_monotonic):
        self.executor = SimulationExecutor(workspace)
        self.deadline = deadline_monotonic
        self.process = None
        self.buffer = bytearray()
        self.stderr_tail = bytearray()
        self.selector = selectors.DefaultSelector()
        self.cleanup_confirmed = False
        self.cancelled = lambda:False
        self.closed = False
        self.expected_controller_sha256 = None

    def bind_controller(self, digest):
        if self.process is not None or self.closed:
            raise RuntimeError('An existing controller channel cannot be rebound')
        if not isinstance(digest,str) or re.fullmatch(r'[a-f0-9]{64}',digest) is None:
            raise ValueError('Expected an exact controller source hash')
        if self.expected_controller_sha256 not in (None,digest):
            raise RuntimeError('The controller channel is already source-bound')
        self.expected_controller_sha256=digest

    def start(self, cancelled=lambda:False):
        if self.closed or self.process is not None:
            raise RuntimeError('Generated controller channel cannot be restarted')
        self.cancelled = cancelled
        if self.expected_controller_sha256 is not None:
            code=read_regular(self.executor.workspace/'controller.py',160000)
            if hashlib.sha256(code).hexdigest()!=self.expected_controller_sha256:
                raise RuntimeError('Staged controller changed before launch; no queue or process started')
        command = self.executor.command()
        command = command[:-1] + ['--interactive', '--entrypoint=python', command[-1],
                                  '/workspace/controller-runtime/controller_entry.py']
        # Host podman needs its user storage/runtime locations. No model key,
        # site token or queue capability is passed to this child process.
        env = {key:os.environ[key] for key in ('PATH','HOME','USER','LOGNAME','XDG_RUNTIME_DIR','TMPDIR','LANG') if key in os.environ}
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, env=env, bufsize=0)
        for file in (self.process.stdout, self.process.stderr):
            os.set_blocking(file.fileno(), False)
            self.selector.register(file, selectors.EVENT_READ)
        try:
            ready = json.loads(self.receive(cancelled))
            if ready != {'kind':'ready', 'protocol':1}:
                raise RuntimeError('Generated controller did not confirm the pinned runtime protocol')
        except BaseException:
            self.close()
            raise

    def receive(self, cancelled):
        self.cancelled = cancelled
        while True:
            if cancelled() or time.monotonic() >= self.deadline:
                self.close()
                raise RuntimeError('Controller channel cancelled or expired; no command replayed')
            if b'\n' in self.buffer:
                line, _, rest = self.buffer.partition(b'\n'); self.buffer[:] = rest
                if len(line) > 16000:
                    self.close(); raise RuntimeError('Controller JSON line exceeded its packet bound')
                return line.decode('utf-8')
            if len(self.buffer) > 16000:
                self.close(); raise RuntimeError('Controller JSON line exceeded its packet bound')
            if self.process is None:
                raise RuntimeError('Controller process exited without a matching completion')
            events = self.selector.select(.05)
            for key, _ in events:
                chunk = os.read(key.fileobj.fileno(), 8192)
                if not chunk:
                    self.selector.unregister(key.fileobj)
                    continue
                if key.fileobj is self.process.stdout:
                    self.buffer.extend(chunk)
                else:
                    self.stderr_tail.extend(chunk)
                    if len(self.stderr_tail) > 32000: del self.stderr_tail[:-32000]
            # A short controller may exit immediately after writing complete.
            # Drain its pipe before classifying exit as a missing completion.
            if not events and self.process.poll() is not None and b'\n' not in self.buffer:
                raise RuntimeError('Controller process exited without a matching completion')

    def send(self, value):
        if self.closed or self.cancelled() or self.process is None or self.process.poll() is not None or time.monotonic() >= self.deadline:
            raise RuntimeError('Controller process unavailable; no command replayed')
        raw = json.dumps(value, allow_nan=False, separators=(',', ':')).encode() + b'\n'
        if len(raw) > 8*1024*1024:
            raise RuntimeError('Controller observation exceeded its transport bound')
        # Nonblocking bounded writes keep Stop/deadline responsive when generated
        # code stops consuming observations. The host caller also closes on Stop.
        fd = self.process.stdin.fileno(); os.set_blocking(fd, False)
        sent = 0
        while sent < len(raw):
            if self.cancelled() or self.process.poll() is not None or time.monotonic() >= self.deadline:
                self.close(); raise RuntimeError('Controller input expired; no command replayed')
            try: sent += os.write(fd, raw[sent:sent+65536])
            except BlockingIOError: time.sleep(.01)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.process is None:
            self.cleanup_confirmed = True
            self.selector.close()
            return
        # Removing this named container cannot target another job. It is never
        # restarted after timeout or an unknown execution outcome.
        try:
            subprocess.run([self.executor.engine, 'rm', '--force', '--time=1', self.executor.container],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        finally:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait(timeout=5)
            for file in (self.process.stdin, self.process.stdout, self.process.stderr):
                file.close()
            self.selector.close()
        exists = subprocess.run([self.executor.engine, 'container', 'exists', self.executor.container],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        self.cleanup_confirmed = exists.returncode == 1
        if not self.cleanup_confirmed:
            raise RuntimeError('Controller container removal is unverified')
