import io,json
from types import SimpleNamespace
from unittest.mock import Mock,patch
import pytest
from remote_yam.remote_runner_policy import RemoteRunnerPolicy
from remote_yam.configured_policy_hosting import ConfiguredPoliciesMixin
from remote_yam.runner_policy_client import RunnerPolicyClient

SPEC=dict(runner_origin='http://127.0.0.1:8787',transport_origin='http://127.0.0.1:38987',robot_id='yam-1',model='cube-reset-v1',label='Reset bin',task='Reset bin',help='Cube reset')

def setup():
    c=Mock(metadata=dict(configured_providers=dict(reset_bin=dict(model=SPEC['model']))),attempt_id=None)
    c.start.side_effect=lambda *a,**k:setattr(c,'attempt_id','attempt')
    return RemoteRunnerPolicy('reset_bin',SPEC,client_factory=lambda *a,**k:c),c

def state(phase='running',status='running'):
    return dict(attempt_id='attempt',status=status,provider=dict(managed_execution=dict(phase=phase,request_id='request',progress=dict(phase='cube',color='blue',path='/secret'),result=dict(state=phase,goals_reached=phase=='complete',request_id='request',path='/secret'))))

def test_once_only_start_status_retries_and_sanitized_results():
    p,c=setup();c.status.side_effect=[TimeoutError(),state(),state('complete','stopped')]
    with patch('remote_yam.remote_runner_policy.time.sleep'):assert p.run_managed('Reset')['goals_reached']
    c.connect.assert_called_once();c.start.assert_called_once()
    assert '/secret' not in str(p.public_config()) and 'transport_origin' not in str(p.public_config())

def test_ambiguous_start_reconciles_same_visitor_without_retry():
    p,c=setup();c.start.side_effect=TimeoutError();c.status.side_effect=[state(),state('complete','stopped')]
    assert p.run_managed('Reset')['goals_reached'];c.start.assert_called_once();assert c.attempt_id=='attempt'

def test_unconfirmed_start_never_retries():
    p,c=setup();c.start.side_effect=TimeoutError();c.status.return_value=dict(status='idle',attempt_id=None)
    with pytest.raises(RuntimeError,match='not retried'):p.run_managed('Reset')
    c.start.assert_called_once()

def test_stop_during_connect_never_starts():
    p,c=setup();c.connect.side_effect=p.request_stop
    assert p.run_managed('Reset')['state']=='cancelled';c.start.assert_not_called()

def test_stop_retries_idempotent_cancellation_and_retains_ownership_until_terminal():
    p,c=setup();c.start.side_effect=lambda *a,**k:p.request_stop()
    c.status.side_effect=[state(),state(),state('cancelled','stopped')];c.stop.side_effect=[TimeoutError(),dict(ok=True)]
    with patch('remote_yam.remote_runner_policy.time.sleep'):assert p.run_managed('Reset')['state']=='cancelled'
    assert c.stop.call_count==2 and c.status.call_count==3

def test_model_and_attempt_mismatch_do_not_control_another_request():
    p,c=setup();c.metadata['configured_providers']['reset_bin']['model']='old'
    with pytest.raises(RuntimeError,match='version'):p.run_managed('Reset')
    c.start.assert_not_called()
    p,c=setup();c.status.side_effect=RuntimeError('different run')
    with pytest.raises(RuntimeError,match='different run'):p.run_managed('Reset')
    c.stop.assert_not_called()

def test_tunnel_preserves_host_origin_and_saved_transport(tmp_path):
    c=RunnerPolicyClient(SPEC['runner_origin'],transport_origin=SPEC['transport_origin']);seen=[]
    c.opener=SimpleNamespace(open=lambda req,**kw:(seen.append(req) or io.BytesIO(b'{"csrf":"fixture"}')))
    c.connect();assert seen[0].full_url=='http://127.0.0.1:38987/api/session'
    assert seen[0].get_header('Host')=='127.0.0.1:8787' and seen[0].get_header('Origin')==SPEC['runner_origin']
    c.save(tmp_path/'session');assert RunnerPolicyClient.load(tmp_path/'session').transport_origin==SPEC['transport_origin']

def test_config_robot_scope_fixed_task_and_cross_visitor_exclusion(tmp_path,monkeypatch):
    path=tmp_path/'config';path.write_text(json.dumps(dict(reset_bin=SPEC)));monkeypatch.setenv('YAM_CONFIGURED_RUNNERS_FILE',str(path))
    class Base:
        def __init__(self,**kwargs):self.kwargs=kwargs;self.visitors={}
        def launch(self,visitor,payload,**kwargs):return payload
    class App(ConfiguredPoliciesMixin,Base):pass
    app=App(robot_id='yam-1');assert 'reset_bin' in app.kwargs['extra_providers']
    payload=app.launch(None,dict(provider='reset_bin',model=SPEC['model'],prompt='override',api_key='secret'))
    assert payload['prompt']=='Reset bin' and payload['api_key']==''
    assert not App(robot_id='other').configured_policies and 'runner_origin' not in str(app.configured_public_config())
    with pytest.raises(Exception,match='version'):app.launch(None,dict(provider='reset_bin',model='old'))
    app.visitors={'busy':SimpleNamespace(controller=SimpleNamespace(busy=lambda:True,_provider=None))}
    with pytest.raises(Exception,match='active'):app.launch(None,dict(provider='reset_bin',model=SPEC['model']))


def test_terminal_failure_survives_proxy_without_forwarding_raw_error():
    from remote_yam.run_errors import public_run_error
    p,c=setup(); terminal=state('failed','failed')
    terminal['error']='RuntimeError: Queue/API owner blocks initialization'
    terminal['provider']['managed_execution']['result']['error']='secret /private/config'
    c.status.return_value=terminal
    with pytest.raises(RuntimeError) as caught:p.run_managed('Reset')
    assert str(caught.value)=='Robot initialization was blocked by queue/API ownership.'
    assert public_run_error(dict(status='failed',error='RuntimeError: '+str(caught.value),provider=p.public_config()))==str(caught.value)
    assert 'secret' not in str(p.public_config()) and '/private' not in str(p.public_config())
    c.start.assert_called_once()


def test_unknown_remote_failure_stays_private():
    p,c=setup(); terminal=state('failed','failed')
    terminal['error']='private exception with https://private/token'
    terminal['provider']['managed_execution']['failure']={'code':'unknown','message':'secret'}
    c.status.return_value=terminal
    with pytest.raises(RuntimeError) as caught:p.run_managed('Reset')
    assert 'private' not in str(caught.value) and 'secret' not in str(p.public_config())


def test_proxy_uses_only_allowlisted_failure_code_not_remote_message():
    p,c=setup(); terminal=state('failed','failed')
    terminal['provider']['managed_execution']['failure']=dict(code='queue_api_owner',message='secret')
    c.status.return_value=terminal
    with pytest.raises(RuntimeError,match='queue/API ownership'):p.run_managed('Reset')
    assert 'secret' not in str(p.public_config())


@pytest.mark.parametrize('seconds',[600,180,300])
def test_hosted_controller_selected_duration_reaches_same_child_run(seconds):
    from remote_yam.controller import RunnerController
    from remote_yam.session import MockSessionAPI
    p,c=setup();c.status.return_value=state('complete','stopped')
    controller=RunnerController(MockSessionAPI())
    controller.join_and_run(p,'Reset bin',run_duration_s=seconds)
    controller._worker.join(3)
    assert not controller._worker.is_alive()
    assert controller.status()['run_duration_s']==seconds
    assert c.start.call_args.kwargs['run_duration_s']==seconds


def test_hosted_reset_executes_in_the_host_without_a_remote_runner(tmp_path,monkeypatch):
    """The hosted factory owns the actual session policy, not a Mac proxy."""
    from remote_yam.controller import RunnerController
    from remote_yam.session import MockSessionAPI
    from remote_yam.resets.session_policy import CubeSessionPolicy
    station=tmp_path/'station.json'
    station.write_text(json.dumps(dict(resources={},io_routes={},transport=dict(ssh='inert'))))
    spec=dict(robot_id='yam-1',model='hosted-reset-v1',label='Reset bin',task='Reset bin',help='Reset',
              execution='session_cube',session_config=str(station),default_run_duration_s=600)
    settings=tmp_path/'policies.json';settings.write_text(json.dumps(dict(reset_bin=spec)))
    monkeypatch.setenv('YAM_CONFIGURED_RUNNERS_FILE',str(settings))
    class Base:
        def __init__(self,**kwargs):self.kwargs=kwargs;self.visitors={}
        def launch(self,visitor,payload,**kwargs):return payload
    class App(ConfiguredPoliciesMixin,Base):pass
    class Camera:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
    with patch('remote_yam.configured_policy_hosting.RemoteRunnerPolicy',side_effect=AssertionError('Mac proxy used')):
        app=App(robot_id='yam-1')
        policy=app.kwargs['extra_providers']['reset_bin'](spec['model'],tmp_path/'recording')
        assert isinstance(policy,CubeSessionPolicy)
        policy.io_factory=Camera
        contexts=[]
        def cube(config,output,**kwargs):
            contexts.append(kwargs['shared_io'].context)
            return dict(state='complete',goals_reached=True,request_id=kwargs['request_id'])
        policy.cube_runner=cube
        api=MockSessionAPI();controller=RunnerController(api)
        controller.join_and_run(policy,'Reset bin')
        controller._worker.join(3)
        assert not controller._worker.is_alive()
        assert len(api.create_requests)==1
        assert contexts[0]['session_id']==controller.status()['session_id']
        assert policy.public_config()['managed_execution']['phase']=='complete'
        assert controller.status()['error'] is None
    public=app.configured_public_config()['reset_bin']
    assert public['default_run_duration_s']==600
    assert 'session_config' not in public and 'execution' not in public
    assert not App(robot_id='other').configured_policies


def test_hosted_api_client_includes_admission_fields_and_keeps_visitor_authority():
    c=RunnerPolicyClient('https://playground.example');requests=[]
    replies=[dict(csrf='test-token',configured_providers=dict(reset_bin=dict(model='hosted-v1',task='Reset bin'))),
             dict(attempt_id='hosted-attempt',status='queued'),dict(attempt_id='hosted-attempt',status='running'),dict(ok=True)]
    def open(req,**kwargs):
        requests.append(req)
        return io.BytesIO(json.dumps(replies.pop(0)).encode())
    c.opener=SimpleNamespace(open=open)
    c.connect();c.cookie='visitor=test-only'
    c.start(email='operator@example.com',runner_name='Remote operator')
    c.stop()
    payload=json.loads(requests[1].data)
    assert payload['email']=='operator@example.com' and payload['runner_name']=='Remote operator'
    assert payload['model']=='hosted-v1' and payload['prompt']=='Reset bin'
    assert [r.full_url.rsplit('/',1)[1] for r in requests]==['session','run','status','stop']
    assert requests[1].get_header('Cookie')=='visitor=test-only'
    assert requests[1].get_header('X-yam-runner-token')=='test-token'
    assert requests[3].get_header('X-yam-runner-token')=='test-token'


def test_hosted_cli_sends_email_and_name_without_a_second_start(tmp_path,monkeypatch):
    import runpy
    from pathlib import Path
    example=Path(__file__).resolve().parents[1]/'examples/reset_environment.py'
    module=runpy.run_path(str(example));clients=[]
    class Client:
        def __init__(self,origin,robot):self.origin=origin;self.robot=robot;self.calls=[];clients.append(self)
        def connect(self):return dict(robot_id=self.robot)
        def save(self,path):pass
        def start(self,policy,**kwargs):self.calls.append((policy,kwargs));return dict(attempt_id='test-attempt')
        def status(self):return dict(status='stopped',provider=dict(managed_execution=dict(phase='complete',result=dict(goals_reached=True))))
    module['main'].__globals__['RunnerPolicyClient']=Client
    assert module['main'](['--origin','https://playground.example','--start','--wait',
        '--email','operator@example.com','--runner-name','Remote operator',
        '--session-file',str(tmp_path/'visitor.json')])==0
    assert clients[0].origin=='https://playground.example'
    assert clients[0].calls==[('reset_bin',dict(email='operator@example.com',runner_name='Remote operator'))]
