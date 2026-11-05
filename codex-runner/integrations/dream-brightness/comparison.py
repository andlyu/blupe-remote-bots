"""Retained per-episode conditions and reviewed relative outcomes."""
import json
import hashlib
import math
from pathlib import Path
import re
import sqlite3
import time

from brightness import brightness_factor

EXPERIMENT_REVISION = hashlib.sha256(b''.join((Path(__file__).parent / name).read_bytes()
    for name in ('brightness.py', 'comparison.py', 'serve.py'))).hexdigest()


def finite_number(value):
    return float(value) if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def run_record(state, *, robot_id, task, runner_name):
    """Select fields explicitly; capabilities, email and SDK secrets never enter."""
    provider = state.get('provider') or {}
    config = state.get('run_configuration') or {}
    if not provider:
        # The controller clears the live policy at shutdown and resets this
        # command on every launch. Its retained configuration belongs to this run.
        previous = (state.get('last_model_command') or {}).get('provider') or {}
        if previous.get('provider') == config.get('provider') and previous.get('model') == config.get('model'):
            provider = previous
    experiment = provider.get('image_experiment')
    episode_id = state.get('episode_id')
    if not experiment or not re.fullmatch(r'ep_[A-Za-z0-9_-]+', episode_id or ''):
        return None
    if provider.get('provider') not in ('dream', 'dream_flash'):
        return None
    factor = brightness_factor(experiment.get('brightness_factor'))
    # Dream does not populate the generic text-model accounting fields. These
    # are decision-pipeline timings, including capture/IK, not server inference.
    latency = (state.get('latency') or {}).get('model') or {}
    calls, average_ms = finite_number(latency.get('count')), finite_number(latency.get('avg_ms'))
    calibration = config.get('kinematic_calibration') or provider.get('kinematic_calibration') or {}
    connection_failed = any(event.get('kind') == 'model_failure' and
        (event.get('details') or {}).get('protocol_category') == 'connection_failure'
        for event in (state.get('interactions') or {}).get('events', []))
    return dict(episode_id=episode_id, robot_id=robot_id,
                task=config.get('task_prompt') or task, runner_name=runner_name,
                model=provider.get('model'), code_revision=config.get('code_revision'),
                experiment_revision=EXPERIMENT_REVISION,
                calibration_fingerprint=calibration.get('fingerprint'),
                model_calibration_id=calibration.get('model_calibration_id'),
                camera_calibration_id=calibration.get('camera_calibration_id'),
                duration_s=state.get('run_duration_s'), brightness_factor=factor,
                brightness_percent=round(factor * 100),
                status=state.get('status'), started_at=finite_number(state.get('run_started_at')),
                failure_category='model_transport' if connection_failed else None,
                ended_at=finite_number(state.get('run_ended_at')),
                model_calls=calls,
                model_s=calls * average_ms / 1000 if calls and average_ms is not None else None,
                timing_source='controller decision pipeline (capture, inference and IK)',
                packets_submitted=finite_number(state.get('packets_submitted')))


class ExperimentStore:
    def __init__(self, path):
        self.path = Path(path)

    def remember(self, record):
        if record is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(mode=0o600, exist_ok=True)
        with sqlite3.connect(self.path, timeout=5) as db:
            db.execute('CREATE TABLE IF NOT EXISTS brightness_runs (episode_id TEXT PRIMARY KEY, record TEXT NOT NULL, updated_at REAL NOT NULL)')
            previous = db.execute('SELECT record FROM brightness_runs WHERE episode_id=?',
                                  (record['episode_id'],)).fetchone()
            if previous:
                old = json.loads(previous[0])
                # A later UI setting must never relabel a previous physical run.
                for key in ('brightness_factor', 'robot_id', 'model', 'duration_s', 'task', 'calibration_fingerprint'):
                    if old.get(key) != record.get(key):
                        raise ValueError('Recorded experiment condition changed for an existing episode')
                record = {**record, 'experiment_revision': old.get('experiment_revision'),
                          'code_revision': old.get('code_revision'),
                          'failure_category': old.get('failure_category') or record.get('failure_category')}
            db.execute('INSERT INTO brightness_runs VALUES (?, ?, ?) ON CONFLICT(episode_id) DO UPDATE SET record=excluded.record, updated_at=excluded.updated_at',
                       (record['episode_id'], json.dumps(record, allow_nan=False), time.time()))

    def records(self):
        if not self.path.exists():
            return []
        with sqlite3.connect(self.path, timeout=5) as db:
            if not db.execute("SELECT name FROM sqlite_master WHERE name='brightness_runs'").fetchone():
                return []
            return [json.loads(row[0]) for row in db.execute(
                'SELECT record FROM brightness_runs ORDER BY updated_at DESC')]


def summarize(records, assessments):
    """Separate task/model/station/duration/revision; score only reviewed outcomes."""
    groups = {}
    for record in records:
        key = tuple(record.get(field) for field in ('robot_id', 'model', 'task', 'duration_s', 'code_revision', 'experiment_revision', 'calibration_fingerprint'))
        group = groups.setdefault(key, dict(zip(
            ('robot_id', 'model', 'task', 'duration_s', 'code_revision', 'experiment_revision', 'calibration_fingerprint'), key),
            model_calibration_id=record.get('model_calibration_id'), variants={}))
        factor = record['brightness_factor']
        variant = group['variants'].setdefault(factor, dict(brightness_factor=factor,
            brightness_percent=record['brightness_percent'], runs=0, successes=0, failures=0,
            unscored=0, excluded=0, connection_failures=0, model_calls=0, model_s=0., run_ids=[]))
        variant['runs'] += 1
        variant['run_ids'].append(record['episode_id'])
        assessment = assessments.get(record['episode_id']) or {}
        if record.get('failure_category') == 'model_transport':
            variant['connection_failures'] += 1
        elif assessment.get('ended') is True and assessment.get('eligibility') == 'included' and assessment.get('label') in ('Success', 'Failure'):
            variant['successes' if assessment['label'] == 'Success' else 'failures'] += 1
        elif assessment.get('eligibility') == 'excluded':
            variant['excluded'] += 1
        else:
            variant['unscored'] += 1
        calls, seconds = record.get('model_calls'), record.get('model_s')
        if calls and seconds is not None:
            variant['model_calls'] += calls
            variant['model_s'] += seconds
    output = []
    for group in groups.values():
        variants = group['variants']
        for variant in variants.values():
            variant['scored'] = variant['successes'] + variant['failures']
            variant['success_rate'] = variant['successes'] / variant['scored'] if variant['scored'] else None
            variant['mean_model_call_s'] = variant['model_s'] / variant['model_calls'] if variant['model_calls'] else None
        baseline, dark = variants.get(1.), variants.get(.5)
        rates_known = baseline and dark and baseline['success_rate'] is not None and dark['success_rate'] is not None
        group['difference_percentage_points'] = 100 * (dark['success_rate'] - baseline['success_rate']) if rates_known else None
        group['variants'] = sorted(variants.values(), key=lambda row: row['brightness_factor'], reverse=True)
        output.append(group)
    return dict(groups=output, runs=len(records),
                note='Relative to 100% brightness. Only ended, reviewed, included runs count toward success rates. Dream connection failures are listed separately and excluded from those rates. Review labels may be entered by the runner or their agent. Unscored runs are not failures. Restore the same scene between trials; one attempt per condition is exploratory.')
