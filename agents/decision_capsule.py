"""Content-addressed, sanitized decision capsule per cycle, for replay.

Captures what a cycle actually saw and produced: quotes, volatility, closes,
strategy output, paper account state, each model stage's exact request and
structured output, and the outcome. Never contains account identifiers,
order histories, tokens or raw broker payloads. Capture failure never fails the
cycle; the cycle records capsule_status UNAVAILABLE instead.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal

from research.strategy_signals import ETF_UNIVERSE, evaluate_daily_signals

VERSION = 1
FORBIDDEN_KEYS = {'account_number', 'account_id', 'account_last4', 'agentic_account_id', 'token',
                  'access_token', 'refresh_token', 'orders', 'order_history'}


def _plain(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items() if str(k) not in FORBIDDEN_KEYS}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_plain(v) for v in value]
        return sorted(items, key=json.dumps) if isinstance(value, (set, frozenset)) else items
    if hasattr(value, 'model_dump'):
        return _plain(value.model_dump(mode='json'))
    return value


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), default=str)


def build(*, cycle_id, data_mode, observed_at, registration_sha256, models, snapshot, strategy_assessment,
          accounts, stage_requests, stage_outputs, result):
    quotes = {s: {'bid': str(q.bid), 'ask': str(q.ask), 'timestamp': q.timestamp.isoformat(), 'halted': q.halted}
              for s, q in (snapshot or {}).get('quotes', {}).items()}
    vols = {s: {'vol': str(v[0]), 'as_of': v[1].isoformat() if v[1] else None}
            for s, v in (snapshot or {}).get('vols', {}).items()}
    capsule = {
        'capsule_version': VERSION, 'cycle_id': cycle_id, 'data_mode': data_mode,
        'observed_at': observed_at.isoformat() if observed_at else None,
        'registration_sha256': registration_sha256, 'models': models,
        'inputs': {'quotes': quotes, 'vols': vols,
                   'session_closes': (snapshot or {}).get('session_closes', {}),
                   'median_dollar_volume_20d': (snapshot or {}).get('median_dollar_volume_20d', {}),
                   'paper_accounts': accounts},
        'strategy_assessment': strategy_assessment,
        'stages': {role: {'request': stage_requests.get(role), 'output': stage_outputs.get(role)}
                   for role in sorted(set(stage_requests) | set(stage_outputs))},
        'outcome': {k: result.get(k) for k in ('status', 'decision', 'critic', 'results', 'desk_results', 'reason')},
    }
    return _plain(capsule)


def digest(capsule) -> str:
    return hashlib.sha256(canonical(capsule).encode()).hexdigest()


def write(db, capsule) -> str:
    text = canonical(capsule)
    for key in FORBIDDEN_KEYS:
        if f'"{key}"' in text:
            raise ValueError('CAPSULE_PRIVACY_VIOLATION')
    h = hashlib.sha256(text.encode()).hexdigest()
    db.execute('CREATE TABLE IF NOT EXISTS decision_capsules (hash TEXT PRIMARY KEY, cycle_id TEXT, '
               'created_at TEXT, payload TEXT NOT NULL)')
    db.execute('INSERT OR IGNORE INTO decision_capsules VALUES (?,?,?,?)',
               (h, capsule.get('cycle_id'), capsule.get('observed_at'), text))
    return h


def load(db, h):
    row = db.execute('SELECT payload FROM decision_capsules WHERE hash=?', (h,)).fetchone()
    if row is None:
        raise ValueError('CAPSULE_NOT_FOUND')
    if hashlib.sha256(row[0].encode()).hexdigest() != h:
        raise ValueError('CAPSULE_HASH_MISMATCH')
    return json.loads(row[0])


def replay_strategy(capsule, universe=None):
    """Deterministically recompute strategy signals from the capsule's own closes."""
    observed = datetime.fromisoformat(capsule['observed_at'])
    from zoneinfo import ZoneInfo
    day = observed.astimezone(ZoneInfo('America/New_York')).date()
    closes = capsule['inputs']['session_closes']
    universe = ETF_UNIVERSE & set(closes) if universe is None else universe
    recomputed = _plain(evaluate_daily_signals(closes, universe, day))
    recorded = capsule['strategy_assessment']
    return {'identical': canonical(recomputed.get('signals')) == canonical((recorded or {}).get('signals')),
            'recomputed_signals': recomputed.get('signals'), 'recorded_signals': (recorded or {}).get('signals')}
