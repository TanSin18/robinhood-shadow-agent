"""Truthful, read-only projection of append-only cycle traces (Agent Desk overlay copy).

The dashboard overlay loads the frozen runtime's ``agents`` package first, so the
desk keeps its own projection here instead of changing the runtime module.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

STAGE_ORDER = ('evidence', 'research', 'portfolio', 'critic', 'risk', 'final')
CYCLE_REVIEW_EVENTS = {
    'cycle_started',
    'data_collected',
    'strategy_evaluated',
    'stage_started',
    'stage_completed',
    'final_refresh',
    'risk_evaluated',
    'cycle_terminal',
}
STATE_PRIORITY = {'reviewed': 1, 'advanced': 2, 'rejected': 3, 'blocked': 4, 'proposed': 5}
VALID_LANES = {'A', 'B'}
REASON_LABELS = {
    'research_compared': 'Compared by the Research Agent.',
    'strategy_signal': 'A deterministic strategy signal advanced this candidate.',
    'portfolio_pick': 'Proposed by the Portfolio Agent.',
    'critic_rejected': 'Rejected by the Critic.',
    'current_quote_missing': 'Current price evidence was unavailable.',
    'risk_blocked': 'A deterministic risk rule blocked the proposal.',
    'not_recorded': 'Reason not recorded.',
}
DECIDING_STAGE = {
    'reviewed': 'Research Agent',
    'advanced': 'Evidence',
    'proposed': 'Portfolio Agent',
    'rejected': 'Critic',
    'blocked': 'Risk Engine',
}
STAGE_META = {
    'evidence': ('Evidence', 'Collect read-only evidence and deterministic signals.'),
    'research': ('Research Agent', 'Compare supplied candidates and evidence.'),
    'portfolio': ('Portfolio Agent', 'Choose zero or more sized paper proposals.'),
    'critic': ('Critic', 'Challenge unsupported assumptions and selections.'),
    'risk': ('Risk Engine', 'Apply deterministic cash, holdings and risk rules.'),
    'final': ('Final outcome', 'Record the paper outcome and operator action.'),
}
KNOWN_PROPOSAL_STATUSES = {'PENDING', 'YES', 'NO', 'EXPIRED'}
KNOWN_PAPER_ACTION_STATUSES = {'FILLED'}
KNOWN_NEGATIVE_RESULT_STATUSES = {
    'REJECTED_NO_STRATEGY_SIGNAL',
    'REJECTED',
    'MISSING_DATA',
    'NEAR_EXPIRY_BUY_BLOCKED',
    'UNAFFORDABLE_OR_UNHELD',
    'RISK_BLOCKED',
    'UNFILLED',
}
PUBLIC_DETAIL_FIELDS = {
    'evidence': ('read_tools', 'quote_count', 'volatility_count', 'history_counts', 'signals', 'blocked'),
    'research': ('summary', 'compared_symbols', 'news_checked', 'news', 'missing_evidence'),
    'portfolio': ('picks', 'reason'),
    'critic': ('counterargument', 'rejected_instruments'),
    'risk': ('status', 'results', 'real_execution'),
    'final': ('status', 'results', 'reason', 'api_cost_estimate_usd', 'completed_at'),
}


def _aware(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def _event_time(record):
    return _aware(record.get('timestamp')) or _aware(record.get('_created_at'))


def _row_order(record):
    value = record.get('_row_id')
    return value if isinstance(value, int) else 0


def _stage_key(record):
    event = record.get('event')
    if not isinstance(event, str):
        return None
    if event in {'data_collected', 'strategy_evaluated'}:
        return 'evidence'
    if event in {'stage_started', 'stage_completed'}:
        role = record.get('role')
        return role if isinstance(role, str) and role in {'research', 'portfolio', 'critic'} else None
    if event == 'risk_evaluated':
        return 'risk'
    if event == 'cycle_terminal':
        return 'final'
    return None


def _record_incomplete(record):
    malformed_candidate = False
    rows = record.get('candidate_decisions')
    if isinstance(rows, list):
        malformed_candidate = any(
            not isinstance(row, dict)
            or not isinstance(row.get('instrument'), str)
            or not isinstance(row.get('lane'), str)
            or not isinstance(row.get('state'), str)
            for row in rows
        )
    return (
        not isinstance(record.get('event'), str)
        or ('role' in record and not isinstance(record.get('role'), str))
        or ('data_mode' in record and not isinstance(record.get('data_mode'), str))
        or ('status' in record and not isinstance(record.get('status'), str))
        or ('signals' in record and not isinstance(record.get('signals'), list))
        or ('quote_count' in record and _count(record.get('quote_count')) is None)
        or ('volatility_count' in record and _count(record.get('volatility_count')) is None)
        or ('candidate_decisions' in record and not isinstance(record.get('candidate_decisions'), list))
        or malformed_candidate
        or ('output' in record and not isinstance(record.get('output'), dict))
        or ('payload' in record and not isinstance(record.get('payload'), dict))
    )


def _text(value, limit=2000):
    return value[:limit] if isinstance(value, str) and value else None


def _text_list(value, *, limit=50, item_limit=500):
    if not isinstance(value, list):
        return []
    return [item[:item_limit] for item in value if isinstance(item, str) and item][:limit]


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _public_news(value):
    rows = []
    if not isinstance(value, list):
        return rows
    for item in value[:30]:
        if not isinstance(item, dict):
            continue
        row = {}
        for field in ('fact', 'source_url', 'observed_at'):
            public = _text(item.get(field), 1000 if field == 'fact' else 500)
            if public:
                row[field] = public
        if row:
            rows.append(row)
    return rows


def _public_rows(value, fields):
    rows = []
    if not isinstance(value, list):
        return rows
    for item in value[:50]:
        if not isinstance(item, dict):
            continue
        row = {}
        for field in fields:
            raw = item.get(field)
            if isinstance(raw, (str, int, float, bool)) or raw is None:
                row[field] = raw
        if row:
            rows.append(row)
    return rows


def _public_results(value):
    if not isinstance(value, list):
        return []
    rows = []
    for source in value[:50]:
        if not isinstance(source, dict):
            continue
        public = {}
        for field in ('status', 'card_id', 'instrument', 'lane', 'reason_code', 'reason'):
            raw = source.get(field)
            if isinstance(raw, (str, int, float, bool)) or raw is None:
                public[field] = raw
        reasons = _text_list(source.get('reasons'), limit=30, item_limit=240)
        if reasons:
            public['reasons'] = reasons
        if public:
            rows.append(public)
    return rows


def _public_summary(record, key):
    output = record.get('output') if isinstance(record.get('output'), dict) else {}
    payload = record.get('payload') if isinstance(record.get('payload'), dict) else {}
    decision = payload.get('decision') if isinstance(payload.get('decision'), dict) else {}
    quote_count = _count(record.get('quote_count'))
    volatility_count = _count(record.get('volatility_count'))
    evidence_summary = (
        f"{quote_count} quotes and {volatility_count} volatility series recorded"
        + (
            f" in the {record.get('record_source').lower()}."
            if isinstance(record.get('record_source'), str)
            else '.'
        )
        if quote_count is not None and volatility_count is not None
        else 'Evidence counts were not recorded.'
    )
    values = {
        'evidence': evidence_summary,
        'research': _text(output.get('summary')),
        'portfolio': _text(output.get('reason')),
        'critic': _text(output.get('counterargument')),
        'risk': (
            'Deterministic risk checks completed.'
            if record.get('status') == 'completed'
            else 'Deterministic risk checks blocked the proposal.'
            if record.get('status') == 'blocked'
            else _text(record.get('reason'))
            if record.get('status') == 'not_applicable'
            else 'Deterministic risk checks did not run.'
        ),
        'final': _text(payload.get('reason')) or _text(decision.get('reason')),
    }
    return str(values.get(key) or 'Not recorded')[:2000]


def _public_details(record, key):
    if key in {'research', 'portfolio', 'critic'}:
        source = record.get('output')
    elif key == 'final':
        source = record.get('payload')
    else:
        source = record
    if not isinstance(source, dict):
        return {}
    if key == 'evidence':
        details = {
            'read_tools': _text_list(source.get('read_tools')),
            'quote_count': _count(source.get('quote_count')),
            'volatility_count': _count(source.get('volatility_count')),
            'history_counts': {
                str(name)[:160]: count
                for name, count in (source.get('history_counts') or {}).items()
                if isinstance(source.get('history_counts'), dict)
                and isinstance(name, str) and _count(count) is not None
            } if isinstance(source.get('history_counts'), dict) else {},
            'signals': _public_rows(source.get('signals'), ('instrument', 'strategy', 'reason_code')),
            'blocked': _public_rows(source.get('blocked'), ('instrument', 'reason_code', 'reason')),
            'record_source': _text(source.get('record_source'), 80),
        }
    elif key == 'research':
        details = {
            'summary': _text(source.get('summary')),
            'compared_symbols': _text_list(source.get('compared_symbols')),
            'news_checked': source.get('news_checked') if isinstance(source.get('news_checked'), bool) else None,
            'news': _public_news(source.get('news')),
            'missing_evidence': _text_list(source.get('missing_evidence')),
        }
    elif key == 'portfolio':
        details = {
            'picks': _public_rows(source.get('picks'), (
                'instrument', 'lane', 'side', 'quantity', 'limit_price', 'max_loss_usd',
                'thesis', 'good_if', 'invalidation', 'confidence', 'asset_class',
            )),
            'reason': _text(source.get('reason')),
        }
    elif key == 'critic':
        details = {
            'counterargument': _text(source.get('counterargument')),
            'rejected_instruments': _text_list(source.get('rejected_instruments')),
        }
    elif key in {'risk', 'final'}:
        details = {
            'status': _text(source.get('status'), 80),
            'results': _public_results(source.get('results')),
            'real_execution': _text(source.get('real_execution'), 80),
            'reason': _text(source.get('reason')),
            'api_cost_estimate_usd': _text(source.get('api_cost_estimate_usd'), 80),
            'completed_at': _text(source.get('completed_at'), 100),
            'proposal_count': _count(source.get('proposal_count')),
            'record_source': _text(source.get('record_source'), 80),
        }
    else:
        details = {}
    return {field: value for field, value in details.items() if value not in (None, [], {})}


def _duration(events):
    times = [_event_time(event) for event in events]
    recorded = [value for value in times if value]
    if len(recorded) < 2:
        return 'Not recorded'
    seconds = max(0, int((max(recorded) - min(recorded)).total_seconds()))
    return f'{seconds} second' + ('' if seconds == 1 else 's')


def _mode_label(value):
    labels = {'live_readonly': 'Live read-only', 'fixture': 'Fixture', 'not_recorded': 'Not recorded'}
    if not isinstance(value, str) or not value:
        return 'Not recorded'
    return labels.get(value, value.replace('_', ' ').capitalize())


def _money_value(value):
    if not isinstance(value, (str, int, float, Decimal)) or isinstance(value, bool):
        return None
    try:
        return str(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return None


def _inspector(key, mandate, summary, details, status):
    inputs = []
    if key == 'evidence':
        if details.get('read_tools'):
            inputs.append(f"Read-only tools: {', '.join(details['read_tools'])}")
        if 'quote_count' in details:
            inputs.append(f"Quotes recorded: {details['quote_count']}")
        if 'volatility_count' in details:
            inputs.append(f"Volatility series recorded: {details['volatility_count']}")
    elif key == 'research' and details.get('compared_symbols'):
        inputs.append(f"Candidates supplied: {', '.join(details['compared_symbols'])}")
    elif key == 'portfolio':
        inputs.append('Expected input: Research Agent work product. Recorded input references are not available.')
    elif key == 'critic':
        inputs.append('Expected inputs: Portfolio proposal and Research work product. Recorded input references are not available.')
    elif key == 'risk' and 'proposal_count' in details:
        inputs.append(f"Portfolio decision: {details['proposal_count']} picks.")
    elif key == 'risk':
        inputs.append('Expected inputs: proposal, current quotes, positions and settled cash. Recorded input references are not available.')
    elif key == 'final':
        inputs.append('Expected inputs: agent work and deterministic risk result. Recorded input references are not available.')
    sources = []
    if details.get('record_source'):
        sources.append(details['record_source'])
    findings = [summary]
    for news in details.get('news', []):
        if isinstance(news, dict):
            if isinstance(news.get('fact'), str):
                findings.append(news['fact'])
            if isinstance(news.get('source_url'), str):
                sources.append(news['source_url'])
    if details.get('rejected_instruments'):
        findings.append('Rejected instruments: ' + ', '.join(details['rejected_instruments']))
    for pick in details.get('picks', []):
        if isinstance(pick, dict) and isinstance(pick.get('instrument'), str):
            parts = [f"Proposed paper instrument: {pick['instrument']}"]
            if pick.get('side') is not None:
                parts.append(str(pick['side']))
            if pick.get('quantity') is not None:
                parts.append(f"quantity {pick['quantity']}")
            if pick.get('limit_price') is not None:
                parts.append(f"limit ${pick['limit_price']}")
            if pick.get('max_loss_usd') is not None:
                parts.append(f"maximum loss ${pick['max_loss_usd']}")
            findings.append(' · '.join(parts))
            if isinstance(pick.get('thesis'), str):
                findings.append('Recorded thesis: ' + pick['thesis'])
    blockers = list(details.get('missing_evidence', []))
    for result in details.get('results', []):
        if isinstance(result, dict) and str(result.get('status', '')).upper() == 'RISK_BLOCKED':
            reasons = result.get('reasons') if isinstance(result.get('reasons'), list) else []
            blockers.extend(reasons)
            if not reasons:
                blockers.append(str(result.get('reason') or result.get('reason_code') or 'Risk rule blocked the proposal.'))
    next_stage = {
        'evidence': 'Research Agent', 'research': 'Portfolio Agent',
        'portfolio': 'Critic', 'critic': 'Risk Engine',
        'risk': 'Final outcome', 'final': 'Operator record',
    }[key]
    if status == 'blocked':
        handoff = f'{STAGE_META[key][0]} stopped the flow; no normal handoff was made to {next_stage}.'
    elif status == 'skipped' and key == 'risk':
        handoff = 'Risk checks were skipped; no checked proposal was handed to Final outcome.'
    elif status == 'not_applicable' and key == 'risk':
        handoff = 'No proposal entered deterministic risk checks.'
    elif status in {'waiting', 'unavailable'}:
        handoff = 'Handoff not recorded.'
    elif status == 'active':
        handoff = 'Work is in progress; no completed handoff is recorded.'
    elif key == 'final':
        handoff = 'Final outcome was recorded for operator inspection.'
    else:
        handoff = f'Expected next step: {next_stage}. A recorded handoff was not stored.'
    return {
        'mandate': mandate,
        'inputs': inputs or ['Not recorded'],
        'findings': findings,
        'sources': sources or ['Not recorded'],
        'blockers': blockers or ['None recorded'],
        'handoff': handoff,
    }


def _stage_status(key, event, *, terminal_state, terminal_recorded, step, last_recorded_step):
    if event is None:
        if not terminal_recorded and step > last_recorded_step:
            return 'waiting'
        return 'unavailable'

    event_name = event.get('event') if isinstance(event.get('event'), str) else None
    event_status = event.get('status') if isinstance(event.get('status'), str) else None

    if key == 'final':
        if terminal_state.startswith('FAILED') or terminal_state.startswith('NOT_ISSUED'):
            return 'blocked'
        return 'completed' if terminal_state == 'COMPLETED' else 'unavailable'
    if key == 'risk':
        if event_status == 'completed':
            return 'completed'
        if event_status == 'blocked':
            return 'blocked'
        if event_status == 'not_applicable':
            return 'not_applicable'
        if event_status in {'not_run', 'skipped'}:
            return 'skipped'
        return 'unavailable'
    if key in {'research', 'portfolio', 'critic'}:
        if event_name == 'stage_started':
            return 'active'
        return 'completed' if event_name == 'stage_completed' else 'unavailable'
    if key == 'evidence':
        return 'completed' if event_name in {'data_collected', 'strategy_evaluated'} else 'unavailable'
    return 'unavailable'


def normalize_candidate_decisions(events):
    chosen = {'A': {}, 'B': {}}
    for event in events:
        raw_rows = event.get('candidate_decisions') or []
        if not isinstance(raw_rows, list):
            continue
        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue
            lane = raw.get('lane')
            state = raw.get('state')
            instrument = raw.get('instrument')
            if (
                not isinstance(lane, str)
                or lane not in VALID_LANES
                or not isinstance(state, str)
                or state not in STATE_PRIORITY
                or not isinstance(instrument, str)
                or not instrument
            ):
                continue
            reason_code = (
                raw.get('reason_code')
                if isinstance(raw.get('reason_code'), str)
                else 'not_recorded'
            )
            reason = (
                raw.get('reason')
                if isinstance(raw.get('reason'), str) and raw.get('reason')
                else REASON_LABELS.get(reason_code, REASON_LABELS['not_recorded'])
            )
            refs = raw.get('source_refs') if isinstance(raw.get('source_refs'), list) else []
            item = {
                'instrument': instrument[:160],
                'lane': lane,
                'state': state,
                'reason_code': reason_code[:80],
                'reason': reason[:1200],
                'deciding_stage': DECIDING_STAGE[state],
                'rank': raw.get('rank') if isinstance(raw.get('rank'), int) else None,
                'strategy_signal': (
                    raw.get('strategy_signal')
                    if isinstance(raw.get('strategy_signal'), str)
                    else None
                ),
                'data_freshness': (
                    raw.get('data_freshness')
                    if isinstance(raw.get('data_freshness'), str)
                    else None
                ),
                'source_refs': [ref[:240] for ref in refs if isinstance(ref, str)][:20],
            }
            prior = chosen[lane].get(instrument)
            if prior is None or STATE_PRIORITY[state] > STATE_PRIORITY[prior['state']]:
                chosen[lane][instrument] = item
    return {
        lane: sorted(
            items.values(),
            key=lambda row: (
                -STATE_PRIORITY[row['state']],
                row['rank'] if row['rank'] is not None else 10**9,
                row['instrument'],
            ),
        )
        for lane, items in chosen.items()
    }


def project_decision_room(records, cards):
    groups = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        cycle_id = record.get('trace_id')
        if not isinstance(cycle_id, str) or not cycle_id:
            continue
        groups.setdefault(cycle_id, []).append(record)
    pending_by_id = {
        card['id']: card
        for card in cards
        if isinstance(card, dict) and isinstance(card.get('id'), str)
    }
    reviews = []
    for cycle_id, events in groups.items():
        if not any(event.get('event') in CYCLE_REVIEW_EVENTS for event in events):
            continue
        ordered = sorted(
            events,
            key=lambda item: (
                _event_time(item) or datetime.min.replace(tzinfo=timezone.utc),
                _row_order(item),
            ),
        )
        latest = {}
        for event in ordered:
            key = _stage_key(event)
            if key:
                latest[key] = (
                    {**latest[key], **event}
                    if key == 'evidence' and key in latest
                    else event
                )
        terminal = latest.get('final') or {}
        payload = terminal.get('payload') if isinstance(terminal.get('payload'), dict) else {}
        public_status = payload.get('status') if isinstance(payload.get('status'), str) else ''
        terminal_state = public_status.upper()
        payload_results = payload.get('results') if isinstance(payload.get('results'), list) else []
        decision = payload.get('decision') if isinstance(payload.get('decision'), dict) else {}
        picks = decision.get('picks') if isinstance(decision.get('picks'), list) else None
        projected = dict(latest)
        if (
            'evidence' not in projected
            and _count(payload.get('quote_count')) is not None
            and _count(payload.get('volatility_count')) is not None
        ):
            projected['evidence'] = {
                'event': 'data_collected',
                'quote_count': payload['quote_count'],
                'volatility_count': payload['volatility_count'],
                'read_tools': payload.get('read_tools'),
                'record_source': 'Final cycle record',
            }
        if (
            'risk' not in projected
            and terminal_state == 'COMPLETED'
            and picks == []
            and payload_results == []
        ):
            projected['risk'] = {
                'event': 'risk_evaluated',
                'status': 'not_applicable',
                'proposal_count': 0,
                'reason': 'No risk check was needed because Portfolio proposed no trades.',
                'record_source': 'Final cycle record',
            }
        record_incomplete = any(_record_incomplete(event) for event in ordered)
        last_recorded_step = max(
            (STAGE_ORDER.index(key) + 1 for key in projected),
            default=0,
        )
        terminal_recorded = 'final' in latest
        stages = []
        for step, key in enumerate(STAGE_ORDER, 1):
            event = projected.get(key)
            status = _stage_status(
                key,
                event,
                terminal_state=terminal_state,
                terminal_recorded=terminal_recorded,
                step=step,
                last_recorded_step=last_recorded_step,
            )
            label, mandate = STAGE_META[key]
            summary = _public_summary(event or {}, key)
            details = _public_details(event or {}, key)
            stages.append(
                {
                    'key': key,
                    'step': step,
                    'label': label,
                    'mandate': mandate,
                    'status': status,
                    'status_label': (
                        'Not run' if status == 'skipped'
                        else 'Not needed' if status == 'not_applicable'
                        else status.replace('_', ' ').title()
                    ),
                    'tone': 'warn' if status in {'blocked', 'unavailable', 'skipped'} else 'neutral',
                    'summary': summary,
                    'output_line': summary[:160],
                    'details': details,
                    'inspector': _inspector(key, mandate, summary, details, status),
                }
            )
        result_ids = {
            item.get('card_id')
            for item in payload_results
            if isinstance(item, dict) and isinstance(item.get('card_id'), str)
        }
        pending = [
            pending_by_id[key]
            for key in result_ids
            if key in pending_by_id and pending_by_id[key].get('status') == 'PENDING'
        ]
        recorded = [_event_time(event) for event in ordered if _event_time(event)]
        data_mode = next(
            (
                event.get('data_mode')
                for event in reversed(ordered)
                if isinstance(event.get('data_mode'), str) and event.get('data_mode')
            ),
            'not_recorded',
        )
        refresh = next(
            (event for event in reversed(ordered) if event.get('event') == 'final_refresh'),
            None,
        )
        if record_incomplete:
            freshness = 'Incomplete'
        elif isinstance(refresh, dict) and isinstance(refresh.get('missing_instruments'), list):
            freshness = 'Incomplete' if refresh['missing_instruments'] else 'Refreshed at completion'
        elif data_mode == 'fixture':
            freshness = 'Fixture'
        else:
            freshness = 'Not recorded'
        risk_blocked = any(
            isinstance(item, dict) and str(item.get('status', '')).upper() == 'RISK_BLOCKED'
            for item in payload_results
        )
        result_statuses = {
            str(item.get('status', '')).upper()
            for item in payload_results
            if isinstance(item, dict) and isinstance(item.get('status'), str)
        }
        malformed_result = any(
            not isinstance(item, dict) or not isinstance(item.get('status'), str)
            for item in payload_results
        )
        known_result_statuses = (
            KNOWN_PROPOSAL_STATUSES
            | KNOWN_PAPER_ACTION_STATUSES
            | KNOWN_NEGATIVE_RESULT_STATUSES
        )
        unknown_result = malformed_result or bool(result_statuses - known_result_statuses)
        if unknown_result:
            record_incomplete = True
            freshness = 'Incomplete'
        proposal_recorded = bool(result_statuses & KNOWN_PROPOSAL_STATUSES)
        paper_action_recorded = bool(result_statuses & KNOWN_PAPER_ACTION_STATUSES)
        negative_result_only = bool(result_statuses) and result_statuses <= KNOWN_NEGATIVE_RESULT_STATUSES
        # Recorded proposal that a later stage stopped: derive only from saved
        # structured fields (decision.picks, critic.rejected_instruments, results).
        picked = [str(p.get('instrument')) for p in (picks or [])
                  if isinstance(p, dict) and isinstance(p.get('instrument'), str) and p.get('instrument')]
        critic_payload = payload.get('critic') if isinstance(payload.get('critic'), dict) else {}
        critic_rejected = critic_payload.get('rejected_instruments')
        critic_rejected = {str(x) for x in critic_rejected} if isinstance(critic_rejected, list) else set()
        rejected_results = {
            str(item.get('instrument')) for item in payload_results
            if isinstance(item, dict) and str(item.get('status', '')).upper() == 'REJECTED'
            and isinstance(item.get('instrument'), str)
        }
        stopped_by_critic = [i for i in picked if i in critic_rejected and i in rejected_results]
        critic_reason = critic_payload.get('counterargument') if isinstance(critic_payload.get('counterargument'), str) else None
        decision_type = decision.get('type') if isinstance(decision.get('type'), str) else None
        desk_results = [r for r in (payload.get('desk_results') or []) if isinstance(r, dict)]
        desk_card_waiting = any(r.get('status') == 'PENDING' and r.get('arm') == 'with_approvals' for r in desk_results)
        desk_filled = sorted({str(r.get('arm')) for r in desk_results if r.get('status') == 'filled'})
        desk_instrument = next((str(r.get('instrument')) for r in desk_results if isinstance(r.get('instrument'), str)), None)
        signal_instruments = [str(x) for x in decision.get('signal_instruments', []) if isinstance(x, str)] \
            if isinstance(decision.get('signal_instruments'), list) else []
        if pending:
            outcome_label = 'Paper proposal waiting'
            action = f"Review {len(pending)} paper proposal" + ('s' if len(pending) != 1 else '')
        elif terminal_state.startswith('FAILED'):
            outcome_label, action = 'Review failed', 'Inspect the recorded failure'
        elif terminal_state.startswith('NOT_ISSUED'):
            outcome_label, action = 'Review interrupted', 'Inspect the missing requirement'
        elif risk_blocked:
            outcome_label, action = 'Risk blocked', 'Nothing needs your approval'
        elif unknown_result:
            outcome_label, action = 'Completion unconfirmed', 'Check run history'
        elif terminal_state == 'COMPLETED' and decision_type in {'DESK_ENTRY', 'DESK_ENTRY_BLOCKED', 'HOLD_CAPABILITY_GAP'}:
            outcome_label, action = {
                'DESK_ENTRY': ('Desk rule entry', 'Check the desk-rule card' if desk_card_waiting else 'Nothing needs your approval'),
                'DESK_ENTRY_BLOCKED': ('Desk rule blocked', 'Nothing needs your approval'),
                'HOLD_CAPABILITY_GAP': ('Signal not yet actionable', 'Nothing needs your approval'),
            }[decision_type]
        elif terminal_state == 'COMPLETED' and stopped_by_critic and negative_result_only:
            outcome_label, action = 'Proposal rejected by Critic', 'Nothing needs your approval'
        elif terminal_state == 'COMPLETED' and (
            (picks == [] and payload_results == []) or negative_result_only
        ):
            outcome_label, action = 'Hold cash', 'Nothing needs your approval'
        elif terminal_state == 'COMPLETED' and paper_action_recorded:
            outcome_label, action = 'Completed paper action', 'Nothing needs your approval'
        elif terminal_state == 'COMPLETED' and proposal_recorded:
            outcome_label, action = 'Paper proposal recorded', 'Check the recorded approval status'
        elif terminal_state == 'COMPLETED':
            outcome_label, action = 'Completion unconfirmed', 'Check run history'
        elif any(stage['status'] == 'active' for stage in stages):
            outcome_label, action = 'Review in progress', 'Wait for the recorded outcome'
        else:
            outcome_label, action = 'Completion unconfirmed', 'Check run history'
        candidate_details_recorded = any(
            'candidate_decisions' in event and isinstance(event.get('candidate_decisions'), list)
            for event in ordered
        )
        if unknown_result:
            proposal_state = 'unknown'
        elif pending or proposal_recorded or paper_action_recorded:
            proposal_state = 'recorded'
        elif stopped_by_critic and negative_result_only:
            proposal_state = 'stopped'
        elif (picks == [] and payload_results == []) or negative_result_only:
            proposal_state = 'none'
        else:
            proposal_state = 'unknown'
        if proposal_state == 'stopped':
            for stage in stages:
                if stage['key'] == 'portfolio':
                    stage['status_label'] = 'Proposed'
                elif stage['key'] == 'critic':
                    stage.update(status='blocked', status_label='Rejected', tone='warn')
                elif stage['key'] == 'risk':
                    stage.update(status='not_applicable', status_label='Not reached', tone='neutral')
                elif stage['key'] == 'final':
                    stage['status_label'] = 'No card'
        from . import run_log, run_checks
        ai_gate = run_log.gate(ordered)
        log = run_log.build_log(ordered)
        if ai_gate and not ai_gate['open']:
            called = {entry['actor'] for entry in log}
            for stage in stages:
                if stage['key'] in run_log.AI_STAGES and stage['key'] not in called:
                    stage.update(status='skipped', status_label='Not called', tone='neutral',
                                 summary='Not called: the AI gate stayed closed for this run'
                                 + (f" ({ai_gate['reason']})." if ai_gate.get('reason') else '.'))
        completed_stages = sum(stage['status'] in {'completed', 'blocked'} for stage in stages)
        reviews.append(
            {
                'review_id': cycle_id,
                'timestamp': max(recorded).isoformat() if recorded else None,
                'status': (public_status or 'unconfirmed').lower(),
                'data_mode': data_mode,
                'stages': stages,
                'lanes': normalize_candidate_decisions(ordered),
                'selection_recorded': candidate_details_recorded,
                'proposal_state': proposal_state,
                'proposed_instruments': picked,
                'stopped_by': 'critic' if (stopped_by_critic and proposal_state == 'stopped') else None,
                'stopped_instruments': stopped_by_critic if proposal_state == 'stopped' else [],
                'critic_reason': critic_reason if proposal_state == 'stopped' else None,
                'decision_type': decision_type,
                'desk': {'instrument': desk_instrument, 'filled_arms': desk_filled,
                         'card_waiting': desk_card_waiting,
                         'blocked_reasons': sorted({str(r.get('reason')) for r in desk_results
                                                    if r.get('status') == 'BLOCKED' and r.get('reason')})},
                'signal_instruments': signal_instruments,
                'decision_reason': _text(decision.get('reason'), 400),
                'ai_gate': ai_gate,
                'log': log,
                'stage_times': run_log.stage_times(ordered),
                'strategy_blocked': run_log.strategy_blocked(ordered),
                'checks': run_checks.build_checks(ordered),
                'agent_usage': run_log.agent_usage(records, ordered),
                'default_stage': next(
                    (
                        stage['key']
                        for stage in stages
                        if stage['status'] in {'blocked', 'active', 'unavailable', 'waiting'}
                    ),
                    'final',
                ),
                'record_incomplete': record_incomplete,
                'outcome': {
                    'pending_count': len(pending),
                    'reason': _public_summary(terminal, 'final'),
                },
                'header': {
                    'short_id': cycle_id[:12],
                    'outcome': outcome_label,
                    'action': action,
                    'data_mode': _mode_label(data_mode),
                    'freshness': freshness,
                    'duration': _duration(ordered),
                    'api_cost_estimate_usd': _money_value(payload.get('api_cost_estimate_usd')),
                    'completed_stages': completed_stages,
                    'expected_stages': len(STAGE_ORDER),
                    'paper_only': True,
                },
                'technical_events': [
                    {
                        'event': event.get('event') if isinstance(event.get('event'), str) else 'malformed',
                        'timestamp': (
                            _event_time(event).isoformat() if _event_time(event) else None
                        ),
                    }
                    for event in ordered
                ],
            }
        )
    from .run_log import flow
    for review in reviews:
        review['flow'] = flow(review, review['log'])
    return sorted(
        reviews,
        key=lambda review: _aware(review['timestamp'])
        or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
