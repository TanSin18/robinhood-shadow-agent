"""Target specification. Labels only: a future return is never a feature.

Primary target: the 10-session forward excess price return against VTI,

    (C_i[T+10] / C_i[T] - 1) - (C_VTI[T+10] / C_VTI[T] - 1)

on aligned exchange sessions, both legs from the same stored, split-adjusted, price-return closes.

Stated limitation. Both legs are price returns, not total returns: a cash distribution paid by the instrument or by VTI
inside the window is not added back, so an instrument that goes ex-dividend in the window shows a lower excess return
than a holder received. The validated total-return series in Firm Lab covers VTI only and is benchmark-only, so mixing it
with a price return on the other leg would be inconsistent; it is not used here.

Second limitation. The label starts at the same close the features end at. That is a research label, not an executable
entry: a version that could be traded would start no earlier than the next session.

Risk targets are close-based only. An excursion is measured on closes, never on highs or lows, because no validated
high/low data exists.
"""
from __future__ import annotations

import math
import sqlite3
from decimal import Decimal
from pathlib import Path

from firm_lab.research_features.calendar import session_close, session_dates

from . import BENCHMARK

TARGET_VERSION = 'forward-excess-price-return-v1'
HORIZONS = (5, 10, 20)
PRIMARY = 'excess_return_10'
RISK_HORIZON = 10
REGRESSION = tuple(f'excess_return_{h}' for h in HORIZONS)
CLASSIFICATION = 'positive_excess_10'
RISK = ('close_mae_10', 'close_mfe_10', 'future_realized_vol_10')
ALL = REGRESSION + (CLASSIFICATION,) + RISK
MAX_HORIZON = max(HORIZONS + (RISK_HORIZON,))


def load_closes(path) -> tuple:
    """(sessions, {instrument: [close as float, one per session]}) from the modeling database. Refuses a calendar gap, a
    missing close or a non-positive price rather than aligning around it."""
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        rows = db.execute("SELECT instrument, exchange_session_date, value, known_at, revision FROM feature_observations WHERE feature_name='close' "
                          'ORDER BY instrument, exchange_session_date, known_at, revision').fetchall()
    finally:
        db.close()
    by = {}
    for instrument, session, value, _, _ in rows:
        by.setdefault(instrument, {})[session] = value            # the latest revision of a session wins, as in the feature loader
    sessions = sorted({s for v in by.values() for s in v})
    if not sessions or tuple(sessions) != session_dates(sessions[0], sessions[-1]):
        raise ValueError('CLOSE_HISTORY_IS_NOT_A_CONTIGUOUS_SESSION_WINDOW')
    out = {}
    for instrument, values in by.items():
        if sorted(values) != sessions:
            raise ValueError(f'INCOMPLETE_CLOSE_HISTORY:{instrument}')
        series = [Decimal(values[s]) for s in sessions]
        if any(not v.is_finite() or v <= 0 for v in series):
            raise ValueError(f'INVALID_CLOSE:{instrument}')
        out[instrument] = [float(v) for v in series]
    if BENCHMARK not in out:
        raise ValueError('BENCHMARK_CLOSES_MISSING')
    return sessions, out


def build(sessions, closes, *, benchmark=BENCHMARK) -> dict:
    """{(instrument, session): label record} for every non-benchmark instrument and every session. A target whose window
    runs past the last stored session is None. Each record says which sessions and closes it was built from."""
    bench = closes[benchmark]
    count = len(sessions)
    out = {}
    for instrument, series in closes.items():
        if instrument == benchmark:
            continue
        for t, session in enumerate(sessions):
            record = {'instrument': instrument, 'session': session, 'target_version': TARGET_VERSION, 'benchmark': benchmark,
                      'target_start_session': session, 'label_start_known_at': session_close(session)}
            for h in HORIZONS:
                name = f'excess_return_{h}'
                if t + h < count:
                    own, market = series[t + h] / series[t] - 1, bench[t + h] / bench[t] - 1
                    record[name] = own - market
                    record[f'instrument_return_{h}'], record[f'benchmark_return_{h}'] = own, market
                    record[f'target_end_session_{h}'] = sessions[t + h]
                else:
                    record[name] = record[f'instrument_return_{h}'] = record[f'benchmark_return_{h}'] = record[f'target_end_session_{h}'] = None
            ten = record['excess_return_10']
            record[CLASSIFICATION] = None if ten is None else int(ten > 0)
            if t + RISK_HORIZON < count:
                path = [series[t + k] / series[t] - 1 for k in range(1, RISK_HORIZON + 1)]
                logs = [math.log(series[t + k] / series[t + k - 1]) for k in range(1, RISK_HORIZON + 1)]
                mean = sum(logs) / len(logs)
                record['close_mae_10'], record['close_mfe_10'] = min(path), max(path)
                record['future_realized_vol_10'] = math.sqrt(sum((x - mean) ** 2 for x in logs) / (len(logs) - 1)) * math.sqrt(252)
            else:
                record['close_mae_10'] = record['close_mfe_10'] = record['future_realized_vol_10'] = None
            out[(instrument, session)] = record
    return out
