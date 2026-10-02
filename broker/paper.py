from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal

from broker.models import (
    ExpiryEvent,
    FillResult,
    PaperOrder,
    Position,
    Quote,
    ShadowFillResult,
)


class PaperBroker:
    def __init__(
        self,
        starting_cash: Decimal,
        *,
        now: Callable[[], datetime] | None = None,
        max_quote_age_seconds: int = 60,
        track: str = "paper",
        slippage: Decimal = Decimal("0"),
    ) -> None:
        if starting_cash <= 0:
            raise ValueError("starting cash must be positive")
        if not Decimal("0") <= slippage < Decimal("0.01"):
            raise ValueError("slippage must be a small non-negative fraction")
        self.slippage = Decimal(slippage)
        self.settled_cash = Decimal(starting_cash)
        self.unsettled_cash = Decimal("0")
        self.positions: dict[str, Position] = {}
        self._seen_ids: set[str] = set()
        self._pending: dict[str, PaperOrder] = {}
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.max_quote_age_seconds = max_quote_age_seconds
        self.track = track

    def submit(self, order: PaperOrder, quote: Quote) -> FillResult:
        if order.client_order_id in self._seen_ids:
            return self._result(order, "rejected", reason="duplicate_order")
        self._seen_ids.add(order.client_order_id)

        age = (self._now() - quote.timestamp).total_seconds()
        if age < 0 or age > self.max_quote_age_seconds:
            return self._result(order, "rejected", reason="stale_quote")
        if quote.halted:
            return self._result(order, "rejected", reason="halted_ticker")

        # Modeled slippage (v1.7): a buy pays a little above the ask, a sale receives a little below the bid.
        # A buy must still fit inside its limit; a closing sale at the bid is treated as marketable.
        touch = quote.ask if order.side == "buy" else quote.bid
        price = touch * (1 + self.slippage) if order.side == "buy" else touch * (1 - self.slippage)
        market_reached = (
            order.limit_price >= price
            if order.side == "buy"
            else order.limit_price <= quote.bid
        )
        if not market_reached:
            self._pending[order.client_order_id] = order
            return self._result(order, "pending", reason="limit_not_reached")

        units = order.quantity * Decimal(order.multiplier)
        notional = price * units
        midpoint = (quote.bid + quote.ask) / Decimal("2")
        spread_cost = abs(price - midpoint) * units
        slippage_cost = abs(price - touch) * units

        if order.side == "buy":
            if notional > self.settled_cash:
                return self._result(
                    order, "rejected", reason="insufficient_settled_cash"
                )
            self.settled_cash -= notional
            self._add_position(order, price)
        else:
            position = self.positions.get(order.ticker)
            if position is None or position.quantity < order.quantity:
                return self._result(order, "rejected", reason="insufficient_position")
            remaining = position.quantity - order.quantity
            if remaining == 0:
                del self.positions[order.ticker]
            else:
                self.positions[order.ticker] = position.model_copy(
                    update={"quantity": remaining}
                )
            self.unsettled_cash += notional

        return self._result(
            order, "filled", price=price, spread_cost=spread_cost, slippage_cost=slippage_cost
        )

    def process_quote(self, quote: Quote) -> tuple[FillResult, ...]:
        """Re-evaluate resting limit orders against a new point-in-time quote."""
        results: list[FillResult] = []
        for client_order_id, pending in list(self._pending.items()):
            if pending.ticker != quote.ticker:
                continue
            del self._pending[client_order_id]
            self._seen_ids.remove(client_order_id)
            results.append(self.submit(pending, quote))
        return tuple(results)

    def _add_position(self, order: PaperOrder, price: Decimal) -> None:
        existing = self.positions.get(order.ticker)
        if existing is None:
            self.positions[order.ticker] = Position(
                ticker=order.ticker,
                asset_class=order.asset_class,
                quantity=order.quantity,
                average_cost=price,
                underlying_ticker=order.underlying_ticker,
                option_type=order.option_type,
                strike=order.strike,
                expiry=order.expiry,
                multiplier=order.multiplier,
            )
            return
        total_quantity = existing.quantity + order.quantity
        weighted_cost = (
            existing.average_cost * existing.quantity + price * order.quantity
        ) / total_quantity
        self.positions[order.ticker] = existing.model_copy(
            update={"quantity": total_quantity, "average_cost": weighted_cost}
        )

    def _result(
        self,
        order: PaperOrder,
        status: str,
        *,
        price: Decimal | None = None,
        reason: str | None = None,
        spread_cost: Decimal = Decimal("0"),
        slippage_cost: Decimal = Decimal("0"),
    ) -> FillResult:
        return FillResult(
            client_order_id=order.client_order_id,
            ticker=order.ticker,
            status=status,
            quantity=order.quantity,
            price=price,
            reason=reason,
            spread_cost=spread_cost,
            slippage_cost=slippage_cost,
            track=self.track,
        )

    def process_expirations(
        self, as_of: date, underlying_prices: dict[str, Decimal]
    ) -> tuple[ExpiryEvent, ...]:
        events: list[ExpiryEvent] = []
        for ticker, position in list(self.positions.items()):
            if position.asset_class != "option" or position.expiry is None:
                continue
            if position.expiry > as_of:
                continue
            underlying = position.underlying_ticker
            if underlying is None or position.strike is None or position.option_type is None:
                events.append(ExpiryEvent(ticker=ticker, action="invalid_contract", quantity=position.quantity))
                del self.positions[ticker]
                continue
            spot = underlying_prices[underlying]
            itm = (
                spot > position.strike
                if position.option_type == "call"
                else spot < position.strike
            )
            if not itm:
                events.append(ExpiryEvent(ticker=ticker, action="expired_worthless", quantity=position.quantity))
                del self.positions[ticker]
                continue
            shares = position.quantity * Decimal(position.multiplier)
            if position.option_type == "call":
                assignment_cost = position.strike * shares
                if assignment_cost <= self.settled_cash:
                    self.settled_cash -= assignment_cost
                    synthetic = PaperOrder(
                        client_order_id=f"assignment:{ticker}:{as_of.isoformat()}",
                        ticker=underlying,
                        asset_class="stock",
                        side="buy",
                        quantity=shares,
                        limit_price=position.strike,
                    )
                    self._add_position(synthetic, position.strike)
                    action = "assigned_call"
                else:
                    action = "assignment_failed_insufficient_settled_cash"
            else:
                underlying_position = self.positions.get(underlying)
                if underlying_position and underlying_position.quantity >= shares:
                    remaining = underlying_position.quantity - shares
                    if remaining:
                        self.positions[underlying] = underlying_position.model_copy(update={"quantity": remaining})
                    else:
                        del self.positions[underlying]
                    self.unsettled_cash += position.strike * shares
                    action = "assigned_put"
                else:
                    action = "assignment_failed_insufficient_shares"
            events.append(ExpiryEvent(ticker=ticker, action=action, quantity=position.quantity))
            del self.positions[ticker]
        return tuple(events)

    def settle_cash(self) -> None:
        self.settled_cash += self.unsettled_cash
        self.unsettled_cash = Decimal("0")

    def portfolio_value(self, quotes: dict[str, Quote]) -> Decimal:
        value = self.settled_cash + self.unsettled_cash
        for ticker, position in self.positions.items():
            value += (
                quotes[ticker].bid
                * position.quantity
                * Decimal(position.multiplier)
            )
        return value


class ShadowExecution:
    def __init__(self, agent_alone: PaperBroker, with_approvals: PaperBroker) -> None:
        self.agent_alone = agent_alone
        self.with_approvals = with_approvals

    def execute_both_tracks(
        self,
        order: PaperOrder,
        quote: Quote,
        *,
        human_decision: str,
    ) -> ShadowFillResult:
        agent_result = self.agent_alone.submit(order, quote)
        if human_decision == "YES":
            approval_result = self.with_approvals.submit(order, quote)
        else:
            approval_result = FillResult(
                client_order_id=order.client_order_id,
                ticker=order.ticker,
                status="skipped",
                quantity=order.quantity,
                reason="human_no_or_expired",
                track=self.with_approvals.track,
            )
        return ShadowFillResult(
            agent_alone=agent_result, with_approvals=approval_result
        )
