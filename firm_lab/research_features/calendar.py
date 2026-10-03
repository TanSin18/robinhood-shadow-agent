"""Exchange-session boundaries, not inferred source publication timestamps."""
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo
import exchange_calendars
from .types import Request, timestamp


@lru_cache(maxsize=1)
def calendar():
    return exchange_calendars.get_calendar('XNYS')


def session_close(session):
    try:
        return calendar().session_close(session).isoformat()
    except (ValueError, KeyError) as e:
        raise ValueError('INVALID_XNYS_SESSION') from e


def session_dates(start, end):
    return tuple(x.date().isoformat() for x in calendar().sessions_in_range(start, end))


def resolve_request(instrument, as_of=None, session=None, known_by=None):
    if as_of is not None:
        if session is not None or known_by is not None:
            raise ValueError('CONFLICTING_TEMPORAL_MODES')
        if len(as_of) == 10:
            return Request(instrument, as_of, session_close(as_of))
        cutoff = timestamp(as_of)
        local = datetime.fromisoformat(cutoff).astimezone(ZoneInfo('America/New_York'))
        cal = calendar()
        day = cal.date_to_session(local.date().isoformat(), direction='previous')
        if cal.session_close(day).isoformat() > cutoff:
            day = cal.previous_session(day)
        return Request(instrument, day.date().isoformat(), cutoff)
    if session is None or known_by is None:
        raise ValueError('EXPLICIT_TEMPORAL_MODE_REQUIRED')
    session_close(session)
    return Request(instrument, session, timestamp(known_by))
