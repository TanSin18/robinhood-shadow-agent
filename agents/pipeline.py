from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from agents.approval import (
    ApprovalCard,
    ApprovalCardRenderer,
    ApprovalDecision,
    ApprovalManager,
)
from agents.schemas import TradeProposal
from broker.models import PaperOrder, Quote, ShadowFillResult
from broker.paper import ShadowExecution
from data.store import SQLiteStore
from risk.engine import RiskEngine
from risk.models import RiskContext, RiskVerdict


@dataclass(frozen=True)
class PipelineResult:
    risk: RiskVerdict
    card: ApprovalCard | None
    decision: ApprovalDecision | None
    fills: ShadowFillResult | None


class Stage1Pipeline:
    def __init__(
        self,
        risk_engine: RiskEngine,
        execution: ShadowExecution,
        store: SQLiteStore,
    ) -> None:
        self.risk_engine = risk_engine
        self.execution = execution
        self.store = store
        self.cards = ApprovalCardRenderer()

    def run(
        self,
        proposal: TradeProposal,
        context: RiskContext,
        order: PaperOrder,
        quote: Quote,
        *,
        human_decision: Literal["YES", "NO"] | None,
        decided_at: datetime,
        instrument_description: str,
        max_loss_usd: Decimal,
        holdings_after: dict[str, Decimal],
        trace_url: str,
    ) -> PipelineResult:
        self._validate_order_matches(proposal, order)
        verdict = self.risk_engine.evaluate(proposal, context)
        self.store.append_json(
            "decision_records",
            {
                "decision_id": proposal.proposal_id,
                "proposal": proposal.model_dump(mode="json"),
                "risk_status": verdict.status,
                "risk_reasons": [reason.value for reason in verdict.reasons],
                "prompt_versions": proposal.prompt_versions,
                "model_name": proposal.model_name,
                "config_hash": proposal.config_hash,
            },
        )
        if not verdict.allowed:
            return PipelineResult(verdict, None, None, None)

        card = self.cards.render(
            proposal,
            instrument_description=instrument_description,
            max_loss_usd=max_loss_usd,
            holdings_after=holdings_after,
            trace_url=trace_url,
        )
        approvals = ApprovalManager(expiry_minutes=30)
        approvals.issue(proposal.proposal_id, context.now)
        decision = approvals.resolve(
            proposal.proposal_id, human_decision, decided_at
        )
        self.store.append_json(
            "cards",
            {
                "card_id": proposal.proposal_id,
                "body": card.body,
                "trace_url": card.trace_url,
                "decision": decision.decision,
                "expired": decision.expired,
                "response_seconds": decision.response_seconds,
            },
        )
        self.store.append_json(
            "orders",
            {
                "client_order_id": order.client_order_id,
                "ticker": order.ticker,
                "status": "paper_submitted",
            },
        )
        fills = self.execution.execute_both_tracks(
            order, quote, human_decision=decision.decision
        )
        self.store.append_json("fills", fills.agent_alone.model_dump(mode="json"))
        self.store.append_json("fills", fills.with_approvals.model_dump(mode="json"))
        return PipelineResult(verdict, card, decision, fills)

    @staticmethod
    def _validate_order_matches(proposal: TradeProposal, order: PaperOrder) -> None:
        if (
            order.client_order_id != (proposal.client_order_id or proposal.proposal_id)
            or order.ticker != proposal.ticker
            or order.side != proposal.side
            or order.quantity != proposal.quantity
            or order.limit_price != proposal.limit_price
            or order.asset_class != proposal.asset_class
        ):
            raise ValueError("paper order does not match the risk-reviewed proposal")
