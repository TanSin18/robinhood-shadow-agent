"""Read-only access to the registered (Official) database: Control A's records, for comparison and plumbing tests.

Three independent barriers, any one of which is enough:
  1. the file is opened with SQLite ``mode=ro`` (the connection cannot write the file);
  2. ``PRAGMA query_only=ON`` (the connection refuses write statements);
  3. an authorizer that allows only reads and denies everything else.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .errors import FirmLabError

_READS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}


def _authorize(action, *_):
    return sqlite3.SQLITE_OK if action in _READS else sqlite3.SQLITE_DENY


@contextmanager
def open_official(path):
    path = Path(path)
    if not path.is_file():
        raise FirmLabError('OFFICIAL_DATABASE_NOT_FOUND')
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=2)
    try:
        db.execute('PRAGMA query_only=ON')
        db.set_authorizer(_authorize)
        yield db
    finally:
        db.close()


def capsules(path, *, limit=None):
    """Control A's decision capsules, oldest first: what each registered run saw and decided."""
    out = []
    with open_official(path) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='decision_capsules'").fetchone():
            return out
        q = 'SELECT hash, cycle_id, created_at, payload FROM decision_capsules ORDER BY created_at'
        for capsule_hash, cycle_id, created_at, payload in db.execute(q):
            try:
                body = json.loads(payload)
            except ValueError:
                continue
            out.append({'hash': capsule_hash, 'cycle_id': cycle_id, 'created_at': created_at, 'payload': body})
    return out[-limit:] if limit else out
