from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RiskReason(str, Enum):
    INVALID_MULTIPLIER = 'invalid_multiplier'
    MISSING_POSITION_MARK = 'missing_position_mark'
    INSUFFICIENT_POSITION = 'insufficient_position'
    INVALID_CLOSING = 'invalid_closing'
    INSUFFICIENT_SETTLED_CASH = 'insufficient_settled_cash'
    INVALID_REALIZED_VOLATILITY = 'invalid_realized_volatility'
    VOLATILITY_SIZE_LIMIT = 'volatility_size_limit'
    WRONG_ACCOUNT = "wrong_account"
    NOT_WHITELISTED = "not_whitelisted"
    LIMIT_ONLY = "limit_only"
    STALE_QUOTE = "stale_quote"
    LIMIT_TOO_FAR = "limit_too_far"
    POSITION_TOO_LARGE = "position_too_large"
    TOO_MANY_POSITIONS = "too_many_positions"
    OPTIONS_LOCKED = "options_locked"
    OPTION_NOT_DEFINED_RISK = "option_not_defined_risk"
    NAKED_SHORT_CALL = "naked_short_call"
    DAILY_ORDER_LIMIT = "daily_order_limit"
    SAME_DAY_ROUND_TRIP = "same_day_round_trip"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    DRAWDOWN_BUY_BLOCK = "drawdown_buy_block"
    DRAWDOWN_LOCK = "drawdown_lock"
    DUPLICATE_ORDER = "duplicate_order"
    AUTO_APPROVE_FORBIDDEN = "auto_approve_forbidden"
    KILL_SWITCH = "kill_switch"
    INJECTED_INSTRUCTIONS = "injected_instructions"


class RiskContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    now: datetime
    stage: Literal[1, 2, 3]
    quote_timestamp: datetime
    bid: Decimal
    ask: Decimal
    account_value: Decimal
    current_value: Decimal
    peak_value: Decimal
    daily_pnl: Decimal
    settled_cash: Decimal
    position_values: dict[str, Decimal]
    position_quantities: dict[str, Decimal] = Field(default_factory=dict)
    realized_volatility_20d: Decimal | None = None
    volatility_as_of: datetime | None = None
    open_position_count: int
    orders_today: int
    traded_sides_today: dict[str, frozenset[str]]
    seen_client_order_ids: frozenset[str]
    kill_switch: bool
    manually_unlocked_after_drawdown: bool
    auto_approve_requested: bool
    missing_position_marks: tuple[str, ...] = ()

    @field_validator("now", "quote_timestamp")
    @classmethod
    def timestamps_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("risk timestamps must be timezone-aware")
        return value


class RiskVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool
    status: Literal["allowed", "blocked", "would_have_blocked"]
    reasons: tuple[RiskReason, ...]
    actions: tuple[str, ...] = ()
