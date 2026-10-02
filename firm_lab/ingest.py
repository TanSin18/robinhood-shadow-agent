"""Research-only ingestion: Control A's recorded closes -> Firm Lab feature store -> baseline counterfactual.

Reads the Official database through the read-only wall, writes only the Firm Lab database. No broker read,
no model call, no order. Run by hand (``python -m firm_lab.cli ingest``); nothing schedules it yet.
"""
from __future__ import annotations

from decimal import Decimal

from . import baseline, benchmarks, capabilities, features, official, sessions
from .store import canonical, now_utc

D = Decimal
SOURCE = 'control_a_decision_capsule'


def _done(store):
    with store.connect() as db:
        return {r[0] for r in db.execute("SELECT source_hash FROM ingest_runs WHERE source=? AND status='OK'", (SOURCE,))}


def _compare(record, recorded_ranked):
    """How the counterfactual lines up with what Control A itself recorded for the same run."""
    theirs = {str(r.get('instrument')): r for r in recorded_ranked or [] if isinstance(r, dict)}
    recorded_pick = str(recorded_ranked[0].get('instrument')) if recorded_ranked else None
    worst = None
    for c in record['candidates']:
        other = theirs.get(c['instrument'])
        if other and c['momentum_126d'] is not None and other.get('momentum_126d') is not None:
            diff = abs(D(c['momentum_126d']) - D(str(other['momentum_126d'])))
            worst = diff if worst is None or diff > worst else worst
    return {'control_a_recorded_selection': recorded_pick, 'matches_control_a': recorded_pick == record['selected_instrument'],
            'control_a_recorded_ranking': [str(r.get('instrument')) for r in recorded_ranked or []],
            'firm_lab_ranking': [c['instrument'] for c in sorted((c for c in record['candidates'] if c.get('rank')), key=lambda c: c['rank'])],
            'largest_momentum_difference': None if worst is None else str(worst)}


def ingest_official(store, official_db, now=None):
    now = now or now_utc()
    capabilities.seed(store, now)
    benchmarks.seed(store, now)
    report = {'capsules_seen': 0, 'capsules_ingested': 0, 'runs': []}
    done = _done(store)
    for capsule in official.capsules(official_db):
        report['capsules_seen'] += 1
        payload = capsule['payload']
        if capsule['hash'] in done or payload.get('data_mode') != 'live_readonly':
            continue
        started = now_utc().isoformat()
        closes = (payload.get('inputs') or {}).get('session_closes') or {}
        known_at = payload.get('observed_at') or capsule['created_at']
        momentum = ((payload.get('strategy_assessment') or {}).get('strategies') or {}).get('momentum_rotation') or {}
        universe = [str(s) for s in momentum.get('evaluated') or []]
        try:
            written = features.ingest_official_closes(store, closes, known_at=known_at, capsule_hash=capsule['hash'], cycle_id=capsule['cycle_id'], now=now)
            store.add_universe_snapshot(timestamp=sessions.utc_iso(known_at), source=SOURCE, symbols=universe, source_hash=capsule['hash'])
            for symbol in sorted(closes):
                features.store_baseline(store, symbol, known_at=known_at, now=now)
            record = baseline.evaluate(store, universe, known_at=known_at, write=False)
            check = _compare(record, momentum.get('ranked'))
            record = baseline.evaluate(store, universe, known_at=known_at, provenance={
                'source': SOURCE, 'capsule_hash': capsule['hash'], 'cycle_id': capsule['cycle_id'], 'control_a_observed_at': known_at,
                'plumbing_check': check})
            vti = benchmarks.record_vti(store, known_at=known_at, now=now)
            detail = {'closes': written, 'universe': len(universe), 'selected': record['selected_instrument'], 'plumbing_check': check,
                      'vti_observations_added': vti, 'exchange_session_date': record['exchange_session_date']}
            status = 'OK'
        except Exception as error:                        # fail closed: record it, write no partial claim of success
            detail, status = {'error_type': type(error).__name__, 'error': str(error)[:200]}, 'FAILED'
        with store.connect() as db:
            db.execute('INSERT INTO ingest_runs (started_at, finished_at, source, source_hash, status, detail_json) VALUES (?,?,?,?,?,?)',
                       (started, now_utc().isoformat(), SOURCE, capsule['hash'], status, canonical(detail)))
        store.event('INGEST', {'source': SOURCE, 'capsule_hash': capsule['hash'], 'status': status}, now)
        report['runs'].append({'capsule_hash': capsule['hash'], 'cycle_id': capsule['cycle_id'], 'status': status, **detail})
        report['capsules_ingested'] += status == 'OK'
    report['daily_data'] = capabilities.confirm_daily_data(store, now)      # AVAILABLE only if the stored closes validate
    return report
