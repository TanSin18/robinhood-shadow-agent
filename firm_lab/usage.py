"""What a stored record may be used for. Storing a record does not make it usable for everything.

Benchmark use. A historical cash distribution may be used to rebuild an after-the-fact benchmark total-return series:
the benchmark is a ruler looked at afterwards, and each of its observations carries the time it could first have been
computed.

Predictive-feature use. A distribution amount is NOT information that was known on its ex-date unless Firm Lab holds a
validated publication or announcement time proving it was known then. A row without one is BENCHMARK ONLY: it never
enters the feature store and is never handed to anything that builds a feature, whatever its ex-date and however long
ago it was. (Operator rule, 2026-10-03.)

This module is the single gate:
  * ``is_benchmark_only(row)``: the rule, from the row itself;
  * ``distribution_rows(store, instrument, purpose=..., as_of=...)``: the only reader of stored distributions;
  * ``require_feature_source_allowed(...)``: called by every feature-store write.
"""
from __future__ import annotations

from datetime import datetime

from .errors import FirmLabError

BENCHMARK, FEATURE = 'benchmark', 'feature'
PURPOSES = (BENCHMARK, FEATURE)
BENCHMARK_ONLY = 'BENCHMARK_ONLY'
UNAVAILABLE = 'UNAVAILABLE'
RESTRICTION = ('BENCHMARK_ONLY: no validated publication or announcement time is stored, so this is not information known on its '
               'effective date. For after-the-fact benchmark reconstruction only; never a model feature.')
REFUSED = 'BENCHMARK_ONLY_DATA_NOT_ALLOWED_IN_FEATURES'
# Names that identify benchmark-only material when something tries to write it into the feature store.
BENCHMARK_ONLY_TABLES = ('corporate_action_observations', 'benchmark_observations')
BENCHMARK_ONLY_KINDS = ('vti_total_return_index', 'vti_price_return_index', 'index_70_30_vti_total_return', 'index_70_30_vti_price_return_basis',
                        'tbill_13w_accrual_index')
_MARKERS = tuple(x.lower() for x in BENCHMARK_ONLY_TABLES + BENCHMARK_ONLY_KINDS + ('benchmark_only', 'benchmark-only', 'total_return', 'distribution',
                                                                                    'dividend'))


def _timestamp(text):
    try:
        stamp = datetime.fromisoformat(str(text).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return stamp if stamp.tzinfo is not None else None


def is_benchmark_only(row) -> bool:
    """True unless the row carries a real, timezone-aware announcement time and is not marked benchmark-only.
    A date alone, UNAVAILABLE, or nothing at all is not a validated time."""
    if str(row.get('benchmark_only') or '').lower() == 'true':
        return True
    return _timestamp(row.get('announcement_timestamp')) is None


def distribution_rows(store, instrument, *, purpose, as_of) -> list:
    """Stored cash distributions of the instrument, oldest stored first.

    purpose=BENCHMARK: every row Firm Lab held at ``as_of`` (its ``known_at``), for after-the-fact reconstruction.
    purpose=FEATURE:   only rows with a validated announcement time at or before ``as_of`` that are not marked
                       benchmark-only. Today that is no row at all.
    Any other purpose is refused: a caller must say what the data is for."""
    if purpose not in PURPOSES:
        raise FirmLabError(f'PURPOSE_REQUIRED: say whether the distributions are for {BENCHMARK} or {FEATURE} use')
    moment = as_of if isinstance(as_of, datetime) else _timestamp(as_of)
    if moment is None or moment.tzinfo is None:
        raise FirmLabError('AS_OF_REQUIRED: a timezone-aware time is needed')
    with store.connect() as db:
        columns = [r[1] for r in db.execute('PRAGMA table_info(corporate_action_observations)')]
        rows = [dict(zip(columns, r)) for r in db.execute("SELECT * FROM corporate_action_observations WHERE instrument=? AND action_type='cash_dividend' "
                                                          'ORDER BY id', (instrument,))]
    out = []
    for row in rows:
        known = _timestamp(row.get('known_at'))
        if known is None or known > moment:
            continue                                        # not held by Firm Lab at that time
        if purpose == FEATURE:
            announced = _timestamp(row.get('announcement_timestamp'))
            if is_benchmark_only(row) or announced is None or announced > moment:
                continue
        out.append(row)
    return out


def require_feature_source_allowed(*, source=None, provider=None, metadata=None, feature_name=None) -> None:
    """Refuses a feature-store write that names benchmark-only material as where it came from."""
    meta = metadata if isinstance(metadata, dict) else {}
    if meta.get('benchmark_only') in (True, 'true', 'True'):
        raise FirmLabError(f'{REFUSED}: the observation is marked benchmark-only')
    said = ' '.join(str(x) for x in (source, provider, feature_name, meta.get('computed_from'), meta.get('derived_from'), meta.get('source_table'),
                                     meta.get('inputs')) if x).lower()
    for marker in _MARKERS:
        if marker in said:
            raise FirmLabError(f'{REFUSED}: {marker!r} is benchmark-only material ({source or provider or feature_name})')
