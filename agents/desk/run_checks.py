"""Every recorded check of one run, in a displayable, whitelisted shape.

Sources are named public fields of the run's trace (the terminal payload's
strategy_assessment, collector_evidence, ai_gate, results, and stage events).
Strategy conditions are re-evaluated from the *recorded* features using the
rule constants below (mirrors research/strategy_signals.py); each row also
carries the outcome the run itself recorded, and any disagreement is flagged
instead of hidden. Identifiers (authorization ids, account fields) are never
read.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
ROOT_V142 = '39375034732a5ee14b2efb1d13e3c165438140255f1dc95ef25680d136a66075'
MOMENTUM_WARMUP, TREND_WINDOW, DROP = 253, 200, Decimal('-0.03')
STRATEGY_RULES = {
    'momentum_rotation': {
        'title': 'Momentum rotation (ETFs)',
        'version': 'momentum_rotation_126d_trend200_top1',
        'conditions': (('history', f'≥ {MOMENTUM_WARMUP} closes'), ('trend', 'Price above 200-day avg'),
                       ('momentum', '126-day momentum > 0'), ('rank', 'Highest momentum (top 1)')),
    },
    'mean_reversion': {
        'title': 'Mean reversion (all names)',
        'version': 'mean_reversion_drop3_above_ma200',
        'conditions': (('history', f'≥ {TREND_WINDOW + 2} closes'), ('trend', 'Price above 200-day avg'),
                       ('drop', 'Fell ≥ 3% last session')),
    },
}


def D(value):
    try:
        out = Decimal(str(value))
        return out if out.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _s(value, limit=160):
    if isinstance(value, bool) or value is None:
        return None
    text = ' '.join(str(value).split())
    return text[:limit] if text else None


def pct(value, digits=1):
    return None if value is None else f'{value * 100:+.{digits}f}%'


def features_table(assessment):
    feats = assessment.get('features') if isinstance(assessment.get('features'), dict) else {}
    rows = []
    for ticker, f in sorted(feats.items()):
        if not isinstance(f, dict) or not _s(ticker, 12):
            continue
        price, ma = D(f.get('price')), D(f.get('ma200'))
        rows.append({
            'instrument': _s(ticker, 12), 'closes': f.get('completed_closes') if isinstance(f.get('completed_closes'), int) else None,
            'price': price, 'ma200': ma, 'vs_ma200': (price / ma - 1) if price and ma else None,
            'above_ma200': f.get('above_ma200') if isinstance(f.get('above_ma200'), bool) else None,
            'm63': D(f.get('momentum_63d')), 'm126': D(f.get('momentum_126d')), 'm252': D(f.get('momentum_252d')),
            'day': D(f.get('one_day_return')),
        })
    return rows


def _cell(ok, value):
    return {'ok': ok, 'value': value}


def strategy_matrix(assessment, features):
    strategies = assessment.get('strategies') if isinstance(assessment.get('strategies'), dict) else {}
    signals = assessment.get('signals') if isinstance(assessment.get('signals'), list) else []
    signalled = {(str(s.get('strategy')), str(s.get('instrument'))) for s in signals if isinstance(s, dict)}
    by = {r['instrument']: r for r in features}
    out = []
    for key, rule in STRATEGY_RULES.items():
        rec = strategies.get(key) if isinstance(strategies.get(key), dict) else None
        if rec is None:
            continue
        evaluated = [str(t) for t in rec.get('evaluated', []) if isinstance(t, str)] if isinstance(rec.get('evaluated'), list) else sorted(by)
        blocked = rec.get('blocked') if isinstance(rec.get('blocked'), dict) else {}
        ranked = [str(r.get('instrument')) for r in rec.get('ranked', []) if isinstance(r, dict)] if isinstance(rec.get('ranked'), list) else []
        rows = []
        for ticker in evaluated:
            f = by.get(ticker, {})
            closes = f.get('closes')
            cells = {}
            need = MOMENTUM_WARMUP if key == 'momentum_rotation' else TREND_WINDOW + 2
            cells['history'] = _cell(None if closes is None else closes >= need, f'{closes}' if closes is not None else '—')
            cells['trend'] = _cell(f.get('above_ma200'), pct(f.get('vs_ma200')) or '—')
            if key == 'momentum_rotation':
                m = f.get('m126')
                cells['momentum'] = _cell(None if m is None else m > 0, pct(m) or '—')
                position = ranked.index(ticker) + 1 if ticker in ranked else None
                cells['rank'] = _cell(None if position is None else position == 1, f'#{position}' if position else '—')
                computed = all(cells[c]['ok'] is True for c in ('history', 'trend', 'momentum', 'rank'))
            else:
                day = f.get('day')
                cells['drop'] = _cell(None if day is None else day <= DROP, pct(day, 2) or '—')
                computed = all(cells[c]['ok'] is True for c in ('history', 'trend', 'drop'))
            failed = False
            for name, _ in rule['conditions']:
                if failed:
                    cells[name]['ok'] = 'skip'
                elif cells[name]['ok'] is False:
                    failed = True
            recorded_signal = (rule['version'], ticker) in signalled
            reason = _s(blocked.get(ticker), 120)
            recorded = 'signal' if recorded_signal else 'blocked' if reason else 'ranked, not top' if ticker in ranked else 'not recorded'
            mismatch = (computed and not recorded_signal) or (recorded_signal and not computed)
            rows.append({'instrument': ticker, 'cells': cells, 'recorded': recorded, 'reason': reason,
                         'signal': recorded_signal, 'mismatch': mismatch})
        rows.sort(key=lambda r: (not r['signal'], sum(c['ok'] is not True for c in r['cells'].values()), r['instrument']))
        out.append({'key': key, 'title': rule['title'], 'version': rule['version'], 'conditions': rule['conditions'],
                    'rows': rows, 'signals': sum(r['signal'] for r in rows), 'mismatches': sum(r['mismatch'] for r in rows)})
    return out


def _et(value):
    try:
        dt = datetime.fromisoformat(value)
        return dt.astimezone(ET).strftime('%a %b %-d, %-I:%M %p ET') if dt.tzinfo else None
    except (TypeError, ValueError):
        return None


def operational(payload, now=None):
    ce = payload.get('collector_evidence') if isinstance(payload.get('collector_evidence'), dict) else {}
    auth = ce.get('authorization') if isinstance(ce.get('authorization'), dict) else {}
    rows = []

    def add(group, check, value, status, note=''):
        rows.append({'group': group, 'check': check, 'value': value if value not in (None, '') else 'Not recorded',
                     'status': status if value not in (None, '') else 'unknown', 'note': note})
    status = _s(auth.get('status'), 40)
    add('Broker connection', 'Robinhood authorization', status,
        'pass' if status == 'VALID' else 'warn' if status and status.startswith('WARNING') else 'fail' if status else 'unknown',
        ('Expires ' + _et(auth.get('expires_at'))) if _et(auth.get('expires_at')) else '')
    writes = ce.get('effective_write_tool_count')
    add('Broker connection', 'Write/trade tools exposed', str(writes) if isinstance(writes, int) else None,
        'pass' if writes == 0 else 'fail', 'Must be 0: read-only connection')
    reads = ce.get('effective_read_tools') if isinstance(ce.get('effective_read_tools'), list) else []
    add('Broker connection', 'Read-only tools available', str(len(reads)) if reads else None, 'info', ', '.join(_s(t, 40) for t in reads[:20]))
    add('Broker connection', 'Keychain retrieval', _s(ce.get('keychain_retrieval'), 30),
        'pass' if ce.get('keychain_retrieval') == 'available' else 'warn')
    prereg = _s(ce.get('preregistration_hash'), 80)
    add('Registration', 'Preregistration in force', ('v1.4.2 root' if prereg == ROOT_V142 else (prereg or '')[:12] + '…') if prereg else None,
        'pass' if prereg == ROOT_V142 else 'warn')
    trip = ce.get('tripwire')
    trip_text = _s(trip.get('status') if isinstance(trip, dict) else trip, 60)
    add('Safety', 'Tripwire', trip_text, 'pass' if trip_text and trip_text.upper() in {'CLEAR', 'OK', 'NONE', 'ARMED', 'VERIFIED_UNCHANGED'} else 'info')
    add('Market', 'Market open at run time', 'Yes' if payload.get('market_open') is True else 'No' if payload.get('market_open') is False else None,
        'pass' if payload.get('market_open') is True else 'info')
    q, v = payload.get('quote_count'), payload.get('volatility_count')
    add('Data', 'Quotes collected', str(q) if isinstance(q, int) else None, 'pass' if isinstance(q, int) and q > 0 else 'fail')
    add('Data', 'Volatility series', str(v) if isinstance(v, int) else None, 'pass' if isinstance(v, int) and v > 0 else 'warn')
    cae = payload.get('corporate_action_exclusions') if isinstance(payload.get('corporate_action_exclusions'), list) else []
    # The run records every instrument it left out of the day's screen in one list. Two different things land there:
    # a quote the run could not use (no positive, uncrossed bid/ask: almost always a thinly traded option contract),
    # and a real corporate action (split, merger, symbol change). Only the second needs attention.
    quote_skips = [x for x in cae if isinstance(x, dict) and 'QUOTE' in str(x.get('reason') or '').upper()]
    actions = [x for x in cae if x not in quote_skips]
    reasons = sorted({_s(x.get('reason'), 60) for x in actions if isinstance(x, dict) and x.get('reason')})
    add('Data', 'Corporate-action exclusions', str(len(actions)), 'warn' if actions else 'pass', ', '.join(r for r in reasons if r))
    if quote_skips:
        options = sum(1 for x in quote_skips if len(str(x.get('instrument') or '')) == 36 and str(x.get('instrument')).count('-') == 4)
        what = 'all option contracts' if options == len(quote_skips) else f'{options} option contracts' if options else 'no option contracts'
        add('Data', 'Quotes left out (no usable bid/ask)', str(len(quote_skips)), 'info',
            f'{what}; a quote needs a positive, uncrossed bid and ask to be used. Left out of today’s screen only. '
            'New option buys are paused under v1.6, so nothing was missed.')
    gate = payload.get('ai_gate') if isinstance(payload.get('ai_gate'), dict) else None
    if gate:
        add('AI', 'AI gate', 'Open' if gate.get('invoke') is True else 'Closed', 'info', _s(gate.get('reason'), 60) or '')
    add('AI', 'AI cost estimate', ('$' + str(payload.get('api_cost_estimate_usd'))) if payload.get('api_cost_estimate_usd') is not None else None, 'info')
    unc = payload.get('uncertain_model_calls')
    add('AI', 'Uncertain model calls', str(unc) if isinstance(unc, int) else None, 'pass' if unc == 0 else 'warn')
    add('AI', 'News checked', 'Yes' if payload.get('news_checked') is True else 'No' if payload.get('news_checked') is False else None, 'info')
    add('Outcome', 'Run status', _s(payload.get('status'), 40), 'pass' if payload.get('status') == 'COMPLETED' else 'fail')
    acct = _s(payload.get('accounting_status'), 40)
    if acct:
        add('Outcome', 'Paper accounting', acct, 'pass' if acct == 'SETTLED' else 'warn')
    return rows


def risk_checks(payload):
    rows = []
    for key in ('results', 'desk_results'):
        for r in payload.get(key, []) if isinstance(payload.get(key), list) else []:
            if not isinstance(r, dict):
                continue
            reasons = [_s(x, 200) for x in r.get('reasons', [])] if isinstance(r.get('reasons'), list) else []
            rows.append({'instrument': _s(r.get('instrument'), 16) or '—', 'arm': _s(r.get('arm'), 30),
                         'status': _s(r.get('status'), 40) or '—',
                         'reasons': [x for x in reasons if x] or ([_s(r.get('reason'), 200)] if r.get('reason') else [])})
    return rows


def option_screen(ordered):
    event = next((e for e in reversed(ordered) if e.get('event') == 'strategy_evaluated'), None)
    screen = event.get('option_screen') if event and isinstance(event.get('option_screen'), dict) else None
    if not screen or not isinstance(screen.get('funnel'), list):
        return None
    labels = {'quote_fresh': 'Fresh quote', 'underlying_has_buy_signal': 'Underlying has a buy signal',
              'is_call': 'Is a call', 'valid_bid_ask': 'Valid bid/ask', 'spread_within_15pct': 'Spread ≤ 15% of mid',
              'at_least_one_contract_buyable': 'At least 1 contract buyable', 'one_contract_affordable': '1 contract fits the lane'}
    funnel = [{'stage': labels.get(str(r.get('stage')), _s(r.get('stage'), 40)), 'removed': r.get('removed'), 'remaining': r.get('remaining')}
              for r in screen['funnel'] if isinstance(r, dict)]
    under = []
    for name, row in (screen.get('by_underlying') or {}).items():
        if isinstance(row, dict):
            under.append({'underlying': _s(name, 12), 'contracts': row.get('contracts'), 'passed': row.get('passed'),
                          'cheapest_call_cost': _s(row.get('cheapest_call_cost'), 20), 'available': _s(row.get('available_risk_notional'), 20)})
    return {'seen': screen.get('contracts_seen'), 'passed': screen.get('passed_all_filters'), 'funnel': funnel,
            'bullish': [_s(x, 12) for x in screen.get('bullish_underlyings', []) if _s(x, 12)], 'by_underlying': under}


def build_checks(ordered):
    terminal = next((e for e in reversed(ordered) if e.get('event') == 'cycle_terminal'), None)
    payload = terminal.get('payload') if terminal and isinstance(terminal.get('payload'), dict) else {}
    assessment = payload.get('strategy_assessment') if isinstance(payload.get('strategy_assessment'), dict) else {}
    features = features_table(assessment)
    return {
        'decision_date': _s(assessment.get('decision_date'), 20),
        'qualification': _s(assessment.get('qualification'), 60),
        'features': features,
        'strategies': strategy_matrix(assessment, features),
        'operational': operational(payload) if payload else [],
        'risk': risk_checks(payload),
        'options': option_screen(ordered),
        'missing_evidence': [x for x in (_s(m, 400) for m in payload.get('missing_evidence', [])) if x] if isinstance(payload.get('missing_evidence'), list) else [],
    }
