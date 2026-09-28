from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import uuid4

import keyring
from mcp.client.auth import TokenStorage
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


KEYCHAIN_SERVICE = "com.openai.robinhood-shadow.oauth"


class OAuthUnavailable(RuntimeError):
    """A secret-free OAuth failure suitable for logs and the dashboard."""


class KeychainBackend(Protocol):
    def get_password(self, service: str, account: str) -> str | None: ...

    def set_password(self, service: str, account: str, value: str) -> None: ...

    def delete_password(self, service: str, account: str) -> None: ...


class KeychainOAuthStorage(TokenStorage):
    """Persist MCP OAuth state only in the operating-system credential store."""

    def __init__(
        self,
        *,
        service: str = KEYCHAIN_SERVICE,
        backend: KeychainBackend = keyring,
        clock=None,
    ) -> None:
        if not service or len(service) > 128:
            raise ValueError("OAuth Keychain service is invalid")
        self.service = service
        self._backend = backend
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _get(self, account: str, model_type):
        try:
            encoded = self._backend.get_password(self.service, account)
            if encoded is None:
                return None
            return model_type.model_validate_json(encoded)
        except Exception:
            label = "tokens" if account == "tokens" else "client information"
            raise OAuthUnavailable(f"stored OAuth {label} are invalid") from None

    def _set(self, account: str, value) -> None:
        try:
            encoded = value.model_dump_json(exclude_none=True)
            self._backend.set_password(self.service, account, encoded)
        except Exception:
            label = "tokens" if account == "tokens" else "client information"
            raise OAuthUnavailable(f"OAuth {label} could not be stored in Keychain") from None

    async def get_tokens(self) -> OAuthToken | None:
        return self._get("tokens", OAuthToken)

    async def set_tokens(self, tokens: OAuthToken) -> None:
        if type(tokens.expires_in) is not int or tokens.expires_in <= 0:
            raise OAuthUnavailable("OAuth token expiry is invalid")
        stored_at = self.clock()
        if stored_at.tzinfo is None:
            raise OAuthUnavailable("OAuth token clock is invalid")
        timing = {
            "stored_at": stored_at.isoformat(),
            "expires_at": (stored_at + timedelta(seconds=tokens.expires_in)).isoformat(),
            "authorization_id": uuid4().hex,
        }
        try:
            self._backend.set_password(
                self.service, "token_timing", json.dumps(timing, sort_keys=True)
            )
        except Exception:
            raise OAuthUnavailable("OAuth timing metadata could not be stored in Keychain") from None
        self._set("tokens", tokens)

    def authorization_status(self, now: datetime | None = None) -> dict[str, object]:
        now = now or self.clock()
        if now.tzinfo is None:
            raise OAuthUnavailable("OAuth token clock is invalid")
        try:
            encoded = self._backend.get_password(self.service, "token_timing")
            timing = json.loads(encoded) if encoded else None
            if not isinstance(timing, dict):
                raise ValueError()
            stored_at = datetime.fromisoformat(timing["stored_at"])
            expires_at = datetime.fromisoformat(timing["expires_at"])
            authorization_id = timing["authorization_id"]
            if (
                stored_at.tzinfo is None or expires_at.tzinfo is None
                or not isinstance(authorization_id, str) or len(authorization_id) != 32
                or expires_at <= stored_at
            ):
                raise ValueError()
        except Exception:
            raise OAuthUnavailable("stored OAuth timing metadata are invalid") from None
        remaining = expires_at - now
        if remaining <= timedelta(0):
            status = "EXPIRED"
            threshold = "expired"
        elif remaining <= timedelta(days=1):
            status = "WARNING_1_DAY"
            threshold = "1_day"
        elif remaining <= timedelta(days=3):
            status = "WARNING_3_DAYS"
            threshold = "3_days"
        else:
            status = "VALID"
            threshold = None
        return {
            "status": status,
            "stored_at": stored_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "authorization_id": authorization_id,
            "warning_threshold": threshold,
        }

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self._get("client_info", OAuthClientInformationFull)

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._set("client_info", client_info)

    def credentials_absent(self) -> bool:
        try:
            return all(self._backend.get_password(self.service, account) is None
                       for account in ('tokens', 'token_timing', 'client_info'))
        except Exception:
            raise OAuthUnavailable('OAuth credential removal could not be verified') from None

    def delete_tokens_and_client_info(self) -> None:
        for account in ("tokens", "token_timing", "client_info"):
            try:
                self._backend.delete_password(self.service, account)
            except Exception:
                # Missing entries are acceptable; any backend that cannot delete
                # must fail rather than claim the local credential removal step.
                try:
                    if self._backend.get_password(self.service, account) is not None:
                        raise OAuthUnavailable("OAuth credentials could not be deleted")
                except OAuthUnavailable:
                    raise
                except Exception:
                    raise OAuthUnavailable("OAuth credentials could not be deleted") from None


async def require_noninteractive_tokens(storage: TokenStorage) -> OAuthToken:
    tokens = await storage.get_tokens()
    if tokens is None or not tokens.access_token:
        raise OAuthUnavailable(
            "Robinhood authorization is required; run the interactive authorization step"
        )
    status_method = getattr(storage, "authorization_status", None)
    if status_method is not None and status_method()["status"] == "EXPIRED":
        raise OAuthUnavailable("AUTH_EXPIRED")
    return tokens


def classify_granted_scope(scope: str | None) -> str:
    scopes = {item.casefold() for item in (scope or "").split() if item}
    if "internal" in scopes:
        return "full_scope_bounded_cash_fallback"
    if scopes & {"read", "readonly", "read-only"}:
        return "provider_read_only_scope"
    raise OAuthUnavailable("Robinhood returned an unsupported OAuth scope")


def authorization_evidence(tokens: OAuthToken, *, keychain_available: bool) -> dict[str, object]:
    """Return a deliberately secret-free authorization receipt."""

    scopes = sorted({item for item in (tokens.scope or "").split() if item})
    return {
        "granted_scope_names": scopes,
        "selected_path": classify_granted_scope(tokens.scope),
        "keychain_retrieval": "available" if keychain_available else "unavailable",
    }
