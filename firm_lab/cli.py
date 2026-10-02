"""Firm Lab research-only commands. This worker cannot trade: the package imports no trading module.

    python -m firm_lab.cli init   --official-database <agent.db>
    python -m firm_lab.cli ingest --official-database <agent.db>     # Control A's recorded closes -> features -> baseline counterfactual
    python -m firm_lab.cli status --official-database <agent.db>

``--path`` overrides the Firm Lab database location (default: robinhood-diagnostics/firm_lab/firm_lab.db).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import benchmarks, capabilities, ingest, view
from .store import FirmLabStore, default_path


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['init', 'ingest', 'status'])
    p.add_argument('--official-database', required=True)
    p.add_argument('--path')
    a = p.parse_args(argv)
    official_db = Path(a.official_database)
    path = Path(a.path) if a.path else default_path(official_db)
    out = {}
    if a.command in ('init', 'ingest'):
        store = FirmLabStore(path, official_db)
        capabilities.seed(store)
        benchmarks.seed(store)
        if a.command == 'ingest':
            out['ingest'] = ingest.ingest_official(store, official_db)
    state = view.load(path=path)
    state.pop('baseline', None) if a.command != 'status' else None
    out['state'] = {k: v for k, v in state.items() if k not in ('capabilities',)}
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
