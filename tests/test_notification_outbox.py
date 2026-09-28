from datetime import timedelta
from test_inbox_lanes import setup_runtime,issue
from test_risk_engine import NOW

def test_issue_deduplicates_notification_and_delivery(tmp_path):
    from agents.notification_outbox import deliver_pending
    inbox,_=setup_runtime(tmp_path); issue(inbox); issue(inbox)
    calls=[]
    class Notifier:
        def notify(self,title,body): calls.append((title,body))
    deliver_pending(inbox.path,Notifier(),NOW)
    deliver_pending(inbox.path,Notifier(),NOW)
    assert len(calls)==1
    assert inbox.config.risk.agentic_account_id not in str(calls)
    assert len(inbox.state('A','agent_alone')['fills'])==1

def test_failed_notification_does_not_rollback_fill(tmp_path):
    from agents.notification_outbox import deliver_pending
    inbox,_=setup_runtime(tmp_path); issue(inbox)
    class Bad:
        def notify(self,*args): raise OSError('sensitive details')
    result=deliver_pending(inbox.path,Bad(),NOW)
    assert result['failed']==1
    assert len(inbox.cards())==1 and len(inbox.state('A','agent_alone')['fills'])==1
    assert deliver_pending(inbox.path,Bad(),NOW)['failed']==0
    with inbox.connect() as db:
        row=db.execute('SELECT attempts,error_class FROM notification_outbox').fetchone()
        assert tuple(row)==(1,'OSError')

def test_recorded_view_does_not_extend_expiry(tmp_path):
    from agents.notification_outbox import record_views
    inbox,_=setup_runtime(tmp_path); card=issue(inbox)
    record_views(inbox.path,[card['id']],NOW)
    record_views(inbox.path,[card['id']],NOW+timedelta(minutes=2))
    assert inbox.cards()[0]['expires']==card['expires']
    with inbox.connect() as db: assert db.execute('SELECT COUNT(*) FROM card_views').fetchone()[0]==1


def test_notification_channels_retry_independently_without_repeating_success(tmp_path):
    from agents.notification_outbox import deliver_pending, enqueue

    inbox, _ = setup_runtime(tmp_path)
    with inbox.connect() as db:
        enqueue(
            db, 'alert-1', 'Review failed', 'Open the dashboard.', NOW,
            priority=1, url='http://127.0.0.1:8765/#activity',
        )

    macos_calls = []
    pushover_calls = []

    class MacOS:
        def notify(self, title, body):
            macos_calls.append((title, body))

    class Pushover:
        def notify(self, title, body, *, priority, url=None):
            pushover_calls.append((title, body, priority, url))
            if len(pushover_calls) == 1:
                raise OSError('secret details must not be stored')
            return {'request_id': 'request-2', 'receipt': None}

    first = deliver_pending(inbox.path, {'macos': MacOS(), 'pushover': Pushover()}, NOW)
    second = deliver_pending(
        inbox.path, {'macos': MacOS(), 'pushover': Pushover()}, NOW + timedelta(seconds=61)
    )

    assert first['channels']['macos']['delivered'] == 1
    assert first['channels']['pushover']['failed'] == 1
    assert second['channels']['macos']['delivered'] == 0
    assert second['channels']['pushover']['delivered'] == 1
    assert macos_calls == [('Review failed', 'Open the dashboard.')]
    assert pushover_calls[-1] == (
        'Review failed', 'Open the dashboard.', 1,
        'http://127.0.0.1:8765/#activity',
    )
    with inbox.connect() as db:
        rows = db.execute(
            'SELECT channel,status,attempts,error_class,request_id '
            'FROM notification_deliveries WHERE event_id=? ORDER BY channel', ('alert-1',)
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        ('macos', 'DELIVERED', 1, None, None),
        ('pushover', 'DELIVERED', 2, None, 'request-2'),
    ]


def test_unconfigured_pushover_is_visible_but_does_not_block_macos(tmp_path):
    from agents.notification_outbox import deliver_pending, enqueue

    inbox, _ = setup_runtime(tmp_path)
    with inbox.connect() as db:
        enqueue(db, 'alert-2', 'Safety stop', 'Review required.', NOW, priority=1)

    class MacOS:
        def notify(self, *_args):
            return None

    result = deliver_pending(inbox.path, {'macos': MacOS()}, NOW)
    assert result['channels']['macos']['delivered'] == 1
    assert result['channels']['pushover']['disabled'] == 1
    with inbox.connect() as db:
        status = db.execute(
            "SELECT status FROM notification_deliveries WHERE event_id='alert-2' AND channel='pushover'"
        ).fetchone()[0]
    assert status == 'NOT_CONFIGURED'


def test_only_failures_safety_and_required_actions_page(tmp_path):
    from agents.cycle_lifecycle import CycleLifecycle

    inbox, _ = setup_runtime(tmp_path)
    life = CycleLifecycle(inbox.path)
    with life.connect() as db:
        life.schema(db)
        for status in ('COMPLETED', 'HOLD_CASH', 'HEARTBEAT', 'WHAT_IF_COMPLETED'):
            life.event(db, 'routine-' + status, status, NOW, {})
        for status in ('FAILED', 'FAILED_STALLED', 'MISSED_WINDOW', 'AUTH_LOST', 'REQUIRED_ACTION'):
            life.event(db, 'page-' + status, status, NOW, {})
    with inbox.connect() as db:
        events = {row[0] for row in db.execute('SELECT event_id FROM notification_outbox')}
    assert events == {
        'page-FAILED', 'page-FAILED_STALLED', 'page-MISSED_WINDOW',
        'page-AUTH_LOST', 'page-REQUIRED_ACTION',
    }


def test_weekly_summary_is_enqueued_once_for_pushover(tmp_path):
    from datetime import datetime, timezone
    from eval.weekly import report_if_due

    inbox, _ = setup_runtime(tmp_path)
    now = datetime(2026, 10, 2, 20, 31, tzinfo=timezone.utc)
    assert report_if_due(inbox, now, tmp_path / 'reports') is not None
    assert report_if_due(inbox, now, tmp_path / 'reports') is None
    with inbox.connect() as db:
        rows = db.execute(
            "SELECT event_id,channel,priority FROM notification_deliveries "
            "WHERE event_id LIKE 'weekly-summary-%' ORDER BY channel"
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        ('weekly-summary-2026-10-02', 'macos', -1),
        ('weekly-summary-2026-10-02', 'pushover', -1),
    ]
