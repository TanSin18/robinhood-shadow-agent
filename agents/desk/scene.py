"""Decision room: record-backed flow graph, agent inspector and run log.

Presentation only; no model or broker calls. Every edge state, label and log
line comes from the projection (agents.decision_room / agents.run_log), which
copies named public fields from the run's trace. Nothing here infers work that
was not recorded. Geometry lives in SVG attributes (strict CSP: no inline
style or script).
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from .components import esc
from .team import TEAM
from .workspace import date_label, outcome, first_sentence

ET = ZoneInfo('America/New_York')
ACTORS = ('evidence', 'research', 'portfolio', 'critic', 'risk', 'final')
ROLES = {'evidence': 'Scanners · market data', 'research': 'Research', 'portfolio': 'Portfolio builder',
         'critic': 'Critic', 'risk': 'Safety rules', 'final': 'Outcome'}
KIND = {'evidence': ('code', 'Code'), 'research': ('ai', 'AI'), 'portfolio': ('ai', 'AI'),
        'critic': ('ai', 'AI'), 'risk': ('code', 'Rules, not AI'), 'final': ('code', 'Recorded outcome')}
LOG_NAMES = {'system': 'System', 'evidence': 'Scanners', 'gate': 'AI gate', 'research': 'Pip',
             'portfolio': 'Maple', 'critic': 'Pickle', 'risk': 'Nugget', 'final': 'Outcome'}
X = {'evidence': 80, 'research': 248, 'portfolio': 416, 'critic': 584, 'risk': 752, 'final': 920}
Y, R, GATE_X = 112, 32, 164
STATE_WORD = {'carried': 'recorded', 'stopped': 'stopped here', 'skipped': 'not run', 'unknown': 'not recorded'}


def handoffs(review, rows):
    """Only explicit, same-run, typed events become handoff edges. No aliases."""
    result = []
    for row in rows:
        if not isinstance(row, dict) or row.get('cycle_id') != review.get('review_id'): continue
        targets = row.get('to_actors')
        if (row.get('from_actor') not in ACTORS or not isinstance(targets, list) or
                not targets or any(t not in ACTORS for t in targets) or
                not isinstance(row.get('message'), str) or not row['message'].strip() or
                not isinstance(row.get('seq'), int) or isinstance(row['seq'], bool)): continue
        try:
            if datetime.fromisoformat(row['created_at']).tzinfo is None: continue
        except (KeyError, TypeError, ValueError): continue
        result.append({k: row[k] for k in ('seq', 'from_actor', 'to_actors', 'message', 'created_at')})
    return sorted(result, key=lambda r: (r['seq'], r['created_at']))


def name(key):
    return 'You' if key == 'final' else TEAM[key][0]


def short_role(key):
    return ROLES[key].split(' · ')[0]


def portrait(key, size=120):
    asset = TEAM[key][2]
    if asset: return f'<img src="/assets/avatars/{asset}" alt="" width="{size}" height="{size}">'
    path = 'M12 3a9 9 0 1 0 9 9M12 7a5 5 0 1 0 5 5M12 12l8-8' if key == 'evidence' else 'M5 12l4 4L19 6'
    return f'<svg class="scene-symbol" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="{path}"/></svg>'


def clock(value):
    try:
        dt = datetime.fromisoformat(value)
        return dt.astimezone(ET).strftime('%-I:%M:%S %p') if dt.tzinfo else '—'
    except (TypeError, ValueError):
        return '—'


def tone(status):
    return status if status in {'completed', 'blocked', 'active', 'not_applicable', 'waiting', 'skipped'} else 'unavailable'


def fallback_flow():
    return {'edges': [{'from': a, 'to': b, 'state': 'unknown', 'label': ''} for a, b in zip(ACTORS, ACTORS[1:])],
            'bypass': None, 'ai_skipped': False}


# ---------------------------------------------------------------- flow graph
def svg_edge(e, i, recorded_pairs):
    a, b = e['from'], e['to']
    x1, x2 = X[a] + R + 4, X[b] - R - 6
    gate_edge = a == 'evidence' and b == 'research'
    seg = f'M{x1} {Y} L{GATE_X - 12} {Y} M{GATE_X + 12} {Y} L{x2} {Y}' if gate_edge else f'M{x1} {Y} L{x2} {Y}'
    state = e['state'] if e['state'] in STATE_WORD else 'unknown'
    data = f' data-edge="{a}-{b}"' if (a, b) in recorded_pairs else ''
    mid = (GATE_X + 12 + x2) / 2 if gate_edge else (x1 + x2) / 2
    text = e.get('label') or ''
    text = text if len(text) <= 17 else text[:16] + '…'
    label = f'<text class="edge-label" x="{mid:.0f}" y="{Y - 14}" text-anchor="middle">{esc(text)}</text>' if text and not gate_edge else ''
    stop = ''
    if state == 'stopped':
        cx = (x1 + x2) / 2
        stop = (f'<g class="edge-stop"><circle cx="{cx:.0f}" cy="{Y}" r="9"/>'
                f'<path d="M{cx - 4:.0f} {Y - 4} L{cx + 4:.0f} {Y + 4} M{cx + 4:.0f} {Y - 4} L{cx - 4:.0f} {Y + 4}"/></g>')
    return (f'<g class="flow-edge edge-{state}" data-flow="{a}-{b}" data-order="{i}"{data}>'
            f'<title>{esc(name(a))} → {esc(name(b))}: {esc(STATE_WORD[state])}{(" · " + esc(e["label"])) if e.get("label") else ""}</title>'
            f'<path class="edge-line" d="{seg}" marker-end="url(#arrow-{state})"/>{label}{stop}</g>')


def svg_node(key, stage, rid):
    st = tone(stage.get('status'))
    label = stage.get('status_label') or 'Not recorded'
    x = X[key]
    asset = TEAM[key][2]
    face = (f'<image href="/assets/avatars/{asset}" x="{x - R + 4}" y="{Y - R + 4}" width="{2 * R - 8}" height="{2 * R - 8}" clip-path="url(#face-{rid})"/>'
            if asset else f'<text class="node-glyph" x="{x}" y="{Y + 8}" text-anchor="middle">{"◎" if key == "evidence" else "✓"}</text>')
    chip_w = max(58, 7 * len(label) + 18)
    return (f'<g class="flow-node st-{st} kind-{KIND[key][0]}" data-actor="{key}" tabindex="0" role="button" '
            f'aria-label="{esc(name(key))}, {esc(short_role(key))}: {esc(label)}">'
            f'<circle class="node-halo" cx="{x}" cy="{Y}" r="{R + 7}"/><circle class="node-ring" cx="{x}" cy="{Y}" r="{R}"/>{face}'
            f'<text class="node-name" x="{x}" y="{Y + R + 22}" text-anchor="middle">{esc(name(key))}</text>'
            f'<text class="node-role" x="{x}" y="{Y + R + 37}" text-anchor="middle">{esc(short_role(key))}</text>'
            f'<rect class="node-chip" x="{x - chip_w / 2:.0f}" y="{Y + R + 45}" width="{chip_w}" height="18" rx="9"/>'
            f'<text class="node-chip-text" x="{x}" y="{Y + R + 58}" text-anchor="middle">{esc(label)}</text></g>')


def svg_gate(gate):
    diamond = f'<path d="M{GATE_X} {Y - 11} L{GATE_X + 11} {Y} L{GATE_X} {Y + 11} L{GATE_X - 11} {Y} Z"/>'
    if not gate:
        return f'<g class="flow-gate gate-unknown"><title>AI gate: not recorded for this run</title>{diamond}</g>'
    state = 'open' if gate['open'] else 'closed'
    return (f'<g class="flow-gate gate-{state}"><title>AI gate {state}: {esc(gate.get("reason") or "reason not recorded")}</title>{diamond}'
            f'<text class="gate-label" x="{GATE_X}" y="{Y + 30}" text-anchor="middle">AI gate</text>'
            f'<text class="gate-state" x="{GATE_X}" y="{Y + 43}" text-anchor="middle">{state}</text>'
            + (f'<text class="gate-label" x="{GATE_X}" y="{Y - 18}" text-anchor="middle">for {esc(", ".join(gate["candidates"]))}</text>' if gate['open'] and gate.get('candidates') else '')
            + '</g>')


def svg_bypass(bypass):
    if not bypass: return ''
    x1, x2 = GATE_X, X['final']
    return (f'<g class="flow-edge edge-carried edge-bypass" data-flow="evidence-final" data-order="bypass">'
            f'<title>Recorded path: {esc(bypass["label"])}</title>'
            f'<path class="edge-line" d="M{x1} {Y - 12} C{x1 + 40} 14 {x2 - 60} 14 {x2 - 10} {Y - R - 4}" marker-end="url(#arrow-carried)"/>'
            f'<text class="edge-label bypass-label" x="{(x1 + x2) / 2:.0f}" y="24" text-anchor="middle">{esc(bypass["label"])}</text></g>')


def flow_graph(review, rid, stages, flow, recorded_pairs):
    markers = ''.join(f'<marker id="arrow-{s}" class="arrow-{s}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z"/></marker>' for s in STATE_WORD)
    defs = f'<defs>{markers}<clipPath id="face-{rid}" clipPathUnits="objectBoundingBox"><circle cx=".5" cy=".5" r=".5"/></clipPath></defs>'
    edges = ''.join(svg_edge(e, i, recorded_pairs) for i, e in enumerate(flow['edges']))
    nodes = ''.join(svg_node(k, stages.get(k, {'key': k}), rid) for k in ACTORS)
    box = '0 0 1000 220' if flow.get('bypass') else '0 58 1000 162'
    return (f'<svg class="flow-svg" viewBox="{box}" role="group" aria-label="Recorded flow of this run">{defs}'
            f'{svg_bypass(flow.get("bypass"))}{edges}{svg_gate(review.get("ai_gate"))}{nodes}</svg>')


def flow_list(stages, flow):
    """Narrow-screen equivalent of the graph: same data, vertical."""
    by_from = {e['from']: e for e in flow['edges']}
    out = '<ol class="flow-list">'
    for key in ACTORS:
        stage = stages.get(key, {})
        out += (f'<li><button type="button" class="flow-item st-{tone(stage.get("status"))}" data-actor="{key}">'
                f'<span class="fi-face">{portrait(key, 28)}</span><span class="fi-name">{esc(name(key))}</span>'
                f'<span class="fi-role">{esc(short_role(key))}</span><span class="fi-chip">{esc(stage.get("status_label") or "Not recorded")}</span></button>')
        e = by_from.get(key)
        if e: out += f'<span class="fi-edge edge-{e["state"]}">{esc(e.get("label") or STATE_WORD.get(e["state"], ""))}</span>'
        out += '</li>'
    return out + '</ol>'


# ------------------------------------------------------------- inspector
def chips(values):
    values = [str(v) for v in values if isinstance(v, str)]
    return '<div class="chip-row">' + ''.join(f'<span class="chip">{esc(v)}</span>' for v in values) + '</div>' if values else ''


def bullet(values, missing):
    values = [v for v in (values or []) if isinstance(v, str)]
    return '<ul class="tight">' + ''.join(f'<li>{esc(v)}</li>' for v in values) + '</ul>' if values else f'<p class="muted">{esc(missing)}</p>'


def facts(pairs):
    rows = ''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in pairs if v not in (None, '', []))
    return f'<dl class="facts">{rows}</dl>' if rows else ''


def table(head, rows):
    return ('<div class="table-wrap"><table class="mini"><thead><tr>' + ''.join(f'<th>{esc(h)}</th>' for h in head) +
            '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{esc(c)}</td>' for c in row) + '</tr>' for row in rows) + '</tbody></table></div>')


def tools_block(key, stage, review):
    """What this step used: broker tools, code, or AI model — from recorded fields only."""
    d = stage.get('details') if isinstance(stage.get('details'), dict) else {}
    u = (review.get('agent_usage') or {}).get(key)
    rows = []
    if key == 'evidence':
        rows = [('Kind', 'Code, no AI'), ('Broker tools called (read-only)', ', '.join(d.get('read_tools') or []) or 'Not recorded'),
                ('Rules applied', 'research/strategy_signals.py · momentum rotation, mean reversion'),
                ('Hands to', 'AI gate → Pip when a signal needs judgment; otherwise straight to the outcome')]
    elif key in ('research', 'portfolio', 'critic'):
        if u:
            tools = u.get('tools')
            rows = [('Kind', 'AI'), ('Model', u.get('model') or 'Not recorded'),
                    ('Tools it could call', 'None — works only from the supplied record' if tools == [] else ', '.join(tools) if tools else 'Not recorded'),
                    ('Handoffs it could make', 'None — the runner passes its output on' if u.get('handoffs') == [] else ', '.join(u.get('handoffs') or []) or 'Not recorded'),
                    ('Output format', u.get('output_type') or 'Not recorded'),
                    ('Tokens in → out', f"{u.get('input_tokens', '?')} → {u.get('output_tokens', '?')}"),
                    ('Attempts · cost reserved', f"{u.get('attempts', 0)} · ${u.get('reserved_usd') or '?'}"),
                    ('Matched by', 'recorded row order between this step’s start and finish')]
        else:
            rows = [('Kind', 'AI'), ('Model and tools', 'Not called in this run' if stage.get('status') == 'skipped' else 'Not recorded')]
    elif key == 'risk':
        rows = [('Kind', 'Deterministic rules, no AI'), ('Broker tools', 'Quote refresh only (read-only) before checking'),
                ('Checks', 'size, cash, stale prices, loss and drawdown limits'), ('Real execution', d.get('real_execution') or 'blocked')]
    elif key == 'final':
        rows = [('Kind', 'Recorder, no AI'), ('Writes', 'Local run record and, if a trade passed, a paper approval card'),
                ('Broker writes', 'None — real orders are blocked')]
    return '<h4>Tools &amp; model</h4>' + facts(rows)


def work(key, stage, review):
    d = stage.get('details') if isinstance(stage.get('details'), dict) else {}
    news = [r for r in d.get('news', []) if isinstance(r, dict) and isinstance(r.get('fact'), str)] if isinstance(d.get('news'), list) else []
    html = ''
    if key == 'evidence':
        signals = [str(s.get('instrument')) for s in d.get('signals', []) if isinstance(s, dict) and s.get('instrument')]
        html += facts([('Quotes', d.get('quote_count')), ('Volatility series', d.get('volatility_count')),
                       ('Price histories', len(d.get('history_counts') or {}) or None)])
        html += '<h4>Signals that qualified</h4>' + (chips(signals) or '<p class="muted">None recorded.</p>')
        checks = review.get('checks') or {}
        if checks.get('strategies'):
            summary = '; '.join(f"{s['title']}: {s['signals']} signal" + ('' if s['signals'] == 1 else 's')
                                + (f", {s['mismatches']} mismatch" if s['mismatches'] else '') for s in checks['strategies'])
            html += f'<h4>Strategy conditions</h4><p>{esc(summary)}. <a href="/checks">Every ticker × condition →</a></p>'
        else:
            blocked = review.get('strategy_blocked') or []
            if blocked:
                html += (f'<details class="sub"><summary>Why the rest did not qualify · {len(blocked)}</summary>'
                         + table(('Instrument', 'Strategy', 'Reason'), [(r['instrument'], r['strategy'], r['reason']) for r in blocked]) + '</details>')
        g = review.get('ai_gate')
        if g:
            html += ('<h4>AI gate</h4><p>' + esc(('Opened for ' + (', '.join(g['candidates']) or 'candidates')) if g['open'] else 'Stayed closed — no AI was called')
                     + f' <span class="code">{esc(g.get("reason") or "")}</span></p>')
        html += '<h4>Read-only tools used</h4>' + (chips(d.get('read_tools') or []) or '<p class="muted">Not recorded.</p>')
    elif key == 'research':
        html += '<h4>Compared</h4>' + (chips(d.get('compared_symbols') or []) or '<p class="muted">Not recorded.</p>')
        html += facts([('News checked', 'Yes' if d.get('news_checked') is True else 'No' if d.get('news_checked') is False else None)])
        html += '<h4>Missing information it listed</h4>' + bullet(d.get('missing_evidence'), 'None saved.')
        if news:
            html += f'<h4>Recorded facts</h4><p class="muted small">{len(news)} recorded fact(s) below. Classification and freshness are not assessed.</p>' + ''.join(
                '<article class="recorded-fact"><p>' + esc(r['fact']) + '</p><dl><dt>Source</dt><dd>' + esc(r.get('source_url') or 'Not recorded')
                + '</dd><dt>Observed</dt><dd>' + esc(r.get('observed_at') or 'Not recorded') + '</dd></dl><small>Evidence classification not recorded · freshness not assessed</small></article>' for r in news)
        else:
            html += '<p class="muted">Structured supporting facts were not saved.</p>'
    elif key == 'portfolio':
        picks = [p for p in d.get('picks', []) if isinstance(p, dict)]
        if picks:
            html += '<h4>Proposal</h4>' + table(('Instrument', 'Lane', 'Qty', 'Limit', 'Max loss', 'Confidence'),
                [tuple('—' if p.get(f) is None else p.get(f) for f in ('instrument', 'lane', 'quantity', 'limit_price', 'max_loss_usd', 'confidence')) for p in picks])
            for p in picks:
                html += facts([('Good if', p.get('good_if')), ('Wrong if', p.get('invalidation')), ('Thesis', p.get('thesis'))])
        else:
            html += '<p class="muted">No proposal recorded.</p>'
        html += '<h4>Why</h4><p>' + esc(d.get('reason') or 'Not saved.') + '</p>'
    elif key == 'critic':
        html += '<h4>Rejected</h4>' + (chips(d.get('rejected_instruments') or []) or '<p class="muted">Nothing rejected.</p>')
        html += '<h4>Counterargument</h4><p>' + esc(d.get('counterargument') or 'Not saved.') + '</p>'
    else:
        results = [r for r in d.get('results', []) if isinstance(r, dict)]
        ops = (review.get('checks') or {}).get('operational') or []
        if key == 'final' and ops:
            bad = [o for o in ops if o['status'] in {'warn', 'fail'}]
            html += (f'<h4>System checks</h4><p>{sum(o["status"] == "pass" for o in ops)} passed, {len(bad)} need attention'
                     + (': ' + esc('; '.join(o['check'] + ' ' + o['value'] for o in bad)) if bad else '') + '. <a href="/checks">Details →</a></p>')
        if key == 'final':
            html += facts([('Decision', review.get('decision_type')), ('Reason', review.get('decision_reason') or d.get('reason')),
                           ('AI cost estimate', ('$' + str(d['api_cost_estimate_usd'])) if d.get('api_cost_estimate_usd') else None)])
        else:
            html += facts([('Real execution', d.get('real_execution')), ('Proposals checked', d.get('proposal_count'))])
        if results:
            html += '<h4>Results</h4>' + table(('Instrument', 'Status', 'Reasons'),
                [(r.get('instrument') or '—', r.get('status') or '—', '; '.join(r.get('reasons') or []) or r.get('reason') or '') for r in results])
    return html or '<p class="muted">No structured work was saved for this step.</p>'


def connection(key, review, flow):
    """Mini graph: upstream → this agent → downstream, with the recorded edge states."""
    edges = {(e['from'], e['to']): e for e in flow['edges']}
    i = ACTORS.index(key)
    up = edges.get((ACTORS[i - 1], key)) if i else None
    down = edges.get((key, ACTORS[i + 1])) if i < len(ACTORS) - 1 else None
    bypass = flow.get('bypass')
    if bypass and key == 'evidence': down = {'from': 'evidence', 'to': 'final', 'state': 'carried', 'label': bypass['label']}
    if bypass and key == 'final': up = {'from': 'evidence', 'to': 'final', 'state': 'carried', 'label': bypass['label']}
    src = name(up['from']) if up else 'Read-only market data'
    dst = name(down['to']) if down else ('Your approval inbox' if (review.get('outcome') or {}).get('pending_count') else 'Run record')
    stages = {s.get('key'): s for s in review.get('stages', [])}
    ran = lambda k: stages.get(k, {}).get('status') in {'completed', 'blocked'}
    up_state = up['state'] if up else ('carried' if ran('evidence') else 'unknown')
    down_state = down['state'] if down else ('carried' if ran('final') else 'unknown')

    def box(x, text, cls):
        return (f'<rect class="cx-box {cls}" x="{x}" y="14" width="150" height="36" rx="9"/>'
                f'<text class="cx-text" x="{x + 75}" y="37" text-anchor="middle">{esc(text)}</text>')

    def arrow(x1, x2, state, label):
        return (f'<g class="flow-edge edge-{state}"><path class="edge-line" d="M{x1} 32 L{x2} 32" marker-end="url(#arrow-{state})"/>'
                f'<text class="edge-label" x="{(x1 + x2) / 2:.0f}" y="68" text-anchor="middle">{esc(label or STATE_WORD.get(state, ""))}</text></g>')
    return (f'<svg class="cx-svg" viewBox="0 0 640 76" role="img" aria-label="{esc(src)} to {esc(name(key))} to {esc(dst)}">'
            f'{box(0, src, "cx-side")}{arrow(154, 240, up_state, (up or {}).get("label"))}'
            f'{box(245, name(key) + " · " + short_role(key), "cx-self")}'
            f'{arrow(399, 485, down_state, (down or {}).get("label"))}{box(490, dst, "cx-side")}</svg>')


def log_rows(entries, show_actor=True):
    if not entries: return '<p class="muted">No log lines were recorded for this step.</p>'
    out = '<ol class="log">'
    for e in entries:
        actor = str(e.get('actor'))
        detail = ''.join(f'<li>{esc(d)}</li>' for d in e.get('detail', []))
        who = f'<span class="log-actor a-{esc(actor)}">{esc(LOG_NAMES.get(actor, actor))}</span>' if show_actor else ''
        out += (f'<li class="log-row tone-{esc(e.get("tone", "info"))}" data-log-actor="{esc(actor)}" data-log-seq="{esc(e.get("seq"))}">'
                f'<button type="button" class="log-hit" data-log-select="{esc(actor)}"><time>{esc(clock(e.get("time")))}</time>'
                f'<span class="log-offset">{esc(e.get("offset", ""))}</span>{who}<strong class="log-title">{esc(e["title"])}</strong></button>'
                + (f'<ul class="log-detail">{detail}</ul>' if detail else '') + '</li>')
    return out + '</ol>'


def inspector(key, stage, review, flow, rid, log, selected):
    kind, kind_label = KIND[key]
    times = (review.get('stage_times') or {}).get(key, {})
    span = (f'{clock(times["start"])} → {clock(times.get("end"))}' + (f' · {times["seconds"]}s' if 'seconds' in times else '')) if times.get('start') else ''
    panel = f'inspect-{rid}-{key}'
    tabs = (('work', 'Work'), ('report', 'Original report'))
    tablist = ''.join(f'<button type="button" role="tab" id="{panel}-{t}-tab" aria-controls="{panel}-{t}" aria-selected="{str(t == "work").lower()}" data-character-tab="{t}">{esc(label)}</button>' for t, label in tabs)
    report = f'<details class="original-report" open><summary>Original report</summary><p class="report">{esc(stage.get("summary") or "No report was saved.")}</p></details>'
    later = ('<p class="muted small later-note">Coming after the Phase 0 gate: ask Bubbles about this work, and tune it via side tests '
             '(read-only until then — editable after Phase 0 via side test; safety rules stay locked).</p>')
    panes = {'work': tools_block(key, stage, review) + work(key, stage, review) + later, 'report': report}
    content = ''.join(f'<section role="tabpanel" id="{panel}-{t}" aria-labelledby="{panel}-{t}-tab" data-character-pane="{t}"{"" if t == "work" else " hidden"}>{panes[t]}</section>' for t, _ in tabs)
    chip = esc(stage.get('status_label') or 'Not recorded')
    span_html = f'<span class="span">{esc(span)}</span>' if span else ''
    return (f'<article class="inspector scene-character" id="{panel}" data-inspect="{key}"{"" if key == selected else " hidden"}>'
            f'<header class="insp-head"><span class="insp-face kind-{kind}">{portrait(key, 44)}</span><div><h3>{esc(name(key))} <small>{esc(ROLES[key])}</small></h3>'
            f'<p class="insp-meta"><span class="kind-label kind-{kind}">{esc(kind_label)}</span><span class="status-chip st-{tone(stage.get("status"))}">{chip}</span>{span_html}</p></div></header>'
            f'<a class="insp-link" href="/checks">All checks &amp; charts →</a><div class="insp-connect"><h4>Connections in this run</h4>{connection(key, review, flow)}</div>'
            f'<div role="tablist" aria-label="{esc(name(key))} details">{tablist}</div>{content}</article>')


# ------------------------------------------------------------- page
def ideas(review):
    rows = []
    for lane, candidates in (review.get('lanes') or {}).items():
        for c in candidates:
            state = str(c.get('state', 'Not recorded'))
            if state == 'proposed' and c.get('instrument') in (review.get('stopped_instruments') or []):
                state = 'proposed → rejected by Critic'
            elif state == 'advanced':
                state = 'qualified signal, not picked'
            rows.append((c.get('instrument', '—'), 'Stocks & ETFs' if lane == 'A' else 'Options', state, c.get('reason', 'Reason not saved')))
    body = table(('Idea', 'Lane', 'Where it ended', 'Reason'), rows) if rows else '<p class="muted">Individual selection details were not saved.</p>'
    return f'<section class="room-card ideas scene-ideas"><div class="card-head"><h3>Investment ideas</h3><span class="muted small">{len(rows)} recorded</span></div>{body}</section>'


def scene(review, index, rows):
    recorded = handoffs(review, rows)
    pairs = {(e['from_actor'], t) for e in recorded for t in e['to_actors']}
    stages = {s['key']: s for s in review.get('stages', []) if s.get('key') in ACTORS}
    flow = review.get('flow') or fallback_flow()
    log = list(review.get('log') or [])
    for n, h in enumerate(recorded):
        log.append({'seq': 1000 + n, 'actor': h['from_actor'], 'event': 'handoff', 'time': h['created_at'], 'offset': '',
                    'title': 'Handoff: ' + name(h['from_actor']) + ' → ' + ', '.join(name(t) for t in h['to_actors']),
                    'detail': [h['message']], 'tone': 'info'})
    selected = 'critic' if review.get('stopped_by') == 'critic' else review.get('default_stage') if review.get('default_stage') in ACTORS else 'final'
    head = review.get('header') or {}
    reason = ''
    if review.get('proposal_state') == 'stopped' and review.get('critic_reason'):
        reason = TEAM['critic'][0] + '’s reason: “' + first_sentence(review['critic_reason']) + '”'
    elif review.get('decision_reason'):
        reason = review['decision_reason']
    g = review.get('ai_gate')
    duration = head.get('duration')
    meta = [date_label(review.get('timestamp')), head.get('data_mode'),
            ('Took ' + duration) if duration and duration != 'Not recorded' else None,
            (f"{head.get('completed_stages')}/{head.get('expected_stages')} stages recorded" if head.get('expected_stages') else None),
            ('AI gate ' + ('open' if g['open'] else 'closed')) if g else None,
            ('AI cost $' + str(head['api_cost_estimate_usd'])) if head.get('api_cost_estimate_usd') else None]
    meta_html = ''.join(f'<span>{esc(m)}</span>' for m in meta if m)
    mode = ('Recorded handoffs · replay, not live' if recorded else
            'Arrows follow the recorded order of stage events in this run’s trace. Labels quote saved outputs.' if review.get('flow') else
            'Expected workflow · this record predates the run log')
    legend = ('<ul class="legend"><li><i class="lg lg-carried"></i>recorded</li><li><i class="lg lg-stopped"></i>stopped here</li>'
              '<li><i class="lg lg-skipped"></i>not run</li><li><i class="lg lg-unknown"></i>not recorded</li></ul>')
    off = '' if log else ' disabled'
    player = (f'<div class="scene-player"><button type="button" data-replay="play"{off}>Replay run</button>'
              f'<button type="button" data-replay="previous"{off}>Previous</button><button type="button" data-replay="next"{off}>Next</button>'
              f'<span class="now-playing" data-step-label aria-live="polite">{"Replay steps through " + str(len(log)) + " recorded events in order" if log else "Playback unavailable — no run log was recorded"}</span></div>')
    inspectors = ''.join(inspector(k, stages.get(k, {'key': k}), review, flow, index, log, selected) for k in ACTORS)
    present = [a for a in LOG_NAMES if any(e['actor'] == a for e in log)]
    filters = ('<div class="log-filters" role="group" aria-label="Filter run log"><button type="button" data-log-filter="all" aria-pressed="true">All</button>'
               + ''.join(f'<button type="button" data-log-filter="{a}" aria-pressed="false">{esc(LOG_NAMES[a])}</button>' for a in present) + '</div>') if log else ''
    no_handoff = '' if recorded else '<p class="muted small">No recorded handoff messages for this run. Every recorded event is listed below.</p>'
    tech = ' → '.join(str(e.get('event', '')) for e in review.get('technical_events', [])) or 'Not recorded'
    return f'''<section class="scene-review" data-scene-review="{index}" data-selected="{selected}"{" hidden" if index else ""}>
<header class="room-outcome"><div class="meta">{meta_html}</div><h2>{esc(outcome(review))}</h2>{f"<p>{esc(reason)}</p>" if reason else ""}</header>
<section class="room-card flow-card scene-stage" data-scene><div class="card-head"><h3>How this run flowed</h3>{legend}</div>
<p class="scene-mode">{esc(mode)}</p><div class="scene-map">{flow_graph(review, index, stages, flow, pairs)}</div>{flow_list(stages, flow)}{player}</section>
<div class="room-split"><section class="room-card inspect-card"><div class="card-head"><h3>Selected step</h3><span class="muted small">Click a node or a log line</span></div>{inspectors}</section>
<section class="room-card log-card"><div class="card-head"><h3>Run log</h3><span class="muted small">{len(log)} recorded events · times ET</span></div>{no_handoff}{filters}<div class="log-scroll">{log_rows(log)}</div>
<details class="sub"><summary>Technical event names</summary><p class="code">{esc(tech)}</p></details></section></div>
{ideas(review)}
<aside class="scene-bench" aria-label="Future team members"><span>On the bench</span><div>{portrait('filings_news', 28)}<p><strong>Biscuit</strong> <small>joins in Phase 1</small></p></div><div>{portrait('explainer', 28)}<p><strong>Bubbles</strong> <small>Ask arrives after the gate</small></p></div></aside>
</section>'''


def render(state):
    reviews = state.get('decision_room', [])
    choices = ''.join(f'<option value="{i}">{esc(date_label(r.get("timestamp")))} — {esc(outcome(r)[:70])}</option>' for i, r in enumerate(reviews))
    html = ('<div class="scene-heading room-head"><div><h1>Decision room</h1><p>Every step of a run, straight from its saved records.</p></div>'
            f'<label>Run <select id="scene-review">{choices}</select></label></div>')
    if not reviews: return html + '<p>No saved review yet.</p>'
    return html + ''.join(scene(r, i, state.get('handoffs', [])) for i, r in enumerate(reviews))
