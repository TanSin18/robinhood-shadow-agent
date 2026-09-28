from __future__ import annotations

from typing import Any, Protocol


class BrokerError(RuntimeError):
    """A broker request was rejected before or during execution."""


class Broker(Protocol):
    def submit(self, order: Any, quote: Any) -> Any: ...

    def cancel(self, order_id: str) -> Any: ...

