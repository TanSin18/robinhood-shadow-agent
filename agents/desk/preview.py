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

from agents.decision_room import project_decision_room
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
        return {k:public(v) for k,v in value.items() if not any(s in k.lower() for s in ('account_id','account_number','last4','token','secret','credential'))}
    if isinstance(value,list): return [public(v) for v in value]
    return value

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
    history=[]
    for row in runs:
        payload=public(json.loads(row['payload_json']))
        if payload.get('status') in {'COMPLETED','FAILED','HOLD_OPERATIONAL'}:
            history.append({'kind':'cycle','timestamp':row['created_at'],'summary':payload.get('reason') or payload.get('decision',{}).get('reason') or payload['status']})
    return {'preview':True,'updated_at':now.isoformat(),'cards':projected,'history':history,
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
