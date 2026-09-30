"""Byte-pinned activation of preregistration v1.5 policy.

Nothing here reads an environment variable, dashboard switch or draft file.
v1.5 behaviour is active only when the installed root ``preregistration.yaml``
is byte-identical to the operator-approved v1.5 file whose SHA-256 is pinned
below, and the current time is at or after its effective time. Both constants
are set by the reviewed activation release; until then they stay ``None`` and
every v1.5 path is inert.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

APPROVED_V15_SHA256: str | None = None
EFFECTIVE_FROM: datetime | None = None


def registration_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def v15_active(root: Path, now: datetime, *, approved_sha256=None, effective_from=None) -> bool:
    approved = APPROVED_V15_SHA256 if approved_sha256 is None else approved_sha256
    effective = EFFECTIVE_FROM if effective_from is None else effective_from
    if approved is None or effective is None:
        return False
    if now.tzinfo is None or effective.tzinfo is None or now < effective:
        return False
    path = Path(root) / 'preregistration.yaml'
    try:
        if path.is_symlink():
            return False
        return registration_sha256(path) == approved
    except OSError:
        return False
