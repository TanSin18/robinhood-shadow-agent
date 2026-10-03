import hashlib
import json
import sqlite3
import pytest


def test_cli_requires_temporal_mode():
    from firm_lab.research_features.cli import main
    with pytest.raises(SystemExit) as e:
        main(['--database','/not-opened.db','--instrument','VTI'])
    assert e.value.code==2


def test_dry_run_byte_unchanged_and_write_idempotent(tmp_path,capsys):
    from firm_lab.store import FirmLabStore
    from firm_lab.research_features.cli import main
    db=tmp_path/'research'/'firm.db'
    FirmLabStore(db,official_db=tmp_path/'official'/'agent.db')
    args=['--database',str(db),'--instrument','VTI','--session','2026-09-30','--known-by','2026-10-03T20:00:00Z']
    before=hashlib.sha256(db.read_bytes()).hexdigest()
    assert main(args)==0
    receipt=json.loads(capsys.readouterr().out)
    assert receipt['mode']=='DRY_RUN' and receipt['available']==0
    assert hashlib.sha256(db.read_bytes()).hexdigest()==before
    assert main(args+['--write'])==0
    capsys.readouterr()
    with sqlite3.connect(db) as c:
        n=c.execute('SELECT count(*) FROM research_feature_results').fetchone()[0]
    assert main(args+['--write'])==0
    receipt=json.loads(capsys.readouterr().out)
    assert receipt['duplicates']==n and receipt['inserted']==0


def test_cli_refuses_official_schema(tmp_path):
    from firm_lab.research_features.cli import main
    db=tmp_path/'trading.db'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE cycle_runs(day,status)')
    before=db.read_bytes()
    assert main(['--database',str(db),'--instrument','VTI','--as-of','2026-09-30','--write'])==2
    assert db.read_bytes()==before
