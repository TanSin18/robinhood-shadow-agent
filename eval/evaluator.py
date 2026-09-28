from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from data.store import SQLiteStore


@dataclass(frozen=True)
class DecisionOutcome:
    decision_id: str
    confidence: Decimal
    hit: bool
    net_pnl: Decimal
    evidence_types: tuple[str, ...]
    strategy: str
    human_decision: Literal["YES", "NO", "EXPIRED"]


@dataclass(frozen=True)
class CalibrationBucket:
    confidence: Decimal
    count: int
    hit_rate: Decimal


@dataclass(frozen=True)
class Attribution:
    by_evidence: dict[str, Decimal]
    by_strategy: dict[str, Decimal]


@dataclass(frozen=True)
class ApprovalValue:
    agent_alone_pnl: Decimal
    approved_only_pnl: Decimal
    value_added: Decimal


@dataclass(frozen=True)
class TradingCosts:
    api: Decimal = Decimal("0")
    spread: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    short_term_gain: Decimal = Decimal("0")
    long_term_gain: Decimal = Decimal("0")
    short_term_tax_rate: Decimal = Decimal("0.35")
    long_term_tax_rate: Decimal = Decimal("0.15")

    @property
    def estimated_tax(self) -> Decimal:
        short = max(self.short_term_gain, Decimal("0")) * self.short_term_tax_rate
        long = max(self.long_term_gain, Decimal("0")) * self.long_term_tax_rate
        return short + long

    @property
    def total(self) -> Decimal:
        return self.api + self.spread + self.fees + self.estimated_tax


class Evaluator:
    def calibration(
        self, outcomes: list[DecisionOutcome]
    ) -> dict[Decimal, CalibrationBucket]:
        grouped: dict[Decimal, list[DecisionOutcome]] = {}
        for outcome in outcomes:
            grouped.setdefault(outcome.confidence, []).append(outcome)
        return {
            confidence: CalibrationBucket(
                confidence=confidence,
                count=len(group),
                hit_rate=Decimal(sum(item.hit for item in group)) / Decimal(len(group)),
            )
            for confidence, group in grouped.items()
        }

    def attribution(self, outcomes: list[DecisionOutcome]) -> Attribution:
        by_evidence: dict[str, Decimal] = {}
        by_strategy: dict[str, Decimal] = {}
        for outcome in outcomes:
            if outcome.evidence_types:
                share = outcome.net_pnl / Decimal(len(outcome.evidence_types))
                for evidence_type in outcome.evidence_types:
                    by_evidence[evidence_type] = by_evidence.get(
                        evidence_type, Decimal("0")
                    ) + share
            by_strategy[outcome.strategy] = by_strategy.get(
                outcome.strategy, Decimal("0")
            ) + outcome.net_pnl
        return Attribution(by_evidence=by_evidence, by_strategy=by_strategy)

    def approval_value(self, outcomes: list[DecisionOutcome]) -> ApprovalValue:
        agent_alone = sum((item.net_pnl for item in outcomes), Decimal("0"))
        approved = sum(
            (item.net_pnl for item in outcomes if item.human_decision == "YES"),
            Decimal("0"),
        )
        return ApprovalValue(
            agent_alone_pnl=agent_alone,
            approved_only_pnl=approved,
            value_added=approved - agent_alone,
        )


class OutcomeRecorder:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def record(
        self,
        decision_id: str,
        *,
        decided_at: datetime,
        horizon_days: int,
        observations: dict[int, tuple[datetime, Decimal]],
    ) -> None:
        required = {1, 5, 20, horizon_days}
        missing = required - observations.keys()
        if missing:
            raise ValueError(
                "missing outcome observations for day offsets: "
                + ", ".join(str(day) for day in sorted(missing))
            )
        for day_offset in sorted(required):
            observed_at, net_pnl = observations[day_offset]
            if observed_at < decided_at + timedelta(days=day_offset):
                raise ValueError("outcome observation predates its required horizon")
            self.store.append_json(
                "daily_values",
                {
                    "decision_id": decision_id,
                    "day_offset": day_offset,
                    "observed_at": observed_at.isoformat(),
                    "net_pnl": str(net_pnl),
                },
            )
