"""Firm Lab data path: session dates, the point-in-time feature store, the baseline counterfactual,
capabilities, benchmarks and the research-only ingestion from Control A's recorded closes."""
import hashlib
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from firm_lab import DEVELOPMENT_ONLY, baseline, benchmarks, capabilities, cli, features, ingest, providers, sessions, view
from firm_lab.errors import CapabilityUnavailable, FirmLabError
from firm_lab.sessions import SessionDateError
from firm_lab.store import FORBIDDEN_TABLE_WORDS, FirmLabStore

D = Decimal
KNOWN = '2026-10-01T14:00:00+00:00'            # 10:00 New York on Thursday 1 October 2026


def _lab(tmp_path, official_db=None):
    return FirmLabStore(tmp_path / 'diag' / 'firm_lab' / 'firm_lab.db', official_db)


def _sessions(n, last='2026-09-30'):
    """The n most recent weekdays ending at ``last`` (holidays do not matter for these tests)."""
    out, day = [], date.fromisoformat(last)
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day -= timedelta(days=1)
    return out[::-1]


def _bars(prices, last='2026-09-30'):
    return [{'begins_at': f'{d}T00:00:00Z', 'close_price': str(p), 'interpolated': False} for d, p in zip(_sessions(len(prices), last), prices)]


def _labels(prices, last='2026-09-30'):
    """The same closes the way Control A records them: under the New York date of the bar start (session - 1 day)."""
    return {(date.fromisoformat(d) - timedelta(days=1)).isoformat(): str(p) for d, p in zip(_sessions(len(prices), last), prices)}


def _rows(lab, where='1=1'):
    with lab.connect() as db:
        db.row_factory = sqlite3.Row
        return [dict(r) for r in db.execute(f'SELECT * FROM feature_observations WHERE {where} ORDER BY id')]


# ---------------------------------------------------------------- session dates (section K)
@pytest.mark.parametrize('stamp, session', [
    ('2026-09-30T00:00:00Z', '2026-09-30'),          # summer time: 20:00 on the 29th in New York
    ('2026-01-15T00:00:00Z', '2026-01-15'),          # winter time: 19:00 on the 14th in New York
    ('2026-03-09T00:00:00+00:00', '2026-03-09'),     # first session after the clocks change
    ('2026-11-02T00:00:00Z', '2026-11-02'),
    ('2026-09-29T20:00:00-04:00', '2026-09-30'),     # the same instant written in New York time
])
def test_provider_daily_bar_session_date_is_the_utc_date_not_the_new_york_date(stamp, session):
    assert sessions.session_date_from_provider_daily_bar(stamp) == session
    new_york_date = datetime.fromisoformat(stamp.replace('Z', '+00:00')).astimezone(sessions.ET).date().isoformat()
    assert new_york_date != session                  # the conversion Control A uses gives the evening before


@pytest.mark.parametrize('stamp', ['2026-09-30T13:30:00Z', '2026-09-30', '2026-09-27T00:00:00Z', 'yesterday', '2026-09-30T00:00:00'])
def test_unexpected_provider_timestamp_fails_closed(stamp):
    with pytest.raises(SessionDateError):
        sessions.session_date_from_provider_daily_bar(stamp)


def test_official_label_is_one_day_before_the_session():
    assert sessions.session_date_from_official_label('2026-09-29') == '2026-09-30'
    assert sessions.session_date_from_official_label('2026-09-27') == '2026-09-28'      # a Sunday label is a Monday session
    assert sessions.session_date_from_official_label('2026-01-01') == '2026-01-02'
    for bad in ('2026-09-25', '2026-09-26', 'nope'):                                    # would land on a weekend: not our convention
        with pytest.raises(SessionDateError):
            sessions.session_date_from_official_label(bad)


def test_a_session_is_complete_only_after_the_new_york_close():
    assert not sessions.is_completed('2026-10-01', '2026-10-01T19:59:59+00:00')
    assert sessions.is_completed('2026-10-01', '2026-10-01T20:00:00+00:00')
    assert sessions.is_completed('2026-01-15', '2026-01-15T21:00:00+00:00') and not sessions.is_completed('2026-01-15', '2026-01-15T20:59:00+00:00')
    with pytest.raises(SessionDateError):
        sessions.utc_iso('2026-10-01T10:00:00')


# ---------------------------------------------------------------- features (required tests 13-18)
def test_raw_provider_timestamp_is_preserved_and_session_date_is_correct(tmp_path):                 # 13, 14
    lab = _lab(tmp_path)
    out = features.ingest_provider_daily_bars(lab, 'VTI', [{'begins_at': '2026-09-30T00:00:00Z', 'close_price': '331.25'}], known_at=KNOWN)
    assert out['INSERTED'] == 1
    row = _rows(lab)[0]
    assert row['source_timestamp'] == '2026-09-30T00:00:00Z'                  # exactly as the provider sent it
    assert row['exchange_session_date'] == '2026-09-30'                        # not 2026-09-29
    assert row['known_at'] == KNOWN and row['feature_name'] == 'close' and row['value'] == '331.25'
    assert row['ingested_at'] and row['feature_version'] == features.FEATURE_VERSION and json.loads(row['metadata_json'])


def test_todays_unfinished_bar_and_bad_rows_are_not_stored_as_closes(tmp_path):
    lab = _lab(tmp_path)
    bars = [{'begins_at': '2026-09-30T00:00:00Z', 'close_price': '100'},
            {'begins_at': '2026-10-01T00:00:00Z', 'close_price': '101'},                       # session still open at KNOWN
            {'begins_at': '2026-09-29T00:00:00Z', 'close_price': '99', 'interpolated': True},
            {'begins_at': '2026-09-28T00:00:00Z', 'close_price': '0'},
            {'begins_at': '2026-09-25T00:00:00Z', 'close_price': 'NaN'}]
    out = features.ingest_provider_daily_bars(lab, 'SPY', bars, known_at=KNOWN)
    assert out['INSERTED'] == 1 and out['skipped'] == {'interpolated': 1, 'not_completed': 1, 'bad_price': 2}
    assert [r['exchange_session_date'] for r in _rows(lab)] == ['2026-09-30']
    with pytest.raises(SessionDateError):                                                      # one strange bar stops the batch
        features.ingest_provider_daily_bars(lab, 'SPY', [{'begins_at': '2026-09-30T04:00:00Z', 'close_price': '100'}], known_at=KNOWN)


def test_momentum_126d_is_last_close_over_the_close_126_sessions_earlier(tmp_path):                 # 15
    lab = _lab(tmp_path)
    prices = [D(100) + D(i) for i in range(260)]                                # 100 .. 359
    features.ingest_provider_daily_bars(lab, 'QQQ', _bars(prices), known_at=KNOWN)
    b = features.baseline(lab, 'QQQ', known_at=KNOWN)
    assert b['completed_session_count'] == 260 and b['exchange_session_date'] == '2026-09-30' and b['close'] == '359'
    assert D(b['momentum_126d']) == D(359) / D(233) - 1                         # 233 is the close 126 sessions before the last
    assert b['missing'] == []


def test_ma200_is_the_mean_of_the_last_200_completed_closes(tmp_path):                              # 16
    lab = _lab(tmp_path)
    prices = [D(50)] * 60 + [D(100) + D(i) for i in range(200)]                 # the first 60 must not enter the average
    features.ingest_provider_daily_bars(lab, 'XLK', _bars(prices), known_at=KNOWN)
    b = features.baseline(lab, 'XLK', known_at=KNOWN)
    assert D(b['ma200']) == sum(prices[-200:], D(0)) / D(200) == D('199.5')
    assert b['above_ma200'] is True
    lab2 = _lab(tmp_path / 'b')
    features.ingest_provider_daily_bars(lab2, 'XLK', _bars(prices[:-1] + [D(150)]), known_at=KNOWN)
    assert features.baseline(lab2, 'XLK', known_at=KNOWN)['above_ma200'] is False


def test_insufficient_history_gives_no_value_and_says_why(tmp_path):                                # 17
    lab = _lab(tmp_path)
    features.ingest_provider_daily_bars(lab, 'NEW', _bars([D(10) + D(i) for i in range(126)]), known_at=KNOWN)
    b = features.store_baseline(lab, 'NEW', known_at=KNOWN)
    assert b['completed_session_count'] == 126 and b['ma200'] is None and b['above_ma200'] is None and b['momentum_126d'] is None
    assert b['missing'] == ['ma200 needs 200 completed closes; has 126', 'momentum_126d needs 127 completed closes; has 126']
    stored = {r['feature_name']: r for r in _rows(lab, "feature_name != 'close'")}
    assert stored['ma200']['value'] is None and stored['momentum_126d']['value'] is None and stored['above_ma200']['value'] is None
    assert stored['completed_session_count']['value'] == '126' and 'missing' in json.loads(stored['ma200']['metadata_json'])
    empty = features.store_baseline(lab, 'NOTHING', known_at=KNOWN)
    assert empty['completed_session_count'] == 0 and empty['close'] is None and not _rows(lab, "instrument='NOTHING'")
    record = baseline.evaluate(lab, ['NEW'], known_at=KNOWN, write=False)
    assert record['selected_instrument'] is None and record['candidates'][0]['eligibility_reason'] == 'needs 253 completed closes; has 126'


def test_history_is_appended_never_overwritten(tmp_path):                                           # 18
    lab = _lab(tmp_path)
    bar = lambda p: [{'begins_at': '2026-09-30T00:00:00Z', 'close_price': p}]
    assert features.ingest_provider_daily_bars(lab, 'VTI', bar('331.25'), known_at=KNOWN)['INSERTED'] == 1
    assert features.ingest_provider_daily_bars(lab, 'VTI', bar('331.25'), known_at='2026-10-02T14:00:00+00:00')['UNCHANGED'] == 1
    later = '2026-10-03T14:00:00+00:00'
    assert features.ingest_provider_daily_bars(lab, 'VTI', bar('331.40'), known_at=later)['REVISED'] == 1
    rows = _rows(lab)
    assert [(r['value'], r['revision'], r['known_at']) for r in rows] == [('331.25', 0, KNOWN), ('331.40', 1, later)]
    # point in time: a question asked as of the first day still gets the first value
    assert lab.feature_history('VTI', 'close', features.FEATURE_VERSION, known_by=KNOWN)[0]['value'] == '331.25'
    assert lab.feature_history('VTI', 'close', features.FEATURE_VERSION, known_by=later)[0]['value'] == '331.40'
    assert lab.feature_history('VTI', 'close', features.FEATURE_VERSION, known_by='2026-09-01T00:00:00+00:00') == []
    source = Path(features.__file__).read_text() + Path(features.__file__).with_name('store.py').read_text()
    assert 'UPDATE feature_observations' not in source and 'DELETE FROM feature_observations' not in source


def test_a_close_learned_later_is_invisible_to_an_earlier_evaluation(tmp_path):
    lab = _lab(tmp_path)
    prices = [D(100) + D(i) for i in range(260)]
    features.ingest_provider_daily_bars(lab, 'QQQ', _bars(prices[:-1], last='2026-09-29'), known_at='2026-09-30T14:00:00+00:00')
    features.ingest_provider_daily_bars(lab, 'QQQ', _bars(prices), known_at=KNOWN)
    assert features.baseline(lab, 'QQQ', known_at='2026-09-30T14:00:00+00:00')['exchange_session_date'] == '2026-09-29'
    assert features.baseline(lab, 'QQQ', known_at=KNOWN)['exchange_session_date'] == '2026-09-30'


# ---------------------------------------------------------------- counterfactual (required tests 19-23)
def _universe(lab):
    up = [D(100) + D(i) for i in range(260)]                    # +54% over 126 sessions
    faster = [D(100) * (D('1.004') ** i) for i in range(260)]   # stronger
    down = [D(400) - D(i) for i in range(260)]
    features.ingest_provider_daily_bars(lab, 'AAA', _bars(up), known_at=KNOWN)
    features.ingest_provider_daily_bars(lab, 'BBB', _bars(faster), known_at=KNOWN)
    features.ingest_provider_daily_bars(lab, 'CCC', _bars(down), known_at=KNOWN)
    features.ingest_provider_daily_bars(lab, 'DDD', _bars(up[:150]), known_at=KNOWN)
    return ['AAA', 'BBB', 'CCC', 'DDD']


def test_baseline_counterfactual_is_deterministic_and_complete(tmp_path):                           # 19
    lab = _lab(tmp_path)
    names = _universe(lab)
    one = baseline.evaluate(lab, names, known_at=KNOWN)
    two = baseline.evaluate(lab, list(reversed(names)), known_at=KNOWN)
    assert one['record_hash'] == two['record_hash'] and one['inserted'] and not two['inserted']
    assert lab.counts()['counterfactual_decisions'] == 1
    assert one['selected_instrument'] == 'BBB' and one['exchange_session_date'] == '2026-09-30' and one['evaluated_at'] == KNOWN
    assert one['universe'] == ['AAA', 'BBB', 'CCC', 'DDD'] and one['provenance']['data']
    by = {c['instrument']: c for c in one['candidates']}
    assert (by['BBB']['rank'], by['AAA']['rank']) == (1, 2) and 'rank' not in by['CCC']
    assert by['CCC']['eligibility_reason'] == 'price is not above its 200-session moving average'
    assert by['DDD']['eligibility_reason'] == 'needs 253 completed closes; has 150'
    for c in one['candidates']:
        assert {'momentum_126d', 'ma200', 'eligible', 'eligibility_reason', 'close', 'completed_session_count'} <= set(c)


def test_counterfactual_is_development_only_and_creates_nothing_tradeable(tmp_path):                # 20-23
    lab = _lab(tmp_path)
    record = baseline.evaluate(lab, _universe(lab), known_at=KNOWN)
    assert record['label'] == DEVELOPMENT_ONLY == 'DEVELOPMENT_ONLY' and record['title'] == 'DEVELOPMENT COUNTERFACTUAL — NOT A PAPER TRADE'
    saved = lab.latest_counterfactual(baseline.STRATEGY_ID)
    assert saved['label'] == 'DEVELOPMENT_ONLY' and saved['selected_instrument'] == 'BBB'
    with lab.connect() as db:
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        columns = [r[1] for r in db.execute('PRAGMA table_info(counterfactual_decisions)')]
        with pytest.raises(sqlite3.IntegrityError):                                    # the label cannot be anything else
            db.execute("INSERT INTO counterfactual_decisions (timestamp, exchange_session_date, strategy_id, candidates_json, features_used_json, "
                       "provenance_json, label, record_hash) VALUES ('t','d','s','[]','{}','{}','PAPER_TRADE','x')")
    assert not [t for t in tables for w in FORBIDDEN_TABLE_WORDS if w in t]            # no order, fill, position, cash or portfolio table
    assert not [c for c in columns for w in ('quantity', 'price', 'fill', 'cash', 'account', 'order', 'shares') if w in c]
    counts = lab.counts()
    assert counts['events'] == 0 and counts['experiment_registry'] == 0 and lab.active_experiments() == []
    assert lab.mode() == 'BUILD_OBSERVE'


# ---------------------------------------------------------------- capabilities (required tests 24-27)
def test_blocked_capabilities_are_unavailable(tmp_path):                                            # 24-26
    lab = _lab(tmp_path)
    capabilities.seed(lab)
    status = {c['capability']: c['status'] for c in lab.capabilities()}
    assert status['daily_closes'] == 'AVAILABLE' and status['daily_baseline_features'] == 'AVAILABLE'
    for name in ('fundamentals', 'analyst_revisions', 'earnings_transcripts', 'intraday_bars', 'vwap', 'opening_range', 'time_of_day_rvol',
                 'trade_flow', 'order_book'):
        assert status[name] == 'UNAVAILABLE', name
    assert status['options_chain'] == 'BUILD_ONLY'
    for name in ('options_strategy', 'ml_ranker', 'sector_engine', 'portfolio_optimizer', 'news_catalysts', 'sec_filings'):
        assert status[name] == 'NOT_STARTED', name
    assert set(status.values()) <= set(capabilities.STATUSES) == {'AVAILABLE', 'UNAVAILABLE', 'NOT_STARTED', 'BUILD_ONLY'}
    assert lab.capability('something_nobody_registered') == 'UNAVAILABLE'
    with pytest.raises(FirmLabError):
        lab.set_capability('fundamentals', 'COMING_SOON')
    capabilities.require(lab, 'daily_closes')
    for name in ('fundamentals', 'analyst_revisions', 'intraday_bars', 'options_chain', 'ml_ranker'):
        with pytest.raises(CapabilityUnavailable):
            capabilities.require(lab, name)


def test_a_deliberate_capability_edit_survives_reseeding(tmp_path):
    lab = _lab(tmp_path)
    capabilities.seed(lab)
    lab.set_capability('news_catalysts', 'BUILD_ONLY', 'chosen later', 'edited on purpose')
    capabilities.seed(lab)
    assert lab.capability('news_catalysts') == 'BUILD_ONLY' and len(lab.capabilities()) == len(capabilities.INITIAL)


def test_missing_provider_never_returns_a_made_up_value(tmp_path):                                  # 27
    lab = _lab(tmp_path)
    calls = [lambda: providers.FundamentalsProvider().snapshot('AAPL', KNOWN),
             lambda: providers.AnalystRevisionsProvider().revisions('AAPL', KNOWN),
             lambda: providers.IntradayMarketDataProvider().historical_bars('AAPL', KNOWN, KNOWN),
             lambda: providers.IntradayMarketDataProvider().live_bars('AAPL'),
             lambda: providers.IntradayMarketDataProvider().quotes('AAPL'),
             lambda: providers.IntradayMarketDataProvider().trades('AAPL'),
             lambda: providers.IntradayMarketDataProvider().option_quotes('contract')]
    for call in calls:
        with pytest.raises(CapabilityUnavailable):
            call()
    assert lab.counts()['feature_observations'] == 0 and lab.counts()['option_chain_observations'] == 0
    with lab.connect() as db:
        option_columns = [r[1] for r in db.execute('PRAGMA table_info(option_chain_observations)')]
    greeks = [c for c in option_columns if any(g in c for g in ('delta', 'gamma', 'theta', 'vega', 'implied_volatility'))]
    assert greeks and all(c.startswith('provider_') for c in greeks)                   # a Greek is never stored without its origin


# ---------------------------------------------------------------- benchmarks (section O)
def test_vti_ruler_is_defined_and_the_70_30_ruler_is_defined_but_waits_for_treasury_data(tmp_path):
    lab = _lab(tmp_path)
    benchmarks.seed(lab)
    benchmarks.seed(lab)
    defs = {d['benchmark_id']: d for d in benchmarks.definitions(lab)}
    assert set(defs) == {'VTI_100', 'FIXED_70_30'}
    assert defs['VTI_100']['status'] == 'DEFINED' and json.loads(defs['VTI_100']['definition_json'])['weights'] == {'VTI': '1.00'}
    pending = defs['FIXED_70_30']
    assert pending['status'] == 'DEFINED' and pending['implementation_status'] == 'DATA_SOURCE_PENDING'
    assert pending['name'] == '70% VTI + 30% 3-month U.S. Treasury-bill total return'
    definition = json.loads(pending['definition_json'])
    assert definition['weights'] == {'VTI': '0.70', 'US_TREASURY_BILL_3M_TOTAL_RETURN': '0.30'} and definition['allocation'] == 'fixed'
    assert definition['treasury_bill_series'] is None and definition['rebalancing'] == 'NOT_SPECIFIED_BY_OPERATOR'   # nothing chosen silently
    assert len(definition['rules']) == 4 and defs['VTI_100']['implementation_status'] == 'PRICE_RETURN_ONLY'
    features.ingest_provider_daily_bars(lab, 'VTI', _bars([D(300) + D(i) for i in range(5)]), known_at=KNOWN)
    assert benchmarks.record_vti(lab, known_at=KNOWN) == 5 and benchmarks.record_vti(lab, known_at=KNOWN) == 0
    defs = {d['benchmark_id']: d for d in benchmarks.definitions(lab)}
    assert defs['VTI_100']['observations'] == 5 and defs['VTI_100']['latest'] == ('2026-09-30', '304')
    assert defs['FIXED_70_30']['observations'] == 0                                    # nothing is computed for an undefined ruler
    text = ''.join(p.read_text() for p in Path(benchmarks.__file__).parent.glob('*.py'))
    assert 'alpha' not in text.replace('No alpha is computed', '').lower()            # no "alpha" is reported in BUILD_OBSERVE


# ---------------------------------------------------------------- ingestion from Control A's records (read-only)
def _official_with_capsule(tmp_path, *, data_mode='live_readonly', observed='2026-10-01T14:02:00+00:00'):
    path = tmp_path / 'runtime' / 'data' / 'agent.db'
    path.parent.mkdir(parents=True, exist_ok=True)
    up = [D(100) + D(i) for i in range(260)]
    faster = [(D(100) * (D('1.004') ** i)).quantize(D('0.0001')) for i in range(260)]
    down = [D(400) - D(i) for i in range(260)]
    closes = {'AAA': _labels(up), 'BBB': _labels(faster), 'CCC': _labels(down), 'VTI': _labels(up)}
    mom = lambda p: str(p[-1] / p[-127] - 1)
    payload = {'capsule_version': 1, 'cycle_id': 'cycle-1', 'data_mode': data_mode, 'observed_at': observed,
               'inputs': {'session_closes': closes, 'paper_accounts': {'A': {'settled_cash': '25000'}}},
               'strategy_assessment': {'strategies': {'momentum_rotation': {
                   'evaluated': ['AAA', 'BBB', 'CCC', 'VTI'],
                   'ranked': [{'instrument': 'BBB', 'momentum_126d': mom(faster)}, {'instrument': 'AAA', 'momentum_126d': mom(up)},
                              {'instrument': 'VTI', 'momentum_126d': mom(up)}]}}}}
    db = sqlite3.connect(path)
    db.executescript('CREATE TABLE IF NOT EXISTS decision_capsules (hash TEXT PRIMARY KEY, cycle_id TEXT, created_at TEXT, payload TEXT);'
                     'CREATE TABLE IF NOT EXISTS fills (id INTEGER PRIMARY KEY, payload_json TEXT);')
    db.execute('INSERT INTO decision_capsules VALUES (?,?,?,?)', (hashlib.sha256(observed.encode() + data_mode.encode()).hexdigest(), 'cycle-1',
                                                                  observed, json.dumps(payload)))
    db.commit(); db.close()
    return path


def test_ingest_reproduces_control_a_from_its_own_records_without_touching_them(tmp_path):
    off = _official_with_capsule(tmp_path)
    before = hashlib.sha256(off.read_bytes()).hexdigest()
    lab = _lab(tmp_path, off)
    report = ingest.ingest_official(lab, off)
    assert report['capsules_seen'] == 1 and report['capsules_ingested'] == 1
    run = report['runs'][0]
    assert run['status'] == 'OK' and run['selected'] == 'BBB' and run['exchange_session_date'] == '2026-09-30'
    check = run['plumbing_check']
    assert check['matches_control_a'] and check['firm_lab_ranking'] == check['control_a_recorded_ranking'] == ['BBB', 'AAA', 'VTI']
    assert D(check['largest_momentum_difference']) == 0
    close = _rows(lab, "instrument='AAA' AND feature_name='close'")[-1]
    meta = json.loads(close['metadata_json'])
    assert close['exchange_session_date'] == '2026-09-30' and meta['official_label'] == '2026-09-29'      # label + 1 day
    assert close['source'] == 'control_a_decision_capsule' and 'reconstructed' in meta['source_timestamp_basis']
    saved = lab.latest_counterfactual(baseline.STRATEGY_ID)
    assert saved['provenance']['capsule_hash'] == run['capsule_hash'] and saved['label'] == 'DEVELOPMENT_ONLY'
    with lab.connect() as db:
        assert json.loads(db.execute('SELECT symbols_json FROM universe_snapshots').fetchone()[0]) == ['AAA', 'BBB', 'CCC', 'VTI']
        assert db.execute('SELECT mode FROM universe_snapshots').fetchone()[0] == 'BUILD_OBSERVE'
    again = ingest.ingest_official(lab, off)                                           # the same capsule is never ingested twice
    assert again['capsules_ingested'] == 0 and again['runs'] == [] and lab.counts()['counterfactual_decisions'] == 1
    assert hashlib.sha256(off.read_bytes()).hexdigest() == before                      # Control A's file is byte-for-byte unchanged
    assert not [t for t in lab.tables() for w in FORBIDDEN_TABLE_WORDS if w in t]


def test_ingest_skips_rehearsals_and_fails_closed_on_a_strange_label(tmp_path):
    off = _official_with_capsule(tmp_path, data_mode='fixture')
    lab = _lab(tmp_path, off)
    assert ingest.ingest_official(lab, off)['capsules_ingested'] == 0 and lab.counts()['feature_observations'] == 0
    db = sqlite3.connect(off)
    bad = {'data_mode': 'live_readonly', 'observed_at': '2026-10-01T14:02:00+00:00', 'inputs': {'session_closes': {'AAA': {'2026-09-25': '10'}}},
           'strategy_assessment': {'strategies': {'momentum_rotation': {'evaluated': ['AAA'], 'ranked': []}}}}
    db.execute("INSERT INTO decision_capsules VALUES ('bad', 'cycle-2', '2026-10-01T14:03:00+00:00', ?)", (json.dumps(bad),))
    db.commit(); db.close()
    report = ingest.ingest_official(lab, off)
    assert report['runs'][0]['status'] == 'FAILED' and report['runs'][0]['error_type'] == 'SessionDateError'
    assert lab.counts()['feature_observations'] == 0 and lab.counts()['counterfactual_decisions'] == 0


# ---------------------------------------------------------------- read-only view and the research-only CLI
def test_view_reads_without_writing_and_reports_the_fixed_statuses(tmp_path, capsys):
    off = _official_with_capsule(tmp_path)
    path = tmp_path / 'diag' / 'firm_lab' / 'firm_lab.db'
    missing = view.load(path=path)
    assert missing['exists'] is False and missing['mode'] == 'BUILD_OBSERVE' and missing['fills'] == 0 and not path.exists()
    assert cli.main(['ingest', '--official-database', str(off), '--path', str(path)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed['ingest']['capsules_ingested'] == 1 and printed['state']['mode'] == 'BUILD_OBSERVE'
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    state = view.load(path=path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert state['mode'] == 'BUILD_OBSERVE' and state['has_execution_tables'] is False and state['refused_fill_attempts'] == 0
    assert (state['fills'], state['firm_trading_trial'], state['october_research_stop_superseded'], state['official_lane_b'], state['real_execution']) == (
        0, 'NOT REGISTERED', 'NO', 'PAUSED', 'DISABLED')
    assert state['baseline']['selected_instrument'] == 'BBB' and state['baseline']['title'] == 'DEVELOPMENT COUNTERFACTUAL — NOT A PAPER TRADE'
    assert state['latest_session'] == '2026-09-30' and state['experiments'] == [] and state['database'].endswith('firm_lab/firm_lab.db')
    assert {b['benchmark_id']: b['status'] for b in state['benchmarks']} == {'VTI_100': 'DEFINED', 'FIXED_70_30': 'DEFINED'}
    assert {b['benchmark_id']: b['implementation_status'] for b in state['benchmarks']} == {'VTI_100': 'PRICE_RETURN_ONLY', 'FIXED_70_30': 'DATA_SOURCE_PENDING'}
    path.write_bytes(b'not a database')
    broken = view.load(path=path)
    assert broken['error'] and broken['mode'] is None and broken['fills'] == 0         # a broken file is never read as permission
