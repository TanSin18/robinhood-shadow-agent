"""Runs the firm inside the existing scheduled daily service tick (never a second runner).

Disabled unless the operator created the trader database (``python -m agents.ai_trader.cli init``).
Every failure is caught and journaled; nothing here can fail, delay or write to the Official run,
and it only starts after today's Official cycle has COMPLETED.
"""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
MORNING_FROM, MORNING_UNTIL = time(10, 5), time(15, 30)
PROTECT_FROM, PROTECT_UNTIL = time(15, 50), time(15, 58)


def default_path(official_db):
    return Path(official_db).resolve().parents[2] / 'robinhood-diagnostics' / 'ai-trader' / 'trader.db'


def official_completed_today(official_db, day: str) -> bool:
    import sqlite3
    db = sqlite3.connect(f'file:{Path(official_db).resolve()}?mode=ro', uri=True)
    try:
        row = db.execute('SELECT status FROM cycle_runs WHERE day=?', (day,)).fetchone()
    except sqlite3.Error:
        return False
    finally:
        db.close()
    return bool(row) and row[0] == 'COMPLETED'


def parse_quotes(reads):
    out = {}
    for read in reads:
        for item in (read.get('data') or {}).get('results', []) or []:
            q = (item or {}).get('quote') or {}
            try:
                bid, ask = float(q['bid_price']), float(q['ask_price'])
                stamp = datetime.fromisoformat(q.get('updated_at') or min(q['venue_ask_time'], q['venue_bid_time']))
            except (KeyError, TypeError, ValueError):
                continue
            if q.get('symbol') and bid > 0 and ask > 0 and stamp.tzinfo is not None:
                out[q['symbol']] = {'bid': bid, 'ask': ask, 'ts': stamp}
    return out


def parse_history(read, today):
    closes, volumes = [], []
    for item in (read.get('data') or {}).get('results', []) or []:
        for b in item.get('bars', []) or []:
            try:
                day = datetime.fromisoformat(b['begins_at']).astimezone(ET).date()
                if day >= today or b.get('interpolated'):
                    continue
                closes.append((day.isoformat(), float(b['close_price'])))
                if b.get('volume') is not None:
                    volumes.append((day.isoformat(), float(b['volume'])))
            except (KeyError, TypeError, ValueError):
                continue
    return closes, volumes


def collect(call, symbols, now, *, history=True):
    """Read-only: quotes in chunks of 20, one 550-day history per symbol. Same gateway bounds as Official."""
    today = now.astimezone(ET).date()
    reads = [call('get_equity_quotes', {'symbols': list(symbols[i:i + 20])}) for i in range(0, len(symbols), 20)]
    closes, volumes = {}, {}
    if history:
        for s in symbols:
            r = call('get_equity_historicals', {'symbols': [s], 'start_time': (now - timedelta(days=550)).isoformat(),
                                                'end_time': now.isoformat(), 'interval': 'day', 'bounds': 'regular',
                                                'adjustment_type': 'split'})
            closes[s], volumes[s] = parse_history(r, today)
    return parse_quotes(reads), closes, volumes


def _next_session(day):
    from agents.operator import MarketSchedule
    d = datetime.fromisoformat(day).date()
    schedule = MarketSchedule()
    for k in range(1, 8):
        cand = d + timedelta(days=k)
        if schedule.should_run(datetime.combine(cand, time(10, 0), ET), asset_class='stock', stage=1):
            return cand.isoformat()
    return (d + timedelta(days=1)).isoformat()


def tick(inbox, config, now, *, reader_factory=None, client_factory=None, path=None):
    from agents.ai_trader import cycle
    from agents.ai_trader.spec import load_spec
    from agents.ai_trader.store import TraderStore
    from agents.safety_events import safety_stopped
    path = Path(path or default_path(inbox.path))
    if not path.is_file():
        return None                              # not set up: disabled
    if safety_stopped(inbox.path):
        return {'status': 'SKIPPED_SAFETY_STOP'}
    store = TraderStore(path, inbox.path)
    if store.mode() == 'RETIRED':
        return None
    spec = load_spec()
    local = now.astimezone(ET)
    day = local.date().isoformat()
    from agents.operator import MarketSchedule
    if not MarketSchedule().should_run(datetime.combine(local.date(), time(10, 0), ET), asset_class='stock', stage=1):
        return None
    t = local.time()
    attempts = int(store.meta(f'morning_attempts:{day}', '0'))
    want_morning = (MORNING_FROM <= t < MORNING_UNTIL and store.meta('morning_done') != day and attempts < 3
                    and official_completed_today(inbox.path, day))
    want_protect = PROTECT_FROM <= t < PROTECT_UNTIL and store.meta('protective_done') != day and store.mode() == 'PAPER'
    with store.connect() as db:
        awaiting = [r[0] for r in db.execute("SELECT ticket_id FROM operator_cards WHERE status='APPROVED_AWAITING_FILL'")]
    want_fill = bool(awaiting) and local.minute % 2 == 0
    if t >= MORNING_UNTIL:
        cycle.expire_cards(store, now)
    if not (want_morning or want_protect or want_fill):
        return None
    if want_morning:   # counted before any read, so a failing proxy can't cause endless retries
        store.set_meta(f'morning_attempts:{day}', str(attempts + 1))
    try:
        derived = config.model_copy(update={'risk': config.risk.model_copy(update={'instrument_whitelist': frozenset(spec.universe)})})
        if reader_factory is None:
            from agents.market_reader import LiveReader
            reader_factory = lambda: LiveReader(path, derived)   # incident latch lands beside the trader DB
        reader = reader_factory()
        try:
            symbols = list(spec.universe)
            quotes, closes, volumes = collect(reader.gateway.call, symbols, now, history=want_morning or want_protect)
        finally:
            reader.close()
        snap = {'session': day, 'next_session': _next_session(day), 'quotes': quotes, 'closes': closes, 'volumes': volumes}
        out = {}
        if want_fill:
            out['b_fills'] = cycle.fill_pending(store, spec, snap, now)
        if want_morning:
            client = (client_factory or (lambda: __import__('agents.ai_trader.model', fromlist=['x']).OpenAIResponsesClient()))()
            out['morning'] = cycle.morning(store, spec, snap, client, now)
            store.set_meta('morning_done', day)
        if want_protect:
            out['protective'] = cycle.protective(store, spec, snap, now)
            store.set_meta('protective_done', day)
        return json.loads(json.dumps(out, default=str))
    except Exception as error:   # never a Official failure; retried on a later tick inside the window
        store.journal('tick_failed', {'error_type': type(error).__name__}, now)
        return {'status': 'AI_TRADER_TICK_FAILED', 'error_type': type(error).__name__}
