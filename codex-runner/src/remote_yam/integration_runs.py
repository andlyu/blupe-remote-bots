"""Read public receipts and immutable replays from configured same-host integrations.

Only public run fields are projected. Databases stay with their owner; reads use
SQLite read-only mode and never copy credentials, emails or provider settings.
"""
from contextlib import closing
import hashlib
import json
import logging
import math
from pathlib import Path
import re
import sqlite3

from .past_runs import run_result
from .run_history import recorded_model
from .run_search import rank_runs

LOG = logging.getLogger(__name__)
EPISODE = re.compile(r'ep_[A-Za-z0-9_-]{1,100}')
DIGEST = re.compile(r'[0-9a-f]{64}')
MAX_VIDEO_BYTES = 16 * 1024 * 1024


class PublicRunSource:
    def __init__(self, database, replay_root, robot_id):
        self.database = Path(database).resolve()
        self.replay_root = Path(replay_root).resolve()
        self.robot_id = robot_id

    def rows(self):
        if not self.database.is_file():
            return {}
        with closing(sqlite3.connect(self.database.as_uri() + '?mode=ro', uri=True, timeout=.2)) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'run_metadata' not in tables:
                return {}
            names = dict(db.execute('SELECT episode_id,name FROM run_names')) if 'run_names' in tables else {}
            configurations = dict(db.execute('SELECT episode_id,configuration FROM run_configuration')) if 'run_configuration' in tables else {}
            outcomes = {eid: dict(result=result, result_reason=reason,
                        ending_reason=reason, errors=reason if result == 'Failure' else None)
                        for eid, result, reason in db.execute('SELECT episode_id,result,reason FROM run_results')} if 'run_results' in tables else {}
            if 'run_details' in tables:
                for eid, errors, ending in db.execute('SELECT episode_id,errors,ending_reason FROM run_details'):
                    if eid in outcomes:
                        outcomes[eid].update(errors=errors, ending_reason=ending or outcomes[eid]['ending_reason'])
            rows = {}
            for eid, task, started in db.execute(
                    'SELECT episode_id,task,started_at FROM run_metadata WHERE robot_id=?', (self.robot_id,)):
                if not EPISODE.fullmatch(eid or '') or type(started) not in (int, float) or not math.isfinite(started):
                    continue
                try:
                    configuration = json.loads(configurations.get(eid, '{}'))
                    model = recorded_model(configuration.get('model'))
                except (ValueError, AttributeError):
                    model = None
                rows[eid] = dict(episode_id=eid, episode_index=None, robot_id=self.robot_id,
                    prompt=task or 'Task unavailable', started_at=started,
                    runner_name=names.get(eid, 'Name not recorded'),
                    **outcomes.get(eid, {}))
                if model:
                    rows[eid]['model'] = model
            return rows

    def clip(self, eid):
        if not EPISODE.fullmatch(eid or ''):
            return None
        try:
            meta = json.loads((self.replay_root / (eid + '.json')).read_text())
            info = meta['preview']
            digest, duration = info['sha256'], info['duration_s']
            speed, cameras = info.get('speed', 10), info['camera_order']
            path = self.replay_root / eid / (digest + '.mp4')
            if (meta['episode_id'] != eid or meta['robot_id'] != self.robot_id
                    or not DIGEST.fullmatch(digest) or path.resolve().parent != self.replay_root / eid
                    or not 0 < path.stat().st_size == meta['bytes'] <= MAX_VIDEO_BYTES
                    or type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0
                    or type(speed) not in (int, float) or not math.isfinite(speed) or not 1 <= speed <= 10
                    or not isinstance(cameras, list) or not 1 <= len(cameras) <= 4
                    or any(c not in {'left', 'top', 'right', 'observer'} for c in cameras)):
                return None
            return dict(video_url=f'/api/integration-replays/{eid}/{digest}.mp4',
                video_status='ready', video_sha256=digest, video_duration_s=duration,
                camera_order=cameras, compressed=True, preview_speed=speed,
                video_layout=info.get('layout'), original_available=meta.get('original_available') is True,
                original_video_url=f'https://huggingface.co/datasets/andlyu/Public-YAM-runs/resolve/main/videos/{eid}.mp4')
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def video(self, eid, digest, range_header=None):
        if not EPISODE.fullmatch(eid or '') or not DIGEST.fullmatch(digest or ''):
            return None
        if eid not in self.rows():
            return None
        clip = self.clip(eid)
        if not clip or clip['video_sha256'] != digest:
            return None
        path = self.replay_root / eid / (digest + '.mp4')
        with path.open('rb') as stream:
            body = stream.read(MAX_VIDEO_BYTES + 1)
        if not 0 < len(body) <= MAX_VIDEO_BYTES or hashlib.sha256(body).hexdigest() != digest:
            return None
        headers = [(b'accept-ranges', b'bytes'), (b'etag', ('"' + digest + '"').encode())]
        if not range_header:
            return 200, body, headers
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', range_header)
        if not match or not any(match.groups()):
            return 416, b'', headers + [(b'content-range', f'bytes */{len(body)}'.encode())]
        first, last = match.groups()
        start = int(first) if first else max(0, len(body) - int(last))
        end = min(int(last), len(body) - 1) if first and last else len(body) - 1
        if start > end or start >= len(body):
            return 416, b'', headers + [(b'content-range', f'bytes */{len(body)}'.encode())]
        return 206, body[start:end+1], headers + [(b'content-range', f'bytes {start}-{end}/{len(body)}'.encode())]


class IntegrationRuns:
    """Merge configured public integration runs into every existing history view."""
    source = 'public archive and integration run receipts'

    def __init__(self, archive, sources):
        self.archive = archive
        self.sources = [PublicRunSource(**source) for source in sources]
        # Retain compatibility with hosts already serving the quick-replay API.
        self.quick_replays = self

    def __getattr__(self, name):
        return getattr(self.archive, name)

    def receipts(self):
        rows = {}
        for source in self.sources:
            try:
                for eid, row in source.rows().items():
                    rows.setdefault(eid, (source, row))
            except (OSError, sqlite3.Error, ValueError, TypeError):
                LOG.warning('Public integration receipts unavailable')
        return rows

    def page(self, offset=0, *, episode_id=None, episode_ids=None, robot_id=None,
             model='', query='', metadata=False, models=None):
        receipts = self.receipts()
        try:
            catalog = self.archive.page(metadata=True)
        except Exception:
            if not receipts:
                raise
            catalog = {'runs': [], 'stale': True}
        rows = {r['episode_id']: dict(r) for r in catalog['runs']}
        for eid, (_, receipt) in receipts.items():
            old = rows.get(eid, {})
            row = dict(old, **receipt)
            if row.get('model') is None:
                row['model'] = old.get('model')
            if not old:
                row.update(video_status='processing', video_url=None, original_available=False)
            rows[eid] = row
        rows = [r for r in rows.values() if (robot_id is None or r['robot_id'] == robot_id)
                and (episode_ids is None or r['episode_id'] in episode_ids)]
        choices = sorted({r.get('model') or '__unrecorded__' for r in rows}, key=str.casefold)
        rows = [r for r in rows if (not model or (r.get('model') or '__unrecorded__') == model)
                and (not models or (r.get('model') or '__unrecorded__') in models)]
        rows.sort(key=lambda r: r.get('started_at') or 0, reverse=True)
        if query.strip() and episode_id is None:
            rows = rank_runs(rows, query)
        if episode_id is not None:
            rows = [r for r in rows if r['episode_id'] == episode_id]
        selected = rows if metadata else rows[offset:offset+12]
        if metadata:
            for row in selected:
                if row['episode_id'] in receipts:
                    clip = receipts[row['episode_id']][0].clip(row['episode_id'])
                    if clip:
                        row.update(clip)
                        row['preview'] = clip
        else:
            selected = self._details(selected, receipts)
        return dict(runs=selected, models=choices, total=len(rows), stale=catalog.get('stale', False),
            next_offset=offset+len(selected) if not metadata and offset+len(selected)<len(rows) else None)

    def _details(self, rows, receipts):
        local = {r['episode_id']: clip for r in rows if r['episode_id'] in receipts
                 and (clip := receipts[r['episode_id']][0].clip(r['episode_id']))}
        published = [r for r in rows if r['episode_id'] not in local and r.get('video_status') != 'processing']
        details = {r['episode_id']: r for r in self.archive.details_for(published)} if published else {}
        return [{**run_result({}), **details.get(r['episode_id'], r),
                 **receipts.get(r['episode_id'], (None, {}))[1], **local.get(r['episode_id'], {})}
                for r in rows]

    def details_for(self, rows):
        return self._details(rows, self.receipts())

    def get(self, episode_id, robot_id=None):
        if not EPISODE.fullmatch(episode_id or ''):
            raise ValueError('Invalid episode ID')
        receipts = self.receipts()
        if episode_id in receipts:
            source, row = receipts[episode_id]
            if robot_id is not None and row['robot_id'] != robot_id:
                return None
            if clip := source.clip(episode_id):
                return {**run_result({}), **row, **clip}
        try:
            row = self.archive.get(episode_id)
        except Exception:
            if episode_id not in receipts:
                raise
            row = None
        if row:
            return dict(row, **receipts.get(episode_id, (None, {}))[1])
        if episode_id in receipts:
            return {**run_result({}), **receipts[episode_id][1], 'video_status':'processing',
                    'video_url':None, 'original_available':False}
        return None

    def video(self, eid, digest, range_header=None):
        for source in self.sources:
            try:
                if result := source.video(eid, digest, range_header):
                    return result
            except (OSError, sqlite3.Error):
                continue
        original = getattr(self.archive, 'quick_replays', None)
        return original.video(eid, digest, range_header) if original else None
