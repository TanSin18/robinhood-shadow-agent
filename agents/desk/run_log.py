"""Readable, whitelisted run log and recorded flow for one cycle trace.

Presentation projection only. Every value shown is copied from a named,
public field of a recorded trace event; nothing is inferred from prose and no
account, credential or identifier field is ever read. Flow edges describe the
recorded order of stage events in this run, not message passing.
"""
from __future__ import annotations

from datetime import datetime

ACTORS = ('system', 'evidence', 'gate', 'research', 'portfolio', 'critic', 'risk', 'final')
PIPELINE = ('evidence', 'research', 'portfolio', 'critic', 'risk', 'final')
AI_STAGES = ('research', 'portfolio', 'critic')


def _aware(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def _time(event):
    return _aware(event.get('timestamp')) or _aware(event.get('_created_at'))


def _s(value, limit=240):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str) and value.strip():
        text = ' '.join(value.split())
        return text if len(text) <= limit else text[:limit - 1] + '…'
    return None


def _strs(value, limit=40, item=80):
    return [s for s in (_s(v, item) for v in value[:limit]) if s] if isinstance(value, list) else []


def _first_sentence(value, limit=240):
    text = _s(value, 4000)
    if not text:
        return None
    cut = text.find('. ')
    sentence = text if cut == -1 else text[:cut + 1]
    return sentence if len(sentence) <= limit else sentence[:limit - 1] + '…'


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _states(rows):
    counts = {}
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and isinstance(row.get('state'), str):
            counts[row['state']] = counts.get(row['state'], 0) + 1
    return ', '.join(f'{n} {state}' for state, n in sorted(counts.items())) or None


def _signals(rows):
    out = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and _s(row.get('instrument'), 16):
            bits = [_s(row['instrument'], 16)]
            if _s(row.get('lane'), 4):
                bits.append('lane ' + _s(row['lane'], 4))
            if _s(row.get('confidence'), 8):
                bits.append('confidence ' + _s(row['confidence'], 8))
            out.append(bits[0] + (' (' + ', '.join(bits[1:]) + ')' if bits[1:] else ''))
    return out[:12]


def _blocked(value):
    """Strategy → {instrument: reason} or list rows; summarize counts only."""
    if isinstance(value, dict):
        parts = []
        for strategy, rows in value.items():
            if isinstance(strategy, str) and isinstance(rows, dict):
                parts.append(f'{_s(strategy, 40)}: {len(rows)} not eligible')
        return parts[:8]
    if isinstance(value, list):
        return [f'{len(value)} not eligible']
    return []


def _blocked_rows(value):
    rows = []
    if isinstance(value, dict):
        for strategy, items in value.items():
            if isinstance(strategy, str) and isinstance(items, dict):
                for instrument, reason in items.items():
                    if _s(instrument, 16) and _s(reason, 160):
                        rows.append({'strategy': _s(strategy, 40), 'instrument': _s(instrument, 16),
                                     'reason': _s(reason, 160)})
    return rows[:120]


def _results(value):
    out = []
    for row in value if isinstance(value, list) else []:
        if isinstance(row, dict) and _s(row.get('status'), 40):
            name = _s(row.get('instrument'), 16) or _s(row.get('arm'), 30) or 'result'
            out.append(f"{name}: {_s(row['status'], 40)}")
    return out[:12]


def _entry(event, actor, title, detail=(), tone='info'):
    when = _time(event)
    return {'actor': actor, 'event': _s(event.get('event'), 60) or 'malformed',
            'time': when.isoformat() if when else None, 'title': title,
            'detail': [d for d in detail if d], 'tone': tone}


def describe(event, started):
    name = event.get('event')
    role = event.get('role') if event.get('role') in AI_STAGES else None
    if name == 'cycle_started':
        return _entry(event, 'system', 'Run started', [
            'Trigger: ' + (_s(event.get('trigger'), 40) or 'not recorded'),
            'Data mode: ' + (_s(event.get('data_mode'), 40) or 'not recorded')])
    if name == 'data_collected':
        quotes, vols = _count(event.get('quote_count')), _count(event.get('volatility_count'))
        hist = event.get('history_counts') if isinstance(event.get('history_counts'), dict) else {}
        return _entry(event, 'evidence', 'Collected market data', [
            f'{quotes if quotes is not None else "?"} quotes · {vols if vols is not None else "?"} volatility series · {len(hist)} price histories',
            'Read-only tools: ' + (', '.join(_strs(event.get('read_tools'))) or 'not recorded')])
    if name == 'strategy_evaluated':
        signals = _signals(event.get('signals'))
        return _entry(event, 'evidence', f'Scored the universe: {len(signals)} qualified signal' + ('' if len(signals) == 1 else 's'), [
            'Signals: ' + (', '.join(signals) or 'none'),
            'Not eligible: ' + ('; '.join(_blocked(event.get('blocked'))) or 'none recorded'),
            'Candidate states: ' + (_states(event.get('candidate_decisions')) or 'not recorded'),
            ('Options: ' + str(event['option_screen'].get('contracts_seen')) + ' contracts screened, '
             + str(event['option_screen'].get('passed_all_filters')) + ' passed every filter')
            if isinstance(event.get('option_screen'), dict) and 'contracts_seen' in event['option_screen'] else None],
            'good' if signals else 'info')
    if name == 'ai_invocation_gate':
        opened = event.get('invoke') is True
        ids = _strs(event.get('candidate_ids'), 10, 16)
        return _entry(event, 'gate', ('AI gate opened for ' + ', '.join(ids)) if opened and ids else
                      'AI gate opened' if opened else 'AI gate stayed closed — no AI called', [
            'Reason code: ' + (_s(event.get('reason'), 80) or 'not recorded'),
            'Reserved AI cost: $' + (_s(event.get('reserved_cost_usd'), 20) or 'not recorded')],
            'good' if opened else 'muted')
    if name == 'stage_started' and role:
        return _entry(event, role, 'Started', ['Agent: ' + (_s(event.get('agent'), 40) or 'not recorded')])
    if name == 'stage_completed' and role:
        output = event.get('output') if isinstance(event.get('output'), dict) else {}
        start, end = started.get(role), _time(event)
        took = f'{(end - start).total_seconds():.1f}s' if start and end else None
        detail = ['Took ' + took if took else None]
        tone, title = 'good', 'Finished'
        if role == 'research':
            compared = _strs(output.get('compared_symbols'), 20, 16)
            missing = _strs(output.get('missing_evidence'), 20, 200)
            title = f'Compared {len(compared)} idea' + ('' if len(compared) == 1 else 's')
            detail += ['Compared: ' + (', '.join(compared) or 'none recorded'),
                       'News checked: ' + ('yes' if output.get('news_checked') is True else 'no' if output.get('news_checked') is False else 'not recorded'),
                       f'Listed {len(missing)} missing fact' + ('' if len(missing) == 1 else 's'),
                       'Summary: ' + (_first_sentence(output.get('summary')) or 'not saved')]
        elif role == 'portfolio':
            picks = [_s(p.get('instrument'), 16) for p in output.get('picks', []) if isinstance(p, dict)] if isinstance(output.get('picks'), list) else []
            picks = [p for p in picks if p]
            title = ('Proposed ' + ', '.join(picks)) if picks else 'Proposed nothing'
            detail += ['Why: ' + (_first_sentence(output.get('reason')) or 'not saved')]
        elif role == 'critic':
            rejected = _strs(output.get('rejected_instruments'), 10, 40)
            title = ('Rejected ' + ', '.join(rejected)) if rejected else 'Raised no rejection'
            tone = 'stop' if rejected else 'good'
            detail += ['Counterargument: ' + (_first_sentence(output.get('counterargument')) or 'not saved')]
        detail.append('Idea states after this step: ' + (_states(event.get('candidate_decisions')) or 'not recorded'))
        return _entry(event, role, title, detail, tone)
    if name == 'final_refresh':
        return _entry(event, 'risk', 'Refreshed prices before the safety check', [
            'Instruments: ' + (', '.join(_strs(event.get('instruments'), 10, 16)) or 'none'),
            'Missing: ' + (', '.join(_strs(event.get('missing_instruments'), 10, 16)) or 'none')])
    if name == 'risk_evaluated':
        results = _results(event.get('results'))
        blocked = any('BLOCKED' in r for r in results)
        return _entry(event, 'risk', 'Safety rules ' + (_s(event.get('status'), 30) or 'ran'), [
            'Results: ' + (', '.join(results) or 'no trades to check'),
            'Real execution: ' + (_s(event.get('real_execution'), 30) or 'not recorded'),
            _first_sentence(event.get('reason'))], 'stop' if blocked else 'info')
    if name == 'cycle_terminal':
        payload = event.get('payload') if isinstance(event.get('payload'), dict) else {}
        decision = payload.get('decision') if isinstance(payload.get('decision'), dict) else {}
        status = _s(payload.get('status'), 40) or 'not recorded'
        return _entry(event, 'final', 'Run finished: ' + status.replace('_', ' ').lower(), [
            'Decision: ' + (_s(decision.get('type'), 40) or 'not recorded'),
            'Reason: ' + (_first_sentence(decision.get('reason') or payload.get('reason')) or 'not saved'),
            'Results: ' + (', '.join(_results(payload.get('results')) + _results(payload.get('desk_results'))) or 'none'),
            ('Desk exits: ' + ', '.join(_results(payload.get('desk_exits')))) if payload.get('desk_exits') else None,
            'AI cost estimate: $' + (_s(payload.get('api_cost_estimate_usd'), 20) or 'not recorded')],
            'good' if status.upper() == 'COMPLETED' else 'stop')
    if name == 'bridge_failure':
        return _entry(event, 'system', 'Broker read bridge failed', [_s(event.get('reason_code') or event.get('reason'), 120)], 'stop')
    if name == 'bounded_attempt_started':
        return _entry(event, 'system', 'Bounded AI attempt started', [])
    if name == 'cycle_completed':
        return _entry(event, 'final', 'Cycle bookkeeping completed', [])
    return _entry(event, 'system', (_s(name, 60) or 'Unrecognized event').replace('_', ' ').capitalize(), [])


def build_log(ordered):
    started, rows = {}, []
    first = next((_time(e) for e in ordered if _time(e)), None)
    for event in ordered:
        if event.get('event') == 'stage_started' and event.get('role') in AI_STAGES:
            started[event['role']] = _time(event)
        entry = describe(event, started)
        when = _time(event)
        entry['offset'] = f'+{(when - first).total_seconds():.0f}s' if when and first else ''
        entry['seq'] = len(rows)
        rows.append(entry)
    return rows


def gate(ordered):
    event = next((e for e in reversed(ordered) if e.get('event') == 'ai_invocation_gate'), None)
    if not event:
        return None
    return {'open': event.get('invoke') is True, 'reason': _s(event.get('reason'), 80),
            'candidates': _strs(event.get('candidate_ids'), 10, 16)}


def strategy_blocked(ordered):
    event = next((e for e in reversed(ordered) if e.get('event') == 'strategy_evaluated'), None)
    return _blocked_rows(event.get('blocked')) if event else []


def stage_times(ordered):
    times = {}
    for event in ordered:
        role = event.get('role')
        if role in AI_STAGES and event.get('event') in {'stage_started', 'stage_completed'} and _time(event):
            times.setdefault(role, {})['start' if event['event'] == 'stage_started' else 'end'] = _time(event).isoformat()
    for role, span in times.items():
        if 'start' in span and 'end' in span:
            span['seconds'] = round((_aware(span['end']) - _aware(span['start'])).total_seconds(), 1)
    return times


def flow(review, log):
    """One edge per adjacent pipeline pair, labelled from recorded fields.

    state: carried (the next stage has recorded work after this one),
    stopped (the run recorded a stop here), skipped (recorded as not needed or
    gate closed), unknown (nothing recorded to show either way).
    """
    stages = {s['key']: s for s in review.get('stages', [])}
    seen = {e['actor'] for e in log}
    g = review.get('ai_gate')
    picks = review.get('proposed_instruments') or []
    stopped = review.get('stopped_instruments') or []
    decision = review.get('decision_type')
    ai_skipped = bool(g) and not g['open'] and not any(a in seen for a in AI_STAGES)

    def edge(a, b, state, label):
        return {'from': a, 'to': b, 'state': state, 'label': label}

    edges = []
    if ai_skipped:
        edges.append(edge('evidence', 'research', 'skipped', 'AI gate closed'))
        edges += [edge('research', 'portfolio', 'skipped', ''), edge('portfolio', 'critic', 'skipped', '')]
        edges.append(edge('critic', 'risk', 'skipped', ''))
    else:
        if g and g['open']:
            label = 'gate open · ' + (', '.join(g['candidates']) or 'candidates')
        else:
            label = 'shortlist' if 'research' in seen else ''
        edges.append(edge('evidence', 'research', 'carried' if 'research' in seen else 'unknown', label))
        compared = next((e['title'] for e in log if e['actor'] == 'research' and e['event'] == 'stage_completed'), '')
        edges.append(edge('research', 'portfolio', 'carried' if 'portfolio' in seen else 'unknown',
                          compared.replace('Compared ', '').replace(' ideas', ' compared').replace(' idea', ' compared') if 'portfolio' in seen else ''))
        edges.append(edge('portfolio', 'critic', 'carried' if 'critic' in seen else 'unknown',
                          ('proposed ' + ', '.join(picks)) if picks and 'critic' in seen else 'no pick' if 'critic' in seen else ''))
        if stopped:
            edges.append(edge('critic', 'risk', 'stopped', 'rejected ' + ', '.join(stopped)))
        elif stages.get('risk', {}).get('status') == 'not_applicable':
            edges.append(edge('critic', 'risk', 'skipped', 'nothing to check'))
        else:
            edges.append(edge('critic', 'risk', 'carried' if 'risk' in seen else 'unknown',
                              ('passed ' + ', '.join(picks)) if picks and 'risk' in seen else ''))
    final_seen = 'final' in seen
    risk_results = next((e for e in reversed(log) if e['actor'] == 'risk' and e['event'] == 'risk_evaluated'), None)
    if stopped:
        edges.append(edge('risk', 'final', 'skipped', 'no card'))
    else:
        edges.append(edge('risk', 'final', 'carried' if final_seen and risk_results else 'skipped' if final_seen else 'unknown',
                          'results recorded' if risk_results else ''))
    bypass = None
    if ai_skipped and final_seen:
        bypass = {'from': 'evidence', 'to': 'final', 'state': 'carried',
                  'label': {'DESK_ENTRY': 'Desk rule (no AI)', 'DESK_ENTRY_BLOCKED': 'Desk rule blocked',
                            'HOLD_CAPABILITY_GAP': 'Signal, no ETF issuer'}.get(decision, 'No AI needed · hold')}
    return {'edges': edges, 'bypass': bypass, 'ai_skipped': ai_skipped}


def agent_usage(records, ordered):
    """Model, tools and tokens for each AI stage.

    SDK spans and bounded-attempt events are not tagged with the cycle id, so they
    are matched by recorded row order: rows strictly between this cycle's
    stage_started and stage_completed for the same role (the runner is single).
    """
    def rid(e):
        v = e.get('_row_id')
        return v if isinstance(v, int) and not isinstance(v, bool) else None
    out = {}
    for role in AI_STAGES:
        start = next((rid(e) for e in ordered if e.get('event') == 'stage_started' and e.get('role') == role and rid(e)), None)
        end = next((rid(e) for e in ordered if e.get('event') == 'stage_completed' and e.get('role') == role and rid(e)), None)
        if start is None or end is None or end <= start:
            continue
        window = [r for r in records if isinstance(r, dict) and rid(r) is not None and start < rid(r) < end]
        usage = {'matched_by': 'recorded row order', 'attempts': 0, 'tools': None, 'handoffs': None}
        for r in window:
            if r.get('event') == 'bounded_attempt_started' and r.get('role') == role:
                usage['attempts'] += 1
                usage['model'] = _s(r.get('model'), 60)
                usage['reserved_usd'] = _s(r.get('reserved_usd'), 20)
            payload = r.get('payload') if isinstance(r.get('payload'), dict) else {}
            data = payload.get('span_data') if isinstance(payload.get('span_data'), dict) else {}
            if r.get('event') == 'span_start' and data.get('type') == 'agent':
                usage['agent'] = _s(data.get('name'), 40)
                usage['output_type'] = _s(data.get('output_type'), 40)
                usage['tools'] = _strs(data.get('tools'), 20, 60) if isinstance(data.get('tools'), list) else None
                usage['handoffs'] = _strs(data.get('handoffs'), 20, 60) if isinstance(data.get('handoffs'), list) else None
            inner = data.get('data') if isinstance(data.get('data'), dict) else {}
            if r.get('event') == 'span_end' and inner.get('sdk_span_type') == 'turn' and isinstance(inner.get('usage'), dict):
                u = inner['usage']
                usage['input_tokens'] = _count(u.get('input_tokens'))
                usage['output_tokens'] = _count(u.get('output_tokens'))
        if usage['attempts'] or usage.get('agent'):
            out[role] = usage
    return out
