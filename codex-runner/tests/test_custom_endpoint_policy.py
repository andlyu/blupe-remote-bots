import json
import shutil
from unittest.mock import MagicMock, patch

import pytest

import playground
from remote_yam.custom_endpoint_policy import CustomEndpointAdapter, PublicHTTPSConnection, EndpointAddressError
from remote_yam.session import MockSessionAPI
from remote_yam.yam_runpod_policy import GRIPPER_UNITS
from test_yam_runpod_policy import fixture


def policy(endpoint='https://policy.example/yam', key='visitor-key'):
    return CustomEndpointAdapter(key, endpoint=endpoint, camera_source=None, robot_id='yam-1')


@pytest.mark.parametrize('url', [None, '', 'http://policy.example', 'https://policy.example:8443',
    'https://user:secret@policy.example', 'https://policy.example?key=secret',
    'https://policy.example#act', 'https://127.0.0.1', 'https://169.254.169.254',
    'https://[::1]', 'https://10.0.0.1', 'https://policy.example/\nact'])
def test_invalid_endpoint_is_rejected_before_inference(url):
    with pytest.raises(ValueError):
        policy(url)


@pytest.mark.parametrize('ip', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', '192.168.1.2'])
def test_dns_private_addresses_and_mixed_answers_never_connect(ip):
    with patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('8.8.8.8', 443)),
            (2, 1, 6, '', (ip, 443))]), patch('socket.socket') as sock:
        with pytest.raises(ValueError, match='public'):
            PublicHTTPSConnection('policy.example').connect()
        sock.assert_not_called()


def test_dns_is_pinned_and_tls_uses_original_hostname():
    connection = PublicHTTPSConnection('policy.example', timeout=12)
    sock = MagicMock()
    context = MagicMock()
    connection._context = context
    with patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('8.8.8.8', 443))]) as dns, \
            patch('socket.socket', return_value=sock):
        connection.connect()
    dns.assert_called_once()
    sock.connect.assert_called_once_with(('8.8.8.8', 443))
    context.wrap_socket.assert_called_once_with(sock, server_hostname='policy.example')


def test_private_dns_fails_preparation_immediately_instead_of_waiting_for_warmup_timeout():
    adapter = policy()
    connection = MagicMock()
    connection.request.side_effect = EndpointAddressError('private DNS answer')
    with patch('remote_yam.custom_endpoint_policy.PublicHTTPSConnection', return_value=connection):
        adapter._keep_ready(lambda: False)
    assert adapter._warm_state == 'failed'
    with pytest.raises(RuntimeError, match='public IP addresses'):
        adapter.wait_ready(lambda: False)
    assert not adapter._ready.is_set()


@pytest.mark.parametrize('key', ['', 'visitor-key'])
def test_transport_appends_paths_and_uses_only_visitor_credentials(key):
    adapter = policy(key=key)
    connection = MagicMock()
    response = connection.getresponse.return_value
    response.status = 200
    response.read.return_value = b'{"ok": true}'
    with patch('remote_yam.custom_endpoint_policy.PublicHTTPSConnection', return_value=connection) as factory:
        assert adapter._json('/act', {'instruction': 'test'}) == {'ok': True}
    factory.assert_called_once_with('policy.example', timeout=12)
    args, kwargs = connection.request.call_args
    assert args == ('POST', '/yam/act')
    assert json.loads(kwargs['body']) == {'instruction': 'test'}
    assert kwargs['headers'].get('Authorization') == ('Bearer visitor-key' if key else None)
    connection.close.assert_called_once()
    assert 'policy.example' not in str(adapter.public_config())
    assert 'visitor-key' not in str(adapter.public_config())


@pytest.mark.parametrize('status,data', [(302, b'{}'), (200, b'[]'), (200, b'x' * (8 * 1024 * 1024 + 1))])
def test_transport_rejects_redirects_invalid_objects_and_oversize_responses(status, data):
    connection = MagicMock()
    connection.getresponse.return_value.status = status
    connection.getresponse.return_value.read.return_value = data
    with patch('remote_yam.custom_endpoint_policy.PublicHTTPSConnection', return_value=connection):
        with pytest.raises(RuntimeError, match='Custom endpoint request failed') as error:
            policy()._json('/health')
    assert 'policy.example' not in str(error.value)
    assert connection.request.call_count == 1
    connection.close.assert_called_once()


def test_custom_health_and_actions_share_molmoact_observation_and_validation():
    molmo, observation, result = fixture('molmoact2')
    adapter = policy()
    adapter._camera_source = molmo._camera_source
    health = dict(ok=True, robot_id='yam-1', action_dim=14, num_actions=30,
        action_units='radians', gripper_units=GRIPPER_UNITS)
    assert adapter._health_matches(health)
    for field, value in [('robot_id', 'other'), ('num_actions', 24), ('action_units', 'degrees'),
            ('action_dim', 12), ('control_hz', 10), ('ok', False)]:
        assert not adapter._health_matches({**health, field: value})
    # Generic custom servers need no pinned checkpoint, revision, or GPU identity.
    for key in ('model', 'revision', 'device'):
        result.pop(key)
    adapter._ready.set()
    adapter._json = lambda *args: result
    assert len(adapter.build_trajectory('Pick up the block', observation, 0)) == 10
    result['actions'][0][6] = 1.1
    with pytest.raises(ValueError, match='gripper_out_of_range'):
        adapter.build_trajectory('Pick up the block', observation, 0)


@pytest.mark.parametrize('robot,hardware,enabled', [('yam-1','yam',True), ('robohouse','yam',False),
    ('yam-1','custom',False)])
def test_launch_uses_entered_endpoint_without_service_key_or_saved_credentials(robot, hardware, enabled):
    app = playground.HostedRunner(public_origin='https://robot.example', session_api='https://session.example',
        camera_origin='https://session.example', robot_id=robot, hardware=hardware,
        api_factory=lambda: MockSessionAPI(auto_activate=False))
    _, visitor = app.new_visitor()
    payload = dict(provider='custom_endpoint', endpoint='https://policy.example/yam',
        api_key='visitor-key', prompt='Pick up the block', model='custom-endpoint')
    try:
        with patch.object(CustomEndpointAdapter, 'start_preparation'):
            if enabled:
                assert app.launch(visitor, payload)['ok']
                provider = visitor.controller._provider
                assert provider._endpoint == payload['endpoint']
                assert provider._api_key == 'visitor-key'
                assert not visitor.saved_keys
                assert not visitor.controller._session_api.action_log
            else:
                with pytest.raises(playground.RequestError):
                    app.launch(visitor, payload)
    finally:
        visitor.controller.stop()
        visitor.close()
        shutil.rmtree(app.root, ignore_errors=True)
