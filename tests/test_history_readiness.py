"""Checkpoint 8: sufficiency bars, regime description, the readiness report, its page, capability rows and isolation.

What is proven here: the bars in code are the bars written before any data was collected; breadth is measured, never
assumed; with nothing stored every bar is unmet, the strict count is 0 and every family is INSUFFICIENT; the report and
the page hold no price and no instruction; the page shows the permanent warning; and the package can reach no broker,
no network and no trading code, and nothing on the trading side or on a schedule can reach it."""
import ast
import json
import re
import shutil
import sqlite3
from pathlib import Path

import numpy as np
import pytest

import history_fixture as fx
from agents.desk import firm_lab_page, history_readiness
from firm_lab import capabilities, history, history_capability, history_view
from firm_lab.history import calendar, dataset, ingest, readiness, regimes, sharadar_files as sf, splits, sufficiency, universe
from firm_lab.history.store import HistoryStore

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'firm_lab' / 'history'
SPEC = (ROOT / 'docs' / 'firm_lab' / 'CHECKPOINT8_DATA_SUFFICIENCY_SPEC.md').read_text()
AT = '2026-10-03T12:00:00+00:00'
COMMON = {'source': sf.SOURCE, 'adapter': sf.ADAPTER}


@pytest.fixture(autouse=True)
def _machine_clock(monkeypatch):
    fx.set_clock(monkeypatch)                     # the clock a capture is stamped with; later than every time these tests supply
BANNED_IMPORTS = ('agents', 'broker', 'broker_proxy', 'risk', 'config', 'data', 'eval', 'prompts', 'scripts', 'research', 'robin_stocks', 'alpaca', 'urllib', 'socket',
                  'http', 'ssl', 'requests', 'subprocess', 'firm_lab_collectors', 'torch', 'sklearn', 'xgboost', 'lightgbm', 'catboost')
ACTION_WORDS = ('BUY', 'SELL', 'STRONG BUY', 'GO LONG', 'GO SHORT', 'OVERWEIGHT', 'UNDERWEIGHT', 'ENTER NOW', 'TAKE PROFIT', 'PRICE TARGET')


def _research(folder):
    """A small research database of the real shape: mode, a few SEC facts, events, macro rows and closes."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'firm_lab.db'
    db = sqlite3.connect(path)
    db.executescript('''
        CREATE TABLE firm_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
        INSERT INTO firm_meta VALUES ('mode', 'BUILD_OBSERVE', 'x');
        CREATE TABLE fundamental_fact_observations (id INTEGER PRIMARY KEY, instrument TEXT, accession_number TEXT, is_restatement INTEGER, accepted_timestamp TEXT, period_end TEXT);
        CREATE TABLE earnings_event_observations (id INTEGER PRIMARY KEY, instrument TEXT, accepted_timestamp TEXT, release_document_url TEXT, transcript_available INTEGER);
        CREATE TABLE macro_observations (id INTEGER PRIMARY KEY, series TEXT, period TEXT, revision INTEGER, published_at TEXT, known_at TEXT, payload_json TEXT);
        CREATE TABLE feature_observations (id INTEGER PRIMARY KEY, instrument TEXT, feature_name TEXT, value TEXT, known_at TEXT, exchange_session_date TEXT, revision INTEGER);
        CREATE TABLE corporate_action_observations (id INTEGER PRIMARY KEY, instrument TEXT, benchmark_only INTEGER);
        CREATE TABLE data_capabilities (capability TEXT PRIMARY KEY, status TEXT, provider TEXT, detail TEXT, updated_at TEXT);
        INSERT INTO data_capabilities VALUES ('ml_ranker', 'RESEARCH_ONLY', NULL, '', 'x');
        INSERT INTO corporate_action_observations VALUES (1, 'VTI', 1);
        INSERT INTO earnings_event_observations VALUES (1, 'AAA', '2026-07-30T20:30:28+00:00', 'https://www.sec.gov/x', 0);
        INSERT INTO macro_observations VALUES (1, 'fed_target_upper', '2026-06-17', 0, '2026-06-17T18:00:00+00:00', '2026-10-03T20:12:10+00:00', '{"value":"3.75"}');
        INSERT INTO macro_observations VALUES (2, 'fed_target_upper', '2026-09-16', 0, '2026-09-16T18:00:00+00:00', '2026-10-03T20:12:10+00:00', '{"value":"3.5"}');
    ''')
    for k in range(6):
        db.execute('INSERT INTO fundamental_fact_observations (instrument, accession_number, is_restatement, accepted_timestamp, period_end) VALUES (?,?,?,?,?)',
                   ('AAA', f'0000-{k // 3}', 0, '2026-07-31T10:01:02+00:00', '2026-06-30'))
    held = fx.series('AAA')
    for ticker, shift in (('AAA', 1.0), ('III', 1.0), ('VTI', 1.0)):
        data = fx.series('III' if ticker == 'VTI' else ticker)
        for s, v in zip(data['sessions'], data['close']):
            if '2025-03-31' <= s <= '2026-09-30':
                db.execute("INSERT INTO feature_observations (instrument, feature_name, value, known_at, exchange_session_date, revision) VALUES (?, 'close', ?, ?, ?, 0)",
                           (ticker, f'{v * shift:.6f}', '2026-10-01T14:02:11+00:00', s))
    db.commit()
    db.close()
    assert held
    return path


@pytest.fixture(scope='module')
def stored(tmp_path_factory):
    folder = tmp_path_factory.mktemp('readiness')
    files = fx.provider(folder / 'files' if (folder / 'files').mkdir() is None else folder)
    with HistoryStore(folder / 'firm_lab_history.db', create=True) as store:
        ingest.ingest_securities(store, sf.securities(files['tickers']), file=ingest.describe_file(files['tickers']), at=AT, **COMMON)
        ingest.ingest_bars(store, sf.prices(files['prices']), file=ingest.describe_file(files['prices']), at=AT, **COMMON)
        ingest.ingest_actions(store, sf.actions(files['actions']), file=ingest.describe_file(files['actions']), at=AT, **COMMON)
        ingest.ingest_index_events(store, sf.index_events(files['sp500']), file=ingest.describe_file(files['sp500']), at=AT, **COMMON)
        store.put('history_reservations', splits.reservation())
        universe.build(store, fx.FIRST, '2026-10-02', rule={**universe.RULE, 'size': 6}, version=fx.VERSION)
        store.put('history_reports', {'kind': 'strict_count', **dataset.count(store)})
    research = _research(folder / 'firm_lab')
    return folder, research


# ------------------------------------------------------------------------------------------- the specification as code
def test_the_bars_in_code_are_the_bars_written_before_any_data_was_collected():
    assert sufficiency.SPEC_VERSION in SPEC and 'before any Checkpoint 8 data was collected' in SPEC
    assert f'`REFERENCE_IC = {sufficiency.REFERENCE_IC}`' in SPEC and f'`MDE = {sufficiency.POWER_FACTOR} / sqrt(E)`' in SPEC
    assert sufficiency.required_observations() == 6889 and '= 6,889`' in SPEC
    names = {'linear': 'Linear (ridge / elastic net)', 'xgboost': 'XGBoost', 'lightgbm': 'LightGBM', 'catboost': 'CatBoost', 'mlp': 'MLP', 'tcn': 'TCN',
             'lstm_gru': 'LSTM / GRU', 'transformer': 'Transformer encoder', 'multi_task': 'Multi-task network'}
    for family, (reference, smallest, _, _) in sufficiency.FAMILIES.items():
        assert re.search(rf'\| {re.escape(names[family])} \| {reference:,} \| {smallest:,} \|', SPEC), family
    assert '| H3 Instruments per reconstitution | 1,000 | 500 |' in SPEC and sufficiency.HISTORY['target_members'] == 1000 and sufficiency.HISTORY['minimum_members'] == 500
    assert 'At most 0.03 | At most 0.05' in SPEC and sufficiency.WEAK_IC == 0.05
    assert '2 bear markets, 4 corrections, rising and falling policy rates, 3 separate high-volatility episodes' in SPEC
    assert sufficiency.REGIME_BAR == {'bear_markets': 2, 'corrections': 4, 'high_volatility_episodes': 3, 'rising_rate_periods': 1, 'falling_rate_periods': 1}
    assert 'at least two bear markets and at least 8 calendar years' in SPEC and sufficiency.NETWORK_BAR['calendar_years_in_training'] == 8
    assert 'at least 63 consecutive sessions per sample for at least 95% of samples' in SPEC
    assert 'at least 99.5% of expected (member, session) bars' in SPEC.replace('At least', 'at least') and sufficiency.COVERAGE['bars_complete_target'] == 0.995
    assert 'O7 Print precision (added by amendment 1) | At most 1% of member rows have an adjusted close printed more coarsely than 0.05% of its value | At most 5%' in SPEC
    assert (sufficiency.COVERAGE['coarse_print_target'], sufficiency.COVERAGE['coarse_print_minimum'], sufficiency.COVERAGE['print_precision_bound']) == (0.01, 0.05, 5e-4)
    from firm_lab.history import adjust
    assert adjust.PRECISION_BOUND == sufficiency.COVERAGE['print_precision_bound'] and sufficiency.COVERAGE['coarse_print_minimum'] == 0.05
    assert 'No bar was\nlowered' in SPEC
    history_text = subprocess_free_git_log()
    assert history_text is None or 'data-sufficiency specification, written before any collection' in history_text


def subprocess_free_git_log():
    """The commit subjects, read from the repository files without starting a process. None when they cannot be read."""
    head = ROOT / '.git'
    if head.is_file():                                                # a linked work tree: follow it to its own git directory
        target = head.read_text().split('gitdir:', 1)[-1].strip()
        head = Path(target) if Path(target).is_absolute() else (ROOT / target)
    log = head / 'logs' / 'HEAD'
    return log.read_text() if log.is_file() else None


def test_breadth_is_measured_with_the_sampling_noise_removed_and_never_assumed():
    rng = np.random.default_rng(5)
    independent = rng.normal(size=(120, 40))
    assert sufficiency.breadth(independent)['n_eff'] == pytest.approx(40, rel=0.2)                    # unrelated instruments count as themselves
    raw = 40 / (1 + 39 * float(np.mean(np.corrcoef(independent.T)[~np.eye(40, dtype=bool)] ** 2)))
    assert raw < 31                                                                                   # without the correction a short sample looks related
    common = rng.normal(size=(120, 1))
    together = common + 0.05 * rng.normal(size=(120, 40))
    assert sufficiency.breadth(together)['n_eff'] < 1.2                                               # forty copies of one series count as about one
    half = independent.copy()
    half[:, 20:] = common + 0.05 * rng.normal(size=(120, 20))
    assert 2.5 < sufficiency.breadth(half)['n_eff'] < 6
    short = sufficiency.breadth(rng.normal(size=(10, 40)))
    assert short['n_eff'] is None and 'not assumed' in short['note']
    gaps = independent.copy()
    gaps[:60, :10] = np.nan                                                                           # instruments that joined later
    assert sufficiency.breadth(gaps)['n_eff'] == pytest.approx(sufficiency.breadth(gaps)['instruments_per_window'], rel=0.25)
    assert sufficiency.effective_observations(1000, 20, None) is None and sufficiency.detectable_ic(None) is None and sufficiency.testability(None) == 'NOT_MEASURABLE'


def test_detectable_rank_correlation_and_the_family_verdicts():
    assert sufficiency.detectable_ic(6889) == pytest.approx(0.03, abs=1e-5) and sufficiency.detectable_ic(34) == pytest.approx(0.427, abs=1e-3)
    assert sufficiency.effective_observations(1000, 20, 50) == 2500
    assert [sufficiency.testability(x) for x in (0.02, 0.03, 0.04, 0.05, 0.06)] == ['TESTABLE', 'TESTABLE', 'WEAKLY_TESTABLE', 'WEAKLY_TESTABLE', 'NOT_TESTABLE']
    good = dict(holdout_ic=0.025, development_ic=0.02, regimes_met=True, bear_markets_in_training=3, training_years=20.0, sequence_share=0.99)
    assert sufficiency.family_verdict('xgboost', e_train=55000, **good)['verdict'] == 'SUFFICIENT'
    assert sufficiency.family_verdict('xgboost', e_train=13000, **good)['verdict'] == 'BORDERLINE'       # above the smallest configuration, below the reference
    assert sufficiency.family_verdict('xgboost', e_train=3000, **good)['verdict'] == 'INSUFFICIENT'
    assert sufficiency.family_verdict('xgboost', e_train=55000, **{**good, 'holdout_ic': 0.04})['verdict'] == 'BORDERLINE'
    assert sufficiency.family_verdict('xgboost', e_train=55000, **{**good, 'holdout_ic': 0.08})['verdict'] == 'INSUFFICIENT'
    assert sufficiency.family_verdict('xgboost', e_train=55000, **{**good, 'regimes_met': False})['verdict'] == 'BORDERLINE'
    assert sufficiency.family_verdict('linear', e_train=700, **good)['verdict'] == 'SUFFICIENT'
    assert sufficiency.family_verdict('mlp', e_train=10 ** 6, **{**good, 'holdout_ic': 0.04})['verdict'] == 'INSUFFICIENT'      # a network needs a testable holdout
    assert sufficiency.family_verdict('mlp', e_train=10 ** 6, **{**good, 'bear_markets_in_training': 1})['verdict'] == 'INSUFFICIENT'
    assert sufficiency.family_verdict('mlp', e_train=10 ** 6, **{**good, 'training_years': 5.0})['verdict'] == 'INSUFFICIENT'
    assert sufficiency.family_verdict('transformer', e_train=10 ** 6, **{**good, 'sequence_share': 0.5})['verdict'] == 'INSUFFICIENT'
    assert sufficiency.family_verdict('transformer', e_train=10 ** 6, **good)['verdict'] == 'SUFFICIENT'
    assert sufficiency.family_verdict('mlp', e_train=10 ** 9, **{**good, 'bear_markets_in_training': 0})['verdict'] == 'INSUFFICIENT'      # no row count rescues it
    assert sufficiency.family_verdict('linear', e_train=None, **good)['verdict'] == 'INSUFFICIENT'
    assert {v['verdict'] for v in sufficiency.no_data_verdicts().values()} == {'INSUFFICIENT'} and set(sufficiency.no_data_verdicts()) == set(sufficiency.FAMILIES)


# ----------------------------------------------------------------------------------------------------------- regimes
def test_regimes_are_described_from_the_past_only_and_score_nothing():
    closes = [100, 110, 95, 90, 105, 112, 100, 88, 85, 120, 118, 121]
    sessions = [f'd{k:02d}' for k in range(len(closes))]
    found = regimes.drawdowns(sessions, closes)
    assert [(d['peak'], d['trough'], d['recovered'], d['kind']) for d in found] == [('d01', 'd03', 'd05', 'CORRECTION'), ('d05', 'd08', 'd09', 'BEAR')]
    assert regimes.drawdowns(sessions[:9], closes[:9])[-1]['recovered'] is None                       # an open decline is reported as open
    rng = np.random.default_rng(9)
    series = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 900) * np.r_[np.ones(500), 3 * np.ones(150), np.ones(250)]))
    classes = regimes.volatility_classes(series)
    assert np.all(np.isnan(classes[:252])) and np.nanmean(classes[520:650] == 1.0) > 0.9              # the loud stretch is called high once it is under way
    np.testing.assert_array_equal(regimes.volatility_classes(series[:700])[:700], classes[:700])      # and what was said earlier never changes
    rates = regimes.rate_periods([('2004-06-30', 0.25), ('2006-06-29', 0.25), ('2007-09-18', -0.5), ('2008-12-16', -0.75), ('2015-12-16', 0.25), ('2016-01-27', 0)])
    assert rates == {'rising': [['2004-06-30', '2006-06-29'], ['2015-12-16', '2015-12-16']], 'falling': [['2007-09-18', '2008-12-16']]}
    days = list(calendar.sessions('2019-01-02', '2022-07-29'))
    out = regimes.coverage(days, series[:len(days)], [('2019-07-31', -0.25), ('2022-03-16', 0.25)], first='2020-01-02', last='2021-12-31')
    assert out['descriptive_only'] is True and out['first'] == '2020-01-02' and out['last'] == '2021-12-31' and out['rising_rate_periods'] == 0
    assert not {'score', 'signal', 'rank', 'weight'} & set(out)


# ------------------------------------------------------------------------------------------------------------ report
def test_with_nothing_stored_every_market_bar_is_unmet_the_count_is_zero_and_every_family_is_insufficient(tmp_path):
    report = readiness.build(_research(tmp_path / 'firm_lab'), None, now='2026-10-04T16:00:00+00:00')
    assert report['warning'] == 'DATA READINESS ONLY — NO TRADING MODEL IS ACTIVE' == history.WARNING == history_view.WARNING == history_readiness.WARNING
    assert report['market_data']['status'] == 'NO_VALIDATED_HISTORICAL_BARS' and report['market_data']['bars'] == 0 and report['universe'] is None
    strict = report['strict_training']
    assert strict['strict_samples'] == {'5': 0, '10': 0, '20': 0} and strict['strict_samples_by_tier']['20'] == {'HELD_AT_THE_TIME': 0, 'PUBLISHER_DATED_HISTORICAL': 0}
    assert strict['checkpoint7_retrospective_samples'] == 6490 and strict['retrospective_samples_in_this_dataset'] == 0
    assert {v['verdict'] for families in report['sufficiency']['verdicts'].values() for v in families.values()} == {'INSUFFICIENT'}
    bars = {b['id']: b['status'] for b in report['specification_bars']}
    assert all(bars[i] == 'NOT_MET' for i in ('H1', 'H3', 'H4', 'H6', 'P1', 'O4', 'O6', 'O7', 'E1', 'E2', 'E3', 'F2')) and bars['H5'] == 'NOT_MEASURABLE'
    assert report['provider_decision']['status'] == 'OPERATOR PURCHASE DECISION REQUIRED' and report['provider_decision']['stored_sources'] == []
    assert report['holdout']['checkpoint7_holdout_reused_as_pristine'] is False and report['holdout']['historical_holdout'] == 'RESERVED_NO_DATA_YET'
    assert report['market_data']['closes_held']['tier'] == 'RETROSPECTIVE' and report['fundamentals']['tier'] == 'PUBLISHER_DATED_HISTORICAL'
    assert report['regimes']['development_period']['status'] == 'NOT_MEASURABLE' and report['regimes']['held_today']['proxy_tier'] == 'RETROSPECTIVE'
    assert any('FRED' in line for p in report['provenance'] for line in p['limitations'])
    again = readiness.build(tmp_path / 'firm_lab' / 'firm_lab.db', None, now='2026-10-05T09:00:00+00:00')
    assert again['report_hash'] == report['report_hash']                                              # the hash is over the content, not the clock


def test_with_stored_history_the_report_counts_and_still_holds_no_price(stored):
    folder, research = stored
    report = readiness.build(research, folder / 'firm_lab_history.db')
    market = report['market_data']
    assert market['status'] == 'STORED' and market['provider'] == 'Sharadar' and market['delisted_with_bars'] == 2 and market['last_bar_of_delisted_by_year'] == {'2020': 1, '2021': 1}
    assert report['strict_training']['strict_samples']['20'] > 10000 and report['strict_training']['strict_samples_by_tier']['20']['HELD_AT_THE_TIME'] == 0
    assert report['universe']['universe_version'] == fx.VERSION and report['holdout']['historical_holdout'] == 'RESERVED_SEALED'
    assert report['holdout']['reservation_stored_in_database'] is True
    check = report['cross_check']
    assert check['compared'] == 2 * 378 and check['share_agreeing'] == 1.0 and check['instruments_not_matched'] == ['VTI'] and check['disagreements'] == []
    bars = {b['id']: b for b in report['specification_bars']}
    assert bars['O6']['status'] == 'MET' and bars['H1']['status'] == 'NOT_MET' and bars['P1']['status'] == 'MET' and bars['H4']['status'] == 'MET'
    assert {v['verdict'] for families in report['sufficiency']['verdicts'].values() for v in families.values()} == {'INSUFFICIENT'}       # thirteen invented stocks are not enough
    text = json.dumps(report)
    data = fx.series('III')
    for value in (data['close'][100], data['open'][700], data['unadjusted'][1500]):
        assert f'{value:.4f}'[:7] not in text                                                         # no stored price is in the report
    assert not re.search(r'"(open|high|low|close|closes|volume)"\s*:\s*\[', text)
    path = readiness.write(report, folder / 'firm_lab' / history.READINESS_FILE)
    assert Path(path).stat().st_size < 200_000
    with pytest.raises(ValueError, match='NOT_A_READINESS_REPORT'):
        readiness.write({'kind': 'something else'}, folder / 'x.json')


def test_a_disagreeing_close_is_listed_by_identity_and_fails_the_cross_check(stored, tmp_path):
    folder, research = stored
    other = tmp_path / 'firm_lab'
    other.mkdir()
    shutil.copy(research, other / 'firm_lab.db')
    db = sqlite3.connect(other / 'firm_lab.db')
    db.execute("UPDATE feature_observations SET value = CAST(value AS REAL) * 1.02 WHERE instrument='AAA' AND exchange_session_date='2026-03-02'")
    db.commit()
    db.close()
    report = readiness.build(other / 'firm_lab.db', folder / 'firm_lab_history.db')
    assert report['cross_check']['disagreements'] == [['AAA', '2026-03-02']] and report['cross_check']['agreeing'] == report['cross_check']['compared'] - 1
    assert {b['id']: b['status'] for b in report['specification_bars']}['O6'] == 'MET'                # 755 of 756 is above 99.5%, and the one is named


# -------------------------------------------------------------------------------------------------- projection and page
def test_the_projection_reads_only_a_valid_readiness_file(stored, tmp_path):
    folder, research = stored
    readiness.write(readiness.build(research, folder / 'firm_lab_history.db'), research.with_name(history.READINESS_FILE))
    state = history_view.summary(research)
    assert state['exists'] and state['report']['kind'] == 'historical_data_readiness' and state['file'].endswith('firm_lab_history_readiness.json')
    assert history_view.summary(tmp_path / 'nowhere' / 'firm_lab.db') == {'exists': False, 'warning': history.WARNING, 'missing_reason': 'NO_STORED_READINESS_REPORT', 'report': None}
    target = tmp_path / 'firm_lab.db'
    for change, reason in ((lambda r: r['strict_training']['strict_samples'].update({'20': 999999}), 'READINESS_REPORT_HASH_MISMATCH'),
                           (lambda r: r.update(warning='TRADE NOW'), 'NOT_A_READINESS_REPORT'), (lambda r: r.pop('holdout'), 'READINESS_REPORT_INCOMPLETE')):
        report = json.loads(research.with_name(history.READINESS_FILE).read_text())
        change(report)
        target.with_name(history.READINESS_FILE).write_text(json.dumps(report))
        assert history_view.summary(target)['missing_reason'] == reason and history_view.summary(target)['report'] is None
    target.with_name(history.READINESS_FILE).write_text('{not json')
    assert history_view.summary(target)['missing_reason'].startswith('READINESS_FILE_UNREADABLE')
    assert _imports(ROOT / 'firm_lab' / 'history_view.py') <= {'__future__', 'hashlib', 'json', 'pathlib'}       # standard library only: no research code, no numpy


def test_the_page_shows_the_warning_the_strict_count_provenance_and_limitations_and_no_instruction(stored, tmp_path):
    folder, research = stored
    for name, history_db in (('stored', folder / 'firm_lab_history.db'), ('empty', None)):
        report = readiness.build(research, history_db)
        target = tmp_path / name / 'firm_lab.db'
        target.parent.mkdir()
        readiness.write(report, target.with_name(history.READINESS_FILE))
        html = history_readiness.render_history({'history': history_view.summary(target)})
        assert html.count('DATA READINESS ONLY — NO TRADING MODEL IS ACTIVE') == 1 and '<p class="fl-stamp">' in html
        assert 'Strict point-in-time samples:' in html and 'held at the time: 0' in html and '6,490 retrospective samples' in html
        assert 'the Checkpoint 7 holdout is not reused' in html and 'sealed' in html
        for heading in ('Source provenance', 'Known-at methodology', 'Adjustment basis', 'Point-in-time eligibility', 'Provider / source', 'Date range', 'Version',
                        'Fresh holdout', 'Market regime coverage', 'Data sufficiency by model family', 'Remaining gaps', 'Sufficiency bars'):
            assert heading in html, heading
        assert 'INSUFFICIENT for every model family' in html and 'No post-delisting return exists' in html
        assert '<form' not in html and '<input' not in html and '<button' not in html and '<script' not in html and 'href=' not in html
        words = re.sub(r'<[^>]+>', ' ', html).upper()
        assert not [w for w in ACTION_WORDS if re.search(rf'\b{w}\b', words)]
        assert not re.search(r'\$\s?\d+\.\d{2}\b', re.sub(r'\$39 per month or \$299 per year', '', html))       # the only dollar amounts are the subscription's
        if name == 'empty':
            assert 'No historical market data is stored' in html and 'OPERATOR PURCHASE DECISION REQUIRED' in html and 'Nothing has been purchased by this system' in html
            assert '0 with a 20-session label' in html
        else:
            assert 'daily bars stored; each passed the row checks. 13 securities' in html and fx.VERSION in html and 'Tier B — publisher-dated historical' in html
    none = history_readiness.render_history({'history': history_view.empty()})
    assert history.WARNING in none and 'No historical data readiness report is stored' in none
    broken = history_readiness.render_history({'history': {'exists': True, 'report': {'market_data': 7}}})
    assert history.WARNING in broken and 'could not be drawn' in broken                               # a damaged report never takes the page down
    page = firm_lab_page.render({'firm_lab': {'exists': False, 'mode': 'BUILD_OBSERVE', 'fills': 0}})
    assert isinstance(page, str)
    assert 'id="fl-history"><h2>Historical Data Readiness</h2>' in (ROOT / 'agents' / 'desk' / 'firm_lab_page.py').read_text()


# ------------------------------------------------------------------------------------------------------ capabilities
def test_capability_rows_follow_the_report_and_nothing_is_available_without_validated_data(stored, tmp_path):
    from firm_lab.errors import CapabilityUnavailable
    from firm_lab.store import FirmLabStore
    folder, research = stored
    lab = FirmLabStore(tmp_path / 'diag' / 'firm_lab' / 'firm_lab.db')
    capabilities.seed(lab)
    before = {c['capability']: c['status'] for c in lab.capabilities()}
    empty = readiness.build(research, None)
    written = history_capability.record(lab, empty)
    assert written == {'historical_ohlcv': 'UNAVAILABLE', 'historical_universe': 'UNAVAILABLE', 'pit_fundamentals': 'PARTIAL_EXISTING', 'pit_earnings': 'PARTIAL_EXISTING',
                       'pit_macro': 'PARTIAL_EXISTING', 'strict_pit_training_data': 'UNAVAILABLE'}
    status = {c['capability']: c for c in lab.capabilities()}
    assert {k: status[k]['status'] for k in before} == before                                         # no existing row moved: the model rows are untouched
    assert 'OPERATOR PURCHASE DECISION REQUIRED' in status['historical_ohlcv']['detail'] and '0 strict point-in-time samples' in status['strict_pit_training_data']['detail']
    assert 'FRED' in status['pit_macro']['detail']
    for name in ('historical_ohlcv', 'strict_pit_training_data', 'pit_fundamentals'):
        with pytest.raises(CapabilityUnavailable):
            capabilities.require(lab, name)
    full = readiness.build(research, folder / 'firm_lab_history.db')
    written = history_capability.record(lab, full)
    assert written['historical_ohlcv'] == 'PARTIAL_EXISTING' and written['historical_universe'] == 'PARTIAL_EXISTING'      # stored, but the history bar is not met
    assert written['strict_pit_training_data'] == 'PARTIAL_EXISTING'                                  # samples exist; the data behind them is not yet validated to the bars
    passing = json.loads(json.dumps(full))
    for b in passing['specification_bars']:
        if b['id'] in ('H1', 'H3', 'H4', 'O4', 'O6'):
            b['status'] = 'MET'
    with pytest.raises(ValueError, match='READINESS_REPORT_HASH_MISMATCH'):
        history_capability.statuses(passing)                                                          # an edited report is refused
    passing['report_hash'] = history_view._hash(passing)                                              # as a new report with these bars met would be
    rows = history_capability.statuses(passing)
    assert rows['historical_ohlcv'][0] == rows['historical_universe'][0] == rows['strict_pit_training_data'][0] == 'AVAILABLE'
    assert rows['historical_ohlcv'][3]['records'] == full['market_data']['bars'] and rows['historical_ohlcv'][3]['validation_passed'] is True
    assert rows['pit_fundamentals'][0] == 'PARTIAL_EXISTING'                                          # a five-company sample is never "available"
    with pytest.raises(ValueError, match='NOT_A_READINESS_REPORT'):
        history_capability.record(lab, {'kind': 'x'})
    assert lab.mode() == 'BUILD_OBSERVE' and not lab.active_experiments()
    assert set(history_capability.ROWS).isdisjoint({'ml_ranker', 'deep_learning', 'transformer_models', 'portfolio_optimizer', 'options_strategy', 'rl_policy'})


# --------------------------------------------------------------------------------------------------------- isolation
def _imports(path):
    tree = ast.parse(path.read_text())
    return ({a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
            | {n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and not n.level})


def test_the_history_package_cannot_reach_a_broker_the_network_a_model_or_the_trading_side():
    files = sorted(PACKAGE.glob('*.py')) + [ROOT / 'firm_lab' / 'history_view.py', ROOT / 'firm_lab' / 'history_capability.py']
    assert len(files) >= 17
    for path in files:
        modules = _imports(path)
        assert not [m for m in modules if m.split('.')[0] in BANNED_IMPORTS], (path.name, modules)
        assert not [m for m in modules if m.startswith('firm_lab')], (path.name, modules)             # only relative imports inside the package
        text = path.read_text()
        for word in ('paper_accounts', 'submit(', 'place_order', 'ExecutionBoundary', 'launchctl', 'crontab', 'schedule.every', 'api_key', 'password', 'getpass',
                     'os.environ', 'keyring'):
            if (path.name, word) == ('store.py', 'paper_accounts'):
                assert text.count('paper_accounts') == 1 and "OFFICIAL_TABLES = {'paper_accounts'" in text       # named once, only to be refused
                continue
            assert word not in text, (path.name, word)
    relative = {path.name: {n.module for n in ast.walk(ast.parse(path.read_text())) if isinstance(n, ast.ImportFrom) and n.level and n.module} for path in files}
    assert not [name for name, modules in relative.items() if modules & {'modeling', 'research_features', 'boundary', 'providers', 'ingest_official'}]
    assert relative['history_capability.py'] == {'capabilities', 'history_view'}                      # the registry, and the check that a report is intact
    for name in ('dataset.py', 'universe.py', 'targets.py', 'features.py', 'pivots.py', 'sufficiency.py', 'regimes.py', 'splits.py'):
        assert 'sqlite3' not in _imports(PACKAGE / name), name                                        # they reach data only through the checked store
    assert 'fit(' not in ''.join(p.read_text() for p in files) and 'predict(' not in ''.join(p.read_text() for p in files)


def test_nothing_on_the_trading_side_imports_the_history_package_and_nothing_schedules_it():
    for folder in ('agents', 'broker', 'broker_proxy', 'risk', 'config', 'eval', 'scripts', 'data', 'research', 'firm_lab_collectors'):
        for path in sorted((ROOT / folder).rglob('*.py')) if (ROOT / folder).is_dir() else []:
            text = path.read_text(errors='ignore')
            if path.name in ('firm_lab_page.py', 'history_readiness.py'):
                continue
            assert 'firm_lab.history' not in text and 'history_view' not in text and 'firm_lab_history' not in text, path
    assert _imports(ROOT / 'agents' / 'desk' / 'history_readiness.py') == set()                       # the renderer imports only the escaper
    assert 'from .components import esc' in (ROOT / 'agents' / 'desk' / 'history_readiness.py').read_text()
    page = (ROOT / 'agents' / 'desk' / 'firm_lab_page.py').read_text()
    assert 'firm_lab.history' not in page and 'from .history_readiness import render_history' in page
    view = (ROOT / 'firm_lab' / 'view.py').read_text()
    assert 'from .history_view import summary as history_summary' in view and 'from .history ' not in view and 'history.readiness' not in view
    for path in ROOT.rglob('*'):
        if path.is_file() and path.suffix in ('.plist', '.sh', '.command', '.service', '.timer', '.cron') and '.git' not in path.parts:
            assert 'firm_lab.history' not in path.read_text(errors='ignore'), path
    for name in ('modeling',):                                         # the Checkpoint 7 laboratory is not wired to this data: no tournament can start from here
        for path in sorted((ROOT / 'firm_lab' / name).glob('*.py')):
            assert 'firm_lab.history' not in path.read_text() and 'from ..history' not in path.read_text(), path


def test_the_commands_are_manual_and_read_only_what_the_operator_downloaded(stored, tmp_path, capsys):
    from firm_lab.history import cli
    folder, research = stored
    assert cli.main(['init', '--db', str(tmp_path / 'new' / 'firm_lab_history.db')]) == 0
    with HistoryStore(tmp_path / 'new' / 'firm_lab_history.db', read_only=True) as store:
        assert [p['split_version'] for _, p, _ in store.rows('history_reservations')] == ['c9-chronology-v1']       # the holdout is reserved before any data exists
    assert cli.main(['readiness', '--research-db', str(research), '--out', str(tmp_path / history.READINESS_FILE)]) == 0
    assert json.loads((tmp_path / history.READINESS_FILE).read_text())['market_data']['status'] == 'NO_VALIDATED_HISTORICAL_BARS'
    out = capsys.readouterr().out
    assert '"strict_samples"' in out and 'api' not in out.lower()
    text = (PACKAGE / 'cli.py').read_text() + (PACKAGE / 'sharadar_files.py').read_text()
    assert 'https://' not in text and 'http://' not in text
