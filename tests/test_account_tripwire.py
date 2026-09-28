from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest


NOW = datetime(2026, 9, 28, 14, 0, tzinfo=timezone.utc)


def evaluate(path, *, cash="500", positions=None, equity_orders=None,
             option_orders=None, crypto_orders=None, cycle_id="c1", now=NOW):
    from agents.account_tripwire import evaluate_snapshot

    return evaluate_snapshot(
        path,
        cash=cash,
        positions=positions or [],
        equity_orders=equity_orders or [],
        option_orders=option_orders or [],
        crypto_orders=crypto_orders or [],
        max_agentic_cash_usd=Decimal("1200"),
        cycle_id=cycle_id,
        now=now,
        dashboard_base_url="http://127.0.0.1:8765",
    )


def test_first_verified_snapshot_seeds_without_page(tmp_path):
    result = evaluate(tmp_path / "agent.db")

    assert result.status == "BASELINE_CREATED"
    assert not (tmp_path / "INCIDENT_STOP").exists()
    with sqlite3.connect(tmp_path / "agent.db") as db:
        assert db.execute("SELECT COUNT(*) FROM notification_outbox").fetchone()[0] == 0


def test_identical_snapshot_is_verified_without_page(tmp_path):
    path = tmp_path / "agent.db"
    evaluate(path)
    result = evaluate(path, cash="500.00", cycle_id="c2", now=NOW + timedelta(days=1))
    assert result.status == "VERIFIED_UNCHANGED"
    assert not (tmp_path / "INCIDENT_STOP").exists()


def test_in_cap_cash_increase_is_benign_and_advances_baseline(tmp_path):
    path = tmp_path / "agent.db"
    evaluate(path)
    result = evaluate(path, cash="512.34", cycle_id="c2", now=NOW + timedelta(days=1))

    assert result.status == "ACCOUNT_CASH_INCREASE_BENIGN"
    assert not (tmp_path / "INCIDENT_STOP").exists()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM notification_outbox").fetchone()[0] == 0
        event = db.execute("SELECT status FROM broker_tripwire_events ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert event == "ACCOUNT_CASH_INCREASE_BENIGN"


@pytest.mark.parametrize(
    ("changes", "change_class", "code"),
    [
        ({"cash": "499"}, "cash_decrease", "AGENTIC_ACCOUNT_UNACKNOWLEDGED_CHANGE"),
        ({"cash": "1200.01"}, "cash_above_cap", "AGENTIC_ACCOUNT_OUTSIDE_BOUNDS"),
        ({"positions": [{"instrument_id": "instrument-secret", "quantity": "17.25", "direction": "long"}]}, "positions", "AGENTIC_ACCOUNT_UNACKNOWLEDGED_CHANGE"),
        ({"equity_orders": [{"id": "order-secret", "state": "filled", "updated_at": "2026-09-28T14:01:00Z"}]}, "order_activity", "AGENTIC_ACCOUNT_UNACKNOWLEDGED_CHANGE"),
        ({"option_orders": [{"id": "option-secret", "state": "queued"}]}, "order_activity", "AGENTIC_ACCOUNT_UNACKNOWLEDGED_CHANGE"),
        ({"crypto_orders": [{"id": "crypto-secret", "state": "confirmed"}]}, "order_activity", "AGENTIC_ACCOUNT_UNACKNOWLEDGED_CHANGE"),
    ],
)
def test_critical_changes_page_latch_and_redact(tmp_path, changes, change_class, code):
    from agents.account_tripwire import TripwireViolation
    from agents.safety_events import incident_active

    path = tmp_path / "agent.db"
    evaluate(path)
    with pytest.raises(TripwireViolation, match=code) as error:
        evaluate(path, cycle_id="c2", now=NOW + timedelta(days=1), **changes)

    assert error.value.change_class == change_class
    assert incident_active(path)
    with sqlite3.connect(path) as db:
        title, body = db.execute(
            "SELECT title,body FROM notification_outbox ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    assert title == "Agentic account change detected"
    assert "Review and revoke access if unrecognized" in body
    encoded = title + body + str(error.value)
    for forbidden in ("512.34", "17.25", "instrument-secret", "order-secret", "option-secret", "crypto-secret"):
        assert forbidden not in encoded


def test_acknowledgement_is_exact_expiring_and_one_shot(tmp_path):
    from agents.account_tripwire import TripwireViolation, acknowledge_change
    from agents.safety_events import incident_active

    path = tmp_path / "agent.db"
    evaluate(path)
    with pytest.raises(TripwireViolation) as caught:
        evaluate(path, cash="450", cycle_id="c2", now=NOW + timedelta(minutes=1))
    violation = caught.value

    for changes in (
        {"incident_id": "wrong"},
        {"expected_snapshot_hash": "0" * 64},
        {"change_class": "positions"},
        {"expires_at": NOW},
    ):
        arguments = {
            "incident_id": violation.incident_id,
            "expected_snapshot_hash": violation.snapshot_hash,
            "change_class": violation.change_class,
            "expires_at": NOW + timedelta(minutes=10),
            "csrf_confirmed": True,
            "now": NOW + timedelta(minutes=2),
            **changes,
        }
        with pytest.raises(ValueError):
            acknowledge_change(path, **arguments)
        assert incident_active(path)

    acknowledge_change(
        path,
        incident_id=violation.incident_id,
        expected_snapshot_hash=violation.snapshot_hash,
        change_class=violation.change_class,
        expires_at=NOW + timedelta(minutes=10),
        csrf_confirmed=True,
        now=NOW + timedelta(minutes=2),
    )
    assert not incident_active(path)
    with pytest.raises(ValueError):
        acknowledge_change(
            path,
            incident_id=violation.incident_id,
            expected_snapshot_hash=violation.snapshot_hash,
            change_class=violation.change_class,
            expires_at=NOW + timedelta(minutes=10),
            csrf_confirmed=True,
            now=NOW + timedelta(minutes=3),
        )


def test_acknowledgement_never_removes_user_owned_pause(tmp_path):
    from agents.account_tripwire import TripwireViolation, acknowledge_change

    path = tmp_path / "agent.db"
    pause = tmp_path / "STOP_TRADING"
    pause.write_text("Manual safety stop")
    original = pause.read_bytes()
    evaluate(path)
    with pytest.raises(TripwireViolation) as caught:
        evaluate(path, cash="400", cycle_id="c2", now=NOW + timedelta(minutes=1))
    violation = caught.value
    acknowledge_change(
        path,
        incident_id=violation.incident_id,
        expected_snapshot_hash=violation.snapshot_hash,
        change_class=violation.change_class,
        expires_at=NOW + timedelta(minutes=10),
        csrf_confirmed=True,
        now=NOW + timedelta(minutes=2),
    )
    assert pause.read_bytes() == original


def test_snapshot_payload_is_local_but_public_projection_is_redacted(tmp_path):
    from agents.account_tripwire import public_status

    path = tmp_path / "agent.db"
    evaluate(path, cash="512.34", positions=[{
        "instrument_id": "instrument-secret", "quantity": "17.25", "direction": "long"
    }])
    encoded = json.dumps(public_status(path), sort_keys=True)
    for forbidden in ("512.34", "17.25", "instrument-secret"):
        assert forbidden not in encoded
