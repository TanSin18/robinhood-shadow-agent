"""Local dashboard projections. No market requests, inference or real execution."""
from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal as D

from agents.decision_room import project_decision_room
from agents.inbox import ET
from agents.operator import MarketSchedule

CONTROL_LOCK = threading.Lock()
STOP_OWNER = 'shadow-dashboard-v1'


def stamp(value):
    try:
        result = datetime.fromisoformat(value)
        return result if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def money(value):
    return f'{D(value):.2f}'


def _activity_summary(record):
    event = record.get('event')
    role = record.get('role')
    output = record.get('output') if isinstance(record.get('output'), dict) else {}
    if event == 'cycle_started':
        return 'The daily review started and is collecting read-only evidence.'
    if event == 'data_collected':
        return f"Read-only market collection returned {record.get('quote_count', 0)} quotes and {record.get('volatility_count', 0)} volatility series."
    if event == 'strategy_evaluated':
        signals = record.get('signals') if isinstance(record.get('signals'), list) else []
        count = len(signals)
        return f'{count} deterministic strategy signal' + (' was' if count == 1 else 's were') + ' eligible for agent review.'
    if event == 'stage_started':
        return f'{str(role).title()} Agent started reviewing the prepared evidence.'
    if event == 'stage_completed' and role == 'research':
        return output.get('summary') or 'Research completed without a recorded summary.'
    if event == 'stage_completed' and role == 'portfolio':
        return output.get('reason') or 'Portfolio review completed without a recorded reason.'
    if event == 'stage_completed' and role == 'critic':
        return output.get('counterargument') or 'Critic completed without a recorded counterargument.'
    if event == 'final_refresh':
        return f"Final read-only price refresh returned {record.get('quote_count', 0)} quotes."
    if event == 'cycle_terminal':
        payload = record.get('payload') if isinstance(record.get('payload'), dict) else {}
        return payload.get('reason') or f"Review ended with status {payload.get('status', 'unknown')}."
    return 'Agent activity was recorded.'


def _activity_details(record):
    event = record.get('event')
    output = record.get('output') if isinstance(record.get('output'), dict) else {}
    if event == 'stage_completed':
        role = record.get('role') if isinstance(record.get('role'), str) else None
        fields = {
            'research': ('compared_symbols', 'news_checked', 'news', 'missing_evidence'),
            'portfolio': ('picks', 'reason'),
            'critic': ('rejected_instruments', 'counterargument'),
        }.get(role, ())
        return {key: output[key] for key in fields if key in output}
    fields = {
        'data_collected': ('read_tools', 'quote_count', 'volatility_count', 'history_counts'),
        'strategy_evaluated': ('signals', 'blocked'),
        'final_refresh': ('quote_count', 'instruments', 'missing_instruments'),
    }.get(event, ())
    if event == 'cycle_terminal':
        payload = record.get('payload') if isinstance(record.get('payload'), dict) else {}
        fields = ('status', 'results', 'reason', 'api_cost_estimate_usd')
        return {key: payload[key] for key in fields if key in payload}
    return {key: record[key] for key in fields if key in record}


def activity_projection(records):
    allowed = {'cycle_started', 'data_collected', 'strategy_evaluated', 'stage_started',
               'stage_completed', 'final_refresh', 'cycle_terminal'}
    groups = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        event = record.get('event')
        if not isinstance(event, str) or event not in allowed:
            continue
        cycle_id = record.get('trace_id')
        if not isinstance(cycle_id, str) or not cycle_id:
            continue
        timestamp = record.get('timestamp')
        role = record.get('role') if isinstance(record.get('role'), str) else None
        terminal_payload = record.get('payload') if isinstance(record.get('payload'), dict) else {}
        status = ('started' if event in {'cycle_started', 'stage_started'} else
                  'completed' if event in {'stage_completed', 'data_collected', 'strategy_evaluated', 'final_refresh'} else
                  str(terminal_payload.get('status', 'completed')).lower())
        label = ({'research': 'Research Agent', 'portfolio': 'Portfolio Agent', 'critic': 'Critic'}
                 .get(role) or event.replace('_', ' ').title())
        item = {'event': event, 'label': label, 'status': status, 'timestamp': timestamp,
                'summary': _activity_summary(record), 'details': _activity_details(record),
                '_index': index}
        group = groups.setdefault(cycle_id, {'cycle_id': cycle_id, 'events': [], 'timestamp': timestamp})
        group['events'].append(item)
        if stamp(timestamp) and (not stamp(group.get('timestamp')) or stamp(timestamp) > stamp(group['timestamp'])):
            group['timestamp'] = timestamp
    for group in groups.values():
        group['events'].sort(key=lambda item: (stamp(item['timestamp']) or datetime.min.replace(tzinfo=timezone.utc), item['_index']), reverse=True)
        for item in group['events']:
            item.pop('_index', None)
        group['status'] = group['events'][0]['status'] if group['events'] else 'unknown'
    return sorted(groups.values(), key=lambda group: stamp(group.get('timestamp')) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


def set_paused(inbox, action, now=None):
    """Use the existing kill switch; never clear a stop created elsewhere."""
    if action not in {'pause', 'resume'}:
        raise ValueError('Choose pause or resume.')
    from agents.safety_events import incident_active
    if action == 'resume' and incident_active(inbox.path):
        raise ValueError('An unresolved safety incident needs manual review; resume is blocked.')
    now = now or datetime.now(timezone.utc)
    flag = inbox.path.parent / 'STOP_TRADING'
    with CONTROL_LOCK:
        if flag.is_symlink():
            raise ValueError('An external safety stop needs manual review. It was not changed.')
        if action == 'pause':
            marker = {'owner': STOP_OWNER, 'token': secrets.token_urlsafe(32), 'timestamp': now.isoformat()}
            try:
                with flag.open('x') as handle:
                    json.dump(marker, handle)
                    identity = os.fstat(handle.fileno())
            except FileExistsError:
                return
            # If logging fails, leave the stop in place (fail closed).
            inbox.store.append_json('alerts', {'kind': 'dashboard_control', 'action': action,
                                               'timestamp': now.isoformat(), 'stop_token': marker['token'],
                                               'stop_inode': identity.st_ino, 'stop_device': identity.st_dev})
        elif flag.exists():
            try:
                with os.fdopen(os.open(flag, os.O_RDONLY | os.O_NOFOLLOW)) as handle:
                    identity = os.fstat(handle.fileno())
                    marker = json.loads(handle.read(1024)) if identity.st_size < 1024 else {}
                pauses = [e for e in inbox.store.read_json('alerts') if e.get('kind') == 'dashboard_control' and e.get('action') == 'pause']
                receipt = pauses[-1] if pauses else {}
                owned = (marker.get('owner') == STOP_OWNER and bool(receipt.get('stop_token'))
                         and secrets.compare_digest(str(marker.get('token', '')), receipt['stop_token'])
                         and receipt.get('stop_inode') == identity.st_ino and receipt.get('stop_device') == identity.st_dev)
            except (ValueError, OSError, AttributeError):
                owned = False
            if not owned:
                raise ValueError('An external safety stop needs manual review. It was not changed.')
            # Durable intent precedes the only operation that relaxes this switch.
            inbox.store.append_json('alerts', {'kind': 'dashboard_control_request', 'action': action,
                                               'timestamp': now.isoformat()})
            latest = flag.lstat()
            if (latest.st_ino, latest.st_dev) != (identity.st_ino, identity.st_dev):
                raise ValueError('The safety stop changed. It was not cleared; review it manually.')
            flag.unlink()
            try:
                inbox.store.append_json('alerts', {'kind': 'dashboard_control', 'action': action,
                                                   'timestamp': now.isoformat()})
            except Exception:
                # Restore a fail-closed stop if completion could not be audited.
                try:
                    with flag.open('x') as handle:
                        json.dump(marker, handle)
                except FileExistsError:
                    pass
                raise
        else:
            return


def cycle_status(status, payload, day, now):
    if status == 'STARTED':
        started = stamp(payload.get('started_at')) or stamp(payload.get('timestamp')) or datetime.combine(date.fromisoformat(day), time(10), ET)
        return 'RUNNING' if timedelta(0) <= now - started <= timedelta(minutes=30) else 'UNCONFIRMED'
    if status == 'COMPLETED':
        picks = payload.get('decision', {}).get('picks')
        results = payload.get('results')
        if not isinstance(picks, list) or not isinstance(results, list):
            return 'UNCONFIRMED'
        return 'HOLD' if picks == [] and results == [] else 'COMPLETED'
    return status


def dashboard_snapshot(inbox, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Dashboard clock must be timezone-aware')
    local = now.astimezone(ET)
    today = local.date().isoformat()
    with inbox.connect() as db:
        cycles = [dict(r) for r in db.execute('SELECT * FROM cycle_runs ORDER BY day DESC')]
        reports = [dict(r) for r in db.execute('SELECT * FROM weekly_reports ORDER BY week DESC')]
        raw_runs = [dict(r) for r in db.execute('SELECT created_at,payload_json FROM run_states ORDER BY id DESC')]
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        raw_activity = []
        if 'local_traces' in tables:
            for row in db.execute(
                'SELECT id,created_at,payload_json FROM local_traces ORDER BY id'
            ):
                try:
                    payload = json.loads(row['payload_json'])
                except (TypeError, json.JSONDecodeError):
                    payload = {'event': 'malformed', 'status': 'unavailable'}
                if isinstance(payload, dict):
                    raw_activity.append(
                        {
                            **payload,
                            '_row_id': row['id'],
                            '_created_at': row['created_at'],
                        }
                    )
        reservations = [dict(r) for r in db.execute('SELECT * FROM cost_reservations WHERE day=?', (today,))] if 'cost_reservations' in tables else []
        if 'notification_deliveries' in tables:
            # Prefer channel-specific delivery state, while retaining legacy rows
            # written before multi-channel delivery was introduced.
            notifications=[dict(r) for r in db.execute('''SELECT o.event_id,
                COALESCE(d.status,o.status) AS status,o.title,o.created_at,
                COALESCE(d.attempts,o.attempts) AS attempts,
                COALESCE(d.error_class,o.error_class) AS error_class
              FROM notification_outbox o
              LEFT JOIN notification_deliveries d
                ON d.event_id=o.event_id AND d.channel='macos'
              ORDER BY o.created_at DESC LIMIT 50''')]
            delivery_rows=[dict(r) for r in db.execute('''SELECT d.channel,d.status,d.attempts,d.error_class,d.delivered_at,o.created_at
              FROM notification_deliveries d JOIN notification_outbox o USING(event_id)
              ORDER BY o.created_at DESC''')]
        else:
            notifications=[dict(r) for r in db.execute('SELECT event_id,status,title,created_at,attempts,error_class FROM notification_outbox ORDER BY created_at DESC LIMIT 50')] if 'notification_outbox' in tables else []
            delivery_rows=[]
        incidents={r['id']:dict(r) for r in db.execute('SELECT id,code,created_at,resolved_at FROM safety_incidents')} if 'safety_incidents' in tables else {}
    claimed = {c['day'] for c in cycles}
    schedule = MarketSchedule()
    hour, minute = map(int, inbox.config.full_llm_cycle_time_et.split(':'))
    next_run = None
    for offset in range(370):
        candidate = datetime.combine(local.date() + timedelta(days=offset), time(hour, minute), ET)
        if (candidate + timedelta(minutes=20) > local and candidate.date().isoformat() not in claimed
                and schedule.should_run(candidate, asset_class='stock', stage=1)):
            next_run = candidate.isoformat()
            break
    today_at = datetime.combine(local.date(), time(hour, minute), ET)
    today_status = ('WAITING' if local < today_at + timedelta(minutes=20) else 'NO_RUN_RECORDED') if schedule.should_run(today_at, asset_class='stock', stage=1) else 'MARKET_CLOSED'
    history = []
    for notice in notifications:
        incident=incidents.get(notice['event_id'])
        details={'error_class':notice['error_class']} if notice['error_class'] else {}
        if incident:
            details.update(incident_code=incident['code'],incident_resolved_at=incident['resolved_at'])
        history.append({'kind':'notification','timestamp':notice['created_at'],'lane':'','status':notice['status'],'title':notice['title'],'summary':'Sent to macOS; this does not prove it was seen.' if notice['status']=='DELIVERED' else f'Notification {notice["status"].lower()}; attempts: {notice["attempts"]}.','details':details,'event_id':notice['event_id'],'resolution':'RESOLVED' if incident and incident['resolved_at'] else None})
    for cycle in cycles:
        payload = json.loads(cycle['payload'])
        status = cycle_status(cycle['status'], payload, cycle['day'], now)
        when = payload.get('timestamp') or datetime.combine(date.fromisoformat(cycle['day']), time(hour, minute), ET).isoformat()
        if cycle['day'] == today:
            today_status = status
        history.append({'kind': 'cycle', 'timestamp': when, 'lane': '', 'status': status, 'authoritative': True,
                        'title': 'Daily review' + (' · Mock / fixture data' if payload.get('data_mode') == 'fixture' else ''), 'summary': payload.get('reason') or (payload.get('decision') or {}).get('reason') or payload.get('remediation') or '',
                        'details': {k: payload[k] for k in ('agents', 'completed_stages', 'strategy_assessment', 'decision', 'critic', 'results', 'missing_evidence', 'error_type', 'data_mode', 'api_cost_estimate_usd', 'quote_count', 'volatility_count', 'market_open', 'trigger', 'completed_at') if k in payload}})
    # Standalone/interactive failures are not necessarily in cycle_runs.
    for record in raw_runs:
        payload = json.loads(record['payload_json'])
        if payload.get('status') != 'FAILED':
            continue
        when = stamp(payload.get('timestamp')) or stamp(record['created_at'])
        if when and not any(c['day'] == when.astimezone(ET).date().isoformat() and c['status'] == 'FAILED' for c in cycles):
            history.append({'kind': 'cycle', 'timestamp': when.isoformat(), 'lane': '', 'status': 'FAILED', 'authoritative': False,
                            'title': 'Run failure recorded', 'summary': payload.get('remediation') or 'This recovery attempt stopped before completion.',
                            'details': {'error_type': payload.get('error_type', 'Unknown')}})
    # Preserve missing scheduled windows as absence of evidence, not invented failure reasons.
    first_observed = date.fromisoformat(min(claimed)) if claimed else local.date()
    first_observed = max(first_observed, local.date() - timedelta(days=90))
    for offset in range((local.date() - first_observed).days + 1):
        candidate = datetime.combine(first_observed + timedelta(days=offset), time(hour, minute), ET)
        if (candidate + timedelta(minutes=20) <= local and candidate.date().isoformat() not in claimed
                and schedule.should_run(candidate, asset_class='stock', stage=1)):
            history.append({'kind': 'schedule', 'timestamp': candidate.isoformat(), 'lane': '', 'status': 'NO_RUN_RECORDED',
                            'title': 'No run recorded', 'summary': 'No scheduled run is recorded for this window. The app may have been paused, asleep or unavailable; the cause is not proven.', 'details': {}})
    cards = inbox.cards()
    for card in cards:
        history.append({'kind': 'decision', 'timestamp': card.get('decided', card['issued']), 'lane': card['lane'],
                        'status': card['status'], 'title': card['proposal']['ticker'] + ' · Your decision',
                        'summary': card.get('approval_fill', {}).get('status', 'Waiting for you' if card['status'] == 'PENDING' else card['status']),
                        'details': card.get('approval_fill', {}), 'card_id': card['id']})
    for fill in inbox.store.read_json('fills'):
        history.append({'kind': 'fill', 'timestamp': fill.get('timestamp', ''), 'lane': fill.get('lane') or str(fill.get('track', '')).split(':')[0],
                        'status': fill.get('status', fill.get('kind', 'recorded')), 'title': str(fill.get('ticker', '')) + ' · Paper record',
                        'summary': f"{fill.get('track', '')} {fill.get('side', '')} {fill.get('quantity', '')} {fill.get('reason', '')}".strip(),
                        'details': fill})
    for event in inbox.store.read_json('alerts'):
        if event.get('kind') == 'dashboard_control':
            history.append({'kind': 'control', 'timestamp': event['timestamp'], 'lane': '', 'status': event['action'],
                            'title': 'Paper activity ' + ('paused' if event['action'] == 'pause' else 'resumed'), 'summary': 'Changed by you in this dashboard.', 'details': {}})
    history.sort(key=lambda r: stamp(r['timestamp']) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    costs = inbox.store.read_json('api_costs')
    all_cost = sum((D(c['cost_usd']) for c in costs), D(0))
    today_cost = sum((D(c['cost_usd']) for c in costs if stamp(c.get('timestamp')) and stamp(c['timestamp']).astimezone(ET).date().isoformat() == today), D(0))
    held = sum((D(r['amount']) for r in reservations if not r['settled']), D(0))
    accounted = max(today_cost, sum((D(r['amount']) for r in reservations if r['settled']), D(0)))
    values = inbox.store.read_json('daily_values')
    from agents.account_tripwire import public_status as tripwire_public_status
    tripwire = tripwire_public_status(inbox.path)
    if tripwire and tripwire[0].get('incident_id'):
        tripwire[0]['ack_expires_at']=(now+timedelta(minutes=10)).isoformat()
    benchmark = [v for v in values if v.get('benchmark') == 'VTI' and v.get('data_mode') == 'live_readonly' and v.get('close', {}).get('date')]
    benchmark.sort(key=lambda v: v['close']['date'])
    vti_ratio = None
    if len(benchmark) >= 2 and benchmark[0]['close']['date'] != benchmark[-1]['close']['date'] and D(benchmark[0]['close']['price']) > 0:
        vti_ratio = D(benchmark[-1]['close']['price']) / D(benchmark[0]['close']['price'])
    lanes = []
    for lane in ('A', 'B'):
        tracks = []
        for track in ('agent_alone', 'with_approvals'):
            account = inbox.state(lane, track)
            missing = [ticker for ticker in account['positions'] if ticker not in account['marks'] or not stamp(account.get('marks_at', {}).get(ticker))]
            marks = [stamp(account.get('marks_at', {}).get(t)) for t in account['positions']]
            as_of = min((t for t in marks if t), default=None)
            stale = bool(missing) or any(t is None or not 0 <= (now-t).total_seconds() <= inbox.config.risk.max_quote_age_seconds for t in marks)
            value = None if missing else D(account['settled_cash']) + D(account['unsettled_cash']) + sum((D(p['quantity']) * D(account['marks'][t]) * p['multiplier'] for t, p in account['positions'].items()), D(0))
            tracks.append({'track': track, 'value': money(value) if value is not None else None,
                           'net_value': money(value - all_cost / 2) if value is not None else None,
                           'api_cost': str(all_cost / 2), 'settled_cash': money(account['settled_cash']),
                           'unsettled_cash': money(account['unsettled_cash']), 'positions': account['positions'],
                           'stale': stale, 'as_of': as_of.isoformat() if as_of else None,
                           'data_mode': account.get('data_mode', 'unmarked')})
        start = D(inbox.state(lane, 'agent_alone')['start'])
        lanes.append({'lane': lane, 'start': money(start), 'tracks': tracks, 'cash_benchmark': money(start),
                      'vti_benchmark': money(start * vti_ratio) if vti_ratio is not None else None})
    first_day = min(claimed) if claimed else None
    from agents.safety_events import safety_stopped
    channel_status = {}
    for channel in ('macos', 'pushover'):
        rows = [row for row in delivery_rows if row['channel'] == channel]
        latest = rows[0] if rows else None
        channel_status[channel] = {
            'enabled': channel == 'macos' or inbox.config.notifications.pushover_enabled,
            'status': latest['status'] if latest else 'NO_MESSAGES',
            'last_attempt': latest['created_at'] if latest else None,
            'last_delivered': next((row['delivered_at'] for row in rows if row['delivered_at']), None),
            'error_class': latest['error_class'] if latest else None,
        }
    activity = activity_projection(inbox.store.read_json('local_traces'))
    decision_room = project_decision_room(raw_activity, cards)
    return {'checked_at': now.isoformat(), 'next_run': next_run, 'today_status': today_status,
            'paused': safety_stopped(inbox.path),
            'history': history, 'cards': cards, 'lanes': lanes, 'activity': activity,
            'decision_room': decision_room,
            'tripwire': tripwire,
            'notification_channels': channel_status,
            'costs': {'today': str(today_cost), 'held': str(held), 'budget': str(inbox.config.daily_api_budget_usd),
                      'remaining': str(max(D(0), inbox.config.daily_api_budget_usd - accounted - held)), 'total': str(all_cost)},
            'benchmark_period': f"{benchmark[0]['close']['date']} to {benchmark[-1]['close']['date']}" if vti_ratio is not None else None,
            'reports': [{'week': r['week'], **json.loads(r['payload'])} for r in reports if first_day is None or r['week'] >= first_day]}
