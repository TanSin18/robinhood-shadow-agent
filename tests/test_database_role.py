from datetime import datetime,timezone
import pytest
from test_inbox_lanes import setup_runtime

def test_fixture_refuses_database_with_live_evidence(tmp_path):
    from agents.daily_cycle import run_fixture_cycle
    from data.database_role import DatabaseRoleError
    inbox,cfg=setup_runtime(tmp_path)
    inbox.store.append_json('run_states',{'data_mode':'live_readonly'})
    with pytest.raises(DatabaseRoleError): run_fixture_cycle(inbox,cfg,datetime(2026,9,21,14,tzinfo=timezone.utc))
    with inbox.connect() as db: assert db.execute('SELECT COUNT(*) FROM cycle_runs').fetchone()[0]==0

def test_fixture_never_claims_live_day(tmp_path):
    from agents.daily_cycle import run_fixture_cycle
    inbox,cfg=setup_runtime(tmp_path)
    run_fixture_cycle(inbox,cfg,datetime(2026,9,21,14,tzinfo=timezone.utc))
    with inbox.connect() as db: assert db.execute('SELECT COUNT(*) FROM cycle_runs').fetchone()[0]==0

def test_role_survives_aliases_and_mixed_evidence_rejected(tmp_path):
    from data.database_role import require_database_role,DatabaseRoleError
    inbox,cfg=setup_runtime(tmp_path)
    require_database_role(inbox.path,'live')
    alias=tmp_path/'alias.db'; alias.symlink_to(inbox.path)
    with pytest.raises(DatabaseRoleError): require_database_role(alias,'fixture')
    inbox.store.append_json('run_states',{'data_mode':'fixture'})
    with pytest.raises(DatabaseRoleError): require_database_role(inbox.path,'live')


@pytest.mark.parametrize('role', ['fixture', 'whatif', 'replay'])
def test_nonofficial_database_roles_cannot_claim_or_write_official_day(tmp_path, role):
    from agents.cycle_lifecycle import CycleLifecycle
    from data.database_role import DatabaseRoleError, require_database_role
    path = tmp_path / f'{role}.db'
    require_database_role(path, role)

    with pytest.raises(DatabaseRoleError):
        CycleLifecycle(path).acquire(
            datetime(2026, 9, 28, 14, tzinfo=timezone.utc), scheduled=True
        )

    with __import__('sqlite3').connect(path) as db:
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='cycle_runs'"
        ).fetchone()
