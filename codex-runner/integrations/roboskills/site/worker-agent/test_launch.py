import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from launch import launch


class LauncherTests(unittest.TestCase):
    def test_child_receives_pipe_and_survives_parent_exit_without_logging_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);ready=root/'ready';log=root/'log'
            child_code='import json,os,sys,time; c=json.loads(sys.stdin.readline()); open(c["ready"],"w").write(str(os.getsid(0))); time.sleep(15)'
            parent_code='from launch import launch_process; import json,sys; c=json.loads(sys.stdin.readline()); p=launch_process(c["command"],c["config"],log=c["log"]); print(p.pid)'
            data={'command':[sys.executable,'-c',child_code],'config':{'ready':str(ready),'workerToken':'test-only-secret'},'log':str(log)}
            parent=subprocess.run([sys.executable,'-c',parent_code],input=json.dumps(data)+'\n',text=True,capture_output=True,check=True,cwd=Path(__file__).parent)
            pid=int(parent.stdout.strip())
            try:
                deadline=time.monotonic()+5
                while not ready.exists() and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(ready.exists(),'Detached worker did not receive pipe configuration')
                self.assertEqual(int(ready.read_text()),pid,'Worker must own a separate session')
                os.kill(pid,0)
                self.assertNotIn('test-only-secret',parent.stdout+parent.stderr+log.read_text())
            finally:os.kill(pid,signal.SIGTERM)

    def test_existing_live_service_is_rejected_without_starting_another(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            state={'simulation':{'pid':os.getpid()}}
            (root/'services.json').write_text(json.dumps(state))
            with self.assertRaisesRegex(RuntimeError,'already running'):
                launch({'python':sys.executable,'runsRoot':str(root),'simulationToken':'test-only'})
            self.assertEqual(json.loads((root/'services.json').read_text()),state)


if __name__=='__main__':unittest.main()
