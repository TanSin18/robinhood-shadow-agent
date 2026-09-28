from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from agents.budget import AIInvocationGate, BudgetAllocator, BudgetUnavailable


D = Decimal
NOW = datetime(2026, 9, 28, 14, tzinfo=timezone.utc)


def test_ai_gate_is_zero_cost_without_qualified_stock_or_qualitative_holding():
    gate = AIInvocationGate().evaluate(
        discovery=[{'candidate_id': 'vti', 'asset_class': 'etf', 'qualified': True}],
        holdings=[],
    )
    assert gate.invoke is False
    assert gate.reserved_cost_usd == D('0')


def test_ai_gate_invokes_only_for_qualified_stock_or_holding_review():
    stock = AIInvocationGate().evaluate(
        discovery=[{'candidate_id': 'aapl', 'asset_class': 'stock', 'qualified': True}],
        holdings=[],
    )
    holding = AIInvocationGate().evaluate(
        discovery=[],
        holdings=[{'position_id': 'p1', 'qualitative_review_required': True}],
    )
    assert stock.invoke is True and stock.reason == 'QUALIFIED_AI_ELIGIBLE_CANDIDATE'
    assert holding.invoke is True and holding.reason == 'HOLDING_QUALITATIVE_REVIEW_REQUIRED'


def test_budget_enforces_daily_monthly_and_annual_without_cross_lane_shift(tmp_path):
    allocator = BudgetAllocator(tmp_path / 'budget.db')
    reservation = allocator.reserve(NOW, lane='A', stage='research', amount=D('0.03'))
    allocator.settle(reservation, actual=D('0.02'))
    assert allocator.available(NOW, lane='A') == D('1.63')
    assert allocator.available(NOW, lane='B') == D('1.65')

    with pytest.raises(BudgetUnavailable, match='official daily'):
        allocator.reserve(NOW, lane='A', stage='test', amount=D('0.39'))


def test_monthly_carry_is_capped_at_five_and_credit_at_six_sixty_five(tmp_path):
    allocator = BudgetAllocator(tmp_path / 'budget.db')
    for month in range(1, 6):
        moment = datetime(2026, month, 2, 15, tzinfo=timezone.utc)
        allocator.available(moment, lane='A')
    june = datetime(2026, 6, 2, 15, tzinfo=timezone.utc)
    assert allocator.available(june, lane='A') == D('6.65')


def test_budget_uses_registered_degradation_order_and_never_borrows_future_month(tmp_path):
    allocator = BudgetAllocator(tmp_path / 'budget.db')
    assert allocator.degradation_order == (
        'drop_news_sources_after_second_corroboration',
        'drop_research_candidates_ranked_6_through_8',
        'drop_research_candidate_ranked_5',
        'drop_optional_cross_candidate_narrative_and_optional_insider_enrichment',
        'drop_all_new_entry_research_and_run_holdings_plus_deterministic_baselines_only',
    )
    for day in range(1, 5):
        allocator.reserve(
            datetime(2026, 9, day, 14, tzinfo=timezone.utc),
            lane='A', stage='used', amount=D('0.40'),
        )
    with pytest.raises(BudgetUnavailable, match='monthly AI allowance'):
        allocator.reserve(
            datetime(2026, 9, 5, 14, tzinfo=timezone.utc),
            lane='A', stage='no_future_borrow', amount=D('0.06'),
        )


def test_registered_stage_reservations_fit_forty_cent_ceiling(tmp_path):
    allocator = BudgetAllocator(tmp_path / 'budget.db')
    assert allocator.stage_reservations == {
        'research': D('0.03'),
        'portfolio': D('0.05'),
        'critic': D('0.11'),
    }
    assert sum(allocator.stage_reservations.values(), D('0')) == D('0.19')
    assert allocator.run_ceiling == D('0.40')


def test_official_etf_only_cycle_is_code_only_and_records_zero_ai_cost(tmp_path):
    from agents.cycle_lifecycle import CycleLifecycle
    from agents.daily_cycle import FixtureReader, run_cycle
    from data.database_role import require_database_role
    from test_inbox_lanes import setup_runtime

    inbox, config = setup_runtime(tmp_path)
    require_database_role(inbox.path, 'live')
    lifecycle = CycleLifecycle(inbox.path)
    claim = lifecycle.acquire(NOW, scheduled=True)

    class NoModelBridge:
        isolation_evidence = []
        def run(self, *args, **kwargs):
            raise AssertionError('ETF-only official cycle must not call a model')

    try:
        result = run_cycle(
            inbox, config, NoModelBridge(), NOW,
            data_mode='live_readonly', reader=FixtureReader(config, NOW),
            cycle_id=claim['cycle_id'], lifecycle=lifecycle, clock=lambda: NOW,
        )
    finally:
        lifecycle.close()

    assert result['status'] == 'COMPLETED'
    assert result['decision']['type'] == 'HOLD_CASH'
    assert result['agents'] == []
    assert result['api_cost_estimate_usd'] == '0'
