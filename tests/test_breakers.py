from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from risk.breakers import BreakerState, RearmApproval, ValuationSnapshot


NOW = datetime(2026, 9, 28, 14, tzinfo=timezone.utc)
D = Decimal


def snapshot(**changes):
    values = {
        'current_value': D('500'),
        'prior_market_close_value': D('500'),
        'prior_friday_close_value': D('500'),
        'peak_value': D('500'),
        'observed_at': NOW,
    }
    values.update(changes)
    return ValuationSnapshot(**values)


@pytest.mark.parametrize(
    ('changes', 'code'),
    [
        ({'current_value': D('485')}, 'DAILY_LOSS_BREAKER'),
        ({'current_value': D('475')}, 'WEEKLY_LOSS_BREAKER'),
        ({'current_value': D('450')}, 'PEAK_TO_TROUGH_BREAKER'),
        ({'current_value': D('425')}, 'HARD_DRAWDOWN_LOCK'),
    ],
)
def test_automatic_breakers_block_new_entries(changes, code):
    state = BreakerState(global_kill_switch=False)
    result = state.evaluate(snapshot(**changes))
    assert result.block_new_entries is True
    assert code in result.codes


def test_unknown_global_kill_switch_fails_closed_but_exit_stays_allowed():
    state = BreakerState(global_kill_switch=None)
    result = state.evaluate(snapshot())
    assert 'GLOBAL_KILL_SWITCH_UNKNOWN' in result.codes
    assert result.allows_entry is False
    assert result.allows_exit(quantity=D('2'), held_quantity=D('2')) is True
    assert result.allows_exit(quantity=D('3'), held_quantity=D('2')) is False


def test_peak_breaker_rearms_only_after_documented_operator_approval():
    state = BreakerState(global_kill_switch=False)
    state.evaluate(snapshot(current_value=D('450')))
    recovered_market = snapshot(current_value=D('499'))
    assert state.evaluate(recovered_market).block_new_entries is True

    denied = RearmApproval(operator_approved=True, documented_review=False, reviewed_at=NOW)
    assert state.evaluate(recovered_market, rearm=denied).block_new_entries is True

    approved = RearmApproval(operator_approved=True, documented_review=True, reviewed_at=NOW)
    assert state.evaluate(recovered_market, rearm=approved).block_new_entries is False


def test_missing_or_nonfinite_valuation_blocks_entries():
    state = BreakerState(global_kill_switch=False)
    result = state.evaluate(snapshot(current_value=None))
    assert result.codes == ('VALUATION_UNAVAILABLE',)
    assert result.block_new_entries is True

