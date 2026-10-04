"""Checkpoint 8 review regressions. Each test was written to fail on the code it was found in, then the code was repaired.

Compliance and point-in-time integrity findings live here so that a later change cannot quietly undo a repair."""
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from firm_lab.errors import FirmLabError

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs' / 'firm_lab'


class _Recorder:
    """A transport that answers nothing and remembers what it was asked."""
    def __init__(self):
        self.urls = []

    def get(self, url, headers=None):
        from firm_lab_collectors.transport import Response
        self.urls.append(url)
        return Response(404, b'', url, '2026-10-04T16:00:00+00:00', 'not found', {})


# ---------------------------------------------------------------------------------------- licensing: FRED and ALFRED
def test_no_collector_asks_fred_or_alfred_and_no_fred_sourced_row_can_be_stored(tmp_path):
    """The St. Louis Fed terms prohibit, without written consent, storing FRED content and using it to develop or train
    machine-learning systems. Checkpoint 5's sample capture saved FRED and ALFRED answers to files, and the macro store
    accepted FRED as a source. Neither may remain."""
    from firm_lab import macro
    from firm_lab_collectors import capture
    public, keyed = _Recorder(), _Recorder()
    out = capture.run_macro(tmp_path / 'capture', environ={'FIRM_LAB_FRED_API_KEY': 'a' * 32}, transport=public, keyed_transport=keyed)
    assert public.urls and not [u for u in public.urls + keyed.urls if 'stlouisfed' in u]
    assert not keyed.urls and 'fred_api_key_present' not in out
    for path in sorted((ROOT / 'firm_lab_collectors').glob('*.py')):
        assert 'stlouisfed.org' not in path.read_text(), path.name
    assert 'FRED' not in macro.SOURCE_HOSTS and not [name for name, spec in macro.SERIES.items() if 'FRED' in spec[3]]
    raw = b'{"synthetic_fixture":true}'
    row = dict(series='unemployment_rate', value='4.3', unit='percent', period='2026-08', source='FRED',
               source_url='https://fred.stlouisfed.org/series/UNRATE', source_timestamp='2026-09-04T12:30:00Z', published_at='2026-09-04T12:30:00Z',
               ingested_at='2026-09-04T12:31:00Z', revision=0, source_hash=hashlib.sha256(raw).hexdigest())
    with pytest.raises(FirmLabError, match='SERIES_SOURCE_MISMATCH'):
        macro.validate_observation(row, raw=raw, now=datetime(2026, 10, 3, 16, tzinfo=timezone.utc))


# ------------------------------------------------------------------- review round 1 (independent reviewer A, commit 2c8a5c4)
import numpy as np

import history_fixture as fx
from firm_lab.history import adjust, features, panel


def _columns(ticker='III', lo=0, hi=None, *, factor=None, decimals=6, unadjusted_decimals=4, price=None):
    """Vendor-shaped columns for one invented security. ``factor`` is unadjusted close over adjusted close, per session:
    the unadjusted close is the price printed on the day (it drops where the factor steps down, as at a split) and the
    adjusted prices are on the share basis of the last session, so they are continuous."""
    d = fx.series(ticker)
    hi = hi or len(d['sessions'])
    scale = (price / d['close'][0]) if price else 1.0
    f = np.ones(hi) if factor is None else np.asarray(factor, float)[:hi]
    text = lambda values, places: [f'{v:.{places}f}' for v in values[lo:hi]]
    return {'sessions': d['sessions'][lo:hi], 'open': text(d['open'][:hi] * scale / f[0], decimals), 'high': text(d['high'][:hi] * scale / f[0], decimals),
            'low': text(d['low'][:hi] * scale / f[0], decimals), 'close': text(d['close'][:hi] * scale / f[0], decimals), 'volume': text(d['volume'][:hi] * f[0], 1),
            'close_unadjusted': text(d['close'][:hi] * scale * f / f[0], unadjusted_decimals), 'close_total_return': text(d['close'][:hi] * scale / f[0], decimals)}


def test_a_break_restarts_wilder_smoothing_so_no_price_from_before_it_survives():
    """ATR and RSI are recursive. The recursion carried pre-break prices past a break indefinitely while the declared
    lookback of 15 bars let the values through after 14 sessions (and the ATR-distance features even earlier)."""
    n, b = 600, 300
    step = np.r_[np.full(b, 3.0), np.ones(n - b)]                   # an unexplained 3x step in the factor at b
    mask = np.zeros(n, bool)
    mask[b] = True
    served = features.compute(panel.from_columns(_columns(hi=n, factor=step, decimals=9, unadjusted_decimals=9)), mask)['values']
    clean = features.compute(panel.from_columns(_columns(lo=b, hi=n, decimals=9, unadjusted_decimals=9)))['values']       # the same bars, nothing before the break
    names = ['atr14_fraction', 'rsi14_wilder', 'range_expansion'] + [n_ for n_ in features.NAMES if n_.endswith('_atr_distance')]
    for name in names:
        for t in range(0, n - b):
            a, c = served[name][b + t], clean[name][t]
            assert np.isnan(a) or a == pytest.approx(c, rel=1e-4, abs=1e-7), (name, t, a, c)      # equal up to the rounding of the printed prices
        assert np.isfinite(served[name][b + 60:]).any(), name
    assert np.all(np.isnan(served['atr14_fraction'][b:b + 14])) and served['atr14_fraction'][b + 14] == pytest.approx(clean['atr14_fraction'][14], rel=1e-4)
    assert np.all(np.isnan(served['rsi14_wilder'][b:b + 14])) and served['rsi14_wilder'][b + 14] == pytest.approx(clean['rsi14_wilder'][14], rel=1e-4)


def test_a_later_split_reprinted_at_fixed_decimals_does_not_move_any_close_based_feature_before_it():
    """A vendor reprints adjusted prices after a split at a fixed number of decimals. For a 50-for-1 split that turns a
    40-dollar history into prices near 0.80 printed to three decimals, and the rounding moved almost every feature
    before the split. Close-based features now come from the unadjusted close and the confirmed split ratios."""
    n, at = 900, 800
    plain = panel.from_columns(_columns(hi=n, decimals=3, price=100.0))
    split = panel.from_columns(_columns(hi=n, decimals=3, price=100.0, factor=np.r_[np.full(at, 2500.0), np.ones(n - at)]))      # adjusted prices near 0.04, three decimals
    action = [{'type': 'split', 'effective_date': split['sessions'][at], 'value': '2500'}]
    audit = adjust.breaks(split, action)
    assert audit['breaks'] == [] and audit['splits_confirmed'] == 1 and audit['splits'] == [(at, 2500.0)]
    a = features.compute(plain)['values']
    b = features.compute(split, adjust.break_mask(split, audit['breaks']), splits=audit['splits'])['values']
    close_based = [d['name'] for d in features.DEFINITIONS if not d['uses_high_low_open'] and d['family'] != 'volume']
    assert {'return5', 'return252', 'sma200_distance', 'rsi14_wilder', 'realized_vol20', 'close_swing_high_distance', 'fib_close_retracement_0.5_distance'} <= set(close_based)
    for name in close_based:
        np.testing.assert_allclose(b[name][:at], a[name][:at], rtol=1e-9, atol=1e-12, equal_nan=True, err_msg=name)
        assert np.isfinite(b[name][300:at]).any(), name
    # what the prints cannot support is said, not served: where the adjusted print is coarser than 0.05% of price, the
    # high/low/open features are unavailable
    assert adjust.coarse_print(split)[:at].all() and not adjust.coarse_print(plain).any()
    for name in ('body_fraction', 'atr14_fraction', 'ohlc_swing_high_distance', 'fib_ohlc_retracement_0.5_distance', 'fib_close_retracement_0.5_atr_distance'):
        assert np.all(np.isnan(b[name][:at])) and np.isfinite(a[name][300:at]).any(), name
    assert 'atr14_fraction' not in __import__('firm_lab.history.dataset', fromlist=['x']).CORE_FEATURES      # eligibility must not depend on print precision


def test_whether_a_dividend_is_a_break_does_not_depend_on_a_later_split():
    """An 80-cent dividend on a 600-dollar stock is 0.13% of price. After a later 40-for-1 split the adjusted close is 15
    and the same 0.80 looked like 5.3%, so every ordinary dividend of a stock that later split became a break."""
    n = 300
    dividend = lambda day, value: [{'type': 'cash_dividend', 'effective_date': day, 'value': value}]
    for later_split in (1.0, 40.0):
        p = panel.from_columns(_columns(hi=n, price=600.0, factor=np.full(n, later_split), unadjusted_decimals=2))
        assert adjust.breaks(p, dividend(p['sessions'][100], '0.80'))['breaks'] == [], later_split
    # a real one-off distribution of a tenth of the price is a break with or without a later split
    found = {}
    for later_split in (1.0, 40.0):
        columns = _columns('FFF', factor=np.full(len(fx.series('FFF')['sessions']), later_split))
        tr = fx.series('FFF')['total'] / later_split
        columns['close_total_return'] = [f'{v:.6f}' for v in tr]
        p = panel.from_columns(columns)
        paid = fx.DISTRIBUTION[2] * fx.series('FFF')['unadjusted'][p['sessions'].index(fx.DISTRIBUTION[1]) - 1]
        found[later_split] = [(b['session'], b['reason'], round(b['share_of_prior_close'], 3)) for b in adjust.breaks(p, dividend(fx.DISTRIBUTION[1], f'{paid:.4f}'))['breaks']]
    assert found[1.0] == found[40.0] == [('2020-05-11', 'LARGE_DISTRIBUTION', 0.1)]


def test_structure_features_do_not_reach_across_a_missing_bar():
    columns = _columns(hi=400)
    for name in columns:
        del columns[name][350]
    p = panel.from_columns(columns)
    values = features.compute(p)['values']
    whole = features.compute(panel.from_columns(_columns(hi=400)))['values']
    for name in ('ohlc_leg_size', 'ohlc_swing_high_distance', 'fib_ohlc_retracement_0.5_distance', 'close_leg_size', 'fib_close_extension_1.272_distance'):
        assert np.isfinite(whole[name][351:365]).all(), name
        assert np.all(np.isnan(values[name][351:358])), name          # the leg and its pivots lie before the gap
    assert np.isfinite(values['ohlc_leg_size'][385:]).any()            # a leg formed entirely after the gap is served again


def test_an_inverted_split_adjustment_is_a_break_not_a_confirmed_split():
    """Either split convention is read, but the adjusted series must be continuous across the split. A factor that steps
    the wrong way (prices before the split multiplied instead of divided) matched the other convention and passed."""
    n, at = 400, 200
    columns = _columns(hi=n, factor=np.r_[np.full(at, 2.0), np.ones(n - at)])
    good = panel.from_columns(columns)
    inverted = {k: list(v) for k, v in columns.items()}
    for name in ('open', 'high', 'low', 'close', 'close_total_return'):
        inverted[name][:at] = [f'{float(x) * 4:.6f}' for x in columns[name][:at]]        # the factor before the split is now 0.5 instead of 2
    bad = panel.from_columns(inverted)
    action = [{'type': 'split', 'effective_date': good['sessions'][at], 'value': '2.0'}]
    assert adjust.breaks(good, action)['splits_confirmed'] == 1 and adjust.breaks(good, action)['splits'] == [(at, 2.0)]
    found = adjust.breaks(bad, action)
    assert found['splits_confirmed'] == 0 and found['splits'] == [] and [b['reason'] for b in found['breaks']] == ['SPLIT_FACTOR_WITHOUT_ACTION']
    assert 'not continuous' in found['breaks'][0]['note']


def test_print_precision_is_read_from_the_column_and_small_input_oddities_fail_safe():
    columns = _columns(hi=60, decimals=2, price=29.0)
    columns['close'][10] = columns['close'][10].rstrip('0').rstrip('.')             # a vendor that strips trailing zeros: "29" for 29.00
    p = panel.from_columns(columns)
    assert p['half_ulp'][10] == pytest.approx(p['half_ulp'][11], rel=0.2) and p['half_ulp'][10] < 0.001      # two decimals, not zero decimals
    stamped = panel.from_columns(_columns(hi=400, factor=np.r_[np.full(200, 2.0), np.ones(200)]))
    day = stamped['sessions'][200]
    assert adjust.breaks(stamped, [{'type': 'split', 'effective_date': day + 'T00:00:00', 'value': '2'}])['breaks'] == []        # a timestamp is read as its date
    twice = panel.from_columns(_columns(hi=400, factor=np.r_[np.full(200, 6.0), np.ones(200)]))
    both = [{'type': 'split', 'effective_date': day, 'value': '2'}, {'type': 'split', 'effective_date': day, 'value': '3'}]
    assert adjust.breaks(twice, both)['breaks'] == [] and adjust.breaks(twice, both)['splits'] == [(200, 6.0)]      # two splits on one day multiply
    broken = _columns(hi=20)
    broken['close'][5] = '0'
    with pytest.raises(ValueError, match='INVALID_STORED_BAR'):
        panel.from_columns(broken)
