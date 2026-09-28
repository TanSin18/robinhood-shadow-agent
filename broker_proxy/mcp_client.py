from __future__ import annotations

from concurrent.futures import Future
from contextlib import AsyncExitStack
from queue import Queue
from threading import Event
from typing import Any, Awaitable, Callable

import anyio
from anyio.from_thread import start_blocking_portal
from mcp import ClientSession, types
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientMetadata

from broker_proxy.oauth import (
    KeychainOAuthStorage,
    OAuthUnavailable,
    authorization_evidence,
    require_noninteractive_tokens,
)
from broker.policy import Stage1ToolPolicy


ROBINHOOD_MCP_URL = "https://agent.robinhood.com/mcp/trading"
ROBINHOOD_CALLBACK_URL = "http://127.0.0.1:9876/callback"


class MCPProtocolError(RuntimeError):
    pass


class RobinhoodMCPClient:
    """Persistent application-owned MCP session authenticated through OAuth."""

    def __init__(
        self,
        *,
        server_url: str = ROBINHOOD_MCP_URL,
        storage: KeychainOAuthStorage | None = None,
        redirect_handler: Callable[[str], Awaitable[None]] | None = None,
        callback_handler: Callable[[], Awaitable[AuthorizationCodeResult]] | None = None,
    ) -> None:
        if server_url != ROBINHOOD_MCP_URL:
            raise ValueError("official mode requires the official Robinhood MCP endpoint")
        self.server_url = server_url
        self.storage = storage or KeychainOAuthStorage()
        self.redirect_handler = redirect_handler
        self.callback_handler = callback_handler
        self._stack: AsyncExitStack | None = None
        self._session: Any | None = None
        self._portal_context = None
        self._portal = None
        self._owner_future: Future[None] | None = None
        self._sync_commands: Queue[tuple[str, Any, Future[Any]]] | None = None
        self._sync_open_error: BaseException | None = None

    @classmethod
    def for_testing(cls, session: Any) -> "RobinhoodMCPClient":
        instance = cls.__new__(cls)
        instance.server_url = ROBINHOOD_MCP_URL
        instance.storage = None
        instance.redirect_handler = None
        instance.callback_handler = None
        instance._stack = None
        instance._session = session
        instance._portal_context = None
        instance._portal = None
        instance._owner_future = None
        instance._sync_commands = None
        instance._sync_open_error = None
        return instance

    async def open_async(self, *, interactive: bool = False) -> None:
        if self._session is not None:
            return
        if not interactive:
            await require_noninteractive_tokens(self.storage)
        elif self.redirect_handler is None or self.callback_handler is None:
            raise OAuthUnavailable("interactive OAuth handlers are not configured")

        metadata = OAuthClientMetadata(
            client_name="Robinhood Shadow Research",
            redirect_uris=[ROBINHOOD_CALLBACK_URL],
            token_endpoint_auth_method="none",
            scope="internal",
        )
        auth = OAuthClientProvider(
            self.server_url,
            metadata,
            self.storage,
            redirect_handler=self.redirect_handler,
            callback_handler=self.callback_handler,
        )
        stack = AsyncExitStack()
        try:
            http_client = await stack.enter_async_context(create_mcp_http_client(auth=auth))
            read_stream, write_stream = await stack.enter_async_context(
                streamable_http_client(
                    self.server_url,
                    http_client=http_client,
                    terminate_on_close=False,
                )
            )
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
        except OAuthUnavailable:
            await stack.aclose()
            raise
        except Exception:
            await stack.aclose()
            raise OAuthUnavailable("AUTH_REFRESH_FAILED") from None
        self._stack = stack
        self._session = session

    def open(self, *, interactive: bool = False) -> "RobinhoodMCPClient":
        if self._portal is not None:
            return self
        context = start_blocking_portal(backend="asyncio")
        portal = context.__enter__()
        ready = Event()
        self._sync_commands = Queue()
        self._sync_open_error = None
        try:
            owner_future = portal.start_task_soon(self._sync_owner, interactive, ready)
            self._owner_future = owner_future
            ready.wait()
            if self._sync_open_error is not None:
                raise self._sync_open_error
        except BaseException:
            context.__exit__(None, None, None)
            self._owner_future = None
            self._sync_commands = None
            raise
        self._portal_context = context
        self._portal = portal
        return self

    async def _sync_owner(self, interactive: bool, ready: Event) -> None:
        close_reply: Future[Any] | None = None
        try:
            await self.open_async(interactive=interactive)
        except BaseException as exc:
            self._sync_open_error = exc
            ready.set()
            return
        ready.set()

        try:
            while True:
                commands = self._sync_commands
                if commands is None:
                    raise MCPProtocolError("MCP command channel is unavailable")
                command, payload, reply = await anyio.to_thread.run_sync(commands.get)
                if command == "close":
                    close_reply = reply
                    break
                try:
                    if command == "list_remote_tools":
                        result = await self.list_remote_tools_async()
                    elif command == "call_read":
                        name, arguments = payload
                        result = await self.call_read_async(name, arguments)
                    elif command == "authorization_evidence":
                        result = await self.authorization_evidence_async()
                    else:
                        raise MCPProtocolError("unknown MCP client command")
                except BaseException as exc:
                    reply.set_exception(exc)
                else:
                    reply.set_result(result)
        finally:
            try:
                await self.close_async()
            except BaseException as exc:
                if close_reply is not None:
                    close_reply.set_exception(exc)
                else:
                    raise
            else:
                if close_reply is not None:
                    close_reply.set_result(None)

    def _sync_request(self, command: str, payload: Any = None) -> Any:
        if self._portal is None or self._sync_commands is None:
            raise MCPProtocolError("MCP client is not open")
        reply: Future[Any] = Future()
        self._sync_commands.put((command, payload, reply))
        return reply.result()

    async def list_remote_tools_async(self) -> list[Any]:
        session = self._require_session()
        cursor: str | None = None
        seen: set[str] = set()
        collected: list[Any] = []
        while True:
            params = types.PaginatedRequestParams(cursor=cursor) if cursor else None
            page = await session.list_tools(params=params)
            collected.extend(page.tools)
            next_cursor = getattr(page, "nextCursor", None)
            if not next_cursor:
                return collected
            if next_cursor in seen:
                raise MCPProtocolError("remote catalog returned a repeated pagination cursor")
            seen.add(next_cursor)
            cursor = next_cursor

    async def call_read_async(self, name: str, arguments: dict[str, Any]) -> Any:
        Stage1ToolPolicy().authorize(name)
        if self.storage is not None:
            await require_noninteractive_tokens(self.storage)
        session = self._require_session()
        return await session.call_tool(
            name,
            arguments,
            allow_input_required=False,
            allow_claimed=False,
        )

    def list_remote_tools(self) -> list[Any]:
        return self._sync_request("list_remote_tools")

    def call_read(self, name: str, arguments: dict[str, Any]) -> Any:
        return self._sync_request("call_read", (name, arguments))

    async def authorization_evidence_async(self) -> dict[str, object]:
        tokens = await require_noninteractive_tokens(self.storage)
        status = self.storage.authorization_status()
        return {
            **authorization_evidence(tokens, keychain_available=True),
            "authorization": {
                key: status[key]
                for key in ("status", "expires_at", "warning_threshold", "authorization_id")
            },
        }

    def authorization_evidence(self) -> dict[str, object]:
        return self._sync_request("authorization_evidence")

    async def close_async(self) -> None:
        stack, self._stack = self._stack, None
        self._session = None
        if stack is not None:
            await stack.aclose()

    def close(self) -> None:
        try:
            if self._portal is not None:
                self._sync_request("close")
            if self._owner_future is not None:
                self._owner_future.result()
        finally:
            if self._portal_context is not None:
                self._portal_context.__exit__(None, None, None)
            self._portal = None
            self._portal_context = None
            self._owner_future = None
            self._sync_commands = None

    def _require_session(self):
        if self._session is None:
            raise MCPProtocolError("MCP client is not open")
        return self._session

    def __enter__(self) -> "RobinhoodMCPClient":
        return self.open()

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
