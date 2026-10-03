import json
import sqlite3
import pytest
from firm_lab.errors import IsolationError
from firm_lab_collectors.transport import Response
from test_macro_parsers import NOW, FED, PCE, reply


def test_manual_ingest_records_rejections_and_never_writes_official(tmp_path):
    from firm_lab_collectors.macro_ingest import ingest_responses
    official=tmp_path/'official'/'agent.db'; official.parent.mkdir(); official.write_bytes(b'untouched')
    path=tmp_path/'research'/'firm.db'
    rows=[('fed',reply('fed',FED)),('cpi',Response(403,b'denied','https://www.bls.gov/news.release/cpi.htm',NOW.isoformat()))]
    result=ingest_responses(rows,path,official_db=official,now=NOW)
    assert result['fed']['accepted']==2 and result['cpi']['rejected']==1
    assert result['cpi']['reasons']=={'HTTP_403':1}
    assert official.read_bytes()==b'untouched'
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM macro_observations').fetchone()[0]==2
        assert db.execute('SELECT count(*) FROM macro_ingest_receipts').fetchone()[0]==2
        assert db.execute("SELECT status FROM data_capabilities WHERE capability='fed_policy_data'").fetchone()[0]=='AVAILABLE'
        assert db.execute("SELECT status FROM data_capabilities WHERE capability='cpi'").fetchone()[0]=='UNAVAILABLE'
        assert db.execute("SELECT status FROM data_capabilities WHERE capability='macro_regime'").fetchone()[0]=='NOT_STARTED'


def test_duplicate_ingest_and_realistic_republication_append(tmp_path):
    from firm_lab_collectors.macro_ingest import ingest_responses
    path=tmp_path/'research'/'firm.db'; official=tmp_path/'official'/'agent.db'
    a=ingest_responses([('pce',reply('pce',PCE))],path,official_db=official,now=NOW)
    b=ingest_responses([('pce',reply('pce',PCE))],path,official_db=official,now=NOW)
    assert a['pce']['accepted']==4 and b['pce']['duplicates']==4
    revised=PCE.replace('September 30, 2026','October 1, 2026').replace('<td>0.3</td>','<td>0.4</td>')
    c=ingest_responses([('pce',reply('pce',revised))],path,official_db=official,now=NOW)
    assert c['pce']['revisions']==4
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM macro_observations').fetchone()[0]==8
        assert db.execute('SELECT max(revision) FROM macro_events').fetchone()[0]==1


def test_ingest_refuses_official_path_before_any_write(tmp_path):
    from firm_lab_collectors.macro_ingest import ingest_responses
    path=tmp_path/'agent.db'; path.write_bytes(b'unchanged')
    with pytest.raises(IsolationError):
        ingest_responses([],path,official_db=path,now=NOW)
    assert path.read_bytes()==b'unchanged'


def test_cached_capture_hash_and_path_cannot_be_substituted(tmp_path):
    from firm_lab_collectors.macro_ingest import load_capture
    import hashlib
    raw=tmp_path/'x.raw'; raw.write_bytes(b'release')
    manifest=[dict(file='x.raw',family='fed',status=200,url='https://www.federalreserve.gov/test',
                   fetched_at=NOW.isoformat(),sha256=hashlib.sha256(b'release').hexdigest())]
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    assert load_capture(tmp_path)[0][1].body==b'release'
    raw.write_bytes(b'changed')
    with pytest.raises(Exception,match='CAPTURE_HASH_MISMATCH'): load_capture(tmp_path)
    manifest[0]['file']='../outside'
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(Exception,match='CAPTURE_PATH_REFUSED'): load_capture(tmp_path)


def test_release_is_atomic_if_event_write_fails(tmp_path,monkeypatch):
    from firm_lab.macro import MacroStore
    from firm_lab.errors import FirmLabError
    from firm_lab_collectors.macro_ingest import ingest_responses
    def fail(*a,**k): raise FirmLabError('TEST_EVENT_FAILURE')
    monkeypatch.setattr(MacroStore,'add_event',fail)
    path=tmp_path/'research'/'firm.db'
    result=ingest_responses([('fed',reply('fed',FED))],path,official_db=tmp_path/'official'/'agent.db',now=NOW)
    assert result['fed']['accepted']==0
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM macro_observations').fetchone()[0]==0


def test_cached_ingestion_does_not_claim_network_requests(tmp_path):
    from firm_lab_collectors.macro_ingest import ingest_responses
    result=ingest_responses([('fed',reply('fed',FED))],tmp_path/'research'/'firm.db',
                            official_db=tmp_path/'official'/'agent.db',now=NOW)
    assert result['fed']['requests']==0
    assert result['fed']['documents']==1


def test_other_family_or_empty_ingestion_cannot_clear_failed_refresh(tmp_path):
    from firm_lab_collectors.macro_ingest import ingest_responses
    path=tmp_path/'research'/'firm.db'; official=tmp_path/'official'/'agent.db'
    def ingest(rows): return ingest_responses(rows,path,official_db=official,now=NOW)
    ingest([('fed',reply('fed',FED))])
    ingest([('fed',Response(403,b'denied','https://www.federalreserve.gov/test',NOW.isoformat()))])
    with sqlite3.connect(path) as db:
        before=db.execute("SELECT status,detail,updated_at FROM data_capabilities WHERE capability='fed_policy_data'").fetchone()
    assert before[0]=='PARTIAL_EXISTING'
    ingest([('pce',reply('pce',PCE))]); ingest([])
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT status,detail,updated_at FROM data_capabilities WHERE capability='fed_policy_data'").fetchone()==before


def test_bad_treasury_number_has_receipt_and_does_not_abort_next_source(tmp_path):
    from firm_lab_collectors.macro_ingest import ingest_responses
    bad=Response(200,b'Date,2 Yr,10 Yr\n10/02/2026,N/A,4.2\n','https://home.treasury.gov/test.csv',NOW.isoformat())
    result=ingest_responses([('treasury',bad),('fed',reply('fed',FED))],tmp_path/'research'/'firm.db',official_db=tmp_path/'official'/'agent.db',now=NOW)
    assert result['treasury']['rejected']==1
    assert result['treasury']['reasons']=={'TREASURY_VALUE_INVALID':1}
    assert result['fed']['accepted']==2
