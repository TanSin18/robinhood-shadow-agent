"""Read-only long-history backfill for the backtest (research only; never trades).

Walks each reviewed ETF backwards through the read gateway in windows the gateway
allows (at most 550 days, daily, regular hours, split-adjusted) until the provider
returns no bars or the floor date is reached. Writes to its own SQLite store in its
own directory, so any gateway safety latch lands beside the store, never beside the
official database. Stops cleanly on the first provider error or at the budget.

    python -m research.history_backfill --config <settings.local.yaml> \
        --official-database <agent.db> --store <dir>/history.db [--floor 2005-01-01]

Then export with ``--export <dir>/bars.csv`` (no broker access needed).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
D = Decimal
WINDOW_DAYS = 540          # inside the gateway's 550-day bound
BUDGET = {'max_calls': 400, 'max_seconds': 1500}
DEFAULT_FLOOR = date(2005, 1, 1)


class BackfillError(RuntimeError):
    pass


class HistoryStore:
    def __init__(self, path: Path, official: Path | None = None):
        self.path = Path(path).resolve()
        if official is not None:
            official = Path(official).resolve()
            if self.path == official or self.path.parent == official.parent:
                raise BackfillError('HISTORY_STORE_MUST_HAVE_ITS_OWN_DIRECTORY')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS bars (symbol TEXT, day TEXT, open TEXT, close TEXT, '
                       'volume TEXT, fetched_at TEXT, PRIMARY KEY(symbol, day))')
            db.execute('CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, created_at TEXT, payload_json TEXT)')

    def connect(self):
        return sqlite3.connect(self.path, isolation_level=None)

    def put(self, symbol, rows, fetched_at):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.executemany('INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?)',
                           [(symbol, d, None if o is None else str(o), str(c), None if v is None else str(v), fetched_at)
                            for d, o, c, v in rows])
            db.execute('COMMIT')

    def first_day(self, symbol):
        with self.connect() as db:
            return db.execute('SELECT min(day) FROM bars WHERE symbol=?', (symbol,)).fetchone()[0]

    def record(self, payload, now):
        with self.connect() as db:
            db.execute('INSERT INTO runs(created_at,payload_json) VALUES (?,?)', (now.isoformat(), json.dumps(payload, default=str)))

    def rows(self):
        with self.connect() as db:
            return db.execute('SELECT symbol, day, open, close, volume FROM bars ORDER BY symbol, day').fetchall()


def parse(response, today: date):
    out = []
    for item in (response.get('data') or {}).get('results', []) or []:
        if not isinstance(item, dict):
            continue
        for b in item.get('bars', []) or []:
            try:
                day = datetime.fromisoformat(b['begins_at']).astimezone(ET).date()
                if day >= today or b.get('interpolated'):
                    continue
                close = D(str(b['close_price']))
                opened = D(str(b['open_price'])) if b.get('open_price') is not None else None
                volume = D(str(b['volume'])) if b.get('volume') is not None else None
                if close.is_finite() and close > 0:
                    out.append((day.isoformat(), opened, close, volume))
            except (KeyError, TypeError, ValueError, InvalidOperation):
                continue
    return out


def windows(now: datetime, floor: date):
    end = now
    while end.date() > floor:
        start = max(end - timedelta(days=WINDOW_DAYS), datetime.combine(floor, datetime.min.time(), timezone.utc))
        yield start, end
        end = start - timedelta(seconds=1)


def backfill(call, symbols, store: HistoryStore, now: datetime, *, floor=DEFAULT_FLOOR, budget=BUDGET, clock=time.monotonic):
    started, calls, stop = clock(), 0, None
    today = now.astimezone(ET).date()
    per_symbol = {}
    for symbol in symbols:
        got = 0
        for start, end in windows(now, floor):
            if calls >= budget['max_calls'] or clock() - started >= budget['max_seconds']:
                stop = 'BUDGET_REACHED'
                break
            calls += 1
            try:
                response = call('get_equity_historicals', {'symbols': [symbol], 'start_time': start.isoformat(),
                                 'end_time': end.isoformat(), 'interval': 'day', 'bounds': 'regular',
                                 'adjustment_type': 'split'})
            except Exception as error:  # never retry blindly
                stop = f'PROVIDER_ERROR:{type(error).__name__}'
                break
            rows = parse(response, today)
            if not rows:
                break  # history exhausted for this symbol
            store.put(symbol, rows, now.isoformat())
            got += len(rows)
        per_symbol[symbol] = {'bars': got, 'first_day': store.first_day(symbol)}
        if stop:
            break
    return {'calls': calls, 'seconds': round(clock() - started, 1), 'stopped': stop, 'symbols': per_symbol}


def export(store: HistoryStore, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', newline='') as handle:
        w = csv.writer(handle)
        w.writerow(['symbol', 'day', 'open', 'close', 'volume'])
        w.writerows(store.rows())
    return hashlib.sha256(out.read_bytes()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--store', required=True)
    parser.add_argument('--export')
    parser.add_argument('--config')
    parser.add_argument('--official-database')
    parser.add_argument('--floor', default=DEFAULT_FLOOR.isoformat())
    args = parser.parse_args(argv)
    os.umask(0o077)
    if args.export and not args.config:
        store = HistoryStore(Path(args.store))
        print(json.dumps({'export': args.export, 'sha256': export(store, Path(args.export))}))
        return 0
    if not (args.config and args.official_database):
        parser.error('--config and --official-database are required to fetch')
    from agents.safety_events import safety_stopped
    from config.loader import load_config
    from research.strategy_signals import ETF_UNIVERSE
    official = Path(args.official_database)
    if safety_stopped(official):
        raise BackfillError('OFFICIAL_SAFETY_STOP')
    store = HistoryStore(Path(args.store), official)
    config = load_config(args.config)
    config.validate_runtime_ready()
    symbols = sorted(ETF_UNIVERSE)
    derived = config.model_copy(update={'risk': config.risk.model_copy(update={'instrument_whitelist': frozenset(symbols)})})
    from agents.market_reader import LiveReader
    reader = LiveReader(store.path, derived)   # preflight verifies the Agentic account first
    now = datetime.now(timezone.utc)
    try:
        result = backfill(reader.gateway.call, symbols, store, now, floor=date.fromisoformat(args.floor))
    finally:
        reader.close()
    payload = {'mode': 'research_only_not_used_by_official_cycle', 'adjustment': 'split_only_price_return', **result}
    store.record(payload, now)
    if args.export:
        payload['export_sha256'] = export(store, Path(args.export))
    print(json.dumps(payload, indent=1, default=str))
    return 0 if not result['stopped'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
