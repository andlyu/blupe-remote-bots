"""Serve the local YAM playground with Gemini 4 Argon and a server-side API key."""
import argparse
import json
import os
from importlib.util import find_spec
from pathlib import Path
from urllib.parse import urlsplit

from local_playground import LocalPlayground
from playground import RequestError
from remote_yam.gemini_policy import DEFAULT_MODEL, GeminiAdapter

SESSION_API = 'https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com'


def load_api_key(env_file=None):
    """Read one dotenv value without executing shell code or exporting secrets."""
    key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if not key and env_file:
        for line in Path(env_file).expanduser().read_text().splitlines():
            name, sep, value = line.strip().removeprefix('export ').partition('=')
            if sep and name.strip() == 'GEMINI_API_KEY':
                key = value.strip()
                if len(key) >= 2 and key[0] == key[-1] and key[0] in {'"', "'"}:
                    key = key[1:-1]
                break
    if not key or not key.strip():
        raise ValueError('Set GEMINI_API_KEY or pass --env-file with GEMINI_API_KEY before launching')
    return key.strip()


class GeminiPlayground(LocalPlayground):
    def __init__(self, *, gemini_key, gemini_model=DEFAULT_MODEL, thinking_level='medium',
                 local_subscriptions=False, default_provider='gemini', preview=False, recording_root=None, **kwargs):
        origin = urlsplit(kwargs['public_origin'])
        if origin.scheme != 'http' or origin.hostname not in {'127.0.0.1', 'localhost'}:
            raise ValueError('Gemini Playground is restricted to localhost')
        if tuple(kwargs.get('joint_counts', (6, 6))) != (6, 6) or kwargs.get('hardware', 'yam') != 'yam':
            raise ValueError('This Gemini policy requires bimanual YAMs')
        self.preview = preview
        self.gemini_recording_root = Path(recording_root) if recording_root is not None else None
        self._gemini_key = gemini_key
        self.gemini_model, self.thinking_level = gemini_model, thinking_level
        if default_provider not in ({'gemini', 'codex', 'claude'} if local_subscriptions else {'gemini'}):
            raise ValueError('Enable local subscriptions to select Codex or Claude')
        super().__init__(**kwargs, default_provider=default_provider,
                         local_codex=local_subscriptions, local_claude=local_subscriptions)
        if self.preview:
            # Cookies are not port-scoped. Keep a second local preview from
            # replacing the session of another already-running local UI.
            self.cookie_name += '-gemini-preview-' + str(origin.port)
        self.extra_providers['gemini'] = self.gemini_provider

    async def session_extension(self, cookies, visitor):
        metadata, headers = await super().session_extension(cookies, visitor)
        return {**metadata, 'local_runner': True, 'default_provider': self.default_provider,
                'configured_providers': {'gemini': {
                    'label': 'Gemini 4 Argon' if self.gemini_model == DEFAULT_MODEL else self.gemini_model,
                    'model': self.gemini_model,
                    'help': ('Read-only local preview. Robot runs are disabled. ' if self.preview else '')
                            + 'Gemini retains completed calls at ages 1, 2, 3, 5, 7 and 10, with all their cameras. '
                            'Sparse native history is experimental: Google documents full thought replay. '
                            'The API key stays on this computer.'}}}, headers

    def page(self):
        # Scope Standard defaults to this launcher, including after a reload.
        return super().page().replace(
            b'<option value="fast" selected>Fast</option><option value="standard">Standard</option>',
            b'<option value="fast">Fast</option><option value="standard" selected>Standard</option>')

    def launch(self, visitor, payload, **kwargs):
        if self.preview:
            raise RequestError(403, 'Read-only Gemini preview: robot runs are disabled')
        if payload.get('provider') == 'gemini':
            mode = payload.get('gemini_calling_mode', 'sparse')
            if mode not in ('sparse', 'normal'):
                raise RequestError(400, 'Choose Sparse calling or Normal calling')
            transform = kwargs.pop('provider_transform', None)
            def configure(provider):
                provider.set_calling_mode(mode)
                return transform(provider) if transform else provider
            kwargs['provider_transform'] = configure
        return super().launch(visitor, {'response_speed': 'standard', **payload}, **kwargs)

    def gemini_provider(self, model, directory):
        if model not in ('', self.gemini_model):
            raise RequestError(400, 'Choose the configured Gemini model')
        return GeminiAdapter(self._gemini_key, self.gemini_model,
                             thinking_level=self.thinking_level,
                             camera_source=self.camera_source,
                             recording_root=(self.gemini_recording_root / self.robot_id
                                             if self.gemini_recording_root is not None else directory))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', default=SESSION_API)
    parser.add_argument('--camera-origin')
    parser.add_argument('--robot-id', choices=['yam-1', 'robot-ba8413962083809c'], default='yam-1')
    parser.add_argument('--model', default=DEFAULT_MODEL)
    parser.add_argument('--thinking-level', choices=['low', 'medium', 'high'], default='medium')
    parser.add_argument('--local-subscriptions', action='store_true',
                        help='Enable existing local ChatGPT/Codex and Claude subscription logins')
    parser.add_argument('--provider', choices=['gemini', 'codex', 'claude'], default='gemini')
    parser.add_argument('--env-file', help='Local dotenv file containing GEMINI_API_KEY')
    parser.add_argument('--port', type=int, default=8796)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--preview', action='store_true', help='Read-only local UI; no robot connection or runs')
    parser.add_argument('--recording-root', type=Path, default=Path(__file__).parent / 'recordings/gemini')
    args = parser.parse_args(argv)
    if args.provider != 'gemini' and not args.local_subscriptions:
        parser.error('--provider codex/claude requires --local-subscriptions')
    try:
        key = 'preview-no-inference' if args.preview else load_api_key(args.env_file)
        if not args.preview and find_spec('websocket') is None:
            raise RuntimeError('Install websocket-client from requirements.txt before launching')
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    from multi_robot import fleet
    import uvicorn
    import webbrowser
    origin = f'http://127.0.0.1:{args.port}'
    robots = [r for r in json.loads((Path(__file__).parent / 'config/robots.json').read_text())
              if r.get('hardware') == 'yam' and r.get('joint_counts') == [6, 6]]
    app = fleet(GeminiPlayground, dict(public_origin=origin, session_api=None if args.preview else args.api,
        camera_origin='http://127.0.0.1:1' if args.preview else args.camera_origin or args.api,
        development=True, hardware_control=not args.preview, preview=args.preview,
        share_conversation=False, recording_root=args.recording_root,
        gemini_key=key, gemini_model=args.model, thinking_level=args.thinking_level,
        local_subscriptions=args.local_subscriptions, default_provider=args.provider), robots)
    app.default = args.robot_id
    config = uvicorn.Config(app, host='127.0.0.1', port=args.port, access_log=False)
    sock = config.bind_socket()
    try:
        print(f'Local Gemini Playground: {origin} ({args.model}, {args.thinking_level} thinking)', flush=True)
        if not args.no_browser:
            webbrowser.open(origin)
        uvicorn.Server(config).run(sockets=[sock])
    finally:
        sock.close()


if __name__ == '__main__':
    main()
