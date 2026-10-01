"""Daily auction read from completed daily bars (open, high, low, close, volume).

The registered read gateway only allows daily bars, so this is a daily-bar approximation of an
auction / market-profile read, not an intraday value-area: gap, range versus the 20-session
average true range, where the close sat in the day's range, relative volume and the day type.
"""
from __future__ import annotations


def read(bars):
    """bars: [{'day','open','high','low','close','volume'}] sorted, completed sessions. Reads the last bar."""
    if len(bars) < 22:
        return {'status': 'TOO_FEW_SESSIONS', 'sessions': len(bars)}
    t, p = bars[-1], bars[-2]
    o, h, l, c, v = (t.get(k) for k in ('open', 'high', 'low', 'close', 'volume'))
    if None in (o, h, l, c) or p.get('close') in (None, 0):
        return {'status': 'INCOMPLETE_BAR', 'day': t.get('day')}
    trs = []
    for prev, cur in zip(bars[-21:-1], bars[-20:]):
        if None in (cur.get('high'), cur.get('low'), prev.get('close')):
            continue
        trs.append(max(cur['high'] - cur['low'], abs(cur['high'] - prev['close']), abs(cur['low'] - prev['close'])))
    atr = sum(trs) / len(trs) if trs else None
    vols = [b.get('volume') for b in bars[-21:-1] if b.get('volume')]
    rng = h - l
    clv = ((c - l) - (h - c)) / rng if rng > 0 else 0.0
    rel_range = rng / atr if atr else None
    rel_vol = v / (sum(vols) / len(vols)) if v and vols else None
    inside = h < p.get('high', h) and l > p.get('low', l)
    outside = h > p.get('high', h) and l < p.get('low', l)
    if inside:
        kind = 'inside day (balance)'
    elif rel_range and rel_range >= 1.2 and clv >= 0.6:
        kind = 'trend day up'
    elif rel_range and rel_range >= 1.2 and clv <= -0.6:
        kind = 'trend day down'
    elif outside:
        kind = 'outside day'
    elif rel_range is not None and rel_range < 0.7:
        kind = 'quiet / narrow range'
    else:
        kind = 'normal day'
    return {'status': 'OK', 'day': t['day'], 'open': o, 'high': h, 'low': l, 'close': c,
            'gap_pct': round((o / p['close'] - 1) * 100, 2), 'change_pct': round((c / p['close'] - 1) * 100, 2),
            'range_pct': round(rng / p['close'] * 100, 2), 'range_vs_atr20': None if rel_range is None else round(rel_range, 2),
            'close_location': round(clv, 2), 'volume_vs_avg20': None if rel_vol is None else round(rel_vol, 2), 'day_type': kind}
