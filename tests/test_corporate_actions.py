from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from data.corporate_actions import (
    CorporateActionError,
    normalize_live_quote,
    normalize_live_security,
)


NOW = datetime(2026, 9, 28, 14, tzinfo=timezone.utc)


def _record(**changes):
    return {
        "permanent_security_id": "security-1",
        "symbol": "OLD",
        "price": Decimal("100"),
        "quantity": Decimal("10"),
        "volume": Decimal("1000"),
        "cost_basis": Decimal("80"),
        "option_deliverable": {"strike": Decimal("100"), "multiplier": Decimal("100")},
        **changes,
    }


def _action(kind, **changes):
    return {
        "kind": kind,
        "permanent_security_id": "security-1",
        "announcement_at": NOW - timedelta(days=10),
        "known_at": NOW - timedelta(days=10),
        "effective_at": NOW - timedelta(days=1),
        "source_id": "issuer-action-feed",
        "content_hash": "a" * 64,
        **changes,
    }


@pytest.mark.parametrize(
    ("ratio", "price", "quantity", "strike", "multiplier"),
    [
        (Decimal("4"), Decimal("25"), Decimal("40"), Decimal("25"), Decimal("400")),
        (Decimal("0.1"), Decimal("1000"), Decimal("1"), Decimal("1000"), Decimal("10")),
    ],
)
def test_split_and_reverse_split_normalize_every_live_value(
    ratio, price, quantity, strike, multiplier
):
    result = normalize_live_security(_record(), [_action("split", ratio=ratio)], known_at=NOW)

    assert result.record["price"] == price
    assert result.record["quantity"] == quantity
    assert result.record["volume"] == Decimal("1000") * ratio
    assert result.record["cost_basis"] == Decimal("80") / ratio
    assert result.record["option_deliverable"] == {
        "strike": strike,
        "multiplier": multiplier,
    }
    assert result.audit[0]["adjustment_factor"] == str(ratio)


def test_ticker_change_preserves_permanent_identity() -> None:
    result = normalize_live_security(
        _record(),
        [_action("ticker_change", old_symbol="OLD", new_symbol="NEW")],
        known_at=NOW,
    )
    assert result.record["symbol"] == "NEW"
    assert result.record["permanent_security_id"] == "security-1"


def test_future_known_action_is_not_applied() -> None:
    result = normalize_live_security(
        _record(),
        [_action("split", ratio=Decimal("4"), known_at=NOW + timedelta(minutes=1))],
        known_at=NOW,
    )
    assert result.record == _record()
    assert result.audit == []


@pytest.mark.parametrize(
    "action",
    [
        _action("split", ratio=Decimal("0")),
        _action("ticker_change", old_symbol="OTHER", new_symbol="NEW"),
        _action("split", ratio=Decimal("2"), permanent_security_id="different"),
        _action("merger"),
    ],
)
def test_unresolved_or_out_of_scope_action_is_visible_and_excluded(action) -> None:
    with pytest.raises(CorporateActionError) as caught:
        normalize_live_security(_record(), [action], known_at=NOW)
    assert caught.value.code in {
        "CORPORATE_ACTION_UNRESOLVED",
        "CORPORATE_ACTION_SCOPE_NOT_IMPLEMENTED",
    }


def test_live_quote_normalization_applies_before_agent_input() -> None:
    item = {
        "quote": {
            "symbol": "OLD",
            "instrument_id": "security-1",
            "bid_price": "100",
            "ask_price": "101",
        },
        "corporate_actions": [_action("split", ratio="4")],
    }

    result = normalize_live_quote(item, known_at=NOW)

    assert result.record["quote"]["bid_price"] == "25"
    assert result.record["quote"]["ask_price"] == "25.25"
    assert result.record["permanent_security_id"] == "security-1"


def test_mixed_chain_underlyings_never_resolve_blank_symbol_by_elimination():
    from data.corporate_actions import quote_with_recorded_identity
    quote={'quote':{'symbol':'VTI'}}
    read={'tool':'get_option_chains','arguments':{'underlying_symbol':'VTI'},
          'source_id':'robinhood-mcp:get_option_chains','content_hash':'a'*64,
          'data':{'chains':[{'symbol':'VTI','underlying_instruments':[
              {'symbol':'','instrument':'https://api.robinhood.com/instruments/11111111-1111-4111-8111-111111111111/'},
              {'symbol':'SPY','instrument':'https://api.robinhood.com/instruments/22222222-2222-4222-8222-222222222222/'},
          ]}]}}
    resolved,audit=quote_with_recorded_identity(quote,[read])
    assert 'permanent_security_id' not in resolved
    assert audit==[]
