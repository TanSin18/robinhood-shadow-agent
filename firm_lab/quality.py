"""Data-quality checks for provider responses. They flag; they never repair.

Every check returns a list of ``Issue``. Records are read, never changed: a questionable value stays exactly as
the provider sent it and the response is rejected with the reasons attached.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from .schemas import BARE_GREEK_NAMES, NOT_A_TOTAL_RETURN, SCHEMAS

STALE_TIMESTAMP = 'STALE_TIMESTAMP'
FUTURE_TIMESTAMP = 'FUTURE_TIMESTAMP'
UNPARSEABLE_TIMESTAMP = 'UNPARSEABLE_TIMESTAMP'
TIMEZONE_MISSING = 'TIMEZONE_MISSING'
MISSING_FIELD = 'MISSING_FIELD'
MISSING_IDENTIFIER = 'MISSING_IDENTIFIER'
DUPLICATE_RECORD = 'DUPLICATE_RECORD'
IMPOSSIBLE_VALUE = 'IMPOSSIBLE_VALUE'
CONFLICTING_INSTRUMENT_IDENTITY = 'CONFLICTING_INSTRUMENT_IDENTITY'
MISSING_UNITS_OR_CURRENCY = 'MISSING_UNITS_OR_CURRENCY'
NON_MONOTONIC_TIMESTAMPS = 'NON_MONOTONIC_TIMESTAMPS'
INCOMPLETE_HISTORICAL_WINDOW = 'INCOMPLETE_HISTORICAL_WINDOW'
NOT_POINT_IN_TIME = 'NOT_POINT_IN_TIME'
UNNAMESPACED_GREEK = 'UNNAMESPACED_GREEK'
YIELD_IS_NOT_TOTAL_RETURN = 'YIELD_IS_NOT_TOTAL_RETURN'
VALUE_NOT_ALLOWED = 'VALUE_NOT_ALLOWED'
NOT_A_RECORD = 'NOT_A_RECORD'
UNKNOWN_DOMAIN = 'UNKNOWN_DOMAIN'
INCOMPLETE_PROVENANCE = 'INCOMPLETE_PROVENANCE'
KNOWN_BEFORE_SOURCE = 'KNOWN_BEFORE_SOURCE'


@dataclass(frozen=True)
class Issue:
    code: str
    detail: str
    index: Optional[int] = None          # position of the record in the response, when the issue is about one record
    field: Optional[str] = None


@dataclass(frozen=True)
class Report:
    domain: str
    records_checked: int
    issues: tuple = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return not self.issues and self.records_checked > 0

    def codes(self) -> list:
        return sorted({i.code for i in self.issues})


def _present(value) -> bool:
    return value is not None and str(value).strip() != ''


def parse_timestamp(value):
    """A timezone-aware datetime, or the issue code explaining why not. The original text is never altered."""
    if isinstance(value, datetime):
        stamp = value
    else:
        try:
            stamp = datetime.fromisoformat(str(value).strip().replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return None, UNPARSEABLE_TIMESTAMP
    if stamp.tzinfo is None:
        return None, TIMEZONE_MISSING
    return stamp, None


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def check_fields(records, required) -> list:
    out = []
    for i, r in enumerate(records):
        for name in required:
            if not _present(r.get(name)):
                out.append(Issue(MISSING_FIELD, f'{name} is missing', i, name))
    return out


def check_identifiers(records, identifier) -> list:
    return [Issue(MISSING_IDENTIFIER, f'{identifier} is missing', i, identifier) for i, r in enumerate(records) if not _present(r.get(identifier))]


def check_timestamps(records, fields, *, now, max_age: Optional[timedelta] = None) -> list:
    """Unparseable, timezone-less, future and (when ``max_age`` is given) stale timestamps."""
    out = []
    now_stamp, problem = parse_timestamp(now)
    if problem:
        return [Issue(problem, 'the reference time itself is not a timezone-aware timestamp')]
    for i, r in enumerate(records):
        for name in fields:
            if not _present(r.get(name)):
                continue                                     # absence is reported by check_fields
            stamp, problem = parse_timestamp(r[name])
            if problem:
                out.append(Issue(problem, f'{name}={r[name]!r}', i, name))
            elif stamp > now_stamp:
                out.append(Issue(FUTURE_TIMESTAMP, f'{name}={r[name]!r} is after {now_stamp.isoformat()}', i, name))
            elif max_age is not None and now_stamp - stamp > max_age:
                out.append(Issue(STALE_TIMESTAMP, f'{name}={r[name]!r} is older than {max_age}', i, name))
    return out


def check_duplicates(records, key) -> list:
    out, seen = [], {}
    if not key:
        return out
    for i, r in enumerate(records):
        k = tuple(str(r.get(name)) for name in key)
        if k in seen:
            out.append(Issue(DUPLICATE_RECORD, f'same {", ".join(key)} as record {seen[k]}', i))
        else:
            seen[k] = i
    return out


def check_values(records, *, positive=(), non_negative=()) -> list:
    """Values that cannot be true: a non-number where a number belongs, a price at or below zero, a negative count,
    a high below a low, an ask below a bid."""
    out = []
    for i, r in enumerate(records):
        for name in tuple(positive) + tuple(non_negative):
            if not _present(r.get(name)):
                continue
            number = _number(r[name])
            if number is None:
                out.append(Issue(IMPOSSIBLE_VALUE, f'{name}={r[name]!r} is not a finite number', i, name))
            elif name in positive and number <= 0:
                out.append(Issue(IMPOSSIBLE_VALUE, f'{name}={r[name]!r} must be above zero', i, name))
            elif name in non_negative and number < 0:
                out.append(Issue(IMPOSSIBLE_VALUE, f'{name}={r[name]!r} must not be negative', i, name))
        low, high = _number(r.get('low')), _number(r.get('high'))
        if low is not None and high is not None:
            if high < low:
                out.append(Issue(IMPOSSIBLE_VALUE, f'high {r["high"]!r} is below low {r["low"]!r}', i, 'high'))
            for name in ('open', 'close'):
                value = _number(r.get(name))
                if value is not None and not low <= value <= high:
                    out.append(Issue(IMPOSSIBLE_VALUE, f'{name} {r[name]!r} is outside low/high', i, name))
        bid, ask = _number(r.get('bid')), _number(r.get('ask'))
        if bid is not None and ask is not None and ask < bid:
            out.append(Issue(IMPOSSIBLE_VALUE, f'ask {r["ask"]!r} is below bid {r["bid"]!r}', i, 'ask'))
    return out


def check_identity(records, identifier, expected) -> list:
    """Every record must be about the instrument that was asked for."""
    if expected is None:
        return []
    return [Issue(CONFLICTING_INSTRUMENT_IDENTITY, f'{identifier}={r.get(identifier)!r} but {expected!r} was requested', i, identifier)
            for i, r in enumerate(records) if _present(r.get(identifier)) and str(r[identifier]) != str(expected)]


def check_units(records, money) -> list:
    """An amount of money without a currency is not usable."""
    out = []
    for i, r in enumerate(records):
        if any(_present(r.get(name)) for name in money) and not _present(r.get('currency')):
            out.append(Issue(MISSING_UNITS_OR_CURRENCY, 'money amounts without a currency', i, 'currency'))
    return out


def check_monotonic(records, field_name) -> list:
    out, last = [], None
    if not field_name:
        return out
    for i, r in enumerate(records):
        stamp, problem = parse_timestamp(r.get(field_name)) if _present(r.get(field_name)) else (None, 'absent')
        if problem:
            continue                                         # reported elsewhere
        if last is not None and stamp < last:
            out.append(Issue(NON_MONOTONIC_TIMESTAMPS, f'{field_name} goes backwards at record {i}', i, field_name))
        last = stamp
    return out


def check_window(records, field_name, expected) -> list:
    """``expected``: the values (for example session dates) a complete window must contain."""
    if not expected:
        return []
    have = {str(r.get(field_name)) for r in records}
    missing = [str(x) for x in expected if str(x) not in have]
    return [Issue(INCOMPLETE_HISTORICAL_WINDOW, f'{len(missing)} of {len(expected)} expected {field_name} values are missing '
                                                f'(first: {missing[0]})', None, field_name)] if missing else []


def check_point_in_time(records, field_name) -> list:
    """A value with no dated snapshot is only "today's" value and cannot be used for clean history."""
    if not field_name:
        return []
    return [Issue(NOT_POINT_IN_TIME, f'{field_name} is missing: this is not a dated snapshot', i, field_name)
            for i, r in enumerate(records) if not _present(r.get(field_name))]


def check_greek_namespaces(records) -> list:
    """``provider_delta`` or ``model_estimated_delta``; never a bare ``delta``."""
    out = []
    for i, r in enumerate(records):
        for name in sorted(set(r) & BARE_GREEK_NAMES):
            out.append(Issue(UNNAMESPACED_GREEK, f'{name!r} does not say where it came from; use provider_{name} or model_estimated_{name}', i, name))
    return out


def check_allowed(records, allowed) -> list:
    out = []
    for i, r in enumerate(records):
        for name, values in (allowed or {}).items():
            if _present(r.get(name)) and r[name] not in values:
                code = YIELD_IS_NOT_TOTAL_RETURN if name == 'measure' and str(r[name]).upper() in NOT_A_TOTAL_RETURN else VALUE_NOT_ALLOWED
                out.append(Issue(code, f'{name}={r[name]!r}; allowed: {", ".join(values)}', i, name))
    return out


def check_provenance(provenance) -> list:
    if provenance is None:
        return [Issue(INCOMPLETE_PROVENANCE, 'no provenance was supplied')]
    out = [Issue(INCOMPLETE_PROVENANCE, f'{name} is missing', None, name) for name in provenance.missing()]
    known, bad_known = parse_timestamp(provenance.known_at) if provenance.known_at else (None, 'absent')
    source, bad_source = parse_timestamp(provenance.source_timestamp) if provenance.source_timestamp else (None, 'absent')
    ingested, bad_ingested = parse_timestamp(provenance.ingested_at) if provenance.ingested_at else (None, 'absent')
    for name, problem, value in (('known_at', bad_known, provenance.known_at), ('source_timestamp', bad_source, provenance.source_timestamp),
                                 ('ingested_at', bad_ingested, provenance.ingested_at)):
        if problem in (UNPARSEABLE_TIMESTAMP, TIMEZONE_MISSING):
            out.append(Issue(problem, f'provenance {name}={value!r}', None, name))
    if known is not None and source is not None and known < source:
        out.append(Issue(KNOWN_BEFORE_SOURCE, 'known_at is earlier than the source timestamp: nothing can be known before it exists', None, 'known_at'))
    return out


def validate(domain, records, *, now, provenance=None, expected_instrument=None, max_age=None, expected_window=None, window_field=None,
             require_provenance=True) -> Report:
    """Runs every applicable check for the domain. The records are not modified."""
    schema = SCHEMAS.get(domain)
    if schema is None:
        return Report(domain, 0, (Issue(UNKNOWN_DOMAIN, f'no schema is defined for {domain!r}'),))
    if not isinstance(records, (list, tuple)):
        return Report(domain, 0, (Issue(NOT_A_RECORD, 'the response is not a list of records'),))
    bad = [Issue(NOT_A_RECORD, 'the record is not a mapping of field names to values', i) for i, r in enumerate(records) if not isinstance(r, dict)]
    if bad:
        return Report(domain, len(records), tuple(bad))
    issues = []
    if require_provenance:
        issues += check_provenance(provenance)
    issues += check_identifiers(records, schema.identifier)
    issues += check_fields(records, [f for f in schema.required if f != schema.identifier])
    issues += check_allowed(records, schema.allowed)
    issues += check_timestamps(records, schema.timestamps, now=now, max_age=max_age)
    issues += check_duplicates(records, schema.key)
    issues += check_values(records, positive=schema.positive, non_negative=schema.non_negative)
    issues += check_identity(records, schema.identifier, expected_instrument)
    issues += check_units(records, schema.money)
    issues += check_monotonic(records, schema.order_by)
    issues += check_point_in_time(records, schema.point_in_time)
    issues += check_greek_namespaces(records)
    issues += check_window(records, window_field or 'exchange_session_date', expected_window)
    return Report(domain, len(records), tuple(issues))
