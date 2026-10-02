"""History (/history): one card per trading day, newest first, built from the same local records as the
other pages. Each day shows what the desk decided, every paper fill, the 15:50 protective check and the
notes that were written, in time order. Read-only."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from .charts import esc, money
from .components import ARM_NAMES, RUN_LABEL, category_chips

ET = ZoneInfo('America/New_York')
ARM = {**ARM_NAMES, 'deterministic_no_ai': 'Rules only'}
KIND = {'run': 'Run', 'fill': 'Paper fill', 'guard': 'Protective check', 'note': 'Team note'}


def _dt(stamp):
    try:
        d = datetime.fromisoformat(str(stamp))
        return d.astimezone(ET) if d.tzinfo else None
    except (TypeError, ValueError):
        return None


def _qty(v):
    try:
        return f'{float(v):,.5f}'.rstrip('0').rstrip('.')
    except (TypeError, ValueError):
        return str(v)


def events(state):
    """[(datetime ET, kind, title, text, review or None)] for everything recorded, any day."""
    from .workspace import outcome
    pf = state.get('portfolio') or {}
    a = state.get('analyst') or {}
    out = []
    for r in state.get('decision_room') or []:
        d = _dt(r.get('timestamp'))
        if d:
            official = (r.get('category') or {}).get('group') == 'official'
            out.append((d, 'run', RUN_LABEL if official else 'Build run', outcome(r), r))
    fills = defaultdict(list)
    for f in pf.get('fills') or []:
        d = _dt(f.get('timestamp'))
        if d and f.get('status') == 'filled':
            fills[(d.replace(second=0, microsecond=0), f.get('side'), f.get('ticker'), str(f.get('price')), str(f.get('quantity')))].append(f)
    for (d, side, ticker, price, qty), group in fills.items():
        arms = [ARM.get(str(f.get('track') or '').split(':')[-1], str(f.get('track'))) for f in group]
        lane = str(group[0].get('track') or '').split(':')[0]
        out.append((d, 'fill', f'{"Bought" if side == "buy" else "Sold"} {ticker}',
                    f'{_qty(qty)} shares at {money(price)} · ' + ' and '.join(dict.fromkeys(arms)) + (f' (Lane {lane})' if lane in ('A', 'B') else ''), None))
    for p in (state.get('research') or {}).get('protective') or []:
        d = _dt(p.get('timestamp'))
        if d:
            held = ', '.join(p.get('held') or [])
            text = (f'Sold {p.get("fired")} position(s).' if p.get('fired') else 'Nothing sold.') + (f' Still holding {held}.' if held else '')
            if p.get('error_type') or (p.get('status') and p.get('status') not in ('OK', 'COMPLETED')):
                text += f' Status: {p.get("error_type") or p.get("status")}.'
            out.append((d, 'guard', 'Protective check', text, None))
    for key, label in (('morning', 'Morning note'), ('close', 'After-close note')):
        n = a.get(key) or {}
        d = _dt(n.get('at'))
        if d:
            out.append((d, 'note', f'Bubbles · {label}', str(n.get('headline') or ''), None))
    names = {'pip': 'Blossom', 'biscuit': 'Buttercup', 'maple': 'Mayor', 'pickle': 'Mojo Jojo'}
    team = [(names.get(s, s), _dt(n.get('at'))) for s, n in (a.get('team') or {}).items()]
    by_day = defaultdict(list)
    for name, d in team:
        if d:
            by_day[d.date()].append((d, name))
    for day, items in by_day.items():
        out.append((max(d for d, _ in items), 'note', 'Team notes', ', '.join(n for _, n in sorted(items)) + ' wrote their daily notes.', None))
    rank = {'run': 0, 'fill': 1, 'guard': 2, 'note': 3}       # inside one minute: the run, then what it did
    out.sort(key=lambda e: (e[0].replace(second=0, microsecond=0), rank[e[1]], e[0]))
    return out


def _tech(r):
    head = r.get('header') or {}
    gate = r.get('ai_gate') or {}
    rows = [('Run id', head.get('short_id')), ('Took', head.get('duration')), ('Data', head.get('data_mode')),
            ('Stages recorded', f'{head.get("completed_stages")} of {head.get("expected_stages")}' if head.get('expected_stages') else None),
            ('AI gate', ('open' if gate.get('open') else 'closed') + (f' ({gate.get("reason")})' if gate.get('reason') else '') if gate else None),
            ('AI cost', ('$' + str(head.get('api_cost_estimate_usd'))) if head.get('api_cost_estimate_usd') is not None else None),
            ('Signals', ', '.join(r.get('signal_instruments') or []) or 'none')]
    return ''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in rows if v not in (None, ''))


def render(state):
    from .workspace import outcome
    ev = events(state)
    head = ('<div class="room-head"><div><h1>History</h1><p>One card per day, newest first: what the desk decided, every paper fill, '
            'the protective check and the notes that were written.</p></div></div>')
    if not ev:
        return head + '<p class="v10-empty">Nothing is recorded yet.</p>'
    days = defaultdict(list)
    for e in ev:
        days[e[0].date()].append(e)
    runs = [e for e in ev if e[1] == 'run']
    official = [e for e in runs if (e[4].get('category') or {}).get('group') == 'official']
    tiles = (('Days recorded', len(days), 'with at least one event'), ('Registered paper runs', len(official), f'{sum(1 for e in official if (e[4].get("category") or {}).get("counts"))} count toward the experiment'),
             ('Paper fills', sum(1 for e in ev if e[1] == 'fill'), 'buys and sells, grouped by price'),
             ('Protective checks', sum(1 for e in ev if e[1] == 'guard'), 'the 15:50 look at every holding'))
    kpis = '<div class="an-kpis">' + ''.join(f'<div class="an-kpi"><span>{esc(t)}</span><b>{esc(v)}</b><small>{esc(n)}</small></div>' for t, v, n in tiles) + '</div>'
    cards = ''
    for day in sorted(days, reverse=True)[:40]:
        items = days[day]
        day_runs = [e for e in items if e[1] == 'run']
        lead = next((e for e in reversed(day_runs) if (e[4].get('category') or {}).get('group') == 'official'), day_runs[-1] if day_runs else None)
        title = outcome(lead[4]) if lead else next((e[2] + ': ' + e[3] for e in items if e[1] != 'note'), items[-1][2])
        chips = category_chips(lead[4]) if lead else ''
        line = ''.join(f'<li class="k-{kind}"><time>{esc(d.strftime("%-I:%M %p"))}</time><i aria-hidden="true"></i><div><b>{esc(t)}</b>'
                       f'<p>{esc(text)}</p></div></li>' for d, kind, t, text, _ in items)
        tech = ''.join(f'<h4>{esc(d.strftime("%-I:%M %p"))} · {esc(t)}</h4><dl class="v10-facts">{_tech(r)}</dl>' for d, _, t, _, r in day_runs)
        counts = ' · '.join(f'{n} {KIND[k].lower()}{"s" if n != 1 else ""}' for k in ('run', 'fill', 'guard', 'note')
                           for n in [sum(1 for e in items if e[1] == k)] if n)
        cards += (f'<article class="v10-panel hd"><header><div><p class="hd-date">{esc(day.strftime("%A, %B %-d"))}</p><h2>{esc(title)}</h2></div>'
                  f'{chips}</header><p class="hd-counts">{esc(counts)}</p><ol class="hd-line">{line}</ol>'
                  + (f'<details class="hd-tech"><summary>Run details</summary>{tech}<p><a href="/room">Open the Decision room →</a></p></details>' if tech else '')
                  + '</article>')
    return (head + kpis + f'<div class="hd-list">{cards}</div>'
            + '<p class="v10-note"><a href="/legacy#history">Operational history with filters (older format) →</a> · Times are New York time.</p>')
