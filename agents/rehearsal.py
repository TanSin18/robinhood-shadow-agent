"""Operator-only diagnostic. No service installation, claims, cards or fills.

The official database is opened mode=ro and closed before broker collection.
Paper holdings are an in-memory snapshot. Only diagnostic/health records may
be persisted in a newly created, private what-if directory.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sqlite3
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from data.connections import connection
from data.database_role import database_role, require_database_role
from data.store import SQLiteStore
from agents.safety_events import safety_stopped

PROTECTED = frozenset({'cycle_runs', 'approval_inbox', 'paper_accounts', 'orders',
    'fills', 'cards', 'daily_values', 'lessons', 'decision_records', 'strategy_versions',
    'strategy_changes', 'improvement_proposals', 'weekly_reports'})


class RehearsalBlocked(ValueError):
    pass


@contextmanager
def official_read(path):
    db = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True, timeout=1)
    try:
        db.execute('PRAGMA query_only=ON')
        db.set_authorizer(lambda action, *_: sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_ATTACH else sqlite3.SQLITE_OK)
        db.execute('BEGIN')
        yield db
    finally:
        db.close()


def official_digest(path):
    """Compare business records, not maintenance timestamps or WAL bytes."""
    with official_read(path) as db:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        rows={t:db.execute(f'SELECT * FROM {t} ORDER BY rowid').fetchall() for t in sorted(PROTECTED & tables)}
    return hashlib.sha256(json.dumps(rows,sort_keys=True,default=str).encode()).hexdigest()


class DiagnosticStore(SQLiteStore):
    def __init__(self, path, parent):
        self.parent = parent
        super().__init__(path)

    def append_json(self, table, payload):
        if table not in {'run_states','local_traces','api_costs','validation_failures'}:
            raise RehearsalBlocked('REHEARSAL_WRITE_BLOCKED')
        payload = {**payload, 'data_mode':'whatif', 'parent_official_run_id':self.parent}
        payload.pop('account_last4', None)
        return super().append_json(table,payload)


class RehearsalInbox:
    def __init__(self, path, official, config, parent, states):
        self.path, self.official_path, self.config = Path(path), Path(official), config
        self.parent_official_run_id = parent
        self._states = copy.deepcopy(states)
        self.store = DiagnosticStore(path, parent)

    def assert_isolated(self):
        if self.path.resolve() == self.official_path.resolve():
            raise RehearsalBlocked('OFFICIAL_DATABASE_FORBIDDEN')
        with connection(self.path) as db:
            if database_role(db) != 'whatif':
                raise RehearsalBlocked('REHEARSAL_ROLE_REQUIRED')
        if safety_stopped(self.official_path) or safety_stopped(self.path):
            raise RehearsalBlocked('OFFICIAL_SAFETY_STOP')

    def connect(self):
        return connection(self.path)

    def state(self, lane, track, db=None):
        return copy.deepcopy(self._states[(lane,track)])

    def _has_track(self, lane, track):
        return (lane,track) in self._states

    def _context(self, *args, **kwargs):
        from agents.inbox import PaperInbox
        return PaperInbox._context(self,*args,**kwargs)

    def mark_accounts(self, quotes, now, data_mode):
        # Mark the in-memory copy only; never settle cash, fill, or value a ledger.
        for state in self._states.values():
            missing=[]
            for ticker in state['positions']:
                q=quotes.get(ticker)
                if q is None or q.halted or not 0 <= (now-q.timestamp).total_seconds() <= self.config.risk.max_quote_age_seconds:
                    missing.append(ticker)
                else:
                    state.setdefault('marks',{})[ticker]=str(q.bid)
            state['missing_marks']=missing

    def settle_expirations(self, *args, **kwargs):
        from agents.inbox import PAPER_TRACKS
        if any(self.state('B',t)['positions'] for t in PAPER_TRACKS if self._has_track('B',t)):
            raise RehearsalBlocked('OPTIONS_HOLDINGS_REHEARSAL_NOT_IMPLEMENTED')

    def issue(self, *args, **kwargs):
        raise RehearsalBlocked('REHEARSAL_WRITE_BLOCKED')

    def decide(self, *args, **kwargs):
        raise RehearsalBlocked('REHEARSAL_WRITE_BLOCKED')

    def evaluate_proposal(self, proposal, quote, vol, vol_as_of, now, **kwargs):
        from agents.inbox import PaperInbox
        from risk.engine import RiskEngine
        self.assert_isolated()
        lane='B' if proposal.asset_class=='option' else 'A'
        context=PaperInbox._context(self, self.state(lane,'agent_alone'), quote, vol, vol_as_of, now)
        verdict=RiskEngine(self.config.risk).evaluate(proposal,context)
        return {'status':'REHEARSAL_RISK_PASSED' if verdict.allowed else 'RISK_BLOCKED',
                'reasons':[r.value for r in verdict.reasons]}


def prepare(official, output_dir, config):
    official, output_dir = Path(official).resolve(), Path(output_dir).absolute()
    if output_dir.exists() or output_dir.is_symlink():
        raise RehearsalBlocked('FRESH_OUTPUT_DIRECTORY_REQUIRED')
    if safety_stopped(official):
        raise RehearsalBlocked('OFFICIAL_SAFETY_STOP')
    with official_read(official) as source:
        if database_role(source) != 'live':
            raise RehearsalBlocked('OFFICIAL_PARENT_REQUIRED')
        records=[json.loads(r[0]) for r in source.execute('SELECT payload_json FROM run_states ORDER BY id DESC')]
        parent=next((r.get('cycle_id') for r in records if r.get('status')=='COMPLETED' and r.get('data_mode')=='live_readonly' and r.get('cycle_id')),None)
        if not parent: raise RehearsalBlocked('OFFICIAL_PARENT_REQUIRED')
        states={(lane,track):json.loads(payload) for lane,track,payload in source.execute('SELECT lane,track,payload FROM paper_accounts')}
        legacy={(l,t) for l in ('A','B') for t in ('agent_alone','with_approvals')}
        if not legacy <= set(states) or set(states)-{(l,t) for l in ('A','B') for t in ('agent_alone','with_approvals','deterministic_no_ai')}:
            raise RehearsalBlocked('PAPER_SNAPSHOT_INCOMPLETE')
        # Health-only seeds preserve comparison against the last verified broker
        # snapshot and the shortest accepted order-history lookback. No orders
        # are returned to the agent cycle or the public report.
        seeds=[]
        for table in ('broker_state_snapshots','order_monitor_checkpoint'):
            schema=source.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
            if schema:
                rows=source.execute('SELECT * FROM '+table+(' WHERE status=\'VERIFIED\' ORDER BY id DESC LIMIT 1' if table=='broker_state_snapshots' else '')).fetchall()
                seeds.append((schema[0], table, rows))
    output_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
    path=output_dir/'rehearsal.db'
    path.touch(mode=0o600,exist_ok=False)
    require_database_role(path,'whatif')
    inbox=RehearsalInbox(path,official,config,parent,states)
    with connection(path) as db:
        for schema, table, rows in seeds:
            db.execute(schema)
            for row in rows: db.execute(f'INSERT INTO {table} VALUES ({",".join("?" for _ in row)})',row)
        db.execute('CREATE TABLE cycle_runs (day TEXT PRIMARY KEY,status TEXT,payload TEXT)')
        db.execute('CREATE TABLE approval_inbox (id TEXT PRIMARY KEY,status TEXT,issued TEXT,expires TEXT,payload TEXT)')
        db.execute('CREATE TABLE paper_accounts (lane TEXT,track TEXT,payload TEXT)')
        db.execute('CREATE TABLE weekly_reports (week TEXT,payload TEXT)')
        for table in sorted(PROTECTED):
            for operation in ('INSERT','UPDATE','DELETE'):
                db.execute(f"CREATE TRIGGER deny_{table}_{operation} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'REHEARSAL_WRITE_BLOCKED'); END")
    inbox.assert_isolated()
    return inbox


def public_report(result):
    allowed=('status','data_mode','trigger','parent_official_run_id','cycle_id',
             'quote_count','volatility_count','market_open','api_cost_estimate_usd',
             'agents','ai_gate','error_type','official_records_unchanged','stages',
             'quote_freshness','risk_proposals_evaluated','source_hash_count','elapsed_seconds','error_location','diagnostic_noncompliant','cap_waiver','uncertain_model_calls')
    report={k:result[k] for k in allowed if k in result}
    report.update(real_orders='blocked',cards_created=0,fills_created=0,
                  scheduled_proof=False,news='disabled',cost_basis=result.get('cost_basis','estimated_api_equivalent'),
                  model_execution='not proven unless a model stage is recorded')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--official-database',required=True)
    parser.add_argument('--config',required=True)
    parser.add_argument('--output-dir',required=True)
    transport=parser.add_mutually_exclusive_group()
    transport.add_argument('--operator-diagnostic-cap-waiver',action='store_true',help='Explicit operator exception for this noncompliant diagnostic only')
    transport.add_argument('--registered-api',action='store_true',help='Registered models and token caps; requires separate API access and matching config')
    args=parser.parse_args()
    os.umask(0o077)
    from config.loader import load_config
    from agents.daily_cycle import run_cycle
    from agents.market_reader import LiveReader
    config=load_config(args.config)
    config.validate_runtime_ready()
    before=official_digest(args.official_database)
    inbox=prepare(args.official_database,args.output_dir,config)
    reader=None
    bridge=None
    started=datetime.now(timezone.utc)
    class NoUncheckedModel:
        def run(self,*args,**kwargs):
            raise RehearsalBlocked('REHEARSAL_MODEL_CAP_NOT_CERTIFIED')
    try:
        if args.registered_api:
            from agents.bounded_inference import configured_bridge
            bridge=configured_bridge(inbox.path,config)
        print(json.dumps({'stage':'live_readonly_collection','status':'STARTED'}),flush=True)
        reader=LiveReader(inbox.path,config)
        # Log method names only. Never arguments, raw responses or account data.
        call=reader.gateway.call
        def progress(tool, arguments):
            print(json.dumps({'read_method':tool}),flush=True)
            return call(tool,arguments)
        reader.gateway.call=progress
        bridge=bridge or NoUncheckedModel()
        if args.operator_diagnostic_cap_waiver:
            from agents.codex_bridge import CodexBridge
            bridge=CodexBridge(inbox.path,limit=Decimal('Infinity'))
            original_run=bridge.run
            def model_progress(model,*arguments,**kwargs):
                print(json.dumps({'model_stage':'STARTED','model':model}),flush=True)
                response=original_run(model,*arguments,**kwargs)
                print(json.dumps({'model_stage':'COMPLETED','model':model}),flush=True)
                return response
            bridge.run=model_progress
        result=run_cycle(inbox,config,bridge,started,data_mode='whatif',reader=reader,
                         diagnostic_cap_waiver=args.operator_diagnostic_cap_waiver)
    except Exception as error:
        result={'status':'HOLD_OPERATIONAL','error_type':type(error).__name__,'data_mode':'whatif',
                'parent_official_run_id':inbox.parent_official_run_id,
                'error_location':[{'module':Path(f.filename).name,'line':f.lineno,'function':f.name}
                                  for f in traceback.extract_tb(error.__traceback__)]}
        inbox.store.append_json('run_states',result)
    finally:
        if reader: reader.close()
        if args.registered_api and bridge: bridge.close()
    if args.registered_api and bridge:
        result.update(bridge.cost_report())
    result['official_records_unchanged']=before==official_digest(args.official_database)
    result['elapsed_seconds']=round((datetime.now(timezone.utc)-started).total_seconds(),2)
    if not result['official_records_unchanged']: result['status']='ISOLATION_VERIFICATION_FAILED'
    report=public_report(result)
    (inbox.path.parent/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if result['status']=='COMPLETED' and result['official_records_unchanged'] else 2


if __name__=='__main__':
    # Keep the inbox class identical to the one run_cycle imports for its guard.
    from agents.rehearsal import main as canonical_main
    raise SystemExit(canonical_main())
