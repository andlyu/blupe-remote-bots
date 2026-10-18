"""Requested replay→one Home→fresh sensing, and staged feedback references."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from remote_yam.resets.yam_cube_program import CubeProgram
from remote_yam.resets.yam_cube_size_profile import PickupFeedbackCubeProgram


def home_program(tmp_path):
    p=CubeProgram.__new__(CubeProgram)
    p.args=SimpleNamespace(execution_policy='controller-faults',resume_plan=None,owner_file=None,
        planning_profile='qualified',after_replay='synthetic-replay',home_after_replay=True)
    p.out=tmp_path;p.token=None;p.motion_count=0;p.pending=None;p.completed=[];p.events=[];p.goals_sha='synthetic'
    p.planner=SimpleNamespace(ik=SimpleNamespace(low=np.zeros(12),high=np.ones(12)))
    state=dict(joints=[.2]*12,home_target=[.4]*12,left_gripper=.2,right_gripper=.3)
    p.state=Mock(return_value=state);p.initialize=Mock();p.event=Mock();p.motion=Mock()
    p.run_qualified_scene=Mock(return_value={'blue':dict(state='already_correct')})
    p.io=SimpleNamespace(call=Mock(side_effect=[dict(owner_token='owner'),{}]),
                         emergency_hold=Mock(return_value=dict(state='held')))
    return p,state


def test_explicit_post_replay_home_runs_once_at_bounded_pose(tmp_path):
    p,state=home_program(tmp_path)
    p.prepare_planning_start();p.prepare_planning_start()
    p.motion.assert_called_once()
    color,stage=p.motion.call_args.args
    assert color=='startup' and stage['name']=='home'
    assert stage['points_rad']==[state['home_target']]
    assert stage['grippers']==[state['left_gripper'],state['right_gripper']]
    assert p.replay_home_completed


def test_home_completes_before_first_scene_and_reset_uses_same_io(tmp_path):
    p,_=home_program(tmp_path);order=[];io=p.io
    p.motion.side_effect=lambda *a:order.append('home')
    def capture(name):
        assert p.replay_home_completed
        order.append('fresh scene');return {}
    p.scene=Mock(side_effect=capture)
    p.run_qualified_scene.side_effect=lambda scene:order.append('reset') or {'blue':dict(state='already_correct')}
    assert p.run(io=io)==0
    assert order==['home','fresh scene','reset']
    assert p.io is io and [c.args[0] for c in io.call.call_args_list]==['reserve','release']


@pytest.mark.parametrize('error,code',[(TimeoutError('uncertain Home'),2),(KeyboardInterrupt('Stop'),130)])
def test_uncertain_or_cancelled_home_never_captures_or_retries(tmp_path,error,code):
    p,_=home_program(tmp_path);p.motion.side_effect=error;p.scene=Mock()
    assert p.run(io=p.io)==code
    p.motion.assert_called_once();p.scene.assert_not_called();p.run_qualified_scene.assert_not_called()
    assert not getattr(p,'replay_home_completed',False)


def test_no_explicit_home_retains_existing_bounded_start_behavior(tmp_path):
    p,_=home_program(tmp_path);p.args.home_after_replay=False
    p.prepare_planning_start();p.motion.assert_not_called()


def test_staged_blue_references_keep_distinct_audited_sources(tmp_path,monkeypatch):
    p=PickupFeedbackCubeProgram.__new__(PickupFeedbackCubeProgram)
    p.out=tmp_path;p.targets={'original':'goals'};targets=p.targets
    p.planner=SimpleNamespace(proactive_staging=False);p.state=Mock(return_value={});p.event=Mock()
    def schedule(program,state,scene,folder,*,remaining_colors):
        assert program.planner.proactive_staging and remaining_colors==['blue']
        sequence=[]
        for number,source in enumerate(('dumped','central staging'),1):
            name=f'leg-{number:02d}-blue-plan';leg=folder/name;leg.mkdir()
            (leg/'planning-scene.json').write_text(json.dumps({'blue':dict(source=source)}))
            sequence.append(dict(directory=name,color='blue',goal_kind='staging' if number==1 else 'goal'))
        program.out=folder/'internal';program.targets={'temporary':'target'}
        return sequence
    monkeypatch.setattr('remote_yam.resets.yam_cube_rearrangement.plan_rearrangement',schedule)
    p.load_audited_leg=Mock(side_effect=[dict(color='blue'),dict(color='blue')])
    plans=p.staged_feedback_references({'blue':{}},['blue'])
    assert [r['source_scene_row']['source'] for r in plans]==['dumped','central staging']
    assert p.out==tmp_path and p.targets is targets and p.planner.proactive_staging is False
    assert p.load_audited_leg.call_count==2


def test_staging_plan_failure_restores_original_goals_and_source_root(tmp_path,monkeypatch):
    p=PickupFeedbackCubeProgram.__new__(PickupFeedbackCubeProgram)
    p.out=tmp_path;p.targets={'immutable':'goals'};targets=p.targets
    p.planner=SimpleNamespace(proactive_staging=False);p.state=Mock(return_value={});p.event=Mock()
    def failed(program,*args,**kw):
        program.out=tmp_path/'other';program.targets={};raise RuntimeError('No complete path')
    monkeypatch.setattr('remote_yam.resets.yam_cube_rearrangement.plan_rearrangement',failed)
    with pytest.raises(RuntimeError):p.staged_feedback_references({},['blue'])
    assert p.out==tmp_path and p.targets is targets and not p.planner.proactive_staging


def test_staging_feedback_route_does_not_load_unrelated_nominal_reference(tmp_path):
    p=PickupFeedbackCubeProgram.__new__(PickupFeedbackCubeProgram)
    p.out=tmp_path;p.targets={};p.args=SimpleNamespace(staging_feedback=True,
        feedback_reference_root=tmp_path/'absent',execution_policy='controller-faults')
    scene={'blue':{}};references=[dict(color='blue',source_scene_row={'source':'buffer'})]
    p.compare_qualified_scene=Mock(side_effect=[{c:dict(state='displaced' if c=='blue' else 'already_correct') for c in ('blue','orange','yellow')},{c:dict(state='already_correct') for c in ('blue','orange','yellow')}])
    p.staged_feedback_references=Mock(return_value=references);p.event=Mock()
    def execute(nominal,plans):
        assert nominal==scene and plans==references
        (tmp_path/'pickup-feedback.json').write_text(json.dumps(dict(final_scene=scene)))
    p.run_pickup_feedback=Mock(side_effect=execute)
    assert p.run_qualified_scene(scene)['blue']['state']=='already_correct'
    p.staged_feedback_references.assert_called_once_with(scene,['blue'])
