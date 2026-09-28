from __future__ import annotations

from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

from agents.notifications import Notifier
from data.store import SQLiteStore

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _require_local_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in _LOCAL_HOSTS:
        raise ValueError("trace endpoints must use localhost or a loopback address")


class LocalAgentsTraceProcessor:
    """OpenAI Agents SDK processor that persists traces locally only."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def _save(self, kind: str, item: object) -> None:
        try:
            exported = item.export()
            if exported is not None:
                self.store.append_json(
                    "local_traces", {"event": kind, "payload": exported}
                )
        except Exception:
            # Tracing must never interrupt the trading safety path.
            return

    def on_trace_start(self, trace: object) -> None:
        self._save("trace_start", trace)

    def on_trace_end(self, trace: object) -> None:
        self._save("trace_end", trace)

    def on_span_start(self, span: object) -> None:
        self._save("span_start", span)

    def on_span_end(self, span: object) -> None:
        self._save("span_end", span)

    def shutdown(self) -> None:
        return None

    def force_flush(self) -> None:
        return None


class TraceManager:
    def __init__(
        self,
        store: SQLiteStore,
        *,
        otlp_endpoint: str,
        viewer_base_url: str,
        enable_otlp: bool = False,
    ) -> None:
        _require_local_url(otlp_endpoint)
        _require_local_url(viewer_base_url)
        self.store = store
        self.otlp_endpoint = otlp_endpoint
        self.viewer_base_url = viewer_base_url.rstrip("/")
        self.processor = LocalAgentsTraceProcessor(store)
        self.otel_status = "disabled"
        self._otel_tracer = self._configure_otel() if enable_otlp else None

    def install_sdk_processor(self) -> None:
        from agents.tracing import set_trace_processors, set_tracing_disabled

        set_tracing_disabled(False)
        # Replacing the default processor keeps SDK tracing active without the
        # default remote trace exporter.
        set_trace_processors([self.processor])

    def _configure_otel(self) -> object | None:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError:
            self.otel_status = "unavailable: install the observability extra"
            return None
        provider = TracerProvider()
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=self.otlp_endpoint))
        )
        self.otel_status = "configured_local"
        return provider.get_tracer("robinhood-ai-shadow-agent")

    def record(self, trace_id: str, event: str, payload: dict[str, Any]) -> None:
        self.store.append_json(
            "local_traces",
            {"trace_id": trace_id, "event": event, "payload": payload},
        )
        if self._otel_tracer is not None:
            with self._otel_tracer.start_as_current_span(event) as span:
                span.set_attribute("local.trace_id", trace_id)

    def trace_url(self, trace_id: str) -> str:
        return f"{self.viewer_base_url}/redirects/traces/{trace_id}"


class TokenCostRecorder:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def record(
        self,
        *,
        trace_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: Decimal,
    ) -> int:
        return self.store.append_json(
            "api_costs",
            {
                "trace_id": trace_id,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": str(cost_usd),
            },
        )


class DailyBudget:
    def __init__(self, limit_usd: Decimal, notifier: Notifier) -> None:
        self.limit_usd = limit_usd
        self.spent_usd = Decimal("0")
        self.notifier = notifier
        self._alerted = False

    def can_spend(self, estimated_cost: Decimal) -> bool:
        return self.spent_usd < self.limit_usd and (
            self.spent_usd + estimated_cost <= self.limit_usd
        )

    def record(self, actual_cost: Decimal) -> bool:
        self.spent_usd += actual_cost
        can_continue = self.spent_usd < self.limit_usd
        if not can_continue and not self._alerted:
            self.notifier.notify(
                "Daily API budget reached",
                f"Agents stopped after ${self.spent_usd:.2f} of API spend.",
            )
            self._alerted = True
        return can_continue
