"""One fully prepared SDK process with exclusive, reset-isolated visitor handles.

SDK 1.0.0's documented reset_episode ends its model session, clears the image
window and resets chunk blending while retaining IK. See docs/refs/dreamlabs.
No fork of a JAX process and no sharing of an active SDK episode is involved.
"""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from collections import deque
import logging
import os
from pathlib import Path
import threading
import time

from .dream_policy import DreamWorker, DreamWorkerUnavailable, MODELS

LOG = logging.getLogger(__name__)


class DreamWorkerPool:
    def __init__(self, python, credentials, directory, *, worker_factory=DreamWorker,
                 recovery_delays=(1., 10., 30.), recovery_window=600., prime_timeout=360.):
        self.python = str(python)
        self.credentials = str(Path(credentials).expanduser().resolve())
        self.directory = Path(directory)
        self.worker_factory = worker_factory
        self._condition = threading.Condition(threading.RLock())
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='dream-prepared')
        self._stop = threading.Event()
        self._worker = None
        self._owner = None
        self._ready = False
        self._priming = False
        self._credential_revision = None
        self._recovery_pending = False
        self._recovery_exhausted = False
        self._recovery_attempts = deque()
        self._recovery_failures = 0
        self._recovery_delays = tuple(recovery_delays)
        self._recovery_window = recovery_window
        self._prime_timeout = prime_timeout
        threading.Thread(target=self._maintain, daemon=True, name='dream-worker-recovery').start()

    def _credentials_revision(self):
        info = Path(self.credentials).stat()
        return info.st_ino, info.st_size, info.st_mtime_ns

    def status(self):
        with self._condition:
            if self._worker is not None and self._worker.process.poll() is not None:
                self._ready = False
                self._recovery_pending = not self._recovery_exhausted
            try:
                if self._credentials_revision() != self._credential_revision:
                    self._ready = False
                    self._recovery_pending = False
            except OSError:
                self._ready = False
                self._recovery_pending = False
            return dict(ready=self._ready and not self._stop.is_set(),
                        busy=self._owner is not None, preparing=self._priming,
                        recovery_attempts=len(self._recovery_attempts),
                        recovery_exhausted=self._recovery_exhausted)

    def prime(self, *, timeout=360):
        """Deployment calls this before advertising Dream; never from a visitor."""
        return self._prime(timeout=timeout)

    def _prime(self, *, timeout, owner=None, recovery=False):
        with self._condition:
            if self._stop.is_set() or self._owner is not owner or self._priming:
                raise RuntimeError('Dream prepared worker cannot be primed now')
            if self.status()['ready']:
                return
            if recovery:
                if self._credentials_revision() != self._credential_revision:
                    self._recovery_pending = False
                    raise RuntimeError('Dream credentials changed; preparation requires operator review')
                now = time.monotonic()
                while self._recovery_attempts and now-self._recovery_attempts[0] >= self._recovery_window:
                    self._recovery_attempts.popleft()
                if (len(self._recovery_attempts) >= len(self._recovery_delays) or
                        self._recovery_failures >= len(self._recovery_delays)):
                    self._recovery_pending = False
                    self._recovery_exhausted = True
                    LOG.warning('[dream-worker] recovery_limit_reached')
                    raise RuntimeError('Dream worker recovery limit reached')
                self._recovery_attempts.append(now)
                LOG.info('[dream-worker] recovery_started attempt=%d', len(self._recovery_attempts))
            else:
                self._recovery_attempts.clear()
                self._recovery_failures = 0
                self._recovery_exhausted = False
            self._priming = True
        try:
            self._discard()
            self._credential_revision = self._credentials_revision()
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            worker = self.worker_factory(self.python, self.credentials, self.directory)
            with self._condition:
                if self._stop.is_set():
                    worker.close()
                    raise RuntimeError('Dream preparation cancelled')
                self._worker = worker
            reply = worker.call('prime', checkpoints=[m[0] for m in MODELS.values()],
                                cancelled=self._stop.is_set, timeout=timeout)
            if not reply['ok'] or reply.get('result', {}).get('fully_ready') is not True:
                raise RuntimeError('Dream full preparation failed')
            if recovery:
                clean = worker.call('release', cancelled=self._stop.is_set, timeout=10)
                if not clean['ok']:
                    raise RuntimeError('Dream replacement episode cleanup failed')
            with self._condition:
                if self._stop.is_set():
                    raise RuntimeError('Dream preparation cancelled')
                self._ready = True
                self._recovery_pending = False
            if recovery:
                LOG.info('[dream-worker] recovery_ready')
            return reply
        except Exception:
            self._discard(recover=recovery)
            if recovery:
                with self._condition:
                    self._recovery_failures += 1
                LOG.warning('[dream-worker] recovery_failed')
            raise
        finally:
            with self._condition:
                self._priming = False
                self._condition.notify_all()

    def _maintain(self):
        """Prepare replacements only; never repeat an inference or acquire a robot."""
        while not self._stop.wait(.1):
            with self._condition:
                self.status()
                if (not self._recovery_pending or self._owner is not None or self._priming):
                    continue
                index = min(len(self._recovery_attempts), len(self._recovery_delays)-1)
                delay = self._recovery_delays[index] if self._recovery_delays else 0
            if self._stop.wait(delay):
                return
            with self._condition:
                if self._stop.is_set():
                    return
                if not self._recovery_pending or self._owner is not None or self._priming:
                    continue
                future = self._executor.submit(self._restore, None, None)
            try:
                future.result()
            except Exception:
                pass  # Readiness remains false; retries have a fixed budget.

    def _restore(self, owner, checkpoint):
        self._prime(timeout=self._prime_timeout, owner=owner, recovery=True)
        if owner is None or owner.closed.is_set() or self._stop.is_set():
            with self._condition:
                self._recovery_failures = 0
            return
        # Same exclusive owner, fresh SDK session and empty observation window.
        try:
            reply = self._worker.call('configure', checkpoint=checkpoint,
                                      cancelled=self._stop.is_set, timeout=10,
                                      **({'overlap': True} if os.environ.get('YAM_DREAM_OVERLAP_1HZ') == '1' else {}))
            if not reply['ok']:
                raise RuntimeError('Dream recovered worker configuration failed')
        except Exception:
            with self._condition:
                self._recovery_failures += 1
            self._discard(recover=True)
            raise RuntimeError('Dream recovered worker configuration failed')
        with self._condition:
            self._recovery_failures = 0

    def factory(self, python, credentials, directory):
        if (str(python) != self.python or
                str(Path(credentials).expanduser().resolve()) != self.credentials or
                self._credentials_revision() != self._credential_revision):
            raise ValueError('Prepared Dream credentials/interpreter differ')
        # Returning a handle never blocks while DreamAdapter holds its transport
        # lock. Ownership is acquired cancellably by its configure call.
        return _VisitorWorker(self)

    def _acquire(self, owner, cancelled, timeout):
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._owner is not None and self._owner is not owner:
                if owner.closed.is_set() or cancelled() or self._stop.is_set():
                    raise RuntimeError('Dream request cancelled')
                if time.monotonic() >= deadline:
                    raise RuntimeError('Dream prepared worker is busy')
                self._condition.wait(.05)
            if owner.closed.is_set() or cancelled() or self._stop.is_set():
                raise RuntimeError('Dream request cancelled')
            if not self._ready:
                raise RuntimeError('Dream prepared worker is unavailable')
            self._owner = owner

    def _invoke(self, owner, command, payload, timeout):
        with self._condition:
            if self._owner is not owner or self._worker is None or self._stop.is_set():
                raise RuntimeError('Dream visitor ownership ended')
            worker = self._worker
        try:
            # A stopped caller returns immediately, but this one serial task
            # drains its reply before release/reset or another visitor's call.
            reply = worker.call(command, cancelled=self._stop.is_set, timeout=timeout, **payload)
            if not reply['ok'] and command in {'configure', 'reset'}:
                self._discard(recover=True)
            return reply
        except Exception as error:
            reason = 'worker_timeout' if str(error) == 'Dream worker timed out' else 'worker_failure'
            self._discard(recover=True)
            LOG.warning('[dream-worker] worker_failed reason=%s', reason)
            raise DreamWorkerUnavailable('Dream prepared worker failed; recovery required', reason=reason) from None

    def _release(self, owner):
        def release():
            try:
                with self._condition:
                    if self._owner is not owner:
                        return
                    worker = self._worker
                if worker is not None and not self._stop.is_set():
                    reply = worker.call('release', cancelled=self._stop.is_set, timeout=10)
                    if not reply['ok']:
                        raise RuntimeError('Dream episode cleanup failed')
            except Exception:
                self._discard(recover=True)
            finally:
                with self._condition:
                    if self._owner is owner:
                        self._owner = None
                    self._condition.notify_all()
        with self._condition:
            if self._stop.is_set():
                return
            self._executor.submit(release)
            self._condition.notify_all()

    def _discard(self, *, recover=False):
        with self._condition:
            self._ready = False
            if recover and not self._stop.is_set():
                self._recovery_pending = True
            worker, self._worker = self._worker, None
            self._condition.notify_all()
        if worker is not None:
            worker.close()

    def close(self):
        self._stop.set()
        self._discard()
        with self._condition:
            self._owner = None
            self._condition.notify_all()
        self._executor.shutdown(wait=False, cancel_futures=True)


class _VisitorWorker:
    def __init__(self, pool):
        self.pool = pool
        self.closed = threading.Event()
        self._lock = threading.Lock()

    def call(self, command, *, cancelled=lambda: False, timeout=30, **payload):
        if command == 'configure':
            self.pool._acquire(self, cancelled, timeout)
        with self._lock:
            if self.closed.is_set() or cancelled():
                raise RuntimeError('Dream request cancelled')
            with self.pool._condition:
                if self.pool._owner is not self:
                    raise RuntimeError('Dream visitor is not configured')
                future = self.pool._executor.submit(self.pool._invoke, self, command, payload, timeout)
        return self._wait(future, cancelled)

    def recover(self, *, checkpoint, cancelled=lambda: False):
        with self._lock, self.pool._condition:
            if (self.closed.is_set() or cancelled() or self.pool._owner is not self
                    or self.pool._stop.is_set()):
                raise RuntimeError('Dream worker recovery cancelled')
            future = self.pool._executor.submit(self.pool._restore, self, checkpoint)
        return self._wait(future, cancelled)

    def _wait(self, future, cancelled):
        while True:
            if self.closed.is_set() or cancelled() or self.pool._stop.is_set():
                raise RuntimeError('Dream request cancelled')
            try:
                return future.result(timeout=.05)
            except FutureTimeout:
                if future.done():
                    # Distinguish a task's own TimeoutError from polling.
                    return future.result()

    def close(self):
        with self._lock:
            if self.closed.is_set():
                return
            self.closed.set()
            self.pool._release(self)
