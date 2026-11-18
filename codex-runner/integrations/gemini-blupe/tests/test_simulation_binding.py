"""Controller/replay mutation regressions; SDK and engine never use the network."""
import asyncio
import hashlib
import json
from pathlib import Path
import time
import os
import sys
import unittest
from unittest.mock import patch

import test_worker as helpers
w=helpers.w
import simulation_artifacts as artifacts
from executor import SimulationExecutor


class ScriptedExecutor:
    tamper_station_once=False
    def __init__(self,workspace):self.workspace=workspace;self.last_execution=None;self.calls=0
    async def run(self,timeout_s=90):
        # Trusted offline engine double. This is not a MuJoCo/model pass.
        before=artifacts.input_snapshot(self.workspace)
        report=dict(controller_completed=True,error=None,physical=False,task_success_verified=False,
                    controller_sha256=hashlib.sha256((self.workspace/'controller.py').read_bytes()).hexdigest(),
                    station_snapshot_sha256=hashlib.sha256((self.workspace/'station.json').read_bytes()).hexdigest())
        (self.workspace/'report.json').write_text(json.dumps(report))
        (self.workspace/'simulation.mp4').write_bytes(b'offline-engine-video-fixture')
        self.calls+=1
        if type(self).tamper_station_once and self.calls==1:
            (self.workspace/'station.json').write_text('{"forged_by_previous_execution":true}')
        self.last_execution,report=artifacts.retain_execution(self.workspace,before,
            image='sha256:'+'c'*64,variant='yam1',exit_code=0,log='scripted offline engine',cleanup_confirmed=True)
        return dict(exit_code=0,report=report,execution=self.last_execution)
    async def stop(self):pass


class EditingAgent:
    reached_end=False
    edit_after=True
    resimulate=False
    identical_write=False
    def __init__(self,config):self.tools={fn.__name__:fn for fn in config.tools}
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def chat(self,prompt):
        await self.tools['write_controller']('def run(env):\n    env.left.set_gripper(0.)\n')
        await self.tools['simulate_controller']()
        # Editing after simulation must invalidate its eligibility, never reuse
        # the old replay as evidence for this new source.
        if type(self).edit_after:
            code=('def run(env):\n    env.left.set_gripper(0.)\n' if type(self).identical_write else
                  'def run(env):\n    env.right.set_gripper(1.)\n')
            await self.tools['write_controller'](code)
        if type(self).resimulate:await self.tools['simulate_controller']()
        type(self).reached_end=True
        async def response():yield 'Offline scripted mutation case'
        return response()


class SimulationBindingTests(unittest.TestCase):
    setUp=helpers.WorkerTests.setUp

    def scripted_run(self,*,edit_after=True,resimulate=False,identical_write=False,tamper_station_once=False):
        EditingAgent.reached_end=False;EditingAgent.edit_after=edit_after;EditingAgent.resimulate=resimulate
        EditingAgent.identical_write=identical_write;ScriptedExecutor.tamper_station_once=tamper_station_once
        row=self.store.create(self.spec,'a'*64)
        station=dict(calibration=dict(calibration_id='offline'),observation=dict(source='offline_fixture'),camera_frames={})
        with patch.dict('os.environ',{'GEMINI_API_KEY':'synthetic-key'}), \
             patch.object(w,'SimulationExecutor',ScriptedExecutor), \
             patch('google.antigravity.Agent',EditingAgent), \
             patch('station_inputs.collect_station_inputs',return_value=(station,[])), \
             patch('station_inputs.sdk_prompt',return_value=['offline fixture']):
            asyncio.run(w.run_agent(self.store,row['id'],Path(self.temp.name)))
        result=self.store.get(row['id'])
        self.assertTrue(EditingAgent.reached_end,result)
        return result

    def test_edit_after_simulation_cannot_complete_using_previous_replay(self):
        result=self.scripted_run()
        self.assertEqual(result['state'],'failed',result)
        self.assertNotEqual(result['progress'],'Simulation finished; report and video are available for review')
        self.assertEqual(len(result['configuration']['simulation_attempts']),1)
        self.assertTrue(any(a['name']=='simulation.mp4' for a in result['artifacts']))

    def test_current_source_completes_with_retained_host_report_and_original_start(self):
        result=self.scripted_run(edit_after=False)
        self.assertEqual(result['state'],'complete',result)
        self.assertFalse(result['result']['verified'])
        attempt=result['configuration']['simulation_attempts'][0]
        self.assertTrue(attempt['binding_passed'])
        self.assertEqual(result['result']['execution_id'],attempt['id'])
        self.assertLessEqual(result['created_at'],result['events'][0]['at'])
        self.assertNotIn('private@example.test',json.dumps(result))

    def test_identical_source_write_reuses_valid_execution_without_extra_simulation(self):
        result=self.scripted_run(identical_write=True)
        self.assertEqual(result['state'],'complete',result)
        self.assertEqual(len(result['configuration']['simulation_attempts']),1)

    def test_resimulation_restores_host_scene_after_generated_workspace_mutation(self):
        result=self.scripted_run(edit_after=False,resimulate=True,tamper_station_once=True)
        self.assertEqual(result['state'],'complete',result)
        attempts=result['configuration']['simulation_attempts'];self.assertEqual(len(attempts),2)
        self.assertEqual([a['binding_passed'] for a in attempts],[False,True])
        self.assertTrue(all(a['station_snapshot_sha256']==result['configuration']['station_snapshot_sha256'] for a in attempts))

    def test_resimulation_preserves_each_attempt_and_protected_history_artifacts(self):
        result=self.scripted_run(resimulate=True)
        self.assertEqual(result['state'],'complete',result)
        attempts=result['configuration']['simulation_attempts'];self.assertEqual(len(attempts),2)
        self.assertEqual(result['result']['execution_id'],attempts[-1]['id'])
        videos=[a for a in result['artifacts'] if a['name']=='simulation.mp4']
        self.assertEqual([v['attempt'] for v in videos],[2,1])
        controller=next(a for a in result['artifacts'] if a['name']=='controller.py' and a['attempt']==1)
        (self.store.root/result['id']/'controller.py').write_text('forged mutable workspace')
        app=w.create_app(self.temp.name)
        with patch.dict(os.environ,{'GEMINI_SITE_TOKEN':'test-secret'}):
            status,_=asyncio.run(helpers.request(app,controller['url']));self.assertEqual(status,403)
            status,body=asyncio.run(helpers.request(app,controller['url'],headers={'x-gemini-site-token':'test-secret'},as_json=False))
            self.assertEqual(status,200);self.assertIn(b'env.left.set_gripper(0.)',body)
            path=self.store.root/'simulation-evidence'/result['id']/controller['execution_id']/'controller.py'
            path.write_text('changed protected original')
            status,_=asyncio.run(helpers.request(app,controller['url'],headers={'x-gemini-site-token':'test-secret'}))
            self.assertEqual(status,404)


ENGINE_SCRIPT='''#!PYTHON
import hashlib,json,sys,time
from pathlib import Path
args=sys.argv[1:]
if args[0]=='run':
    work=Path(args[args.index('--volume')+1].removesuffix(':/workspace:rw'))
    active=Path(__file__).with_name('engine-active');active.touch()
    mode=Path(__file__).with_name('engine-mode').read_text()
    if mode=='mutate':(work/'controller.py').write_text('modified during execution')
    if mode=='station':(work/'station.json').write_text('{"changed":true}')
    report=dict(controller_completed=True,error=None,physical=False,task_success_verified=False,
        controller_sha256=hashlib.sha256((work/'controller.py').read_bytes()).hexdigest(),
        station_snapshot_sha256=hashlib.sha256((work/'station.json').read_bytes()).hexdigest())
    if mode=='forged':report['controller_sha256']='f'*64
    if mode=='symlink':(work/'report.json').symlink_to(work/'controller.py')
    else:(work/'report.json').write_text(json.dumps(report))
    (work/'simulation.mp4').write_bytes(b'offline engine video fixture')
    (work/'commands.json').write_text('[]')
    print('trusted offline engine, no generated code or network',flush=True)
    if mode in ('timeout','cleanup-fails'):time.sleep(20)
    active.unlink(missing_ok=True)
    sys.exit(0)
if args[0]=='rm':
    if Path(__file__).with_name('engine-mode').read_text()!='cleanup-fails':
        Path(__file__).with_name('engine-active').unlink(missing_ok=True)
    sys.exit(0)
if args[:2]==['container','exists']:
    sys.exit(0 if Path(__file__).with_name('engine-active').exists() else 1)
sys.exit(2)
'''


class ExecutorBindingTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.work=self.root/'job';self.work.mkdir()
        self.controller=b'def run(env): pass\n';self.station=b'{"source":"offline_fixture"}'
        (self.work/'controller.py').write_bytes(self.controller);(self.work/'station.json').write_bytes(self.station)
        self.engine=self.root/'offline-engine';self.engine.write_text(ENGINE_SCRIPT.replace('PYTHON',sys.executable,1));self.engine.chmod(0o700)
        self.mode=self.root/'engine-mode';self.mode.write_text('normal')
        self.env=patch.dict(os.environ,{'GEMINI_CONTAINER_ENGINE':str(self.engine),'GEMINI_SIM_IMAGE':'sha256:'+'c'*64,'GEMINI_SIM_VARIANT':'yam1'});self.env.start();self.addCleanup(self.env.stop)

    def test_real_executor_retains_source_bound_files_outside_job_mount(self):
        executor=SimulationExecutor(self.work);result=asyncio.run(executor.run())
        receipt=result['execution'];self.assertTrue(receipt['binding_passed'],receipt)
        self.assertTrue(executor.cleanup_confirmed)
        self.assertTrue(artifacts.current_controller_matches(self.work,receipt))
        bundle=self.root/'simulation-evidence/job'/receipt['id']
        self.assertEqual((bundle/'controller.py').read_bytes(),self.controller)
        (self.work/'report.json').write_text('forged after execution')
        self.assertTrue(json.loads((bundle/'report.json').read_text())['controller_completed'])
        (self.work/'controller.py').write_text('new untested source')
        self.assertFalse(artifacts.current_controller_matches(self.work,receipt))

    def test_changed_inputs_or_forged_report_never_bind_even_with_zero_exit(self):
        for mode in ('mutate','station','forged','symlink'):
            with self.subTest(mode=mode):
                self.mode.write_text(mode)
                (self.work/'controller.py').write_bytes(self.controller);(self.work/'station.json').write_bytes(self.station)
                executor=SimulationExecutor(self.work);result=asyncio.run(executor.run())
                receipt=result['execution'];self.assertEqual(result['exit_code'],0)
                self.assertFalse(receipt['binding_passed']);self.assertTrue(receipt['rejections'])
                self.assertFalse(artifacts.current_controller_matches(self.work,receipt))
                bundle=self.root/'simulation-evidence/job'/receipt['id']
                self.assertEqual((bundle/'controller.py').read_bytes(),self.controller)
                self.assertEqual((bundle/'station.json').read_bytes(),self.station)

    def test_timeout_preserves_failed_attempt_after_confirmed_removal(self):
        self.mode.write_text('timeout');executor=SimulationExecutor(self.work)
        with self.assertRaises(TimeoutError):asyncio.run(executor.run(timeout_s=.2))
        self.assertTrue(executor.cleanup_confirmed)
        self.assertFalse(executor.last_execution['binding_passed'])
        self.assertNotEqual(executor.last_execution['exit_code'],0)
        self.assertFalse((self.root/'engine-active').exists())

    def test_cleanup_failure_cannot_promote_simulation_or_copy_live_outputs(self):
        self.mode.write_text('cleanup-fails');executor=SimulationExecutor(self.work)
        with self.assertRaisesRegex(RuntimeError,'cleanup could not be confirmed'):
            asyncio.run(executor.run(timeout_s=.2))
        self.assertFalse(executor.cleanup_confirmed);self.assertIsNone(executor.last_execution)
        self.assertFalse((self.root/'simulation-evidence').exists())
        self.assertTrue(executor.active_invocation)
        with self.assertRaisesRegex(RuntimeError,'no new execution started'):asyncio.run(executor.run())

    def test_regular_file_reader_rejects_links_fifos_and_oversize_without_blocking(self):
        link=self.root/'link';link.symlink_to(self.work/'controller.py')
        fifo=self.root/'fifo';os.mkfifo(fifo)
        for path,limit in ((link,1000),(fifo,1000),(self.work/'controller.py',2)):
            with self.subTest(path=path.name),self.assertRaises((OSError,ValueError)):
                artifacts.read_regular(path,limit)

    def test_owned_filename_replacement_never_follows_links_or_blocks_on_fifo(self):
        outside=self.root/'untouched';outside.write_bytes(b'original')
        link=self.work/'link';link.symlink_to(outside)
        fifo=self.work/'fifo';os.mkfifo(fifo)
        for path in (link,fifo):
            artifacts.write_private(path,b'host replacement')
            self.assertEqual(path.read_bytes(),b'host replacement')
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
        self.assertEqual(outside.read_bytes(),b'original')


if __name__=='__main__':unittest.main()
