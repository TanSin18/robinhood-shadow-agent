"""v1.7 amendment layer: a market core plus satellites, exits that act, entry filters, honest fill costs.

Byte-pinned like v1.5 and v1.6: inert unless ``preregistration-amendment-v1.7.0.yaml`` is byte-identical to
the operator-signed file pinned below, the effective time has passed and v1.6 is active. Paper only; real
orders stay blocked.

What changes when it is active (all in the three Lane A paper arms):

* Core. Each arm holds VTI at 70% of its value, bought by rule at the 10:00 run (topped up when it drifts
  below 65%). The core is never sold by the trend exits, the 15:50 check or the exit guard.
* Satellites. The registered momentum rule may hold up to the top three ranked ETFs (never VTI), at most
  two new entries per run, sized by the unchanged risk engine. An AI stock pick no longer blocks them.
* Entry filters, which can only keep the desk out: the name must be TRENDING on completed daily bars
  (all arms); no new entry while the regime model says "stressed" (all arms); no entry in a ticker with a
  negative, high-relevance news call in the last after-close note (AI arms only; the rules-only arm is the
  control). Missing or stale regime or news evidence has no effect and is recorded.
* Exit guard. At the 15:50 check, after the unchanged v1.6 triggers, a satellite is sold when the fresh bid
  is at or below its trailing stop (highest completed close since entry minus 3 x ATR22, with a profit
  lock; the stop never moves down), when half of a 10%+ peak gain is gone, or when it is below its
  50-session average while the regime is stressed.
* Fill costs. Buys fill at ask x 1.001 and sells at bid x 0.999, charged in the ledger.
* Drawdown latch. The 10% latch releases once the account is back within 5% of its peak, and the peak is
  re-based after 28 latched days. The 15% hard switch is unchanged.
* Aligned-pick marker. Six code checks per entry; a star when all six pass. Information only.

Every v1.7 step is wrapped by its caller: if anything here raises, the run records the failure and finishes
without the v1.7 step. Nothing here calls a model or a broker write.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from zoneinfo import ZoneInfo

D = Decimal
ET = ZoneInfo('America/New_York')
APPROVED_V170_SHA256: str | None = None   # WITHDRAWN 2026-10-01: never signed off for install; Control A is frozen
V170_EFFECTIVE_FROM: datetime | None = None
V170_AMENDMENT_NAME = 'preregistration-amendment-v1.7.0.yaml'
ARMS = ('agent_alone', 'deterministic_no_ai', 'with_approvals')
IMMEDIATE_ARMS = ('agent_alone', 'deterministic_no_ai')
AI_ARMS = ('agent_alone', 'with_approvals')
TOP3_STRATEGY = 'momentum_rotation_126d_trend200_top3'
CORE_AUTHOR = 'Core holding (rule, no AI)'
GUARD_REASONS = ('GUARD_TRAILING_STOP', 'GUARD_PROFIT_LOCK', 'GUARD_GIVE_BACK', 'GUARD_FAST_TREND_BREAK')


def _root(root):
    return Path(root) if root else Path(__file__).resolve().parents[1]


def v17_active(root=None, now=None, *, approved_sha256=None, effective_from=None) -> bool:
    approved = APPROVED_V170_SHA256 if approved_sha256 is None else approved_sha256
    effective = V170_EFFECTIVE_FROM if effective_from is None else effective_from
    if approved is None or effective is None:
        return False
    root, now = _root(root), now or datetime.now(timezone.utc)
    if now.tzinfo is None or now < effective:
        return False
    path = root / V170_AMENDMENT_NAME
    try:
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != approved:
            return False
        from agents.v16_policy import v16_active
        if not v16_active(root, now):
            return False
        return (amendment(root).get('amendment', {}).get('operator_signature') or {}).get('status') == 'SIGNED'
    except (OSError, ValueError, AttributeError):
        return False


def amendment(root=None) -> dict:
    import yaml
    return yaml.safe_load((_root(root) / V170_AMENDMENT_NAME).read_bytes()) or {}


def params(root=None) -> dict:
    """The numbers the code uses, read from the signed file (never from config or environment)."""
    a = amendment(root)
    out = {'core_ticker': str(a['core']['instrument']), 'core_target': D(str(a['core']['target_weight'])),
           'core_top_up_below': D(str(a['core']['top_up_below_weight'])),
           'max_momentum_positions': int(a['satellites']['max_momentum_positions']),
           'max_new_entries_per_run': int(a['satellites']['max_new_entries_per_run']),
           'regime_valid_days': int(a['entry_filters']['regime']['valid_for_calendar_days']),
           'news_valid_days': int(a['entry_filters']['news_veto']['valid_for_calendar_days']),
           'news_arms': tuple(a['entry_filters']['news_veto']['applies_to']),
           'atr_multiple': float(a['exit_guard']['atr_multiple']), 'give_back_min': float(a['exit_guard']['give_back_min_peak_gain']),
           'slippage': D(str(a['fill_costs']['slippage_fraction'])),
           'latch_release': D(str(a['drawdown_latch']['release_when_drawdown_from_peak_at_or_below'])),
           'latch_rebase_days': int(a['drawdown_latch']['rebase_peak_after_latched_calendar_days'])}
    if not (D(0) < out['core_top_up_below'] <= out['core_target'] < D(1)) or not D(0) <= out['slippage'] < D('0.01') \
            or out['max_momentum_positions'] < 1 or out['max_new_entries_per_run'] < 1:
        raise ValueError('invalid v1.7 parameters')
    return out


def slippage_fraction(root=None, now=None) -> Decimal:
    """0 unless v1.7 is active. A failure to read the layer charges nothing rather than stopping a fill."""
    try:
        return params(root)['slippage'] if v17_active(root, now) else D(0)
    except Exception:
        return D(0)


def is_core(state, ticker) -> bool:
    return isinstance(state.get('core'), dict) and state['core'].get('ticker') == ticker


def ensure_tables(db):
    db.execute('CREATE TABLE IF NOT EXISTS aligned_picks (id TEXT PRIMARY KEY, created_at TEXT, payload_json TEXT)')


# ------------------------------------------------------------------ advisory evidence (regime label, news calls)
def advisory(official_db, now, *, regime_days=4, news_days=4, path=None) -> dict:
    """Reads the after-close job's records, read-only. Anything missing, stale or unreadable means "no effect"."""
    out = {'status': 'UNAVAILABLE', 'regime': None, 'regime_as_of': None, 'news_checked': False, 'note_as_of': None, 'negative_news': {}}
    try:
        path = Path(path) if path else Path(official_db).resolve().parents[2] / 'robinhood-diagnostics' / 'analyst' / 'analyst.db'
        if not path.is_file():
            return out
        db = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=1)
    except (OSError, sqlite3.Error, IndexError):
        return out
    try:
        def fresh(stamp, days):
            at = datetime.fromisoformat(stamp)
            return at.tzinfo is not None and timedelta(0) <= now - at <= timedelta(days=days)
        row = db.execute('SELECT at, payload_json FROM regimes ORDER BY id DESC LIMIT 1').fetchone()
        if row and fresh(row[0], regime_days):
            fit = json.loads(row[1])
            if fit.get('status') == 'OK' and fit.get('current') in ('calm', 'normal', 'stressed'):
                out.update(regime=fit['current'], regime_as_of=row[0])
        for kind in ('close', 'close:biscuit'):
            note = db.execute('SELECT at, payload_json FROM notes WHERE kind=? ORDER BY id DESC LIMIT 1', (kind,)).fetchone()
            if not note or not fresh(note[0], news_days):
                continue
            out['news_checked'] = True
            out['note_as_of'] = max(out['note_as_of'] or note[0], note[0])
            for item in json.loads(note[1]).get('news') or []:
                if item.get('sentiment') == 'negative' and item.get('relevance') == 'high' and item.get('ticker'):
                    out['negative_news'][str(item['ticker'])] = str(item.get('note') or '')[:200]
        out['status'] = 'OK'
    except (sqlite3.Error, ValueError, TypeError, KeyError):
        out.update(status='UNREADABLE', regime=None, news_checked=False, negative_news={})
    finally:
        db.close()
    return out


# ------------------------------------------------------------------ candidates and filters
def candidates(strategy_assessment, signal_map, fresh_instruments, snapshot, p) -> list:
    """Momentum top-N (never the core ticker), then any ETF dip signal. Only names with a fresh quote."""
    from research.strategy_signals import ETF_UNIVERSE
    ranked = ((strategy_assessment.get('strategies') or {}).get('momentum_rotation') or {}).get('ranked') or []
    out, seen = [], set()
    eligible = [s for s in ranked if s.get('instrument') != p['core_ticker']]
    for rank, sig in enumerate(eligible[:p['max_momentum_positions']], start=1):
        symbol = str(sig['instrument'])
        if symbol not in fresh_instruments or symbol not in snapshot['quotes']:
            continue
        seen.add(symbol)
        out.append({'symbol': symbol, 'kind': 'momentum', 'rank': rank, 'signal': {
            **sig, 'strategy': TOP3_STRATEGY,
            'thesis': f'{symbol} ranks #{rank} of the ETFs on positive 126-session momentum while above its 200-session average.'}})
    for symbol, sig in sorted(signal_map.items()):
        if (symbol in ETF_UNIVERSE and symbol != p['core_ticker'] and symbol not in seen and sig.get('side') == 'buy'
                and sig.get('strategy') == 'mean_reversion_drop3_above_ma200' and symbol in fresh_instruments and symbol in snapshot['quotes']):
            out.append({'symbol': symbol, 'kind': 'dip', 'rank': None, 'signal': sig})
    return out


def chop(snapshot, symbol) -> dict:
    from risk import tape
    bars = (snapshot.get('daily_bars') or {}).get(symbol) or []
    try:
        return tape.chop_label(bars)
    except Exception as error:
        return {'status': 'ERROR', 'error_type': type(error).__name__}


def alignment(candidate, features, chop_read, adv, eligible) -> dict:
    """Six code checks. A star means all six agree; it is not a forecast."""
    f = features or {}

    def positive(key):
        try:
            return D(str(f[key])) > 0
        except (KeyError, ArithmeticError, ValueError):
            return False
    symbol = candidate['symbol']
    checks = [
        ('Trend rule passed', True, 'above its 200-session average with positive 126-session momentum' if candidate['kind'] == 'momentum'
         else 'above its 200-session average after a 3% one-day drop'),
        ('Momentum agrees on three horizons', all(positive(k) for k in ('momentum_63d', 'momentum_126d', 'momentum_252d')),
         '63, 126 and 252 sessions all positive'),
        ('Tape is trending', chop_read.get('label') == 'TRENDING', f'label {chop_read.get("label") or chop_read.get("status")}'),
        ('Market regime calm or normal', adv.get('regime') in ('calm', 'normal'), f'regime {adv.get("regime") or "not known"}'),
        ('News checked, nothing negative', bool(adv.get('news_checked')) and symbol not in (adv.get('negative_news') or {}),
         'no negative high-relevance call' if adv.get('news_checked') else 'no fresh after-close note to check'),
        ('Liquidity and spread pass', bool(eligible), 'registered liquidity, spread and limit checks'),
    ]
    score = sum(1 for _, ok, _ in checks if ok)
    return {'score': score, 'of': len(checks), 'starred': score == len(checks),
            'checks': [{'check': n, 'ok': bool(ok), 'detail': d} for n, ok, d in checks]}


def _value(state):
    marks = state.get('marks') or {}
    return D(state['settled_cash']) + D(state['unsettled_cash']) + sum(
        D(p['quantity']) * D(marks.get(t, p['average_cost'])) * p['multiplier'] for t, p in state['positions'].items())


# ------------------------------------------------------------------ the 10:00 step: core, then satellites
def _core_step(inbox, db, config, arm, quote, vol, p, now, cycle_id):
    from agents.schemas import TradeProposal
    from risk.models import RiskReason
    ticker = p['core_ticker']
    row = {'arm': arm, 'instrument': ticker, 'role': 'core', 'attribution': 'core_rule_not_ai'}
    state = inbox.state('A', arm, db)
    if quote is None or vol is None:
        return {**row, 'status': 'BLOCKED', 'reason': 'MISSING_DATA'}
    if quote.halted or not 0 <= (now - quote.timestamp).total_seconds() <= config.risk.max_quote_age_seconds or not 0 < quote.bid <= quote.ask:
        return {**row, 'status': 'BLOCKED', 'reason': 'FRESH_QUOTE_REQUIRED'}
    if (quote.ask - quote.bid) / ((quote.ask + quote.bid) / 2) > D('.003'):
        return {**row, 'status': 'BLOCKED', 'reason': 'FRICTION_BLOCKED'}
    value = _value(state)
    held = state['positions'].get(ticker)
    core_value = D(held['quantity']) * quote.bid if held else D(0)
    weight = core_value / value if value > 0 else D(0)
    if weight >= p['core_top_up_below']:
        if held and not is_core(state, ticker):
            state['core'] = {'ticker': ticker, 'target': str(p['core_target']), 'since': now.isoformat()}
            db.execute('UPDATE paper_accounts SET payload=? WHERE lane=? AND track=?', (json.dumps(state), 'A', arm))
        return {**row, 'status': 'HOLD', 'reason': 'CORE_AT_TARGET', 'weight': str(weight.quantize(D('.0001')))}
    limit = quote.ask * D('1.002')
    amount = min(p['core_target'] * value - core_value, D(state['settled_cash']) * D('.999'))
    quantity = (amount / limit).quantize(D('.000001'), rounding=ROUND_DOWN)
    if quantity * limit < D(1):
        return {**row, 'status': 'BLOCKED', 'reason': 'BELOW_MINIMUM_NOTIONAL', 'weight': str(weight.quantize(D('.0001')))}
    ident = f'{cycle_id}-A-core'
    proposal = TradeProposal(proposal_id=ident, client_order_id=ident, account_id=config.risk.agentic_account_id, ticker=ticker,
                             asset_class='etf', side='buy', quantity=quantity, limit_price=limit,
                             thesis=f'Core holding: {ticker} at {p["core_target"] * 100:.0f}% of the account so it moves with the market.',
                             good_if='The market rises over the holding period.', invalidation='None: the core is not traded on signals.',
                             horizon_days=252, confidence=D('.5'), prompt_versions={}, model_name='deterministic_not_a_model', config_hash='0' * 64)
    fill = inbox._execute(db, 'A', arm, proposal, quote, vol[0], vol[1], now,
                          ignore_reasons=frozenset({RiskReason.POSITION_TOO_LARGE.value, RiskReason.VOLATILITY_SIZE_LIMIT.value}),
                          extra={'role': 'core', 'origin': 'v17_core'})
    db.execute('INSERT INTO decision_records(created_at,payload_json) VALUES (?,?)', (now.isoformat(), json.dumps({
        'proposal_id': ident, 'lane': 'A', 'track': arm, 'status': fill['status'], 'reasons': fill.get('reasons', []),
        'author': CORE_AUTHOR, 'origin': 'v17_core'})))
    if fill.get('status') == 'filled':
        state = inbox.state('A', arm, db)
        state['core'] = {'ticker': ticker, 'target': str(p['core_target']), 'since': (state.get('core') or {}).get('since') or now.isoformat()}
        db.execute('UPDATE paper_accounts SET payload=? WHERE lane=? AND track=?', (json.dumps(state), 'A', arm))
    return {**row, 'status': fill['status'], 'reasons': fill.get('reasons', []), 'reason': fill.get('reason'),
            'quantity': str(quantity), 'limit_price': str(limit), 'weight_before': str(weight.quantize(D('.0001')))}


def entries(inbox, config, *, snapshot, strategy_assessment, signal_map, fresh_instruments, now, cycle_id,
            lifecycle=None, root=None, advisory_path=None) -> list:
    """The v1.7 10:00 step for Lane A. Returns per-arm rows: satellites first, then the core rows."""
    from agents.etf_desk_policy import plan_entry
    from agents.etf_issuer import APPROVAL_ARM, liquidity_spread, median_recorded_spread
    from agents.inbox import DESK_AUTHOR
    from agents.schemas import TradeProposal
    from data.database_role import database_role
    from research.strategy_signals import ETF_UNIVERSE
    p = params(root)
    adv = advisory(inbox.path, now, regime_days=p['regime_valid_days'], news_days=p['news_valid_days'], path=advisory_path)
    features = strategy_assessment.get('features') or {}
    cands = candidates(strategy_assessment, signal_map, fresh_instruments, snapshot, p)
    day = now.astimezone(ET).date().isoformat()
    core_rows, rows = [], []
    with inbox.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if database_role(db) == 'live' and (lifecycle is None or not lifecycle.owns(db, cycle_id)):
            raise ValueError('Live cycle ownership is required')
        ensure_tables(db)
        core_quote, core_vol = snapshot['quotes'].get(p['core_ticker']), snapshot['vols'].get(p['core_ticker'])
        for arm in ARMS:
            core_rows.append(_core_step(inbox, db, config, arm, core_quote, core_vol, p, now, cycle_id))
        new = {arm: 0 for arm in ARMS}
        for cand in cands:
            symbol, quote, vol = cand['symbol'], snapshot['quotes'].get(cand['symbol']), snapshot['vols'].get(cand['symbol'])
            chop_read = chop(snapshot, symbol)
            base = {'instrument': symbol, 'kind': cand['kind'], 'rank': cand['rank'], 'attribution': 'desk_policy_not_ai',
                    'chop': chop_read.get('label') or chop_read.get('status'), 'regime': adv.get('regime')}
            spread = liquidity_spread(median_recorded_spread(db, symbol, day), quote, quote, True) if quote is not None else None
            dollar_volume = snapshot.get('median_dollar_volume_20d', {}).get(symbol)
            issued, eligible_any, arm_rows = {}, False, []
            for arm in ARMS:
                state = inbox.state('A', arm, db)
                if symbol in state['positions']:
                    continue                                   # already held in this arm: nothing to do
                if quote is None or vol is None:
                    arm_rows.append({'arm': arm, **base, 'status': 'BLOCKED', 'reason': 'MISSING_DATA'})
                    continue
                momentum_held = sum(1 for t, pos in state['positions'].items() if t in ETF_UNIVERSE and not is_core(state, t))
                reason = None
                if new[arm] >= p['max_new_entries_per_run']:
                    reason = 'MAX_NEW_ENTRIES_PER_RUN'
                elif cand['kind'] == 'momentum' and momentum_held >= p['max_momentum_positions']:
                    reason = 'MAX_MOMENTUM_POSITIONS'
                elif chop_read.get('label') != 'TRENDING':
                    reason = f'CHOP_GATE:{chop_read.get("label") or chop_read.get("status") or "UNKNOWN"}'
                elif adv.get('regime') == 'stressed':
                    reason = 'REGIME_STRESSED'
                elif arm in p['news_arms'] and symbol in (adv.get('negative_news') or {}):
                    reason = 'NEWS_VETO'
                if reason:
                    arm_rows.append({'arm': arm, **base, 'status': 'BLOCKED', 'reason': reason})
                    continue
                context = inbox._context(state, quote, vol[0], vol[1], now)
                plan = plan_entry(symbol=symbol, quote=quote, reference_quote=quote, evaluated_at=now, now=now,
                                  holdings_review_complete=True, approved_ai_stock_pick=False, entry_slot_used=False,
                                  median_spread_fraction=spread, median_dollar_volume=dollar_volume, context=context,
                                  risk_config=config.risk, signal=cand['signal'], cycle_id=cycle_id, order_tag=symbol)
                if plan['status'] != 'ELIGIBLE':
                    arm_rows.append({'arm': arm, **base, **plan})
                    continue
                eligible_any = True
                issued[arm] = plan
            mark = alignment(cand, features.get(symbol), chop_read, adv, eligible_any)
            text = f'Checks aligned: {mark["score"]} of {mark["of"]}' + (' ★' if mark['starred'] else '') + '.'
            for arm, plan in issued.items():
                proposal = TradeProposal.model_validate(plan['proposal'])
                if arm in IMMEDIATE_ARMS:
                    fill = inbox._execute(db, 'A', arm, proposal, quote, vol[0], vol[1], now, etf_entry_reference=D(plan['reference_midpoint']),
                                          extra={'role': 'satellite', 'origin': 'official_open', 'aligned': mark['score'], 'starred': mark['starred']})
                    db.execute('INSERT INTO decision_records(created_at,payload_json) VALUES (?,?)', (now.isoformat(), json.dumps({
                        'proposal_id': proposal.proposal_id, 'lane': 'A', 'track': arm, 'status': fill['status'], 'reasons': fill.get('reasons', []),
                        'author': DESK_AUTHOR, 'origin': 'official_open', 'aligned': mark['score']})))
                    arm_rows.append({'arm': arm, **base, 'status': fill['status'], 'reasons': fill.get('reasons', []), 'reason': fill.get('reason'),
                                     'quantity': plan['quantity'], 'limit_price': plan['limit_price']})
                    if fill.get('status') == 'filled':
                        new[arm] += 1
                elif arm == APPROVAL_ARM:
                    card = inbox.issue_desk_card(db, proposal, quote, vol, {**plan, 'alignment_text': text, 'alignment': mark}, now)
                    arm_rows.append({'arm': arm, **base, 'status': card['status'], 'card_id': card['id'], 'quantity': plan['quantity'],
                                     'limit_price': plan['limit_price'], 'expires_at': plan['expires_at']})
                    new[arm] += 1
            for r in arm_rows:
                r['aligned'] = f'{mark["score"]}/{mark["of"]}'
                r['starred'] = mark['starred']
            rows += arm_rows
            if any(r.get('status') in ('filled', 'PENDING') for r in arm_rows):
                vti = snapshot['quotes'].get(p['core_ticker'])
                db.execute('INSERT OR REPLACE INTO aligned_picks VALUES (?,?,?)', (f'{cycle_id}:{symbol}', now.isoformat(), json.dumps({
                    'ticker': symbol, 'day': day, 'kind': cand['kind'], 'rank': cand['rank'], **mark,
                    'entry_ask': str(quote.ask), 'benchmark': p['core_ticker'], 'benchmark_ask': str(vti.ask) if vti else None,
                    'arms': {r['arm']: r['status'] for r in arm_rows}})))
        db.execute('INSERT INTO daily_values(created_at,payload_json) VALUES (?,?)', (now.isoformat(), json.dumps({
            'kind': 'v17_entry_step', 'timestamp': now.isoformat(), 'advisory': {k: adv.get(k) for k in ('status', 'regime', 'regime_as_of', 'news_checked', 'note_as_of')},
            'negative_news': sorted(adv.get('negative_news') or {}), 'candidates': [c['symbol'] for c in cands]})))
    return rows + core_rows


# ------------------------------------------------------------------ the 15:50 step: exit guard for satellites
def guard_levels(cost, entry_day, bars, p) -> dict | None:
    """Stop and peak from completed daily bars. None when there is too little history to compute ATR22."""
    from risk import tape
    if not bars or not cost:
        return None
    a22, _ = tape.atr(bars, 22)
    if not a22:
        return None
    closes = [b['close'] for b in bars]
    since = [b['close'] for b in bars if entry_day and b['day'] >= entry_day]
    high = max(since + [cost])
    trail = high - p['atr_multiple'] * a22
    lock = cost + 2 * a22 if high - cost >= 4 * a22 else cost if high - cost >= 2 * a22 else None
    stop, rule = (lock, 'GUARD_PROFIT_LOCK') if lock is not None and lock > trail else (trail, 'GUARD_TRAILING_STOP')
    return {'stop': stop, 'rule': rule, 'high_since_entry': high, 'atr22': a22, 'ma50': tape.ma(closes, 50)}


def guard_reason(cost, bid, levels, prior_stop, regime, p):
    """Returns (reason or None, stop in force). The stop in force never moves down."""
    stop, rule = levels['stop'], levels['rule']
    if prior_stop is not None and prior_stop > stop:
        stop, rule = prior_stop, 'GUARD_TRAILING_STOP'
    if bid <= stop:
        return rule, stop
    peak_gain, gain = levels['high_since_entry'] / cost - 1, bid / cost - 1
    if peak_gain >= p['give_back_min'] and gain <= peak_gain / 2:
        return 'GUARD_GIVE_BACK', stop
    if levels.get('ma50') and bid < levels['ma50'] and regime == 'stressed':
        return 'GUARD_FAST_TREND_BREAK', stop
    return None, stop


def entry_day(state, ticker):
    buys = [f for f in state.get('fills', []) if f.get('ticker') == ticker and f.get('side') == 'buy' and f.get('status') == 'filled']
    if not buys:
        return None
    return max(datetime.fromisoformat(f['timestamp']) for f in buys).astimezone(ET).date().isoformat()


def guard_check(inbox, arm, ticker, position, bid, raw_bars, now, adv, p) -> tuple:
    """One satellite in one arm at the 15:50 check. Returns (reason or None, details). Persists a raised stop."""
    from risk import tape
    state = inbox.state('A', arm)
    cost = float(D(str(position.get('average_cost', '0'))))
    levels = guard_levels(cost, entry_day(state, ticker), tape.bars_from_raw(raw_bars, now.astimezone(ET).date()), p)
    if levels is None:
        return None, {'guard': 'GUARD_EVIDENCE_MISSING'}
    prior = (state.get('guard_stops') or {}).get(ticker)
    reason, stop = guard_reason(cost, float(bid), levels, float(prior) if prior is not None else None, adv.get('regime'), p)
    if prior is None or stop > float(prior):
        with inbox.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            state = inbox.state('A', arm, db)
            if ticker in state['positions']:
                state.setdefault('guard_stops', {})[ticker] = str(round(stop, 4))
                db.execute('UPDATE paper_accounts SET payload=? WHERE lane=? AND track=?', (json.dumps(state), 'A', arm))
    return reason, {'guard_stop': round(stop, 4), 'guard_rule': levels['rule'], 'high_since_entry': round(levels['high_since_entry'], 4),
                    'atr22': round(levels['atr22'], 4), 'regime': adv.get('regime')}


# ------------------------------------------------------------------ drawdown latch
def latch_step(state, value, today, p) -> str | None:
    """Mutates one arm's state. Returns what happened, if anything. Called from the daily marking."""
    if not state.get('peak_breaker_latched'):
        state.pop('latched_since', None)
        return None
    peak = D(state['peak'])
    drawdown = (peak - value) / peak if peak > 0 else D(1)
    since = state.setdefault('latched_since', today.isoformat())
    if drawdown <= p['latch_release']:
        state['peak_breaker_latched'] = False
        state.pop('latched_since', None)
        return 'LATCH_RELEASED_RECOVERED'
    from datetime import date
    if (today - date.fromisoformat(since)).days >= p['latch_rebase_days']:
        state['peak'] = str(value)
        state['peak_breaker_latched'] = False
        state['peak_rebased_at'] = today.isoformat()
        state.pop('latched_since', None)
        return 'LATCH_RELEASED_PEAK_REBASED'
    return None
