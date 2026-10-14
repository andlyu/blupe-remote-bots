"""Opt-in cross-repository test: real gateway/API/runner, in-memory motor IO only.

Set BLUPE_HOME_SCENE_STATION to the companion controller checkout and
BLUPE_HOME_SCENE_API to the companion API checkout. No hardware/network model.
"""
import base64
import importlib
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
from unittest.mock import patch

import pytest

STATION = os.environ.get('BLUPE_HOME_SCENE_STATION')
API = os.environ.get('BLUPE_HOME_SCENE_API')
pytestmark = pytest.mark.skipif(not STATION or not API, reason='companion checkouts not supplied')


def wait_for(predicate, timeout=40):
    end=time.monotonic()+timeout
    while not predicate():
        if time.monotonic()>end:raise AssertionError('Timed out waiting for simulated lifecycle')
        time.sleep(.025)


@pytest.mark.parametrize('transport',['astra','codex'])
def test_real_station_api_runner_contract(tmp_path,monkeypatch,transport):
    sys.path[:0]=[str(Path(STATION)/'src/blupe_controller/runtime'),str(Path(API)/'src')]
    import uvicorn
    from blupe_evals.session_api import SessionApiService,SessionApiAsgi
    from scripts import yam_operator_hardware_web as hardware
    from YAM_control.home_scene import install
    from YAM_control.i2rt_bimanual_adapter import I2RTBimanualAdapter
    from YAM_control.simulated_driver import SimulatedBus
    from YAM_control.motor_shutdown import disable_motorchain
    from YAM_control.session_api_sim_client import SessionApiSimClient
    from remote_yam.controller import RunnerController
    from remote_yam.session import HttpSessionAPI
    from remote_yam.cameras import CameraFrame
    from remote_yam.codex_policy import CodexAdapter
    from remote_yam.robocurve_policy import AstraAdapter
    from test_codex_policy import decision,events
    from test_robocurve_policy import response
    assert Path(hardware.__file__).is_relative_to(Path(STATION))
    assert Path(importlib.import_module('blupe_evals.session_api.home_scene').__file__).is_relative_to(Path(API))
    monkeypatch.delenv('YAM_DATASET_ROOT',raising=False)
    monkeypatch.setenv('YAM_AUTO_QUEUE_STATE',str(tmp_path/'queue.json'))
    parent=hardware.PhysicalOperator
    install(hardware,dict(robot_id='yam-1',cameras={'left':10,'right':4,'top':16}),tmp_path/'scene.json')
    bus=SimulatedBus()
    adapter=I2RTBimanualAdapter(left_gripper_limits=(6.3,1.15),right_gripper_limits=(6.4,1.14),
        robot_factory=bus.factory,robot_disabler=disable_motorchain,channel_ready=lambda _:True)
    op=hardware.PhysicalOperator(adapter=adapter)
    hardware.PhysicalOperator=parent
    op.training_simulated=True
    service=SessionApiService()
    token=secrets.token_urlsafe(32);token_file=tmp_path/'test-token';token_file.write_text(token)
    app=SessionApiAsgi(service,jetson_tokens={'yam-1':token})
    sock=socket.socket();sock.bind(('127.0.0.1',0));url=f'http://127.0.0.1:{sock.getsockname()[1]}'
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='on'))
    server_thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);server_thread.start()
    wait_for(lambda:server.started,10)
    bridge=SessionApiSimClient(op,url.replace('http:','ws:')+'/v1/jetsons/connect','yam-1',token_file)
    op.session_api_base=url;op.camera_reference_base='http://127.0.0.1:0';op.attach_api_client(bridge);bridge.start()
    wait_for(lambda:op.api_connected,10)
    jpeg=b'\xff\xd8stable-simulated-scene\xff\xd9'
    def frame(name,device):
        return name,dict(jpeg=jpeg,monotonic=time.monotonic(),sequence=1)
    monkeypatch.setattr('YAM_control.home_scene.capture_frame',frame)
    class Cameras:
        data=jpeg
        def capture(self,obs):
            return [CameraFrame(n,self.data,time.time(),source_captured_at=time.time()) for n in ('left','top','right')]
    runners=[];providers=[];evidence=[]
    try:
        op.action('launch');op.action('park');assert op.auto_queue.parked
        op.action('auto_queue_on')
        for scenario in ('cold','hit','changed'):
            calls=[]
            waiting_for_stop=threading.Event()
            def finish_or_wait_for_stop():
                if scenario=='cold':
                    waiting_for_stop.set()
                    end=time.monotonic()+10
                    while not provider.cancelled() and time.monotonic()<end:
                        time.sleep(.005)
                    assert provider.cancelled(), 'Normal Stop did not cancel inference'
                    raise RuntimeError('test inference cancelled by normal Stop')
            camera=Cameras()
            if scenario=='changed':camera.data=b'\xff\xd8objects-rearranged\xff\xd9'
            if transport=='codex':
                with patch('remote_yam.codex_policy.codex_status',return_value={'ready':True}), patch('remote_yam.codex_policy.codex_binary',return_value='/no-external-cli'):
                    provider=CodexAdapter(camera_source=camera)
                def execute(command,prompt,root):
                    calls.append((time.monotonic(),'Saved home scene' in prompt))
                    assert '--image' in command
                    if not provider._pending and len(provider._history)<5:
                        move=decision('move_to',note='Close left slightly');move['targets']['left_gripper']=.9
                        return events(move)
                    finish_or_wait_for_stop()
                    return events(decision())
                provider._execute=execute
            else:
                provider=AstraAdapter('test-key','gpt-6-astra','http://127.0.0.1:0/responses',camera_source=camera)
                def send(req):
                    payload=json.loads(req.data)
                    calls.append((time.monotonic(),'Saved home scene' in str(payload)))
                    if len(provider._history)<5:
                        return response('move_to',{'targets':{'left_gripper':.9},'note':'Close left slightly'})
                    finish_or_wait_for_stop()
                    return response('done',{'summary':'simulated task finished','hindsight':'none'},'done')
                provider._send_json=send
            api=HttpSessionAPI(url,supports_trajectories=True)
            runner=RunnerController(api,share_conversation=False)
            runners.append(runner);providers.append(provider)
            runner.join_and_run(provider,'close the left gripper slightly')
            wait_for(lambda:runner._home_registered,5)
            run_started=time.monotonic()
            # Real queue tick owns launch, home, and handoff. No fake lifecycle.
            op.auto_queue.tick()
            if scenario=='cold':
                wait_for(waiting_for_stop.is_set)
                runner.stop('user_requested')
            wait_for(lambda:runner._worker is not None and not runner._worker.is_alive())
            state=runner.status()
            assert state['error'] is None,state
            assert state['commands_submitted']>0,state
            trace=service.get_episode_trace(state['session_id'])
            accepted=[r for r in trace['trajectory_results'] if r['status']=='accepted']
            assert len(accepted)==1,trace['trajectory_results']
            wait_for(lambda:op.auto_queue.completion_pending,5)
            op.auto_queue.tick()
            assert op.auto_queue.parked and op._physical.torque_off_verified
            assert op.home_scene.scene is not None and (tmp_path/'scene.json').exists()
            events_log=runner._interactions.snapshot()["events"]
            states=[e.get('details',{}).get('state') for e in events_log if e['kind']=='home_scene']
            if scenario=='hit':assert 'hit' in states,(states,calls)
            if scenario=='changed':assert 'fallback' in states,(states,calls)
            if scenario!='cold':
                assert calls[0][1] is True
                assert calls[0][0] < op.home_scene.timing['home_ready_monotonic']
            assert len(service._home_samples)==1
            samples=next(iter(service._home_samples.values()))
            assert len(samples)==len(evidence)+1
            assert all(0<v<5 for v in samples)
            evidence.append(dict(transport=transport,scenario=scenario,states=states,
                calls=len(calls),sample_count=len(samples),measured_first_plan_s=samples[-1],
                startup=op.home_scene.timing))
        # Cancel the next queued run while its model and real launch overlap.
        # Hold the simulator's launch return so the queue disappears before Home.
        previous_capture=(tmp_path/'scene.json').read_bytes()
        model_entered=threading.Event();release_launch=threading.Event()
        if transport=='codex':
            with patch('remote_yam.codex_policy.codex_status',return_value={'ready':True}), patch('remote_yam.codex_policy.codex_binary',return_value='/no-cli'):
                pending=CodexAdapter(camera_source=Cameras())
        else:
            pending=AstraAdapter('test-key','gpt-6-astra','http://127.0.0.1:0/responses',camera_source=Cameras())
        def blocking_model(*args):
            model_entered.set()
            end=time.monotonic()+10
            while not pending.cancelled() and time.monotonic()<end:
                time.sleep(.005)
            raise RuntimeError('test request cancelled')
        if transport=='codex':pending._execute=blocking_model
        else:pending._send_json=blocking_model
        providers.append(pending)
        cancelled_runner=RunnerController(HttpSessionAPI(url,supports_trajectories=True),share_conversation=False)
        runners.append(cancelled_runner)
        cancelled_runner.join_and_run(pending,'cancel during startup')
        wait_for(lambda:cancelled_runner._home_registered,5)
        original_launch=op._launch_physical
        def held_launch(**kwargs):
            result=original_launch(**kwargs)
            assert release_launch.wait(10)
            return result
        with patch.object(op,'_launch_physical',side_effect=held_launch), patch.object(op,'_move_home',wraps=op._move_home) as home_spy:
            startup=threading.Thread(target=op.auto_queue.tick)
            startup.start()
            try:
                assert model_entered.wait(5)
                # The model thread can start before its job is assigned to the
                # runner. Observe both before checking cancellation joins it.
                wait_for(lambda:cancelled_runner._home_plan is not None,5)
                job=cancelled_runner._home_plan
                cancelled_runner.stop()
                assert not job.thread.is_alive()
            finally:
                release_launch.set();startup.join(15)
            assert not startup.is_alive()
            home_spy.assert_not_called()
        assert cancelled_runner.status()['commands_submitted']==0
        assert (tmp_path/'scene.json').read_bytes()==previous_capture
        assert op.auto_queue.parked and op._physical.torque_off_verified
        evidence.append(dict(transport=transport,scenario='cancel_during_startup',commands=0,extra_home=False,capture_unchanged=True))
        print('HOME_SCENE_INTEGRATION '+json.dumps(evidence,sort_keys=True))
    finally:
        op.auto_queue.pause('test shutdown');op.stop_event.set()
        for runner in runners:runner.stop('test_shutdown')
        bridge.stop();bus.cleanup();server.should_exit=True;server_thread.join(5);sock.close()
        for provider in providers:
            if hasattr(provider,'_workspace'):provider._workspace.cleanup()
