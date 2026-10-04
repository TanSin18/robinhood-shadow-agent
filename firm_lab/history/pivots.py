"""Confirmed swing highs and lows, and the legs between them. Deterministic; no chart is interpreted by a model.

``ohlcv_pivot_v1``: a bar is a swing high when its high is strictly above the highs of the three bars before it and the
three bars after it, and a swing low when its low is strictly below the lows of the same six bars. Ties are not pivots.
All seven bars must be consecutive exchange sessions with a bar. A bar that is both is neither (an outside bar gives no
direction). A pivot is known only when its third following session has closed: the confirmation delay is 3 sessions,
and nothing here can see a pivot earlier than that.

The window is 3 and 3 on purpose. It is the same window as ``close_fractal_3x3_v1``, so that a later comparison of
close-based and high/low-based structure differs in the price basis and in nothing else. Run on a series whose high and
low are both the close, this engine reproduces the close-based pivots and legs exactly; a test proves it.

Legs follow the same rule as the close-based version: successive pivots of one kind keep the more extreme; a pivot of
the other kind completes a leg from the kept pivot to it. A leg is known when its end pivot is confirmed.
"""
from __future__ import annotations

import numpy as np

PIVOT_VERSION = 'ohlcv_pivot_v1'
CLOSE_PIVOT_VERSION = 'close_fractal_3x3_v1'
WINDOW = 3
HIGH, LOW = 1, -1


def _strict_extreme(values, n, sign):
    """True where values[i] is strictly beyond every one of the n values on each side (sign +1: above, -1: below)."""
    count = len(values)
    out = np.zeros(count, bool)
    if count < 2 * n + 1:
        return out
    x = sign * values
    windows = np.lib.stride_tricks.sliding_window_view(x, 2 * n + 1)
    centre = windows[:, n]
    others = np.delete(windows, n, axis=1)
    with np.errstate(invalid='ignore'):
        out[n:count - n] = np.all(np.isfinite(windows), axis=1) & (centre > others.max(axis=1))
    return out


def confirmed(high, low, n=WINDOW) -> dict:
    """{'index', 'kind', 'price', 'confirmed_at'} arrays in session order, and the number of outside bars set aside."""
    high, low = np.asarray(high, float), np.asarray(low, float)
    highs, lows = _strict_extreme(high, n, 1), _strict_extreme(low, n, -1)
    both = highs & lows
    highs, lows = highs & ~both, lows & ~both
    index = np.flatnonzero(highs | lows)
    kind = np.where(highs[index], HIGH, LOW)
    price = np.where(highs[index], high[index], low[index])
    return {'index': index, 'kind': kind, 'price': price, 'confirmed_at': index + n, 'outside_bars': int(both.sum())}


def legs(pivots) -> list:
    """Completed legs in the order they became known: (known_at, start_index, start_price, end_index, end_price)."""
    out, pending = [], None
    for i, kind, price, known in zip(pivots['index'], pivots['kind'], pivots['price'], pivots['confirmed_at']):
        current = (int(i), int(kind), float(price))
        if pending is None:
            pending = current
        elif kind == pending[1]:
            if (kind == HIGH and price > pending[2]) or (kind == LOW and price < pending[2]):
                pending = current
        else:
            if price != pending[2]:
                out.append((int(known), pending[0], pending[2], current[0], current[2]))
            pending = current
    return out


def _as_of(count, known, values, fill=np.nan):
    """For each session, the value of the latest event known at or before it."""
    out = np.full(count, fill, dtype=float)
    if len(known) == 0:
        return out
    known = np.asarray(known)
    position = np.searchsorted(known, np.arange(count), side='right') - 1
    has = position >= 0
    out[has] = np.asarray(values, float)[position[has]]
    return out


def structure(high, low, n=WINDOW) -> dict:
    """Per session, what was known at that session's close: the latest confirmed swing high and low, and the latest
    completed leg (start A, end B). NaN where nothing is known yet."""
    count = len(high)
    p = confirmed(high, low, n)
    out = {'outside_bars': p['outside_bars'], 'pivots': int(len(p['index']))}
    for name, kind in (('swing_high', HIGH), ('swing_low', LOW)):
        chosen = p['kind'] == kind
        out[name + '_price'] = _as_of(count, p['confirmed_at'][chosen], p['price'][chosen])
        out[name + '_index'] = _as_of(count, p['confirmed_at'][chosen], p['index'][chosen])
    found = legs(p)
    known = [l[0] for l in found]
    for k, name in ((1, 'leg_start_index'), (2, 'leg_start_price'), (3, 'leg_end_index'), (4, 'leg_end_price')):
        out[name] = _as_of(count, known, [l[k] for l in found])
    out['legs'] = len(found)
    return out
