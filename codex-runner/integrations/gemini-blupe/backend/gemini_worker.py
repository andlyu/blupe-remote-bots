"""Persistent Gemini Robotics worker. No direct CAN or motor ownership.

SDK contract: google-antigravity 0.1.23, official agent_skills.py example.
Physical readiness is supplied only by the separately qualified BluPe bridge.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager,contextmanager
import hashlib
import hmac
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from typing import Literal
import uuid

from fastapi import FastAPI, HTTPException, Request

try:
    from .executor import SimulationExecutor
    from .simulation_artifacts import current_controller_matches, read_regular, write_private
except ImportError:
    from executor import SimulationExecutor
    from simulation_artifacts import current_controller_matches, read_regular, write_private
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

APPROACH = 'Gemini Robotics'
MODEL = os.environ.get('GEMINI_MODEL', 'gemini-4-hydrogen')
SIMULATION_VARIANT = 'yam1'
TERMINAL = {'complete', 'failed', 'cancelled'}
PUBLIC_FIELDS = ('launch_requested_at','stop_requested_at','id', 'runner_name', 'prompt', 'mode', 'state', 'created_at',
                 'updated_at', 'duration_s', 'progress', 'events', 'artifacts',
                 'configuration', 'result')


class RunInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: uuid.UUID
    launch_requested_at: float | None = None
    runner_name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=200)
    prompt: str = Field(min_length=1, max_length=4000)
    duration_s: int = Field(default=180, ge=60, le=600)
    mode: Literal['simulation', 'robot']
    execution_mode: Literal['interactive', 'automated test'] = 'interactive'


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = root / 'runs.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, owner TEXT NOT NULL, email TEXT NOT NULL, data TEXT NOT NULL)')
        os.chmod(self.db, 0o600)

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.db,timeout=10)
        try:
            with db:yield db
        finally:db.close()

    def create(self, spec: RunInput, owner: str):
        name, email, prompt = spec.runner_name.strip(), spec.email.strip(), spec.prompt.strip()
        if not name or name.lower() in {'anonymous', 'autonomous', 'automated'} or any(ord(c) < 32 for c in name):
            raise HTTPException(400, 'Enter the actual runner name')
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or not prompt:
            raise HTTPException(400, 'Enter a valid email and task')
        now = time.time()
        if spec.launch_requested_at is not None and not math.isfinite(spec.launch_requested_at):
            raise HTTPException(400, 'Start timestamp must be finite')
        data = dict(launch_requested_at=spec.launch_requested_at,
                    stop_requested_at=None,id=str(spec.request_id), runner_name=name, prompt=prompt,
                    mode=spec.mode, duration_s=spec.duration_s, state='queued',
                    created_at=now, updated_at=now, progress='Waiting for the Gemini worker',
                    events=[], artifacts=[], result=None,
                    configuration=dict(approach=APPROACH, model=APPROACH,
                        start_clock_source='browser' if spec.launch_requested_at is not None else 'server_received_legacy',
                        underlying_models=dict(planning=MODEL, vision=MODEL, coding=MODEL, resolved=None),
                        robot_id='yam-1', execution_mode=spec.execution_mode,
                        variant='Antigravity Robotics adapted to BluPe',
                        source_revision=os.environ.get('GEMINI_SOURCE_REVISION'),
                        simulation_image=os.environ.get('GEMINI_SIM_IMAGE'),
                        simulation_variant=SIMULATION_VARIANT,
                        robotics_plugin='9cb7f624c4d7c50859a39f1d49d088990429a83d',
                        mujoco_playground='c9de052f099a36be915af38344f427aacdbf3abe'))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT owner,email,data FROM runs WHERE id=?', (data['id'],)).fetchone()
            if old:
                if not hmac.compare_digest(old[0], owner):
                    raise HTTPException(409, 'Request identifier belongs to another visitor')
                retained = json.loads(old[2])
                if spec.launch_requested_at is not None and spec.launch_requested_at != retained.get('launch_requested_at',retained['created_at']):
                    raise HTTPException(409, 'Request identifier retains its original Start timestamp')
                if old[1] != email or retained['configuration']['execution_mode'] != spec.execution_mode:
                    raise HTTPException(409, 'Request identifier was already used for different attribution')
                if any(retained[k] != data[k] for k in ('prompt', 'mode', 'duration_s', 'runner_name')):
                    raise HTTPException(409, 'Request identifier was already used for different settings')
                return retained
            db.execute('INSERT INTO runs VALUES(?,?,?,?)', (data['id'], owner, email, json.dumps(data)))
        return data

    def get(self, ident: str):
        with self.connect() as db:
            row = db.execute('SELECT data FROM runs WHERE id=?', (ident,)).fetchone()
        if not row:
            raise HTTPException(404, 'Run not found')
        return json.loads(row[0])

    def _edit(self,ident,change):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT data FROM runs WHERE id=?',(ident,)).fetchone()
            if not row:raise HTTPException(404,'Run not found')
            data=json.loads(row[0])
            if change(data):
                data['updated_at']=time.time()
                db.execute('UPDATE runs SET data=? WHERE id=?',(json.dumps(data),ident))
        return data

    @staticmethod
    def _transition_allowed(data,state):
        if data['state'] in TERMINAL and state!=data['state']:return False
        if data['mode']=='robot' and data.get('stop_requested_at') is not None:
            return state in {'stopping','cancelled','failed'}
        return True

    def update(self,ident,**values):
        def change(data):
            if 'state' in values and not self._transition_allowed(data,values['state']):return False
            data.update(values);return True
        return self._edit(ident,change)

    def event(self,ident,stage,message):
        def change(data):
            if not self._transition_allowed(data,stage):return False
            data.update(state=stage,progress=message)
            data['events'].append(dict(stage=stage,message=message,at=time.time()))
            return True
        return self._edit(ident,change)

    def note(self,ident,stage,message,at):
        def change(data):
            data['events'].append(dict(stage=stage,message=message,at=at));return True
        return self._edit(ident,change)

    def request_stop(self,ident):
        def change(data):
            if data['state'] in TERMINAL or data.get('stop_requested_at') is not None:return False
            stamp=time.time();data['stop_requested_at']=stamp
            pending=data['mode']=='robot' and data['state']!='queued'
            stage='stopping' if pending else 'cancelled'
            message=('Requesting Stop; waiting for controller acknowledgement and recording' if pending
                     else 'Stopped before execution' if data['mode']=='robot' else 'Stopped by the runner')
            data.update(state=stage,progress=message)
            data['events'].append(dict(stage=stage,message=message,at=stamp))
            return True
        return self._edit(ident,change)

    def stop_requested(self,ident):
        row=self.get(ident)
        return row.get('stop_requested_at') is not None or row['state'] in {'stopping','cancelled'}

    def private_email(self,ident):
        with self.connect() as db:row=db.execute('SELECT email FROM runs WHERE id=?',(ident,)).fetchone()
        if not row:raise HTTPException(404,'Run not found')
        return row[0]

    def physical_status(self,ident,status):
        from physical_evidence import public_status
        public=public_status(status)
        def change(data):
            if data['configuration'].get('physical')==public:return False
            data['configuration']['physical']=public;return True
        return self._edit(ident,change)

    def retain_physical(self,ident,artifacts):
        def change(data):
            data['artifacts']=[a for a in data['artifacts'] if a.get('kind')!='physical']+artifacts
            return True
        return self._edit(ident,change)

    def retain_execution(self, ident, receipt):
        data=self.get(ident)
        if any(item.get('execution_id')==receipt['id'] for item in data['artifacts']):return
        attempts=data['configuration'].get('simulation_attempts',[])
        attempt=len(attempts)+1
        records=[dict(**item,kind='simulation',execution_id=receipt['id'],attempt=attempt,
                      url=f"/api/runs/{ident}/executions/{receipt['id']}/artifacts/{item['name']}")
                 for item in receipt['artifacts']]
        inputs=[a for a in data['artifacts'] if a.get('kind')=='input']
        older=[a for a in data['artifacts'] if a.get('kind')!='input']
        config={**data['configuration'],'simulation_attempts':[*attempts,
            {key:receipt[key] for key in ('id','created_at','image','variant','exit_code',
                'cleanup_confirmed','binding_passed','rejections','controller_sha256','station_snapshot_sha256')}]}
        return self.update(ident,artifacts=inputs+records+older,configuration=config)

    def owned(self, ident, owner):
        with self.connect() as db:
            row = db.execute('SELECT owner FROM runs WHERE id=?', (ident,)).fetchone()
        return bool(row and hmac.compare_digest(row[0], owner))

    def recent(self):
        with self.connect() as db:
            rows = db.execute("SELECT data FROM runs ORDER BY json_extract(data,'$.created_at') DESC LIMIT 50").fetchall()
        return [json.loads(row[0]) for row in rows]


def provider_failure_code(message):
    """Classify only the observed billing failure; never expose provider bodies."""
    text = message.lower()
    if ('http 402' in text or 'error 402' in text) and ('prepayment credits' in text or 'prepay' in text):
        return 'google_prepay_depleted'
    return None


def retain_provider_failure(root, ident, message):
    code = provider_failure_code(message)
    if code:
        record = dict(code=code, run_id=ident, observed_at=time.time())
        temp = root / ('.provider-' + secrets.token_hex(8))
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as file:
            json.dump(record, file)
        os.replace(temp, root / 'provider-status.json')
        print('[gemini-worker] ' + json.dumps(dict(event='provider_unavailable', code=code, run_id=ident)), flush=True)
    return code


def runtime_status(skills: Path, state_root: Path | None = None):
    versions = {}
    for package in ('google-antigravity', 'mujoco', 'playground', 'reaf', 'reaf-sim'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    skills_ready = (skills / 'mujoco-playground' / 'SKILL.md').is_file()
    proof = {}
    try:
        proof = json.loads(Path(os.environ.get('GEMINI_EXECUTOR_PROOF', '/nonexistent')).read_text())
    except (OSError, ValueError):
        pass
    executor_ready = bool(proof.get('isolation_passed') and proof.get('simulation_passed')
                          and proof.get('image') == os.environ.get('GEMINI_SIM_IMAGE')
                          and proof.get('variant') == SIMULATION_VARIANT
                          and os.environ.get('GEMINI_SIM_VARIANT','yam1') == SIMULATION_VARIANT)
    provider_code = None
    try:
        retained = json.loads(((state_root or Path(os.environ.get('GEMINI_STATE_DIR', '/tmp/gemini-blupe-state'))) / 'provider-status.json').read_text())
        if retained.get('code') == 'google_prepay_depleted':
            provider_code = retained['code']
    except (OSError, ValueError):
        pass
    simulation_ready = bool(not provider_code and os.environ.get('GEMINI_API_KEY') and skills_ready
                            and versions['google-antigravity'] and executor_ready)
    return dict(online=True, client_start_supported=True, simulation_ready=simulation_ready, physical_ready=False,
                model=MODEL, approach=APPROACH, versions=versions, skills_ready=skills_ready,
                executor_ready=executor_ready, provider_error=provider_code, source_revision=os.environ.get('GEMINI_SOURCE_REVISION'), simulation_variant=SIMULATION_VARIANT, simulation_scope='YAM1 adapted bimanual simulator; task-scene/contact qualification pending',
                message=('Google API credits are depleted; the owner needs to restore billing' if provider_code else ('YAM1 simulation worker ready; task-scene/contact qualification pending' if simulation_ready else ('Gemini API key is not configured' if not os.environ.get('GEMINI_API_KEY') else 'Simulation runtime is being prepared'))),
                physical_message='YAM 1 adapter qualification is pending')


async def run_agent(store, ident, skills):
    from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig
    from google.antigravity.policy import deny, allow
    from google.antigravity.types import BudgetConfig, RetryConfig, ModelAPIRetryConfig, ModelOutputRetryConfig
    job = store.get(ident)
    if store.stop_requested(ident):return
    physical_started=False
    workspace = store.root / ident
    workspace.mkdir(mode=0o700, exist_ok=True)
    stop = asyncio.Event()
    store.event(ident, 'generating', 'Hydrogen is preparing the controller and simulation')
    executor = SimulationExecutor(workspace)
    tool_lock = asyncio.Lock()
    last_execution = None
    async def read_robotics_reference(path: str) -> str:
        """Read a path relative to the installed Google Robotics skills directory."""
        file = (skills / path).resolve()
        if not file.is_relative_to(skills.resolve()) or file.suffix not in {'.md', '.py', '.json', '.xml'} or not file.is_file() or file.stat().st_size > 160000:
            raise ValueError('Choose a reference file inside the installed Robotics skills')
        return file.read_text()
    async def read_station_reference() -> str:
        """Read the exact adapted bimanual YAM1 controller API and frame/limit notes."""
        return (Path(__file__).resolve().parents[1] / 'docs/YAM1-CONTROLLER-API.md').read_text()
    async def write_controller(code: str) -> str:
        """Write controller.py defining run(env) using the adapted YAM1 API from read_station_reference."""
        nonlocal last_execution
        import ast
        if len(code.encode()) > 160000:
            raise ValueError('Controller is too large')
        ast.parse(code)
        async with tool_lock:
            path = workspace / 'controller.py'
            try:unchanged=read_regular(path,160000)==code.encode()
            except (OSError,ValueError):unchanged=False
            if not unchanged:last_execution=None
            write_private(path,code.encode())
        store.event(ident, 'generating', 'Controller written; preparing its actual simulation')
        return 'controller.py saved'
    async def simulate_controller() -> dict:
        """Run controller.py in isolated bimanual YAM1 MuJoCo and return actual results and limitations."""
        nonlocal last_execution
        async with tool_lock:
            if getattr(executor,'active_invocation',False):
                raise RuntimeError('Previous simulation cleanup is unverified; no new execution started')
            last_execution=None
            # Every attempt starts with the host's originally captured scene,
            # never a station file that generated code changed in a prior run.
            station=read_regular(store.root/'input-evidence'/ident/'station.json',64000)
            if hashlib.sha256(station).hexdigest()!=store.get(ident)['configuration']['station_snapshot_sha256']:
                raise RuntimeError('Original captured station evidence changed; no simulation started')
            write_private(workspace/'station.json',station)
            store.event(ident, 'simulating', 'Running the generated controller in MuJoCo and recording its behavior')
            try:
                last_execution = await executor.run(timeout_s=min(90, max(1, job['created_at'] + job['duration_s'] - time.time())))
            finally:
                if executor.last_execution:store.retain_execution(ident,executor.last_execution)
        return last_execution
    # Official SDK custom-tool/skills interface; all builtin tools disabled.
    # Only generated code in a keyless, offline per-run container can execute.
    names = ['read_robotics_reference', 'read_station_reference', 'write_controller', 'simulate_controller']
    config = LocalAgentConfig(model=MODEL, api_key=os.environ['GEMINI_API_KEY'],
        capabilities=CapabilitiesConfig(enabled_tools=[], enable_subagents=False),
        tools=[read_robotics_reference, read_station_reference, write_controller, simulate_controller],
        policies=[deny('*'), *[allow(name) for name in names]],
        budget_config=BudgetConfig(max_model_calls=12, max_total_tokens=64000),
        retry_config=RetryConfig(api_retry=ModelAPIRetryConfig(max_retries=0), model_output_retry=ModelOutputRetryConfig(max_retries=0)),
        workspaces=[str(workspace)], skills_paths=[str(skills)],
        system_instructions=(
            'You are the Gemini Robotics worker. Use the installed Google Robotics skills, starting '
            'with mujoco-playground/SKILL.md via read_robotics_reference, then read_station_reference. Write a controller.py '
            'defining run(env), where env is the adapted bimanual YAM1 environment with env.left and env.right. '
            'Use write_controller and simulate_controller to execute and inspect actual results; fix failures. '
            'The model has the installed arm/tool geometry, native joint limits and provisional camera calibration. '
            'Robot dynamics are nominal, and current object/contact reconstruction is pending. Explain these limits '
            'and do not claim physical or manipulation qualification. Do not silently use the stock single-arm API. '
            'The run uses10Hz canonical packets, native-default simulated joint settling, no automatic hover or park. '
            'Use observable images and joint feedback, not privileged object poses. Keep simulation '
            'bounded to 60 simulated seconds. No physical hardware or network is available in execution. '
            'The container handles report.json and simulation.mp4 recording. Never fabricate evidence. '
            'Summarize actual results, remaining gaps and assumptions without hidden reasoning.'))
    async def cancelled():
        while True:
            if store.stop_requested(ident):
                stop.set()
                return
            await asyncio.sleep(.2)
    async def infer():
        try:
            from .station_inputs import collect_station_inputs, sdk_prompt
        except ImportError:
            from station_inputs import collect_station_inputs, sdk_prompt
        if store.stop_requested(ident):raise asyncio.CancelledError()
        store.event(ident, 'generating', 'Reading current YAM1 cameras, joints and calibration')
        station, frames = await asyncio.to_thread(collect_station_inputs)
        if stop.is_set() or store.stop_requested(ident):
            raise asyncio.CancelledError()
        if time.time()>=job['created_at']+job['duration_s']:
            raise TimeoutError('Run duration expired during station observation')
        evidence=store.root/'input-evidence'/ident
        evidence.mkdir(parents=True,exist_ok=True,mode=0o700)
        blobs={'station.json':(json.dumps(station,indent=2)+'\n').encode()}
        blobs.update({'input-'+f.name+'.jpg':f.jpeg for f in frames})
        input_artifacts=[]
        for name,data in blobs.items():
            fd=os.open(evidence/name,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as file:file.write(data)
            input_artifacts.append(dict(name=name,kind='input',url=f'/api/runs/{ident}/artifacts/{name}',bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
        fd=os.open(workspace/'station.json',os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as file:file.write(blobs['station.json'])
        configuration={**job['configuration'], 'calibration_id':station['calibration']['calibration_id'],
                       'station_snapshot_sha256':hashlib.sha256(blobs['station.json']).hexdigest(),
                       'input_cameras':station['camera_frames']}
        store.update(ident,configuration=configuration,artifacts=input_artifacts)
        store.event(ident,'generating','Current scene captured; Hydrogen is preparing the controller')
        async with Agent(config) as agent:
            response = await agent.chat(sdk_prompt(job['prompt'],station,frames))
            text = ''
            async for token in response:
                text += token
                if len(text) > 64000:
                    text = text[-64000:]
            return text
    inference = asyncio.create_task(infer())
    watcher = asyncio.create_task(cancelled())
    try:
        done, _ = await asyncio.wait([inference, watcher], timeout=max(0, job['created_at'] + job['duration_s'] - time.time()), return_when=asyncio.FIRST_COMPLETED)
        if inference not in done:
            inference.cancel()
            await asyncio.gather(inference, return_exceptions=True)
            if stop.is_set():
                if job['mode']=='robot':store.event(ident,'cancelled','Stopped before robot queue admission')
                return
            raise TimeoutError('Run duration expired during controller generation/simulation')
        result = inference.result()
        # A model's text alone is not a successful simulation or task pass.
        receipt=last_execution.get('execution') if last_execution else None
        if not last_execution or not current_controller_matches(workspace,receipt):
            store.update(ident,result=dict(summary=result,verified=False))
            raise RuntimeError('Saved controller has no matching completed simulation; simulate the current source before handoff')
        report = last_execution['report']
        store.update(ident,result=dict(summary=result,report=report,execution_id=receipt['id'],verified=False))
        if store.stop_requested(ident):
            store.event(ident,'cancelled','Stopped before robot queue admission')
        elif job['mode']=='robot':
            from physical_store import run_physical
            physical_started=True
            await run_physical(store,ident,receipt)
        else:
            store.event(ident, 'complete', 'Simulation finished; report and video are available for review')
    except asyncio.CancelledError:
        if job['mode']=='robot' and not physical_started and store.stop_requested(ident):
            store.event(ident,'cancelled','Stopped before robot queue admission')
        inference.cancel()
        await asyncio.gather(inference, return_exceptions=True)
        raise
    except Exception as exc:
        # Provider bodies/tracebacks may echo credentials; retain a bounded class
        # and our own known error messages only in public status.
        provider_code = retain_provider_failure(store.root, ident, str(exc))
        message = str(exc) if type(exc) in (TimeoutError, RuntimeError, json.JSONDecodeError) else type(exc).__name__
        if provider_code:
            message = 'Google API credits are depleted; the owner needs to restore billing'
        key = os.environ.get('GEMINI_API_KEY', '')
        if key:
            message = message.replace(key, '[redacted]')
        store.event(ident, 'failed', message[:500])
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
        await asyncio.shield(executor.stop())


def create_app(state_root=None, skills_root=None):
    store = Store(Path(state_root or os.environ.get('GEMINI_STATE_DIR', '/tmp/gemini-blupe-state')))
    skills = Path(skills_root or os.environ.get('GEMINI_SKILLS_ROOT', '/opt/robotics/plugins/robotics/skills'))
    active = {}
    semaphore = asyncio.Semaphore(1)
    async def queued_run(ident):
        async with semaphore:
            if store.get(ident)['state'] != 'queued':
                return
            await run_agent(store, ident, skills)
    @asynccontextmanager
    async def lifespan(app):
        # Restart never replays a possibly dispatched run.
        for job in store.recent():
            if job['state'] not in TERMINAL:
                store.event(job['id'], 'failed', 'Worker restarted; execution was not replayed')
        yield
        for task in active.values():
            task.cancel()
        await asyncio.gather(*active.values(), return_exceptions=True)
    app = FastAPI(lifespan=lifespan)
    app.state.store = store
    def authenticate(request):
        token = os.environ.get('GEMINI_SITE_TOKEN', '')
        supplied = request.headers.get('x-gemini-site-token', '')
        if not token or not hmac.compare_digest(token, supplied):
            raise HTTPException(403, 'Site authentication required')
    def owner(request):
        value = request.headers.get('x-gemini-visitor', '')
        if not re.fullmatch('[a-f0-9]{64}', value):
            raise HTTPException(403, 'Visitor capability required')
        return value
    @app.get('/health')
    async def health():
        return runtime_status(skills, store.root)
    @app.get('/api/state')
    async def state(request: Request):
        authenticate(request)
        who = request.headers.get('x-gemini-visitor', '')
        return dict(worker=runtime_status(skills, store.root), runs=[{**{k:j.get(k) for k in PUBLIC_FIELDS}, 'owned':store.owned(j['id'], who)} for j in store.recent()])
    @app.post('/api/runs')
    async def start(spec: RunInput, request: Request):
        authenticate(request)
        who = owner(request)
        if spec.mode == 'robot':
            raise HTTPException(503, 'YAM 1 adapter qualification is pending; no robot request submitted')
        status = runtime_status(skills, store.root)
        if not status['simulation_ready']:
            raise HTTPException(503, status['message'])
        job = store.create(spec, who)
        if job['id'] not in active and job['state'] == 'queued':
            task = asyncio.create_task(queued_run(job['id']))
            active[job['id']] = task
            task.add_done_callback(lambda _: active.pop(job['id'], None))
        return {k:job.get(k) for k in PUBLIC_FIELDS}
    @app.post('/api/runs/{ident}/stop')
    async def stop(ident: uuid.UUID, request: Request):
        authenticate(request)
        if not store.owned(str(ident), owner(request)):
            raise HTTPException(403, 'This browser does not own the run')
        job = store.get(str(ident))
        if job['state'] not in TERMINAL:
            store.request_stop(str(ident))
        return {'ok': True}
    @app.get('/api/runs/{ident}/artifacts/{name}')
    @app.get('/api/runs/{ident}/executions/{execution}/artifacts/{name}')
    async def artifact(ident: uuid.UUID, name: str, request: Request, execution: uuid.UUID | None = None):
        authenticate(request)
        if name not in {'controller.py', 'simulation.mp4', 'report.json','station.json','input-top.jpg','input-left.jpg','input-right.jpg','execution.json','commands.json','simulation.log','physical.mp4','physical.json'}:
            raise HTTPException(404)
        job = store.get(str(ident))
        record = next((a for a in job['artifacts'] if a['name'] == name and
                       (execution is None or a.get('execution_id')==execution.hex)), None)
        directory=store.root/str(ident)
        if record and record.get('kind')=='input':directory=store.root/'input-evidence'/str(ident)
        if record and record.get('kind')=='physical':directory=store.root/'physical-evidence'/str(ident)
        if record and record.get('kind')=='simulation':
            directory=store.root/'simulation-evidence'/str(ident)/uuid.UUID(record['execution_id']).hex
        file = directory / name
        if not record or not file.is_file() or file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest() != record['sha256']:
            raise HTTPException(404, 'Retained artifact unavailable')
        return FileResponse(file, media_type={'py':'text/plain','log':'text/plain','mp4':'video/mp4','json':'application/json','jpg':'image/jpeg'}[name.rsplit('.',1)[1]])
    return app


app = create_app()
