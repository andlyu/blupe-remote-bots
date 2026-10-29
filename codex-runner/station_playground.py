"""Jetson station UI: loopback robot transport, local logs, subscription inference."""
from __future__ import annotations

import asyncio
import os
import secrets
from pathlib import Path
import re
from urllib.parse import urlsplit
import webbrowser

from playground import HostedRunner, RequestError
from station_credentials import DEFAULT_KEY_FILE, CredentialError, read_openai_key


def loopback_origin(value):
    parsed = urlsplit(value or "")
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
            or parsed.username or parsed.password or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment):
        raise ValueError("Station endpoints must be HTTP origins on 127.0.0.1")
    parsed.port  # Reject malformed ports before starting any service.
    return value.rstrip("/")


class StationPlayground(HostedRunner):
    def __init__(self, *, public_origin, session_api, camera_origin, recording_root,
                 operator_origin="http://127.0.0.1:8096", station_provider='codex', openai_key_file=None,
                 episode_roots=None, media_cache=None, native_renderer=None, **kwargs):
        self.operator_origin = loopback_origin(operator_origin)
        if station_provider not in {'codex','openai'}:
            raise ValueError('Station provider must be codex or openai')
        self.station_provider = station_provider
        self.openai_key_file = Path(openai_key_file or DEFAULT_KEY_FILE).expanduser()
        if station_provider == 'openai' and not kwargs.get('provider_factory'):
            kwargs['provider_factory'] = self.openai_provider
        super().__init__(public_origin=loopback_origin(public_origin),
            session_api=loopback_origin(session_api), camera_origin=loopback_origin(camera_origin),
            recording_root=recording_root, development=True, local_codex=station_provider=='codex',
            local_claude=False, default_provider=station_provider, share_conversation=False,
            operator_status_origin=self.operator_origin,
            **kwargs)
        self.video_stream = None
        if not (Path(__file__).parent/'config/task-cloud-projection-v1.json').is_file():
            raise ValueError('Station package is missing the shared frozen task projection')
        from remote_yam.native_history import NativePastRuns, render_replay
        from remote_yam.run_history import run_models
        if episode_roots is None:
            default_root = self.root / 'episodes'
            default_root.mkdir(mode=0o700, exist_ok=True)
            episode_roots = [default_root]
        self.past_runs = NativePastRuns(episode_roots, media_cache or self.root/'media-cache',
            robot_id=self.robot_id, model_reader=lambda:run_models(self.submission_log.path),
            renderer=native_renderer or render_replay)
        # Trusted local application identity survives browser/service restarts;
        # ownership is recorded only when a real run belongs to its controller.
        identity = self.root / '.station-user'
        if identity.is_symlink(): raise ValueError('Station identity must not be a link')
        try:
            descriptor = os.open(identity, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        except FileExistsError:
            if identity.stat().st_uid != os.getuid() or identity.stat().st_mode & 0o077:
                raise ValueError('Station identity must be private to its local user')
        else:
            with os.fdopen(descriptor,'w') as stream: stream.write(secrets.token_urlsafe(32))
        self._assessment_user = identity.read_text()
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}',self._assessment_user):
            raise ValueError('Invalid station identity')

    def assessment_user(self, visitor):
        return self._assessment_user

    async def session_extension(self, cookies, visitor):
        metadata = {'station_local': True, 'operator_origin': self.operator_origin,
                    'local_runner': True, 'station_provider': self.station_provider,
                    'default_provider': self.station_provider}
        if self.station_provider == 'openai':
            try:
                ready = bool(read_openai_key(self.openai_key_file))
            except (CredentialError, OSError):
                ready = False
            return {**metadata, 'station_provider_label':'Astra · OpenAI API',
                    'station_api_key_ready':ready, 'configured_providers':{'openai':{
                        'label':'Astra · OpenAI API', 'model':'gpt-6-astra',
                        'help':'Uses the API key saved privately on this Jetson. Run blupe-playground --set-api-key in a Jetson terminal to set it up.'}}}, []
        from remote_yam.subscription_setup import subscription_status
        setup = await asyncio.to_thread(subscription_status, 'codex')
        setup['setup_prompt'] = 'On the Jetson, run ~/.local/bin/blupe-playground --login and complete the ChatGPT browser sign-in. Then use Check again here.'
        return {**metadata, 'station_provider_label':'Codex subscription · Astra', "codex": setup}, []

    def openai_provider(self, name, ignored_key, model, directory):
        from remote_yam.robocurve_policy import OpenAIAdapter
        from remote_yam.cameras import NoRedirect
        from urllib import request
        key = read_openai_key(self.openai_key_file)
        if not key:
            raise RequestError(409, 'Save an API key on the Jetson with blupe-playground --set-api-key')
        provider = OpenAIAdapter(key, model or 'gpt-6-astra',
            camera_source=self.camera_source, recording_root=directory)
        provider._urlopen = request.build_opener(NoRedirect).open
        return provider

    def launch(self, visitor, payload, paid=False, **kwargs):
        if self.station_provider == 'openai':
            if payload.get('api_key'):
                raise RequestError(400, 'Enter API keys only in the private Jetson terminal')
            self.validate_launch(visitor, payload, paid)
            try:
                ready = bool(read_openai_key(self.openai_key_file))
            except (CredentialError, OSError):
                ready = False
            if not ready:
                raise RequestError(409, 'Save an API key on the Jetson with blupe-playground --set-api-key')
            # The actual key is read only by the provider factory. It never
            # enters browser payloads, saved visitor keys or submission journals.
            payload = {**payload, 'api_key':'station-backend-managed'}
        try:
            return super().launch(visitor, payload, paid=paid, **kwargs)
        except RequestError as error:
            if error.setup is not None:
                error.setup = {**error.setup, 'setup_prompt':
                    'On the Jetson, run ~/.local/bin/blupe-playground --login and complete the ChatGPT browser sign-in. Then use Check again here.'}
            raise

    def validate_launch(self, visitor, payload, paid):
        if payload.get("provider") != self.station_provider:
            raise RequestError(400, 'Use the configured Astra provider for this station')
        if payload.get('model') not in (None, '', 'gpt-6-astra'):
            raise RequestError(400, 'This station uses gpt-6-astra')

    def page(self):
        page = super().page().decode()
        page = page.replace('<body', f'<body data-station-local="true" data-station-provider="{self.station_provider}"', 1)
        page = page.replace('<script src="/synchronized/reader.js" defer></script>', '')
        page = re.sub(r'<iframe\b[^>]*id="datasetViewer"[^>]*>.*?</iframe>',
                      '<iframe id="datasetViewer" hidden title="Local station"></iframe>', page, flags=re.S)
        page = page.replace('id="dataset" class=', 'id="dataset" hidden class=')
        page = page.replace('class="panel history" hidden', 'class="panel history"')
        page = page.replace('<h1>BluPe Playground</h1>',
            '<h1>BluPe Playground</h1>'
            f'<a href="{self.operator_origin}" target="_blank" rel="noopener">Prepare robot</a>'
            '<p id="stationModelConnection" class="help"></p>', 1)
        page = re.sub(r'<p class="playgroundIntro">.*?</p>',
            '<p class="playgroundIntro">UI, cameras, controller, and run logs stay on this Jetson. '
            'Astra receives your prompts, selected images, and robot feedback. '
            f'<a href="{self.operator_origin}" target="_blank" rel="noopener">Open operator controls</a></p>',
            page, count=1, flags=re.S)
        page = page.replace('Replay becomes available after the robot uploads its video.',
            'Prompts, replies, images, and robot feedback are saved locally. Download log to export a run.')
        page = page.replace('Your name, task, and readable Astra conversation will be visible to everyone watching.',
                            'Your task and Astra conversation are saved on this Jetson.')
        page = page.replace("This project is super new. We'd love to follow up about your experience.",
                            'Optional label saved with your local run.')
        return page.encode()

    async def http(self, scope, receive, send):
        path = scope["path"]
        # Never fall through to the local runner's public video/history proxies,
        # or the shared artifact helper that constructs hosted recording URLs.
        if path.startswith(("/synchronized/", "/live-video/")) or path.endswith("/artifacts"):
            raise RequestError(404, "Hosted media is disabled on this station")
        from remote_yam.native_history import MEDIA
        if path.startswith('/api/native-runs/'):
            headers = dict(scope.get('headers',[]))
            if headers.get(b'host',b'').decode() != self.authority:
                raise RequestError(421,'Unrecognized website host')
            if (scope['method'] != 'GET' or headers.get(b'origin',self.origin.encode()).decode() != self.origin
                    or headers.get(b'sec-fetch-site') not in (None,b'same-origin',b'none')):
                raise RequestError(403,'Open the native replay directly on this station')
            match = MEDIA.fullmatch(path)
            if not match: raise RequestError(404,'Native replay unavailable')
            try:
                target = await asyncio.to_thread(self.past_runs.media_path,*match.groups())
                descriptor = os.open(target,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
            except (OSError,ValueError):
                raise RequestError(404,'Native replay unavailable') from None
            with os.fdopen(descriptor,'rb') as stream:
                size = os.fstat(stream.fileno()).st_size
                start,end = 0,size-1; status = 200
                extra = [(b'accept-ranges',b'bytes'),(b'cache-control',b'private, no-store')]
                if b'range' in headers:
                    requested = re.fullmatch(rb'bytes=([0-9]*)-([0-9]*)',headers[b'range'])
                    try:
                        if requested is None: raise ValueError()
                        first,last = requested.groups()
                        if not first and not last: raise ValueError()
                        if first: start = int(first); end = int(last) if last else size-1
                        else: start = max(0,size-int(last))
                        if not 0 <= start <= end or start >= size: raise ValueError()
                        end = min(end,size-1); status = 206
                    except ValueError:
                        await self.respond(send,416,b'', 'video/mp4',[(b'content-range',f'bytes */{size}'.encode())])
                        return
                    extra.append((b'content-range',f'bytes {start}-{end}/{size}'.encode()))
                await self.start_response(send,status,'video/mp4',end-start+1,extra)
                stream.seek(start); remaining=end-start+1
                while remaining:
                    chunk = await asyncio.to_thread(stream.read,min(65536,remaining))
                    if not chunk: break
                    remaining -= len(chunk)
                    await send({'type':'http.response.body','body':chunk,'more_body':True})
                await send({'type':'http.response.body','body':b''})
            return
        if path in {'/api/past-runs','/api/run-catalog'}:
            headers = dict(scope.get('headers',[]))
            if headers.get(b'host',b'').decode() != self.authority:
                raise RequestError(421,'Unrecognized website host')
            if (scope['method'] != 'GET' or headers.get(b'origin',self.origin.encode()).decode() != self.origin
                    or headers.get(b'sec-fetch-site') not in (None,b'same-origin',b'none')):
                raise RequestError(403,'Open native history directly on this station')
        await super().http(scope, receive, send)

    async def start_response(self, send, status, content_type, size, extra=()):
        # Replace the shared public CSP, including HF frames and Google analytics.
        async def local_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = [(k, v) for k, v in message["headers"]
                    if k.lower() != b"content-security-policy"] + [(b"content-security-policy",
                    b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                    b"img-src 'self' data: blob:; connect-src 'self'; media-src 'self' blob:; "
                    b"frame-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")]
            await send(message)
        await super().start_response(local_send, status, content_type, size, extra)


def serve(args):
    import uvicorn
    origin = f"http://127.0.0.1:{args.port}"
    app = StationPlayground(public_origin=origin, session_api=args.session_api,
        camera_origin=args.camera_origin, recording_root=args.recording_root,
        robot_id=args.robot_id, hardware_control=args.allow_hardware_control,
        station_provider=args.station_provider, openai_key_file=args.station_api_key_file,
        episode_roots=args.station_episodes_root, media_cache=args.station_media_cache)
    config = uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning")
    socket = config.bind_socket()
    print(f"Jetson Playground: {origin}\nLogs: {app.root}", flush=True)
    if not args.no_browser:
        webbrowser.open(origin)
    asyncio.run(uvicorn.Server(config).serve(sockets=[socket]))
