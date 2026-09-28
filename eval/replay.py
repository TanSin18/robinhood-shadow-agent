from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class PointInTimeSnapshot:
    observed_at: datetime
    payload: dict[str, Any]


class ReplayHarness:
    def run(
        self,
        snapshots: list[PointInTimeSnapshot],
        *,
        replay_clock: datetime,
    ) -> tuple[dict[str, Any], ...]:
        if replay_clock.tzinfo is None or replay_clock.utcoffset() is None:
            raise ValueError("replay clock must be timezone-aware")
        ordered = sorted(snapshots, key=lambda item: item.observed_at)
        if any(item.observed_at > replay_clock for item in ordered):
            raise ValueError("lookahead detected: snapshot is later than replay clock")
        return tuple(item.payload for item in ordered)

