"""Dream's existing10Hz packets must not hit a five-minute waypoint ceiling."""
import pytest
from remote_yam.session import command_budget,MockSessionAPI,SessionAPIError
from remote_yam.dream_policy import action_waypoints,motion_limited_waypoints


@pytest.mark.parametrize('provider',['dream','dream_flash'])
def test_twelve_thousand_waypoints_pass_real_dream_conversion_and_mock_transport(provider):
    api=MockSessionAPI();created=api.create_session('Synthetic20minute fixture',1200,provider=provider)
    sid=created['session_id'];state=api._sessions[sid];limit=command_budget(provider,1200)
    action={key:[[0]*6+[.5] for _ in range(40)] for key in ['q_l_chunk','q_r_chunk']}
    observation=dict(left_joints_deg=[0]*6,right_joints_deg=[0]*6,left_gripper=.5,right_gripper=.5)
    for first in range(0,12000,20):
        points=action_waypoints(action,first,max_commands=limit)
        points=motion_limited_waypoints(points,observation,20,max_commands=limit)
        api.submit_trajectory(sid,state['episode_id'],state['lease_id'],'chunk_'+str(first),10,points)
    assert len(api.action_log)==12000
    assert len(api.trajectory_log)==600
    assert limit==12300  #1200s*10Hz plus one pending300-waypoint packet.
    assert len(action_waypoints(action,12000,max_commands=limit))==20
    with pytest.raises(ValueError):action_waypoints(action,limit,max_commands=limit)


@pytest.mark.parametrize('provider,seconds,limit',[('dream',120,3000),('dream_flash',120,3000),
    ('dream',600,3000),('dream',601,6310),('dream',1200,12300),('dream_flash',1200,12300),
    ('openai',1200,3000),('anthropic',1200,3000),('',1200,3000)])
def test_only_extended_dream_runs_gain_a_bounded_budget(provider,seconds,limit):
    assert command_budget(provider,seconds)==limit


@pytest.mark.parametrize('provider',['dream','dream_flash'])
def test_real_controller_event_loop_crosses_old_ceiling_with_sustained_packets(provider):
    from remote_yam.controller import RunnerController
    from remote_yam.providers import ScriptedAdapter,PolicyComplete
    class SyntheticDream(ScriptedAdapter):
        provider_name=provider
        def __init__(self):super().__init__([])
        def configure_run_duration(self,seconds):self.limit=command_budget(provider,seconds)
        def build_trajectory(self,prompt,observation,first):
            if first>=12000:raise PolicyComplete('Synthetic twenty minutes completed')
            action={key:[[0]*6+[.5] for _ in range(40)] for key in ['q_l_chunk','q_r_chunk']}
            return action_waypoints(action,first,max_commands=self.limit)
    api=MockSessionAPI();controller=RunnerController(api)
    controller.join(SyntheticDream(),'Synthetic sustained packets',run_duration_s=1200)
    try:
        for _ in range(15000):
            controller.process_next_event(.01)
            if len(api.action_log)==12000:break
        assert len(api.action_log)==12000
        assert len(api.trajectory_log)==600
        assert controller._command_limit==12300
    finally:controller.stop()
