import pytest

from broker.base import BrokerError
from broker.policy import Stage1ToolPolicy
from broker.robinhood import LiveUnlock, RobinhoodBroker


class RecordingInvoker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((tool_name, arguments))
        return {"ok": True, "tool": tool_name}


def test_known_read_tool_reaches_injected_mcp_invoker() -> None:
    invoker = RecordingInvoker()
    broker = RobinhoodBroker(invoker=invoker, stage=1)

    result = broker.call_tool("get_equity_quotes", {"symbols": ["VTI"]})

    assert result == {"ok": True, "tool": "get_equity_quotes"}
    assert invoker.calls == [("get_equity_quotes", {"symbols": ["VTI"]})]


@pytest.mark.parametrize(
    "real_tool_name",
    [
        "place_equity_order",
        "cancel_equity_order",
        "exercise_option",
        "transfer_money",
        "cancel_option_order",
        "mcp__robinhood_trading__place_crypto_order",
    ],
)
def test_stage_one_blocks_real_order_cancel_and_exercise_before_invocation(
    real_tool_name: str,
) -> None:
    invoker = RecordingInvoker()
    broker = RobinhoodBroker(invoker=invoker, stage=1)

    with pytest.raises(BrokerError, match="Stage 1 default-deny"):
        broker.call_tool(real_tool_name, {"account_number": "agentic-1"})

    assert invoker.calls == []


def test_unknown_future_money_movement_tool_is_denied_by_default() -> None:
    policy = Stage1ToolPolicy()

    with pytest.raises(BrokerError, match="Stage 1 default-deny"):
        policy.authorize("move_money_new_tool")


def test_stage1_policy_denies_every_real_write_capability() -> None:
    policy = Stage1ToolPolicy()
    real_writes = (
        'place_equity_order',
        'place_option_order',
        'place_crypto_order',
        'cancel_equity_order',
        'cancel_option_order',
        'cancel_crypto_order',
        'replace_equity_order',
        'exercise_option',
        'transfer_money',
        'deposit_funds',
        'withdraw_funds',
    )

    for tool_name in real_writes:
        with pytest.raises(BrokerError, match='Stage 1 default-deny'):
            policy.authorize(tool_name)


def test_watchlist_write_is_blocked_even_though_it_is_not_an_order() -> None:
    invoker = RecordingInvoker()
    broker = RobinhoodBroker(invoker=invoker, stage=1)

    with pytest.raises(BrokerError, match="Stage 1 default-deny"):
        broker.call_tool("add_to_watchlist", {"list_id": "x", "symbols": ["VTI"]})

    assert invoker.calls == []


def test_future_live_unlock_cannot_authorize_unknown_or_money_moving_tool() -> None:
    invoker = RecordingInvoker()
    broker = RobinhoodBroker(
        invoker=invoker,
        stage=2,
        live_unlock=LiveUnlock(True, "transfer_money", "approval-1"),
    )

    with pytest.raises(BrokerError, match="live default-deny"):
        broker.call_tool("transfer_money", {"_manual_approval_id": "approval-1"})

    assert invoker.calls == []


def test_future_live_order_strips_internal_approval_metadata_before_mcp() -> None:
    invoker = RecordingInvoker()
    broker = RobinhoodBroker(
        invoker=invoker,
        stage=2,
        live_unlock=LiveUnlock(True, "place_equity_order", "approval-1"),
    )

    broker.call_tool(
        "place_equity_order",
        {"account_number": "agentic-1", "_manual_approval_id": "approval-1"},
    )

    assert invoker.calls == [("place_equity_order", {"account_number": "agentic-1"})]
