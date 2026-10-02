"""Rulers the Firm cannot trade, change or choose after the fact. No alpha is computed in BUILD_OBSERVE."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path

from . import capabilities, features, sessions, treasury
from .errors import FirmLabError
from .store import canonical, now_utc

VTI = 'VTI_100'
RULER_70_30 = 'FIXED_70_30'
DATA_SOURCE_PENDING = 'DATA_SOURCE_PENDING'
TREASURY_CAPABILITY = 'treasury_total_return'
# The construction of the Treasury-bill leg. The operator approved construction A and froze this exact file on 2026-10-02
# (docs/firm_lab/treasury_bill_total_return_methodology.APPROVAL.md). The file is never edited again: a change is a new
# methodology version with its own file, hash and approval. Nothing is computed unless the file on disk has this hash.
METHODOLOGY_FROZEN = 'APPROVED_AND_FROZEN'
TREASURY_METHODOLOGY = {
    'document': 'docs/firm_lab/treasury_bill_total_return_methodology.md',
    'version': 1,
    'status': METHODOLOGY_FROZEN,
    'sha256': 'c954c81b330aa3d43d97f4e19184321cf9f1c67fb974458f82443185d5fe40c4',
    'approved_at': '2026-10-02T10:31:00-04:00',
    'approved_by': 'operator instruction, 2026-10-02 10:31 ET',
    'construction': 'A: bought at auction, held to maturity, rolled; straight-line accrual between',
}
IMPLEMENTATION = 'AUCTION_ACCRUAL_INDEX_V1'
KIND_BILL_INDEX = 'tbill_13w_accrual_index'
KIND_RULER = 'index_70_30_vti_price_return_basis'
STATUS_KEY = 'treasury_index_status'
# (id, name, status, definition, defined_by, note, implementation_status)
DEFINITIONS = (
    (VTI, '100% VTI', 'DEFINED', {'weights': {'VTI': '1.00'}, 'rebalancing': 'none', 'basis': 'price return; dividends not yet included'},
     'firm_lab_foundation', 'Fixed 100% equity ruler. Price return only until a total-return source exists.', 'PRICE_RETURN_ONLY'),
    (RULER_70_30, '70% VTI + 30% 3-month U.S. Treasury-bill total return', 'DEFINED',
     {'weights': {'VTI': '0.70', 'US_TREASURY_BILL_3M_TOTAL_RETURN': '0.30'}, 'allocation': 'fixed',
      'rebalancing': {'frequency': 'monthly', 'on': 'the first NYSE trading session of each calendar month', 'calendar': 'XNYS'},
      'rules': ['fixed weights', 'no tactical changes', 'the Firm cannot trade, optimize or alter this benchmark',
                'no retroactive asset substitution',
                'computed only under the frozen methodology; a data gap stops the series and nothing is filled in'],
      'treasury_bill_series': {'source': 'U.S. Treasury Fiscal Data, Treasury Securities Auctions Data (13-week bills)',
                               'construction': TREASURY_METHODOLOGY['construction'], 'methodology': TREASURY_METHODOLOGY['document'],
                               'methodology_version': TREASURY_METHODOLOGY['version'], 'methodology_sha256': TREASURY_METHODOLOGY['sha256'],
                               'approved_at': TREASURY_METHODOLOGY['approved_at'],
                               'valuation': 'accrual between auction and maturity; not a market value'},
      'vti_leg': 'price return; dividends are not included until a validated dividend source exists'},
     'operator instruction, 2026-10-01; Treasury-bill methodology approved 2026-10-02',
     'Lower-risk passive ruler, defined by the operator. The Treasury-bill leg is an accrual index built from official auction records under the '
     'frozen methodology. The VTI leg is price return. A ruler only: nothing trades it and nothing is chosen from it.', IMPLEMENTATION),
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


def methodology_path(root=None) -> Path:
    return Path(root) / TREASURY_METHODOLOGY['document'] if root else Path(__file__).resolve().parents[1] / TREASURY_METHODOLOGY['document']


def require_frozen_methodology(root=None) -> str:
    """Refuses unless the methodology is approved and frozen and the file on disk is byte-for-byte the approved one."""
    if TREASURY_METHODOLOGY['status'] != METHODOLOGY_FROZEN:
        raise FirmLabError('TREASURY_METHODOLOGY_NOT_FROZEN: the construction methodology must be approved and frozen first')
    path = methodology_path(root)
    if not path.is_file():
        raise FirmLabError('TREASURY_METHODOLOGY_FILE_MISSING: the frozen methodology file is not present; nothing is computed without it')
    found = hashlib.sha256(path.read_bytes()).hexdigest()
    if found != TREASURY_METHODOLOGY['sha256']:
        raise FirmLabError(f'TREASURY_METHODOLOGY_HASH_MISMATCH: the file on disk ({found[:12]}…) is not the approved version '
                           f'({TREASURY_METHODOLOGY["sha256"][:12]}…). A change needs a new methodology version.')
    return found


def index_status(store) -> dict:
    """What the last computation recorded, or an empty dict when none has run."""
    text = store.meta(STATUS_KEY)
    return json.loads(text) if text else {}


def compute_fixed_70_30(store, now=None, *, root=None) -> dict:
    """Computes the 13-week bill accrual index and the monthly-rebalanced 70/30 ruler from stored auction records and stored
    VTI closes, and stores one observation per NYSE session. A ruler only: nothing reads these values to choose or trade.

    Refuses without the frozen methodology file. Stops at the first data gap and stores nothing from that date on. An
    observation that was already stored with a different value is never overwritten: the computation stops instead."""
    require_frozen_methodology(root)
    at = now or now_utc()
    with store.connect() as db:
        columns = [r[1] for r in db.execute('PRAGMA table_info(treasury_auction_observations)')]
        rows = [dict(zip(columns, r)) for r in db.execute('SELECT * FROM treasury_auction_observations ORDER BY id')]
    history = store.feature_history('VTI', 'close', features.FEATURE_VERSION, known_by=at.isoformat())
    closes = [(date.fromisoformat(h['exchange_session_date']), Decimal(h['value'])) for h in history]
    close_known = {date.fromisoformat(h['exchange_session_date']): h['known_at'] for h in history}
    report = {'computed_at': at.isoformat(), 'methodology_sha256': TREASURY_METHODOLOGY['sha256'], 'auction_rows': len(rows), 'sessions': len(closes),
              'status': treasury.DATA_GAP, 'gap_date': None, 'gap_reason': '', 'stored': 0, 'unchanged': 0}
    if not closes:
        report['gap_reason'] = 'no completed VTI session is stored'
        store.set_meta(STATUS_KEY, canonical(report), at)
        return report
    base, last = closes[0][0], closes[-1][0]
    bills, unusable = treasury.bills_from_rows(rows, at)
    index = treasury.accrual_index(bills, unusable, base, last)
    ruler = treasury.fixed_70_30(closes, index.values)
    source = (f'firm_lab.treasury construction A; base {base.isoformat()} = 100 (development base, rebased when a trial is registered); '
              f'methodology sha256 {TREASURY_METHODOLOGY["sha256"][:16]}')
    stamp = lambda day, extra=None: max([x for x in (index.known_at.get(day), extra,
                                                     datetime.combine(day, time(16, 0), sessions.ET).astimezone(timezone.utc)) if x]).isoformat()
    wanted = []
    for day, _ in closes:
        if day in index.values:
            wanted.append((day, KIND_BILL_INDEX, str(treasury.q6(index.values[day])), stamp(day)))
        if day in ruler.values:
            wanted.append((day, KIND_RULER, str(treasury.q6(ruler.values[day])),
                           stamp(day, datetime.fromisoformat(close_known[day].replace('Z', '+00:00')))))
    with store.connect() as db:
        for day, kind, value, _ in wanted:                    # nothing already stored may change
            old = db.execute('SELECT value FROM benchmark_observations WHERE benchmark_id=? AND exchange_session_date=? AND kind=? AND source=?',
                             (RULER_70_30, day.isoformat(), kind, source)).fetchone()
            if old is not None and old[0] != value:
                raise FirmLabError(f'BENCHMARK_OBSERVATION_CONFLICT:{kind}:{day}: stored {old[0]}, computed {value}. Nothing was changed.')
        for day, kind, value, known in wanted:
            added = db.execute('INSERT OR IGNORE INTO benchmark_observations (benchmark_id, exchange_session_date, value, kind, source, known_at, '
                               'ingested_at) VALUES (?,?,?,?,?,?,?)', (RULER_70_30, day.isoformat(), value, kind, source, known, at.isoformat())).rowcount
            report['stored'] += added
            report['unchanged'] += 1 - added
    gap = index if index.status != treasury.OK else ruler
    report.update(status=gap.status, gap_date=gap.gap_date.isoformat() if gap.gap_date else None, gap_reason=gap.gap_reason,
                  base_date=base.isoformat(), last_session=last.isoformat(), bills_stored=len(bills), unusable_bills=len(unusable),
                  bills_used=[{'date': d.isoformat(), 'cusip': c, 'price': str(treasury.q6(p))} for d, c, p in index.rolls],
                  uninvested_days=[d.isoformat() for d in index.uninvested_days],
                  rebalances=[d.isoformat() for d in ruler.rebalances],
                  last_bill_index=str(treasury.q6(index.values[max(index.values)])) if index.values else None,
                  last_bill_index_date=max(index.values).isoformat() if index.values else None,
                  last_ruler=str(treasury.q6(ruler.values[max(ruler.values)])) if ruler.values else None,
                  last_ruler_date=max(ruler.values).isoformat() if ruler.values else None,
                  vti_leg='price return; dividends not included')
    store.set_meta(STATUS_KEY, canonical(report), at)
    store.event('BENCHMARK_COMPUTED', {k: report[k] for k in ('status', 'gap_date', 'gap_reason', 'stored', 'unchanged', 'base_date', 'last_session',
                                                              'methodology_sha256')}, at)
    capabilities.confirm_provider_data(store, at)
    return report


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
