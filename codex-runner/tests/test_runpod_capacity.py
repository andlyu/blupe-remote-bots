from unittest.mock import Mock
import pytest
from remote_yam import runpod_capacity as capacity

@pytest.mark.parametrize('pod,expected', [('EXITED',False),('RUNNING',True),('STARTING',None),(None,None)])
def test_worker_idle_alone_is_not_proof_of_a_warm_gpu(monkeypatch,pod,expected):
    read=Mock(side_effect=[{'workers':[{'id':'worker1','status':'IDLE'}]},{'status':pod}])
    monkeypatch.setattr(capacity,'_read',read)
    result=capacity.capacity_snapshot('endpoint1','secret')
    assert result['available'] is expected
    assert result['workers'][0]['pod_status']==pod
    assert 'secret' not in str(result)


def test_unavailable_control_api_is_unknown_and_empty_capacity_is_cold(monkeypatch):
    read=Mock(side_effect=TimeoutError)
    monkeypatch.setattr(capacity,'_read',read)
    assert capacity.capacity_snapshot('endpoint1','secret')['available'] is None
    read.side_effect=None;read.return_value={'workers':[]}
    assert capacity.capacity_snapshot('endpoint1','secret')['available'] is False
    read.reset_mock()
    assert capacity.capacity_snapshot('../bad','secret')['available'] is None
    read.assert_not_called()


def test_capacity_read_uses_only_fixed_control_host_bounded_get_and_no_redirect(monkeypatch):
    connection=Mock();reply=Mock(status=302);reply.read.return_value=b'{}'
    connection.getresponse.return_value=reply
    factory=Mock(return_value=connection)
    monkeypatch.setattr(capacity.http.client,'HTTPSConnection',factory)
    with pytest.raises(ValueError):capacity._read('serverless/endpoint1/workers','secret')
    factory.assert_called_once_with('api.runpod.io',timeout=2)
    assert connection.request.call_args.args==('GET','/v2/serverless/endpoint1/workers')
    reply.read.assert_called_once_with(1024*1024+1)
    connection.close.assert_called_once()
