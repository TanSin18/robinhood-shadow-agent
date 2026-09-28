"""Deterministic weekly digest: no model calls or fabricated market returns."""
from __future__ import annotations

import json
from datetime import timedelta,datetime
from decimal import Decimal
from pathlib import Path

from agents.codex_bridge import ET

def eastern_day(value):
    stamp=datetime.fromisoformat(value)
    if stamp.tzinfo is None: raise ValueError('Report observations must be timezone-aware')
    return stamp.astimezone(ET).date().isoformat()


def report_if_due(inbox, now, directory):
    local = now.astimezone(ET)
    # Friday after the configured time, with weekend catch-up after sleep/restart.
    friday = local.date() - timedelta(days=(local.weekday()-4)%7)
    if local.weekday()==4 and local.strftime('%H:%M')<inbox.config.weekly_report_time_et:
        friday-=timedelta(days=7)
    # No backfilling artificial reports before the first observed runtime cycle.
    with inbox.connect() as db:
        first=db.execute('SELECT MIN(day) FROM cycle_runs').fetchone()[0]
    if first is not None and first>friday.isoformat():
        return None
    if first is None and (local.weekday()<4 or (local.weekday()==4 and local.strftime('%H:%M')<inbox.config.weekly_report_time_et)):
        return None
    monday = friday - timedelta(days=4)
    key = friday.isoformat()
    directory = Path(directory)
    path = directory / f'week-{key}.md'
    with inbox.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM weekly_reports WHERE week=?', (key,)).fetchone():
            return None
        cycles = [json.loads(r[0]) for r in db.execute('SELECT payload FROM cycle_runs WHERE day>=? AND day<=? AND status=?', (monday.isoformat(),key,'COMPLETED'))]
        costs = [c for c in inbox.store.read_json('api_costs') if monday.isoformat() <= eastern_day(c['timestamp']) <= key]
        total = sum((Decimal(c['cost_usd']) for c in costs),Decimal(0))
        cards = [c for c in inbox.cards() if monday.isoformat() <= eastern_day(c['issued']) <= key]
        lines = [f'# Shadow report — week ending {key}', '', 'Stage 1. No real orders. Approval comparison uses proposal-time counterfactual fills.', '', f'Completed cycles: {len(cycles)}. Cards: {len(cards)}. YES: {sum(c["status"]=="YES" for c in cards)}. NO: {sum(c["status"]=="NO" for c in cards)}. Expired: {sum(c["status"]=="EXPIRED" for c in cards)}.', f'Estimated API-equivalent AI cost: ${total:.6f}. This is not a Codex subscription bill.', '']
        if not cycles:
            lines += ['No completed cycles; performance is unavailable.', '']
        viewed={r[0] for r in db.execute('SELECT card_id FROM card_views')} if db.execute("SELECT 1 FROM sqlite_master WHERE name='card_views'").fetchone() else set()
        lines += [f'Expired with a recorded page rendering: {sum(c["status"]=="EXPIRED" and c["id"] in viewed for c in cards)}. Expired without one: {sum(c["status"]=="EXPIRED" and c["id"] not in viewed for c in cards)}. Rendering does not prove a person read the card.','']
        observations = [v for v in inbox.store.read_json('daily_values') if v.get('kind')=='paper_valuation' and monday.isoformat()<=eastern_day(v['timestamp'])<=key and v.get('data_mode')=='live_readonly']
        lines += ['| Lane / track | Latest observed equity | Since-start gross P&L | AI cost allocated | After AI cost |', '|---|---:|---:|---:|---:|']
        # Shared pipeline cost is split equally between lanes, fully charged to each alternative track.
        all_cost = sum((Decimal(c['cost_usd']) for c in inbox.store.read_json('api_costs') if eastern_day(c['timestamp'])<=key),Decimal(0))
        for lane in ('A','B'):
            for track in ('agent_alone','with_approvals'):
                candidates=[v for v in observations if v['lane']==lane and v['track']==track]
                value=candidates[-1].get('value') if candidates else None
                if value is None:
                    lines.append(f'| {lane} / {track} | unavailable | unavailable | ${all_cost/2:.6f} | unavailable |')
                else:
                    start=Decimal(inbox.state(lane,track)['start'])
                    gross=Decimal(value)-start
                    lines.append(f'| {lane} / {track} | ${Decimal(value):.2f} | ${gross:.2f} | ${all_cost/2:.6f} | ${gross-all_cost/2:.2f} |')
        lines += ['', 'VTI benchmark: unavailable until two comparable observed prices exist. Cash benchmark: $500 per lane, $0 AI costs; no assumed interest.', '', 'Equity uses observed bid marks (spread already included); no second spread subtraction. Missing marks remain unavailable. Taxes, fees not modeled by this runtime, dividends, and approval execution latency are excluded; these are paper estimates, not investment returns.']
        benchmark=[v for v in inbox.store.read_json('daily_values') if v.get('benchmark')=='VTI' and v.get('data_mode')=='live_readonly' and eastern_day(v['timestamp'])<=key]
        if len(benchmark)>=2 and benchmark[0]['close'].get('date')!=benchmark[-1]['close'].get('date'):
            first,last=Decimal(benchmark[0]['close']['price']),Decimal(benchmark[-1]['close']['price'])
            lines += ['', f'Observed VTI price-only benchmark since first observation: ${500*last/first:.2f} per $500, $0 AI costs. Not dividend-adjusted.']
        body='\n'.join(lines)+'\n'
        directory.mkdir(parents=True,exist_ok=True)
        path.write_text(body)
        db.execute('INSERT INTO weekly_reports VALUES (?,?)',(key,json.dumps({'path':str(path),'body':body,'generated_at':now.isoformat()})))
        from agents.notification_outbox import enqueue
        enqueue(
            db, f'weekly-summary-{key}', 'Weekly shadow summary',
            f'Week ending {key}: {len(cycles)} completed cycles, {len(cards)} approval cards, ${total:.4f} measured AI cost.',
            now, priority=-1, url=inbox.config.notifications.dashboard_url('results'),
        )
    return path
