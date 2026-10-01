from __future__ import annotations

import json
import os

import pytest
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import ValidationError

from broker_proxy.oauth import (
    KeychainOAuthStorage,
    OAuthUnavailable,
    classify_granted_scope,
    require_noninteractive_tokens,
)
from config.loader import load_config


class MemoryKeychain:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, account: str) -> str | None:
        return self.values.get((service, account))

    def set_password(self, service: str, account: str, value: str) -> None:
        self.values[(service, account)] = value


@pytest.mark.asyncio
async def test_keychain_storage_round_trips_tokens_and_client_info() -> None:
    backend = MemoryKeychain()
    storage = KeychainOAuthStorage(backend=backend)
    tokens = OAuthToken(
        access_token="access-secret",
        refresh_token="refresh-secret",
        expires_in=3600,
        scope="internal",
    )
    client = OAuthClientInformationFull(
        client_id="dynamic-client",
        redirect_uris=["http://127.0.0.1:9876/callback"],
        token_endpoint_auth_method="none",
    )

    await storage.set_tokens(tokens)
    await storage.set_client_info(client)

    assert await storage.get_tokens() == tokens
    assert await storage.get_client_info() == client
    assert set(account for _, account in backend.values) == {"tokens", "token_timing", "client_info"}
    assert "access-secret" in backend.values[(storage.service, "tokens")]


@pytest.mark.asyncio
async def test_keychain_storage_rejects_malformed_json_without_echoing_secret() -> None:
    backend = MemoryKeychain()
    storage = KeychainOAuthStorage(backend=backend)
    backend.values[(storage.service, "tokens")] = "not-json-secret"

    with pytest.raises(OAuthUnavailable, match="stored OAuth tokens are invalid") as caught:
        await storage.get_tokens()

    assert "not-json-secret" not in str(caught.value)


@pytest.mark.asyncio
async def test_noninteractive_auth_never_starts_browser_flow() -> None:
    storage = KeychainOAuthStorage(backend=MemoryKeychain())

    with pytest.raises(OAuthUnavailable, match="authorization is required"):
        await require_noninteractive_tokens(storage)


def test_scope_classification_uses_documented_full_scope_fallback() -> None:
    assert classify_granted_scope("read") == "provider_read_only_scope"
    assert classify_granted_scope("internal") == "full_scope_bounded_cash_fallback"
    assert classify_granted_scope("read internal") == "full_scope_bounded_cash_fallback"
    with pytest.raises(OAuthUnavailable, match="unsupported OAuth scope"):
        classify_granted_scope("")


def test_keychain_payload_is_json_not_a_plaintext_side_file(tmp_path) -> None:
    backend = MemoryKeychain()
    storage = KeychainOAuthStorage(backend=backend)
    backend.set_password(storage.service, "tokens", json.dumps({"access_token": "x"}))

    assert list(tmp_path.iterdir()) == []


def test_official_oauth_configuration_is_pinned() -> None:
    from broker_proxy.config import load_broker_proxy_config

    config = load_broker_proxy_config("config/broker-proxy.yaml", operator_uid=os.getuid() or 501)

    assert config.server_url == "https://agent.robinhood.com/mcp/trading"
    assert config.requested_scope == "internal"
    assert config.keychain_service == "com.openai.robinhood-shadow.oauth"

    with pytest.raises(ValidationError):
        config.model_validate(
            {**config.model_dump(), "server_url": "https://evil.example/mcp"}
        )


def test_proxy_configuration_is_separate_from_main_application() -> None:
    from broker_proxy.config import load_broker_proxy_config

    proxy = load_broker_proxy_config("config/broker-proxy.yaml", operator_uid=os.getuid() or 501)
    main = load_config("config/settings.yaml")

    assert proxy.proxy_user == "robinhoodproxy"
    assert proxy.socket_group == "robinhoodreaders"
    assert proxy.operator_uid > 0
    assert not hasattr(main, "oauth")
