from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from data.evidence import EvidenceCache, EvidenceEnvelope


NOW = datetime(2026, 9, 28, 14, tzinfo=timezone.utc)


def test_content_hash_uses_canonical_source_content_not_url_or_timestamp() -> None:
    first = EvidenceEnvelope.from_payload(
        source_id="robinhood:get_equity_quotes",
        payload={"b": 2, "a": 1},
        observed_at=NOW,
        effective_at=NOW - timedelta(seconds=1),
        fetched_at=NOW,
    )
    second = EvidenceEnvelope.from_payload(
        source_id="different-label",
        payload={"a": 1, "b": 2},
        observed_at=NOW + timedelta(seconds=1),
        effective_at=NOW - timedelta(seconds=1),
        fetched_at=NOW + timedelta(seconds=1),
    )
    revision = EvidenceEnvelope.from_payload(
        source_id="robinhood:get_equity_quotes",
        payload={"a": 1, "b": 3},
        observed_at=NOW,
        effective_at=NOW,
        fetched_at=NOW,
    )

    assert first.content_hash == second.content_hash
    assert revision.content_hash != first.content_hash


def test_envelope_rejects_naive_or_future_effective_source() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        EvidenceEnvelope.from_payload(
            source_id="x", payload={}, observed_at=NOW.replace(tzinfo=None),
            effective_at=NOW, fetched_at=NOW,
        )
    with pytest.raises(ValueError, match="lookahead"):
        EvidenceEnvelope.from_payload(
            source_id="x", payload={}, observed_at=NOW,
            effective_at=NOW + timedelta(seconds=1), fetched_at=NOW,
        )


def test_cache_returns_only_evidence_available_as_of_query_time(tmp_path) -> None:
    cache = EvidenceCache(tmp_path / "evidence.db")
    early = EvidenceEnvelope.from_payload(
        source_id="source", payload={"value": 1}, observed_at=NOW,
        effective_at=NOW, fetched_at=NOW,
    )
    late = EvidenceEnvelope.from_payload(
        source_id="source", payload={"value": 2}, observed_at=NOW + timedelta(hours=1),
        effective_at=NOW + timedelta(hours=1), fetched_at=NOW + timedelta(hours=1),
    )
    cache.put(early)
    cache.put(late)

    assert cache.latest("source", as_of=NOW + timedelta(minutes=30)).payload == {"value": 1}

