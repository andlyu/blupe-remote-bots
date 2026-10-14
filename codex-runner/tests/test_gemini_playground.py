import json
import shutil
from unittest.mock import Mock, patch

import pytest

from gemini_playground import GeminiPlayground, load_api_key
from remote_yam.gemini_policy import GeminiAdapter
from remote_yam.session import MockSessionAPI
from remote_yam.providers import ScriptedAdapter
import asyncio


@pytest.fixture
def app(tmp_path, monkeypatch, request):
    for key in ('YAM_SOCIAL_DATABASE', 'YAM_RUN_NAMES_DATABASE', 'YAM_SUBMISSION_DATABASE'):
        monkeypatch.setenv(key, str(tmp_path / (key + '.sqlite3')))
    api = MockSessionAPI(auto_activate=False)
    api.create_session = Mock(wraps=api.create_session)
    runner = GeminiPlayground(public_origin='http://127.0.0.1:8794', session_api=None,
        camera_origin='http://127.0.0.1:8089', development=True, hardware_control=True,
        api_factory=lambda: api, gemini_key='private-key', share_conversation=False,
        **getattr(request, 'param', {}))
    yield runner, api
    for visitor in runner.visitors.values():
        visitor.close()
    shutil.rmtree(runner.root, ignore_errors=True)


def test_session_selects_argon_without_exposing_key_or_joining(app):
    runner, api = app
    code, body, _ = call(runner, '/api/session', {})
    assert code == 200 and body['default_provider'] == 'gemini'
    assert body['configured_providers']['gemini']['model'] == 'gemini-4-argon'
    assert body['share_conversation'] is False
    assert 'private-key' not in json.dumps(body)
    api.create_session.assert_not_called()


@pytest.mark.parametrize('app', [{'local_subscriptions': True, 'default_provider': 'codex'}], indirect=True)
def test_subscription_models_available_without_starting_a_run(app):
    runner, api = app
    with patch('remote_yam.subscription_setup.subscription_status', return_value={'ready': True}):
        code, body, _ = call(runner, '/api/session', {})
    assert code == 200 and body['default_provider'] == 'codex'
    assert body['codex']['ready'] and body['claude']['ready']
    assert body['claude_model'] == 'claude-opus-5-5'
    assert body['configured_providers']['gemini']['model'] == 'gemini-4-argon'
    assert b'<option value="standard" selected>Standard</option>' in runner.page()
    api.create_session.assert_not_called()


@pytest.mark.parametrize('app', [{'local_subscriptions': True}], indirect=True)
@pytest.mark.parametrize('name,model', [('codex', 'gpt-6-astra'), ('claude', 'claude-opus-5-5')])
@pytest.mark.parametrize('speed', [None, 'standard', 'fast'])
def test_subscription_speed_reaches_selected_model(app, name, model, speed):
    runner, _ = app
    provider = ScriptedAdapter([])
    runner.provider_factory = Mock(return_value=provider)
    with patch('remote_yam.subscription_setup.subscription_status', return_value={'ready': True}), \
         patch('remote_yam.subscription_setup.verify_subscription', return_value={'ready': True, 'setup_prompt': ''}):
        _, _, session = call(runner, '/api/session', {})
        payload = dict(provider=name, model=model, prompt='Inspect the scene')
        if speed is not None:
            payload['response_speed'] = speed
        code, body, _ = call(runner, '/api/run', payload, session)
    assert code == 200 and body['ok']
    assert runner.provider_factory.call_args.args[:3] == (name, '', model)
    assert provider.response_speed == (speed or 'standard')
    call(runner, '/api/stop', {}, session)


def test_run_and_stop_use_existing_controller(app):
    runner, api = app
    _, _, session = call(runner, '/api/session', {})
    code, body, _ = call(runner, '/api/run', dict(provider='gemini', model='gemini-4-argon',
        prompt='Inspect the scene', run_duration_s=60), session)
    assert code == 200 and body['ok']
    api.create_session.assert_called_once()
    controller = next(iter(runner.visitors.values())).controller
    assert isinstance(controller._provider, GeminiAdapter)
    assert controller._provider._camera_source is runner.camera_source
    assert controller._provider.reasoning_effort == 'medium'
    code, body, _ = call(runner, '/api/stop', {}, session)
    assert code == 200 and body['ok']


@pytest.mark.parametrize('override', [
    {'model': 'other-model'}, {'endpoint': 'https://other.invalid'},
    {'response_speed': 'fast'}, {'use_api_depth': True},
])
def test_invalid_run_does_not_join_queue(app, override):
    runner, api = app
    _, _, session = call(runner, '/api/session', {})
    code, _, _ = call(runner, '/api/run', dict(provider='gemini', model='gemini-4-argon',
        prompt='Inspect the scene', **override) if 'model' not in override else
        dict(provider='gemini', prompt='Inspect the scene', **override), session)
    assert code == 400
    api.create_session.assert_not_called()


def test_key_loader_reads_data_without_shell_execution(tmp_path, monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    with pytest.raises(ValueError, match='Set GEMINI_API_KEY'):
        load_api_key()
    p = tmp_path / 'local.env'
    p.write_text('export GEMINI_API_KEY="test-$(echo nope)"\n')
    assert load_api_key(p) == 'test-$(echo nope)'
    monkeypatch.setenv('GEMINI_API_KEY', 'environment-key')
    assert load_api_key(p) == 'environment-key'


def test_localhost_only():
    with pytest.raises(ValueError, match='localhost'):
        GeminiPlayground(public_origin='https://public.invalid', gemini_key='test-key')


def call(app, path, payload, session=None):
    headers = {'host': '127.0.0.1:8794', 'origin': 'http://127.0.0.1:8794',
               'content-type': 'application/json'}
    if session:
        headers.update(cookie=session[0], **{'x-yam-runner-token': session[1]})
    async def invoke():
        messages = []
        async def receive():
            return {'type': 'http.request', 'body': json.dumps(payload).encode()}
        async def send(message):
            messages.append(message)
        await app({'type': 'http', 'method': 'POST', 'path': path, 'query_string': b'',
                   'headers': [(k.encode(), v.encode()) for k, v in headers.items()]}, receive, send)
        response_headers = dict(messages[0]['headers'])
        body = json.loads(b''.join(m.get('body', b'') for m in messages[1:]))
        cookie = response_headers.get(b'set-cookie', b'').decode().split(';')[0]
        return messages[0]['status'], body, (cookie, body.get('csrf'))
    return asyncio.run(invoke())



@pytest.mark.parametrize('mode', [None, 'sparse', 'normal'])
def test_calling_mode_defaults_and_saved_run_configuration(app, mode):
    runner, api = app
    _, _, session = call(runner, '/api/session', {})
    payload = dict(provider='gemini', model='gemini-4-argon', prompt='Inspect only')
    if mode is not None:
        payload['gemini_calling_mode'] = mode
    code, body, _ = call(runner, '/api/run', payload, session)
    assert code == 200, body
    provider = next(iter(runner.visitors.values())).controller._provider
    assert provider.calling_mode == (mode or 'sparse')
    config = json.loads((provider._recorder.path/'gemini-config.json').read_text())
    assert config['calling_mode'] == (mode or 'sparse')
    assert provider.public_config()['calling_mode'] == config['calling_mode']
    call(runner, '/api/stop', {}, session)


@pytest.mark.parametrize('mode', ['', 'summary', None, 42, [], {}])
def test_invalid_calling_mode_never_joins_queue(app, mode):
    runner, api = app
    _, _, session = call(runner, '/api/session', {})
    code, body, _ = call(runner, '/api/run', dict(provider='gemini', prompt='Inspect only', gemini_calling_mode=mode), session)
    assert code == 400
    api.create_session.assert_not_called()


@pytest.mark.parametrize('app', [{'preview':True}], indirect=True)
def test_preview_cannot_admit_any_provider_or_start_inference(app):
    runner, api = app
    _, metadata, session = call(runner, '/api/session', {})
    assert 'Robot runs are disabled' in metadata['configured_providers']['gemini']['help']
    for name in ('gemini','local_raise_lower','openai'):
        code, body, _ = call(runner, '/api/run', dict(provider=name,prompt='Inspect only'),session)
        assert code == 403
    api.create_session.assert_not_called()


def test_mode_control_has_exact_names_and_default(app):
    page = app[0].page().decode()
    assert '<option value="sparse" selected>Sparse calling</option>' in page
    assert '<option value="normal">Normal calling</option>' in page


def test_preview_cli_needs_no_key_or_robot_transport(tmp_path, monkeypatch):
    from gemini_playground import main
    for key in ('YAM_SOCIAL_DATABASE', 'YAM_RUN_NAMES_DATABASE', 'YAM_SUBMISSION_DATABASE'):
        monkeypatch.setenv(key,str(tmp_path/(key+'.sqlite3')))
    with patch('gemini_playground.load_api_key') as key, patch('gemini_playground.find_spec') as transport, \
         patch('uvicorn.Config') as config, patch('uvicorn.Server') as server:
        main(['--preview','--no-browser','--port','19994','--recording-root',str(tmp_path/'records')])
    key.assert_not_called();transport.assert_not_called()
    server.return_value.run.assert_called_once()
    fleet = config.call_args.args[0]
    for runner in fleet.apps.values():
        assert runner.preview and runner.simulation and not runner.hardware_control
        assert runner.gemini_recording_root == tmp_path/'records'
        shutil.rmtree(runner.root,ignore_errors=True)
