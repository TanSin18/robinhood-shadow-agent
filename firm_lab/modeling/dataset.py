"""The modeling dataset contract. Features and labels are built apart and joined only by (instrument, session).

Features come from the stored session-time snapshots (``history``): each is what the unchanged Checkpoint 6 calculators
said was known at the close of its session. Labels come from ``targets``. The feature builder is never given a label or
a close after the session it describes; a test changes the future and proves the features do not move.

Every sample keeps: instrument, feature session, feature knowledge cutoff, calculation hash, the identity of its stored
feature snapshot, the target horizon, start and end sessions, the target and benchmark values, and the target and
encoding versions. The whole dataset has one hash over all of that, so a model can name exactly what it was fitted on.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from firm_lab.research_features.calendar import session_close
from firm_lab.research_features.registry import definitions
from firm_lab.research_features.types import canonical, content_hash

from . import BENCHMARK, TIME_POLICY, history, targets, timeview

ENCODING_VERSION = 'numeric-encoding-v1'
DATASET_VERSION = 'modeling-dataset-v1'
# Units that mean the same thing for every instrument and every date. A dollar price level does not, so it is left out.
MODEL_UNITS = ('fraction', 'ratio', 'count', 'sessions', 'days', 'percentile', 'annualized_fraction', 'percent', 'basis_points',
               'percent_change_mom_sa', 'index_0_100', 'rank', 'rank_change', 'boolean', 'interaction')
EXCLUDED_UNITS = {'price': 'a dollar level: not comparable across instruments or dates', 'ATR': 'needs validated OHLCV, which does not exist',
                  'shares': 'needs validated volume, which does not exist'}
# Feature groups for the ablation, in the order they are added.
GROUPS = (('technical_baseline', ('trend', 'momentum', 'volatility')), ('fibonacci', ('fibonacci',)),
          ('structure', ('support_resistance', 'breakout_structure')), ('fundamentals', ('fundamentals',)), ('earnings', ('earnings_events',)),
          ('sector', ('sector',)), ('macro', ('macro_context',)))
MINIMUM_HISTORY = 63            # sessions of closes before a session is used as a sample (the 63-session descriptors exist from here)


@dataclass
class Dataset:
    sessions: list                      # every stored exchange session, in order
    instruments: list                   # every instrument except the benchmark, in order
    feature_names: list
    feature_family: dict
    X: np.ndarray                       # [row, feature]; nan = unavailable at that session's close
    row_instrument: np.ndarray          # index into instruments
    row_session: np.ndarray             # index into sessions
    y: dict                             # target name -> [row]; nan = no label (window runs past the stored history)
    snapshot_ids: list                  # the stored feature snapshot behind each row
    label_records: list                 # the label audit record behind each row
    excluded: dict                      # feature name -> why it is not a model input
    manifest: dict = field(default_factory=dict)

    def rows(self, session_indices) -> np.ndarray:
        return np.flatnonzero(np.isin(self.row_session, np.asarray(list(session_indices))))

    def columns(self, groups) -> list:
        families = {f for name, members in GROUPS if name in groups for f in members}
        return [i for i, name in enumerate(self.feature_names) if self.feature_family[name] in families]

    def row_of(self) -> dict:
        return {(int(i), int(s)): r for r, (i, s) in enumerate(zip(self.row_instrument, self.row_session))}


def _encoding() -> tuple:
    """(model features in a fixed order with their family, features left out with the reason). From the registered definitions."""
    kept, family, excluded = [], {}, {}
    for d in sorted(definitions(), key=lambda d: (d['family'], d['name'])):
        if d['value_type'] == 'object':
            excluded[d['name']] = 'a structured description, not a number'
        elif d['unit'] in EXCLUDED_UNITS:
            excluded[d['name']] = EXCLUDED_UNITS[d['unit']]
        elif d['unit'] not in MODEL_UNITS:
            excluded[d['name']] = f'unit {d["unit"]!r} has no encoding rule'
        else:
            kept.append(d['name'])
            family[d['name']] = d['family']
    return kept, family, excluded


def _number(value):
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    return float(value)


def build_features(path) -> dict:
    """{(instrument, session): (snapshot id, {feature name: number})} from the stored snapshots. Reads no close and no label.
    Refuses a snapshot whose cutoff is not its own session close, or which holds anything known after that close."""
    timeview.check(path)
    kept, _, _ = _encoding()
    wanted = set(kept)
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    out = {}
    try:
        for identity, payload in db.execute('SELECT id, payload FROM modeling_feature_results ORDER BY id'):
            body = json.loads(payload)
            cutoff = session_close(body['session'])
            if body['knowledge_cutoff'] != cutoff or body['time_policy'] != TIME_POLICY:
                raise ValueError('SNAPSHOT_IS_NOT_A_SESSION_CLOSE_VIEW')
            if body['latest_input_known_at'] and body['latest_input_known_at'] > cutoff:
                raise ValueError('SNAPSHOT_INPUT_KNOWN_AFTER_SESSION_CLOSE')
            values = {}
            for r in history.read_results(body):
                if r['availability'] != 'AVAILABLE':
                    continue
                if r['known_at'] > cutoff:
                    raise ValueError('FEATURE_KNOWN_AFTER_SESSION_CLOSE')
                if r['name'] in wanted:
                    values[r['name']] = _number(r['value'])
            key = (body['instrument'], body['session'])
            if key in out:
                raise ValueError('DUPLICATE_SNAPSHOT')
            out[key] = (identity, values, body['calculation_hash'], body['results_digest'])
    finally:
        db.close()
    return out


def _array_hash(array) -> str:
    clean = np.where(np.isnan(array), np.float64('nan'), array).astype('<f8')          # one bit pattern for "unavailable"
    view = clean.copy()
    view[np.isnan(view)] = -9.87654321e300
    return hashlib.sha256(view.tobytes()).hexdigest()


def build(path, *, benchmark=BENCHMARK) -> Dataset:
    kept, family, excluded = _encoding()
    features = build_features(path)                                  # built first, from snapshots only
    sessions, closes = targets.load_closes(path)                     # labels are built afterwards, from closes only
    labels = targets.build(sessions, closes, benchmark=benchmark)
    instruments = sorted(i for i in closes if i != benchmark)
    position = {s: k for k, s in enumerate(sessions)}
    rows = [(i, s) for s in sessions for i in instruments if (i, s) in features]
    missing = [(i, s) for s in sessions[MINIMUM_HISTORY:] for i in instruments if (i, s) not in features]
    if missing:
        raise ValueError(f'FEATURE_SNAPSHOT_MISSING:{missing[0][0]}:{missing[0][1]} (+{len(missing) - 1} more)')
    X = np.full((len(rows), len(kept)), np.nan)
    column = {name: k for k, name in enumerate(kept)}
    snapshot_ids, records, calculation = [], [], set()
    for r, key in enumerate(rows):
        identity, values, digest, _ = features[key]
        calculation.add(digest)
        snapshot_ids.append(identity)
        records.append(labels[key])
        for name, value in values.items():
            X[r, column[name]] = value
    if len(calculation) != 1:
        raise ValueError('MIXED_CALCULATION_VERSIONS')
    y = {name: np.array([np.nan if rec[name] is None else float(rec[name]) for rec in records]) for name in targets.ALL}
    data = Dataset(sessions=sessions, instruments=instruments, feature_names=kept, feature_family=family, X=X,
                   row_instrument=np.array([instruments.index(i) for i, _ in rows]), row_session=np.array([position[s] for _, s in rows]),
                   y=y, snapshot_ids=snapshot_ids, label_records=records, excluded=excluded)
    policy = timeview.check(path)
    usable = np.flatnonzero((data.row_session >= MINIMUM_HISTORY) & np.isfinite(y[f'excess_return_{targets.MAX_HORIZON}']))
    availability = {name: float(np.mean(np.isfinite(X[usable, k]))) if len(usable) else 0.0 for name, k in column.items()}
    parts = {'features': _array_hash(X), 'labels': content_hash({name: _array_hash(values) for name, values in y.items()}),
             'snapshots': content_hash(snapshot_ids), 'rows': content_hash([list(r) for r in rows])}
    manifest = {'dataset_version': DATASET_VERSION, 'encoding_version': ENCODING_VERSION, 'target_version': targets.TARGET_VERSION,
                'time_policy': TIME_POLICY, 'calculation_hash': calculation.pop(), 'source_sha256': policy['source_sha256'], 'benchmark': benchmark,
                'instruments': instruments, 'first_session': sessions[0], 'last_session': sessions[-1], 'sessions': len(sessions),
                'rows': len(rows), 'minimum_history_sessions': MINIMUM_HISTORY, 'usable_samples_all_horizons': int(len(usable)),
                'usable_sessions_all_horizons': int(len(np.unique(data.row_session[usable]))), 'targets': list(targets.ALL),
                'horizons': list(targets.HORIZONS), 'features': kept, 'feature_family': family, 'feature_availability': availability,
                'excluded_features': excluded, 'hashes': parts}
    manifest['dataset_hash'] = content_hash({k: manifest[k] for k in ('dataset_version', 'encoding_version', 'target_version', 'time_policy',
                                                                      'calculation_hash', 'source_sha256', 'benchmark', 'features', 'hashes')})
    data.manifest = manifest
    return data


def sample_records(data: Dataset) -> list:
    """One audit record per row: what the sample is, which stored snapshot its features came from and how its labels were built."""
    out = []
    for r, record in enumerate(data.label_records):
        session = data.sessions[data.row_session[r]]
        out.append({'instrument': record['instrument'], 'feature_session': session, 'feature_knowledge_cutoff': session_close(session),
                    'calculation_hash': data.manifest['calculation_hash'], 'feature_snapshot_id': data.snapshot_ids[r],
                    'target_version': record['target_version'], 'benchmark': record['benchmark'], 'target_start_session': record['target_start_session'],
                    'targets': {name: record[name] for name in targets.ALL},
                    'horizons': {str(h): {'target_end_session': record[f'target_end_session_{h}'], 'instrument_return': record[f'instrument_return_{h}'],
                                          'benchmark_return': record[f'benchmark_return_{h}']} for h in targets.HORIZONS},
                    'dataset_hash': data.manifest['dataset_hash']})
    return out


def register(path, data: Dataset) -> bool:
    """Stores the manifest and the per-sample audit records in the modeling database. Content-addressed and append-only:
    the same dataset registers once; a different dataset gets a different identity."""
    db = sqlite3.connect(Path(path).resolve(), timeout=120)
    at = datetime.now(timezone.utc).isoformat()
    try:
        timeview.create_tables(db)
        samples = base64.b64encode(zlib.compress(canonical(sample_records(data)).encode(), 9)).decode()
        with db:
            added = db.execute('INSERT OR IGNORE INTO modeling_datasets VALUES (?,?,?)', (data.manifest['dataset_hash'], canonical(data.manifest), at)).rowcount
            db.execute('INSERT OR IGNORE INTO modeling_datasets VALUES (?,?,?)',
                       (data.manifest['dataset_hash'] + ':samples', canonical({'dataset_hash': data.manifest['dataset_hash'], 'samples_zlib_b64': samples}), at))
        return bool(added)
    finally:
        db.close()


def sequences(data: Dataset, rows, columns, length) -> tuple:
    """([sample, step, feature] windows ending at each row's own session, mask of rows that have a full window).
    Every step is the instrument's own row for an earlier session, so nothing in a window is later than the sample."""
    index = data.row_of()
    columns = list(columns)
    out = np.full((len(rows), length, len(columns)), np.nan)
    full = np.zeros(len(rows), dtype=bool)
    for n, r in enumerate(rows):
        instrument, session = int(data.row_instrument[r]), int(data.row_session[r])
        steps = [index.get((instrument, session - back)) for back in range(length - 1, -1, -1)]
        if all(s is not None for s in steps):
            out[n] = data.X[np.asarray(steps)][:, columns]
            full[n] = True
    return out, full
