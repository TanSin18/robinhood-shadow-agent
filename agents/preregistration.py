from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict


APPROVED_PHASE0_VERSION = "1.4.2"
APPROVED_PREREGISTRATION_SHA256 = (
    "39375034732a5ee14b2efb1d13e3c165438140255f1dc95ef25680d136a66075"
)


class Phase0Approval(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    scope: Literal["phase_0_only"]
    approved_on: date
    approved_by: str
    phase_1_allowed: bool


class Phase0Registration(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    registration_id: Literal["intelligent-agentic-investment-organization"]
    version: Literal["1.4.2"]
    status: Literal["approved_for_phase_0"]
    authority: Literal["operator_only"]
    allowed_fallback_path: Literal["full_scope_bounded_cash_fallback"]
    max_agentic_cash_usd: Decimal
    approval: Phase0Approval
    canonical_sha256: str


def load_phase0_registration(
    path: str | Path,
    *,
    expected_sha256: str = APPROVED_PREREGISTRATION_SHA256,
) -> Phase0Registration:
    """Load the byte-exact registration approved for Phase 0 only."""

    registration_path = Path(path)
    contents = registration_path.read_bytes()
    actual_sha256 = hashlib.sha256(contents).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError("preregistration hash does not match the approved canonical file")

    raw = yaml.safe_load(contents)
    if not isinstance(raw, dict):
        raise ValueError("preregistration must be a mapping")
    registration = raw.get("registration")
    approval = raw.get("approval")
    if not isinstance(registration, dict):
        raise ValueError("preregistration registration record is missing")
    if registration.get("version") != APPROVED_PHASE0_VERSION:
        raise ValueError("preregistration is not approved version 1.4.2")
    if registration.get("status") != "approved_for_phase_0":
        raise ValueError("preregistration is not approved for Phase 0")
    if not isinstance(approval, dict) or approval.get("approved_by") != "operator":
        raise ValueError("operator approval record is missing")
    if approval.get("scope") != "phase_0_only":
        raise ValueError("operator approval is not limited to Phase 0")
    if approval.get("phase_1_allowed") is not False:
        raise ValueError("Phase 1 remains blocked by this approval")
    try:
        oauth = raw["safety"]["oauth"]
        fallback = oauth["allowed_fallback_path"]
        cap = Decimal(str(oauth["bounded_cash"]["max_agentic_cash_usd"]))
    except (KeyError, TypeError, ValueError):
        raise ValueError("approved bounded-cash policy is missing") from None
    if fallback != "full_scope_bounded_cash_fallback":
        raise ValueError("approved bounded-cash fallback changed")
    if cap != Decimal("1200.00"):
        raise ValueError("approved Agentic cash cap changed")
    from broker.read_contracts import READ_METHODS, validate_schema_manifest
    manifest = raw['safety'].get('read_schema_manifest', {})
    approved_tools = raw['safety'].get('allowed_robinhood_read_tools', [])
    if len(approved_tools) != 11 or set(approved_tools) != READ_METHODS:
        raise ValueError('approved eleven read methods changed')
    if (manifest.get('path') != 'broker/read_schemas_v1.4.2.json'
            or manifest.get('sha256') != validate_schema_manifest()
            or manifest.get('validate_at_load') is not True):
        raise ValueError('approved read schema manifest changed')

    return Phase0Registration.model_validate(
        {
            "registration_id": registration.get("id"),
            "version": registration.get("version"),
            "status": registration.get("status"),
            "authority": registration.get("authority"),
            "allowed_fallback_path": fallback,
            "max_agentic_cash_usd": cap,
            "approval": approval,
            "canonical_sha256": actual_sha256,
        }
    )
