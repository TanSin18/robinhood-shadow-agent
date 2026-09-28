"""Deterministic, redacted tripwire for changes in the Agentic account."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from agents.safety_events import ensure_operations_schema, record_incident
from data.connections import connection


class TripwireViolation(RuntimeError):
    def __init__(self, code: str, *, incident_id: str, snapshot_hash: str,
                 change_class: str) -> None:
        super().__init__(code)
        self.code = code
        self.incident_id = incident_id
        self.snapshot_hash = snapshot_hash
        self.change_class = change_class


@dataclass(frozen=True)
class TripwireDecision:
    status: str
    snapshot_hash: str
    change_class: str | None = None
    incident_id: str | None = None


def ensure_tripwire_schema(db) -> None:
    ensure_operations_schema(db)
    db.execute('''CREATE TABLE IF NOT EXISTS broker_state_snapshots (
      id INTEGER PRIMARY KEY AUTOINCREMENT, cycle_id TEXT NOT NULL,
      snapshot_hash TEXT NOT NULL, status TEXT NOT NULL, change_class TEXT,
      incident_id TEXT, created_at TEXT NOT NULL, payload_json TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS broker_change_acknowledgements (
      id TEXT PRIMARY KEY, incident_id TEXT NOT NULL,
      expected_snapshot_hash TEXT NOT NULL, change_class TEXT NOT NULL,
      expires_at TEXT NOT NULL, created_at TEXT NOT NULL, consumed_at TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS broker_tripwire_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT NOT NULL,
      snapshot_hash TEXT NOT NULL, change_class TEXT,
      created_at TEXT NOT NULL)''')


def _decimal(value) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('invalid broker snapshot') from None
    if not number.is_finite() or number < 0:
        raise ValueError('invalid broker snapshot')
    normalized = number.normalize()
    return '0' if normalized == 0 else format(normalized, 'f')


def _records(records, *, kind: str) -> list[dict]:
    if not isinstance(records, list):
        raise ValueError('invalid broker snapshot')
    result = []
    for item in records:
        if not isinstance(item, dict):
            raise ValueError('invalid broker snapshot')
        if kind == 'position':
            identifier = item.get('instrument_id') or item.get('instrument') or item.get('id')
            if not isinstance(identifier, str) or not identifier:
                raise ValueError('invalid broker snapshot')
            result.append({
                'id': identifier,
                'quantity': _decimal(item.get('quantity')),
                'direction': str(item.get('direction') or item.get('side') or 'long'),
            })
        else:
            identifier = item.get('id') or item.get('order_id')
            if not isinstance(identifier, str) or not identifier:
                raise ValueError('invalid broker snapshot')
            result.append({
                'id': identifier,
                'state': str(item.get('state') or item.get('status') or ''),
                'created_at': str(item.get('created_at') or ''),
                'updated_at': str(item.get('updated_at') or ''),
                'type': str(item.get('type') or item.get('side') or ''),
                'record_hash': _hash(item),
            })
    return sorted(result, key=lambda item: json.dumps(item, sort_keys=True))


def _snapshot(cash, positions, equity_orders, option_orders, crypto_orders) -> dict:
    return {
        'cash': _decimal(cash),
        'positions': _records(positions, kind='position'),
        'orders': {
            'equity': _records(equity_orders, kind='order'),
            'option': _records(option_orders, kind='order'),
            'crypto': _records(crypto_orders, kind='order'),
        },
    }


def _hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()


def _change_class(previous: dict, current: dict, cap: Decimal) -> tuple[str | None, str | None]:
    categories = []
    cash = Decimal(current['cash'])
    prior_cash = Decimal(previous['cash'])
    if cash > cap:
        categories.append('cash_above_cap')
    elif cash < prior_cash:
        categories.append('cash_decrease')
    if current['positions'] != previous['positions']:
        categories.append('positions')
    if current['orders'] != previous['orders']:
        categories.append('order_activity')
    change_class = '+'.join(categories) if categories else None
    code = ('AGENTIC_ACCOUNT_OUTSIDE_BOUNDS' if 'cash_above_cap' in categories
            else 'AGENTIC_ACCOUNT_UNACKNOWLEDGED_CHANGE' if categories else None)
    return change_class, code


def evaluate_snapshot(database, *, cash, positions, equity_orders, option_orders,
                      crypto_orders, max_agentic_cash_usd, cycle_id, now,
                      dashboard_base_url) -> TripwireDecision:
    path = Path(database).resolve()
    if now.tzinfo is None:
        raise ValueError('tripwire clock must be timezone-aware')
    cap = Decimal(str(max_agentic_cash_usd))
    if not cap.is_finite() or cap < 0:
        raise ValueError('invalid cash cap')
    payload = _snapshot(cash, positions, equity_orders, option_orders, crypto_orders)
    snapshot_hash = _hash(payload)
    with connection(path) as db:
        ensure_tripwire_schema(db)
        row = db.execute('''SELECT payload_json,snapshot_hash FROM broker_state_snapshots
          WHERE status='VERIFIED' ORDER BY id DESC LIMIT 1''').fetchone()
        if row is None:
            if Decimal(payload['cash']) > cap:
                previous = {**payload, 'cash': '0'}
            else:
                db.execute('''INSERT INTO broker_state_snapshots
                  (cycle_id,snapshot_hash,status,change_class,incident_id,created_at,payload_json)
                  VALUES (?,?,'VERIFIED',NULL,NULL,?,?)''',
                  (cycle_id, snapshot_hash, now.isoformat(), json.dumps(payload, sort_keys=True)))
                db.execute('INSERT INTO broker_tripwire_events(status,snapshot_hash,created_at) VALUES (?,?,?)',
                           ('BASELINE_CREATED', snapshot_hash, now.isoformat()))
                return TripwireDecision('BASELINE_CREATED', snapshot_hash)
        else:
            previous = json.loads(row[0])
            if row[1] == snapshot_hash:
                db.execute('INSERT INTO broker_tripwire_events(status,snapshot_hash,created_at) VALUES (?,?,?)',
                           ('VERIFIED_UNCHANGED', snapshot_hash, now.isoformat()))
                return TripwireDecision('VERIFIED_UNCHANGED', snapshot_hash)
        change_class, code = _change_class(previous, payload, cap)
        if change_class is None and Decimal(payload['cash']) > Decimal(previous['cash']):
            db.execute('''INSERT INTO broker_state_snapshots
              (cycle_id,snapshot_hash,status,change_class,incident_id,created_at,payload_json)
              VALUES (?,?,'VERIFIED',NULL,NULL,?,?)''',
              (cycle_id, snapshot_hash, now.isoformat(), json.dumps(payload, sort_keys=True)))
            db.execute('INSERT INTO broker_tripwire_events(status,snapshot_hash,created_at) VALUES (?,?,?)',
                       ('ACCOUNT_CASH_INCREASE_BENIGN', snapshot_hash, now.isoformat()))
            return TripwireDecision('ACCOUNT_CASH_INCREASE_BENIGN', snapshot_hash)
        # A cash-only increase is benign; _change_class deliberately omits it.
        if change_class is None:
            raise ValueError('unclassifiable broker snapshot')
        existing = db.execute('''SELECT incident_id FROM broker_state_snapshots
          WHERE snapshot_hash=? AND status='PENDING' ORDER BY id DESC LIMIT 1''',
          (snapshot_hash,)).fetchone()
        if existing and existing[0]:
            incident_id = existing[0]
        else:
            db.execute('''INSERT INTO broker_state_snapshots
              (cycle_id,snapshot_hash,status,change_class,incident_id,created_at,payload_json)
              VALUES (?,?,'PENDING',?,NULL,?,?)''',
              (cycle_id, snapshot_hash, change_class, now.isoformat(), json.dumps(payload, sort_keys=True)))
            incident_id = None
    if incident_id is None:
        incident_id = record_incident(
            path,
            code,
            cycle_id=cycle_id,
            now=now,
            dashboard_base_url=dashboard_base_url,
            title='Agentic account change detected',
            body='Review and revoke access if unrecognized. Open the local dashboard for redacted details.',
        )
        with connection(path) as db:
            ensure_tripwire_schema(db)
            db.execute('''UPDATE broker_state_snapshots SET incident_id=?
              WHERE snapshot_hash=? AND status='PENDING' AND incident_id IS NULL''',
              (incident_id, snapshot_hash))
            db.execute('INSERT INTO broker_tripwire_events(status,snapshot_hash,change_class,created_at) VALUES (?,?,?,?)',
                       (code, snapshot_hash, change_class, now.isoformat()))
    raise TripwireViolation(
        code,
        incident_id=incident_id,
        snapshot_hash=snapshot_hash,
        change_class=change_class,
    )


def _remove_owned_latches(path: Path) -> None:
    incident = path.parent / 'INCIDENT_STOP'
    stop = path.parent / 'STOP_TRADING'
    for marker, required_owner in ((incident, None), (stop, 'safety-incident')):
        try:
            details = marker.lstat()
            if not stat.S_ISREG(details.st_mode) or details.st_uid != os.getuid():
                continue
            with os.fdopen(os.open(marker, os.O_RDONLY | os.O_NOFOLLOW)) as handle:
                current = os.fstat(handle.fileno())
                payload = json.loads(handle.read(2048))
            if required_owner is not None and payload.get('owner') != required_owner:
                continue
            latest = marker.lstat()
            if (latest.st_ino, latest.st_dev) == (current.st_ino, current.st_dev):
                marker.unlink()
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
            continue


def acknowledge_change(database, *, incident_id, expected_snapshot_hash,
                       change_class, expires_at, csrf_confirmed, now) -> None:
    path = Path(database).resolve()
    if not csrf_confirmed or now.tzinfo is None or expires_at.tzinfo is None or now >= expires_at:
        raise ValueError('invalid or expired acknowledgement')
    with connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        ensure_tripwire_schema(db)
        incident = db.execute(
            'SELECT code FROM safety_incidents WHERE id=? AND resolved_at IS NULL',
            (incident_id,),
        ).fetchone()
        pending = db.execute('''SELECT id,snapshot_hash,change_class FROM broker_state_snapshots
          WHERE incident_id=? AND status='PENDING' ORDER BY id DESC LIMIT 1''',
          (incident_id,)).fetchone()
        if (
            incident is None or pending is None
            or pending[1] != expected_snapshot_hash
            or pending[2] != change_class
        ):
            raise ValueError('acknowledgement does not match the pending change')
        identifier = uuid4().hex
        db.execute('''INSERT INTO broker_change_acknowledgements
          VALUES (?,?,?,?,?,?,?)''', (
            identifier, incident_id, expected_snapshot_hash, change_class,
            expires_at.isoformat(), now.isoformat(), now.isoformat(),
        ))
        db.execute("UPDATE broker_state_snapshots SET status='VERIFIED' WHERE id=?", (pending[0],))
        db.execute('UPDATE safety_incidents SET resolved_at=? WHERE id=? AND resolved_at IS NULL',
                   (now.isoformat(), incident_id))
        unresolved = db.execute(
            'SELECT COUNT(*) FROM safety_incidents WHERE resolved_at IS NULL'
        ).fetchone()[0]
    if unresolved == 0:
        _remove_owned_latches(path)


def public_status(database) -> list[dict]:
    path = Path(database).resolve()
    if not path.exists():
        return []
    with connection(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'broker_tripwire_events' not in tables:
            return []
        pending = {
            row[0]: row[1]
            for row in db.execute('''SELECT snapshot_hash,incident_id
              FROM broker_state_snapshots WHERE status='PENDING' AND incident_id IS NOT NULL''')
        }
        return [
            {
                'status': row[0],
                'snapshot_hash': row[1],
                'change_class': row[2],
                'created_at': row[3],
                'incident_id': pending.get(row[1]),
            }
            for row in db.execute('''SELECT status,snapshot_hash,change_class,created_at
              FROM broker_tripwire_events ORDER BY id DESC''')
        ]
