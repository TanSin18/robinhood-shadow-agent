"""Escaped, offline shared components."""
from html import escape
from .team import TEAM

ROUTES = (('/', 'Today'), ('/room', 'Decision room'), ('/checks', 'Checks & charts'), ('/portfolio', 'Portfolio'),
          ('/money', 'Road to money'), ('/scoreboard', 'Is the AI working?'),
          ('/controls', 'Controls'), ('/health', 'Tweaks and health'), ('/guide', 'How it works'), ('/inbox', 'Inbox'), ('/firm', 'AI trader'),
          ('/rules', 'Rule book'), ('/architecture', 'Architecture'), ('/analyst', 'Analyst desk'))


# One navigation for the whole dashboard. Operational views (Approvals, History,
# Results, Controls) are served by the unchanged operational page at /legacy.
NAV = (('/', 'Today', ''), ('/portfolio', 'Portfolio', ''), ('/legacy#decisions', 'Approvals', 'decisions'), ('/inbox', 'Inbox', ''), ('/analyst', 'Analyst', ''),
       ('/room', 'Decision room', ''), ('/checks', 'Checks & charts', ''), ('/legacy#history', 'History', 'history'),
       ('/legacy#controls', 'Controls', 'controls'), ('/guide', 'How it works', ''), ('/rules', 'Rule book', ''),
       ('/architecture', 'Architecture', ''))


def nav_links(path):
    return ''.join(f'<a href="{href}"' + (f' data-nav="{key}"' if key else '') + (' aria-current="page"' if href == path else '')
                   + f'>{esc(label)}</a>' for href, label, key in NAV)


def esc(value):
    return escape(str(value), quote=True)


def avatar(key):
    name, role, asset, kind = TEAM[key]
    portrait = (f'<img src="/assets/avatars/{asset}" width="56" height="56" alt="">'
                if asset else '<span class="desk-symbol" aria-hidden="true">◉</span>')
    return f'<span class="desk-identity {kind}">{portrait}<span><strong>{name}</strong><small>{esc(role)}</small></span></span>'


def card(title, body, classes=''):
    return f'<section class="desk-card {classes}"><h2>{esc(title)}</h2>{body}</section>'


def shell(title, body, path='/', state=None):
    state = state or {}
    stopped = state.get('paused') or any(t.get('incident_id') for t in state.get('tripwire', []))
    safety = 'Safety stop or pause active · real orders blocked' if stopped else 'Paper only · real orders blocked'
    links = nav_links(path) if state.get('preview') else ''.join(f'<a href="{route}"'+(' aria-current="page"' if route == path else '')+f'>{label}</a>' for route, label in ROUTES)
    scripts = '<script src="/assets/agent-desk.js" defer></script><script src="/assets/agent-scene.js" defer></script>' if state.get('preview') else '<script src="/assets/dashboard.js" defer></script><script src="/assets/agent-desk.js" defer></script>'
    preview = '<p class="desk-preview" role="status">Preview — view only · No approvals, controls or broker connection</p>' if state.get('preview') else ''
    refresh = ''
    body_class = 'agent-desk team-preview' if state.get('preview') else 'agent-desk'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · Botfolio</title><link rel="icon" href="/assets/botfolio-logo.svg"><link rel="stylesheet" href="/assets/dashboard.css"><link rel="stylesheet" href="/assets/agent-desk.css">
{'<link rel="stylesheet" href="/assets/agent-polish.css"><link rel="stylesheet" href="/assets/agent-scene.css"><link rel="stylesheet" href="/assets/agent-compact.css">' if state.get('preview') else ''}
{'<link rel="stylesheet" href="/assets/guide.css"><script src="/assets/guide.js" defer></script>' if path == '/guide' else ''}
<link rel="stylesheet" href="/assets/agent-v10.css"><link rel="stylesheet" href="/assets/botfolio-theme.css"><script src="/assets/agent-v10.js" defer></script>
{scripts}{refresh}</head><body class="{body_class}">{preview}<a class="skip" href="#main">Skip to content</a>
<header class="desk-header"><a class="desk-brand bf-brand" href="/"><img src="/assets/botfolio-logo.svg" width="34" height="34" alt="">Botfolio</a><nav aria-label="Sections">{links}</nav>
<span class="desk-safety {'stopped' if stopped else ''}">{esc(safety)}</span></header>
<main id="main" tabindex="-1">{body}</main><footer>Local records · Paper trading only. Real orders are blocked.</footer></body></html>'''


def deferred(title, milestone):
    return f'<h1>{esc(title)}</h1>'+card('Not available yet', f'<p>This screen is scheduled for {esc(milestone)}. No results are assumed.</p>')


def category_chips(review):
    cat = review.get('category') or {}
    chips = ''.join(f'<span class="cat cat-{esc(t["tone"])}" title="{esc(t["title"])}">{esc(t["label"])}</span>' for t in cat.get('tags', []))
    if cat:
        chips += f'<span class="cat cat-{"counts" if cat.get("counts") else "nocount"}">{esc(cat.get("counts_reason", ""))}</span>'
    return f'<div class="cat-row">{chips}</div>' if chips else ''


def category_prefix(review):
    cat = review.get('category') or {}
    return '' if not cat else ('[Official] ' if cat.get('group') == 'official' else '[Build] ')


V16_CAPITAL = 25000   # signed v1.6.0 amendment: Lane A paper capital per account
V16_START_TEXT = 'Thursday Oct 1, at the first official run (10:00 ET)'


def capital_state(state):
    """'rebased' once the ledger shows the v1.6 reset; otherwise 'scheduled'. Read from records only."""
    paper = (state.get('portfolio') or {}).get('paper') or []
    lane_a = [p for p in paper if p.get('lane') == 'A']
    rebase = (state.get('research') or {}).get('rebase')
    if rebase or any(p.get('capital_version') == '1.6.0' for p in lane_a):
        return 'rebased', rebase
    return 'scheduled', None


def capital_note(state):
    status, rebase = capital_state(state)
    if status == 'rebased':
        at = (rebase or {}).get('timestamp', '')
        return ('<p class="capital-note is-live"><strong>Paper capital:</strong> Lane A (stocks &amp; ETFs) '
                f'${V16_CAPITAL:,} per account under v1.6' + (f', since {esc(at[:16].replace("T", " "))} UTC' if at else '')
                + '. Lane B (options) $500, new option buys paused. Real money: $0.</p>')
    return ('<p class="capital-note is-scheduled"><strong>Paper capital:</strong> Lane A (stocks &amp; ETFs) becomes '
            f'<strong>${V16_CAPITAL:,} per account</strong> on {V16_START_TEXT} under the signed v1.6 rules. Until then the '
            'accounts still hold the $500 build-phase balances, which are archived (not deleted) at the switch. '
            'Lane B (options) stays $500 with new option buys paused. Real money: $0.</p>')
