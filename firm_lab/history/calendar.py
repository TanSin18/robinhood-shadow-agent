"""Exchange sessions for the whole historical period, and the availability bound of a daily bar.

``bar-known-at-v1``: a bar cannot be known before its session closes, and it is treated as available no later than the
open of the next exchange session. That is a bound, not a measured publication time; none is invented.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from functools import lru_cache

import exchange_calendars

FIRST = '1990-01-01'


@lru_cache(maxsize=1)
def calendar():
    return exchange_calendars.get_calendar('XNYS', start=FIRST)


@lru_cache(maxsize=1)
def _sessions() -> tuple:
    return tuple(s.date().isoformat() for s in calendar().sessions)


@lru_cache(maxsize=1)
def _index() -> dict:
    return {s: k for k, s in enumerate(_sessions())}


def is_session(day) -> bool:
    return day in _index()


def sessions(start, end) -> tuple:
    """Every exchange session from ``start`` to ``end`` inclusive."""
    every = _sessions()
    return every[bisect_left(every, start[:10]):bisect_right(every, end[:10])]


def position(session) -> int:
    try:
        return _index()[session]
    except KeyError:
        raise ValueError('NOT_AN_EXCHANGE_SESSION') from None


def offset(session, by) -> str:
    """The session ``by`` sessions after (or before) ``session``."""
    k = position(session) + by
    every = _sessions()
    if not 0 <= k < len(every):
        raise ValueError('OUTSIDE_THE_CALENDAR')
    return every[k]


def session_close(session) -> str:
    position(session)
    return calendar().session_close(session).isoformat()


def eligible_from(session) -> str:
    """When a bar of ``session`` may first be used: the open of the next exchange session."""
    return calendar().session_open(offset(session, 1)).isoformat()


def month_ends(start, end) -> tuple:
    """The last exchange session of every calendar month, for months whose last session lies inside [start, end]."""
    every = _sessions()
    out = []
    for s in sessions(start, end):
        k = position(s) + 1
        if k < len(every) and every[k][:7] != s[:7]:
            out.append(s)
    return tuple(out)
