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
    if record['role'] not in ('BASELINE', 'CANDIDATE', 'DIAGNOSTIC'):
        raise ValueError('INVALID_ROLE')
    return clean(record)


def model_id(name, target, dataset_hash, hyperparameters, code) -> str:
    return content_hash([name, target, dataset_hash, hyperparameters, code])


class Registry:
    def __init__(self, path):
        timeview.check(path)
        self.db = sqlite3.connect(Path(path).resolve(), timeout=120)
        with self.db:
            timeview.create_tables(self.db)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.db.close()

    def _insert(self, table, identity, payload) -> bool:
        with self.db:
            return self.db.execute(f'INSERT OR IGNORE INTO {table} VALUES (?,?,?)',
                                   (identity, canonical(payload), datetime.now(timezone.utc).isoformat())).rowcount > 0

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
