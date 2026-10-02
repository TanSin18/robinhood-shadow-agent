from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Quote(FrozenModel):
    ticker: str
    bid: Decimal = Field(gt=0)
    ask: Decimal = Field(gt=0)
    timestamp: datetime
    halted: bool = False

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("quote timestamp must be timezone-aware")
        return value


class PaperOrder(FrozenModel):
    client_order_id: str
    ticker: str
    asset_class: Literal["stock", "etf", "option", "crypto"]
    side: Literal["buy", "sell"]
    quantity: Decimal = Field(gt=0)
    limit_price: Decimal = Field(gt=0)
    underlying_ticker: str | None = None
    option_type: Literal["call", "put"] | None = None
    strike: Decimal | None = None
    expiry: date | None = None
    multiplier: int = 1


class FillResult(FrozenModel):
    client_order_id: str
    ticker: str
    status: Literal["filled", "pending", "rejected", "skipped"]
    quantity: Decimal
    price: Decimal | None = None
    reason: str | None = None
    spread_cost: Decimal = Decimal("0")
    slippage_cost: Decimal = Decimal("0")
    track: str = "paper"


class Position(FrozenModel):
    ticker: str
    asset_class: Literal["stock", "etf", "option", "crypto"]
    quantity: Decimal
    average_cost: Decimal
    underlying_ticker: str | None = None
    option_type: Literal["call", "put"] | None = None
    strike: Decimal | None = None
    expiry: date | None = None
    multiplier: int = 1


class ExpiryEvent(FrozenModel):
    ticker: str
    action: str
    quantity: Decimal


class ShadowFillResult(FrozenModel):
    agent_alone: FillResult
    with_approvals: FillResult

