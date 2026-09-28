from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from broker.base import BrokerError
from broker.policy import (
    READ_ONLY_TOOL_ALLOWLIST,
    Stage1ToolPolicy,
    normalize_robinhood_tool_name,
)

MCPInvoker = Callable[[str, dict[str, Any]], Any]

LIVE_ORDER_TOOL_ALLOWLIST = frozenset(
    {
        "place_equity_order",
        "place_option_order",
        "place_crypto_order",
        "cancel_equity_order",
        "cancel_option_order",
        "cancel_crypto_order",
    }
)


@dataclass(frozen=True)
class LiveUnlock:
    """Future Stage 2 scaffold; never constructed from an agent setting."""

    manually_unlocked: bool
    approved_tool_name: str
    approval_id: str


class RobinhoodBroker:
    def __init__(
        self,
        invoker: MCPInvoker,
        stage: int = 1,
        live_unlock: LiveUnlock | None = None,
    ) -> None:
        self._invoker = invoker
        self.stage = stage
        self._live_unlock = live_unlock
        self._stage1_policy = Stage1ToolPolicy()

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        normalized = normalize_robinhood_tool_name(tool_name)
        forwarded = dict(arguments)
        if self.stage == 1:
            self._stage1_policy.authorize(tool_name)
        elif normalized not in READ_ONLY_TOOL_ALLOWLIST:
            self._authorize_future_live_write(normalized, forwarded)
            forwarded.pop("_manual_approval_id", None)
        return self._invoker(tool_name, forwarded)

    def _authorize_future_live_write(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> None:
        if tool_name not in LIVE_ORDER_TOOL_ALLOWLIST:
            raise BrokerError(f"Stage 2 live default-deny blocked Robinhood tool: {tool_name}")
        unlock = self._live_unlock
        supplied_approval = arguments.get("_manual_approval_id")
        if (
            unlock is None
            or not unlock.manually_unlocked
            or unlock.approved_tool_name != tool_name
            or supplied_approval != unlock.approval_id
        ):
            raise BrokerError(
                "Live Robinhood writes require a matching manual approval unlock"
            )
