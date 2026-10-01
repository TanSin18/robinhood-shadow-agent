"""Runs the analyst desk inside the existing daily service tick (never a second runner).

Disabled until the operator runs ``python -m agents.analyst.cli init``. Two jobs a trading day:
  * morning (10:05-12:00 ET, after today's Official run COMPLETED): commentary on the official
    decision plus news and sentiment notes. No broker reads.
  * after the close (16:15-18:00 ET): read-only daily bars for the 23 registered names, retrain the
    regime model, compute shadow Kelly sizes and the daily auction read, fetch news, write the
    close commentary.
Every failure is caught and journaled; nothing here can fail, delay or write to the Official run.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from . import auction, commentary, guard, kelly, news, regime, team
from .store import AnalystStore, default_path

ET = ZoneInfo('America/New_York')
MORNING_FROM, MORNING_UNTIL = time(10, 5), time(12, 0)
CLOSE_FROM, CLOSE_UNTIL = time(16, 15), time(18, 0)
MAX_ATTEMPTS = 2
UNIVERSE = ('AAPL', 'AMZN', 'GLD', 'GOOGL', 'META', 'MSFT', 'NVDA', 'QQQ', 'SOXX', 'SPY', 'TLT', 'VTI', 'XLB', 'XLC', 'XLE',
            'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLU', 'XLV', 'XLY')
STOCKS = ('AAPL', 'AMZN', 'GOOGL', 'META', 'MSFT', 'NVDA')


def spec():
    return SimpleNamespace(models={'commentary': commentary.MODEL}, envelopes={'commentary': commentary.ENVELOPE},
                           daily_budget=Decimal(commentary.DAILY_CAP_USD))


# ------------------------------------------------------------------ official records (read-only)
def _ro(official_db):
    return sqlite3.connect(f'file:{Path(official_db).resolve()}?mode=ro', uri=True, timeout=1)


def official_completed_today(official_db, day):
    db = _ro(official_db)
    try:
        row = db.execute('SELECT status FROM cycle_runs WHERE day=?', (day,)).fetchone()
    except sqlite3.Error:
        return False
    finally:
        db.close()
    return bool(row) and row[0] == 'COMPLETED'


def official_view(official_db):
    """Latest decision capsule and paper holdings, reduced to what commentary needs. Read-only."""
    db = _ro(official_db)
    try:
        cap = db.execute('SELECT payload FROM decision_capsules ORDER BY created_at DESC LIMIT 1').fetchone()
        accts = db.execute('SELECT lane, track, payload FROM paper_accounts').fetchall()
    except sqlite3.Error:
        cap, accts = None, []
    finally:
        db.close()
    out = {'decision': None, 'features': {}, 'signals': [], 'holdings': [], 'closes': {}}
    if cap:
        c = json.loads(cap[0])
        d = (c.get('outcome') or {}).get('decision') or {}
        out['decision'] = {'type': d.get('type'), 'reason': d.get('reason'), 'reason_code': d.get('reason_code'),
                           'signal_instruments': d.get('signal_instruments') or [], 'observed_at': c.get('observed_at')}
        a = c.get('strategy_assessment') or {}
        for t, f in (a.get('features') or {}).items():
            def g(k):
                try:
                    return round(float(f.get(k)), 4)
                except (TypeError, ValueError):
                    return None
            price, ma = g('price'), g('ma200')
            out['features'][t] = {'price': price, 'pct_vs_ma200': round((price / ma - 1) * 100, 2) if price and ma else None,
                                  'momentum_126d_pct': round(g('momentum_126d') * 100, 2) if g('momentum_126d') is not None else None,
                                  'one_day_pct': round(g('one_day_return') * 100, 2) if g('one_day_return') is not None else None}
        out['signals'] = [s.get('instrument') for s in a.get('signals') or [] if s.get('instrument')]
        out['closes'] = (c.get('inputs') or {}).get('session_closes') or {}
    for lane, track, payload in accts:
        st = json.loads(payload)
        for t, p in (st.get('positions') or {}).items():
            mark = (st.get('marks') or {}).get(t)
            buys = sorted(str(f.get('timestamp')) for f in st.get('fills') or [] if f.get('ticker') == t and f.get('side') == 'buy')
            entry = None
            if buys:
                try:
                    entry = datetime.fromisoformat(buys[-1]).astimezone(ET).date().isoformat()
                except ValueError:
                    entry = None
            out['holdings'].append({'account': f'{lane}:{track}', 'ticker': t, 'quantity': float(p.get('quantity') or 0),
                                    'average_cost': float(p.get('average_cost') or 0), 'last_bid': float(mark) if mark else None,
                                    'entry_day': entry})
    return out


# ------------------------------------------------------------------ market data
def parse_bars(read, now):
    """Daily bars keyed by their real session date (begins_at is 00:00 UTC of the session, so the UTC date is
    the session). Today's bar is kept only after 16:15 ET, when the session is complete."""
    today = now.astimezone(ET).date()
    late = now.astimezone(ET).time() >= CLOSE_FROM
    out = []
    for item in (read.get('data') or {}).get('results', []) or []:
        for b in item.get('bars', []) or []:
            try:
                day = datetime.fromisoformat(b['begins_at'].replace('Z', '+00:00')).astimezone(timezone.utc).date()
                if b.get('interpolated') or day > today or (day == today and not late):
                    continue
                f = lambda k: float(b[k]) if b.get(k) is not None else None
                out.append({'day': day.isoformat(), 'open': f('open_price'), 'high': f('high_price'), 'low': f('low_price'),
                            'close': f('close_price'), 'volume': f('volume')})
            except (KeyError, TypeError, ValueError):
                continue
    dedup = {b['day']: b for b in out if b['close']}
    return [dedup[d] for d in sorted(dedup)]


def long_history(official_db, symbol='VTI'):
    """Older closes from the research backfill (robinhood-diagnostics/backtest/bars.csv), whose stored dates are one
    day early (known 00:00 UTC labelling issue), so each is moved to its real session."""
    path = Path(official_db).resolve().parents[2] / 'robinhood-diagnostics' / 'backtest' / 'bars.csv'
    out = []
    try:
        with path.open() as fh:
            for r in csv.DictReader(fh):
                if r.get('symbol') == symbol:
                    out.append(((date.fromisoformat(r['day']) + timedelta(days=1)).isoformat(), float(r['close'])))
    except (OSError, ValueError, KeyError):
        return []
    return out


def merged_closes(older, recent):
    m = dict(older)
    m.update(recent)                      # gateway bars win where both exist
    return sorted(m.items())


def read_bars(reader_factory, path, config, now, symbols=UNIVERSE):
    derived = config.model_copy(update={'risk': config.risk.model_copy(update={'instrument_whitelist': frozenset(symbols)})})
    if reader_factory is None:
        from agents.market_reader import LiveReader
        reader_factory = lambda: LiveReader(path, derived)   # incident latch lands beside the analyst DB
    reader = reader_factory()
    try:
        bars = {}
        for s in symbols:
            r = reader.gateway.call('get_equity_historicals', {'symbols': [s], 'start_time': (now - timedelta(days=550)).isoformat(),
                                                               'end_time': now.isoformat(), 'interval': 'day', 'bounds': 'regular',
                                                               'adjustment_type': 'split'})
            bars[s] = parse_bars(r, now)
        return bars
    finally:
        reader.close()


# ------------------------------------------------------------------ jobs
def _contact(path):
    try:
        line = (Path(path).parent / 'contact.txt').read_text().strip().splitlines()[0]
        return line if '@' in line and len(line) < 200 else None
    except (OSError, IndexError):
        return None


def _seat_spec(seat):
    return SimpleNamespace(models={seat: team.MODELS[seat]}, envelopes={seat: team.ENVELOPES[seat]},
                           daily_budget=Decimal(commentary.DAILY_CAP_USD))


def _note(store, kind, pkt, client, day, now, prices=None):
    """The whole team writes, in order; Bubbles' note is the one stored under the job's own kind."""
    report = team.run(store, kind, pkt, client, day, now, spec_factory=_seat_spec, prices=prices)
    b = report.get('bubbles') or {}
    return {'status': b.get('status', 'NOT_RUN'), 'flags': b.get('flags', []), 'team': report}


def morning(store, official_db, now, client, *, opener=None, prices=None, contact=None):
    day = now.astimezone(ET).date().isoformat()
    view = official_view(official_db)
    held = sorted({h['ticker'] for h in view['holdings']})
    tickers = list(dict.fromkeys(held + view['signals'] + list(STOCKS) + ['SPY', 'QQQ']))
    items, problems = news.collect(tickers, now, contact=contact, opener=opener)
    store.add('news', day, {'items': items, 'problems': problems}, now, kind='morning')
    reg, kel, auc, grd = store.latest('regimes'), store.latest('kelly'), store.latest('auction'), store.latest('guard') or {}
    pkt = commentary.packet('morning', decision=view['decision'], features=view['features'], regime=reg,
                            guard=grd.get('exits'), chop=grd.get('chop'),
                            kelly=(kel or {}).get('tickers'), auction=(auc or {}).get('tickers'), holdings=view['holdings'], headlines=items)
    return {'news_items': len(items), 'news_problems': len(problems), 'note': _note(store, 'morning', pkt, client, day, now, prices)}


def close(store, official_db, config, now, client, *, reader_factory=None, opener=None, prices=None, contact=None):
    day = now.astimezone(ET).date().isoformat()
    bars = read_bars(reader_factory, store.path, config, now)
    vti = merged_closes(long_history(official_db), [(b['day'], b['close']) for b in bars.get('VTI') or []])
    fit = regime.fit(regime.log_returns(vti))
    labels = fit.pop('_labels', {}) if isinstance(fit, dict) else {}
    prev = store.latest('regimes')
    fit['stability_vs_last_fit'] = regime.stability(fit, prev)
    store.add('regimes', day, fit, now)
    sizes = {}
    for t in UNIVERSE:
        closes = [(b['day'], b['close']) for b in bars.get(t) or []]
        if t in ('VTI',) or t not in STOCKS:
            closes = merged_closes(long_history(official_db, t), closes)
        sizes[t] = kelly.size(closes, labels, fit.get('current'))
    store.add('kelly', day, {'method': 'continuous Kelly mean/variance of daily excess return over 4% cash; half-Kelly; disciplined = 0 '
                                       'unless t-stat >= 2 both in the regime and over all history, capped at the registered 25% position limit; regime = sessions with the same '
                                       'in-sample HMM label (look-ahead: labels use the whole sample)',
                             'regime': fit.get('current'), 'tickers': sizes}, now)
    reads = {t: auction.read(bars.get(t) or []) for t in UNIVERSE}
    store.add('auction', day, {'tickers': reads}, now)
    view = official_view(official_db)
    chop = {t: guard.chop_label(bars.get(t) or []) for t in UNIVERSE}
    exits = [guard.exit_guard(h, bars.get(h['ticker']) or [], fit) for h in view['holdings']]
    previous = store.latest('guard') or {}
    first_sells = {(e['account'], e['ticker']) for e in previous.get('exits') or [] if e.get('verdict') == 'WOULD_SELL'}
    for e in exits:   # remember the first "would sell" price so the record can show later what it saved or cost
        e['first_would_sell'] = next((p.get('first_would_sell') for p in previous.get('exits') or []
                                      if (p.get('account'), p.get('ticker')) == (e['account'], e['ticker']) and p.get('first_would_sell')), None)
        if e.get('verdict') == 'WOULD_SELL' and not e['first_would_sell'] and (e['account'], e['ticker']) not in first_sells:
            e['first_would_sell'] = {'day': day, 'price': e.get('last_close'), 'rules': e.get('triggers')}
    entries = (view['decision'] or {}).get('signal_instruments') or []
    gate = [{'ticker': t, 'label': (chop.get(t) or {}).get('label'), 'would_block': (chop.get(t) or {}).get('gate') == 'sit out'} for t in entries]
    store.add('guard', day, {'exits': exits, 'chop': chop, 'entry_gate': gate}, now)
    movers = sorted((a for a in reads.items() if a[1].get('status') == 'OK'), key=lambda kv: -abs(kv[1]['change_pct']))[:5]
    tickers = list(dict.fromkeys(sorted({h['ticker'] for h in view['holdings']}) + [t for t, _ in movers] + ['SPY', 'QQQ']))
    items, problems = news.collect(tickers, now, contact=contact, opener=opener)
    store.add('news', day, {'items': items, 'problems': problems}, now, kind='close')
    pkt = commentary.packet('close', decision=view['decision'], regime=fit, kelly=sizes, guard=exits, chop=chop,
                            auction={t: a for t, a in reads.items() if t in tickers or t in ('VTI', 'SPY', 'QQQ')},
                            holdings=view['holdings'], headlines=items)
    return {'regime': fit.get('current'), 'regime_status': fit.get('status'), 'bars': {t: len(b) for t, b in bars.items() if len(b) < 200},
            'news_items': len(items), 'note': _note(store, 'close', pkt, client, day, now, prices)}


def tick(inbox, config, now, *, reader_factory=None, client_factory=None, path=None, opener=None):
    from agents.safety_events import safety_stopped
    path = Path(path or default_path(inbox.path))
    if not path.is_file():
        return None                                   # not set up: disabled
    if safety_stopped(inbox.path):
        return None
    store = AnalystStore(path, inbox.path)
    if store.meta('paused') == '1':
        return None
    local = now.astimezone(ET)
    day = local.date().isoformat()
    from agents.operator import MarketSchedule
    if not MarketSchedule().should_run(datetime.combine(local.date(), time(10, 0), ET), asset_class='stock', stage=1):
        return None
    t = local.time()
    jobs = []
    if MORNING_FROM <= t < MORNING_UNTIL and store.meta('morning_done') != day and int(store.meta(f'morning_attempts:{day}', '0')) < MAX_ATTEMPTS \
            and official_completed_today(inbox.path, day):
        jobs.append('morning')
    if CLOSE_FROM <= t < CLOSE_UNTIL and store.meta('close_done') != day and int(store.meta(f'close_attempts:{day}', '0')) < MAX_ATTEMPTS:
        jobs.append('close')
    if not jobs:
        return None
    out = {}
    contact = _contact(path)
    for job in jobs:
        key = f'{job}_attempts:{day}'
        store.set_meta(key, str(int(store.meta(key, '0')) + 1))   # counted first: a failing feed can't cause endless retries
        try:
            client = (client_factory or (lambda: __import__('agents.ai_trader.model', fromlist=['x']).OpenAIResponsesClient()))()
            if job == 'morning':
                out[job] = morning(store, inbox.path, now, client, opener=opener, contact=contact)
            else:
                out[job] = close(store, inbox.path, config, now, client, reader_factory=reader_factory, opener=opener, contact=contact)
            store.set_meta(f'{job}_done', day)
        except Exception as error:   # never an Official failure
            store.journal(f'{job}_failed', {'error_type': type(error).__name__}, now)
            out[job] = {'status': 'ANALYST_JOB_FAILED', 'error_type': type(error).__name__}
    return json.loads(json.dumps(out, default=str))
