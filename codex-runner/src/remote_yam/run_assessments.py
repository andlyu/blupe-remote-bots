"""Durable human assessments. Archive/machine outcomes never create a label.

Session and optional application user identifiers stay in this private SQLite
overlay; public projections contain neither. Votes belong to a label revision.
"""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import sqlite3
import time


class AssessmentConflict(ValueError):
    pass


def identity(value):
    return hashlib.sha256(value.encode()).hexdigest() if value else None


class RunAssessments:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def database(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(mode=0o600, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS assessment_runs (
                    run_id TEXT PRIMARY KEY, owner_session TEXT NOT NULL,
                    owner_user TEXT, ended INTEGER NOT NULL DEFAULT 0,
                    revision INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS assessments (
                    run_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    label TEXT, author_session TEXT NOT NULL, author_user TEXT,
                    created_at REAL NOT NULL, PRIMARY KEY(run_id, revision));
                CREATE TABLE IF NOT EXISTS assessment_votes (
                    run_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    reviewer TEXT NOT NULL, vote INTEGER NOT NULL,
                    updated_at REAL NOT NULL, PRIMARY KEY(run_id,revision,reviewer));
                CREATE TABLE IF NOT EXISTS assessment_vote_events (
                    run_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    reviewer TEXT NOT NULL, vote INTEGER, created_at REAL NOT NULL);
            ''')
            with db:
                yield db
        finally:
            db.close()

    def register(self, run_id, session, user=None, *, ended=False):
        """Only called with a run already associated with the trusted runner."""
        with self.database() as db:
            db.execute('''INSERT INTO assessment_runs(run_id,owner_session,owner_user,ended)
                VALUES(?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET
                ended=MAX(assessment_runs.ended,excluded.ended),
                owner_user=COALESCE(assessment_runs.owner_user,excluded.owner_user)
                WHERE assessment_runs.owner_session=excluded.owner_session''',
                (run_id, identity(session), identity(user), int(ended)))

    @staticmethod
    def can_edit(owner, session, user):
        return bool(owner and (owner['owner_session'] == identity(session)
                    or user and owner['owner_user'] == identity(user)))

    def assess(self, run_id, label, revision, session, user=None):
        if label not in (None, 'Success', 'Failure'):
            raise ValueError('Choose Not completed, Failed, or Succeeded')
        with self.database() as db:
            db.execute('BEGIN IMMEDIATE')
            owner = db.execute('SELECT * FROM assessment_runs WHERE run_id=?', (run_id,)).fetchone()
            if not self.can_edit(owner, session, user):
                raise PermissionError('Only the runner session or recorded user can edit this assessment')
            current = db.execute('SELECT label FROM assessments WHERE run_id=? AND revision=?',
                                 (run_id, owner['revision'])).fetchone()
            # Retried identical writes are idempotent, including after a lost response.
            if (current['label'] if current else None) == label:
                return
            if type(revision) is not int or revision != owner['revision']:
                raise AssessmentConflict('Assessment changed. Refresh before editing.')
            next_revision = revision + 1
            db.execute('INSERT INTO assessments VALUES(?,?,?,?,?,?)',
                       (run_id, next_revision, label, identity(session), identity(user), time.time()))
            db.execute('UPDATE assessment_runs SET revision=? WHERE run_id=?', (next_revision, run_id))

    def vote(self, run_id, revision, vote, session):
        if vote is not None and (type(vote) is not int or vote not in (-1, 1)):
            raise ValueError('Vote must be correct, incorrect, or removed')
        with self.database() as db:
            db.execute('BEGIN IMMEDIATE')
            owner = db.execute('SELECT * FROM assessment_runs WHERE run_id=?', (run_id,)).fetchone()
            if owner and owner['owner_session'] == identity(session):
                raise PermissionError('The originating runner session cannot review its own assessment')
            if not owner or type(revision) is not int or owner['revision'] != revision:
                raise AssessmentConflict('Assessment changed. Refresh before reviewing.')
            label = db.execute('SELECT label FROM assessments WHERE run_id=? AND revision=?',
                               (run_id, revision)).fetchone()
            if not label or not label['label'] or not owner['ended']:
                raise ValueError('Only ended, labeled runs can be reviewed')
            reviewer, now = identity(session), time.time()
            old = db.execute('SELECT vote FROM assessment_votes WHERE run_id=? AND revision=? AND reviewer=?',
                             (run_id, revision, reviewer)).fetchone()
            if (old['vote'] if old else None) == vote:
                return
            if vote is None:
                db.execute('DELETE FROM assessment_votes WHERE run_id=? AND revision=? AND reviewer=?',
                           (run_id, revision, reviewer))
            else:
                db.execute('''INSERT INTO assessment_votes VALUES(?,?,?,?,?)
                    ON CONFLICT(run_id,revision,reviewer) DO UPDATE SET vote=excluded.vote,
                    updated_at=excluded.updated_at''', (run_id, revision, reviewer, vote, now))
            db.execute('INSERT INTO assessment_vote_events VALUES(?,?,?,?,?)',
                       (run_id, revision, reviewer, vote, now))

    def summaries(self):
        with self.database() as db:
            rows = db.execute('''SELECT r.run_id,r.revision,r.ended,a.label,a.created_at,
                COALESCE(SUM(v.vote=1),0) AS correct, COALESCE(SUM(v.vote=-1),0) AS incorrect
                FROM assessment_runs r LEFT JOIN assessments a
                  ON a.run_id=r.run_id AND a.revision=r.revision
                LEFT JOIN assessment_votes v ON v.run_id=r.run_id AND v.revision=r.revision
                GROUP BY r.run_id''').fetchall()
        return {r['run_id']: self.summary(dict(r)) for r in rows}

    @staticmethod
    def summary(row=None):
        data = dict(revision=0, label=None, correct=0, incorrect=0, ended=True, created_at=None)
        if row:
            data.update({k: row[k] for k in data if k in row})
        data['ended'] = bool(data['ended'])
        data['eligibility'] = ('provisional' if not data['ended'] else 'unlabeled' if not data['label']
                               else 'included' if data['correct'] >= data['incorrect'] else 'excluded')
        return data

    def detail(self, run_id, session, user=None):
        summary = self.summaries().get(run_id, self.summary())
        with self.database() as db:
            owner = db.execute('SELECT * FROM assessment_runs WHERE run_id=?', (run_id,)).fetchone()
            vote = db.execute('SELECT vote FROM assessment_votes WHERE run_id=? AND revision=? AND reviewer=?',
                              (run_id, summary['revision'], identity(session))).fetchone()
            history = db.execute('''SELECT a.revision,a.label,a.created_at,
                COALESCE(SUM(v.vote=1),0) AS correct, COALESCE(SUM(v.vote=-1),0) AS incorrect
                FROM assessments a LEFT JOIN assessment_votes v
                ON a.run_id=v.run_id AND a.revision=v.revision WHERE a.run_id=?
                GROUP BY a.revision ORDER BY a.revision DESC''', (run_id,)).fetchall()
        return {**summary, 'can_edit': self.can_edit(owner, session, user),
                'can_vote': bool(owner and owner['owner_session'] != identity(session)
                                 and summary['label'] and summary['ended']),
                'my_vote': vote['vote'] if vote else None, 'history': [dict(r) for r in history]}


def model_key(row):
    return (row.get('model') or '__unrecorded__', row.get('model_version') or 'unknown')


def score_models(rows, groups=()):
    """Call on the complete filtered metadata set, before pagination/drawing."""
    def blank(model, version):
        return dict(model=model, version=version, successes=0, failures=0,
                    unlabeled=0, excluded=0, provisional=0)
    models = {model_key(row): blank(*model_key(row)) for row in groups}
    for row in rows:
        model, version = model_key(row)
        score = models.setdefault((model, version), blank(model, version))
        assessment = row.get('assessment') or RunAssessments.summary()
        state = assessment['eligibility']
        if state == 'included':
            score['successes' if assessment['label'] == 'Success' else 'failures'] += 1
        else:
            score[state] += 1
    for score in models.values():
        score['denominator'] = score['successes'] + score['failures']
        score['rate'] = score['successes'] / score['denominator'] if score['denominator'] else None
    return sorted(models.values(), key=lambda s: (s['model'].casefold(), s['version']))
