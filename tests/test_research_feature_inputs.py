"""PIT regressions: data may describe September but first be known in October."""
import sqlite3
import json
import pytest


def test_calendar_early_close_and_holiday():
    from firm_lab.research_features.calendar import resolve_request
    assert resolve_request('VTI', as_of='2026-11-27').knowledge_cutoff == '2026-11-27T18:00:00+00:00'
    with pytest.raises(ValueError):
        resolve_request('VTI', as_of='2026-07-03')
    r = resolve_request('VTI', as_of='2026-11-27T17:59:00+00:00')
    assert r.as_of_session == '2026-11-25'
    with pytest.raises(ValueError):
        resolve_request('VTI', as_of='2026-11-27T17:59:00')


def test_temporal_modes_are_explicit():
    from firm_lab.research_features.calendar import resolve_request
    with pytest.raises(ValueError):
        resolve_request('VTI', session='2026-09-30')
    with pytest.raises(ValueError):
        resolve_request('VTI', as_of='2026-09-30', session='2026-09-30', known_by='2026-10-03T20:00:00Z')
    assert resolve_request('VTI', session='2026-09-30', known_by='2026-10-03T20:00:00Z').as_of_session == '2026-09-30'


def fixture_db(tmp_path):
    from firm_lab.store import FirmLabStore
    path = tmp_path / 'research' / 'firm.db'
    store = FirmLabStore(path, official_db=tmp_path / 'official' / 'agent.db')
    for day, value in [('2026-09-28', '100'), ('2026-09-29', '101'), ('2026-09-30', '102')]:
        store.add_feature(instrument='VTI', feature_name='close', value=value, source='provider',
            source_timestamp=day+'T00:00:00+00:00', known_at='2026-10-01T20:00:00+00:00',
            exchange_session_date=day, feature_version='baseline-v1', provider='test', metadata={})
    return path, store


def test_old_closes_require_later_knowledge_and_revision_waits(tmp_path):
    from firm_lab.research_features.inputs import load_snapshot
    from firm_lab.research_features.calendar import resolve_request
    path, store = fixture_db(tmp_path)
    store.add_feature(instrument='VTI', feature_name='close', value='103', source='provider',
        source_timestamp='2026-09-30T00:00:00+00:00', known_at='2026-10-02T20:00:00+00:00',
        exchange_session_date='2026-09-30', feature_version='baseline-v1', provider='test')
    with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as db:
        old = load_snapshot(db, resolve_request('VTI', as_of='2026-09-30'))
        assert old['closes'] == []
        req = resolve_request('VTI', session='2026-09-30', known_by='2026-10-01T20:00:00Z')
        rows = load_snapshot(db, req)['closes']
        assert [r['value'] for r in rows] == ['100', '101', '102']
        assert all(r['ref'].content_hash for r in rows)


def test_missing_session_not_compressed(tmp_path):
    from firm_lab.research_features.inputs import load_snapshot
    from firm_lab.research_features.calendar import resolve_request
    path, _ = fixture_db(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM feature_observations WHERE exchange_session_date='2026-09-29'")
    with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as db:
        snapshot = load_snapshot(db, resolve_request('VTI', session='2026-09-30', known_by='2026-10-03T20:00:00Z'))
        assert snapshot['closes'] == []
        assert 'INCOMPLETE_WINDOW' in snapshot['missing_reasons']


def test_event_revision_and_acceptance_filter():
    from firm_lab.research_features.inputs import eligible_rows
    rows = [dict(id=1, known_at='2026-10-01T10:00:00Z', accepted_timestamp='2026-10-02T10:00:00Z'),
            dict(id=2, known_at='2026-10-01T10:00:00Z', accepted_timestamp='2026-10-01T09:00:00Z')]
    assert [r['id'] for r in eligible_rows(rows, '2026-10-01T20:00:00Z')] == [2]
    macro = [dict(id=1, series='pce', period='2026-08', revision=0,
                  known_at='2026-10-01T10:00:00Z', published_at='2026-09-30T12:30:00Z'),
             dict(id=2, series='pce', period='2026-08', revision=1,
                  known_at='2026-10-02T10:00:00Z', published_at='2026-10-02T09:00:00Z')]
    assert len(eligible_rows(macro, '2026-10-01T20:00:00Z')) == 1


def test_source_revision_conflict_and_benchmark_guard(tmp_path):
    from firm_lab.research_features.inputs import load_snapshot
    from firm_lab.research_features.calendar import resolve_request
    path, _ = fixture_db(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE feature_observations SET metadata_json=? WHERE id=1", (json.dumps({'benchmark_only': True}),))
    with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as db:
        snap = load_snapshot(db, resolve_request('VTI', session='2026-09-30', known_by='2026-10-03T20:00:00Z'))
        assert snap['closes'] == []
        assert any('BENCHMARK' in r for r in snap['missing_reasons'])


@pytest.mark.parametrize('damage,reason', [('conflict', 'CONFLICTING_SOURCE_REVISION'),
    ('basis', 'MIXED_PRICE_BASIS'), ('split', 'CORPORATE_ACTION_UNRESOLVED')])
def test_unusable_price_window_fails_closed(tmp_path, damage, reason):
    from firm_lab.research_features.inputs import load_snapshot
    from firm_lab.research_features.calendar import resolve_request
    path, _ = fixture_db(tmp_path)
    with sqlite3.connect(path) as db:
        if damage == 'conflict':
            cols = [r[1] for r in db.execute('PRAGMA table_info(feature_observations)') if r[1] != 'id']
            row = list(db.execute('SELECT '+','.join(cols)+' FROM feature_observations LIMIT 1').fetchone())
            row[cols.index('value')] = '999'
            db.execute('INSERT INTO feature_observations('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+')', row)
        elif damage == 'basis':
            db.execute("UPDATE feature_observations SET metadata_json=? WHERE id=1", ('{"currency":"EUR"}',))
        else:
            # Dedicated minimal source schema isolates action-gating from unrelated collector validation.
            db.execute('DROP TABLE corporate_action_observations')
            db.execute('CREATE TABLE corporate_action_observations(instrument,action_type,effective_date,known_at)')
            db.execute("INSERT INTO corporate_action_observations VALUES('VTI','split','2026-09-29','2026-10-01T20:00:00Z')")
    with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as db:
        snap = load_snapshot(db, resolve_request('VTI', session='2026-09-30', known_by='2026-10-03T20:00:00Z'))
        assert snap['closes'] == []
        assert reason in snap['missing_reasons']
