from __future__ import annotations

import argparse
import json
import math
import signal
import threading
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from pathlib import Path
from enum import Enum
from typing import Literal
from zoneinfo import ZoneInfo

from agents.notifications import Notifier
from config.loader import load_config
from data.store import SQLiteStore


class IdempotentOperator:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def run_once(self, client_order_id: str, operation: Callable[[], object]) -> bool:
        existing = {
            item["client_order_id"]
            for item in self.store.read_json("orders")
            if "client_order_id" in item
        }
        if client_order_id in existing:
            return False
        self.store.append_json(
            "orders", {"client_order_id": client_order_id, "status": "reserved"}
        )
        operation()
        return True


class MarketSchedule:
    def __init__(self) -> None:
        self.eastern = ZoneInfo("America/New_York")
        import exchange_calendars as xcals
        self.calendar = xcals.get_calendar("XNYS")

    class State(str, Enum):
        TRADING_WINDOW = "TRADING_WINDOW"
        NOT_A_TRADING_DAY = "NOT_A_TRADING_DAY"
        BEFORE_WINDOW = "BEFORE_WINDOW"
        MISSED_WINDOW = "MISSED_WINDOW"

    def _session(self, moment: datetime):
        if moment.tzinfo is None:
            raise ValueError("Timezone-aware timestamp required")
        import pandas as pd
        local = moment.astimezone(self.eastern)
        session = pd.Timestamp(local.date())
        return session if self.calendar.is_session(session) else None

    def classify(self, moment: datetime) -> "MarketSchedule.State":
        if self._session(moment) is None:
            return self.State.NOT_A_TRADING_DAY
        local = moment.astimezone(self.eastern)
        start = local.replace(hour=10, minute=0, second=0, microsecond=0)
        if local < start:
            return self.State.BEFORE_WINDOW
        if local < start + timedelta(minutes=20):
            return self.State.TRADING_WINDOW
        return self.State.MISSED_WINDOW

    def session_close(self, moment: datetime) -> datetime:
        session = self._session(moment)
        if session is None:
            raise ValueError("not an XNYS trading day")
        return self.calendar.session_close(session).to_pydatetime()

    def should_run(
        self,
        moment: datetime,
        *,
        asset_class: Literal["stock", "etf", "option", "crypto"],
        stage: int,
    ) -> bool:
        local = moment.astimezone(self.eastern)
        if asset_class == "crypto" and stage == 1:
            return True
        session = self._session(moment)
        if session is None:
            return False
        instant = moment.astimezone(ZoneInfo("UTC"))
        opened = self.calendar.session_open(session).to_pydatetime()
        closed = self.calendar.session_close(session).to_pydatetime()
        return opened <= instant <= closed


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    day = date(year, month, 1)
    offset = (weekday - day.weekday()) % 7
    return day + timedelta(days=offset + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        day = date(year, month + 1, 1) - timedelta(days=1)
    return day - timedelta(days=(day.weekday() - weekday) % 7)


def _easter(year: int) -> date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    correction = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * correction) // 451
    month = (h + correction - 7 * m + 114) // 31
    day = (h + correction - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def nyse_holidays(year: int) -> frozenset[date]:
    """Regular full-day NYSE holidays; unscheduled national closures are external data."""
    holidays = {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),
        _nth_weekday(year, 2, 0, 3),
        _easter(year) - timedelta(days=2),
        _last_weekday(year, 5, 0),
        _observed(date(year, 6, 19)),
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 11, 3, 4),
        _observed(date(year, 12, 25)),
    }
    return frozenset(holidays)


class StallMonitor:
    def __init__(self, notifier: Notifier, *, threshold: timedelta) -> None:
        self.notifier = notifier
        self.threshold = threshold
        self.last_progress: datetime | None = None
        self._alerted_for: datetime | None = None

    def mark_progress(self, moment: datetime) -> None:
        self.last_progress = moment
        self._alerted_for = None

    def check(self, moment: datetime) -> bool:
        if self.last_progress is None or moment - self.last_progress <= self.threshold:
            return False
        if self._alerted_for != self.last_progress:
            self.notifier.notify(
                "Trading agent stalled",
                "No progress was recorded for more than 30 minutes during the active window.",
            )
            self._alerted_for = self.last_progress
        return True


def run_shadow_supervisor_once(
    config_path: str | Path,
    database_path: str | Path,
) -> dict[str, object]:
    """Validate Stage 1 and record a heartbeat without invoking any broker."""
    config = load_config(config_path)
    config.validate_runtime_ready()
    if config.stage != 1 or config.broker != "paper":
        raise ValueError("shadow supervisor requires Stage 1 with the paper broker")

    account_id = config.risk.agentic_account_id.strip()
    if not account_id.isdigit() or len(account_id) < 5:
        raise ValueError("Agentic account identifier must be configured")
    status: dict[str, object] = {
        "status": "ready",
        "stage": config.stage,
        "broker": config.broker,
        "live_execution": "blocked",
        "account_id_last4": account_id[-4:],
        "starting_cash_usd": str(config.starting_cash_usd),
    }
    SQLiteStore(database_path).append_json("run_states", status)
    return status


def _positive_seconds(value: str) -> float:
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("interval must be positive")
    return seconds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 1 shadow-mode safety supervisor")
    parser.add_argument("--config", default="config/settings.local.yaml")
    parser.add_argument("--database", default="data/agent.db")
    parser.add_argument("--interval-seconds", type=_positive_seconds, default=300.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)

    status = run_shadow_supervisor_once(args.config, args.database)
    print(json.dumps(status, sort_keys=True), flush=True)
    if args.once:
        return 0

    stop = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    while not stop.wait(args.interval_seconds):
        status = run_shadow_supervisor_once(args.config, args.database)
        print(json.dumps(status, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
