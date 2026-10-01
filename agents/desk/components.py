"""Escaped, offline shared components."""
from html import escape
from .team import TEAM

ROUTES = (('/', 'Today'), ('/room', 'Decision room'), ('/checks', 'Checks & charts'), ('/portfolio', 'Portfolio'),
          ('/money', 'Road to money'), ('/scoreboard', 'Is the AI working?'),
          ('/controls', 'Controls'), ('/health', 'Tweaks and health'), ('/guide', 'How it works'))


# One navigation for the whole dashboard. Operational views (Approvals, History,
# Results, Controls) are served by the unchanged operational page at /legacy.
NAV = (('/', 'Today', ''), ('/portfolio', 'Portfolio', ''), ('/legacy#decisions', 'Approvals', 'decisions'),
       ('/room', 'Decision room', ''), ('/checks', 'Checks & charts', ''), ('/legacy#history', 'History', 'history'),
       ('/legacy#controls', 'Controls', 'controls'), ('/guide', 'How it works', ''))


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
<title>{esc(title)} · Agent Desk</title><link rel="stylesheet" href="/assets/dashboard.css"><link rel="stylesheet" href="/assets/agent-desk.css">
{'<link rel="stylesheet" href="/assets/agent-polish.css"><link rel="stylesheet" href="/assets/agent-scene.css"><link rel="stylesheet" href="/assets/agent-compact.css">' if state.get('preview') else ''}
{'<link rel="stylesheet" href="/assets/guide.css"><script src="/assets/guide.js" defer></script>' if path == '/guide' else ''}
{scripts}{refresh}</head><body class="{body_class}">{preview}<a class="skip" href="#main">Skip to content</a>
<header class="desk-header"><a class="desk-brand" href="/">↗ Agent Desk</a><nav aria-label="Sections">{links}</nav>
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
