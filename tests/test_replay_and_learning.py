from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from data.store import SQLiteStore
from eval.learning import (
    ChallengerResult,
    ImprovementProposer,
    LessonMemory,
    PromotionGate,
)
from eval.replay import PointInTimeSnapshot, ReplayHarness

NOW = datetime(2026, 9, 27, 14, 30, tzinfo=timezone.utc)


def test_replay_rejects_any_snapshot_from_the_future() -> None:
    harness = ReplayHarness()
    snapshots = [
        PointInTimeSnapshot(observed_at=NOW, payload={"price": "100"}),
        PointInTimeSnapshot(observed_at=NOW + timedelta(seconds=1), payload={"price": "101"}),
    ]

    with pytest.raises(ValueError, match="lookahead"):
        harness.run(snapshots, replay_clock=NOW)


def test_replay_returns_only_point_in_time_payloads() -> None:
    snapshots = [PointInTimeSnapshot(observed_at=NOW, payload={"price": "100"})]

    result = ReplayHarness().run(snapshots, replay_clock=NOW)

    assert result == ({"price": "100"},)


def test_lessons_and_improvement_proposals_are_append_only(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "agent.db")
    LessonMemory(store).append(
        thesis="Rates would fall.",
        outcome="Rates rose.",
        reasoning_or_luck="The reasoning ignored inflation data.",
    )
    proposer = ImprovementProposer(store)
    proposer.propose(
        title="Require inflation evidence",
        evidence="Three rate theses omitted current inflation releases.",
    )

    assert len(store.read_json("lessons")) == 1
    assert len(store.read_json("improvement_proposals")) == 1
    assert proposer.applies_changes_live is False


@pytest.mark.parametrize(
    ("weeks", "decisions", "metric", "challenger", "all_costs", "expected"),
    [
        (3, 40, "net_return", Decimal("11"), True, False),
        (4, 29, "net_return", Decimal("11"), True, False),
        (4, 30, "different_metric", Decimal("11"), True, False),
        (4, 30, "net_return", Decimal("9"), True, False),
        (4, 30, "net_return", Decimal("11"), False, False),
        (4, 30, "net_return", Decimal("11"), True, True),
    ],
)
def test_challenger_promotion_requires_every_fixed_gate(
    weeks: int,
    decisions: int,
    metric: str,
    challenger: Decimal,
    all_costs: bool,
    expected: bool,
) -> None:
    result = ChallengerResult(
        weeks=weeks,
        decisions=decisions,
        predeclared_metric="net_return",
        measured_metric=metric,
        champion_score=Decimal("10"),
        challenger_score=challenger,
        all_costs_included=all_costs,
        human_live_approval=False,
    )

    verdict = PromotionGate().evaluate(result)

    assert verdict.promote_to_champion is expected
    assert verdict.unlock_live is False


def test_live_always_requires_separate_human_yes() -> None:
    base = ChallengerResult(
        weeks=4,
        decisions=30,
        predeclared_metric="net_return",
        measured_metric="net_return",
        champion_score=Decimal("10"),
        challenger_score=Decimal("11"),
        all_costs_included=True,
        human_live_approval=True,
    )

    verdict = PromotionGate().evaluate(base)

    assert verdict.promote_to_champion is True
    assert verdict.unlock_live is True
