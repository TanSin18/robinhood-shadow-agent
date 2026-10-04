"""Read-only projection of the modeling laboratory for the dashboard. Standard library only.

Reads the newest stored report from the small laboratory file that sits beside the research database. It fits nothing,
computes nothing, writes nothing and imports no model code. If the file is not there, or is not a modeling database, the
page says that no laboratory run is stored.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

WARNING = 'MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE'
FILE_NAME = 'firm_lab_modeling_lab.db'
ROLE = 'CHECKPOINT7_MODELING_RESEARCH'
ALLOWED_STATUSES = ('EXPERIMENTAL', 'CHALLENGER', 'REJECTED', 'ELIGIBLE_FOR_FUTURE_REVIEW')
EXECUTION_WORDS = ('order', 'fill', 'position', 'account', 'cash', 'portfolio', 'broker')


def empty(reason='NO_STORED_LABORATORY_RUN') -> dict:
    return {'exists': False, 'warning': WARNING, 'missing_reason': reason, 'report': None, 'models': 0}


def summary(research_database) -> dict:
    """{'exists', 'warning', 'report', 'models', 'file'} for the laboratory file beside ``research_database``."""
    path = Path(research_database).with_name(FILE_NAME)
    if not path.is_file():
        return empty()
    try:
        db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=0.5)
    except sqlite3.Error:
        return empty('LABORATORY_FILE_UNREADABLE')
    try:
        db.execute('PRAGMA query_only=ON')
        names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if any(word in name for name in names for word in EXECUTION_WORDS) or 'firm_meta' not in names:
            return empty('NOT_A_MODELING_DATABASE')
        meta = dict(db.execute('SELECT key, value FROM firm_meta'))
        if meta.get('mode') != 'BUILD_OBSERVE' or meta.get('database_role') != ROLE or 'modeling_reports' not in names:
            return empty('NOT_A_MODELING_DATABASE')
        row = db.execute('SELECT payload, created_at FROM modeling_reports ORDER BY created_at DESC, id DESC LIMIT 1').fetchone()
        if not row:
            return empty()
        report = json.loads(row[0])
        statuses = {}
        for (payload,) in db.execute('SELECT payload FROM modeling_models'):
            status = json.loads(payload).get('status')
            if status not in ALLOWED_STATUSES:
                return empty('UNEXPECTED_MODEL_STATUS')            # never show a model with a status this laboratory cannot give
            statuses[status] = statuses.get(status, 0) + 1
        return {'exists': True, 'warning': WARNING, 'report': report, 'models': sum(statuses.values()), 'registry_statuses': statuses,
                'stored_at': row[1], 'file': '/'.join(path.parts[-3:])}
    except (sqlite3.Error, ValueError, KeyError, TypeError) as error:
        return empty('LABORATORY_FILE_UNREADABLE:' + type(error).__name__)
    finally:
        db.close()
