"""Checkpoint 8: the historical universe, labels, the strict point-in-time sample count and the sealed holdouts.

What is proven here: membership at a date is formed only from bars up to that date and never changes when later data
arrives; delisted companies are members while they qualified; a source of survivors is refused; a label starts after
the last feature bar; a row built from an archive is tier B, never tier A; no label value of a sealed holdout is ever
returned or used; and the same inputs give the same dataset hash."""
import numpy as np
import pytest

import history_fixture as fx
from firm_lab.history import HELD_AT_THE_TIME, PUBLISHER_DATED_HISTORICAL, RETROSPECTIVE, calendar, dataset, ingest, lowest_tier, panel, sharadar_files as sf, splits, targets, universe
from firm_lab.history.store import HistoryStore

AT = '2026-10-03T12:00:00+00:00'
COMMON = {'source': sf.SOURCE, 'adapter': sf.ADAPTER}
RULE = {**universe.RULE, 'size': 6}


def _store(folder, *, through=fx.LAST, rescale=None, tickers=None, without_delisted=False, edit=None):
    folder.mkdir(parents=True, exist_ok=True)
    fx.write_tickers(folder / 'T.csv', without_delisted=without_delisted)
    rows = [list(r) for r in fx.price_rows(tickers, through=through, rescale=rescale) if not without_delisted or not fx.SECURITIES[r[0]][4]]
    if edit:
        rows = [edit(r) for r in rows]
    fx.write_prices(folder / 'P.csv', rows)
    fx.write_actions(folder / 'A.csv')
    store = HistoryStore(folder / 'firm_lab_history.db', create=True)
    ingest.ingest_securities(store, sf.securities(folder / 'T.csv'), file=ingest.describe_file(folder / 'T.csv'), at=AT, **COMMON)
    ingest.ingest_bars(store, sf.prices(folder / 'P.csv'), file=ingest.describe_file(folder / 'P.csv'), at=AT, **COMMON)
    ingest.ingest_actions(store, sf.actions(folder / 'A.csv'), file=ingest.describe_file(folder / 'A.csv'), at=AT, **COMMON)
    return store


@pytest.fixture(scope='module')
def built(tmp_path_factory):
    store = _store(tmp_path_factory.mktemp('full'))
    manifest = universe.build(store, fx.FIRST, '2026-10-02', rule=RULE)
    counted = dataset.count(store)
    yield store, manifest, counted
    store.close()


# ---------------------------------------------------------------------------------------------------------- universe
def test_the_universe_is_deterministic_and_every_record_is_known_before_it_takes_effect(built):
    store, manifest, _ = built
    again = universe.build(store, fx.FIRST, '2026-10-02', rule=RULE)
    assert again['universe_hash'] == manifest['universe_hash'] and again['records_hash'] == manifest['records_hash']
    loaded = universe.load(store)
    assert loaded['manifest']['universe_hash'] == manifest['universe_hash'] and len(loaded['records']) == manifest['formation_sessions'] == 100
    for record in loaded['records']:
        assert record['effective_from'] == calendar.offset(record['formation_session'], 1)
        assert record['known_at'] == calendar.eligible_from(record['formation_session'])              # the open of the first effective session
        assert record['known_at'] > calendar.session_close(record['formation_session']) and record['tier'] == PUBLISHER_DATED_HISTORICAL
        assert record['member_count'] <= 6 and record['members'] == sorted(record['members'])
    first_full = next(r for r in loaded['records'] if r['member_count'] == 6)
    assert first_full['formation_session'] == '2019-06-28'                                            # 252 bars of history after 2018-06-01, then the month end
    assert loaded['records'][5]['screened_out'] == {'INSUFFICIENT_HISTORY': 13}
    assert manifest['rule'] == RULE and 'sector' not in str(manifest['rule']).lower() and 'category' not in str(manifest['rule']).lower()


def test_membership_at_a_date_does_not_change_when_later_data_arrives(built, tmp_path):
    store, _, _ = built
    early = _store(tmp_path / 'early', through='2021-12-31')
    try:
        universe.build(early, fx.FIRST, '2021-12-31', rule=RULE)
        then = {r['formation_session']: r for r in universe.load(early)['records']}
    finally:
        early.close()
    now = {r['formation_session']: r for r in universe.load(store)['records']}
    assert len(then) == 43
    for session, record in then.items():
        for key in ('members', 'eligible_count', 'screened_out', 'effective_from', 'known_at', 'smallest_member_median_dollar_volume'):
            assert record[key] == now[session][key], (session, key)                                  # four more years of bars changed nothing before them


def test_delisted_companies_are_members_while_they_qualified_and_survivors_alone_are_refused(built, tmp_path):
    store, manifest, _ = built
    spans = universe.membership(universe.load(store)['records'])
    assert manifest['members_later_delisted'] == 2
    acquired, bankrupt = spans['100003'], spans['100004']
    assert acquired[0][0] == '2019-07-01' and any(first <= '2021-06-30' <= last for first, last in acquired)      # a member in the month it was taken over
    assert bankrupt[-1][0] <= '2020-09-15' <= bankrupt[-1][1] and all(first <= '2020-09-15' for first, _ in bankrupt)
    # its last bar fell on a formation session, so the rule (which cannot see the future) named it for one more month; it has no bar there, so no row
    assert acquired[-1] == ('2021-07-01', '2021-07-30')
    rows = dataset.security_rows(store, '100003', ingest.current_securities(store)['100003'], acquired, [])
    assert rows['sessions'][-1] == '2021-06-30' and rows['eligible'].sum() > 400
    survivors = _store(tmp_path / 'survivors', through='2020-01-31', without_delisted=True)
    try:
        with pytest.raises(ValueError, match='SURVIVOR_ONLY_SOURCE'):
            universe.build(survivors, fx.FIRST, '2020-01-31', rule=RULE)
    finally:
        survivors.close()


def test_the_price_screen_reads_the_printed_price_and_liquidity_ranks_the_rest(built, tmp_path):
    store, _, _ = built
    records = universe.load(store)['records']
    spans = universe.membership(records)
    assert '100008' not in spans                                                                      # two dollars: below the minimum on every formation
    assert '100013' not in spans                                                                      # qualifies, but ranks below the six most traded
    full = next(r for r in records if r['formation_session'] == '2019-12-31')
    assert full['screened_out'] == {'PRICE_BELOW_MINIMUM': 1, 'RANKED_BELOW_SIZE': 6} and full['eligible_count'] == 12
    resplit = _store(tmp_path / 'resplit', through='2020-01-31', rescale=('AAA', 40.0))               # as if AAA split 40-for-1 later: adjusted close near 2 dollars
    try:
        universe.build(resplit, fx.FIRST, '2020-01-31', rule=RULE)
        after = {r['formation_session']: r['members'] for r in universe.load(resplit)['records']}
    finally:
        resplit.close()
    for record in records:
        if record['formation_session'] <= '2019-12-31':
            assert after[record['formation_session']] == record['members']                           # the printed price and the dollar volume did not change
    assert '100001' in after['2019-12-31']


def test_a_member_is_used_from_the_session_after_formation(built):
    store, _, _ = built
    spans = universe.membership(universe.load(store)['records'])['100001']
    sessions = calendar.sessions('2019-06-25', '2019-07-05')
    mask = universe.member_mask(sessions, spans)
    assert dict(zip(sessions, mask))['2019-06-28'] == False and dict(zip(sessions, mask))['2019-07-01'] == True       # noqa: E712


# ------------------------------------------------------------------------------------------------------------ labels
def test_a_label_starts_at_the_open_after_the_last_feature_bar(built):
    store, _, _ = built
    p = panel.load(store, '100009')
    labels = targets.build(p, None, delisted=False)
    t = 500
    for h in targets.HORIZONS:
        assert labels[h]['value'][t] == pytest.approx(p['open'][t + 1 + h] / p['open'][t + 1] - 1)
        assert labels[h]['state'][t] == targets.OK and labels[h]['exit_index'][t] == t + 1 + h
    changed = dict(p)
    for name in ('open', 'high', 'low', 'close', 'volume'):
        changed[name] = p[name].copy()
        changed[name][:t + 1] *= 3.0                                                                  # everything at or before T
    again = targets.build(changed, None, delisted=False)
    assert again[20]['value'][t] == labels[20]['value'][t]                                            # the label uses nothing the features use
    moved = dict(p)
    moved['open'] = p['open'].copy()
    moved['open'][t + 1] *= 1.1
    assert targets.build(moved, None, delisted=False)[20]['value'][t] != labels[20]['value'][t]
    assert targets.TARGET_VERSION == 'forward-open-to-open-price-return-v2'


def test_labels_through_a_delisting_are_kept_and_flagged_and_the_end_of_the_data_is_not_a_delisting(built):
    store, _, _ = built
    gone = panel.load(store, '100003')
    last = len(gone['sessions']) - 1
    labels = targets.build(gone, None, delisted=True)[20]
    assert labels['state'][last] == targets.NO_ENTRY and np.isnan(labels['value'][last])              # nothing to buy after the last bar
    assert labels['state'][last - 1] == targets.DELISTED_EXIT and labels['value'][last - 1] == pytest.approx(gone['close'][last] / gone['open'][last] - 1)
    assert labels['state'][last - 21] == targets.OK and labels['state'][last - 20] == targets.DELISTED_EXIT
    assert labels['exit_index'][last - 5] == last
    listed = panel.load(store, '100009')
    end = len(listed['sessions']) - 1
    still = targets.build(listed, None, delisted=False)[20]
    assert set(still['state'][end - 20:]) == {targets.PAST_HISTORY} and np.all(np.isnan(still['value'][end - 20:])) and still['state'][end - 21] == targets.OK


def test_a_label_window_that_holds_a_break_is_excluded_and_one_that_starts_on_it_is_not(built):
    store, _, _ = built
    p = panel.load(store, '100005')
    k = p['sessions'].index('2020-08-03')                                                             # the spin-off ex-date: the open of k already reflects it
    mask = np.zeros(len(p['sessions']), bool)
    mask[k] = True
    labels = targets.build(p, mask, delisted=False)[5]
    assert labels['state'][k - 1] == targets.OK                                                       # entry at the open of k, after the gap
    assert labels['state'][k - 2] == targets.HAS_BREAK and np.isnan(labels['value'][k - 2])           # entry at k-1, exit after k: the gap is inside
    assert labels['state'][k - 7] == targets.OK and labels['state'][k - 6] == targets.HAS_BREAK       # exit at the open of k-1 is clean; exit at the open of k is not


# ----------------------------------------------------------------------------------------------- strict sample count
def test_the_strict_count_is_honest_about_tiers_segments_and_what_it_did_not_read(built):
    store, manifest, counted = built
    assert counted['universe_hash'] == manifest['universe_hash'] and counted['dataset_version'] == 'pit-dataset-v2'
    assert counted['retrospective_samples'] == 0
    assert counted['by_tier'] == {HELD_AT_THE_TIME: 0, PUBLISHER_DATED_HISTORICAL: counted['eligible_feature_rows']}      # an archive is never "held at the time"
    assert counted['strict_samples']['5'] >= counted['strict_samples']['10'] >= counted['strict_samples']['20'] > 0
    assert sum(part['eligible_feature_rows'] for part in counted['by_segment'].values()) == counted['eligible_feature_rows'] <= counted['raw_member_rows']
    assert counted['by_segment'][splits.FORWARD_HOLDOUT]['eligible_feature_rows'] == 0 and counted['by_segment'][splits.BURN_IN]['eligible_feature_rows'] == 0
    assert counted['by_segment'][splits.HISTORICAL_HOLDOUT]['sessions'] == len(calendar.sessions(splits.HOLDOUT_FIRST, splits.holdout_last_sample()))
    assert counted['delisting_exits_by_reason'] == {'delisted': 20, 'bankruptcyliquidation': 20}      # kept, and counted by the provider's reason
    assert counted['breaks_by_reason'] == {'SPIN_OFF': 1, 'LARGE_DISTRIBUTION': 1, 'SPLIT_FACTOR_WITHOUT_ACTION': 1} and counted['splits_confirmed'] == 1
    states = counted['label_states']['20']
    assert states['EXIT_AT_LAST_PRICE_BEFORE_DELISTING'] == 40 and states['LABEL_WINDOW_HAS_BREAK'] > 0 and states['WINDOW_PAST_STORED_HISTORY'] > 0
    effective = counted['effective']
    assert effective['5']['breadth']['n_eff'] <= effective['5']['breadth']['instruments_per_window'] == 6.0
    assert effective['20']['breadth']['n_eff'] is None and effective['20']['detectable_ic_holdout'] is None      # too few windows to measure: not assumed
    assert effective['20']['holdout_testability'] == 'NOT_MEASURABLE' and effective['5']['holdout_testability'] == 'NOT_TESTABLE'
    spec = counted['manifest']
    assert spec['target_version'] == targets.TARGET_VERSION and spec['split_version'] == splits.SPLIT_VERSION and len(spec['captures']) == 3
    assert all(len(c['sha256']) == 64 for c in spec['captures']) and len(spec['feature_code_hash']) == 64


def test_no_label_value_of_a_sealed_holdout_is_returned_or_used(built, tmp_path):
    store, _, counted = built
    securities = ingest.current_securities(store)
    spans = universe.membership(universe.load(store)['records'])
    rows = dataset.security_rows(store, '100009', securities['100009'], spans['100009'], [])
    sealed = np.isin(rows['segment'], splits.SEALED)
    assert sealed.sum() > 1000
    for h in targets.HORIZONS:
        assert np.all(np.isnan(rows['labels'][h]['value'][sealed]))                                   # the value is gone before the rows leave the builder
        assert (rows['labels'][h]['state'][sealed] == targets.OK).sum() > 1000                        # whether a label can be built is still known
        assert np.isfinite(rows['labels'][h]['value'][rows['segment'] == splits.DEVELOPMENT]).sum() > 100
    for name in (splits.HISTORICAL_HOLDOUT, splits.FORWARD_HOLDOUT):
        with pytest.raises(ValueError, match='SEALED_SEGMENT'):
            dataset.materialise(store, segments=(name,))
        assert not splits.labels_allowed(name)

    def spoil(first, last):
        def edit(row):                                                 # change only the opens inside [first, last]: labels there change, nothing else does
            if first <= row[1] <= last:
                row[2] = f'{min(float(row[2]) * 1.004, float(row[3])):.6f}'
            return row
        return edit

    def recount(folder, edit):
        other = _store(folder, edit=edit)
        try:
            universe.build(other, fx.FIRST, '2026-10-02', rule=RULE)
            return dataset.count(other)
        finally:
            other.close()

    same = recount(tmp_path / 'holdout-changed', spoil(splits.HOLDOUT_FIRST, splits.HOLDOUT_LAST))
    assert same['effective'] == counted['effective'] and same['strict_samples'] == counted['strict_samples'] and same['by_segment'] == counted['by_segment']
    moved = recount(tmp_path / 'development-changed', spoil('2019-08-01', '2020-10-30'))
    assert moved['effective']['5']['breadth'] != counted['effective']['5']['breadth']                 # the measure does read development labels, and only those


def test_a_dataset_is_reproducible_and_its_hash_names_its_inputs(built, tmp_path):
    store, manifest, _ = built
    a, b = dataset.materialise(store), dataset.materialise(store)
    assert a['manifest']['dataset_hash'] == b['manifest']['dataset_hash'] and a['manifest'] == b['manifest']
    assert set(splits.segment(s) for s in a['session']) == {splits.DEVELOPMENT} and max(a['session']) <= splits.development_last()
    assert a['X'].shape == (len(a['session']), len(a['feature_names'])) and set(a['tier']) == {PUBLISHER_DATED_HISTORICAL}
    assert a['manifest']['universe_hash'] == manifest['universe_hash'] and a['manifest']['rows'] == len(a['session']) > 1000
    assert list(zip(a['session'], a['security_id'])) == sorted(zip(a['session'], a['security_id']))
    for h in targets.HORIZONS:                                         # the excess label sums to zero within a session
        finite = np.isfinite(a['y_excess'][h])
        sessions = np.array(a['session'])
        for s in ('2019-10-01', '2020-03-16', '2020-10-01'):
            assert abs(a['y_excess'][h][finite & (sessions == s)].sum()) < 1e-12
    core = [a['feature_names'].index(n) for n in dataset.CORE_FEATURES]
    assert np.all(np.isfinite(a['X'][:, core]))
    assert dataset.register(store, a) is True and dataset.register(store, b) is False
    burned = dataset.materialise(store, segments=(splits.BURNED,))
    assert burned['manifest']['dataset_hash'] != a['manifest']['dataset_hash'] and set(splits.segment(s) for s in burned['session']) == {splits.BURNED}

    def nudge(row):
        if row[0] == 'III' and row[1] == '2020-02-10':
            row[5] = f'{float(row[5]) * 1.0001:.6f}'
            row[3] = f'{max(float(row[3]), float(row[5])):.6f}'
        return row

    other = _store(tmp_path / 'one-bar-changed', edit=nudge)
    try:
        universe.build(other, fx.FIRST, '2026-10-02', rule=RULE)
        c = dataset.materialise(other)
    finally:
        other.close()
    assert c['manifest']['dataset_hash'] != a['manifest']['dataset_hash'] and c['manifest']['source_blocks_hash'] != a['manifest']['source_blocks_hash']


def test_a_row_is_tier_a_only_when_every_one_of_its_last_252_bars_was_held_at_the_time():
    sessions = list(calendar.sessions('2024-01-02', '2025-12-31'))
    present = np.ones(len(sessions), bool)
    archive = {s: '2026-10-03T12:00:00+00:00' for s in sessions}
    assert set(dataset.row_tiers(sessions, present, archive)) == {PUBLISHER_DATED_HISTORICAL}
    start = 100                                                        # from this session on, each bar was stored the evening of its own session
    forward = {s: (calendar.session_close(s) if k >= start else '2026-10-03T12:00:00+00:00') for k, s in enumerate(sessions)}
    tiers = dataset.row_tiers(sessions, present, forward)
    assert list(tiers[:start + 251]) == [PUBLISHER_DATED_HISTORICAL] * (start + 251) and set(tiers[start + 251:]) == {HELD_AT_THE_TIME}
    late = dict(forward)
    late[sessions[400]] = calendar.session_close(sessions[402])        # one bar arrived two days late
    tiers = dataset.row_tiers(sessions, present, late)
    assert tiers[399] == HELD_AT_THE_TIME and set(tiers[400:500]) == {PUBLISHER_DATED_HISTORICAL}
    assert lowest_tier([HELD_AT_THE_TIME, PUBLISHER_DATED_HISTORICAL]) == PUBLISHER_DATED_HISTORICAL
    assert lowest_tier([HELD_AT_THE_TIME, 'UNKNOWN']) == RETROSPECTIVE and lowest_tier([]) == RETROSPECTIVE


def test_without_a_stored_universe_the_count_is_zero_and_says_why(tmp_path):
    store = _store(tmp_path / 'bare', through='2018-12-31', tickers=['III'])
    try:
        counted = dataset.count(store)
        assert counted['strict_samples'] == {'5': 0, '10': 0, '20': 0} and counted['reason'] == 'NO_STORED_UNIVERSE'
        with pytest.raises(ValueError, match='NO_STORED_UNIVERSE'):
            dataset.materialise(store)
    finally:
        store.close()


# ------------------------------------------------------------------------------------------------------------ splits
def test_the_reserved_chronology_never_reuses_the_checkpoint_7_window_and_seals_both_holdouts():
    r = splits.reservation()
    assert r['checkpoint7_holdout_reused_as_pristine'] is False and r['sealed'] == ['HISTORICAL_HOLDOUT', 'FORWARD_HOLDOUT']
    assert r['segments']['HISTORICAL_HOLDOUT'] == ['2021-01-04', '2025-03-28'] and r['segments']['BURNED_CHECKPOINT7'] == ['2025-03-31', '2026-10-02']
    assert r['segments']['FORWARD_HOLDOUT'] == ['2026-10-05', None] and r['segments']['DEVELOPMENT'] == ['1999-01-04', '2020-11-23']
    for session in ('2025-03-31', '2026-06-09', '2026-09-01'):                                       # Checkpoint 7's window; its holdout ran 2026-06-09 to 2026-09-01
        assert splits.segment(session) == splits.BURNED and splits.BURNED not in splits.SEALED
    for session in ('2026-09-03', '2026-09-30', '2026-10-02'):                                       # the tail: a label from here would end in the forward holdout
        assert splits.segment(session) == splits.PURGED
    assert r['last_burned_sample_session'] == '2026-09-02' and r['label_values_readable_in'] == ['DEVELOPMENT', 'BURNED_CHECKPOINT7']
    assert splits.segment('1998-06-01') == splits.BURN_IN and splits.segment('1999-01-04') == splits.DEVELOPMENT and splits.segment('2020-11-23') == splits.DEVELOPMENT
    assert splits.segment('2020-11-24') == splits.PURGED and splits.segment('2020-12-31') == splits.PURGED and splits.segment('2021-01-04') == splits.HISTORICAL_HOLDOUT
    gap = calendar.sessions('2020-11-24', '2020-12-31')
    assert len(gap) == splits.PURGE == targets.MAX_HORIZON + 1 + splits.EMBARGO == 26
    last = splits.holdout_last_sample()
    assert calendar.offset(last, targets.MAX_HORIZON + 1) == '2025-03-28'                             # its longest label ends at the holdout's last open
    assert splits.segment(last) == splits.HISTORICAL_HOLDOUT and splits.segment(calendar.offset(last, 1)) == splits.PURGED
    assert splits.segment('2026-10-05') == splits.FORWARD_HOLDOUT and splits.segment('2027-01-04') == splits.FORWARD_HOLDOUT
    for day in ('2026-10-03', '2030-01-02'):                                                          # a Saturday; a date past the calendar
        with pytest.raises(ValueError, match='NOT_AN_EXCHANGE_SESSION'):
            splits.segment(day)
    assert splits.labels_allowed(splits.DEVELOPMENT) and not splits.labels_allowed(splits.PURGED)
    assert not [name for name in dir(splits) if 'unseal' in name.lower()]                             # this checkpoint has no way to open a holdout
