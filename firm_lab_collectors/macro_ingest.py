"""Manual macro capture/ingestion. Run only deliberately; never a scheduled job.

python -m firm_lab_collectors.macro_ingest --database RESEARCH_DB --official-database OFFICIAL_DB --capture-directory NEW_DIRECTORY
The Official path is only an isolation constraint. It is never opened.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from firm_lab.macro import MacroStore
from firm_lab.errors import FirmLabError
from firm_lab.capabilities import set_status
from firm_lab.store import canonical
from .macro import parse_release, parse_treasury, treasury_candidates, validate_links
from .transport import HttpTransport, Response

URLS = tuple(
    [('fed',f'https://www.federalreserve.gov/newsevents/pressreleases/monetary{d}a.htm') for d in ('20260617','20260729','20260916')]
    + [('pce',f'https://www.bea.gov/news/2026/personal-income-and-outlays-{m}-2026') for m in ('june','july','august')]
    + [('cpi',f'https://www.bls.gov/news.release/archives/cpi_{d}.htm') for d in ('08122026','09112026')]
    + [('labor',f'https://www.bls.gov/news.release/archives/empsit_{d}.htm') for d in ('08072026','09042026')]
    + [('treasury','https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv')])
FAMILIES={'fed':('fed_policy_data',('fed_target_lower','fed_target_upper')),
          'cpi':('cpi',('cpi_headline_nsa','cpi_core_nsa')),
          'pce':('pce',('pce_headline_mom_sa','pce_core_mom_sa')),
          'labor':('labor_data',('unemployment_rate','nonfarm_payroll_change')),
          'treasury':('treasury_yields',('treasury_2y','treasury_10y'))}


def ingest_responses(responses,path,*,official_db,now,network_requests=False):
    store=MacroStore(path,official_db=official_db)
    with store.lab.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS macro_ingest_receipts (id INTEGER PRIMARY KEY, at TEXT NOT NULL, family TEXT NOT NULL, payload_json TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS macro_release_evidence (source_hash TEXT PRIMARY KEY, source_url TEXT NOT NULL, metadata_json TEXT NOT NULL)')
    totals={}
    for family,response in responses:
        report=dict(requests=int(network_requests),documents=1,parsed=0,accepted=0,rejected=0,duplicates=0,revisions=0,events=0,reasons={})
        try:
            if not response.ok: raise FirmLabError(f'HTTP_{response.status}')
            if family=='treasury':
                # Decode identities for the rejection receipt, never insert date-only candidates.
                report['parsed']=len(treasury_candidates(response.body,now=now))
                parse_treasury(response.body)
            bundle=parse_release(family,response,now=now,include_prior=True)
            report['parsed']=len(bundle['observations'])
            # Assign the next LOCAL version; never represent this as the publisher's vintage count.
            with store.lab.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                for o,e in zip(bundle['observations'],bundle['events']):
                    old=db.execute('SELECT revision,payload_json FROM macro_observations WHERE series=? AND period=? ORDER BY revision DESC',
                                   (o['series'],o['period'])).fetchall()
                    identical=next((revision for revision,payload in old if json.loads(payload)['source_hash']==o['source_hash'] and json.loads(payload)['published_at']==o['published_at']),None)
                    o['revision']=identical if identical is not None else old[0][0]+1 if old else 0
                    e['revision']=o['revision']
                validate_links(bundle)
                for o,e in zip(bundle['observations'],bundle['events']):
                    state=store.add_observation(o,raw=response.body,now=now,_connection=db)
                    report['duplicates' if state=='DUPLICATE' else 'accepted']+=1
                    report['revisions']+=state=='REVISED'
                    event_state=store.add_event(e,raw=response.body,now=now,_connection=db)
                    report['events']+=event_state!='DUPLICATE'
                digest=hashlib.sha256(response.body).hexdigest()
                db.execute('INSERT OR IGNORE INTO macro_release_evidence VALUES(?,?,?)',
                           (digest,response.url,canonical(bundle['metadata'] | {'observation_versions':{o['series']+':'+o['period']:o['revision'] for o in bundle['observations']}})))
        except (FirmLabError,ValueError,UnicodeError) as error:
            report.update(accepted=0,duplicates=0,revisions=0,events=0)
            report['rejected']+=max(1,report['parsed'])
            report['reasons'][str(error)]=1
        with store.lab.connect() as db:
            db.execute('INSERT INTO macro_ingest_receipts(at,family,payload_json) VALUES(?,?,?)',
                       (now.isoformat(),family,canonical(report | {'source_url':response.url,'captured_at':response.fetched_at,
                         'source_hash':hashlib.sha256(response.body).hexdigest(),'http_status':response.status})))
        total=totals.setdefault(family,{k:0 for k in ('requests','documents','parsed','accepted','rejected','duplicates','revisions','events')} | {'reasons':{}})
        for key in total:
            if key!='reasons': total[key]+=report[key]
        for key,count in report['reasons'].items(): total['reasons'][key]=total['reasons'].get(key,0)+count
    for family,(cap,series) in FAMILIES.items():
        if family not in totals:
            continue  # Another family's capture is not a fresh validation of this family.
        with store.lab.connect() as db:
            counts=[db.execute('SELECT count(*) FROM macro_observations WHERE series=?',(s,)).fetchone()[0] for s in series]
        rows=sum(counts); failed=totals.get(family,{}).get('rejected',0)
        status='AVAILABLE' if all(counts) and not failed else 'PARTIAL_EXISTING' if rows else 'UNAVAILABLE'
        detail=f'{rows} validated observations. Scope: {", ".join(series)}. '+('; '.join(totals.get(family,{}).get('reasons',{})) or 'No inferred publication times. Historical values become locally known only at capture.')
        set_status(store.lab,cap,status,'Official macro publishers',detail,now,evidence={'provider':'Official macro publishers','records':rows,'validation_passed':True,'validated_at':now.isoformat()} if status=='AVAILABLE' else None)
    with store.lab.connect() as db:
        event_count=db.execute('SELECT count(*) FROM macro_events').fetchone()[0]
    set_status(store.lab,'macro_event_calendar','PARTIAL_EXISTING' if event_count else 'UNAVAILABLE','Official release documents',
               f'{event_count} factual event-series records. Future scheduled calendar and missing families not confirmed.',now)
    for name,state in [('macro_regime','NOT_STARTED'),('market_volatility','UNAVAILABLE'),('technical_engine','NOT_STARTED')]:
        set_status(store.lab,name,state,None,'No model, signal or newly activated market feed.',now)
    return totals


def load_capture(folder):
    folder=Path(folder).resolve()
    rows=[]
    for entry in json.loads((folder/'manifest.json').read_text()):
        file=folder/entry['file']
        if file.resolve().parent!=folder or file.is_symlink(): raise FirmLabError('CAPTURE_PATH_REFUSED')
        raw=file.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']: raise FirmLabError('CAPTURE_HASH_MISMATCH')
        rows.append((entry['family'],Response(entry['status'],raw,entry['url'],entry['fetched_at'])))
    return rows


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True); parser.add_argument('--official-database',required=True)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--capture-directory'); group.add_argument('--from-capture')
    args=parser.parse_args(argv)
    # Verify database isolation before any requests; never touches Official.
    MacroStore(args.database,official_db=args.official_database)
    if args.from_capture:
        result=ingest_responses(load_capture(args.from_capture),args.database,official_db=args.official_database,now=datetime.now(timezone.utc))
        print(json.dumps(result,indent=2))
        return 2 if any(r['rejected'] for r in result.values()) else 0
    folder=Path(args.capture_directory)
    folder.mkdir(parents=True,exist_ok=False)
    transport=HttpTransport(['www.federalreserve.gov','www.bls.gov','www.bea.gov','home.treasury.gov'],
                            user_agent='FirmLabResearch/1.0 (personal research; manual small validation sample)',min_interval=1,timeout=20)
    responses=[]; manifest=[]
    for i,(family,url) in enumerate(URLS):
        response=transport.get(url)
        name=f'{i:02d}-{family}.raw'
        (folder/name).write_bytes(response.body)
        responses.append((family,response))
        manifest.append({'family':family,'file':name,'url':response.url,'status':response.status,'fetched_at':response.fetched_at,'sha256':hashlib.sha256(response.body).hexdigest()})
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2))
    result=ingest_responses(responses,args.database,official_db=args.official_database,now=datetime.now(timezone.utc),network_requests=True)
    (folder/'receipt.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    return 2 if any(r['rejected'] for r in result.values()) else 0


if __name__=='__main__':
    raise SystemExit(main())
