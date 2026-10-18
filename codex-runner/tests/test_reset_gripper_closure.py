"""Position closure, native travel, and warm references; no hardware access."""
import copy
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from remote_yam.resets.yam_cube_grasps import aperture_for_gap,grasp_aperture,pregrasp_aperture
from remote_yam.resets.yam_cube_feedback_geometry import retarget_source
from remote_yam.resets.yam_cube_size_profile import configure_size_aware
from remote_yam.resets.yam_cube_reset import ResetBlocked

REF=dict(closed_gap_m=-.001,opening_travel_m=.095)


def gap(command):return REF['closed_gap_m']+REF['opening_travel_m']*command


@pytest.mark.parametrize('edge',[.025,.0275,.030])
def test_profile_requests_half_mm_total_compression_and_keeps_extra_opening(edge,monkeypatch):
    monkeypatch.setattr('remote_yam.resets.yam_cube_size_profile.contact_for_cube',lambda *a,**k:dict(tcp_height_above_support_m=.022))
    monkeypatch.setattr('remote_yam.resets.yam_cube_size_profile.resize_targets',lambda target,*a:copy.deepcopy(target))
    program=SimpleNamespace(args=SimpleNamespace(),planner=SimpleNamespace(),ref={},targets={},report={})
    configure_size_aware(program,dict.fromkeys(('blue','orange','yellow'),edge))
    p=program.planner
    assert p.grasp_compression_m==.0005 and p.grasp_gap_relief_m==0. and p.grasp_command_gap_m==.020
    close=grasp_aperture(edge,REF,compression_m=p.grasp_compression_m,gap_relief_m=p.grasp_gap_relief_m,command_gap_m=p.grasp_command_gap_m)
    assert gap(close)==pytest.approx(.020)
    assert gap(pregrasp_aperture(edge,p.pregrasp_clearance_m,REF,p.pregrasp_extra_open_gap_m))==pytest.approx(edge+.030)
    assert gap(aperture_for_gap(edge+.010,REF))==pytest.approx(edge+.010)


def test_recorded_old_target_and_corrected_default_conversion():
    old=grasp_aperture(.030,REF,compression_m=0.,gap_relief_m=.0001)
    new=grasp_aperture(.030,REF,compression_m=.0005,gap_relief_m=0.)
    assert old==pytest.approx(.3273684210526316) and gap(old)==pytest.approx(.0301)
    assert new==pytest.approx(.32105263157894737) and gap(new)==pytest.approx(.0295)
    assert gap(old)-gap(new)==pytest.approx(.0006)
    # Encoder-to-gap is a CAD/reference estimate, not a measured contact width.
    observed_encoder=.329887965305385
    assert gap(observed_encoder)==pytest.approx(.030339356704011574)


def test_actual_combined_cli_defaults_do_not_reintroduce_positive_relief(tmp_path,monkeypatch):
    from remote_yam.resets import cube_cli
    monkeypatch.setattr('remote_yam.resets.yam_cube_size_profile.contact_for_cube',lambda *a,**k:dict(tcp_height_above_support_m=.022))
    monkeypatch.setattr('remote_yam.resets.yam_cube_size_profile.resize_targets',lambda target,*a:copy.deepcopy(target))
    selected=[]
    def program(args):
        p=SimpleNamespace(args=args,planner=SimpleNamespace(),ref={},targets={},report={})
        configure_size_aware(p,args.cube_edges_m)
        assert p.planner.grasp_compression_m==.0005 and p.planner.grasp_gap_relief_m==0.
        selected.append(gap(grasp_aperture(.030,REF,compression_m=p.planner.grasp_compression_m,
                                          gap_relief_m=p.planner.grasp_gap_relief_m,command_gap_m=p.planner.grasp_command_gap_m)))
        return SimpleNamespace(sense_only=lambda:0,planner=p.planner)
    monkeypatch.setattr('remote_yam.resets.yam_cube_size_profile.PickupFeedbackCubeProgram',program)
    argv=['--runtime-root',str(tmp_path),'--calibration',str(tmp_path/'calibration.json'),
          '--targets',str(tmp_path/'goals.json'),'--parts',str(tmp_path/'parts'),
          '--output',str(tmp_path/'run'),'--planning-profile','pickup-feedback',
          '--after-replay','offline','--home-after-replay','--staging-feedback','--feedback-close-gap-mm','20','--sense-only']
    assert cube_cli.main(argv,shared_io=object())==0
    assert selected==pytest.approx([.020])


@pytest.mark.parametrize('compression,relief',[(float('nan'),0.),(-.0001,0.),(.0021,0.),(0.,-.0001),(0.,.0003)])
def test_existing_compression_and_relief_bounds_still_apply(compression,relief):
    with pytest.raises(ResetBlocked):grasp_aperture(.030,REF,compression_m=compression,gap_relief_m=relief)


def test_native_travel_is_not_extended_or_silently_clipped():
    with pytest.raises(ResetBlocked):grasp_aperture(.100,REF,compression_m=.0005)
    assert pregrasp_aperture(.090,.010,REF,.020)==1.


@pytest.mark.parametrize('arm',['left','right'])
def test_old_warm_reference_close_and_every_carry_stage_use_new_target(arm,monkeypatch):
    import remote_yam.resets.yam_cube_feedback_geometry as geometry
    monkeypatch.setattr(geometry,'solve_endpoint',lambda planner,seed,*a:seed)
    rotation=np.diag([1.,-1.,-1.]);point=np.array([.3,-.2,.022]);q=[0.]*12
    index=0 if arm=='left' else 1
    planner=SimpleNamespace(world=lambda row:np.asarray(row['xyz'],float),contact_reference=REF,
        pregrasp_extra_open_gap_m=.020,grasp_compression_m=.0005,grasp_gap_relief_m=0.,grasp_command_gap_m=.020,
        ik=SimpleNamespace(_forward=Mock(),_poses=lambda:((point,rotation),(point,rotation))))
    source=dict(xyz=[.3,-.2,.03],yaw_rad=0.)
    old_close=aperture_for_gap(.0301,REF);opened=aperture_for_gap(.060,REF);released=aperture_for_gap(.040,REF)
    carry={'lift_clear','lift','transfer','place_align','place'}
    names=['open','approach','align','descend','close','lift_clear','lift','transfer','place_align','place','release','retreat_clear','retreat','view_clear']
    stages=[]
    for name in names:
        command=old_close if name=='close' or name in carry else released if name in ('release','retreat_clear') else opened
        g=[.7,.8];g[index]=command
        stages.append(dict(name=name,points_rad=[q.copy()],grippers=g,expected_tip_world_m=point.tolist(),expected_rotation=rotation.tolist(),carrying=name in carry))
    plan=dict(color='blue',arm=arm,stages=stages,pregrasp_aperture=opened,release_aperture=released,
              contact_geometry=dict(projected_grasp_width_m=.030,nominal_aperture=old_close))
    original=copy.deepcopy(plan);state=dict(joints=q,left_gripper=.7,right_gripper=.8)
    corrected=retarget_source(planner,plan,source,source,state)
    assert plan==original
    assert corrected['grasp_compression_m']==.0005 and corrected['grasp_gap_relief_m']==0. and corrected['grasp_command_gap_m']==.020
    assert gap(corrected['contact_geometry']['nominal_aperture'])==pytest.approx(.0295)
    for stage in corrected['stages']:
        name=stage['name']
        if name=='close' or name in carry:assert gap(stage['grippers'][index])==pytest.approx(.020)
        if name in ('open','approach','align','descend'):assert gap(stage['grippers'][index])==pytest.approx(.060)
        if name in ('release','retreat_clear'):assert gap(stage['grippers'][index])==pytest.approx(.040)
        assert stage['grippers'][1-index]==state['right_gripper' if index==0 else 'left_gripper']


def edge_contact_case():
    # Actual rejected blue close contact, 1.565mm beyond the nominal pad Z edge.
    return dict(names=['cube_blue','right_installed_tip_left_193'],side='right',color='blue',
        stage=dict(name='close',intended_selected_contact=True),
        plan=dict(grasp_compression_m=.0005,grasp_gap_relief_m=0.,contact_geometry=dict(
            projected_grasp_width_m=.030,nominal_aperture=.32105263157894737,
            candidate_vertical_error_bound_m=.002)),
        native=np.array([-.013741508692446478,.014999978485836792,-.007923721636900777]),
        pad=dict(pad_bounds_native_grasp_m=[[-.012440559245190849,-.0005197232510326939,-.006358460062747567],
                                          [.012629384676009936,-.0005038649517441198,.009498193562429036]]),
        pad_y=.01475,aperture=.32105263157894737,reference=REF,distance=-.00011157940122302981)


@pytest.mark.parametrize('carrying',[False,True])
def test_selected_tip_preload_edge_contact_admitted_only_in_close_or_carry(carrying):
    from remote_yam.resets.installed_geometry import intended_tip_contact_kind
    case=edge_contact_case()
    if carrying:case['stage']=dict(name='lift',carrying=True)
    assert intended_tip_contact_kind(**case)=='preload_edge'


def test_release_start_retains_only_existing_preload_while_opening():
    from remote_yam.resets.installed_geometry import intended_tip_contact_kind
    case=edge_contact_case()
    case['stage']=dict(name='release',intended_selected_contact=True,grippers=[1.,aperture_for_gap(.040,REF)])
    assert intended_tip_contact_kind(**case)=='preload_edge'
    case['aperture']=aperture_for_gap(.0301,REF)
    assert intended_tip_contact_kind(**case) is None


@pytest.mark.parametrize('names',[
    ['cube_orange','right_installed_tip_left_193'],
    ['cube_blue','left_installed_tip_left_193'],
    ['cube_blue','right_installed_wrist_0'],
    ['table','right_installed_tip_left_193'],
    ['cube_blue','right_link6'],
])
def test_preload_edge_does_not_exempt_other_cubes_arm_body_or_floor(names):
    from remote_yam.resets.installed_geometry import intended_tip_contact_kind
    case=edge_contact_case();case['names']=names
    assert intended_tip_contact_kind(**case) is None


@pytest.mark.parametrize('fault',[
    'approach','release','no_intent','no_compression','deep_contact','far_edge',
    'wrong_plane','early_open_sample','excess_close_sample','wrong_nominal','larger_error_bound',
])
def test_preload_edge_is_bounded_by_commanded_compression_and_existing_uncertainty(fault):
    from remote_yam.resets.installed_geometry import intended_tip_contact_kind
    case=edge_contact_case();plan=case['plan']
    if fault in ('approach','release'):case['stage']['name']=fault
    elif fault=='no_intent':case['stage']['intended_selected_contact']=False
    elif fault=='no_compression':plan['grasp_compression_m']=0.
    elif fault=='deep_contact':case['distance']=-.0004
    elif fault=='far_edge':case['native'][2]=-.009
    elif fault=='wrong_plane':case['native'][1]+=.002
    elif fault=='early_open_sample':case['aperture']=aperture_for_gap(.0301,REF)
    elif fault=='excess_close_sample':case['aperture']=aperture_for_gap(.029,REF)
    elif fault=='wrong_nominal':plan['contact_geometry']['nominal_aperture']=aperture_for_gap(.0301,REF)
    elif fault=='larger_error_bound':plan['contact_geometry']['candidate_vertical_error_bound_m']=.003
    assert intended_tip_contact_kind(**case) is None


def test_existing_pad_patch_admission_is_preserved_without_preload():
    from remote_yam.resets.installed_geometry import intended_tip_contact_kind
    case=edge_contact_case();case['native'][0]=0.;case['native'][2]=0.;case['distance']=-.0009
    case['plan']['grasp_compression_m']=0.
    assert intended_tip_contact_kind(**case)=='pad'


@pytest.mark.parametrize('arm',['left','right'])
@pytest.mark.parametrize('name',['close','lift','transfer','place','release'])
def test_native_twenty_mm_target_remains_distinct_from_blocked_contact_geometry(arm,name):
    from remote_yam.resets.installed_geometry import contact_blocked_aperture
    case=edge_contact_case();plan=case['plan'];plan['arm']=arm;plan['grasp_command_gap_m']=.020
    command=aperture_for_gap(.020,REF);plan['contact_geometry']['commanded_aperture']=command
    g=[1.,1.];g[0 if arm=='left' else 1]=aperture_for_gap(.040,REF) if name=='release' else command
    stage=dict(name=name,carrying=name in ('lift','transfer','place'),intended_selected_contact=True,grippers=g)
    original=copy.deepcopy(stage)
    modeled=contact_blocked_aperture(plan,stage,command,REF)
    assert gap(modeled)==pytest.approx(.0295)
    assert gap(command)==pytest.approx(.020) and stage==original
    # No object deformation is inferred from target position; opening remains unchanged.
    opened=aperture_for_gap(.060,REF)
    assert contact_blocked_aperture(plan,stage,opened,REF)==opened
    stage['name']='approach';stage['carrying']=False
    assert contact_blocked_aperture(plan,stage,command,REF)==command


def test_twenty_mm_is_a_gap_not_twenty_percent_and_respects_native_travel():
    command=grasp_aperture(.030,REF,command_gap_m=.020)
    assert command==pytest.approx(.22105263157894736) and command!=.20
    with pytest.raises(ResetBlocked):grasp_aperture(.030,REF,command_gap_m=.100)
