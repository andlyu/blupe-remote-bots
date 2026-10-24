"""Dream launch limits reach the actual queue and controller cancellation clock."""
import asyncio
import shutil
from unittest.mock import patch

import pytest
import playground
import test_hosted
from remote_yam.dream_policy import MODELS
from remote_yam.session import MockSessionAPI


@pytest.mark.parametrize('robot_id',['yam-1','robot-ba8413962083809c'])
@pytest.mark.parametrize('provider',list(MODELS))
@pytest.mark.parametrize('seconds',[None,0,59,60,119,120,121,300,599,600,601,1199,1200,1201,True,120.0])
def test_dream_duration_boundary_before_queue_and_local_deadline(tmp_path,robot_id,provider,seconds):
    credentials=tmp_path/'credentials';credentials.write_text('synthetic only')
    api=MockSessionAPI(auto_activate=False)
    app=playground.HostedRunner(public_origin='https://robot.example',session_api='https://session.example',camera_origin='http://127.0.0.1:8089',robot_id=robot_id,
        api_factory=lambda:api,dream_credentials_file=str(credentials),dream_python='/inert/python')
    policy=test_hosted.HeldProvider('')
    policy.provider_name=provider
    app.extra_providers[provider]=lambda *args:policy
    try:
        metadata=app.dream_providers[provider]
        maximum = 1200
        assert metadata['default_run_duration_s']==120
        assert metadata['max_run_duration_s']==maximum
        harness=type('Harness',(),{'app':app})()
        code,session,headers=asyncio.run(test_hosted.HostedTests.call(harness,'/api/session',method='POST'))
        browser=dict(cookie=headers[b'set-cookie'].decode().split(';',1)[0],csrf=session['csrf'])
        payload=dict(provider=provider,model=MODELS[provider][0],prompt='Synthetic duration fixture')
        if seconds is not None:payload['run_duration_s']=seconds
        code,result,_=asyncio.run(test_hosted.HostedTests.call(harness,'/api/run',method='POST',payload=payload,**browser))
        visitor=next(iter(app.visitors.values()))
        if seconds is not None and (type(seconds) is not int or not 60 <= seconds <= maximum):
            assert code==400 and f'1 to {maximum // 60} minutes' in result['error']
            assert not api.create_requests and visitor.launches==0
        else:
            expected=120 if seconds is None else seconds
            assert code==200,result
            assert api.create_requests[0]['run_duration_s']==expected
            assert api.create_requests[0].get('provider')==(provider if expected > 600 else None)
            controller=visitor.controller
            assert controller.status()['run_duration_s']==expected
            with controller._lock:
                controller._status='running';controller._run_started_at=1000
                # Hold the same lock as the real snapshot handler, so a queued
                # background snapshot cannot overwrite this synthetic clock.
                with patch('remote_yam.controller.time.time',return_value=1000+expected-.001):
                    assert not controller._provider_cancelled(policy)
                with patch('remote_yam.controller.time.time',return_value=1000+expected):
                    assert controller._provider_cancelled(policy)
                controller._stop_event.set()
                with patch('remote_yam.controller.time.time',return_value=1000+expected/2):
                    assert controller._provider_cancelled(policy)
        assert not api.action_log and not api.trajectory_log
    finally:
        for visitor in app.visitors.values():
            visitor.controller.stop()
            if visitor.controller._worker:visitor.controller._worker.join(2)
        shutil.rmtree(app.root,ignore_errors=True)


@pytest.mark.parametrize('seconds',[None,600,601,1200])
def test_other_provider_duration_is_unchanged(tmp_path,seconds):
    api=MockSessionAPI(auto_activate=False)
    app=playground.HostedRunner(public_origin='https://robot.example',session_api='https://session.example',camera_origin='http://127.0.0.1:8089',api_factory=lambda:api)
    try:
        _,visitor=app.new_visitor()
        payload=dict(provider='local_raise_lower',prompt='Synthetic duration fixture')
        if seconds is not None:payload['run_duration_s']=seconds
        if seconds is not None and seconds > 600:
            with pytest.raises(playground.RequestError, match='1 to 10 minutes'):
                app.launch(visitor,payload)
            assert not api.create_requests
        else:
            app.launch(visitor,payload)
            assert api.create_requests[0].get('run_duration_s',300)==(300 if seconds is None else seconds)
    finally:
        for visitor in app.visitors.values():
            visitor.controller.stop()
            if visitor.controller._worker:visitor.controller._worker.join(2)
        shutil.rmtree(app.root,ignore_errors=True)
