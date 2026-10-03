"""Stored-result projection only. No calculators, migration or write connection."""
from collections import Counter
from dataclasses import asdict
from datetime import date
import json
import re
import sqlite3
from .types import from_payload,timestamp,valid_hash
from .stored_payload import read_result


def feature_view(db,filters=None):
    empty={'rows':[],'coverage':{},'choices':[],'invalid_rows':0,'missing_reason':'NO_STORED_FEATURE_RUN'}
    db.execute('PRAGMA query_only=ON')
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'research_feature_runs','research_feature_results'}<=tables:
        return empty
    try:
        filters=filters or {}
        instrument=filters.get('instrument') or None
        session=filters.get('session') or None
        cutoff=timestamp(filters['known_by']) if filters.get('known_by') else None
        if instrument and not re.fullmatch(r'[A-Z0-9.\-]{1,16}',instrument):
            raise ValueError('INVALID_INSTRUMENT')
        if session:
            date.fromisoformat(session)
        # A completed receipt identifies one calculation version and knowledge
        # snapshot. Never silently mix outputs from different runs/versions.
        runs=[]
        for payload,created in db.execute('SELECT payload,created_at FROM research_feature_runs ORDER BY created_at DESC,id DESC'):
            data=json.loads(payload)
            if data.get('state')!='FINISHED':
                continue
            r=data['receipt']
            valid_hash(r['calculation_hash'])
            r={**r,'knowledge_cutoff':timestamp(r['knowledge_cutoff']),'computed_at':created}
            runs.append(r)
        choices=sorted({(r['instrument'],r['session'],r['knowledge_cutoff']) for r in runs},reverse=True)
        eligible=[r for r in runs if (not instrument or r['instrument']==instrument) and
                  (not session or r['session']==session) and (not cutoff or r['knowledge_cutoff']<=cutoff)]
        if not eligible:
            return {**empty,'choices':choices,'missing_reason':'NO_COMPLETED_RUN_AT_CUTOFF'}
        selected=eligible[0]
        query="""SELECT payload,created_at FROM research_feature_results
            WHERE json_extract(payload,'$.instrument')=? AND json_extract(payload,'$.as_of_session')=?
            AND json_extract(payload,'$.calculation_hash')=?
            AND json_extract(payload,'$.audit.knowledge_cutoff')=? ORDER BY id"""
        rows=[]; invalid=0
        for payload,created in db.execute(query,(selected['instrument'],selected['session'],selected['calculation_hash'],selected['knowledge_cutoff'])):
            try:
                r=read_result(db,payload)
                if r.known_at and r.known_at>selected['knowledge_cutoff']:
                    raise ValueError('FUTURE_RESULT')
                rows.append({**asdict(r),'computed_at':created})
            except (ValueError,KeyError,TypeError):
                invalid+=1
        rows.sort(key=lambda r:(r['family'],r['name'],r['feature_version']))
        return {**empty,'rows':rows,'choices':choices,'selected':selected,'invalid_rows':invalid,
                'coverage':dict(Counter(r['availability'] for r in rows)),
                'missing_reason':None if rows else 'NO_VALID_RESULTS_FOR_RUN'}
    except (ValueError,KeyError,TypeError,sqlite3.Error):
        return {**empty,'missing_reason':'INVALID_REQUEST_OR_STORED_FEATURE_DATA'}
