"""Rulers the Firm cannot trade, change or choose after the fact. No alpha is computed in BUILD_OBSERVE."""
from __future__ import annotations

import json

from . import capabilities, features, sessions
from .errors import FirmLabError
from .store import canonical, now_utc

VTI = 'VTI_100'
RULER_70_30 = 'FIXED_70_30'
DATA_SOURCE_PENDING = 'DATA_SOURCE_PENDING'
TREASURY_CAPABILITY = 'treasury_total_return'
# The construction of the Treasury-bill leg is written down first, reviewed by the operator, then frozen. Until the status
# here is APPROVED_AND_FROZEN nothing is computed. It is changed only by a deliberate, dated operator approval.
METHODOLOGY_FROZEN = 'APPROVED_AND_FROZEN'
TREASURY_METHODOLOGY = {'document': 'docs/firm_lab/treasury_bill_total_return_methodology.md', 'status': 'DRAFT_FOR_OPERATOR_REVIEW',
                        'computation': 'NOT_COMPUTED'}
# (id, name, status, definition, defined_by, note, implementation_status)
DEFINITIONS = (
    (VTI, '100% VTI', 'DEFINED', {'weights': {'VTI': '1.00'}, 'rebalancing': 'none', 'basis': 'price return; dividends not yet included'},
     'firm_lab_foundation', 'Fixed 100% equity ruler. Price return only until a total-return source exists.', 'PRICE_RETURN_ONLY'),
    (RULER_70_30, '70% VTI + 30% 3-month U.S. Treasury-bill total return', 'DEFINED',
     {'weights': {'VTI': '0.70', 'US_TREASURY_BILL_3M_TOTAL_RETURN': '0.30'}, 'allocation': 'fixed',
      'rebalancing': {'frequency': 'monthly', 'on': 'the first NYSE trading session of each calendar month', 'calendar': 'XNYS'},
      'rules': ['fixed weights', 'no tactical changes', 'the Firm cannot trade, optimize or alter this benchmark',
                'no retroactive asset substitution',
                'while no clean Treasury-bill total-return data exists, the computation is unavailable'],
      'treasury_bill_series': None},
     'operator instruction, 2026-10-01',
     'Lower-risk passive ruler, defined by the operator. No clean 3-month Treasury-bill total-return source is chosen, so nothing is '
     'computed and no other asset stands in for it.', DATA_SOURCE_PENDING),
)


def seed(store, now=None):
    """Writes the definitions. A definition that differs from the stored one replaces it only while the ruler has no
    observations (and the change is recorded); once observations exist the definition is locked."""
    at = (now or now_utc()).isoformat()
    with store.connect() as db:
        for bench_id, name, status, definition, defined_by, note, implementation in DEFINITIONS:
            text = canonical(definition)
            row = db.execute('SELECT name, definition_json, implementation_status FROM benchmark_definitions WHERE benchmark_id=?', (bench_id,)).fetchone()
            if row is None:
                db.execute('INSERT INTO benchmark_definitions (benchmark_id, name, status, definition_json, defined_at, defined_by, note, '
                           'implementation_status) VALUES (?,?,?,?,?,?,?,?)', (bench_id, name, status, text, at, defined_by, note, implementation))
                continue
            if (row[0], row[1], row[2]) == (name, text, implementation):
                continue
            if db.execute('SELECT COUNT(*) FROM benchmark_observations WHERE benchmark_id=?', (bench_id,)).fetchone()[0]:
                raise FirmLabError(f'BENCHMARK_DEFINITION_LOCKED:{bench_id}: observations exist; a ruler is never changed after the fact')
            db.execute('UPDATE benchmark_definitions SET name=?, status=?, definition_json=?, defined_at=?, defined_by=?, note=?, '
                       'implementation_status=? WHERE benchmark_id=?', (name, status, text, at, defined_by, note, implementation, bench_id))
            db.execute('INSERT INTO events(at, kind, payload_json) VALUES (?,?,?)',
                       (at, 'BENCHMARK_DEFINITION_CHANGED', canonical({'benchmark_id': bench_id, 'defined_by': defined_by,
                                                                       'before': {'name': row[0], 'definition': json.loads(row[1]) if row[1] else None,
                                                                                  'implementation_status': row[2]},
                                                                       'after': {'name': name, 'definition': definition,
                                                                                 'implementation_status': implementation}})))


def compute_fixed_70_30(store, *_, **__):
    """The 70/30 ruler cannot be computed until a 3-month Treasury-bill total-return source is AVAILABLE. Until then this
    raises: no yield is treated as a return and no other asset is substituted."""
    capabilities.require(store, TREASURY_CAPABILITY)
    if TREASURY_METHODOLOGY['status'] != METHODOLOGY_FROZEN:
        raise FirmLabError('TREASURY_METHODOLOGY_NOT_FROZEN: the construction methodology must be approved and frozen first')
    raise FirmLabError('FIXED_70_30_COMPUTATION_NOT_BUILT: a Treasury-bill total-return source must be chosen and validated first')


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
