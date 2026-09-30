"""Broad universe screen (SHADOW ONLY): S&P 500 constituents plus reviewed ETFs.

Operator-run after the close. It never trades, never writes the official
database and never changes what the official cycle sees. It:

1. loads a pinned universe file (built from two free issuer holdings files,
   keeping only tickers both list), recorded by SHA-256;
2. keeps a daily-bar cache in its own database (default data/universe.db).
   The first fill is 550 days, one symbol per call, capped per night; later
   nights fetch a short recent window;
3. applies the registered filters and strategy rules to completed sessions
   only, and records the full funnel and a shortlist of up to 30.

Broker access goes through the existing EffectiveReadGateway with a derived
config whose whitelist is exactly the pinned universe. Only
get_equity_historicals is used after the gateway's own account preflight, and
anything off-list is refused by the gateway itself.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
D = Decimal
SYMBOL = re.compile(r'^[A-Z]{1,5}(\.[A-Z])?$')
BOUNDS = {'shortlist': 30, 'verified': 20, 'ai_research': 8}
FILTERS = {'minimum_price_usd': D('5'), 'minimum_history_sessions': 253,
           'minimum_median_20d_dollar_volume_usd': D('50000000')}
BUDGET = {'max_calls': 600, 'max_seconds': 20 * 60, 'max_backfill_symbols': 120}
BACKFILL_DAYS, RECENT_DAYS = 550, 10
LEVERAGED_OR_INVERSE = re.compile(r'\b(2X|3X|ULTRA|INVERSE|SHORT|BEAR|BULL)\b', re.I)


class ScreenError(RuntimeError):
    pass


# ------------------------------------------------------------------ universe file
def _norm(symbol: str) -> str:
    return re.sub(r'[^A-Z]', '', symbol.upper())


def _robinhood_symbol(symbol: str) -> str | None:
    s = symbol.strip().upper().replace('/', '.').replace(' ', '.')
    return s if SYMBOL.match(s) else None


def parse_ivv_csv(text: str) -> list[str]:
    """iShares holdings CSV: preamble lines, then a header with Ticker and Asset Class."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith('Ticker,')), None)
    if start is None:
        raise ScreenError('IVV_HEADER_NOT_FOUND')
    rows = csv.DictReader(io.StringIO('\n'.join(lines[start:])))
    out = []
    for row in rows:
        if (row.get('Asset Class') or '').strip() == 'Equity':
            sym = _robinhood_symbol(row.get('Ticker') or '')
            if sym:
                out.append(sym)
    return out


def parse_spy_rows(rows: list[list[object]]) -> list[str]:
    """State Street daily holdings (xlsx rows): header row contains 'Ticker'."""
    start = next((i for i, row in enumerate(rows) if any(str(c).strip() == 'Ticker' for c in row if c is not None)), None)
    if start is None:
        raise ScreenError('SPY_HEADER_NOT_FOUND')
    col = [str(c).strip() if c is not None else '' for c in rows[start]].index('Ticker')
    out = []
    for row in rows[start + 1:]:
        if col < len(row) and row[col]:
            sym = _robinhood_symbol(str(row[col]))
            if sym and sym not in {'CASH', 'USD'}:
                out.append(sym)
    return out


def read_xlsx_rows(path) -> list[list[object]]:
    """Minimal stdlib reader for the first worksheet of an .xlsx file (strings and numbers only)."""
    import zipfile
    import xml.etree.ElementTree as ET_XML
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            for si in ET_XML.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', ns):
                shared.append(''.join(t.text or '' for t in si.iter('{%s}t' % ns['m'])))
        sheet = sorted(n for n in z.namelist() if n.startswith('xl/worksheets/sheet'))[0]
        rows = []
        for row in ET_XML.fromstring(z.read(sheet)).iter('{%s}row' % ns['m']):
            cells = []
            for c in row.findall('m:c', ns):
                col = sum((ord(ch) - 64) * 26 ** i for i, ch in enumerate(reversed(re.sub(r'\d', '', c.get('r', 'A')))))
                while len(cells) < col - 1:
                    cells.append(None)
                v = c.find('m:v', ns)
                inline = c.find('m:is', ns)
                if c.get('t') == 's' and v is not None:
                    cells.append(shared[int(v.text)])
                elif inline is not None:
                    cells.append(''.join(t.text or '' for t in inline.iter('{%s}t' % ns['m'])))
                else:
                    cells.append(v.text if v is not None else None)
            rows.append(cells)
    return rows


def build_universe(spy: list[str], ivv: list[str], *, as_of: str, etfs: list[str]) -> dict:
    """Keep only tickers both issuer files list; SPY's spelling wins."""
    ivv_norm = {_norm(s) for s in ivv}
    both = sorted({s for s in spy if _norm(s) in ivv_norm})
    only_spy = sorted({s for s in spy if _norm(s) not in ivv_norm})
    only_ivv = sorted({s for s in ivv if _norm(s) not in {_norm(x) for x in spy}})
    if len(both) < 450:
        raise ScreenError('CONSTITUENT_OVERLAP_TOO_SMALL')
    return {'as_of': as_of, 'source': 'SPY(State Street)+IVV(iShares) daily holdings; intersection',
            'label': 'SURVIVORSHIP-BIASED (current constituents only)',
            'stocks': both, 'etfs': sorted(set(etfs)), 'differences': {'only_spy': only_spy, 'only_ivv': only_ivv}}


def load_universe(path: Path) -> tuple[dict, str]:
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    symbols = data.get('stocks', []) + data.get('etfs', [])
    if not symbols or any(not isinstance(s, str) or not SYMBOL.match(s) for s in symbols) or len(set(symbols)) != len(symbols):
        raise ScreenError('UNIVERSE_FILE_INVALID')
    return data, hashlib.sha256(raw).hexdigest()


# ------------------------------------------------------------------ bar cache
class BarStore:
    def __init__(self, path: Path, official: Path | None = None):
        self.path = Path(path).resolve()
        if official is not None and (self.path == Path(official).resolve() or self.path.parent == Path(official).resolve().parent):
            # Own directory: any safety latch written by the gateway lands beside
            # this store, never beside the official database.
            raise ScreenError('SCREEN_STORE_MUST_HAVE_ITS_OWN_DIRECTORY')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS bars (symbol TEXT, day TEXT, close TEXT, volume TEXT, fetched_at TEXT, PRIMARY KEY(symbol, day))')
            db.execute('CREATE TABLE IF NOT EXISTS screen_runs (id INTEGER PRIMARY KEY, created_at TEXT, payload_json TEXT)')

    def connect(self):
        return sqlite3.connect(self.path, isolation_level=None)

    def last_day(self, symbol):
        with self.connect() as db:
            row = db.execute('SELECT max(day), count(*) FROM bars WHERE symbol=?', (symbol,)).fetchone()
        return row[0], row[1]

    def put(self, symbol, bars, fetched_at):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.executemany('INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?)',
                           [(symbol, d, str(c), None if v is None else str(v), fetched_at) for d, c, v in bars])
            db.execute('COMMIT')

    def closes(self, symbol):
        with self.connect() as db:
            return [(d, D(c), None if v is None else D(v)) for d, c, v in
                    db.execute('SELECT day, close, volume FROM bars WHERE symbol=? ORDER BY day', (symbol,))]

    def record(self, payload, now):
        with self.connect() as db:
            db.execute('INSERT INTO screen_runs(created_at, payload_json) VALUES (?,?)', (now.isoformat(), json.dumps(payload, default=str)))


def parse_bars(response, today: date):
    out = {}
    for item in (response.get('data') or {}).get('results', []) or []:
        if not isinstance(item, dict) or not isinstance(item.get('symbol'), str):
            continue
        rows = []
        for b in item.get('bars', []) or []:
            try:
                day = datetime.fromisoformat(b['begins_at']).astimezone(ET).date()
                if day >= today or b.get('interpolated'):
                    continue  # completed sessions only
                close = D(str(b['close_price']))
                volume = D(str(b['volume'])) if b.get('volume') is not None else None
                if close.is_finite() and close > 0:
                    rows.append((day.isoformat(), close, volume))
            except (KeyError, TypeError, ValueError, InvalidOperation):
                continue
        out[item['symbol']] = rows
    return out


def plan(symbols, store: BarStore, today: date, budget=BUDGET):
    backfill, incremental = [], []
    for s in symbols:
        last, count = store.last_day(s)
        if count < FILTERS['minimum_history_sessions'] or last is None:
            backfill.append(s)
        elif last < (today - timedelta(days=1)).isoformat():
            incremental.append(s)
    return {'backfill': backfill[:budget['max_backfill_symbols']], 'backfill_deferred': backfill[budget['max_backfill_symbols']:],
            'incremental': incremental}


def fetch(call, work, store: BarStore, now: datetime, budget=BUDGET, clock=time.monotonic):
    """Collect planned bars. Stops cleanly at the budget or the first provider error."""
    started, calls, done, stop = clock(), 0, [], None
    today = now.astimezone(ET).date()
    jobs = [(s, BACKFILL_DAYS) for s in work['backfill']] + [(s, RECENT_DAYS) for s in work['incremental']]
    for symbol, days in jobs:
        if calls >= budget['max_calls'] or clock() - started >= budget['max_seconds']:
            stop = 'BUDGET_REACHED'
            break
        calls += 1
        try:
            response = call('get_equity_historicals', {'symbols': [symbol], 'start_time': (now - timedelta(days=days)).isoformat(),
                                                       'end_time': now.isoformat(), 'interval': 'day', 'bounds': 'regular',
                                                       'adjustment_type': 'split'})
        except Exception as error:  # provider or gateway refusal: stop, never retry blindly
            stop = f'PROVIDER_ERROR:{type(error).__name__}'
            break
        bars = parse_bars(response, today).get(symbol, [])
        store.put(symbol, bars, now.isoformat())
        done.append(symbol)
    return {'calls': calls, 'fetched': len(done), 'seconds': round(clock() - started, 1), 'stopped': stop}


# ------------------------------------------------------------------ screen
def screen(universe: dict, store: BarStore, today: date):
    from research.strategy_signals import evaluate_daily_signals
    etfs = set(universe.get('etfs', []))
    symbols = universe.get('stocks', []) + universe.get('etfs', [])
    funnel = {'universe': len(symbols)}
    excluded = []
    closes_by = {}
    passed = []
    for s in symbols:
        rows = store.closes(s)
        reason = None
        if not rows:
            reason = 'NO_HISTORY_CACHED'
        elif LEVERAGED_OR_INVERSE.search(s):
            reason = 'LEVERAGED_OR_INVERSE'
        elif rows[-1][1] < FILTERS['minimum_price_usd']:
            reason = 'PRICE_BELOW_5'
        elif len(rows) < FILTERS['minimum_history_sessions']:
            reason = f'HISTORY_{len(rows)}_BELOW_253'
        else:
            last20 = rows[-20:]
            if len(last20) < 20 or any(v is None for _, _, v in last20):
                reason = 'VOLUME_EVIDENCE_MISSING'
            elif median([c * v for _, c, v in last20]) < FILTERS['minimum_median_20d_dollar_volume_usd']:
                reason = 'DOLLAR_VOLUME_BELOW_50M'
        if reason:
            excluded.append({'symbol': s, 'reason': reason})
            continue
        passed.append(s)
        closes_by[s] = {d: str(c) for d, c, _ in rows}
    for key in ('NO_HISTORY_CACHED', 'LEVERAGED_OR_INVERSE', 'PRICE_BELOW_5', 'HISTORY', 'VOLUME_EVIDENCE_MISSING', 'DOLLAR_VOLUME_BELOW_50M'):
        funnel['removed_' + key.lower()] = sum(e['reason'].startswith(key) for e in excluded)
    funnel['passed_filters'] = len(passed)
    assessment = evaluate_daily_signals(closes_by, etfs & set(passed), today)
    signals = assessment['signals']
    ranked = sorted(signals, key=lambda s: (-D(str(s.get('strength', '0'))), str(s['instrument'])))
    held_first = []  # held positions are merged by the morning run, not here
    shortlist = [{'symbol': s['instrument'], 'strategy': s['strategy'], 'strength': s['strength'],
                  'asset_class': 'etf' if s['instrument'] in etfs else 'stock'} for s in ranked][:BOUNDS['shortlist']]
    funnel['signals'] = len(signals)
    funnel['shortlist'] = len(shortlist) + len(held_first)
    return {'funnel': funnel, 'shortlist': shortlist, 'excluded': excluded,
            'strategy_blocked_counts': {k: len(v.get('blocked', {})) for k, v in assessment['strategies'].items()}}


# ------------------------------------------------------------------ CLI
def run(*, config, official: Path, universe_path: Path, store_path: Path, now=None, gateway_factory=None):
    from agents.safety_events import safety_stopped
    now = now or datetime.now(timezone.utc)
    if safety_stopped(official):
        raise ScreenError('OFFICIAL_SAFETY_STOP')
    universe, universe_hash = load_universe(universe_path)
    store = BarStore(store_path, official)
    today = now.astimezone(ET).date()
    symbols = universe['stocks'] + universe['etfs']
    work = plan(symbols, store, today)
    gateway, close = (gateway_factory or _live_gateway)(config, store.path, frozenset(symbols))
    try:
        collection = fetch(gateway.call, work, store, now)
    finally:
        close()
    result = screen(universe, store, today)
    payload = {'status': 'COMPLETED' if not (collection['stopped'] or '').startswith('PROVIDER') else 'PARTIAL',
               'mode': 'shadow_only_not_used_by_official_cycle', 'as_of_session': today.isoformat(),
               'universe_file_sha256': universe_hash, 'universe_as_of': universe.get('as_of'), 'label': universe.get('label'),
               'plan': {k: len(v) for k, v in work.items()}, 'collection': collection, **result,
               'bounds': BOUNDS, 'filters': {k: str(v) for k, v in FILTERS.items()}}
    store.record(payload, now)
    return payload


def _live_gateway(config, store_path, symbols):
    from agents.market_reader import LiveReader
    derived = config.model_copy(update={'risk': config.risk.model_copy(update={'instrument_whitelist': symbols})})
    # Evidence cache and any incident latch live beside the screen store.
    reader = LiveReader(store_path, derived)   # gateway preflight verifies the Agentic account first
    return reader.gateway, reader.close


def build_main(argv):
    parser = argparse.ArgumentParser(prog='universe_screen build')
    parser.add_argument('--spy-xlsx', required=True)
    parser.add_argument('--ivv-csv', required=True)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    from research.strategy_signals import ETF_UNIVERSE
    spy = parse_spy_rows(read_xlsx_rows(args.spy_xlsx))
    ivv = parse_ivv_csv(Path(args.ivv_csv).read_text(encoding='utf-8-sig'))
    universe = build_universe(spy, ivv, as_of=args.as_of, etfs=sorted(ETF_UNIVERSE))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(universe, indent=1, sort_keys=True) + '\n')
    print(json.dumps({'stocks': len(universe['stocks']), 'etfs': len(universe['etfs']),
                      'only_spy': universe['differences']['only_spy'], 'only_ivv': universe['differences']['only_ivv'],
                      'sha256': hashlib.sha256(out.read_bytes()).hexdigest()}, indent=2))
    return 0


def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'build':
        return build_main(sys.argv[2:])
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--config', required=True)
    parser.add_argument('--official-database', required=True)
    parser.add_argument('--universe', required=True)
    parser.add_argument('--store', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    from config.loader import load_config
    config = load_config(args.config)
    config.validate_runtime_ready()
    payload = run(config=config, official=Path(args.official_database), universe_path=Path(args.universe), store_path=Path(args.store))
    summary = {k: payload[k] for k in ('status', 'mode', 'as_of_session', 'universe_file_sha256', 'plan', 'collection', 'funnel')}
    summary['shortlist'] = [s['symbol'] for s in payload['shortlist']]
    print(json.dumps(summary, indent=2, default=str))
    return 0 if payload['status'] == 'COMPLETED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
