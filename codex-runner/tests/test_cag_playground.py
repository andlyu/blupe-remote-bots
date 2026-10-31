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
    from remote_yam.molmoact_policy import MolmoActAdapter
    monkeypatch.setattr(MolmoActAdapter, '_capacity_snapshot', lambda self: dict(available=False, checked_at=1, workers=[]))
    api=MockSessionAPI(auto_activate=False);api.create_session=Mock(wraps=api.create_session)
    app=CAGPlayground(public_origin='http://127.0.0.1:8794',session_api=None,
        camera_origin='http://127.0.0.1:1',development=True,hardware_control=True,
        api_factory=lambda:api,runpod_key='private-key',endpoint='https://abc123.api.runpod.ai')
    yield app,api
    for visitor in app.visitors.values():visitor.close()


def test_session_controls_without_key_or_queue(app):
    runner,api=app
    code,body,_=call(runner,'/api/session',{})
    assert code==200 and body['default_provider']=='molmoact_guided'
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
    monkeypatch.setattr(MolmoActAdapter,'prepare_before_session',lambda *args:None)
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
    monkeypatch.setattr(MolmoActAdapter,'prepare_before_session',lambda *args:None)
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


def wait_for(predicate):
    import time
    end=time.monotonic()+2
    while not predicate():
        assert time.monotonic()<end, 'condition did not arrive'
        time.sleep(.01)


def test_cold_gpu_is_visible_and_does_not_join_or_launch_robot_until_ready(app,monkeypatch):
    import threading,time
    from remote_yam.molmoact_policy import MolmoActAdapter,VARIANT
    from remote_yam.molmoact_protocol import identity
    runner,api=app;ready=threading.Event();requested=threading.Event()
    def health(policy,path,payload=None):
        assert path=='/health'
        requested.set()
        while not ready.wait(.01):
            if policy.cancelled():raise RuntimeError('cancelled')
        return dict(identity(),ok=True,device='cuda:0',cuda_available=True,variant=VARIANT,
            verification={k:True for k in ('pristine_baseline_equal','zero_strength_exact_equal','nonzero_text_kv_changed','non_goal_kv_unchanged')})
    monkeypatch.setattr(MolmoActAdapter,'_json',health)
    _,_,session=call(runner,'/api/session',{})
    code,body,_=call(runner,'/api/run',dict(provider='molmoact_guided',prompt='Pick cup',runner_kind='automated'),session)
    assert code==200 and body['status']=='preparing' and 'Starting RunPod' in body['launch_message']
    assert requested.wait(1)
    visitor=next(iter(runner.visitors.values()))
    status=visitor.controller.status()
    assert status['session_id'] is None and status['provider']['warmup']=='warming'
    api.create_session.assert_not_called()
    ready.set();wait_for(lambda:visitor.controller.status()['status']=='queued')
    runner.remember_runner(visitor)
    assert visitor.runner_session_id==visitor.controller.status()['session_id']
    assert visitor.runner_name=='Automated CAG test'
    assert visitor.controller.status()['run_configuration']['run_context']['runner']['name']=='Automated CAG test'
    assert api.create_session.call_count==1
    call(runner,'/api/stop',{},session)


def test_stop_during_gpu_startup_never_creates_robot_session(app,monkeypatch):
    import threading
    from remote_yam.molmoact_policy import MolmoActAdapter
    runner,api=app;requested=threading.Event()
    def health(policy,path,payload=None):
        requested.set()
        while not policy.cancelled():threading.Event().wait(.01)
        raise RuntimeError('cancelled')
    monkeypatch.setattr(MolmoActAdapter,'_json',health)
    _,_,session=call(runner,'/api/session',{})
    code,_,_=call(runner,'/api/run',dict(provider='molmoact_baseline',prompt='Pick cup',runner_kind='automated'),session)
    assert code==200 and requested.wait(1)
    call(runner,'/api/stop',{},session)
    visitor=next(iter(runner.visitors.values()))
    wait_for(lambda: not visitor.controller._worker.is_alive())
    api.create_session.assert_not_called()


def test_finished_run_keeps_actual_cag_method_and_runner_after_provider_teardown(app,monkeypatch):
    from remote_yam.molmoact_policy import MolmoActAdapter
    runner,api=app
    monkeypatch.setattr(MolmoActAdapter,'prepare_before_session',lambda *args:None)
    _,_,session=call(runner,'/api/session',{})
    code,_,_=call(runner,'/api/run',dict(provider='molmoact_guided',prompt='Pick cup',runner_name='Andrew',email='andrew@example.com'),session)
    assert code==200
    visitor=next(iter(runner.visitors.values()))
    wait_for(lambda:visitor.controller.status()['status']=='queued')
    call(runner,'/api/stop',{},session)
    visitor.controller._provider=None
    import asyncio
    async def get_status():
        messages=[]
        async def receive():return {'type':'http.request','body':b''}
        async def send(value):messages.append(value)
        await runner({'type':'http','method':'GET','path':'/api/status','query_string':b'',
            'headers':[(b'host',b'127.0.0.1:8794'),(b'cookie',session[0].encode())]},receive,send)
        return messages[0]['status'],json.loads(b''.join(x.get('body',b'') for x in messages[1:]))
    code,state=asyncio.run(get_status())
    assert code==200
    assert state['public_run']['runner_name']=='Andrew'
    assert state['public_run']['model_name']=='MolmoAct2 + CAG-inspired guidance'


def test_shared_replay_keeps_local_confirmed_name_and_actual_approach(app):
    runner,api=app
    config=dict(provider='molmoact_guided',model='allenai/MolmoAct2-BimanualYAM',approach='MolmoAct2 + CAG-inspired guidance',run_context={'runner':{'name':'Andrew','kind':'human','email_confirmed':True}})
    runner.run_names.remember('ep_history','Andrew')
    runner.run_names.remember_metadata('ep_history','yam-1','Put box in bin',1,config)
    runner.run_names.results=Mock(return_value={'ep_history':{'result':'Failure','result_reason':'Robot rejected the action packet before motion','errors':'adjacent_delta_limit'}})
    result=runner.decorate_history({'runs':[{'episode_id':'ep_history','runner_name':'Name not recorded','model':None,'video_url':'/api/quick-replays/unchanged.mp4'}]})
    row=result['runs'][0]
    assert row['runner_name']=='Andrew'
    assert row['result']=='Failure' and 'rejected' in row['result_reason']
    assert row['model_version']=='MolmoAct2 + CAG-inspired guidance'
    assert row['model']=='allenai/MolmoAct2-BimanualYAM'
    assert row['video_url']=='/api/quick-replays/unchanged.mp4'
    assert '@' not in json.dumps(row)


def test_current_replay_does_not_wait_for_archive_and_retains_andrew(app):
    runner,api=app
    _,_,session=call(runner,'/api/session',{})
    visitor=next(iter(runner.visitors.values()))
    config=dict(provider='molmoact_guided',model='allenai/MolmoAct2-BimanualYAM',approach='MolmoAct2 + CAG-inspired guidance',run_context={'runner':{'name':'Andrew','kind':'human','email_confirmed':True}})
    runner.run_names.remember('ep_ready','Andrew')
    runner.run_names.remember_metadata('ep_ready','yam-1','Put box in bin',1,config)
    visitor.episode_ids.add('ep_ready')
    runner.quick_replays.get=Mock(return_value={'episode_id':'ep_ready','started_at':1,'video_url':'/api/quick-replays/ep_ready/'+'a'*64+'.mp4'})
    runner.past_runs.page=Mock(side_effect=AssertionError('Current replay must not wait for archive catalog'))
    code,body,_=call(runner,'/api/my-runs',{'offset':0},session)
    assert code==200 and body['runs'][0]['runner_name']=='Andrew'
    assert body['runs'][0]['model_version']=='MolmoAct2 + CAG-inspired guidance'
    assert body['runs'][0]['video_url'].endswith('.mp4')
    assert '@' not in json.dumps(body)
    visitor.episode_ids.clear()
    code,body,_=call(runner,'/api/my-runs',{'offset':0},session)
    assert code==200 and body['runs']==[]
    code,_,_=call(runner,'/api/my-runs',{'episode_ids':['ep_ready']},session)
    assert code==400


def test_shared_terminal_status_keeps_person_method_and_neutral_time_limit(app):
    runner,_=app
    config=dict(provider='molmoact_guided',model='allenai/MolmoAct2-BimanualYAM',approach='MolmoAct2 + CAG-inspired guidance',run_context={'runner':{'name':'Andrew','kind':'human','email_confirmed':True}})
    runner.run_names.remember('ep_status','Andrew')
    runner.run_names.remember_metadata('ep_status','yam-1','Put box in bin',1,config)
    state={'public_run':{'run_id':'ep_status','runner_name':'API caller','status':'stopped','error':'policy_runtime_timeout: Run duration limit reached; parking at zero and disabling torque',
        'events':[{'kind':'error','message':'policy_runtime_timeout: Run duration limit reached'},{'kind':'error','message':'An actual unrelated fault'}]}}
    result=runner.decorate_status(state)['public_run']
    assert result['runner_name']=='Andrew'
    assert result['model_name']==config['approach']
    assert result['error']=='Run reached time limit'
    assert result['events'][0]['kind']=='lifecycle'
    assert result['events'][1]['kind']=='error'
    result=runner.decorate_status({'public_run':{'run_id':'ep_status','status':'stopped','error':'Hardware feedback blocked: station_unsafe'}})['public_run']
    assert result['error']=='Hardware feedback blocked: station_unsafe'
