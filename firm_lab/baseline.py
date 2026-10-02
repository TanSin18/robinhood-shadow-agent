"""control_a_baseline_counterfactual: what would Control A's existing rule select, computed from the new store?

This is a plumbing test for Firm Lab's data path, not a Firm strategy. It applies the registered rule as it is
(at least 253 completed closes, last close above its 200-session average, positive 126-session momentum, pick
the single strongest) and writes a DEVELOPMENT_ONLY record. It never creates an order, a fill or a position.
"""
from __future__ import annotations

from decimal import Decimal

from . import DEVELOPMENT_ONLY, features, sessions

D = Decimal
STRATEGY_ID = 'control_a_baseline_counterfactual'
TITLE = 'DEVELOPMENT COUNTERFACTUAL — NOT A PAPER TRADE'
MOMENTUM_WARMUP = 253


def evaluate(store, universe, *, known_at, provenance=None, write=True):
    known = sessions.utc_iso(known_at)
    candidates = []
    for symbol in sorted(set(universe)):
        b = features.baseline(store, symbol, known_at=known)
        if b['completed_session_count'] < MOMENTUM_WARMUP:
            eligible, reason = False, f'needs {MOMENTUM_WARMUP} completed closes; has {b["completed_session_count"]}'
        elif b['above_ma200'] is not True:
            eligible, reason = False, 'price is not above its 200-session moving average'
        elif b['momentum_126d'] is None or D(b['momentum_126d']) <= 0:
            eligible, reason = False, '126-session momentum is not positive'
        else:
            eligible, reason = True, 'eligible'
        candidates.append({'instrument': symbol, 'exchange_session_date': b['exchange_session_date'], 'close': b['close'],
                           'completed_session_count': b['completed_session_count'], 'ma200': b['ma200'], 'above_ma200': b['above_ma200'],
                           'momentum_126d': b['momentum_126d'], 'eligible': eligible, 'eligibility_reason': reason})
    ranked = sorted((c for c in candidates if c['eligible']), key=lambda c: (-D(c['momentum_126d']), c['instrument']))
    for rank, c in enumerate(ranked, start=1):
        c['rank'] = rank
    selected = ranked[0]['instrument'] if ranked else None
    session_dates = sorted({c['exchange_session_date'] for c in candidates if c['exchange_session_date']})
    record = {'title': TITLE, 'label': DEVELOPMENT_ONLY, 'strategy_id': STRATEGY_ID, 'evaluated_at': known,
              'exchange_session_date': session_dates[-1] if session_dates else None, 'universe': sorted(set(universe)),
              'candidates': candidates, 'selected_instrument': selected,
              'features_used': {'feature_version': features.FEATURE_VERSION, 'names': ['close', *features.DERIVED],
                                'rule': 'count >= 253, close > 200-session average, 126-session momentum > 0, strongest one'},
              'provenance': {'data': 'firm_lab feature store, closes known at or before evaluated_at', **(provenance or {})}}
    if write and record['exchange_session_date']:
        saved = store.add_counterfactual(timestamp=known, exchange_session_date=record['exchange_session_date'], strategy_id=STRATEGY_ID,
                                         candidates=candidates, selected_instrument=selected, features_used=record['features_used'],
                                         provenance=record['provenance'])
        record.update(saved)
    return record
