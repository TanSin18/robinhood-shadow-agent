from datetime import datetime, timezone
import sqlite3

import pytest


def test_existing_user_pause_cannot_hide_new_incident(tmp_path):
    from test_inbox_lanes import setup_runtime
    from agents.dashboard import set_paused
    from agents.safety_events import record_incident
    inbox, _ = setup_runtime(tmp_path)
    set_paused(inbox, 'pause')
    marker = (tmp_path / 'STOP_TRADING').read_bytes()
    record_incident(inbox.path, 'UNEXPECTED_CAPABILITY', cycle_id=None, now=datetime.now(timezone.utc))
    assert (tmp_path / 'STOP_TRADING').read_bytes() == marker
    with pytest.raises(ValueError, match='incident'):
        set_paused(inbox, 'resume')
    with inbox.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM notification_outbox').fetchone()[0] == 1
        deliveries = db.execute(
            'SELECT channel,priority FROM notification_deliveries ORDER BY channel'
        ).fetchall()
        assert [tuple(row) for row in deliveries] == [('macos', 1), ('pushover', 1)]


def test_incident_is_still_active_if_stop_file_is_removed(tmp_path):
    from agents.safety_events import record_incident, safety_stopped
    path = tmp_path / 'incident.db'
    record_incident(path, 'UNEXPECTED_CAPABILITY', cycle_id=None, now=datetime.now(timezone.utc))
    (tmp_path / 'STOP_TRADING').unlink()
    assert safety_stopped(path)


def test_incident_preserves_symlink_target(tmp_path):
    from agents.safety_events import record_incident, safety_stopped
    target = tmp_path / 'external'
    target.write_text('keep')
    (tmp_path / 'STOP_TRADING').symlink_to(target)
    record_incident(tmp_path / 'incident.db', 'UNEXPECTED_CAPABILITY', cycle_id=None, now=datetime.now(timezone.utc))
    assert target.read_text() == 'keep'
    assert safety_stopped(tmp_path / 'incident.db')
def test_risk_context_honors_incident_without_marker(tmp_path):
    from test_inbox_lanes import setup_runtime,issue
    from agents.safety_events import record_incident
    from datetime import datetime,timezone
    inbox,_=setup_runtime(tmp_path)
    record_incident(inbox.path,'UNEXPECTED_CAPABILITY',now=datetime.now(timezone.utc))
    (tmp_path/'STOP_TRADING').unlink()
    assert issue(inbox)['status']=='RISK_BLOCKED'

def test_incident_database_latches_even_if_marker_cannot_be_created(tmp_path,monkeypatch):
    from pathlib import Path
    from agents.safety_events import record_incident,incident_active
    original=Path.open
    def guarded(path,*args,**kwargs):
        if path.name=='STOP_TRADING': raise PermissionError('test')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',guarded)
    with pytest.raises(PermissionError): record_incident(tmp_path/'incident.db','UNEXPECTED_CAPABILITY',now=datetime.now(timezone.utc))
    assert incident_active(tmp_path/'incident.db')


def test_safety_alert_uses_configured_private_dashboard_link(tmp_path):
    from test_inbox_lanes import setup_runtime
    from agents.safety_events import record_incident
    inbox, config = setup_runtime(tmp_path)
    record_incident(
        inbox.path,
        'UNEXPECTED_CAPABILITY',
        now=datetime.now(timezone.utc),
        dashboard_base_url=config.notifications.dashboard_base_url,
    )
    with inbox.connect() as db:
        url = db.execute(
            "SELECT url FROM notification_deliveries WHERE channel='pushover'"
        ).fetchone()[0]
    assert url == config.notifications.dashboard_url('activity')
