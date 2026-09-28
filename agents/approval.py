from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from agents.schemas import TradeProposal


def _money(value: Decimal) -> str:
    return f"${value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"


@dataclass(frozen=True)
class ApprovalCard:
    body: str
    trace_url: str


class ApprovalCardRenderer:
    def render(
        self,
        proposal: TradeProposal,
        *,
        instrument_description: str,
        max_loss_usd: Decimal,
        holdings_after: dict[str, Decimal],
        trace_url: str,
        calibrated_confidence: str | None = None,
    ) -> ApprovalCard:
        amount = proposal.quantity * proposal.limit_price * proposal.multiplier
        holdings = ", ".join(
            f"{name} {_money(value)}" for name, value in holdings_after.items()
        )
        confidence = (
            f" Based on past results, comparable calls were right {calibrated_confidence}."
            if calibrated_confidence
            else ""
        )
        body = "\n".join(
            (
                f"WHAT: {proposal.side.title()} {proposal.quantity} of {proposal.ticker} ({instrument_description}) for about {_money(amount)}.",
                f"WHY: {proposal.thesis}{confidence}",
                f"MONEY AT RISK: The most this can lose is {_money(max_loss_usd)}.",
                f"GOOD IF / BAD IF: Good if {proposal.good_if} Bad if {proposal.invalidation}",
                f"DEVIL'S ADVOCATE: {proposal.critic_counterargument or 'The critic did not produce a valid counterargument, so do not approve.'}",
                f"AFTER THIS: The agent-alone paper account holds {holdings}.",
                "IF YOU SAY NO: No approved-track trade is placed; the agent-alone shadow track is still measured.",
                "[YES] [NO]",
            )
        )
        if len(body.split()) > 150:
            raise ValueError("approval card exceeds 150 words")
        return ApprovalCard(body=body, trace_url=trace_url)


@dataclass(frozen=True)
class ApprovalDecision:
    card_id: str
    decision: Literal["YES", "NO"]
    expired: bool
    response_seconds: int


class ApprovalManager:
    def __init__(self, *, expiry_minutes: int = 30) -> None:
        self.expiry = timedelta(minutes=expiry_minutes)
        self._issued: dict[str, datetime] = {}
        self._resolved: set[str] = set()

    def issue(self, card_id: str, issued_at: datetime) -> None:
        self._issued[card_id] = issued_at

    def resolve(
        self,
        card_id: str,
        decision: Literal["YES", "NO"] | None,
        decided_at: datetime,
    ) -> ApprovalDecision:
        if card_id in self._resolved:
            raise ValueError(f"approval card {card_id} is already resolved")
        issued_at = self._issued[card_id]
        elapsed = decided_at - issued_at
        if decision is None and elapsed < self.expiry:
            raise ValueError("approval card is still pending")
        expired = elapsed >= self.expiry
        final_decision: Literal["YES", "NO"] = "NO" if expired else decision
        result = ApprovalDecision(
            card_id=card_id,
            decision=final_decision,
            expired=expired,
            response_seconds=max(0, int(elapsed.total_seconds())),
        )
        self._resolved.add(card_id)
        return result
