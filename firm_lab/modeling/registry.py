"""The research model registry: what was fitted, on what, how it scored and what research status it has.

Append-only and content-addressed, in the modeling database. A model record names its dataset hash, split definition,
configuration, seeds, library versions and code hash, so it can be traced and refitted. There is no production or live
status, no promotion step and no artifact that the trading runtime reads.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from firm_lab.research_features.types import canonical, content_hash

from . import STATUSES, timeview

REQUIRED = ('model_id', 'name', 'family', 'architecture', 'target', 'horizons', 'feature_groups', 'feature_names', 'feature_versions',
            'training_window', 'validation_window', 'split', 'hyperparameters', 'seeds', 'library_versions', 'code_hash', 'dataset_hash',
            'metrics', 'artifact', 'status', 'status_reasons', 'role')
FORBIDDEN_STATUS_WORDS = ('PRODUCTION', 'LIVE', 'DEPLOYED', 'ACTIVE', 'CHAMPION_LIVE')


def code_hash() -> str:
    """One hash over every source file of the modeling package: the code a result was produced by."""
    digest = hashlib.sha256()
    for file in sorted(Path(__file__).parent.glob('*.py')):
        digest.update(file.name.encode())
        digest.update(b'\0' + file.read_bytes())
    return digest.hexdigest()


def clean(value):
    """JSON-safe copy: numpy scalars and arrays become plain numbers and lists; a non-finite number becomes None."""
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def validate(record) -> dict:
    missing = [k for k in REQUIRED if k not in record]
    if missing:
        raise ValueError('MODEL_RECORD_INCOMPLETE:' + ','.join(missing))
    if record['status'] not in STATUSES or any(word in str(record['status']).upper() for word in FORBIDDEN_STATUS_WORDS):
        raise ValueError('RESEARCH_STATUS_REQUIRED')
    for status in (record.get('status_by_target') or {}).values():
        if status not in STATUSES:
            raise ValueError('RESEARCH_STATUS_REQUIRED')
    if record['role'] not in ('BASELINE', 'CANDIDATE', 'DIAGNOSTIC'):
        raise ValueError('INVALID_ROLE')
    return clean(record)


def model_id(name, target, dataset_hash, hyperparameters, code, run=None) -> str:
    """Names one model of one run: what was fitted, on what, by which code, in which run. A rerun is a new run and gets new rows."""
    return content_hash([name, target, dataset_hash, hyperparameters, code, run])


REGISTRY_TABLES = ('modeling_models', 'modeling_predictions', 'modeling_runs', 'modeling_reports')


def protect(db):
    """INSERT OR REPLACE deletes the old row without firing a delete trigger. These triggers close that door: on a
    registry table a second insert under an existing identity is an error; on the dataset table it is ignored, which is
    what registering the same dataset twice already meant. Applied to the modeling database and to every exported file."""
    for table in REGISTRY_TABLES:
        db.execute(f'CREATE TRIGGER IF NOT EXISTS {table}_no_replace BEFORE INSERT ON {table} WHEN EXISTS (SELECT 1 FROM {table} WHERE id = NEW.id) '
                   "BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY'); END")
    db.execute('CREATE TRIGGER IF NOT EXISTS modeling_datasets_no_replace BEFORE INSERT ON modeling_datasets WHEN EXISTS (SELECT 1 FROM modeling_datasets WHERE id = NEW.id) '
               'BEGIN SELECT RAISE(IGNORE); END')


def read_only(path) -> tuple:
    """(newest report, every model row) read without writing a byte to the file."""
    timeview.check(path)
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        row = db.execute('SELECT payload FROM modeling_reports ORDER BY created_at DESC, id DESC LIMIT 1').fetchone()
        return (json.loads(row[0]) if row else None), [json.loads(p) for (p,) in db.execute('SELECT payload FROM modeling_models ORDER BY created_at, id')]
    finally:
        db.close()


class Registry:
    def __init__(self, path):
        timeview.check(path)
        self.db = sqlite3.connect(Path(path).resolve(), timeout=120)
        with self.db:
            timeview.create_tables(self.db)
            protect(self.db)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.db.close()

    def _insert(self, table, identity, payload) -> bool:
        """True if stored, False if the identical row is already there. The same identity with different content is an
        error: a stored research record is never silently kept in place of a different one."""
        body = canonical(payload)
        row = self.db.execute(f'SELECT payload FROM {table} WHERE id = ?', (identity,)).fetchone()
        if row is not None:
            if row[0] != body:
                raise ValueError('REGISTRY_ROW_CONFLICT:' + table)
            return False
        with self.db:
            self.db.execute(f'INSERT INTO {table} VALUES (?,?,?)', (identity, body, datetime.now(timezone.utc).isoformat()))
        return True

    def add_model(self, record) -> bool:
        record = validate(record)
        return self._insert('modeling_models', record['model_id'], record)

    def add_predictions(self, identity, rows, prediction, *, part, extra=None) -> str:
        """Stores a model's out-of-sample predictions (compressed), returns the artifact hash."""
        body = {'rows': np.asarray(rows).tolist(), 'prediction': clean(np.asarray(prediction)), 'part': part, **(extra or {})}
        blob = base64.b64encode(zlib.compress(canonical(body).encode(), 9)).decode()
        artifact = hashlib.sha256(blob.encode()).hexdigest()
        self._insert('modeling_predictions', content_hash([identity, part]), {'model_id': identity, 'part': part, 'artifact_sha256': artifact,
                                                                            'predictions_zlib_b64': blob})
        return artifact

    def add_run(self, identity, payload) -> bool:
        return self._insert('modeling_runs', identity, clean(payload))

    def add_report(self, identity, payload) -> bool:
        return self._insert('modeling_reports', identity, clean(payload))

    def models(self) -> list:
        return [json.loads(p) for (p,) in self.db.execute('SELECT payload FROM modeling_models ORDER BY created_at, id')]

    def latest_report(self):
        row = self.db.execute('SELECT payload FROM modeling_reports ORDER BY created_at DESC, id DESC LIMIT 1').fetchone()
        return json.loads(row[0]) if row else None
