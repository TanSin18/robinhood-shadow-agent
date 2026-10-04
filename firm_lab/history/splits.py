"""The chronology reserved for a future tournament. Dates only: no model, no metric, no label is read here.

``c9-chronology-v1`` (reserved 2026-10-04, before any Checkpoint 8 market data existed):

    DEVELOPMENT           1999-01-04 .. 26 sessions before the holdout   training and purged walk-forward validation
    PURGE                 the 26 sessions before the holdout             no samples: label windows and an embargo
    HISTORICAL_HOLDOUT    2021-01-04 .. 2025-03-28                       sealed; read once, by a registered Checkpoint 9 plan
    BURNED_CHECKPOINT7    2025-03-31 .. 2026-09-02                       Checkpoint 7's window; never a pristine test set
    PURGE                 2026-09-03 .. 2026-10-02                       no samples: a label from here would end inside the forward holdout
    FORWARD_HOLDOUT       2026-10-05 onward                              sealed; data that did not exist when this was written

The Checkpoint 7 holdout lies inside the burned window and is not reused. At every boundary the sessions whose longest
label would end in the next segment are purged: the historical holdout never touches the burned window, and no label
that can be read is built from a price of a sealed segment. Label values are readable in DEVELOPMENT and in
BURNED_CHECKPOINT7 only.

Checkpoint 8 has no way to unseal a holdout: ``labels_allowed`` refuses both, and no code path here records an unseal.
"""
from __future__ import annotations

from functools import lru_cache

from . import calendar
from .targets import MAX_HORIZON

SPLIT_VERSION = 'c9-chronology-v1'
EMBARGO = 5
PURGE = MAX_HORIZON + 1 + EMBARGO                      # the label of T ends at the close of T+1+h; then the embargo
FIRST_SAMPLE = '1999-01-04'
HOLDOUT_FIRST, HOLDOUT_LAST = '2021-01-04', '2025-03-28'
BURNED_FIRST, BURNED_LAST = '2025-03-31', '2026-10-02'
FORWARD_FIRST = '2026-10-05'
BURN_IN, DEVELOPMENT, PURGED, HISTORICAL_HOLDOUT, BURNED, FORWARD_HOLDOUT = ('BURN_IN', 'DEVELOPMENT', 'PURGE', 'HISTORICAL_HOLDOUT', 'BURNED_CHECKPOINT7',
                                                                             'FORWARD_HOLDOUT')
SEALED = (HISTORICAL_HOLDOUT, FORWARD_HOLDOUT)
MINIMUM_FOLDS, MINIMUM_FOLD_SESSIONS = 5, 252


@lru_cache(maxsize=1)
def development_last() -> str:
    return calendar.offset(HOLDOUT_FIRST, -PURGE - 1)


@lru_cache(maxsize=1)
def holdout_last_sample() -> str:
    """The last holdout session whose longest label still ends inside the holdout."""
    return calendar.offset(HOLDOUT_LAST, -(MAX_HORIZON + 1))


@lru_cache(maxsize=1)
def burned_last_sample() -> str:
    """The last burned session whose longest label still ends before the forward holdout begins."""
    return calendar.offset(BURNED_LAST, -(MAX_HORIZON + 1))


def segment(session) -> str:
    calendar.position(session)                                          # only an exchange session has a segment
    return _segment(session)


@lru_cache(maxsize=None)
def _segment(session) -> str:
    if session < FIRST_SAMPLE:
        return BURN_IN
    if session <= development_last():
        return DEVELOPMENT
    if session < HOLDOUT_FIRST:
        return PURGED
    if session <= HOLDOUT_LAST:
        return HISTORICAL_HOLDOUT if session <= holdout_last_sample() else PURGED
    if session < FORWARD_FIRST:
        return BURNED if session <= burned_last_sample() else PURGED
    return FORWARD_HOLDOUT


SAMPLE_SEGMENTS = (DEVELOPMENT, HISTORICAL_HOLDOUT, BURNED, FORWARD_HOLDOUT)       # burn-in and purge sessions yield no sample


def labels_allowed(name) -> bool:
    """Whether label values of this segment may be read in Checkpoint 8. A sealed segment never; a purge or burn-in
    session never either, because its label would reach into the segment after it."""
    return name in (DEVELOPMENT, BURNED)


def reservation() -> dict:
    """The record stored (append-only) and published in ``CHECKPOINT8_HOLDOUT_DESIGN.md``."""
    return {'kind': 'holdout_reservation', 'split_version': SPLIT_VERSION, 'reserved_on': '2026-10-04',
            'segments': {DEVELOPMENT: [FIRST_SAMPLE, development_last()], PURGED: [calendar.offset(development_last(), 1), calendar.offset(HOLDOUT_FIRST, -1)],
                         HISTORICAL_HOLDOUT: [HOLDOUT_FIRST, HOLDOUT_LAST], BURNED: [BURNED_FIRST, BURNED_LAST], FORWARD_HOLDOUT: [FORWARD_FIRST, None]},
            'last_burned_sample_session': burned_last_sample(), 'label_values_readable_in': [DEVELOPMENT, BURNED],
            'purge_sessions': PURGE, 'embargo_sessions': EMBARGO, 'max_horizon_sessions': MAX_HORIZON, 'last_holdout_sample_session': holdout_last_sample(),
            'sealed': list(SEALED), 'checkpoint7_holdout_reused_as_pristine': False,
            'walk_forward': {'minimum_folds': MINIMUM_FOLDS, 'minimum_validation_sessions_per_fold': MINIMUM_FOLD_SESSIONS, 'method': 'expanding, purged, chronological'},
            'rules': ['No model metric of any kind is computed on a sealed segment in Checkpoint 8.',
                      'Breadth (effective independent instruments) is measured on DEVELOPMENT only.',
                      'HISTORICAL_HOLDOUT is read once, by a registered Checkpoint 9 plan, after every model and every choice is frozen.',
                      'FORWARD_HOLDOUT is read once, not before its smallest detectable rank correlation is at most 0.05 at the horizon being confirmed.',
                      'BURNED_CHECKPOINT7 is never a test set. It may be used as training data only for a model that is then tested on FORWARD_HOLDOUT.',
                      'A second read of a sealed segment makes it burned, and that is recorded.']}
