from datetime import datetime,timedelta,timezone
from decimal import Decimal
import pytest
from test_inbox_lanes import setup_runtime,issue

NOW=datetime(2026,9,28,14,tzinfo=timezone.utc)

@pytest.mark.parametrize('offset,allowed',[(59,True),(62,True),(1199,True),(1200,False),(1260,False)])
def test_schedule_window(tmp_path,offset,allowed):
    from agents.daily_cycle import claim_daily_cycle
    inbox,_=setup_runtime(tmp_path)
    assert bool(claim_daily_cycle(inbox,NOW+timedelta(seconds=offset))) is allowed

def test_stale_worker_fenced_and_lock_retained(tmp_path):
    from agents.cycle_lifecycle import CycleLifecycle
    inbox,_=setup_runtime(tmp_path)
    life=CycleLifecycle(inbox.path)
    claim=life.acquire(NOW,scheduled=True)
    other=CycleLifecycle(inbox.path)
    assert other.acquire(NOW,scheduled=True) is None
    assert other.reconcile(NOW+timedelta(minutes=31))
    with inbox.connect() as db: assert not life.owns(db,claim['cycle_id'])
    assert not life.finish(claim['cycle_id'],'COMPLETED',{},NOW+timedelta(minutes=32))
    life.close()

def test_live_issue_requires_ownership(tmp_path):
    from data.database_role import require_database_role
    inbox,_=setup_runtime(tmp_path)
    require_database_role(inbox.path,'live')
    with pytest.raises(ValueError,match='ownership'): issue(inbox)


def test_cycle_failure_uses_configured_private_dashboard_link(tmp_path):
    from agents.cycle_lifecycle import CycleLifecycle
    inbox, config = setup_runtime(tmp_path)
    life = CycleLifecycle(inbox.path, config.notifications.dashboard_base_url)
    with life.connect() as db:
        life.schema(db)
        life.event(db, 'failed-1', 'FAILED', NOW, {})
    with inbox.connect() as db:
        url = db.execute(
            "SELECT url FROM notification_deliveries WHERE event_id='failed-1' AND channel='pushover'"
        ).fetchone()[0]
    assert url == config.notifications.dashboard_url('activity')


@pytest.mark.parametrize(
    ('moment', 'expected'),
    [
        (datetime(2026, 11, 26, 15, tzinfo=timezone.utc), 'NOT_A_TRADING_DAY'),
        (datetime(2026, 9, 27, 14, tzinfo=timezone.utc), 'NOT_A_TRADING_DAY'),
        (datetime(2026, 3, 9, 13, 59, tzinfo=timezone.utc), 'BEFORE_WINDOW'),
        (datetime(2026, 3, 9, 14, 0, tzinfo=timezone.utc), 'TRADING_WINDOW'),
        (datetime(2026, 3, 9, 14, 19, 59, tzinfo=timezone.utc), 'TRADING_WINDOW'),
        (datetime(2026, 3, 9, 14, 20, tzinfo=timezone.utc), 'MISSED_WINDOW'),
    ],
)
def test_exchange_calendar_classifies_official_window(moment, expected):
    from agents.operator import MarketSchedule
    assert MarketSchedule().classify(moment).value == expected


def test_exchange_calendar_knows_early_close():
    from agents.operator import MarketSchedule
    close = MarketSchedule().session_close(datetime(2026, 11, 27, 15, tzinfo=timezone.utc))
    assert close.astimezone(MarketSchedule().eastern).hour == 13


def test_only_scheduled_worker_can_claim_official_day(tmp_path):
    from agents.cycle_lifecycle import CycleLifecycle
    inbox, _ = setup_runtime(tmp_path)
    life = CycleLifecycle(inbox.path)
    assert life.acquire(NOW, scheduled=False) is None
    with inbox.connect() as db:
        assert db.execute('SELECT count(*) FROM cycle_runs').fetchone()[0] == 0


def test_exactly_one_budgeted_recovery_after_failed_claim(tmp_path):
    from agents.cycle_lifecycle import CycleLifecycle
    inbox, _ = setup_runtime(tmp_path)
    first = CycleLifecycle(inbox.path)
    claim = first.acquire(NOW, scheduled=True)
    assert first.finish(claim['cycle_id'], 'FAILED', {'api_cost_usd': '0.10'}, NOW + timedelta(minutes=1))
    first.close()

    recovery = CycleLifecycle(inbox.path)
    recovered = recovery.acquire(
        NOW + timedelta(minutes=2),
        scheduled=True,
        recovery=True,
        remaining_budget_usd=Decimal('0.30'),
    )
    assert recovered['trigger'] == 'scheduled_recovery'
    assert recovered['recovery_of'] == claim['cycle_id']
    assert recovery.official_context.cycle_id == recovered['cycle_id']
    recovery.finish(recovered['cycle_id'], 'FAILED', {}, NOW + timedelta(minutes=3))
    recovery.close()

    third = CycleLifecycle(inbox.path)
    assert third.acquire(
        NOW + timedelta(minutes=4),
        scheduled=True,
        recovery=True,
        remaining_budget_usd=Decimal('0.30'),
    ) is None


def test_recovery_without_budget_is_not_claimed(tmp_path):
    from agents.cycle_lifecycle import CycleLifecycle
    inbox, _ = setup_runtime(tmp_path)
    first = CycleLifecycle(inbox.path)
    claim = first.acquire(NOW, scheduled=True)
    first.finish(claim['cycle_id'], 'FAILED', {}, NOW + timedelta(minutes=1))
    first.close()
    retry = CycleLifecycle(inbox.path)
    assert retry.acquire(NOW + timedelta(minutes=2), scheduled=True, recovery=True) is None
