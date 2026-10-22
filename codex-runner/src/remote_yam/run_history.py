"""Project public episode and model identities from private submissions."""
import re
import sqlite3
from contextlib import closing
from pathlib import Path

def recorded_model(value):
    if (isinstance(value, str) and len(value) <= 128 and value.strip()
            and all(ord(c) >= 32 for c in value)):
        return value.strip()
    return None


def run_models(database):
    """Project only recorded episode IDs and model IDs from the private journal."""
    path = Path(database)
    if not path.is_file():
        return {}
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
        rows = db.execute("""
            SELECT json_extract(e.details, '$.episode_id'),
                   json_extract(s.details, '$.fields.model')
            FROM submissions e JOIN submissions s USING (submission_id)
            WHERE s.event='submitted' AND json_valid(s.details)
              AND e.event IN ('lifecycle','stop_accepted') AND json_valid(e.details)
              AND json_type(s.details, '$.fields.model')='text'
              AND json_type(e.details, '$.episode_id')='text'
            ORDER BY e.id DESC, s.id DESC
            """)
        models = {}
        for eid, model in rows:
            model = recorded_model(model)
            if (isinstance(eid, str) and re.fullmatch(r'ep_[A-Za-z0-9_-]{1,100}', eid)
                    and model):
                models.setdefault(eid, model)
        return models
