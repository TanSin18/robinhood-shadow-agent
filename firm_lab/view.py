"""Read-only view of the Firm Lab database for the dashboard page and the CLI. Opens the file with mode=ro."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import MODE_BUILD_OBSERVE
from .baseline import STRATEGY_ID, TITLE
from .store import FORBIDDEN_TABLE_WORDS, default_path

FIXED = {'fills': 0, 'firm_trading_trial': 'NOT REGISTERED', 'october_research_stop_superseded': 'NO', 'official_lane_b': 'PAUSED', 'real_execution': 'DISABLED'}


def defaults() -> dict:
    """What a new Firm Lab database starts with, for a machine where it has not been created yet. Reads no file."""
    from .benchmarks import DEFINITIONS
    from .capabilities import INITIAL
    return {'capabilities': [{'capability': c, 'status': s, 'provider': p, 'detail': d} for c, s, p, d in INITIAL],
            'benchmarks': [{'benchmark_id': i, 'name': n, 'status': s, 'definition': d, 'defined_by': by, 'note': note,
                            'implementation_status': impl, 'observations': 0, 'latest': None} for i, n, s, d, by, note, impl in DEFINITIONS]}


def load(official_db=None, path=None) -> dict:
    path = Path(path) if path else default_path(official_db)
    if not path.is_file():
        return {'exists': False, 'mode': MODE_BUILD_OBSERVE, **FIXED}
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=0.5)
    try:
        one = lambda q, a=(): db.execute(q, a).fetchone()
        tables = sorted(r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'"))
        meta = dict(db.execute('SELECT key, value FROM firm_meta').fetchall())
        cf = one('SELECT timestamp, exchange_session_date, candidates_json, selected_instrument, provenance_json, label, record_hash FROM '
                 'counterfactual_decisions WHERE strategy_id=? ORDER BY id DESC LIMIT 1', (STRATEGY_ID,))
        ingest = one('SELECT finished_at, status, detail_json FROM ingest_runs ORDER BY id DESC LIMIT 1')
        benchmarks = [{'benchmark_id': b, 'name': n, 'status': s, 'note': note, 'implementation_status': impl,
                       'definition': json.loads(d) if d else None, 'defined_by': by,
                       'observations': one('SELECT COUNT(*) FROM benchmark_observations WHERE benchmark_id=?', (b,))[0],
                       'latest': one('SELECT exchange_session_date, value FROM benchmark_observations WHERE benchmark_id=? '
                                     'ORDER BY exchange_session_date DESC LIMIT 1', (b,))}
                      for b, n, s, note, impl, d, by in db.execute('SELECT benchmark_id, name, status, note, implementation_status, definition_json, '
                                                              'defined_by FROM benchmark_definitions ORDER BY rowid').fetchall()]
        return {
            'exists': True, 'mode': meta.get('mode'), 'database': '/'.join(path.parts[-3:]), 'created_at': meta.get('created_at'),
            'tables': tables, 'has_execution_tables': any(w in t for t in tables for w in FORBIDDEN_TABLE_WORDS),
            'feature_rows': one('SELECT COUNT(*) FROM feature_observations')[0],
            'instruments': one('SELECT COUNT(DISTINCT instrument) FROM feature_observations')[0],
            'last_feature_update': one('SELECT MAX(ingested_at) FROM feature_observations')[0],
            'latest_session': one("SELECT MAX(exchange_session_date) FROM feature_observations WHERE feature_name='close'")[0],
            'last_ingest': None if not ingest else {'finished_at': ingest[0], 'status': ingest[1], 'detail': json.loads(ingest[2])},
            'baseline': None if not cf else {'title': TITLE, 'timestamp': cf[0], 'exchange_session_date': cf[1], 'candidates': json.loads(cf[2]),
                                             'selected_instrument': cf[3], 'provenance': json.loads(cf[4]), 'label': cf[5], 'record_hash': cf[6]},
            'counterfactuals': one('SELECT COUNT(*) FROM counterfactual_decisions')[0],
            'capabilities': [{'capability': c, 'status': s, 'provider': p, 'detail': d} for c, s, p, d in
                             db.execute('SELECT capability, status, provider, detail FROM data_capabilities ORDER BY rowid')],
            'benchmarks': benchmarks,
            'experiments': [{'experiment_id': e, 'name': n, 'status': s} for e, n, s in db.execute('SELECT experiment_id, name, status FROM experiment_registry')],
            'refused_fill_attempts': one("SELECT COUNT(*) FROM events WHERE kind IN ('FILL_REFUSED','REAL_ORDER_REFUSED')")[0],
            **FIXED}
    except (sqlite3.Error, ValueError) as error:
        return {'exists': True, 'error': type(error).__name__, 'mode': None, **FIXED}
    finally:
        db.close()
