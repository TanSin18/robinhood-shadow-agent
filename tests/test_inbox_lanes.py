from datetime import timedelta
from decimal import Decimal as D

import pytest

from test_risk_engine import NOW, make_proposal
from broker.models import Quote
from config.loader import load_config


def setup_runtime(tmp_path, expiry=30):
    from agents.inbox import PaperInbox
    config = load_config('config/settings.yaml').model_copy(update={'approval_expiry_minutes':expiry})
    config = config.model_copy(update={'risk': config.risk.model_copy(update={'agentic_account_id':'agentic-1', 'options_unlocked':True})})
    return PaperInbox(tmp_path/'runtime.db', config), config


def issue(inbox, **changes):
    proposal = make_proposal(quantity=D('.49'), **changes)
    return inbox.issue(proposal, Quote(ticker='VTI', bid=D(100), ask=D('100.20'), timestamp=NOW), D('.20'), NOW, NOW)


def test_pending_survives_restart_and_only_yes_fills_approval_track(tmp_path):
    from agents.inbox import PaperInbox
    inbox, config = setup_runtime(tmp_path)
    card = issue(inbox)
    assert card['status'] == 'PENDING'
    assert inbox.state('A','agent_alone')['settled_cash'] == '450.9020'
    assert D(inbox.state('A','with_approvals')['settled_cash']) == 500
    restored = PaperInbox(tmp_path/'runtime.db', config)
    assert restored.decide(card['id'], 'YES', NOW+timedelta(minutes=1))['status'] == 'YES'
    assert D(restored.state('A','with_approvals')['settled_cash']) == D('450.902')
    with pytest.raises(ValueError, match='resolved'):
        restored.decide(card['id'], 'YES', NOW+timedelta(minutes=2))


def test_config_expiry_and_no_never_fill(tmp_path):
    inbox, _ = setup_runtime(tmp_path, expiry=7)
    card = issue(inbox)
    assert inbox.decide(card['id'],'YES', NOW+timedelta(minutes=7))['status'] == 'EXPIRED'
    assert D(inbox.state('A','with_approvals')['settled_cash']) == 500


def test_lane_cash_is_independent_and_options_require_defined_loss(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    issue(inbox)
    assert D(inbox.state('B','agent_alone')['settled_cash']) == 500
    bad = make_proposal(proposal_id='option-bad',client_order_id='option-bad',ticker='AAPL-C',asset_class='option', underlying_ticker='AAPL',multiplier=100,quantity=D(1),limit_price=D('.20'),option_strategy='short_call',max_loss_usd=D(20))
    result = inbox.issue(bad,Quote(ticker='AAPL-C',bid=D('.199'),ask=D('.20'),timestamp=NOW),D('.20'),NOW,NOW)
    assert result['status'] == 'RISK_BLOCKED'
    assert D(inbox.state('B','agent_alone')['settled_cash']) == 500


def test_invalid_sell_is_blocked_before_broker_and_duplicate_issuance_is_idempotent(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    result = issue(inbox, side='sell',is_closing=True)
    assert result['status'] == 'RISK_BLOCKED'
    assert 'insufficient_position' in result['reasons']
    assert D(inbox.state('A','agent_alone')['settled_cash']) == 500


def test_inbox_rejects_unknown_decision(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    card = issue(inbox)
    with pytest.raises(ValueError):
        inbox.decide(card['id'], 'AUTO', NOW)


def test_official_approval_card_expires_at_exchange_close(tmp_path):
    from agents.cycle_lifecycle import CycleLifecycle
    from data.database_role import require_database_role
    from datetime import datetime, timezone

    inbox, _ = setup_runtime(tmp_path)
    monday = datetime(2026, 9, 28, 14, tzinfo=timezone.utc)
    require_database_role(inbox.path, 'live')
    lifecycle = CycleLifecycle(inbox.path)
    claim = lifecycle.acquire(monday, scheduled=True)
    try:
        proposal = make_proposal(quantity=D('.49'))
        card = inbox.issue(
            proposal,
            Quote(ticker='VTI', bid=D(100), ask=D('100.20'), timestamp=monday),
            D('.20'), monday, monday,
            cycle_id=claim['cycle_id'], lifecycle=lifecycle,
        )
    finally:
        lifecycle.close()
    assert card['expires'] == '2026-09-28T20:00:00+00:00'


def test_approval_card_and_alert_use_private_phone_dashboard_url(tmp_path):
    inbox, config = setup_runtime(tmp_path)

    card = issue(inbox)

    assert card['trace_url'] == config.notifications.dashboard_url(
        'trace/' + card['id'], fragment=False
    )
    with inbox.connect() as db:
        url = db.execute(
            "SELECT url FROM notification_deliveries WHERE event_id=? AND channel='pushover'",
            ('card-' + card['id'],),
        ).fetchone()[0]
    assert url == config.notifications.dashboard_url('decisions')
