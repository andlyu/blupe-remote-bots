"""Import approach attribution from an integration's existing public run API.

Only a dedicated public receipt cache is written. Robot control, source databases,
media and private contact fields are never accessed or changed.
"""
import argparse
from contextlib import closing
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .run_history import recorded_model

MAX_BYTES = 16 * 1024 * 1024
EPISODE = re.compile(r'ep_[A-Za-z0-9_-]{1,100}')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, 'History source redirected', headers, fp)


def read_runs(origin, token=''):
    parsed = urlsplit(origin)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('History source must be an HTTPS origin')
    headers = {'User-Agent':'BluPe-Public-History/1.0', 'Accept':'application/json'}
    if token:
        headers['OAI-Sites-Authorization'] = 'Bearer ' + token
    # Never forward a service credential to a redirect destination.
    with build_opener(NoRedirect()).open(Request(origin.rstrip('/') + '/api/physical/runs',
                                                headers=headers), timeout=20) as response:
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError('History response is too large')
    data = json.loads(body)
    if not isinstance(data, dict) or not isinstance(data.get('runs'), list):
        raise ValueError('History source did not return runs')
    return data['runs']


def project_runs(runs, *, origin, approach, robot_id):
    if recorded_model(approach) != approach:
        raise ValueError('An explicit recorded approach is required')
    projected = {}
    for run in runs:
        if not isinstance(run, dict):
            continue
        result = run.get('result')
        if (run.get('approach') != approach or run.get('robot') != robot_id
                or run.get('execution') != 'physical' or not isinstance(result, dict)
                or result.get('approach') != approach or result.get('robot_id') != robot_id):
            continue
        eid = result.get('episode_id')
        task, name = run.get('instruction'), run.get('runnerName')
        started = result.get('run_started_at')
        if (not isinstance(eid, str) or not EPISODE.fullmatch(eid)
                or not isinstance(task, str) or not task.strip()
                or not isinstance(name, str) or not name.strip()
                or type(started) not in (int, float) or not math.isfinite(started) or started <= 0):
            continue
        configuration = {'model':approach, 'source_origin':origin, 'source_run_id':run.get('id')}
        inference = recorded_model(result.get('inference_model'))
        if inference:
            configuration['inference_model'] = inference
        models = result.get('inference_models')
        if isinstance(models, dict):
            configuration['inference_models'] = {role:model for role in ('initial','subsequent')
                if (model := recorded_model(models.get(role)))}
        # The source returns newest first. Keep that receipt if an episode repeats.
        projected.setdefault(eid, {'episode_id':eid, 'robot_id':robot_id, 'task':task[:8000],
            'started_at':started, 'runner_name':name.strip()[:32], 'configuration':configuration})
    return list(projected.values())


def save_receipts(database, receipts, *, origin, approach, robot_id):
    path = Path(database)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.touch(mode=0o600, exist_ok=True)
    with closing(sqlite3.connect(path)) as db, db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables and 'public_history_source' not in tables:
            raise ValueError('Use a dedicated public history cache')
        db.execute('CREATE TABLE IF NOT EXISTS public_history_source (origin TEXT, approach TEXT, robot_id TEXT)')
        source = db.execute('SELECT origin,approach,robot_id FROM public_history_source').fetchall()
        if source and source != [(origin, approach, robot_id)]:
            raise ValueError('History cache belongs to a different source')
        if not source:
            db.execute('INSERT INTO public_history_source VALUES (?,?,?)', (origin, approach, robot_id))
        db.execute('CREATE TABLE IF NOT EXISTS run_metadata (episode_id TEXT PRIMARY KEY, robot_id TEXT, task TEXT, started_at REAL)')
        db.execute('CREATE TABLE IF NOT EXISTS run_names (episode_id TEXT PRIMARY KEY, name TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS run_configuration (episode_id TEXT PRIMARY KEY, configuration TEXT NOT NULL)')
        for row in receipts:
            db.execute('INSERT INTO run_metadata VALUES (?,?,?,?) ON CONFLICT(episode_id) DO UPDATE SET task=excluded.task,started_at=excluded.started_at',
                       (row['episode_id'],row['robot_id'],row['task'],row['started_at']))
            db.execute('INSERT INTO run_names VALUES (?,?) ON CONFLICT(episode_id) DO UPDATE SET name=excluded.name',
                       (row['episode_id'],row['runner_name']))
            db.execute('INSERT INTO run_configuration VALUES (?,?) ON CONFLICT(episode_id) DO UPDATE SET configuration=excluded.configuration',
                       (row['episode_id'],json.dumps(row['configuration'])))
        return db.execute('SELECT count(*) FROM run_metadata').fetchone()[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--database', required=True)
    parser.add_argument('--approach', required=True)
    parser.add_argument('--robot-id', required=True)
    parser.add_argument('--token-file')
    args = parser.parse_args()
    try:
        token = Path(args.token_file).read_text().strip() if args.token_file else ''
        runs = read_runs(args.origin, token)
        receipts = project_runs(runs, origin=args.origin, approach=args.approach, robot_id=args.robot_id)
        retained = save_receipts(args.database, receipts, origin=args.origin,
                                 approach=args.approach, robot_id=args.robot_id)
    except (OSError, ValueError, sqlite3.Error) as error:
        # No raw response bodies, credentials or contact details in service logs.
        print('Public history sync failed (' + type(error).__name__ + ')', file=sys.stderr)
        return 1
    print(json.dumps({'source':args.origin, 'approach':args.approach, 'imported':len(receipts), 'retained':retained}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
