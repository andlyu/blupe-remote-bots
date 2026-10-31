import importlib.util
import os
from pathlib import Path
import subprocess
import sys

spec=importlib.util.spec_from_file_location('website_worker',Path(__file__).parents[1]/'worker-agent/worker.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def test_worker_keeps_the_configured_virtual_environment(tmp_path):
    interpreter=tmp_path/'venv/bin/python';interpreter.parent.mkdir(parents=True);interpreter.symlink_to(sys.executable)
    w=module.Worker({'origin':'https://example.test','python':str(interpreter),'runs':str(tmp_path/'runs')})
    assert w.python==str(interpreter)

def test_stop_reaches_a_detached_child(tmp_path):
    import time
    w=module.Worker({'origin':'https://example.test','python':sys.executable,'runs':str(tmp_path/'runs')})
    script="import subprocess,time; p=subprocess.Popen(['sleep','60'],start_new_session=True); print(p.pid,flush=True); time.sleep(60)"
    w.child=subprocess.Popen([sys.executable,'-u','-c',script],stdout=subprocess.PIPE,text=True,start_new_session=True)
    descendant=int(w.child.stdout.readline())
    try:
        w.terminate()
        assert w.child.poll() is not None
        for _ in range(30):
            status=subprocess.check_output(['ps','-p',str(descendant),'-o','state='],text=True) if subprocess.call(['kill','-0',str(descendant)],stderr=subprocess.DEVNULL)==0 else ''
            if not status.strip() or status.strip()=='Z':break
            time.sleep(.05)
        assert not status.strip() or status.strip()=='Z'
    finally:
        try:os.kill(descendant,9)
        except ProcessLookupError:pass
