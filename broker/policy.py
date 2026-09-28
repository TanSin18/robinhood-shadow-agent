from __future__ import annotations

from dataclasses import dataclass

from broker.base import BrokerError
from broker.read_contracts import READ_METHODS

READ_ONLY_TOOL_ALLOWLIST = READ_METHODS


def normalize_robinhood_tool_name(tool_name: str) -> str:
    prefix = "mcp__robinhood_trading__"
    return tool_name[len(prefix) :] if tool_name.startswith(prefix) else tool_name


@dataclass(frozen=True)
class Stage1ToolPolicy:
    allowed_tools: frozenset[str] = READ_ONLY_TOOL_ALLOWLIST

    def authorize(self, tool_name: str) -> str:
        normalized = normalize_robinhood_tool_name(tool_name)
        if tool_name != normalized or normalized not in self.allowed_tools:
            raise BrokerError(
                f"Stage 1 default-deny blocked Robinhood tool: {normalized}"
            )
        return normalized
