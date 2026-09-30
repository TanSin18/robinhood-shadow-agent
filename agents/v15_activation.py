"""Byte-pinned activation of preregistration v1.5 policy.

Nothing here reads an environment variable, dashboard switch or draft file.
The v1.4.2 root ``preregistration.yaml`` stays byte-identical (Phase 0 safety
loaders pin it). v1.5 is a scoped amendment layer file,
``preregistration-amendment-v1.5.0.yaml``, active only when it is byte-identical
to the operator-signed file pinned below, declares the installed root as its
base, and the current time is at or after its effective time. Both constants
are set by the reviewed activation release; until then they stay ``None`` and
every v1.5 path is inert.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

APPROVED_V15_SHA256: str | None = None
EFFECTIVE_FROM: datetime | None = None
AMENDMENT_NAME = 'preregistration-amendment-v1.5.0.yaml'


def registration_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def v15_active(root: Path, now: datetime, *, approved_sha256=None, effective_from=None) -> bool:
    approved = APPROVED_V15_SHA256 if approved_sha256 is None else approved_sha256
    effective = EFFECTIVE_FROM if effective_from is None else effective_from
    if approved is None or effective is None:
        return False
    if now.tzinfo is None or effective.tzinfo is None or now < effective:
        return False
    root = Path(root)
    amendment = root / AMENDMENT_NAME
    try:
        if amendment.is_symlink() or (root / 'preregistration.yaml').is_symlink():
            return False
        if registration_sha256(amendment) != approved:
            return False
        import yaml
        declared = (yaml.safe_load(amendment.read_bytes()) or {}).get('amendment', {})
        if declared.get('base_sha256') != registration_sha256(root / 'preregistration.yaml'):
            return False
        return (declared.get('operator_signature') or {}).get('status') == 'SIGNED'
    except (OSError, ValueError, AttributeError):
        return False
