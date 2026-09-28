from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from data.store import SQLiteStore


class LessonMemory:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def append(self, *, thesis: str, outcome: str, reasoning_or_luck: str) -> int:
        return self.store.append_json(
            "lessons",
            {
                "thesis": thesis,
                "outcome": outcome,
                "reasoning_or_luck": reasoning_or_luck,
            },
        )


class ImprovementProposer:
    applies_changes_live = False

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def propose(self, *, title: str, evidence: str) -> int:
        return self.store.append_json(
            "improvement_proposals",
            {"title": title, "evidence": evidence, "status": "pending_human_approval"},
        )


@dataclass(frozen=True)
class ChallengerResult:
    weeks: int
    decisions: int
    predeclared_metric: str
    measured_metric: str
    champion_score: Decimal
    challenger_score: Decimal
    all_costs_included: bool
    human_live_approval: bool


@dataclass(frozen=True)
class PromotionVerdict:
    promote_to_champion: bool
    unlock_live: bool
    reasons: tuple[str, ...]


class PromotionGate:
    def evaluate(self, result: ChallengerResult) -> PromotionVerdict:
        reasons: list[str] = []
        if result.weeks < 4:
            reasons.append("needs_four_weeks")
        if result.decisions < 30:
            reasons.append("needs_thirty_decisions")
        if result.measured_metric != result.predeclared_metric:
            reasons.append("metric_changed")
        if not result.all_costs_included:
            reasons.append("costs_missing")
        if result.challenger_score <= result.champion_score:
            reasons.append("challenger_did_not_win")
        promote = not reasons
        return PromotionVerdict(
            promote_to_champion=promote,
            unlock_live=promote and result.human_live_approval,
            reasons=tuple(reasons),
        )

