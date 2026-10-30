"""Visitor-owned joint policies using the documented /health and /act contract."""
import http.client
import ipaddress
import json
import socket
from urllib.parse import urlsplit

from .yam_runpod_policy import GRIPPER_UNITS, YAMRunpodAdapter


class EndpointAddressError(ValueError):
    pass


class PublicHTTPSConnection(http.client.HTTPSConnection):
    """Connect only to checked public addresses; retain hostname TLS verification.

    Resolve once per connection and connect to that exact address, so a second
    DNS lookup cannot redirect the runner into its private network. No proxies,
    redirects, or caller-supplied service credentials are involved.
    """
    def connect(self):
        addresses = socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise EndpointAddressError('Endpoint must resolve exclusively to public IP addresses')
        for family, kind, protocol, _, address in addresses:
            sock = socket.socket(family, kind, protocol)
            try:
                sock.settimeout(self.timeout)
                sock.connect(address)
                self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
                return
            except OSError:
                sock.close()
        raise OSError('Endpoint connection failed')


class CustomEndpointAdapter(YAMRunpodAdapter):
    health_mismatch = 'Custom endpoint health contract mismatch'
    readiness_timeout = 'Custom endpoint did not become ready within twenty minutes'

    def __init__(self, api_key, *, endpoint, camera_source, robot_id,
                 joint_counts=(6, 6), camera_names=('top', 'left', 'right')):
        if (not isinstance(robot_id, str) or not robot_id or len(joint_counts) != 2
                or any(type(count) is not int or count < 0 for count in joint_counts)
                or not any(joint_counts) or not camera_names):
            raise ValueError('Custom endpoint requires a selected robot joint and camera profile')
        if (not isinstance(endpoint, str) or not 1 <= len(endpoint) <= 2048
                or any(c.isspace() or ord(c) < 32 for c in endpoint)):
            raise ValueError('Enter an HTTPS endpoint URL')
        try:
            target = urlsplit(endpoint)
            valid = (target.scheme == 'https' and target.hostname and target.port in (None, 443)
                     and not target.username and not target.password and not target.query and not target.fragment)
            host = target.hostname.encode('idna').decode('ascii') if target.hostname else ''
            if not valid or not host:
                raise ValueError()
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
            if address is not None and not address.is_global:
                raise ValueError('Endpoint must use a public address')
        except (ValueError, UnicodeError):
            raise ValueError('Use a public HTTPS endpoint on port 443, without credentials, a query or a fragment') from None
        # Retain the measured-observation, trajectory validation and cancellation
        # path of the pinned adapter. Its configured credentials are never read.
        self._initialize(api_key, 'custom_endpoint',
            dict(label='Custom end-point', model='custom-endpoint', num_actions=30), endpoint, camera_source)
        self._robot_id = robot_id
        self._profile_label = robot_id
        self._joint_counts = tuple(joint_counts)
        self._camera_names = tuple(camera_names)
        self._host = host
        self._base_path = target.path.rstrip('/')
        self._endpoint = endpoint.rstrip('/')

    def prepare_before_session(self, prompt):
        if self.cancelled():
            raise RuntimeError('Custom endpoint preparation cancelled')
        self.interaction_sink('model_progress', 'Waiting for your policy server before joining the robot queue; the run timer has not started')
        self.start_preparation(self.cancelled)
        self.wait_ready(self.cancelled)
        self.interaction_sink('model_progress', 'Custom endpoint ready; joining the robot queue')

    def public_config(self):
        return dict(provider=self.provider_name, model=self.model, warmup=self._warm_state,
                    api_key_configured=bool(self._api_key))

    def _identity(self, value):
        return (value.get('robot_id') == self._robot_id and value.get('action_units') == 'radians'
                and value.get('gripper_units') == GRIPPER_UNITS)

    def _device_valid(self, value):
        return True

    def _capture_policy_frames(self, observation):
        return [frame for frame in super()._capture_policy_frames(observation)
                if frame.name in self._camera_names]

    def _health_matches(self, health):
        return (self._identity(health) and health.get('ok') is True
                and health.get('action_dim') == sum(count + 1 for count in self._joint_counts if count)
                and health.get('num_actions') == 30
                and health.get('control_hz', 30) == 30)

    def _json(self, path, payload=None):
        connection = PublicHTTPSConnection(self._host, timeout=30 if payload is None else 12)
        try:
            headers = {'Content-Type': 'application/json'}
            if self._api_key:
                headers['Authorization'] = 'Bearer ' + self._api_key
            connection.request('GET' if payload is None else 'POST', self._base_path + path,
                body=None if payload is None else json.dumps(payload).encode(), headers=headers)
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError('Expected HTTP 200; redirects are not followed')
            data = response.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024:
                raise ValueError('Policy response exceeds limit')
            value = json.loads(data)
            if not isinstance(value, dict):
                raise ValueError('Expected a policy object')
            return value
        except EndpointAddressError:
            self._failure = 'Use an endpoint that resolves exclusively to public IP addresses'
            self._warm_state = 'failed'
            raise RuntimeError(self._failure) from None
        except Exception as exc:
            raise RuntimeError('Custom endpoint request failed (' + type(exc).__name__ + ')') from None
        finally:
            connection.close()
