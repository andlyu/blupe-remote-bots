import json
from unittest.mock import Mock
import pytest
from cag_molmoact_playground import CAGPlayground
from remote_yam.session import MockSessionAPI
from test_gemini_playground import call


@pytest.fixture
def app(tmp_path,monkeypatch):
    for key in ('YAM_SOCIAL_DATABASE','YAM_RUN_NAMES_DATABASE','YAM_SUBMISSION_DATABASE'):
        monkeypatch.setenv(key,str(tmp_path/(key+'.sqlite3')))
    api=MockSessionAPI(auto_activate=False);api.create_session=Mock(wraps=api.create_session)
    app=CAGPlayground(public_origin='http://127.0.0.1:8794',session_api=None,
        camera_origin='http://127.0.0.1:1',development=True,hardware_control=True,
        api_factory=lambda:api,runpod_key='private-key',endpoint='https://abc123.api.runpod.ai')
    yield app,api
    for visitor in app.visitors.values():visitor.close()


def test_session_controls_without_key_or_queue(app):
    runner,api=app
    code,body,_=call(runner,'/api/session',{})
    assert code==200 and body['default_provider']=='molmoact_baseline'
    assert 'molmoact_guided' in body['configured_providers']
    assert 'private-key' not in json.dumps(body)
    assert b'cag-comparison.js' in runner.page()
    api.create_session.assert_not_called()


@pytest.mark.parametrize('strength',[True,float('nan'),-.1,.31,'0.15'])
def test_invalid_strength_never_joins_queue(app,strength):
    runner,api=app
    _,_,session=call(runner,'/api/session',{})
    code,_,_=call(runner,'/api/run',dict(provider='molmoact_guided',prompt='Pick cup',guidance_strength=strength),session)
    assert code==400
    api.create_session.assert_not_called()


def test_preview_cannot_run_any_provider(app):
    runner,api=app;runner.preview=True
    _,_,session=call(runner,'/api/session',{})
    code,_,_=call(runner,'/api/run',dict(provider='molmoact_guided',prompt='Pick cup'),session)
    assert code==403
    api.create_session.assert_not_called()


def test_incompatible_robot_fails_before_service_setup():
    with pytest.raises(ValueError,match='only YAM1'):
        CAGPlayground(runpod_key='x',endpoint='https://abc.api.runpod.ai',robot_id='robot-ba8413962083809c')


def test_strength_reaches_frozen_run_configuration_before_queue(app,monkeypatch):
    from remote_yam.molmoact_policy import MolmoActAdapter
    runner,api=app
    monkeypatch.setattr(MolmoActAdapter,'start_preparation',lambda *args:None)
    _,_,session=call(runner,'/api/session',{})
    code,body,_=call(runner,'/api/run',dict(provider='molmoact_guided',prompt='Pick cup',guidance_strength=.22,runner_name='Test runner',email='runner@example.com'),session)
    assert code==200,body
    provider=next(iter(runner.visitors.values())).controller._provider
    assert provider.public_config()['guidance_strength']==.22
    assert provider.public_config()['mode']=='guided'
    call(runner,'/api/stop',{},session)


@pytest.mark.parametrize('identity', [{}, {'runner_name':'Anonymous','email':'a@example.com'},
    {'runner_name':'Runner'}, {'runner_name':'Runner','email':'invalid'},
    {'runner_kind':'automated','email':'a@example.com'}, {'runner_kind':'other'}])
def test_unconfirmed_identity_never_joins_queue(app,identity):
    runner,api=app
    _,_,session=call(runner,'/api/session',{})
    code,_,_=call(runner,'/api/run',dict(provider='molmoact_guided',prompt='Pick cup',**identity),session)
    assert code==400
    api.create_session.assert_not_called()


@pytest.mark.parametrize('identity,expected', [
    ({'runner_name':'Edited Name','email':'edited@example.com'}, {'name':'Edited Name','kind':'human','email_confirmed':True}),
    ({'runner_kind':'automated'}, {'name':'Automated CAG test','kind':'automated','email_confirmed':False}),
])
def test_confirmed_attribution_reaches_queue_and_run_context(app,monkeypatch,identity,expected):
    from remote_yam.molmoact_policy import MolmoActAdapter
    runner,api=app
    monkeypatch.setattr(MolmoActAdapter,'start_preparation',lambda *args:None)
    _,_,session=call(runner,'/api/session',{})
    code,body,_=call(runner,'/api/run',dict(provider='molmoact_guided',prompt='Pick cup',guidance_strength=.19,**identity),session)
    assert code==200,body
    visitor=next(iter(runner.visitors.values()))
    context=visitor.controller._provider.public_config()['run_context']
    assert context['runner']==expected
    assert context['approach']=='MolmoAct2 + CAG-inspired guidance'
    assert context['guidance_strength']==.19
    assert '@' not in json.dumps(context)
    assert visitor.runner_name==expected['name']
    assert visitor.controller._session_api.queue_identity.get('email','')==identity.get('email','')
    call(runner,'/api/stop',{},session)


def test_paused_service_does_not_prepare_or_join(app,monkeypatch):
    runner,api=app
    runner.runs_enabled=False
    _,_,session=call(runner,'/api/session',{})
    code,body,_=call(runner,'/api/run',dict(provider='molmoact_guided',prompt='Pick cup',runner_kind='automated'),session)
    assert code==503 and 'paused' in body['error']
    api.create_session.assert_not_called()
