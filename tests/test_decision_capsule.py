import json

import pytest

from test_desk_cycle_integration import run


def test_cycle_records_capsule_that_round_trips_and_replays(tmp_path, monkeypatch):
    from agents import decision_capsule
    inbox, result = run(tmp_path, monkeypatch, enabled=True)
    assert result['capsule_status'] == 'RECORDED'
    with inbox.connect() as db:
        capsule = decision_capsule.load(db, result['capsule_hash'])
    assert decision_capsule.digest(capsule) == result['capsule_hash']
    assert capsule['cycle_id'] == result['cycle_id']
    assert capsule['outcome']['decision']['type'] == 'DESK_ENTRY'
    assert capsule['inputs']['quotes']['VTI']['ask']
    assert capsule['inputs']['paper_accounts']['A:agent_alone']['settled_cash'] in {'500', '500.0', '500.00'}
    text = json.dumps(capsule)
    for forbidden in ('agentic-1', 'account_last4', 'account_number'):
        assert forbidden not in text


def test_replay_recomputes_identical_strategy_from_capsule_closes(tmp_path, monkeypatch):
    from agents import decision_capsule
    import research.strategy_signals as real
    inbox, result = run(tmp_path, monkeypatch, enabled=False)
    with inbox.connect() as db:
        capsule = decision_capsule.load(db, result['capsule_hash'])
    # The integration harness stubs signals; restore the real rules and compare with
    # a capsule whose recorded assessment came from the real rules too.
    from datetime import datetime
    from zoneinfo import ZoneInfo
    day = datetime.fromisoformat(capsule['observed_at']).astimezone(ZoneInfo('America/New_York')).date()
    closes = capsule['inputs']['session_closes']
    capsule['strategy_assessment'] = json.loads(json.dumps(
        real.evaluate_daily_signals(closes, real.ETF_UNIVERSE & set(closes), day), default=str))
    assert decision_capsule.replay_strategy(capsule)['identical']


def test_tampered_capsule_is_rejected(tmp_path, monkeypatch):
    from agents import decision_capsule
    inbox, result = run(tmp_path, monkeypatch, enabled=False)
    with inbox.connect() as db:
        db.execute('UPDATE decision_capsules SET payload=replace(payload,\'VTI\',\'XYZ\')')
        with pytest.raises(ValueError, match='HASH_MISMATCH'):
            decision_capsule.load(db, result['capsule_hash'])


def test_capsule_failure_never_fails_the_cycle(tmp_path, monkeypatch):
    from agents import decision_capsule
    monkeypatch.setattr(decision_capsule, 'write', lambda *a, **k: (_ for _ in ()).throw(OSError('disk')))
    _, result = run(tmp_path, monkeypatch, enabled=True)
    assert result['status'] == 'COMPLETED'
    assert result['capsule_status'] == 'UNAVAILABLE' and result['capsule_error_type'] == 'OSError'
    assert result['decision']['type'] == 'DESK_ENTRY'


def test_privacy_guard_refuses_identifier_keys(tmp_path):
    import sqlite3
    from agents import decision_capsule
    db = sqlite3.connect(tmp_path / 'c.db')
    with pytest.raises(ValueError, match='PRIVACY'):
        decision_capsule.write(db, {'cycle_id': 'x', 'observed_at': None, 'nested': [{'account_number': '1'}]})
