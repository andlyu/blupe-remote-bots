#!/usr/bin/env python3
"""Run the existing Dream1 playground with an isolated local brightness extension."""
import argparse
import asyncio
import base64
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from urllib.parse import parse_qs

from brightness import brightness_factor, configure_policy, preview_jpeg
from comparison import ExperimentStore, run_record, summarize

HERE = Path(__file__).resolve().parent
SHARED = HERE.parents[1]
BACKEND = 'https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com'


def runner_root(value):
    if value:
        path = Path(value).expanduser().resolve()
        candidates = [path, path / 'codex-runner']
    else:
        candidates = [SHARED]
        # Reuse an existing Dream-capable checkout without changing its files.
        candidates += sorted((Path.home() / '.codex/worktrees').glob(
            '*/blupe-evals/public-projects/blupe-remote-yam/codex-runner'))
        candidates += sorted((Path.home() / '.codex/worktrees').glob('*/blupe-remote-yam/codex-runner'))
    for path in candidates:
        if (path / 'src/remote_yam/dream_policy.py').is_file() and (path / 'local_playground.py').is_file():
            return path
    raise SystemExit('No Dream1 runner found. Pass --runner-root /path/to/blupe-remote-yam.')


def make_runner_type(root, *, local=True):
    sys.path[:0] = [str(root), str(root / 'src')]
    from local_playground import LocalPlayground
    from playground import RequestError

    class BrightnessPlayground(LocalPlayground):
        def __init__(self, *, experiment_root=None, **kwargs):
            super().__init__(**kwargs)
            self.experiment_root = Path(experiment_root).resolve() if experiment_root else self.root
            self.experiment_root.mkdir(parents=True, exist_ok=True, mode=0o700)

        @property
        def experiment_database(self):
            return getattr(self, 'experiment_root', self.root) / 'brightness-experiment.sqlite3'

        async def json(self, send, status, payload, extra=()):
            # Correct only an episode whose actual experiment provenance is
            # retained locally. A different station user's run is never renamed.
            if isinstance(payload, dict) and isinstance(payload.get('public_run'), dict):
                public = payload['public_run']
                episode = public.get('episode_id')
                record = next((record for record in ExperimentStore(
                    self.experiment_database).records()
                    if record['episode_id'] == episode), None)
                if record:
                    payload = {**payload, 'public_run': {**public, 'model_name': record['model'],
                        'image_experiment': {key: record[key] for key in
                            ('brightness_factor', 'brightness_percent', 'experiment_revision')},
                        'experiment_failure_category': record.get('failure_category')}}
                    if record.get('calibration_fingerprint'):
                        payload['public_run']['kinematic_calibration'] = {
                            key:record.get(key) for key in ('model_calibration_id', 'camera_calibration_id')}
            await super().json(send, status, payload, extra)

        def remember_runner(self, visitor):
            super().remember_runner(visitor)
            # The shared snapshot allowlist omits experimental image settings.
            # Retain per-episode conditions independently of its historical schema.
            try:
                record = run_record(visitor.controller.status(), robot_id=self.robot_id,
                                    task=visitor.runner_task, runner_name=visitor.runner_name)
                if record is not None:
                    ExperimentStore(self.experiment_database).remember(record)
                    self.brightness_recording_error = None
            except (OSError, ValueError, sqlite3.Error):
                self.brightness_recording_error = 'Experiment metadata could not be saved. Check local storage before comparing runs.'

        def page(self):
            additions = ('<link rel="stylesheet" href="/experiment/brightness.css">'
                         '<script src="/experiment/brightness.js" defer></script>')
            return super().page().replace(b'<!-- application-head -->', additions.encode())

        async def session_extension(self, cookies, visitor):
            extra, headers = await super().session_extension(cookies, visitor)
            identity = {}
            identity_file = os.environ.get('YAM_BRIGHTNESS_IDENTITY_FILE')
            if identity_file:
                if not local:
                    raise RequestError(503, 'Private runner defaults are restricted to the local experiment.')
                path = Path(identity_file).expanduser()
                if path.stat().st_mode & 0o077:
                    raise RequestError(503, 'The private runner defaults file must be readable only by its owner.')
                values = json.loads(path.read_text())
                identity = {key: str(values.get(key, '')) for key in ('name', 'email')}
            return {**extra, 'local_runner': local, 'default_provider': 'dream',
                    'runner_identity': identity,
                    'image_experiment': {'brightness_percent': 50}}, headers

        def validate_launch(self, visitor, payload, paid):
            super().validate_launch(visitor, payload, paid)
            name = payload.get('runner_name', '')
            if not isinstance(name, str) or not name.strip() or name.strip().lower() in ('anonymous', 'local runner', 'automated', 'autonomous'):
                raise RequestError(400, 'Enter your real runner name in run settings before starting this experiment.')
            email = payload.get('email', '')
            if not isinstance(email, str) or not email.strip():
                raise RequestError(400, 'Enter your runner email in run settings for experiment attribution.')

        async def public_extension(self, scope, receive, send, headers):
            path = scope['path']
            if scope['method'] == 'GET' and path == '/experiment/calibration':
                if headers.get('sec-fetch-site') == 'cross-site':
                    raise RequestError(403, 'Open the local experiment directly.')
                from remote_yam.dream_calibration import ROBOHOUSE
                if self.robot_id != ROBOHOUSE:
                    await self.json(send, 200, {'selected':None,
                        'note':'This station retains its existing native encoder conventions.'})
                    return True
                def selected_profile():
                    from remote_yam.dream_policy import DreamAdapter
                    provider = DreamAdapter(provider='dream', model='dreamlabs/dream-1-beta',
                        credentials='', python='', directory=self.root / 'calibration-inspection',
                        camera_source=self.camera_source, observation_source=lambda:None, robot_id=self.robot_id)
                    provider.configure_robot_workspace(self.robot_id)
                    from remote_yam.run_changes import BUILD_HISTORY
                    return {'selected':provider.public_config()['kinematic_calibration'],
                        'runner_revision':BUILD_HISTORY[0]['revision'] if BUILD_HISTORY else None,
                        'worker_prepared':False, 'inference_started':False,
                        'note':'Live selected profile checked by this runner. Actual run binding is recorded separately.'}
                try:
                    data = await asyncio.to_thread(selected_profile)
                except Exception:
                    raise RequestError(503, 'Selected calibration could not be verified. Check the operator selection and camera report before Run.') from None
                await self.json(send, 200, data)
                return True
            if scope['method'] == 'GET' and path in ('/experiment/brightness.js', '/experiment/brightness.css'):
                name = path.rsplit('/', 1)[1]
                kind = 'text/javascript' if name.endswith('.js') else 'text/css'
                await self.respond(send, 200, (HERE / name).read_bytes(), kind + '; charset=utf-8')
                return True
            if scope['method'] == 'GET' and path == '/experiment/results':
                if headers.get('sec-fetch-site') == 'cross-site':
                    raise RequestError(403, 'Open the local experiment directly.')
                def results():
                    for visitor in list(self.visitors.values()):
                        self.remember_runner(visitor)
                    records = ExperimentStore(self.experiment_database).records()
                    data = summarize(records, self.run_assessments.summaries())
                    data['warning'] = getattr(self, 'brightness_recording_error', None)
                    return data
                try:
                    data = await asyncio.to_thread(results)
                except Exception:
                    raise RequestError(503, 'Experiment results unavailable. Refresh to try again.') from None
                await self.json(send, 200, data)
                return True
            if scope['method'] == 'GET' and path == '/experiment/preview':
                if headers.get('sec-fetch-site') == 'cross-site':
                    raise RequestError(403, 'Open the local experiment directly.')
                query = parse_qs(scope.get('query_string', b'').decode())
                try:
                    factor = brightness_factor(float(query.get('brightness', ['0.5'])[0]))
                except ValueError as exc:
                    raise RequestError(400, str(exc)) from None

                def capture():
                    raw = self.monitor_api.get_robot_observation(self.robot_id)
                    observation = raw.get('observation') or raw.get('payload') or raw
                    frames = self.camera_source.capture(observation)
                    return [{'camera': frame.name, 'captured_at': frame.source_captured_at or frame.received_at,
                             'jpeg': base64.b64encode(preview_jpeg(frame, factor)).decode()} for frame in frames]
                try:
                    frames = await asyncio.to_thread(capture)
                except Exception:
                    raise RequestError(503, 'Camera preview unavailable. Check the robot connection and refresh the preview.') from None
                await self.json(send, 200, {'frames': frames, 'brightness_factor': factor,
                                           'note': 'Fresh camera preview, not a recorded inference request.'})
                return True
            return await super().public_extension(scope, receive, send, headers)

        def launch(self, visitor, payload, **kwargs):
            if payload.get('provider') not in ('dream', 'dream_flash') or payload.get('executor'):
                raise RequestError(400, 'This experiment runs Dream1. Select Dream-1 beta or Flash.')
            try:
                factor = brightness_factor(payload.get('image_brightness', .5))
            except ValueError as exc:
                raise RequestError(400, str(exc)) from None
            previous = kwargs.pop('provider_transform', None)

            def transform(policy):
                if previous:
                    policy = previous(policy)
                policy = configure_policy(policy, factor)
                (visitor.directory / 'image-experiment.json').write_text(json.dumps(
                    policy.public_config()['image_experiment'], indent=2) + '\n')
                return policy

            return super().launch(visitor, payload, provider_transform=transform, **kwargs)

    return BrightnessPlayground


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner-root', default=os.environ.get('YAM_DREAM_RUNNER_ROOT'))
    parser.add_argument('--dream-python', default=os.environ.get('YAM_DREAM_PYTHON', sys.executable))
    parser.add_argument('--port', type=int, default=8798)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--session-api', default=BACKEND)
    parser.add_argument('--recordings', type=Path, default=SHARED / 'outputs/dream-brightness/runs')
    args = parser.parse_args()
    root = runner_root(args.runner_root)
    credentials = Path(os.environ.get('YAM_DREAM_CREDENTIALS', '~/.dreamlabs/credentials')).expanduser()
    if not credentials.is_file():
        parser.error('Save your Dream Labs credentials using its normal setup before launching Dream1.')
    probe = subprocess.run([args.dream_python, '-c',
                            'import dream; assert dream.__version__ == "1.0.0"'], capture_output=True)
    if probe.returncode:
        parser.error('Dream SDK 1.0.0 is missing. Install requirements-dream.txt in Python 3.12 and pass --dream-python.')
    runner_type = make_runner_type(root)
    from multi_robot import fleet
    import uvicorn
    origin = f'http://127.0.0.1:{args.port}'
    robots = json.loads((SHARED / 'config/robots.json').read_text())
    robots = [robot for robot in robots if robot.get('hardware') == 'yam']

    class RecordingRunner(runner_type):
        def __init__(self, **kwargs):
            kwargs['recording_root'] = args.recordings.resolve() / kwargs['robot_id']
            super().__init__(**kwargs)

    app = fleet(RecordingRunner, dict(public_origin=origin, session_api=args.session_api,
        camera_origin=args.session_api, hardware_control=True, development=True,
        dream_credentials_file=str(credentials), dream_python=args.dream_python,
        default_provider='dream'), robots)
    server = uvicorn.Config(app, host='127.0.0.1', port=args.port, access_log=False)
    sock = server.bind_socket()
    print(f'Dream1 brightness experiment: {origin}', flush=True)
    print(f'Existing runner: {root}', flush=True)
    try:
        if not args.no_browser:
            import webbrowser
            webbrowser.open(origin)
        uvicorn.Server(server).run(sockets=[sock])
    finally:
        sock.close()


if __name__ == '__main__':
    main()
