"""Run the current mutation regression against an exact exported old worker.

Offline only: the test uses a scripted SDK and engine. An exit1 containing
'complete != failed' reproduces the old acceptance bug, not a model/task pass.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

p=argparse.ArgumentParser();p.add_argument('--worker-file',type=Path,required=True)
p.add_argument('--runner-root',type=Path,required=True);a=p.parse_args()
root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'tests'),str(root/'backend'),str(a.runner_root/'src')]
os.environ['GEMINI_TEST_RUNNER_ROOT']=str(a.runner_root)
with tempfile.TemporaryDirectory(prefix='gemini-red-state-') as directory:
    os.environ['GEMINI_STATE_DIR']=directory
    import test_simulation_binding as tests
    spec=importlib.util.spec_from_file_location('gemini_baseline_worker',a.worker_file)
    baseline=importlib.util.module_from_spec(spec);sys.modules[spec.name]=baseline;spec.loader.exec_module(baseline)
    tests.w=baseline;tests.helpers.w=baseline
    suite=unittest.TestSuite([tests.SimulationBindingTests('test_edit_after_simulation_cannot_complete_using_previous_replay')])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
