"""Database identity belongs to SQLite, not to its filename."""
import json
import sqlite3
from datetime import datetime,timezone
from pathlib import Path

class DatabaseRoleError(ValueError): pass

def database_role(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='database_role'").fetchone(): return None
    row=db.execute('SELECT role FROM database_role WHERE singleton=1').fetchone()
    return row[0] if row else None

def require_database_role(path,role):
    roles={'live','fixture','whatif','replay'}
    if role not in roles: raise DatabaseRoleError('Unknown database role')
    path=Path(path).resolve(); path.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path,timeout=15) as db:
        db.execute('BEGIN IMMEDIATE')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        evidence=set(); ambiguous=False
        for table,column in [('run_states','payload_json'),('daily_values','payload_json'),('paper_accounts','payload'),('cycle_runs','payload'),('approval_inbox','payload')]:
            if table not in tables: continue
            for row in db.execute(f'SELECT {column} FROM {table}'):
                value=json.loads(row[0]); mode=value.get('data_mode')
                if mode in {'fixture','whatif','replay'}: evidence.add(mode)
                elif mode=='live_readonly': evidence.add('live')
                elif table=='paper_accounts' and (value.get('positions') or value.get('fills')): ambiguous=True
                elif table in {'cycle_runs','approval_inbox'}: ambiguous=True
        existing=database_role(db)
        if existing and existing!=role or evidence-{role} or (ambiguous and not existing):
            raise DatabaseRoleError('Database contains incompatible or ambiguous activity; preserve it for review')
        db.execute("CREATE TABLE IF NOT EXISTS database_role(singleton INTEGER PRIMARY KEY CHECK(singleton=1),role TEXT NOT NULL CHECK(role IN ('live','fixture','whatif','replay')),established_at TEXT NOT NULL)")
        db.execute('INSERT OR IGNORE INTO database_role VALUES (1,?,?)',(role,datetime.now(timezone.utc).isoformat()))
