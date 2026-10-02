"""The provenance every provider response must carry before it may enter the feature store.

Timestamps are kept exactly as received (text). Nothing here parses, rounds or repairs them: the quality checks
read them, and a response whose provenance is incomplete is rejected, not completed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Optional

REQUIRED = ('provider', 'source_id', 'source_timestamp', 'ingested_at', 'known_at', 'schema_version')


@dataclass(frozen=True)
class Provenance:
    provider: str                              # who supplied it
    source_id: str                             # the provider's own identifier for this response, document or series
    source_timestamp: str                      # the provider's timestamp, exactly as sent
    ingested_at: str                           # when Firm Lab received it
    known_at: str                              # the earliest moment Firm Lab could have known it (point in time)
    schema_version: str                        # the Firm Lab schema the records were checked against
    exchange_session_date: Optional[str] = None    # for market data: the session the records belong to
    content_hash: Optional[str] = None             # sha256 of the raw payload, where practical

    def as_dict(self) -> dict:
        return asdict(self)

    def missing(self) -> list:
        """Names of required fields that are empty. An empty list means the provenance is complete."""
        return [name for name in REQUIRED if not str(getattr(self, name) or '').strip()]


def content_hash(payload) -> str:
    """sha256 of the payload: bytes as they are, text as UTF-8, anything else as canonical JSON."""
    if isinstance(payload, bytes):
        raw = payload
    elif isinstance(payload, str):
        raw = payload.encode()
    else:
        raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str).encode()
    return hashlib.sha256(raw).hexdigest()
