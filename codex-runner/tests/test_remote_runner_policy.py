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
