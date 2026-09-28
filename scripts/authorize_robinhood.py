from __future__ import annotations

import argparse
import asyncio
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

from mcp.shared.auth import AuthorizationCodeResult

from broker_proxy.mcp_client import ROBINHOOD_MCP_URL, RobinhoodMCPClient
from broker_proxy.identity import require_proxy_identity
from broker_proxy.oauth import KeychainOAuthStorage, OAuthUnavailable, authorization_evidence


class _CallbackServer:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._result: AuthorizationCodeResult | None = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlsplit(self.path)
                if parsed.path != "/callback":
                    self.send_error(404)
                    return
                values = parse_qs(parsed.query)
                code = values.get("code", [None])[0]
                if code:
                    owner._result = AuthorizationCodeResult(
                        code=code,
                        state=values.get("state", [None])[0],
                        iss=values.get("iss", [None])[0],
                    )
                    response = b"Authorization received. You may close this tab."
                    self.send_response(200)
                else:
                    response = b"Authorization was not completed."
                    self.send_response(400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)
                owner._event.set()

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = HTTPServer(("127.0.0.1", 9876), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    async def redirect(self, authorization_url: str) -> None:
        if not self._thread.is_alive():
            self._thread.start()
        opened = await asyncio.to_thread(webbrowser.open, authorization_url, 1, True)
        if not opened:
            raise OAuthUnavailable("the system browser could not be opened")

    async def callback(self) -> AuthorizationCodeResult:
        received = await asyncio.to_thread(self._event.wait, 300)
        self._server.shutdown()
        self._server.server_close()
        if not received or self._result is None:
            raise OAuthUnavailable("Robinhood authorization timed out")
        return self._result


async def _authorize() -> dict[str, object]:
    handlers = _CallbackServer()
    storage = KeychainOAuthStorage()
    client = RobinhoodMCPClient(
        storage=storage,
        redirect_handler=handlers.redirect,
        callback_handler=handlers.callback,
    )
    await client.open_async(interactive=True)
    try:
        tokens = await storage.get_tokens()
        if tokens is None:
            raise OAuthUnavailable("authorization completed without stored tokens")
        return {
            "endpoint": ROBINHOOD_MCP_URL,
            **authorization_evidence(tokens, keychain_available=True),
        }
    finally:
        await client.close_async()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Authorize the local read-only shadow application with Robinhood."
    )
    parser.parse_args()
    try:
        require_proxy_identity()
    except RuntimeError as error:
        print(json.dumps({"status": "FAILED", "error": str(error)}, sort_keys=True))
        return 2
    try:
        evidence = asyncio.run(_authorize())
    except OAuthUnavailable as error:
        print(json.dumps({"status": "FAILED", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"status": "AUTHORIZED", **evidence}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
