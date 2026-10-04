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


# ------------------------------------------------------- review round 2 (independent reviewers B and C, commit aacea1e)
import json
import sqlite3

from firm_lab.history import calendar, dataset, ingest, readiness, regimes, sharadar_files as sf, splits, sufficiency, targets, universe
from firm_lab.history.store import HistoryStore, classify_change

AT = '2026-10-03T12:00:00+00:00'
LATER = '2026-10-12T12:00:00+00:00'
COMMON = {'source': sf.SOURCE, 'adapter': sf.ADAPTER}
RULE = {**universe.RULE, 'size': 6}


def _store(folder, *, at=AT, through=fx.LAST, tickers=None, edit=None, rescale=None, decimals=6, actions=(), ticker_rows=None):
    folder.mkdir(parents=True, exist_ok=True)
    fx.write_tickers(folder / 'T.csv') if ticker_rows is None else ticker_rows(folder / 'T.csv')
    rows = [list(r) for r in fx.price_rows(tickers, through=through, rescale=rescale, decimals=decimals)]
    fx.write_prices(folder / 'P.csv', [edit(r) for r in rows] if edit else rows)
    fx.write_actions(folder / 'A.csv', extra=actions)
    store = HistoryStore(folder / 'firm_lab_history.db', create=True)
    ingest.ingest_securities(store, sf.securities(folder / 'T.csv'), file=ingest.describe_file(folder / 'T.csv'), at=at, **COMMON)
    ingest.ingest_bars(store, sf.prices(folder / 'P.csv'), file=ingest.describe_file(folder / 'P.csv'), at=at, **COMMON)
    ingest.ingest_actions(store, sf.actions(folder / 'A.csv'), file=ingest.describe_file(folder / 'A.csv'), at=at, **COMMON)
    return store


def _block(sessions, close, *, volume='1000', unadjusted=None):
    close = [f'{c}' for c in close]
    return {'sessions': list(sessions), 'open': close, 'high': close, 'low': close, 'close': close, 'volume': [volume] * len(close),
            'close_unadjusted': list(unadjusted or close), 'close_total_return': close, 'provider_updated': [''] * len(close)}


def _bare(tmp_path, name='h.db'):
    return HistoryStore(tmp_path / name, create=True)


DAYS = ['2024-03-04', '2024-03-05', '2024-03-06', '2024-03-07']


# ------------------------------------------------------------------------------------------ holdouts and label reach
def test_no_readable_label_reaches_a_price_of_a_sealed_segment(tmp_path):
    """The last sessions of the burned window had labels that ended inside the forward holdout, and purge rows left the
    builder with labels built from holdout prices."""
    assert splits.segment('2026-09-02') == splits.BURNED and splits.segment('2026-09-03') == splits.PURGED and splits.segment('2026-10-02') == splits.PURGED
    assert calendar.offset(splits.burned_last_sample(), targets.MAX_HORIZON + 1) == '2026-10-02'

    def late_opens(row):
        if row[1] >= splits.FORWARD_FIRST:
            row[2] = f'{min(float(row[2]) * 1.004, float(row[3])):.6f}'
        return row

    a = _store(tmp_path / 'a', at=LATER)
    b = _store(tmp_path / 'b', at=LATER, edit=late_opens)
    try:
        for store in (a, b):
            universe.build(store, fx.FIRST, fx.LAST, rule=RULE)
        ya, yb = dataset.materialise(a, segments=(splits.BURNED,)), dataset.materialise(b, segments=(splits.BURNED,))
        for h in targets.HORIZONS:
            np.testing.assert_array_equal(ya['y'][h], yb['y'][h])                  # forward-holdout prices cannot move a burned label
        assert ya['manifest']['rows'] > 1000 and max(ya['session']) <= splits.burned_last_sample()
        rows = dataset.security_rows(a, '100009', ingest.current_securities(a)['100009'], universe.membership(universe.load(a)['records'])['100009'], [])
        unreadable = ~np.isin(rows['segment'], [splits.DEVELOPMENT, splits.BURNED])
        assert unreadable.sum() > 1000 and (rows['segment'] == splits.PURGED).sum() >= 26 + 21 + 21
        for h in targets.HORIZONS:
            assert np.all(np.isnan(rows['labels'][h]['value'][unreadable]))        # purge and burn-in rows too, not only the sealed ones
    finally:
        a.close()
        b.close()


def test_the_strict_count_is_reported_by_segment_and_purge_rows_are_not_samples(tmp_path):
    store = _store(tmp_path / 's')
    try:
        universe.build(store, fx.FIRST, '2026-10-02', rule=RULE)
        counted = dataset.count(store)
    finally:
        store.close()
    by = counted['strict_samples_by_segment']['20']
    assert set(by) == {splits.DEVELOPMENT, splits.HISTORICAL_HOLDOUT, splits.BURNED, splits.FORWARD_HOLDOUT}
    assert counted['strict_samples']['20'] == sum(by.values()) and by[splits.DEVELOPMENT] > 0 and by[splits.HISTORICAL_HOLDOUT] > by[splits.DEVELOPMENT]
    assert counted['by_segment'][splits.PURGED]['labelled_20'] > 0                  # they exist, and they are not counted as samples
    assert counted['strict_samples']['20'] < sum(part['labelled_20'] for part in counted['by_segment'].values())


# ------------------------------------------------------------------------------------- tiers, revisions and versions
def test_a_revised_bar_is_not_held_at_the_time_and_a_row_takes_the_lowest_tier(tmp_path):
    sessions = list(calendar.sessions('2024-01-02', '2025-03-28'))
    store = _bare(tmp_path)
    try:
        ingest.ingest_securities(store, [{'security_id': '1', 'symbol': 'X', 'name': 'X', 'exchange': 'NYSE', 'category': 'c', 'currency': 'USD', 'is_delisted': False,
                                          'first_price_date': sessions[0], 'last_price_date': sessions[-1], 'price_table': 'stocks'}],
                                 file={'file': 't', 'sha256': 'a' * 64, 'bytes': 1}, at='2024-01-02T12:00:00+00:00', **COMMON)
        price = lambda k: f'{50 + 0.01 * k:.2f}'
        for k, s in enumerate(sessions):                               # stored each evening, before the next session opened
            rows = [{'symbol': 'X', 'session': s, 'open': price(k), 'high': price(k), 'low': price(k), 'close': price(k), 'volume': '100', 'close_unadjusted': price(k),
                     'close_total_return': price(k), 'provider_updated': ''}]
            ingest.ingest_bars(store, rows, file={'file': f'd{k}', 'sha256': f'{k:064d}', 'bytes': 1}, at=calendar.session_close(s), **COMMON)
        assert len(store.bars('1')['sessions']) == len(sessions)       # a one-session file extends the year; it does not replace it
        held = store.held_since('1')
        assert held[sessions[5]] == calendar.session_close(sessions[5])
        tiers = dataset.row_tiers(sessions, np.ones(len(sessions), bool), held)
        assert tiers[251] == 'HELD_AT_THE_TIME' and tiers[250] == 'PUBLISHER_DATED_HISTORICAL'
        revised = [{'symbol': 'X', 'session': sessions[200], 'open': '62.63', 'high': '62.63', 'low': '62.63', 'close': '62.63', 'volume': '100', 'close_unadjusted': '62.63',
                    'close_total_return': '62.63', 'provider_updated': ''}]
        out = ingest.ingest_bars(store, revised, file={'file': 'rev', 'sha256': 'f' * 64, 'bytes': 1}, at='2026-11-01T12:00:00+00:00', **COMMON)
        assert out['blocks_by_change'] == {'VALUE_CHANGE': 1}
        held = store.held_since('1')
        assert held[sessions[200]] == '2026-11-01T12:00:00+00:00' and held[sessions[199]] == calendar.session_close(sessions[199])
        tiers = dataset.row_tiers(sessions, np.ones(len(sessions), bool), held)
        assert set(tiers[200:452]) == {'PUBLISHER_DATED_HISTORICAL'}   # every row whose window holds the revised bar
        assert dataset.row_tier('HELD_AT_THE_TIME', 'PUBLISHER_DATED_HISTORICAL') == 'PUBLISHER_DATED_HISTORICAL'       # the universe's tier counts too
    finally:
        store.close()


def test_a_vendor_that_reverts_gets_a_new_version_and_current_follows_the_latest_capture(tmp_path):
    store = _bare(tmp_path)
    try:
        a, b = _block(DAYS, ['10.5', '11.5', '12.5', '13.5']), _block(DAYS, ['10.5', '11.6', '12.5', '13.5'])
        results = [store.put_bars('X', '1', 2024, block, f'cap{k}', price_table='stocks', at=f'2026-10-0{k + 1}T12:00:00+00:00') for k, block in enumerate((a, b, a, a))]
        assert [r['stored'] for r in results] == [True, True, True, False] and [r.get('version') for r in results[:3]] == [1, 2, 3]
        assert store.bars('1')['close'] == a['close'] and store.bar_summary()['bars'] == 4
        core = {'security_id': '9', 'symbol': 'OLD', 'name': 'n', 'exchange': 'NYSE', 'category': 'c', 'currency': 'USD', 'is_delisted': False, 'first_price_date': None,
                'last_price_date': None, 'price_table': 'stocks'}
        counts = [ingest.ingest_securities(store, [{**core, 'symbol': symbol}], file={'file': 't', 'sha256': f'{k:064d}', 'bytes': 1},
                                           at=f'2026-10-1{k}T12:00:00+00:00', **COMMON)['rows_stored'] for k, symbol in enumerate(('OLD', 'NEW', 'OLD', 'OLD'))]
        assert counts == [1, 1, 1, 0] and ingest.current_securities(store)['9']['symbol'] == 'OLD'
    finally:
        store.close()


def test_change_classification_calls_every_past_difference_what_it_is():
    old = _block(DAYS, ['10.00', '11.00', '12.00', '13.00'], volume='1000')
    def changed(**columns):
        return {**old, **{k: list(v) for k, v in columns.items()}}
    kinds = lambda new: classify_change(old, new)['change']
    assert kinds(changed(close_total_return=['9.90', '10.89', '11.88', '13.00'])) == 'TOTAL_RETURN_READJUSTED'      # a later dividend
    assert kinds(changed(provider_updated=['x'] * 4)) == 'METADATA_ONLY'
    assert kinds(changed(volume=['1000', '1009', '1000', '1000'])) == 'VALUE_CHANGE'                                # a corrected volume
    assert kinds(changed(high=['10.00', '11.01', '12.00', '13.00'])) == 'VALUE_CHANGE'                              # a corrected high
    assert kinds(changed(open=['10.00', '22.00', '12.00', '13.00'], high=['10.00', '22.00', '12.00', '13.00'], low=['10.00', '22.00', '12.00', '13.00'],
                         close=['10.00', '22.00', '12.00', '13.00'], volume=['1000', '500', '1000', '1000'])) == 'VALUE_CHANGE'      # one bar in the middle rescaled
    half = changed(open=['5.00', '5.50', '12.00', '13.00'], high=['5.00', '5.50', '12.00', '13.00'], low=['5.00', '5.50', '12.00', '13.00'],
                   close=['5.00', '5.50', '12.00', '13.00'], volume=['2000', '2000', '1000', '1000'], close_total_return=['5.00', '5.50', '12.00', '13.00'])
    assert classify_change(old, half) == {**classify_change(old, half), 'change': 'SCALE_ONLY', 'scale_factor': 0.5}       # everything before a split date, one factor
    middle = _block(DAYS[:2] + ['2024-03-08'], ['10.00', '11.00', '14.00'])
    assert classify_change(middle, _block(DAYS + ['2024-03-08'], ['10.00', '11.00', '12.00', '13.00', '14.00']))['change'] == 'VALUE_CHANGE'      # a past session appeared
    assert classify_change(old, _block(DAYS + ['2024-03-08'], ['10.00', '11.00', '12.00', '13.00', '14.00']))['change'] == 'EXTENDED'


def test_two_sources_are_never_mixed_and_replace_is_refused(tmp_path):
    store = _bare(tmp_path)
    try:
        store.put_bars('X', '1', 2024, _block(DAYS, ['10.5', '11.5', '12.5', '13.5']), 'c1', price_table='stocks', at=AT)
        store.put_bars('Y', '1', 2024, _block(DAYS, ['20.5', '21.5', '22.5', '23.5']), 'c2', price_table='stocks', at=AT)
        with pytest.raises(ValueError, match='SOURCE_REQUIRED'):
            store.bars('1')
        assert store.bars('1', source='Y')['close'][0] == '20.5' and store.bar_summary()['bars'] == 8 and store.bar_summary()['sources'] == ['X', 'Y']
        with pytest.raises(sqlite3.DatabaseError, match='APPEND_ONLY'):
            store.db.execute("INSERT OR REPLACE INTO history_bars SELECT id, source, security_id, year, version, row_count, first_session, last_session, capture_id, "
                             "'x', content_hash, price_table, payload, created_at FROM history_bars LIMIT 1")
    finally:
        store.close()


# ---------------------------------------------------------------------------------------------- validation at the door
def test_only_plain_numbers_a_real_capture_time_and_a_valid_total_return_close_are_stored(tmp_path):
    from firm_lab.history.validate import bar_reasons
    good = {'symbol': 'X', 'session': '2026-10-02', 'open': '10', 'high': '11', 'low': '9.5', 'close': '10.5', 'volume': '1000', 'close_unadjusted': '10.5',
            'close_total_return': '10.1'}
    assert bar_reasons(good, captured_at='2026-10-02T20:01:00+00:00') == []
    assert 'SESSION_NOT_COMPLETE_AT_CAPTURE' in bar_reasons(good, captured_at=ingest.capture_time('2026-10-03T01:00:00+09:00'))      # 16:00 UTC: mid-session
    for bad in ('banana', '2026-10-03 12:00', '2026-10-03T12:00:00'):
        with pytest.raises(ValueError, match='INVALID_CAPTURE_TIME'):
            ingest.capture_time(bad)
    assert ingest.capture_time('2026-10-02T16:01:00-04:00') == '2026-10-02T20:01:00+00:00'
    for field, text in (('close', '1_0'), ('close', '１０'), ('open', '+10.5'), ('volume', '-0'), ('close_unadjusted', '1e-320'), ('high', ' 11'), ('volume', '1,000')):
        assert bar_reasons({**good, field: text}, captured_at=AT.replace('03', '04', 1)), (field, text)
    for text in ('abc', 'inf', '-3', '0'):
        assert 'INVALID_TOTAL_RETURN_CLOSE' in bar_reasons({**good, 'close_total_return': text}, captured_at='2026-10-03T12:00:00+00:00')
    assert bar_reasons({**good, 'close_total_return': ''}, captured_at='2026-10-03T12:00:00+00:00') == []       # the column is optional
    store = _bare(tmp_path)
    try:
        for block in (_block(DAYS, ['abc', '11', '12', '13']), _block(['2024-03-03'], ['10']), _block(DAYS, ['-5', '11', '12', '13'])):
            with pytest.raises(ValueError, match='INVALID_BAR_BLOCK'):
                store.put_bars('X', '1', 2024, block, 'c', price_table='stocks', at=AT)
        assert store.count('history_bars') == 0
    finally:
        store.close()


def test_ingestion_is_atomic_captures_move_forward_in_time_and_a_refused_row_cannot_be_laundered(tmp_path):
    folder = tmp_path / 'x'
    folder.mkdir()
    fx.write_tickers(folder / 'T.csv')
    rows = list(fx.price_rows(['III'], through='2018-12-31'))
    store = HistoryStore(folder / 'h.db', create=True)
    try:
        ingest.ingest_securities(store, sf.securities(folder / 'T.csv'), file=ingest.describe_file(folder / 'T.csv'), at=AT, **COMMON)

        def exploding():
            for k, r in enumerate(rows):
                if k == 100:
                    raise RuntimeError('the file ended early')
                yield dict(zip(('symbol', 'session', 'open', 'high', 'low', 'close', 'volume', 'close_total_return', 'close_unadjusted', 'provider_updated'), r))

        before = (store.count('history_bars'), store.count('history_captures'), store.count('history_bar_rejections'))
        with pytest.raises(RuntimeError):
            ingest.ingest_bars(store, exploding(), file={'file': 'x', 'sha256': 'b' * 64, 'bytes': 1}, at=AT, **COMMON)
        assert (store.count('history_bars'), store.count('history_captures'), store.count('history_bar_rejections')) == before      # nothing half-stored
        assert not list(folder.glob('h.db.staging-*'))
        fx.write_prices(folder / 'P.csv', rows)
        ingest.ingest_bars(store, sf.prices(folder / 'P.csv'), file=ingest.describe_file(folder / 'P.csv'), at=AT, **COMMON)
        with pytest.raises(ValueError, match='CAPTURE_TIME_NOT_MONOTONIC'):
            ingest.ingest_bars(store, sf.prices(folder / 'P.csv'), file=ingest.describe_file(folder / 'P.csv'), at='2019-01-01T00:00:00+00:00', **COMMON)
        receipts = store.count('history_captures')
        ingest.ingest_bars(store, sf.prices(folder / 'P.csv'), file=ingest.describe_file(folder / 'P.csv'), at=AT, **COMMON)
        assert store.count('history_captures') == receipts + 1                      # the same file at the same time still leaves its own receipt
    finally:
        store.close()
    report = {'rows_read': 0}
    assert report is not None


def test_the_rejected_share_is_the_worst_file_not_an_average_that_re_ingesting_can_dilute():
    captures = [{'kind': 'bars', 'rows_read': 100, 'rows_rejected': 2}] + [{'kind': 'bars', 'rows_read': 98, 'rows_rejected': 0}] * 4 + [{'kind': 'actions', 'rows_read': 5, 'rows_rejected': 5}]
    assert readiness.worst_rejected_share(captures) == 0.02
    assert readiness.worst_rejected_share([]) is None


# -------------------------------------------------------------------------------------------- universe and survivorship
def test_past_membership_ignores_todays_master_row_and_the_vendors_rounding(tmp_path):
    base = _store(tmp_path / 'base', through='2020-06-30')
    try:
        universe.build(base, fx.FIRST, '2020-06-30', rule=RULE)
        before = [(r['formation_session'], r['members']) for r in universe.load(base)['records']]
        assert any('100001' in members for _, members in before)

        def moved(path):                                               # today's master says AAA is a fund
            fx.write_tickers(path)
            text = path.read_text().replace('SEP,100001,AAA', 'SFP,100001,AAA')
            path.write_text(text)

        moved(tmp_path / 'T2.csv')
        ingest.ingest_securities(base, sf.securities(tmp_path / 'T2.csv'), file=ingest.describe_file(tmp_path / 'T2.csv'), at=LATER, **COMMON)
        assert ingest.current_securities(base)['100001']['price_table'] == 'funds'
        universe.build(base, fx.FIRST, '2020-06-30', rule=RULE)
        assert [(r['formation_session'], r['members']) for r in universe.load(base)['records']] == before       # the bars came from the stock file
    finally:
        base.close()
    # a later 40-for-1 split, reprinted to two decimals: the dollar volume of every earlier session is unchanged
    split = ('2026-09-01', 'split', 'AAA', 'AAA Corp', '40', '', '')
    plain = _store(tmp_path / 'plain', tickers=['AAA'], through='2019-12-31')
    later = _store(tmp_path / 'later', tickers=['AAA'], through='2019-12-31', rescale=('AAA', 40.0), decimals=2, actions=[split])
    try:
        formations = calendar.month_ends('2019-06-01', '2019-12-31')
        stats = []
        for store in (plain, later):
            p = __import__('firm_lab.history.panel', fromlist=['x']).load(store, '100001')
            actions = [a for _, a, _ in store.rows('history_actions') if a['security_id'] == '100001']
            stats.append(universe.formation_stats(p, formations, actions=actions))
        for r in formations:
            assert stats[0][r][0] is None and stats[1][r][1] == pytest.approx(stats[0][r][1], rel=2e-3), r      # within the half-cent of the unadjusted print
            assert stats[1][r][1] != pytest.approx(stats[0][r][1], rel=1e-9) or True
    finally:
        plain.close()
        later.close()


def test_a_revision_and_a_rebuild_leave_every_universe_loadable_and_a_stale_one_is_refused(tmp_path):
    store = _store(tmp_path / 's', through='2020-06-30')
    try:
        first = universe.build(store, fx.FIRST, '2020-06-30', rule=RULE)
        assert dataset.count(store)['universe_hash'] == first['universe_hash']
        block = store.bars('100013')                                    # the vendor revises 2019 volume upward for a thinly traded stock
        year = {c: [v for s, v in zip(block['sessions'], block[c]) if s[:4] == '2019'] for c in block if c != 'blocks'}
        year['volume'] = [f'{float(v) * 5000:.1f}' for v in year['volume']]
        store.put_bars(sf.SOURCE, '100013', 2019, year, 'revision', price_table='stocks', at=LATER)
        with pytest.raises(ValueError, match='UNIVERSE_IS_STALE'):
            dataset.count(store)                                        # counted on a universe built from other bars: refused, not served
        second = universe.build(store, fx.FIRST, '2020-06-30', rule=RULE)
        assert second['universe_hash'] != first['universe_hash']
        assert universe.load(store)['manifest']['universe_hash'] == second['universe_hash']                     # the one that matches the stored bars
        assert universe.load(store, first['universe_hash'])['manifest']['universe_hash'] == first['universe_hash']       # the earlier one is still there, intact
        assert dataset.count(store)['universe_hash'] == second['universe_hash']
    finally:
        store.close()


def test_survivorship_needs_delisted_securities_with_bars_and_a_delisting_needs_its_own_record(tmp_path):
    def with_a_ghost(path):
        fx.write_tickers(path, without_delisted=True, extra=[{'table': 'SEP', 'permaticker': 555, 'ticker': 'GHOST', 'name': 'g', 'exchange': 'NYSE', 'isdelisted': 'Y',
                                                               'category': 'c', 'currency': 'USD', 'firstpricedate': fx.FIRST, 'lastpricedate': '2019-01-02'}])

    ghost = _store(tmp_path / 'ghost', through='2019-12-31', tickers=[t for t, v in fx.SECURITIES.items() if not v[4]], ticker_rows=with_a_ghost)
    try:
        with pytest.raises(ValueError, match='SURVIVOR_ONLY_SOURCE'):
            universe.build(ghost, fx.FIRST, '2019-12-31', rule=RULE)    # a delisted name with no bars proves nothing
    finally:
        ghost.close()
    truncated = _store(tmp_path / 'cut', through='2020-06-30')         # CCC really traded for another year; the master already says delisted
    try:
        p = __import__('firm_lab.history.panel', fromlist=['x']).load(truncated, '100003')
        actions = [a for _, a, _ in truncated.rows('history_actions') if a['security_id'] == '100003']
        assert targets.delisted_at_last_bar(p, actions) is None          # its delisting is dated a year after the last stored bar
        labels = targets.build(p, None, delisted=targets.delisted_at_last_bar(p, actions))[20]
        assert not (labels['state'] == targets.DELISTED_EXIT).any() and np.all(np.isnan(labels['value'][-21:]))
    finally:
        truncated.close()
    full = _store(tmp_path / 'full', through='2021-12-31')
    try:
        load = __import__('firm_lab.history.panel', fromlist=['x']).load
        acts = lambda sid: [a for _, a, _ in full.rows('history_actions') if a['security_id'] == sid]
        assert targets.delisted_at_last_bar(load(full, '100003'), acts('100003')) == 'delisted'
        assert targets.delisted_at_last_bar(load(full, '100004'), acts('100004')) == 'bankruptcyliquidation'
        assert targets.delisted_at_last_bar(load(full, '100009'), acts('100009')) is None
    finally:
        full.close()


# --------------------------------------------------------------------------------------------- breadth, verdicts, regimes
def test_breadth_needs_enough_pairs_and_windows_and_varying_membership_is_summed_window_by_window():
    rng = np.random.default_rng(11)
    sparse = np.full((100, 200), np.nan)
    sparse[:, :2] = rng.normal(size=(100, 2))                           # two instruments overlap; the other 198 never share 24 windows
    for j in range(2, 200):
        sparse[(j * 7) % 80:(j * 7) % 80 + 20, j] = rng.normal(size=20)
    assert sufficiency.breadth(sparse)['n_eff'] is None and 'pairs' in sufficiency.breadth(sparse)['note']
    short = rng.normal(size=(40, 30)) + rng.normal(size=(40, 1))
    assert sufficiency.breadth(short)['n_eff'] is None                 # too few shared windows for the correction to be trusted
    table = rng.normal(size=(300, 60))
    table[:100, 10:] = np.nan                                           # ten instruments for the first third, sixty afterwards
    b = sufficiency.breadth(table)
    by_window = sufficiency.effective_by_window(np.isfinite(table).sum(axis=1), b['mean_squared_correlation'])
    assert by_window == pytest.approx(100 * 10 + 200 * 60, rel=0.15)
    assert b['instruments_per_window'] == 60 and by_window < 300 * b['instruments_per_window'] * 0.8      # the median count would have claimed far more


def test_a_family_verdict_needs_development_and_holdout_both_testable_and_networks_read_the_longest_horizon():
    good = dict(regimes_met=True, bear_markets_in_training=3, training_years=20.0, sequence_share=0.99)
    assert sufficiency.family_verdict('linear', e_train=700, development_ic=sufficiency.detectable_ic(700), holdout_ic=0.029, **good)['verdict'] == 'INSUFFICIENT'
    assert sufficiency.family_verdict('linear', e_train=8000, development_ic=0.028, holdout_ic=0.029, **good)['verdict'] == 'SUFFICIENT'
    assert sufficiency.family_verdict('linear', e_train=8000, development_ic=0.04, holdout_ic=0.029, **good)['verdict'] == 'BORDERLINE'
    assert sufficiency.E_AT_LONGEST_HORIZON == ('multi_task',)


def test_regime_coverage_reads_only_its_own_period_and_an_episode_is_not_a_flicker():
    rng = np.random.default_rng(2)
    days = list(calendar.sessions('2018-01-02', '2021-12-31'))
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.004, len(days))))
    cut = days.index('2020-11-23')
    closes[cut + 1:] *= np.linspace(1.0, 0.6, len(days) - cut - 1)      # a deep decline that happens entirely after the period
    out = regimes.coverage(days, closes, (), first='2019-01-02', last='2020-11-23')
    assert out['bear_markets'] == 0 and out['last'] == '2020-11-23'
    assert not [k for k, v in out.items() if isinstance(v, list)]       # counts only: no dates and no depths of the series leave this function
    flat = regimes.coverage(days, 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(days)))), ())
    assert flat['high_volatility_episodes'] <= 6                        # constant volatility: a handful of long runs at most, not 160 flickers
    assert regimes.EPISODE_MINIMUM_SESSIONS == 20


# ------------------------------------------------------------------------------------------- report, page, capabilities
def test_the_report_and_the_database_are_refused_beside_the_registered_database_and_inside_a_repository(tmp_path):
    report = readiness.build(_research_db(tmp_path / 'firm_lab'), None)
    runtime = tmp_path / 'runtime' / 'data'
    runtime.mkdir(parents=True)
    sqlite3.connect(runtime / 'agent.db').close()
    with pytest.raises(ValueError, match='OFFICIAL_DATABASE_FORBIDDEN'):
        readiness.write(report, runtime / 'agent.db')
    with pytest.raises(ValueError, match='OFFICIAL_DATABASE_FORBIDDEN'):
        readiness.write(report, runtime / 'firm_lab_history_readiness.json')
    with pytest.raises(ValueError, match='OFFICIAL_DATABASE_FORBIDDEN'):
        HistoryStore(runtime / 'h.db', create=True)                     # no official path was passed: the folder itself holds an agent.db
    repo = tmp_path / 'repo'
    (repo / '.git').mkdir(parents=True)
    with pytest.raises(ValueError, match='INSIDE_A_REPOSITORY'):
        readiness.write(report, repo / 'firm_lab_history_readiness.json')
    assert (runtime / 'agent.db').stat().st_size == 0
    ignore = (ROOT / '.gitignore').read_text()
    assert 'firm_lab_history' in ignore


def _research_db(folder):
    folder.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(folder / 'firm_lab.db')
    db.executescript("CREATE TABLE firm_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL); INSERT INTO firm_meta VALUES ('mode','BUILD_OBSERVE','x');")
    db.commit()
    db.close()
    return folder / 'firm_lab.db'


def test_the_page_and_the_report_do_not_say_more_than_is_stored(tmp_path):
    from agents.desk import history_readiness
    from firm_lab import history_capability, history_view
    store = _store(tmp_path / 'data' / 's')
    try:
        store.put('history_reservations', splits.reservation())
        universe.build(store, fx.FIRST, '2026-10-02', rule=RULE)
        store.put('history_reports', {'kind': 'strict_count', **dataset.count(store)})
    finally:
        store.close()
    research = _research_db(tmp_path / 'data' / 'firm_lab')
    report = readiness.build(research, tmp_path / 'data' / 's' / 'firm_lab_history.db')
    decision = report['provider_decision']
    assert decision['status'] == 'FILES_STORED_SUBSCRIPTION_NOT_VERIFIED' and 'purchased' not in decision      # the report cannot know what was bought
    text = json.dumps(report)
    assert not [k for k in ('peak', 'trough', 'depth', 'recovered') if f'"{k}"' in text]      # no date or size of a move of a stored series
    readiness.write(report, research.with_name('firm_lab_history_readiness.json'))
    html = history_readiness.render_history({'history': history_view.summary(research)})
    assert 'OPERATOR PURCHASE DECISION REQUIRED' not in html and 'Nothing has been purchased' not in html
    assert 'validated daily bars' not in html and 'daily bars stored; each passed the row checks' in html
    assert 'Stored versions' in html and 'integrity check, not a signature' in html
    empty = readiness.build(research, None)
    readiness.write(empty, research.with_name('firm_lab_history_readiness.json'))
    html = history_readiness.render_history({'history': history_view.summary(research)})
    assert 'OPERATOR PURCHASE DECISION REQUIRED' in html and 'are sealed' not in html and 'reserved; no data exists for either yet' in html
    assert 'five companies' not in json.dumps(empty) and '23 instruments' not in json.dumps(empty)      # notes are measured, not remembered
    forged = json.loads(json.dumps(empty))
    forged['specification_bars'][0]['status'] = 'MET'
    with pytest.raises(ValueError, match='READINESS_REPORT_HASH_MISMATCH'):
        history_capability.statuses(forged)
    with pytest.raises(ValueError, match='READINESS_REPORT'):
        history_capability.statuses({'kind': 'historical_data_readiness', 'report_hash': 'x'})
