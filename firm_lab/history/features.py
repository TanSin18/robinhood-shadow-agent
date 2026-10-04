"""Descriptive features from validated daily OHLCV, as arrays over a security's sessions. No model, no rule, no score.

Every feature is a ratio: a later split multiplies every earlier price by one number and leaves the feature where it
was. Nothing here is in dollars.

Which prices are used. Across sessions, the close is the exact close (``adjust.exact_close``): the unadjusted close and
the confirmed split ratios, so the vendor's rounding of reprinted adjusted prices cannot carry a later split back into
an earlier feature. Within one bar, the open, high and low are the vendor's adjusted prints relative to that bar's own
adjusted close. Where the adjusted close is printed more coarsely than 0.05% of itself, the bar's shape cannot be
trusted, and every feature that reads a high, low or open is unavailable there. Close-based features are not affected.

A value at session T uses bars up to and including T and nothing after. A window that reaches across a missing bar,
or across a session where prices are not comparable (``adjust.breaks``), is NaN: unavailable, never estimated. The
recursive averages (ATR, RSI) restart at such a session, so nothing from before it survives in them.

Versions. These are new feature versions, stored beside the Checkpoint 6 close-only features, which are not changed:

    candle_geometry_v1    body, range and wick fractions, close location, gaps
    atr14_ohlcv_v1        true range, Wilder ATR14, ATR over price, range expansion, realized volatility
    rvol20_v1             relative volume, volume percentile, price-volume products, breakout-volume confirmation
    ohlcv_pivot_v1        confirmed 3x3 swing highs and lows on highs and lows, and the legs between them
    fib_ohlcv_pivot_v1    retracements and extensions of the latest completed high/low leg
    close_pivot_vectorized_v1 / fib_close_pivot_vectorized_v1
                          the same engine on closes: reproduces close_fractal_3x3_v1 for a like-for-like comparison
    close_technical_vectorized_v1
                          trailing returns, distances to averages, Wilder RSI14: the Checkpoint 6 formulas, on arrays

Named candlestick patterns are not produced. Volume features describe volume; they say nothing about who traded.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from . import adjust, pivots

FEATURE_SET_VERSION = 'ohlcv-features-v1'
RETRACEMENTS = ('0.236', '0.382', '0.5', '0.618', '0.786')
EXTENSIONS = ('1.272', '1.618')
BREAKOUT_RVOL = 1.5
VARIABLE = -1          # the lookback is the age of a pivot or leg, checked against breaks separately


def code_hash() -> str:
    here = Path(__file__).parent
    digest = hashlib.sha256()
    for name in ('features.py', 'pivots.py', 'adjust.py', 'panel.py', 'calendar.py'):
        digest.update((here / name).read_bytes())
    return digest.hexdigest()


def _definitions() -> tuple:
    out = []

    def add(name, version, family, lookback, unit, formula):
        shape = (version in ('candle_geometry_v1', 'ohlcv_pivot_v1', 'fib_ohlcv_pivot_v1') or name.endswith('_atr_distance')
                 or name in ('true_range_fraction', 'atr14_fraction', 'range_expansion', 'range_expansion_rvol'))
        out.append({'name': name, 'version': version, 'family': family, 'lookback': lookback, 'unit': unit, 'formula': formula, 'uses_high_low_open': shape,
                    'uses_volume': family == 'volume'})

    for name, n, formula in (('body_fraction', 1, '|C-O|/(H-L)'), ('upper_wick_fraction', 1, '(H-max(O,C))/(H-L)'), ('lower_wick_fraction', 1, '(min(O,C)-L)/(H-L)'),
                             ('clv', 1, '(2C-H-L)/(H-L)'), ('open_close_return', 1, 'C/O-1'), ('range_fraction', 1, '(H-L)/C'), ('gap_close', 2, 'O/C[-1]-1'),
                             ('gap_high', 2, 'O/H[-1]-1'), ('gap_low', 2, 'O/L[-1]-1')):
        add(name, 'candle_geometry_v1', 'candlestick_geometry', n, 'fraction', formula + '; zero range gives NaN')
    add('true_range_fraction', 'atr14_ohlcv_v1', 'volatility', 2, 'fraction', 'max(H-L,|H-C[-1]|,|L-C[-1]|)/C')
    add('atr14_fraction', 'atr14_ohlcv_v1', 'volatility', 15, 'fraction', 'Wilder ATR14 (mean of first 14 TR, then (13*ATR+TR)/14) over C')
    add('range_expansion', 'atr14_ohlcv_v1', 'volatility', 16, 'ratio', 'TR / ATR14[-1]')
    for n in (20, 63):
        add(f'realized_vol{n}', 'atr14_ohlcv_v1', 'volatility', n + 1, 'annualized_fraction', f'sample sd of {n} log close returns * sqrt(252)')
    add('rvol20', 'rvol20_v1', 'volume', 21, 'ratio', 'V / mean(V[-20..-1])')
    add('volume_change', 'rvol20_v1', 'volume', 2, 'fraction', 'V/V[-1]-1')
    add('volume_percentile252', 'rvol20_v1', 'volume', 252, 'percentile', 'midrank of V among the last 252 volumes, 0-100')
    add('return_rvol', 'rvol20_v1', 'volume', 21, 'interaction', '(C/C[-1]-1) * rvol20')
    add('range_expansion_rvol', 'rvol20_v1', 'volume', 21, 'interaction', '(H-L)/mean((H-L)[-20..-1]) * rvol20')
    add('breakout_distance_rvol', 'rvol20_v1', 'volume', 21, 'interaction', '(C/max(C[-20..-1])-1) * rvol20')
    add('breakout_volume_confirmation', 'rvol20_v1', 'volume', 21, 'boolean', f'C > max(C[-20..-1]) and rvol20 >= {BREAKOUT_RVOL}')
    for n in (5, 10, 20, 63, 126, 252):
        add(f'return{n}', 'close_technical_vectorized_v1', 'momentum', n + 1, 'fraction', f'C/C[-{n}]-1')
    for n in (20, 50, 100, 200):
        add(f'sma{n}_distance', 'close_technical_vectorized_v1', 'trend', n, 'fraction', f'C/mean(last {n} C)-1')
    add('rsi14_wilder', 'close_technical_vectorized_v1', 'momentum', 15, 'index_0_100', 'Wilder 14; flat = 50')
    for basis, version, fib in (('ohlc', 'ohlcv_pivot_v1', 'fib_ohlcv_pivot_v1'), ('close', 'close_pivot_vectorized_v1', 'fib_close_pivot_vectorized_v1')):
        family, source = ('structure_ohlc', 'highs and lows') if basis == 'ohlc' else ('structure_close', 'closes')
        for name, unit, formula in ((f'{basis}_swing_high_distance', 'fraction', 'C / latest confirmed swing high - 1'),
                                    (f'{basis}_swing_low_distance', 'fraction', 'C / latest confirmed swing low - 1'),
                                    (f'{basis}_swing_high_age', 'sessions', 'sessions since the latest confirmed swing high bar'),
                                    (f'{basis}_swing_low_age', 'sessions', 'sessions since the latest confirmed swing low bar'),
                                    (f'{basis}_leg_direction', 'direction', '+1 when the latest completed leg ends above its start, else -1'),
                                    (f'{basis}_leg_size', 'fraction', 'B/A-1 of the latest completed leg'),
                                    (f'{basis}_leg_sessions', 'sessions', 'sessions from A to B'),
                                    (f'{basis}_leg_age', 'sessions', 'sessions since B'),
                                    (f'{basis}_position_in_leg', 'ratio', '(C-A)/(B-A)')):
            add(name, version, family, VARIABLE, unit, formula + f'; confirmed 3x3 pivots on {source}, known 3 sessions after the pivot')
        fam = 'fibonacci_ohlc' if basis == 'ohlc' else 'fibonacci_close'
        for kind, ratios in (('retracement', RETRACEMENTS), ('extension', EXTENSIONS)):
            for r in ratios:
                level = 'B-r(B-A)' if kind == 'retracement' else 'A+r(B-A)'
                add(f'fib_{basis}_{kind}_{r}_distance', fib, fam, VARIABLE, 'fraction', f'(C-level)/level, level={level}, r={r}, latest completed leg A to B')
                add(f'fib_{basis}_{kind}_{r}_atr_distance', fib, fam, VARIABLE, 'atr', f'(C-level)/ATR14, level={level}, r={r}')
        add(f'fib_{basis}_nearest_retracement_distance', fib, fam, VARIABLE, 'fraction', 'smallest |C-level|/level over the five retracements')
    return tuple(out)


DEFINITIONS = _definitions()
NAMES = tuple(d['name'] for d in DEFINITIONS)


def _rolling(values, n, how):
    """how(values[t-n+1..t]) for each t; NaN before n values exist or when the window holds a NaN."""
    out = np.full(len(values), np.nan)
    if len(values) >= n:
        windows = np.lib.stride_tricks.sliding_window_view(values, n)
        out[n - 1:] = how(windows, axis=1)
    return out


def _shift(values, by):
    out = np.full(len(values), np.nan)
    if by < len(values):
        out[by:] = values[:len(values) - by]
    return out


def _wilder(values, n):
    """Wilder smoothing: the mean of the first n values, then (prior*(n-1)+value)/n. Restarts after a NaN."""
    out = np.full(len(values), np.nan)
    run, total, state = 0, 0.0, np.nan
    for t, v in enumerate(values):
        if v != v:
            run, total, state = 0, 0.0, np.nan
            continue
        run += 1
        if run < n:
            total += v
        elif run == n:
            total += v
            state = total / n
            out[t] = state
        else:
            state = (state * (n - 1) + v) / n
            out[t] = state
    return out


def _rsi(close, n=14, restart=None):
    diff = close - _shift(close, 1)
    if restart is not None:
        diff = np.where(restart, np.nan, diff)                          # the change into a break session is not a price change
    gain = _wilder(np.where(diff != diff, np.nan, np.maximum(diff, 0.0)), n)
    loss = _wilder(np.where(diff != diff, np.nan, np.maximum(-diff, 0.0)), n)
    with np.errstate(invalid='ignore', divide='ignore'):
        value = 100.0 - 100.0 / (1.0 + gain / loss)
    value = np.where(loss == 0, np.where(gain > 0, 100.0, 50.0), value)
    return np.where(np.isfinite(gain) & np.isfinite(loss), value, np.nan)


def _percentile(values, n):
    out = np.full(len(values), np.nan)
    if len(values) >= n:
        windows = np.lib.stride_tricks.sliding_window_view(values, n)
        current = windows[:, -1:]
        with np.errstate(invalid='ignore'):
            rank = 100.0 * ((windows < current).sum(axis=1) + 0.5 * (windows == current).sum(axis=1)) / n
        out[n - 1:] = np.where(np.isfinite(windows).all(axis=1), rank, np.nan)
    return out


def _structure_features(prefix, close, high, low, atr, out):
    s = pivots.structure(high, low)
    t = np.arange(len(close), dtype=float)
    with np.errstate(invalid='ignore', divide='ignore'):
        out[f'{prefix}_swing_high_distance'] = close / s['swing_high_price'] - 1
        out[f'{prefix}_swing_low_distance'] = close / s['swing_low_price'] - 1
        out[f'{prefix}_swing_high_age'] = t - s['swing_high_index']
        out[f'{prefix}_swing_low_age'] = t - s['swing_low_index']
        a, b = s['leg_start_price'], s['leg_end_price']
        out[f'{prefix}_leg_direction'] = np.where(np.isfinite(a), np.where(b > a, 1.0, -1.0), np.nan)
        out[f'{prefix}_leg_size'] = b / a - 1
        out[f'{prefix}_leg_sessions'] = s['leg_end_index'] - s['leg_start_index']
        out[f'{prefix}_leg_age'] = t - s['leg_end_index']
        out[f'{prefix}_position_in_leg'] = (close - a) / (b - a)
        nearest = np.full(len(close), np.inf)
        for kind, ratios in (('retracement', RETRACEMENTS), ('extension', EXTENSIONS)):
            for r in ratios:
                level = b - float(r) * (b - a) if kind == 'retracement' else a + float(r) * (b - a)
                level = np.where(level > 0, level, np.nan)                 # a projected level at or below zero is not a price
                distance = (close - level) / level
                out[f'fib_{prefix}_{kind}_{r}_distance'] = distance
                out[f'fib_{prefix}_{kind}_{r}_atr_distance'] = (close - level) / np.where(atr > 0, atr, np.nan)
                if kind == 'retracement':
                    nearest = np.fmin(nearest, np.abs(distance))
        out[f'fib_{prefix}_nearest_retracement_distance'] = np.where(np.isfinite(nearest), nearest, np.nan)
    # the earliest bar each value depends on, for the comparability check
    starts = {name: s['leg_start_index'] for name in out if name.startswith((f'{prefix}_leg', f'{prefix}_position', f'fib_{prefix}_'))}
    starts[f'{prefix}_swing_high_distance'] = starts[f'{prefix}_swing_high_age'] = s['swing_high_index']
    starts[f'{prefix}_swing_low_distance'] = starts[f'{prefix}_swing_low_age'] = s['swing_low_index']
    # a pivot needs the three bars before it as well
    return {k: v - pivots.WINDOW for k, v in starts.items()}, {'pivots': s['pivots'], 'legs': s['legs'], 'outside_bars': s['outside_bars']}


LONGEST_FIXED_LOOKBACK = max(d['lookback'] for d in DEFINITIONS if d['lookback'] != VARIABLE)      # bars, the row's own bar included
LONGEST_VOLUME_LOOKBACK = max(d['lookback'] for d in DEFINITIONS if d['uses_volume'])


def compute(panel, break_mask=None, splits=()) -> dict:
    """{'values': {feature name: array over panel sessions}, 'audit': {...}}. NaN means unavailable at that session.

    ``break_mask`` marks the sessions prices cannot be compared across and ``splits`` the confirmed splits, both from
    ``adjust.breaks``."""
    count = len(panel['close'])
    present = np.asarray(panel['present'], bool)
    broken = np.zeros(count, bool) if break_mask is None else np.asarray(break_mask, bool)
    coarse = adjust.coarse_print(panel, splits)
    c = adjust.exact_close(panel, splits)
    # The shape of a bar is read from the vendor's own prints of that bar: open, high, low and close as printed, which
    # stand on one basis and keep the order they had on the day. ``scale`` is exactly 1 for a correct record, so the
    # prints are compared untouched; everything measured across sessions on the close uses the exact close ``c``.
    scale = adjust.reprint_scale(panel, splits)
    o, h, l, cp = (np.asarray(panel[k], float) * scale for k in ('open', 'high', 'low', 'close'))
    # Volume on one share basis: the shares that traded on the day (the middle of what the vendor's re-count allows, which
    # is the exact number wherever a whole number of shares fits only once) times the divisor. The vendor's own re-count
    # is that product rounded again, and for a thin day after a 3-for-2 the rounding is a third of the volume.
    fewest, most = adjust.volume_bounds(panel, splits)
    v = (fewest + most) / 2 * adjust.share_divisor(panel, splits)
    out = {}
    with np.errstate(invalid='ignore', divide='ignore'):
        span = h - l
        positive = np.where(span > 0, span, np.nan)
        out['body_fraction'] = np.abs(cp - o) / positive
        out['upper_wick_fraction'] = (h - np.maximum(o, cp)) / positive
        out['lower_wick_fraction'] = (np.minimum(o, cp) - l) / positive
        out['clv'] = (2 * cp - h - l) / positive
        out['open_close_return'] = cp / o - 1
        out['range_fraction'] = span / cp
        pc, pcp, ph, pl = _shift(c, 1), _shift(cp, 1), _shift(h, 1), _shift(l, 1)
        out['gap_close'], out['gap_high'], out['gap_low'] = o / pcp - 1, o / ph - 1, o / pl - 1
        tr = np.maximum(span, np.maximum(np.abs(h - pcp), np.abs(l - pcp)))
        tr = np.where(broken | coarse, np.nan, tr)                      # the smoothing restarts after a break, and after prices too coarse to give a range
        atr = _wilder(tr, 14)
        out['true_range_fraction'] = tr / cp
        out['atr14_fraction'] = atr / cp
        out['range_expansion'] = tr / _shift(atr, 1)
        logs = np.log(c / pc)
        for n in (20, 63):
            out[f'realized_vol{n}'] = _rolling(logs, n, lambda w, axis: np.std(w, axis=axis, ddof=1)) * np.sqrt(252.0)
        mean20 = _shift(_rolling(v, 20, np.mean), 1)
        rvol = np.where(mean20 > 0, v / mean20, np.nan)
        out['rvol20'] = rvol
        pv = _shift(v, 1)
        out['volume_change'] = np.where(pv > 0, v / pv - 1, np.nan)
        out['volume_percentile252'] = _percentile(v, 252)
        out['return_rvol'] = (c / pc - 1) * rvol
        mean_range = _shift(_rolling(span, 20, np.mean), 1)
        out['range_expansion_rvol'] = np.where(mean_range > 0, span / mean_range, np.nan) * rvol
        prior_high = _shift(_rolling(c, 20, np.max), 1)
        out['breakout_distance_rvol'] = (c / prior_high - 1) * rvol
        out['breakout_volume_confirmation'] = np.where(np.isfinite(prior_high) & np.isfinite(rvol), ((c > prior_high) & (rvol >= BREAKOUT_RVOL)).astype(float), np.nan)
        for n in (5, 10, 20, 63, 126, 252):
            # every bar of the window must exist, not only its two ends
            out[f'return{n}'] = np.where(np.isfinite(_rolling(c, n + 1, np.sum)), c / _shift(c, n) - 1, np.nan)
        for n in (20, 50, 100, 200):
            out[f'sma{n}_distance'] = c / _rolling(c, n, np.mean) - 1
        out['rsi14_wilder'] = _rsi(c, restart=broken)
    starts, audit = {}, {}
    for prefix, last, hi, lo in (('ohlc', cp, h, l), ('close', c, c, c)):
        first, info = _structure_features(prefix, last, hi, lo, atr, out)
        starts.update(first)
        audit[prefix] = info
    # What each value's window must not contain: a break after its first bar, a missing bar, and (for features that read
    # a high, low or open) a coarsely printed bar. Counted with running totals so a window is one subtraction.
    t = np.arange(count)
    seen_break, seen_missing, seen_coarse = np.cumsum(broken), np.cumsum(~present), np.cumsum(coarse)
    for d in DEFINITIONS:
        name = d['name']
        if d['lookback'] == VARIABLE:
            first = starts[name]
            begin = np.where(np.isfinite(first), first, 0).astype(int).clip(0, max(count - 1, 0))
            unusable = seen_missing[t] - seen_missing[begin] > 0        # a pivot or leg found before a missing bar is not carried across it
        else:
            begin = (t - d['lookback'] + 1).clip(0, max(count - 1, 0))
            unusable = np.zeros(count, bool)                            # a missing bar inside a fixed window already makes the value NaN
        unusable |= seen_break[t] - seen_break[begin] > 0               # a break strictly after the window's first bar and at or before T
        if d['uses_high_low_open']:
            before = np.where(begin > 0, seen_coarse[np.maximum(begin - 1, 0)], 0)
            unusable |= seen_coarse[t] - before > 0                     # any coarse bar in the window, its first bar included
        out[name] = np.where(unusable | ~present, np.nan, out[name])    # a session without a bar has no features
    audit['coarse_print_bars'] = int(coarse.sum())
    # The oldest bar a row reads. Two reaches, because they are found from different numbers:
    #   oldest_bar_read        the longest fixed window, or the start of the close-based pivot or leg the row stands on.
    #                          Found from the exact close only, so no later split can move it. A row's tier follows it.
    #   oldest_bar_read_shape  the same, or the start of the high/low pivot or leg if that is earlier. Found from the
    #                          vendor's reprinted highs and lows, so it may only feed an all-or-none decision.
    oldest = (t - LONGEST_FIXED_LOOKBACK + 1).astype(float)
    shape = oldest.copy()
    for name, first in starts.items():
        reach = np.where(np.isfinite(first), first, shape)
        shape = np.fmin(shape, reach)
        if name.startswith(('close_', 'fib_close_')):                   # pivots and legs on the exact close
            oldest = np.fmin(oldest, np.where(np.isfinite(first), first, oldest))
    return {'values': {name: out[name] for name in NAMES}, 'audit': audit, 'oldest_bar_read': oldest.clip(0).astype(int),
            'oldest_bar_read_shape': shape.clip(0).astype(int)}
