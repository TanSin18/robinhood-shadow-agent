"""Operator-invoked, local research generation. Dry-run unless --write."""
import argparse
from collections import Counter
from dataclasses import replace
import json
import sqlite3
from .calendar import resolve_request
from .inputs import load_snapshot
from .engine import compute, calculation_hash
from .registry import definitions
from .sector import current_mappings, mapping_at,load_sector_context
from .store import FeatureStore, validate_path, CANONICAL_OFFICIAL


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True)
    parser.add_argument('--instrument',required=True)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--as-of')
    mode.add_argument('--session')
    parser.add_argument('--known-by')
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args(argv)
    try:
        request=resolve_request(args.instrument,as_of=args.as_of,session=args.session,known_by=args.known_by)
        path=validate_path(args.database,CANONICAL_OFFICIAL)
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
            snapshot=load_snapshot(db,request)
            snapshot.update(load_sector_context(db,request))
            mapping=mapping_at(snapshot['mappings'],request.instrument,request.knowledge_cutoff,request.as_of_session)
            symbols={'VTI'} | ({mapping['etf']} if mapping else set())
            for key in ('sector_membership_record','constituent_record'):
                if snapshot.get(key):
                    symbols.update(snapshot[key]['members'])
            snapshot['reference_closes']={s:load_snapshot(db,replace(request,instrument=s))['closes'] for s in sorted(symbols)}
        rows=compute(snapshot,request)
        receipt={'mode':'WRITE' if args.write else 'DRY_RUN','instrument':request.instrument,
            'session':request.as_of_session,'knowledge_cutoff':request.knowledge_cutoff,
            'temporal_mode':'HISTORICAL_PIT' if args.as_of else 'RETROSPECTIVE_NOT_HISTORICAL_AVAILABILITY',
            'calculation_hash':calculation_hash(),'available':sum(r.value is not None for r in rows),
            'unavailable':sum(r.value is None for r in rows),'inserted':0,'duplicates':0,
            'missing_reasons':dict(Counter(r.missing_reason for r in rows if r.missing_reason)),
            'families':{family:dict(available=sum(r.family==family and r.value is not None for r in rows),
                unavailable=sum(r.family==family and r.value is None for r in rows)) for family in sorted({r.family for r in rows})}}
        if args.write:
            with FeatureStore(path) as store:
                for record in snapshot['mappings']:
                    store.register_mapping(record)
                for key in ('sector_membership_record','constituent_record'):
                    if snapshot.get(key):
                        store.register_mapping(snapshot[key])
                run=store.start_run(request)
                for d in definitions():
                    store.register(d)
                for row in rows:
                    receipt['inserted' if store.append(row) else 'duplicates']+=1
                store.finish_run(run,receipt)
        print(json.dumps(receipt,sort_keys=True))
        return 0
    except (ValueError,sqlite3.Error) as exc:
        print(json.dumps({'status':'REJECTED','reason':str(exc)}))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
