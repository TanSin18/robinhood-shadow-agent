"""Checks & charts: every recorded check of a run, plus record-backed charts.

Server-rendered SVG only (strict CSP). Values come from agents.run_checks,
which reads named public fields of the run's trace.
"""
from decimal import Decimal
from .components import esc, category_chips, category_prefix
from .workspace import date_label, outcome


def table(head, rows):
    from .scene import table as _table
    return _table(head, rows)

ICON = {'pass': '✓', 'warn': '!', 'fail': '✕', 'info': 'i', 'unknown': '?'}


def status_icon(status):
    status = status if status in ICON else 'unknown'
    return f'<span class="ck ck-{status}" aria-label="{status}">{ICON[status]}</span>'


def cell(c, compact=False):
    ok = c.get('ok')
    if ok == 'skip':
        return f'<td class="cond cond-skip" title="Not evaluated: an earlier condition already failed ({esc(c.get("value", "—"))})"><span>·</span>{"" if compact else " " + esc(c.get("value", "—"))}</td>'
    cls = 'pass' if ok is True else 'fail' if ok is False else 'unknown'
    return f'<td class="cond cond-{cls}" title="{esc(c.get("value", "—"))}"><span>{ICON[cls]}</span>{"" if compact else " " + esc(c.get("value", "—"))}</td>'


# ------------------------------------------------------------------ charts
def bar_chart(rows, *, title, note, threshold=None, threshold_label='', fmt=lambda v: f'{v * 100:+.1f}%'):
    """Horizontal bars around zero. rows: (label, Decimal|None, css_class)."""
    rows = [(l, v, c) for l, v, c in rows if v is not None]
    if not rows:
        return f'<figure class="chart"><figcaption>{esc(title)}</figcaption><p class="muted small">Not recorded for this run.</p></figure>'
    values = [float(v) for _, v, _ in rows] + ([float(threshold)] if threshold is not None else [])
    lo, hi = min(0.0, min(values)), max(0.0, max(values))
    span = (hi - lo) or 1.0
    left, width, row_h = 64, 330, 20
    x = lambda v: left + (float(v) - lo) / span * width
    height = len(rows) * row_h + 26
    zero = x(0)
    bars = ''
    for i, (label, v, cls) in enumerate(rows):
        y = 8 + i * row_h
        a, b = sorted((zero, x(v)))
        bars += (f'<g class="bar {esc(cls)}"><title>{esc(label)}: {esc(fmt(v))}</title>'
                 f'<text class="bar-label" x="{left - 8}" y="{y + 12}" text-anchor="end">{esc(label)}</text>'
                 f'<rect x="{a:.1f}" y="{y + 2}" width="{max(b - a, 1.5):.1f}" height="{row_h - 7}" rx="2"/>'
                 f'<text class="bar-value" x="{(b + 6) if v >= 0 else (zero + 6):.1f}" y="{y + 12}" text-anchor="start">{esc(fmt(v))}</text></g>')
    axis = f'<line class="axis-zero" x1="{zero:.1f}" x2="{zero:.1f}" y1="4" y2="{height - 18}"/>'
    if threshold is not None:
        t = x(threshold)
        axis += (f'<line class="axis-threshold" x1="{t:.1f}" x2="{t:.1f}" y1="4" y2="{height - 18}"/>'
                 f'<text class="axis-note" x="{t:.1f}" y="{height - 4}" text-anchor="middle">{esc(threshold_label)}</text>')
    return (f'<figure class="chart"><figcaption>{esc(title)}</figcaption>'
            f'<svg viewBox="0 0 470 {height}" role="img" aria-label="{esc(title)}">{axis}{bars}</svg>'
            f'<p class="muted small">{esc(note)}</p></figure>')


def charts(checks):
    feats = checks.get('features') or []
    strategies = {s['key']: s for s in checks.get('strategies', [])}
    mom = strategies.get('momentum_rotation')
    etfs = [r['instrument'] for r in mom['rows']] if mom else []
    top = {r['instrument'] for r in mom['rows'] if r['signal']} if mom else set()
    by = {f['instrument']: f for f in feats}
    trend = sorted(((f['instrument'], f['vs_ma200'], 'pos' if (f['vs_ma200'] or 0) > 0 else 'neg') for f in feats),
                   key=lambda r: -(r[1] or Decimal(0)))
    momentum = sorted(((t, by.get(t, {}).get('m126'),
                        'top' if t in top else 'pos' if by.get(t, {}).get('above_ma200') and (by.get(t, {}).get('m126') or 0) > 0 else 'off')
                       for t in etfs), key=lambda r: -(r[1] or Decimal(-99)))
    day = sorted(((f['instrument'], f['day'], 'trigger' if f['day'] is not None and f['day'] <= Decimal('-0.03') else 'neutral') for f in feats),
                 key=lambda r: (r[1] if r[1] is not None else Decimal(0)))
    return ('<div class="chart-grid">'
            + bar_chart(trend, title='Trend check: price vs 200-day average',
                        note='Right of zero = above the 200-day average (both strategies require this).')
            + bar_chart(momentum, title='Momentum ranking (126 days, ETFs)',
                        note='Highlighted = the one ETF the rule picks. Grey = fails the trend or momentum condition.')
            + bar_chart(day, title='Last session move vs mean-reversion trigger', threshold=Decimal('-0.03'),
                        threshold_label='−3% trigger', fmt=lambda v: f'{v * 100:+.2f}%',
                        note='A name qualifies only if it fell 3% or more AND is above its 200-day average.')
            + '</div>')


# ------------------------------------------------------------------ sections
def operational(rows):
    if not rows:
        return '<p class="muted">Operational checks were not recorded for this run.</p>'
    groups = {}
    for r in rows:
        groups.setdefault(r['group'], []).append(r)
    counts = {s: sum(r['status'] == s for r in rows) for s in ('pass', 'warn', 'fail')}
    summary = (f'<p class="ck-summary">{status_icon("pass")} {counts["pass"]} passed · {status_icon("warn")} {counts["warn"]} warnings'
               f' · {status_icon("fail")} {counts["fail"]} failed</p>')
    body = ''
    for group, items in groups.items():
        body += f'<section class="ck-group"><h4>{esc(group)}</h4><ul>' + ''.join(
            f'<li class="ck-row st-{esc(r["status"])}">{status_icon(r["status"])}<span class="ck-name">{esc(r["check"])}</span>'
            f'<span class="ck-value">{esc(r["value"])}</span>' + (f'<span class="ck-note">{esc(r["note"])}</span>' if r.get('note') else '') + '</li>'
            for r in items) + '</ul></section>'
    return summary + f'<div class="ck-groups">{body}</div>'


def strategy_tables(strategies, limit=None, compact=False):
    if not strategies:
        return '<p class="muted">Strategy conditions were not recorded for this run.</p>'
    html = ''
    for s in strategies:
        rows = s['rows'][:limit] if limit else s['rows']
        extra = ' compact' if compact else ''
        head = ''.join(f'<th>{esc(label)}</th>' for _, label in s['conditions'])
        body = ''
        for r in rows:
            flag = ' <span class="mismatch" title="Recomputed conditions disagree with the recorded outcome">mismatch</span>' if r['mismatch'] else ''
            outcome_cls = 'signal' if r['signal'] else 'blocked'
            body += (f'<tr class="row-{outcome_cls}"><th scope="row">{esc(r["instrument"])}</th>'
                     + ''.join(cell(r['cells'][k], compact) for k, _ in s['conditions'])
                     + f'<td class="outcome-{outcome_cls}"><strong>{esc("Signal" if r["signal"] else r["recorded"].capitalize())}</strong>{flag}'
                     + (f'<small>{esc(r["reason"])}</small>' if r.get('reason') and not compact else '') + '</td></tr>')
        more = f'<p class="muted small">Showing {len(rows)} of {len(s["rows"])}. All rows are on Checks &amp; charts.</p>' if limit and len(s['rows']) > limit else ''
        verdict = (f'{s["signals"]} signal' + ('' if s['signals'] == 1 else 's')) + (f' · {s["mismatches"]} mismatch' if s['mismatches'] else ' · recorded outcome matches every row')
        html += (f'<section class="strategy"><div class="strategy-head"><h4>{esc(s["title"])}</h4><span class="muted small">{esc(verdict)}</span></div>'
                 f'<p class="muted small code">{esc(s["version"])}</p>'
                 f'<div class="table-wrap"><table class="mini matrix{extra}"><thead><tr><th>Ticker</th>{head}<th>Recorded outcome</th></tr></thead><tbody>{body}</tbody></table></div>{more}</section>')
    return html + ('<p class="muted small">Condition cells are re-evaluated from the features this run recorded, using the rule constants '
                   'in <span class="code">research/strategy_signals.py</span>. The outcome column is what the run itself recorded; '
                   'any disagreement is flagged “mismatch”.</p>')


def risk_table(rows):
    if not rows:
        return '<p class="muted">No trade reached the safety rules in this run.</p>'
    return ('<div class="table-wrap"><table class="mini"><thead><tr><th>Instrument</th><th>Arm</th><th>Status</th><th>Reasons</th></tr></thead><tbody>'
            + ''.join(f'<tr><td>{esc(r["instrument"])}</td><td>{esc(r.get("arm") or "—")}</td><td>{esc(r["status"])}</td><td>{esc("; ".join(r["reasons"]) or "—")}</td></tr>' for r in rows)
            + '</tbody></table></div>')


def feature_table(feats):
    if not feats:
        return '<p class="muted">Features were not recorded.</p>'
    p = lambda v, d=1: '—' if v is None else f'{v * 100:+.{d}f}%'
    n = lambda v: '—' if v is None else f'{v:,.2f}'
    return ('<div class="table-wrap"><table class="mini num"><thead><tr><th>Ticker</th><th>Price</th><th>200-day avg</th><th>vs avg</th>'
            '<th>1-day</th><th>63-day</th><th>126-day</th><th>252-day</th><th>Closes</th></tr></thead><tbody>'
            + ''.join(f'<tr><th scope="row">{esc(f["instrument"])}</th><td>{n(f["price"])}</td><td>{n(f["ma200"])}</td>'
                      f'<td class="{"pos" if (f["vs_ma200"] or 0) > 0 else "neg"}">{p(f["vs_ma200"])}</td><td class="{"neg" if (f["day"] or 0) < 0 else "pos"}">{p(f["day"], 2)}</td>'
                      f'<td>{p(f["m63"])}</td><td>{p(f["m126"])}</td><td>{p(f["m252"])}</td><td>{esc(f["closes"] if f["closes"] is not None else "—")}</td></tr>' for f in feats)
            + '</tbody></table></div>')


def history(reviews):
    """One row per saved run: outcome, signals, AI gate and cost."""
    if not reviews:
        return ''
    costs = [float(r.get('header', {}).get('api_cost_estimate_usd') or 0) for r in reviews]
    top = max(costs) or 1.0
    rows = ''
    for r, cost in zip(reviews, costs):
        checks = r.get('checks') or {}
        signals = sum(s['signals'] for s in checks.get('strategies', []))
        ops = checks.get('operational', [])
        warn = sum(o['status'] in {'warn', 'fail'} for o in ops)
        g = r.get('ai_gate')
        stages = ''.join(f'<i class="dot st-{esc(s.get("status", "unavailable"))}" title="{esc(s.get("key"))}: {esc(s.get("status_label"))}"></i>' for s in r.get('stages', []))
        cat = r.get('category') or {}
        kind = ('<span class="cat cat-neutral">Registered paper run</span>' if cat.get('group') == 'official' else '<span class="cat cat-build">Build</span>') if cat else ''
        counts = ('Yes' if cat.get('counts') else 'No') if cat else '—'
        extra = ''.join(f'<span class="cat cat-{esc(t["tone"])}" title="{esc(t["title"])}">{esc(t["label"])}</span>' for t in cat.get('tags', [])[1:] if t['tone'] in {'warn', 'stop'})
        rows += (f'<tr class="{"row-build" if cat.get("group") == "build" else ""}"><td class="nowrap">{esc(date_label(r.get("timestamp")))}</td><td>{kind}{extra}</td><td title="{esc(cat.get("counts_reason", ""))}">{counts}</td><td>{esc(outcome(r))}</td><td class="dots">{stages}</td>'
                 f'<td class="num">{signals}</td><td>{esc("open" if g and g["open"] else "closed" if g else "—")}</td>'
                 f'<td><svg class="spark" viewBox="0 0 100 10" aria-hidden="true"><rect x="0" y="1" width="{cost / top * 100:.1f}" height="8" rx="2"/></svg>'
                 f'<span class="num">${cost:.4f}</span></td><td class="num">{warn or "—"}</td></tr>')
    return ('<section class="room-card"><div class="card-head"><h3>Run history</h3><span class="muted small">Build = made while the system was being built (never counts) · Registered paper run = under the signed rules, from Oct 1, 9:30 AM ET</span></div>'
            '<div class="table-wrap"><table class="mini history"><thead><tr><th>Run</th><th>Category</th><th>Counts toward experiment</th><th>Outcome</th><th>Steps</th><th>Signals</th><th>AI gate</th><th>AI cost</th><th>Warnings</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div></section>')


def options_section(opt):
    if not opt:
        return ('<p class="muted">This run did not record an options screen. Runs from the 2026-09-30 evening release on record how many '
                'contracts pass each filter.</p><p class="muted small">Rules: a call on an underlying with a buy signal, valid bid/ask, '
                'spread within 15% of the midpoint, and one contract (ask × 100) within the lane’s available money.</p>')
    top = max([r['remaining'] or 0 for r in opt['funnel']] + [opt.get('seen') or 0, 1])
    rows = ''
    prev = opt.get('seen') or 0
    for i, r in enumerate(opt['funnel']):
        w = (r['remaining'] or 0) / top * 300
        rows += (f'<g class="bar {"top" if i == len(opt["funnel"]) - 1 else "pos"}"><text class="bar-label" x="172" y="{16 + i * 22}" text-anchor="end">{esc(r["stage"])}</text>'
                 f'<rect x="180" y="{5 + i * 22}" width="{max(w, 1.5):.1f}" height="15" rx="2"/>'
                 f'<text class="bar-value" x="{186 + w:.1f}" y="{16 + i * 22}">{esc(r["remaining"])} left (−{esc(r["removed"])})</text></g>')
        prev = r['remaining']
    chart = (f'<figure class="chart"><figcaption>Option contracts surviving each filter · {esc(opt.get("seen"))} seen → {esc(opt.get("passed"))} passed</figcaption>'
             f'<svg viewBox="0 0 620 {len(opt["funnel"]) * 22 + 8}" role="img" aria-label="Options funnel">{rows}</svg></figure>')
    under = table(('Underlying', 'Contracts', 'Passed', 'Cheapest call (1 contract)', 'Available in lane'),
                  [(u['underlying'], u['contracts'], u['passed'], ('$' + u['cheapest_call_cost']) if u['cheapest_call_cost'] else '—',
                    ('$' + u['available']) if u['available'] else '—') for u in opt['by_underlying']]) if opt['by_underlying'] else ''
    return chart + f'<p class="muted small">Underlyings with a buy signal: {esc(", ".join(opt["bullish"]) or "none")}</p>' + under


def usage_table(review):
    u = review.get('agent_usage') or {}
    stages = {s.get('key'): s for s in review.get('stages', [])}
    names = (('research', 'Blossom · Research'), ('portfolio', 'Mayor · Portfolio'), ('critic', 'Mojo Jojo · Critic'))
    rows = ''
    for key, label in names:
        x = u.get(key)
        if x:
            tools = 'none' if x.get('tools') == [] else ', '.join(x.get('tools') or []) or 'not recorded'
            rows += (f'<tr><td>{esc(label)}</td><td class="code">{esc(x.get("model") or "not recorded")}</td><td>{esc(tools)}</td>'
                     f'<td class="num">{esc(x.get("input_tokens", "—"))}</td><td class="num">{esc(x.get("output_tokens", "—"))}</td><td class="num">${esc(x.get("reserved_usd") or "—")}</td></tr>')
        else:
            rows += f'<tr><td>{esc(label)}</td><td colspan="5" class="muted">{esc("Not called" if stages.get(key, {}).get("status") == "skipped" else "Not recorded")}</td></tr>'
    return ('<div class="table-wrap"><table class="mini"><thead><tr><th>AI step</th><th>Model</th><th>Tools it could call</th><th>Tokens in</th><th>Tokens out</th><th>Cost reserved</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div><p class="muted small">Code steps (Scanners, AI gate, Prof. X, Outcome) use no AI. Scanners call only read-only broker tools, listed under System checks.</p>')


def run_section(review, index):
    c = review.get('checks') or {}
    missing = c.get('missing_evidence') or []
    missing_html = ('<ul class="tight">' + ''.join('<li>' + esc(m) + '</li>' for m in missing) + '</ul>') if missing else '<p class="muted">None recorded.</p>'
    return f'''<section class="scene-review checks-run" data-scene-review="{index}"{" hidden" if index else ""}>
<header class="room-outcome">{category_chips(review)}<div class="meta"><span>{esc(date_label(review.get("timestamp")))}</span><span>Decision date {esc(c.get("decision_date") or "not recorded")}</span><span>{esc(c.get("qualification") or "")}</span></div><h2>{esc(outcome(review))}</h2></header>
<section class="room-card"><div class="card-head"><h3>System checks</h3><span class="muted small">Connection, registration, data, AI and outcome</span></div>{operational(c.get("operational", []))}</section>
<section class="room-card"><div class="card-head"><h3>AI steps · model, tools and tokens</h3></div>{usage_table(review)}</section>
<section class="room-card"><div class="card-head"><h3>Charts</h3><span class="muted small">From this run’s recorded features</span></div>{charts(c)}</section>
<section class="room-card"><div class="card-head"><h3>Options screen (Lane B)</h3><span class="muted small">Why contracts were or weren’t considered</span></div>{options_section(c.get("options"))}</section>
<section class="room-card"><div class="card-head"><h3>Scanners · strategy conditions</h3><span class="muted small">Every ticker × every condition</span></div>{strategy_tables(c.get("strategies", []))}</section>
<section class="room-card"><div class="card-head"><h3>Missing information recorded</h3><span class="muted small">Blossom’s notes when AI ran; otherwise the system’s note</span></div>{missing_html}</section>
<section class="room-card"><div class="card-head"><h3>Prof. X · safety-rule results</h3></div>{risk_table(c.get("risk", []))}</section>
<section class="room-card"><details class="sub"><summary>Raw features for every ticker</summary>{feature_table(c.get("features", []))}</details></section>
</section>'''


def render(state):
    if not state.get('preview'):
        from .components import card
        return '<h1>Checks & charts</h1>' + card('Not available yet', '<p>This screen is part of the Botfolio preview. No results are assumed.</p>')
    reviews = state.get('decision_room', [])
    choices = ''.join(f'<option value="{i}">{esc(category_prefix(r))}{esc(date_label(r.get("timestamp")))} — {esc(outcome(r)[:70])}</option>' for i, r in enumerate(reviews))
    html = ('<div class="room-head"><div><h1>Checks &amp; charts</h1><p>Every check each step ran, with the numbers behind it.</p></div>'
            f'<label>Run <select id="scene-review">{choices}</select></label></div>')
    from .research import render as measurement
    from .components import capital_note
    html += capital_note(state) + measurement(state.get('research'))
    if not reviews:
        return html + '<p>No saved review yet.</p>'
    return html + '<h2 class="section-title">Per-run checks</h2>' + ''.join(run_section(r, i) for i, r in enumerate(reviews))
