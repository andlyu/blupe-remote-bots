"""Whole outbound-worker queued/Stop lifecycle on the real pinned controller."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from remote_yam.session import MockSessionAPI
from remote_yam.kinex_safety import ROBOHOUSE
from test_kinex import observation
from test_kinex_robohouse import report

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations/kinex'))
spec=importlib.util.spec_from_file_location('_kinex_worker_test',ROOT/'integrations/kinex/agent.py')
worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)


class WorkerLifecycle(unittest.TestCase):
    def test_actual_queue_entry_and_first_admission_are_retained_without_changing_events(self):
        from types import SimpleNamespace
        event={'schema_version':1,'session_id':'session','type':'lifecycle','episode_id':'episode',
            'timestamp':102.,'payload':{'state':'preparing','reason':'jetson_leased'}}
        stream=SimpleNamespace(receive=lambda timeout:event,close=lambda:None)
        api=SimpleNamespace(open_events=lambda session:stream,
            _request=lambda *a:{'entries':[{'session_id':'other','robot_id':ROBOHOUSE,'created_at':99.},
                {'session_id':'session','robot_id':ROBOHOUSE,'created_at':100.}]})
        facade=worker.KinexAPI(api,'Fixture','fixture@example.test',robot_id=ROBOHOUSE);facade.session_id='session'
        facade.refresh_queue_entry();self.assertEqual(facade.queue_lifecycle['entered_at'],100.)
        observed=facade.open_events('session');self.assertIs(observed.receive(.5),event)
        self.assertEqual(facade.queue_lifecycle['admitted_at'],102.)
        event['timestamp']=105.;observed.receive(.5)
        self.assertEqual(facade.queue_lifecycle['admitted_at'],102.)
        stage,reason=worker.progress('queued',None,[],facade.queue_lifecycle)
        self.assertEqual(stage,'Preparing robot');self.assertIn('admission is confirmed',reason)
        missing=worker.KinexAPI(SimpleNamespace(_request=lambda *a:{'entries':[]}), 'Fixture','fixture@example.test',robot_id=ROBOHOUSE)
        missing.session_id='absent';missing.refresh_queue_entry();self.assertEqual(missing.queue_lifecycle,{})
        self.assertEqual(worker.progress('queued',None,[])[0],'Waiting for robot admission')

    def test_planning_dispatch_and_execution_waits_explain_the_actual_stage(self):
        from types import SimpleNamespace
        p=SimpleNamespace(_thread=object(),_pending=None,_active=False)
        stage,reason=worker.progress('running',p,[])
        self.assertIn('planning',stage);self.assertIn('Astra',reason);self.assertIn('Stop',reason)
        p._pending={};p._pending={'device':'right_arm'}
        stage,reason=worker.progress('running',p,[])
        self.assertIn('Validating',stage);self.assertIn('acknowledgement',reason)
        p._active=True
        stage,reason=worker.progress('running',p,[])
        self.assertIn('Executing',stage);self.assertIn('measured completion',reason)
        self.assertEqual(worker.progress('failed',p,[{'message':'original error'}]),('Failed','original error'))

    def test_real_controller_queued_stop_no_model_spawn_or_actuator_dispatch(self):
        class Finished(BaseException):pass
        api=MockSessionAPI(auto_activate=False);api._session_capabilities={}
        obs=observation();obs.update(jetson_id=ROBOHOUSE,mode='DISABLED',queue_ready=True,homed=False,settled=False,
            safety={'ok':False,'estop_engaged':False,'reason':'hardware_not_initialized'})
        def read(*args):return dict(obs,observed_at=time.time())
        api.get_robot_observation=read
        submitted=[]
        def request(method,path,data=None):
            if method=='POST' and path=='/v1/sessions':
                submitted.append(data);return dict(api.create_session(data['prompt'],data['run_duration_s']),session_capability='offline-only')
            if path.endswith('/calibration'):return report()
            if path.startswith('/v1/queue'):return dict(generated_at=time.time(),stations=[dict(jetson_id=ROBOHOUSE,connected=True,queue_ready=True,available=False)])
            self.fail('Unexpected mock station request '+path)
        api._request=request
        updates=[];heartbeats=[];claimed=False;publication_timeout=False
        def site(req,**kwargs):
            nonlocal claimed,publication_timeout
            data=json.loads(req.data);path=req.full_url.split('.test')[-1]
            if path=='/api/runner/heartbeat':heartbeats.append(data);result={'ok':True}
            elif path=='/api/runner/claim':
                if claimed:raise Finished()
                claimed=True;result={'run':{'id':'offline_job','name':'Offline fixture','email':'fixture@example.test','prompt':'Queue/Stop protocol only; no model or robot','duration_s':60}}
            elif path=='/api/runner/update':
                updates.append(data)
                if not publication_timeout:
                    publication_timeout=True;raise TimeoutError('synthetic lost status response after processing')
                result={'ok':True,'stop':data['status']=='queued_robot'}
            else:self.fail('Unexpected mock Site request '+path)
            return io.BytesIO(json.dumps(result).encode())
        with tempfile.TemporaryDirectory() as directory:
            token=Path(directory)/'token';token.write_text('offline-token')
            args=['agent.py','--site','https://kinex.test','--token-file',str(token),'--state',directory,
                  '--upstream',directory,'--preflight',directory+'/receipt.json','--robot-id',ROBOHOUSE]
            gate={'physical_command_contract':{ROBOHOUSE:'verified'}}
            with patch.object(sys,'argv',args),patch.object(worker,'HttpSessionAPI',return_value=api),patch.object(worker,'urlopen',side_effect=site),patch('preflight.verify',return_value=gate),patch('remote_yam.kinex_policy.subprocess.Popen') as model:
                with self.assertRaises(Finished):worker.main()
                model.assert_not_called()
        self.assertEqual([u['status'] for u in updates],['preparing','preparing','queued_robot','stopped'])
        self.assertEqual(updates[0],updates[1])
        self.assertEqual([u['publication_sequence'] for u in updates],[1,1,2,3])
        self.assertTrue(any(not h['ready'] and 'progress' in h['message'] for h in heartbeats))
        self.assertFalse(any(u.get('error') for u in updates))
        self.assertEqual(api.action_attempts,[]);self.assertEqual(api.trajectory_attempts,[])
        self.assertEqual(submitted[0]['robot_id'],ROBOHOUSE);self.assertEqual(submitted[0]['model'],'Kinex')
        self.assertEqual(api.get_session(next(iter(api._sessions)))['status'],'stopped')
