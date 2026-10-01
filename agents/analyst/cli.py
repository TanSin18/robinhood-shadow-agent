"""Operator commands for the analyst desk (run in the main user's Terminal).

    python -m agents.analyst.cli init   --official-database <agent.db>
    python -m agents.analyst.cli status --official-database <agent.db>
    python -m agents.analyst.cli pause  --official-database <agent.db>
    python -m agents.analyst.cli resume --official-database <agent.db>

Optional, for SEC filings: write one line with your name and email to
robinhood-diagnostics/analyst/contact.txt (EDGAR asks every client to identify itself).
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from agents.analyst import commentary
from agents.analyst.store import AnalystStore, default_path


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['init', 'status', 'pause', 'resume'])
    p.add_argument('--official-database', required=True)
    p.add_argument('--path')
    a = p.parse_args(argv)
    official = Path(a.official_database)
    path = Path(a.path) if a.path else default_path(official)
    now = datetime.now(timezone.utc)
    if a.command != 'init' and not path.is_file():
        raise SystemExit('Not set up yet: run init first.')
    store = AnalystStore(path, official)
    if a.command == 'init' and not store.meta('initialized_at'):
        store.set_meta('initialized_at', now.isoformat())
        store.set_meta('prompt_sha256', commentary.prompt_sha256())
        store.journal('initialized', {'prompt_sha256': commentary.prompt_sha256()}, now)
    if a.command in ('pause', 'resume'):
        store.set_meta('paused', '1' if a.command == 'pause' else '0')
        store.journal(a.command, {}, now)
    latest = {k: (store.latest(k) or {}).get('at') for k in ('notes', 'regimes', 'kelly', 'auction', 'news')}
    print(json.dumps({'path': str(path), 'paused': store.meta('paused') == '1', 'prompt_sha256': store.meta('prompt_sha256'),
                      'model': commentary.MODEL, 'daily_cap_usd': commentary.DAILY_CAP_USD, 'ai_spent_usd': str(store.spent()),
                      'sec_contact_file': (path.parent / 'contact.txt').is_file(), 'latest': latest}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
