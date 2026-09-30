"""v1.5 desk-policy ETF issuance across three paper arms.

Inert unless ``agents.v15_activation.v15_active`` is true for the installed
registration. Uses the pure planner in ``agents.etf_desk_policy`` separately
for each arm's own cash, holdings and risk context. Paper only: no broker
writes, no model calls. Cards are authored "Desk rule (no AI)" and fill only
at a fresh approval-time quote within the registered limit and cutoff.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from statistics import median

from agents.etf_desk_policy import plan_entry
from agents.inbox import DESK_AUTHOR
from agents.schemas import TradeProposal
from broker.models import Quote

D = Decimal
IMMEDIATE_ARMS = ('agent_alone', 'deterministic_no_ai')
APPROVAL_ARM = 'with_approvals'
SLIPPAGE = D('0.001')
# Set True only by the reviewed activation release if the operator-approved
# v1.5 registration contains the interim live-spread liquidity rule.
LIQUIDITY_INTERIM_LIVE_SPREAD = False
SPREAD_SESSIONS_REQUIRED = 20


def spread_fraction(quote: Quote) -> Decimal | None:
    if not (quote.bid.is_finite() and quote.ask.is_finite()) or quote.bid <= 0 or quote.ask < quote.bid:
        return None
    mid = (quote.bid + quote.ask) / 2
    return (quote.ask - quote.bid) / mid


def ensure_liquidity_table(db) -> None:
    db.execute('CREATE TABLE IF NOT EXISTS liquidity_observations (day TEXT, symbol TEXT, '
               'spread_fraction TEXT, observed_at TEXT, cycle_id TEXT, PRIMARY KEY(day, symbol))')


def record_spreads(db, day: str, quotes: dict, observed_at: datetime, cycle_id: str) -> int:
    """One first observation per symbol per trading day; never overwritten."""
    ensure_liquidity_table(db)
    written = 0
    for symbol, quote in sorted(quotes.items()):
        fraction = spread_fraction(quote)
        if fraction is None or quote.halted:
            continue
        written += db.execute('INSERT OR IGNORE INTO liquidity_observations VALUES (?,?,?,?,?)',
                              (day, symbol, str(fraction), observed_at.isoformat(), cycle_id)).rowcount
    return written


def median_recorded_spread(db, symbol: str, before_day: str) -> Decimal | None:
    ensure_liquidity_table(db)
    rows = db.execute('SELECT spread_fraction FROM liquidity_observations WHERE symbol=? AND day<? '
                      'ORDER BY day DESC LIMIT ?', (symbol, before_day, SPREAD_SESSIONS_REQUIRED)).fetchall()
    if len(rows) < SPREAD_SESSIONS_REQUIRED:
        return None
    return D(str(median(D(r[0]) for r in rows)))


def liquidity_spread(recorded: Decimal | None, reference: Quote, current: Quote) -> Decimal | None:
    if recorded is not None:
        return recorded
    if not LIQUIDITY_INTERIM_LIVE_SPREAD:
        return None
    spreads = [spread_fraction(reference), spread_fraction(current)]
    return None if any(s is None for s in spreads) else max(spreads)


def issue_desk_entry(inbox, config, *, signal, snapshot, evaluated_at, now, cycle_id,
                     lifecycle=None, approved_ai_stock_pick=False, entry_slot_used=False,
                     holdings_review_complete=True, recorded_spread=None):
    """Plan and issue one Lane A desk-policy ETF entry. Returns per-arm results."""
    symbol = str(signal.get('instrument'))
    quote = snapshot['quotes'].get(symbol)
    vol = snapshot['vols'].get(symbol)
    if quote is None or vol is None:
        return [{'arm': arm, 'status': 'BLOCKED', 'reason': 'MISSING_DATA', 'instrument': symbol,
                 'attribution': 'desk_policy_not_ai'} for arm in (*IMMEDIATE_ARMS, APPROVAL_ARM)]
    spread = liquidity_spread(recorded_spread, quote, quote)
    dollar_volume = snapshot.get('median_dollar_volume_20d', {}).get(symbol)
    results = []
    with inbox.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        from data.database_role import database_role
        if database_role(db) == 'live' and (lifecycle is None or not lifecycle.owns(db, cycle_id)):
            raise ValueError('Live cycle ownership is required')
        for arm in (*IMMEDIATE_ARMS, APPROVAL_ARM):
            state = inbox.state('A', arm, db)
            context = inbox._context(state, quote, vol[0], vol[1], now)
            plan = plan_entry(symbol=symbol, quote=quote, reference_quote=quote, evaluated_at=evaluated_at,
                              now=now, holdings_review_complete=holdings_review_complete,
                              approved_ai_stock_pick=approved_ai_stock_pick, entry_slot_used=entry_slot_used,
                              median_spread_fraction=spread, median_dollar_volume=dollar_volume,
                              context=context, risk_config=config.risk, signal=signal, cycle_id=cycle_id)
            if plan['status'] != 'ELIGIBLE':
                results.append({'arm': arm, 'instrument': symbol, **plan})
                continue
            proposal = TradeProposal.model_validate(plan['proposal'])
            if arm in IMMEDIATE_ARMS:
                fill = inbox._execute(db, 'A', arm, proposal, quote, vol[0], vol[1], now,
                                      etf_entry_reference=D(plan['reference_midpoint']))
                if fill.get('status') == 'filled':
                    fill = {**fill, 'origin': 'official_open', 'attribution': 'desk_policy_not_ai'}
                db.execute('INSERT INTO decision_records(created_at,payload_json) VALUES (?,?)',
                           (now.isoformat(), json.dumps({'proposal_id': proposal.proposal_id, 'lane': 'A',
                            'track': arm, 'status': fill['status'], 'reasons': fill.get('reasons', []),
                            'author': DESK_AUTHOR, 'origin': 'official_open'})))
                results.append({'arm': arm, 'instrument': symbol, 'status': fill['status'],
                                'reasons': fill.get('reasons', []), 'quantity': plan['quantity'],
                                'limit_price': plan['limit_price'], 'attribution': 'desk_policy_not_ai'})
            else:
                card = inbox.issue_desk_card(db, proposal, quote, vol, plan, now)
                results.append({'arm': arm, 'instrument': symbol, 'status': card['status'], 'card_id': card['id'],
                                'quantity': plan['quantity'], 'limit_price': plan['limit_price'],
                                'expires_at': plan['expires_at'], 'attribution': 'desk_policy_not_ai'})
    return results


def quotes_from_reads(reads) -> dict:
    quotes = {}
    for read in reads:
        if read.get('tool') != 'get_equity_quotes':
            continue
        for item in (read.get('data') or {}).get('results', []) or []:
            q = (item or {}).get('quote') or {}
            try:
                bid, ask = D(q['bid_price']), D(q['ask_price'])
                stamp = datetime.fromisoformat(q.get('updated_at') or min(q['venue_ask_time'], q['venue_bid_time']))
            except (KeyError, TypeError, ValueError, ArithmeticError):
                continue
            if not q.get('symbol') or bid <= 0 or ask <= 0 or stamp.tzinfo is None:
                continue
            quotes[q['symbol']] = Quote(ticker=q['symbol'], bid=bid, ask=ask, timestamp=stamp,
                                        halted=q.get('state', 'active') != 'active' or q.get('has_traded', True) is False)
    return quotes


def approval_fill_tick(inbox, reader, now) -> list:
    """Fill operator-approved desk cards at a fresh quote. Read-only quotes only."""
    waiting = [c for c in inbox.cards() if c.get('status') == 'APPROVED_AWAITING_FILL']
    if not waiting:
        return []
    symbols = sorted({c['proposal']['ticker'] for c in waiting})
    quotes = quotes_from_reads(reader.refresh(now, symbols, []))
    return inbox.fill_approved_desk_cards(quotes, now)
