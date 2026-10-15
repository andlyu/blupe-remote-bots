"""A private, per-visitor chat session for local public-queue playgrounds.

Only visitor-chat routes are exposed. Robot, provider and local browser credentials
never cross this bridge. Remote cookies remain in memory and redirects are refused.
"""
from http.cookiejar import CookieJar
import json
import threading
from urllib import request, error

from remote_yam.cameras import NoRedirect


class ChatUnavailable(Exception):
    def __init__(self, status=503, message='Public visitor chat is temporarily unavailable. Try again.'):
        self.status, self.message = status, message


class VisitorChat:
    def __init__(self, origin, robot_id):
        self.origin, self.robot_id = origin.rstrip('/'), robot_id
        self.cookies = CookieJar()
        self.opener = request.build_opener(NoRedirect, request.HTTPCookieProcessor(self.cookies))
        self.csrf = ''
        self.cursor = 0
        self.lock = threading.Lock()

    def _request(self, path, payload=None):
        assert path in {'/api/session', '/api/chat', '/api/reactions'}
        headers = {'Origin':self.origin, 'X-Blupe-Robot':self.robot_id}
        body = None
        if payload is not None:
            headers.update({'Content-Type':'application/json', 'X-YAM-Runner-Token':self.csrf})
            body = json.dumps(payload).encode()
        req = request.Request(self.origin + path, data=body, headers=headers)
        try:
            with self.opener.open(req, timeout=5) as response:
                raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise ValueError('Chat response too large')
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise ValueError('Invalid chat response')
                return result
        except error.HTTPError as exc:
            if exc.code == 401:
                self.csrf = ''
                self.cookies.clear()
            if exc.code == 429:
                raise ChatUnavailable(429, 'Please wait a moment before sending again.') from None
            if exc.code == 404 and path == '/api/reactions':
                raise ChatUnavailable(503, 'Shared reactions are not available on the public playground yet.') from None
            raise ChatUnavailable() from None
        except (OSError, ValueError):
            raise ChatUnavailable() from None

    def _connect(self):
        if not self.csrf:
            setup = self._request('/api/session', {})
            csrf = setup.get('csrf')
            if not isinstance(csrf, str) or not csrf:
                raise ChatUnavailable()
            self.csrf = csrf
            self.cursor = setup.get('reaction_cursor', 0)

    def setup(self):
        with self.lock:
            self._connect()
            return {'reaction_cursor':self.cursor, 'chat_scope':'public'}

    def snapshot(self):
        with self.lock:
            self._connect()
            result = self._request('/api/chat')
            # Suppress events sent before this browser joined the shared room,
            # including when a temporary outage delayed its initial connection.
            result['reactions'] = [event for event in result.get('reactions', [])
                                   if event['id'] > self.cursor]
            return result

    def publish(self, path, payload):
        assert path in {'/api/chat', '/api/reactions'}
        with self.lock:
            self._connect()
            return self._request(path, payload)
