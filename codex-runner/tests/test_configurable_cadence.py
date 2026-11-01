"""Cadence must survive admission/dispatch without changing playback or speed limits."""
import math

import pytest

from remote_yam.cadence import trajectory_cadence
from remote_yam.controller import RunnerController
from remote_yam.dream_policy import DreamAdapter, action_waypoints, motion_limited_waypoints
from remote_yam.providers import ScriptedAdapter, PolicyComplete
from remote_yam.session import HttpSessionAPI, MockSessionAPI, SessionAPIError, command_budget


def chunk():
    return {key: [[i / 10000] * 6 + [.5] for i in range(48)]
            for key in ('q_l_chunk', 'q_r_chunk')}


@pytest.mark.parametrize('rate,count,seconds', [(10,24,2.4), (20,48,2.4), (30,48,1.6)])
def test_dream_sampling_preserves_endpoint_and_selected_playback(rate, count, seconds):
    source = chunk()
    points = action_waypoints(source, 7, cadence_hz=rate)
    assert len(points) == count
    assert len(points) / rate == seconds
    assert [p['step_id'] for p in points] == list(range(7, 7 + count))
    assert points[-1]['left_joints_deg'] == pytest.approx([math.degrees(.0047)] * 6)
    assert points[-1]['right_gripper'] == .5


@pytest.mark.parametrize('rate', [10,20,30])
def test_motion_limits_preserve_joint_and_gripper_speed_at_every_rate(rate):
    observation = dict(left_joints_deg=[0]*6, right_joints_deg=[0]*6,
                       left_gripper=0, right_gripper=0)
    endpoint = dict(step_id=0, left_joints_deg=[40]*6, right_joints_deg=[-40]*6,
                    left_gripper=.6, right_gripper=.6)
    points = motion_limited_waypoints([endpoint], observation, 20, cadence_hz=rate)
    assert len(points) / rate == pytest.approx(.2)
    previous = observation
    for p in points:
        assert max(abs(a-b) for a,b in zip(p['left_joints_deg'],previous['left_joints_deg'])) * rate <= 200 + 1e-9
        assert abs(p['left_gripper']-previous['left_gripper']) * rate <= 3 + 1e-9
        previous = p
    assert points[-1]['left_joints_deg'] == endpoint['left_joints_deg']
    assert points[-1]['left_gripper'] == endpoint['left_gripper']


@pytest.mark.parametrize('rate', [None, True, False, '20', 0, -1, 15, 50, float('nan'), float('inf')])
def test_invalid_cadence_rejected_before_any_queue_or_motion(rate):
    api = MockSessionAPI()
    with pytest.raises(ValueError):
        api.create_session('invalid cadence', cadence_hz=rate)
    assert not api.create_requests
    with pytest.raises(ValueError):
        action_waypoints(chunk(), 0, cadence_hz=rate)
    with pytest.raises(ValueError):
        trajectory_cadence(rate)


@pytest.mark.parametrize('rate', [10,20,30])
def test_http_transport_preserves_session_and_packet_rate(rate):
    api = HttpSessionAPI('https://example.invalid', websocket_factory=lambda *_: None)
    requests = []
    def request(method,path,payload,**kwargs):
        requests.append((path,payload))
        return {'session_id':'sess', 'session_capability':'x'*40}
    api._request = request
    api.create_session('test', cadence_hz=rate)
    assert requests[-1][1].get('cadence_hz',10) == rate
    api.submit_trajectory('sess','ep','lease','traj',rate,action_waypoints(chunk(),0,cadence_hz=rate))
    assert requests[-1][1]['cadence_hz'] == rate


@pytest.mark.parametrize('rate', [20,30])
def test_runner_propagates_provider_cadence_through_actual_event_loop(rate):
    class Dream(ScriptedAdapter):
        provider_name = 'dream'
        trajectory_cadence_hz = rate
        def __init__(self):
            super().__init__([])
        def build_trajectory(self,prompt,observation,first):
            if first:
                raise PolicyComplete('fixture complete')
            return action_waypoints(chunk(),first,cadence_hz=rate)
    api = MockSessionAPI()
    controller = RunnerController(api)
    controller.join(Dream(),'cadence fixture')
    try:
        for _ in range(100):
            controller.process_next_event(.01)
            if api.trajectory_log:
                break
        assert api.create_requests[-1]['cadence_hz'] == rate
        assert api.trajectory_log[-1]['cadence_hz'] == rate
        assert len(api.trajectory_log[-1]['waypoints']) == 48
        assert controller._command_limit == command_budget('dream',300,rate)
    finally:
        controller.stop()


def test_mock_rejects_midrun_rate_change_with_zero_dispatch():
    api = MockSessionAPI()
    sid = api.create_session('rate mismatch',cadence_hz=20)['session_id']
    record = api._sessions[sid]
    with pytest.raises(SessionAPIError,match='cadence'):
        api.submit_trajectory(sid,record['episode_id'],record['lease_id'],'wrong',30,
                              action_waypoints(chunk(),0,cadence_hz=30))
    assert not api.action_log and not api.trajectory_log


def test_budget_accounts_for_clock_without_extending_run_deadline():
    assert command_budget('dream',1200,30) == 36300
    assert command_budget('dream',1200,20) == 24300
    assert command_budget('dream',1200) == 12300
    assert command_budget('',300,30) == 9000


@pytest.mark.parametrize('rate', [10,20,30])
def test_dream_configuration_retains_actual_packet_and_model_timing(tmp_path,rate):
    provider = DreamAdapter(provider='dream',model='dreamlabs/dream-1-beta',
        credentials='unused',python='unused',directory=tmp_path,
        camera_source=None,observation_source=lambda: {},robot_id='yam-1')
    provider.configure_cadence(rate)
    provider.configure_run_duration(1200)
    config = provider.public_config()
    assert config['cadence_hz'] == rate
    assert config['model_action_hz'] == (30 if rate == 30 else 20)
    assert provider._max_commands == command_budget('dream',1200,rate)


@pytest.mark.parametrize('rate',[10,20,30])
def test_preparation_passes_actual_playback_clock_to_worker(tmp_path,rate):
    from test_dream_policy import adapter
    provider=adapter(tmp_path)
    provider.configure_cadence(rate)
    try:
        provider.wait_ready(lambda:False)
        configure=[kwargs for command,kwargs in provider._worker.calls if command=='configure']
        assert configure[0]['action_hz'] == (30 if rate==30 else 20)
    finally:
        provider.close_transport()


@pytest.mark.parametrize('rate',[10,20,30,15,True,'20'])
def test_hosted_launch_validates_rate_before_queue_and_passes_it_to_dream(tmp_path,rate):
    import shutil
    import playground
    import test_hosted
    api=MockSessionAPI(auto_activate=False)
    credentials=tmp_path/'credentials';credentials.write_text('synthetic only')
    app=playground.HostedRunner(public_origin='https://robot.example',session_api='https://session.example',
        camera_origin='http://127.0.0.1:8089',api_factory=lambda:api,
        dream_credentials_file=str(credentials),dream_python='/inert/python')
    policy=test_hosted.HeldProvider('')
    policy.provider_name='dream'
    def configure(hz):
        policy.trajectory_cadence_hz=hz
    policy.configure_cadence=configure
    app.extra_providers['dream']=lambda *args:policy
    try:
        _,visitor=app.new_visitor()
        payload=dict(provider='dream',model='dreamlabs/dream-1-beta',prompt='Synthetic cadence fixture',cadence_hz=rate)
        if type(rate) not in (int,float) or rate not in (10,20,30):
            with pytest.raises(playground.RequestError,match='cadence'):
                app.launch(visitor,payload)
            assert not api.create_requests
        else:
            app.launch(visitor,payload)
            assert policy.trajectory_cadence_hz==rate
            assert api.create_requests[0].get('cadence_hz',10)==rate
    finally:
        for visitor in app.visitors.values():
            visitor.controller.stop()
            if visitor.controller._worker:visitor.controller._worker.join(2)
        shutil.rmtree(app.root,ignore_errors=True)
