from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

Money = Annotated[Decimal, Field(decimal_places=8)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceItem(StrictModel):
    fact: Annotated[str, Field(min_length=1)]
    source_url: HttpUrl
    observed_at: datetime
    evidence_type: Literal["market", "news", "fundamental", "technical", "filing"]
    contains_instructions: bool = False

    @field_validator("observed_at")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value


class ResearchPacket(StrictModel):
    ticker: Annotated[str, Field(min_length=1)]
    as_of: datetime
    evidence: tuple[EvidenceItem, ...]

    @field_validator("as_of")
    @classmethod
    def as_of_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        return value


class CriticOutput(StrictModel):
    proposal_id: str
    counterargument: Annotated[str, Field(min_length=1)]


class TradeProposal(StrictModel):
    proposal_id: str
    account_id: str
    ticker: Annotated[str, Field(min_length=1)]
    asset_class: Literal["stock", "etf", "option", "crypto"]
    side: Literal["buy", "sell"]
    quantity: Annotated[Decimal, Field(gt=0)]
    order_type: Literal["limit", "market"] = "limit"
    limit_price: Annotated[Money, Field(gt=0)]
    thesis: Annotated[str, Field(min_length=1)]
    good_if: Annotated[str, Field(min_length=1)]
    horizon_days: Annotated[int, Field(gt=0)]
    confidence: Annotated[Decimal, Field(ge=0, le=1)]
    invalidation: Annotated[str, Field(min_length=1)]
    critic_counterargument: str | None = None
    evidence: tuple[EvidenceItem, ...] = ()
    prompt_versions: dict[str, str]
    model_name: str
    config_hash: Annotated[str, Field(min_length=64, max_length=64)]
    client_order_id: str | None = None
    is_closing: bool = False
    option_strategy: str | None = None
    max_loss_usd: Annotated[Money, Field(ge=0)] | None = None
    naked_short_call: bool = False
    underlying_ticker: str | None = None
    multiplier: Annotated[int, Field(gt=0)] = 1
    option_type: Literal['call', 'put'] | None = None
    strike: Annotated[Decimal, Field(gt=0)] | None = None
    expiry: date | None = None


class DecisionRecord(StrictModel):
    decision_id: str
    proposal: TradeProposal
    decided_at: datetime
    risk_status: Literal["allowed", "blocked", "would_have_blocked"]
    risk_reasons: tuple[str, ...]
    human_decision: Literal["YES", "NO", "EXPIRED"] | None = None
    prompt_versions: dict[str, str]
    model_name: str
    config_hash: Annotated[str, Field(min_length=64, max_length=64)]

    @field_validator("decided_at")
    @classmethod
    def decided_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("decided_at must be timezone-aware")
        return value
