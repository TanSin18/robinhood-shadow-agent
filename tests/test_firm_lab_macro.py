"""Macro facts must never acquire an earlier availability time or overwrite a vintage."""
from datetime import datetime, timezone
import hashlib
import sqlite3

import pytest

from firm_lab import store
from firm_lab.errors import FirmLabError, IsolationError


NOW = datetime(2026, 10, 3, 16, tzinfo=timezone.utc)
RAW = b'{"synthetic_fixture":true}'


def observation(**changes):
    row = dict(series="unemployment_rate", value="4.3", unit="percent",
               period="2026-08", source="BLS", source_url="https://www.bls.gov/news.release/empsit.htm",
               source_timestamp="2026-09-04T12:30:00Z", published_at="2026-09-04T12:30:00Z",
               ingested_at="2026-09-04T12:31:00Z", revision=0,
               source_hash=hashlib.sha256(RAW).hexdigest())
    return row | changes


def lab(tmp_path):
    # Missing macro support must fail an assertion before any production code exists.
    from firm_lab import macro
    return macro.MacroStore(tmp_path / "research" / "firm.db", official_db=tmp_path / "official" / "agent.db")


def test_macro_domain_exists():
    import importlib.util
    assert importlib.util.find_spec("firm_lab.macro") is not None, "Missing macro point-in-time domain"


def test_revisions_append_and_are_invisible_before_known_at(tmp_path):
    db = lab(tmp_path)
    assert db.add_observation(observation(), raw=RAW, now=NOW) == "INSERTED"
    revised = observation(value="4.4", revision=1, published_at="2026-10-02T12:30:00Z",
                          source_timestamp="2026-10-02T12:30:00Z", ingested_at="2026-10-02T12:31:00Z")
    assert db.add_observation(revised, raw=RAW, now=NOW) == "REVISED"
    assert db.observations(known_by="2026-09-04T12:30:59Z") == []
    assert db.observations(known_by="2026-10-02T12:30:59Z")[0]["value"] == "4.3"
    assert db.observations(known_by="2026-10-02T12:31:00Z")[0]["value"] == "4.4"
    with sqlite3.connect(db.path) as cx:
        assert cx.execute("SELECT count(*) FROM macro_observations").fetchone()[0] == 2


def test_repeat_capture_is_idempotent_without_retiming_original(tmp_path):
    db = lab(tmp_path)
    db.add_observation(observation(), raw=RAW, now=NOW)
    assert db.add_observation(observation(ingested_at="2026-10-03T12:00:00Z"), raw=RAW, now=NOW) == "DUPLICATE"
    assert db.observations(known_by="2026-09-05T00:00:00Z")[0]["known_at"] == "2026-09-04T12:31:00+00:00"


@pytest.mark.parametrize("changes,code", [
    ({"published_at":None}, "MISSING_PUBLICATION_TIME"),
    ({"published_at":"2026-09-04"}, "TIMESTAMP_REQUIRES_OFFSET"),
    ({"published_at":"2026-09-04T12:30:00"}, "TIMESTAMP_REQUIRES_OFFSET"),
    ({"ingested_at":"2026-10-04T00:00:00Z"}, "FUTURE_TIMESTAMP"),
    ({"ingested_at":"2026-09-03T00:00:00Z"}, "INGESTION_PRECEDES_SOURCE"),
    ({"unit":"index"}, "UNIT_MISMATCH"),
    ({"value":"101"}, "IMPOSSIBLE_VALUE"),
    ({"value":"NaN"}, "IMPOSSIBLE_VALUE"),
    ({"source":"Fiction"}, "SERIES_SOURCE_MISMATCH"),
    ({"series":"alpha"}, "UNKNOWN_SERIES"),
    ({"period":"2026-13"}, "INVALID_PERIOD"),
    ({"source_hash":"a" * 64}, "SOURCE_HASH_MISMATCH"),
    ({"source_url":""}, "MISSING_PROVENANCE"),
    ({"source_url":"https://evil.example/bls.gov"}, "SOURCE_HOST_MISMATCH"),
    ({"revision":True}, "INVALID_REVISION"),
])
def test_invalid_facts_are_rejected_not_repaired(tmp_path, changes, code):
    db = lab(tmp_path)
    with pytest.raises(FirmLabError, match=code):
        db.add_observation(observation(**changes), raw=RAW, now=NOW)
    assert db.observations(known_by=NOW.isoformat()) == []


@pytest.mark.parametrize("changes", [
    {"value":"4.4"}, {"revision":2},
    {"value":"4.4", "revision":1, "published_at":"2026-09-03T12:30:00Z"},
])
def test_conflicting_or_out_of_order_revision_rejected(tmp_path, changes):
    db = lab(tmp_path)
    db.add_observation(observation(), raw=RAW, now=NOW)
    with pytest.raises(FirmLabError, match="UNEXPECTED_REVISION"):
        db.add_observation(observation(**changes), raw=RAW, now=NOW)


def test_revision_number_is_transactionally_unique(tmp_path):
    db = lab(tmp_path)
    db.add_observation(observation(), raw=RAW, now=NOW)
    other = lab(tmp_path)
    with pytest.raises(FirmLabError, match="UNEXPECTED_REVISION"):
        other.add_observation(observation(value="5.0"), raw=RAW, now=NOW)
    assert other.observations(known_by=NOW.isoformat())[0]["value"] == "4.3"


def test_timezone_offsets_use_instant_not_text_order(tmp_path):
    db = lab(tmp_path)
    db.add_observation(observation(published_at="2026-09-04T08:30:00-04:00",
                                   ingested_at="2026-09-04T08:31:00-04:00"), raw=RAW, now=NOW)
    assert len(db.observations(known_by="2026-09-04T12:31:00Z")) == 1
    assert db.observations(known_by="2026-09-04T08:30:59-04:00") == []


def test_macro_cannot_initialize_official_database(tmp_path):
    from firm_lab import macro
    official = tmp_path / "official" / "agent.db"
    official.parent.mkdir()
    official.write_bytes(b"official sentinel")
    with pytest.raises(IsolationError):
        macro.MacroStore(official, official_db=official)
    assert official.read_bytes() == b"official sentinel"


def test_macro_storage_has_no_execution_state(tmp_path):
    db = lab(tmp_path)
    db.add_observation(observation(), raw=RAW, now=NOW)
    with sqlite3.connect(db.path) as cx:
        tables = [r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        assert cx.execute("SELECT value FROM firm_meta WHERE key='mode'").fetchone()[0] == "BUILD_OBSERVE"
        assert cx.execute("SELECT count(*) FROM experiment_registry").fetchone()[0] == 0
    assert not any(word in table for table in tables for word in store.FORBIDDEN_TABLE_WORDS)


def event(**changes):
    base = observation()
    for key in ("series", "value", "unit"):
        del base[key]
    return base | dict(event_id="bls-unemployment-2026-08", event_type="unemployment_release",
                       series="unemployment_rate", scheduled_at="2026-09-04T12:30:00Z",
                       actual_published_at="2026-09-04T12:30:00Z", released_value="4.3",
                       prior_value="4.2", revised_prior_value=None, unit="percent", consensus="UNAVAILABLE") | changes


def test_macro_event_identity_and_actual_vs_scheduled(tmp_path):
    db = lab(tmp_path)
    db.add_event(event(actual_published_at="2026-09-04T12:30:30Z"), raw=RAW, now=NOW)
    rows = db.events(known_by="2026-09-04T12:31:00Z")
    assert rows[0]["scheduled_at"] == "2026-09-04T12:30:00+00:00"
    assert rows[0]["actual_published_at"] == "2026-09-04T12:30:30+00:00"
    assert rows[0]["consensus"] == "UNAVAILABLE"


def test_scheduled_event_does_not_imply_actual_release_or_value(tmp_path):
    db = lab(tmp_path)
    db.add_event(event(period="2026-10", scheduled_at="2026-11-06T13:30:00Z", actual_published_at=None,
                       released_value=None, prior_value=None), raw=RAW, now=NOW)
    row = db.events(known_by=NOW.isoformat())[0]
    assert row["actual_published_at"] is None
    assert row["released_value"] is None


def test_actual_release_cannot_claim_a_future_observation_period(tmp_path):
    db = lab(tmp_path)
    with pytest.raises(FirmLabError, match="FUTURE_OBSERVATION_PERIOD"):
        db.add_event(event(period="2026-11"), raw=RAW, now=NOW)
    assert db.events(known_by=NOW.isoformat()) == []


@pytest.mark.parametrize("changes,code", [
    ({"event_type":"cpi_release"}, "EVENT_SERIES_MISMATCH"),
    ({"actual_published_at":None}, "VALUE_WITHOUT_RELEASE"),
    ({"actual_published_at":"2026-10-04T12:30:00Z"}, "FUTURE_TIMESTAMP"),
    ({"consensus":"4.1"}, "CONSENSUS_UNAVAILABLE"),
    ({"unit":"index"}, "UNIT_MISMATCH"),
    ({"released_value":"-1"}, "IMPOSSIBLE_VALUE"),
    ({"prior_value":"101"}, "IMPOSSIBLE_VALUE"),
    ({"revised_prior_value":"NaN"}, "IMPOSSIBLE_VALUE"),
    ({"event_id":""}, "MISSING_EVENT_ID"),
])
def test_event_rejects_invented_release_consensus_or_wrong_identity(tmp_path, changes, code):
    db = lab(tmp_path)
    with pytest.raises(FirmLabError, match=code):
        db.add_event(event(**changes), raw=RAW, now=NOW)
    assert db.events(known_by=NOW.isoformat()) == []


def test_calendar_revision_preserves_prior_schedule_and_values(tmp_path):
    db = lab(tmp_path)
    first = event(actual_published_at=None, released_value=None, prior_value=None)
    assert db.add_event(first, raw=RAW, now=NOW) == "INSERTED"
    assert db.add_event(first, raw=RAW, now=NOW) == "DUPLICATE"
    second = event(revision=1, published_at="2026-09-04T12:32:00Z", ingested_at="2026-09-04T12:33:00Z")
    assert db.add_event(second, raw=RAW, now=NOW) == "REVISED"
    assert db.events(known_by="2026-09-04T12:32:59Z")[0]["released_value"] is None
    assert db.events(known_by="2026-09-04T12:33:00Z")[0]["released_value"] == "4.3"


def test_future_observation_period_rejected(tmp_path):
    db = lab(tmp_path)
    with pytest.raises(FirmLabError, match="FUTURE_OBSERVATION_PERIOD"):
        db.add_observation(observation(period="2026-11"), raw=RAW, now=NOW)


def test_nonserializable_extra_field_never_reaches_database(tmp_path):
    db = lab(tmp_path)
    with pytest.raises(FirmLabError, match="UNSUPPORTED_MACRO_FIELD"):
        db.add_observation(observation(signal="BUY"), raw=RAW, now=NOW)
