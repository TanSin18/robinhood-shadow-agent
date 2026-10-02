"""Data-quality checks for provider responses. They flag; they never repair.

Every check returns a list of ``Issue``. Records are read, never changed: a questionable value stays exactly as
the provider sent it and the response is rejected with the reasons attached.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from .schemas import BARE_GREEK_NAMES, MONEY_UNITS, NOT_A_TOTAL_RETURN, SCHEMAS, UNAVAILABLE
from .sessions import ET

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
SESSION_MISMATCH = 'SESSION_MISMATCH'
OUTSIDE_SESSION_HOURS = 'OUTSIDE_SESSION_HOURS'
SESSION_DATE_MISMATCH = 'SESSION_DATE_MISMATCH'
CROSSED_MARKET = 'CROSSED_MARKET'
KNOWN_AT_NOT_HEADER = 'KNOWN_AT_NOT_HEADER'
JSON_TIME_REWRITTEN = 'JSON_TIME_REWRITTEN'


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


def check_values(records, *, positive=(), non_negative=(), numeric=()) -> list:
    """Values that cannot be true: a non-number where a number belongs, a price at or below zero, a negative count,
    a high below a low, an ask below a bid."""
    out = []
    for i, r in enumerate(records):
        for name in tuple(positive) + tuple(non_negative) + tuple(numeric):
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
        if bid is not None and ask is not None and bid > 0 and ask > 0 and ask < bid:      # a side at 0 means no quote on that side
            out.append(Issue(IMPOSSIBLE_VALUE, f'ask {r["ask"]!r} is below bid {r["bid"]!r} (crossed market)', i, 'ask'))
            out.append(Issue(CROSSED_MARKET, f'bid {r["bid"]!r} above ask {r["ask"]!r}', i, 'ask'))
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
        is_money = any(_present(r.get(name)) for name in money) or r.get('units') in MONEY_UNITS
        if is_money and not _present(r.get('currency')):
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


def check_timestamp_or_unavailable(records, fields) -> list:
    """The field must be there, as a timezone-aware timestamp or as the literal UNAVAILABLE. A date alone is not a timestamp."""
    out = []
    for i, r in enumerate(records):
        for name in fields:
            value = r.get(name)
            if value == UNAVAILABLE:
                continue
            if not _present(value):
                out.append(Issue(MISSING_FIELD, f'{name} must be a timestamp or the literal UNAVAILABLE', i, name))
                continue
            _, problem = parse_timestamp(value)
            if problem:
                out.append(Issue(problem, f'{name}={value!r} is not a timezone-aware timestamp (use UNAVAILABLE if it is not known)', i, name))
    return out


def check_any_of(records, groups) -> list:
    """At least one field of each group must be present. A name starting with ``*`` matches any field ending with the rest."""
    out = []
    for i, r in enumerate(records):
        for group in groups or ():
            found = any((_present(r.get(n)) if not n.startswith('*') else any(k.endswith(n[1:]) and _present(v) for k, v in r.items())) for n in group)
            if not found:
                out.append(Issue(MISSING_FIELD, 'one of ' + ', '.join(group) + ' is required', i, group[0]))
    return out


def check_filing_times(records) -> list:
    """The filing's known-at is its header time and nothing else, and the JSON text is carried exactly as sent: the two
    copies of it must be identical, and a flagged conflict must not have been "fixed" into agreement."""
    out = []
    for i, r in enumerate(records):
        if _present(r.get('accepted_timestamp')) and r.get('accepted_timestamp') != r.get('accepted_timestamp_header'):
            out.append(Issue(KNOWN_AT_NOT_HEADER, 'accepted_timestamp must be the filing-header time', i, 'accepted_timestamp'))
        if r.get('accepted_timestamp_json') != r.get('accepted_timestamp_raw'):
            out.append(Issue(JSON_TIME_REWRITTEN, 'accepted_timestamp_json differs from the text the SEC sent', i, 'accepted_timestamp_json'))
        if not isinstance(r.get('acceptance_time_conflict'), bool) and _present(r.get('acceptance_time_conflict')):
            out.append(Issue(VALUE_NOT_ALLOWED, 'acceptance_time_conflict must be true or false', i, 'acceptance_time_conflict'))
    return out


def session_of(stamp) -> str:
    """pre_market 04:00-09:30, regular 09:30-16:00, post_market 16:00-20:00 New York clock time; '' outside those hours.
    Clock only: an exchange early close is not known here, so a bar after an early close is still labelled regular."""
    local = stamp.astimezone(ET)
    minutes = local.hour * 60 + local.minute
    if 240 <= minutes < 570:
        return 'pre_market'
    if 570 <= minutes < 960:
        return 'regular'
    if 960 <= minutes < 1200:
        return 'post_market'
    return ''


def check_sessions(records, field_name='bar_start') -> list:
    """The stated session and session date must agree with the bar's own timestamp."""
    out = []
    for i, r in enumerate(records):
        if 'session' not in r or not _present(r.get(field_name)):
            continue
        stamp, problem = parse_timestamp(r[field_name])
        if problem:
            continue
        actual = session_of(stamp)
        if not actual:
            out.append(Issue(OUTSIDE_SESSION_HOURS, f'{field_name}={r[field_name]!r} is outside 04:00-20:00 New York time', i, field_name))
        elif r.get('session') != actual:
            out.append(Issue(SESSION_MISMATCH, f'labelled {r.get("session")!r} but the timestamp is in {actual}', i, 'session'))
        if _present(r.get('exchange_session_date')) and str(r['exchange_session_date']) != stamp.astimezone(ET).date().isoformat():
            out.append(Issue(SESSION_DATE_MISMATCH, f'exchange_session_date {r["exchange_session_date"]!r} is not the New York date of the bar', i,
                             'exchange_session_date'))
    return out


def missing_regular_minutes(records, field_name='bar_start') -> dict:
    """A diagnostic, not a failure: how many regular-session minutes have no bar, per session date. A minute with no
    eligible trade legitimately has no bar."""
    seen = {}
    for r in records:
        stamp, problem = parse_timestamp(r.get(field_name)) if _present(r.get(field_name)) else (None, 'absent')
        if problem or session_of(stamp) != 'regular':
            continue
        seen.setdefault(stamp.astimezone(ET).date().isoformat(), set()).add(stamp.astimezone(ET).strftime('%H:%M'))
    return {day: 390 - len(minutes) for day, minutes in sorted(seen.items())}


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
    issues += check_values(records, positive=schema.positive, non_negative=schema.non_negative, numeric=schema.numeric)
    issues += check_timestamp_or_unavailable(records, schema.timestamp_or_unavailable)
    issues += check_any_of(records, schema.any_of)
    if domain == 'intraday_bars':
        issues += check_sessions(records)
    if domain == 'filings':
        issues += check_filing_times(records)
    if domain == 'treasury_auctions':
        from . import treasury
        issues += [Issue(code, detail, i) for i, code, detail in treasury.check_records(records)]
    issues += check_identity(records, schema.identifier, expected_instrument)
    issues += check_units(records, schema.money)
    issues += check_monotonic(records, schema.order_by)
    issues += check_point_in_time(records, schema.point_in_time)
    issues += check_greek_namespaces(records)
    issues += check_window(records, window_field or 'exchange_session_date', expected_window)
    return Report(domain, len(records), tuple(issues))
