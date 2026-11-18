"""Required local release gate. Never contacts a model or robot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--runner-root', type=Path, default=root.parents[1])
parser.add_argument('--receipt', type=Path)
parser.add_argument('--skills-root', type=Path, default=Path(os.environ.get('GEMINI_SKILLS_ROOT', '/opt/robotics/plugins/robotics/skills')))
args = parser.parse_args()
started = time.monotonic()
os.environ['GEMINI_TEST_RUNNER_ROOT'] = str(args.runner_root.resolve())
os.environ['GEMINI_SKILLS_ROOT'] = str(args.skills_root.resolve())
suite = unittest.defaultTestLoader.discover(str(root / 'tests'), pattern='test_*.py')
# Missing contract modules must not silently turn a release green with zero tests.
def names(test):
    if isinstance(test, unittest.TestSuite):
        return [name for child in test for name in names(child)]
    return [test.id()]
cases = names(suite)
required = ('CommandContractTests.test_all_twelve_joint_numeric_endpoints_and_preservation',
            'CommandContractTests.test_gripper_endpoints_fractional_starts_and_untouched_state',
            'CommandContractTests.test_invalid_requests_are_rejected_before_any_transport',
            'CommandContractTests.test_existing_speed_and_packet_session_budgets_are_preserved',
            'WorkerTests.test_billing_failure_is_specific_persistent_and_contains_no_provider_body',
            'Yam1SceneTests.test_native_fk_both_arms_and_named_indices_match_canonical',
            'Yam1SceneTests.test_articulated_finger_travel_axis_and_tcp_are_exact',
            'Yam1SceneTests.test_pinhole_intrinsics_and_cv_camera_poses_match_calibration',
            'Yam1SceneTests.test_google_generic_ik_uses_correct_arm_and_checks_residuals',
            'ControllerBridgeTests.test_real_runner_local_rejection_new_request_and_measured_completion',
            'ControllerBridgeTests.test_stop_during_channel_read_discards_late_command_before_transport',
            'Yam1EnvironmentTests.test_gripper_only_preserves_joint_fields_and_exact_endpoints',
            'Yam1EnvironmentTests.test_wrong_completion_identity_or_unknown_outcome_does_not_replay')
required += ('Yam1SimulationTests.test_shared_compiler_packet_is_identical_before_physics_dispatch',
             'Yam1SimulationTests.test_invalid_requests_leave_simulation_cursor_time_and_state_unchanged',
             'Yam1SimulationTests.test_no_load_partial_grip_hold_has_no_mapping_induced_drift',
             'Yam1SimulationTests.test_nominal_robot_gravity_hold_preserves_global_object_gravity',
             'StationInputsTests.test_current_scene_uses_real_camera_parser_and_sdk_image_parts_without_contact_or_lease',
             'WorkerTests.test_only_matching_yam1_image_variant_can_be_ready',
             'WorkerTests.test_retained_input_artifact_uses_host_evidence_not_generated_workspace')
required += ('SimulationBindingTests.test_edit_after_simulation_cannot_complete_using_previous_replay',
             'SimulationBindingTests.test_resimulation_preserves_each_attempt_and_protected_history_artifacts',
             'ExecutorBindingTests.test_changed_inputs_or_forged_report_never_bind_even_with_zero_exit',
             'ExecutorBindingTests.test_cleanup_failure_cannot_promote_simulation_or_copy_live_outputs',
             'SimulationBindingTests.test_identical_source_write_reuses_valid_execution_without_extra_simulation',
             'SimulationBindingTests.test_resimulation_restores_host_scene_after_generated_workspace_mutation')
required += ('QuietSessionTests.test_real_serializer_uses_same_queue_with_identity_and_both_emails_disabled',
             'QuietSessionTests.test_unsupported_or_contradictory_contract_sends_no_identity_or_queue_post',
             'QuietSessionTests.test_rollback_after_capability_read_never_falls_back_to_email_endpoint',
             'QuietSessionTests.test_ambiguous_queue_creation_timeout_is_not_retried')
if any(not any(name.endswith(case) for name in cases) for case in required):
    raise SystemExit('Required command/readiness coverage is missing')
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful():
    raise SystemExit(1)
if any(any(test.id().endswith(case) for case in required)
       for test,reason in [*result.skipped,*result.expectedFailures]):
    raise SystemExit('Required command/readiness coverage did not pass')
subprocess.run(['node', str(root / 'tests/test_gateway.mjs')], check=True)
page = (root / 'site/page.html').read_text()
script = page.split('<script>', 1)[1].split('</script>', 1)[0]
with tempfile.TemporaryDirectory(prefix='gemini-preflight-') as directory:
    file = Path(directory) / 'browser.js'; file.write_text(script)
    subprocess.run(['node', '--check', str(file)], check=True)
receipt = dict(scope='Offline packet compiler, real RunnerController/client serializer, bimanual geometry/Google IK, worker persistence/readiness and gateway; no physical or model task qualification',
               passed=True, python=sys.version.split()[0], tests=result.testsRun,
               elapsed_wall_s=round(time.monotonic()-started, 4),
               integration_source_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('backend/executor.py','backend/gemini_worker.py','backend/simulation_artifacts.py','backend/quiet_session.py','tests/test_simulation_binding.py','tests/test_quiet_session.py','site/worker.js','site/page.html','tools/preflight.py')},
               validator_sha256=hashlib.sha256((args.runner_root / 'src/remote_yam/session.py').read_bytes()).hexdigest(),
               native_safety_sha256=hashlib.sha256((args.runner_root / 'config/controller-workspaces/native-both-20260929.safety.json').read_bytes()).hexdigest())
if args.receipt:
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2)+'\n')
print(json.dumps(receipt))
