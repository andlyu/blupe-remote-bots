"""Controller-owned model registrations, reusing the ordinary runner adapters.

Configuration is installed by the station administrator. Run requests carry a
registration ID, never URLs, credentials, commands or Python import paths.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import threading
from urllib.parse import urlsplit

ROBOTS = {'yam-1', 'robot-ba8413962083809c'}
ADAPTERS = {'dream', 'dream_flash', 'codex', 'claude', 'openai', 'anthropic',
            'gemini', 'groot', 'molmoact2', 'responses'}
PUBLIC_FIELDS = ('provider', 'model', 'label', 'available', 'reason', 'custom', 'user_endpoint')


def registration_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', value):
        raise ValueError('Invalid controller model registration')
    return value


def public_models(rows):
    """Allowlist prevents private station settings entering status or the UI."""
    result = {}
    for name, spec in rows.items():
        registration_id(name)
        if not isinstance(spec, dict) or not all(isinstance(spec.get(k), str)
                and 0 < len(spec[k]) <= 128 for k in ('provider', 'model', 'label')):
            raise ValueError('Invalid controller model descriptor')
        if type(spec.get('available')) is not bool:
            raise ValueError('Controller model availability must be explicit')
        result[name] = {k: deepcopy(spec[k]) for k in PUBLIC_FIELDS if k in spec}
        if 'reason' in spec and (not isinstance(spec['reason'], str) or len(spec['reason']) > 240):
            raise ValueError('Invalid controller model availability reason')
        if any(type(spec[k]) is not bool for k in ('custom', 'user_endpoint') if k in spec):
            raise ValueError('Invalid custom endpoint descriptor')
    return result


def load_public_models(path, robot_id):
    if not path:
        return {}
    config = json.loads(Path(path).read_text())
    if config.get('schema') != 'blupe-controller-model-catalog-v1':
        raise ValueError('Unsupported controller model catalog')
    return public_models(config.get('robots', {}).get(robot_id, {}))


def private_file(path):
    p = Path(path).expanduser()
    stat = p.stat()
    if not p.is_absolute() or not p.is_file() or stat.st_mode & 0o077 or stat.st_uid not in (0, os.getuid()):
        raise ValueError('Controller configuration and credentials must be private local files')
    return p


def endpoint(value):
    p = urlsplit(value)
    if (p.scheme != 'https' or not p.hostname or p.username or p.password
            or p.query or p.fragment):
        raise ValueError('Registered inference endpoints require HTTPS without credentials')
    return value


class ControllerModels:
    """One runtime in the native operator; a separate adapter per leased run."""
    def __init__(self, config, *, robot_id, camera_origin='http://127.0.0.1:8089', directory):
        if config.get('schema') != 'blupe-controller-models-v1' or config.get('robot_id') != robot_id or robot_id not in ROBOTS:
            raise ValueError('Controller model configuration identity mismatch')
        self.robot_id, self.camera_origin = robot_id, camera_origin
        self.directory = Path(directory)
        self.rows = deepcopy(config['models'])
        self.catalog = public_models(self.rows)
        self.dream_pool = None
        for spec in self.rows.values():
            if not spec['available']:
                continue
            kind = spec.get('adapter')
            if kind not in ADAPTERS:
                raise ValueError('Unsupported registered controller adapter')
            if kind in {'groot', 'molmoact2'} and robot_id != 'yam-1':
                raise ValueError('The configured joint checkpoint requires the YAM1 embodiment')
            if spec.get('endpoint'):
                endpoint(spec['endpoint'])
            if kind == 'responses' and not spec.get('custom'):
                raise ValueError('Responses endpoint registrations must be marked custom')
            if kind not in {'codex', 'claude'} and not spec.get('user_endpoint'):
                private_file(spec['credentials_file'])
        dream = [s for s in self.rows.values() if s['available'] and s['adapter'] in {'dream', 'dream_flash'}]
        if dream:
            from .dream_worker_pool import DreamWorkerPool
            spec = dream[0]
            if any((s['credentials_file'], s['python']) != (spec['credentials_file'], spec['python']) for s in dream):
                raise ValueError('Dream registrations must share one prepared controller SDK')
            self.dream_pool = DreamWorkerPool(spec['python'], spec['credentials_file'], self.directory / 'dream-sdk')

    @classmethod
    def load(cls, path, **kwargs):
        return cls(json.loads(private_file(path).read_text()), **kwargs)

    def prime(self):
        # Keep SDK compilation off startup for unrelated adapters. No provider
        # request, GPU wakeup or motor access occurs during this preparation.
        if self.dream_pool:
            def prepare():
                try:
                    self.dream_pool.prime()
                except Exception:
                    pass  # Bounded pool status exposes preparation failure.
            threading.Thread(target=prepare, daemon=True, name='controller-model-sdk').start()

    def status(self):
        return dict(ready=True, models=self.catalog,
                    **({'dream': self.dream_pool.status()} if self.dream_pool else {}))

    def select(self, model_id):
        spec = self.rows.get(registration_id(model_id))
        if not spec or not spec['available']:
            raise ValueError('Controller model is not provisioned on this robot')
        return spec

    def adapter(self, model_id, observation_source, custom_endpoint=None, custom_model=None):
        from .cameras import CameraFrameSource
        spec = deepcopy(self.select(model_id))
        if spec.get('user_endpoint'):
            from .model_catalog import model_id as validate_model
            spec['model'] = validate_model(custom_model)
        kind = spec['adapter']
        camera = CameraFrameSource(self.camera_origin)
        kwargs = dict(camera_source=camera)
        key = None if kind in {'codex', 'claude', 'dream', 'dream_flash'} or spec.get('user_endpoint') else private_file(spec['credentials_file']).read_text().strip()
        if kind in {'dream', 'dream_flash'}:
            from .dream_policy import DreamAdapter
            adapter = DreamAdapter(provider=kind, model=spec['model'],
                credentials=spec['credentials_file'], python=spec['python'],
                directory=self.directory / 'dream-sdk', robot_id=self.robot_id,
                observation_source=observation_source, worker_factory=self.dream_pool.factory,
                gateway_max_step_deg=spec.get('gateway_max_step_deg', 9), **kwargs)
        elif kind == 'molmoact2':
            from .yam_runpod_policy import YAMRunpodAdapter
            adapter = YAMRunpodAdapter(key, provider=kind, endpoint=spec['endpoint'], robot_id=self.robot_id, **kwargs)
        elif kind == 'groot':
            from .groot_policy import GrootAdapter
            adapter = GrootAdapter(key, model=spec['model'], endpoint=spec['endpoint'],
                norm_tag=spec['norm_tag'], artifact_sha256=spec['artifact_sha256'], **kwargs)
        elif kind in {'codex', 'claude'}:
            if kind == 'codex':
                from .codex_policy import CodexAdapter
                adapter = CodexAdapter(spec['model'], **kwargs)
            else:
                from .claude_policy import ClaudeAdapter
                adapter = ClaudeAdapter(spec['model'], **kwargs)
        elif kind == 'gemini':
            from .gemini_policy import GeminiAdapter
            adapter = GeminiAdapter(key, spec['model'], **kwargs)
        elif kind == 'anthropic':
            from .anthropic_policy import AnthropicAdapter
            adapter = AnthropicAdapter(key, spec['model'], **kwargs)
        elif kind == 'responses' and spec.get('user_endpoint'):
            from .controller_custom import CustomResponsesAdapter
            adapter = CustomResponsesAdapter(spec['model'], custom_endpoint, **kwargs)
        else:
            from .robocurve_policy import OpenAIAdapter, AstraAdapter
            adapter = (AstraAdapter(key, spec['model'], spec['endpoint'], **kwargs) if kind == 'responses'
                       else OpenAIAdapter(key, spec['model'], **kwargs))
        if adapter.model != spec['model']:
            raise ValueError('Registered controller checkpoint differs from the adapter')
        workspace = getattr(adapter, 'configure_robot_workspace', None)
        if callable(workspace):
            workspace(self.robot_id)
        if hasattr(adapter, 'refresh_observation'):
            adapter.refresh_observation = observation_source
        return adapter

    def native(self, operator, model_id, *, dispatch, cameras=None, custom_endpoint=None, custom_model=None):
        from .controller_dream import NativeControllerDream
        return NativeControllerDream(operator, robot_id=self.robot_id,
            credentials='', python='', directory=str(self.directory),
            camera_origin=self.camera_origin, cameras=cameras, dispatch=dispatch,
            adapter_factory=lambda **kw: self.adapter(model_id, kw['observation_source'], custom_endpoint, custom_model))

    def factory(self, *args, **kwargs):
        raise RuntimeError('Select a registered controller adapter')

    def close(self):
        if self.dream_pool:
            self.dream_pool.close()
