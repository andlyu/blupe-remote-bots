import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from remote_yam.runner_policy_client import RunnerPolicyClient


def response(value):return io.BytesIO(json.dumps(value).encode())


def test_client_uses_existing_policy_fields_once_and_retains_stop_authority(tmp_path):
    client=RunnerPolicyClient();client.cookie='fixture=not-a-credential'
    opened=[]
    replies=[dict(csrf='fixture-token',configured_providers=dict(reset_bin=dict(model='reset-bin-v1',task='Reset bin'))),
             dict(attempt_id='fixture-run',ok=True,status='running'),dict(attempt_id='fixture-run',status='running'),
             dict(attempt_id='fixture-run',status='running'),dict(ok=True)]
    def open(request,**kw):opened.append(request);return response(replies.pop(0))
    client.opener=SimpleNamespace(open=open)
    client.connect();client.start();assert client.status()['attempt_id']=='fixture-run'
    path=tmp_path/'session.json';client.save(path)
    assert path.stat().st_mode&0o777==0o600
    restored=RunnerPolicyClient.load(path);assert restored.cookie==client.cookie and restored.attempt_id==client.attempt_id
    client.stop()
    assert [r.full_url.rsplit('/',1)[1] for r in opened]==['session','run','status','status','stop']
    payload=json.loads(opened[1].data)
    assert payload==dict(provider='reset_bin',model='reset-bin-v1',prompt='Reset bin',runner_name='API operator',run_duration_s=600)
    assert opened[1].get_header('X-yam-runner-token')=='fixture-token'
    assert opened[1].get_header('X-blupe-robot')=='yam-1'


def test_client_refuses_missing_policy_without_start_and_never_retries_write():
    client=RunnerPolicyClient();client.metadata=dict(configured_providers={})
    client.opener=Mock()
    with pytest.raises(ValueError,match='not installed'):client.start()
    client.opener.open.assert_not_called()
    client.metadata=dict(configured_providers=dict(reset_bin=dict(model='reset-bin-v1',task='Reset bin')))
    client.opener.open.side_effect=TimeoutError('uncertain start')
    with pytest.raises(TimeoutError):client.start()
    assert client.opener.open.call_count==1


def test_plaintext_nonloopback_origins_and_replaced_run_are_refused():
    with pytest.raises(ValueError):RunnerPolicyClient('http://untrusted.example')
    client=RunnerPolicyClient();client.attempt_id='old'
    client.opener=SimpleNamespace(open=lambda *a,**k:response(dict(attempt_id='new')))
    with pytest.raises(RuntimeError,match='different run'):client.stop()
