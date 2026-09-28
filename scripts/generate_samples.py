from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from agents.approval import ApprovalCardRenderer
from agents.schemas import TradeProposal
from eval.scoreboard import ScoreboardInputs, build_scoreboard


@dataclass(frozen=True)
class SampleOutputs:
    approval_card: Path
    scoreboard: Path


def generate_samples(output_dir: str | Path) -> SampleOutputs:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    proposal = TradeProposal(
        proposal_id="mock-proposal-001",
        client_order_id="mock-order-001",
        account_id="mock-agentic-account",
        ticker="VTI",
        asset_class="etf",
        side="buy",
        quantity=Decimal("0.49"),
        order_type="limit",
        limit_price=Decimal("100.40"),
        thesis="The broad US market offers diversified exposure without depending on one company.",
        good_if='market breadth improves over the next month.',
        horizon_days=20,
        confidence=Decimal("0.70"),
        invalidation="the quote becomes stale or the risk limit blocks the trade.",
        critic_counterargument="A broad selloff could outweigh the diversification benefit.",
        evidence=(),
        prompt_versions={"research": "research_v1", "portfolio": "portfolio_v1", "critic": "critic_v1"},
        model_name="mock-model",
        config_hash="a" * 64,
    )
    card = ApprovalCardRenderer().render(
        proposal,
        instrument_description="a broad US stock fund",
        max_loss_usd=Decimal("49.196"),
        holdings_after={"cash": Decimal("450.804"), "VTI": Decimal("49.196")},
        trace_url=str((target / 'sample_approval_trace.md').resolve()),
    )
    (target / 'sample_approval_trace.md').write_text('# MOCKED decision trace\n\nNo provider call and no real order. This is a worked example, not a Phoenix trace.\n\nResearch: broad-market diversification.\n\nPortfolio: 0.49 VTI units at a fictional $100.40 limit, $49.196 notional in a $500 reference account.\n\nCritic: a broad selloff can overwhelm diversification.\n\nRisk: simulated 20% realized volatility yields a $50 target at 20% target volatility, capped at $125. $49.196 is below both and $500 settled cash.\n\nApproval: PENDING until YES, NO, or configured expiry. No approval assumed.\n\nStage 1 execution: paper only; broker writes unavailable.\n',encoding='utf-8')
    card_path = target / "sample_approval_card.md"
    card_path.write_text(
        "# MOCKED SAMPLE — no order was sent\n\n"
        + card.body
        + f"\n\n[Open the local trace]({card.trace_url})\n",
        encoding="utf-8",
    )

    board = build_scoreboard(
        ScoreboardInputs(
            starting_cash=Decimal("500"),
            agent_alone_gross_pnl=Decimal("10"),
            approved_gross_pnl=Decimal("8"),
            vti_gross_pnl=Decimal("4"),
            agent_alone_non_api_costs=Decimal("1"),
            approved_non_api_costs=Decimal("1"),
            api_cost=Decimal("0.40"),
        )
    )
    scoreboard_path = target / "sample_scoreboard.md"
    scoreboard_path.write_text(
        "# MOCKED SAMPLE SCOREBOARD\n\n" + board.to_markdown() + "\n",
        encoding="utf-8",
    )
    return SampleOutputs(approval_card=card_path, scoreboard=scoreboard_path)


if __name__ == "__main__":
    generated = generate_samples(Path(__file__).parents[1] / "reports")
    print(generated.approval_card)
    print(generated.scoreboard)
