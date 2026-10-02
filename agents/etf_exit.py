"""Registered exit for desk-rule ETF positions (v1.5.1 draft; inert unless enabled).

The desk rule records an exit with every ETF entry ("closes at or below its
200-session average or loses positive 126-session momentum"). This module
executes it, deterministically and the same way for every paper arm:

* agent_alone and deterministic_no_ai sell the full position at the fresh bid;
* with_approvals gets a SELL card (your YES fills at the card's quote, like
  every standard card; NO keeps the position).

The exit test uses only completed-session features from the run's own strategy
assessment. Missing or stale evidence never triggers a sale; it is reported.
AI never decides these exits.
"""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

D = Decimal
EXIT_ARMS = ('agent_alone', 'deterministic_no_ai')


def exit_reason(features: dict | None) -> str | None:
    """Registered invalidation for momentum_rotation_126d_trend200_top1 entries."""
    if not isinstance(features, dict):
        return None
    if features.get('above_ma200') is False:
        return 'CLOSED_AT_OR_BELOW_200_DAY_AVERAGE'
    try:
        if D(str(features['momentum_126d'])) <= 0:
            return 'MOMENTUM_126D_NOT_POSITIVE'
    except (KeyError, ArithmeticError, ValueError):
        return None
    return None


REASON_TEXT = {'CLOSED_AT_OR_BELOW_200_DAY_AVERAGE': 'closed at or below its 200-session average',
               'MOMENTUM_126D_NOT_POSITIVE': 'lost positive 126-session momentum',
               'HOLDING_PERIOD_20_SESSIONS_REACHED': 'reached its registered 20-session holding horizon',
               # v1.6 protective exit (same-day, 15:50 ET)
               'PROTECTIVE_STOP_BELOW_AVERAGE_COST': 'fell to the registered protective stop below its average cost',
               'LIVE_PRICE_AT_OR_BELOW_200_DAY_AVERAGE': 'is trading at or below its 200-session average near the close',
               'LIVE_MOMENTUM_126D_NOT_POSITIVE': 'shows non-positive 126-session momentum near the close',
               # v1.7 exit guard (15:50 ET, satellites only)
               'GUARD_TRAILING_STOP': 'fell to its trailing stop (highest close since entry minus 3 x ATR)',
               'GUARD_PROFIT_LOCK': 'fell back to its profit-lock floor',
               'GUARD_GIVE_BACK': 'gave back half of a peak gain of 10% or more',
               'GUARD_FAST_TREND_BREAK': 'is below its 50-session average while the market regime is stressed'}
HORIZON_SESSIONS = 20


def _sell(config, cycle_id, ticker, arm, quantity, quote, reason, asset_class='etf'):
    from agents.schemas import TradeProposal
    text = REASON_TEXT[reason]
    ident = f'{cycle_id}-A-exit-{ticker}-{arm}'
    return TradeProposal(proposal_id=ident, client_order_id=ident, account_id=config.risk.agentic_account_id,
        ticker=ticker, asset_class=asset_class, side='sell', quantity=D(str(quantity)), limit_price=quote.bid,
        thesis=f'Registered exit: {ticker} {text}.', good_if='The registered exit condition holds at the fresh quote.',
        invalidation='Not applicable to a closing sale.', horizon_days=1, confidence=D('.5'), prompt_versions={},
        model_name='deterministic_not_a_model', config_hash='0' * 64, is_closing=True)


def _is_core(state, ticker, now):
    """v1.7: an arm's market core (VTI) is held, not traded on signals. False whenever v1.7 is not active."""
    try:
        from agents.v17_policy import is_core, v17_active
        return v17_active(now=now) and is_core(state, ticker)
    except Exception:
        return False


def issue_desk_exits(inbox, config, *, strategy_assessment, snapshot, now, cycle_id, lifecycle=None):
    from agents.approval import ApprovalCardRenderer
    from research.strategy_signals import ETF_UNIVERSE
    from data.database_role import database_role
    features = strategy_assessment.get('features') or {}
    held = {}
    for track in ('agent_alone', 'with_approvals', 'deterministic_no_ai'):
        try:
            positions = inbox.state('A', track)['positions']
        except (KeyError, TypeError, ValueError):
            continue  # arm not present in this ledger
        state = inbox.state('A', track)
        for ticker, position in positions.items():
            if ticker in ETF_UNIVERSE and not _is_core(state, ticker, now):
                held.setdefault(ticker, {})[track] = position
    results = []
    for ticker, by_arm in sorted(held.items()):
        reason = exit_reason(features.get(ticker))
        if reason is None:
            results.append({'instrument': ticker, 'status': 'HOLD',
                            'reason': 'EXIT_CONDITION_NOT_MET' if ticker in features else 'EXIT_EVIDENCE_MISSING',
                            'attribution': 'desk_policy_not_ai'})
            continue
        quote, vol = snapshot['quotes'].get(ticker), snapshot['vols'].get(ticker)
        if (quote is None or quote.halted or not 0 <= (now - quote.timestamp).total_seconds() <= config.risk.max_quote_age_seconds
                or not quote.bid > 0):
            results.append({'instrument': ticker, 'status': 'EXIT_BLOCKED', 'reason': 'FRESH_QUOTE_REQUIRED',
                            'exit_reason': reason, 'attribution': 'desk_policy_not_ai'})
            continue
        with inbox.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if database_role(db) == 'live' and (lifecycle is None or not lifecycle.owns(db, cycle_id)):
                raise ValueError('Live cycle ownership is required')
            for arm, position in sorted(by_arm.items()):
                proposal = _sell(config, cycle_id, ticker, arm, position['quantity'], quote, reason)
                if arm in EXIT_ARMS:
                    fill = inbox._execute(db, 'A', arm, proposal, quote, vol[0] if vol else None, vol[1] if vol else None, now)
                    db.execute('INSERT INTO decision_records(created_at,payload_json) VALUES (?,?)',
                               (now.isoformat(), json.dumps({'proposal_id': proposal.proposal_id, 'lane': 'A', 'track': arm,
                                'status': fill['status'], 'reasons': fill.get('reasons', []), 'author': 'Desk rule (no AI)',
                                'origin': 'registered_exit', 'exit_reason': reason})))
                    results.append({'arm': arm, 'instrument': ticker, 'status': fill['status'], 'side': 'sell',
                                    'quantity': str(position['quantity']), 'price': str(quote.bid),
                                    'exit_reason': reason, 'reasons': fill.get('reasons', []), 'attribution': 'desk_policy_not_ai'})
                else:
                    if db.execute('SELECT 1 FROM approval_inbox WHERE id=?', (proposal.proposal_id,)).fetchone():
                        continue
                    card = ApprovalCardRenderer().render(proposal, instrument_description='stock/ETF', max_loss_usd=D(0),
                        holdings_after={}, trace_url=config.notifications.dashboard_url(f'trace/{proposal.proposal_id}', fragment=False))
                    if database_role(db) == 'live':
                        from agents.operator import MarketSchedule
                        expires = MarketSchedule().session_close(now)
                    else:
                        expires = now + timedelta(minutes=config.approval_expiry_minutes)
                    payload = {'id': proposal.proposal_id, 'status': 'PENDING', 'lane': 'A', 'author': 'Desk rule (no AI)',
                               'attribution': 'desk_policy_not_ai', 'origin': 'registered_exit', 'exit_reason': reason,
                               'body': card.body, 'trace_url': card.trace_url, 'proposal': proposal.model_dump(mode='json'),
                               'quote': quote.model_dump(mode='json'), 'vol': str(vol[0]) if vol else None,
                               'vol_as_of': vol[1].isoformat() if vol else None, 'issued': now.isoformat(),
                               'expires': expires.isoformat(), 'comparison': 'Proposal-time counterfactual; excludes approval execution latency.'}
                    db.execute('INSERT INTO approval_inbox VALUES (?,?,?,?,?)',
                               (proposal.proposal_id, 'PENDING', payload['issued'], payload['expires'], json.dumps(payload)))
                    results.append({'arm': arm, 'instrument': ticker, 'status': 'PENDING', 'side': 'sell', 'card_id': proposal.proposal_id,
                                    'quantity': str(position['quantity']), 'exit_reason': reason, 'attribution': 'desk_policy_not_ai'})
    return results


def _fresh(quote, config, now):
    return (quote is not None and not quote.halted and quote.bid > 0
            and 0 <= (now - quote.timestamp).total_seconds() <= config.risk.max_quote_age_seconds)


def _entry_day(state, ticker):
    from zoneinfo import ZoneInfo
    from datetime import datetime
    buys = [f for f in state.get('fills', []) if f.get('ticker') == ticker and f.get('side') == 'buy' and f.get('status') == 'filled']
    if not buys:
        return None
    last = max(datetime.fromisoformat(f['timestamp']) for f in buys)
    return last.astimezone(ZoneInfo('America/New_York')).date().isoformat()


def stock_reason(features, closes, entry_day):
    """Backstop for AI-bought stocks: registered invalidation or the 20-session horizon."""
    if isinstance(features, dict) and features.get('above_ma200') is False:
        return 'CLOSED_AT_OR_BELOW_200_DAY_AVERAGE'
    if entry_day and isinstance(closes, dict) and sum(1 for d in closes if d > entry_day) >= HORIZON_SESSIONS:
        return 'HOLDING_PERIOD_20_SESSIONS_REACHED'
    return None


def stock_backstop_exits(inbox, config, *, strategy_assessment, snapshot, now, cycle_id, lifecycle=None):
    """Runs after the AI had its chance this cycle; sells only what is still held."""
    from agents.approval import ApprovalCardRenderer
    from data.database_role import database_role
    features = strategy_assessment.get('features') or {}
    results = []
    for arm in ('agent_alone', 'with_approvals', 'deterministic_no_ai'):
        try:
            state = inbox.state('A', arm)
        except (KeyError, TypeError, ValueError):
            continue
        for ticker, position in sorted(state['positions'].items()):
            if position.get('asset_class') != 'stock':
                continue
            reason = stock_reason(features.get(ticker), snapshot['session_closes'].get(ticker), _entry_day(state, ticker))
            if reason is None:
                continue
            quote, vol = snapshot['quotes'].get(ticker), snapshot['vols'].get(ticker)
            if not _fresh(quote, config, now):
                results.append({'arm': arm, 'instrument': ticker, 'status': 'EXIT_BLOCKED', 'reason': 'FRESH_QUOTE_REQUIRED', 'exit_reason': reason})
                continue
            proposal = _sell(config, cycle_id, ticker, arm, position['quantity'], quote, reason, asset_class='stock')
            with inbox.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if database_role(db) == 'live' and (lifecycle is None or not lifecycle.owns(db, cycle_id)):
                    raise ValueError('Live cycle ownership is required')
                if arm == 'with_approvals':
                    if db.execute('SELECT 1 FROM approval_inbox WHERE id=?', (proposal.proposal_id,)).fetchone():
                        continue
                    pending_sell = any(json.loads(p)['proposal'].get('ticker') == ticker and json.loads(p)['proposal'].get('side') == 'sell'
                                       for (p,) in db.execute("SELECT payload FROM approval_inbox WHERE status='PENDING'"))
                    if pending_sell:
                        continue  # the AI already asked you to sell this position
                    card = ApprovalCardRenderer().render(proposal, instrument_description='stock/ETF', max_loss_usd=D(0), holdings_after={},
                        trace_url=config.notifications.dashboard_url(f'trace/{proposal.proposal_id}', fragment=False))
                    if database_role(db) == 'live':
                        from agents.operator import MarketSchedule
                        expires = MarketSchedule().session_close(now)
                    else:
                        expires = now + timedelta(minutes=config.approval_expiry_minutes)
                    payload = {'id': proposal.proposal_id, 'status': 'PENDING', 'lane': 'A', 'author': 'Registered exit (no AI)',
                               'attribution': 'registered_backstop_not_ai', 'origin': 'registered_exit', 'exit_reason': reason,
                               'body': card.body, 'trace_url': card.trace_url, 'proposal': proposal.model_dump(mode='json'),
                               'quote': quote.model_dump(mode='json'), 'vol': str(vol[0]) if vol else None,
                               'vol_as_of': vol[1].isoformat() if vol else None, 'issued': now.isoformat(), 'expires': expires.isoformat(),
                               'comparison': 'Proposal-time counterfactual; excludes approval execution latency.'}
                    db.execute('INSERT INTO approval_inbox VALUES (?,?,?,?,?)', (proposal.proposal_id, 'PENDING', payload['issued'], payload['expires'], json.dumps(payload)))
                    results.append({'arm': arm, 'instrument': ticker, 'status': 'PENDING', 'side': 'sell', 'card_id': proposal.proposal_id, 'exit_reason': reason})
                else:
                    fill = inbox._execute(db, 'A', arm, proposal, quote, vol[0] if vol else None, vol[1] if vol else None, now)
                    db.execute('INSERT INTO decision_records(created_at,payload_json) VALUES (?,?)', (now.isoformat(), json.dumps({
                        'proposal_id': proposal.proposal_id, 'lane': 'A', 'track': arm, 'status': fill['status'], 'reasons': fill.get('reasons', []),
                        'author': 'Registered exit (no AI)', 'origin': 'registered_exit', 'exit_reason': reason})))
                    results.append({'arm': arm, 'instrument': ticker, 'status': fill['status'], 'side': 'sell', 'quantity': str(position['quantity']),
                                    'price': str(quote.bid), 'exit_reason': reason, 'reasons': fill.get('reasons', [])})
    return results
