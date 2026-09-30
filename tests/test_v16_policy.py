"""v1.6 amendment: capital rebase, options pause, protective exit."""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from agents import v16_policy
from agents.v16_policy import (ProtectiveClaim, checked_today, in_window, protective_check, protective_reason,
                               rebase_lane_a, record_protective_failure, v16_active)
from test_etf_exit import seed
from test_inbox_lanes import setup_runtime
from test_phase0_budget import NOW

ROOT = Path(__file__).resolve().parents[1]
BEFORE = datetime(2026, 10, 1, 13, 29, tzinfo=timezone.utc)
AFTER = datetime(2026, 10, 1, 13, 31, tzinfo=timezone.utc)


def test_activation_is_byte_pinned_and_time_gated():
    assert v16_active(ROOT, BEFORE) is False
    assert v16_active(ROOT, AFTER) is True
    assert v16_active(ROOT, AFTER, approved_sha256='0' * 64) is False
    assert v16_policy.lane_a_capital(ROOT) == Decimal('25000.00')
    assert v16_policy.hard_stop_fraction(ROOT) == Decimal('0.08')


def test_rebase_archives_build_phase_and_is_idempotent(tmp_path):
    inbox, config = setup_runtime(tmp_path)
    seed(inbox, ('agent_alone', 'with_approvals', 'deterministic_no_ai'))
    with inbox.connect() as db:
        db.execute('INSERT INTO approval_inbox VALUES (?,?,?,?,?)', ('old-card', 'PENDING', NOW.isoformat(), NOW.isoformat(),
                   json.dumps({'id': 'old-card', 'lane': 'A', 'status': 'PENDING', 'proposal': {'ticker': 'SOXX'}})))
    first = rebase_lane_a(inbox, Decimal('25000'), AFTER)
    assert first['status'] == 'REBASED' and first['expired_cards'] == ['old-card']
    for arm in ('agent_alone', 'with_approvals', 'deterministic_no_ai'):
        state = inbox.state('A', arm)
        assert state['positions'] == {} and state['settled_cash'] == '25000' and state['start'] == '25000'
    assert inbox.state('B', 'agent_alone')['settled_cash'] == '500.00' or Decimal(inbox.state('B', 'agent_alone')['settled_cash']) == 500
    with inbox.connect() as db:
        archived = json.loads(db.execute('SELECT payload_json FROM capital_rebases').fetchone()[0])['archived_build_phase_state']
    assert 'SOXX' in archived['agent_alone']['positions']
    assert rebase_lane_a(inbox, Decimal('25000'), AFTER + timedelta(days=1))['status'] == 'ALREADY_REBASED'


def test_option_buys_paused_only_when_active(tmp_path, monkeypatch):
    from test_inbox_lanes import make_proposal
    from broker.models import Quote
    inbox, _ = setup_runtime(tmp_path)
    monkeypatch.setattr(v16_policy, 'v16_active', lambda root=None, now=None: True)
    proposal = make_proposal(quantity=Decimal('1')).model_copy(update={'asset_class': 'option'})
    out = inbox.issue(proposal, Quote(ticker=proposal.ticker, bid=Decimal(1), ask=Decimal('1.1'), timestamp=NOW),
                      Decimal('.2'), NOW, NOW)
    assert out == {'status': 'RISK_BLOCKED', 'reasons': ['OPTIONS_LANE_PAUSED_V16']}


def test_protective_reasons():
    pos = {'average_cost': '100'}
    assert protective_reason(pos, Decimal('93'), {'ma200': Decimal('80')}, True, Decimal('.08')) is None
    assert protective_reason(pos, Decimal('92'), {}, True, Decimal('.08')) == 'PROTECTIVE_STOP_BELOW_AVERAGE_COST'
    assert protective_reason(pos, Decimal('99'), {'ma200': Decimal('99.5')}, True, Decimal('.08')) == 'LIVE_PRICE_AT_OR_BELOW_200_DAY_AVERAGE'
    assert protective_reason(pos, Decimal('99'), {'close_126_sessions_ago': Decimal('100')}, True, Decimal('.08')) == 'LIVE_MOMENTUM_126D_NOT_POSITIVE'
    assert protective_reason(pos, Decimal('99'), {'close_126_sessions_ago': Decimal('100')}, False, Decimal('.08')) is None


def _gateway(bid):
    def call(tool, args):
        if tool == 'get_equity_quotes':
            return {'tool': tool, 'data': {'results': [{'quote': {'symbol': 'SOXX', 'bid_price': bid, 'ask_price': str(Decimal(bid) + Decimal('.5')),
                                                                   'updated_at': NOW.isoformat(), 'state': 'active'}}]}}
        bars = [{'begins_at': (NOW - timedelta(days=300 - i)).isoformat(), 'close_price': '400'} for i in range(260)]
        return {'tool': tool, 'data': {'results': [{'symbol': 'SOXX', 'bars': bars}]}}
    return call


def test_protective_check_sells_once_per_session(tmp_path):
    inbox, config = setup_runtime(tmp_path)
    seed(inbox, ('agent_alone', 'with_approvals', 'deterministic_no_ai'))       # average cost 500
    out = protective_check(inbox, config, _gateway('450'), NOW, root=ROOT)          # 10% below cost
    by_arm = {r['arm']: r for r in out['results']}
    assert by_arm['agent_alone']['status'] == 'filled' and by_arm['deterministic_no_ai']['status'] == 'filled'
    assert by_arm['with_approvals']['status'] == 'PENDING'
    assert by_arm['agent_alone']['exit_reason'] == 'PROTECTIVE_STOP_BELOW_AVERAGE_COST'
    assert 'SOXX' not in inbox.state('A', 'agent_alone')['positions']
    assert checked_today(inbox, NOW)
    assert protective_check(inbox, config, _gateway('450'), NOW, root=ROOT) == {'status': 'ALREADY_CHECKED_TODAY'}
    with inbox.connect() as db:
        kinds = [json.loads(r[0]).get('kind') for r in db.execute('SELECT payload_json FROM daily_values')]
    assert 'protective_check' in kinds


def test_protective_check_holds_without_trigger_and_records(tmp_path):
    inbox, config = setup_runtime(tmp_path)
    seed(inbox, ('agent_alone',))
    out = protective_check(inbox, config, _gateway('520'), NOW, root=ROOT)
    assert all(r['status'] == 'HOLD' for r in out['results'])
    assert 'SOXX' in inbox.state('A', 'agent_alone')['positions']


def test_failed_attempt_releases_claim(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    claim = ProtectiveClaim(inbox.path)
    with inbox.connect() as db:
        claim.acquire(db, NOW)
    assert checked_today(inbox, NOW)
    record_protective_failure(inbox, NOW, RuntimeError('x'))
    assert not checked_today(inbox, NOW)


def test_window():
    assert in_window(datetime(2026, 10, 1, 19, 52, tzinfo=timezone.utc))
    assert not in_window(datetime(2026, 10, 1, 19, 45, tzinfo=timezone.utc))
    assert not in_window(datetime(2026, 10, 1, 19, 58, tzinfo=timezone.utc))
    assert not in_window(datetime(2026, 10, 3, 19, 52, tzinfo=timezone.utc))   # Saturday
