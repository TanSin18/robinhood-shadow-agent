"""Labels for a future tournament. Labels only: a future price is never a feature.

``forward-close-to-close-price-return-v3``. For a row at session T (features use bars up to and including T; the
decision time is the open of T+1), the label at horizon h is

    close[T+1+h] / close[T+1] - 1

on the exact close (``adjust.exact_close``): the unadjusted close and the recorded split ratios, a price return, the
same method for every security. The entry is the close of the first session after the decision time, so no label uses
a price at or before the last feature bar. Checkpoint 7's label began at the close the features ended at; this one
begins a session later.

Why the close and not the open of T+1. The vendor supplies the open only split-adjusted, reprinted after every later
split and rounded. For a stock that split heavily afterwards the reprinted opens are small, coarse numbers, and a label
built from them is quantised by something that had not happened yet (measured in review: a median error of 0.7% and up
to 4% at an adjusted price near 0.40 printed to two decimals). The unadjusted close is the price printed on the day and
no later split changes it, so this label is the same number whatever happened afterwards.

A label is not built, and the reason is recorded, when:

    NO_ENTRY_BAR                  there is no bar on T+1
    WINDOW_PAST_STORED_HISTORY    T+1+h lies after the last stored session of a security that is still listed
    NO_EXIT_BAR                   the security is still listed at T+1+h but has no bar there
    LABEL_WINDOW_HAS_BREAK        a spin-off, large distribution or split inconsistency lies inside the window

Delisting. When the security's last bar falls before T+1+h and a delisting or acquisition is recorded at that last bar,
the label uses the last close as the exit and is flagged. The master's present-day "delisted" flag is not used: a store
that simply ends, or a file that was cut short, is not a delisting, and bars that stop with no record yield no label
(``WINDOW_PAST_STORED_HISTORY``), which is counted. These rows are kept: they are the failures and the takeovers. For a bankruptcy or a
regulatory delisting the last price overstates what a holder recovered; that is a stated limitation, counted per reason.

The excess label subtracts the equal-weighted mean label of the universe members of session T. No fund is needed, and
it is formed from the same rows, so it carries no information from outside the sample.
"""
from __future__ import annotations

import numpy as np

from . import adjust

TARGET_VERSION = 'forward-close-to-close-price-return-v3'
HORIZONS = (5, 10, 20)
MAX_HORIZON = max(HORIZONS)
OK, NO_ENTRY, PAST_HISTORY, NO_EXIT, HAS_BREAK, DELISTED_EXIT = 0, 1, 2, 3, 4, 5
REASONS = {OK: 'OK', NO_ENTRY: 'NO_ENTRY_BAR', PAST_HISTORY: 'WINDOW_PAST_STORED_HISTORY', NO_EXIT: 'NO_EXIT_BAR', HAS_BREAK: 'LABEL_WINDOW_HAS_BREAK',
           DELISTED_EXIT: 'EXIT_AT_LAST_PRICE_BEFORE_DELISTING'}


DELISTING_WINDOW = 5                     # sessions before the last bar within which a delisting record explains the end of the bars


def delisted_at_last_bar(panel, actions, data_end=None):
    """The provider's code of the delisting (or acquisition) recorded at this security's last bar, or None. A record
    dated more than a few sessions before the last bar does not explain why the bars stop where they do. ``data_end``
    is the last session stored for any security: bars that stop there have not been shown to stop at all, and a record
    dated after it describes something the stored data cannot show, so neither makes an exit."""
    sessions = panel['sessions']
    if not sessions or (data_end is not None and sessions[-1] >= data_end):
        return None
    first_allowed = sessions[max(0, len(sessions) - 1 - DELISTING_WINDOW)]
    last_allowed = _after(sessions[-1]) if data_end is None else min(_after(sessions[-1]), data_end)
    found = [a for a in actions if a['type'] == 'delisting' or (a['type'] == 'merger' and a.get('provider_code') == 'acquisitionby')]
    near = [a for a in found if first_allowed <= str(a['effective_date'])[:10] <= last_allowed]
    if not near:
        return None
    codes = [a.get('provider_code') or a['type'] for a in sorted(near, key=lambda a: (a['type'] != 'delisting', str(a['effective_date'])))]
    return codes[0]


def _after(session, days=DELISTING_WINDOW) -> str:
    from . import calendar
    try:
        return calendar.offset(session, days)
    except ValueError:
        return session


def build(panel, break_mask, *, delisted, horizons=HORIZONS, splits=()) -> dict:
    """{h: {'value': array, 'state': array of codes, 'exit_index': array}} over the panel's sessions. ``splits`` are the
    applied split ratios from ``adjust.breaks``; prices are the exact close.

    ``delisted`` is true (or the provider's code, from ``delisted_at_last_bar``) when a delisting is recorded at the last
    bar, so the end of its bars is an end and not merely the end of the stored data. A label with state OK or DELISTED_EXIT has a value; every other state has NaN."""
    count = len(panel['sessions'])
    closes, present = adjust.exact_close(panel, splits), panel['present']
    seen = np.cumsum(break_mask) if break_mask is not None else np.zeros(count, int)
    last = count - 1                                                 # the panel ends at the security's last stored bar
    t = np.arange(count)
    out = {}
    for h in horizons:
        value = np.full(count, np.nan)
        state = np.full(count, PAST_HISTORY)
        exit_index = np.full(count, -1)
        entry = t + 1
        target = entry + h
        can_enter = (entry <= last)
        has_entry = np.zeros(count, bool)
        has_entry[can_enter] = present[entry[can_enter]]
        inside = target <= last
        full = has_entry & inside
        exit_present = np.zeros(count, bool)
        exit_present[inside] = present[target[inside]]
        normal = full & exit_present
        with np.errstate(invalid='ignore', divide='ignore'):
            value[normal] = closes[target[normal]] / closes[entry[normal]] - 1
        state[normal], exit_index[normal] = OK, target[normal]
        state[full & ~exit_present] = NO_EXIT
        ended = has_entry & ~inside & (entry < last)                   # entered on the last bar itself, nothing is left to hold
        state[has_entry & ~inside & (entry >= last)] = NO_EXIT if delisted else PAST_HISTORY
        if delisted:
            with np.errstate(invalid='ignore', divide='ignore'):
                value[ended] = closes[last] / closes[entry[ended]] - 1
            state[ended], exit_index[ended] = DELISTED_EXIT, last
        state[~has_entry & (can_enter | bool(delisted))] = NO_ENTRY
        if not delisted:
            state[~can_enter] = PAST_HISTORY
        # a break strictly after the entry session and at or before the exit makes the return meaningless
        labelled = (state == OK) | (state == DELISTED_EXIT)
        crossed = np.zeros(count, bool)
        crossed[labelled] = seen[exit_index[labelled]] - seen[entry[labelled]] > 0
        value[crossed], state[crossed] = np.nan, HAS_BREAK
        out[h] = {'value': value, 'state': state, 'exit_index': exit_index}
    return out
