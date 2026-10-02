"""Rulers the Firm cannot trade, change or choose after the fact. No alpha is computed in BUILD_OBSERVE."""
from __future__ import annotations

from . import features, sessions
from .store import canonical, now_utc

VTI = 'VTI_100'
RULER_70_30 = 'FIXED_70_30'
DATA_SOURCE_PENDING = 'DATA_SOURCE_PENDING'
# (id, name, status, definition, defined_by, note, implementation_status)
DEFINITIONS = (
    (VTI, '100% VTI', 'DEFINED', {'weights': {'VTI': '1.00'}, 'rebalancing': 'none', 'basis': 'price return; dividends not yet included'},
     'firm_lab_foundation', 'Fixed 100% equity ruler. Price return only until a total-return source exists.', 'PRICE_RETURN_ONLY'),
    (RULER_70_30, '70% VTI + 30% 3-month U.S. Treasury-bill total return', 'DEFINED',
     {'weights': {'VTI': '0.70', 'US_TREASURY_BILL_3M_TOTAL_RETURN': '0.30'}, 'allocation': 'fixed',
      'rules': ['the Firm cannot trade it', 'the Firm cannot dynamically modify it', 'no tactical reallocation',
                'no optimization after seeing Firm results'],
      'rebalancing': 'NOT_SPECIFIED_BY_OPERATOR', 'treasury_bill_series': None},
     'operator instruction, 2026-10-01',
     'Lower-risk passive ruler, defined by the operator. No clean 3-month Treasury-bill total-return series is connected, so nothing is '
     'computed and no other asset stands in for it. The rebalancing convention has not been specified.', DATA_SOURCE_PENDING),
)


def seed(store, now=None):
    at = (now or now_utc()).isoformat()
    with store.connect() as db:
        for bench_id, name, status, definition, defined_by, note, implementation in DEFINITIONS:
            db.execute('INSERT OR IGNORE INTO benchmark_definitions (benchmark_id, name, status, definition_json, defined_at, defined_by, note, '
                       'implementation_status) VALUES (?,?,?,?,?,?,?,?)', (bench_id, name, status, canonical(definition), at, defined_by, note, implementation))


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
        return [{'benchmark_id': b, 'name': n, 'status': s, 'definition_json': d, 'defined_at': a, 'note': note, 'implementation_status': impl,
                 'observations': db.execute('SELECT COUNT(*) FROM benchmark_observations WHERE benchmark_id=?', (b,)).fetchone()[0],
                 'latest': db.execute('SELECT exchange_session_date, value FROM benchmark_observations WHERE benchmark_id=? '
                                      'ORDER BY exchange_session_date DESC LIMIT 1', (b,)).fetchone()}
                for b, n, s, d, a, _, note, impl in db.execute('SELECT benchmark_id, name, status, definition_json, defined_at, defined_by, note, '
                                                               'implementation_status FROM benchmark_definitions ORDER BY rowid').fetchall()]
