"""Registered exit for desk-rule ETF positions."""
import json
from datetime import timedelta
from decimal import Decimal

import pytest

from agents.etf_exit import exit_reason, issue_desk_exits
from broker.models import Quote
from test_inbox_lanes import setup_runtime
from test_phase0_budget import NOW


def test_exit_reason_follows_registered_invalidation():
    assert exit_reason({'above_ma200': False, 'momentum_126d': '0.2'}) == 'CLOSED_AT_OR_BELOW_200_DAY_AVERAGE'
    assert exit_reason({'above_ma200': True, 'momentum_126d': '-0.01'}) == 'MOMENTUM_126D_NOT_POSITIVE'
    assert exit_reason({'above_ma200': True, 'momentum_126d': '0.3'}) is None
    assert exit_reason(None) is None and exit_reason({'above_ma200': True}) is None


def seed(inbox, tracks, qty='0.5'):
    with inbox.connect() as db:
        for track in tracks:
            row = db.execute('SELECT payload FROM paper_accounts WHERE lane=? AND track=?', ('A', track)).fetchone()
            if row is None:
                continue
            state = json.loads(row[0])
            state['settled_cash'] = str(Decimal(state['settled_cash']) - Decimal('250'))
            state['positions']['SOXX'] = {'ticker': 'SOXX', 'asset_class': 'etf', 'quantity': qty, 'average_cost': '500',
                                          'underlying_ticker': None, 'option_type': None, 'strike': None, 'expiry': None, 'multiplier': 1}
            db.execute('UPDATE paper_accounts SET payload=? WHERE lane=? AND track=?', (json.dumps(state), 'A', track))


def quote(bid='520', ask='520.5', at=NOW):
    return Quote(ticker='SOXX', bid=Decimal(bid), ask=Decimal(ask), timestamp=at)


def run(inbox, config, features, q):
    return issue_desk_exits(inbox, config, strategy_assessment={'features': {'SOXX': features}},
                            snapshot={'quotes': {'SOXX': q}, 'vols': {'SOXX': (Decimal('0.3'), NOW)}},
                            now=NOW, cycle_id='cyc-1')


def test_exit_sells_immediate_arms_and_cards_approval_arm(tmp_path):
    inbox, config = setup_runtime(tmp_path)
    seed(inbox, ('agent_alone', 'with_approvals', 'deterministic_no_ai'))
    out = run(inbox, config, {'above_ma200': False, 'momentum_126d': '0.1'}, quote())
    by_arm = {r['arm']: r for r in out}
    assert by_arm['agent_alone']['status'] == 'filled' and by_arm['agent_alone']['side'] == 'sell'
    assert by_arm['with_approvals']['status'] == 'PENDING'
    assert 'SOXX' not in inbox.state('A', 'agent_alone')['positions']
    assert 'SOXX' in inbox.state('A', 'with_approvals')['positions']      # waits for your YES
    card = next(c for c in inbox.cards() if c['id'] == 'cyc-1-A-exit-SOXX-with_approvals')
    assert card['proposal']['side'] == 'sell' and card['origin'] == 'registered_exit'
    inbox.decide(card['id'], 'YES', NOW + timedelta(minutes=1))
    assert 'SOXX' not in inbox.state('A', 'with_approvals')['positions']
    # idempotent: a second pass issues nothing new
    assert all(r.get('status') != 'PENDING' for r in run(inbox, config, {'above_ma200': False, 'momentum_126d': '0.1'}, quote()))


def test_no_exit_when_condition_not_met_or_quote_stale(tmp_path):
    inbox, config = setup_runtime(tmp_path)
    seed(inbox, ('agent_alone',))
    assert run(inbox, config, {'above_ma200': True, 'momentum_126d': '0.4'}, quote())[0]['reason'] == 'EXIT_CONDITION_NOT_MET'
    stale = run(inbox, config, {'above_ma200': False, 'momentum_126d': '0.4'}, quote(at=NOW - timedelta(minutes=5)))
    assert stale[0]['status'] == 'EXIT_BLOCKED' and stale[0]['reason'] == 'FRESH_QUOTE_REQUIRED'
    assert 'SOXX' in inbox.state('A', 'agent_alone')['positions']


def test_cycle_exit_hook_is_inert_until_v151_is_signed(monkeypatch):
    from agents.daily_cycle import desk_policy_exits
    from agents import v15_activation
    assert v15_activation.exit_rule_active(now=NOW) is False  # before its effective time
    assert desk_policy_exits(object(), None, {}, {}, NOW, 'c', enabled=True) == []


def test_etf_holding_does_not_wake_ai_under_v15(tmp_path, monkeypatch):
    """An ETF position bought by the desk rule must not trigger a daily AI review."""
    from test_desk_cycle_integration import run as desk_run
    inbox, first = desk_run(tmp_path / 'one', monkeypatch, enabled=True)
    assert first['decision']['type'] == 'DESK_ENTRY'
    import agents.daily_cycle as dc
    from agents.cycle_lifecycle import CycleLifecycle
    from agents.daily_cycle import FixtureReader, run_cycle
    from test_desk_cycle_integration import SIGNAL
    config = inbox.config

    class NoModel:
        def run(self, *a, **k):
            raise AssertionError('AI must not run for an ETF-only holding')
    later = NOW + timedelta(days=1)
    lifecycle = CycleLifecycle(inbox.path)
    claim = lifecycle.acquire(later, scheduled=True)
    try:
        monkeypatch.setattr('agents.daily_cycle.evaluate_daily_signals', lambda *a: {'signals': [], 'strategies': {}, 'features': {}})
        result = run_cycle(inbox, config, NoModel(), later, data_mode='live_readonly', reader=FixtureReader(config, later),
                           clock=lambda: later, lifecycle=lifecycle, cycle_id=claim['cycle_id'], desk_policy_enabled=True)
    finally:
        lifecycle.close()
    assert result['ai_gate']['invoke'] is False


def test_exit_rule_activates_only_with_signed_pinned_file_after_effective_time(tmp_path):
    import shutil
    from datetime import datetime, timezone
    from pathlib import Path
    from agents import v15_activation as act
    repo = Path(act.__file__).resolve().parents[1]
    for name in ('preregistration.yaml', act.AMENDMENT_NAME, act.V151_AMENDMENT_NAME):
        shutil.copy(repo / name, tmp_path / name)
    after = datetime(2026, 10, 1, 13, 31, tzinfo=timezone.utc)
    assert act.exit_rule_active(tmp_path, after) is True
    assert act.exit_rule_active(tmp_path, datetime(2026, 10, 1, 13, 29, tzinfo=timezone.utc)) is False
    (tmp_path / act.V151_AMENDMENT_NAME).write_text('tampered')
    assert act.exit_rule_active(tmp_path, after) is False
