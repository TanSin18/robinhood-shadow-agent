from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from agents.pipeline import Stage1Pipeline
from agents.schemas import TradeProposal
from broker.models import PaperOrder, Quote
from broker.paper import PaperBroker, ShadowExecution
from config.loader import RiskConfig
from data.store import SQLiteStore
from risk.engine import RiskEngine
from risk.models import RiskContext

NOW = datetime(2026, 9, 27, 14, 30, tzinfo=timezone.utc)


def proposal(account: str = "agentic-1") -> TradeProposal:
    return TradeProposal(
        proposal_id="p-1",
        client_order_id="c-1",
        account_id=account,
        ticker="VTI",
        asset_class="etf",
        side="buy",
        quantity=Decimal("1"),
        order_type="limit",
        limit_price=Decimal("100.40"),
        thesis="Diversified exposure.",
        good_if='breadth improves.',
        horizon_days=20,
        confidence=Decimal("0.6"),
        invalidation="the quote becomes stale.",
        critic_counterargument="A broad selloff could overwhelm the thesis.",
        prompt_versions={"portfolio": "portfolio_v1", "critic": "critic_v1"},
        model_name="gpt-test",
        config_hash="a" * 64,
    )


def context() -> RiskContext:
    return RiskContext(
        now=NOW,
        stage=1,
        quote_timestamp=NOW - timedelta(seconds=10),
        bid=Decimal("100"),
        ask=Decimal("100.20"),
        account_value=Decimal("1000"),
        current_value=Decimal("1000"),
        peak_value=Decimal("1000"),
        daily_pnl=Decimal("0"),
        settled_cash=Decimal("1000"),
        position_values={},
        realized_volatility_20d=Decimal('.08'), volatility_as_of=NOW,
        open_position_count=0,
        orders_today=0,
        traded_sides_today={},
        seen_client_order_ids=frozenset(),
        kill_switch=False,
        manually_unlocked_after_drawdown=False,
        auto_approve_requested=False,
    )


def make_pipeline(tmp_path: Path) -> tuple[Stage1Pipeline, SQLiteStore]:
    store = SQLiteStore(tmp_path / "agent.db")
    config = RiskConfig(
        agentic_account_id="agentic-1",
        instrument_whitelist=frozenset({"VTI"}),
    )
    execution = ShadowExecution(
        PaperBroker(Decimal("1000"), now=lambda: NOW, track="agent_alone"),
        PaperBroker(Decimal("1000"), now=lambda: NOW, track="with_approvals"),
    )
    return Stage1Pipeline(RiskEngine(config), execution, store), store


def test_pipeline_persists_risk_card_and_both_shadow_fills(tmp_path: Path) -> None:
    pipeline, store = make_pipeline(tmp_path)
    order = PaperOrder(
        client_order_id="c-1",
        ticker="VTI",
        asset_class="etf",
        side="buy",
        quantity=Decimal("1"),
        limit_price=Decimal("100.40"),
    )
    quote = Quote(ticker="VTI", bid=Decimal("100"), ask=Decimal("100.20"), timestamp=NOW)

    result = pipeline.run(
        proposal(),
        context(),
        order,
        quote,
        human_decision="YES",
        decided_at=NOW + timedelta(seconds=12),
        instrument_description="a broad US stock fund",
        max_loss_usd=Decimal("100.40"),
        holdings_after={"cash": Decimal("899.60"), "VTI": Decimal("100.40")},
        trace_url="http://127.0.0.1:6006/redirects/traces/t-1",
    )

    assert result.risk.allowed is True
    assert result.fills is not None
    assert result.fills.agent_alone.status == "filled"
    assert result.fills.with_approvals.status == "filled"
    assert len(store.read_json("decision_records")) == 1
    assert len(store.read_json("cards")) == 1
    assert len(store.read_json("fills")) == 2


def test_pipeline_never_reaches_broker_when_risk_blocks(tmp_path: Path) -> None:
    pipeline, store = make_pipeline(tmp_path)
    order = PaperOrder(
        client_order_id="c-1",
        ticker="VTI",
        asset_class="etf",
        side="buy",
        quantity=Decimal("1"),
        limit_price=Decimal("100.40"),
    )
    quote = Quote(ticker="VTI", bid=Decimal("100"), ask=Decimal("100.20"), timestamp=NOW)

    result = pipeline.run(
        proposal(account="main-account"),
        context(),
        order,
        quote,
        human_decision="YES",
        decided_at=NOW,
        instrument_description="a broad US stock fund",
        max_loss_usd=Decimal("100.40"),
        holdings_after={},
        trace_url="http://127.0.0.1:6006/redirects/traces/t-2",
    )

    assert result.risk.allowed is False
    assert result.fills is None
    assert store.read_json("fills") == []
