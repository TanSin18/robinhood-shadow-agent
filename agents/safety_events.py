"""Durable incident latch independent of the ordinary dashboard pause."""
import json
import re
import sqlite3
import os
from pathlib import Path
from uuid import uuid4
from data.connections import connection


def ensure_operations_schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS safety_incidents (id TEXT PRIMARY KEY, code TEXT NOT NULL, cycle_id TEXT, created_at TEXT NOT NULL, resolved_at TEXT)')
    db.execute('''CREATE TABLE IF NOT EXISTS notification_outbox (
      event_id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL,
      created_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'PENDING', next_attempt_at TEXT,
      delivered_at TEXT, error_class TEXT)''')
    db.execute('''CREATE TABLE IF NOT EXISTS notification_deliveries (
      event_id TEXT NOT NULL, channel TEXT NOT NULL,
      priority INTEGER NOT NULL DEFAULT 0, url TEXT,
      attempts INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'PENDING', next_attempt_at TEXT,
      delivered_at TEXT, error_class TEXT, request_id TEXT, receipt TEXT,
      PRIMARY KEY(event_id, channel),
      FOREIGN KEY(event_id) REFERENCES notification_outbox(event_id))''')
    # Existing installations had only the macOS status on the event row. Preserve
    # that evidence without replaying historic alerts to newly configured channels.
    db.execute('''INSERT OR IGNORE INTO notification_deliveries
      (event_id,channel,priority,attempts,status,next_attempt_at,delivered_at,error_class)
      SELECT event_id,'macos',0,attempts,status,next_attempt_at,delivered_at,error_class
      FROM notification_outbox''')


def record_incident(path, code, *, cycle_id=None, now,
                    dashboard_base_url='http://127.0.0.1:8765',
                    title='Shadow trading stopped', body=None):
    path = Path(path).resolve()
    if not re.fullmatch(r'[A-Z_]{1,80}', code):
        code = 'UNEXPECTED_CAPABILITY'
    identifier = uuid4().hex
    marker_error=None
    # Independent latch survives a failed database write while preserving a user pause.
    try:
        with (path.parent/'INCIDENT_STOP').open('x') as handle:
            json.dump({'incident_id':identifier,'code':code,'timestamp':now.isoformat()},handle)
            handle.flush(); os.fsync(handle.fileno())
    except FileExistsError: pass
    except OSError as error: marker_error=error
    try:
        with (path.parent / 'STOP_TRADING').open('x') as handle:
            json.dump({'owner': 'safety-incident', 'incident_id': identifier, 'timestamp': now.isoformat()}, handle)
    except FileExistsError:
        pass
    except OSError as error:
        marker_error=error
    with connection(path) as db:
        ensure_operations_schema(db)
        db.execute('INSERT INTO safety_incidents VALUES (?,?,?,?,NULL)', (identifier, code, cycle_id, now.isoformat()))
        from agents.notification_outbox import enqueue
        enqueue(db, identifier, title,
                body or f'Safety incident: {code}. Review the dashboard.', now,
                priority=1, url=dashboard_base_url.rstrip('/')+'/#activity')
    if marker_error is not None: raise marker_error
    return identifier


def incident_active(path):
    path = Path(path).resolve()
    latch=path.parent/'INCIDENT_STOP'
    if latch.exists() or latch.is_symlink(): return True
    if not path.exists():
        return False
    try:
        with connection(path.resolve().as_uri()+'?mode=ro', uri=True) as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='safety_incidents'").fetchone()
            return bool(exists and db.execute('SELECT 1 FROM safety_incidents WHERE resolved_at IS NULL LIMIT 1').fetchone())
    except sqlite3.Error:
        return True


def safety_stopped(path):
    path=Path(path).resolve()
    flag = path.parent / 'STOP_TRADING'
    return flag.exists() or flag.is_symlink() or incident_active(path)
