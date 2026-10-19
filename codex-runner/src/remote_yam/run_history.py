"""Resolve private contact submissions to public episode identifiers only."""
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from .socials import social_handles


def history_ids(database, email, browser_ids):
    email = social_handles({'email': email})['email'].casefold()
    if not isinstance(browser_ids, list) or len(browser_ids) > 100 or any(
            not isinstance(eid, str) or not re.fullmatch(r'ep_[A-Za-z0-9_-]{1,100}', eid)
            for eid in browser_ids):
        raise ValueError('Invalid browser run history')
    found = set(browser_ids)
    path = Path(database)
    if email and path.is_file():
        # Query the existing private journal. Email never enters the public index,
        # a URL, or the response. Parameters are always bound, including email.
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
            rows = db.execute("""
                SELECT e.details FROM submissions e
                JOIN (SELECT DISTINCT submission_id FROM submissions
                      WHERE event='submitted' AND json_valid(details)
                        AND lower(trim(json_extract(details, '$.fields.email')))=?) s
                ON s.submission_id=e.submission_id
                WHERE e.event IN ('lifecycle','stop_accepted')
                ORDER BY e.id DESC LIMIT 1000
                """, (email,)).fetchall()
        for encoded, in rows:
            try:
                eid = json.loads(encoded).get('episode_id', '')
            except (ValueError, AttributeError):
                continue
            if isinstance(eid, str) and re.fullmatch(r'ep_[A-Za-z0-9_-]{1,100}', eid):
                found.add(eid)
    return found
