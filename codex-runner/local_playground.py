"""The shared playground UI and queue backend, served on localhost with Codex."""
import asyncio
import os
import re
import threading
from urllib import request, error
from urllib.parse import urlsplit

from playground import HostedRunner, RequestError

PLAYGROUND = 'https://playground.blupe.io'
PUBLIC_SESSION_API = 'https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com'


from remote_yam.policy_defaults import default_run_duration


class LocalPlayground(HostedRunner):
    """Bridge the public viewer routes normally supplied by remote Caddy."""

    def __init__(self, *, visitor_chat_origin=None, **kwargs):
        super().__init__(**kwargs)
        from remote_yam.managed_command_policy import load_policies, ManagedCommandPolicy
        self.managed_policies = load_policies(os.environ.get('YAM_LOCAL_POLICY_CONFIG'), self.robot_id)
        self._managed_owner = None
        self._managed_launch_lock = threading.RLock()
        for name, spec in self.managed_policies.items():
            def factory(model, directory, name=name, spec=spec):
                if model != spec['model']:
                    raise RequestError(400, 'Unknown configured policy version')
                if spec.get('execution') == 'session_cube':
                    from remote_yam.resets.session_policy import CubeSessionPolicy
                    return CubeSessionPolicy(name, spec, directory)
                return ManagedCommandPolicy(name, spec, directory)
            self.extra_providers[name] = factory
        # Only the public-queue launchers join BluPe's public visitor room.
        # Simulations and custom robot backends keep their own chat scope.
        public_queue = (kwargs.get('session_api') or '').rstrip('/') == PUBLIC_SESSION_API
        self.visitor_chat_origin = visitor_chat_origin or (PLAYGROUND if public_queue else None)
        self.use_public_run_catalog = public_queue
        if (not self.api_depth_provider_factory and self.local_codex
                and self.hardware == 'yam' and kwargs.get('session_api')):
            self.api_depth_provider_factory = self.api_depth_provider(kwargs['session_api'])


    def launch(self,visitor,payload,**kwargs):
        with self._managed_launch_lock:
            if self._managed_owner is not None and self._managed_owner.controller.busy():
                raise RequestError(409, 'A configured policy is active. Wait for its completion or Stop acknowledgement.')
            managed = payload.get('provider') in self.managed_policies
            if managed:
                payload = dict(payload)
                payload.setdefault('run_duration_s', default_run_duration(self.managed_policies[payload['provider']]))
            for other in self.visitors.values():
                active = other.controller.busy()
                other_managed = callable(getattr(other.controller._provider, 'run_managed', None))
                if active and (managed or other_managed):
                    raise RequestError(409, 'A robot run is active. Wait for its completion or Stop acknowledgement.')
            result=super().launch(visitor,payload,**kwargs)
            if managed:self._managed_owner=visitor
            return result


    def public_chat(self, visitor):
        from remote_yam.visitor_chat import VisitorChat
        if visitor.visitor_chat is None:
            visitor.visitor_chat = VisitorChat(self.visitor_chat_origin, self.robot_id)
        return visitor.visitor_chat

    async def chat_setup(self, visitor):
        if not self.visitor_chat_origin:
            return await super().chat_setup(visitor)
        from remote_yam.visitor_chat import ChatUnavailable
        try:
            return await asyncio.to_thread(self.public_chat(visitor).setup)
        except ChatUnavailable:
            # A chat outage must not prevent local model setup or robot controls.
            return {'reaction_cursor':0, 'chat_scope':'public'}

    async def relay_chat(self, visitor, action, *args):
        from remote_yam.visitor_chat import ChatUnavailable
        try:
            return await asyncio.to_thread(getattr(self.public_chat(visitor), action), *args)
        except ChatUnavailable as exc:
            raise RequestError(exc.status, exc.message) from None

    async def chat_snapshot(self, visitor):
        if not self.visitor_chat_origin:
            return await super().chat_snapshot(visitor)
        return await self.relay_chat(visitor, 'snapshot')

    async def append_chat(self, visitor, name, text):
        if not self.visitor_chat_origin:
            return await super().append_chat(visitor, name, text)
        await self.relay_chat(visitor, 'publish', '/api/chat', {'name':name, 'text':text})

    async def publish_reaction(self, visitor, emoji):
        if not self.visitor_chat_origin:
            return await super().publish_reaction(visitor, emoji)
        return (await self.relay_chat(visitor, 'publish', '/api/reactions', {'emoji':emoji}))['reaction']

    def api_depth_provider(self, origin):
        def factory(name, key, model, directory):
            from remote_yam.codex_depth_policy import CodexDepthAdapter
            from remote_yam.depth_preflight import capture_before_queue
            provider = CodexDepthAdapter(origin, model or 'gpt-6-astra', all_depth_origin=origin,
                                         recording_root=directory)
            try:
                capture_before_queue(provider._camera_source.capture_preflight,
                    lambda: self.monitor_api.get_robot_observation('yam-1'),
                    cancelled=provider.cancelled)
                provider.set_depth_calibration(provider._camera_source.snapshots['top'].calibration)
            except Exception as exc:
                provider._workspace.cleanup()
                raise RequestError(503, str(exc)) from None
            return provider
        return factory


    async def session_extension(self, cookies, visitor):
        setup, headers = await super().session_extension(cookies, visitor)
        if self.managed_policies:
            setup = dict(setup, configured_providers={**setup.get('configured_providers', {}),
                **{name: {**{key: spec[key] for key in ('label','model','help','task') if key in spec},
                          'default_run_duration_s': default_run_duration(spec)}
                   for name, spec in self.managed_policies.items()}})
        return setup, headers

    async def http(self, scope, receive, send):
        path, method = scope['path'], scope['method']
        streams = [getattr(app, 'video_stream', None) for app in getattr(self, '_fleet_apps', {'self': self}).values()]
        prefixes = tuple('/' + stream['path'] + '/' for stream in streams if stream)
        media = path.startswith(('/synchronized/', '/live-video/')) or bool(prefixes and path.startswith(prefixes))
        # A public-queue local launch reads the same catalog, coordinates and
        # label provenance as the hosted viewer. Custom backends keep their own
        # local index; UI assets and assessment writes remain local in both.
        public_history = path == '/api/past-runs' or (self.use_public_run_catalog and
            path in {'/api/run-catalog', '/api/run-labels'})
        quick_replay = bool(re.fullmatch(r'/api/quick-replays/ep_[A-Za-z0-9_-]{1,100}/[0-9a-f]{64}\.mp4', path))
        if not media and not public_history and not quick_replay:
            return await super().http(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope.get('headers', [])}
        if headers.get('host') != self.authority:
            raise RequestError(421, 'Unrecognized website host')
        if '..' in path or '%' in path or '\\' in path or method not in ('GET', 'OPTIONS', 'POST', 'PATCH', 'DELETE'):
            raise RequestError(404, 'Unknown viewer route')
        if method != 'GET' and (public_history or quick_replay or '/whep' not in path or headers.get('origin') != self.origin):
            raise RequestError(403, 'Viewer request must come from this runner')
        body = bytearray()
        if method in ('POST', 'PATCH'):
            while True:
                part = await asyncio.wait_for(receive(), 5)
                if part['type'] == 'http.disconnect':
                    raise RequestError(400, 'Incomplete viewer request')
                body.extend(part.get('body', b''))
                if len(body) > 128_000:
                    raise RequestError(413, 'Viewer request too large')
                if not part.get('more_body'):
                    break
        query = scope.get('query_string', b'').decode('ascii')
        if public_history and path != '/api/run-labels':
            from urllib.parse import parse_qsl, urlencode
            query = urlencode([(k,v) for k,v in parse_qsl(query) if k != 'robot_id'] + [('robot_id', self.robot_id)])
        url = PLAYGROUND + path + ('?' + query if query else '')
        forwarded = {key: value for key, value in headers.items() if key in ('content-type', 'if-match')}
        if quick_replay and 'range' in headers:
            forwarded['Range'] = headers['range']
        forwarded['Origin'] = PLAYGROUND

        def fetch():
            req = request.Request(url, data=bytes(body) if method in ('POST', 'PATCH') else None,
                                  headers=forwarded, method=method)
            try:
                response = request.urlopen(req, timeout=15)
            except error.HTTPError as exc:
                response = exc
            with response:
                limit = 16 * 1024 * 1024 if quick_replay else 8_000_000
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise ValueError('Viewer response too large')
                extra = []
                for key in ('Location', 'ETag', 'Accept-Patch', 'Link', 'Accept-Ranges', 'Content-Range'):
                    value = response.headers.get(key)
                    if value:
                        if key == 'Location' and value.startswith(PLAYGROUND + '/'):
                            value = value[len(PLAYGROUND):]
                        extra.append((key.lower().encode(), value.encode()))
                return response.status, response.headers.get('Content-Type', 'application/octet-stream'), data, extra
        try:
            status, kind, data, extra = await asyncio.to_thread(fetch)
        except (OSError, ValueError):
            raise RequestError(503, 'Public viewer temporarily unavailable') from None
        await self.respond(send, status, data, kind, extra)

    async def start_response(self, send, status, content_type, size, extra=()):
        async def local_headers(message):
            if message['type'] == 'http.response.start':
                message['headers'] = [(k, v) for k, v in message['headers'] if k != b'content-security-policy']
                message['headers'].append((b'content-security-policy',
                    b"default-src 'none'; script-src 'self' https://www.googletagmanager.com; "
                    b"style-src 'self'; font-src 'self'; connect-src 'self' https://*.google-analytics.com https://*.analytics.google.com https://www.googletagmanager.com; "
                    b"img-src 'self' data: https://*.google-analytics.com https://www.googletagmanager.com; "
                    b"media-src 'self' blob: https://huggingface.co https://*.huggingface.co https://*.hf.co; "
                    b"frame-src https://lerobot-visualize-dataset.hf.space https://huggingface.co; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"))
            await send(message)
        await super().start_response(local_headers, status, content_type, size, extra)


def serve(args):
    import os
    import sys
    import webbrowser
    import uvicorn
    origin = f'http://127.0.0.1:{args.port}'
    import json
    from pathlib import Path
    from multi_robot import fleet
    groot_key_file = os.environ.get('YAM_GROOT_KEY_FILE')
    if groot_key_file is None:
        saved_key = Path.home() / '.config/runpod/api-key'
        groot_key_file = str(saved_key) if saved_key.is_file() else ''
    dream_credentials = os.environ.get('YAM_DREAM_CREDENTIALS')
    if dream_credentials is None:
        saved_dream = Path.home() / '.dreamlabs/credentials'
        dream_credentials = str(saved_dream) if saved_dream.is_file() else ''
    app = fleet(LocalPlayground, dict(public_origin=origin, session_api=args.session_api,
        camera_origin=args.camera_origin or args.session_api or 'http://127.0.0.1:8089',
        astra_endpoint=os.environ.get('ASTRA_ENDPOINT', ''),
        groot_key_file=groot_key_file,
        groot_config=json.loads(os.environ.get('YAM_GROOT_CONFIG', '{}')),
        dream_credentials_file=dream_credentials,
        dream_python=os.environ.get('YAM_DREAM_PYTHON', sys.executable),
        hardware_control=args.allow_hardware_control, development=True,
        local_codex=True, local_claude=True,
        share_conversation=not getattr(args, "no_share_conversation", False),
        default_provider='codex' if args.provider == 'auto' else args.provider),
        json.loads(os.environ['YAM_DASHBOARD_ROBOTS']) if os.environ.get('YAM_DASHBOARD_ROBOTS') else None)
    config = uvicorn.Config(app, host='127.0.0.1', port=args.port, access_log=False)
    # Reserve the port before opening a URL that could belong to an older runner.
    sock = config.bind_socket()
    try:
        print(f'Local playground: {origin}', flush=True)
        if not args.no_browser:
            webbrowser.open(origin)
        uvicorn.Server(config).run(sockets=[sock])
    finally:
        sock.close()
