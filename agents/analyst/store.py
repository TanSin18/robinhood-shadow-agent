"""The analyst desk's own database. Never the Official database or its directory."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)",
    "CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, at TEXT, day TEXT, kind TEXT, model TEXT, payload_json TEXT, "
    "checks_json TEXT)",
    "CREATE TABLE IF NOT EXISTS regimes (id INTEGER PRIMARY KEY, at TEXT, day TEXT, payload_json TEXT)",
    "CREATE TABLE IF NOT EXISTS kelly (id INTEGER PRIMARY KEY, at TEXT, day TEXT, payload_json TEXT)",
    "CREATE TABLE IF NOT EXISTS auction (id INTEGER PRIMARY KEY, at TEXT, day TEXT, payload_json TEXT)",
    "CREATE TABLE IF NOT EXISTS news (id INTEGER PRIMARY KEY, at TEXT, day TEXT, kind TEXT, payload_json TEXT)",
    "CREATE TABLE IF NOT EXISTS guard (id INTEGER PRIMARY KEY, at TEXT, day TEXT, payload_json TEXT)",
    "CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY, at TEXT, day TEXT, seat TEXT, model TEXT, reserved TEXT, "
    "actual TEXT, status TEXT)",
    "CREATE TABLE IF NOT EXISTS journal (id INTEGER PRIMARY KEY, at TEXT, kind TEXT, payload_json TEXT)",
)


class StoreError(RuntimeError):
    pass


def default_path(official_db):
    """robinhood-diagnostics/analyst/analyst.db beside the runtime checkout (same rule as the AI trader)."""
    return Path(official_db).resolve().parents[2] / 'robinhood-diagnostics' / 'analyst' / 'analyst.db'


class AnalystStore:
    def __init__(self, path, official_db=None, *, create=True):
        self.path = Path(path)
        if official_db is not None:
            official_dir = Path(official_db).resolve().parent
            if self.path.resolve().parent == official_dir or self.path.resolve() == Path(official_db).resolve():
                raise StoreError('ANALYST_DB_MUST_NOT_SHARE_THE_OFFICIAL_DIRECTORY')
        if not create and not self.path.is_file():
            raise StoreError('NOT_SET_UP')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            for stmt in SCHEMA:
                db.execute(stmt)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            yield db
            db.commit()
        finally:
            db.close()

    # ---------------------------------------------------------------- meta / journal
    def meta(self, key, default=None):
        with self.connect() as db:
            row = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return row[0] if row else default

    def set_meta(self, key, value):
        with self.connect() as db:
            db.execute('INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))

    def journal(self, kind, payload, now):
        with self.connect() as db:
            db.execute('INSERT INTO journal(at,kind,payload_json) VALUES(?,?,?)', (now.isoformat(), kind, json.dumps(payload, default=str)))

    # ---------------------------------------------------------------- records
    def add(self, table, day, payload, now, **extra):
        if table not in ('notes', 'regimes', 'kelly', 'auction', 'news', 'guard'):
            raise StoreError('UNKNOWN_TABLE')
        cols = ['at', 'day'] + list(extra) + ['payload_json']
        vals = [now.isoformat(), day] + [json.dumps(v, default=str) if isinstance(v, (dict, list)) else v for v in extra.values()]
        vals.append(json.dumps(payload, default=str))
        with self.connect() as db:
            db.execute(f'INSERT INTO {table}({",".join(cols)}) VALUES({",".join("?" * len(cols))})', vals)

    def latest(self, table, kind=None):
        q = f'SELECT day, at, payload_json FROM {table}' + (' WHERE kind=?' if kind else '') + ' ORDER BY id DESC LIMIT 1'
        with self.connect() as db:
            row = db.execute(q, (kind,) if kind else ()).fetchone()
        return None if not row else {'day': row[0], 'at': row[1], **json.loads(row[2])}

    # ---------------------------------------------------------------- budget (same contract BudgetedModels expects)
    def spent(self, day=None):
        with self.connect() as db:
            q = 'SELECT actual, reserved, status FROM budget' + (' WHERE day=?' if day else '')
            rows = db.execute(q, (day,) if day else ()).fetchall()
        return sum((Decimal(a) if a is not None else Decimal(r)) for a, r, _ in rows) if rows else Decimal(0)
