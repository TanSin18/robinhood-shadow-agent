from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from agents.observability import DailyBudget, TraceManager
from agents.operator import (
    IdempotentOperator,
    MarketSchedule,
    StallMonitor,
    run_shadow_supervisor_once,
)
from agents.operator import (
    main as operator_main,
)
from data.store import SQLiteStore
from eval.experiment import MLflowTracker
from scripts.start_phoenix import phoenix_settings

NOW = datetime(2026, 9, 27, 14, 30, tzinfo=timezone.utc)


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def notify(self, title: str, body: str) -> None:
        self.messages.append((title, body))


class FakeMLflow:
    def __init__(self) -> None:
        self.uri = ""
        self.params: dict[str, object] = {}
        self.metrics: dict[str, float] = {}

    def set_tracking_uri(self, uri: str) -> None:
        self.uri = uri

    def set_experiment(self, name: str) -> None:
        self.experiment = name

    @contextmanager
    def start_run(self, run_name: str):
        self.run_name = run_name
        yield self

    def log_params(self, params: dict[str, object]) -> None:
        self.params.update(params)

    def log_metrics(self, metrics: dict[str, float]) -> None:
        self.metrics.update(metrics)


def test_trace_manager_rejects_any_non_local_export_or_viewer(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "agent.db")

    with pytest.raises(ValueError, match="localhost"):
        TraceManager(
            store,
            otlp_endpoint="https://collector.example.com/v1/traces",
            viewer_base_url="http://127.0.0.1:6006",
        )
    with pytest.raises(ValueError, match="localhost"):
        TraceManager(
            store,
            otlp_endpoint="http://127.0.0.1:6006/v1/traces",
            viewer_base_url="https://viewer.example.com",
        )


def test_trace_link_is_local_and_trace_is_recorded(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "agent.db")
    manager = TraceManager(
        store,
        otlp_endpoint="http://127.0.0.1:6006/v1/traces",
        viewer_base_url="http://127.0.0.1:6006",
    )

    manager.record("trace-123", "risk_verdict", {"allowed": False})

    assert manager.trace_url("trace-123") == "http://127.0.0.1:6006/redirects/traces/trace-123"
    assert store.read_json("local_traces")[0]["event"] == "risk_verdict"


def test_daily_budget_stops_at_limit_and_alerts() -> None:
    notifier = FakeNotifier()
    budget = DailyBudget(Decimal("25"), notifier)

    assert budget.record(Decimal("10")) is True
    assert budget.record(Decimal("15")) is False
    assert budget.can_spend(Decimal("0.01")) is False
    assert notifier.messages[-1][0] == "Daily API budget reached"


def test_mlflow_uses_local_uri_and_frozen_strategy_versions(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "agent.db")
    fake = FakeMLflow()
    tracker = MLflowTracker(store, tracking_uri=str(tmp_path / "mlruns"), client=fake)

    tracker.track_version(
        "champion-v1",
        params={"model": "gpt-test", "prompt": "portfolio_v1"},
        metrics={"net_return": Decimal("0.02")},
    )

    assert fake.uri.startswith("sqlite:///")
    assert fake.params["prompt"] == "portfolio_v1"
    assert fake.metrics["net_return"] == 0.02
    with pytest.raises(ValueError, match="frozen"):
        tracker.track_version(
            "champion-v1",
            params={"model": "changed"},
            metrics={"net_return": Decimal("0.03")},
        )


def test_real_mlflow_uses_supported_local_sqlite_backend(tmp_path: Path) -> None:
    pytest.importorskip("mlflow")
    store = SQLiteStore(tmp_path / "agent.db")
    database = tmp_path / "mlflow.db"
    tracker = MLflowTracker(store, tracking_uri=str(database))

    tracker.track_version(
        "integration-v1",
        params={"model": "mock"},
        metrics={"net_return": Decimal("0.01")},
    )

    assert tracker.status == "available"
    assert tracker.tracking_uri.startswith("sqlite:///")
    assert database.exists()


def test_restart_recovery_does_not_submit_duplicate(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "agent.db")
    calls: list[str] = []
    operator = IdempotentOperator(store)

    assert operator.run_once("client-1", lambda: calls.append("submitted")) is True
    restarted = IdempotentOperator(SQLiteStore(tmp_path / "agent.db"))
    assert restarted.run_once("client-1", lambda: calls.append("duplicate")) is False
    assert calls == ["submitted"]


def test_schedule_runs_equities_in_market_hours_and_crypto_24_7_in_shadow() -> None:
    schedule = MarketSchedule()
    eastern = ZoneInfo("America/New_York")
    monday_open = datetime(2026, 9, 28, 10, 0, tzinfo=eastern)
    saturday = datetime(2026, 10, 3, 10, 0, tzinfo=eastern)

    assert schedule.should_run(monday_open, asset_class="stock", stage=1) is True
    assert schedule.should_run(saturday, asset_class="stock", stage=1) is False
    assert schedule.should_run(saturday, asset_class="crypto", stage=1) is True


def test_schedule_does_not_run_equities_on_nyse_holiday() -> None:
    schedule = MarketSchedule()
    eastern = ZoneInfo("America/New_York")
    thanksgiving = datetime(2026, 11, 26, 10, 0, tzinfo=eastern)

    assert schedule.should_run(thanksgiving, asset_class="stock", stage=1) is False


def test_stall_monitor_alerts_after_thirty_minutes() -> None:
    notifier = FakeNotifier()
    monitor = StallMonitor(notifier, threshold=timedelta(minutes=30))
    monitor.mark_progress(NOW)

    assert monitor.check(NOW + timedelta(minutes=30)) is False
    assert monitor.check(NOW + timedelta(minutes=31)) is True
    assert notifier.messages[-1][0] == "Trading agent stalled"


def test_phoenix_settings_are_loopback_and_persistent(tmp_path: Path) -> None:
    settings = phoenix_settings(tmp_path)

    assert settings.host == "127.0.0.1"
    assert settings.port == 6006
    assert settings.working_dir == tmp_path.resolve()


def test_shadow_supervisor_records_safe_ready_state_without_broker_access(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "settings.yaml"
    config_path.write_text(
        """\
stage: 1
broker: paper
starting_cash_usd: 500
model_name: gpt-test
daily_api_budget_usd: 25
approval_expiry_minutes: 30
risk:
  agentic_account_id: '999991234'
""",
        encoding="utf-8",
    )
    database = tmp_path / "agent.db"

    status = run_shadow_supervisor_once(config_path, database)

    assert status == {
        "status": "ready",
        "stage": 1,
        "broker": "paper",
        "live_execution": "blocked",
        "account_id_last4": "1234",
        "starting_cash_usd": "500",
    }
    assert SQLiteStore(database).read_json("run_states") == [status]


@pytest.mark.parametrize(
    "account_id",
    ["REPLACE_WITH_AGENTIC_ACCOUNT_ID", "    ", "1234", "TEST-12345"],
)
def test_shadow_supervisor_refuses_invalid_account_id(
    tmp_path: Path,
    account_id: str,
) -> None:
    config_path = tmp_path / "settings.yaml"
    config_path.write_text(
        f"""\
stage: 1
broker: paper
starting_cash_usd: 500
model_name: gpt-test
daily_api_budget_usd: 25
approval_expiry_minutes: 30
risk:
  agentic_account_id: '{account_id}'
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Agentic account identifier"):
        run_shadow_supervisor_once(config_path, tmp_path / "agent.db")


@pytest.mark.parametrize("interval", ["nan", "inf", "-inf"])
def test_shadow_supervisor_refuses_non_finite_interval(
    tmp_path: Path,
    interval: str,
) -> None:
    with pytest.raises(SystemExit):
        operator_main(
            [
                "--config",
                str(tmp_path / "missing.yaml"),
                "--database",
                str(tmp_path / "agent.db"),
                "--interval-seconds",
                interval,
                "--once",
            ]
        )
