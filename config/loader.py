from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agentic_account_id: str
    instrument_whitelist: frozenset[str] = frozenset()
    max_quote_age_seconds: int = 60
    max_limit_distance_fraction: Decimal = Decimal("0.005")
    max_position_fraction: Decimal = Decimal("0.25")
    target_position_fraction: Decimal = Field(default=Decimal('0.10'), gt=0, le=1)
    target_volatility_fraction: Decimal = Field(default=Decimal('0.20'), gt=0, le=2)
    max_open_positions: int = 5
    options_unlocked: bool = False
    max_orders_per_day: int = 5
    daily_loss_fraction: Decimal = Decimal("0.03")
    drawdown_buy_block_fraction: Decimal = Decimal("0.10")
    drawdown_lock_fraction: Decimal = Decimal("0.15")
    short_term_tax_fraction: Decimal = Decimal("0.35")
    long_term_tax_fraction: Decimal = Decimal("0.15")


class ObservabilityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    otlp_endpoint: str = "http://127.0.0.1:6006/v1/traces"
    trace_viewer_base_url: str = "http://127.0.0.1:6006"
    mlflow_tracking_uri: str = "./mlruns/mlflow.db"


class NotificationsConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    pushover_enabled: bool = True
    keychain_service: str = Field(
        default='com.openai.robinhood-shadow.pushover', min_length=1, max_length=128
    )
    user_account: str = Field(default='PUSHOVER_USER', min_length=1, max_length=64)
    token_account: str = Field(default='PUSHOVER_TOKEN', min_length=1, max_length=64)
    dashboard_base_url: str = 'http://127.0.0.1:8765'

    @field_validator('dashboard_base_url')
    @classmethod
    def private_dashboard_only(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError:
            raise ValueError('dashboard_base_url is invalid') from None
        if (
            parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {'', '/'}
        ):
            raise ValueError('dashboard_base_url must be an origin without credentials or a path')
        host = (parsed.hostname or '').lower()
        local = parsed.scheme == 'http' and host in {'127.0.0.1', 'localhost'} and port == 8765
        private_tailnet = (
            parsed.scheme == 'https' and host.endswith('.ts.net') and port == 8443
        )
        if not (local or private_tailnet):
            raise ValueError(
                'dashboard_base_url must be loopback or private Tailscale HTTPS on port 8443'
            )
        return value.rstrip('/')

    def dashboard_url(self, destination: str, *, fragment: bool = True) -> str:
        if fragment:
            if destination not in {'activity', 'controls', 'decisions', 'history', 'next', 'results'}:
                raise ValueError('unknown dashboard section')
            return f'{self.dashboard_base_url}/#{destination}'
        if not destination.startswith('trace/') or any(
            character not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._/'
            for character in destination
        ):
            raise ValueError('invalid dashboard path')
        return f'{self.dashboard_base_url}/{destination}'


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: Literal[1, 2, 3] = 1
    broker: Literal["paper", "robinhood"] = "paper"
    starting_cash_usd: Decimal | None = None
    model_name: str = 'gpt-5.6-terra'  # Legacy replay compatibility only.
    research_model_name: str = 'gpt-5.6-luna'
    portfolio_model_name: str = 'gpt-5.6-terra'
    critic_model_name: str = 'gpt-5.6-terra'
    full_llm_cycle_time_et: Literal['10:00'] = '10:00'
    weekly_report_day_et: Literal['Friday'] = 'Friday'
    weekly_report_time_et: Literal['16:30'] = '16:30'
    paper_lanes: dict[str, Decimal] = Field(default_factory=lambda: {'stocks_etfs_starting_cash_usd': Decimal(500), 'options_starting_cash_usd': Decimal(500)})
    daily_api_budget_usd: Decimal
    approval_expiry_minutes: int = Field(default=30, gt=0)
    risk: RiskConfig
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    broker_proxy_socket: Path = Path("data/runtime/robinhood-read.sock")

    @property
    def config_hash(self) -> str:
        canonical = self.model_dump(mode="json")
        # Pydantic serializes frozensets as arrays in process-dependent order.
        # A background worker and verifier must hash the same logical config.
        canonical["risk"]["instrument_whitelist"] = sorted(self.risk.instrument_whitelist)
        payload = json.dumps(
            canonical, sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(payload).hexdigest()

    def validate_runtime_ready(self) -> None:
        if self.starting_cash_usd is None or self.starting_cash_usd <= 0:
            raise ValueError("starting_cash_usd must be set to a positive amount")
        if self.stage == 1 and self.broker != "paper":
            raise ValueError("Stage 1 requires the paper broker")


def load_config(path: str | Path) -> AppConfig:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return AppConfig.model_validate(raw)
