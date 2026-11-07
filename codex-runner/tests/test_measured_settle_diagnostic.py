import tempfile
from pathlib import Path

from remote_yam.past_runs import RunNames, public_runner_diagnostic
from remote_yam.run_errors import public_run_error


LOWER_ERROR = (
    'Measured target did not settle: lower; blocked_by=measured_position; '
    'measured_joint_2_error_deg=5.693; commanded_joint_4_error_deg=0.008; '
    'allowed_deg=5.000; max_joint_speed_rad_s=0.0220 (limit 0.05); '
    'gripper_measured=0.3123,commanded=0.0000,goal=0.0000; stable_s=0.000 (required 0.15)'
)
PUBLIC = 'Robot stopped: arm did not settle during lowering'


def test_live_lower_stop_remains_specific_after_both_filters_and_storage():
    filtered = public_runner_diagnostic({'error': LOWER_ERROR})
    assert filtered == PUBLIC
    assert public_run_error({'error': 'RuntimeError: ' + filtered}) == PUBLIC
    with tempfile.TemporaryDirectory() as folder:
        names = RunNames(Path(folder) / 'names.sqlite3')
        names.remember_result('ep_settle', {'status': 'stopped', 'error': 'RuntimeError: ' + filtered})
        saved = names.results()['ep_settle']
        assert saved['result'] == 'Failure'
        assert saved['errors'] == PUBLIC


def test_other_native_phase_and_multiple_blockers_report_only_the_phase():
    native = LOWER_ERROR.replace('settle: lower;', 'settle: return_to_start;').replace(
        'blocked_by=measured_position;', 'blocked_by=measured_position,joint_speed,measured_gripper;'
    ).replace('gripper_measured=0.3123', 'gripper_measured=-0.0012')
    assert public_runner_diagnostic({'error': native}) == 'Robot stopped: arm did not settle during return to start'


def test_unrecognized_native_fields_and_private_tails_are_rejected():
    for source in (
        LOWER_ERROR + '\nsecret', LOWER_ERROR + ' secret', PUBLIC + ' private',
        LOWER_ERROR.replace('settle: lower;', 'settle: private;'),
        LOWER_ERROR.replace('measured_joint_2', 'measured_joint_7'),
        LOWER_ERROR.replace('measured_position', 'provider output'),
        LOWER_ERROR.replace('5.693', '123456789.123'),
    ):
        assert public_runner_diagnostic({'error': source}) is None
