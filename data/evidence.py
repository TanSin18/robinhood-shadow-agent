from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("evidence timestamps must be timezone-aware")
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"unsupported evidence value: {type(value).__name__}")


def canonical_source_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    ).encode("utf-8")


@dataclass(frozen=True)
class EvidenceEnvelope:
    source_id: str
    observed_at: datetime
    effective_at: datetime
    fetched_at: datetime
    content_hash: str
    payload: Any

    @classmethod
    def from_payload(
        cls,
        *,
        source_id: str,
        payload: Any,
        observed_at: datetime,
        effective_at: datetime,
        fetched_at: datetime,
    ) -> "EvidenceEnvelope":
        if not source_id:
            raise ValueError("source_id is required")
        if any(value.tzinfo is None for value in (observed_at, effective_at, fetched_at)):
            raise ValueError("evidence timestamps must be timezone-aware")
        if effective_at > observed_at or observed_at > fetched_at:
            raise ValueError("evidence would introduce lookahead")
        return cls(
            source_id=source_id,
            observed_at=observed_at,
            effective_at=effective_at,
            fetched_at=fetched_at,
            content_hash=hashlib.sha256(canonical_source_bytes(payload)).hexdigest(),
            payload=payload,
        )


class EvidenceCache:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS evidence_cache (
                source_id TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                effective_at TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY(source_id, content_hash, fetched_at))"""
            )

    def put(self, envelope: EvidenceEnvelope) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT OR IGNORE INTO evidence_cache VALUES (?,?,?,?,?,?)",
                (
                    envelope.source_id,
                    envelope.content_hash,
                    envelope.observed_at.isoformat(),
                    envelope.effective_at.isoformat(),
                    envelope.fetched_at.isoformat(),
                    canonical_source_bytes(envelope.payload).decode("utf-8"),
                ),
            )

    def latest(self, source_id: str, *, as_of: datetime) -> EvidenceEnvelope | None:
        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                """SELECT content_hash,observed_at,effective_at,fetched_at,payload_json
                FROM evidence_cache
                WHERE source_id=? AND observed_at<=? AND effective_at<=? AND fetched_at<=?
                ORDER BY fetched_at DESC LIMIT 1""",
                (source_id, as_of.isoformat(), as_of.isoformat(), as_of.isoformat()),
            ).fetchone()
        if row is None:
            return None
        return EvidenceEnvelope(
            source_id=source_id,
            content_hash=row[0],
            observed_at=datetime.fromisoformat(row[1]),
            effective_at=datetime.fromisoformat(row[2]),
            fetched_at=datetime.fromisoformat(row[3]),
            payload=json.loads(row[4]),
        )
