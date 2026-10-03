"""Regression boundaries: aliases, history mutation and unavailable != zero."""
import hashlib
import os
import sqlite3
from dataclasses import replace

import pytest


def result(**changes):
    from firm_lab.research_features.types import FeatureResult, SourceRef
    r = FeatureResult('VTI', 'trend', 'sma20', '0', 'USD', '2026-09-30',
                      '2026-10-03T20:00:00+00:00', 'AVAILABLE', None,
                      (SourceRef('feature_observations', '1', 'a' * 64,
                                 '2026-10-03T20:00:00+00:00'),),
                      'sma20_v1', 'b' * 64, {})
    return replace(r, **changes)


def research_db(tmp_path):
    from firm_lab.store import FirmLabStore
    official = tmp_path / 'official' / 'agent.db'
    official.parent.mkdir(exist_ok=True)
    db = tmp_path / 'research' / 'firm_lab.db'
    FirmLabStore(db, official_db=official)
    return db, official


@pytest.mark.parametrize('alias_kind', ['same', 'symlink', 'hardlink'])
def test_official_alias_rejected(tmp_path, alias_kind):
    from firm_lab.research_features.store import FeatureStore
    official = tmp_path / 'agent.db'
    sqlite3.connect(official).close()
    alias = tmp_path / 'alias.db'
    if alias_kind == 'same':
        alias = official
    elif alias_kind == 'symlink':
        alias.symlink_to(official)
    else:
        os.link(official, alias)
    before = hashlib.sha256(official.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='OFFICIAL'):
        FeatureStore(alias, official_db=official)
    assert hashlib.sha256(official.read_bytes()).hexdigest() == before


def test_rejects_unknown_or_official_signature(tmp_path):
    from firm_lab.research_features.store import FeatureStore
    db = tmp_path / 'other.db'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE paper_accounts(id INTEGER)')
    with pytest.raises(ValueError):
        FeatureStore(db, official_db=tmp_path / 'official' / 'agent.db')
    assert not (tmp_path / 'missing.db').exists()
    with pytest.raises(ValueError):
        FeatureStore(tmp_path / 'missing.db', official_db=tmp_path / 'official' / 'agent.db')
    assert not (tmp_path / 'missing.db').exists()


def test_append_duplicate_revision_and_cutoff(tmp_path):
    from firm_lab.research_features.store import FeatureStore
    from firm_lab.research_features.types import Request
    db, official = research_db(tmp_path)
    with FeatureStore(db, official_db=official) as store:
        assert store.append(result())
        assert not store.append(result())
        later = result(value='2', known_at='2026-10-04T20:00:00+00:00')
        assert store.append(later)
        req = Request('VTI', '2026-09-30', '2026-10-03T20:00:00+00:00')
        assert [r.value for r in store.read(req)] == ['0']
        assert store.read(replace(req, knowledge_cutoff='2026-09-30T20:00:00+00:00')) == ()
        assert [r.value for r in store.read(replace(req, knowledge_cutoff='2026-10-04T20:00:00+00:00'))] == ['2']
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT count(*) FROM research_feature_results').fetchone()[0] == 2
        for action in ['DELETE FROM research_feature_results', "UPDATE research_feature_results SET payload='{}'"]:
            with pytest.raises(sqlite3.IntegrityError, match='APPEND_ONLY'):
                c.execute(action)


@pytest.mark.parametrize('changes', [dict(value='NaN'), dict(value='Infinity'),
    dict(value=1.5), dict(value=None), dict(refs=()), dict(known_at='2026-10-03'),
    dict(known_at='2026-10-02T00:00:00+00:00'), dict(calculation_hash='path'),
    dict(value={'nested': float('nan')}), dict(family='orders')])
def test_invalid_result_rejected(changes):
    with pytest.raises(ValueError):
        result(**changes)


def test_missing_does_not_become_zero():
    missing = result(value=None, known_at=None, availability='UNAVAILABLE',
                     missing_reason='NO_VALIDATED_OHLC', refs=())
    assert missing.value is None
    assert result().value == '0'


def test_content_hash_stable_but_source_revision_changes():
    from firm_lab.research_features.types import content_hash
    assert content_hash({'a': 1, 'b': 2}) == content_hash({'b': 2, 'a': 1})
    assert content_hash(result()) != content_hash(result(value='1'))


def test_receipts_append_and_definitions_immutable(tmp_path):
    from firm_lab.research_features.store import FeatureStore
    from firm_lab.research_features.types import Request
    db, official = research_db(tmp_path)
    with FeatureStore(db, official_db=official) as store:
        run = store.start_run(Request('VTI', '2026-09-30', '2026-10-03T20:00:00+00:00'))
        store.finish_run(run, {'available': 0, 'unavailable': 1})
        with pytest.raises(ValueError):
            store.finish_run(run, {'available': 2})
        with pytest.raises(ValueError):
            store.finish_run('unknown', {})
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT count(*) FROM research_feature_runs').fetchone()[0] == 2
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not names & {'orders', 'fills', 'positions', 'accounts'}


def test_definition_version_cannot_change_and_sources_restricted(tmp_path):
    from firm_lab.research_features.store import FeatureStore
    from firm_lab.research_features.types import SourceRef
    db, official = research_db(tmp_path)
    definition = dict(name='sma20', family='trend', version='v1', required_inputs=['close'],
        optional_inputs=[], unit='USD', value_type='decimal', lookback=20,
        point_in_time='all inputs known', cadence='daily', formula='mean20',
        missing_behavior='null')
    with FeatureStore(db, official_db=official) as store:
        assert store.register(definition)
        assert not store.register(definition)
        with pytest.raises(ValueError, match='VERSION'):
            store.register(dict(definition, formula='mean21'))
        with pytest.raises(ValueError, match='BENCHMARK'):
            store.append(result(refs=(SourceRef('corporate_action_observations', '1',
                         'a' * 64, '2026-10-03T20:00:00+00:00'),)))
