"""Configured station policies executed here or by an explicit remote runner."""
import json
import os
from pathlib import Path
import threading

from .remote_runner_policy import RemoteRunnerPolicy
from .policy_defaults import default_run_duration


class ConfiguredPoliciesMixin:
    def __init__(self, **kwargs):
        from playground import RequestError
        path = os.environ.get('YAM_CONFIGURED_RUNNERS_FILE')
        settings = json.loads(Path(path).read_text()) if path else {}
        robot = kwargs.get('robot_id', 'yam-1')
        self.configured_policies = {key: spec for key, spec in settings.items() if spec.get('robot_id') == robot}
        self._configured_launch_lock = threading.RLock()
        providers = dict(kwargs.get('extra_providers', {}))
        for name, spec in self.configured_policies.items():
            default_run_duration(spec)
            execution = spec.get('execution', 'remote_runner')
            if execution not in ('remote_runner', 'session_cube'):
                raise ValueError('Unknown configured policy execution: ' + str(execution))
            def factory(model, directory, name=name, spec=spec):
                if model != spec['model']:
                    raise RequestError(400, 'Unknown configured policy version')
                if spec.get('execution') == 'session_cube':
                    from .resets.session_policy import CubeSessionPolicy
                    return CubeSessionPolicy(name, spec, directory)
                return RemoteRunnerPolicy(name, spec)
            providers[name] = factory
        kwargs['extra_providers'] = providers
        super().__init__(**kwargs)

    async def session_extension(self, cookies, visitor):
        setup, headers = await super().session_extension(cookies, visitor)
        setup = dict(setup, configured_providers={**setup.get('configured_providers', {}),
            **self.configured_public_config()})
        return setup, headers

    def configured_public_config(self):
        return {name: {**{key: spec[key] for key in ('label', 'model', 'task', 'help')},
                       'default_run_duration_s': default_run_duration(spec)}
                for name, spec in self.configured_policies.items()}

    def launch(self, visitor, payload, **kwargs):
        from playground import RequestError
        with self._configured_launch_lock:
            name = payload.get('provider')
            configured = isinstance(name, str) and name in self.configured_policies
            for other in self.visitors.values():
                if other.controller.busy() and (configured or callable(getattr(other.controller._provider, 'run_managed', None))):
                    raise RequestError(409, 'A robot run is active; wait for completion or Stop acknowledgement')
            if configured:
                spec = self.configured_policies[name]
                if payload.get('model') != spec['model']:
                    raise RequestError(400, 'Unknown configured policy version')
                payload = {**payload, 'prompt': spec['task'], 'api_key': ''}
                payload.setdefault('run_duration_s', default_run_duration(spec))
            return super().launch(visitor, payload, **kwargs)
