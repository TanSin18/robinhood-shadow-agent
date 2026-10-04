"""Checkpoint 8: OHLCV feature versions, the swing engine and high/low Fibonacci.

What is proven here: no value uses a bar after its own session; a later split leaves every earlier value where it was;
the array formulas equal the accepted Checkpoint 6 formulas; the swing engine run on closes reproduces
``close_fractal_3x3_v1`` exactly, so close-based and high/low-based structure differ in the price basis only; a pivot
is never visible before its confirmation; and a window that crosses a break or a missing bar is unavailable."""
from decimal import Decimal as D

import numpy as np
import pytest

import history_fixture as fx
from firm_lab.history import features, panel, pivots
from firm_lab.research_features import fibonacci as c6_fib, ohlcv as c6_ohlcv, structure as c6_structure, technical as c6
from firm_lab.research_features.types import SourceRef


def _panel(ticker='III', count=None):
    data = fx.series(ticker)
    n = count or len(data['sessions'])
    columns = {'sessions': data['sessions'][:n], 'open': [f'{v:.6f}' for v in data['open'][:n]], 'high': [f'{v:.6f}' for v in data['high'][:n]],
               'low': [f'{v:.6f}' for v in data['low'][:n]], 'close': [f'{v:.6f}' for v in data['close'][:n]], 'volume': [f'{v:.1f}' for v in data['volume'][:n]],
               'close_unadjusted': [f'{v:.4f}' for v in data['unadjusted'][:n]], 'close_total_return': [f'{v:.6f}' for v in data['total'][:n]]}
    return panel.from_columns(columns), columns


def test_the_feature_versions_are_new_and_named_and_nothing_is_in_dollars():
    versions = {d['version'] for d in features.DEFINITIONS}
    assert {'candle_geometry_v1', 'atr14_ohlcv_v1', 'rvol20_v1', 'ohlcv_pivot_v1', 'fib_ohlcv_pivot_v1'} <= versions
    assert 'close_fractal_3x3_v1' not in versions and pivots.CLOSE_PIVOT_VERSION == 'close_fractal_3x3_v1' == c6_structure.PIVOT_VERSION     # the accepted version is not redefined
    assert len({d['name'] for d in features.DEFINITIONS}) == len(features.DEFINITIONS)
    assert not [d for d in features.DEFINITIONS if d['unit'] in ('price', 'shares', 'currency')]
    ratios = {float(d['name'].split('_')[3]) for d in features.DEFINITIONS if d['name'].startswith('fib_ohlc_') and d['name'].endswith('_distance') and 'atr' not in d['name']
              and 'nearest' not in d['name']}
    assert ratios == {0.236, 0.382, 0.5, 0.618, 0.786, 1.272, 1.618}
    assert features.RETRACEMENTS == c6_fib.RETRACEMENTS and features.EXTENSIONS == c6_fib.EXTENSIONS


def test_no_value_uses_a_bar_after_its_own_session():
    full, _ = _panel()
    whole = features.compute(full)['values']
    for cut in (300, 777, 1234):
        part, _ = _panel(count=cut)
        prefix = features.compute(part)['values']
        for name in features.NAMES:
            np.testing.assert_array_equal(prefix[name], whole[name][:cut], err_msg=name)        # bit for bit: the future does not exist for the past


def test_a_later_split_leaves_every_earlier_feature_where_it_was():
    base, columns = _panel()
    k = 7.0
    scaled = dict(columns)
    for name in ('open', 'high', 'low', 'close', 'close_total_return'):
        scaled[name] = [f'{float(v) / k:.9f}' for v in columns[name]]
    scaled['volume'] = [f'{float(v) * k:.3f}' for v in columns['volume']]
    a, b = features.compute(base)['values'], features.compute(panel.from_columns(scaled))['values']
    for name in features.NAMES:
        np.testing.assert_allclose(a[name], b[name], rtol=1e-6, atol=1e-7, equal_nan=True, err_msg=name)


def test_the_array_formulas_equal_the_accepted_checkpoint_6_formulas():
    p, columns = _panel(count=420)
    values = features.compute(p)['values']
    closes = [D(v) for v in columns['close']]
    bars = [{k: D(columns[k][i]) for k in ('open', 'high', 'low', 'close', 'volume')} for i in range(len(closes))]
    for t in (60, 251, 300, 419):
        seen = closes[:t + 1]
        expected = {'return5': c6.simple_return(seen, 5), 'return20': c6.simple_return(seen, 20), 'return63': c6.simple_return(seen, 63),
                    'return252': c6.simple_return(seen, 252), 'rsi14_wilder': c6.rsi_wilder(seen), 'realized_vol20': c6.realized_vol(seen, 20),
                    'realized_vol63': c6.realized_vol(seen, 63), 'sma20_distance': seen[-1] / c6.sma(seen, 20) - 1,
                    'sma200_distance': seen[-1] / c6.sma(seen, 200) - 1 if c6.sma(seen, 200) is not None else None}
        window = bars[:t + 1]
        geometry = c6_ohlcv.geometry(window[-1]['open'], window[-1]['high'], window[-1]['low'], window[-1]['close'], window[-2]['close'], window[-2]['high'], window[-2]['low'])
        expected.update({k: geometry[k] for k in ('body_fraction', 'upper_wick_fraction', 'lower_wick_fraction', 'clv', 'open_close_return', 'gap_close', 'gap_high', 'gap_low')})
        ranges = [c6_ohlcv.true_range(b['high'], b['low'], a['close']) for a, b in zip(window, window[1:])]
        expected['atr14_fraction'] = c6_ohlcv.atr(ranges) / window[-1]['close']
        volume = c6_ohlcv.volume_metrics([b['volume'] for b in window])
        expected.update({'rvol20': volume['rvol20'], 'volume_change': volume['volume_change'], 'volume_percentile252': volume['volume_percentile252']})
        for name, want in expected.items():
            if want is None:
                assert np.isnan(values[name][t]), (name, t)
            else:
                assert values[name][t] == pytest.approx(float(want), rel=1e-9, abs=1e-12), (name, t)


def _close_bars(columns):
    ref = SourceRef('feature_observations', 'x', 'a' * 64, '2026-10-01T00:00:00+00:00')
    return [{'session': s, 'value': v, 'known_at': '2026-10-01T00:00:00+00:00', 'ref': ref} for s, v in zip(columns['sessions'], columns['close'])]


def test_the_engine_on_closes_reproduces_close_fractal_3x3_v1_pivots_legs_and_levels():
    p, columns = _panel(count=600)
    close = p['close']
    theirs = c6_structure.confirmed_pivots(_close_bars(columns))
    mine = pivots.confirmed(close, close)
    assert [(columns['sessions'][i], 'HIGH' if k == pivots.HIGH else 'LOW') for i, k in zip(mine['index'], mine['kind'])] == [(q['session'], q['type']) for q in theirs]
    assert [columns['sessions'][i] for i in mine['confirmed_at']] == [q['confirmed_session'] for q in theirs]
    their_legs = c6_structure.completed_legs(theirs)
    my_legs = pivots.legs(mine)
    assert [(columns['sessions'][a], columns['sessions'][b]) for _, a, _, b, _ in my_legs] == [(l['start']['session'], l['end']['session']) for l in their_legs]
    assert len(my_legs) > 20
    values = features.compute(p)['values']
    last = their_legs[-1]
    levels = c6_fib.directed_levels(D(last['start']['value']), D(last['end']['value']))
    current = D(columns['close'][-1])
    for key, level in levels.items():
        kind, ratio = key.split('_')
        assert values[f'fib_close_{kind}_{ratio}_distance'][-1] == pytest.approx(float((current - level) / level), rel=1e-9), key


def test_a_pivot_is_not_visible_before_its_third_following_session_has_closed():
    high = np.array([10, 11, 12, 15, 12, 11, 10, 9.5, 9, 8, 9, 10, 11, 12], float)
    low = high - 1.0
    found = pivots.confirmed(high, low)
    assert list(found['index']) == [3, 9] and list(found['kind']) == [pivots.HIGH, pivots.LOW] and list(found['confirmed_at']) == [6, 12]
    s = pivots.structure(high, low)
    assert np.all(np.isnan(s['swing_high_price'][:6])) and s['swing_high_price'][6] == 15 and s['swing_high_index'][6] == 3
    assert np.all(np.isnan(s['swing_low_price'][:12])) and s['swing_low_price'][12] == 7           # the low of the swing-low bar, not its high
    assert np.all(np.isnan(s['leg_end_price'][:12])) and (s['leg_start_price'][12], s['leg_end_price'][12]) == (15, 7)      # the leg exists once its end is confirmed
    for cut in range(7, 14):                                           # truncating the future never changes what was known
        part = pivots.structure(high[:cut], low[:cut])
        np.testing.assert_array_equal(part['swing_high_price'], s['swing_high_price'][:cut])
        np.testing.assert_array_equal(part['leg_end_price'], s['leg_end_price'][:cut])


def test_ties_and_outside_bars_are_not_pivots_and_a_gap_in_the_bars_blocks_a_pivot():
    flat = np.array([10, 11, 12, 15, 15, 11, 10, 9, 8, 7], float)
    assert len(pivots.confirmed(flat, flat - 1)['index']) == 0                                    # 15 is not strictly above its neighbour
    high = np.array([10, 10, 10, 20, 10, 10, 10], float)
    low = np.array([9, 9, 9, 1, 9, 9, 9], float)
    outside = pivots.confirmed(high, low)
    assert len(outside['index']) == 0 and outside['outside_bars'] == 1                            # highest high and lowest low on one bar: no direction
    gap = np.array([10, 11, 12, 15, 12, np.nan, 10], float)
    assert len(pivots.confirmed(gap, gap - 1)['index']) == 0


def test_high_low_fibonacci_levels_follow_the_latest_completed_leg():
    high = np.array([10, 11, 12, 15, 12, 11, 10, 9.5, 9, 8, 9, 10, 11, 12], float)
    low = high - 1.0
    close = high - 0.5
    columns = {'sessions': list(fx.SESSIONS[:14]), 'open': [str(v) for v in close], 'high': [str(v) for v in high], 'low': [str(v) for v in low],
               'close': [str(v) for v in close], 'volume': ['100'] * 14, 'close_unadjusted': [str(v) for v in close], 'close_total_return': [str(v) for v in close]}
    values = features.compute(panel.from_columns(columns))['values']
    a, b, c = 15.0, 7.0, close[12]                                    # leg from the swing high (high 15) down to the swing low (low 7)
    assert values['ohlc_leg_direction'][12] == -1 and values['ohlc_leg_size'][12] == pytest.approx(b / a - 1)
    for r in ('0.236', '0.5', '0.786'):
        level = b - float(r) * (b - a)
        assert values[f'fib_ohlc_retracement_{r}_distance'][12] == pytest.approx((c - level) / level)
    level = a + 1.618 * (b - a)                                       # 15 - 12.944 = 2.056
    assert values['fib_ohlc_extension_1.618_distance'][12] == pytest.approx((c - level) / level)
    assert np.all(np.isnan(values['fib_ohlc_retracement_0.5_distance'][:12]))
    assert values['ohlc_position_in_leg'][12] == pytest.approx((c - a) / (b - a))
    # the close-based leg runs 14.5 to 7.5: a different leg, so a different level (the 50% levels happen to coincide here; the others do not)
    close_level = 7.5 - 0.236 * (7.5 - 14.5)
    assert values['fib_close_retracement_0.236_distance'][12] == pytest.approx((c - close_level) / close_level)
    assert values['fib_close_retracement_0.236_distance'][12] != pytest.approx(values['fib_ohlc_retracement_0.236_distance'][12])


def test_a_projected_level_at_or_below_zero_is_not_a_price():
    high = np.array([10, 11, 12, 40, 12, 11, 10, 9.5, 9, 3, 9, 10, 11, 12], float)
    low = high - 1.0
    columns = {'sessions': list(fx.SESSIONS[:14]), 'open': [str(v) for v in high], 'high': [str(v) for v in high], 'low': [str(v) for v in low],
               'close': [str(v) for v in high], 'volume': ['100'] * 14, 'close_unadjusted': [str(v) for v in high], 'close_total_return': [str(v) for v in high]}
    values = features.compute(panel.from_columns(columns))['values']
    assert np.isnan(values['fib_ohlc_extension_1.272_distance'][12]) and np.isnan(values['fib_ohlc_extension_1.618_distance'][12])    # 40 + 1.272*(2-40) < 0
    assert np.isfinite(values['fib_ohlc_retracement_0.5_distance'][12])


def test_a_window_that_crosses_a_break_or_a_missing_bar_is_unavailable():
    p, columns = _panel(count=400)
    mask = np.zeros(400, bool)
    mask[300] = True
    values = features.compute(p, mask)['values']
    plain = features.compute(p)['values']
    assert np.isfinite(values['return20'][299]) and np.all(np.isnan(values['return20'][300:320])) and values['return20'][320] == plain['return20'][320]
    assert np.all(np.isnan(values['return63'][300:363])) and np.isfinite(values['return63'][363])
    assert values['body_fraction'][300] == plain['body_fraction'][300]                               # a single-bar feature crosses nothing
    assert np.isnan(values['gap_close'][300]) and np.isfinite(values['gap_close'][301])              # the gap on the break session is the break itself
    assert np.all(np.isnan(values['volume_percentile252'][300:400]))
    leg_start = pivots.structure(p['high'], p['low'])['leg_start_index']
    for t in range(300, 400):
        crosses = leg_start[t] - pivots.WINDOW < 300
        assert np.isnan(values['fib_ohlc_retracement_0.5_distance'][t]) == bool(crosses or np.isnan(plain['fib_ohlc_retracement_0.5_distance'][t])), t
    holed = {k: list(v) for k, v in columns.items()}
    for name in holed:
        del holed[name][350]                                                                         # one exchange session with no bar
    gap = panel.from_columns(holed)
    assert len(gap['sessions']) == 400 and not gap['present'][350]
    after = features.compute(gap)['values']
    assert all(np.isnan(after[name][350]) for name in features.NAMES)                                # no bar, no features
    assert np.all(np.isnan(after['return20'][350:371])) and np.isfinite(after['return20'][371])
    assert np.all(np.isnan(after['atr14_fraction'][350:365])) and np.isfinite(after['atr14_fraction'][365])    # the smoothing restarts after the gap


def test_volume_features_describe_volume_only():
    text = ' '.join(d['formula'] + d['name'] for d in features.DEFINITIONS).lower() + (features.__doc__ or '').lower()
    for word in ('institutional', 'smart money', 'accumulation', 'buy signal', 'sell signal'):
        assert word not in text
    p, _ = _panel(count=300)
    confirmation = features.compute(p)['values']['breakout_volume_confirmation']
    assert set(np.unique(confirmation[np.isfinite(confirmation)])) <= {0.0, 1.0}
