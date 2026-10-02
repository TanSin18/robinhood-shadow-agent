"""Read-only view of the Firm Lab database for the dashboard page and the CLI. Opens the file with mode=ro."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import MODE_BUILD_OBSERVE
from .baseline import STRATEGY_ID, TITLE
from .store import FORBIDDEN_TABLE_WORDS, default_path

FIXED = {'fills': 0, 'firm_trading_trial': 'NOT REGISTERED', 'october_research_stop_superseded': 'NO', 'official_lane_b': 'PAUSED', 'real_execution': 'DISABLED'}


def readiness(capability_rows, raw=None, daily=None) -> list:
    """The Data Readiness rows: one per data domain, in a fixed order. For each: the registry status, the chosen
    provider, what is known about the connection, the validation record and what is actually stored.
    ``raw`` is ``rawstore.summary_db``'s result; ``daily`` describes the stored daily closes."""
    from .capabilities import DATA_READINESS, NO_CREDENTIAL_PROVIDERS, NOT_SELECTED, PROVIDER_PLAN
    from .rawstore import DOMAIN_TABLE
    by = {c['capability']: c for c in capability_rows}
    raw = raw or {}
    connections = raw.get('connections') or {}
    out = []
    for label, capability, required_next in DATA_READINESS:
        row = by.get(capability) or {}
        item = {'domain': label, 'capability': capability, 'status': row.get('status') or 'UNAVAILABLE', 'source': row.get('provider'),
                'limitation': row.get('detail') or 'Not in the registry: treated as unavailable.', 'required_next': required_next,
                'provider': None, 'connection': 'NOT SELECTED', 'connection_detail': NOT_SELECTED.get(capability, ''), 'validation': 'NOT RUN',
                'validation_issues': [], 'sample': [], 'last_successful_ingest': None, 'observations': 0, 'rows': 0, 'oldest': None, 'newest': None,
                'failures': {}, 'flags': {}}
        if capability == 'daily_closes':
            daily = daily or {}
            item.update(provider='Control A’s recorded closes (read-only)', connection='ACTIVE' if daily.get('rows') else 'NOT CONFIGURED',
                        connection_detail='Read from the registered database, never from a broker.',
                        validation='PASS' if row.get('status') == 'AVAILABLE' else 'NOT RUN' if not daily.get('rows') else 'FAIL',
                        last_successful_ingest=daily.get('last_ingest'), observations=daily.get('rows', 0), oldest=daily.get('oldest'),
                        newest=daily.get('newest'))
        elif capability in PROVIDER_PLAN:
            provider, domains, needs = PROVIDER_PLAN[capability]
            link = connections.get(provider) or {}
            tables = [raw.get(DOMAIN_TABLE[d]) or {} for d in domains]
            runs = [r for t in tables for r in t.get('last_batch') or [] if (t.get('last_run') or {}).get('provider') == provider]
            covered = {r['domain'] for r in runs}
            failures = {}
            for t in tables:
                for code, n in (t.get('rejected_issue_counts') or {}).items():
                    failures[code] = failures.get(code, 0) + n
            if not runs:
                validation = 'NOT RUN'
            elif any(r['status'] == 'REJECTED' for r in runs):
                validation = 'FAIL'
            elif all(r['status'] == 'OK' for r in runs) and covered == set(domains):
                validation = 'PASS'
            elif any(r['status'] == 'OK' for r in runs):
                validation = 'INCOMPLETE'                     # part of the sample was stored; the provider did not answer for the rest
            else:
                validation = 'NOT RUN'                        # the provider did not answer, so nothing was validated
            stamps = [x for t in tables for x in (t.get('oldest'), t.get('newest')) if x]
            flags = {}
            for t in tables:
                for code, n in (t.get('flags') or {}).items():
                    flags[code] = flags.get(code, 0) + n
            open_source = provider in NO_CREDENTIAL_PROVIDERS
            item.update(provider=provider, connection=(link.get('state') or ('CONFIGURED' if open_source else 'NOT_CONFIGURED')).replace('_', ' '),
                        connection_detail=link.get('detail') or ('Public data, no credential. Not run yet.' if open_source else
                                                                 f'Credentials or provider activation required: {needs}.'),
                        flags=flags, rows=sum(t.get('rows', 0) for t in tables), validation=validation,
                        validation_issues=sorted({c for r in runs for c in r.get('issues') or [] if r['status'] == 'REJECTED'}),
                        sample=[{'instrument': r['instrument'], 'domain': r['domain'], 'status': r['status'], 'reason': r['reason']} for r in runs],
                        last_successful_ingest=max((t.get('last_successful_ingest') for t in tables if t.get('last_successful_ingest')), default=None),
                        observations=sum(t.get('distinct', t.get('rows', 0)) for t in tables), oldest=min(stamps) if stamps else None,
                        newest=max(stamps) if stamps else None, failures=failures)
        out.append(item)
    return out


def defaults() -> dict:
    """What a new Firm Lab database starts with, for a machine where it has not been created yet. Reads no file."""
    from .benchmarks import DEFINITIONS
    from .capabilities import INITIAL
    rows = [{'capability': c, 'status': s, 'provider': p, 'detail': d} for c, s, p, d in INITIAL]
    from .benchmarks import TREASURY_METHODOLOGY
    return {'capabilities': rows, 'data_readiness': readiness(rows), 'treasury_methodology': dict(TREASURY_METHODOLOGY),
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
        series = lambda b: {kind: {'observations': n, 'first': first, 'latest': [last, one('SELECT value FROM benchmark_observations WHERE benchmark_id=? '
                                                                                      'AND kind=? AND exchange_session_date=? ORDER BY id DESC LIMIT 1',
                                                                                      (b, kind, last))[0]]}
                            for kind, n, first, last in db.execute('SELECT kind, COUNT(*), MIN(exchange_session_date), MAX(exchange_session_date) FROM '
                                                                   'benchmark_observations WHERE benchmark_id=? GROUP BY kind', (b,)).fetchall()}
        benchmarks = [{'benchmark_id': b, 'name': n, 'status': s, 'note': note, 'implementation_status': impl, 'series': series(b),
                       'definition': json.loads(d) if d else None, 'defined_by': by,
                       'observations': one('SELECT COUNT(*) FROM benchmark_observations WHERE benchmark_id=?', (b,))[0],
                       'latest': one('SELECT exchange_session_date, value FROM benchmark_observations WHERE benchmark_id=? '
                                     'ORDER BY exchange_session_date DESC LIMIT 1', (b,))}
                      for b, n, s, note, impl, d, by in db.execute('SELECT benchmark_id, name, status, note, implementation_status, definition_json, '
                                                              'defined_by FROM benchmark_definitions ORDER BY rowid').fetchall()]
        from . import crosscheck, rawstore
        from .benchmarks import TREASURY_METHODOLOGY
        raw = rawstore.summary_db(db)
        cross = crosscheck.summarise(crosscheck.fundamentals_vs_filings(db)) if (raw.get('fundamental_observations') or {}).get('rows') else None
        closes = one("SELECT COUNT(*), MIN(exchange_session_date), MAX(exchange_session_date), MAX(ingested_at) FROM feature_observations "
                     "WHERE feature_name='close'")
        daily = {'rows': closes[0], 'oldest': closes[1], 'newest': closes[2], 'last_ingest': closes[3]}
        capability_rows = [{'capability': c, 'status': s, 'provider': p, 'detail': d} for c, s, p, d in
                           db.execute('SELECT capability, status, provider, detail FROM data_capabilities ORDER BY rowid')]
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
            'capabilities': capability_rows, 'data_readiness': readiness(capability_rows, raw, daily), 'raw': raw, 'sec_cross_check': cross,
            'treasury_methodology': dict(TREASURY_METHODOLOGY), 'treasury_index': json.loads(meta['treasury_index_status']) if meta.get('treasury_index_status') else None,
            'capability_registry_version': meta.get('capability_registry_version', '1'),
            'benchmarks': benchmarks,
            'experiments': [{'experiment_id': e, 'name': n, 'status': s} for e, n, s in db.execute('SELECT experiment_id, name, status FROM experiment_registry')],
            'refused_fill_attempts': one("SELECT COUNT(*) FROM events WHERE kind IN ('FILL_REFUSED','REAL_ORDER_REFUSED')")[0],
            **FIXED}
    except (sqlite3.Error, ValueError) as error:
        return {'exists': True, 'error': type(error).__name__, 'mode': None, **FIXED}
    finally:
        db.close()
