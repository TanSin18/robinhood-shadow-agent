from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from data.connections import connection as managed_connection

REQUIRED_TABLES = {
    "decision_records",
    "orders",
    "fills",
    "daily_values",
    "api_costs",
    "cards",
    "strategy_versions",
    "strategy_changes",
    "lessons",
    "improvement_proposals",
    "alerts",
    "validation_failures",
    "run_states",
    "local_traces",
}


class SQLiteStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        with self._connect() as connection:
            connection.executescript(schema)

    def _connect(self):
        return managed_connection(self.path, row_factory=sqlite3.Row)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def table_names(self) -> tuple[str, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        return tuple(row["name"] for row in rows if not row["name"].startswith("sqlite_"))

    def append_json(self, table: str, payload: dict[str, Any]) -> int:
        if table not in REQUIRED_TABLES or table == "strategy_versions":
            raise ValueError(f"table is not append-enabled: {table}")
        encoded = json.dumps(payload, sort_keys=True, default=str)
        with self._connect() as connection:
            cursor = connection.execute(
                f"INSERT INTO {table} (created_at, payload_json) VALUES (?, ?)",
                (self._now(), encoded),
            )
            return int(cursor.lastrowid)

    def read_json(self, table: str) -> list[dict[str, Any]]:
        if table not in REQUIRED_TABLES:
            raise ValueError(f"unknown table: {table}")
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload_json FROM {table} ORDER BY id"
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def freeze_strategy_version(self, version_id: str, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, sort_keys=True, default=str)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload_json FROM strategy_versions WHERE version_id = ?",
                (version_id,),
            ).fetchone()
            if existing is not None:
                if existing["payload_json"] != encoded:
                    raise ValueError(f"strategy version {version_id} is frozen")
                return
            connection.execute(
                "INSERT INTO strategy_versions (created_at, version_id, payload_json) VALUES (?, ?, ?)",
                (self._now(), version_id, encoded),
            )

    def record_validation_failure(self, agent: str, prompt_version: str, raw_output: str) -> int:
        return self.append_json(
            "validation_failures",
            {"agent": agent, "prompt_version": prompt_version, "raw_output": raw_output},
        )
