"""Hosted Run/status/Stop proxy to a configured runner over a private tunnel."""
from copy import deepcopy
import threading
import time

from .runner_policy_client import RunnerPolicyClient
from .runner_failures import failure_from_state


class RemoteRunnerPolicy:
    def __init__(self, name, spec, *, client_factory=RunnerPolicyClient):
        self.provider_name, self.model = name, spec['model']
        self.spec = deepcopy(spec)
        self.client = client_factory(spec['runner_origin'], spec['robot_id'],
            transport_origin=spec.get('transport_origin'), timeout=10)
        self.cancelled = lambda: False
        self.interaction_sink = None
        self._stop = threading.Event()
        self._phase, self._progress, self._result = 'preparing', None, None
        self._stop_sent = False
        self._failure = None

    def public_config(self):
        return dict(provider=self.provider_name, model=self.model, display_name=self.spec['label'],
            model_calls=0, managed_execution=dict(phase=self._phase,
                request_id=getattr(self, 'request_id', None), progress=deepcopy(self._progress),
                result=deepcopy(self._result), failure=deepcopy(self._failure)))

    def request_stop(self):
        self._stop.set()

    close_transport = request_stop

    def run_managed(self, prompt):
        if self.cancelled() or self._stop.is_set():
            self._phase = 'cancelled'
            return dict(state='cancelled', goals_reached=False)
        try:
            self.client.connect()
        except Exception:
            self._phase = 'failed'
            raise RuntimeError('Configured runner is unavailable; no reset was started') from None
        remote = (self.client.metadata or {}).get('configured_providers', {}).get(
            self.spec.get('remote_policy', self.provider_name), {})
        if remote.get('model') != self.model:
            self._phase = 'failed'
            raise RuntimeError('Configured runner policy version differs')
        if self.cancelled() or self._stop.is_set():
            self._phase = 'cancelled'
            return dict(state='cancelled', goals_reached=False)
        # Start is attempted once. Reconcile an ambiguous response using the
        # same visitor, never by repeating the write or creating another visitor.
        try:
            self.client.start(self.spec.get('remote_policy', self.provider_name),
                runner_name='Hosted ' + self.spec['label'], run_duration_s=600)
        except Exception:
            state = self._status()
            if not state.get('attempt_id'):
                self._phase = 'failed'
                raise RuntimeError('Reset start was not confirmed; it was not retried') from None
            self.client.attempt_id = state['attempt_id']
        self._phase = 'running'
        while True:
            state = self._status()
            execution = (state.get('provider') or {}).get('managed_execution') or {}
            self.request_id = execution.get('request_id')
            progress = execution.get('progress') or {}
            self._progress = {key: progress[key] for key in ('phase', 'state', 'color', 'goals_reached') if key in progress}
            if (self.cancelled() or self._stop.is_set()) and not self._stop_sent:
                self._phase = 'cancelling'
                try:
                    self.client.stop()
                    self._stop_sent = True
                except RuntimeError:
                    raise
                except Exception:
                    # Stop is idempotent. Retain ownership and retry cancellation
                    # while status remains tied to this same attempt.
                    self._phase = 'unconfirmed'
            if state.get('status') not in ('queued', 'preparing', 'running'):
                result = execution.get('result') or {}
                self._result = {key: deepcopy(result[key]) for key in
                    ('state', 'goals_reached', 'request_id') if key in result}
                self._phase = execution.get('phase', 'failed')
                if self._phase == 'complete' and result.get('goals_reached') is True:
                    return self._result
                if self._phase == 'cancelled':
                    return self._result
                self._failure = failure_from_state(state)
                raise RuntimeError(self._failure['message'] if self._failure else
                    'Reset did not reach its goals; terminal evidence is retained by the configured runner')
            time.sleep(.2)

    def _status(self):
        while True:
            try:
                return self.client.status()
            except RuntimeError:
                raise  # A different visitor attempt must never be controlled.
            except Exception:
                # Reads may be retried. Retain ownership while the physical
                # request's outcome is uncertain; never retry its start write.
                self._phase = 'unconfirmed'
                time.sleep(.5)
