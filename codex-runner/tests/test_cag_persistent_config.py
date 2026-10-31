import importlib.util
from pathlib import Path
import sys
from unittest.mock import Mock
import pytest

ROOT=Path(__file__).resolve().parents[1]/'examples/cag_molmoact2'
spec=importlib.util.spec_from_file_location('cag_deploy_config',ROOT/'config.py')
config=importlib.util.module_from_spec(spec);spec.loader.exec_module(config)

def test_persistent_runtime_has_no_trial_lifetime_and_remains_disabled_until_activation():
    persistent=config.gpu_config('volume',persistent=True)
    assert persistent['env']['MAX_WORKER_LIFETIME_SECONDS']=='0'
    assert persistent['workers']==dict(min=0,max=0,idleTimeout=300)
    assert persistent['gpu']['count']==1
    assert config.gpu_config('volume')['env']['MAX_WORKER_LIFETIME_SECONDS']=='3600'
