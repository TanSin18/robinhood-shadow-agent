from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from data.store import SQLiteStore


class MLflowTracker:
    def __init__(
        self,
        store: SQLiteStore,
        *,
        tracking_uri: str,
        client: Any | None = None,
    ) -> None:
        self.store = store
        self.tracking_uri = self._local_uri(tracking_uri)
        if client is None:
            try:
                import mlflow as client
            except ImportError:
                client = None
        self.client = client
        self.status = "available" if client is not None else "unavailable: install mlflow"

    @staticmethod
    def _local_uri(value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"}:
            if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("MLflow tracking must be local")
            return value
        if parsed.scheme == "sqlite":
            return value
        if parsed.scheme == "file":
            database = Path(parsed.path)
        else:
            requested = Path(value).resolve()
            database = requested if requested.suffix == ".db" else requested / "mlflow.db"
        database.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{database}"

    def track_version(
        self,
        version_id: str,
        *,
        params: dict[str, object],
        metrics: dict[str, Decimal],
    ) -> None:
        self.store.freeze_strategy_version(version_id, params)
        if self.client is None:
            return
        self.client.set_tracking_uri(self.tracking_uri)
        self.client.set_experiment("robinhood-ai-shadow-agent")
        with self.client.start_run(run_name=version_id):
            self.client.log_params(params)
            self.client.log_metrics({key: float(value) for key, value in metrics.items()})
