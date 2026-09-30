"""Nightly S&P 500 shadow screen (SHADOW ONLY; never trades, never writes the official DB).

Run by its own launchd agent (``com.openai.robinhood-universe-screen``) at 16:50 ET on
weekdays. It is a read-only research job, not a trading runner:

1. skips non-trading days and any active safety stop or pause;
2. refreshes the pinned universe file from the two free issuer holdings files
   (SPY primary, IVV cross-check, both must list a ticker) when the newest file
   is older than ``REFRESH_DAYS``;
3. runs ``agents.universe_screen.run`` with its budget (600 calls / 20 min / 120
   first-fill symbols) into its own store directory;
4. writes ``latest.json`` beside the store for the dashboard's Checks page.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

SPY_URL = 'https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx'
IVV_URL = ('https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/1467271812596.ajax'
           '?fileType=csv&fileName=IVV_holdings&dataType=fund')
REFRESH_DAYS = 7


def _download(url, dest, opener=urllib.request.urlopen):
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with opener(request, timeout=60) as response:
        data = response.read()
    if len(data) < 1000:
        raise RuntimeError('HOLDINGS_FILE_TOO_SMALL')
    Path(dest).write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def newest_universe(directory: Path):
    files = sorted(directory.glob('sp500-*.json'))
    return files[-1] if files else None


def refresh_universe(directory: Path, today: date, *, download=_download):
    from agents.universe_screen import build_universe, parse_ivv_csv, parse_spy_rows, read_xlsx_rows
    from research.strategy_signals import ETF_UNIVERSE
    spy_path, ivv_path = directory / 'spy.xlsx', directory / 'ivv.csv'
    download(SPY_URL, spy_path)
    download(IVV_URL, ivv_path)
    universe = build_universe(parse_spy_rows(read_xlsx_rows(spy_path)),
                              parse_ivv_csv(ivv_path.read_text(encoding='utf-8-sig')),
                              as_of=today.isoformat(), etfs=sorted(ETF_UNIVERSE))
    out = directory / f'sp500-{today.isoformat()}.json'
    out.write_text(json.dumps(universe, indent=1, sort_keys=True) + '\n')
    return out


def run_nightly(*, config, official: Path, directory: Path, now=None, download=_download, runner=None, trading_day=None):
    from agents.safety_events import safety_stopped
    now = now or datetime.now(timezone.utc)
    directory.mkdir(parents=True, exist_ok=True)
    from zoneinfo import ZoneInfo
    today = now.astimezone(ZoneInfo('America/New_York')).date()
    if trading_day is None:
        from agents.operator import MarketSchedule
        try:
            MarketSchedule().session_close(now)
            trading_day = True
        except ValueError:
            trading_day = False
    result = {'at': now.isoformat(), 'mode': 'shadow_only_not_used_by_official_cycle'}
    if not trading_day:
        return {**result, 'status': 'SKIPPED_NOT_A_TRADING_DAY'}
    if safety_stopped(official):
        return {**result, 'status': 'SKIPPED_SAFETY_STOP_OR_PAUSE'}
    universe = newest_universe(directory)
    stale = universe is None or (today - date.fromisoformat(universe.stem.removeprefix('sp500-'))).days >= REFRESH_DAYS
    if stale:
        try:
            universe = refresh_universe(directory, today, download=download)
            result['universe_refreshed'] = True
        except Exception as error:
            result['universe_refresh_error'] = type(error).__name__
            if universe is None:
                return {**result, 'status': 'NO_UNIVERSE_FILE'}
    from agents.universe_screen import run
    payload = (runner or run)(config=config, official=official, universe_path=universe,
                              store_path=directory / 'store' / 'universe.db', now=now)
    return {**result, 'status': payload.get('status'), 'universe_file': universe.name,
            'universe_file_sha256': payload.get('universe_file_sha256'), 'funnel': payload.get('funnel'),
            'collection': payload.get('collection'), 'shortlist': [s.get('symbol') for s in payload.get('shortlist', [])],
            'as_of_session': payload.get('as_of_session')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--config', required=True)
    parser.add_argument('--database', required=True, help='official database (read for safety state only)')
    parser.add_argument('--dir', required=True)
    args = parser.parse_args(argv)
    os.umask(0o077)
    directory = Path(args.dir)
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / '.lock', 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print(json.dumps({'status': 'SKIPPED_ALREADY_RUNNING'}))
            return 0
        from config.loader import load_config
        config = load_config(args.config)
        config.validate_runtime_ready()
        try:
            summary = run_nightly(config=config, official=Path(args.database), directory=directory)
        except Exception as error:   # recorded, never retried blindly
            summary = {'at': datetime.now(timezone.utc).isoformat(), 'status': 'FAILED', 'error_type': type(error).__name__}
        (directory / 'latest.json').write_text(json.dumps(summary, indent=1, default=str) + '\n')
        print(json.dumps(summary, default=str))
    return 0 if summary.get('status') in {'COMPLETED', 'PARTIAL'} or str(summary.get('status', '')).startswith('SKIPPED') else 2


if __name__ == '__main__':
    raise SystemExit(main())
