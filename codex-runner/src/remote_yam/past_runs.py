"""Read-only, bounded public dataset catalog. No visitor artifacts or credentials."""
from concurrent.futures import ThreadPoolExecutor
import json
import math
import re
import sqlite3
from pathlib import Path
import threading
import time
from urllib.request import urlopen

from .run_history import recorded_model

BASE = 'https://huggingface.co/datasets/andlyu/Public-YAM-runs/resolve/main/'


def run_timed_out(state):
    if state.get('status') == 'timed_out':
        return True
    if (state.get('safety_error') or {}).get('code') in {'session_timeout', 'policy_runtime_timeout'}:
        return True
    text = str(state.get('error') or '').lower()
    if any(marker in text for marker in ('runtime limit', 'session_timeout', 'policy_runtime_timeout', 'selected duration limit')):
        return True
    return any(event.get('kind') == 'lifecycle' and
               (event.get('details') or {}).get('reason') in {'session_timeout', 'policy_runtime_timeout'}
               for event in (state.get('interactions') or {}).get('events', []))


def merge_run_result(row, stored):
    """A catalog timeout is robot evidence; stale generic runner errors cannot erase it."""
    timed_out = row.get('result_reason') == 'Run reached time limit'
    row.update(stored)
    diagnostic = public_runner_diagnostic({'error': row.get('errors')})
    if diagnostic and row.get('result') == 'Failure' and not timed_out:
        row['result_reason'] = diagnostic
    if timed_out and row.get('result_reason') in {'Runner or model error', 'Robot safety check stopped the run', 'Run reached time limit'}:
        row.update(result='Stopped', result_reason='Run reached time limit', errors=None)
        if row.get('ending_reason') in {None, 'Runner or model error', 'Robot safety check stopped the run'}:
            row['ending_reason'] = 'Run reached time limit'
    return normalize_time_limit_result(row)


def normalize_time_limit_result(row):
    """Read old timeout records as normal stops without rewriting the archive."""
    if row.get('result_reason') == 'Run reached time limit':
        row['result'] = 'Stopped'
        legacy_reasons = {'Run reached time limit', 'Runner or model error', 'Robot safety check stopped the run'}
        if row.get('errors') in legacy_reasons:
            row['errors'] = None
        if row.get('ending_reason') in legacy_reasons or not row.get('ending_reason'):
            row['ending_reason'] = 'Run reached time limit'
    return row


def run_result(meta):
    # Completion is the runner's report, not an independent task evaluation.
    outcomes = {
        'policy_complete': ('Success', 'Runner reported task complete'),
        'user_requested': ('Stopped', 'Run stopped; no specific result recorded'),
        'session_timeout': ('Stopped', 'Run reached time limit'),
        'policy_runtime_timeout': ('Stopped', 'Run reached time limit'),
        'lease_expired': ('Failure', 'Runner connection expired'),
        'physical_execution_failure': ('Failure', 'Robot execution failed'),
        'runner_failed': ('Failure', 'Runner or model error'),
        'recorder_process_interrupted': ('Unknown', 'Recording interrupted'),
        'operator_stop': ('Stopped', 'Stopped by the operator'),
    }
    label, reason = outcomes.get(meta.get('outcome'), ('Unknown', 'Result was not recorded'))
    return {'result': label, 'result_reason': reason,
            'ending_reason': None if label == 'Unknown' else reason,
            'errors': reason if label == 'Failure' else None}


def public_runner_diagnostic(state):
    """Preserve allowlisted diagnostics; never include arbitrary provider text."""
    from .runner_failures import failure_from_state
    failure = failure_from_state(state)
    if failure:
        return failure['message']
    error = state.get('error')
    if not isinstance(error, str):
        return None
    # GR00T rejects the whole chunk before dispatch. Preserve this reason in
    # both the live banner and saved result without exposing arbitrary text.
    scalar = r'[0-9]{1,20}(?:\.[0-9]{1,20})?(?:[eE][+-]?[0-9]{1,3})?'
    groot = re.fullmatch(
        rf'(?:ValueError: )?(GR00T action exceeds the runner motion limit; '
        rf'chunk rejected without retiming \(largest sampled change ({scalar}) rad; '
        rf'limit ({scalar}) rad\))', error)
    if groot and all(math.isfinite(float(v)) for v in groot.groups()[1:]):
        return groot.group(1)
    for message in (
        'GR00T action exceeds the gateway motion limit; chunk rejected without retiming',
        'GR00T trajectory exceeds gateway budget; chunk rejected without truncation',
    ):
        if error in {message, 'ValueError: ' + message}:
            return message
    # CameraFrameSource emits a fixed diagnostic without response bodies/URLs.
    # Retain it in the live banner and saved result instead of hiding the cause.
    camera = r'left|right|top|observer|overhead|side|front|wrist'
    cause = (r'HTTP [1-5][0-9]{2}|TimeoutError|URLError|HTTPError|ValueError|'
             r'ConnectionError|ConnectionResetError|ConnectionRefusedError|'
             r'RemoteDisconnected|OSError|SSLError|SSLCertVerificationError|IncompleteRead')
    failure = re.fullmatch(
        rf'(?:RuntimeError: )?(Camera failure: (?:{camera}) camera frame unavailable '
        rf'after [1-9][0-9]{{0,2}} attempt\(s\) \((?:{cause})\))', error)
    if failure:
        return failure.group(1)
    camera_error = 'No fresh RGB-D capture available'
    if error in {camera_error, 'RuntimeError: ' + camera_error}:
        return camera_error
    # Providers may report a planning residual without exposing their internals.
    number = r'[0-9]{1,4}\.[0-9]{3,6}'
    phase = r'approach|descend|close|lift|carry|lower|open|retreat|return_to_start'
    planned = re.fullmatch(
        rf'(?:RuntimeError: )?(Planned path error: {number} m > {number} m maximum '
        rf'\((?:{phase})\)\.)', error)
    if planned:
        return planned.group(1)
    reasons = {
        'station_safety_status_missing': 'Robot safety status was missing',
        'station_emergency_stop_engaged': 'Robot emergency stop was engaged',
        'station_contact_reported': 'Robot reported contact',
        'station_controller_fault': 'Robot controller reported FAULT',
        'station_emergency_stop_status_unknown': 'Robot emergency-stop status was unknown',
        'station_disabled': 'Robot was disabled',
        'station_physical_controller_fault': 'Robot reported a physical controller fault',
        'station_joint_limit': 'Robot reported a joint outside its position limits',
        'station_hardware_not_initialized': 'Robot hardware was not initialized',
        'station_safety_not_confirmed': 'Robot safety.ok was not true; no recognized specific reason was supplied',
    }
    for code, message in reasons.items():
        if error in {f'Hardware feedback blocked: {code}', f'RuntimeError: Hardware feedback blocked: {code}'}:
            return message
    reasons = (
        'station_unsafe', 'completion_timestamp_invalid_or_stale',
        'completion_not_explicitly_settled', 'completion_not_explicitly_homed',
        'station_source_not_hardware', 'station_timestamp_invalid',
        'station_precedes_completion_or_is_stale', 'station_not_explicitly_settled',
        'station_not_explicitly_homed',
    )
    if re.fullmatch(r'(?:RuntimeError: )?Hardware feedback blocked: (' + '|'.join(reasons) + r')', error):
        return error
    return None


def public_robot_error(state):
    """Expose only the known numeric joint mismatch, never arbitrary exceptions."""
    candidates = [(state.get('safety_error') or {}).get('message'), state.get('error')]
    candidates += [(e.get('details') or {}).get('context', {}).get('message')
                   for e in (state.get('interactions') or {}).get('events', []) if e.get('kind') == 'error']
    pattern = r'within ([0-9.]+)s: (left|right)_joint_([0-5]) residual_rad=([0-9.]+) measured_rad=(-?[0-9.]+) target_rad=(-?[0-9.]+); allowed_rad=([0-9]+(?:\.[0-9]+)?)'
    for candidate in candidates:
        gripper_delta = re.fullmatch(r'(?:ValueError: )?gripper delta limit at waypoint ([0-9]{1,6})', candidate or '')
        if gripper_delta:
            return f'ValueError: gripper delta limit at waypoint {int(gripper_delta.group(1))}'
        # This station-level message is already allowlisted by the gateway;
        # validate again before exposing it through the public hosted UI.
        number = r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?'
        gripper = re.fullmatch(
            rf'(Left|Right) gripper feedback ({number}) is outside the accepted range '
            rf'\[({number}), ({number})\]\. Robot unavailable; operator attention needed\.',
            candidate or '')
        if gripper and all(math.isfinite(float(v)) for v in gripper.groups()[1:]):
            return gripper.group(0)
        match = re.search(pattern, candidate or '')
        if not match:
            continue
        seconds, arm, joint, residual, measured, target, allowed = match.groups()
        try:
            seconds, residual, measured, target, allowed = map(float, (seconds,residual,measured,target,allowed))
        except ValueError:
            continue
        if not all(math.isfinite(v) for v in (seconds,residual,measured,target,allowed)):
            continue
        return (f'{arm.capitalize()} arm joint {joint} (joint {int(joint)+1} of 6) did not reach its target within {seconds:g}s. '
                f'Measured {math.degrees(measured):.1f}°, target {math.degrees(target):.1f}°; '
                f'error {math.degrees(residual):.1f}° exceeds {math.degrees(allowed):.1f}° allowed. '
                'Motion stopped. Check for contact or obstruction before continuing.')
    return None


def model_ending(state):
    candidates = [(state.get('provider') or {}).get('outcome')]
    candidates += [(e.get('details') or {}).get('result')
                   for e in reversed((state.get('interactions') or {}).get('events', []))
                   if e.get('kind') == 'tool_result']
    for outcome in candidates:
        if not isinstance(outcome, dict) or outcome.get('status') not in {'done', 'give_up'}:
            continue
        reason = outcome.get('reason' if outcome['status'] == 'give_up' else 'summary')
        if isinstance(reason, str) and reason.strip():
            return outcome['status'], reason.strip()[:2000]
    return None


class RunNames:
    def __init__(self, path):
        self.path = Path(path)

    def replay_speeds(self):
        """Only expose pacing derived from recorded provider identity."""
        if not self.path.exists():
            return {}
        with sqlite3.connect(self.path) as db:
            if not db.execute("SELECT name FROM sqlite_master WHERE name='run_configuration'").fetchone():
                return {}
            settings = {}
            for eid, value in db.execute('SELECT * FROM run_configuration'):
                provider = json.loads(value).get('provider')
                if isinstance(provider, str) and provider:
                    settings[eid] = 2 if provider in {'dream', 'dream_flash'} else 10
            return settings

    def pending(self, episode_id, robot_id):
        """Public receipt metadata is available before the video is published."""
        if not re.fullmatch(r'ep_[A-Za-z0-9_-]+', episode_id or '') or not self.path.exists():
            return None
        with sqlite3.connect(self.path) as db:
            if not db.execute("SELECT name FROM sqlite_master WHERE name='run_metadata'").fetchone():
                return None
            row = db.execute('SELECT robot_id,task,started_at FROM run_metadata WHERE episode_id=? AND robot_id=?',
                             (episode_id, robot_id)).fetchone()
        if row is None:
            return None
        return {'episode_id':episode_id, 'robot_id':row[0], 'prompt':row[1], 'started_at':row[2],
                'episode_index':None, 'video_status':'processing', 'video_url':None,
                'video_duration_s':None, 'camera_order':[]}

    def remember_metadata(self, episode_id, robot_id, task, started_at, configuration=None):
        if not re.fullmatch(r'ep_[A-Za-z0-9_-]+', episode_id or ''):
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(mode=0o600, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS run_metadata (episode_id TEXT PRIMARY KEY, robot_id TEXT, task TEXT, started_at REAL)')
            db.execute('INSERT OR IGNORE INTO run_metadata VALUES (?, ?, ?, ?)', (episode_id, robot_id, task, started_at))
            if configuration:
                db.execute('CREATE TABLE IF NOT EXISTS run_configuration (episode_id TEXT PRIMARY KEY, configuration TEXT NOT NULL)')
                db.execute('INSERT OR IGNORE INTO run_configuration VALUES (?, ?)', (episode_id, json.dumps(configuration)))

    def comparisons(self, robot_id):
        results = self.results()
        metadata = {}
        configurations = {}
        if self.path.exists():
            with sqlite3.connect(self.path) as db:
                if db.execute("SELECT name FROM sqlite_master WHERE name='run_metadata'").fetchone():
                    metadata = {eid: (robot, task, started) for eid, robot, task, started in db.execute('SELECT * FROM run_metadata')}
                if db.execute("SELECT name FROM sqlite_master WHERE name='run_configuration'").fetchone():
                    configurations = {eid: json.loads(value) for eid, value in db.execute('SELECT * FROM run_configuration')}
        runs = []
        for eid, result in results.items():
            if not (result.get('run_metrics') or result.get('step_timings')):
                continue
            robot, task, started = metadata.get(eid, (None, 'Older local run — robot/task not recorded', None))
            if robot is not None and robot != robot_id:
                continue
            runs.append({'episode_id': eid, 'robot_id': robot, 'prompt': task, 'started_at': started, **result})
        runs.sort(key=lambda run: run.get('started_at') or 0)
        from .run_changes import changes
        previous = None
        for run in runs:
            current = configurations.get(run['episode_id'])
            run['change_notes'] = changes(previous, current)
            previous = current
        return runs[-100:]

    def remember(self, episode_id, name):
        if not re.fullmatch(r'ep_[A-Za-z0-9_-]+', episode_id or '') or not name:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(mode=0o600, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS run_names (episode_id TEXT PRIMARY KEY, name TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO run_names VALUES (?, ?)', (episode_id, name[:32]))

    def remember_result(self, episode_id, state):
        if not re.fullmatch(r'ep_[A-Za-z0-9_-]+', episode_id or ''):
            return
        events = (state.get('interactions') or {}).get('events', [])
        stop_reasons = [(event.get('details') or {}).get('reason') for event in events
                        if event.get('kind') == 'stop_requested']
        ending = model_ending(state)
        errors = None
        specific = public_robot_error(state)
        if specific:
            result, reason = 'Failure', specific
            errors = reason
        elif run_timed_out(state):
            result, reason = 'Stopped', 'Run reached time limit'
        elif state.get('safety_error'):
            result, reason = 'Failure', 'Robot safety check stopped the run'
            errors = reason
        elif state.get('error'):
            from .run_errors import public_run_error
            result, reason = 'Failure', public_run_error(state)
            errors = reason
        elif ending:
            result = 'Failure' if ending[0] == 'give_up' else 'Success'
            reason = ending[1]
        elif 'policy_complete' in stop_reasons:
            result, reason = 'Success', 'Runner reported task complete'
        elif 'user_requested' in stop_reasons:
            result, reason = 'Cancelled', 'Stopped by the visitor'
        else:
            return
        # Store the same redacted diagnostic shown in the live banner.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(mode=0o600, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS run_results (episode_id TEXT PRIMARY KEY, result TEXT NOT NULL, reason TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS run_details (episode_id TEXT PRIMARY KEY, errors TEXT, ending_reason TEXT)')
            totals = {key: value for key, value in (state.get('run_metrics') or {}).items()
                      if key in {'model_s', 'execution_s', 'left_path_m', 'right_path_m', 'model_calls', 'execution_packets', 'accepted_packets', 'distance_waypoints', 'confirmed_waypoints'}
                      and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0}
            if totals:
                db.execute('CREATE TABLE IF NOT EXISTS run_totals (episode_id TEXT PRIMARY KEY, metrics TEXT NOT NULL)')
                db.execute('INSERT INTO run_totals VALUES (?, ?) ON CONFLICT(episode_id) DO UPDATE SET metrics=excluded.metrics', (episode_id, json.dumps(totals)))
            metrics = []
            for row in (state.get('step_timings') or [])[-200:]:
                metrics.append({key: value for key, value in row.items()
                                if key in {'step', 'model_s', 'arm_motion_s', 'left_displacement_m', 'right_displacement_m', 'path_m', 'execution_robot_s'}
                                and isinstance(value, (int, float)) and not isinstance(value, bool)
                                and math.isfinite(value) and value >= 0})
            if metrics:
                db.execute('CREATE TABLE IF NOT EXISTS run_metrics (episode_id TEXT PRIMARY KEY, metrics TEXT NOT NULL)')
                db.execute('INSERT INTO run_metrics VALUES (?, ?) ON CONFLICT(episode_id) DO UPDATE SET metrics=excluded.metrics',
                           (episode_id, json.dumps(metrics)))
            if not specific:
                previous_error = db.execute('SELECT errors FROM run_details WHERE episode_id=?', (episode_id,)).fetchone()
                if previous_error and previous_error[0] and (re.match(r'(Left|Right) arm joint [0-5] ', previous_error[0]) or re.fullmatch(r'ValueError: gripper delta limit at waypoint [0-9]{1,6}', previous_error[0])):
                    result, reason, errors = 'Failure', previous_error[0], previous_error[0]
            if not ending and not errors and reason != 'Run reached time limit':
                previous = db.execute('SELECT r.result, r.reason FROM run_results r JOIN run_details d USING (episode_id) WHERE r.episode_id=? AND d.ending_reason IS NOT NULL', (episode_id,)).fetchone()
                if previous:
                    result, reason = previous
            previous = db.execute('SELECT reason FROM run_results WHERE episode_id=?', (episode_id,)).fetchone()
            if previous and previous[0] == 'Run reached time limit' and not specific:
                result, reason, errors = 'Stopped', 'Run reached time limit', None
            db.execute('INSERT INTO run_details VALUES (?, ?, ?) ON CONFLICT(episode_id) DO UPDATE SET errors=COALESCE(excluded.errors,errors), ending_reason=COALESCE(excluded.ending_reason,ending_reason)',
                       (episode_id, errors, ending[1] if ending else None))
            if reason == 'Run reached time limit':
                db.execute('UPDATE run_details SET errors=NULL, ending_reason=? WHERE episode_id=?', (reason, episode_id))
            db.execute('INSERT INTO run_results VALUES (?, ?, ?) ON CONFLICT(episode_id) DO UPDATE SET result=excluded.result, reason=excluded.reason WHERE result != excluded.result OR reason != excluded.reason', (episode_id, result, reason))

    def results(self):
        if not self.path.exists():
            return {}
        with sqlite3.connect(self.path) as db:
            if not db.execute("SELECT name FROM sqlite_master WHERE name='run_results'").fetchone():
                return {}
            result = {eid: {'result': label, 'result_reason': reason,
                            'ending_reason': reason, 'errors': reason if label == 'Failure' else None}
                      for eid, label, reason in db.execute('SELECT episode_id, result, reason FROM run_results')}
            if db.execute("SELECT name FROM sqlite_master WHERE name='run_details'").fetchone():
                for eid, errors, ending in db.execute('SELECT episode_id, errors, ending_reason FROM run_details'):
                    if eid in result:
                        result[eid]['errors'] = errors
                        if ending:
                            result[eid]['ending_reason'] = ending
            if db.execute("SELECT name FROM sqlite_master WHERE name='run_metrics'").fetchone():
                for eid, metrics in db.execute('SELECT episode_id, metrics FROM run_metrics'):
                    if eid in result:
                        result[eid]['step_timings'] = json.loads(metrics)
            if db.execute("SELECT name FROM sqlite_master WHERE name='run_totals'").fetchone():
                for eid, metrics in db.execute('SELECT episode_id, metrics FROM run_totals'):
                    if eid in result:
                        result[eid]['run_metrics'] = json.loads(metrics)
            return {eid: normalize_time_limit_result(row) for eid, row in result.items()}


    def names(self):
        if not self.path.exists():
            return {}
        with sqlite3.connect(self.path) as db:
            if not db.execute("SELECT name FROM sqlite_master WHERE name='run_names'").fetchone():
                return {}
            return dict(db.execute('SELECT episode_id, name FROM run_names'))


def fetch(path):
    with urlopen(BASE + path, timeout=8) as response:
        body = response.read(8 * 1024 * 1024 + 1)
    if len(body) > 8 * 1024 * 1024:
        raise ValueError('Public catalog is too large')
    return body.decode()


class PastRuns:
    def __init__(self, reader=fetch, *, robot_id="yam-1", model_reader=None):
        self.robot_id = robot_id
        self.reader = reader
        self.model_reader = model_reader
        self.lock = threading.Lock()
        self.rows = None
        self.updated = 0
        self.details = {}
        self.viewing = {}

    def get(self, episode_id):
        if not re.fullmatch(r'ep_[A-Za-z0-9_-]+', episode_id):
            raise ValueError('Invalid episode ID')
        rows = self.page(episode_id=episode_id)['runs']
        return rows[0] if rows else None

    def page(self, offset=0, *, episode_id=None, episode_ids=None, robot_id=None, model=''):
        with self.lock:
            stale = False
            if self.rows is None or time.monotonic() - self.updated > 60:
                try:
                    sources = [json.loads(line) for line in self.reader('meta/blupe_source_episodes.jsonl').splitlines() if line]
                    tasks = {x['episode_index']: x.get('tasks', []) for x in
                             (json.loads(line) for line in self.reader('meta/episodes.jsonl').splitlines() if line)}
                    try:
                        motion = {r['episode_id']: r for r in (json.loads(line) for line in
                                  self.reader('meta/blupe_motion_classification.jsonl').splitlines() if line)}
                    except Exception:
                        motion = {}  # Never hide a run using its prompt or a guessed result.
                    try:
                        viewing = {r['episode_id']:r for r in (json.loads(line) for line in
                                   self.reader('meta/blupe_viewing.jsonl').splitlines() if line)
                                   if re.fullmatch(r'ep_[A-Za-z0-9_-]+', r.get('episode_id',''))}
                    except Exception:
                        viewing = self.viewing
                    self.viewing = viewing
                    rows = []
                    archived = {row['episode_id'] for row in sources}
                    for eid, item in viewing.items():
                        if eid not in archived:
                            rows.append({'episode_id':eid, 'episode_index':None,
                                         'started_at':item['started_at'], 'prompt':item.get('task') or 'Task unavailable',
                                         'original_available':item.get('original_available', False),
                                         'model':item.get('model'),
                                         'robot_id':item.get('robot_id', 'yam-1')})
                    for row in sources:
                        if not re.fullmatch(r'ep_[A-Za-z0-9_-]+', row.get('episode_id', '')):
                            continue
                        classification = motion.get(row['episode_id'], {})
                        if (classification.get('kind') == 'arm_check' and classification.get('version') in {1, 2}
                                and row.get('samples_sha256') and classification.get('samples_sha256') == row['samples_sha256']):
                            continue
                        prompts = tasks.get(row['episode_index'], [])
                        rows.append({'episode_id': row['episode_id'], 'episode_index': row['episode_index'],
                                     'robot_id':row.get('robot_id', 'yam-1'),
                                     'model':row.get('model') or viewing.get(row['episode_id'], {}).get('model'),
                                     'started_at': row['recorded_at'], 'prompt': '\n'.join(prompts) or 'Task unavailable'})
                    # Explicitly excluded by the operator, including incomplete recordings.
                    rows = [r for r in rows if (self.robot_id is None or r['robot_id'] == self.robot_id) and ' '.join(r['prompt'].split()).casefold().rstrip('.') != 'raise and lower both arms for three cycles']
                    self.rows = sorted(rows, key=lambda r: (r['started_at'], r['episode_index'] or -1), reverse=True)
                    self.updated = time.monotonic()
                except Exception:
                    if self.rows is None:
                        raise
                    stale = True
            available = [r for r in self.rows if (episode_ids is None or r['episode_id'] in episode_ids)
                         and (robot_id is None or r['robot_id'] == robot_id)]
            recorded_models = self.model_reader() if self.model_reader else {}
            available = [dict(r, model=recorded_model(recorded_models.get(r['episode_id'])) or recorded_model(r.get('model')))
                         for r in available]
            models = sorted({r['model'] for r in available if r['model']}, key=str.casefold)
            if any(r['model'] is None for r in available):
                models.append('__unrecorded__')
            if model:
                available = [r for r in available if (r['model'] or '__unrecorded__') == model]
            selected = ([r for r in available if r['episode_id'] == episode_id]
                        if episode_id is not None else available[offset:offset+12])
            now = time.monotonic()
            missing = [r for r in selected if r['episode_id'] not in self.details or now-self.details[r['episode_id']][0] > 60]
            with ThreadPoolExecutor(max_workers=4) as pool:
                for eid, detail in pool.map(self._detail, missing):
                    self.details[eid] = (now, detail)
            # Bound caches as the archive grows.
            if len(self.details) > 240:
                wanted = {r['episode_id'] for r in selected}
                self.details = {k: v for k, v in self.details.items() if k in wanted}
            result = [dict(r, **self.details[r['episode_id']][1]) for r in selected]
            return {'runs': result, 'next_offset': offset+len(selected) if offset+len(selected) < len(available) else None,
                    'stale': stale, 'total': len(available), 'models': models}

    def _detail(self, row):
        eid = row['episode_id']
        try:
            meta = json.loads(self.reader(f'episodes/{eid}.json'))
            preview = meta.get('preview') or {}
        except Exception:
            meta = {}
            preview = {}
        viewing = self.viewing.get(eid)
        if viewing:
            meta = {**meta, **viewing}
            preview = viewing['preview']
        speed = preview.get('speed', preview.get('nominal_action_speed')
                            if preview.get('processing') == 'main-flow-or-gripper-v1' else None)
        compressed = (type(speed) in (int, float) and math.isfinite(speed) and 1 <= speed <= 10)
        video_meta = preview if compressed else (meta.get('video') or {})
        duration = video_meta.get('duration_s')
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0:
            duration = 0 if video_meta.get('frames') == 0 or meta.get('rows') == 0 else None
        return eid, {**run_result(meta), 'video_duration_s': duration, 'video_url': BASE + f'{"viewing" if viewing else "previews" if compressed else "videos"}/{eid}.mp4',
                     'original_video_url': BASE + f'videos/{eid}.mp4',
                     'original_available': row.get('original_available', True),
                     'compressed': compressed,
                     'preview_speed': speed if compressed else None,
                     'video_layout': video_meta.get('layout'),
                     'camera_order': preview.get('camera_order', ['left', 'top', 'right']) if compressed else ['left', 'top', 'right']}
