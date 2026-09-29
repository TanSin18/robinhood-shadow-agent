"""Escaped, offline shared components."""
from html import escape
from .team import TEAM

ROUTES = (('/', 'Today'), ('/room', 'Decision room'), ('/portfolio', 'Portfolio'),
          ('/money', 'Road to money'), ('/scoreboard', 'Is the AI working?'),
          ('/controls', 'Controls'), ('/health', 'Tweaks and health'))


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
    links = ''.join(f'<a href="{route}"'+(' aria-current="page"' if route == path else '')+f'>{"Road to real money" if state.get("preview") and route == "/money" else label}</a>' for route, label in ROUTES)
    scripts = '<script src="/assets/agent-desk.js" defer></script><script src="/assets/agent-scene.js" defer></script>' if state.get('preview') else '<script src="/assets/dashboard.js" defer></script><script src="/assets/agent-desk.js" defer></script>'
    preview = '<p class="desk-preview" role="status">Preview — view only · No approvals, controls or broker connection</p>' if state.get('preview') else ''
    refresh = ''
    body_class = 'agent-desk team-preview' if state.get('preview') else 'agent-desk'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · Agent Desk</title><link rel="stylesheet" href="/assets/dashboard.css"><link rel="stylesheet" href="/assets/agent-desk.css">
{'<link rel="stylesheet" href="/assets/agent-scene.css"><link rel="stylesheet" href="/assets/agent-polish.css">' if state.get('preview') else ''}
{scripts}{refresh}</head><body class="{body_class}">{preview}<a class="skip" href="#main">Skip to content</a>
<header class="desk-header"><a class="desk-brand" href="/">↗ Agent Desk</a><nav aria-label="Sections">{links}</nav>
<span class="desk-safety {'stopped' if stopped else ''}">{esc(safety)}</span></header>
<main id="main" tabindex="-1">{body}</main><footer>Local records · Paper trading only. Real orders are blocked.</footer></body></html>'''


def deferred(title, milestone):
    return f'<h1>{esc(title)}</h1>'+card('Not available yet', f'<p>This screen is scheduled for {esc(milestone)}. No results are assumed.</p>')
