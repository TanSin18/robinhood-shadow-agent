"""Exit guard and chop gate, computed by code after the close. Shadow only.

Exit guard (per official paper holding) answers "should this be sold to protect the gain or stop a
loss?" with rules that adapt to each name's own volatility instead of a fixed percentage:
  * chandelier stop: highest close since entry minus 3 x ATR(22)                      (trails up only)
  * profit lock: once the best close since entry is 2 x ATR above cost, the floor is cost
    (break-even); at 4 x ATR, the floor is cost + 2 x ATR
  * give-back: after a peak gain of at least 10%, selling if half of that gain is gone
  * fast trend break: close below its 50-day average while the market regime is "stressed"
plus the distance to the official exits (200-day average, 8% below cost). It never sells anything:
each "would sell" is recorded with its price so the record can show later whether the guard would
have saved money or cut a winner early. Only a signed amendment could make any of it real.

Chop gate (per ticker) labels the tape the way a code gate would, from daily bars:
  TRENDING (ADX(14) >= 20), CHOPPY (ADX < 20), LOW_VOL (ATR% in the bottom fifth of its own last
  year) or OVEREXTENDED (more than 3 x ATR(14) from its 50-day average). The label is recorded next
  to every official entry to show what a gate would have blocked.
"""
from __future__ import annotations


def _atr(bars, n):
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


def _ma(closes, n):
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
    a14, _ = _atr(bars, 14)
    x = adx(bars)
    ma50 = _ma(closes, 50)
    last = closes[-1]
    atr_pct_hist = []
    for i in range(max(15, len(bars) - 252), len(bars) + 1):
        a, _ = _atr(bars[max(0, i - 40):i], 14)
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


def exit_guard(holding, bars, regime=None):
    """holding: {'account','ticker','quantity','average_cost','entry_day'}; bars: completed daily bars (dicts)."""
    cost = holding.get('average_cost')
    if not bars or not cost:
        return {**holding, 'status': 'NO_DATA'}
    closes = [b['close'] for b in bars]
    last = closes[-1]
    since = [b for b in bars if b['day'] >= (holding.get('entry_day') or bars[-1]['day'])] or bars[-1:]
    high = max([b['close'] for b in since] + [last])
    a22, _ = _atr(bars, 22)
    ma50, ma200 = _ma(closes, 50), _ma(closes, 200)
    out = {**holding, 'status': 'OK', 'last_close': round(last, 4), 'high_since_entry': round(high, 4),
           'gain_pct': round((last / cost - 1) * 100, 2), 'peak_gain_pct': round((high / cost - 1) * 100, 2),
           'atr22': None if a22 is None else round(a22, 4), 'ma50': None if ma50 is None else round(ma50, 4),
           'ma200': None if ma200 is None else round(ma200, 4), 'official_stop_8pct': round(cost * 0.92, 4)}
    stops, triggers = [('official 8% stop', cost * 0.92)], []
    if a22:
        chand = high - 3 * a22
        stops.append(('chandelier (high − 3×ATR)', chand))
        out['chandelier_stop'] = round(chand, 4)
        if high - cost >= 4 * a22:
            stops.append(('profit lock (cost + 2×ATR)', cost + 2 * a22))
        elif high - cost >= 2 * a22:
            stops.append(('profit lock (break-even)', cost))
    name, level = max(stops, key=lambda s: s[1])
    out['guard_stop'], out['guard_stop_rule'] = round(level, 4), name
    out['distance_to_guard_pct'] = round((last / level - 1) * 100, 2)
    if last <= level:
        triggers.append(name)
    peak_gain, gain = high / cost - 1, last / cost - 1
    if peak_gain >= 0.10 and gain <= peak_gain / 2:
        triggers.append('give-back (half of a 10%+ peak gain gone)')
    if ma50 and last < ma50 and (regime or {}).get('current') == 'stressed':
        triggers.append('fast trend break (below 50-day average in a stressed market)')
    if ma200 and last <= ma200:
        triggers.append('official: close at or below the 200-day average')
    out['triggers'] = triggers
    out['verdict'] = 'WOULD_SELL' if triggers else 'HOLD'
    return out
