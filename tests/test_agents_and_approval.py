from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from agents.approval import ApprovalCardRenderer, ApprovalManager
from agents.definitions import build_agents
from agents.notifications import MacOSNotifier
from agents.schemas import CriticOutput, ResearchPacket, TradeProposal
from agents.workflow import TradingWorkflow, ValidatedAgentRunner
from data.store import SQLiteStore
from prompts.registry import PromptRegistry

NOW = datetime(2026, 9, 27, 14, 30, tzinfo=timezone.utc)
PROMPTS = Path(__file__).parents[1] / "prompts"


class SequenceRunner:
    def __init__(self, outputs: list[object]) -> None:
        self.outputs = list(outputs)
        self.calls: list[tuple[str, str]] = []

    def run(self, agent: object, prompt: str) -> object:
        self.calls.append((agent.name, prompt))
        return self.outputs.pop(0)


def proposal_dict() -> dict[str, object]:
    return {
        "proposal_id": "p-1",
        "client_order_id": "client-1",
        "account_id": "agentic-1",
        "ticker": "VTI",
        "asset_class": "etf",
        "side": "buy",
        "quantity": "2",
        "order_type": "limit",
        "limit_price": "100.40",
        "thesis": "Broad diversification at a known price.",
        "good_if": "participation broadens.",
        "horizon_days": 20,
        "confidence": "0.70",
        "invalidation": "The broad-market thesis breaks.",
        "evidence": [],
        "prompt_versions": {"portfolio": "portfolio_v1"},
        "model_name": "gpt-test",
        "config_hash": "a" * 64,
    }


def test_builds_exactly_three_sdk_agents_with_separate_critic() -> None:
    bundle = build_agents(PromptRegistry(PROMPTS), model_name="gpt-test")

    assert bundle.research.name == "Research Agent"
    assert bundle.portfolio.name == "Portfolio Agent"
    assert bundle.critic.name == "Critic"
    assert bundle.research.output_type is ResearchPacket
    assert bundle.portfolio.output_type is TradeProposal
    assert bundle.critic.output_type is CriticOutput
    assert len({id(bundle.research), id(bundle.portfolio), id(bundle.critic)}) == 3


def test_malformed_output_is_retried_once_then_validated(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "agent.db")
    sdk_agents = build_agents(PromptRegistry(PROMPTS), model_name="gpt-test")
    low_level = SequenceRunner([{"ticker": "VTI"}, proposal_dict()])
    runner = ValidatedAgentRunner(low_level, store)

    result = runner.run_typed(
        sdk_agents.portfolio,
        "make a proposal",
        TradeProposal,
        prompt_version="portfolio_v1",
    )

    assert result is not None
    assert result.ticker == "VTI"
    assert len(low_level.calls) == 2
    assert "failed schema validation" in low_level.calls[1][1]


def test_second_malformed_output_is_logged_and_skipped(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "agent.db")
    sdk_agents = build_agents(PromptRegistry(PROMPTS), model_name="gpt-test")
    low_level = SequenceRunner([{"bad": 1}, {"still_bad": 2}])
    runner = ValidatedAgentRunner(low_level, store)

    result = runner.run_typed(
        sdk_agents.portfolio,
        "make a proposal",
        TradeProposal,
        prompt_version="portfolio_v1",
    )

    assert result is None
    assert len(low_level.calls) == 2
    assert store.read_json("validation_failures")[0]["agent"] == "Portfolio Agent"


def test_workflow_attaches_separate_critics_counterargument(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "agent.db")
    bundle = build_agents(PromptRegistry(PROMPTS), model_name="gpt-test")
    low_level = SequenceRunner(
        [
            {"ticker": "VTI", "as_of": NOW.isoformat(), "evidence": []},
            proposal_dict(),
            {"proposal_id": "p-1", "counterargument": "The valuation already assumes good news."},
        ]
    )
    workflow = TradingWorkflow(bundle, ValidatedAgentRunner(low_level, store))

    result = workflow.run("Research VTI using data available now.")

    assert result is not None
    assert result.critic_counterargument == "The valuation already assumes good news."
    assert [name for name, _ in low_level.calls] == ["Research Agent", "Portfolio Agent", "Critic"]


def test_approval_card_is_plain_short_and_uses_dollars() -> None:
    proposal = TradeProposal.model_validate(proposal_dict()).model_copy(
        update={"critic_counterargument": "A broad selloff could overwhelm the thesis."}
    )
    renderer = ApprovalCardRenderer()

    card = renderer.render(
        proposal,
        instrument_description="a broad US stock fund",
        max_loss_usd=Decimal("200.80"),
        holdings_after={"cash": Decimal("799.20"), "VTI": Decimal("200.80")},
        trace_url="http://127.0.0.1:6006/redirects/traces/trace-123",
    )

    for heading in ("WHAT:", "WHY:", "MONEY AT RISK:", "GOOD IF / BAD IF:", "DEVIL'S ADVOCATE:", "AFTER THIS:", "IF YOU SAY NO:"):
        assert heading in card.body
    assert "$200.80" in card.body
    assert "70%" not in card.body
    assert "http://127.0.0.1:6006/redirects/traces/trace-123" in card.trace_url
    assert len(card.body.split()) <= 150


def test_card_expires_after_thirty_minutes_and_counts_as_no() -> None:
    manager = ApprovalManager(expiry_minutes=30)
    manager.issue("card-1", NOW)

    decision = manager.resolve("card-1", None, NOW + timedelta(minutes=31))

    assert decision.decision == "NO"
    assert decision.expired is True
    assert decision.response_seconds == 31 * 60


def test_manual_decision_tracks_response_time() -> None:
    manager = ApprovalManager(expiry_minutes=30)
    manager.issue("card-1", NOW)

    decision = manager.resolve("card-1", "YES", NOW + timedelta(seconds=42))

    assert decision.decision == "YES"
    assert decision.expired is False
    assert decision.response_seconds == 42


def test_exactly_thirty_minutes_expires_and_card_cannot_be_decided_twice() -> None:
    manager = ApprovalManager(expiry_minutes=30)
    manager.issue("card-1", NOW)

    decision = manager.resolve("card-1", None, NOW + timedelta(minutes=30))

    assert decision.decision == "NO"
    assert decision.expired is True
    try:
        manager.resolve("card-1", "YES", NOW + timedelta(minutes=31))
    except ValueError as error:
        assert "already resolved" in str(error)
    else:
        raise AssertionError("a resolved approval card was accepted twice")


def test_macos_notification_passes_untrusted_text_as_arguments_not_script() -> None:
    calls: list[list[str]] = []

    def runner(arguments: list[str], **_: object) -> None:
        calls.append(arguments)

    hostile = '" & do shell script "touch /tmp/never" & "'
    MacOSNotifier(runner=runner).notify(hostile, hostile)

    command = calls[0]
    script_parts = [command[index + 1] for index, item in enumerate(command[:-1]) if item == "-e"]
    assert all(hostile not in script for script in script_parts)
    assert command[-2:] == [hostile, hostile]
