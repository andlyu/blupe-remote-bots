"""Prepared process reuse, public SDK reset and cancelled-reply isolation."""
import json
from pathlib import Path
import sys
import threading
import time

import pytest

from remote_yam.dream_worker_pool import DreamWorkerPool
from remote_yam.dream_policy import DreamAdapter, DreamWorker, DreamWorkerUnavailable, MODELS


def wait_for(check, timeout=5):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if check(): return
        time.sleep(.01)
    assert check()


def test_native_bounds_survive_replacement_and_require_worker_acknowledgement(tmp_path):
    from types import SimpleNamespace
    from remote_yam.dream_joint_bounds import bounds_sha256
    commands = []
    class Worker:
        def __init__(self, *args): self.process = SimpleNamespace(poll=lambda: None)
        def call(self, kind, **kwargs):
            commands.append((kind, kwargs))
            return dict(ok=True, result=dict(fully_ready=True,
                joint_bounds_sha256=bounds_sha256(kwargs['joint_bounds'])))
        def close(self): pass
    credentials = tmp_path/'key'; credentials.write_text('synthetic')
    pool = DreamWorkerPool('unused', credentials, tmp_path/'worker', worker_factory=Worker)
    try:
        pool.configure_joint_bounds([-2.] * 12, [1.5] * 12)
        pool.prime()
        with pytest.raises(RuntimeError, match='before Dream preparation'):
            pool.configure_joint_bounds([-2.] * 12, [1.6] * 12)
        pool._discard()
        pool.prime()
        assert len(commands) == 2 and commands[0][1]['joint_bounds'] == commands[1][1]['joint_bounds']
        assert pool.status()['joint_bounds_sha256'] == bounds_sha256(commands[0][1]['joint_bounds'])
        pool._discard()
        Worker.call = lambda *args, **kwargs: dict(ok=True, result=dict(fully_ready=True))
        with pytest.raises(RuntimeError, match='bounds were not prepared'):
            pool.prime()
        assert not pool.status()['ready']
    finally:
        pool.close()


@pytest.fixture
def resident(tmp_path, monkeypatch):
    sdk=tmp_path/'sdk';sdk.mkdir()
    trace=tmp_path/'trace.jsonl';hold=tmp_path/'hold';release=tmp_path/'release';fail=tmp_path/'fail-reset'
    (sdk/'dream.py').write_text('''
import json, os, threading, time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
__version__='1.0.0'
def log(kind, **values):
    with open(os.environ['TEST_TRACE'],'a') as out:out.write(json.dumps(dict(kind=kind,**values))+'\\n')
def _solve_traj(*args):
    log('prepared-variant',variant='independent' if args[-2] is None else 'coupled')
    return [np.zeros((48,6)),np.zeros((48,6))]
class Solver:
    sides=('right','left')
    side_rest=np.zeros((2,6))
    side_base=np.zeros((2,3))
    def fk(self,q,side):return np.eye(4)
    def solve_traj(self,targets,rest,history,speed,serve):
        return _solve_traj(*range(10),None,{'unchanged':True})
class DreamClient:
    last_timing={'rtt_ms':1}
    def __init__(self):
        self.frames=[];self.positions=[];self.session_id=None
        event=threading.Event();event.set()
        self._policy=SimpleNamespace(_ik=SimpleNamespace(traj_ready=event,
            _solver=Solver(),_solve_spec=lambda:SimpleNamespace(solve='traj')))
    def policy(self, config):
        self.checkpoint=config['checkpoint'];log('policy',checkpoint=self.checkpoint)
        while Path(os.environ['TEST_HOLD']+'-prime').exists() and not Path(os.environ['TEST_RELEASE']).exists():time.sleep(.01)
        assert config['ik']=={'arm':'yam','head':'eef','solve':'traj'} and config['_record'] is False
    def set_observation(self, frames, state, timestamp):
        self.frames.append(state['prompt'])
        value=state.get('state.left_arm')
        self.positions.append(value.tolist() if hasattr(value,'tolist') else value)
    def get_action(self, commanded=None):
        assert self.frames
        log('predict-start',frames=list(self.frames),positions=list(self.positions),session_id=self.session_id,checkpoint=self.checkpoint,commanded=commanded)
        while Path(os.environ['TEST_HOLD']).exists() and not Path(os.environ['TEST_RELEASE']).exists():time.sleep(.01)
        self.session_id='synthetic-session'
        log('predict-end',frames=list(self.frames))
        return {key:[[0.]*6+[.5] for _ in range(48)] for key in ['q_l_chunk','q_r_chunk']}
    def reset_episode(self):
        if Path(os.environ['TEST_FAIL_RESET']).exists():raise RuntimeError('synthetic reset failure')
        log('reset',frames=list(self.frames),session_id=self.session_id)
        self.frames=[];self.positions=[];self.session_id=None
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
        assert reply['result']['trajectory_variants']=={
            checkpoint:['independent','coupled'] for checkpoint,_ in MODELS.values()}
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
    assert [r['variant'] for r in records if r['kind']=='prepared-variant']==[
        'independent','independent','coupled']*2
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


def fail_next_prediction(pool, release):
    """Use the real pipe deadline/termination path, shortened only for this test."""
    physical = pool._worker
    call = physical.call
    def short_deadline(command, **kwargs):
        if command == 'predict':
            kwargs['timeout'] = .15
        return call(command, **kwargs)
    physical.call = short_deadline
    def replacement(*args):
        assert physical.process.poll() is not None  # No overlapping SDK processes.
        release.touch()
        return DreamWorker(*args)
    pool.worker_factory = replacement
    return physical


def test_adapter_continues_same_step_after_timeout_with_fresh_context(resident, tmp_path):
    import math
    from test_dream_policy import Cameras, observation
    pool, credentials, trace, hold, release, _ = resident
    phase = {'degrees': 10, 'refreshes': 0}
    def feedback():
        return dict(observation(), left_joints_deg=[phase['degrees']] * 6)
    policy = DreamAdapter(provider='dream', model=MODELS['dream'][0], credentials=credentials,
        python=sys.executable, directory=tmp_path/'adapter', camera_source=Cameras(),
        observation_source=feedback, robot_id='yam-1', worker_factory=pool.factory)
    events = []
    policy.interaction_sink = lambda kind, message, **details: events.append((kind, details))
    def refresh():
        phase['degrees'] = 20
        phase['refreshes'] += 1
        return feedback()
    policy.refresh_observation = refresh
    try:
        first = policy.build_trajectory('same run', feedback(), 0)
        policy.trajectory_completed(feedback(), len(first))
        assert policy._commanded is not None
        physical = fail_next_prediction(pool, release)
        hold.touch()
        recovered = policy.build_trajectory('same run', feedback(), len(first))
        assert recovered[0]['step_id'] == len(first)
        assert phase['refreshes'] == 1 and pool.status()['ready'] and pool.status()['busy']
        assert physical.process.poll() is not None
        predictions = [row for row in rows(trace) if row['kind'] == 'predict-start']
        assert len(predictions) == 3  # Success, discarded timeout, one NEW prediction.
        assert predictions[1]['commanded'] is not None
        assert predictions[2]['commanded'] is None and predictions[2]['session_id'] is None
        assert all(position == pytest.approx([math.radians(20)]*6)
                   for position in predictions[2]['positions'])
        assert [d['state'] for k,d in events if k == 'worker_recovery'] == ['started','completed']
        # The allowance belongs to this run, not each build_trajectory call.
        fail_next_prediction(pool, release)
        release.unlink()
        with pytest.raises(DreamWorkerUnavailable, match='recovery is unavailable'):
            policy.build_trajectory('same run', feedback(), recovered[-1]['step_id']+1)
        assert phase['refreshes'] == 1
    finally:
        policy.close_transport()


def test_idle_dead_worker_is_prepared_again_without_any_prediction(resident):
    pool, _, trace, *_ = resident
    pool._recovery_delays = (.01, .01, .01)
    physical = pool._worker
    physical.process.kill(); physical.process.wait()
    wait_for(lambda: pool.status()['ready'] and pool._worker is not physical)
    assert not pool.status()['busy'] and physical.process.poll() is not None
    assert len([r for r in rows(trace) if r['kind'] == 'policy']) == 4
    assert not any(r['kind'] == 'predict-start' for r in rows(trace))


@pytest.mark.parametrize('window', [600., .001])
def test_failed_background_preparation_opens_circuit_after_three_attempts(resident, window):
    pool, _, _, *_ = resident
    pool._recovery_delays = (.01, .01, .01)
    pool._recovery_window = window  # Slow failures must not evade the burst cap.
    attempts = []
    def broken(*args):
        attempts.append(1)
        raise RuntimeError('synthetic preparation failure')
    pool.worker_factory = broken
    pool._discard(recover=True)
    wait_for(lambda: pool.status()['recovery_exhausted'])
    assert len(attempts) == 3 and not pool.status()['ready']
    time.sleep(.15)
    assert len(attempts) == 3 and pool._worker is None


def test_credential_rotation_blocks_background_replacement(resident):
    pool, credentials, _, *_ = resident
    pool._recovery_delays = (.01, .01, .01)
    physical = pool._worker
    credentials.write_text('rotated synthetic credentials')
    physical.process.kill(); physical.process.wait()
    time.sleep(.2)
    assert not pool.status()['ready'] and not pool.status()['preparing']
    assert pool.status()['recovery_attempts'] == 0 and not pool._recovery_pending
    assert pool._worker is physical


@pytest.mark.parametrize('cancel_kind', ['stop', 'deadline'])
def test_recovery_cancels_promptly_and_next_visitor_cannot_share_it(resident, tmp_path, cancel_kind):
    pool, credentials, trace, hold, release, _ = resident
    first = loan(pool, credentials, tmp_path/'first', MODELS['dream'][0])
    physical = pool._worker
    physical.process.kill(); physical.process.wait()
    with pytest.raises(DreamWorkerUnavailable):
        first.call('predict', ticks=ticks('old visitor'))
    Path(str(hold)+'-prime').touch()
    cancelled = threading.Event()
    errors = []
    def recover():
        try:
            first.recover(checkpoint=MODELS['dream'][0], cancelled=cancelled.is_set)
        except RuntimeError as error:
            errors.append(str(error))
    thread = threading.Thread(target=recover); thread.start()
    wait_for(lambda: pool.status()['preparing'])
    began = time.monotonic()
    if cancel_kind == 'deadline': cancelled.set()
    first.close(); thread.join(1)
    assert errors and not thread.is_alive() and time.monotonic()-began < .5
    second = pool.factory(sys.executable, credentials, tmp_path/'second')
    configured = threading.Event()
    def configure():
        second.call('configure', checkpoint=MODELS['dream'][0]); configured.set()
    next_thread = threading.Thread(target=configure); next_thread.start()
    assert not configured.wait(.1)
    release.touch(); next_thread.join(2)
    assert configured.is_set()
    assert second.call('predict', ticks=ticks('new visitor'))['ok']
    second.close(); wait_for(lambda: not pool.status()['busy'])
    predictions = [r for r in rows(trace) if r['kind'] == 'predict-start']
    assert [r['frames'] for r in predictions] == [['new visitor']]
    assert predictions[0]['session_id'] is None


def test_close_during_background_recovery_does_not_respawn(resident):
    pool, _, _, hold, _, _ = resident
    pool._recovery_delays = (.01, .01, .01)
    Path(str(hold)+'-prime').touch()
    pool._discard(recover=True)
    wait_for(lambda: pool.status()['preparing'] and pool._worker is not None)
    process = pool._worker.process
    pool.close()
    wait_for(lambda: process.poll() is not None and not pool.status()['preparing'])
    assert pool._worker is None and not pool.status()['ready']


@pytest.mark.parametrize('outcome', ['continue', 'deadline', 'stop', 'changed_lease'])
def test_hosted_run_recovery_preserves_session_and_never_submits_after_cancel(
        resident, tmp_path, monkeypatch, outcome):
    import shutil
    import test_hosted
    from test_dream_policy import Cameras
    from remote_yam.session import MockSessionAPI
    pool, credentials, trace, hold, release, _ = resident
    second_packet = threading.Event()
    finish_dispatch = threading.Event()
    class API(MockSessionAPI):
        def get_session(self, session_id):
            with self._lock:
                result = super().get_session(session_id)
                record = self._record(session_id)
                result.update(lease_id=record['lease_id'],
                              latest_observation_step=record['next_command_step'])
                if outcome == 'changed_lease' and pool.status()['recovery_attempts']:
                    result['lease_id'] = 'different-synthetic-lease'
                return result
        def submit_trajectory(self, *args, **kwargs):
            result = super().submit_trajectory(*args, **kwargs)
            if len(self.trajectory_log) == 2:
                second_packet.set()
                assert finish_dispatch.wait(5)
            return result
    api = API()
    monkeypatch.setattr(test_hosted.hosted, 'CameraFrameSource', lambda *a, **kw: Cameras())
    physical = pool._worker
    call = physical.call
    calls = []
    def fail_second(command, **kwargs):
        if command == 'predict':
            calls.append(1)
            if len(calls) == 2:
                hold.touch()
                kwargs['timeout'] = .15
                if outcome in {'deadline', 'stop'}:
                    Path(str(hold)+'-prime').touch()
        return call(command, **kwargs)
    physical.call = fail_second
    def replacement(*args):
        assert physical.process.poll() is not None
        if outcome not in {'deadline', 'stop'}:
            release.touch()
        return DreamWorker(*args)
    pool.worker_factory = replacement
    app = test_hosted.hosted.HostedRunner(public_origin='https://robot.example',
        session_api='https://session.example', camera_origin='https://session.example',
        api_factory=lambda: api, share_conversation=False,
        dream_credentials_file=str(credentials), dream_python=sys.executable,
        dream_worker_pool=threading.BoundedSemaphore(1), dream_worker_factory=pool.factory,
        dream_worker_ready=lambda: pool.status()['ready'])
    _, visitor = app.new_visitor()
    try:
        app.launch(visitor, dict(provider='dream', model=MODELS['dream'][0], prompt='synthetic run'))
        controller = visitor.controller
        if outcome == 'continue':
            assert second_packet.wait(5), controller.status().get('error')
            first, second = api.trajectory_log
            assert len(api.create_requests) == 1 and len(api._sessions) == 1
            assert first['episode_id'] == second['episode_id'] and first['lease_id'] == second['lease_id']
            assert second['waypoints'][0]['step_id'] == first['waypoints'][-1]['step_id']+1
            assert controller._run_duration_s == 120
        else:
            if outcome == 'changed_lease':
                wait_for(lambda: controller.status().get('error') is not None)
                assert 'Session changed before model retry' in controller.status()['error']
            else:
                wait_for(lambda: pool.status()['preparing'])
                if outcome == 'deadline':
                    with controller._lock:
                        controller._run_started_at = time.time()-121
                    wait_for(lambda: controller.status()['status'] == 'timed_out')
                    assert controller._provider is None
                else:
                    controller.stop()
                release.touch()
                wait_for(lambda: not pool.status()['busy'])
            assert len(api.trajectory_log) == 1 and not second_packet.is_set()
        predictions = [r for r in rows(trace) if r['kind'] == 'predict-start']
        assert len(predictions) == (3 if outcome == 'continue' else 2)
    finally:
        finish_dispatch.set(); release.touch(); visitor.close()
        shutil.rmtree(app.root, ignore_errors=True)
