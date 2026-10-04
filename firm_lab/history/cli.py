"""Hand-started commands for the historical research database. Nothing here is scheduled and nothing uses the network.

    python -m firm_lab.history.cli init      --db PATH
    python -m firm_lab.history.cli ingest    --db PATH --tickers FILE --prices FILE [--funds FILE] [--actions FILE] [--sp500 FILE]
    python -m firm_lab.history.cli universe  --db PATH --start 1998-01-02 --end 2026-09-30
    python -m firm_lab.history.cli count     --db PATH
    python -m firm_lab.history.cli readiness --db PATH --research-db PATH --out FILE

The files are ones the operator downloaded. No key, login or address is read, asked for or stored.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import dataset, ingest, readiness, sharadar_files, splits, universe
from .store import HistoryStore


def _progress(done, total):
    print(f'  {done:,} of {total:,}', file=sys.stderr, flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='firm_lab.history', description='Historical research data. Research only; no trading.')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('init', 'ingest', 'universe', 'count', 'readiness'):
        p = sub.add_parser(name)
        p.add_argument('--db', required=name != 'readiness')
        if name == 'ingest':
            p.add_argument('--tickers')
            p.add_argument('--prices')
            p.add_argument('--funds')
            p.add_argument('--actions')
            p.add_argument('--sp500')
        if name == 'universe':
            p.add_argument('--start', required=True)
            p.add_argument('--end', required=True)
        if name == 'readiness':
            p.add_argument('--research-db', required=True)
            p.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    if args.command == 'readiness':
        report = readiness.build(args.research_db, args.db)
        readiness.write(report, args.out)
        print(json.dumps({'written': args.out, 'report_hash': report['report_hash'], 'strict_samples': report['strict_training']['strict_samples']}, indent=1))
        return 0
    with HistoryStore(args.db, create=args.command == 'init') as store:
        if args.command == 'init':
            store.put('history_reservations', splits.reservation())
            print(json.dumps({'created': str(store.path), 'holdout_reservation': splits.SPLIT_VERSION}, indent=1))
        elif args.command == 'ingest':
            out = {}
            common = {'source': sharadar_files.SOURCE, 'adapter': sharadar_files.ADAPTER}
            if args.tickers:
                out['securities'] = ingest.ingest_securities(store, sharadar_files.securities(args.tickers), file=ingest.describe_file(args.tickers), **common)
            if args.prices:
                out['stock_bars'] = ingest.ingest_bars(store, sharadar_files.prices(args.prices), file=ingest.describe_file(args.prices), price_table='stocks', **common)
            if args.funds:
                out['fund_bars'] = ingest.ingest_bars(store, sharadar_files.prices(args.funds), file=ingest.describe_file(args.funds), price_table='funds', **common)
            if args.actions:
                out['actions'] = ingest.ingest_actions(store, sharadar_files.actions(args.actions), file=ingest.describe_file(args.actions), **common)
            if args.sp500:
                out['index_events'] = ingest.ingest_index_events(store, sharadar_files.index_events(args.sp500), file=ingest.describe_file(args.sp500), **common)
            print(json.dumps(out, indent=1))
        elif args.command == 'universe':
            print(json.dumps(universe.build(store, args.start, args.end, progress=_progress), indent=1))
        elif args.command == 'count':
            result = dataset.count(store, progress=_progress)
            store.put('history_reports', {'kind': 'strict_count', **result})        # counts and hashes only: what the readiness report reads
            print(json.dumps(result, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
