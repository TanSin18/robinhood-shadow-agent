"""Firm Lab research collectors, started by hand. This program cannot trade: it imports only the standard library, the
Firm Lab research package and this package, and it writes only the Firm Lab database. Nothing schedules it.

    python -m firm_lab_collectors.cli status
    python -m firm_lab_collectors.cli edgar      [--symbols SPY,VTI,SOXX,AAPL,NVDA] [--days 365] [--max-filings 5]
    python -m firm_lab_collectors.cli xbrl       [--symbols AAPL,MSFT,NVDA,AMZN,GOOGL] [--days 550] [--max-filings 4]   # reported company facts
    python -m firm_lab_collectors.cli earnings   [--symbols ...] [--days 550] [--max-events 4]     # earnings-release filings, facts only
    python -m firm_lab_collectors.cli massive    [--symbols ...] [--session-date YYYY-MM-DD] [--no-ticks] [--min-interval SECONDS]
    python -m firm_lab_collectors.cli sharadar   [--symbols AAPL,NVDA] [--years 3]
    python -m firm_lab_collectors.cli thetadata  [--symbols SPY,QQQ,NVDA] [--session-date YYYY-MM-DD] [--expiration YYYY-MM-DD]
    python -m firm_lab_collectors.cli treasury   [--start YYYY-MM-DD]      # 13-week bill auctions, then the 70/30 ruler
    python -m firm_lab_collectors.cli distributions                        # issuer VTI distributions, then the total-return rulers
    python -m firm_lab_collectors.cli capture    --out DIRECTORY           # raw public samples saved as received; no database

``--path`` names the Firm Lab database (default: ~/LocalProjects/robinhood-diagnostics/firm_lab/firm_lab.db). It must exist
already (``python -m firm_lab.cli init``). The registered database is never opened, and its location is never given here.

Settings come from the environment and are never printed (see ``firm_lab_collectors.config``). They are research-data
settings only; brokerage authentication is not involved.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from firm_lab import capabilities, view
from firm_lab.errors import FirmLabError
from firm_lab.store import FirmLabStore

from . import config, runner

DEFAULT_PATH = Path.home() / 'LocalProjects' / 'robinhood-diagnostics' / 'firm_lab' / 'firm_lab.db'


def _status(path, environ=None) -> dict:
    state = view.load(path=path)
    rows = [{k: r.get(k) for k in ('domain', 'provider', 'connection', 'validation', 'validation_issues', 'observations', 'oldest', 'newest',
                                   'last_successful_ingest', 'failures', 'status')}
            for r in state.get('data_readiness') or [] if r.get('provider') and r.get('capability') != 'daily_closes']
    return {'configured_in_this_shell': config.states(environ), 'mode': state.get('mode'), 'fills': state.get('fills'),
            'firm_trading_trial': state.get('firm_trading_trial'), 'has_execution_tables': state.get('has_execution_tables'), 'providers': rows}


def main(argv=None, environ=None, transport=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['status', 'capture', *runner.RUNS])
    p.add_argument('--out')
    p.add_argument('--path')
    p.add_argument('--symbols')
    p.add_argument('--session-date')
    p.add_argument('--expiration')
    p.add_argument('--start')
    p.add_argument('--days', type=int)
    p.add_argument('--years', type=int)
    p.add_argument('--max-filings', type=int)
    p.add_argument('--max-events', type=int)
    p.add_argument('--min-interval', type=float)
    p.add_argument('--no-ticks', action='store_true')
    a = p.parse_args(argv)
    path = Path(a.path) if a.path else DEFAULT_PATH
    out = {'command': a.command}
    if a.command == 'capture':                               # no database is opened for a raw capture
        if not a.out:
            p.error('capture needs --out DIRECTORY')
        from . import capture
        try:
            out['capture'] = capture.run(a.out, environ=environ)
            code = 0
        except Exception as error:
            out['error'], code = type(error).__name__, 1
        print(json.dumps(out, indent=1, default=str))
        return code
    try:
        if a.command != 'status':
            store = FirmLabStore(path, create=False)
            capabilities.seed(store)
            options = {'symbols': tuple(s.strip().upper() for s in a.symbols.split(',') if s.strip()) if a.symbols else None,
                       'days': a.days, 'years': a.years, 'max_filings': a.max_filings, 'max_events': a.max_events, 'min_interval': a.min_interval,
                       'session_date': a.session_date if a.command == 'massive' else None, 'as_of': a.session_date if a.command == 'thetadata' else None,
                       'expiration': a.expiration, 'ticks': False if a.no_ticks else None, 'start': a.start}
            allowed = {'edgar': ('symbols', 'days', 'max_filings'), 'xbrl': ('symbols', 'days', 'max_filings'),
                       'earnings': ('symbols', 'days', 'max_events'), 'massive': ('symbols', 'session_date', 'ticks', 'min_interval'),
                       'sharadar': ('symbols', 'years'), 'thetadata': ('symbols', 'as_of', 'expiration'), 'treasury': ('start',), 'distributions': ()}[a.command]
            chosen = {k: v for k, v in options.items() if k in allowed and v is not None}
            out['run'] = runner.RUNS[a.command](store, environ=environ, transport=transport, **chosen)
        out['status'] = _status(path, environ)
        code = 0
    except FirmLabError as error:
        out['error'], code = str(error)[:200], 1
    except Exception as error:                              # nothing unexpected is printed in full: a message could quote a request
        out['error'], code = type(error).__name__, 1
    print(json.dumps(out, indent=1, default=str))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
