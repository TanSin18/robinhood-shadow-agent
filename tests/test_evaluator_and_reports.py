from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from data.store import SQLiteStore
from eval.evaluator import DecisionOutcome, Evaluator, OutcomeRecorder, TradingCosts
from eval.reports import WeeklyReport
from eval.scoreboard import ScoreboardInputs, build_scoreboard


def outcomes() -> list[DecisionOutcome]:
    return [
        DecisionOutcome(
            decision_id="d-1",
            confidence=Decimal("0.70"),
            hit=True,
            net_pnl=Decimal("120"),
            evidence_types=("fundamental", "news"),
            strategy="earnings_quality",
            human_decision="YES",
        ),
        DecisionOutcome(
            decision_id="d-2",
            confidence=Decimal("0.70"),
            hit=False,
            net_pnl=Decimal("-40"),
            evidence_types=("technical",),
            strategy="momentum",
            human_decision="NO",
        ),
    ]


def test_calibration_uses_stated_confidence_and_literal_hit_rate() -> None:
    bucket = Evaluator().calibration(outcomes())[Decimal("0.70")]

    assert bucket.count == 2
    assert bucket.hit_rate == Decimal("0.5")


def test_attribution_splits_pnl_equally_across_evidence_types() -> None:
    attribution = Evaluator().attribution(outcomes())

    assert attribution.by_evidence["fundamental"] == Decimal("60")
    assert attribution.by_evidence["news"] == Decimal("60")
    assert attribution.by_evidence["technical"] == Decimal("-40")
    assert attribution.by_strategy["earnings_quality"] == Decimal("120")


def test_human_approval_value_compares_yes_only_with_approve_everything() -> None:
    result = Evaluator().approval_value(outcomes())

    assert result.agent_alone_pnl == Decimal("80")
    assert result.approved_only_pnl == Decimal("120")
    assert result.value_added == Decimal("40")


def test_taxes_use_configured_short_and_long_term_rates() -> None:
    costs = TradingCosts(
        api=Decimal("20"),
        spread=Decimal("10"),
        fees=Decimal("5"),
        short_term_gain=Decimal("200"),
        long_term_gain=Decimal("100"),
        short_term_tax_rate=Decimal("0.35"),
        long_term_tax_rate=Decimal("0.15"),
    )

    assert costs.estimated_tax == Decimal("85")
    assert costs.total == Decimal("120")


def test_scoreboard_subtracts_api_cost_exactly_once_from_agent_lines() -> None:
    board = build_scoreboard(
        ScoreboardInputs(
            starting_cash=Decimal("10000"),
            agent_alone_gross_pnl=Decimal("500"),
            approved_gross_pnl=Decimal("300"),
            vti_gross_pnl=Decimal("200"),
            agent_alone_non_api_costs=Decimal("115"),
            approved_non_api_costs=Decimal("69"),
            api_cost=Decimal("20"),
        )
    )

    assert board.agent_alone.net_value == Decimal("10365")
    assert board.with_approvals.net_value == Decimal("10211")
    assert board.vti.net_value == Decimal("10200")
    assert board.cash.net_value == Decimal("10000")
    assert board.agent_alone.api_cost == board.with_approvals.api_cost == Decimal('20')
    assert board.vti.api_cost == board.cash.api_cost == 0


def test_weekly_report_is_plain_english_and_writes_scoreboard(tmp_path: Path) -> None:
    board = build_scoreboard(
        ScoreboardInputs(
            starting_cash=Decimal("10000"),
            agent_alone_gross_pnl=Decimal("500"),
            approved_gross_pnl=Decimal("300"),
            vti_gross_pnl=Decimal("200"),
            agent_alone_non_api_costs=Decimal("115"),
            approved_non_api_costs=Decimal("69"),
            api_cost=Decimal("20"),
        )
    )
    path = tmp_path / "weekly_report.md"

    WeeklyReport().write(
        path,
        board,
        holdings="VTI: $200.80; cash: $799.20",
        calibration="70% confidence has been right 50% of the time.",
        biggest_wins="VTI +$120.00",
        biggest_losses="AAPL -$40.00",
        rules_fired="Stale quote: 1",
    )

    text = path.read_text()
    assert "After paying $20.00 in AI costs" in text
    assert "What the account holds" in text
    assert "Rules that fired" in text


def test_outcome_recorder_persists_one_five_twenty_and_proposal_horizon(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "agent.db")
    decided_at = datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc)
    observations = {
        day: (decided_at + timedelta(days=day), Decimal(day))
        for day in (1, 5, 20, 30)
    }

    OutcomeRecorder(store).record(
        "decision-1", decided_at=decided_at, horizon_days=30, observations=observations
    )

    rows = store.read_json("daily_values")
    assert {row["day_offset"] for row in rows} == {1, 5, 20, 30}
    assert all(row["decision_id"] == "decision-1" for row in rows)


def test_outcome_recorder_rejects_missing_required_horizon(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "agent.db")
    decided_at = datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="missing outcome observations"):
        OutcomeRecorder(store).record(
            "decision-1",
            decided_at=decided_at,
            horizon_days=30,
            observations={1: (decided_at + timedelta(days=1), Decimal("1"))},
        )
