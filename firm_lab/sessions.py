"""exchange_session_date: the trading session a daily observation belongs to.

A timestamp and a session date are different fields. The provider's daily bar begins at 00:00:00 UTC of its
session, so its session date is the UTC calendar date of that timestamp. Converting that instant to New York
time first gives the evening before, which is the wrong day. Control A stores its closes under that earlier
New York date; Firm Lab never does. Anything that does not match the expected convention fails closed.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .errors import FirmLabError

ET = ZoneInfo('America/New_York')


class SessionDateError(FirmLabError):
    pass


def utc_iso(moment) -> str:
    """One canonical text form for instants, so text comparison orders them correctly."""
    if isinstance(moment, str):
        moment = datetime.fromisoformat(moment.replace('Z', '+00:00'))
    if moment.tzinfo is None:
        raise SessionDateError('TIMEZONE_REQUIRED')
    return moment.astimezone(timezone.utc).isoformat()


def _weekday(day: date, what: str) -> date:
    if day.weekday() >= 5:
        raise SessionDateError(f'{what} resolves to a weekend ({day.isoformat()}): unexpected convention, refusing to guess')
    return day


def session_date_from_provider_daily_bar(begins_at: str) -> str:
    """Raw provider timestamp of a daily bar -> exchange session date (ISO)."""
    try:
        stamp = datetime.fromisoformat(str(begins_at).replace('Z', '+00:00'))
    except ValueError:
        raise SessionDateError('UNPARSEABLE_PROVIDER_TIMESTAMP') from None
    if stamp.tzinfo is None:
        raise SessionDateError('TIMEZONE_REQUIRED')
    utc = stamp.astimezone(timezone.utc)
    if utc.time() != time(0, 0):
        raise SessionDateError('DAILY_BAR_DOES_NOT_BEGIN_AT_00:00_UTC: unexpected convention, refusing to guess')
    return _weekday(utc.date(), 'provider daily bar').isoformat()


def session_date_from_official_label(label: str) -> str:
    """Control A's recorded label (the New York date of a 00:00 UTC bar start) -> the real session date.

    00:00 UTC is 19:00 or 20:00 the previous evening in New York, in winter and in summer alike, so the label
    is always exactly one calendar day before the session."""
    try:
        day = date.fromisoformat(str(label))
    except ValueError:
        raise SessionDateError('UNPARSEABLE_OFFICIAL_LABEL') from None
    return _weekday(day + timedelta(days=1), 'Official label + 1 day').isoformat()


def provider_timestamp_for(session_date: str) -> str:
    return f'{session_date}T00:00:00+00:00'


def is_completed(session_date: str, known_at) -> bool:
    """True once the regular session of that date has closed (16:00 New York) at or before ``known_at``."""
    if isinstance(known_at, str):
        known_at = datetime.fromisoformat(known_at.replace('Z', '+00:00'))
    close = datetime.combine(date.fromisoformat(session_date), time(16, 0), ET)
    return close <= known_at
