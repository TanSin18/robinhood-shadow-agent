"""Rulers the Firm cannot trade, change or choose after the fact. No alpha is computed in BUILD_OBSERVE."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path

from . import capabilities, features, sessions, total_return, treasury, usage
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
# Total return (Checkpoint 4). The price-return ruler above is kept exactly as it is and is called the legacy ruler; the
# total-return series are separate benchmarks with their own observations. Nothing stored earlier is overwritten.
VTI_TR = 'VTI_TOTAL_RETURN'
RULER_70_30_TR = 'FIXED_70_30_TOTAL_RETURN'
LABELS = {RULER_70_30: 'LEGACY_PRICE_RETURN_RULER', RULER_70_30_TR: 'TOTAL_RETURN_RULER'}
KIND_VTI_PRICE_INDEX = 'vti_price_return_index'
KIND_VTI_TR_INDEX = 'vti_total_return_index'
KIND_RULER_TR = 'index_70_30_vti_total_return'
TR_STATUS_KEY = 'vti_total_return_status'
TR_IMPLEMENTATION = 'EX_DATE_REINVESTMENT_V1'
TR_METHODOLOGY = {'document': 'docs/firm_lab/vti_total_return_methodology.md', 'version': 1}
DISTRIBUTION_ISSUER = 'Vanguard'                       # the fund's own issuer: the primary source of its distributions
MAX_EX_DATE_GAP_DAYS = 110                             # a quarterly payer: a longer hole means a distribution is missing
REINVEST_PRICE_TOLERANCE = Decimal('0.01')             # the issuer's reinvestment price against the stored close on the ex-date
VALIDATION_FAILED = 'VALIDATION_FAILED'
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
    (VTI_TR, 'VTI total return', 'DEFINED',
     {'weights': {'VTI': '1.00'}, 'rebalancing': 'none',
      'basis': 'total return: each cash distribution is reinvested at the close of its ex-dividend session',
      'price_series': 'stored completed-session closes (split-adjusted by their provider, not dividend-adjusted)',
      'distributions': {'source': 'the fund issuer’s published distributions (Vanguard)', 'known_at': 'when Firm Lab fetched the record; the '
                        'source gives no declaration time', 'validation': 'quarterly cadence; ex-date is a stored session; the issuer’s '
                        'reinvestment price agrees with the stored close on the ex-date; any independent source stored must agree exactly'},
      'rules': ['no vendor adjusted close and no vendor total-return index is used', 'a distribution is used only once it is stored and validated',
                'a data gap stops the series and nothing is filled in', 'a stored observation is never overwritten'],
      'methodology': TR_METHODOLOGY['document'], 'methodology_version': TR_METHODOLOGY['version']},
     'operator instruction, Checkpoint 4 (2026-10-02)',
     'VTI with cash distributions reinvested, beside (not instead of) the price-return series. A ruler only.', TR_IMPLEMENTATION),
    (RULER_70_30_TR, '70% VTI total return + 30% 3-month U.S. Treasury-bill accrual index', 'DEFINED',
     {'label': LABELS[RULER_70_30_TR], 'weights': {'VTI_TOTAL_RETURN': '0.70', 'US_TREASURY_BILL_3M_TOTAL_RETURN': '0.30'}, 'allocation': 'fixed',
      'rebalancing': {'frequency': 'monthly', 'on': 'the first NYSE trading session of each calendar month', 'calendar': 'XNYS'},
      'rules': ['fixed weights', 'no tactical changes', 'the Firm cannot trade, optimize or alter this benchmark',
                'no retroactive asset substitution', 'a data gap stops the series and nothing is filled in'],
      'treasury_bill_series': {'methodology': TREASURY_METHODOLOGY['document'], 'methodology_version': TREASURY_METHODOLOGY['version'],
                               'methodology_sha256': TREASURY_METHODOLOGY['sha256'], 'note': 'the frozen bill index, unchanged'},
      'vti_leg': 'total return: ' + TR_METHODOLOGY['document']},
     'operator instruction, Checkpoint 4 (2026-10-02)',
     'The 70/30 ruler with dividends included on the VTI side. The earlier price-return ruler is kept, unchanged, as the legacy ruler. '
     'A ruler only: nothing trades it and nothing is chosen from it.', TR_IMPLEMENTATION),
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


def total_return_status(store) -> dict:
    """What the last total-return computation recorded, or an empty dict when none has run."""
    text = store.meta(TR_STATUS_KEY)
    return json.loads(text) if text else {}


def _stored_distributions(store, instrument, as_of):
    """Stored cash distributions of the instrument, by source, read for BENCHMARK use only (firm_lab.usage): an after-the-fact
    ruler may use a distribution Firm Lab learned later; a feature may not. Returns (issuer records, independent records,
    conflicts, details by ex-date, split rows)."""
    held = usage.distribution_rows(store, instrument, purpose=usage.BENCHMARK, as_of=as_of)
    rows = [(r['provider'], r['effective_date'], r['value'], r['currency'], r['known_at'], r['provider_action'], r.get('source_record'),
             r.get('record_date'), r.get('pay_date'), usage.is_benchmark_only(r)) for r in held]
    with store.connect() as db:
        splits = db.execute("SELECT provider, effective_date, value FROM corporate_action_observations WHERE instrument=? AND action_type='split' "
                            'ORDER BY id', (instrument,)).fetchall()
    seen, conflicts, issuer, independent, detail = {}, [], [], [], {}
    for provider, ex_date, value, currency, known, kind, source_record, record_date, pay_date, restricted in rows:
        key = (provider, ex_date, kind)
        if key in seen:
            if seen[key] != (Decimal(value), currency):     # the same source published two different amounts for one distribution
                conflicts.append(f'{provider} {ex_date}: {seen[key][0]} and {value}')
            elif provider == DISTRIBUTION_ISSUER:            # same amount: the first record's known-at stands; the newest details are the ones checked
                detail[date.fromisoformat(ex_date)] = {'source_record': json.loads(source_record) if source_record else {},
                                                       'record_date': record_date, 'pay_date': pay_date, 'benchmark_only': restricted}
            continue
        seen[key] = (Decimal(value), currency)
        item = total_return.Distribution(date.fromisoformat(ex_date), Decimal(value), str(currency or ''),
                                         datetime.fromisoformat(known.replace('Z', '+00:00')), 'cash_dividend')
        (issuer if provider == DISTRIBUTION_ISSUER else independent).append(item)
        if provider == DISTRIBUTION_ISSUER:
            detail[item.ex_date] = {'source_record': json.loads(source_record) if source_record else {}, 'record_date': record_date,
                                    'pay_date': pay_date, 'benchmark_only': restricted}
    return issuer, independent, conflicts, detail, splits


def compute_total_return(store, now=None, *, root=None) -> dict:
    """Validates the stored VTI distributions, then computes and stores, one observation per NYSE session:

      * the VTI price-return index and, separately, the VTI total-return index (benchmark VTI_TOTAL_RETURN);
      * the 70/30 total-return ruler (benchmark FIXED_70_30_TOTAL_RETURN), using the frozen bill index unchanged.

    Nothing is stored unless the distributions pass validation. The legacy price-return ruler and the stored closes are
    not touched. A ruler only: nothing reads these values to choose or trade."""
    require_frozen_methodology(root)                          # the bill leg is the frozen index or nothing
    at = now or now_utc()
    history = store.feature_history('VTI', 'close', features.FEATURE_VERSION, known_by=at.isoformat())
    closes = [(date.fromisoformat(h['exchange_session_date']), Decimal(h['value'])) for h in history]
    close_known = {date.fromisoformat(h['exchange_session_date']): datetime.fromisoformat(h['known_at'].replace('Z', '+00:00')) for h in history}
    report = {'computed_at': at.isoformat(), 'implementation': TR_IMPLEMENTATION, 'methodology': TR_METHODOLOGY['document'], 'sessions': len(closes),
              'distribution_use': usage.BENCHMARK_ONLY, 'use_rule': usage.RESTRICTION,
              'status': VALIDATION_FAILED, 'issues': [], 'notes': [], 'stored': 0, 'unchanged': 0, 'gap_date': None, 'gap_reason': ''}

    def finish():
        store.set_meta(TR_STATUS_KEY, canonical(report), at)
        store.event('TOTAL_RETURN_COMPUTED', {k: report.get(k) for k in ('status', 'ruler_status', 'issues', 'gap_date', 'gap_reason', 'ruler_gap_reason', 'stored', 'unchanged',
                                                                         'base_date', 'last_session', 'distributions_applied')}, at)
        capabilities.confirm_provider_data(store, at)
        return report

    if not closes:
        report['issues'].append({'code': 'NO_SESSIONS', 'detail': 'no completed VTI session is stored'})
        return finish()
    base, last = closes[0][0], closes[-1][0]
    issuer, independent, conflicts, detail, splits = _stored_distributions(store, 'VTI', at)
    known = [d for d in issuer if d.known_at <= at]
    window = [d for d in known if base < d.ex_date <= last]
    issues = [{'code': 'CONFLICTING_DISTRIBUTION_RECORDS', 'detail': text} for text in conflicts]
    if not window:
        issues.append({'code': total_return.NO_PRIMARY_RECORDS, 'detail': f'no issuer distribution is stored with an ex-date after {base} and up to {last}'})
    marks = [base] + sorted(d.ex_date for d in window) + [last]
    for a, b in zip(marks, marks[1:]):
        if (b - a).days > MAX_EX_DATE_GAP_DAYS:
            issues.append({'code': total_return.CADENCE_GAP, 'detail': f'no ex-date between {a} and {b} ({(b - a).days} days); the fund pays quarterly'})
    by_day = dict(closes)
    checked = []
    for d in sorted(window, key=lambda x: x.ex_date):
        stated = (detail.get(d.ex_date) or {}).get('source_record', {}).get('reinvestPrice')
        close = by_day.get(d.ex_date)
        entry = {'ex_date': d.ex_date.isoformat(), 'amount': str(d.amount), 'currency': d.currency, 'known_at': d.known_at.isoformat(),
                 'record_date': (detail.get(d.ex_date) or {}).get('record_date'), 'pay_date': (detail.get(d.ex_date) or {}).get('pay_date'),
                 'benchmark_only': bool((detail.get(d.ex_date) or {}).get('benchmark_only')),
                 'announcement_timestamp': 'UNAVAILABLE' if (detail.get(d.ex_date) or {}).get('benchmark_only') else 'stored',
                 'issuer_reinvestment_price': stated, 'stored_close_on_ex_date': str(close) if close is not None else None}
        checked.append(entry)
        if close is None:
            issues.append({'code': total_return.EX_DATE_NOT_A_SESSION, 'detail': f'{d.ex_date} is not a stored VTI session'})
            continue
        try:
            ratio = Decimal(str(stated)) / close
        except (ArithmeticError, TypeError, ValueError):
            issues.append({'code': 'REINVESTMENT_PRICE_MISSING', 'detail': f'{d.ex_date}: the issuer record carries no usable reinvestment price'})
            continue
        entry['reinvestment_price_over_close'] = str(treasury.q6(ratio))
        if abs(ratio - 1) > REINVEST_PRICE_TOLERANCE:        # a wrong date, or a share basis that differs from the stored closes (a split)
            issues.append({'code': 'REINVESTMENT_PRICE_MISMATCH', 'detail': f'{d.ex_date}: issuer reinvestment price {stated}, stored close {close}'})
    if independent:
        for code, text in total_return.compare_sources(window, [d for d in independent if d.known_at <= at], base + (date.resolution), last,
                                                       max_gap_days=10 ** 6):
            issues.append({'code': code, 'detail': text})
        report['independent_confirmation'] = 'COMPARED'
    else:
        report['independent_confirmation'] = 'NONE_STORED'
        report['notes'].append('No independent distribution source is stored. The amounts rest on the issuer’s own publication; the dates and the '
                               'share basis are cross-checked against the stored closes through the issuer’s reinvestment price.')
    if splits:
        issues.append({'code': 'SPLIT_RECORD_NEEDS_A_RULE', 'detail': f'{len(splits)} split record(s) are stored for VTI; no split handling is approved'})
    else:
        report['notes'].append('No split record is stored and none is assumed away: a split between a distribution and the stored closes would '
                               'show as a reinvestment-price mismatch, and stops the series.')
    report.update(base_date=base.isoformat(), last_session=last.isoformat(), distributions_checked=checked, issuer_records=len(issuer),
                  distributions_before_window=sorted(d.ex_date.isoformat() for d in known if d.ex_date <= base), issues=issues)
    if issues:
        return finish()                                       # nothing is computed from distributions that did not validate

    result = total_return.total_return_index(closes, window, (), as_of=at)
    with store.connect() as db:
        columns = [r[1] for r in db.execute('PRAGMA table_info(treasury_auction_observations)')]
        rows = [dict(zip(columns, r)) for r in db.execute('SELECT * FROM treasury_auction_observations ORDER BY id')]
    bills, unusable = treasury.bills_from_rows(rows, at)
    index = treasury.accrual_index(bills, unusable, base, last)
    levels = [(day, result.total_return[day]) for day, _ in closes if day in result.total_return]
    ruler = treasury.fixed_70_30(levels, index.values)
    close_time = lambda day: datetime.combine(day, time(16, 0), sessions.ET).astimezone(timezone.utc)
    stamp = lambda day, *extra: max([x for x in (close_time(day), close_known.get(day), *extra) if x]).isoformat()
    source_vti = (f'firm_lab.total_return {TR_IMPLEMENTATION}; base {base.isoformat()} = 100 (development base); distributions from '
                  f'{DISTRIBUTION_ISSUER}, reinvested at the ex-date close')
    source_ruler = (f'{source_vti}; bill leg: firm_lab.treasury construction A, methodology sha256 {TREASURY_METHODOLOGY["sha256"][:16]}')
    wanted = []
    for day, _ in closes:
        if day in result.price_return:
            wanted.append((VTI_TR, day, KIND_VTI_PRICE_INDEX, str(treasury.q6(result.price_return[day])), stamp(day), source_vti))
        if day in result.total_return:
            wanted.append((VTI_TR, day, KIND_VTI_TR_INDEX, str(treasury.q6(result.total_return[day])), stamp(day, result.known_at.get(day)), source_vti))
        if day in ruler.values:
            wanted.append((RULER_70_30_TR, day, KIND_RULER_TR, str(treasury.q6(ruler.values[day])),
                           stamp(day, result.known_at.get(day), index.known_at.get(day)), source_ruler))
    with store.connect() as db:
        for bench, day, kind, value, _, source in wanted:      # nothing already stored may change
            old = db.execute('SELECT value FROM benchmark_observations WHERE benchmark_id=? AND exchange_session_date=? AND kind=? AND source=?',
                             (bench, day.isoformat(), kind, source)).fetchone()
            if old is not None and old[0] != value:
                raise FirmLabError(f'BENCHMARK_OBSERVATION_CONFLICT:{kind}:{day}: stored {old[0]}, computed {value}. Nothing was changed.')
        for bench, day, kind, value, known_at, source in wanted:
            added = db.execute('INSERT OR IGNORE INTO benchmark_observations (benchmark_id, exchange_session_date, value, kind, source, known_at, '
                               'ingested_at) VALUES (?,?,?,?,?,?,?)', (bench, day.isoformat(), value, kind, source, known_at, at.isoformat())).rowcount
            report['stored'] += added
            report['unchanged'] += 1 - added
    ruler_gap = result if result.status != total_return.OK else index if index.status != treasury.OK else ruler
    last_of = lambda values: (str(treasury.q6(values[max(values)])), max(values).isoformat()) if values else (None, None)
    report.update(status=result.status, gap_date=result.gap_date.isoformat() if result.gap_date else None, gap_reason=result.gap_reason,
                  ruler_status=ruler_gap.status, ruler_gap_date=ruler_gap.gap_date.isoformat() if ruler_gap.gap_date else None,
                  ruler_gap_reason=ruler_gap.gap_reason,
                  distributions_applied=[{'ex_date': d.isoformat(), 'amount': str(a)} for d, a, _ in result.applied],
                  rebalances=len(ruler.rebalances), last_price_return=last_of(result.price_return)[0],
                  last_total_return=last_of(result.total_return)[0], last_total_return_date=last_of(result.total_return)[1],
                  last_ruler=last_of(ruler.values)[0], last_ruler_date=last_of(ruler.values)[1],
                  observations={'price_return': len(result.price_return), 'total_return': len(result.total_return), 'ruler': len(ruler.values)})
    return finish()


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
