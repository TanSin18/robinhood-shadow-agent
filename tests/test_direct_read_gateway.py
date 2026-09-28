from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

import pytest

from broker.base import BrokerError
from broker_proxy.mcp_client import RobinhoodMCPClient
from broker.read_gateway import CapabilityError, EffectiveReadGateway, SCHEMAS
from broker.robinhood import RobinhoodBroker
from test_inbox_lanes import setup_runtime


@dataclass
class Tool:
    name: str
    inputSchema: dict


class FakeDirectClient:
    def __init__(
        self,
        account: dict | None = None,
        tools: list[Tool] | None = None,
        portfolio: dict | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.account = account
        self.tools = tools or [Tool(name, schema) for name, schema in SCHEMAS.items()]
        self.portfolio = portfolio or {}

    def list_remote_tools(self):
        return self.tools

    def call_read(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "get_accounts":
            data = {"accounts": [self.account]}
        elif name == "get_portfolio":
            data = self.portfolio
        else:
            data = {}
        return {"structuredContent": {"data": data}}


def _account(config, **changes):
    return {
        "account_number": config.risk.agentic_account_id,
        "agentic_allowed": True,
        "unsettled_funds": "0.00",
        **changes,
    }


def _portfolio(**changes):
    result = {
        "cash": "0.00",
        "pending_deposits": "0.00",
        "buying_power": {
            "buying_power": "0.00",
            "unleveraged_buying_power": "0.00",
        },
    }
    for name, value in changes.items():
        if name in {"buying_power", "unleveraged_buying_power"}:
            result["buying_power"][name] = value
        else:
            result[name] = value
    return result


def _gateway(tmp_path, *, account=None, tools=None, portfolio=None):
    _, config = setup_runtime(tmp_path)
    incidents: list[str] = []
    client = FakeDirectClient(account or _account(config), tools, portfolio or _portfolio())
    gateway = EffectiveReadGateway(
        client,
        config,
        incidents.append,
        max_agentic_cash_usd=Decimal("1200.00"),
    )
    return gateway, client, incidents, config


def test_remote_superset_is_recorded_but_effective_capability_is_exact_eleven(tmp_path) -> None:
    _, config = setup_runtime(tmp_path)
    tools = [Tool(name, schema) for name, schema in SCHEMAS.items()]
    tools.append(Tool("place_equity_order", {"type": "object"}))
    gateway, client, _, _ = _gateway(tmp_path, account=_account(config), tools=tools)

    evidence = gateway.preflight(scope_path="full_scope_bounded_cash_fallback")

    assert evidence["effective_read_tools"] == sorted(SCHEMAS)
    assert evidence["effective_write_tool_count"] == 0
    assert evidence["remote_tool_count"] == 12
    assert evidence["account_bounds"] == {
        "status": "VERIFIED",
        "checked_fields": ["cash", "buying_power", "unleveraged_buying_power"],
    }
    assert client.calls == [
        ("get_accounts", {}),
        ("get_portfolio", {"account_number": config.risk.agentic_account_id}),
    ]

    read = gateway.call("get_accounts", {})
    assert read["source_id"] == "robinhood-mcp:get_accounts"
    assert len(read["content_hash"]) == 64
    assert read["observed_at"] == read["effective_at"] == read["fetched_at"]


@pytest.mark.parametrize("cash", ["0", "500", "1200.00"])
def test_bounded_fallback_accepts_nonmargin_cash_at_or_below_cap(tmp_path, cash) -> None:
    _, config = setup_runtime(tmp_path)
    account = {
        "account_number": config.risk.agentic_account_id,
        "agentic_allowed": True,
        "unsettled_funds": "0.00",
    }
    portfolio = {
        "cash": cash,
        "pending_deposits": "0.00",
        "buying_power": {
            "buying_power": cash,
            "unleveraged_buying_power": cash,
        },
    }
    incidents: list[str] = []
    client = FakeDirectClient(account, portfolio=portfolio)
    gateway = EffectiveReadGateway(
        client,
        config,
        incidents.append,
        max_agentic_cash_usd=Decimal("1200.00"),
    )

    evidence = gateway.preflight(scope_path="full_scope_bounded_cash_fallback")

    assert incidents == []
    assert evidence["account_bounds"]["status"] == "VERIFIED"
    assert client.calls == [
        ("get_accounts", {}),
        ("get_portfolio", {"account_number": config.risk.agentic_account_id}),
    ]


@pytest.mark.parametrize(
    "tool_name",
    [
        "place_equity_order",
        "replace_equity_order",
        "cancel_equity_order",
        "exercise_option",
        "transfer_money",
        "deposit_funds",
        "withdraw_funds",
        "update_account_settings",
        "unknown_tool",
        "mcp__robinhood_trading__get_accounts",
        "get_accounts\N{FULLWIDTH LOW LINE}extra",
    ],
)
def test_every_enforcement_layer_blocks_non_exact_tool_before_upstream(tmp_path, tool_name) -> None:
    gateway, direct, _, _ = _gateway(tmp_path)
    with pytest.raises((CapabilityError, BrokerError)):
        gateway.call(tool_name, {})
    assert direct.calls == []

    class Session:
        def __init__(self): self.calls = []
        async def call_tool(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    session = Session()
    client = RobinhoodMCPClient.for_testing(session)

    async def attempt():
        with pytest.raises(BrokerError, match="Stage 1 default-deny"):
            await client.call_read_async(tool_name, {})

    import asyncio
    asyncio.run(attempt())
    assert session.calls == []

    invoked = []
    broker = RobinhoodBroker(lambda name, args: invoked.append((name, args)), stage=1)
    with pytest.raises(BrokerError, match="Stage 1 default-deny"):
        broker.call_tool(tool_name, {})
    assert invoked == []


def test_missing_read_or_schema_drift_fails_before_account_call(tmp_path) -> None:
    for tools in (
        [Tool(name, schema) for name, schema in SCHEMAS.items() if name != "get_accounts"],
        [
            Tool(name, {"type": "object"} if name == "get_accounts" else schema)
            for name, schema in SCHEMAS.items()
        ],
    ):
        gateway, client, incidents, _ = _gateway(tmp_path, tools=tools)
        with pytest.raises(CapabilityError):
            gateway.preflight(scope_path="full_scope_bounded_cash_fallback")
        assert client.calls == []
        assert incidents == ["UNEXPECTED_CAPABILITY"]


@pytest.mark.parametrize(("cash", "buying", "unleveraged"), [
    ("1200.01", "1200.01", "1200.01"),
    ("500", "550", "500"),
    ("500", "500", "499.99"),
    ("NaN", "NaN", "NaN"),
    ("-1", "-1", "-1"),
])
def test_bounded_fallback_holds_outside_cap_or_on_margin(
    tmp_path, cash, buying, unleveraged
) -> None:
    _, config = setup_runtime(tmp_path)
    gateway, _, incidents, _ = _gateway(
        tmp_path,
        account=_account(config),
        portfolio=_portfolio(
            cash=cash,
            buying_power=buying,
            unleveraged_buying_power=unleveraged,
        ),
    )

    with pytest.raises(CapabilityError, match="AGENTIC_ACCOUNT_OUTSIDE_BOUNDS"):
        gateway.preflight(scope_path="full_scope_bounded_cash_fallback")

    assert incidents == ["AGENTIC_ACCOUNT_OUTSIDE_BOUNDS"]


def test_bounded_account_evidence_and_errors_never_report_amount_or_identifier(tmp_path) -> None:
    _, config = setup_runtime(tmp_path)
    distinctive_cash = "987.65"
    gateway, _, _, _ = _gateway(
        tmp_path,
        account=_account(config),
        portfolio=_portfolio(
            cash=distinctive_cash,
            buying_power=distinctive_cash,
            unleveraged_buying_power=distinctive_cash,
        ),
    )

    evidence = gateway.preflight(scope_path="full_scope_bounded_cash_fallback")
    report = json.dumps(evidence, sort_keys=True)

    assert distinctive_cash not in report
    assert config.risk.agentic_account_id not in report


def test_duplicate_or_non_agentic_account_match_fails_closed(tmp_path) -> None:
    _, config = setup_runtime(tmp_path)
    account = _account(config, agentic_allowed=False)
    gateway, _, incidents, _ = _gateway(tmp_path, account=account)

    with pytest.raises(CapabilityError, match="STAGE1_AGENTIC_ACCOUNT_UNVERIFIED"):
        gateway.preflight(scope_path="full_scope_bounded_cash_fallback")

    assert incidents == ["STAGE1_AGENTIC_ACCOUNT_UNVERIFIED"]
