"""Read-only macro projection. Never initializes a schema or contacts a provider."""
import json
from datetime import datetime, timezone


def summary_db(db, tables):
    result={'latest':[], 'events':[], 'receipts':[], 'regime':'NOT_STARTED', 'trading':'NO TRADES'}
    if not {'macro_observations','macro_events'} <= tables:
        return result
    now=datetime.now(timezone.utc).isoformat()
    latest={}
    for (payload,) in db.execute('SELECT payload_json FROM macro_observations WHERE known_at<=? ORDER BY period,revision',(now,)):
        row=json.loads(payload)
        if 'macro_release_evidence' in tables:
            evidence=db.execute('SELECT metadata_json FROM macro_release_evidence WHERE source_hash=?',(row['source_hash'],)).fetchone()
            row['source_metadata']=json.loads(evidence[0]) if evidence else {}
        latest[row['series']]=row
    result['latest']=list(latest.values())
    result['observation_rows']=db.execute('SELECT count(*) FROM macro_observations').fetchone()[0]
    for (payload,) in db.execute('SELECT payload_json FROM macro_events WHERE known_at<=? ORDER BY published_at DESC,revision DESC LIMIT 24',(now,)):
        row=json.loads(payload)
        previous=db.execute('SELECT payload_json FROM macro_events WHERE event_id=? AND revision=? AND known_at<=?',
                            (row['event_id'],row['revision']-1,now)).fetchone()
        row['previous_local_value']=json.loads(previous[0]).get('released_value') if previous else None
        result['events'].append(row)
    if 'macro_ingest_receipts' in tables:
        seen=set()
        for family,payload in db.execute('SELECT family,payload_json FROM macro_ingest_receipts ORDER BY id DESC'):
            if family not in seen:
                result['receipts'].append({'family':family,**json.loads(payload)})
                seen.add(family)
    return result
