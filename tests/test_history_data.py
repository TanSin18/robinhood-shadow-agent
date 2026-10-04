"""Checkpoint 8: the historical research database, ingestion and bar validation.

What is proven here: the file is separate, append-only and versioned; a failing row is rejected with its reasons and
never repaired; conflicting duplicates are both rejected; a symbol is only a label; corporate-action inconsistencies
are found and named; nothing can be stored beside the registered database or inside a repository."""
import csv
import sqlite3

import numpy as np
import pytest

import history_fixture as fx
from firm_lab.history import DATABASE_ROLE, adjust, calendar, ingest, panel, sharadar_files as sf
from firm_lab.history.store import BAR_TABLE, JSON_TABLES, HistoryStore, classify_change
from firm_lab.history.validate import REASONS, bar_reasons

AT = '2026-10-03T12:00:00+00:00'
COMMON = {'source': sf.SOURCE, 'adapter': sf.ADAPTER}


def _ingest(store, files, at=AT):
    out = {'securities': ingest.ingest_securities(store, sf.securities(files['tickers']), file=ingest.describe_file(files['tickers']), at=at, **COMMON),
           'bars': ingest.ingest_bars(store, sf.prices(files['prices']), file=ingest.describe_file(files['prices']), at=at, **COMMON)}
    if 'actions' in files:
        out['actions'] = ingest.ingest_actions(store, sf.actions(files['actions']), file=ingest.describe_file(files['actions']), at=at, **COMMON)
    if 'sp500' in files:
        out['index'] = ingest.ingest_index_events(store, sf.index_events(files['sp500']), file=ingest.describe_file(files['sp500']), at=at, **COMMON)
    return out


@pytest.fixture(scope='module')
def stored(tmp_path_factory):
    folder = tmp_path_factory.mktemp('history')
    files = fx.provider(folder)
    with HistoryStore(folder / 'firm_lab_history.db', create=True) as store:
        receipts = _ingest(store, files)
    return folder, files, receipts


def _bar(**changes):
    row = {'symbol': 'AAA', 'session': '2024-03-04', 'open': '10', 'high': '11', 'low': '9.5', 'close': '10.5', 'volume': '1000', 'close_unadjusted': '10.5'}
    row.update(changes)
    return row


# ------------------------------------------------------------------------------------------------------ bar validity
@pytest.mark.parametrize('changes, reason', [
    ({'open': '0'}, 'NON_POSITIVE_PRICE'), ({'close': '-1'}, 'NON_POSITIVE_PRICE'), ({'close_unadjusted': '0'}, 'NON_POSITIVE_PRICE'),
    ({'low': '10.2'}, 'LOW_ABOVE_OPEN_OR_CLOSE'), ({'high': '10.2'}, 'HIGH_BELOW_OPEN_OR_CLOSE'), ({'low': '12', 'high': '11'}, 'LOW_ABOVE_HIGH'),
    ({'volume': '-5'}, 'NEGATIVE_VOLUME'), ({'high': 'nan'}, 'NOT_FINITE'), ({'open': 'abc'}, 'NOT_FINITE'), ({'close': ''}, 'MISSING_FIELD'),
    ({'session': '2024-03-03'}, 'NOT_AN_EXCHANGE_SESSION'), ({'session': '2024-12-25'}, 'NOT_AN_EXCHANGE_SESSION'), ({'session': '2026-10-05'}, 'SESSION_NOT_COMPLETE_AT_CAPTURE')])
def test_an_invalid_bar_is_named_not_repaired(changes, reason):
    reasons = bar_reasons(_bar(**changes), captured_at=AT)
    assert reason in reasons and set(reasons) <= set(REASONS)


def test_a_valid_bar_has_no_reason_and_zero_volume_is_allowed():
    assert bar_reasons(_bar(), captured_at=AT) == []
    assert bar_reasons(_bar(volume='0'), captured_at=AT) == []
    assert bar_reasons(_bar(open='10', high='10', low='10', close='10'), captured_at=AT) == []        # a flat bar is a bar


def test_a_bar_is_usable_only_from_the_next_session_open_and_a_half_day_closes_early():
    assert calendar.session_close('2024-11-29') == '2024-11-29T18:00:00+00:00'                       # the day after Thanksgiving closes at 13:00 New York
    assert calendar.eligible_from('2024-11-29') == '2024-12-02T14:30:00+00:00'                       # the next session is Monday
    assert calendar.eligible_from('2024-11-29') > calendar.session_close('2024-11-29')
    assert not calendar.is_session('2001-09-11') and not calendar.is_session('2012-10-29')          # closures are not sessions
    with pytest.raises(ValueError, match='NOT_AN_EXCHANGE_SESSION'):
        calendar.eligible_from('2024-11-28')


# --------------------------------------------------------------------------------------------------------- ingestion
def test_ingestion_gives_a_receipt_and_rejects_rows_with_reasons(stored):
    folder, files, receipts = stored
    bars = receipts['bars']
    expected = sum(1 for _ in fx.price_rows())
    future = sum(1 for r in fx.price_rows() if r[1] > '2026-10-02')
    assert bars['rows_read'] == expected and bars['rows_rejected'] == future and bars['rows_stored'] == expected - future
    assert bars['rejections_by_reason'] == {'SESSION_NOT_COMPLETE_AT_CAPTURE': future}
    assert bars['known_at_version'] == 'bar-known-at-v1' and bars['basis']['close_unadjusted'] == 'UNADJUSTED' and bars['basis']['open'] == 'SPLIT_ADJUSTED_AS_OF_CAPTURE'
    assert receipts['actions']['rejections_by_reason'] == {'UNKNOWN_SECURITY': 1}                    # an action for a ticker that is not in the master
    with HistoryStore(folder / 'firm_lab_history.db', read_only=True) as store:
        captures = {p['kind']: p for _, p, _ in store.rows('history_captures')}
        assert set(captures) == {'securities', 'bars', 'actions', 'index_events'}
        assert captures['bars']['sha256'] == ingest.describe_file(files['prices'])['sha256'] and captures['bars']['file'] == 'SEP.csv'
        assert store.count('history_bar_rejections') == future
        rejection = next(store.rows('history_bar_rejections'))[1]
        assert rejection['reasons'] == ['SESSION_NOT_COMPLETE_AT_CAPTURE'] and rejection['row']['close']       # the refused row is kept as evidence
        assert store.bar_summary()['bars'] == expected - future


def test_the_same_file_twice_stores_nothing_new(stored, tmp_path):
    folder, files, _ = stored
    with HistoryStore(tmp_path / 'h.db', create=True) as store:
        first = _ingest(store, files)
        again = _ingest(store, files, at='2026-10-03T13:00:00+00:00')
        assert again['bars']['rows_stored'] == 0 and again['bars']['blocks_stored'] == 0 and again['bars']['blocks_duplicate'] == first['bars']['blocks_stored']
        assert again['securities']['rows_stored'] == 0 and again['actions']['rows_stored'] == 0
        assert store.count('history_captures') == 8                                                   # every run leaves its own receipt


def test_conflicting_duplicates_are_both_rejected_and_identical_duplicates_are_kept_once(tmp_path):
    rows = list(fx.price_rows(['III'], through='2019-01-31'))
    twin = list(rows[5])
    clash = list(rows[9])
    clash[5] = f'{float(clash[5]) * 1.0001:.6f}'                                                      # same session, a different close
    fx.write_tickers(tmp_path / 'T.csv')
    fx.write_prices(tmp_path / 'P.csv', rows + [twin, clash])
    with HistoryStore(tmp_path / 'h.db', create=True) as store:
        ingest.ingest_securities(store, sf.securities(tmp_path / 'T.csv'), file=ingest.describe_file(tmp_path / 'T.csv'), at=AT, **COMMON)
        receipt = ingest.ingest_bars(store, sf.prices(tmp_path / 'P.csv'), file=ingest.describe_file(tmp_path / 'P.csv'), at=AT, **COMMON)
        assert receipt['rows_duplicate_identical'] == 1 and receipt['rejections_by_reason'] == {'CONFLICTING_DUPLICATE': 2}
        assert receipt['rows_stored'] == len(rows) - 1                                                # the conflicted session is absent; nothing was chosen
        sessions = store.bars('100009')['sessions']
        assert rows[9][1] not in sessions and rows[5][1] in sessions and len(sessions) == len(set(sessions))
        assert not list((tmp_path).glob('h.db.staging-*'))                                            # the staging file is removed


def test_unknown_and_reused_symbols_are_rejected_and_bad_rows_never_reach_the_store(tmp_path):
    rows = list(fx.price_rows(['III'], through='2018-06-29'))
    bad = [['NOPE'] + rows[0][1:], ['JJJ'] + rows[1][1:], ['III', '2018-06-30'] + rows[2][2:], ['III', rows[3][1], '10', '9', '8', '9.5', '100', '9.5', '9.5', 'x']]
    reused = {'table': 'SEP', 'permaticker': 999999, 'ticker': 'JJJ', 'name': 'Another JJJ', 'exchange': 'NYSE', 'isdelisted': 'Y', 'category': 'Domestic Common Stock',
              'currency': 'USD', 'firstpricedate': '2001-01-02', 'lastpricedate': '2009-01-02'}
    foreign = {'table': 'SEP', 'permaticker': 888888, 'ticker': 'EUR1', 'name': 'Euro Co', 'exchange': 'NYSE', 'isdelisted': 'N', 'category': 'ADR Common Stock',
               'currency': 'EUR', 'firstpricedate': fx.FIRST, 'lastpricedate': fx.LAST}
    fx.write_tickers(tmp_path / 'T.csv', extra=[reused, foreign])
    fx.write_prices(tmp_path / 'P.csv', rows[4:] + bad + [['EUR1'] + rows[4][1:]])
    with HistoryStore(tmp_path / 'h.db', create=True) as store:
        ingest.ingest_securities(store, sf.securities(tmp_path / 'T.csv'), file=ingest.describe_file(tmp_path / 'T.csv'), at=AT, **COMMON)
        receipt = ingest.ingest_bars(store, sf.prices(tmp_path / 'P.csv'), file=ingest.describe_file(tmp_path / 'P.csv'), at=AT, **COMMON)
        reasons = receipt['rejections_by_reason']
        assert reasons['UNKNOWN_SECURITY'] == 1 and reasons['AMBIGUOUS_SECURITY'] == 1 and reasons['NOT_AN_EXCHANGE_SESSION'] == 1 and reasons['CURRENCY_NOT_USD'] == 1
        assert reasons['HIGH_BELOW_OPEN_OR_CLOSE'] == 1
        assert store.security_ids() == ['100009'] and len(store.bars('100009')['sessions']) == len(rows) - 4


def test_a_file_without_the_documented_columns_is_refused_whole(tmp_path):
    with open(tmp_path / 'P.csv', 'w', newline='') as handle:
        csv.writer(handle).writerows([['ticker', 'date', 'open', 'high', 'low', 'close', 'volume'], ['III', '2024-03-04', '1', '1', '1', '1', '1']])
    with pytest.raises(sf.UnexpectedFileLayout, match='closeunadj'):
        list(sf.prices(tmp_path / 'P.csv'))


# ------------------------------------------------------------------------------------------- immutability and versions
def test_every_table_is_append_only(stored):
    folder, _, _ = stored
    db = sqlite3.connect(folder / 'firm_lab_history.db')
    try:
        triggers = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        tried = 0
        for table in JSON_TABLES + (BAR_TABLE, 'firm_meta'):
            assert {f'{table}_update', f'{table}_delete'} <= triggers, table
            if not db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]:
                continue                                                # a trigger fires per row; an empty table has nothing to refuse
            tried += 1
            for statement in (f'DELETE FROM {table}', f"UPDATE {table} SET created_at='x'" if table != 'firm_meta' else "UPDATE firm_meta SET value='x'"):
                with pytest.raises(sqlite3.DatabaseError, match='APPEND_ONLY'):
                    db.execute(statement)
        assert tried >= 7
        assert dict(db.execute('SELECT key, value FROM firm_meta'))['database_role'] == DATABASE_ROLE
    finally:
        db.close()


def test_a_changed_source_row_is_a_new_version_and_the_old_one_stays(tmp_path):
    fx.write_tickers(tmp_path / 'T.csv')
    with HistoryStore(tmp_path / 'h.db', create=True) as store:
        ingest.ingest_securities(store, sf.securities(tmp_path / 'T.csv'), file=ingest.describe_file(tmp_path / 'T.csv'), at=AT, **COMMON)

        def load(name, rows, at):
            fx.write_prices(tmp_path / name, rows)
            return ingest.ingest_bars(store, sf.prices(tmp_path / name), file=ingest.describe_file(tmp_path / name), at=at, **COMMON)

        base = list(fx.price_rows(['III'], through='2019-03-29'))
        load('a.csv', base, '2026-10-03T12:00:00+00:00')
        longer = load('b.csv', list(fx.price_rows(['III'], through='2019-06-28')), '2026-10-03T12:10:00+00:00')
        assert longer['blocks_by_change'] == {'EXTENDED': 1} and longer['blocks_duplicate'] == 1       # 2018 is unchanged; 2019 gained sessions
        split = load('c.csv', list(fx.price_rows(['III'], through='2019-06-28', rescale=('III', 4.0))), '2026-10-03T12:20:00+00:00')
        assert split['blocks_by_change'] == {'SCALE_ONLY': 2}                                          # a later split rescales every past price by one factor
        revised = [list(r) for r in fx.price_rows(['III'], through='2019-06-28', rescale=('III', 4.0))]
        revised[20][5] = f'{float(revised[20][5]) * 0.97:.6f}'
        revised[20][4] = f'{float(revised[20][4]) * 0.9:.6f}'
        change = load('d.csv', revised, '2026-10-03T12:30:00+00:00')
        assert change['blocks_by_change'] == {'VALUE_CHANGE': 1}                                       # the vendor changed a past print: recorded as that
        versions = store.db.execute(f"SELECT year, version, change FROM {BAR_TABLE} WHERE security_id='100009' ORDER BY year, version").fetchall()
        assert [(y, v) for y, v, _ in versions] == [(2018, 1), (2018, 2), (2018, 3), (2019, 1), (2019, 2), (2019, 3)]
        early = store.bars('100009', through_capture_time='2026-10-03T12:05:00+00:00')
        assert early['sessions'][-1] == '2019-03-29' and early['close'][0] == base[0][5]               # the first capture can still be read exactly
        assert store.bars('100009')['close'][20] == revised[20][5]
        seen = store.first_seen('100009')
        assert seen['2019-03-29'] == '2026-10-03T12:00:00+00:00' and seen['2019-06-28'] == '2026-10-03T12:10:00+00:00'


def test_change_classification():
    old = {'sessions': ['2024-03-04', '2024-03-05'], 'open': ['10', '11'], 'high': ['12', '12'], 'low': ['9', '10'], 'close': ['11', '11.5'], 'volume': ['100', '200'],
           'close_unadjusted': ['11', '11.5'], 'close_total_return': ['11', '11.5'], 'provider_updated': ['', '']}
    halved = {**old, 'open': ['5', '5.5'], 'high': ['6', '6'], 'low': ['4.5', '5'], 'close': ['5.5', '5.75'], 'volume': ['200', '400']}
    assert classify_change(old, halved)['change'] == 'SCALE_ONLY' and classify_change(old, halved)['scale_factor'] == 0.5
    assert classify_change(old, {**halved, 'close_unadjusted': ['5.5', '5.75']})['change'] == 'VALUE_CHANGE'      # the printed price itself moved
    assert classify_change(old, {k: v[:1] for k, v in old.items()})['change'] == 'VALUE_CHANGE'                   # a session disappeared
    assert classify_change(old, {k: v + [v[-1]] if k != 'sessions' else v + ['2024-03-06'] for k, v in old.items()})['change'] == 'EXTENDED'


# --------------------------------------------------------------------------------------------------------- isolation
def test_the_database_is_refused_beside_the_registered_one_inside_a_repository_or_with_execution_tables(tmp_path):
    official = tmp_path / 'runtime' / 'data' / 'agent.db'
    official.parent.mkdir(parents=True)
    sqlite3.connect(official).close()
    with pytest.raises(ValueError, match='OFFICIAL_DATABASE_FORBIDDEN'):
        HistoryStore(official, official_db=official, create=True)
    with pytest.raises(ValueError, match='OFFICIAL_DATABASE_FORBIDDEN'):
        HistoryStore(official.parent / 'history.db', official_db=official, create=True)
    repo = tmp_path / 'repo'
    (repo / '.git').mkdir(parents=True)
    with pytest.raises(ValueError, match='HISTORY_DATABASE_INSIDE_A_REPOSITORY'):
        HistoryStore(repo / 'private' / 'history.db', create=True)
    with pytest.raises(ValueError, match='HISTORY_DATABASE_REQUIRED'):
        HistoryStore(tmp_path / 'absent.db')
    other = tmp_path / 'other.db'
    db = sqlite3.connect(other)
    db.execute('CREATE TABLE orders (id INTEGER)')
    db.commit()
    db.close()
    with pytest.raises(ValueError, match='EXECUTION_TABLE_FORBIDDEN'):
        HistoryStore(other)
    plain = tmp_path / 'plain.db'
    db = sqlite3.connect(plain)
    db.execute('CREATE TABLE notes (id INTEGER)')
    db.commit()
    db.close()
    with pytest.raises(ValueError, match='NOT_A_HISTORY_DATABASE'):
        HistoryStore(plain)


def test_no_table_can_hold_a_trade(stored):
    folder, _, _ = stored
    db = sqlite3.connect(folder / 'firm_lab_history.db')
    names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    db.close()
    assert not [n for n in names for w in ('order', 'fill', 'position', 'account', 'cash', 'portfolio', 'broker') if w in n]


# ------------------------------------------------------------------------------- symbol changes and corporate actions
def test_a_renamed_company_is_one_series_keyed_by_its_permanent_identifier(stored):
    folder, _, _ = stored
    with HistoryStore(folder / 'firm_lab_history.db', read_only=True) as store:
        securities = ingest.current_securities(store)
        assert securities['100002']['symbol'] == 'BBB' and securities['100002']['cik'] == '100002'
        sessions = store.bars('100002')['sessions']
        assert sessions[0] == fx.FIRST and '2020-02-28' in sessions and '2020-03-02' in sessions       # no break in the series at the rename
        changes = [p for _, p, _ in store.rows('history_actions') if p['security_id'] == '100002']
        assert [(c['type'], c['provider_code'], c['contra_symbol'], c['announcement_timestamp']) for c in changes] == [('symbol_change', 'tickerchangeto', 'OLDB', 'UNAVAILABLE')]


def test_splits_are_confirmed_and_inconsistencies_are_named_without_changing_a_value(stored):
    folder, _, _ = stored
    with HistoryStore(folder / 'firm_lab_history.db', read_only=True) as store:
        actions = {}
        for _, p, _ in store.rows('history_actions'):
            actions.setdefault(p['security_id'], []).append(p)
        found = {sid: adjust.breaks(panel.load(store, sid), actions.get(sid, [])) for sid in ('100001', '100005', '100006', '100007', '100009')}
    assert found['100001'] == {'breaks': [], 'splits_confirmed': 1, 'split_convention': {'new_per_old': 1, 'old_per_new': 0}}
    assert [(b['session'], b['reason']) for b in found['100005']['breaks']] == [('2020-08-03', 'SPIN_OFF')]
    assert [(b['session'], b['reason']) for b in found['100006']['breaks']] == [('2020-05-11', 'LARGE_DISTRIBUTION')]       # the small 2021 dividend is not a break
    assert [(b['session'], b['reason']) for b in found['100007']['breaks']] == [('2020-07-01', 'SPLIT_FACTOR_WITHOUT_ACTION')]
    assert found['100009']['breaks'] == []


def test_a_recorded_split_with_no_step_in_the_factor_is_a_break_and_either_split_convention_is_read(stored):
    folder, _, _ = stored
    with HistoryStore(folder / 'firm_lab_history.db', read_only=True) as store:
        plain, split = panel.load(store, '100009'), panel.load(store, '100001')
    phantom = [{'type': 'split', 'effective_date': '2021-05-03', 'value': '2.0'}]
    assert [(b['session'], b['reason']) for b in adjust.breaks(plain, phantom)['breaks']] == [('2021-05-03', 'ACTION_WITHOUT_SPLIT_FACTOR')]
    inverse = adjust.breaks(split, [{'type': 'split', 'effective_date': '2020-06-15', 'value': '0.5'}])
    assert inverse['breaks'] == [] and inverse['split_convention'] == {'new_per_old': 0, 'old_per_new': 1}
    wrong = adjust.breaks(split, [{'type': 'split', 'effective_date': '2020-06-15', 'value': '3.0'}])
    assert [b['reason'] for b in wrong['breaks']] == ['SPLIT_FACTOR_WITHOUT_ACTION'] and wrong['breaks'][0]['recorded_split_values'] == ['3.0']
    weekend = adjust.breaks(split, [{'type': 'split', 'effective_date': '2020-06-13', 'value': '2.0'}])       # dated on a Saturday: the next session carries it
    assert weekend['breaks'] == [] and weekend['splits_confirmed'] == 1


def test_rounding_of_printed_prices_is_not_mistaken_for_a_split(stored):
    """A vendor prints adjusted prices to a few decimals. For a low adjusted price that rounding moves the factor by
    more than half a percent; the tolerance grows with the rounding, so it is not called a break."""
    sessions = list(calendar.sessions('2024-01-02', '2024-03-28'))
    rng = np.random.default_rng(3)
    true = 0.31 * np.exp(np.cumsum(rng.normal(0, 0.01, len(sessions))))
    columns = {'sessions': sessions, 'close': [f'{v:.2f}' for v in true], 'close_unadjusted': [f'{v * 40:.2f}' for v in true]}
    for name in ('open', 'high', 'low', 'close_total_return'):
        columns[name] = columns['close']
    columns['volume'] = ['1000'] * len(sessions)
    assert adjust.breaks(panel.from_columns(columns), [])['breaks'] == []
    columns['close_unadjusted'] = [f'{v * (40 if s < "2024-02-15" else 20):.2f}' for v, s in zip(true, sessions)]       # a real two-for-one
    assert [b['session'] for b in adjust.breaks(panel.from_columns(columns), [])['breaks']] == ['2024-02-15']


def test_the_total_return_factor_is_only_audited(stored):
    folder, _, _ = stored
    with HistoryStore(folder / 'firm_lab_history.db', read_only=True) as store:
        actions = [p for _, p, _ in store.rows('history_actions') if p['security_id'] == '100006']
        audit = adjust.total_return_audit(panel.load(store, '100006'), actions)
    assert audit == {'factor_steps': 1, 'steps_on_a_recorded_distribution': 1, 'steps_without_a_record': 0, 'recorded_distributions_without_a_step': 1}
