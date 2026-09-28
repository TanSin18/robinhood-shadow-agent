"""Today uses recorded outcomes and existing approval rendering only."""
from .components import card, esc


def render(state, config, csrf, filters=None):
    latest = next((h for h in state.get('history', []) if h.get('kind') == 'cycle'), None)
    summary = ('<p>'+esc(latest.get('summary') or 'Not recorded: no terminal reason is available.')+'</p><p>Recorded at '+esc(latest.get('timestamp') or 'Not recorded')+'</p>') if latest else '<p>Not recorded: no cycle outcome is available.</p>'
    approvals = '<p>Nothing needs your approval right now. An empty inbox does not prove a successful run.</p>'
    if state.get('preview') and state.get('cards'):
        from .approval_card import preview_card
        approvals=''.join(preview_card(c) for c in state['cards'][:30])
    elif state.get('cards'):
        from agents.dashboard_view import card_view, matches
        cards = state['cards']
        if filters:
            cards = [c for c in cards if matches(c, filters, card=True)]
        approvals = ''.join(card_view(c, csrf, state.get('paused', False)) for c in cards[:30]) or '<p>No matching proposals. Clear the filters to see all recorded cards.</p><a href="/">Clear filters</a>'
    money = ''.join(card(label, f'<p class="desk-number">{value}</p><p>{reason}</p>') for label, value, reason in (
        ('AI account', 'Not recorded', 'Official-mode balances are not available in this UI version.'),
        ('No-AI arm', 'Not tracked yet', 'The comparison arm has not been connected.'),
        ('VTI', 'Not recorded', 'A comparable official observation period is required.'),
        ('AI cost this year', 'Not recorded', 'Mode-separated annual costs require U1 records.')))
    return f'''<h1>Today</h1><p class="desk-muted">Last official run: Not recorded · Experiment day: Not recorded</p>
<p class="desk-mode">Historical records · run mode not recorded. Official and learning totals are unavailable.</p>
<div class="desk-today">{card('Latest recorded outcome', summary+'<p class="desk-muted">Code-built summary from the latest recorded cycle outcome; not an AI explanation. This may be from an earlier day.</p>', 'desk-story')}{card('Needs you', approvals)}</div>
{card('From the universe to your inbox', '<p>Not recorded: per-candidate funnel counts arrive with U1. No counts are inferred from cycle-level stages.</p>')}
<div class="desk-money">{money}</div>
{card('This week', '<p>Not recorded: day-by-day official costs need mode-separated records.</p>')}
{card('Is the AI helping yet?', '<p>Not tracked yet. Comparable official arms are required.</p><a href="/scoreboard">Open the scoreboard</a>')}'''
