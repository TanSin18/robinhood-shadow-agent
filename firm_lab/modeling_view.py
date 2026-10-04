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
# the parts of a report the page cannot do without, and the shape each must have
REQUIRED_PARTS = (('report_id', str), ('plan_version', str), ('time_policy', str), ('code_hash', str), ('dataset', dict), ('validation', dict), ('tables', dict),
                  ('ablation', dict), ('best_research_models', dict))


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
        if not isinstance(report, dict) or any(not isinstance(report.get(key), kind) for key, kind in REQUIRED_PARTS):
            return empty('LABORATORY_REPORT_INCOMPLETE')
        for rows in report['tables'].values():
            for r in rows if isinstance(rows, list) else [None]:
                if not isinstance(r, dict) or r.get('status') not in ALLOWED_STATUSES + (None,):
                    return empty('UNEXPECTED_MODEL_STATUS')        # a status inside the report is checked like a registry row
        statuses, others = {}, 0
        for (payload,) in db.execute('SELECT payload FROM modeling_models'):
            record = json.loads(payload)
            if not isinstance(record, dict) or record.get('status') not in ALLOWED_STATUSES:
                return empty('UNEXPECTED_MODEL_STATUS')            # never show a model with a status this laboratory cannot give
            if record.get('report_id') != report.get('report_id'):
                others += 1                                        # a model of another run, or of none: kept in the file, not counted with this report
                continue
            statuses[record['status']] = statuses.get(record['status'], 0) + 1
        return {'exists': True, 'warning': WARNING, 'report': report, 'models': sum(statuses.values()), 'registry_statuses': statuses, 'models_from_other_runs': others,
                'stored_at': row[1], 'file': '/'.join(path.parts[-3:])}
    except (sqlite3.Error, ValueError, KeyError, TypeError, AttributeError, ArithmeticError, RecursionError) as error:
        return empty('LABORATORY_FILE_UNREADABLE:' + type(error).__name__)
    finally:
        db.close()
