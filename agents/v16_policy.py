"""v1.6 amendment layer: realistic paper capital, options pause, same-day protective exit.

Byte-pinned like v1.5: inert unless ``preregistration-amendment-v1.6.0.yaml`` is
byte-identical to the operator-signed file pinned below, the effective time has
passed and v1.5 is active. Paper only; real orders stay blocked.

* Lane A (stocks/ETFs) paper capital becomes the amendment's value. The rebase
  happens once, at the first official v1.6 cycle: the build-phase Lane A state of
  every arm is archived (never deleted) and each arm starts fresh.
* Lane B (options): no new option buys; held contracts keep their AI exit or
  expiry settlement.
* Protective exit, 15:50–15:58 ET once per session inside the existing
  scheduled service tick (never a second runner): sells a Lane A holding when
  the fresh bid is at or below its 200-session average (completed closes), an ETF
  whose bid shows non-positive 126-session momentum, or any holding at least 8%
  below its average cost. Every check is recorded, fired or not.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

D = Decimal
ET = ZoneInfo('America/New_York')
APPROVED_V160_SHA256: str | None = '86c891cd44238bd45c77934447df6384b29b6532655da25bed5c21e8712887b0'  # operator-signed 2026-09-30 16:25 ET
V160_EFFECTIVE_FROM: datetime | None = datetime.fromisoformat('2026-10-01T09:30:00-04:00')
V160_AMENDMENT_NAME = 'preregistration-amendment-v1.6.0.yaml'
PROTECTIVE_WINDOW = (time(15, 50), time(15, 58))
IMMEDIATE_ARMS = ('agent_alone', 'deterministic_no_ai')
ARMS = ('agent_alone', 'with_approvals', 'deterministic_no_ai')


def _root(root):
    return Path(root) if root else Path(__file__).resolve().parents[1]


def v16_active(root=None, now=None, *, approved_sha256=None, effective_from=None) -> bool:
    approved = APPROVED_V160_SHA256 if approved_sha256 is None else approved_sha256
    effective = V160_EFFECTIVE_FROM if effective_from is None else effective_from
    if approved is None or effective is None:
        return False
    root, now = _root(root), now or datetime.now(timezone.utc)
    if now.tzinfo is None or now < effective:
        return False
    path = root / V160_AMENDMENT_NAME
    try:
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != approved:
            return False
        from agents.v15_activation import v15_active
        if not v15_active(root, now):
            return False
        return (amendment(root).get('amendment', {}).get('operator_signature') or {}).get('status') == 'SIGNED'
    except (OSError, ValueError, AttributeError):
        return False


def amendment(root=None) -> dict:
    import yaml
    return yaml.safe_load((_root(root) / V160_AMENDMENT_NAME).read_bytes()) or {}


def lane_a_capital(root=None) -> Decimal:
    value = D(str(amendment(root)['paper_capital']['lane_A_stocks_etfs_usd']))
    if not value.is_finite() or value <= 0:
        raise ValueError('invalid v1.6 lane A capital')
    return value


def hard_stop_fraction(root=None) -> Decimal:
    return D(str(amendment(root)['protective_exit']['hard_stop_below_average_cost']))


def options_buys_paused(root=None, now=None) -> bool:
    return v16_active(root, now)


# ------------------------------------------------------------------ capital rebase
def ensure_tables(db):
    db.execute('CREATE TABLE IF NOT EXISTS capital_rebases (version TEXT PRIMARY KEY, created_at TEXT, payload_json TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS protective_checks (day TEXT PRIMARY KEY, owner TEXT, started_at TEXT, '
               'finished_at TEXT, payload_json TEXT)')


def fresh_state(cash: Decimal) -> dict:
    return {'settled_cash': str(cash), 'unsettled_cash': '0', 'positions': {}, 'seen': [], 'fills': [],
            'peak': str(cash), 'start': str(cash), 'weekly_start_value': str(cash), 'peak_breaker_latched': False,
            'global_kill_switch': False, 'marks': {}, 'capital_version': '1.6.0'}


def rebase_lane_a(inbox, capital: Decimal, now: datetime) -> dict:
    """Idempotent: archive build-phase Lane A state and start every arm at ``capital``."""
    with inbox.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        ensure_tables(db)
        done = db.execute("SELECT payload_json FROM capital_rebases WHERE version='1.6.0'").fetchone()
        if done:
            return {'status': 'ALREADY_REBASED', **json.loads(done[0])}
        archived = {}
        for arm in ARMS:
            row = db.execute("SELECT payload FROM paper_accounts WHERE lane='A' AND track=?", (arm,)).fetchone()
            if row is not None:
                archived[arm] = json.loads(row[0])
            db.execute('INSERT OR REPLACE INTO paper_accounts VALUES (?,?,?)', ('A', arm, json.dumps(fresh_state(capital))))
        expired = []
        for card_id, payload in db.execute("SELECT id, payload FROM approval_inbox WHERE status IN ('PENDING','APPROVED_AWAITING_FILL')").fetchall():
            card = json.loads(payload)
            if card.get('lane') == 'A':
                card.update(status='EXPIRED_CAPITAL_REBASE', decided=now.isoformat())
                db.execute('UPDATE approval_inbox SET status=?, payload=? WHERE id=?', ('EXPIRED_CAPITAL_REBASE', json.dumps(card), card_id))
                expired.append(card_id)
        record = {'at': now.isoformat(), 'capital': str(capital), 'lane': 'A', 'archived_build_phase_state': archived,
                  'expired_cards': expired}
        db.execute('INSERT INTO capital_rebases VALUES (?,?,?)', ('1.6.0', now.isoformat(), json.dumps(record)))
        db.execute('INSERT INTO daily_values(created_at,payload_json) VALUES (?,?)', (now.isoformat(), json.dumps({
            'kind': 'capital_rebase', 'version': '1.6.0', 'lane': 'A', 'capital': str(capital), 'timestamp': now.isoformat()})))
    return {'status': 'REBASED', 'capital': str(capital), 'expired_cards': expired}


# ------------------------------------------------------------------ protective exit
class ProtectiveClaim:
    """One protective check per session; duck-types ``CycleLifecycle.owns``."""

    def __init__(self, path):
        self.path = Path(path)
        self.cycle_id = None

    def acquire(self, db, now):
        ensure_tables(db)
        day = now.astimezone(ET).date().isoformat()
        owner = f'protective-{day}-{uuid.uuid4().hex[:8]}'
        if db.execute('INSERT OR IGNORE INTO protective_checks VALUES (?,?,?,?,?)',
                      (day, owner, now.isoformat(), None, None)).rowcount != 1:
            return None
        self.cycle_id = owner
        return owner

    def owns(self, db, cycle_id):
        from agents.safety_events import safety_stopped
        if cycle_id is None or cycle_id != self.cycle_id or safety_stopped(self.path):
            return False
        return bool(db.execute('SELECT 1 FROM protective_checks WHERE owner=? AND finished_at IS NULL', (cycle_id,)).fetchone())

    def finish(self, db, payload, now):
        db.execute('UPDATE protective_checks SET finished_at=?, payload_json=? WHERE owner=?',
                   (now.isoformat(), json.dumps(payload, default=str), self.cycle_id))


def in_window(now) -> bool:
    local = now.astimezone(ET)
    from agents.operator import MarketSchedule
    try:
        close = MarketSchedule().session_close(now)
    except ValueError:
        return False  # not a trading day
    close_local = close.astimezone(ET)
    if close_local.date() != local.date():
        return False
    # Early-close sessions: the window is the last 10 minutes before the close.
    if close_local.time() < time(16, 0):
        start = close_local - timedelta(minutes=10)
        return start <= local < close_local - timedelta(minutes=2)
    return PROTECTIVE_WINDOW[0] <= local.time() < PROTECTIVE_WINDOW[1]


def features_from_bars(bars, today):
    closes = []
    for b in sorted(bars or [], key=lambda b: b.get('begins_at', '')):
        try:
            day = datetime.fromisoformat(b['begins_at']).astimezone(ET).date()
            if day < today and not b.get('interpolated'):
                closes.append(D(str(b['close_price'])))
        except (KeyError, TypeError, ValueError, ArithmeticError):
            continue
    out = {'completed_closes': len(closes)}
    if len(closes) >= 200:
        out['ma200'] = sum(closes[-200:], D(0)) / 200
    if len(closes) >= 126:
        out['close_126_sessions_ago'] = closes[-126]
    return out


def protective_reason(position, bid, feats, is_etf, stop_fraction):
    average = D(str(position.get('average_cost', '0')))
    if average > 0 and bid <= average * (1 - stop_fraction):
        return 'PROTECTIVE_STOP_BELOW_AVERAGE_COST'
    ma = feats.get('ma200')
    if ma is not None and bid <= ma:
        return 'LIVE_PRICE_AT_OR_BELOW_200_DAY_AVERAGE'
    anchor = feats.get('close_126_sessions_ago')
    if is_etf and anchor is not None and bid / anchor - 1 <= 0:
        return 'LIVE_MOMENTUM_126D_NOT_POSITIVE'
    return None


QUOTE_LEAD_SECONDS = 180      # a quote may be this much newer than the tick's start time (reader preflight + reads)


def protective_check(inbox, config, gateway_call, now, *, root=None, refresh=None):
    """Run once per session inside the window. ``gateway_call`` is the read gateway's call."""
    from agents.etf_exit import _sell
    from agents.etf_issuer import quotes_from_reads
    from research.strategy_signals import ETF_UNIVERSE
    claim = ProtectiveClaim(inbox.path)
    with inbox.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if claim.acquire(db, now) is None:
            return {'status': 'ALREADY_CHECKED_TODAY'}
    stop = hard_stop_fraction(root)
    held = {}
    for arm in ARMS:
        for ticker, position in inbox.state('A', arm)['positions'].items():
            held.setdefault(ticker, {})[arm] = position
    results, today = [], now.astimezone(ET).date()
    quotes = {}
    if held:
        reads = refresh(sorted(held)) if refresh else [gateway_call('get_equity_quotes', {'symbols': sorted(held)})]
        quotes = quotes_from_reads(reads)
    for ticker, by_arm in sorted(held.items()):
        quote = quotes.get(ticker)
        # `now` is when this service tick began; the quote is fetched after the reader's preflight, so it is
        # normally a few seconds NEWER than `now`. Judge it at its own time (bounded) instead of calling it stale.
        lead = (quote.timestamp - now).total_seconds() if quote is not None else 0
        at = quote.timestamp if quote is not None and 0 < lead <= QUOTE_LEAD_SECONDS else now
        if quote is None or quote.halted or not quote.bid > 0 or lead > QUOTE_LEAD_SECONDS \
                or not 0 <= (at - quote.timestamp).total_seconds() <= config.risk.max_quote_age_seconds:
            results.append({'instrument': ticker, 'status': 'HOLD', 'reason': 'FRESH_QUOTE_REQUIRED',
                            'quote_seconds_after_tick_start': round(lead, 1) if quote is not None else None})
            continue
        try:
            hist = gateway_call('get_equity_historicals', {'symbols': [ticker], 'start_time': (now - timedelta(days=400)).isoformat(),
                                'end_time': now.isoformat(), 'interval': 'day', 'bounds': 'regular', 'adjustment_type': 'split'})
            bars = next((i.get('bars') for i in (hist.get('data') or {}).get('results', []) if i and i.get('symbol') == ticker), [])
        except Exception as error:
            results.append({'instrument': ticker, 'status': 'HOLD', 'reason': f'HISTORY_UNAVAILABLE:{type(error).__name__}'})
            continue
        feats = features_from_bars(bars, today)
        for arm, position in sorted(by_arm.items()):
            reason = protective_reason(position, quote.bid, feats, ticker in ETF_UNIVERSE, stop)
            if reason is None:
                results.append({'arm': arm, 'instrument': ticker, 'status': 'HOLD', 'reason': 'NO_PROTECTIVE_TRIGGER',
                                'bid': str(quote.bid), 'ma200': str(feats.get('ma200')), 'average_cost': position.get('average_cost')})
                continue
            asset = 'etf' if ticker in ETF_UNIVERSE else 'stock'
            proposal = _sell(config, claim.cycle_id, ticker, arm, position['quantity'], quote, reason, asset_class=asset)
            with inbox.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if not claim.owns(db, claim.cycle_id):
                    raise ValueError('Protective check ownership is required')
                if arm in IMMEDIATE_ARMS:
                    fill = inbox._execute(db, 'A', arm, proposal, quote, None, None, at)
                    db.execute('INSERT INTO decision_records(created_at,payload_json) VALUES (?,?)', (now.isoformat(), json.dumps({
                        'proposal_id': proposal.proposal_id, 'lane': 'A', 'track': arm, 'status': fill['status'],
                        'reasons': fill.get('reasons', []), 'author': 'Protective exit (no AI)', 'origin': 'v16_protective_exit',
                        'exit_reason': reason})))
                    results.append({'arm': arm, 'instrument': ticker, 'status': fill['status'], 'side': 'sell',
                                    'quantity': str(position['quantity']), 'price': str(quote.bid), 'exit_reason': reason})
                else:
                    pending = any(json.loads(p)['proposal'].get('ticker') == ticker and json.loads(p)['proposal'].get('side') == 'sell'
                                  for (p,) in db.execute("SELECT payload FROM approval_inbox WHERE status='PENDING'"))
                    if pending:
                        results.append({'arm': arm, 'instrument': ticker, 'status': 'SELL_CARD_ALREADY_PENDING', 'exit_reason': reason})
                        continue
                    from agents.approval import ApprovalCardRenderer
                    from agents.operator import MarketSchedule
                    card = ApprovalCardRenderer().render(proposal, instrument_description='stock/ETF', max_loss_usd=D(0), holdings_after={},
                        trace_url=config.notifications.dashboard_url(f'trace/{proposal.proposal_id}', fragment=False))
                    payload = {'id': proposal.proposal_id, 'status': 'PENDING', 'lane': 'A', 'author': 'Protective exit (no AI)',
                               'attribution': 'v16_protective_exit_not_ai', 'origin': 'v16_protective_exit', 'exit_reason': reason,
                               'body': card.body, 'trace_url': card.trace_url, 'proposal': proposal.model_dump(mode='json'),
                               'quote': quote.model_dump(mode='json'), 'vol': None, 'vol_as_of': None, 'issued': now.isoformat(),
                               'expires': MarketSchedule().session_close(now).isoformat(),
                               'comparison': 'Proposal-time counterfactual; excludes approval execution latency.'}
                    db.execute('INSERT INTO approval_inbox VALUES (?,?,?,?,?)', (proposal.proposal_id, 'PENDING', payload['issued'], payload['expires'], json.dumps(payload)))
                    results.append({'arm': arm, 'instrument': ticker, 'status': 'PENDING', 'side': 'sell', 'card_id': proposal.proposal_id, 'exit_reason': reason})
    summary = {'status': 'CHECKED', 'at': now.isoformat(), 'held': sorted(held), 'hard_stop': str(stop), 'results': results}
    with inbox.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        claim.finish(db, summary, now)
        db.execute('INSERT INTO daily_values(created_at,payload_json) VALUES (?,?)', (now.isoformat(), json.dumps({
            'kind': 'protective_check', 'timestamp': now.isoformat(), 'fired': sum(1 for r in results if r.get('side') == 'sell'),
            'held': sorted(held)})))
    return summary


def checked_today(inbox, now) -> bool:
    with inbox.connect() as db:
        ensure_tables(db)
        return bool(db.execute('SELECT 1 FROM protective_checks WHERE day=?', (now.astimezone(ET).date().isoformat(),)).fetchone())


def record_protective_failure(inbox, now, error) -> dict:
    """A failed attempt releases nothing and is recorded; the next tick in the window retries."""
    payload = {'kind': 'protective_check', 'status': 'FAILED', 'error_type': type(error).__name__, 'timestamp': now.isoformat()}
    with inbox.connect() as db:
        ensure_tables(db)
        day = now.astimezone(ET).date().isoformat()
        # Drop an unfinished claim so the next tick can retry (completed checks are never removed).
        db.execute('DELETE FROM protective_checks WHERE day=? AND finished_at IS NULL', (day,))
        db.execute('INSERT INTO daily_values(created_at,payload_json) VALUES (?,?)', (now.isoformat(), json.dumps(payload)))
    return payload
