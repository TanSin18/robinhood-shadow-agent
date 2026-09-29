from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from agents.schemas import EvidenceItem, TradeProposal
from config.loader import load_config

SETTINGS = Path(__file__).parents[1] / "config" / "settings.yaml"


def test_default_config_is_stage_one_paper_only() -> None:
    config = load_config(SETTINGS)

    assert config.stage == 1
    assert config.broker == "paper"
    assert config.starting_cash_usd == 500
    assert config.risk.max_position_fraction == Decimal("0.25")
    assert config.risk.max_open_positions == 5
    assert config.risk.max_orders_per_day == 5
    assert config.risk.daily_loss_fraction == Decimal("0.03")
    assert config.risk.drawdown_buy_block_fraction == Decimal("0.10")
    assert config.risk.drawdown_lock_fraction == Decimal("0.15")
    assert config.notifications.pushover_enabled is True
    assert config.notifications.keychain_service == 'com.openai.robinhood-shadow.pushover'
    assert config.notifications.dashboard_base_url == (
        'http://127.0.0.1:8765'
    )
    assert config.notifications.dashboard_url('decisions').endswith('/#decisions')


@pytest.mark.parametrize(
    'url',
    [
        'http://tanmays-macbook-air.tail4c3ace.ts.net:8443',
        'https://example.com:8443',
        'https://tanmays-macbook-air.tail4c3ace.ts.net',
        'https://tanmays-macbook-air.tail4c3ace.ts.net:8443/path',
        'https://user@tanmays-macbook-air.tail4c3ace.ts.net:8443',
    ],
)
def test_remote_dashboard_url_is_restricted_to_private_tailscale_https(url) -> None:
    config = load_config(SETTINGS)

    with pytest.raises(ValidationError, match='dashboard_base_url'):
        config.notifications.model_copy(update={'dashboard_base_url': url}).model_validate(
            {**config.notifications.model_dump(), 'dashboard_base_url': url}
        )


def test_runtime_validation_requires_starting_cash() -> None:
    config = load_config(SETTINGS).model_copy(update={'starting_cash_usd': None})

    with pytest.raises(ValueError, match="starting_cash_usd"):
        config.validate_runtime_ready()


def test_private_phone_dashboard_config_roundtrips(portable_settings) -> None:
    config = load_config(portable_settings)

    assert config.notifications.dashboard_base_url == (
        'https://shadow-fixture.example.ts.net:8443'
    )


def test_config_hash_is_stable_for_same_file() -> None:
    first = load_config(SETTINGS)
    second = load_config(SETTINGS)

    assert first.config_hash == second.config_hash
    assert len(first.config_hash) == 64


def test_trade_confidence_must_be_between_zero_and_one() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        TradeProposal(
            proposal_id="p-1",
            account_id="agentic-1",
            ticker="VTI",
            asset_class="etf",
            side="buy",
            quantity=Decimal("1"),
            order_type="limit",
            limit_price=Decimal("250"),
            thesis="Broad-market exposure.",
            horizon_days=20,
            confidence=Decimal("1.01"),
            invalidation="Market data becomes stale.",
            evidence=[],
            prompt_versions={"portfolio": "portfolio_v1"},
            model_name="gpt-test",
            config_hash="a" * 64,
        )


def test_evidence_requires_complete_source_and_aware_timestamp() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(
            fact="Revenue increased.",
            source_url="",
            observed_at=datetime(2026, 9, 27, 12, 0),
            evidence_type="fundamental",
        )

    valid = EvidenceItem(
        fact="Revenue increased.",
        source_url="https://example.test/filing",
        observed_at=datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc),
        evidence_type="fundamental",
    )
    assert valid.observed_at.tzinfo is not None


def test_option_maximum_loss_cannot_be_negative() -> None:
    with pytest.raises(ValidationError, match="max_loss_usd"):
        TradeProposal(
            proposal_id="p-option",
            account_id="agentic-1",
            ticker="AAPL-OPT",
            asset_class="option",
            side="buy",
            quantity=Decimal("1"),
            order_type="limit",
            limit_price=Decimal("2"),
            thesis="Defined-risk spread.",
            horizon_days=5,
            confidence=Decimal("0.5"),
            invalidation="Volatility falls.",
            prompt_versions={"portfolio": "portfolio_v1"},
            model_name="gpt-test",
            config_hash="a" * 64,
            option_strategy="call_spread",
            max_loss_usd=Decimal("-1"),
        )
