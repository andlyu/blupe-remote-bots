#!/usr/bin/env python3
"""Serve Path Studio locally or behind HTTPS with explicit owner authentication."""
import argparse
import base64
import json
import os
import secrets
import signal
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie, CookieError
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from remote_yam.path_studio_service import PathStudioService, StudioVisitors, API_ORIGIN

STATIC = Path(__file__).resolve().parent / "static"
ASSETS = {
    "path-studio.html": "text/html; charset=utf-8",
    "path-studio.css": "text/css; charset=utf-8",
    "path-studio-yam-model.js": "text/javascript; charset=utf-8",
    "path-studio-stl.js": "text/javascript; charset=utf-8",
    "path-studio-core.js": "text/javascript; charset=utf-8",
    "path-studio.js": "text/javascript; charset=utf-8",
    "path-studio-observer.js": "text/javascript; charset=utf-8",
    "hls.min.js": "text/javascript; charset=utf-8",
    "path-studio-api.js": "text/javascript; charset=utf-8",
    "path-studio-three.js": "text/javascript; charset=utf-8",
    "path-studio-three-core.js": "text/javascript; charset=utf-8",
    "path-studio-orbit.js": "text/javascript; charset=utf-8",
    "manrope-variable.ttf": "font/ttf",
    "path-studio-login.css": "text/css; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    def _host_ok(self):
        return self.headers.get('Host') in self.server.allowed_hosts

    def _site(self):
        return self.server.host_sites.get(self.headers.get('Host'), (None, self.server.base_path))

    def _authenticated(self):
        if self.headers.get('Host') in self.server.public_hosts:
            return True
        if self.server.auth_header is None:
            return True
        if secrets.compare_digest(self.headers.get('Authorization', '').encode(), self.server.auth_header):
            return True
        try:
            cookies = SimpleCookie(self.headers.get('Cookie', ''))
            value = cookies.get('path_studio_owner')
            if value and secrets.compare_digest(value.value.encode(), self.server.owner_cookie.encode()):
                return True
        except CookieError:
            pass
        self._login_page()
        return False

    def _context(self, *, create=False):
        if self.headers.get('Host') not in self.server.public_hosts:
            return self.server.service, self.server.csrf_token
        try:
            cookie = SimpleCookie(self.headers.get('Cookie','')).get('path_studio_visitor')
            record, fresh = self.server.visitors.resolve(cookie.value if cookie else None, create=create)
        except CookieError:
            record, fresh = self.server.visitors.resolve(None, create=create)
        if record is None:
            raise ValueError('Refresh Path Studio to reconnect your browser session.')
        if fresh:
            self.visitor_cookie = f'path_studio_visitor={fresh}; Path={self._site()[1]}; Secure; HttpOnly; SameSite=Strict; Max-Age=86400'
        return record['service'], record['csrf']

    def _login_page(self, failed=False):
        page = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sign in | Path Studio</title>
<link rel="stylesheet" href="./path-studio-login.css"><main><p class="brand">Path Studio</p>
<h1>Sign in to Path Studio</h1><p>Preview a drawing, watch the observer and control your run.</p>
LOGIN_ERROR<form method="post" action="./login"><label>Username<input name="username" autocomplete="username" required></label>
<label>Password<input name="password" type="password" autocomplete="current-password" required></label>
<button type="submit">Sign in</button></form><p class="note">Private controller access</p></main></html>'''
        message = '<p role="alert">That username and password did not match. Try again.</p>' if failed else ''
        # Native form POSTs use an opaque Origin under no-referrer. Keep the
        # same-origin form's Origin while disclosing no referrer off this site.
        self._respond(401, page.replace('LOGIN_ERROR', message).encode(), 'text/html; charset=utf-8', referrer_policy='same-origin')

    def _login(self):
        if self.headers.get('Host') in self.server.public_hosts:
            self._public_entry()
            return
        if (not self._host_ok() or not self.server.public_origin
                or self.headers.get('Origin') != self._site()[0]
                or self.headers.get('Sec-Fetch-Site') == 'cross-site'):
            self._respond(403, dict(error='Sign in from the configured Path Studio address'))
            return
        try:
            size = int(self.headers.get('Content-Length', '-1'))
            if not 0 <= size <= 4096 or self.headers.get_content_type() != 'application/x-www-form-urlencoded':
                raise ValueError('Invalid login form')
            form = parse_qs(self.rfile.read(size).decode(), strict_parsing=True)
            value = b'Basic '+base64.b64encode(f"{form['username'][0]}:{form['password'][0]}".encode())
            if not secrets.compare_digest(value, self.server.auth_header):
                self._login_page(failed=True)
                return
        except (ValueError, KeyError, UnicodeError):
            self._login_page(failed=True)
            return
        self.send_response(303)
        mount = self._site()[1]
        self.send_header('Location', mount)
        self.send_header('Set-Cookie', f'path_studio_owner={self.server.owner_cookie}; Path={mount}; Secure; HttpOnly; SameSite=Strict; Max-Age=86400')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def _public_entry(self):
        self.send_response(303)
        self.send_header('Location',self._site()[1])
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length','0')
        self.end_headers()

    def _respond(self, status, body, content_type='application/json; charset=utf-8', *, referrer_policy='no-referrer'):
        if not isinstance(body, bytes):
            body = json.dumps(body, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        if getattr(self, 'visitor_cookie', None):
            self.send_header('Set-Cookie', self.visitor_cookie)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', referrer_policy)
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlsplit(self.path).path == '/healthz':
            self._respond(200, dict(status='ok'))
            return
        if not self._host_ok():
            self._respond(403, dict(error='Use the configured Path Studio address'))
            return
        if urlsplit(self.path).path == '/login' and self.headers.get('Host') in self.server.public_hosts:
            self._public_entry()
            return
        if urlsplit(self.path).path == '/path-studio-login.css':
            self._respond(200, (STATIC/'path-studio-login.css').read_bytes(), ASSETS['path-studio-login.css'])
            return
        if not self._authenticated():
            return
        path = urlsplit(self.path).path
        if path.startswith('/api/path-studio/'):
            try:
                station = parse_qs(urlsplit(self.path).query).get('station', ['robohouse'])[0]
                if path.endswith('/config'):
                    service, token = self._context(create=True)
                    self._respond(200, dict(csrf_token=token, api_origin=API_ORIGIN, identity=service.identity))
                elif path.endswith('/status'):
                    service, _ = self._context()
                    self._respond(200, service.status(station))
                elif path.startswith('/api/path-studio/video/'):
                    video_path=path.removeprefix('/api/path-studio/video/')
                    body,kind=self.server.service.video(video_path,urlsplit(self.path).query)
                    self._respond(200,body,kind)
                elif path.startswith('/api/path-studio/cameras/') and path.endswith('.jpg'):
                    role = path.rsplit('/', 1)[1][:-4]
                    self._respond(200, self.server.service.camera(station, role), 'image/jpeg')
                else:
                    self._respond(404, dict(error='Unknown API route'))
            except ValueError as exc:
                self._respond(400, dict(error=str(exc)))
            except Exception:
                self._respond(502, dict(error='Robot API unavailable. Retry in a moment.'))
            return
        name = "path-studio.html" if path == "/" else path.removeprefix("/")
        if name not in ASSETS:
            self.send_error(404)
            return
        body = (STATIC / name).read_bytes()
        self._respond(200, body, ASSETS[name])

    def do_POST(self):
        if urlsplit(self.path).path == '/login':
            self._login()
            return
        if not self._authenticated():
            return
        try:
            service, token = self._context()
        except ValueError as exc:
            self._respond(403, dict(error=str(exc)))
            return
        origin = self.headers.get('Origin')
        expected = self._site()[0] or f'http://{self.headers.get("Host")}'
        if (not self._host_ok() or (origin is not None and origin != expected)
                or self.headers.get('Sec-Fetch-Site') == 'cross-site'
                or not secrets.compare_digest(self.headers.get('X-Path-Studio-Token', ''), token)):
            self._respond(403, dict(error='Open the configured Path Studio address to control your run'))
            return
        try:
            size = int(self.headers.get('Content-Length', '-1'))
            if not 0 <= size <= 256000 or self.headers.get_content_type() != 'application/json':
                raise ValueError('Send a JSON request smaller than 256 KB')
            body = json.loads(self.rfile.read(size))
            path = urlsplit(self.path).path
            if path == '/api/path-studio/run':
                result = service.run(body)
            elif path == '/api/path-studio/simulate':
                result = service.simulate(body)
            elif path == '/api/path-studio/stop':
                result = service.stop()
            else:
                self._respond(404, dict(error='Unknown API route'))
                return
            self._respond(200, result)
        except (ValueError, TypeError) as exc:
            self._respond(400, dict(error=str(exc)))
        except Exception:
            self._respond(502, dict(error='API request failed. Check the run status and retry Stop if needed.'))


def create_server(port, service=None, *, bind='127.0.0.1', public_origin=None, username=None, password=None, base_path='/', origin_mounts=None, public_origins=None, visitor_factory=None):
    if not base_path.startswith('/') or not base_path.endswith('/') or any(c not in '/-_' and not c.isalnum() for c in base_path):
        raise ValueError('Base path must be a plain absolute directory path')
    if public_origin:
        parsed = urlsplit(public_origin)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
            raise ValueError('Hosted Path Studio requires an HTTPS origin without a path')
        public_origin = public_origin.rstrip('/')
        if not username or ':' in username or not password or len(password) < 24:
            raise ValueError('Hosted Path Studio requires a username and a password of at least 24 characters')
    elif bind not in ('127.0.0.1', 'localhost') or username or password:
        raise ValueError('Public binding requires an HTTPS origin and owner authentication')
    sites = {urlsplit(public_origin).netloc: (public_origin, base_path)} if public_origin else {}
    if origin_mounts and not public_origin:
        raise ValueError('Additional origins require authenticated hosting')
    if origin_mounts is not None and not isinstance(origin_mounts, dict):
        raise ValueError('Additional origins must map HTTPS origins to mount paths')
    for origin, mount in (origin_mounts or {}).items():
        parsed = urlsplit(origin)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
            raise ValueError('Additional origins must use HTTPS without a path')
        if (not isinstance(mount,str) or not mount.startswith('/') or not mount.endswith('/')
                or any(c not in '/-_' and not c.isalnum() for c in mount)):
            raise ValueError('Additional origin mounts must be plain absolute directories')
        if parsed.netloc in sites:
            raise ValueError('Each origin host must have one explicit mount')
        sites[parsed.netloc] = (origin.rstrip('/'), mount)
    public_hosts = set()
    if public_origins is not None and not isinstance(public_origins,list):
        raise ValueError('Public origins must be an explicit list')
    for origin in public_origins or []:
        host = urlsplit(origin).netloc
        if host not in sites or sites[host][0] != origin:
            raise ValueError('Public origins must match configured HTTPS origins exactly')
        public_hosts.add(host)
    server = ThreadingHTTPServer((bind, port), Handler)
    server.daemon_threads = True
    server.allowed_hosts = (set(sites) if public_origin else
                            {f'127.0.0.1:{server.server_port}', f'localhost:{server.server_port}'})
    server.host_sites = sites
    server.public_origin = public_origin
    server.base_path = base_path
    server.owner_cookie = secrets.token_urlsafe(32)
    server.auth_header = (b'Basic ' + base64.b64encode(f'{username}:{password}'.encode())) if public_origin else None
    server.csrf_token = secrets.token_urlsafe(32)
    server.service = service or PathStudioService()
    server.public_hosts = public_hosts
    def make_visitor(key):
        owner = server.service
        return PathStudioService(api_factory=owner.api_factory,
            identity_path=owner.identity_path.parent/'visitors'/key/'identity.json',
            default_identity=dict(runner_name='',email=''), monitor_service=owner)
    server.visitors = StudioVisitors(visitor_factory or make_visitor) if public_hosts else None
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=int(os.environ.get('PORT', '8795')))
    parser.add_argument("--bind", default=os.environ.get('PATH_STUDIO_BIND', '127.0.0.1'))
    args = parser.parse_args()
    state_dir = os.environ.get('PATH_STUDIO_STATE_DIR')
    service = PathStudioService(identity_path=Path(state_dir)/'identity.json' if state_dir else None)
    server = create_server(args.port, service, bind=args.bind,
        public_origin=os.environ.get('PATH_STUDIO_PUBLIC_ORIGIN'),
        username=os.environ.get('PATH_STUDIO_USERNAME'), password=os.environ.get('PATH_STUDIO_PASSWORD'),
        base_path=os.environ.get('PATH_STUDIO_BASE_PATH', '/'),
        origin_mounts=json.loads(os.environ.get('PATH_STUDIO_ADDITIONAL_ORIGINS', '{}')),
        public_origins=json.loads(os.environ.get('PATH_STUDIO_PUBLIC_ORIGINS', '[]')))
    print(f"Path Studio: {server.public_origin or f'http://127.0.0.1:{args.port}'}/", flush=True)
    print('Preview + BluPe API. Run on real arms explicitly joins the hardware queue.', flush=True)
    try:
        def terminate(_signal, _frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, terminate)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if server.visitors is not None:
                server.visitors.close()
            server.service.close()
        except Exception:
            print('Stop acknowledgement unavailable; check the station.', file=sys.stderr)
        server.server_close()


if __name__ == "__main__":
    main()
