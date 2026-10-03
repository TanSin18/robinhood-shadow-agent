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


def test_manual_cli_reads_and_persists_sector_evidence(tmp_path,capsys):
    from firm_lab.research_features.store import FeatureStore
    from firm_lab.research_features.cli import main
    from firm_lab.research_features.sector import load_sector_context,current_mappings
    from firm_lab.research_features.types import Request,content_hash
    from test_research_feature_contract import research_db
    db,official=research_db(tmp_path)
    record=dict(kind='ETF_MEMBERSHIP',members=['XLK','XLY'],version='test-v1',
        effective_from='2026-09-01',effective_to=None,known_at='2026-10-05T19:00:00Z',source_urls=['https://www.ssga.com/'])
    record['content_hash']=content_hash(record)
    with FeatureStore(db,official) as store:
        store.register_mapping(record)
    with sqlite3.connect(db) as conn:
        context=load_sector_context(conn,Request('MSFT','2026-10-05','2026-10-05T20:00:00Z'))
    assert context['sector_membership_record']['members']==['XLK','XLY']
    assert main(['--database',str(db),'--instrument','MSFT','--session','2026-10-05','--known-by','2026-10-05T20:00:00Z','--write'])==0
    capsys.readouterr()
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT count(*) FROM research_sector_mappings WHERE id=?',(current_mappings()[0]['content_hash'],)).fetchone()[0]==1


def test_default_comparator_set_is_versioned_not_historical(tmp_path):
    from firm_lab.research_features.sector import load_sector_context
    from firm_lab.research_features.types import Request
    from test_research_feature_contract import research_db
    db,_=research_db(tmp_path)
    with sqlite3.connect(db) as conn:
        current=load_sector_context(conn,Request('MSFT','2026-10-05','2026-10-05T20:00:00Z'))
        past=load_sector_context(conn,Request('MSFT','2026-09-30','2026-10-05T20:00:00Z'))
    assert current['sector_membership_record']['members']==['XLK','XLY','XLC']
    assert past['sector_membership_record'] is None
