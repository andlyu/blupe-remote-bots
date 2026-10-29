from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import json
import socket

import pytest

from remote_yam.controller_models import ControllerModels, public_models
from remote_yam.controller_executor import selected_executor, execution_request
from remote_yam.controller_custom import PublicHTTPSConnection, validate_custom
from remote_yam.providers import PolicyComplete
from remote_yam.runner_policy_client import RunnerPolicyClient
from test_controller_dream_executor import setup, finish, Adapter


ROWS = {'astra': dict(provider='openai', model='gpt-6-astra', label='Astra', adapter='codex', available=True),
        'custom': dict(provider='custom', model='custom', label='Your endpoint', adapter='responses',
                       custom=True, user_endpoint=True, available=True)}
ENDPOINT = dict(protocol='responses_v1', url='https://inference.example/v1/responses')


@pytest.mark.parametrize('robot', ['yam-1', 'robot-ba8413962083809c'])
def test_controller_selection_is_robot_scoped_and_does_not_change_null_route(robot):
    assert selected_executor(None, provider='openai', model='anything', robot_id=robot) is None
    p = selected_executor('controller', provider='openai', model='gpt-6-astra', robot_id=robot,
                          models=ROWS, model_id='astra')
    assert p.public_config()['execution_location'] == 'controller'
    assert p.public_config()['controller_model'] == 'astra'
    with pytest.raises(ValueError):
        selected_executor('controller', provider='dream', model='', robot_id=robot, models=ROWS, model_id='astra')
    with pytest.raises(ValueError):
        selected_executor('controller', provider='openai', model='', robot_id=robot, models=ROWS, model_id='not-installed')


def test_private_config_never_appears_in_catalog_and_joint_checkpoints_cannot_cross_embodiments(tmp_path):
    row = dict(ROWS['astra'], credentials_file='/private/path', endpoint='https://private.example')
    assert public_models({'astra': row}) == {'astra': {k: row[k] for k in ('provider','model','label','available')}}
    with pytest.raises(ValueError, match='YAM1 embodiment'):
        ControllerModels(dict(schema='blupe-controller-models-v1', robot_id='robot-ba8413962083809c',
            models={'groot': dict(row, adapter='groot')}), robot_id='robot-ba8413962083809c', directory=tmp_path)


@pytest.mark.parametrize('url', ['http://example.com', 'https://127.0.0.1/act', 'https://[::1]/act',
    'https://169.254.169.254/', 'https://user:secret@example.com/', 'https://example.com/?key=secret',
    'https://example.local/act', 'https://example.com/\nheader', 'https://example.com:0/'])
def test_user_endpoint_cannot_target_local_metadata_or_carry_url_credentials(url):
    with pytest.raises(ValueError): validate_custom(dict(ENDPOINT, url=url))


def test_dns_rebinding_cannot_reach_a_private_address_and_tls_keeps_original_hostname(monkeypatch):
    resolver, connect, tls = Mock(), Mock(), Mock()
    monkeypatch.setattr(socket, 'getaddrinfo', resolver)
    monkeypatch.setattr(socket, 'create_connection', connect)
    conn = PublicHTTPSConnection('inference.example', context=__import__('ssl').create_default_context())
    conn._context = tls
    resolver.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.1.10.117',443))]
    with pytest.raises(ValueError, match='non-public'): conn.connect()
    connect.assert_not_called()
    resolver.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34',443))]
    conn.connect()
    assert connect.call_args.args[0] == ('93.184.216.34',443)
    tls.wrap_socket.assert_called_once_with(connect.return_value, server_hostname='inference.example')


def test_session_user_custom_url_and_model_are_sent_without_keys_or_paths():
    p = selected_executor('controller', provider='custom', model='my/model-v2', robot_id='yam-1',
        models=ROWS, model_id='custom', custom_endpoint=ENDPOINT)
    assert p.model == 'my/model-v2'
    assert 'url' not in json.dumps(p.public_config())
    api = Mock(); api._capability.return_value = 'fixture-capability'
    execution_request(api, dict(session_id='s',episode_id='e',lease_id='l'), 'controller',
        model_id='custom', custom_endpoint=ENDPOINT, model=p.model)
    assert api._request.call_args.args[2]['payload'] == dict(model_id='custom',custom_endpoint=ENDPOINT,model='my/model-v2')
    with pytest.raises(ValueError, match='endpoint override'):
        selected_executor('controller', provider='openai', model='gpt-6-astra',robot_id='yam-1',
            models=ROWS,model_id='astra',custom_endpoint=ENDPOINT)


@pytest.mark.parametrize('robot', ['yam-1','robot-ba8413962083809c'])
@pytest.mark.parametrize('predict_only', [False,True])
def test_registered_adapter_uses_existing_native_receipts_and_predict_is_command_free(robot,predict_only):
    op, ex, req, submitted, sent, adapters = setup()
    op.api_client.jetson_id = ex.settings['robot_id'] = robot
    runtime = ControllerModels(dict(schema='blupe-controller-models-v1',robot_id=robot,models=ROWS),
                              robot_id=robot,directory='unused')
    runtime.native = lambda operator, model_id, **kw: ex.native_factory(operator, **ex.settings, dispatch=kw['dispatch'])
    ex.model_runtime = ex.pool = runtime
    req = dict(req,executor='controller',payload={'model_id':'astra'},operation='predict' if predict_only else 'start')
    ex.request(req)
    assert finish(ex) == 'completed'
    assert len(submitted) == (0 if predict_only else 1)
    assert ex.status()['predictions'] == 1
    with pytest.raises(ValueError, match='another controller model'):
        ex.request(dict(req,payload=dict(model_id='custom',custom_endpoint=ENDPOINT,model='my/model')))


def test_model_done_is_completion_instead_of_executor_failure():
    class Done(Adapter):
        def build_trajectory(self,*args): raise PolicyComplete('done')
    op, ex, req, submitted, sent, adapters = setup(adapter_factory=Done)
    ex.request(req)
    assert finish(ex) == 'completed'
    assert not submitted and not sent and op.api_authorized


def test_api_client_keeps_custom_endpoint_selection_and_never_retries_uncertain_start():
    client = RunnerPolicyClient();client.metadata = dict(controller_models=ROWS)
    client._request = Mock(side_effect=TimeoutError('uncertain start'))
    with pytest.raises(TimeoutError):
        client.start_model(provider='custom',model='my/model',prompt='Hold.',executor='controller',
            controller_model='custom',custom_endpoint=ENDPOINT)
    assert client._request.call_count == 1
    assert client._request.call_args.args[1]['custom_endpoint'] == ENDPOINT
    assert 'api_key' not in client._request.call_args.args[1]
