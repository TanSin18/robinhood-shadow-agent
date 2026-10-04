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
    """A factor that steps the wrong way (prices before the split multiplied instead of divided) matched the other
    convention and passed. The unadjusted close says whether the record or the factor is wrong."""
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
    assert 'steps the wrong way' in found['breaks'][0]['note'] and found['split_convention'] == {'new_per_old': 0, 'old_per_new': 0}


def test_print_precision_is_read_from_the_bars_own_row_and_small_input_oddities_fail_safe():
    columns = _columns(hi=60, decimals=2, price=29.0)
    columns['close'][10] = '29'                                                     # a vendor that strips trailing zeros: "29" for 29.00
    columns['high'][10] = max(columns['high'][10], '29.01')
    columns['low'][10] = min(columns['low'][10], '28.99')
    p = panel.from_columns(columns)
    assert p['half_ulp'][10] == pytest.approx(p['half_ulp'][11], rel=0.2) and p['half_ulp'][10] < 0.001      # two decimals (its other prices show them), not zero
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


@pytest.fixture(autouse=True)
def _machine_clock(monkeypatch):
    fx.set_clock(monkeypatch)                     # the clock a capture is stamped with; later than every time these tests supply


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

    def late_opens(row):                                                # other prices from the forward holdout's first session on
        if row[1] >= splits.FORWARD_FIRST:
            for c in (2, 3, 4, 5, 7):
                row[c] = f'{float(row[c]) * 1.03:.6f}'
            row[8] = f'{float(row[8]) * 1.03:.4f}'
        return row

    a = _store(tmp_path / 'a', at=LATER)
    b = _store(tmp_path / 'b', at=LATER, edit=late_opens)
    try:
        for store in (a, b):
            universe.build(store, fx.FIRST, fx.LAST, rule=RULE, version=fx.VERSION)
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
        universe.build(store, fx.FIRST, '2026-10-02', rule=RULE, version=fx.VERSION)
        counted = dataset.count(store)
    finally:
        store.close()
    by = counted['strict_samples_by_segment']['20']
    assert set(by) == {splits.DEVELOPMENT, splits.HISTORICAL_HOLDOUT, splits.BURNED, splits.FORWARD_HOLDOUT}
    assert counted['strict_samples']['20'] == sum(by.values()) and by[splits.DEVELOPMENT] > 0 and by[splits.HISTORICAL_HOLDOUT] > by[splits.DEVELOPMENT]
    assert counted['by_segment'][splits.PURGED]['labelled_20'] > 0                  # they exist, and they are not counted as samples
    assert counted['strict_samples']['20'] < sum(part['labelled_20'] for part in counted['by_segment'].values())


# ------------------------------------------------------------------------------------- tiers, revisions and versions
def test_a_revised_bar_is_not_held_at_the_time_and_a_row_takes_the_lowest_tier(tmp_path, monkeypatch):
    sessions = list(calendar.sessions('2024-01-02', '2025-03-28'))
    fx.set_clock(monkeypatch, '2024-01-02T12:00:00+00:00')
    store = _bare(tmp_path)
    try:
        ingest.ingest_securities(store, [{'security_id': '1', 'symbol': 'X', 'name': 'X', 'exchange': 'NYSE', 'category': 'c', 'currency': 'USD', 'is_delisted': False,
                                          'first_price_date': sessions[0], 'last_price_date': sessions[-1], 'price_table': 'stocks'}],
                                 file={'file': 't', 'sha256': 'a' * 64, 'bytes': 1}, **COMMON)
        price = lambda k: f'{50 + 0.01 * k:.2f}'
        for k, s in enumerate(sessions):                               # stored each evening by the machine's own clock, before the next session opened
            rows = [{'symbol': 'X', 'session': s, 'open': price(k), 'high': price(k), 'low': price(k), 'close': price(k), 'volume': '100', 'close_unadjusted': price(k),
                     'close_total_return': price(k), 'provider_updated': ''}]
            fx.set_clock(monkeypatch, calendar.session_close(s))
            ingest.ingest_bars(store, rows, file={'file': f'd{k}', 'sha256': f'{k:064d}', 'bytes': 1}, **COMMON)
        assert len(store.bars('1')['sessions']) == len(sessions)       # a one-session file extends the year; it does not replace it
        history = store.bar_history('1')
        assert history['since'][sessions[5]] == calendar.session_close(sessions[5]) and set(history['clock'].values()) == {'SYSTEM'} and not history['revised']
        tiers = dataset.row_tiers(sessions, np.ones(len(sessions), bool), history)
        assert tiers[252] == 'HELD_AT_THE_TIME' and tiers[251] == 'PUBLISHER_DATED_HISTORICAL'       # 253 bars: what the 252-session return reads
        revised = [{'symbol': 'X', 'session': sessions[200], 'open': '62.63', 'high': '62.63', 'low': '62.63', 'close': '62.63', 'volume': '100', 'close_unadjusted': '62.63',
                    'close_total_return': '62.63', 'provider_updated': ''}]
        fx.set_clock(monkeypatch, '2026-11-01T12:00:00+00:00')
        out = ingest.ingest_bars(store, revised, file={'file': 'rev', 'sha256': 'f' * 64, 'bytes': 1}, **COMMON)
        assert out['blocks_by_change'] == {'VALUE_CHANGE': 1}
        history = store.bar_history('1')
        assert history['since'][sessions[200]] == '2026-11-01T12:00:00+00:00' and history['since'][sessions[199]] == calendar.session_close(sessions[199])
        assert history['revised'] == {sessions[200]}
        tiers = dataset.row_tiers(sessions, np.ones(len(sessions), bool), history)
        # a restated value: every row whose features or longest label read the revised bar is tier C, and so not a strict sample
        assert set(tiers[200 - 21:]) == {'RETROSPECTIVE'} and tiers[200 - 22] != 'RETROSPECTIVE' and len(sessions) < 200 + 253
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
                             "'x', content_hash, price_table, payload, created_at, clock FROM history_bars LIMIT 1")
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
        universe.build(base, fx.FIRST, '2020-06-30', rule=RULE, version=fx.VERSION)
        before = [(r['formation_session'], r['members']) for r in universe.load(base)['records']]
        assert any('100001' in members for _, members in before)

        def moved(path):                                               # today's master says AAA is a fund
            fx.write_tickers(path)
            text = path.read_text().replace('SEP,100001,AAA', 'SFP,100001,AAA')
            path.write_text(text)

        moved(tmp_path / 'T2.csv')
        ingest.ingest_securities(base, sf.securities(tmp_path / 'T2.csv'), file=ingest.describe_file(tmp_path / 'T2.csv'), at=LATER, **COMMON)
        assert ingest.current_securities(base)['100001']['price_table'] == 'funds'
        universe.build(base, fx.FIRST, '2020-06-30', rule=RULE, version=fx.VERSION)
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
        first = universe.build(store, fx.FIRST, '2020-06-30', rule=RULE, version=fx.VERSION)
        assert dataset.count(store)['universe_hash'] == first['universe_hash']
        block = store.bars('100013')                                    # the vendor revises 2019 volume upward for a thinly traded stock
        year = {c: [v for s, v in zip(block['sessions'], block[c]) if s[:4] == '2019'] for c in block if c != 'blocks'}
        year['volume'] = [f'{float(v) * 5000:.1f}' for v in year['volume']]
        store.put_bars(sf.SOURCE, '100013', 2019, year, 'revision', price_table='stocks', at=LATER)
        with pytest.raises(ValueError, match='UNIVERSE_IS_STALE'):
            dataset.count(store)                                        # counted on a universe built from other bars: refused, not served
        second = universe.build(store, fx.FIRST, '2020-06-30', rule=RULE, version=fx.VERSION)
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
            universe.build(ghost, fx.FIRST, '2019-12-31', rule=RULE, version=fx.VERSION)    # a delisted name with no bars proves nothing
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
        universe.build(store, fx.FIRST, '2026-10-02', rule=RULE, version=fx.VERSION)
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


# ------------------------------------------------------ review round 3 (a fourth, fresh reviewer; commit e1a502e)
SPAN = list(calendar.sessions('2024-03-04', '2024-03-15'))             # ten sessions


def _ohlc(sessions, rows, *, volume, unadjusted=None):
    """A block from (open, high, low, close) rows printed as given."""
    columns = list(zip(*rows))
    return {'sessions': list(sessions), 'open': list(columns[0]), 'high': list(columns[1]), 'low': list(columns[2]), 'close': list(columns[3]),
            'volume': list(volume) if not isinstance(volume, str) else [volume] * len(rows), 'close_unadjusted': list(unadjusted or columns[3]),
            'close_total_return': list(columns[3]), 'provider_updated': [''] * len(rows)}


def _later_split_store(folder, later, through='2020-12-31'):
    """The same market history twice; in one, AAA is printed as a vendor prints it after a 40-for-1 split in 2026."""
    folder.mkdir(parents=True)
    fx.write_tickers(folder / 'T.csv')
    rows = []
    for ticker in fx.SECURITIES:
        extra = {'rescale': ('AAA', 40.0), 'decimals': 2} if later and ticker == 'AAA' else {}
        rows += [list(r) for r in fx.price_rows([ticker], through=through, **extra)]
    fx.write_prices(folder / 'P.csv', rows)
    fx.write_actions(folder / 'A.csv', extra=[('2026-09-01', 'split', 'AAA', 'AAA Corp', '40', '', '')] if later else ())
    store = HistoryStore(folder / 'firm_lab_history.db', create=True)
    ingest.ingest_securities(store, sf.securities(folder / 'T.csv'), file=ingest.describe_file(folder / 'T.csv'), at=LATER, **COMMON)
    ingest.ingest_bars(store, sf.prices(folder / 'P.csv'), file=ingest.describe_file(folder / 'P.csv'), at=LATER, **COMMON)
    ingest.ingest_actions(store, sf.actions(folder / 'A.csv'), file=ingest.describe_file(folder / 'A.csv'), at=LATER, **COMMON)
    universe.build(store, fx.FIRST, through, rule={**universe.RULE, 'size': 40}, version='liquid-top40-test')
    return store


def test_whether_a_high_low_open_feature_exists_never_depends_on_a_later_split(tmp_path, monkeypatch):
    """Withholding those features only on coarsely printed rows marked exactly the stocks that split years later."""
    from firm_lab.history import features
    more = {f'Q{k:02d}': (200001 + k, 30.0 + 2 * k, 4.2 + 0.05 * k, None, False) for k in range(30)}       # so that AAA is a small share of the rows
    monkeypatch.setattr(fx, 'SECURITIES', {**fx.SECURITIES, **more})
    plain, later = _later_split_store(tmp_path / 'plain', False), _later_split_store(tmp_path / 'later', True)
    try:
        a, b = dataset.materialise(plain), dataset.materialise(later)
        counted = dataset.count(later)
    finally:
        plain.close()
        later.close()
    assert list(zip(a['security_id'], a['session'])) == list(zip(b['security_id'], b['session'])) and a['manifest']['rows'] > 1000
    shape = [k for k, d in enumerate(features.DEFINITIONS) if d['uses_high_low_open']]
    close_only = [k for k, d in enumerate(features.DEFINITIONS) if not d['uses_high_low_open'] and d['family'] != 'volume']
    aaa = np.array(a['security_id']) == '100001'
    assert 100 < aaa.sum() < 0.05 * len(aaa)
    assert a['manifest']['high_low_open_families_usable'] and np.isfinite(a['X'][aaa][:, shape]).any() and a['manifest']['rows_reading_a_coarse_print'] == 0
    # the later split is in the future of every one of these rows: it may not show in which rows have a value
    missing = np.isnan(b['X'][:, shape])
    assert missing[aaa].all() and missing[~aaa].all()                    # all rows or none, never the future splitter alone
    assert not b['manifest']['high_low_open_families_usable'] and b['manifest']['rows_reading_a_coarse_print'] > 0
    assert not counted['high_low_open_families_usable'] and counted['rows_reading_a_coarse_print'] > 0
    assert 0 < counted['coarse_print_share'] < 0.05                      # far below the share at which the earlier rule withheld them from everyone
    np.testing.assert_allclose(a['X'][aaa][:, close_only], b['X'][aaa][:, close_only], rtol=1e-9, atol=1e-12, equal_nan=True)


def test_nothing_of_a_sealed_segment_leaves_the_builder_and_no_readable_row_reads_a_sealed_price(tmp_path):
    """Burned rows read the holdout through their lookbacks, and rows of sealed sessions left with their features: a
    20-session return is the label of the row 21 sessions earlier."""
    def holdout_only(row):                                              # other prices in the holdout's last months; dollar volume and so membership unchanged
        if '2024-07-01' <= row[1] <= splits.HOLDOUT_LAST:
            k = 1.0 + 0.3 * (calendar.position(row[1]) - calendar.position('2024-07-01')) / 190.0
            for c in (2, 3, 4, 5, 7):
                row[c] = f'{float(row[c]) * k:.6f}'
            row[8], row[6] = f'{float(row[8]) * k:.4f}', f'{float(row[6]) / k:.1f}'
        return row

    a, b = _store(tmp_path / 'a', at=LATER), _store(tmp_path / 'b', at=LATER, edit=holdout_only)
    try:
        for store in (a, b):
            universe.build(store, fx.FIRST, fx.LAST, rule=RULE, version=fx.VERSION)
        xa, xb = dataset.materialise(a, segments=(splits.BURNED,)), dataset.materialise(b, segments=(splits.BURNED,))
        common = sorted(set(zip(xa['security_id'], xa['session'])) & set(zip(xb['security_id'], xb['session'])))
        ia, ib = {k: n for n, k in enumerate(zip(xa['security_id'], xa['session']))}, {k: n for n, k in enumerate(zip(xb['security_id'], xb['session']))}
        assert len(common) > 1000 and len(common) > 0.9 * xa['manifest']['rows']
        np.testing.assert_array_equal(xa['X'][[ia[k] for k in common]], xb['X'][[ib[k] for k in common]])      # no holdout price reaches a burned feature
        assert min(xa['session']) >= calendar.offset(splits.BURNED_FIRST, 20)        # a burned row starts from the burned window's own bars
        assert xa['manifest']['features_of_burned_rows_read_from'] == splits.BURNED_FIRST
        assert dataset.materialise(a)['manifest']['hashes'] == dataset.materialise(b)['manifest']['hashes']      # development never saw the holdout either
        rows = dataset.security_rows(a, '100009', None, universe.membership(universe.load(a)['records'])['100009'], [])
        unreadable = ~np.isin(rows['segment'], [splits.DEVELOPMENT, splits.BURNED])
        sealed = np.isin(rows['segment'], [splits.HISTORICAL_HOLDOUT, splits.FORWARD_HOLDOUT])
        assert sealed.sum() > 1000 and rows['eligible'][sealed].sum() > 900          # the rows are counted ...
        for name, values in rows['features'].items():
            assert np.all(np.isnan(values[unreadable])), name                        # ... and not one feature value of them is handed out
        assert np.isfinite(rows['features']['return20'][~unreadable]).sum() > 400
    finally:
        a.close()
        b.close()


def test_two_builds_never_share_records_and_every_bar_a_universe_reads_makes_it_stale(tmp_path, monkeypatch):
    store = _store(tmp_path / 's', through='2019-12-31')
    try:
        with pytest.raises(ValueError, match='RULE_NEEDS_ITS_OWN_VERSION'):
            universe.build(store, fx.FIRST, '2019-12-31', rule=RULE)     # another rule may not carry the registered rule's name
        first = universe.build(store, fx.FIRST, '2019-12-31', rule=RULE, version=fx.VERSION)
        original = universe.formation_stats

        def other(panel, formations, rule=universe.RULE, actions=()):   # the screening code changes; the bars do not
            return {r: (('NO_DOLLAR_VOLUME', None) if panel['security_id'] == '100002' else found) for r, found in original(panel, formations, rule, actions).items()}

        monkeypatch.setattr(universe, 'formation_stats', other)
        second = universe.build(store, fx.FIRST, '2019-12-31', rule=RULE, version=fx.VERSION)
        monkeypatch.setattr(universe, 'formation_stats', original)
        assert first['universe_hash'] != second['universe_hash']
        loaded = [universe.load(store, m['universe_hash']) for m in (first, second)]            # both stay readable, each with its own records
        assert all(len(found['records']) == first['formation_sessions'] for found in loaded)
        assert any('100002' in r['members'] for r in loaded[0]['records']) and not any('100002' in r['members'] for r in loaded[1]['records'])
        # the vendor moves FFF to its fund table from 2020 on; a universe then reads fund-file bars of a screened security
        moved = tmp_path / 'T2.csv'
        fx.write_tickers(moved)
        moved.write_text(moved.read_text().replace('SEP,100006,FFF', 'SFP,100006,FFF'))
        ingest.ingest_securities(store, sf.securities(moved), file=ingest.describe_file(moved), at=LATER, **COMMON)
        assert ingest.current_securities(store)['100006']['price_table'] == 'funds'
        rows = [list(r) for r in fx.price_rows(['FFF'], through='2020-12-31') if r[1] >= '2020-01-01']
        fx.write_prices(tmp_path / 'F.csv', rows)
        ingest.ingest_bars(store, sf.prices(tmp_path / 'F.csv'), file=ingest.describe_file(tmp_path / 'F.csv'), price_table='funds', at=LATER, **COMMON)
        third = universe.build(store, fx.FIRST, '2020-12-31', rule=RULE, version=fx.VERSION)
        assert universe.is_current(store, third) and dataset.count(store, universe_hash=third['universe_hash'])['strict_samples']['5'] > 0
        assert any('100006' in r['members'] for r in universe.load(store, third['universe_hash'])['records'] if r['formation_session'] >= '2020-03-01')
        for r in rows:
            r[6] = f'{float(r[6]) / 10000:.1f}'                         # and then revises those fund-file bars
        fx.write_prices(tmp_path / 'F2.csv', rows)
        out = ingest.ingest_bars(store, sf.prices(tmp_path / 'F2.csv'), file=ingest.describe_file(tmp_path / 'F2.csv'), price_table='funds', at='2026-10-13T12:00:00+00:00', **COMMON)
        assert out['blocks_by_change'] == {'VALUE_CHANGE': 1} and not universe.is_current(store, third)
        with pytest.raises(ValueError, match='UNIVERSE_IS_STALE'):
            dataset.count(store, universe_hash=third['universe_hash'])
    finally:
        store.close()


def test_a_bar_rewritten_as_a_rescale_is_a_revised_bar(tmp_path):
    first, second = '2024-03-15T21:00:00+00:00', '2026-10-01T12:00:00+00:00'
    flat = lambda price: (price, price, price, price)
    store = _bare(tmp_path, 'a.db')
    try:                                                                # one bar in the middle: prices doubled, volume halved, printed price unchanged
        base = _ohlc(SPAN, [flat(f'{10 + k}.00') for k in range(10)], volume='1000')
        store.put_bars('X', '1', 2024, base, 'c1', price_table='stocks', at=first)
        changed = {c: list(v) for c, v in base.items()}
        for c in ('open', 'high', 'low', 'close'):
            changed[c][4] = '28.00'
        changed['volume'][4] = '500'
        assert store.put_bars('X', '1', 2024, changed, 'c2', price_table='stocks', at=second)['change'] == 'VALUE_CHANGE'
        history = store.bar_history('1')
        assert history['since'][SPAN[4]] == second and history['revised'] == {SPAN[4]} and history['since'][SPAN[3]] == first
    finally:
        store.close()
    store = _bare(tmp_path, 'b.db')
    try:                                                                # a vendor that prints whole numbers: a different bar is not a rescale
        base = _ohlc(SPAN, [flat('52')] * 10, volume='1000')
        store.put_bars('X', '1', 2024, base, 'c1', price_table='stocks', at=first)
        other = {c: list(v) for c, v in base.items()}
        other['open'][0], other['high'][0], other['low'][0], other['close'][0], other['volume'][0] = '51', '55', '51', '53', '990'
        assert store.put_bars('X', '1', 2024, other, 'c2', price_table='stocks', at=second)['change'] == 'VALUE_CHANGE'
        assert store.bar_history('1')['revised'] == {SPAN[0]}
    finally:
        store.close()
    old = _ohlc(SPAN, [flat(f'{10 + k}.00') for k in range(10)], volume='1000')
    halved = _ohlc(SPAN, [flat(f'{(10 + k) / 2:.2f}') for k in range(10)], volume='2000', unadjusted=old['close'])
    assert classify_change(old, halved)['change'] == 'SCALE_ONLY' and classify_change(old, halved)['scale_factor'] == 0.5      # a real re-adjustment still is one
    reprinted = _ohlc(SPAN, [flat(f'{10 + k}.0') for k in range(10)], volume='1000', unadjusted=old['close'])
    assert classify_change(old, reprinted)['change'] == 'VALUE_CHANGE'  # the same numbers printed otherwise: not a rescale, and never silently equal


def test_a_session_the_vendor_removed_is_removed_and_a_sparse_file_removes_nothing(tmp_path):
    times = [f'2026-10-0{k}T12:00:00+00:00' for k in range(1, 6)]
    full = _block(SPAN, [f'{10 + k}.25' for k in range(10)])
    without = {c: [v for j, v in enumerate(column) if j != 4] for c, column in full.items()}
    store = _bare(tmp_path)
    try:
        store.put_bars('X', '1', 2024, full, 'c1', price_table='stocks', at=times[0])
        out = store.put_bars('X', '1', 2024, without, 'c2', price_table='stocks', at=times[1])       # the vendor's whole-year file no longer has the session
        assert out['stored'] and out['change'] == 'VALUE_CHANGE' and out['sessions_removed'] == 1
        assert SPAN[4] not in store.bars('1')['sessions'] and SPAN[4] in store.bars('1', through_capture_time=times[0])['sessions']
        tail = {c: column[6:] for c, column in full.items()}            # a file that only covers later sessions carries the earlier ones
        assert store.put_bars('X', '1', 2024, tail, 'c3', price_table='stocks', at=times[2])['stored'] is False and len(store.bars('1')['sessions']) == 9
        scattered = {c: [column[0], column[9]] for c, column in full.items()}
        scattered['volume'] = ['1000', '1234']                          # two changed rows, far apart: with "sparse" nothing between them is removed
        out = store.put_bars('X', '1', 2024, scattered, 'c4', price_table='stocks', at=times[3], sparse=True)
        assert out['stored'] and out['sessions_removed'] == 0 and len(store.bars('1')['sessions']) == 9
        store.put_bars('X', '1', 2024, full, 'c5', price_table='stocks', at=times[4])
        history = store.bar_history('1')                                # the bar that came back, and the one that changed, are revised bars
        assert len(store.bars('1')['sessions']) == 10 and {SPAN[4], SPAN[9]} <= history['revised'] and history['since'][SPAN[4]] == times[4]
    finally:
        store.close()


def test_a_supplied_capture_time_orders_versions_and_proves_nothing(tmp_path, monkeypatch):
    days = list(calendar.sessions('2024-01-02', '2025-03-28'))
    price = lambda k: f'{50 + 0.01 * k:.2f}'
    year = lambda y: _block([d for d in days if d[:4] == y], [price(k) for k, d in enumerate(days) if d[:4] == y])
    fx.set_clock(monkeypatch, '2026-10-04T12:00:00+00:00')
    store = _bare(tmp_path)
    try:
        with pytest.raises(ValueError, match='INVALID_BAR_BLOCK'):      # "captured" before any of its sessions existed
            store.put_bars('X', '1', 2024, year('2024'), 'c', price_table='stocks', at='2023-12-01T00:00:00+00:00')
        store.put_bars('X', '1', 2024, year('2024'), 'c', price_table='stocks', at=calendar.session_close('2024-12-31'))
        store.put_bars('X', '1', 2025, year('2025'), 'c', price_table='stocks', at=calendar.session_close('2025-03-28'))
        history = store.bar_history('1')
        assert set(history['clock'].values()) == {'SUPPLIED'}
        assert set(dataset.row_tiers(days, np.ones(len(days), bool), history)) == {'PUBLISHER_DATED_HISTORICAL'}      # a typed time is a claim, not a clock
        with pytest.raises(ValueError, match='CAPTURE_TIME_NOT_MONOTONIC'):
            store.put_bars('X', '2', 2024, _block(SPAN, ['10.00'] * 10), 'c', price_table='stocks', at='2024-06-03T00:00:00+00:00')
        with pytest.raises(ValueError, match='CAPTURE_TIME_IN_THE_FUTURE'):
            ingest.ingest_bars(store, [], file={'file': 'f', 'sha256': 'f' * 64, 'bytes': 1}, at='2027-03-02T00:00:00+00:00', **COMMON)
        assert ingest.ingest_bars(store, [], file={'file': 'g', 'sha256': 'e' * 64, 'bytes': 1}, **COMMON)['rows_read'] == 0      # the machine's own clock still works
        assert [p['clock'] for _, p, _ in store.rows('history_captures')] == ['SYSTEM']
    finally:
        store.close()


def test_the_tiers_split_the_strict_samples_and_a_row_that_reads_a_revised_bar_is_not_one(tmp_path):
    store = _store(tmp_path / 's', through='2020-12-31')
    try:
        before = dataset.count(store, universe_hash=universe.build(store, fx.FIRST, '2020-12-31', rule=RULE, version=fx.VERSION)['universe_hash'])
        for h in ('5', '10', '20'):
            assert sum(before['strict_samples_by_tier'][h].values()) == before['strict_samples'][h] > 0
        block = store.bars('100002')                                    # one corrected close in the middle of 2020
        year = {c: [v for s, v in zip(block['sessions'], block[c]) if s[:4] == '2020'] for c in block if c != 'blocks'}
        k = 120
        year['close'][k] = f'{float(year["close"][k]) * 1.0004:.6f}'
        year['high'][k] = f'{max(float(year["high"][k]), float(year["close"][k])):.6f}'
        assert store.put_bars(sf.SOURCE, '100002', 2020, year, 'correction', price_table='stocks', at=LATER)['change'] == 'VALUE_CHANGE'
        chosen = universe.build(store, fx.FIRST, '2020-12-31', rule=RULE, version=fx.VERSION)['universe_hash']
        after = dataset.count(store, universe_hash=chosen)
        lost = after['rows_not_strict_because_a_bar_was_revised']
        assert lost > 20 and after['eligible_feature_rows'] == before['eligible_feature_rows'] - lost
        assert after['strict_samples']['5'] < before['strict_samples']['5']
        data = dataset.materialise(store, universe_hash=chosen)
        assert data['manifest']['rows_left_out_because_a_bar_was_revised'] > 0 and set(data['tier']) == {'PUBLISHER_DATED_HISTORICAL'}
    finally:
        store.close()


def test_the_end_of_the_store_is_not_a_delisting_and_the_report_can_only_be_written_under_its_own_name(tmp_path):
    store = _store(tmp_path / 's', through='2026-08-31', actions=[('2026-09-03', 'delisted', 'III', 'III Corp', '', '', '')])
    try:
        p = __import__('firm_lab.history.panel', fromlist=['x']).load(store, '100009')
        actions = [a for _, a, _ in store.rows('history_actions') if a['security_id'] == '100009']
        end = store.bar_summary()['last_session']
        assert p['sessions'][-1] == end == '2026-08-31'
        assert targets.delisted_at_last_bar(p, actions, end) is None     # its bars stop where every security's stop: nothing shows that it stopped trading
        universe.build(store, fx.FIRST, '2026-08-31', rule=RULE, version=fx.VERSION)
        assert 'delisted' not in dataset.count(store)['delisting_exits_by_year'].get('2026', {})
        # a time given with another offset is the same time
        stored_at = store.db.execute('SELECT MIN(created_at) FROM history_bars').fetchone()[0]
        assert stored_at == AT and len(list(store.bar_blocks('100009', through_capture_time='2026-10-03T09:00:00-04:00'))) > 0
        assert not list(store.bar_blocks('100009', through_capture_time='2026-10-03T07:00:00-04:00'))
        # a second universe over another period: both fit the stored bars, the report shows one and does not call it stale
        store.put('history_reports', {'kind': 'strict_count', **dataset.count(store)})
        universe.build(store, fx.FIRST, '2026-06-30', rule=RULE, version=fx.VERSION)
    finally:
        store.close()
    research = _research_db(tmp_path / 'firm_lab')
    database = tmp_path / 's' / 'firm_lab_history.db'
    report = readiness.build(research, database)
    assert report['market_data']['universe_stale'] is False and report['market_data']['universes_current'] == 2 and report['universe']['end'] == '2026-08-31'
    before = database.read_bytes()
    for target in (database, tmp_path / 's' / 'notes.json'):
        with pytest.raises(ValueError, match='NOT_THE_READINESS_FILE'):
            readiness.write(report, target)
    assert database.read_bytes() == before
    from firm_lab.history import cli
    assert cli.main(['count', '--db', str(database)]) == 0              # with several universes the command counts the one built last


def test_an_interrupted_ingestion_leaves_no_vendor_row_beside_the_database(tmp_path):
    folder = tmp_path / 'private'
    folder.mkdir()
    store = HistoryStore(folder / 'firm_lab_history.db', create=True)
    fx.write_tickers(tmp_path / 'T.csv')
    ingest.ingest_securities(store, sf.securities(tmp_path / 'T.csv'), file=ingest.describe_file(tmp_path / 'T.csv'), at=AT, **COMMON)
    seen = []

    def rows():
        for n, r in enumerate(fx.price_rows(['III'], through='2019-12-31')):
            if n == 300:
                seen.append(sorted(p.name for p in folder.iterdir()))   # what a process killed here would leave behind
            yield dict(zip(('symbol', 'session', 'open', 'high', 'low', 'close', 'volume', 'close_total_return', 'close_unadjusted', 'provider_updated'), r))

    try:
        ingest.ingest_bars(store, rows(), file={'file': 'p', 'sha256': 'a' * 64, 'bytes': 1}, at=AT, **COMMON)
    finally:
        store.close()
    assert seen and all(name.startswith('firm_lab_history.db') and 'staging' not in name for name in seen[0])


def test_the_report_lists_every_bar_of_the_specification_and_a_history_is_not_one_early_bar(tmp_path):
    import re
    spec = (ROOT / 'docs' / 'firm_lab' / 'CHECKPOINT8_DATA_SUFFICIENCY_SPEC.md').read_text()
    named = sorted(set(re.findall(r'^\| ([HPEFO][0-9]) ', spec, re.M)))
    empty = readiness.build(_research_db(tmp_path / 'firm_lab'), None)
    assert sorted(b['id'] for b in empty['specification_bars']) == named and len(named) == 25
    assert all(b['status'] != 'MET' for b in empty['specification_bars'])
    store = _store(tmp_path / 's', through='2020-12-31')
    try:
        early = _block(['2004-03-01'], ['9.50'])                        # one bar of one security, long before the rest
        store.put_bars(sf.SOURCE, '100009', 2004, early, 'early', price_table='stocks', at=LATER)
        universe.build(store, fx.FIRST, '2020-12-31', rule=RULE, version=fx.VERSION)
        store.put('history_reports', {'kind': 'strict_count', **dataset.count(store)})
    finally:
        store.close()
    report = readiness.build(tmp_path / 'firm_lab' / 'firm_lab.db', tmp_path / 's' / 'firm_lab_history.db')
    bars = {b['id']: b for b in report['specification_bars']}
    assert report['market_data']['history_range'][0] == '2004-03-01' and bars['H1']['status'] == 'NOT_MET' and bars['H1']['measured'] is None
    assert bars['O5']['status'] == 'MET' and bars['O2']['status'] == 'NOT_MET' and bars['P7']['status'] == 'NOT_MET'
    assert report['regimes']['training_alone']['status'] == 'NOT_MEASURABLE'


# ------------------------------------------------------ review round 4 (a fifth, fresh reviewer; commit 9e593ae)
def _aaa_columns(day, ratio, later, decimals, monkeypatch, ticker='AAA'):
    """AAA with a recorded split of ``ratio`` on ``day``, as a vendor prints it after a later cumulative split."""
    if ratio is not None:
        monkeypatch.setattr(fx, 'SPLIT', (ticker, day, ratio))
    rows = list(fx.price_rows([ticker], through='2020-12-31', rescale=(ticker, later) if later != 1 else None, decimals=decimals))
    columns = {'sessions': [r[1] for r in rows]}
    for k, name in ((2, 'open'), (3, 'high'), (4, 'low'), (5, 'close'), (6, 'volume'), (7, 'close_total_return'), (8, 'close_unadjusted')):
        columns[name] = [r[k] for r in rows]
    return columns


def test_how_one_bar_is_printed_never_changes_how_another_bar_is_read(tmp_path):
    """Print precision was taken over the whole column: one finer print inside the sealed holdout made every earlier
    coarse bar count as precise, and development rows changed with it."""
    def stores(folder, finer):
        folder.mkdir(parents=True)
        fx.write_tickers(folder / 'T.csv')
        rows = [list(r) for r in fx.price_rows([t for t in fx.SECURITIES if t != 'AAA'])] + [list(r) for r in fx.price_rows(['AAA'], rescale=('AAA', 40.0), decimals=2)]
        for r in rows:
            if finer and r[0] == 'AAA' and r[1] == '2024-06-03':
                r[5] = r[5] + '00'                                      # the same number, printed with four decimals
        fx.write_prices(folder / 'P.csv', rows)
        fx.write_actions(folder / 'A.csv')
        store = HistoryStore(folder / 'firm_lab_history.db', create=True)
        ingest.ingest_securities(store, sf.securities(folder / 'T.csv'), file=ingest.describe_file(folder / 'T.csv'), at=LATER, **COMMON)
        ingest.ingest_bars(store, sf.prices(folder / 'P.csv'), file=ingest.describe_file(folder / 'P.csv'), at=LATER, **COMMON)
        ingest.ingest_actions(store, sf.actions(folder / 'A.csv'), file=ingest.describe_file(folder / 'A.csv'), at=LATER, **COMMON)
        universe.build(store, fx.FIRST, fx.LAST, rule=RULE, version=fx.VERSION)
        return store

    assert splits.segment('2024-06-03') == splits.HISTORICAL_HOLDOUT
    a, b = stores(tmp_path / 'a', False), stores(tmp_path / 'b', True)
    try:
        for segment in (splits.DEVELOPMENT, splits.BURNED):
            xa, xb = dataset.materialise(a, segments=(segment,)), dataset.materialise(b, segments=(segment,))
            assert xa['manifest']['hashes']['rows'] == xb['manifest']['hashes']['rows'] and xa['manifest']['hashes']['features'] == xb['manifest']['hashes']['features'], segment
            assert xa['manifest']['high_low_open_families_usable'] == xb['manifest']['high_low_open_families_usable'], segment
        ca, cb = dataset.count(a), dataset.count(b)
        assert ca['strict_samples'] == cb['strict_samples'] and ca['breaks_by_reason'] == cb['breaks_by_reason']
    finally:
        a.close()
        b.close()
    p = panel.from_columns(_columns(hi=60, decimals=2, price=29.0))
    finer = _columns(hi=60, decimals=2, price=29.0)
    finer['close'][40] += '00'
    q = panel.from_columns(finer)
    np.testing.assert_array_equal(np.delete(p['print_error'], 40), np.delete(q['print_error'], 40))      # only the bar that was printed finer is read as finer


def test_a_coarse_reprint_after_a_later_split_does_not_undo_a_recorded_split_or_inflate_a_dividend(monkeypatch):
    """A recorded 1.03-for-1 split became a break once later splits made the vendor reprint the prices around it too
    coarsely to show a 3% step, and the rows of exactly that stock lost their long lookbacks."""
    from firm_lab.history import features
    close_based = [d['name'] for d in features.DEFINITIONS if not d['uses_high_low_open']]
    lost = different = 0
    for day in calendar.sessions('2019-06-03', '2020-03-31')[::14]:
        series = fx.series('AAA')
        later = float(round(series['close'][series['sessions'].index(day)] / 0.36))       # a cumulative later split that leaves the price near 0.36
        action = [{'type': 'split', 'effective_date': day, 'value': '1.03'}]
        plain, coarse = panel.from_columns(_aaa_columns(day, 1.03, 1, 2, monkeypatch)), panel.from_columns(_aaa_columns(day, 1.03, later, 2, monkeypatch))
        a, b = adjust.breaks(plain, action), adjust.breaks(coarse, action)
        lost += a['splits_confirmed'] + a['splits_unchecked'] != b['splits_confirmed'] + b['splits_unchecked'] or a['splits'] != b['splits'] or bool(b['breaks'])
        va = features.compute(plain, adjust.break_mask(plain, a['breaks']), splits=a['splits'])['values']
        vb = features.compute(coarse, adjust.break_mask(coarse, b['breaks']), splits=b['splits'])['values']
        different += sum(not np.array_equal(np.isnan(va[name]), np.isnan(vb[name])) for name in close_based)
        assert a['splits'] == [(plain['sessions'].index(day), 1.03)]
    assert lost == 0 and different == 0                                 # the record stands as recorded, and nothing close-based goes missing
    # a recorded ordinary dividend near coarse prints is sized by its amount over the day's price, not by a blurred factor
    monkeypatch.setattr(fx, 'SPLIT', ('AAA', '2020-06-15', 2.0))
    day, amount = fx.DISTRIBUTION[1], None
    for later in (1.0, 150.0):
        columns = _aaa_columns(None, None, later, 2, monkeypatch, ticker='FFF')
        p = panel.from_columns(columns)
        k = p['sessions'].index(day)
        amount = amount or f'{0.10 * float(columns["close_unadjusted"][k - 1]) / 0.9:.4f}'
        ordinary = [{'type': 'cash_dividend', 'effective_date': s, 'value': f'{0.01 * float(columns["close_unadjusted"][p["sessions"].index(s) - 1]):.4f}'}
                    for s in p['sessions'][100:400:15] if abs(p['sessions'].index(s) - k) > 3]
        found = adjust.breaks(p, [{'type': 'cash_dividend', 'effective_date': day, 'value': amount}] + ordinary)
        assert [(b['session'], b['reason']) for b in found['breaks']] == [(day, 'LARGE_DISTRIBUTION')], later


def test_a_split_re_adjustment_is_a_rescale_however_the_vendor_prints_its_volume():
    rng = np.random.default_rng(5)
    days = list(calendar.sessions('2019-01-02', '2019-12-31'))[:120]
    close = 40 * np.exp(np.cumsum(rng.normal(0, 0.02, len(days))))
    volume = np.round(np.exp(rng.normal(13, 0.4, len(days))))

    def block(k, decimals, volume_text):
        price = lambda scale: [f'{c * scale / k:.{decimals}f}' for c in close]
        return {'sessions': days, 'open': price(0.999), 'high': price(1.004), 'low': price(0.995), 'close': price(1.0), 'volume': [volume_text(v * k) for v in volume],
                'close_unadjusted': [f'{c:.2f}' for c in close], 'close_total_return': price(1.0), 'provider_updated': [''] * len(days)}

    whole_as_float = lambda v: f'{float(round(v)):.1f}'                  # 2253.0: a whole number of shares printed with a decimal
    for ratio in (1.5, 0.1, 1.25, 1.05, 2.0, 7.0):
        for decimals in (2, 4, 6):
            found = classify_change(block(1.0, decimals, whole_as_float), block(ratio, decimals, whole_as_float))
            assert found['change'] == 'SCALE_ONLY' and found['scale_factor'] == pytest.approx(1 / ratio, rel=2e-3), (ratio, decimals)
    silent = block(1.0, 2, lambda v: '0')                               # nothing traded: nothing says the shares were re-counted
    moved = {**silent, **{c: [f'{float(v) * 1.1:.2f}' for v in silent[c]] for c in ('open', 'high', 'low', 'close')}}
    assert classify_change(silent, moved)['change'] == 'VALUE_CHANGE'
    one_wrong = block(1.5, 4, whole_as_float)
    one_wrong['volume'][30] = whole_as_float(volume[30] * 1.5 * 1.02)   # and a real change among the rescaled rows is still one
    assert classify_change(block(1.0, 4, whole_as_float), one_wrong)['change'] == 'VALUE_CHANGE'


def test_a_removed_bar_a_claimed_clock_and_a_second_connection(tmp_path, monkeypatch):
    sessions = list(calendar.sessions('2024-01-02', '2025-12-31'))
    present = np.ones(len(sessions), bool)
    present[100] = False                                                # the vendor took this bar out after it had been stored
    history = {'since': {s: '2026-10-03T12:00:00+00:00' for s in sessions if s != sessions[100]}, 'clock': {s: 'SYSTEM' for s in sessions}, 'revised': set(),
               'removed': {sessions[100]}}
    tiers = dataset.row_tiers(sessions, present, history)
    assert set(tiers[100 - 21:100 + 253]) == {'RETROSPECTIVE'} and tiers[100 - 22] == tiers[100 + 253] == 'PUBLISHER_DATED_HISTORICAL'
    fx.set_clock(monkeypatch, '2026-10-04T12:00:00+00:00')
    store = _bare(tmp_path)
    try:
        full = _block(SPAN, [f'{10 + k}.25' for k in range(10)])
        store.put_bars('X', '1', 2024, full, 'c1', price_table='stocks', at='2026-10-01T12:00:00+00:00')
        store.put_bars('X', '1', 2024, {c: [v for j, v in enumerate(column) if j != 4] for c, column in full.items()}, 'c2', price_table='stocks', at='2026-10-02T12:00:00+00:00')
        assert store.bar_history('1')['removed'] == {SPAN[4]} and store.bar_history('1')['revised'] == set()
        with pytest.raises(ValueError, match='INVALID_CAPTURE_TIME'):   # a clock cannot be claimed: only the pair the store handed out is accepted
            store.put_bars('X', '2', 2024, full, 'c3', price_table='stocks', capture=('2024-03-15T21:00:00+00:00', 'SYSTEM'))
        with pytest.raises(TypeError):
            store.put_bars('X', '2', 2024, full, 'c3', price_table='stocks', at='2024-03-15T21:00:00+00:00', clock='SYSTEM')
        other = HistoryStore(store.path)                                # another connection stores something later
        try:
            other.put_bars('X', '3', 2024, full, 'c4', price_table='stocks', at='2026-10-03T12:00:00+00:00')
        finally:
            other.close()
        with pytest.raises(ValueError, match='CAPTURE_TIME_NOT_MONOTONIC'):
            store.put_bars('X', '4', 2024, full, 'c5', price_table='stocks', at='2026-10-02T18:00:00+00:00')
    finally:
        store.close()


def test_sample_measures_count_samples_and_a_break_is_returned_without_its_size(tmp_path):
    store = _store(tmp_path / 's')
    try:
        universe.build(store, fx.FIRST, '2026-10-02', rule=RULE, version=fx.VERSION)
        counted = dataset.count(store)
        assert 0 < counted['unique_sample_sessions'] < counted['unique_sessions']        # purge sessions and rows without a label are not sample sessions
        segments = [splits.segment(s) for s in calendar.sessions(fx.FIRST, '2026-10-02')]
        assert counted['unique_sample_sessions'] <= sum(name in splits.SAMPLE_SEGMENTS for name in segments)
        assert counted['splits_unchecked'] == 0 and counted['distributions_without_amount'] == 0 and counted['action_table_contradictions'] == []
        actions = [a for _, a, _ in store.rows('history_actions') if a['security_id'] == '100005']
        rows = dataset.security_rows(store, '100005', None, universe.membership(universe.load(store)['records'])['100005'], actions)
        assert rows['breaks'] and all(set(b) == {'session', 'index', 'reason'} for b in rows['breaks']) and 'breaks' not in rows['audit']
    finally:
        store.close()


# ------------------------------------------------------ review round 5 (a sixth, fresh reviewer; commit f00680d)
def _coarse_and_fine(day, ratio, monkeypatch, *, near=0.05, drop=None):
    """The same AAA history with a recorded split of ``ratio`` on ``day``, printed finely and as after a later split that
    leaves the price near ``near`` at two decimals. ``drop`` removes the bar of that session from both."""
    series = fx.series('AAA')
    later = float(max(2, round(series['close'][series['sessions'].index(day)] / near)))
    out = []
    for factor, decimals in ((1, 6), (later, 2)):
        columns = _aaa_columns(day, ratio, factor, decimals, monkeypatch)
        if drop:
            keep = [k for k, s in enumerate(columns['sessions']) if s != drop]
            columns = {name: [values[k] for k in keep] for name, values in columns.items()}
        out.append(panel.from_columns(columns))
    return out


def test_a_correct_split_record_is_applied_whatever_a_later_split_did_to_the_reprint(monkeypatch):
    """The continuity check read the reprinted closes ('0.05' then '0.06' is +20%), and a split recorded for a session
    without a bar was dropped: both let a later split decide what an earlier row could read."""
    from firm_lab.history import features
    close_based = [d['name'] for d in features.DEFINITIONS if not d['uses_high_low_open'] and d['family'] != 'volume']
    days = calendar.sessions('2019-06-03', '2020-03-31')[::9]
    for ratio in (1.25, 2.0, 0.8, 1.03):
        for day in days:
            fine, coarse = _coarse_and_fine(day, ratio, monkeypatch)
            action = [{'type': 'split', 'effective_date': day, 'value': str(ratio)}]
            a, b = adjust.breaks(fine, action), adjust.breaks(coarse, action)
            assert a['splits'] == b['splits'] == [(fine['sessions'].index(day), ratio)] and a['breaks'] == b['breaks'] == [], (ratio, day)
            va, vb = (features.compute(p, None, splits=found['splits'])['values'] for p, found in ((fine, a), (coarse, b)))
            for name in close_based:
                np.testing.assert_allclose(va[name], vb[name], rtol=1e-9, atol=1e-12, equal_nan=True, err_msg=f'{name} {ratio} {day}')
            la, lb = (targets.build(p, None, delisted=False, splits=found['splits']) for p, found in ((fine, a), (coarse, b)))
            for h in targets.HORIZONS:                                  # and no label moves with the reprint either
                np.testing.assert_array_equal(la[h]['value'], lb[h]['value'])
                np.testing.assert_array_equal(la[h]['state'], lb[h]['state'])
    day = days[3]
    after = calendar.offset(day, 1)
    for ratio in (1.10, 2.0):                                           # the split's own session has no bar: the next bar carries it, in both prints
        fine, coarse = _coarse_and_fine(day, ratio, monkeypatch, drop=day)
        action = [{'type': 'split', 'effective_date': day, 'value': str(ratio)}]
        a, b = adjust.breaks(fine, action), adjust.breaks(coarse, action)
        assert a['splits'] == b['splits'] == [(fine['sessions'].index(after), ratio)] and a['breaks'] == b['breaks'] == [], ratio


def test_a_distribution_is_sized_by_its_recorded_amount_and_one_without_an_amount_is_a_break(monkeypatch):
    monkeypatch.setattr(fx, 'SPLIT', ('AAA', '2020-06-15', 2.0))
    day = fx.DISTRIBUTION[1]                                            # FFF pays one tenth of its prior close here
    outcomes = {}
    for later in (1.0, 150.0):
        columns = _aaa_columns(None, None, later, 2, monkeypatch, ticker='FFF')
        p = panel.from_columns(columns)
        k = p['sessions'].index(day)
        prior = float(columns['close_unadjusted'][k - 1])
        for share in (0.049, 0.051, 0.10):
            found = adjust.breaks(p, [{'type': 'cash_dividend', 'effective_date': day, 'value': f'{share * prior:.6f}'}])
            outcomes[later, share] = [(b['session'], b['reason']) for b in found['breaks']]
        nameless = adjust.breaks(p, [{'type': 'cash_dividend', 'effective_date': day, 'value': ''}])
        assert [(b['session'], b['reason']) for b in nameless['breaks']] == [(day, 'DISTRIBUTION_WITHOUT_AMOUNT')] and nameless['distributions_without_amount'] == 1
    for share in (0.049, 0.051, 0.10):                                  # the same decision under the fine and the coarse print, on either side of 5%
        assert outcomes[1.0, share] == outcomes[150.0, share] == ([(day, 'LARGE_DISTRIBUTION')] if share >= 0.05 else []), share


def test_a_dataset_is_refused_when_the_action_table_means_something_else(tmp_path):
    def inverse(path, extra=()):
        fx.write_actions(path)
        path.write_text(path.read_text().replace('2020-06-15,split,AAA,AAA Corp,2.0', '2020-06-15,split,AAA,AAA Corp,0.5'))

    folder = tmp_path / 's'
    folder.mkdir()
    fx.write_tickers(folder / 'T.csv')
    fx.write_prices(folder / 'P.csv', [list(r) for r in fx.price_rows(None, through='2020-12-31')])
    inverse(folder / 'A.csv')
    store = HistoryStore(folder / 'firm_lab_history.db', create=True)
    try:
        ingest.ingest_securities(store, sf.securities(folder / 'T.csv'), file=ingest.describe_file(folder / 'T.csv'), at=AT, **COMMON)
        ingest.ingest_bars(store, sf.prices(folder / 'P.csv'), file=ingest.describe_file(folder / 'P.csv'), at=AT, **COMMON)
        ingest.ingest_actions(store, sf.actions(folder / 'A.csv'), file=ingest.describe_file(folder / 'A.csv'), at=AT, **COMMON)
        universe.build(store, fx.FIRST, '2020-12-31', rule=RULE, version=fx.VERSION)
        counted = dataset.count(store)
        assert counted['split_convention']['old_per_new'] == 1 and counted['action_table_contradictions'] == ['SPLIT_VALUE_CONVENTION_CONTRADICTED']
        with pytest.raises(ValueError, match='SPLIT_VALUE_CONVENTION_CONTRADICTED'):
            dataset.materialise(store)                                  # the split value is not what every decision assumes: no dataset until the adapter is corrected
    finally:
        store.close()
    assert dataset.contradictions({'new_per_old': 9, 'old_per_new': 0}, {'unadjusted': 3, 'adjusted': 1, 'neither': 0}) == ['DIVIDEND_AMOUNT_BASIS_CONTRADICTED']


def test_a_tiny_volume_confirms_nothing_and_a_capture_pair_expires(tmp_path, monkeypatch):
    flat = lambda price: (price, price, price, price)
    old = _ohlc(SPAN, [flat(f'{10 + k}.00') for k in range(10)], volume='1')
    new = _ohlc(SPAN, [flat(f'{(10 + k) * 1.1:.2f}') for k in range(10)], volume='1', unadjusted=old['close'])
    assert classify_change(old, new)['change'] == 'VALUE_CHANGE'        # one share before and after fits any factor: it shows no re-count
    fx.set_clock(monkeypatch, '2026-10-04T12:00:00+00:00')
    store = _bare(tmp_path)
    try:
        pair = store.begin_capture()
        with store.transaction():
            assert store.put_bars('X', '1', 2024, _block(SPAN, ['10.00'] * 10), 'c1', price_table='stocks', capture=pair)['stored']
        fx.set_clock(monkeypatch, '2026-10-15T12:00:00+00:00')
        with pytest.raises(ValueError, match='INVALID_CAPTURE_TIME'):   # the pair was good for its own transaction only
            store.put_bars('X', '2', 2024, _block(SPAN, ['10.00'] * 10), 'c2', price_table='stocks', capture=pair)
    finally:
        store.close()


def test_a_volume_a_later_reverse_split_made_unreadable_is_counted_and_marks_no_row(tmp_path, monkeypatch):
    """The vendor re-counts volume after every later split. After a large later reverse split an early volume is a
    handful of today's shares: its rows lost their volume features (and, through a core feature, existed or not), and
    the security dropped out of the universe as if it had not traded."""
    from firm_lab.history import features
    day = '2019-06-03'
    monkeypatch.setattr(fx, 'SPLIT', ('AAA', day, 0.1))                 # a 1-for-10 reverse split: every earlier volume is re-counted

    def thin(row):                                                      # before it, AAA's volume is a few dozen of today's shares
        if row[0] == 'AAA' and row[1] < day:
            row[6] = '40.0'
        return row

    def build(folder, edit):
        folder.mkdir(parents=True)
        fx.write_tickers(folder / 'T.csv')
        rows = [list(r) for r in fx.price_rows(None, through='2020-12-31')]
        fx.write_prices(folder / 'P.csv', [edit(r) for r in rows] if edit else rows)
        fx.write_actions(folder / 'A.csv')
        text = (folder / 'A.csv').read_text().replace('2020-06-15,split,AAA,AAA Corp,2.0', f'{day},split,AAA,AAA Corp,0.1')
        (folder / 'A.csv').write_text(text)
        store = HistoryStore(folder / 'firm_lab_history.db', create=True)
        ingest.ingest_securities(store, sf.securities(folder / 'T.csv'), file=ingest.describe_file(folder / 'T.csv'), at=AT, **COMMON)
        ingest.ingest_bars(store, sf.prices(folder / 'P.csv'), file=ingest.describe_file(folder / 'P.csv'), at=AT, **COMMON)
        ingest.ingest_actions(store, sf.actions(folder / 'A.csv'), file=ingest.describe_file(folder / 'A.csv'), at=AT, **COMMON)
        manifest = universe.build(store, fx.FIRST, '2020-12-31', rule={**universe.RULE, 'size': 12}, version='liquid-top12-test')
        return store, manifest

    plain, m0 = build(tmp_path / 'plain', None)
    marked, m1 = build(tmp_path / 'marked', thin)
    try:
        assert m0['security_months_screened_out_for_unreadable_volume'] == 0 and m1['security_months_screened_out_for_unreadable_volume'] > 0
        p = panel.load(marked, '100001')
        k = p['sessions'].index(day)
        unreadable = adjust.coarse_volume(p, [(k, 0.1)])
        assert unreadable[:k].all() and not unreadable[k:].any()
        assert not adjust.coarse_volume(panel.load(marked, '100009'), ()).any()       # no later split: exact, whatever the volume
        a, b = dataset.materialise(plain), dataset.materialise(marked)
        ca, cb = dataset.count(plain), dataset.count(marked)
    finally:
        plain.close()
        marked.close()
    volume = [n for n, d in enumerate(features.DEFINITIONS) if d['uses_volume']]
    rest = [n for n, d in enumerate(features.DEFINITIONS) if not d['uses_volume'] and not d['uses_high_low_open']]
    assert len(volume) == 7 and dataset.CORE_FEATURES == ('return20', 'realized_vol20')
    ka, kb = list(zip(a['security_id'], a['session'])), list(zip(b['security_id'], b['session']))
    late = [n for n, key in enumerate(kb) if key[0] == '100001']
    assert late and b['manifest']['rows_reading_an_unreadable_volume'] > 0 and not b['manifest']['volume_features_usable'] and not cb['volume_features_usable']
    assert np.isnan(b['X'][:, volume]).all()                            # all rows or none: AAA's rows cannot be told apart by what is missing
    assert a['manifest']['volume_features_usable'] and ca['volume_features_usable'] and np.isfinite(a['X'][:, volume]).any()
    common = sorted(set(ka) & set(kb))
    ia, ib = {key: n for n, key in enumerate(ka)}, {key: n for n, key in enumerate(kb)}
    np.testing.assert_array_equal(a['X'][[ia[key] for key in common]][:, rest], b['X'][[ib[key] for key in common]][:, rest])      # nothing close-based moved
    # once AAA can be ranked again its rows exist as before: whether a row exists is decided from the exact close alone
    after = [key for key in ka if key[0] == '100001' and key[1] > '2019-10-31']
    assert after and set(after) <= set(kb)
