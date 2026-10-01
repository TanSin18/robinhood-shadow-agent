"""View-only Agent Desk: stdlib SQLite reads, no inbox/cycle/broker imports."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
import json
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlsplit

from .room_projection import project_decision_room
from .components import ROUTES
from .router import render

ET=ZoneInfo('America/New_York')
ASSETS=Path(__file__).resolve().parents[1]/'static'

@contextmanager
def open_readonly(path):
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=0,isolation_level=None)
    try:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        if db.execute('PRAGMA journal_mode').fetchone()[0].lower()!='wal':
            raise ValueError('Preview requires an existing WAL database')
        deadline=time.monotonic()+.1
        db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
        def authorize(action,a,b,*unused):
            if action in {sqlite3.SQLITE_SELECT,sqlite3.SQLITE_READ,sqlite3.SQLITE_FUNCTION,sqlite3.SQLITE_TRANSACTION}:
                return sqlite3.SQLITE_OK
            if action==sqlite3.SQLITE_PRAGMA and a=='query_only' and b is None:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        db.set_authorizer(authorize)
        yield db
    finally:
        db.close()

def public(value):
    if isinstance(value,dict):
        return {k:public(v) for k,v in value.items() if not (any(s in k.lower() for s in ('account_id','account_number','last4','secret','credential','authorization_id')) or ('token' in k.lower() and not k.lower().endswith('_tokens')))}
    if isinstance(value,list): return [public(v) for v in value]
    return value

def _research_files(path):
    """Shadow research outputs kept beside the runtime (never the official database)."""
    base=Path(path).resolve().parents[2]/'robinhood-diagnostics'
    out={}
    for key,rel in (('screen','universe/latest.json'),('backtest','backtest/report.json')):
        try:
            data=json.loads((base/rel).read_text())
            out[key]=public(data) if isinstance(data,dict) else None
        except (OSError,ValueError):
            out[key]=None
    return out


def _promotion(path):
    try:
        from eval.promotion_stats import evaluate, load
        return evaluate(load(path))
    except Exception as error:  # module ships with the runtime release; absent is shown as absent
        return {'unavailable':type(error).__name__}


def _capsule_view(row):
    """The latest decision capsule, reduced to what the Portfolio page explains: the signal table for every
    ticker, why each one was or wasn't picked, and daily closes for anything held (plus VTI) for charts."""
    if not row:
        return None
    try:
        cap=json.loads(row['payload'])
    except (TypeError,ValueError):
        return None
    assess=cap.get('strategy_assessment') or {}
    outcome=cap.get('outcome') or {}
    held=set()
    for acct in ((cap.get('inputs') or {}).get('paper_accounts') or {}).values():
        held.update((acct.get('positions') or {}).keys())
    held.update(r.get('instrument') for r in outcome.get('desk_results') or [] if r.get('instrument'))
    held.update(s.get('instrument') for s in assess.get('signals') or [] if s.get('instrument'))
    closes=(cap.get('inputs') or {}).get('session_closes') or {}
    strategies={k:{'version':v.get('version'),'blocked':v.get('blocked') or {},'evaluated':v.get('evaluated') or [],
                   'ranked':[x.get('instrument') for x in v.get('ranked') or []],'qualifying_count':v.get('qualifying_count')}
                for k,v in (assess.get('strategies') or {}).items() if isinstance(v,dict)}
    return public({'cycle_id':row['cycle_id'],'observed_at':cap.get('observed_at') or row['created_at'],
        'decision':outcome.get('decision') or {},'desk_results':outcome.get('desk_results') or [],'models':cap.get('models') or {},
        'features':assess.get('features') or {},'signals':assess.get('signals') or [],'strategies':strategies,
        'qualification_note':assess.get('qualification_note'),'decision_date':assess.get('decision_date'),
        'liquidity':(cap.get('inputs') or {}).get('median_dollar_volume_20d') or {},
        'vols':(cap.get('inputs') or {}).get('vols') or {},
        'closes':{t:closes[t] for t in sorted(held|{'VTI'}) if isinstance(closes.get(t),dict)}})


def snapshot(path,*,now=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None: raise ValueError('Aware clock required')
    # Fetch and close before JSON projection, HTML rendering or socket writes.
    with open_readonly(path) as db:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        def rows(table,columns,order):
            return [dict(r) for r in db.execute(f'SELECT {columns} FROM {table} ORDER BY {order} DESC LIMIT 200')] if table in tables else []
        cards=rows('approval_inbox','id,status,issued,expires,payload','issued')
        traces=rows('local_traces','id,created_at,payload_json','id')
        runs=rows('run_states','id,created_at,payload_json','id')
        handoff_rows=rows('handoffs','id,created_at,payload_json','id')
        # Real Agentic account: the last VERIFIED tripwire snapshot (cash, position
        # quantities, order states). Never account numbers; instrument ids are not shown.
        broker_snapshot=(db.execute("SELECT created_at,payload_json FROM broker_state_snapshots WHERE status='VERIFIED' ORDER BY id DESC LIMIT 1").fetchone()
                         if 'broker_state_snapshots' in tables else None)
        tripwire_last=(db.execute('SELECT status,created_at FROM broker_tripwire_events ORDER BY id DESC LIMIT 1').fetchone()
                       if 'broker_tripwire_events' in tables else None)
        paper_rows=[dict(r) for r in db.execute('SELECT lane,track,payload FROM paper_accounts')] if 'paper_accounts' in tables else []
        fill_rows=rows('fills','id,created_at,payload_json','id')
        tripwire_rows=rows('broker_tripwire_events','id,status,change_class,created_at','id')
        real_rows=([dict(r) for r in db.execute("SELECT created_at,status,payload_json FROM broker_state_snapshots ORDER BY id DESC LIMIT 200")]
                   if 'broker_state_snapshots' in tables else [])
        capsule_row=(db.execute('SELECT cycle_id,created_at,payload FROM decision_capsules ORDER BY created_at DESC LIMIT 1').fetchone()
                     if 'decision_capsules' in tables else None)
        capsule_row=dict(capsule_row) if capsule_row else None
        values=rows('daily_values','id,created_at,payload_json','id')
        cycle_meta={}
        if 'cycle_runs' in tables:
            for r in db.execute('SELECT payload FROM cycle_runs'):
                try:
                    m=json.loads(r['payload'])
                except (TypeError,ValueError):
                    continue
                if isinstance(m,dict) and isinstance(m.get('cycle_id'),str):
                    cycle_meta[m['cycle_id']]={k:m.get(k) for k in ('trigger','recovery_of','temporary_api_budget_usd','recovery_count')}
    projected=[]
    for row in cards:
        card=public(json.loads(row['payload']))
        card.update({key:row[key] for key in ('id','status','issued','expires')})
        try:
            expires=datetime.fromisoformat(row['expires'])
            if expires.tzinfo is None: raise ValueError()
            passed=now>=expires
            if passed and card['status']=='PENDING': card['status']='EXPIRED'
            card['expiry_label']=('Expired ' if passed else 'Expires ')+expires.astimezone(ET).strftime('%I:%M %p').lstrip('0')+' ET'
        except (TypeError,ValueError):
            card['status']='UNAVAILABLE';card['expiry_label']='Expiry not recorded — unavailable'
        card['actionable']=False
        projected.append(card)
    records=[{**public(json.loads(r['payload_json'])), '_row_id':r['id'], '_created_at':r['created_at']} for r in traces]
    # Same documented six-stage projector; unrecorded work remains unrecorded.
    rooms=project_decision_room(records,projected)
    from .run_category import categorize
    for room in rooms:
        room['category']=categorize(room, cycle_meta.get(room.get('review_id')))
    history=[]
    for row in runs:
        payload=public(json.loads(row['payload_json']))
        if payload.get('status') in {'COMPLETED','FAILED','HOLD_OPERATIONAL'}:
            history.append({'kind':'cycle','timestamp':row['created_at'],'summary':payload.get('reason') or payload.get('decision',{}).get('reason') or payload['status']})
    portfolio={'real':None,'paper':[],'values':[]}
    if broker_snapshot:
        snap=json.loads(broker_snapshot['payload_json'])
        portfolio['real']={'as_of':broker_snapshot['created_at'],'cash':snap.get('cash'),
            'positions':[{'quantity':p.get('quantity'),'direction':p.get('direction')} for p in snap.get('positions',[])],
            'open_orders':{k:len(v) for k,v in (snap.get('orders') or {}).items()},
            'last_check':dict(tripwire_last) if tripwire_last else None}
    portfolio['fills']=[public(json.loads(r['payload_json'])) for r in reversed(fill_rows)]
    portfolio['tripwire']=[{k:r[k] for k in ('status','change_class','created_at')} for r in reversed(tripwire_rows)]
    portfolio['real_history']=[]
    for r in reversed(real_rows):
        try:
            snap_=json.loads(r['payload_json'])
        except (TypeError,ValueError):
            continue
        portfolio['real_history'].append({'at':r['created_at'],'status':r['status'],'cash':snap_.get('cash'),
                                          'positions':len(snap_.get('positions') or []),
                                          'orders':sum(len(v) for v in (snap_.get('orders') or {}).values())})
    portfolio['capsule']=_capsule_view(capsule_row)
    for row in paper_rows:
        state_=json.loads(row['payload'])
        portfolio['paper'].append({'lane':row['lane'],'track':row['track'],'start':state_.get('start'),'capital_version':state_.get('capital_version'),'settled_cash':state_.get('settled_cash'),
            'unsettled_cash':state_.get('unsettled_cash'),'marks':state_.get('marks') or {},'peak':state_.get('peak'),
            'day_start_value':state_.get('day_start_value'),'weekly_start_value':state_.get('weekly_start_value'),
            'peak_breaker_latched':bool(state_.get('peak_breaker_latched')),'kill_switch':bool(state_.get('global_kill_switch')),
            'fills':[public(f) for f in (state_.get('fills') or []) if isinstance(f,dict)],'positions':[{k:p.get(k) for k in ('ticker','asset_class','quantity','average_cost','option_type','strike','expiry','multiplier')}
                                                                        for p in (state_.get('positions') or {}).values()] if isinstance(state_.get('positions'),dict) else []})
    research={'protective':[],'rebase':None}
    for row in values:
        v=json.loads(row['payload_json'])
        if v.get('kind')=='paper_valuation' and 'comparison' not in v:
            portfolio['values'].append({k:v.get(k) for k in ('timestamp','lane','track','value','data_mode')})
        elif v.get('kind')=='protective_check':
            research['protective'].append({k:v.get(k) for k in ('timestamp','status','fired','held','error_type')})
        elif v.get('kind')=='capital_rebase' and research['rebase'] is None:
            research['rebase']={k:v.get(k) for k in ('timestamp','capital','lane','version')}
    research.update(_research_files(path))
    research['promotion']=_promotion(path)
    try:
        from agents.cards import default_path, read_view
        card_inbox=read_view(default_path(path))
    except Exception as error:
        card_inbox={'cards':[],'journal':[],'acks':[],'error':type(error).__name__}
    try:
        from .firm_page import load as load_firm
        firm=load_firm(path)
    except Exception as error:
        firm={'exists':False,'error':type(error).__name__}
    try:
        from .analyst_page import load as load_analyst
        analyst=load_analyst(path)
    except Exception as error:
        analyst={'exists':False,'error':type(error).__name__}
    return {'preview':True,'card_inbox':card_inbox,'firm':firm,'analyst':analyst,'updated_at':now.isoformat(),'cards':projected,'history':history,'portfolio':portfolio,'research':research,
        'decision_room':rooms,'paused':(Path(path).parent/'STOP_TRADING').exists(),
        'accounts':[], 'reports':[], 'tripwire':[],
        'handoffs':[public(json.loads(r['payload_json'])) for r in handoff_rows]}

def make_server(database,port=8766,*,clock=None):
    clock=clock or (lambda:datetime.now(timezone.utc))
    read_lock=Lock()
    class Handler(BaseHTTPRequestHandler):
        timeout=5
        def log_message(self,*args): pass
        def send(self,status,body,kind='text/html; charset=utf-8'):
            body=body.encode() if isinstance(body,str) else body
            self.send_response(status)
            for key,value in {'Content-Type':kind,'Content-Length':str(len(body)),
                'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
                'Content-Security-Policy':"default-src 'none'; style-src 'self'; script-src 'self'; img-src 'self'; font-src 'self'; connect-src 'none'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'"}.items(): self.send_header(key,value)
            self.end_headers();self.wfile.write(body)
        def do_POST(self): self.send(405,'Preview — view only. All actions are disabled.')
        do_PUT=do_PATCH=do_DELETE=do_POST
        def do_GET(self):
            if self.headers.get('Host') not in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}:
                return self.send(403,'Local preview only')
            path=urlsplit(self.path).path
            if path.startswith('/assets/'):
                asset=(ASSETS/path.removeprefix('/assets/')).resolve()
                types={'.css':'text/css','.js':'text/javascript','.svg':'image/svg+xml','.woff2':'font/woff2'}
                if not asset.is_relative_to(ASSETS) or asset.suffix not in types or not asset.is_file(): return self.send(404,'Not found')
                return self.send(200,asset.read_bytes(),types[asset.suffix])
            if path not in dict(ROUTES): return self.send(404,'Not found')
            try:
                with read_lock:
                    state=snapshot(database,now=clock())
                body=render(path,state,None,'')
            except Exception: return self.send(503,'Preview — view only. Records temporarily unavailable; no healthy status is assumed.')
            self.send(200,body)
    # Browser preconnections must not monopolize request handling. Only database
    # reads are serialized; no lock or DB connection spans socket writes.
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True)
    parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args()
    snapshot(args.database)
    with make_server(args.database,args.port) as server:
        print(f'Preview — view only: http://127.0.0.1:{server.server_port}',flush=True)
        server.serve_forever()

if __name__=='__main__': main()
