"""Baseline daily features, point in time. Exactly enough to reproduce Control A's rule and no more:
completed-session close, completed-session count, 200-session average, above-average flag, 126-session momentum.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from . import sessions
from .store import canonical, now_utc

D = Decimal
FEATURE_VERSION = 'baseline-v1'
TREND_WINDOW = 200
MOMENTUM_LOOKBACK = 126
DERIVED = ('completed_session_count', 'ma200', 'above_ma200', 'momentum_126d')
RECONSTRUCTED = ('reconstructed: Control A stores only the New York date label of the provider’s 00:00 UTC bar start; '
                 'the session date is that label plus one day')


def _price(value):
    try:
        v = D(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return v if v.is_finite() and v > 0 else None


def _insert_closes(store, rows, now=None):
    """rows: dicts for add_feature. One transaction; append-only; unchanged values are not repeated."""
    out = {'INSERTED': 0, 'REVISED': 0, 'UNCHANGED': 0}
    at = (now or now_utc()).isoformat()
    with store.connect() as db:
        latest = {}
        instruments = sorted({r['instrument'] for r in rows})
        for inst in instruments:
            for session, value, revision, source in db.execute(
                    'SELECT exchange_session_date, value, revision, source FROM feature_observations WHERE instrument=? AND feature_name=? '
                    'AND feature_version=? ORDER BY id', (inst, 'close', FEATURE_VERSION)):
                latest[(inst, session)] = (value, revision, source)
        for r in rows:
            key = (r['instrument'], r['exchange_session_date'])
            last = latest.get(key)
            if last is not None and last[0] == r['value'] and last[2] == r['source']:
                out['UNCHANGED'] += 1
                continue
            revision = 0 if last is None else last[1] + 1
            db.execute('INSERT INTO feature_observations (instrument, feature_name, value, source, source_timestamp, known_at, ingested_at, '
                       'exchange_session_date, feature_version, provider, revision, metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                       (r['instrument'], 'close', r['value'], r['source'], r['source_timestamp'], r['known_at'], at, r['exchange_session_date'],
                        FEATURE_VERSION, r.get('provider'), revision, canonical(r.get('metadata') or {})))
            latest[key] = (r['value'], revision, r['source'])
            out['INSERTED' if revision == 0 else 'REVISED'] += 1
    return out


def ingest_provider_daily_bars(store, instrument, raw_bars, *, known_at, provider='robinhood_read_gateway', now=None):
    """Raw provider daily bars. The provider timestamp is stored exactly as received; the session date is derived from it."""
    known = sessions.utc_iso(known_at)
    rows, skipped = [], {'interpolated': 0, 'not_completed': 0, 'bad_price': 0}
    for bar in raw_bars or []:
        session = sessions.session_date_from_provider_daily_bar(bar['begins_at'])
        if bar.get('interpolated'):
            skipped['interpolated'] += 1
            continue
        if not sessions.is_completed(session, known):
            skipped['not_completed'] += 1                # today's bar while the session is still open is not a close
            continue
        price = _price(bar.get('close_price'))
        if price is None:
            skipped['bad_price'] += 1
            continue
        rows.append({'instrument': instrument, 'value': str(price), 'source': 'provider_daily_bars', 'source_timestamp': str(bar['begins_at']),
                     'known_at': known, 'exchange_session_date': session, 'provider': provider,
                     'metadata': {'source_timestamp_basis': 'raw provider value'}})
    return {**_insert_closes(store, rows, now), 'skipped': skipped}


def ingest_official_closes(store, labelled_closes_by_symbol, *, known_at, capsule_hash, cycle_id, now=None):
    """Closes exactly as Control A recorded them for one registered run (read-only source)."""
    known = sessions.utc_iso(known_at)
    rows, skipped = [], {'not_completed': 0, 'bad_price': 0}
    for instrument, labelled in sorted((labelled_closes_by_symbol or {}).items()):
        for label, value in sorted(labelled.items()):
            session = sessions.session_date_from_official_label(label)
            if not sessions.is_completed(session, known):
                skipped['not_completed'] += 1
                continue
            price = _price(value)
            if price is None:
                skipped['bad_price'] += 1
                continue
            rows.append({'instrument': instrument, 'value': str(price), 'source': 'control_a_decision_capsule',
                         'source_timestamp': sessions.provider_timestamp_for(session), 'known_at': known, 'exchange_session_date': session,
                         'provider': 'robinhood_read_gateway (as recorded by Control A)',
                         'metadata': {'official_label': label, 'source_timestamp_basis': RECONSTRUCTED,
                                      'capsule_hash': capsule_hash, 'cycle_id': cycle_id}})
    return {**_insert_closes(store, rows, now), 'skipped': skipped}


def baseline(store, instrument, *, known_at):
    """Computes the four baseline features from stored closes known at or before ``known_at``. Nothing is written."""
    history = store.feature_history(instrument, 'close', FEATURE_VERSION, known_by=sessions.utc_iso(known_at))
    closes = [D(h['value']) for h in history if h['value'] is not None]
    out = {'instrument': instrument, 'completed_session_count': len(closes), 'exchange_session_date': history[-1]['exchange_session_date'] if history else None,
           'close': str(closes[-1]) if closes else None, 'ma200': None, 'above_ma200': None, 'momentum_126d': None, 'missing': []}
    if len(closes) >= TREND_WINDOW:
        ma = sum(closes[-TREND_WINDOW:], D(0)) / D(TREND_WINDOW)
        out['ma200'], out['above_ma200'] = str(ma), closes[-1] > ma
    else:
        out['missing'].append(f'ma200 needs {TREND_WINDOW} completed closes; has {len(closes)}')
    if len(closes) > MOMENTUM_LOOKBACK:
        out['momentum_126d'] = str(closes[-1] / closes[-MOMENTUM_LOOKBACK - 1] - 1)
    else:
        out['missing'].append(f'momentum_126d needs {MOMENTUM_LOOKBACK + 1} completed closes; has {len(closes)}')
    return out


def store_baseline(store, instrument, *, known_at, now=None):
    """Computes and appends the derived features for the latest completed session. Missing values are stored as NULL."""
    b = baseline(store, instrument, known_at=known_at)
    if b['exchange_session_date'] is None:
        return b
    known = sessions.utc_iso(known_at)
    values = {'completed_session_count': b['completed_session_count'], 'ma200': b['ma200'],
              'above_ma200': None if b['above_ma200'] is None else ('true' if b['above_ma200'] else 'false'), 'momentum_126d': b['momentum_126d']}
    for name in DERIVED:
        store.add_feature(instrument=instrument, feature_name=name, value=values[name], source='firm_lab_feature_store', source_timestamp=None,
                          known_at=known, exchange_session_date=b['exchange_session_date'], feature_version=FEATURE_VERSION, provider='firm_lab',
                          metadata={'computed_from': 'close', 'missing': b['missing']} if values[name] is None else {'computed_from': 'close'}, now=now)
    return b
