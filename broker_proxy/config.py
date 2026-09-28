from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class BrokerProxyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    server_url: Literal["https://agent.robinhood.com/mcp/trading"]
    callback_url: Literal["http://127.0.0.1:9876/callback"]
    keychain_service: Literal["com.openai.robinhood-shadow.oauth"]
    requested_scope: Literal["internal"]
    socket_path: Path
    proxy_user: Literal["robinhoodproxy"]
    socket_group: Literal["robinhoodreaders"]
    operator_uid: int = Field(gt=0)


def load_broker_proxy_config(
    path: str | Path, *, operator_uid: int | None = None
) -> BrokerProxyConfig:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError("broker proxy configuration must be a mapping")
    if operator_uid is not None:
        raw = {**raw, "operator_uid": operator_uid}
    return BrokerProxyConfig.model_validate(raw)
