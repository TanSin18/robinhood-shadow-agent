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


# The Benchmark readiness rows: (label, benchmark id, observation kind, capability that decides the state, ruler label).
BENCHMARK_SERIES = (
    ('VTI price return', 'VTI_100', 'close_price_return_basis', 'daily_closes', ''),
    ('VTI total return', 'VTI_TOTAL_RETURN', 'vti_total_return_index', 'vti_total_return', ''),
    ('Treasury total return', 'FIXED_70_30', 'tbill_13w_accrual_index', 'treasury_total_return', ''),
    ('70/30 legacy', 'FIXED_70_30', 'index_70_30_vti_price_return_basis', 'treasury_total_return', 'LEGACY_PRICE_RETURN_RULER'),
    ('70/30 total-return', 'FIXED_70_30_TOTAL_RETURN', 'index_70_30_vti_total_return', 'total_return_ruler', 'TOTAL_RETURN_RULER'),
)
NORMALIZED_FIELDS = ('revenue', 'gross_profit', 'operating_income', 'net_income', 'eps_diluted', 'operating_cash_flow', 'capital_expenditure',
                     'cash_and_equivalents', 'total_debt', 'diluted_shares_weighted_average')
EVENT_VALUE_FIELDS = ('revenue', 'net_income', 'eps_diluted')


def benchmark_readiness(capability_rows, series=None, treasury_index=None, total_return=None) -> list:
    """One row per benchmark series: the capability state, what is stored and whether it validated. ``series`` maps
    (benchmark id, kind) to (observations, oldest, newest, latest value)."""
    by = {c['capability']: c for c in capability_rows}
    series = series or {}
    out = []
    for label, bench, kind, capability, ruler_label in BENCHMARK_SERIES:
        count, oldest, newest, latest = series.get((bench, kind)) or (0, None, None, None)
        state = (by.get(capability) or {}).get('status') or 'UNAVAILABLE'
        if not count and state == 'AVAILABLE' and capability != 'daily_closes':
            state = 'UNAVAILABLE'                               # never shown as available without stored observations
        if kind in ('tbill_13w_accrual_index', 'index_70_30_vti_price_return_basis'):
            run = treasury_index or {}
            validation = ('NOT RUN' if not run else 'PASS' if run.get('status') == 'OK' else 'FAIL')
            note = '' if not run or run.get('status') == 'OK' else str(run.get('gap_reason') or run.get('status'))
        elif kind in ('vti_total_return_index', 'index_70_30_vti_total_return'):
            run = total_return or {}
            ruler = kind == 'index_70_30_vti_total_return'
            good = run.get('status') == 'OK' and (not ruler or run.get('ruler_status') == 'OK')
            validation = ('NOT RUN' if not run else 'PASS' if good else 'FAIL')
            note = '' if not run or good else ', '.join(sorted({i.get('code', '') for i in run.get('issues') or []})) or str(
                run.get('gap_reason') or (run.get('ruler_gap_reason') if ruler else '') or run.get('status'))
        else:
            validation, note = ('PASS' if state == 'AVAILABLE' else 'NOT RUN' if not count else 'FAIL'), ''
        out.append({'series': label, 'benchmark_id': bench, 'kind': kind, 'capability': capability, 'status': state, 'label': ruler_label,
                    'observations': count, 'oldest': oldest, 'newest': newest, 'latest_value': latest, 'validation': validation,
                    'validation_note': note})
    return out


def _fundamentals(db, tables) -> dict:
    """What the latest company-facts sample found, company by company, from the stored validation reports. Reads only."""
    from .fundamentals import NOT_COLLECTED, OPTIONAL_FIELDS, REQUIRED_FIELDS, RULES_VERSION
    out = {'source': 'SEC XBRL company facts (SEC EDGAR)', 'normalized_fields': list(NORMALIZED_FIELDS), 'companies': [], 'accepted': 0,
           'required_fields': list(REQUIRED_FIELDS), 'optional_fields': list(OPTIONAL_FIELDS), 'not_collected': list(NOT_COLLECTED),
           'rules_version': RULES_VERSION,
           'rejected_runs': 0, 'unresolved': 0, 'unresolved_mappings': {}, 'stored_rows': 0, 'restatements': 0, 'not_found_in_filing': 0}
    if 'fundamental_fact_observations' not in tables or 'provider_runs' not in tables:
        return out
    out['stored_rows'] = db.execute('SELECT COUNT(*) FROM fundamental_fact_observations').fetchone()[0]
    out['restatements'] = db.execute("SELECT COUNT(*) FROM fundamental_fact_observations WHERE is_restatement='true'").fetchone()[0]
    out['not_found_in_filing'] = db.execute("SELECT COUNT(*) FROM fundamental_fact_observations WHERE confirmed_in_filing='NOT_FOUND'").fetchone()[0]
    last = db.execute("SELECT batch FROM provider_runs WHERE domain='xbrl_facts' ORDER BY id DESC LIMIT 1").fetchone()
    if not last:
        return out
    for instrument, status, issues, stored, duplicates, text in db.execute(
            "SELECT instrument, status, issues_json, stored, duplicates, diagnostics_json FROM provider_runs WHERE domain='xbrl_facts' AND batch=? ORDER BY id",
            (last[0],)):
        report = (json.loads(text or '{}') or {}).get('validation') or {}
        verdict = report.get('quality') or {}
        unresolved = verdict.get('unresolved_by_field') or {}
        company = {'instrument': instrument, 'status': status, 'issues': sorted({i['code'] for i in json.loads(issues or '[]')}),
                   'raw_facts': report.get('raw_facts_in_filings_read'), 'accepted': report.get('normalized_accepted') or 0,
                   'unresolved': report.get('unresolved') or 0, 'unresolved_by_field': unresolved, 'units': report.get('units') or {},
                   'filings': report.get('filings') or [], 'quality_passes': verdict.get('passes') is True,
                   'critical_unresolved': verdict.get('critical_unresolved') or [], 'checked_against_filing': report.get('checked_against_filing') or {},
                   'restatements': report.get('restatements') or 0, 'accepted_by_field': report.get('accepted_by_field') or {},
                   'not_confirmed': verdict.get('critical_not_confirmed_in_filing') or [],
                   'optional_fields_missing': report.get('optional_fields_missing') or [], 'derived_totals': report.get('derived_totals') or 0}
        out['companies'].append(company)
        out['accepted'] += company['accepted'] if status == 'OK' else 0
        out['rejected_runs'] += 1 if status == 'REJECTED' else 0
        out['unresolved'] += company['unresolved']
        for name, reasons in unresolved.items():
            for reason in reasons:
                out['unresolved_mappings'].setdefault(name, {}).setdefault(reason, []).append(instrument)
    return out


def _earnings(db, tables) -> dict:
    """Stored earnings-release filings, newest first, with the basic reported values of the linked periodic report read from
    the stored company facts at view time (each with its own SEC acceptance time). Facts only."""
    out = {'source': 'SEC EDGAR (8-K, Item 2.02)', 'events': [], 'stored': 0, 'transcripts': 'UNAVAILABLE', 'signal_or_model': 'NONE'}
    if 'earnings_event_observations' not in tables:
        return out
    rows = db.execute('SELECT instrument, fiscal_period_end, accession_number, accepted_timestamp, event_date, acceptance_session, form, filing_url, '
                      'release_document_url, periodic_accession_number, acceptance_time_conflict, MAX(id) FROM earnings_event_observations '
                      'GROUP BY instrument, accession_number ORDER BY accepted_timestamp DESC, instrument').fetchall()
    out['stored'] = len(rows)
    have_facts = 'fundamental_fact_observations' in tables
    for instrument, period_end, accession, accepted, event_date, session, form, filing_url, release_url, periodic, conflict, _ in rows[:40]:
        values = {}
        if have_facts and periodic:
            for name in EVENT_VALUE_FIELDS:
                found = db.execute("SELECT value, unit, period_type, accepted_timestamp FROM fundamental_fact_observations WHERE instrument=? AND "
                                   "accession_number=? AND normalized_field=? AND period_end=? AND relation_to_filing='current' "
                                   "ORDER BY CASE period_type WHEN '3M' THEN 0 WHEN '12M' THEN 1 ELSE 2 END, id DESC LIMIT 1",
                                   (instrument, periodic, name, period_end)).fetchone()
                if found:
                    values[name] = {'value': found[0], 'unit': found[1], 'period_type': found[2], 'accepted_timestamp': found[3]}
        out['events'].append({'instrument': instrument, 'fiscal_period_end': period_end, 'accession_number': accession, 'accepted_timestamp': accepted,
                              'event_date': event_date, 'acceptance_session': session, 'form': form, 'filing_url': filing_url,
                              'release_document_url': release_url, 'periodic_accession_number': periodic,
                              'acceptance_time_conflict': conflict == 'true', 'reported_values': values})
    return out


def defaults() -> dict:
    """What a new Firm Lab database starts with, for a machine where it has not been created yet. Reads no file."""
    from .benchmarks import DEFINITIONS
    from .capabilities import INITIAL
    rows = [{'capability': c, 'status': s, 'provider': p, 'detail': d} for c, s, p, d in INITIAL]
    from .benchmarks import TREASURY_METHODOLOGY
    return {'capabilities': rows, 'data_readiness': readiness(rows), 'treasury_methodology': dict(TREASURY_METHODOLOGY),
            'benchmark_readiness': benchmark_readiness(rows),
            'benchmarks': [{'benchmark_id': i, 'name': n, 'status': s, 'definition': d, 'defined_by': by, 'note': note,
                            'implementation_status': impl, 'observations': 0, 'latest': None} for i, n, s, d, by, note, impl in DEFINITIONS]}


def load(official_db=None, path=None, feature_filters=None) -> dict:
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
        kinds = {(b, k): (n, first, last, one('SELECT value FROM benchmark_observations WHERE benchmark_id=? AND kind=? AND exchange_session_date=? '
                                              'ORDER BY id DESC LIMIT 1', (b, k, last))[0])
                 for b, k, n, first, last in db.execute('SELECT benchmark_id, kind, COUNT(*), MIN(exchange_session_date), MAX(exchange_session_date) '
                                                        'FROM benchmark_observations GROUP BY benchmark_id, kind').fetchall()}
        treasury_index = json.loads(meta['treasury_index_status']) if meta.get('treasury_index_status') else None
        total_return = json.loads(meta['vti_total_return_status']) if meta.get('vti_total_return_status') else None
        from .macro_view import summary_db as macro_summary
        from .research_features.view import feature_view
        from .modeling_view import summary as modeling_summary
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
            'treasury_methodology': dict(TREASURY_METHODOLOGY), 'treasury_index': treasury_index, 'total_return': total_return,
            'benchmark_readiness': benchmark_readiness(capability_rows, kinds, treasury_index, total_return),
            'fundamentals': _fundamentals(db, set(tables)), 'earnings_events': _earnings(db, set(tables)),
            'capability_registry_version': meta.get('capability_registry_version', '1'),
            'benchmarks': benchmarks,
            'macro': macro_summary(db, set(tables)),
            'research_features': feature_view(db,feature_filters),
            'modeling': modeling_summary(path),
            'experiments': [{'experiment_id': e, 'name': n, 'status': s} for e, n, s in db.execute('SELECT experiment_id, name, status FROM experiment_registry')],
            'refused_fill_attempts': one("SELECT COUNT(*) FROM events WHERE kind IN ('FILL_REFUSED','REAL_ORDER_REFUSED')")[0],
            **FIXED}
    except (sqlite3.Error, ValueError) as error:
        return {'exists': True, 'error': type(error).__name__, 'mode': None, **FIXED}
    finally:
        db.close()
