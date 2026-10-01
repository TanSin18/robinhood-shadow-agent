"""Seat tools, computed by code and embedded in the packet (no live tool calls, no news in v1).

Every number a seat may cite has a tool id, so code can check citations exactly:
  quote:<T>, features:<T>, screen:<T>, risk:book, journal:<T>
"""
from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal

D = Decimal


def _r(x, n=4):
    return None if x is None else round(float(x), n)


def get_quote(snapshot, ticker, now: datetime):
    q = snapshot['quotes'].get(ticker)
    if not q:
        return {'id': f'quote:{ticker}', 'available': False}
    age = (now - q['ts']).total_seconds()
    bid, ask = D(str(q['bid'])), D(str(q['ask']))
    mid = (bid + ask) / 2
    return {'id': f'quote:{ticker}', 'available': True, 'bid': _r(bid, 4), 'ask': _r(ask, 4), 'mid': _r(mid, 4),
            'spread_pct': _r((ask - bid) / mid * 100, 3) if mid > 0 else None, 'age_seconds': round(age, 1),
            'fresh': -5 <= age <= 60}


def get_features(snapshot, ticker):
    rows = [c for _, c in sorted(snapshot['closes'].get(ticker, []))]
    out = {'id': f'features:{ticker}', 'completed_sessions': len(rows)}
    if len(rows) < 2:
        return out
    last = rows[-1]
    out['last_close'] = _r(last, 4)
    for n in (1, 5, 20, 63, 126, 252):
        if len(rows) > n:
            out[f'return_{n}d_pct'] = _r((last / rows[-1 - n] - 1) * 100, 2)
    for n in (50, 200):
        if len(rows) >= n:
            ma = sum(rows[-n:]) / n
            out[f'ma{n}'] = _r(ma, 4)
            out[f'pct_vs_ma{n}'] = _r((last / ma - 1) * 100, 2)
    if len(rows) >= 21:
        rets = [math.log(b / a) for a, b in zip(rows[-21:], rows[-20:])]
        m = sum(rets) / len(rets)
        out['vol20_annual_pct'] = _r(math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1)) * math.sqrt(252) * 100, 2)
    if len(rows) >= 252:
        out['high_252'] = _r(max(rows[-252:]), 4)
        out['pct_off_252_high'] = _r((last / max(rows[-252:]) - 1) * 100, 2)
    vols = [v for _, v in sorted(snapshot.get('volumes', {}).get(ticker, []))][-20:]
    if len(vols) == 20 and len(rows) >= 20:
        dv = sorted(c * v for c, v in zip(rows[-20:], vols))
        out['median_dollar_volume_20d_musd'] = _r((dv[9] + dv[10]) / 2 / 1e6, 1)
    return out


def get_screen_row(snapshot, ticker):
    row = (snapshot.get('screen') or {}).get(ticker)
    return {'id': f'screen:{ticker}', 'available': bool(row), **({k: row[k] for k in sorted(row)} if row else {})}


def get_open_risk(book, marks, spec):
    value = book.value(marks)
    return {'id': 'risk:book', 'book_value': _r(value, 2), 'open_names': len(book.positions),
            'max_names': spec.max_names, 'max_fraction_per_name': float(spec.max_fraction),
            'day_change_pct': _r((value / book.day_start_value - 1) * 100, 2) if book.day_start_value else None,
            'week_change_pct': _r((value / book.week_start_value - 1) * 100, 2) if book.week_start_value else None,
            'held': sorted(book.positions)}


def get_journal_similar(store, ticker, limit=5):
    rows = [t for t in store.tickets() if t['ticker'] == ticker][-limit:]
    return {'id': f'journal:{ticker}', 'past_tickets': [{'day': t['day'], 'status': t['status']} for t in rows]}


def packet(snapshot, tickers, book, marks, spec, store, now):
    tools = {}
    for t in tickers:
        for fn in (lambda: get_quote(snapshot, t, now), lambda: get_features(snapshot, t),
                   lambda: get_screen_row(snapshot, t), lambda: get_journal_similar(store, t)):
            out = fn()
            tools[out['id']] = out
    risk = get_open_risk(book, marks, spec)
    tools[risk['id']] = risk
    return tools


def number_in_tools(tools, tool_id, field, value, tolerance=0.005):
    """A cited number must exist in that tool output and match (relative 0.5% or 0.01 absolute)."""
    out = tools.get(tool_id)
    if not out or field not in out or out[field] is None:
        return False
    try:
        actual, cited = float(out[field]), float(value)
    except (TypeError, ValueError):
        return False
    return abs(actual - cited) <= max(0.01, abs(actual) * tolerance)
