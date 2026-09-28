from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class ValuationSnapshot:
    current_value: Decimal | None
    prior_market_close_value: Decimal | None
    prior_friday_close_value: Decimal | None
    peak_value: Decimal | None
    observed_at: datetime


@dataclass(frozen=True)
class RearmApproval:
    operator_approved: bool
    documented_review: bool
    reviewed_at: datetime


@dataclass(frozen=True)
class BreakerDecision:
    block_new_entries: bool
    codes: tuple[str, ...]
    global_kill_switch: bool

    @property
    def allows_entry(self) -> bool:
        return not self.block_new_entries

    def allows_exit(self, *, quantity: Decimal, held_quantity: Decimal) -> bool:
        return quantity > 0 and quantity <= held_quantity


class BreakerState:
    def __init__(
        self,
        *,
        global_kill_switch: bool | None,
        peak_drawdown_latched: bool = False,
    ) -> None:
        self.global_kill_switch = global_kill_switch
        self.peak_drawdown_latched = peak_drawdown_latched

    def evaluate(
        self,
        valuation: ValuationSnapshot,
        *,
        rearm: RearmApproval | None = None,
    ) -> BreakerDecision:
        values = (
            valuation.current_value,
            valuation.prior_market_close_value,
            valuation.prior_friday_close_value,
            valuation.peak_value,
        )
        if valuation.observed_at.tzinfo is None or any(
            value is None or not value.is_finite() or value <= 0 for value in values
        ):
            return BreakerDecision(True, ("VALUATION_UNAVAILABLE",), bool(self.global_kill_switch))

        current, prior_close, prior_friday, peak = values
        daily_loss = (prior_close - current) / prior_close
        weekly_loss = (prior_friday - current) / prior_friday
        drawdown = (peak - current) / peak
        codes: list[str] = []

        if self.global_kill_switch is None:
            codes.append("GLOBAL_KILL_SWITCH_UNKNOWN")
        elif self.global_kill_switch:
            codes.append("GLOBAL_KILL_SWITCH")
        if daily_loss >= Decimal("0.03"):
            codes.append("DAILY_LOSS_BREAKER")
        if weekly_loss >= Decimal("0.05"):
            codes.append("WEEKLY_LOSS_BREAKER")
        if drawdown >= Decimal("0.10"):
            self.peak_drawdown_latched = True
        if drawdown >= Decimal("0.15"):
            self.global_kill_switch = True
            codes.append("HARD_DRAWDOWN_LOCK")

        if self.peak_drawdown_latched:
            if (
                rearm is not None
                and rearm.operator_approved
                and rearm.documented_review
                and rearm.reviewed_at.tzinfo is not None
            ):
                self.peak_drawdown_latched = False
            else:
                codes.append("PEAK_TO_TROUGH_BREAKER")
        return BreakerDecision(bool(codes), tuple(dict.fromkeys(codes)), bool(self.global_kill_switch))
