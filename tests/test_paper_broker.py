from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from broker.models import PaperOrder, Quote
from broker.paper import PaperBroker, ShadowExecution

NOW = datetime(2026, 9, 27, 14, 30, tzinfo=timezone.utc)


def quote(ticker: str = "VTI", bid: str = "100", ask: str = "101", age: int = 0) -> Quote:
    return Quote(
        ticker=ticker,
        bid=Decimal(bid),
        ask=Decimal(ask),
        timestamp=NOW - timedelta(seconds=age),
    )


def order(**changes: object) -> PaperOrder:
    values: dict[str, object] = {
        "client_order_id": "order-1",
        "ticker": "VTI",
        "asset_class": "etf",
        "side": "buy",
        "quantity": Decimal("2"),
        "limit_price": Decimal("101"),
    }
    values.update(changes)
    return PaperOrder.model_validate(values)


def test_marketable_buy_fills_at_ask_never_midpoint() -> None:
    broker = PaperBroker(Decimal("1000"), now=lambda: NOW)

    result = broker.submit(order(), quote())

    assert result.status == "filled"
    assert result.price == Decimal("101")
    assert broker.settled_cash == Decimal("798")
    assert broker.positions["VTI"].quantity == Decimal("2")


def test_marketable_sell_fills_at_bid_never_midpoint() -> None:
    broker = PaperBroker(Decimal("1000"), now=lambda: NOW)
    broker.submit(order(), quote())

    result = broker.submit(
        order(client_order_id="order-2", side="sell", quantity=Decimal("1"), limit_price=Decimal("99")),
        quote(bid="99", ask="100"),
    )

    assert result.status == "filled"
    assert result.price == Decimal("99")
    assert broker.positions["VTI"].quantity == Decimal("1")
    assert broker.unsettled_cash == Decimal("99")


def test_limit_order_waits_when_market_has_not_reached_price() -> None:
    broker = PaperBroker(Decimal("1000"), now=lambda: NOW)

    result = broker.submit(order(limit_price=Decimal("100")), quote())

    assert result.status == "pending"
    assert broker.settled_cash == Decimal("1000")


def test_pending_limit_order_fills_when_later_quote_reaches_price() -> None:
    broker = PaperBroker(Decimal("1000"), now=lambda: NOW)
    pending = broker.submit(order(limit_price=Decimal("100")), quote(bid="100", ask="101"))

    fills = broker.process_quote(quote(bid="99", ask="100"))

    assert pending.status == "pending"
    assert fills[0].status == "filled"
    assert fills[0].price == Decimal("100")
    assert broker.positions["VTI"].quantity == Decimal("2")


def test_stale_quote_rejects_order() -> None:
    broker = PaperBroker(Decimal("1000"), now=lambda: NOW, max_quote_age_seconds=60)

    result = broker.submit(order(), quote(age=61))

    assert result.status == "rejected"
    assert result.reason == "stale_quote"


def test_buy_uses_settled_cash_only() -> None:
    broker = PaperBroker(Decimal("100"), now=lambda: NOW)
    broker.unsettled_cash = Decimal("1000")

    result = broker.submit(order(quantity=Decimal("1")), quote())

    assert result.status == "rejected"
    assert result.reason == "insufficient_settled_cash"


def test_duplicate_client_order_id_is_rejected_without_second_fill() -> None:
    broker = PaperBroker(Decimal("1000"), now=lambda: NOW)
    first = broker.submit(order(), quote())

    second = broker.submit(order(), quote())

    assert first.status == "filled"
    assert second.status == "rejected"
    assert second.reason == "duplicate_order"
    assert broker.positions["VTI"].quantity == Decimal("2")


def test_shadow_execution_tracks_agent_alone_when_human_says_no() -> None:
    execution = ShadowExecution(
        agent_alone=PaperBroker(Decimal("1000"), now=lambda: NOW),
        with_approvals=PaperBroker(Decimal("1000"), now=lambda: NOW),
    )

    result = execution.execute_both_tracks(order(), quote(), human_decision="NO")

    assert result.agent_alone.status == "filled"
    assert result.with_approvals.status == "skipped"
    assert "VTI" in execution.agent_alone.positions
    assert "VTI" not in execution.with_approvals.positions


def option_order(client_id: str, strike: str) -> PaperOrder:
    return order(
        client_order_id=client_id,
        ticker=f"AAPL-C-{strike}",
        asset_class="option",
        quantity=Decimal("1"),
        limit_price=Decimal("2"),
        underlying_ticker="AAPL",
        option_type="call",
        strike=Decimal(strike),
        expiry=date(2026, 9, 27),
        multiplier=100,
    )


def test_itm_long_call_is_assigned_at_expiry() -> None:
    broker = PaperBroker(Decimal("20000"), now=lambda: NOW)
    broker.submit(option_order("call-itm", "100"), quote("AAPL-C-100", "1.90", "2"))

    events = broker.process_expirations(date(2026, 9, 27), {"AAPL": Decimal("110")})

    assert events[0].action == "assigned_call"
    assert broker.positions["AAPL"].quantity == Decimal("100")
    assert "AAPL-C-100" not in broker.positions
    assert broker.settled_cash == Decimal("9800")


def test_otm_option_expires_worthless() -> None:
    broker = PaperBroker(Decimal("20000"), now=lambda: NOW)
    broker.submit(option_order("call-otm", "120"), quote("AAPL-C-120", "1.90", "2"))

    events = broker.process_expirations(date(2026, 9, 27), {"AAPL": Decimal("110")})

    assert events[0].action == "expired_worthless"
    assert "AAPL-C-120" not in broker.positions
    assert "AAPL" not in broker.positions
