from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from agents.preregistration import load_phase0_registration


def test_phase0_registration_exposes_bounded_cash_policy() -> None:
    registration = load_phase0_registration(Path("preregistration.yaml"))

    assert registration.version == "1.4.2"
    assert registration.allowed_fallback_path == "full_scope_bounded_cash_fallback"
    assert registration.max_agentic_cash_usd == Decimal("1200.00")


def _write_registration(tmp_path: Path, **overrides: object) -> Path:
    registration = {
        "id": "intelligent-agentic-investment-organization",
        "version": "1.4.2",
        "status": "approved_for_phase_0",
        "authority": "operator_only",
    }
    approval = {
        "scope": "phase_0_only",
        "approved_on": "2026-09-28",
        "approved_by": "operator",
        "phase_1_allowed": False,
    }
    registration.update(overrides.pop("registration", {}))
    approval.update(overrides.pop("approval", {}))
    payload = {
        "schema_version": 1,
        "registration": registration,
        "approval": approval,
        "safety": {
            "allowed_robinhood_read_tools": yaml.safe_load(Path('preregistration.yaml').read_text())['safety']['allowed_robinhood_read_tools'],
            "read_schema_manifest": yaml.safe_load(Path('preregistration.yaml').read_text())['safety']['read_schema_manifest'],
            "oauth": {
                "allowed_fallback_path": "full_scope_bounded_cash_fallback",
                "bounded_cash": {"max_agentic_cash_usd": 1200.00},
            }
        },
        **overrides,
    }
    path = tmp_path / "preregistration.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_phase0_preflight_accepts_exact_approved_registration(tmp_path: Path) -> None:
    path = _write_registration(tmp_path)

    registration = load_phase0_registration(path, expected_sha256=_digest(path))

    assert registration.version == "1.4.2"
    assert registration.approval.scope == "phase_0_only"
    assert registration.approval.phase_1_allowed is False
    assert registration.canonical_sha256 == _digest(path)


@pytest.mark.parametrize("status", ["pending_operator_review", "approved_for_phase_1"])
def test_phase0_preflight_rejects_wrong_status(tmp_path: Path, status: str) -> None:
    path = _write_registration(tmp_path, registration={"status": status})

    with pytest.raises(ValueError, match="approved for Phase 0"):
        load_phase0_registration(path, expected_sha256=_digest(path))


def test_phase0_preflight_rejects_missing_operator_approval(tmp_path: Path) -> None:
    path = _write_registration(tmp_path, approval={"approved_by": ""})

    with pytest.raises(ValueError, match="operator approval"):
        load_phase0_registration(path, expected_sha256=_digest(path))


def test_phase0_preflight_rejects_phase1_authority(tmp_path: Path) -> None:
    path = _write_registration(tmp_path, approval={"phase_1_allowed": True})

    with pytest.raises(ValueError, match="Phase 1 remains blocked"):
        load_phase0_registration(path, expected_sha256=_digest(path))


def test_phase0_preflight_rejects_changed_canonical_bytes(tmp_path: Path) -> None:
    path = _write_registration(tmp_path)
    approved_digest = _digest(path)
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="hash does not match"):
        load_phase0_registration(path, expected_sha256=approved_digest)
