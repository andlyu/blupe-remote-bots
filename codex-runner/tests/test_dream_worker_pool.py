"""Prepared process reuse, public SDK reset and cancelled-reply isolation."""
import json
from pathlib import Path
import sys
import threading
import time

import pytest

from remote_yam.dream_worker_pool import DreamWorkerPool
from remote_yam.dream_policy import MODELS


def wait_for(check, timeout=5):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if check(): return
        time.sleep(.01)
    assert check()


@pytest.fixture
def resident(tmp_path, monkeypatch):
    sdk=tmp_path/'sdk';sdk.mkdir()
    trace=tmp_path/'trace.jsonl';hold=tmp_path/'hold';release=tmp_path/'release';fail=tmp_path/'fail-reset'
    (sdk/'dream.py').write_text('''
import json, os, threading, time
from pathlib import Path
from types import SimpleNamespace
__version__='1.0.0'
def log(kind, **values):
    with open(os.environ['TEST_TRACE'],'a') as out:out.write(json.dumps(dict(kind=kind,**values))+'\\n')
class DreamClient:
    last_timing={'rtt_ms':1}
    def __init__(self):
        self.frames=[];self.session_id=None
        event=threading.Event();event.set()
        self._policy=SimpleNamespace(_ik=SimpleNamespace(traj_ready=event))
    def policy(self, config):
        self.checkpoint=config['checkpoint'];log('policy',checkpoint=self.checkpoint)
        assert config['ik']=={'arm':'yam','head':'eef','solve':'traj'} and config['_record'] is False
    def set_observation(self, frames, state, timestamp):
        self.frames.append(state['prompt'])
    def get_action(self, commanded=None):
        assert self.frames
        log('predict-start',frames=list(self.frames),session_id=self.session_id,checkpoint=self.checkpoint,commanded=commanded)
        while Path(os.environ['TEST_HOLD']).exists() and not Path(os.environ['TEST_RELEASE']).exists():time.sleep(.01)
        self.session_id='synthetic-session'
        log('predict-end',frames=list(self.frames))
        return {key:[[0.]*6+[.5] for _ in range(48)] for key in ['q_l_chunk','q_r_chunk']}
    def reset_episode(self):
        if Path(os.environ['TEST_FAIL_RESET']).exists():raise RuntimeError('synthetic reset failure')
        log('reset',frames=list(self.frames),session_id=self.session_id)
        self.frames=[];self.session_id=None
    def close(self):log('close')
''')
    for name,value in dict(PYTHONPATH=sdk,TEST_TRACE=trace,TEST_HOLD=hold,TEST_RELEASE=release,TEST_FAIL_RESET=fail).items():
        monkeypatch.setenv(name,str(value))
    credentials=tmp_path/'synthetic-credentials'
    credentials.write_text('synthetic')
    pool=DreamWorkerPool(sys.executable,credentials,tmp_path/'worker')
    try:
        reply=pool.prime(timeout=10)
        assert reply['result']['fully_ready']
        yield pool,credentials,trace,hold,release,fail
    finally:pool.close()


def loan(pool,credentials,tmp_path,checkpoint):
    worker=pool.factory(sys.executable,credentials,tmp_path)
    assert worker.call('configure',checkpoint=checkpoint)['result']['prepared_reused']
    return worker


def ticks(prompt,timestamp=1):
    return [dict(timestamp=timestamp,frames={},observation={'prompt':prompt})]


def rows(trace):return [json.loads(line) for line in trace.read_text().splitlines()]


def test_fully_prepared_process_reuses_both_models_and_resets_every_visitor(resident,tmp_path):
    pool,credentials,trace,*_=resident
    pid=pool._worker.process.pid
    models=[v[0] for v in MODELS.values()]
    for i,checkpoint in enumerate([models[0],models[0],models[1],models[0]]):
        worker=loan(pool,credentials,tmp_path/str(i),checkpoint)
        assert worker.call('predict',ticks=ticks('visitor-'+str(i),10-i),commanded=None)['ok']
        worker.close();wait_for(lambda:not pool.status()['busy'])
        assert pool._worker.process.pid==pid and pool.status()['ready']
    records=rows(trace)
    assert [r['checkpoint'] for r in records if r['kind']=='policy']==models
    predictions=[r for r in records if r['kind']=='predict-start']
    assert [r['frames'] for r in predictions]==[['visitor-'+str(i)] for i in range(4)]
    assert all(r['session_id'] is None and r['commanded'] is None for r in predictions)


def test_stop_returns_promptly_but_next_visitor_waits_for_reply_drain_and_reset(resident,tmp_path):
    pool,credentials,trace,hold,release,_=resident
    first=loan(pool,credentials,tmp_path/'first',MODELS['dream'][0]);hold.touch()
    cancelled=threading.Event();errors=[]
    def predict():
        try:first.call('predict',ticks=ticks('old-visitor'),cancelled=cancelled.is_set)
        except RuntimeError as error:errors.append(str(error))
    thread=threading.Thread(target=predict);thread.start()
    wait_for(lambda:any(r['kind']=='predict-start' for r in rows(trace)))
    started=time.monotonic();cancelled.set();first.close();thread.join(1)
    assert not thread.is_alive() and time.monotonic()-started<.5 and errors
    second=pool.factory(sys.executable,credentials,tmp_path/'second');configured=threading.Event()
    def configure():
        assert second.call('configure',checkpoint=MODELS['dream'][0])['ok'];configured.set()
    next_thread=threading.Thread(target=configure);next_thread.start()
    assert not configured.wait(.1)
    release.touch();next_thread.join(2);assert configured.is_set()
    assert second.call('predict',ticks=ticks('new-visitor',.5))['ok']
    second.close();wait_for(lambda:not pool.status()['busy'])
    predictions=[r for r in rows(trace) if r['kind']=='predict-start']
    assert [r['frames'] for r in predictions]==[['old-visitor'],['new-visitor']]
    assert all(r['session_id'] is None for r in predictions)


def test_waiting_visitor_can_cancel_without_closing_owner(resident,tmp_path):
    pool,credentials,_,*_=resident
    first=loan(pool,credentials,tmp_path/'first',MODELS['dream'][0])
    second=pool.factory(sys.executable,credentials,tmp_path/'second');errors=[]
    def configure():
        try:second.call('configure',checkpoint=MODELS['dream'][0])
        except RuntimeError:errors.append('cancelled')
    thread=threading.Thread(target=configure);thread.start();second.close();thread.join(1)
    assert errors and not thread.is_alive()
    assert first.call('predict',ticks=ticks('owner'))['ok']
    first.close();wait_for(lambda:not pool.status()['busy'])


def test_failed_reset_discards_process_before_reuse(resident,tmp_path):
    pool,credentials,_,_,_,fail=resident
    worker=loan(pool,credentials,tmp_path/'first',MODELS['dream'][0])
    physical=pool._worker
    assert worker.call('predict',ticks=ticks('first'))['ok']
    fail.touch();worker.close();wait_for(lambda:not pool.status()['busy'])
    assert not pool.status()['ready'] and physical.process.poll() is not None
    next_worker=pool.factory(sys.executable,credentials,tmp_path/'second')
    with pytest.raises(RuntimeError,match='unavailable'):
        next_worker.call('configure',checkpoint=MODELS['dream'][0])
    next_worker.close()


def test_prepared_credentials_cannot_be_replaced(resident,tmp_path):
    pool,_,_,*_=resident
    with pytest.raises(ValueError,match='credentials/interpreter differ'):
        pool.factory(sys.executable,tmp_path/'different-key',tmp_path)


def test_rotated_credentials_require_new_preparation(resident,tmp_path):
    pool,credentials,_,*_=resident
    credentials.write_text('rotated synthetic credential')
    with pytest.raises(ValueError,match='credentials/interpreter differ'):
        pool.factory(sys.executable,credentials,tmp_path)


def test_transport_failure_does_not_reuse_a_broken_process(resident,tmp_path):
    pool,credentials,_,*_=resident
    worker=loan(pool,credentials,tmp_path/'first',MODELS['dream'][0])
    pool._worker.process.kill();pool._worker.process.wait()
    with pytest.raises(RuntimeError):worker.call('predict',ticks=ticks('first'))
    worker.close();wait_for(lambda:not pool.status()['busy'])
    assert not pool.status()['ready']


def test_hosted_readiness_gate_and_lease_hook_use_resident_factory(resident,tmp_path):
    import asyncio
    import shutil
    from types import SimpleNamespace
    import test_hosted
    from remote_yam.session import MockSessionAPI
    pool,credentials,trace,*_=resident
    admitted={'ready':False};semaphore=threading.BoundedSemaphore(1)
    app=test_hosted.hosted.HostedRunner(public_origin='https://robot.example',
        session_api='https://session.example',camera_origin='https://session.example',
        api_factory=lambda:MockSessionAPI(auto_activate=False),share_conversation=False,
        dream_credentials_file=str(credentials),dream_python=sys.executable,
        dream_worker_pool=semaphore,dream_worker_factory=pool.factory,
        dream_worker_ready=lambda:admitted['ready'] and pool.status()['ready'])
    try:
        _,config,_=asyncio.run(test_hosted.HostedTests.call(SimpleNamespace(app=app),'/api/session',method='POST'))
        assert not config['dream_providers']
        visitor=next(iter(app.visitors.values()))
        payload=dict(provider='dream',model=MODELS['dream'][0],prompt='synthetic fixture')
        with pytest.raises(test_hosted.hosted.RequestError) as caught:app.launch(visitor,payload)
        assert caught.value.status==503 and not visitor.controller._session_api.create_requests
        admitted['ready']=True
        app.launch(visitor,payload)
        assert visitor.controller.status()['status']=='queued'
        assert not pool.status()['busy'] and not any(r['kind']=='predict-start' for r in rows(trace))
        visitor.controller._handle_event(dict(schema_version=1,type='lifecycle',
            session_id=visitor.controller._session_id,episode_id='fixture',
            payload={'state':'preparing','reason':'jetson_leased'}))
        wait_for(lambda:visitor.controller._provider._ready.is_set())
        assert pool.status()['busy']
        visitor.controller.stop();wait_for(lambda:not pool.status()['busy'])
        assert semaphore.acquire(blocking=False);semaphore.release()
        assert pool.status()['ready'] and len([r for r in rows(trace) if r['kind']=='policy'])==2
    finally:
        for visitor in app.visitors.values():visitor.close()
        shutil.rmtree(app.root,ignore_errors=True)
