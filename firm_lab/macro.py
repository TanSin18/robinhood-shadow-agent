"""Factual macro vintages only. No network, trading imports, signals or activation.

An exact, offset-aware publication timestamp is required. A release date is not
a release time. Collectors must supply cited timing evidence or reject the row.
``known_at`` is conservative local availability: max(publication, source,
ingestion). Historical publication alone never backdates a later capture.
"""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

from .errors import FirmLabError
from .store import FirmLabStore, canonical


# Identity, units and broad plausibility bounds, not a macro scoring rubric.
# The percent ranges allow negative rates; payroll change is not payroll level.
SERIES = {
    "fed_target_lower": ("percent", -10, 100, ("Federal Reserve", "FRED")),
    "fed_target_upper": ("percent", -10, 100, ("Federal Reserve", "FRED")),
    "effective_federal_funds": ("percent", -10, 100, ("New York Fed", "FRED")),
    "treasury_2y": ("percent", -10, 100, ("US Treasury", "FRED")),
    "treasury_10y": ("percent", -10, 100, ("US Treasury", "FRED")),
    "treasury_3m": ("percent", -10, 100, ("US Treasury", "FRED")),
    "cpi_headline": ("index_1982_84_100_sa", 0, 10000, ("BLS", "FRED")),
    "cpi_core": ("index_1982_84_100_sa", 0, 10000, ("BLS", "FRED")),
    "pce_headline": ("index_2017_100_sa", 0, 10000, ("BEA", "FRED")),
    "pce_core": ("index_2017_100_sa", 0, 10000, ("BEA", "FRED")),
    "unemployment_rate": ("percent", 0, 100, ("BLS", "FRED")),
    "nonfarm_payroll_change": ("thousand_persons_sa", -100000, 100000, ("BLS", "FRED")),
}
SOURCE_HOSTS = {
    "Federal Reserve": ("www.federalreserve.gov", "federalreserve.gov"),
    "New York Fed": ("markets.newyorkfed.org", "www.newyorkfed.org"),
    "US Treasury": ("home.treasury.gov", "www.treasury.gov"),
    "BLS": ("www.bls.gov", "api.bls.gov"),
    "BEA": ("www.bea.gov", "apps.bea.gov"),
    "FRED": ("api.stlouisfed.org", "fred.stlouisfed.org", "alfred.stlouisfed.org"),
}
EVENT_SERIES = {
    "fomc_rate_decision": ("fed_target_lower", "fed_target_upper"),
    "fomc_statement": ("fed_target_lower", "fed_target_upper"),
    "cpi_release": ("cpi_headline", "cpi_core"),
    "pce_release": ("pce_headline", "pce_core"),
    "payrolls_release": ("nonfarm_payroll_change",),
    "unemployment_release": ("unemployment_rate",),
}
SCHEMA = (
    "CREATE TABLE IF NOT EXISTS macro_observations (id INTEGER PRIMARY KEY, series TEXT NOT NULL, period TEXT NOT NULL, "
    "revision INTEGER NOT NULL, published_at TEXT NOT NULL, known_at TEXT NOT NULL, payload_json TEXT NOT NULL, "
    "record_hash TEXT NOT NULL UNIQUE, UNIQUE(series,period,revision))",
    "CREATE INDEX IF NOT EXISTS macro_known ON macro_observations(series,known_at,period)",
    "CREATE TABLE IF NOT EXISTS macro_events (id INTEGER PRIMARY KEY, event_id TEXT NOT NULL, revision INTEGER NOT NULL, "
    "published_at TEXT NOT NULL, known_at TEXT NOT NULL, payload_json TEXT NOT NULL, record_hash TEXT NOT NULL UNIQUE, "
    "UNIQUE(event_id,revision))",
)


def instant(value, *, missing="MISSING_TIMESTAMP"):
    if not value:
        raise FirmLabError(missing)
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise FirmLabError("INVALID_TIMESTAMP") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise FirmLabError("TIMESTAMP_REQUIRES_OFFSET")
    return stamp.astimezone(timezone.utc)


def _period(value):
    try:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", value):
            raise ValueError
        date.fromisoformat(value + "-01" if len(value) == 7 else value)
    except ValueError as exc:
        raise FirmLabError("INVALID_PERIOD") from exc


def _provenance(row, raw, now):
    row = dict(row)
    if not row.get("source_url") or not row.get("source_hash") or not row.get("source"):
        raise FirmLabError("MISSING_PROVENANCE")
    host = re.fullmatch(r"https://([^/?#:]+)(?:/[^\s#]*)?", row["source_url"])
    if not host or host[1] not in SOURCE_HOSTS.get(row["source"], ()):
        raise FirmLabError("SOURCE_HOST_MISMATCH")
    # Do not store authentication parameters in public provenance.
    if re.search(r"(?i)(api[_-]?key|token|secret|password)=", row["source_url"]):
        raise FirmLabError("PRIVATE_PROVENANCE_REFUSED")
    if not isinstance(raw, bytes) or not raw or hashlib.sha256(raw).hexdigest() != row["source_hash"]:
        raise FirmLabError("SOURCE_HASH_MISMATCH")
    published = instant(row.get("published_at"), missing="MISSING_PUBLICATION_TIME")
    source = instant(row.get("source_timestamp"))
    ingested = instant(row.get("ingested_at"))
    ceiling = instant(now.isoformat())
    if max(published, source, ingested) > ceiling:
        raise FirmLabError("FUTURE_TIMESTAMP")
    if ingested < max(published, source):
        raise FirmLabError("INGESTION_PRECEDES_SOURCE")
    for key, value in (("published_at", published), ("source_timestamp", source), ("ingested_at", ingested)):
        row[key] = value.isoformat()
    row["known_at"] = max(published, source, ingested).isoformat()
    if type(row.get("revision")) is not int or row["revision"] < 0:
        raise FirmLabError("INVALID_REVISION")
    _period(row.get("period"))
    return row


def _definition(row):
    definition = SERIES.get(row.get("series"))
    if definition is None:
        raise FirmLabError("UNKNOWN_SERIES")
    unit, low, high, sources = definition
    if row.get("source") not in sources:
        raise FirmLabError("SERIES_SOURCE_MISMATCH")
    if row.get("unit") != unit:
        raise FirmLabError("UNIT_MISMATCH")
    return low, high


def _value(value, low, high):
    try:
        value = Decimal(str(value))
        if not value.is_finite() or not low <= value <= high:
            raise InvalidOperation
    except (InvalidOperation, ValueError) as exc:
        raise FirmLabError("IMPOSSIBLE_VALUE") from exc


def validate_observation(row, *, raw, now):
    low, high = _definition(row)
    _value(row.get("value"), low, high)
    allowed = {"series", "value", "unit", "period", "source", "source_url", "source_timestamp", "published_at",
               "ingested_at", "revision", "source_hash"}
    if set(row) - allowed:
        raise FirmLabError("UNSUPPORTED_MACRO_FIELD")
    validated = _provenance(row, raw, now)
    period = row["period"] + "-01" if len(row["period"]) == 7 else row["period"]
    if date.fromisoformat(period) > instant(validated["published_at"]).date():
        raise FirmLabError("FUTURE_OBSERVATION_PERIOD")
    return validated


def validate_event(row, *, raw, now):
    if not isinstance(row.get("event_id"), str) or not row["event_id"].strip():
        raise FirmLabError("MISSING_EVENT_ID")
    if row.get("series") not in EVENT_SERIES.get(row.get("event_type"), ()):
        raise FirmLabError("EVENT_SERIES_MISMATCH")
    if row.get("consensus") != "UNAVAILABLE":
        raise FirmLabError("CONSENSUS_UNAVAILABLE")
    low, high = _definition(row)
    allowed = {"event_id", "event_type", "series", "unit", "period", "source", "source_url", "source_timestamp",
               "published_at", "ingested_at", "revision", "source_hash", "scheduled_at", "actual_published_at",
               "released_value", "prior_value", "revised_prior_value", "consensus"}
    if set(row) - allowed:
        raise FirmLabError("UNSUPPORTED_MACRO_FIELD")
    for field in ("released_value", "prior_value", "revised_prior_value"):
        if row.get(field) is not None:
            _value(row[field], low, high)
    result = _provenance(row, raw, now)
    if row.get("scheduled_at") is not None:
        result["scheduled_at"] = instant(row["scheduled_at"]).isoformat()
    if row.get("actual_published_at") is None:
        if any(row.get(k) is not None for k in ("released_value", "revised_prior_value")):
            raise FirmLabError("VALUE_WITHOUT_RELEASE")
    else:
        actual = instant(row["actual_published_at"])
        if actual > instant(now.isoformat()):
            raise FirmLabError("FUTURE_TIMESTAMP")
        if actual > instant(result["ingested_at"]):
            raise FirmLabError("INGESTION_PRECEDES_SOURCE")
        period = row["period"] + "-01" if len(row["period"]) == 7 else row["period"]
        if date.fromisoformat(period) > actual.date():
            raise FirmLabError("FUTURE_OBSERVATION_PERIOD")
        result["actual_published_at"] = actual.isoformat()
        result["known_at"] = max(instant(result["known_at"]), actual).isoformat()
    return result


class MacroStore:
    """Opt-in research schema. Cannot share Official's directory; no execution handle."""

    def __init__(self, path, *, official_db):
        self.lab = FirmLabStore(path, official_db=official_db)
        self.path = self.lab.path
        with self.lab.connect() as db:
            for statement in SCHEMA:
                db.execute(statement)

    def add_observation(self, row, *, raw, now):
        row = validate_observation(row, raw=raw, now=now)
        identity = {k: v for k, v in row.items() if k not in ("ingested_at", "known_at")}
        digest = hashlib.sha256(canonical(identity).encode()).hexdigest()
        with self.lab.connect() as db:
            # Serialize revision checks with insertion; another writer cannot race the chain.
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM macro_observations WHERE record_hash=?", (digest,)).fetchone():
                return "DUPLICATE"
            prior = db.execute("SELECT revision,published_at FROM macro_observations WHERE series=? AND period=? "
                               "ORDER BY revision DESC LIMIT 1", (row["series"], row["period"])).fetchone()
            if (prior is None and row["revision"] != 0) or (prior is not None and
                    (row["revision"] != prior[0] + 1 or row["published_at"] <= prior[1])):
                raise FirmLabError("UNEXPECTED_REVISION")
            db.execute("INSERT INTO macro_observations(series,period,revision,published_at,known_at,payload_json,record_hash) "
                       "VALUES(?,?,?,?,?,?,?)", (row["series"], row["period"], row["revision"], row["published_at"],
                                                 row["known_at"], canonical(row), digest))
        return "REVISED" if prior else "INSERTED"

    def observations(self, *, known_by):
        cutoff = instant(known_by).isoformat()
        latest = {}
        with self.lab.connect() as db:
            for (payload,) in db.execute("SELECT payload_json FROM macro_observations WHERE known_at<=? "
                                        "ORDER BY series,period,revision", (cutoff,)):
                row = json.loads(payload)
                latest[row["series"], row["period"]] = row
        return list(latest.values())

    def add_event(self, row, *, raw, now):
        row = validate_event(row, raw=raw, now=now)
        identity = {k: v for k, v in row.items() if k not in ("ingested_at", "known_at")}
        digest = hashlib.sha256(canonical(identity).encode()).hexdigest()
        with self.lab.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM macro_events WHERE record_hash=?", (digest,)).fetchone():
                return "DUPLICATE"
            prior = db.execute("SELECT revision,published_at,payload_json FROM macro_events WHERE event_id=? "
                               "ORDER BY revision DESC LIMIT 1", (row["event_id"],)).fetchone()
            if (prior is None and row["revision"] != 0) or (prior is not None and
                    (row["revision"] != prior[0] + 1 or row["published_at"] <= prior[1])):
                raise FirmLabError("UNEXPECTED_REVISION")
            if prior:
                old = json.loads(prior[2])
                if any(row[k] != old[k] for k in ("event_type", "series", "period", "unit", "source")):
                    raise FirmLabError("EVENT_SERIES_MISMATCH")
            db.execute("INSERT INTO macro_events(event_id,revision,published_at,known_at,payload_json,record_hash) "
                       "VALUES(?,?,?,?,?,?)", (row["event_id"], row["revision"], row["published_at"], row["known_at"],
                                               canonical(row), digest))
        return "REVISED" if prior else "INSERTED"

    def events(self, *, known_by):
        cutoff = instant(known_by).isoformat()
        latest = {}
        with self.lab.connect() as db:
            for (payload,) in db.execute("SELECT payload_json FROM macro_events WHERE known_at<=? ORDER BY revision", (cutoff,)):
                row = json.loads(payload)
                latest[row["event_id"]] = row
        return list(latest.values())
