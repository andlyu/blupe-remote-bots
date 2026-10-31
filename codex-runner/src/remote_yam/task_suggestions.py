"""Public task suggestions, with one durable override per robot."""
from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3

DEFAULTS = {
    'yam-1': ['Put the apple onto the plate', 'Put the markers into the cup', 'Stack the blocks'],
    'yam-2': ['Stack the blocks', 'Put the orange block on the towel', 'Put the towel into the bin'],
}


def database_path(default=None):
    path = os.environ.get('YAM_TASK_SUGGESTIONS_DATABASE')
    if path:
        return Path(path)
    order = os.environ.get('YAM_ROBOT_ORDER_DATABASE')
    return Path(order).with_name('task-suggestions.sqlite3') if order else default


def validate_suggestions(values):
    if not isinstance(values, list) or len(values) != 3:
        raise ValueError('Enter exactly three task suggestions.')
    clean = []
    for value in values:
        if (not isinstance(value, str) or not value.strip() or len(value.strip()) > 200
                or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            raise ValueError('Each suggestion must be one line of 1–200 characters.')
        clean.append(value.strip())
    return clean


def read_suggestions(robot_id, path=None):
    path = database_path() if path is None else path
    if path and Path(path).exists():
        with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='task_suggestions'").fetchone():
                row = db.execute('SELECT suggestions FROM task_suggestions WHERE robot_id=?', (robot_id,)).fetchone()
                if row:
                    return validate_suggestions(json.loads(row[0]))
    return list(DEFAULTS.get(robot_id, []))


def save_suggestions(path, robot_id, values):
    if not isinstance(robot_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', robot_id):
        raise ValueError('Choose a valid robot.')
    values = validate_suggestions(values)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(descriptor)
    with closing(sqlite3.connect(path, timeout=5)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS task_suggestions (robot_id TEXT PRIMARY KEY, suggestions TEXT NOT NULL)')
        db.execute('INSERT INTO task_suggestions VALUES (?, ?) ON CONFLICT(robot_id) '
                   'DO UPDATE SET suggestions=excluded.suggestions', (robot_id, json.dumps(values)))
    return values
