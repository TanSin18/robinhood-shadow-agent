"""Rule book: every rule the system runs, with its real numbers, schedule, effect and source.

Content comes from rulebook.json, a catalogue built by reading the installed code and the signed
YAML (each entry carries a file:line or YAML key). The page renders without records or scripts;
/assets/agent-v10.js only adds "Expand all". Nothing here is a black box: where the docs and the
code disagree, the code value is shown and the mismatch is listed under Known issues.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .charts import esc

DATA = Path(__file__).with_name('rulebook.json')
GROUP_ORDER = ('signals', 'desk_entry', 'risk_engine', 'exits', 'approvals', 'accounting', 'ai_official', 'safety',
               'data', 'schedule', 'activation', 'isolation', 'registered_not_implemented')
KIND = (('ai', ('AI', 'Research', 'Critic', 'Portfolio', 'model')), ('you', ('approval', 'card', 'operator', 'YES')),
        ('safety', ('protective', 'tripwire', 'safety', 'breaker', 'stop')))
LIMITS = (('$25,000', 'paper cash per Lane A account (v1.6)'), ('25%', 'largest single position, of account value'),
          ('5', 'most open positions per account'), ('min(25%, 2% ÷ vol)', 'position size: 10% × 20% target ÷ 20-session realized volatility'),
          ('0.5%', 'furthest a limit price may sit from the reference price'), ('3%', 'daily loss that blocks new buys'),
          ('5%', 'weekly loss that trips the kill switch'), ('10%', 'drawdown from peak that latches off new buys'),
          ('8%', 'v1.6 protective stop below average cost (15:50 check)'), ('$0.40', 'official AI spend ceiling per day'),
          ('5', 'most filled orders per account per day'), ('$1,200', 'highest real Agentic cash the system accepts'))


@lru_cache(maxsize=1)
def catalogue():
    try:
        return json.loads(DATA.read_text())
    except (OSError, ValueError):
        return {}


def _status_cls(status):
    s = (status or '').lower()
    if s.startswith('active'):
        return 'active'
    if s.startswith('not') or 'not implemented' in s or 'not found' in s:
        return 'missing'
    if s.startswith('paused'):
        return 'paused'
    if s.startswith('draft'):
        return 'draft'
    return 'disabled'


def _status_label(status):
    s = (status or 'not stated').split(';')[0].split('(')[0].strip()
    return {'not': 'not in code'}.get(s, s.replace('-', ' '))[:40]


def value(v, depth=0):
    """Render any catalogue value: dict -> definition list, list -> bullets, text -> text."""
    if isinstance(v, dict):
        return '<dl>' + ''.join(f'<dt>{esc(str(k).replace("_", " "))}</dt><dd>{value(x, depth + 1)}</dd>' for k, x in v.items()) + '</dl>'
    if isinstance(v, list):
        if all(not isinstance(x, (dict, list)) for x in v) and sum(len(str(x)) for x in v) < 220:
            return esc(', '.join(str(x) for x in v))
        return '<ul>' + ''.join(f'<li>{value(x, depth + 1)}</li>' for x in v) + '</ul>'
    if v is None:
        return '—'
    return esc(v)


def _rule(r):
    fields = (('Applies to', r.get('applies_to')), ('When', r.get('when')), ('Condition', r.get('condition')),
              ('What happens', r.get('action')), ('Why', r.get('why')), ('Effective', r.get('effective')),
              ('Source', r.get('source')))
    body = ''.join(f'<dt>{esc(k)}</dt><dd{" class=rb-src" if k == "Source" else ""}>{value(v)}</dd>' for k, v in fields if v)
    return (f'<details class="rb-rule" id="rule-{esc(r.get("id", ""))}"><summary><b>{esc(r.get("name", r.get("id", "")))}</b>'
            f'<span class="rb-status {_status_cls(r.get("status"))}">{esc(_status_label(r.get("status")))}</span>'
            f'<span class="rb-plain">{esc((r.get("condition") or "")[:170])}{"…" if len(r.get("condition") or "") > 170 else ""}</span></summary>'
            f'<div class="rb-body"><dl>{body}</dl></div></details>')


def _section(sid, title, intro, body, tools=False):
    btn = f'<div class="rb-tools"><button type="button" class="rb-btn" data-expand-all="{sid}">Expand all</button></div>' if tools else ''
    return (f'<section class="rb-section" id="{sid}"><header><h2>{esc(title)}</h2>'
            + (f'<p>{intro}</p>' if intro else '') + f'</header>{btn}{body}</section>')


def _kind(text):
    for k, words in KIND:
        if any(w in text for w in words):
            return k
    return 'code'


def timeline(c):
    items = ''
    for i, t in enumerate(c.get('daily_timeline') or []):
        what = t.get('what') or ''
        first = what.split('. ')[0]
        items += (f'<li class="k-{_kind(what)}"><details{" open" if i < 1 else ""}><summary><time>{esc(t.get("time_et"))}</time>'
                  f'{esc(first[:150])}{"…" if len(first) > 150 else ""}</summary><p>{esc(what)}</p>'
                  f'<p class="rb-src">{esc(t.get("source"))}</p></details></li>')
    return f'<div class="rb-day"><ol>{items}</ol></div>'


def pipeline(c):
    out = ''
    for s in c.get('official_cycle_stages') or []:   # already in run order (7a…7i are the AI-path sub-steps)
        gates = ''.join(f'<span>{esc(g)}</span>' for g in s.get('gates') or [])
        what = s.get('what') or ''
        out += (f'<details class="rb-stage"><summary><span><b>{esc(s.get("stage"))}</b><small>{esc(what[:110])}{"…" if len(what) > 110 else ""}</small></span></summary>'
                f'<div class="rb-body"><p>{esc(what)}</p>' + (f'<div class="rb-gates">{gates}</div>' if gates else '')
                + f'<p class="rb-src">{esc(s.get("source"))}</p></div></details>')
    return f'<div class="rb-pipe">{out}</div>'


def _cards(items, title_key, keys):
    out = ''
    for it in items:
        body = ''.join(f'<dt>{esc(k.replace("_", " ").title())}</dt><dd{" class=rb-src" if k == "source" else ""}>{value(it.get(k))}</dd>'
                       for k in keys if it.get(k))
        status = it.get('status')
        out += (f'<details class="rb-rule"><summary><b>{esc(it.get(title_key))}</b>'
                + (f'<span class="rb-status {_status_cls(status)}">{esc(_status_label(status))}</span>' if status else '')
                + f'<span class="rb-plain">{esc(str(it.get(keys[0]) or "")[:170])}</span></summary><div class="rb-body"><dl>{body}</dl></div></details>')
    return f'<div class="rb-groupgrid">{out}</div>'


def render(state):
    c = catalogue()
    if not c:
        return '<h1>Rule book</h1><p class="v10-empty">The rule catalogue file is missing from this install.</p>'
    groups = {g['id']: g for g in c.get('rule_groups') or []}
    ordered = [groups[g] for g in GROUP_ORDER if g in groups] + [g for k, g in groups.items() if k not in GROUP_ORDER]
    n_rules = sum(len(g.get('rules') or []) for g in ordered)
    toc = [('day', 'A day, minute by minute'), ('cycle', 'The 10:00 run, stage by stage'), ('limits', 'Key limits')]
    toc += [(f'g-{g["id"]}', g['title'].split('(')[0].strip()) for g in ordered]
    toc += [('accounts', 'Accounts and lanes'), ('fills', 'How paper fills are priced'), ('breakers', 'Breakers and stops'),
            ('budgets', 'AI budgets'), ('real', 'Why real money cannot move'), ('promotion', 'What must be proven'),
            ('ai-trader', 'AI trader (separate book)'), ('issues', 'Known issues'), ('shorthand', 'Shorthand decoded')]
    meta = c.get('meta') or {}
    layers = ''.join(f'<li><b>{esc(l.get("file"))}</b> · v{esc(l.get("version"))} · {esc(l.get("status"))}'
                     f'<small> sha256 {esc(str(l.get("sha256") or "")[:16])}…</small></li>' for l in meta.get('registration_layers') or [])
    html = ['<div class="rb">',
            '<header><p class="v10-eyebrow">Nothing is a black box</p><h1>Rule book</h1>'
            f'<p class="rb-lede">All {n_rules} rules the system runs, with the real numbers, when they run, what they do and the file and line '
            'they come from. Read from the installed code and the signed rule files; where the guide text and the code disagree, the code wins '
            'and the gap is listed under Known issues. Open any row for the full detail.</p></header>',
            '<nav class="rb-toc" aria-label="Rule book sections">' + ''.join(f'<a href="#{i}">{esc(t)}</a>' for i, t in toc) + '</nav>',
            _section('day', 'A day, minute by minute', 'Eastern time. Colour of the dot: blue = code, violet = AI, green = you, amber = safety.',
                     timeline(c)),
            _section('cycle', 'The 10:00 official run, stage by stage',
                     'Each card is one stage in order. The amber chips are the gates that must pass; any failed gate stops the run or the trade '
                     'with a recorded reason.', pipeline(c)),
            _section('limits', 'Key limits at a glance', 'The numbers that bound every paper trade. Full conditions are in the groups below.',
                     '<div class="rb-limits">' + ''.join(f'<div class="rb-limit"><b>{esc(a)}</b><span>{esc(b)}</span></div>' for a, b in LIMITS) + '</div>')]
    for g in ordered:
        html.append(_section(f'g-{g["id"]}', g['title'], esc(g.get('plain') or ''),
                             '<div class="rb-groupgrid">' + ''.join(_rule(r) for r in g.get('rules') or []) + '</div>', tools=True))
    arms = c.get('arms_and_lanes') or {}
    html.append(_section('accounts', 'Accounts and lanes', 'Who trades which money, and what each account is there to measure.',
                         f'<div class="rb-rule"><div class="rb-body">{value(arms)}</div></div>'))
    html.append(_section('fills', 'How paper fills are priced', 'Real quotes, simulated orders. These are the exact formulas.',
                         f'<div class="rb-rule"><div class="rb-body">{value(c.get("fill_model") or {})}</div></div>'))
    html.append(_section('breakers', 'Breakers and stops', 'Automatic brakes, what trips them and how (or whether) they reset.',
                         _cards(c.get('breakers_and_stops') or [], 'name', ['condition', 'scope', 'effect', 'reset', 'source']), tools=True))
    html.append(_section('budgets', 'AI budgets', 'Every model call reserves its worst-case cost first; uncertain calls keep the full reservation.',
                         _cards(c.get('budgets') or [], 'name', ['value', 'source']), tools=True))
    html.append(_section('real', 'Why real money cannot move', 'Independent layers; any one of them is enough to stop a real order.',
                         _cards(c.get('real_money_blocks') or [], 'mechanism', ['detail', 'source']), tools=True))
    html.append(_section('promotion', 'What must be proven before anything goes live', '',
                         f'<div class="rb-rule"><div class="rb-body">{value(c.get("promotion_gate") or {})}</div></div>'))
    html.append(_section('ai-trader', 'AI trader (separate forward book)', 'Its own database and budget; never counted in the official results.',
                         f'<div class="rb-rule"><div class="rb-body">{value(c.get("ai_trader") or {})}</div></div>'))
    issues = sorted(c.get('known_issues') or [], key=lambda i: {'high': 0, 'medium': 1, 'low': 2}.get(i.get('severity'), 3))
    html.append(_section('issues', 'Known issues', 'Honest list of bugs, gaps and mismatches found while writing this book. High first.',
                         '<div class="rb-groupgrid">' + ''.join(
                             f'<details class="rb-rule rb-issue sev-{esc(i.get("severity"))}"><summary><b>{esc(i.get("id", "").replace("ki-", "").replace("-", " "))}</b>'
                             f'<span class="rb-status {"missing" if i.get("severity") == "high" else "paused"}">{esc(i.get("severity"))}</span>'
                             f'<span class="rb-plain">{esc((i.get("issue") or "")[:200])}…</span></summary>'
                             f'<div class="rb-body"><p>{esc(i.get("issue"))}</p><p class="rb-src">{esc(i.get("source"))}</p></div></details>' for i in issues)
                         + '</div>', tools=True))
    html.append(_section('shorthand', 'Shorthand decoded', 'Phrases used elsewhere in the dashboard, and exactly what they mean.',
                         '<dl class="rb-vague">' + ''.join(f'<dt>“{esc(v.get("phrase"))}”<br><small>{esc(v.get("where"))}</small></dt><dd>{esc(v.get("means"))}</dd>'
                                                          for v in c.get('vague_phrases_resolved') or []) + '</dl>'))
    html.append(_section('layers', 'Signed rule files in force', esc(meta.get('method') or ''), f'<ul class="v10-list">{layers}</ul>'))
    html.append('</div>')
    return ''.join(html)
