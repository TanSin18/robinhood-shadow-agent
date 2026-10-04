"""Checkpoint 7 dataset construction: the session-time modeling database, the feature history and the dataset contract.

What is proven here: the live research database is never written; every relabelled time is recorded beside the original;
a feature for session T does not change when anything after T changes (no label or future close can enter it); labels
are aligned with the benchmark; the dataset has stable hashes; and the modeling database cannot hold a trade."""
import hashlib
import json
import sqlite3

import pytest

np = pytest.importorskip('numpy')
pytest.importorskip('exchange_calendars')

from firm_lab.modeling import dataset, history, targets, timeview
from firm_lab.research_features.calendar import session_close, session_dates
from firm_lab.research_features.engine import calculation_hash

CAPTURED = '2026-10-01T14:02:11.471152+00:00'
SESSIONS = session_dates('2025-03-31', '2025-06-27')            # 62 real exchange sessions
INSTRUMENTS = ('VTI', 'AAA', 'BBB')


def _price(instrument, k, shock_after=None):
    base = {'VTI': 300.0, 'AAA': 50.0, 'BBB': 120.0}[instrument]
    drift = {'VTI': 0.0008, 'AAA': 0.002, 'BBB': -0.0005}[instrument]
    wave = {'VTI': 0.004, 'AAA': 0.02, 'BBB': 0.012}[instrument]
    value = base * (1 + drift) ** k * (1 + wave * np.sin(k / 3.0 + len(instrument)))
    if shock_after is not None and k > shock_after:
        value *= 1.9 if instrument != 'VTI' else 0.6                                                # everything after the cut is different
    return f'{value:.6f}'


def _source(path, *, shock_after=None, extra=None):
    """A research database in the stored form: closes captured on 2026-10-01, long after the sessions they describe."""
    db = sqlite3.connect(path)
    with db:
        db.execute('CREATE TABLE firm_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)')
        db.execute("INSERT INTO firm_meta VALUES ('mode', 'BUILD_OBSERVE', ?)", (CAPTURED,))
        db.execute('CREATE TABLE feature_observations (id INTEGER PRIMARY KEY, instrument TEXT NOT NULL, feature_name TEXT NOT NULL, value TEXT, source TEXT NOT NULL, '
                   'source_timestamp TEXT, known_at TEXT NOT NULL, ingested_at TEXT NOT NULL, exchange_session_date TEXT NOT NULL, feature_version TEXT NOT NULL, '
                   "provider TEXT, revision INTEGER NOT NULL DEFAULT 0, metadata_json TEXT NOT NULL DEFAULT '{}')")
        for instrument in INSTRUMENTS:
            for k, session in enumerate(SESSIONS):
                db.execute('INSERT INTO feature_observations (instrument, feature_name, value, source, source_timestamp, known_at, ingested_at, exchange_session_date, '
                           'feature_version, provider, revision, metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                           (instrument, 'close', _price(instrument, k, shock_after), 'control_a_decision_capsule', session + 'T00:00:00+00:00', CAPTURED, CAPTURED,
                            session, 'baseline-v1', 'robinhood_read_gateway (as recorded by Control A)', 0, '{}'))
            db.execute("INSERT INTO feature_observations (instrument, feature_name, value, source, known_at, ingested_at, exchange_session_date, feature_version, provider) "
                       "VALUES (?, 'ma200', '1', 'firm_lab_feature_store', ?, ?, ?, 'baseline-v1', 'firm_lab')", (instrument, CAPTURED, CAPTURED, SESSIONS[-1]))
        for statement in extra or ():
            db.execute(statement)
    db.close()
    return path


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope='module')
def lab(tmp_path_factory):
    """A modeling database with the feature history of two instruments for the sessions a small dataset needs."""
    root = tmp_path_factory.mktemp('modeling')
    (root / 'research').mkdir()
    source = _source(root / 'research' / 'firm_lab.db')
    before = _sha(source)
    target = root / 'modeling' / 'firm_lab_modeling.db'
    target.parent.mkdir()
    policy = timeview.build(source, target, official_db=root / 'runtime' / 'data' / 'agent.db')
    receipt = history.generate(target, sessions=SESSIONS[30:])
    return {'root': root, 'source': source, 'source_sha_before': before, 'target': target, 'policy': policy, 'receipt': receipt}


def test_the_modeling_database_is_a_separate_file_and_the_research_database_is_not_written(lab, tmp_path):
    assert _sha(lab['source']) == lab['source_sha_before']                                         # opened read-only: not a byte changed
    policy = timeview.check(lab['target'])
    assert policy['policy'] == 'SESSION_TIME_RETROSPECTIVE' and policy['source_sha256'] == lab['source_sha_before']
    assert policy['rows']['feature_observations'] == len(SESSIONS) * 3 and 'Not evidence' in policy['statement']
    db = sqlite3.connect(lab['target'])
    names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not [n for n in names if any(word in n for word in timeview.FORBIDDEN_TABLE_WORDS)]     # no order, fill, position, account or cash table
    assert dict(db.execute('SELECT key, value FROM firm_meta'))['database_role'] == 'CHECKPOINT7_MODELING_RESEARCH'
    assert db.execute("SELECT COUNT(*) FROM feature_observations WHERE feature_name != 'close'").fetchone()[0] == 0      # only closes are carried over
    # every relabelled row is on record beside what it was
    entry = json.loads(db.execute('SELECT payload FROM modeling_time_view LIMIT 1').fetchone()[0])
    assert entry['original_known_at'] == CAPTURED and entry['basis'] == 'exchange session close' and len(entry['original_row_hash']) == 64
    row = db.execute("SELECT exchange_session_date, known_at FROM feature_observations WHERE instrument='AAA' ORDER BY id LIMIT 1").fetchone()
    assert row[1] == session_close(row[0]) and row[1] < CAPTURED                                   # known at its own session close, not at capture
    assert db.execute('SELECT COUNT(*) FROM modeling_time_view').fetchone()[0] == len(SESSIONS) * 3
    for statement in ("UPDATE modeling_time_view SET payload='{}'", 'DELETE FROM modeling_feature_results', "UPDATE modeling_feature_results SET payload='{}'"):
        with pytest.raises(sqlite3.DatabaseError, match='APPEND_ONLY'):
            db.execute(statement)
    db.close()
    with pytest.raises(ValueError, match='MODELING_DATABASE_EXISTS'):
        timeview.build(lab['source'], lab['target'], official_db=tmp_path / 'agent.db')              # never overwritten
    official = tmp_path / 'runtime' / 'data' / 'agent.db'
    official.parent.mkdir(parents=True)
    sqlite3.connect(official).close()
    with pytest.raises(ValueError, match='OFFICIAL_DATABASE_FORBIDDEN'):
        timeview.build(official, tmp_path / 'm.db', official_db=official)                            # the registered database is never a source
    with pytest.raises(ValueError, match='MODELING_DATABASE_MUST_BE_SEPARATE'):
        timeview.build(lab['source'], official.parent / 'm.db', official_db=official)                # and nothing is created beside it
    trade = tmp_path / 'with_orders.db'
    db = sqlite3.connect(trade)
    db.execute('CREATE TABLE firm_meta (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)')
    db.executemany('INSERT INTO firm_meta VALUES (?,?,?)', [('mode', 'BUILD_OBSERVE', ''), ('database_role', 'CHECKPOINT7_MODELING_RESEARCH', ''), ('time_policy', '{}', '')])
    db.execute('CREATE TABLE paper_orders (id INTEGER)')
    db.commit()
    db.close()
    with pytest.raises(ValueError, match='EXECUTION_TABLE_FORBIDDEN'):
        timeview.check(trade)


def test_publisher_times_replace_capture_times_and_a_row_without_one_is_left_out(tmp_path):
    extra = ['CREATE TABLE filing_observations (id INTEGER PRIMARY KEY, instrument TEXT, accepted_timestamp TEXT, known_at TEXT)',
             "INSERT INTO filing_observations VALUES (1, 'AAA', '2025-05-01T20:05:00+00:00', '2026-10-02T15:04:20+00:00')",
             "INSERT INTO filing_observations VALUES (2, 'AAA', NULL, '2026-10-02T15:04:20+00:00')",
             'CREATE TABLE macro_observations (id INTEGER PRIMARY KEY, series TEXT, period TEXT, revision INTEGER, published_at TEXT, known_at TEXT, payload_json TEXT, record_hash TEXT)',
             "INSERT INTO macro_observations VALUES (1, 'pce_core_mom_sa', '2025-04', 0, '2025-05-30T12:30:00+00:00', '2026-10-03T20:12:13+00:00', "
             "'{\"known_at\":\"2026-10-03T20:12:13+00:00\",\"value\":\"0.2\"}', 'h')",
             'CREATE TABLE research_sector_mappings (id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL)',
             "INSERT INTO research_sector_mappings VALUES ('m', '{\"known_at\":\"2026-10-03T21:50:02+00:00\"}', '2026-10-03T23:33:03+00:00')"]
    source = _source(tmp_path / 'firm_lab.db', extra=extra)
    target = tmp_path / 'modeling.db'
    policy = timeview.build(source, target, official_db=tmp_path / 'runtime' / 'agent.db')
    db = sqlite3.connect(target)
    assert db.execute('SELECT id, known_at FROM filing_observations').fetchall() == [(1, '2025-05-01T20:05:00+00:00')]      # SEC acceptance, not capture
    assert policy['rows_without_a_public_time_left_out'] == {'filing_observations': 1}                                     # undatable: left out, and counted
    macro = db.execute('SELECT known_at, payload_json FROM macro_observations').fetchone()
    assert macro[0] == '2025-05-30T12:30:00+00:00' and json.loads(macro[1])['known_at'] == '2025-05-30T12:30:00+00:00'      # publication time, inside the payload too
    assert json.loads(db.execute('SELECT payload FROM research_sector_mappings').fetchone()[0])['known_at'] == '2026-10-03T21:50:02+00:00'
    db.close()                                                                                     # a mapping dated 2026-10-03 stays unusable for every earlier session


def test_the_feature_history_uses_the_unchanged_calculators_at_each_session_close_and_is_idempotent(lab):
    receipt = lab['receipt']
    assert receipt['inserted'] == 3 * 32 and receipt['duplicates'] == 0 and receipt['calculation_hash'] == calculation_hash()
    assert history.generate(lab['target'], sessions=SESSIONS[30:]) == {**receipt, 'inserted': 0, 'duplicates': 96, 'results': 0, 'available': 0}
    db = sqlite3.connect(lab['target'])
    payloads = [json.loads(p) for (p,) in db.execute('SELECT payload FROM modeling_feature_results')]
    db.close()
    assert len(payloads) == 96 and all(p['result_count'] == 222 for p in payloads)
    for p in payloads:
        cutoff = session_close(p['session'])
        assert p['knowledge_cutoff'] == cutoff and p['latest_input_known_at'] <= cutoff and p['time_policy'] == 'SESSION_TIME_RETROSPECTIVE'
        results = history.read_results(p)
        assert all(r['known_at'] <= cutoff for r in results if r['availability'] == 'AVAILABLE')    # nothing in a snapshot was known after its session closed
        assert all(r['value'] is None and r['missing_reason'] for r in results if r['availability'] != 'AVAILABLE')
    one = next(p for p in payloads if p['instrument'] == 'AAA' and p['session'] == SESSIONS[45])
    values = {r['name']: r for r in history.read_results(one)}
    closes = [float(_price('AAA', k)) for k in range(46)]
    assert float(values['return20']['value']) == pytest.approx(closes[45] / closes[25] - 1)         # the accepted calculator's number, from closes up to T only
    assert values['return63']['availability'] == 'UNAVAILABLE' and values['atr14']['missing_reason']      # short history and absent OHLCV stay unavailable


def test_nothing_after_a_session_can_change_that_sessions_features(lab, tmp_path):
    """The same history, except that every close after session 45 is wildly different. The stored feature snapshot for
    session 45 is identical; only labels that look past session 45 move."""
    changed = _source(tmp_path / 'firm_lab.db', shock_after=45)
    target = tmp_path / 'modeling.db'
    timeview.build(changed, target, official_db=tmp_path / 'runtime' / 'agent.db')
    history.generate(target, instruments=['AAA'], sessions=[SESSIONS[45], SESSIONS[50]])

    def snapshot(path, session):
        db = sqlite3.connect(path)
        try:
            rows = [json.loads(p) for (p,) in db.execute('SELECT payload FROM modeling_feature_results')]
        finally:
            db.close()
        return next(p for p in rows if p['instrument'] == 'AAA' and p['session'] == session)

    original, altered = snapshot(lab['target'], SESSIONS[45]), snapshot(target, SESSIONS[45])
    assert original['results_digest'] == altered['results_digest'] and original['results_zlib_b64'] == altered['results_zlib_b64']
    assert snapshot(lab['target'], SESSIONS[50])['results_digest'] != snapshot(target, SESSIONS[50])['results_digest']      # a later session does see the change
    _, a = targets.load_closes(lab['target'])
    _, b = targets.load_closes(target)
    first, second = targets.build(SESSIONS, a), targets.build(SESSIONS, b)
    assert first[('AAA', SESSIONS[30])]['excess_return_10'] == second[('AAA', SESSIONS[30])]['excess_return_10']        # its window ends at session 40
    assert first[('AAA', SESSIONS[40])]['excess_return_10'] != second[('AAA', SESSIONS[40])]['excess_return_10']        # its window reaches past the cut


def test_features_are_built_without_reading_a_close_or_a_label(lab, monkeypatch):
    def refuse(*_, **__):
        raise AssertionError('the feature builder must not read closes or labels')
    monkeypatch.setattr(targets, 'load_closes', refuse)
    monkeypatch.setattr(targets, 'build', refuse)
    features = dataset.build_features(lab['target'])
    assert len(features) == 96 and ('AAA', SESSIONS[45]) in features
    identity, values, digest, _ = features[('AAA', SESSIONS[45])]
    assert len(identity) == 64 and digest == calculation_hash() and 'return20' in values and 'sma20' not in values      # a dollar level is not a model input
    assert not [name for name in values if name.startswith('excess_return') and not name.startswith('excess_vti')]     # no label name among the features


def test_the_dataset_contract_keeps_every_field_and_its_hashes_are_stable(lab, monkeypatch):
    monkeypatch.setattr(dataset, 'MINIMUM_HISTORY', 30)
    data = dataset.build(lab['target'])
    again = dataset.build(lab['target'])
    assert data.manifest['dataset_hash'] == again.manifest['dataset_hash'] and data.manifest['hashes'] == again.manifest['hashes']
    assert data.instruments == ['AAA', 'BBB'] and data.X.shape[0] == 2 * 32 and data.manifest['benchmark'] == 'VTI'       # the benchmark is not a sample
    assert data.manifest['time_policy'] == 'SESSION_TIME_RETROSPECTIVE' and data.manifest['calculation_hash'] == calculation_hash()
    assert data.manifest['target_version'] == 'forward-excess-price-return-v1' and data.manifest['encoding_version'] == 'numeric-encoding-v1'
    assert data.manifest['source_sha256'] == lab['source_sha_before']
    # labels: aligned with the benchmark over the same sessions, absent when the window runs past the stored history
    row = next(r for r in range(len(data.snapshot_ids)) if data.instruments[data.row_instrument[r]] == 'AAA' and data.sessions[data.row_session[r]] == SESSIONS[35])
    own = float(_price('AAA', 45)) / float(_price('AAA', 35)) - 1
    market = float(_price('VTI', 45)) / float(_price('VTI', 35)) - 1
    assert data.y['excess_return_10'][row] == pytest.approx(own - market, abs=1e-9)
    assert np.isnan(data.y['excess_return_10'][data.row_session == len(SESSIONS) - 1]).all() and np.isnan(data.y['excess_return_20'][data.row_session >= len(SESSIONS) - 20]).all()
    record = dataset.sample_records(data)[row]
    assert record['instrument'] == 'AAA' and record['feature_session'] == SESSIONS[35] and record['feature_knowledge_cutoff'] == session_close(SESSIONS[35])
    assert record['feature_snapshot_id'] == data.snapshot_ids[row] and record['target_start_session'] == SESSIONS[35] and record['benchmark'] == 'VTI'
    assert record['horizons']['10'] == {'target_end_session': SESSIONS[45], 'instrument_return': pytest.approx(own), 'benchmark_return': pytest.approx(market)}
    assert record['dataset_hash'] == data.manifest['dataset_hash'] and record['calculation_hash'] == calculation_hash() and record['target_version']
    # excluded by rule, and named
    assert 'sma20' in data.excluded and 'close_fib_nearest' in data.excluded and 'sma20_distance' in data.feature_names and 'atr14' in data.excluded
    assert all(data.feature_family[name] for name in data.feature_names) and set(data.columns(('fibonacci',))) < set(range(len(data.feature_names)))
    # registered once; a different dataset has a different identity
    assert dataset.register(lab['target'], data) is True and dataset.register(lab['target'], data) is False
    db = sqlite3.connect(lab['target'])
    stored = dict(db.execute('SELECT id, payload FROM modeling_datasets'))
    db.close()
    assert set(stored) == {data.manifest['dataset_hash'], data.manifest['dataset_hash'] + ':samples'}
    assert json.loads(stored[data.manifest['dataset_hash']])['hashes'] == data.manifest['hashes']
    monkeypatch.setattr(dataset, 'ENCODING_VERSION', 'numeric-encoding-v2')
    assert dataset.build(lab['target']).manifest['dataset_hash'] != data.manifest['dataset_hash']


def test_a_snapshot_that_is_not_a_session_close_view_is_refused(lab, tmp_path):
    target = tmp_path / 'tampered.db'
    target.write_bytes(lab['target'].read_bytes())
    db = sqlite3.connect(target)
    identity, payload = db.execute('SELECT id, payload FROM modeling_feature_results LIMIT 1').fetchone()
    body = json.loads(payload)
    later = dict(body, knowledge_cutoff='2026-10-03T22:00:00+00:00', session=body['session'])
    with db:
        db.execute('DROP TRIGGER modeling_feature_results_delete')
        db.execute('DELETE FROM modeling_feature_results WHERE id=?', (identity,))
        db.execute('INSERT INTO modeling_feature_results VALUES (?,?,?)', (identity, json.dumps(later), '2026-10-03T00:00:00+00:00'))
    db.close()
    with pytest.raises(ValueError, match='SNAPSHOT_IS_NOT_A_SESSION_CLOSE_VIEW'):
        dataset.build_features(target)                                                               # a later-knowledge snapshot cannot become a training feature


def test_close_history_with_a_gap_or_a_missing_instrument_is_refused(tmp_path):
    source = _source(tmp_path / 'firm_lab.db', extra=[f"DELETE FROM feature_observations WHERE instrument='BBB' AND exchange_session_date='{SESSIONS[20]}'"])
    target = tmp_path / 'modeling.db'
    timeview.build(source, target, official_db=tmp_path / 'runtime' / 'agent.db')
    with pytest.raises(ValueError, match='INCOMPLETE_CLOSE_HISTORY:BBB'):
        targets.load_closes(target)
    source = _source(tmp_path / 'b.db', extra=["DELETE FROM feature_observations WHERE instrument='VTI'"])
    timeview.build(source, tmp_path / 'b_modeling.db', official_db=tmp_path / 'runtime' / 'agent.db')
    with pytest.raises(ValueError, match='BENCHMARK_CLOSES_MISSING'):
        targets.load_closes(tmp_path / 'b_modeling.db')
