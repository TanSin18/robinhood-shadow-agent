"""Portfolio: the real Robinhood Agentic account next to the paper accounts.

Real side: the last VERIFIED account snapshot the tripwire recorded (cash,
position quantities, open-order counts). Paper side: the paper ledger and its
recorded valuations. Nothing is fetched from the broker here; missing is shown
as missing, never as zero.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from .components import deferred, esc

ET = ZoneInfo('America/New_York')
ARMS = {'agent_alone': 'AI alone', 'with_approvals': 'AI + your approval', 'deterministic_no_ai': 'Rules only (no AI)'}
LANES = {'A': 'Lane A · Stocks & ETFs', 'B': 'Lane B · Options'}
START = Decimal('500')


def D(v):
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return None


def money(v):
    v = D(v)
    return '—' if v is None else f'${v:,.2f}'


def when(value):
    try:
        dt = datetime.fromisoformat(value)
        return dt.astimezone(ET).strftime('%a %b %-d, %-I:%M %p ET') if dt.tzinfo else 'time not recorded'
    except (TypeError, ValueError):
        return 'time not recorded'


def real_card(real):
    if not real:
        return ('<section class="room-card pf-real"><div class="card-head"><h3>Real · Robinhood Agentic account</h3></div>'
                '<p class="muted">No verified account snapshot is recorded yet. Missing is not zero.</p></section>')
    orders = real.get('open_orders') or {}
    check = real.get('last_check') or {}
    positions = real.get('positions') or []
    status = (check.get('status') or '').replace('_', ' ').lower()
    return (f'<section class="room-card pf-real"><div class="card-head"><h3>Real · Robinhood Agentic account</h3><span class="pill-real">read-only</span></div>'
            f'<p class="pf-big">{money(real.get("cash"))}<span>cash</span></p>'
            f'<dl class="facts"><div><dt>Positions</dt><dd>{len(positions)}</dd></div>'
            f'<div><dt>Orders on record</dt><dd>{sum(orders.values())} (stocks {orders.get("equity", 0)} · options {orders.get("option", 0)} · crypto {orders.get("crypto", 0)})</dd></div>'
            f'<div><dt>Last checked</dt><dd>{esc(when(check.get("created_at")))} · {esc(status or "not recorded")}</dd></div>'
            f'<div><dt>Snapshot recorded</dt><dd>{esc(when(real.get("as_of")))}</dd></div></dl>'
            + (''.join(f'<p class="small">Position: {esc(p.get("quantity"))} ({esc(p.get("direction"))}), instrument name not stored</p>' for p in positions))
            + '<p class="muted small">Real orders are blocked in Stage 1. The system reads this account every run and stops if it changes '
              'unexpectedly. Only cash, position quantities and order counts are stored: no account numbers, and buying power isn’t recorded.</p></section>')


def latest_values(values):
    out = {}
    for v in values:
        key = (v.get('lane'), v.get('track'))
        if key not in out or str(v.get('timestamp')) > str(out[key].get('timestamp')):
            out[key] = v
    return out


def paper_card(paper, values):
    latest = latest_values(values)
    html = '<section class="room-card pf-paper"><div class="card-head"><h3>Paper · what the agents trade</h3><span class="pill-paper">simulated</span></div>'
    total = Decimal(0)
    for lane in ('A', 'B'):
        arms = [p for p in paper if p['lane'] == lane]
        if not arms:
            continue
        rows = ''
        for p in sorted(arms, key=lambda x: list(ARMS).index(x['track']) if x['track'] in ARMS else 9):
            cash = (D(p.get('settled_cash')) or Decimal(0)) + (D(p.get('unsettled_cash')) or Decimal(0))
            cost = sum(((D(x.get('quantity')) or 0) * (D(x.get('average_cost')) or 0) * (D(x.get('multiplier')) or 1)) for x in p['positions'])
            recorded = latest.get((lane, p['track']))
            value = D(recorded['value']) if recorded and D(recorded.get('value')) is not None else cash + cost
            basis = 'marked ' + when(recorded['timestamp']) if recorded else 'at cost'
            total += value
            start = D(p.get('start')) or START
            change = value - start
            rows += (f'<tr><td>{esc(ARMS.get(p["track"], p["track"]))}</td><td class="num">{money(cash)}</td><td class="num">{len(p["positions"])}</td>'
                     f'<td class="num">{money(value)}</td><td class="num {"pos" if change > 0 else "neg" if change < 0 else ""}">{"+" if change > 0 else ""}{money(change) if change else "$0.00"}</td>'
                     f'<td class="muted small">{esc(basis)}</td></tr>')
        html += (f'<h4>{esc(LANES[lane])}</h4><div class="table-wrap"><table class="mini"><thead><tr><th>Account</th><th>Cash</th><th>Positions</th>'
                 f'<th>Value</th><th>vs start</th><th>Valued</th></tr></thead><tbody>{rows}</tbody></table></div>')
    positions = [(p['lane'], p['track'], x) for p in paper for x in p['positions']]
    if positions:
        html += '<h4>Paper positions</h4><div class="table-wrap"><table class="mini"><thead><tr><th>Ticker</th><th>Account</th><th>Quantity</th><th>Average cost</th></tr></thead><tbody>'
        html += ''.join(f'<tr><td class="code">{esc(x.get("ticker"))}</td><td>{esc(ARMS.get(t, t))} · {lane}</td><td class="num">{esc(x.get("quantity"))}</td><td class="num">{money(x.get("average_cost"))}</td></tr>'
                        for lane, t, x in positions) + '</tbody></table></div>'
    else:
        html += ('<p class="muted">No paper positions yet. Every run so far ended without an entry (holds and one Critic rejection). '
                 'From Thursday the desk rule can buy ETFs such as SOXX in these accounts.</p>')
    starts = sorted({f'lane {p["lane"]} ${D(p.get("start")) or START:,.0f}' for p in paper})
    return html + f'<p class="muted small">Starting capital: {esc(", ".join(starts))}. From Oct 1 (v1.6) lane A trades a $25,000 paper book so fills and costs are realistic. Paper results are not investment returns.</p></section>'


OFFICIAL_FROM = '2026-10-01T13:30:00+00:00'


def value_chart(values, starts=None):
    starts = starts or {}
    official = [v for v in values if str(v.get('timestamp')) >= OFFICIAL_FROM and v.get('data_mode') == 'live_readonly']
    values = official or values
    series = {}
    for v in sorted(values, key=lambda x: str(x.get('timestamp'))):
        if D(v.get('value')) is None:
            continue
        base = starts.get((v.get('lane'), v.get('track'))) or START
        series.setdefault((v.get('lane'), v.get('track')), []).append((str(v['timestamp']), START * D(v['value']) / base))
    if not series:
        return ''
    stamps = sorted({t for pts in series.values() for t, _ in pts})
    vals = [x for pts in series.values() for _, x in pts] + [START]
    lo, hi = min(vals), max(vals)
    pad = max((hi - lo) * Decimal('0.2'), Decimal('5'))
    lo, hi = lo - pad, hi + pad
    W, H, L = 640, 180, 56
    x = lambda t: L + (stamps.index(t) / max(len(stamps) - 1, 1)) * (W - L - 12)
    y = lambda v: 12 + float((hi - v) / (hi - lo)) * (H - 36)
    lines = ''
    for i, ((lane, track), pts) in enumerate(sorted(series.items())):
        d = ' '.join(f'{"M" if j == 0 else "L"}{x(t):.1f} {y(v):.1f}' for j, (t, v) in enumerate(pts))
        lines += f'<path class="pf-line s{i % 5}" d="{d}"><title>{esc(ARMS.get(track, track))} · lane {esc(lane)}</title></path>'
    axis = (f'<line class="axis-zero" x1="{L}" x2="{W - 12}" y1="{y(START):.1f}" y2="{y(START):.1f}"/>'
            f'<text class="bar-label" x="{L - 6}" y="{y(START) + 4:.1f}" text-anchor="end">start</text>'
            f'<text class="bar-value" x="{L}" y="{H - 6}">{esc(when(stamps[0]))}</text>'
            f'<text class="bar-value" x="{W - 12}" y="{H - 6}" text-anchor="end">{esc(when(stamps[-1]))}</text>')
    legend = ''.join(f'<li><i class="lg pf-line-key s{i % 5}"></i>{esc(ARMS.get(t, t))} · {esc(l)}</li>' for i, (l, t) in enumerate(sorted(series)))
    return (f'<section class="room-card"><div class="card-head"><h3>Paper value over time</h3><ul class="legend">{legend}</ul></div>'
            f'<svg class="pf-chart" viewBox="0 0 {W} {H}" role="img" aria-label="Paper account value over time">{axis}{lines}</svg>'
            '<p class="muted small">Scaled to each account’s own start, so lanes of different size compare fairly. Official runs only once they exist. Flat lines mean cash only.</p></section>')


def render(state):
    if not state.get('preview'):
        return deferred('Portfolio', 'U4')
    pf = state.get('portfolio') or {}
    return ('<div class="room-head"><div><h1>Portfolio</h1><p>Your real Robinhood Agentic account next to the paper accounts the agents trade.</p></div></div>'
            f'<div class="pf-split">{real_card(pf.get("real"))}{paper_card(pf.get("paper", []), pf.get("values", []))}</div>'
            + value_chart(pf.get('values', []), {(p['lane'], p['track']): D(p.get('start')) for p in pf.get('paper', []) if D(p.get('start'))})
            + _lanes(state))


def _lanes(state):
    from .lanes import render as lane_map
    return ('<details class="room-card sub pf-lanes"><summary>How the two paper lanes work</summary>'
            + lane_map(state) + '</details>')
