"""Session-time feature history: the unchanged Checkpoint 6 calculators, run once per instrument and session.

For each (instrument, session T) the request is "what was known at the close of T" against the modeling database
(``timeview``). Nothing in ``firm_lab.research_features`` is modified or re-implemented here: the same loader, the same
engine and the same calculation hash produce the values. One content-addressed row is stored per snapshot, holding all
of its results and a digest over the full Checkpoint 6 result identities, so a rerun that produces anything different
cannot be stored under the same identity.

Manual and local. No network, no model, no schedule.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import zlib
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from firm_lab.research_features.calendar import session_close
from firm_lab.research_features.engine import calculation_hash, compute
from firm_lab.research_features.inputs import load_snapshot
from firm_lab.research_features.sector import load_sector_context, mapping_at
from firm_lab.research_features.types import Request, canonical, content_hash

from . import BENCHMARK, TIME_POLICY, timeview

_DB = None


def _open(path):
    global _DB
    _DB = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=120)


def snapshot_id(instrument, session, digest) -> str:
    return content_hash([instrument, session, digest, TIME_POLICY])


def compute_snapshot(task) -> dict:
    """All Checkpoint 6 results for one instrument at the close of one session, in the compact stored form."""
    instrument, session = task
    request = Request(instrument, session, session_close(session))
    snapshot = load_snapshot(_DB, request)
    snapshot.update(load_sector_context(_DB, request))
    mapping = mapping_at(snapshot['mappings'], request.instrument, request.knowledge_cutoff, request.as_of_session)
    symbols = {BENCHMARK} | ({mapping['etf']} if mapping else set())
    for key in ('sector_membership_record', 'constituent_record'):
        if snapshot.get(key):
            symbols.update(snapshot[key]['members'])
    snapshot['reference_closes'] = {s: load_snapshot(_DB, replace(request, instrument=s))['closes'] for s in sorted(symbols)}
    rows = compute(snapshot, request)
    identities = hashlib.sha256()
    refs = set()
    results = []
    for row in rows:
        if row.known_at and row.known_at > request.knowledge_cutoff:
            raise ValueError('RESULT_KNOWN_AFTER_SESSION_CLOSE')            # the engine refuses this already; refuse it again here
        identities.update(content_hash(row).encode())
        refs.update((r.table, r.row_id, r.content_hash, r.known_at) for r in row.refs)
        results.append([row.family, row.name, row.feature_version, row.value, row.unit, row.availability, row.missing_reason, row.known_at])
    digest = calculation_hash()
    body = {'instrument': instrument, 'session': session, 'knowledge_cutoff': request.knowledge_cutoff, 'time_policy': TIME_POLICY,
            'calculation_hash': digest, 'results_digest': identities.hexdigest(), 'result_count': len(results),
            'available': sum(r[5] == 'AVAILABLE' for r in results),
            'input_refs_digest': content_hash(sorted(refs)), 'input_ref_count': len(refs),
            'latest_input_known_at': max((r[3] for r in refs), default=None),
            'results_zlib_b64': base64.b64encode(zlib.compress(canonical(results).encode(), 9)).decode()}
    return {'id': snapshot_id(instrument, session, digest), 'payload': body}


def read_results(payload) -> list:
    """[{family, name, version, value, unit, availability, missing_reason, known_at}] from a stored snapshot payload."""
    body = json.loads(payload) if isinstance(payload, str) else payload
    names = ('family', 'name', 'version', 'value', 'unit', 'availability', 'missing_reason', 'known_at')
    return [dict(zip(names, r)) for r in json.loads(zlib.decompress(base64.b64decode(body['results_zlib_b64'])))]


def universe(path) -> tuple:
    """(instruments, sessions) present as stored closes in the modeling database."""
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        instruments = [r[0] for r in db.execute("SELECT DISTINCT instrument FROM feature_observations WHERE feature_name='close' ORDER BY 1")]
        sessions = [r[0] for r in db.execute("SELECT DISTINCT exchange_session_date FROM feature_observations WHERE feature_name='close' ORDER BY 1")]
        return instruments, sessions
    finally:
        db.close()


def generate(path, *, instruments=None, sessions=None, workers=1, progress=None) -> dict:
    """Computes and stores every missing snapshot. Idempotent: an existing identity is counted as a duplicate."""
    timeview.check(path)
    all_instruments, all_sessions = universe(path)
    instruments = [i for i in all_instruments if instruments is None or i in instruments]
    sessions = [s for s in all_sessions if sessions is None or s in sessions]
    digest = calculation_hash()
    out = sqlite3.connect(Path(path).resolve(), timeout=120)
    receipt = {'calculation_hash': digest, 'time_policy': TIME_POLICY, 'instruments': len(instruments), 'sessions': len(sessions),
               'inserted': 0, 'duplicates': 0, 'results': 0, 'available': 0}
    try:
        timeview.create_tables(out)
        held = {r[0] for r in out.execute('SELECT id FROM modeling_feature_results')}
        tasks = [(i, s) for s in sessions for i in instruments if snapshot_id(i, s, digest) not in held]
        receipt['duplicates'] = len(instruments) * len(sessions) - len(tasks)

        def store(item):
            body = item['payload']
            with out:
                added = out.execute('INSERT OR IGNORE INTO modeling_feature_results VALUES (?,?,?)',
                                    (item['id'], canonical(body), datetime.now(timezone.utc).isoformat())).rowcount
            receipt['inserted' if added else 'duplicates'] += 1
            receipt['results'] += body['result_count']
            receipt['available'] += body['available']
            if progress and (receipt['inserted'] % 200 == 0):
                progress(receipt)

        if workers > 1 and tasks:
            import multiprocessing
            with multiprocessing.get_context('fork').Pool(workers, initializer=_open, initargs=(str(path),)) as pool:
                for item in pool.imap_unordered(compute_snapshot, tasks, chunksize=8):
                    store(item)
        else:
            _open(path)
            for task in tasks:
                store(compute_snapshot(task))
    finally:
        out.close()
    return receipt
