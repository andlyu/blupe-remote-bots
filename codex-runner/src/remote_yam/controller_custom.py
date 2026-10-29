"""Session-user endpoints using the existing Responses/tool/IK adapter contract.

No adapter code or credential travels with a run. Each HTTPS connection resolves
and pins a public address, verifies TLS for the original hostname, disables
proxies/redirects and withholds Authorization. See docs/controller-models.md.
"""
import http.client
import ipaddress
import socket
import ssl
from urllib import request
from urllib.parse import urlsplit

from .cameras import NoRedirect
from .robocurve_policy import RoboCurveResponsesAdapter


def validate_custom(value):
    if not isinstance(value, dict) or set(value) != {'protocol', 'url'} or value.get('protocol') != 'responses_v1':
        raise ValueError('Custom endpoints require the installed responses_v1 protocol')
    url = value.get('url')
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) <= 32 or ord(c) >= 127 for c in url):
        raise ValueError('Invalid custom endpoint URL')
    p = urlsplit(url)
    if (p.scheme != 'https' or not p.hostname or p.username or p.password or p.query or p.fragment
            or p.hostname.endswith('.') or p.hostname in {'localhost', 'metadata.google.internal'}
            or p.hostname.endswith(('.localhost', '.local', '.internal'))):
        raise ValueError('Custom endpoints require a public HTTPS URL without credentials or query parameters')
    try:
        address = ipaddress.ip_address(p.hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError('Custom endpoints require a public address')
    if p.port is not None and not 1 <= p.port <= 65535:
        raise ValueError('Invalid custom endpoint port')
    return dict(protocol='responses_v1', url=url)


class PublicHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        if self._tunnel_host:
            raise ValueError('Custom inference does not support proxy tunnels')
        addresses = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise ValueError('Custom inference resolved to a non-public address')
        # Connect to the validated numeric address, retaining the original TLS
        # hostname. A second DNS lookup cannot redirect this request into a LAN.
        address = addresses[0][4][0]
        self.sock = socket.create_connection((address, self.port), self.timeout, self.source_address)
        try:
            self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)
        except BaseException:
            self.sock.close()
            raise


class PublicHTTPSHandler(request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(PublicHTTPSConnection, req, context=self._context)


class CustomResponsesAdapter(RoboCurveResponsesAdapter):
    provider_name = 'custom'

    def __init__(self, model, selection, **kwargs):
        target = validate_custom(selection)['url']
        # Base initialization requires a nonempty key; the transport below
        # strips the sentinel header and never sends it to the endpoint.
        super().__init__('no-custom-credential', model, target, **kwargs)
        opener = request.build_opener(request.ProxyHandler({}), NoRedirect,
                                      PublicHTTPSHandler(context=ssl.create_default_context()))
        def open_request(req, **options):
            if req.full_url != target:
                raise ValueError('Custom inference destination changed')
            req.remove_header('Authorization')
            return opener.open(req, **options)
        self._urlopen = open_request

    def public_config(self):
        return {**super().public_config(), 'api_key_configured': False,
                'custom_protocol': 'responses_v1'}

    def _post_json(self, payload):
        try:
            return super()._post_json(payload)
        except Exception as error:
            # Provider-controlled bodies/URLs are never operator diagnostics.
            raise RuntimeError('Custom inference request failed (' + type(error).__name__ + ')') from None
