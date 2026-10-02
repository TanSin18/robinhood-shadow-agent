"""Rulers the Firm cannot trade, change or choose after the fact. No alpha is computed in BUILD_OBSERVE."""
from __future__ import annotations

from . import features, sessions
from .store import canonical, now_utc

VTI = 'VTI_100'
RULER_70_30 = 'FIXED_70_30'
DEFINITIONS = (
    (VTI, '100% VTI', 'DEFINED', {'weights': {'VTI': '1.00'}, 'rebalancing': 'none', 'basis': 'price return; dividends not yet included'},
     'Fixed ruler. Price return only until a total-return source exists.'),
    (RULER_70_30, 'Fixed 70/30 allocation', 'DEFINITION_PENDING', None,
     'The operator has not chosen the 30% sleeve. Nothing is assumed and nothing is computed until they do.'),
)


def seed(store, now=None):
    at = (now or now_utc()).isoformat()
    with store.connect() as db:
        for bench_id, name, status, definition, note in DEFINITIONS:
            db.execute('INSERT OR IGNORE INTO benchmark_definitions VALUES (?,?,?,?,?,?,?)',
                       (bench_id, name, status, canonical(definition) if definition else None, at if definition else None,
                        'firm_lab_foundation' if definition else None, note))


def record_vti(store, *, known_at, now=None):
    """Copies VTI's completed-session closes from the feature store into the ruler's own observations."""
    known, at = sessions.utc_iso(known_at), (now or now_utc()).isoformat()
    history = store.feature_history('VTI', 'close', features.FEATURE_VERSION, known_by=known)
    added = 0
    with store.connect() as db:
        for h in history:
            added += db.execute('INSERT OR IGNORE INTO benchmark_observations (benchmark_id, exchange_session_date, value, kind, source, known_at, '
                                'ingested_at) VALUES (?,?,?,?,?,?,?)', (VTI, h['exchange_session_date'], h['value'], 'close_price_return_basis',
                                                                        h['source'], h['known_at'], at)).rowcount
    return added


def definitions(store):
    with store.connect() as db:
        return [{'benchmark_id': b, 'name': n, 'status': s, 'definition_json': d, 'defined_at': a, 'note': note,
                 'observations': db.execute('SELECT COUNT(*) FROM benchmark_observations WHERE benchmark_id=?', (b,)).fetchone()[0],
                 'latest': db.execute('SELECT exchange_session_date, value FROM benchmark_observations WHERE benchmark_id=? '
                                      'ORDER BY exchange_session_date DESC LIMIT 1', (b,)).fetchone()}
                for b, n, s, d, a, _, note in db.execute('SELECT * FROM benchmark_definitions ORDER BY rowid').fetchall()]
