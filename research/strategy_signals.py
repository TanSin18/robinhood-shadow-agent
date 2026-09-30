"""Point-in-time daily signals for the Stage 1 paper selection cycle.

These functions never call a broker and never place orders. They turn completed
daily closes into deterministic, inspectable candidate signals for the agents.
Historical qualification and promotion remain a separate gate.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, Mapping, Sequence

D = Decimal
ETF_UNIVERSE = frozenset({'SPY', 'QQQ', 'VTI', 'SOXX', 'XLE', 'XLU', 'GLD', 'TLT'})
MOMENTUM_WARMUP = 253
TREND_WINDOW = 200
MEAN_REVERSION_DROP = D('0.03')
MAX_OPTION_SPREAD_FRACTION = D('0.15')


def _dated_closes(history: Mapping[str, object], decision_date: date) -> list[D]:
    rows = []
    for raw_day, raw_value in history.items():
        observed = datetime.fromisoformat(raw_day).date()
        if observed <= decision_date:
            value = D(str(raw_value))
            if value.is_finite() and value > 0:
                rows.append((observed, value))
    return [value for _, value in sorted(rows)]


def _features(history: Mapping[str, object], decision_date: date) -> dict[str, object]:
    values = _dated_closes(history, decision_date)
    result: dict[str, object] = {'completed_closes': len(values)}
    if len(values) < 2:
        return result
    last, prior = values[-1], values[-2]
    result.update(price=str(last), one_day_return=str(last / prior - 1))
    if len(values) >= TREND_WINDOW:
        ma200 = sum(values[-TREND_WINDOW:], D(0)) / D(TREND_WINDOW)
        result.update(ma200=str(ma200), above_ma200=last > ma200)
    for lookback in (63, 126, 252):
        if len(values) > lookback:
            result[f'momentum_{lookback}d'] = str(last / values[-lookback - 1] - 1)
    return result


def _momentum_signal(ticker: str, features: Mapping[str, object]) -> dict[str, object]:
    momentum = D(str(features['momentum_126d']))
    return {
        'instrument': ticker,
        'underlying': ticker,
        'lane': 'A',
        'side': 'buy',
        'strategy': 'momentum_rotation_126d_trend200_top1',
        'strength': str(momentum),
        'momentum_63d': features['momentum_63d'],
        'momentum_126d': features['momentum_126d'],
        'momentum_252d': features['momentum_252d'],
        'price': features['price'],
        'ma200': features['ma200'],
        'thesis': f'{ticker} ranks highest on positive 126-session momentum while above its 200-session average.',
        'good_if': f'{ticker} remains above its 200-session average and relative momentum stays positive.',
        'invalidation': f'{ticker} closes at or below its 200-session average or loses positive 126-session momentum.',
        'confidence': str(min(D('0.85'), D('0.55') + max(D(0), momentum))),
    }


def _mean_reversion_signal(ticker: str, features: Mapping[str, object]) -> dict[str, object]:
    drop = D(str(features['one_day_return']))
    return {
        'instrument': ticker,
        'underlying': ticker,
        'lane': 'A',
        'side': 'buy',
        'strategy': 'mean_reversion_drop3_above_ma200',
        'strength': str(abs(drop)),
        'one_day_return': str(drop),
        'price': features['price'],
        'ma200': features['ma200'],
        'thesis': f'{ticker} fell at least 3% in one completed session while its longer trend remains positive.',
        'good_if': f'{ticker} remains above its 200-session average and recovers toward the pre-drop close.',
        'invalidation': f'{ticker} closes at or below its 200-session average or fails to recover within 10 sessions.',
        'confidence': str(min(D('0.80'), D('0.55') + abs(drop))),
    }


def evaluate_daily_signals(
    session_closes: Mapping[str, Mapping[str, object]],
    etf_universe: Iterable[str] = ETF_UNIVERSE,
    decision_date: date | None = None,
) -> dict[str, object]:
    """Evaluate fixed daily signal rules using only closes known by decision_date."""
    decision_date = decision_date or date.today()
    features = {ticker: _features(history, decision_date)
                for ticker, history in sorted(session_closes.items())}
    blocked: dict[str, str] = {}
    ranked = []
    etfs = set(etf_universe)
    for ticker in sorted(etfs):
        item = features.get(ticker, {'completed_closes': 0})
        count = int(item['completed_closes'])
        if count < MOMENTUM_WARMUP:
            blocked[ticker] = f'needs {MOMENTUM_WARMUP} completed closes; has {count}'
        elif item.get('above_ma200') is not True:
            blocked[ticker] = 'price is not above its 200-session moving average'
        elif D(str(item['momentum_126d'])) <= 0:
            blocked[ticker] = '126-session momentum is not positive'
        else:
            ranked.append(_momentum_signal(ticker, item))
    ranked.sort(key=lambda item: (-D(str(item['momentum_126d'])), item['instrument']))

    mean_reversion = []
    mean_blocked: dict[str, str] = {}
    for ticker, item in features.items():
        count = int(item['completed_closes'])
        if count < TREND_WINDOW + 2:
            mean_blocked[ticker] = f'needs {TREND_WINDOW + 2} completed closes; has {count}'
        elif item.get('above_ma200') is not True:
            mean_blocked[ticker] = 'price is not above its 200-session moving average'
        elif D(str(item['one_day_return'])) > -MEAN_REVERSION_DROP:
            mean_blocked[ticker] = 'latest completed-session drop is smaller than 3%'
        else:
            mean_reversion.append(_mean_reversion_signal(ticker, item))
    mean_reversion.sort(key=lambda item: (-D(str(item['strength'])), item['instrument']))

    signals = ranked[:1] + mean_reversion
    return {
        'decision_date': decision_date.isoformat(),
        'signals': signals,
        'features': features,
        'strategies': {
            'momentum_rotation': {
                'version': 'momentum_rotation_126d_trend200_top1',
                'evaluated': sorted(etfs),
                'ranked': ranked,
                'blocked': blocked,
                'qualifying_count': min(1, len(ranked)),
            },
            'mean_reversion': {
                'version': 'mean_reversion_drop3_above_ma200',
                'evaluated': sorted(features),
                'ranked': mean_reversion,
                'blocked': mean_blocked,
                'qualifying_count': len(mean_reversion),
            },
        },
        'qualification': 'DAILY_SHADOW_SIGNAL_ONLY',
        'qualification_note': 'These signals may guide Stage 1 paper proposals; they are not historically promoted strategies.',
    }


def rank_option_candidates(
    candidates: Sequence[Mapping[str, object]],
    underlying_signals: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Choose at most one affordable, liquid-enough long call per bullish underlying."""
    bullish = {str(signal['instrument']): str(signal['strategy'])
               for signal in underlying_signals if signal.get('side') == 'buy'}
    eligible = []
    for candidate in candidates:
        contract = candidate.get('contract')
        underlying = str(candidate.get('underlying', ''))
        if not isinstance(contract, Mapping) or underlying not in bullish or contract.get('type') != 'call':
            continue
        bid, ask = D(str(candidate['bid'])), D(str(candidate['ask']))
        mid = (bid + ask) / 2
        spread = (ask - bid) / mid if mid > 0 else D('Infinity')
        unit = ask * 100
        if (bid <= 0 or ask <= bid or spread > MAX_OPTION_SPREAD_FRACTION
                or D(str(candidate.get('max_buy_units', 0))) < 1
                or D(str(candidate.get('available_risk_notional', 0))) < unit):
            continue
        item = dict(candidate)
        item['strategy'] = f'defined_risk_call_on_{bullish[underlying]}'
        item['spread_fraction'] = str(spread)
        item['thesis'] = f'Defined-risk call expression of the qualifying {underlying} signal.'
        item['good_if'] = f'{underlying} signal remains valid and the option spread stays within 15% of midpoint.'
        item['invalidation'] = f'{underlying} signal invalidates or the option spread exceeds 15% of midpoint.'
        item['confidence'] = '0.55'
        eligible.append(item)
    eligible.sort(key=lambda item: (D(str(item['spread_fraction'])), item['underlying'], item['instrument']))
    chosen = []
    used = set()
    for item in eligible:
        if item['underlying'] not in used:
            chosen.append(item)
            used.add(item['underlying'])
    return chosen



def option_screen(candidates: Sequence[Mapping[str, object]],
                  underlying_signals: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Explain rank_option_candidates: how many contracts survive each filter.

    Read-only summary for the run record. Filters are applied in the same order
    as rank_option_candidates; the first failing filter is the one counted.
    """
    bullish = {str(signal['instrument']) for signal in underlying_signals if signal.get('side') == 'buy'}
    stages = ['quote_fresh', 'underlying_has_buy_signal', 'is_call', 'valid_bid_ask',
              'spread_within_15pct', 'at_least_one_contract_buyable', 'one_contract_affordable']
    failed = {stage: 0 for stage in stages}
    per_underlying: dict[str, dict[str, object]] = {}
    total = passed = 0
    for candidate in candidates:
        contract = candidate.get('contract')
        if not isinstance(contract, Mapping):
            continue
        total += 1
        underlying = str(candidate.get('underlying', ''))
        row = per_underlying.setdefault(underlying, {'contracts': 0, 'passed': 0, 'cheapest_call_cost': None,
                                                     'available_risk_notional': None})
        row['contracts'] += 1
        try:
            bid, ask = D(str(candidate['bid'])), D(str(candidate['ask']))
            available = D(str(candidate.get('available_risk_notional', 0)))
            units = D(str(candidate.get('max_buy_units', 0)))
        except (KeyError, ArithmeticError, ValueError):
            bid = ask = available = units = D(0)
        row['available_risk_notional'] = str(available)
        if contract.get('type') == 'call' and ask > 0:
            cost = ask * 100
            if row['cheapest_call_cost'] is None or cost < D(str(row['cheapest_call_cost'])):
                row['cheapest_call_cost'] = str(cost)
        mid = (bid + ask) / 2
        spread = (ask - bid) / mid if mid > 0 else D('Infinity')
        checks = [not candidate.get('quote_stale'), underlying in bullish, contract.get('type') == 'call',
                  bid > 0 and ask > bid, spread <= MAX_OPTION_SPREAD_FRACTION, units >= 1, available >= ask * 100]
        first = next((stages[i] for i, ok in enumerate(checks) if not ok), None)
        if first:
            failed[first] += 1
        else:
            passed += 1
            row['passed'] += 1
    remaining, funnel = total, []
    for stage in stages:
        remaining -= failed[stage]
        funnel.append({'stage': stage, 'removed': failed[stage], 'remaining': remaining})
    return {'contracts_seen': total, 'passed_all_filters': passed, 'funnel': funnel,
            'bullish_underlyings': sorted(bullish),
            'by_underlying': dict(sorted(per_underlying.items()))}
