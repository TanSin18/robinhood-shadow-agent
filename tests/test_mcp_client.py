from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass

import pytest

from broker_proxy.mcp_client import MCPProtocolError, RobinhoodMCPClient


@dataclass
class Page:
    tools: list[object]
    nextCursor: str | None = None


@dataclass
class Tool:
    name: str


class FakeSession:
    def __init__(self) -> None:
        self.cursors: list[str | None] = []
        self.calls: list[tuple[str, dict]] = []

    async def list_tools(self, *, params=None):
        cursor = getattr(params, "cursor", None)
        self.cursors.append(cursor)
        if cursor is None:
            return Page([Tool("get_accounts")], "page-2")
        return Page([Tool("place_equity_order"), Tool("get_portfolio")], None)

    async def call_tool(self, name, arguments, **kwargs):
        self.calls.append((name, arguments))
        return {"ok": True, "name": name}


@pytest.mark.asyncio
async def test_direct_client_collects_paginated_remote_catalog() -> None:
    session = FakeSession()
    client = RobinhoodMCPClient.for_testing(session)

    tools = await client.list_remote_tools_async()

    assert [tool.name for tool in tools] == [
        "get_accounts",
        "place_equity_order",
        "get_portfolio",
    ]
    assert session.cursors == [None, "page-2"]


@pytest.mark.asyncio
async def test_direct_client_calls_read_without_allowing_input_required() -> None:
    session = FakeSession()
    client = RobinhoodMCPClient.for_testing(session)

    result = await client.call_read_async("get_accounts", {})

    assert result == {"ok": True, "name": "get_accounts"}
    assert session.calls == [("get_accounts", {})]


@pytest.mark.asyncio
async def test_catalog_repeated_cursor_fails_closed() -> None:
    class LoopingSession(FakeSession):
        async def list_tools(self, *, params=None):
            return Page([Tool("get_accounts")], "same")

    client = RobinhoodMCPClient.for_testing(LoopingSession())

    with pytest.raises(MCPProtocolError, match="repeated pagination cursor"):
        await client.list_remote_tools_async()


def test_official_endpoint_cannot_be_overridden() -> None:
    with pytest.raises(ValueError, match="official Robinhood MCP endpoint"):
        RobinhoodMCPClient(server_url="https://evil.example/mcp")


def test_sync_client_opens_calls_and_closes_on_one_owner_task() -> None:
    task_ids: list[int] = []

    class TaskBoundClient(RobinhoodMCPClient):
        def __init__(self) -> None:
            super().__init__(storage=object())  # type: ignore[arg-type]

        async def open_async(self, *, interactive: bool = False) -> None:
            del interactive
            stack = AsyncExitStack()

            @asynccontextmanager
            async def task_bound_session():
                owner = asyncio.current_task()
                assert owner is not None
                task_ids.append(id(owner))
                try:
                    yield FakeSession()
                finally:
                    closer = asyncio.current_task()
                    assert closer is not None
                    task_ids.append(id(closer))
                    if closer is not owner:
                        raise RuntimeError("session closed by a different task")

            self._session = await stack.enter_async_context(task_bound_session())
            self._stack = stack

    client = TaskBoundClient().open()
    try:
        assert [tool.name for tool in client.list_remote_tools()] == [
            "get_accounts",
            "place_equity_order",
            "get_portfolio",
        ]
    finally:
        client.close()

    assert len(set(task_ids)) == 1


@pytest.mark.asyncio
async def test_direct_transport_skips_unsupported_remote_session_termination(monkeypatch) -> None:
    import broker_proxy.mcp_client as module

    recorded: dict[str, object] = {}

    async def tokens(_storage):
        return object()

    @asynccontextmanager
    async def http_client(*, auth):
        del auth
        yield object()

    @asynccontextmanager
    async def transport(url, *, http_client, terminate_on_close):
        del url, http_client
        recorded["terminate_on_close"] = terminate_on_close
        yield object(), object()

    class Session:
        def __init__(self, read_stream, write_stream):
            del read_stream, write_stream

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

        async def initialize(self):
            return None

    monkeypatch.setattr(module, "require_noninteractive_tokens", tokens)
    monkeypatch.setattr(module, "OAuthClientProvider", lambda *args, **kwargs: object())
    monkeypatch.setattr(module, "create_mcp_http_client", http_client)
    monkeypatch.setattr(module, "streamable_http_client", transport)
    monkeypatch.setattr(module, "ClientSession", Session)

    client = RobinhoodMCPClient(storage=object())  # type: ignore[arg-type]
    await client.open_async()
    await client.close_async()

    assert recorded == {"terminate_on_close": False}
