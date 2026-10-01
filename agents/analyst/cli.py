"""Operator commands for the analyst desk (run in the main user's Terminal).

    python -m agents.analyst.cli init   --official-database <agent.db>
    python -m agents.analyst.cli status --official-database <agent.db>
    python -m agents.analyst.cli pause  --official-database <agent.db>
    python -m agents.analyst.cli resume --official-database <agent.db>
    python -m agents.analyst.cli rerun  --official-database <agent.db> --job close     (or --job morning)
    python -m agents.analyst.cli ask    --official-database <agent.db>   < {"question": "...", "context": "...", "packet": {...}}

`rerun` lets today's morning or after-close job run once more at the service's next tick inside that job's
time window (for example after a release that added seats was installed later than the job ran).
`ask` is what the dashboard runs when the operator asks Bubbles a question: it reads one JSON object from
standard input, answers from that packet only (no tools, budgeted, numbers checked) and stores the answer.

Optional, for SEC filings: write one line with your name and email to
robinhood-diagnostics/analyst/contact.txt (EDGAR asks every client to identify itself).
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from agents.analyst import commentary
from agents.analyst.store import AnalystStore, default_path


def _ask(store, raw, now, client):
    from zoneinfo import ZoneInfo
    from agents.analyst import ask
    if store.meta('paused') == '1':
        return {'status': 'ANALYST_PAUSED'}
    try:
        body = json.loads(raw)
        if not isinstance(body, dict) or not isinstance(body.get('packet'), dict):
            raise ValueError
    except ValueError:
        return {'status': 'INVALID_REQUEST'}
    if client is None:
        from agents.ai_trader.model import OpenAIResponsesClient
        client = OpenAIResponsesClient()
    day = now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    try:
        out = ask.answer(store, body.get('question'), body['packet'], now, client, day=day, context=str(body.get('context') or ''))
    except ask.AskError as error:
        return {'status': str(error)}
    return {'status': out['status'], 'flags': (out.get('checks') or {}).get('flags', [])}


def main(argv=None, *, stdin=None, client=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['init', 'status', 'pause', 'resume', 'rerun', 'ask'])
    p.add_argument('--official-database', required=True)
    p.add_argument('--path')
    p.add_argument('--job', choices=['morning', 'close'])
    a = p.parse_args(argv)
    official = Path(a.official_database)
    path = Path(a.path) if a.path else default_path(official)
    now = datetime.now(timezone.utc)
    if a.command != 'init' and not path.is_file():
        raise SystemExit('Not set up yet: run init first.')
    store = AnalystStore(path, official)
    if a.command == 'ask':
        import sys
        print(json.dumps(_ask(store, (stdin or sys.stdin).read(200_000), now, client)))
        return 0
    if a.command == 'init' and not store.meta('initialized_at'):
        store.set_meta('initialized_at', now.isoformat())
        store.set_meta('prompt_sha256', commentary.prompt_sha256())
        store.journal('initialized', {'prompt_sha256': commentary.prompt_sha256()}, now)
    if a.command == 'rerun':
        from zoneinfo import ZoneInfo
        if not a.job:
            raise SystemExit('rerun needs --job morning or --job close')
        day = now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        if store.meta(f'{a.job}_done') == day:
            store.set_meta(f'{a.job}_done', f'rerun-requested:{day}')
        store.set_meta(f'{a.job}_attempts:{day}', '0')
        store.journal('rerun_requested', {'job': a.job, 'day': day}, now)
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
