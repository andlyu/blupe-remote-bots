"""Persistent Gemini Robotics worker. No direct CAN or motor ownership.

SDK contract: google-antigravity 0.1.23, official agent_skills.py example.
Physical readiness is supplied only by the separately qualified BluPe bridge.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hashlib
import hmac
import importlib.metadata
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from typing import Literal
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

APPROACH = 'Gemini Robotics'
MODEL = os.environ.get('GEMINI_MODEL', 'gemini-4-hydrogen')
TERMINAL = {'complete', 'failed', 'cancelled'}
PUBLIC_FIELDS = ('id', 'runner_name', 'prompt', 'mode', 'state', 'created_at',
                 'updated_at', 'duration_s', 'progress', 'events', 'artifacts',
                 'configuration', 'result')


class RunInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: uuid.UUID
    runner_name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=200)
    prompt: str = Field(min_length=1, max_length=4000)
    duration_s: int = Field(default=180, ge=60, le=600)
    mode: Literal['simulation', 'robot']


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = root / 'runs.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, owner TEXT NOT NULL, email TEXT NOT NULL, data TEXT NOT NULL)')
        os.chmod(self.db, 0o600)

    def connect(self):
        return sqlite3.connect(self.db, timeout=10)

    def create(self, spec: RunInput, owner: str):
        name, email, prompt = spec.runner_name.strip(), spec.email.strip(), spec.prompt.strip()
        if not name or name.lower() in {'anonymous', 'autonomous', 'automated'} or any(ord(c) < 32 for c in name):
            raise HTTPException(400, 'Enter the actual runner name')
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or not prompt:
            raise HTTPException(400, 'Enter a valid email and task')
        now = time.time()
        data = dict(id=str(spec.request_id), runner_name=name, prompt=prompt,
                    mode=spec.mode, duration_s=spec.duration_s, state='queued',
                    created_at=now, updated_at=now, progress='Waiting for the Gemini worker',
                    events=[], artifacts=[], result=None,
                    configuration=dict(approach=APPROACH, model=MODEL,
                        robot_id='yam-1', execution_mode='interactive',
                        variant='Antigravity Robotics adapted to BluPe'))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT owner,data FROM runs WHERE id=?', (data['id'],)).fetchone()
            if old:
                if not hmac.compare_digest(old[0], owner):
                    raise HTTPException(409, 'Request identifier belongs to another visitor')
                retained = json.loads(old[1])
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

    def update(self, ident, **values):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT data FROM runs WHERE id=?', (ident,)).fetchone()
            if not row:
                raise HTTPException(404, 'Run not found')
            data = json.loads(row[0])
            data.update(values, updated_at=time.time())
            db.execute('UPDATE runs SET data=? WHERE id=?', (json.dumps(data), ident))
        return data

    def event(self, ident, stage, message):
        data = self.get(ident)
        events = data['events'] + [dict(stage=stage, message=message, at=time.time())]
        return self.update(ident, state=stage, progress=message, events=events)

    def owned(self, ident, owner):
        with self.connect() as db:
            row = db.execute('SELECT owner FROM runs WHERE id=?', (ident,)).fetchone()
        return bool(row and hmac.compare_digest(row[0], owner))

    def recent(self):
        with self.connect() as db:
            rows = db.execute("SELECT data FROM runs ORDER BY json_extract(data,'$.created_at') DESC LIMIT 50").fetchall()
        return [json.loads(row[0]) for row in rows]


def runtime_status(skills: Path):
    versions = {}
    for package in ('google-antigravity', 'mujoco', 'playground', 'reaf', 'reaf-sim'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    skills_ready = (skills / 'mujoco-playground' / 'SKILL.md').is_file()
    # Import/install presence is a setup check, never physical qualification.
    simulation_ready = bool(os.environ.get('GEMINI_API_KEY') and skills_ready and all(versions.values()))
    return dict(online=True, simulation_ready=simulation_ready, physical_ready=False,
                model=MODEL, approach=APPROACH, versions=versions, skills_ready=skills_ready,
                message=('Simulation worker ready' if simulation_ready else 'Simulation runtime is being prepared'),
                physical_message='YAM 1 adapter qualification is pending')


async def run_agent(store, ident, skills):
    from google.antigravity import Agent, LocalAgentConfig
    job = store.get(ident)
    workspace = store.root / ident
    workspace.mkdir(mode=0o700, exist_ok=True)
    stop = asyncio.Event()
    store.event(ident, 'generating', 'Hydrogen is preparing the controller and simulation')
    # Follow the official SDK skills/workspaces interface. The hosted process
    # must run inside its dedicated container; this is not a Python sandbox.
    config = LocalAgentConfig(model=MODEL, api_key=os.environ['GEMINI_API_KEY'],
                              workspaces=[str(workspace)], skills_paths=[str(skills)],
                              system_instructions=(
        'You are the Gemini Robotics worker for BluPe YAM 1. Use the installed Robotics skills. '
        'This job is a simulation execution. Use measured public scene/calibration inputs when available; '
        'label assumptions explicitly. Write controller.py, run it in MuJoCo, retain a simulation.mp4 '
        'and report.json containing the task outcome and actual tests. Keep code and artifacts in the '
        'workspace. Do not access physical hardware or create a robot lease in simulation mode. '
        'The controller must use a DeviceLayer for sim/real composition, with observable images and '
        'joint feedback, not privileged object poses. Preserve requested model choice. '
        'Report failures honestly. Do not include credentials or private contact details in output.'))
    async def cancelled():
        while True:
            if store.get(ident)['state'] == 'cancelled':
                stop.set()
                return
            await asyncio.sleep(.2)
    async def infer():
        async with Agent(config) as agent:
            response = await agent.chat(job['prompt'])
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
                return
            raise TimeoutError('Run duration expired during controller generation/simulation')
        result = inference.result()
        artifacts = []
        for name in ('controller.py', 'simulation.mp4', 'report.json'):
            file = workspace / name
            if file.is_file() and not file.is_symlink():
                artifacts.append(dict(name=name, url=f'/api/runs/{ident}/artifacts/{name}', bytes=file.stat().st_size,
                    sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
        # A model's text alone is not a successful simulation or task pass.
        actual_report = workspace / 'report.json'
        if not actual_report.is_file() or not (workspace / 'simulation.mp4').is_file():
            store.update(ident, artifacts=artifacts, result=dict(summary=result, verified=False))
            raise RuntimeError('Controller preparation ended without a retained simulation report and video')
        report = json.loads(actual_report.read_text())
        store.update(ident, artifacts=artifacts, result=dict(summary=result, report=report, verified=False))
        store.event(ident, 'complete', 'Simulation finished; report and video are available for review')
    except asyncio.CancelledError:
        inference.cancel()
        await asyncio.gather(inference, return_exceptions=True)
        raise
    except Exception as exc:
        # Provider bodies/tracebacks may echo credentials; retain a bounded class
        # and our own known error messages only in public status.
        message = str(exc) if type(exc) in (TimeoutError, RuntimeError, json.JSONDecodeError) else type(exc).__name__
        key = os.environ.get('GEMINI_API_KEY', '')
        if key:
            message = message.replace(key, '[redacted]')
        store.event(ident, 'failed', message[:500])
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)


def create_app(state_root=None, skills_root=None):
    store = Store(Path(state_root or os.environ.get('GEMINI_STATE_DIR', '/tmp/gemini-blupe-state')))
    skills = Path(skills_root or os.environ.get('GEMINI_SKILLS_ROOT', '/opt/robotics/plugins/robotics/skills'))
    active = {}
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
        return runtime_status(skills)
    @app.get('/api/state')
    async def state(request: Request):
        authenticate(request)
        who = request.headers.get('x-gemini-visitor', '')
        return dict(worker=runtime_status(skills), runs=[{**{k:j[k] for k in PUBLIC_FIELDS}, 'owned':store.owned(j['id'], who)} for j in store.recent()])
    @app.post('/api/runs')
    async def start(spec: RunInput, request: Request):
        authenticate(request)
        who = owner(request)
        if spec.mode == 'robot':
            raise HTTPException(503, 'YAM 1 adapter qualification is pending; no robot request submitted')
        if not runtime_status(skills)['simulation_ready']:
            raise HTTPException(503, 'Simulation dependencies or model access are not configured')
        job = store.create(spec, who)
        if job['id'] not in active and job['state'] == 'queued':
            task = asyncio.create_task(run_agent(store, job['id'], skills))
            active[job['id']] = task
            task.add_done_callback(lambda _: active.pop(job['id'], None))
        return {k:job[k] for k in PUBLIC_FIELDS}
    @app.post('/api/runs/{ident}/stop')
    async def stop(ident: uuid.UUID, request: Request):
        authenticate(request)
        if not store.owned(str(ident), owner(request)):
            raise HTTPException(403, 'This browser does not own the run')
        job = store.get(str(ident))
        if job['state'] not in TERMINAL:
            store.event(str(ident), 'cancelled', 'Stopped by the runner')
        return {'ok': True}
    @app.get('/api/runs/{ident}/artifacts/{name}')
    async def artifact(ident: uuid.UUID, name: str, request: Request):
        authenticate(request)
        if name not in {'controller.py', 'simulation.mp4', 'report.json'}:
            raise HTTPException(404)
        job = store.get(str(ident))
        record = next((a for a in job['artifacts'] if a['name'] == name), None)
        file = store.root / str(ident) / name
        if not record or not file.is_file() or file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest() != record['sha256']:
            raise HTTPException(404, 'Retained artifact unavailable')
        return FileResponse(file, media_type={'py':'text/plain','mp4':'video/mp4','json':'application/json'}[name.rsplit('.',1)[1]])
    return app


app = create_app()
