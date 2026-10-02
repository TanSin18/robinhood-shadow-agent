"""Tape measures used by the signed v1.7 rules: ATR, ADX and the trending / choppy label.

Pure arithmetic on completed daily bars (dicts with 'day', 'high', 'low', 'close' as floats). No broker,
model, database or clock. The same formulas as the advisory desk's shadow guard (agents/analyst/guard.py);
a test keeps the two identical, so what the dashboard shows is what the rules use.
"""
from __future__ import annotations


def atr(bars, n):
    trs = []
    for p, c in zip(bars, bars[1:]):
        if None in (c.get('high'), c.get('low'), p.get('close')):
            continue
        trs.append(max(c['high'] - c['low'], abs(c['high'] - p['close']), abs(c['low'] - p['close'])))
    if len(trs) < n:
        return None, trs
    a = sum(trs[:n]) / n
    for tr in trs[n:]:
        a = (a * (n - 1) + tr) / n            # Wilder smoothing
    return a, trs


def ma(closes, n):
    return sum(closes[-n:]) / n if len(closes) >= n else None


def adx(bars, n=14):
    if len(bars) < 2 * n + 2:
        return None
    pdm, mdm, trs = [], [], []
    for p, c in zip(bars, bars[1:]):
        if None in (c.get('high'), c.get('low'), p.get('high'), p.get('low'), p.get('close')):
            return None
        up, down = c['high'] - p['high'], p['low'] - c['low']
        pdm.append(up if up > down and up > 0 else 0.0)
        mdm.append(down if down > up and down > 0 else 0.0)
        trs.append(max(c['high'] - c['low'], abs(c['high'] - p['close']), abs(c['low'] - p['close'])))

    def wilder(xs):
        s = sum(xs[:n])
        out = [s]
        for x in xs[n:]:
            s = s - s / n + x
            out.append(s)
        return out
    tr_s, p_s, m_s = wilder(trs), wilder(pdm), wilder(mdm)
    dx = []
    for t, p, m in zip(tr_s, p_s, m_s):
        if t <= 0:
            dx.append(0.0)
            continue
        pdi, mdi = 100 * p / t, 100 * m / t
        dx.append(100 * abs(pdi - mdi) / (pdi + mdi) if pdi + mdi else 0.0)
    if len(dx) < n:
        return None
    a = sum(dx[:n]) / n
    for x in dx[n:]:
        a = (a * (n - 1) + x) / n
    return a


def chop_label(bars):
    if len(bars) < 60:
        return {'status': 'TOO_FEW_SESSIONS'}
    closes = [b['close'] for b in bars]
    a14, _ = atr(bars, 14)
    x = adx(bars)
    ma50 = ma(closes, 50)
    last = closes[-1]
    atr_pct_hist = []
    for i in range(max(15, len(bars) - 252), len(bars) + 1):
        a, _ = atr(bars[max(0, i - 40):i], 14)
        if a:
            atr_pct_hist.append(a / bars[i - 1]['close'])
    atr_pct = a14 / last if a14 else None
    low_cut = sorted(atr_pct_hist)[len(atr_pct_hist) // 5] if len(atr_pct_hist) >= 20 else None
    stretch = (last - ma50) / a14 if a14 and ma50 else None
    if stretch is not None and abs(stretch) > 3:
        label = 'OVEREXTENDED'
    elif atr_pct is not None and low_cut is not None and atr_pct <= low_cut:
        label = 'LOW_VOL'
    elif x is not None and x < 20:
        label = 'CHOPPY'
    elif x is not None:
        label = 'TRENDING'
    else:
        label = 'UNKNOWN'
    return {'status': 'OK', 'label': label, 'adx14': None if x is None else round(x, 1),
            'atr14_pct': None if atr_pct is None else round(atr_pct * 100, 2),
            'atr14_pct_low_cut': None if low_cut is None else round(low_cut * 100, 2),
            'stretch_vs_ma50_atr': None if stretch is None else round(stretch, 2), 'gate': 'pass' if label == 'TRENDING' else 'sit out'}


def bars_from_raw(raw_bars, today):
    """Gateway daily bars -> completed sessions before `today` (a date), oldest first.

    A daily bar begins at 00:00 UTC of its session, so the UTC date is the session date."""
    from datetime import datetime, timezone
    out = []
    for b in raw_bars or []:
        try:
            day = datetime.fromisoformat(str(b['begins_at']).replace('Z', '+00:00')).astimezone(timezone.utc).date()
            if b.get('interpolated') or day >= today:
                continue
            out.append({'day': day.isoformat(), 'high': float(b['high_price']), 'low': float(b['low_price']), 'close': float(b['close_price'])})
        except (KeyError, TypeError, ValueError):
            continue
    out.sort(key=lambda x: x['day'])
    return out
