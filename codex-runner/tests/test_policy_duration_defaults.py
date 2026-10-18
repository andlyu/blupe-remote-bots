"""Configured defaults reach real controller/API requests without hardware."""
import asyncio
import json
import shutil
from unittest.mock import patch

import pytest

from local_playground import LocalPlayground
from playground import HostedRunner
from remote_yam.configured_policy_hosting import ConfiguredPoliciesMixin
from remote_yam.policy_defaults import default_run_duration
from remote_yam.session import MockSessionAPI


class Hosted(ConfiguredPoliciesMixin, HostedRunner):
    pass


class QueuedPolicy:
    provider_name = 'reset_bin'
    model = 'configured-reset'
    def public_config(self):
        return dict(provider='reset_bin',model='configured-reset')
    def infer(self,*args):
        raise AssertionError('No policy inference or motion in duration test')


@pytest.mark.parametrize('kind',['hosted','local'])
@pytest.mark.parametrize('provider,explicit,expected',[
    ('reset_bin',None,600),('reset_bin',180,180),('local_raise_lower',None,300)])
def test_configured_default_metadata_and_actual_queue_duration(tmp_path,monkeypatch,kind,provider,explicit,expected):
    spec=dict(robot_id='yam-1',label='Reset bin',model='configured-reset',task='Reset bin',help='Reset',
        default_run_duration_s=600,runner_origin='http://127.0.0.1:8787',
        command=['/inert/python','{output}','{request_id}'])
    path=tmp_path/'policies.json'
    if kind=='hosted':
        path.write_text(json.dumps(dict(reset_bin=spec)));monkeypatch.setenv('YAM_CONFIGURED_RUNNERS_FILE',str(path))
    else:
        path.write_text(json.dumps(dict(schema='blupe-managed-policies-v1',policies=dict(reset_bin=spec))))
        monkeypatch.setenv('YAM_LOCAL_POLICY_CONFIG',str(path))
    api=MockSessionAPI(auto_activate=False)
    with patch('remote_yam.configured_policy_hosting.RemoteRunnerPolicy',lambda *a:QueuedPolicy()), \
         patch('remote_yam.managed_command_policy.ManagedCommandPolicy',lambda *a:QueuedPolicy()):
        cls=Hosted if kind=='hosted' else LocalPlayground
        app=cls(public_origin='http://127.0.0.1:8791',development=True,session_api=None,
                camera_origin='http://127.0.0.1:8089',hardware_control=True,api_factory=lambda:api)
        try:
            _,visitor=app.new_visitor()
            metadata,_=asyncio.run(app.session_extension({},visitor))
            assert metadata['configured_providers']['reset_bin']['default_run_duration_s']==600
            payload=dict(provider=provider,model='configured-reset',prompt='Reset bin',runner_name='Duration fixture')
            if explicit is not None:payload['run_duration_s']=explicit
            app.launch(visitor,payload)
            assert visitor.controller.status()['run_duration_s']==expected
            assert api.create_requests[0].get('run_duration_s',300)==expected
        finally:
            for visitor in app.visitors.values():
                visitor.controller.stop()
                if visitor.controller._worker:visitor.controller._worker.join(3)
            shutil.rmtree(app.root,ignore_errors=True)


def test_other_configured_provider_default_is_unchanged():
    assert default_run_duration({})==300


@pytest.mark.parametrize('value',[None,True,30,601,90])
def test_invalid_configured_minute_default_is_rejected(value):
    with pytest.raises(ValueError):default_run_duration(dict(default_run_duration_s=value))
