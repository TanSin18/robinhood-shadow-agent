"""Plain-language, read-only view of the existing six-stage records."""
from datetime import datetime
from zoneinfo import ZoneInfo
from .components import esc
from .team import TEAM
from .approval_card import preview_card
from .clock import render_clock

ROLES = {
    'evidence': ('Find', 'Collect market data', 'Market data was collected.'),
    'research': ('Research', 'Understand the opportunities', 'Compared the supplied investment ideas.'),
    'portfolio': ('Choose', 'Decide what is worth buying', 'Finished choosing whether to propose a trade.'),
    'critic': ('Challenge', 'Look for reasons this could fail', 'Checked the proposal for weak assumptions.'),
    'risk': ('Protect', 'Check the safety rules', 'Finished the recorded safety checks.'),
    'final': ('Decide', 'Your next step', 'The outcome was saved.'),
}

def date_label(value):
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return 'Time not recorded'
        return dt.astimezone(ZoneInfo('America/New_York')).strftime('%b %d · %-I:%M %p ET')
    except (TypeError, ValueError):
        return 'Time not recorded'

def _names(items):
    items = [str(i) for i in items]
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1] if items else ''

def first_sentence(text, limit=220):
    text = ' '.join(str(text or '').split())
    if not text:
        return ''
    cut = text.find('. ')
    sentence = text if cut == -1 else text[:cut + 1]
    return sentence if len(sentence) <= limit else sentence[:limit - 1] + '…'

def outcome(review):
    label = review.get('header', {}).get('outcome', '')
    if review.get('proposal_state') == 'stopped' and review.get('stopped_by') == 'critic':
        pm, critic = TEAM['portfolio'][0], TEAM['critic'][0]
        return f"{pm} proposed {_names(review.get('stopped_instruments', []))}. {critic} rejected it. No card for you today."
    if review.get('proposal_state') == 'recorded' and label == 'Hold cash':
        return 'Outcome not confirmed'
    if label == 'Hold cash':
        return 'Review finished. No trade proposed.'
    if review.get('status') == 'completed' and review.get('proposal_state') == 'none':
        return 'Review finished. No trade proposed.'
    return {
        'Review in progress': 'The last saved review was still running.',
        'Paper proposal recorded': 'A paper trade was proposed.',
        'Completed paper action': 'A paper action was recorded.',
        'Completion unconfirmed': 'Outcome not confirmed',
    }.get(label, label or 'Outcome not confirmed')

def concerns(review):
    # Never reclassify legacy prose as a structured fact by keyword matching.
    return []

def short_stage(stage, review):
    status, key = stage.get('status'), stage['key']
    if review.get('proposal_state') == 'stopped' and review.get('stopped_by') == 'critic':
        names = _names(review.get('stopped_instruments', []))
        if key == 'portfolio': return 'Proposed ' + names + '.'
        if key == 'critic': return 'Rejected ' + names + ' — stopped here.'
        if key == 'risk': return 'No proposal reached the safety checks.'
        if key == 'final': return 'No card: stopped by the Critic.'
    if status == 'not_applicable': return 'No proposed trade needed this check.'
    if status == 'active': return 'Was working at the last recorded update.'
    if status in {'waiting', 'unavailable'} or status is None: return 'No completed work saved for this step.'
    if status in {'blocked', 'skipped'}: return 'This step stopped or was skipped. Open to see why.'
    if key == 'portfolio' and review.get('proposal_state') == 'none': return 'Did not propose a trade.'
    if key == 'final': return review.get('header', {}).get('action', 'Open the saved outcome.')
    return ROLES[key][2]

def evidence(stage):
    inspector = stage.get('inspector', {})
    body = '<details class="team-evidence"><summary>Show evidence</summary>'
    body += '<h4>Original report</h4><p>' + esc(stage.get('summary', 'No report saved.')) + '</p>'
    for key, label in (('inputs', 'What it received'), ('sources', 'Sources'), ('blockers', 'What was missing'), ('handoff', 'What happened next')):
        value = inspector.get(key)
        if not value: continue
        body += '<h4>' + label + '</h4>'
        body += '<ul>' + ''.join('<li>'+esc(v)+'</li>' for v in value)+'</ul>' if isinstance(value, list) else '<p>'+esc(value)+'</p>'
    return body + '</details>'

def brief(stage, key):
    """Keep short excerpts traceable; never invent an observed handoff."""
    inspector = stage.get('inspector', {})
    inputs = inspector.get('inputs', [])
    received = inputs[0] if isinstance(inputs, list) and inputs else 'Input details were not saved.'
    blockers = inspector.get('blockers', [])
    missing = [str(b) for b in blockers if b != 'None recorded'] if isinstance(blockers, list) else []
    finding = missing[0] if missing else stage.get('summary', 'No findings were saved.')
    handoff = inspector.get('handoff') or 'No handoff was saved.'
    def excerpt(value):
        text = str(value)
        return esc(text if len(text) <= 150 else text[:147]+'…')
    return '<dl class="team-brief">'+''.join('<div><dt>'+label+'</dt><dd>'+excerpt(value)+'</dd></div>'
        for label,value in (('Received',received),('Finding / limitation',finding),('Next step',handoff)))+'</dl>'

def review_view(review, index):
    hidden = ' hidden' if index else ''
    stages = {s['key']: s for s in review.get('stages', [])}
    heading = outcome(review)
    issues = concerns(review)
    reason = ' · '.join(x[0] for x in issues) or 'Open an agent to explore the saved review.'
    if review.get('proposal_state') == 'stopped' and review.get('critic_reason'):
        reason = TEAM['critic'][0] + '’s reason (original report): “' + first_sentence(review['critic_reason']) + '”'
    html = f'<section data-review="{index}"{hidden}><div class="team-outcome"><span class="team-date">{esc(date_label(review.get("timestamp")))}</span><h2>{esc(heading)}</h2><p>{esc(reason)}</p><details><summary>Why this outcome?</summary><p>{esc(review.get("outcome", {}).get("reason") or "The reason was not saved.")}</p></details></div>'
    html += '<div class="team-heading"><h2>Your team</h2><p>Tap anyone to see their work.</p></div><ol class="team-flow" data-team-flow aria-label="Review workflow">'
    panels = ''
    for key, (label, job, _) in ROLES.items():
        stage = stages.get(key, {'key': key, 'status_label': 'Not recorded'})
        name, _, asset, kind = TEAM[key]
        name = 'Outcome' if key == 'final' else name
        portrait = f'<img src="/assets/avatars/{asset}" alt="" width="64" height="64">' if asset else '<span class="team-code-icon" aria-hidden="true">'+('◎' if key == 'evidence' else '✓')+'</span>'
        panel_id = f'team-{index}-{key}'
        status = stage.get('status_label', 'Not recorded')
        tone = stage.get('status', 'unavailable')
        if review.get('proposal_state') == 'stopped' and review.get('stopped_by') == 'critic':
            if key == 'portfolio': status = 'Proposed'
            elif key == 'critic': status, tone = 'Rejected', 'blocked'
            elif key == 'risk': status, tone = 'Not reached', 'not_applicable'
            elif key == 'final': status, tone = 'No card', 'not_applicable'
        tone = tone if tone in {'completed','blocked','active','not_applicable','waiting','skipped'} else 'unavailable'
        html += f'<li><button type="button" class="team-node {tone}" data-agent-panel="{panel_id}" aria-controls="{panel_id}" aria-expanded="false">{portrait}<span class="team-job">{esc(label)}</span><span class="team-name">{esc(name)}</span><span class="team-status">{esc(status)}</span><span class="team-short">{esc(short_stage(stage, review))}</span></button></li>'
        panels += f'<details id="{panel_id}" class="team-panel"><summary>{esc(label)}: {esc(job)}</summary>{brief(stage,key)}{evidence(stage)}</details>'
    html += '</ol><p class="team-caption">Expected workflow. Connections do not prove a recorded handoff. Status is from saved records, not a live feed.</p><div class="team-panels">'+panels+'</div>'
    if issues:
        html += '<details class="team-issues"><summary>What needs attention <span>'+str(len(issues))+'</span></summary>'
        html += ''.join('<div><h3>'+esc(title)+'</h3><p>'+esc(description)+'</p></div>' for title,description in issues)+'</details>'
    html += '<section class="team-ideas"><h2>Investment ideas</h2>'
    if not review.get('selection_recorded'):
        html += '<p>Individual selection reasons weren’t saved for this review.</p>'
    else:
        for lane, rows in review.get('lanes', {}).items():
            html += '<h3>'+('Stocks & ETFs' if lane == 'A' else 'Options')+'</h3>'
            for row in rows:
                label = row.get('state', 'Reviewed').replace('_', ' ').capitalize()
                if row.get('state') == 'proposed' and row.get('instrument') in review.get('stopped_instruments', []):
                    label = 'Proposed → rejected by Critic'
                elif row.get('state') == 'advanced':
                    label = 'Qualified signal, not picked'
                html += '<details><summary>'+esc(row.get('instrument', 'Idea'))+' <span>'+esc(label)+'</span></summary><p>'+esc(row.get('reason', 'Reason not saved'))+'</p></details>'
            if not rows: html += '<p>No detailed ideas saved.</p>'
    return html+'</section></section>'

def render(state):
    reviews = state.get('decision_room', [])
    html = '<div class="team-toolbar"><div><h1>Your investment team</h1><p>See the decision. Explore the work behind it.</p></div>'
    if reviews:
        html += '<label>Review <select id="team-review">'+''.join(f'<option value="{i}">{esc(date_label(r.get("timestamp")))}</option>' for i,r in enumerate(reviews))+'</select></label>'
    html += '<a class="team-refresh" href="/">Refresh records</a><a class="button" href="/room">Enter Decision room</a></div>'
    html += render_clock(state.get('now'))
    if state.get('paused'): html += '<p class="team-pause">Paper activity is paused. You’re viewing saved work.</p>'
    if not reviews: html += '<section class="team-outcome"><h2>No saved review yet</h2><p>When a review is recorded, its team and outcome will appear here.</p></section>'
    html += ''.join(review_view(review, i) for i,review in enumerate(reviews))
    html += '<section class="team-next"><h2>Needs you</h2>'
    cards = state.get('cards', [])
    if cards:
        html += ''.join('<details><summary>'+esc(c.get('proposal', {}).get('ticker', 'Saved proposal'))+' · '+esc(c.get('status', 'Unknown'))+'</summary>'+preview_card(c)+'</details>' for c in cards[:30])
    else: html += '<p>No approval cards in the saved inbox.</p>'
    return html+'<p class="team-caption">This page is view-only. <a href="/legacy#decisions">Approve or reject cards in Approvals →</a></p></section>'
