"""Durable daily claims with an OS worker lock and transaction-time fencing."""
import fcntl
import json
import os
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from agents.operator import MarketSchedule
from agents.safety_events import safety_stopped,ensure_operations_schema
from data.database_role import require_database_role

ET=ZoneInfo('America/New_York')

def eligible(now):
    if now.tzinfo is None: raise ValueError('Timezone-aware timestamp required')
    return MarketSchedule().classify(now) is MarketSchedule.State.TRADING_WINDOW


_OFFICIAL_CONTEXT_MARKER=object()


@dataclass(frozen=True)
class OfficialRunContext:
    cycle_id: str
    database_path: Path
    trigger: str
    _marker: object

    def validate(self, path, cycle_id):
        return (
            self._marker is _OFFICIAL_CONTEXT_MARKER
            and self.database_path == Path(path).resolve()
            and self.cycle_id == cycle_id
            and self.trigger in {'scheduled','scheduled_recovery'}
        )

class CycleLifecycle:
    def __init__(self,path,dashboard_base_url='http://127.0.0.1:8765'):
        self.path=Path(path).resolve(); self.handle=None; self.cycle_id=None; self.official_context=None
        self.dashboard_base_url=dashboard_base_url.rstrip('/')
    def connect(self): return sqlite3.connect(self.path,timeout=15)
    def schema(self,db):
        db.execute('CREATE TABLE IF NOT EXISTS cycle_runs(day TEXT PRIMARY KEY,status TEXT,payload TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS cycle_events(id TEXT PRIMARY KEY,created_at TEXT,payload TEXT)')
        ensure_operations_schema(db)
    def event(self,db,key,status,now,payload):
        db.execute('INSERT OR IGNORE INTO cycle_events VALUES (?,?,?)',(key,now.isoformat(),json.dumps({'status':status,**payload})))
        if status in {'FAILED','FAILED_STALLED','MISSED_WINDOW','AUTH_LOST','REQUIRED_ACTION'}:
            from agents.notification_outbox import enqueue
            priority = 1 if status in {'FAILED','FAILED_STALLED','MISSED_WINDOW'} else 0
            enqueue(db,key,'Shadow cycle update',f'{status}. Review the dashboard.',now,
                    priority=priority,url=self.dashboard_base_url+'/#activity')
    def acquire(self,now,*,scheduled,recovery=False,remaining_budget_usd=None):
        if now.tzinfo is None: raise ValueError('Timezone-aware timestamp required')
        if not scheduled or safety_stopped(self.path) or not eligible(now): return None
        if recovery and (
            remaining_budget_usd is None or Decimal(str(remaining_budget_usd)) <= 0
        ): return None
        require_database_role(self.path,'live')
        if self.handle: return None
        lock=self.path.with_suffix(self.path.suffix+'.cycle.lock')
        fd=os.open(lock,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        self.handle=os.fdopen(fd,'r+')
        try: fcntl.flock(self.handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: self.close(); return None
        claim={'cycle_id':uuid4().hex,'trigger':'scheduled_recovery' if recovery else 'scheduled','started_at':now.isoformat(),'worker_id':f'{os.getpid()}-{uuid4().hex}','recovery_count':0}
        try:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE'); self.schema(db)
                day=now.astimezone(ET).date().isoformat()
                if recovery:
                    prior=db.execute('SELECT status,payload FROM cycle_runs WHERE day=?',(day,)).fetchone()
                    if not prior or prior[0] not in {'FAILED','FAILED_STALLED'}:
                        self.close(); return None
                    prior_payload=json.loads(prior[1])
                    count=int(prior_payload.get('recovery_count',0))
                    if count>=1:
                        self.close(); return None
                    claim.update(recovery_count=count+1,recovery_of=prior_payload.get('cycle_id'))
                    result=db.execute('UPDATE cycle_runs SET status=?,payload=? WHERE day=? AND status=?',('STARTED',json.dumps(claim),day,prior[0]))
                else:
                    result=db.execute('INSERT OR IGNORE INTO cycle_runs VALUES (?,?,?)',(day,'STARTED',json.dumps(claim)))
                if result.rowcount!=1: self.close(); return None
                self.event(db,claim['cycle_id']+'-started','STARTED',now,claim)
            self.cycle_id=claim['cycle_id']; self.trigger=claim['trigger']
            self.official_context=OfficialRunContext(self.cycle_id,self.path,self.trigger,_OFFICIAL_CONTEXT_MARKER)
            return claim
        except BaseException: self.close(); raise
    def owns(self,db,cycle_id):
        if not self.handle or self.handle.closed or cycle_id!=self.cycle_id or safety_stopped(self.path): return False
        row=db.execute("SELECT 1 FROM cycle_runs WHERE status='STARTED' AND json_extract(payload,'$.cycle_id')=?",(cycle_id,)).fetchone()
        return bool(row)
    def finish(self,cycle_id,status,payload,now):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE'); self.schema(db)
            # Failures may be recorded while paused, success may not.
            row=db.execute("SELECT day,payload FROM cycle_runs WHERE status='STARTED' AND json_extract(payload,'$.cycle_id')=?",(cycle_id,)).fetchone()
            if not row or self.cycle_id!=cycle_id or not self.handle or (status=='COMPLETED' and not self.owns(db,cycle_id)): return False
            result={**json.loads(row[1]),**payload,'cycle_id':cycle_id,'status':status,'completed_at':now.isoformat()}
            db.execute('UPDATE cycle_runs SET status=?,payload=? WHERE day=?',(status,json.dumps(result),row[0]))
            self.event(db,cycle_id+'-terminal',status,now,result)
            return True
    def reconcile(self,now):
        changed=[]
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE'); self.schema(db)
            for day,payload in db.execute("SELECT day,payload FROM cycle_runs WHERE status='STARTED'").fetchall():
                p=json.loads(payload)
                stamp=p.get('started_at')
                if not stamp: continue
                started=datetime.fromisoformat(stamp)
                if started.tzinfo is None or started>now or now-started>timedelta(minutes=30):
                    p.update(status='FAILED_STALLED',reason='Attempt did not complete within 30 minutes')
                    db.execute('UPDATE cycle_runs SET status=?,payload=? WHERE day=?',('FAILED_STALLED',json.dumps(p),day))
                    self.event(db,p['cycle_id']+'-terminal','FAILED_STALLED',now,p); changed.append(p['cycle_id'])
            local=now.astimezone(ET)
            if MarketSchedule().classify(now) is MarketSchedule.State.MISSED_WINDOW and not db.execute('SELECT 1 FROM cycle_runs WHERE day=?',(local.date().isoformat(),)).fetchone():
                self.event(db,local.date().isoformat()+'-missed','MISSED_WINDOW',now,{'day':local.date().isoformat()})
        return changed
    def close(self):
        if self.handle: self.handle.close(); self.handle=None
