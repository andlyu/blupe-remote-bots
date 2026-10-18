import asyncio
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from local_playground import LocalPlayground
from remote_yam.controller import RunnerController
from remote_yam.managed_command_policy import ManagedCommandPolicy, load_policies
from remote_yam.session import MockSessionAPI


FAKE = '''import json,signal,sys,time
from pathlib import Path
out=Path(sys.argv[1]); rid=sys.argv[2]; mode=sys.argv[3]
out.mkdir(parents=True)
stopped=False
def stop(*args):
 global stopped
 stopped=True
signal.signal(signal.SIGTERM,stop)
(out/'status.json').write_text(json.dumps(dict(phase='replay',request_id=rid)))
for i in range(15 if mode=='wait' else 2):
 time.sleep(.05)
 if stopped:break
if stopped:time.sleep(.25)
result=dict(request_id=rid,state='cancelled' if stopped else 'complete',goals_reached=not stopped)
if mode=='missing':sys.exit(2)
if mode=='mismatch':result['request_id']='old-run'
if mode=='goals-failed':result.update(goals_reached=False,state='not_reached')
if mode=='queue-owner':result.update(goals_reached=False,state='failed',error='Queue/API owner blocks initialization',private='secret')
(out/('failure.json' if stopped else 'result.json')).write_text(json.dumps(result))
sys.exit(130 if stopped else 2 if mode=='goals-failed' else 0)
'''


class ManagedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = self.root/'fake.py'
        self.script.write_text(FAKE)

    def spec(self, mode='done'):
        return dict(robot_id='yam-1', model='reset-bin-v1', label='Reset bin', task='Reset bin',
                    help='Replay then reset; Stop cancels either stage.',
                    command=[sys.executable,str(self.script),'{output}','{request_id}',mode])

    def policy(self, mode='done'):
        return ManagedCommandPolicy('reset_bin', self.spec(mode), self.root)

    def wait(self, predicate):
        deadline=time.monotonic()+4
        while not predicate():
            if time.monotonic()>deadline:self.fail('Timed out waiting for test worker')
            time.sleep(.01)

    def test_robot_config_is_scoped_and_requires_explicit_identity(self):
        path=self.root/'config.json'
        path.write_text(json.dumps(dict(schema='blupe-managed-policies-v1',policies={'reset_bin':self.spec()})))
        self.assertEqual(load_policies(path,'other'),{})
        self.assertIn('reset_bin',load_policies(path,'yam-1'))
        bad=self.spec();bad['command']=[sys.executable,str(self.script)]
        path.write_text(json.dumps(dict(schema='blupe-managed-policies-v1',policies={'reset_bin':bad})))
        with self.assertRaises(ValueError):load_policies(path,'yam-1')

    def test_stop_before_spawn_and_changed_source_never_execute(self):
        policy=self.policy();policy.request_stop()
        with patch('subprocess.Popen') as spawn:
            self.assertEqual(policy.run_managed('Reset bin')['state'],'cancelled')
            spawn.assert_not_called()
        policy=self.policy();policy.spec['sha256']={str(self.script):'0'*64}
        with patch('subprocess.Popen') as spawn:
            with self.assertRaisesRegex(RuntimeError,'source changed'):policy.run_managed('Reset bin')
            spawn.assert_not_called()

    def test_existing_controller_runs_without_gateway_queue_or_home(self):
        api=MockSessionAPI();controller=RunnerController(api);policy=self.policy()
        controller.join_and_run(policy,'Reset bin')
        self.wait(lambda:not controller._worker.is_alive())
        state=controller.status()
        self.assertEqual(state['status'],'stopped')
        self.assertTrue(state['provider']['managed_execution']['result']['goals_reached'])
        self.assertEqual(api.create_requests,[])
        self.assertIsNone(state['session_id'])
        self.assertEqual(state['run_metrics']['model_calls'],0)

    def test_stop_waits_for_executable_receipt_and_keeps_provider(self):
        api=MockSessionAPI();controller=RunnerController(api);policy=self.policy('wait')
        controller.join_and_run(policy,'Reset bin')
        self.wait(lambda:(policy.output/'status.json').exists())
        controller.disconnect()
        self.assertTrue(controller._worker.is_alive())
        self.assertIs(controller._provider,policy)
        self.assertEqual(policy.public_config()['managed_execution']['phase'],'cancelling')
        self.wait(lambda:not controller._worker.is_alive())
        state=controller.status()
        self.assertEqual(state['status'],'stopped')
        self.assertEqual(state['provider']['managed_execution']['result']['state'],'cancelled')
        self.assertEqual(api.create_requests,[])

    def test_missing_or_mismatched_receipt_is_failure_and_never_retried(self):
        for mode in ('missing','mismatch'):
            policy=self.policy(mode)
            controller=RunnerController(MockSessionAPI())
            controller.join_and_run(policy,'Reset bin')
            self.wait(lambda:not controller._worker.is_alive())
            self.assertEqual(controller.status()['status'],'failed')
            self.assertEqual(policy.public_config()['managed_execution']['phase'],'failed')

    def test_read_only_controller_cannot_start_managed_executable(self):
        with self.assertRaisesRegex(RuntimeError,'disabled'):
            RunnerController(MockSessionAPI(),hardware_control_enabled=False).join_and_run(self.policy(),'Reset bin')

    def test_queue_owner_failure_keeps_private_receipt_and_projects_fixed_category(self):
        from remote_yam.run_errors import public_run_error
        policy=self.policy('queue-owner'); controller=RunnerController(MockSessionAPI())
        controller.join_and_run(policy,'Reset bin')
        self.wait(lambda:not controller._worker.is_alive())
        state=controller.status()
        self.assertEqual(state['status'],'failed')
        self.assertEqual(policy._result['private'],'secret')
        self.assertEqual(policy.public_config()['managed_execution']['failure'],dict(
            code='queue_api_owner',message='Robot initialization was blocked by queue/API ownership.'))
        self.assertEqual(public_run_error(state),'Robot initialization was blocked by queue/API ownership.')
        self.assertEqual(controller._session_api.create_requests,[])

    def test_failed_goals_preserve_the_actual_result(self):
        policy=self.policy('goals-failed');controller=RunnerController(MockSessionAPI())
        controller.join_and_run(policy,'Reset bin')
        self.wait(lambda:not controller._worker.is_alive())
        self.assertEqual(controller.status()['status'],'failed')
        self.assertEqual(policy.public_config()['managed_execution']['result']['state'],'not_reached')


class ManagedRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        script=self.root/'fake.py';script.write_text(FAKE)
        spec=dict(robot_id='yam-1',model='reset-bin-v1',label='Reset bin',task='Reset bin',help='Replay then reset.',
                  command=[sys.executable,str(script),'{output}','{request_id}','wait'])
        config=self.root/'policies.json'
        config.write_text(json.dumps(dict(schema='blupe-managed-policies-v1',policies={'reset_bin':spec})))
        with patch.dict('os.environ',{'YAM_LOCAL_POLICY_CONFIG':str(config)}):
            self.app=LocalPlayground(public_origin='http://127.0.0.1:8791',session_api=None,camera_origin='http://127.0.0.1:8089',
                development=True,hardware_control=True,api_factory=lambda:MockSessionAPI(auto_activate=False))
        self.cookie='';self.csrf=''

    async def asyncTearDown(self):
        for visitor in self.app.visitors.values():
            visitor.controller.stop()
            if visitor.controller._worker:await asyncio.to_thread(visitor.controller._worker.join,3)
        shutil.rmtree(self.app.root,ignore_errors=True);self.temp.cleanup()

    async def call(self,path,payload=None,*,origin='http://127.0.0.1:8791'):
        messages=[]
        async def receive():return {'type':'http.request','body':json.dumps(payload or {}).encode()}
        async def send(message):messages.append(message)
        await self.app({'type':'http','method':'GET' if payload is None else 'POST','path':path,'query_string':b'',
            'headers':[(k.encode(),v.encode()) for k,v in dict(host='127.0.0.1:8791',origin=origin,
                **{'content-type':'application/json','cookie':self.cookie,'x-yam-runner-token':self.csrf}).items()]},receive,send)
        header=dict(messages[0]['headers'])
        if b'set-cookie' in header:self.cookie=header[b'set-cookie'].decode().split(';')[0]
        return messages[0]['status'],json.loads(b''.join(m.get('body',b'') for m in messages[1:]))

    async def test_documented_start_status_stop_contract_and_auth(self):
        self.assertEqual((await self.call('/api/status'))[0],401)
        code,session=await self.call('/api/session',{})
        self.assertEqual(code,200)
        self.assertEqual(session['configured_providers']['reset_bin']['label'],'Reset bin')
        payload=dict(provider='reset_bin',model='reset-bin-v1',prompt='Reset bin',runner_name='API operator',run_duration_s=600)
        self.assertEqual((await self.call('/api/run',payload))[0],403)
        self.csrf=session['csrf']
        self.assertEqual((await self.call('/api/run',payload,origin='https://other.test'))[0],403)
        code,run=await self.call('/api/run',payload)
        self.assertEqual(code,200);self.assertTrue(run['attempt_id'])
        self.assertEqual((await self.call('/api/run',payload))[0],409)
        code,status=await self.call('/api/status')
        self.assertEqual(code,200);self.assertEqual(status['attempt_id'],run['attempt_id'])
        self.assertEqual(status['provider']['model'],'reset-bin-v1')
        self.assertEqual(status['saved_key_providers'],[])
        # A different visitor cannot start any policy while this worker owns it.
        old_cookie,old_csrf=self.cookie,self.csrf
        self.cookie='';self.csrf=''
        _,other=await self.call('/api/session',{});self.csrf=other['csrf']
        self.assertEqual((await self.call('/api/run',dict(payload,provider='local_raise_lower')))[0],409)
        self.cookie,self.csrf=old_cookie,old_csrf
        visitor=self.app._managed_owner
        for _ in range(200):
            if (visitor.controller._provider.output/'status.json').exists():break
            await asyncio.sleep(.01)
        self.assertEqual((await self.call('/api/stop',{}))[0],200)
        await asyncio.to_thread(visitor.controller._worker.join,3)
        _,status=await self.call('/api/status')
        self.assertEqual(status['status'],'stopped')
        self.assertFalse(status['provider']['managed_execution']['result']['goals_reached'])
        self.assertEqual(visitor.controller._session_api.create_requests,[])


if __name__=='__main__':unittest.main()
