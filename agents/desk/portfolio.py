"""Portfolio: Robinhood-style views of the paper accounts and the real Robinhood Agentic account.

Two tabs:
  * Paper accounts: one "home screen" per paper account. Each has a value graph over several
    ranges, today's change, buying power and allocation. Each holding has its price chart, buy
    markers, why it was picked and what would make it sell, plus the full order history.
  * Real · Robinhood Agentic: the read-only account the system watches but never trades.

Everything comes from local records (paper ledger, valuations, fills, approval cards, the latest
decision capsule and the account tripwire). Nothing is fetched from the broker here. Missing values
are shown as missing, never as zero. No account numbers are stored or shown.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from .charts import _dt, _f, donut, esc, meter, money, pct, ranged, short_time
from .components import V16_CAPITAL, V16_START_TEXT, capital_note, capital_state, deferred

ET = ZoneInfo('America/New_York')
ARMS = {'agent_alone': 'AI alone', 'with_approvals': 'AI + your approval', 'deterministic_no_ai': 'Rules only (no AI)'}
ARM_HELP = {
    'agent_alone': 'Takes every AI pick and every desk-rule trade immediately, with no human in the loop.',
    'with_approvals': 'Gets the same ideas as cards; a trade happens only if you answer YES, at a fresh price when you answer.',
    'deterministic_no_ai': 'Never asks a model. Only the written rules trade here: the control the AI must beat.',
}
LANES = {'A': 'Lane A · Stocks & ETFs', 'B': 'Lane B · Options'}
START = Decimal('500')
NAMES = {
    'AAPL': 'Apple', 'AMZN': 'Amazon', 'GLD': 'SPDR Gold Shares', 'GOOGL': 'Alphabet (Google)', 'META': 'Meta Platforms',
    'MSFT': 'Microsoft', 'NVDA': 'NVIDIA', 'QQQ': 'Invesco QQQ (Nasdaq-100)', 'SOXX': 'iShares Semiconductor ETF',
    'SPY': 'SPDR S&P 500 ETF', 'TLT': 'iShares 20+ Year Treasury Bond ETF', 'VTI': 'Vanguard Total Stock Market ETF',
    'XLB': 'Materials Select Sector SPDR', 'XLC': 'Communication Services Select Sector SPDR', 'XLE': 'Energy Select Sector SPDR',
    'XLF': 'Financial Select Sector SPDR', 'XLI': 'Industrial Select Sector SPDR', 'XLK': 'Technology Select Sector SPDR',
    'XLP': 'Consumer Staples Select Sector SPDR', 'XLRE': 'Real Estate Select Sector SPDR', 'XLU': 'Utilities Select Sector SPDR',
    'XLV': 'Health Care Select Sector SPDR', 'XLY': 'Consumer Discretionary Select Sector SPDR'}
STOCKS = {'AAPL', 'AMZN', 'GOOGL', 'META', 'MSFT', 'NVDA'}
SLICE = ('s0', 's1', 's2', 's3', 's4', 's5')
# Registered limits shown next to the numbers they bound (the Rule book lists the sources).
POSITION_CAP = Decimal('0.25')      # risk engine: one position <= 25% of account value
MAX_POSITIONS = 5
DAILY_LOSS = Decimal('0.03')
PROTECTIVE_STOP = Decimal('0.08')   # v1.6: bid <= average cost x (1 - 8%) at the 15:50 check


def D(v):
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return None


def qty_s(v):
    q = D(v)
    return '—' if q is None else f'{q.normalize():f}'


def when(value):
    try:
        dt = datetime.fromisoformat(value)
        return dt.astimezone(ET).strftime('%a %b %-d, %-I:%M %p ET') if dt.tzinfo else 'time not recorded'
    except (TypeError, ValueError):
        return 'time not recorded'


def _cls(v):
    v = _f(v)
    return 'pos' if v and v > 0 else 'neg' if v and v < 0 else ''


# ------------------------------------------------------------------ shared lookups
def _closes(capsule, ticker):
    """Daily closes from the latest decision capsule, moved to the correct trading day.

    Robinhood daily bars begin at 00:00 UTC, so the stored ET date is one calendar day early
    (a documented known issue). Charts show each close on its own session, at 4 PM ET."""
    raw = ((capsule or {}).get('closes') or {}).get(ticker) or {}
    out = []
    for day, close in raw.items():
        try:
            d = datetime.fromisoformat(day).date() + timedelta(days=1)
        except (TypeError, ValueError):
            continue
        v = _f(close)
        if v is not None:
            out.append((datetime.combine(d, time(16, 0), ET), v))
    out.sort()
    return out


def _ma(points, n=200):
    out, acc = [], 0.0
    for i, (d, v) in enumerate(points):
        acc += v
        if i >= n:
            acc -= points[i - n][1]
        if i >= n - 1:
            out.append((d, acc / n))
    return out


def _card_for(state, order_id):
    for c in state.get('cards') or []:
        if order_id and (c.get('id') == order_id or (c.get('proposal') or {}).get('client_order_id') == order_id):
            return c
    return None


def _account_value(p):
    cash = (D(p.get('settled_cash')) or Decimal(0)) + (D(p.get('unsettled_cash')) or Decimal(0))
    invested = Decimal(0)
    for x in p.get('positions') or []:
        mark = D((p.get('marks') or {}).get(x.get('ticker'))) or D(x.get('average_cost')) or Decimal(0)
        invested += (D(x.get('quantity')) or 0) * mark * (D(x.get('multiplier')) or 1)
    return cash, invested, cash + invested


def _series(values, lane, track, since=None):
    pts = {}
    for v in values:
        if v.get('lane') != lane or v.get('track') != track or v.get('data_mode') not in (None, 'live_readonly'):
            continue
        if since and str(v.get('timestamp')) < since:
            continue
        val, d = _f(v.get('value')), _dt(v.get('timestamp'))
        if val is not None and d is not None:
            pts[d] = val          # several valuations can share a run's timestamp; keep the last
    return sorted(pts.items())


# ------------------------------------------------------------------ paper: one account home screen
def _why(state, p, t, fills, capsule):
    first_buy = next((f for f in fills if f.get('side') == 'buy'), None)
    card = _card_for(state, (first_buy or {}).get('client_order_id'))
    prop = (card or {}).get('proposal') or {}
    sig = next((s for s in (capsule or {}).get('signals') or [] if s.get('instrument') == t), {})
    author = (card or {}).get('author') or ('Desk rule (no AI)' if prop.get('model_name') == 'deterministic_not_a_model'
                                            else prop.get('model_name') or 'not recorded')
    rows = [('Who picked it', author + (': not an AI pick' if 'no AI' in author else '')),
            ('Rule / strategy', sig.get('strategy') or 'not in the latest decision record'),
            ('Thesis', prop.get('thesis') or sig.get('thesis') or 'not recorded'),
            ('Good if', prop.get('good_if') or sig.get('good_if') or 'not recorded'),
            ('Wrong if', prop.get('invalidation') or sig.get('invalidation') or 'not recorded'),
            ('Planned horizon', f'{prop.get("horizon_days")} sessions' if prop.get('horizon_days') else 'not recorded')]
    if card and p.get('track') == 'with_approvals':
        secs = card.get('response_seconds')
        lag = f' ({int(secs) // 60} min {int(secs) % 60} s after the card arrived)' if isinstance(secs, (int, float)) else ''
        rows.append(('Your answer', f'{card.get("status")} at {when(card.get("decided"))}{lag}'))
    sizing = ''
    vol = _f((card or {}).get('vol'))
    if vol:
        frac = min(0.25, 0.10 * 0.20 / vol)
        limit = prop.get('limit_price') or (card or {}).get('limit_price')
        sizing = (f'<p class="v10-note">Size: the risk engine targets <b>{frac * 100:.2f}%</b> of the account = min(25%, 10% × 20% ÷ '
                  f'realized volatility {vol * 100:.1f}%). On ${V16_CAPITAL:,} that is {money(frac * V16_CAPITAL)}. '
                  f'Limit price {money(limit)} = reference midpoint × 1.005, so it never chases the price.</p>')
    return rows, sizing, vol


def _numbers(capsule, t, vol):
    feat = ((capsule or {}).get('features') or {}).get(t) or {}
    if not feat:
        return ''
    price, ma, m126 = _f(feat.get('price')), _f(feat.get('ma200')), _f(feat.get('momentum_126d'))
    dist = (price / ma - 1) * 100 if price and ma else None
    liq = _f(((capsule or {}).get('liquidity') or {}).get(t))
    items = [('Price at decision', money(price)),
             ('200-session average', f'{money(ma)} <small class="{_cls(dist)}">price {pct(dist)} vs average</small>'),
             ('126-session momentum', f'<span class="{_cls(m126)}">{pct(m126 * 100) if m126 is not None else "—"}</span>'),
             ('63 / 252-session momentum', f'{pct((_f(feat.get("momentum_63d")) or 0) * 100)} / {pct((_f(feat.get("momentum_252d")) or 0) * 100)}'),
             ('Realized volatility (20 sessions)', pct(vol * 100, False, 1) if vol else '—'),
             ('Median daily $ volume (20 sessions)', f'${liq / 1e6:,.0f}M' if liq else '—')]
    return '<dl class="v10-facts">' + ''.join(f'<div><dt>{esc(k)}</dt><dd>{v}</dd></div>' for k, v in items) + '</dl>'


def _exit_plan(capsule, t, x, cost, mark):
    feat = ((capsule or {}).get('features') or {}).get(t) or {}
    price, ma, m126 = _f(feat.get('price')), _f(feat.get('ma200')), _f(feat.get('momentum_126d'))
    rows = []
    if t not in STOCKS:
        rows.append(('10:00 ETF exit · v1.5.1', 'Close at or below its 200-session average', bool(ma and price and price > ma),
                     f'last close {pct((price / ma - 1) * 100) if ma and price else "—"} vs the average'))
        rows.append(('10:00 ETF exit · v1.5.1', '126-session momentum at or below zero', m126 is not None and m126 > 0,
                     f'now {pct((m126 or 0) * 100)}'))
    else:
        rows.append(('10:00 stock backstop · v1.5.2', 'Close at or below the 200-session average, or 20 sessions after the last buy',
                     bool(ma and price and price > ma), 'sessions are counted from the last buy fill'))
    if cost and mark is not None:
        stop = cost * (1 - PROTECTIVE_STOP)
        rows.append(('15:50 protective check · v1.6', f'Bid at or below 8% under your cost ({money(stop)})', mark > stop,
                     f'last bid {money(mark)}, {pct((mark / stop - 1) * 100)} above the stop'))
    rows.append(('15:50 protective check · v1.6', 'Bid at or below the 200-session average',
                 bool(ma and mark is not None and float(mark) > ma), f'average {money(ma)}'))
    if t not in STOCKS:
        rows.append(('15:50 protective check · v1.6', 'ETF only: 126-session momentum on the live bid at or below zero',
                     m126 is not None and m126 > 0, 'recomputed on the live bid'))
    return ''.join(f'<li class="{"ok" if safe else "hit"}"><span class="v10-chip">{esc(w)}</span><b>{esc(rule)}</b>'
                   f'<small>{"Not triggered" if safe else "Triggered or not known"} · {esc(note)}</small></li>' for w, rule, safe, note in rows)


def _holding(state, p, x, capsule):
    t = x.get('ticker') or '?'
    qty, cost = D(x.get('quantity')) or Decimal(0), D(x.get('average_cost'))
    mark = D((p.get('marks') or {}).get(t))
    mult = D(x.get('multiplier')) or 1
    mv = qty * (mark if mark is not None else (cost or 0)) * mult
    basis = qty * (cost or 0) * mult
    gain = mv - basis if mark is not None else None
    total = _account_value(p)[2]
    weight = (mv / total) if total else None
    fills = sorted((f for f in p.get('fills') or [] if f.get('ticker') == t), key=lambda f: str(f.get('timestamp')))
    head = (f'<summary class="v10-hold-row"><span class="v10-tk"><b>{esc(t)}</b><small>{esc(NAMES.get(t, ""))}</small></span>'
            f'<span class="num">{esc(qty_s(qty))}<small>shares</small></span>'
            f'<span class="num">{money(mark) if mark is not None else "no mark"}<small>last bid</small></span>'
            f'<span class="num">{money(mv)}<small>value</small></span>'
            f'<span class="num {_cls(gain)}">{money(gain, True) if gain is not None else "—"}'
            f'<small>{pct(gain / basis * 100) if gain is not None and basis else ""}</small></span>'
            f'<span class="num">{pct(weight * 100, False, 1) if weight is not None else "—"}<small>of account</small></span></summary>')
    closes = _closes(capsule, t)
    ma_line = _ma(closes)
    last_fill = max((_dt(f.get('timestamp')) for f in fills if _dt(f.get('timestamp'))), default=None)
    if mark is not None and last_fill and (not closes or last_fill > closes[-1][0]):
        closes = closes + [(last_fill, float(mark))]
    markers = [(f.get('timestamp'), f.get('price'), f'{"Bought" if f.get("side") == "buy" else "Sold"} {qty_s(f.get("quantity"))} @ {money(f.get("price"))}',
                'buy' if f.get('side') == 'buy' else 'sell') for f in fills]
    hlines = []
    if cost:
        hlines.append((float(cost), f'your cost {money(cost)}', 'cost'))
        hlines.append((float(cost * (1 - PROTECTIVE_STOP)), f'8% stop {money(cost * (1 - PROTECTIVE_STOP))}', 'stop'))
    chart = ranged(closes, label=f'{t} price', now=closes[-1][0] if closes else None, default='6M', markers=markers,
                   overlays=[(ma_line, 'ma200', '200-session average')], hlines=hlines, show_dates='date',
                   ranges=(('1W', 7), ('1M', 31), ('3M', 92), ('6M', 183), ('1Y', 366), ('ALL', None)))
    rows, sizing, vol = _why(state, p, t, fills, capsule)
    orders = ''.join(f'<tr><td>{esc(short_time(f.get("timestamp")))}</td><td>{esc((f.get("side") or "").upper())}</td>'
                     f'<td class="num">{esc(qty_s(f.get("quantity")))}</td><td class="num">{money(f.get("price"))}</td>'
                     f'<td class="num">{money(f.get("spread_cost"))}</td><td>{esc(f.get("status"))}</td>'
                     f'<td class="small">{esc(f.get("comparison") or "")}</td></tr>' for f in fills)
    return (f'<details class="v10-hold">{head}<div class="v10-hold-body">'
            f'<div class="v10-hold-chart"><h4>{esc(t)} price and your buys</h4>{chart}'
            '<p class="v10-note">Solid line: daily close (the last point is the latest recorded bid). Dashed line: 200-session average. '
            'Dots: your fills. Red line: the 8% protective stop.</p></div>'
            '<div class="v10-two"><section><h4>Why it was picked</h4><dl class="v10-why">'
            + ''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in rows) + f'</dl>{sizing}{_numbers(capsule, t, vol)}</section>'
            f'<section><h4>What would make it sell</h4><ul class="v10-exits">{_exit_plan(capsule, t, x, cost, mark)}</ul>'
            '<p class="v10-note">There are no resting stop orders. Sells happen only at the 10:00 run or the 15:50 check, at the bid. '
            'The “AI + your approval” account gets a SELL card instead.</p>'
            '<h4>Position vs limits</h4>'
            + meter(weight, POSITION_CAP, text=f'{pct((weight or 0) * 100, False, 1)} of account · limit 25% per position', cls='cap')
            + '</section></div>'
            '<h4>Order history</h4><div class="table-wrap"><table class="mini"><thead><tr><th>When</th><th>Side</th><th>Shares</th><th>Price</th>'
            f'<th>Spread paid</th><th>Status</th><th>Price basis</th></tr></thead><tbody>'
            f'{orders or "<tr><td colspan=7>No fills recorded.</td></tr>"}</tbody></table></div></div></details>')


def _account_panel(state, p, values, rebase_at, capsule, active, now):
    lane, track = p['lane'], p['track']
    cash, invested, total = _account_value(p)
    start = D(p.get('start')) or START
    day0 = D(p.get('day_start_value'))
    pts = _series(values, lane, track, rebase_at if lane == 'A' and rebase_at else None)
    if not pts or abs(pts[-1][1] - float(total)) > 0.005:
        pts = pts + [(max(now, pts[-1][0] + timedelta(seconds=1)) if pts else now, float(total))]
    day_change = total - day0 if day0 is not None else None
    peak = D(p.get('peak')) or start
    dd = (peak - total) / peak if peak else Decimal(0)
    chart = ranged(pts, label=f'{ARMS.get(track, track)} value', now=now, baseline=float(start), baseline_label=f'start {money(start)}',
                   ranges=(('1D', 1), ('1W', 7), ('1M', 31), ('3M', 92), ('1Y', 366), ('ALL', None)))
    slices = [('Cash', cash, 'cash')]
    for i, x in enumerate(p.get('positions') or []):
        mark = D((p.get('marks') or {}).get(x.get('ticker'))) or D(x.get('average_cost')) or 0
        slices.append((x.get('ticker'), (D(x.get('quantity')) or 0) * mark * (D(x.get('multiplier')) or 1), SLICE[i % len(SLICE)]))
    holdings = ''.join(_holding(state, p, x, capsule) for x in p.get('positions') or [])
    if not holdings:
        holdings = ('<p class="v10-empty">No holdings. ' + ('New option buys are paused under v1.6, so this lane stays in cash.' if lane == 'B'
                    else 'Every run so far ended without an entry for this account.') + '</p>')
    fills = sorted(p.get('fills') or [], key=lambda f: str(f.get('timestamp')), reverse=True)
    activity = ''.join(f'<li><time>{esc(short_time(f.get("timestamp")))}</time><b>{esc((f.get("side") or "").upper())} {esc(f.get("ticker"))}</b>'
                       f'<span>{esc(qty_s(f.get("quantity")))} shares @ {money(f.get("price"))} · spread {money(f.get("spread_cost"))}</span></li>' for f in fills)
    stats = [('Total value', money(total)), ('Buying power (settled cash)', money(p.get('settled_cash'))),
             ('Unsettled cash (T+1)', money(p.get('unsettled_cash'))), ('Invested, valued at bid', money(invested)),
             ('Return since start', f'<span class="{_cls(total - start)}">{money(total - start, True)} ({pct((total / start - 1) * 100)})</span>'),
             ('Peak value', money(peak)), ('Drawdown from peak', f'{pct(dd * 100, False)} · new buys stop at 10%'),
             ('Daily-loss stop', f'new buys stop if today’s loss reaches 3% ({money(total * DAILY_LOSS)})'),
             ('Open positions', f'{len(p.get("positions") or [])} of max {MAX_POSITIONS}'),
             ('10% drawdown latch', 'latched: new buys blocked' if p.get('peak_breaker_latched') else 'off')]
    return (f'<section class="v10-acct" id="acct-{lane}-{track}" data-acct="{lane}-{track}"{" data-active" if active else ""}>'
            f'<header class="v10-acct-head"><div><p class="v10-eyebrow">{esc(LANES[lane])} · paper</p><h2>{esc(ARMS.get(track, track))}</h2>'
            f'<p class="v10-sub">{esc(ARM_HELP.get(track, ""))}</p></div>'
            f'<div class="v10-big"><b>{money(total)}</b>'
            f'<span class="{_cls(day_change)}">{money(day_change, True) if day_change is not None else "—"} '
            f'({pct(day_change / day0 * 100) if day_change is not None and day0 else "—"}) today</span>'
            f'<span class="{_cls(total - start)}">{money(total - start, True)} since the start ({money(start)})</span></div></header>'
            f'<div class="v10-graph">{chart}<p class="v10-note">Valued at the bid (what you could sell for), so a fresh buy starts slightly '
            'below cost; that gap is the spread paid. Points are the recorded valuations, so the graph grows with every run.</p></div>'
            '<div class="v10-grid">'
            f'<section class="v10-panel"><h3>Allocation</h3>{donut(slices, label="Allocation")}</section>'
            '<section class="v10-panel"><h3>Account stats</h3><dl class="v10-stats">'
            + ''.join(f'<div><dt>{esc(k)}</dt><dd>{v}</dd></div>' for k, v in stats) + '</dl></section></div>'
            '<section class="v10-panel"><h3>Holdings <small>open a row for the chart, the reason and the exit plan</small></h3>'
            f'<div class="v10-hold-head"><span>Name</span><span>Shares</span><span>Price</span><span>Value</span><span>Return</span><span>Weight</span></div>{holdings}</section>'
            '<section class="v10-panel"><h3>Activity</h3>'
            + (f'<ol class="v10-activity">{activity}</ol>' if activity else '<p class="v10-empty">No fills yet.</p>') + '</section></section>')


def _compare(paper):
    rows = ''
    for p in paper:
        cash, _, total = _account_value(p)
        start = D(p.get('start')) or START
        rows += (f'<tr><td><a href="#acct-{p["lane"]}-{p["track"]}" data-acct-link="{p["lane"]}-{p["track"]}">{esc(ARMS.get(p["track"], p["track"]))}</a></td>'
                 f'<td>{esc(p["lane"])}</td><td class="num">{money(total)}</td><td class="num {_cls(total - start)}">{money(total - start, True)}</td>'
                 f'<td class="num">{money(cash)}</td><td class="num">{len(p.get("positions") or [])}</td></tr>')
    return ('<div class="table-wrap"><table class="mini v10-compare"><thead><tr><th>Account</th><th>Lane</th><th>Value</th><th>vs start</th>'
            f'<th>Cash</th><th>Holdings</th></tr></thead><tbody>{rows}</tbody></table></div>')


def _dip_short(reason):
    if not reason:
        return 'Qualifies'
    if 'smaller than 3%' in reason:
        return 'No 3% drop'
    if '200-session' in reason:
        return 'Below 200-day avg'
    return reason


def _screen(capsule):
    """Why this name and not the others: the latest decision's view of all 23 registered tickers."""
    if not capsule or not capsule.get('features'):
        return ''
    strat = capsule.get('strategies') or {}
    mom, dip = strat.get('momentum_rotation') or {}, strat.get('mean_reversion') or {}
    ranked = list(mom.get('ranked') or [])
    picked = set((capsule.get('decision') or {}).get('signal_instruments') or ranked[:1])
    rows = []
    for t, f in capsule['features'].items():
        m = _f(f.get('momentum_126d'))
        if t in picked:
            status, cls = 'Picked #1: the desk bought it', 'pick'
        elif t in ranked:
            status, cls = f'Qualifies, ranked #{ranked.index(t) + 1}: only #1 is bought', 'ok'
        elif t in (mom.get('blocked') or {}):
            status, cls = 'Blocked: ' + mom['blocked'][t].replace('price is not above its 200-session moving average', 'below its 200-session average'), 'blocked'
        elif t in STOCKS or t not in (mom.get('evaluated') or [t]):
            status, cls = 'Single stock: these rules buy ETFs only; stocks need an AI pick', 'na'
        else:
            status, cls = 'Evaluated, not ranked', 'ok'
        rows.append((m, t, f, status, cls, (dip.get('blocked') or {}).get(t)))
    rows.sort(key=lambda r: (r[0] is None, -(r[0] or 0)))
    top = max((abs(r[0]) for r in rows if r[0] is not None), default=1) or 1
    body = ''
    for m, t, f, status, cls, dip_reason in rows:
        price, ma = _f(f.get('price')), _f(f.get('ma200'))
        dist = (price / ma - 1) * 100 if price and ma else None
        w = int(round(min(1, abs(m) / top) * 20)) if m is not None else 0
        body += (f'<tr class="v10-scr-{cls}"><td><b>{esc(t)}</b><small>{esc(NAMES.get(t, ""))}</small></td>'
                 f'<td class="num">{money(price)}</td><td class="num {_cls(dist)}">{pct(dist)}</td>'
                 f'<td class="v10-barcell"><span class="v10-bar {"neg" if (m or 0) < 0 else "pos"} w{w}"></span>'
                 f'<span class="num">{pct(m * 100) if m is not None else "—"}</span></td>'
                 f'<td class="num">{pct((_f(f.get("one_day_return")) or 0) * 100)}</td>'
                 f'<td>{esc(status)}</td><td class="small">{esc(_dip_short(dip_reason))}</td></tr>')
    return ('<details class="v10-panel v10-screen" open><summary><h3>Why this pick and not the others</h3>'
            f'<small>{esc(short_time(capsule.get("observed_at")))} decision · all 23 registered names, strongest momentum first</small></summary>'
            '<p class="v10-note">Momentum rule (the 17 ETFs): needs at least 253 daily closes, the last close above its 200-session average and '
            'positive 126-session momentum; only the single strongest is bought. Dip rule: close above the 200-session average and the last session '
            'fell 3% or more. Single stocks are bought only through an AI pick that passes the Critic and the risk engine.</p>'
            '<div class="table-wrap"><table class="mini v10-scr"><thead><tr><th>Name</th><th>Price</th><th>vs 200-day avg</th><th>126-session momentum</th>'
            f'<th>Last day</th><th>Momentum rule</th><th>Dip rule</th></tr></thead><tbody>{body}</tbody></table></div></details>')


def paper_tab(state, now):
    pf = state.get('portfolio') or {}
    paper = pf.get('paper') or []
    if not paper:
        return '<p class="v10-empty">No paper accounts are recorded yet.</p>'
    order = list(ARMS)
    paper = sorted(paper, key=lambda p: (p['lane'], order.index(p['track']) if p['track'] in order else 9))
    rebase = (state.get('research') or {}).get('rebase') or {}
    capsule = pf.get('capsule')
    first = paper[0]
    chips = ''
    for lane in ('A', 'B'):
        arms = [p for p in paper if p['lane'] == lane]
        if arms:
            chips += (f'<div class="v10-chipgroup"><span>{esc(LANES[lane])}</span>'
                      + ''.join(f'<a class="v10-acct-chip" href="#acct-{lane}-{p["track"]}" data-acct-link="{lane}-{p["track"]}"'
                                f'{" aria-current=true" if p is first else ""}>{esc(ARMS.get(p["track"], p["track"]))}'
                                f'<small>{money(_account_value(p)[2])}</small></a>' for p in arms) + '</div>')
    panels = ''.join(_account_panel(state, p, pf.get('values') or [], rebase.get('timestamp'), capsule, p is first, now) for p in paper)
    return (f'<div class="v10-acct-picker" role="group" aria-label="Choose a paper account">{chips}</div>{panels}'
            + _screen(capsule)
            + f'<section class="v10-panel"><h3>All paper accounts side by side</h3>{_compare(paper)}'
            '<p class="v10-note">Same money, same prices, different decision-makers. The gaps between these accounts are the experiment: '
            'does the AI beat “Rules only”, and does your YES/NO add anything on top?</p></section>')


# ------------------------------------------------------------------ real Agentic account
def real_tab(state):
    pf = state.get('portfolio') or {}
    real = pf.get('real')
    trip = pf.get('tripwire') or ([real['last_check']] if real and real.get('last_check') else [])
    if not real:
        return ('<section class="v10-acct" data-active><p class="v10-empty">No verified snapshot of the Robinhood Agentic account is recorded yet. '
                'Missing is not zero.</p></section>')
    cash = D(real.get('cash'))
    base = _f(real.get('cash'))
    pts = [(h['at'], h['cash']) for h in pf.get('real_history') or [] if h.get('cash') is not None]
    pts += [(e['created_at'], base) for e in trip if e.get('status') in ('VERIFIED_UNCHANGED', 'BASELINE_CREATED') and base is not None]
    last = trip[-1] if trip else {}
    chart = ranged(pts, label='Agentic account cash', now=last.get('created_at'), baseline=base, baseline_label='first snapshot',
                   ranges=(('1W', 7), ('1M', 31), ('3M', 92), ('ALL', None)))
    orders = real.get('open_orders') or {}
    checks = ''.join(f'<li class="{"ok" if (e.get("status") or "").startswith(("VERIFIED", "BASELINE")) else "hit"}">'
                     f'<time>{esc(short_time(e.get("created_at")))}</time><b>{esc((e.get("status") or "").replace("_", " ").title())}</b>'
                     f'<small>{esc(e.get("change_class") or "cash, positions and orders match the recorded snapshot")}</small></li>' for e in reversed(trip))
    positions = real.get('positions') or []
    hold = ('<p class="v10-empty">No positions. The system has never traded this account.</p>' if not positions else
            ''.join(f'<p>Position: {esc(p.get("quantity"))} ({esc(p.get("direction"))}), instrument name not stored</p>' for p in positions))
    return ('<section class="v10-acct" data-active>'
            '<header class="v10-acct-head"><div><p class="v10-eyebrow">Robinhood · Agentic account · read-only</p><h2>Real account</h2>'
            '<p class="v10-sub">The real Robinhood account the agents are scoped to. The system reads it at every 10:00 run and stops itself if '
            'anything changes unexpectedly. It cannot place, cancel or fund orders here.</p></div>'
            f'<div class="v10-big"><b>{money(cash)}</b><span>cash · {len(positions)} positions · {sum(orders.values())} orders on record</span>'
            f'<span>last verified {esc(short_time(last.get("created_at") or real.get("as_of")))}</span></div></header>'
            f'<div class="v10-graph">{chart}<p class="v10-note">Each point is a recorded check of the account. A flat line is expected: '
            'real orders are blocked.</p></div>'
            '<div class="v10-grid">'
            f'<section class="v10-panel"><h3>Holdings and orders</h3>{hold}<dl class="v10-stats">'
            f'<div><dt>Cash</dt><dd>{money(cash)}</dd></div><div><dt>Stock orders on record</dt><dd>{orders.get("equity", 0)}</dd></div>'
            f'<div><dt>Option orders on record</dt><dd>{orders.get("option", 0)}</dd></div><div><dt>Crypto orders on record</dt><dd>{orders.get("crypto", 0)}</dd></div>'
            '<div><dt>Buying power</dt><dd>not recorded</dd></div><div><dt>Highest account cash the system accepts</dt><dd>$1,200 (it stops above that)</dd></div></dl></section>'
            f'<section class="v10-panel"><h3>Account checks (tripwire)</h3><ol class="v10-checks">{checks or "<li>No checks recorded.</li>"}</ol></section></div>'
            '<section class="v10-panel"><h3>Why nothing is ever bought here</h3><ul class="v10-list">'
            '<li><b>No write tools exist.</b> The broker gateway allows exactly 11 read methods. There is no order, cancel or transfer call to make.</li>'
            '<li><b>Separate login.</b> The Robinhood sign-in lives under a separate macOS user; the agents only reach a local read-only proxy.</li>'
            '<li><b>The signed rules forbid it.</b> Real execution stays blocked until a statistical gate is passed (200 filled decisions or 252 '
            'sessions, with the 90% interval of excess return over VTI above zero) and you sign a new amendment.</li>'
            '<li><b>Tripwire.</b> Any unexpected change in cash, positions or orders stops all trading and records an incident.</li></ul>'
            '<p class="v10-note">Stored per check: cash, position quantities and order counts only. No account numbers, no buying power, '
            'no instrument names.</p></section></section>')


def render(state):
    if not state.get('preview'):
        return deferred('Portfolio', 'U4')
    now = _dt(state.get('updated_at')) or datetime.now(timezone.utc)
    status = capital_state(state)[0]
    return ('<div class="room-head"><div><h1>Portfolio</h1><p>The paper accounts the agents trade, and the real Robinhood Agentic account they watch.</p></div></div>'
            + capital_note(state)
            + '<nav class="v10-tabs" role="tablist" aria-label="Portfolio views">'
              '<a role="tab" href="#tab-paper" data-tab="tab-paper" aria-selected="true">Paper accounts <small>simulated · six accounts</small></a>'
              '<a role="tab" href="#tab-real" data-tab="tab-real" aria-selected="false">Real · Robinhood Agentic <small>read-only</small></a></nav>'
            + f'<div class="v10-tabpanel" id="tab-paper" data-tabpanel data-active><h2 class="v10-tabtitle">Paper accounts</h2>{paper_tab(state, now)}</div>'
            + f'<div class="v10-tabpanel" id="tab-real" data-tabpanel><h2 class="v10-tabtitle">Real · Robinhood Agentic account</h2>{real_tab(state)}</div>'
            + ('' if status != 'scheduled' else f'<p class="v10-note">Lane A becomes ${V16_CAPITAL:,} per account {esc(V16_START_TEXT)}.</p>')
            + _lanes(state))


def _lanes(state):
    from .lanes import render as lane_map
    return ('<details class="room-card sub pf-lanes"><summary>How the two paper lanes work</summary>'
            + lane_map(state) + '</details>')
