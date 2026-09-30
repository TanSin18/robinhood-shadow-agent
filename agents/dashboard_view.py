"""Escaped, server-rendered dashboard. Browser code only refreshes local views."""
import html
import json
from datetime import date
from decimal import Decimal
from urllib.parse import quote, urlencode

from agents.dashboard import stamp
from agents.inbox import ET

LABELS = {'WAITING': 'Waiting for the next review', 'MARKET_CLOSED': 'Market closed today',
          'NOT_ISSUED_BUDGET':'No card · AI budget insufficient','NOT_ISSUED_DATA':'No card · Current data unavailable','FAILED_STALLED':'Review stalled','MISSED_WINDOW':'Review window missed','DELIVERED':'Sent to macOS','EXHAUSTED':'Notification delivery failed','UNKNOWN':'Notification delivery unconfirmed',
          'NO_RUN_RECORDED': 'No run recorded today', 'RUNNING': 'Review in progress',
          'UNCONFIRMED': 'Review completion unconfirmed', 'FAILED': 'Review failed',
          'HOLD': 'Completed · No trade recommended', 'COMPLETED': 'Review completed',
          'PENDING': 'Waiting for you', 'YES': 'YES · Approved', 'NO': 'NO · Skipped',
          'EXPIRED': 'Expired', 'RESOLVED': 'Resolved', 'filled': 'Paper fill', 'skipped': 'Skipped', 'RISK_BLOCKED': 'Blocked by risk checks'}


def esc(value):
    return html.escape(str(value), quote=True)


def dollars(value):
    return 'Not available' if value is None else f'${Decimal(value):,.2f}'


def when(value):
    moment = stamp(value)
    return moment.astimezone(ET).strftime('%b %d, %Y at %-I:%M %p ET') if moment else 'Time not recorded'


def shell(title, body, *, auto=False, paused=None):
    body = body.replace('<main id="main"', '<main id="main" tabindex="-1"')
    control = '' if paused is None else f'<a class="button safety-control" href="/control?action={"resume" if paused else "pause"}">{"Resume" if paused else "Pause"} paper activity</a>'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · Shadow</title><link rel="stylesheet" href="/assets/dashboard.css"><script src="/assets/decision-room.js" defer></script><script src="/assets/dashboard.js" defer></script></head>
<body data-auto="{'on' if auto else 'off'}"><a class="skip" href="#main">Skip to content</a>
<aside class="rail"><a class="brand" href="/" aria-label="Shadow home"><span class="brand-mark" aria-hidden="true">S</span>Shadow</a>
<p class="rail-caption">Your paper trading desk</p><nav class="desktop-nav" aria-label="Dashboard sections"><a data-nav="next" href="/#next">Overview</a><a data-nav="decisions" href="/#decisions">Approvals</a><a data-nav="activity" href="/#activity">Decision room</a><a data-nav="history" href="/#history">History</a><a data-nav="results" href="/#results">Results</a><a data-nav="controls" href="/#controls">Controls</a></nav>
<div class="rail-foot"><span class="pill">Stage 1 · Paper only</span><p>Real orders are blocked.<br>Your money stays untouched.</p></div></aside>
<div class="workspace"><header class="topbar"><span class="safety">Paper trading only · Real orders blocked</span>{control}</header>{body}</div>
<nav class="phone-nav" aria-label="Dashboard sections"><a data-nav="next" href="/#next">Overview</a><a data-nav="decisions" href="/#decisions">Approvals</a><a data-nav="activity" href="/#activity">Decision room</a><details class="more-nav"><summary>More</summary><div><a data-nav="history" href="/#history">History</a><a data-nav="results" href="/#results">Results</a><a data-nav="controls" href="/#controls">Controls</a></div></details></nav></body></html>'''


def parse_filters(query):
    lane, status, day = (query.get(k, [''])[0] for k in ('lane', 'status', 'date'))
    if lane not in {'', 'A', 'B'} or status not in {'', 'PENDING', 'YES', 'NO', 'EXPIRED', 'FAILED', 'HOLD', 'COMPLETED', 'RUNNING', 'UNCONFIRMED', 'NO_RUN_RECORDED'}:
        raise ValueError('Choose one of the available filters.')
    if day:
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError('Use a valid calendar date.')
    return {'lane': lane, 'status': status, 'date': day}


def matches(item, filters, *, card=False):
    if filters['lane'] and item.get('lane') not in {'', filters['lane']}:
        return False
    if filters['status'] and item.get('status') != filters['status']:
        return False
    moment = stamp(item.get('issued') if card else item.get('timestamp'))
    return not filters['date'] or (moment and moment.astimezone(ET).date().isoformat() == filters['date'])


def badge(status):
    tone = 'warn' if status in {'FAILED', 'UNCONFIRMED', 'RISK_BLOCKED', 'PENDING', 'NO_RUN_RECORDED'} else 'neutral'
    return text_badge(LABELS.get(status, status), tone)


def text_badge(label, tone='neutral'):
    return f'<span class="badge {tone}">{esc(label)}</span>'


def history_event(item):
    detail = ''
    if item['details']:
        detail = f'<details><summary>Technical record</summary><pre>{esc(json.dumps(item["details"], indent=2))}</pre></details>'
    status = item.get('resolution') or item['status']
    return f'''<li><div class="event-top"><strong>{esc(item['title'])}</strong>{badge(status)}</div><time>{esc(when(item['timestamp']))}</time><p>{esc(item['summary'])}</p>{detail}</li>'''


def history_days(items):
    grouped = {}
    for item in items:
        moment = stamp(item.get('timestamp'))
        key = moment.astimezone(ET).date().isoformat() if moment else 'unknown'
        grouped.setdefault(key, []).append(item)
    return grouped


def history_day_view(day, items):
    records = [item for item in items if item['kind'] != 'notification']
    messages = [item for item in items if item['kind'] == 'notification']
    authoritative = next((item for item in records if item['kind'] == 'cycle' and item.get('authoritative')), None)
    outcome = authoritative or next((item for item in records if item['kind'] in {'cycle','schedule'}), None)
    pending = sum(item['kind'] == 'decision' and item['status'] == 'PENDING' for item in records)
    status = outcome['status'] if outcome else ('PENDING' if pending else records[0]['status'] if records else messages[0]['status'])
    if day == 'unknown':
        day_label = 'Date not recorded'
    else:
        day_label = date.fromisoformat(day).strftime('%A, %B %-d')
    if pending:
        action = f'{pending} proposal needs your answer' if pending == 1 else f'{pending} proposals need your answer'
        action_html = f'<div class="day-action"><strong>{esc(action)}</strong><a href="/#decisions">Open approvals</a></div>'
    else:
        action = 'Nothing needs your approval'
        action_html = f'<p class="day-action-clear">{action}</p>'
    facts = []
    summary = outcome['summary'] if outcome else 'Activity was recorded for this day.'
    details = outcome.get('details', {}) if outcome else {}
    day_title = LABELS.get(status, status)
    day_badge = badge(status)
    closed_review = status in {'HOLD', 'COMPLETED'} and details.get('market_open') is False
    if closed_review:
        day_title = 'After-hours setup run'
        day_badge = text_badge('Market closed')
        summary = 'The review finished while the market was closed. No paper trade was proposed.'
    elif status == 'HOLD':
        day_title = 'Hold cash'
        day_badge = text_badge('Review completed')
        summary = 'Research, Portfolio, and Critic finished. No eligible paper trade was proposed.'
    elif status == 'COMPLETED':
        day_title = 'Paper review completed'
        summary = 'The full review finished and recorded its paper-trading outcome.'
    elif status == 'FAILED':
        summary = outcome['summary'] or 'The review did not finish.'
    elif status == 'NO_RUN_RECORDED':
        summary = outcome['summary']
    agents = details.get('agents') or []
    if agents:
        stages = [name.removesuffix(' Agent') for name in agents]
        facts.append('<span><strong>Stages</strong> ' + esc(' · '.join(stages)) + '</span>')
    strategy = details.get('strategy_assessment') or {}
    if strategy:
        signals = strategy.get('signals') or []
        strategies = strategy.get('strategies') or {}
        momentum = (strategies.get('momentum_rotation') or {}).get('qualifying_count', 0)
        reversion = (strategies.get('mean_reversion') or {}).get('qualifying_count', 0)
        facts.append(f'<span><strong>Strategy signals</strong> · {len(signals)} triggered '
                     f'(Momentum {esc(momentum)} · Mean reversion {esc(reversion)})</span>')
        if signals:
            names = ', '.join(str(signal.get('instrument', 'Unknown')) for signal in signals)
            facts.append(f'<span><strong>Triggered today</strong> · {esc(names)}</span>')
            facts.append('<span>Paper-selection signals only; historical promotion evidence is separate.</span>')
        else:
            facts.append('<span><strong>Next trigger</strong> · positive ETF momentum above its 200-session average, or a 3% one-day drop while still above that average.</span>')
    elif status == 'HOLD':
        facts.append('<span><strong>Strategy signals were not recorded for this run.</strong> The upgraded selector starts with the next eligible cycle.</span>')
    quotes = details.get('quote_count')
    if status in {'HOLD','COMPLETED'} and details.get('data_mode') == 'live_readonly' and isinstance(quotes, int) and quotes > 0:
        if closed_review:
            facts.append(f'<span><strong>Quote refresh</strong> · {quotes} quotes returned</span>')
            facts.append('<span>Returned prices may reflect the prior trading session.</span>')
        else:
            facts.append(f'<span><strong>Final data refresh</strong> · {quotes} quotes returned</span>')
            if not (details.get('decision') or {}).get('picks'):
                facts.append('<span>No selected instrument required final freshness validation.</span>')
    elif status in {'HOLD','COMPLETED'}:
        facts.append('<span><strong>Final price check</strong> · Evidence not recorded</span>')
    facts_html = f'<div class="day-facts">{"".join(facts)}</div>' if facts else ''
    record_html = ''.join(history_event(item) for item in records) or '<li class="muted">No review or decision record for this date.</li>'
    message_html = ''.join(history_event(item) for item in messages)
    systems = f'<details class="system-messages"><summary>System messages · {len(messages)}</summary><ol>{message_html}</ol></details>' if messages else ''
    return f'''<article class="history-day" data-history-day="{esc(day)}"><header><div><time datetime="{esc(day)}">{esc(day_label)}</time><h3>{esc(day_title)}</h3></div>{day_badge}</header><p class="day-summary">{esc(summary)}</p>{action_html}{facts_html}<details class="technical-timeline"><summary>Technical timeline · {len(records)} records</summary><ol>{record_html}</ol>{systems}</details></article>'''


def card_view(card, csrf, paused):
    p = card['proposal']
    pending = card['status'] == 'PENDING'
    amount = Decimal(p['quantity']) * Decimal(p['limit_price']) * p['multiplier']
    max_loss = p.get('max_loss_usd') if p['asset_class'] == 'option' else amount
    risk_label = 'Closing a position' if p['side'] == 'sell' else dollars(max_loss)
    controls = ''
    if pending:
        disabled = ' disabled' if paused else ''
        controls = f'''<form method="post" action="/decision" class="decision-actions"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="id" value="{esc(card['id'])}">
<button class="primary" name="decision" value="YES"{disabled}>YES · Approve paper trade</button><button name="decision" value="NO">NO · Skip this idea</button></form>'''
        if paused:
            controls += '<p class="muted">Approving is disabled while paused. You can still say NO.</p>'
    record = card.get('approval_fill', {})
    return f'''<article class="proposal" data-card-id="{esc(card['id'])}"><div class="section-head"><h3>{esc(p['side'].title())} {esc(p['ticker'])}</h3>{badge(card['status'])}</div>
<p class="muted">Lane {card['lane']} · {esc(p['quantity'])} {'contracts' if p['asset_class']=='option' else 'shares'} · About {dollars(amount)}</p>
<p>{esc(p['thesis'])}</p><dl class="conditions"><div><dt>Good if</dt><dd>{esc(p['good_if'])}</dd></div><div><dt>Reconsider if</dt><dd>{esc(p['invalidation'])}</dd></div><div><dt>Maximum loss</dt><dd>{risk_label}</dd></div></dl>
<details><summary>Reasoning &amp; risk details</summary><p>{esc(p.get('critic_counterargument') or 'No critic counterargument recorded.')}</p><pre>{esc(card['body'].replace('[YES] [NO]', ''))}</pre><p>{esc(card['comparison'])}</p><p><a href="/trace/{quote(card['id'], safe='')}">View decision record</a></p></details>
<p class="expiry" {'data-expires="'+esc(card['expires'])+'"' if pending else ''}>{'Expires' if pending else 'Expiry'} {esc(when(card['expires']))}</p>
{('<p class="notice">Approval recorded; paper execution blocked by the current risk checks.</p>' if record.get('status')=='RISK_BLOCKED' else '')}{controls}</article>'''


STATE_LABELS = {
    'proposed': 'Proposed',
    'advanced': 'Advanced',
    'blocked': 'Blocked',
    'rejected': 'Rejected',
    'reviewed': 'Reviewed',
}
GROUP_ORDER = ('proposed', 'advanced', 'blocked', 'rejected', 'reviewed')
LANE_LABELS = {
    'A': 'Lane A · Stocks & ETFs',
    'B': 'Lane B · Defined-risk options',
}


def decision_stage_view(review_index, stage, active=False):
    selected = 'true' if active else 'false'
    kind = 'deterministic' if stage['key'] in {'evidence', 'risk', 'final'} else 'agent'
    panel_id = f'review-{review_index}-stage-{stage["key"]}'
    return f'''<li class="decision-stage" data-stage="{esc(stage['key'])}" data-entity-kind="{kind}">
      <button type="button" data-stage-choice="{esc(stage['key'])}" aria-pressed="{selected}" aria-controls="{panel_id}">
        <span class="stage-step" aria-hidden="true">{esc(stage['step'])}</span>
        <span><strong>{esc(stage['label'])}</strong><small>{esc(stage['mandate'])}</small></span>
        <small class="stage-output">{esc(stage['output_line'])}</small>
        {text_badge(stage['status_label'], stage['tone'])}
      </button>
    </li>'''


def stage_inspector_view(review_index, stage, active=False):
    panel_id = f'review-{review_index}-stage-{stage["key"]}'
    heading_id = f'{panel_id}-heading'
    inspector = stage['inspector']
    def items(values):
        return '<ul>' + ''.join(f'<li>{esc(value)}</li>' for value in values) + '</ul>'
    body = f'''<div><dt>Mandate</dt><dd>{esc(inspector['mandate'])}</dd></div>
      <div><dt>Inputs</dt><dd>{items(inspector['inputs'])}</dd></div>
      <div><dt>Findings</dt><dd>{items(inspector['findings'])}</dd></div>
      <div><dt>Sources</dt><dd>{items(inspector['sources'])}</dd></div>
      <div><dt>Blockers</dt><dd>{items(inspector['blockers'])}</dd></div>
      <div><dt>Handoff</dt><dd>{esc(inspector['handoff'])}</dd></div>'''
    hidden = '' if active else ' hidden'
    return f'''<section id="{panel_id}" data-stage-panel="{esc(stage['key'])}" aria-labelledby="{heading_id}"{hidden}>
      <h3 id="{heading_id}">{esc(stage['label'])}</h3><p>{esc(stage['summary'])}</p><dl>{body}</dl>
    </section>'''


def decision_row_view(row):
    sources = len(row.get('source_refs') or [])
    source_details = ''
    if sources:
        source_details = f'''<details class="decision-sources"><summary>Evidence sources · {sources}</summary><ul>{''.join(f'<li>{esc(ref)}</li>' for ref in row['source_refs'])}</ul></details>'''
    return f'''<article class="decision-row" data-decision-state="{esc(row['state'])}">
      <div><strong>{esc(row['instrument'])}</strong>{text_badge(STATE_LABELS[row['state']])}</div>
      <p>{esc(row['reason'])}</p>
      <dl><div><dt>Decided by</dt><dd>{esc(row.get('deciding_stage') or 'Not recorded')}</dd></div>
          <div><dt>Signal</dt><dd>{esc(row.get('strategy_signal') or 'Not recorded')}</dd></div>
          <div><dt>Freshness</dt><dd>{esc(row.get('data_freshness') or 'Not recorded')}</dd></div>
          <div><dt>Evidence</dt><dd>{sources if sources else 'Not recorded'}</dd></div></dl>{source_details}
    </article>'''


def selection_board_view(review_index, lanes, proposal_state, selection_recorded):
    tabs = ''.join(
        f'<button type="button" data-lane-choice="{lane}" aria-pressed="{"true" if lane == "A" else "false"}">{esc(LANE_LABELS[lane])}</button>'
        for lane in ('A', 'B')
    )
    panels = []
    structured_count = sum(len(lanes.get(lane) or []) for lane in ('A', 'B'))
    for lane in ('A', 'B'):
        rows = lanes.get(lane) or []
        groups = []
        for state in GROUP_ORDER:
            state_rows = [row for row in rows if row.get('state') == state]
            if not state_rows and state != 'proposed':
                continue
            body = ''.join(decision_row_view(row) for row in state_rows)
            if not state_rows:
                if proposal_state == 'recorded':
                    message = 'Proposal recorded; lane details were not recorded for this historical review.'
                elif proposal_state == 'stopped':
                    message = 'Proposal stopped by the Critic; no card was issued.'
                elif proposal_state == 'none':
                    message = 'No paper proposal from this review.'
                else:
                    message = 'Proposal state was not recorded for this historical review.'
                body = f'<p class="empty-group">{esc(message)}</p>'
            group_id = f'review-{review_index}-{lane}-{state}'
            groups.append(
                f'<section aria-labelledby="{group_id}"><h4 id="{group_id}">{esc(STATE_LABELS[state])}</h4>{body}</section>'
            )
        hidden = '' if lane == 'A' else ' hidden'
        panels.append(
            f'<div data-lane="{lane}" data-lane-panel="{lane}"{hidden}><h3>{esc(LANE_LABELS[lane])}</h3>{"".join(groups)}</div>'
        )
    notice = (
        ''
        if structured_count or selection_recorded
        else '<p class="historical-notice">Detailed selection states were not recorded for this review.</p>'
    )
    return f'''<section class="selection-board"><h2>Selections</h2>
      <div class="selection-tabs" role="group" aria-label="Trading lane">{tabs}</div>
      {notice}{''.join(panels)}</section>'''


def decision_room_view(reviews):
    if not reviews:
        return '''<div class="empty"><h3>No reviews recorded yet</h3>
          <p>The next eligible review will show each handoff here.</p>
          <a href="/#controls">Check readiness</a></div>'''
    options = ''.join(
        f'<option value="{esc(review["review_id"])}">{esc(when(review.get("timestamp")))} · {esc(review["header"]["outcome"])}</option>'
        for review in reviews
    )
    panels = []
    for index, review in enumerate(reviews):
        stages = ''.join(
            decision_stage_view(index, stage, stage['key'] == review['default_stage'])
            for stage in review['stages']
        )
        inspector = ''.join(
            stage_inspector_view(index, stage, stage['key'] == review['default_stage'])
            for stage in review['stages']
        )
        attention = (
            '<a class="button" href="/#decisions">Review pending approval</a>'
            if review['outcome']['pending_count']
            else ''
        )
        incomplete = (
            '<p class="notice warn">Activity record incomplete. Unsafe or malformed fields were omitted.</p>'
            if review['record_incomplete']
            else ''
        )
        header = review['header']
        cost = dollars(header['api_cost_estimate_usd']) if header['api_cost_estimate_usd'] is not None else 'Not recorded'
        hidden = '' if index == 0 else ' hidden'
        panels.append(
            f'''<article data-review="{esc(review['review_id'])}" data-default-stage="{esc(review['default_stage'])}"{hidden}>
              <header class="review-header"><div><h3>{esc(when(review.get('timestamp')))}</h3><p>{esc(review['outcome']['reason'])}</p><details class="review-meta"><summary>Review details</summary><p>Review ID {esc(header['short_id'])}</p></details></div><div>{text_badge(header['outcome'])}{attention}</div></header>
              <p class="operator-action"><strong>Next action:</strong> {esc(header['action'])}</p>
              <dl class="review-facts"><div><dt>Outcome</dt><dd>{esc(header['outcome'])}</dd></div><div><dt>Data mode</dt><dd>{esc(header['data_mode'])}</dd></div><div><dt>Freshness</dt><dd>{esc(header['freshness'])}</dd></div><div><dt>Stages recorded</dt><dd>{esc(header['completed_stages'])} of {esc(header['expected_stages'])}</dd></div><div><dt>Duration</dt><dd>{esc(header['duration'])}</dd></div><div><dt>Estimated AI cost</dt><dd>{esc(cost)}</dd></div><div><dt>Paper state</dt><dd>Paper only · Real orders blocked</dd></div></dl>
              {incomplete}<ol class="decision-flow" aria-label="Review flow">{stages}</ol>
              <div class="decision-layout"><div>{selection_board_view(index, review['lanes'], review['proposal_state'], review['selection_recorded'])}</div><aside class="stage-inspector">{inspector}</aside></div>
              <details><summary>Inspect technical record</summary><pre>{esc(json.dumps(review['technical_events'], indent=2))}</pre></details>
            </article>'''
        )
    return f'''<div data-decision-room><label for="review-choice">Review</label>
      <select id="review-choice" data-review-choice>{options}</select>
      <p class="privacy-note">Structured work products are shown. Private chain-of-thought is not recorded.</p>
      <p class="sr-only" data-decision-room-status aria-live="polite"></p>{''.join(panels)}</div>'''


def render_dashboard(state, config, csrf, filters, readiness=None, service=None):
    readiness = readiness or {}
    background_ok = readiness.get('gates', {}).get('background_auth') is True
    paused = state['paused']
    next_at = stamp(state['next_run'])
    next_label = next_at.strftime('%A, %B %-d') if next_at else 'Not available'
    auth_title = 'Background cycle verified' if background_ok else 'Background connection not yet verified'
    auth_body = ('A completed authenticated background cycle has matching evidence.' if background_ok else
                 'A successful interactive run does not prove the scheduled run works. This stays unverified until a background cycle completes.')
    service_label = {True: 'Scheduler loaded', False: 'Scheduler not loaded', None: 'Scheduler status unavailable'}[service]
    selected = lambda actual, want: ' selected' if actual == want else ''
    filter_form = f'''<form class="filters" method="get" action="/"><label>Lane<select name="lane"><option value="">Both lanes</option><option value="A"{selected(filters['lane'],'A')}>A · Stocks &amp; ETFs</option><option value="B"{selected(filters['lane'],'B')}>B · Options</option></select></label>
<label>Decision / status<select name="status"><option value="">All activity</option>{''.join(f'<option value="{s}"{selected(filters["status"],s)}>{esc(LABELS[s])}</option>' for s in ('PENDING','YES','NO','EXPIRED','FAILED','HOLD','COMPLETED','RUNNING','UNCONFIRMED','NO_RUN_RECORDED'))}</select></label>
<label>Date (Eastern)<input type="date" name="date" value="{esc(filters['date'])}"></label><button type="submit">Apply filters</button><a href="/">Clear</a></form>'''
    filter_form = f'<details class="filter-disclosure"{" open" if any(filters.values()) else ""}><summary>{"Filters applied · Change or clear" if any(filters.values()) else "Filter by lane, status or date"}</summary>{filter_form}</details>'
    approval_filters = filter_form.replace('action="/"', 'action="/#decisions"').replace('href="/"', 'href="/#decisions"')
    history_filters = filter_form.replace('action="/"', 'action="/#history"').replace('href="/"', 'href="/#history"')
    cards = [c for c in state['cards'] if matches(c, filters, card=True)]
    pending_count = sum(c['status'] == 'PENDING' for c in state['cards'])
    empty_title = 'No matching proposals' if pending_count else 'No decisions waiting'
    proposals = ''.join(card_view(c, csrf, paused) for c in cards[:30]) or f'''<div class="empty"><h3>{empty_title}</h3><p>{'There are pending proposals in another view. Clear the filters to find them.' if pending_count else 'When the agent proposes an eligible paper trade, you can review it here. An empty inbox does not mean a review succeeded.'}</p><a class="button" href="{'/#decisions' if pending_count else '/#history'}">{'Clear filters' if pending_count else 'Check run history'}</a></div>'''
    history = [h for h in state['history'] if matches(h, filters)]
    history_html = ''.join(history_day_view(day, items) for day, items in history_days(history[:60]).items())
    if not history_html:
        history_html = '<div class="empty-history">Nothing recorded for these filters. No run recorded is not the same as a successful hold decision.</div>'
    lane_html = ''
    for lane in state['lanes']:
        if filters['lane'] and filters['lane'] != lane['lane']:
            continue
        rows = ''
        for track in lane['tracks']:
            label = 'Agent alone' if track['track'] == 'agent_alone' else 'Agent + my approvals'
            freshness = ('Stale marks · ' if track['stale'] else 'Marks · ') + when(track['as_of']) if track['positions'] else 'Cash only'
            if track['data_mode'] == 'fixture':
                freshness += ' · Mock / fixture marks'
            rows += f'''<tr><th scope="row">{label}<small>{esc(freshness)}</small></th><td>{dollars(track['value'])}</td><td>{dollars(track['api_cost'])}</td><td>{dollars(track['net_value'])}</td></tr>'''
        rows += f'''<tr class="benchmark"><th scope="row">Cash benchmark<small>No assumed interest</small></th><td>{dollars(lane['cash_benchmark'])}</td><td>$0.00</td><td>{dollars(lane['cash_benchmark'])}</td></tr><tr class="benchmark"><th scope="row">VTI benchmark<small>Observed price only, not total return</small></th><td>{dollars(lane['vti_benchmark'])}</td><td>$0.00</td><td>{dollars(lane['vti_benchmark'])}</td></tr>'''
        holdings = ''
        for track in lane['tracks']:
            name = 'Agent alone' if track['track'] == 'agent_alone' else 'With your approvals'
            positions = ', '.join(f"{t}: {p['quantity']}" for t, p in track['positions'].items()) or 'None'
            holdings += f'<p><strong>{name}</strong><br>Settled cash {dollars(track["settled_cash"])} · Unsettled {dollars(track["unsettled_cash"])}<br>Positions: {esc(positions)}</p>'
        lane_html += f'''<article class="lane"><h3><span class="lane-letter">{lane['lane']}</span> {'Stocks &amp; ETFs' if lane['lane']=='A' else 'Defined-risk options'} <small>Started with {dollars(lane['start'])}</small></h3><div class="table-scroll" tabindex="0" role="region" aria-label="Lane {lane['lane']} results"><table><thead><tr><th>Comparison</th><th>Gross equity</th><th>AI cost</th><th>After AI cost</th></tr></thead><tbody>{rows}</tbody></table></div><details><summary>Cash &amp; positions</summary>{holdings}</details></article>'''
    cost = state['costs']
    usage = min(100, max(0, float((Decimal(cost['budget'])-Decimal(cost['remaining'])) / Decimal(cost['budget']) * 100))) if Decimal(cost['budget']) else 100
    report_html = ''.join(f'<li><a href="/report/{esc(r["week"])}">Week ending {esc(r["week"])}</a></li>' for r in state['reports']) or '<li class="muted">No eligible weekly report yet.</li>'
    activity_html = decision_room_view(state.get('decision_room', []))
    pushover = state.get('notification_channels', {}).get('pushover', {})
    push_labels = {'DELIVERED':'Delivered', 'PENDING':'Waiting to retry', 'SENDING':'Sending',
                   'EXHAUSTED':'Delivery failed', 'UNKNOWN':'Delivery unconfirmed',
                   'NOT_CONFIGURED':'Credentials not configured', 'NO_MESSAGES':'No messages sent yet'}
    push_status = push_labels.get(pushover.get('status'), pushover.get('status', 'Unavailable'))
    push_detail = ('Last delivered ' + when(pushover['last_delivered']) if pushover.get('last_delivered') else
                   'No successful Pushover delivery has been recorded yet.')
    tripwire = (state.get('tripwire') or [{}])[0]
    tripwire_status = tripwire.get('status', 'NO_VERIFIED_SNAPSHOT')
    tripwire_action = ''
    if tripwire.get('incident_id') and tripwire.get('ack_expires_at'):
        tripwire_action = f'''<form method="post" action="/tripwire/acknowledge"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="incident_id" value="{esc(tripwire['incident_id'])}"><input type="hidden" name="snapshot_hash" value="{esc(tripwire['snapshot_hash'])}"><input type="hidden" name="change_class" value="{esc(tripwire.get('change_class') or '')}"><input type="hidden" name="expires_at" value="{esc(tripwire['ack_expires_at'])}"><input type="hidden" name="confirm" value="yes"><button type="submit">Acknowledge this exact change</button></form>'''
    tripwire_panel = f'''<section class="connection"><h2>Agentic account tripwire</h2><p><strong>{esc(tripwire_status.replace('_',' ').title())}</strong></p><p class="muted">Only hashes, change categories and timestamps are shown. Balances, quantities, instruments and order IDs stay private.</p>{tripwire_action}</section>'''
    action = 'resume' if paused else 'pause'
    latest = next((h for h in state['history'] if h['kind'] == 'cycle'), None)
    last_text = f'{LABELS.get(latest["status"],latest["status"])} · {when(latest["timestamp"])}' if latest else 'No run recorded'
    if latest and latest['details'].get('data_mode') == 'fixture':
        last_text += ' · Mock / fixture data'
    review_time = next_at.strftime('%-I:%M %p') if next_at else 'Not available'
    attention = (f'{pending_count} proposal{"s" if pending_count != 1 else ""} waiting for your answer'
                 if pending_count else 'Nothing needs your approval right now')
    # Keep all views available without JavaScript; local navigation progressively
    # shows just one view. No model call or trading action is attached to navigation.
    body = f'''<main id="main"><div class="page-heading"><h1 id="view-title">Overview</h1><div class="refresh"><a class="button" data-refresh href="?{esc(urlencode(filters))}">Refresh status</a><label><input id="auto-refresh" type="checkbox" checked> Auto-refresh</label></div></div>
<p class="updated">Updated {esc(when(state['checked_at']))}. Local records only.</p>
<section id="next" data-view="next" tabindex="-1" aria-label="Overview">
<div class="day-sheet"><div class="section-head"><h2>Next up</h2><span class="pill">{'Paused / safety stop' if paused else 'Paper reviews enabled'}</span></div>
<div class="appointment"><div><h3>{esc(next_label)}</h3><p class="appointment-time">{esc(review_time)} <span>Eastern</span></p></div><div class="appointment-note"><p>{'Resume before the scheduled window to allow a review.' if paused else 'Your agent will attempt its next paper-trading review.'}</p><p class="muted">Keep your Mac plugged in, awake, signed in and online.</p></div></div>
<div class="readiness-strip"><span class="status-dot" aria-hidden="true"></span><div><strong>{'Scheduled cycle verified' if background_ok else 'Awaiting first verified scheduled run'}</strong><p>{'Matching background-cycle evidence is available.' if background_ok else 'Configured to run is not the same as a successful run.'} {service_label}.</p></div><a href="/#controls">Check readiness</a></div>
<details class="sequence"><summary>What happens during a review?</summary><ol class="pipeline"><li>Read market data</li><li>Research</li><li>Portfolio decision</li><li>Independent critic</li><li>Refresh prices &amp; check risk</li><li>Eligible paper trades &amp; approval cards</li></ol><p class="muted">Planned sequence, not live progress. The agent-alone lane simulates eligible trades; your YES/NO controls the separate approval comparison. A delayed start is allowed before 10:20 AM ET. There is no automatic retry after an attempt starts. News is currently disabled.</p></details></div>
<a class="attention-row" href="/#decisions"><div><strong>{attention}</strong><p>{'Review the risks and decide before the cards expire.' if pending_count else 'Proposals will appear in Approvals when they are issued.'}</p></div><span>Open approvals</span></a>
<div class="overview-bottom"><section><h2>Last recorded run</h2><p>{esc(last_text)}</p><a href="/#history">See what happened</a></section><section><h2>Estimated AI cost today</h2><p class="cost-number">${Decimal(cost['today']):.4f} <span>of {dollars(cost['budget'])}</span></p><p class="muted">${Decimal(cost['held']):.4f} reserved / unresolved. Estimates, not billed charges.</p><a href="/#controls">Budget details</a></section></div></section>
<section id="decisions" data-view="decisions" tabindex="-1" aria-label="Approvals"><div class="section-head"><div><h2>Needs your answer <span class="count">{pending_count}</span></h2><p class="muted">Approval inbox · YES affects only the paper comparison. Cards expire after {config.approval_expiry_minutes} minutes.</p></div></div>{approval_filters}{proposals}{'<p>Showing the newest 30 cards. Narrow the date or status to see older cards.</p>' if len(cards)>30 else ''}</section>
<section id="activity" data-view="activity" tabindex="-1" aria-label="Decision room"><div class="section-head"><div><h2>Decision room</h2><p class="muted">Follow the evidence, agent handoffs, deterministic risk checks, selections and final outcome.</p></div></div>{activity_html}</section>
<section id="history" data-view="history" tabindex="-1" aria-label="History"><div class="section-head"><div><h2>What happened</h2><p class="muted">One outcome per day. Recovery attempts and system messages stay available in the technical timeline.</p></div></div>{history_filters}<div class="history-days">{history_html}</div>{'<p>Showing days represented by the newest 60 records. Use the date filter for earlier activity.</p>' if len(history)>60 else ''}<details><summary>About missing runs</summary><p class="muted">Unrecorded trading windows are inferred for the last 90 days since the first observed run. Their cause is not assumed. No recorded run is not a successful hold decision.</p></details></section>
<div data-view="results" tabindex="-1" aria-label="Results"><section id="results"><h2>Your paper comparisons</h2><p class="muted">Two independent $500 lanes. These are since-start paper balances, not validated investment returns. Lane filters apply here; date and status filters affect only approvals and history.</p>{lane_html}<details><summary>How these comparisons work</summary><p>Each lane starts at $500. Shared AI costs are split equally between lanes and charged to each alternative agent track, never to cash or VTI. Costs are API-equivalent estimates, not your subscription bill. Unresolved cost reservations are shown separately and are not treated as known spend.</p><p>Approval fills use the proposal-time price, not the later price when you click YES. Gross equity includes observed bid marks; taxes, dividends, additional fees and execution latency are not modeled here.</p><p>VTI observation period: {esc(state['benchmark_period'] or 'Not available — two comparable observations are needed')}. Its period may differ from the paper accounts; this is not a validated performance comparison.</p></details></section><section class="reports-section"><h2>Weekly reports</h2><p class="muted">Friday after 4:30 PM ET, when your Mac is available.</p><ul class="reports">{report_html}</ul></section></div>
<section id="controls" data-view="controls" tabindex="-1" aria-label="Controls"><div class="control-grid"><section class="control-panel"><h2>Paper activity</h2><p>{'Paper activity is paused.' if paused else 'Paper activity is allowed by this switch.'} Risk checks still apply.</p><input type="hidden" name="csrf" value="{csrf}"><form method="get" action="/control"><input type="hidden" name="action" value="{action}"><button type="submit">{action.title()} paper activity</button></form><p class="muted">You’ll confirm before anything changes. Resuming never starts an extra review.</p><dl class="settings"><div><dt>Review</dt><dd>{esc(config.full_llm_cycle_time_et)} ET, trading days</dd></div><div><dt>Trade card expiry</dt><dd>{config.approval_expiry_minutes} minutes</dd></div><div><dt>Real orders</dt><dd>Blocked</dd></div></dl></section>
<section class="cost-panel control-panel"><h2>Estimated AI cost</h2><p class="cost-number">${Decimal(cost['today']):.4f}<span> / {dollars(cost['budget'])} today</span></p><progress max="100" value="{usage}" aria-label="Daily estimated budget used or held"></progress><dl class="settings"><div><dt>Reserved / unresolved</dt><dd>${Decimal(cost['held']):.4f}</dd></div><div><dt>Remaining estimate</dt><dd>${Decimal(cost['remaining']):.4f}</dd></div></dl><p class="muted">Estimates, not billed charges. An in-flight request can exceed its reservation.</p></section></div>
<section class="notification-panel control-panel"><div><h2>Pushover alerts</h2><p><strong>{esc(push_status)}</strong></p><p class="muted">{esc(push_detail)}</p><p>Approvals use normal priority. Failures, missed reviews, and safety stops use high priority. Routine holds stay in this dashboard.</p></div><form method="post" action="/notifications/test"><input type="hidden" name="csrf" value="{csrf}"><button type="submit">Send test notification</button></form></section>
{tripwire_panel}
<section class="connection"><h2>{auth_title}</h2><p>{auth_body}</p><p>{service_label}. Loaded does not mean authenticated.</p><details><summary>Readiness details</summary><ul>{''.join('<li>'+esc(b)+'</li>' for b in readiness.get('blockers', ['No current readiness evidence supplied.']))}</ul></details></section><details class="roadmap"><summary>What isn’t available yet?</summary><p>Backtests, Monte Carlo, AI comparisons and promotion exceptions are not built yet. No strategy has been promoted by this dashboard.</p></details></section>
</main><footer>Local on this Mac. Paper trading only. Your real money stays untouched.</footer>'''
    return shell('Trading dashboard', body, auto=True, paused=paused)


def render_control(action, csrf):
    if action not in {'pause', 'resume'}:
        raise ValueError('Choose pause or resume.')
    explanation = ('This blocks new scheduled cycles and all new paper fills, including sells. An AI request already running may finish and incur cost; this is not an emergency cancellation. Existing paper positions are not closed. Cards still expire and housekeeping continues.' if action == 'pause' else
                   'This removes only a pause created by this dashboard. The next eligible scheduled review may run; no review starts now, missed windows are not replayed, and the one-review-per-day rule is unchanged. External safety stops cannot be cleared here.')
    return shell('Confirm ' + action, f'''<main id="main" class="confirmation"><h1>{action.title()} paper activity?</h1><p>{explanation}</p><p>Stage 1 stays paper-only. Real orders remain blocked.</p><form method="post" action="/control"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="action" value="{action}"><input type="hidden" name="confirm" value="yes"><button class="primary" type="submit">Confirm {action}</button><a class="button" href="/">Go back without changes</a></form></main>''')
