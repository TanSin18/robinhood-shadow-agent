"""Small server-rendered SVG charts (no inline style or script; colour comes from CSS classes).

Every chart is complete without JavaScript. Range buttons ("1W", "1M", ...) are progressive
enhancement: /assets/agent-v10.js shows one range at a time; without it all ranges are listed.
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
RANGES = (('1D', 1), ('1W', 7), ('1M', 31), ('3M', 92), ('6M', 183), ('1Y', 366), ('ALL', None))


def esc(value):
    return escape(str(value), quote=True)


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _dt(v):
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=ET)


def money(v, sign=False):
    v = _f(v)
    if v is None:
        return '—'
    s = f'${abs(v):,.2f}'
    if sign:
        return ('+' if v > 0 else '−' if v < 0 else '') + s
    return ('−' if v < 0 else '') + s


def pct(v, sign=True, digits=2):
    v = _f(v)
    if v is None:
        return '—'
    return (('+' if v > 0 else '−' if v < 0 else '') if sign else ('−' if v < 0 else '')) + f'{abs(v):.{digits}f}%'


def short_time(d, with_time=True):
    d = _dt(d)
    if d is None:
        return 'time not recorded'
    d = d.astimezone(ET)
    return d.strftime('%b %-d, %-I:%M %p ET') if with_time else d.strftime('%b %-d, %Y')


def line_chart(points, *, label, width=720, height=240, baseline=None, baseline_label='start', markers=(),
               hlines=(), overlays=(), tone=None, show_dates=True, money_axis=True):
    """points: [(datetime, value)] sorted. markers: [(datetime, value, text, cls)]. hlines: [(value, text, cls)].
    overlays: [(points, cls, text)] drawn under the main line."""
    pts = [(d, v) for d, v in ((_dt(a), _f(b)) for a, b in points) if d is not None and v is not None]
    if not pts:
        return f'<p class="v10-empty">No recorded values for {esc(label)} in this range. Missing is not zero.</p>'
    pts.sort(key=lambda p: p[0])
    ov = [([(d, v) for d, v in ((_dt(a), _f(b)) for a, b in o_pts) if d is not None and v is not None], cls, text)
          for o_pts, cls, text in overlays]
    t0, t1 = pts[0][0], pts[-1][0]
    for d, *_ in markers:
        d = _dt(d)
        if d is not None:
            t0, t1 = min(t0, d), max(t1, d)
    span = (t1 - t0).total_seconds() or 1.0
    vals = [v for _, v in pts] + [v for o in ov for _, v in o[0] if t0 <= _ <= t1]
    vals += [_f(m[1]) for m in markers if _f(m[1]) is not None] + [_f(h[0]) for h in hlines if _f(h[0]) is not None]
    if baseline is not None:
        vals.append(float(baseline))
    lo, hi = min(vals), max(vals)
    pad = max((hi - lo) * 0.12, abs(hi) * 0.0015, 0.5)
    lo, hi = lo - pad, hi + pad
    L, R, T, B = 10, 10, 20, 26          # labels sit inside the plot, so the line runs edge to edge
    X = lambda d: L + ((d - t0).total_seconds() / span) * (width - L - R) if len(pts) > 1 or markers else (L + width - R) / 2
    Y = lambda v: T + (hi - v) / (hi - lo) * (height - T - B)
    if tone is None:
        ref = baseline if baseline is not None else pts[0][1]
        tone = 'up' if pts[-1][1] > ref + 1e-9 else 'down' if pts[-1][1] < ref - 1e-9 else 'flat'
    gid = 'g' + hashlib.sha256(f'{label}|{width}|{len(pts)}|{pts[0][0]}|{pts[-1][0]}'.encode()).hexdigest()[:10]
    parts = [f'<svg class="v10-chart tone-{tone}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(label)}">'
             f'<defs><linearGradient id="{gid}" x1="0" x2="0" y1="0" y2="1"><stop class="g0" offset="0"/><stop class="g1" offset="1"/></linearGradient></defs>']
    for frac in (0, .5, 1):   # y grid, value written just above its line
        v = hi - frac * (hi - lo)
        y = Y(v)
        parts.append(f'<line class="grid" x1="{L}" x2="{width - R}" y1="{y:.1f}" y2="{y:.1f}"/>'
                     f'<text class="axis" x="{L + 2}" y="{y - 5:.1f}">{esc(money(v) if money_axis else f"{v:,.2f}")}</text>')
    if baseline is not None:
        y = Y(float(baseline))
        parts.append(f'<line class="base" x1="{L}" x2="{width - R}" y1="{y:.1f}" y2="{y:.1f}"/>'
                     f'<text class="axis base-label" x="{width - R - 2}" y="{y - 5:.1f}" text-anchor="end">{esc(baseline_label)}</text>')
    for value, text, cls in hlines:
        v = _f(value)
        if v is None:
            continue
        y = Y(v)
        parts.append(f'<g class="hline {esc(cls)}"><line x1="{L}" x2="{width - R}" y1="{y:.1f}" y2="{y:.1f}"/>'
                     f'<text class="axis" x="{width / 2:.0f}" y="{y - 5:.1f}" text-anchor="middle">{esc(text)}</text></g>')
    for o_pts, cls, text in ov:
        o_pts = [(d, v) for d, v in o_pts if t0 <= d <= t1]
        if len(o_pts) > 1:
            d = ' '.join(f'{"M" if i == 0 else "L"}{X(a):.1f} {Y(b):.1f}' for i, (a, b) in enumerate(o_pts))
            parts.append(f'<path class="overlay {esc(cls)}" d="{d}"><title>{esc(text)}</title></path>')
    if len(pts) > 1:
        d = ' '.join(f'{"M" if i == 0 else "L"}{X(a):.1f} {Y(b):.1f}' for i, (a, b) in enumerate(pts))
        area = d + f' L{X(pts[-1][0]):.1f} {height - B} L{X(pts[0][0]):.1f} {height - B} Z'
        parts.append(f'<path class="area" fill="url(#{gid})" d="{area}"/><path class="line" d="{d}"/>')
    step = max(1, len(pts) // 60)
    sparse = len(pts) <= 12
    for i, (a, b) in enumerate(pts):
        last = i == len(pts) - 1
        if i % step == 0 or last:
            cls = 'pt' + (' solo' if len(pts) == 1 else '') + (' last' if last else '') + ('' if sparse or last else ' quiet')
            parts.append(f'<circle class="{cls}" cx="{X(a):.1f}" cy="{Y(b):.1f}" r="{4 if last else 3}">'
                         f'<title>{esc(short_time(a, show_dates != "date"))}: {esc(money(b) if money_axis else f"{b:,.2f}")}</title></circle>')
    for d, v, text, cls in markers:
        d, v = _dt(d), _f(v)
        if d is None or v is None:
            continue
        x, y = X(d), Y(v)
        anchor = 'end' if x > width * .7 else 'start'
        dx = -9 if anchor == 'end' else 9
        parts.append(f'<g class="marker {esc(cls)}"><circle cx="{x:.1f}" cy="{y:.1f}" r="5"/>'
                     f'<text x="{x + dx:.1f}" y="{y + 16:.1f}" text-anchor="{anchor}">{esc(text)}</text>'
                     f'<title>{esc(text)} · {esc(short_time(d))}</title></g>')
    if show_dates:
        fmt = (lambda d: short_time(d, False)) if show_dates == 'date' else short_time
        parts.append(f'<text class="axis date" x="{L + 2}" y="{height - 8}">{esc(fmt(t0))}</text>'
                     f'<text class="axis date" x="{width - R - 2}" y="{height - 8}" text-anchor="end">{esc(fmt(t1))}</text>')
    parts.append('</svg>')
    return ''.join(parts)


def ranged(points, *, label, now=None, ranges=RANGES, default=None, **kw):
    """Same chart over several look-back windows; the range bar switches between them."""
    pts = [(d, v) for d, v in ((_dt(a), _f(b)) for a, b in points) if d is not None and v is not None]
    pts.sort(key=lambda p: p[0])
    now = _dt(now) or (pts[-1][0] if pts else datetime.now(timezone.utc))
    markers = kw.pop('markers', ())
    overlays = kw.pop('overlays', ())
    buttons, panels, chosen = [], [], None
    for name, days in ranges:
        start = None if days is None else now - timedelta(days=days)
        sub = [p for p in pts if start is None or p[0] >= start]
        if days is not None and len(sub) < 1:
            continue
        # keep the last value before the window so the line starts at the window's left edge
        before = [p for p in pts if start is not None and p[0] < start]
        if before and sub:
            sub = [(start, before[-1][1])] + sub
        if chosen is None and default is None and len(sub) >= 2:
            chosen = name
        mk = [m for m in markers if start is None or (_dt(m[0]) and _dt(m[0]) >= start)]
        ovs = [([p for p in o if start is None or (_dt(p[0]) and _dt(p[0]) >= start)], c, t) for o, c, t in overlays]
        panels.append((name, line_chart(sub, label=f'{label} · {name}', markers=mk, overlays=ovs, **kw), len(sub)))
        buttons.append(name)
    if not panels:
        return line_chart([], label=label)
    chosen = default if default in buttons else (chosen or buttons[-1])
    bar = ''.join(f'<button type="button" class="v10-range" data-range="{n}" aria-pressed="{"true" if n == chosen else "false"}">{n}</button>'
                  for n in buttons)
    body = ''.join(f'<div class="v10-range-panel" data-range-panel="{n}"{" data-active" if n == chosen else ""}>'
                   f'<p class="v10-range-name">{esc(n)} · {c} point{"s" if c != 1 else ""}</p>{svg}</div>' for n, svg, c in panels)
    return f'<div class="v10-ranged"><div class="v10-range-bar" role="group" aria-label="Time range">{bar}</div>{body}</div>'


def donut(slices, *, label, size=180, center=None):
    """slices: [(text, value, cls)]; values >= 0."""
    data = [(t, _f(v) or 0.0, c) for t, v, c in slices if (_f(v) or 0) > 0]
    total = sum(v for _, v, _ in data)
    if total <= 0:
        return f'<p class="v10-empty">Nothing to show for {esc(label)}.</p>'
    r, cx, cy, w = size / 2 - 12, size / 2, size / 2, 12
    parts = [f'<svg class="v10-donut" viewBox="0 0 {size} {size}" role="img" aria-label="{esc(label)}">'
             f'<circle class="track" cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke-width="{w}"/>']
    a0 = -math.pi / 2
    gap = 0.035 if len(data) > 1 else 0          # a hair of space between slices
    for text, v, cls in data:
        frac = v / total
        if frac >= .9999:
            parts.append(f'<circle class="slice {esc(cls)}" cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke-width="{w}"><title>{esc(text)}: 100%</title></circle>')
            continue
        a1 = a0 + frac * 2 * math.pi
        b0, b1 = a0 + gap / 2, max(a0 + gap / 2 + 0.001, a1 - gap / 2)
        large = 1 if (b1 - b0) > math.pi else 0
        x0, y0, x1, y1 = cx + r * math.cos(b0), cy + r * math.sin(b0), cx + r * math.cos(b1), cy + r * math.sin(b1)
        parts.append(f'<path class="slice {esc(cls)}" d="M{x0:.2f} {y0:.2f} A{r} {r} 0 {large} 1 {x1:.2f} {y1:.2f}" fill="none" stroke-width="{w}">'
                     f'<title>{esc(text)}: {frac * 100:.1f}%</title></path>')
        a0 = a1
    if center:
        parts.append(f'<text class="donut-value" x="{cx}" y="{cy + 2}" text-anchor="middle">{esc(center[0])}</text>'
                     f'<text class="donut-label" x="{cx}" y="{cy + 20}" text-anchor="middle">{esc(center[1])}</text>')
    parts.append('</svg>')
    legend = ''.join(f'<li><i class="key {esc(c)}"></i><span>{esc(t)}</span><b>{v / total * 100:.1f}%</b><small>{esc(money(v))}</small></li>'
                     for t, v, c in data)
    return f'<div class="v10-alloc">{"".join(parts)}<ul class="v10-legend">{legend}</ul></div>'


def meter(value, limit, *, text, cls=''):
    """A bar showing value against a limit (e.g. position size vs the 25% cap)."""
    v, m = _f(value), _f(limit)
    if v is None or not m:
        return ''
    frac = max(0.0, min(1.0, v / m))
    steps = int(round(frac * 20))
    return (f'<div class="v10-meter {esc(cls)}" role="img" aria-label="{esc(text)}"><span class="v10-meter-fill w{steps}"></span></div>'
            f'<p class="v10-meter-text">{esc(text)}</p>')
