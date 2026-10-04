"""Read-only projection of the Historical Data Readiness report for the dashboard. Standard library only.

Reads the small summary file that sits beside the research database. That file holds counts, dates, versions and hashes
and no price. This module opens no licensed database, computes nothing, writes nothing and imports no research code. If
the file is missing, damaged or not a readiness report, the page says that no readiness report is stored.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

WARNING = 'DATA READINESS ONLY — NO TRADING MODEL IS ACTIVE'
FILE_NAME = 'firm_lab_history_readiness.json'
KIND = 'historical_data_readiness'
VERDICTS = ('SUFFICIENT', 'BORDERLINE', 'INSUFFICIENT')
BAR_STATES = ('MET', 'NOT_MET', 'NOT_MEASURABLE')
MAXIMUM_BYTES = 4_000_000
REQUIRED_PARTS = (('report_hash', str), ('report_version', str), ('spec_version', str), ('market_data', dict), ('strict_training', dict), ('holdout', dict),
                  ('sufficiency', dict), ('specification_bars', list), ('provenance', list), ('provider_decision', dict), ('gaps', list), ('feature_versions', dict))


def empty(reason='NO_STORED_READINESS_REPORT') -> dict:
    return {'exists': False, 'warning': WARNING, 'missing_reason': reason, 'report': None}


def _hash(report) -> str:
    body = {k: v for k, v in report.items() if k not in ('report_hash', 'generated_at')}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def problem(report):
    """Why this is not a readiness report the page or the capability registry may use; None when it is one. The hash is
    an integrity check against accidental damage. It is not a signature and does not prove who wrote the file."""
    if not isinstance(report, dict) or report.get('kind') != KIND or report.get('warning') != WARNING:
        return 'NOT_A_READINESS_REPORT'
    if any(not isinstance(report.get(key), kind) for key, kind in REQUIRED_PARTS):
        return 'READINESS_REPORT_INCOMPLETE'
    try:
        if _hash(report) != report['report_hash']:
            return 'READINESS_REPORT_HASH_MISMATCH'
    except (TypeError, ValueError):
        return 'READINESS_REPORT_INCOMPLETE'
    for families in (report['sufficiency'].get('verdicts') or {}).values():
        if not isinstance(families, dict) or any(not isinstance(v, dict) or v.get('verdict') not in VERDICTS for v in families.values()):
            return 'UNEXPECTED_SUFFICIENCY_VERDICT'
    if any(not isinstance(b, dict) or b.get('status') not in BAR_STATES for b in report['specification_bars']):
        return 'UNEXPECTED_BAR_STATUS'
    return None


def summary(research_database) -> dict:
    """{'exists', 'warning', 'report', 'file'} for the readiness file beside ``research_database``."""
    path = Path(research_database).with_name(FILE_NAME)
    try:
        if not path.is_file():
            return empty()
        if path.stat().st_size > MAXIMUM_BYTES:
            return empty('READINESS_FILE_TOO_LARGE')
        report = json.loads(path.read_text())
        reason = problem(report)
        if reason:
            return empty(reason)
        return {'exists': True, 'warning': WARNING, 'report': report, 'file': '/'.join(path.parts[-3:])}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        return empty('READINESS_FILE_UNREADABLE:' + type(error).__name__)
