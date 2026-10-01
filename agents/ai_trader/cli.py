"""Operator commands for the AI trader book (run in the main user's Terminal).

    python -m agents.ai_trader.cli init --official-database <agent.db>
    python -m agents.ai_trader.cli status --official-database <agent.db>
    python -m agents.ai_trader.cli start-paper --official-database <agent.db>   # Mon 5 Oct or later
    python -m agents.ai_trader.cli retire --official-database <agent.db>
    python -m agents.ai_trader.cli scoreboard --official-database <agent.db>
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from agents.ai_trader.hook import default_path, official_completed_today
from agents.ai_trader.scoring import scoreboard
from agents.ai_trader.seats import prompts_sha256
from agents.ai_trader.spec import load_spec
from agents.ai_trader.store import TraderStore

FIRST_OFFICIAL_DAY = '2026-10-01'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['init', 'status', 'start-paper', 'retire', 'scoreboard'])
    p.add_argument('--official-database', required=True)
    p.add_argument('--path')
    a = p.parse_args(argv)
    official = Path(a.official_database)
    path = Path(a.path) if a.path else default_path(official)
    now = datetime.now(timezone.utc)
    spec = load_spec()
    if a.command == 'init':
        store = TraderStore(path, official)
        store.bind_spec(spec)
        if not store.meta('prompts_sha256'):
            store.set_meta('prompts_sha256', prompts_sha256())
        store.journal('initialized', {'spec_sha256': spec.sha256, 'mode': store.mode()}, now)
    elif not path.is_file():
        raise SystemExit('Not set up yet: run init first.')
    store = TraderStore(path, official)
    if a.command == 'start-paper':
        store.set_mode('PAPER', at=now, by='operator', spec=spec,
                       official_first_run_completed=official_completed_today(official, FIRST_OFFICIAL_DAY))
    elif a.command == 'retire':
        store.set_mode('RETIRED', at=now, by='operator')
    if a.command == 'scoreboard':
        print(json.dumps(scoreboard(store, spec), indent=1, default=str))
        return 0
    print(json.dumps({'path': str(path), 'mode': store.mode(), 'spec': spec.id, 'spec_sha256': spec.sha256,
                      'prompts_sha256': store.meta('prompts_sha256'), 'ai_spent_usd': str(store.spent()),
                      'books': {b: {'positions': sorted(store.book(b).positions), 'closed_trades': store.book(b).closed_trades}
                                for b in ('A', 'B', 'C')}}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
