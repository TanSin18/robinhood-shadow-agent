import json
import sqlite3
import threading
from datetime import datetime, timezone
from http.client import HTTPConnection
import pytest

NOW=datetime(2026,9,28,15,tzinfo=timezone.utc)

def test_idle_browser_connection_does_not_block_other_tabs(tmp_path):
    import socket
    from agents.desk.preview import make_server
    path,writer=database(tmp_path)
    server=make_server(path,port=0,clock=lambda:NOW)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    idle=socket.create_connection(server.server_address,timeout=1)
    # An incomplete browser request occupies the first connection.
    idle.sendall(b'GET / HTTP/1.1\r\n')
    client=HTTPConnection(*server.server_address,timeout=1)
    try:
        client.request('GET','/')
        response=client.getresponse()
        assert response.status==200
        assert b'Preview' in response.read()
    finally:
        idle.close();client.close()
        server.shutdown();server.server_close();thread.join();writer.close()

def database(tmp_path):
    path=tmp_path/'agent.db'
    db=sqlite3.connect(path)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE approval_inbox(id TEXT,status TEXT,issued TEXT,expires TEXT,payload TEXT)')
    payload={'id':'real-record','lane':'A','status':'PENDING','proposal':{'ticker':'VTI','side':'buy','thesis':'Recorded thesis','good_if':'Recorded condition','invalidation':'Recorded exit','quantity':'1','limit_price':'50','account_id':'PRIVATE-ACCOUNT'}}
    db.execute('INSERT INTO approval_inbox VALUES (?,?,?,?,?)',('real-record','PENDING','2026-09-28T14:00:00+00:00','2026-09-28T14:30:00+00:00',json.dumps(payload)))
    db.commit()
    return path,db

def test_expired_card_is_projected_without_updating_database(tmp_path):
    from agents.desk.preview import snapshot
    path,writer=database(tmp_path)
    state=snapshot(path,now=NOW)
    assert state['cards'][0]['status']=='EXPIRED'
    assert state['cards'][0]['expiry_label']=='Expired 10:30 AM ET'
    assert writer.execute('SELECT status FROM approval_inbox').fetchone()[0]=='PENDING'
    assert 'PRIVATE-ACCOUNT' not in json.dumps(state)
    writer.close()

def test_clock_crosses_deadline_without_persisting_expiry(tmp_path):
    from agents.desk.preview import snapshot
    path,writer=database(tmp_path)
    before=snapshot(path,now=datetime(2026,9,28,14,29,tzinfo=timezone.utc))['cards'][0]
    after=snapshot(path,now=datetime(2026,9,28,14,30,tzinfo=timezone.utc))['cards'][0]
    assert before['status']=='PENDING' and not before['actionable']
    assert after['status']=='EXPIRED' and not after['actionable']
    assert writer.execute('SELECT status FROM approval_inbox').fetchone()[0]=='PENDING'
    writer.close()

def test_preview_does_not_import_execution_components():
    import subprocess,sys
    result=subprocess.run([sys.executable,'-B','-c',
        'import sys; import agents.desk.preview; '
        'assert not any(m.startswith(("agents.inbox", "agents.daily_cycle", "brokers", "agents.dashboard_view")) for m in sys.modules)'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr

def test_readonly_connection_denies_writes_and_releases_wal_reader(tmp_path):
    from agents.desk.preview import open_readonly,snapshot
    path,writer=database(tmp_path)
    writer.execute('PRAGMA busy_timeout=0')
    with open_readonly(path) as reader:
        assert reader.execute('PRAGMA query_only').fetchone()[0]==1
        with pytest.raises(sqlite3.DatabaseError): reader.execute('DELETE FROM approval_inbox')
        reader.execute('BEGIN')
        reader.execute('SELECT * FROM approval_inbox').fetchall()
        # A real writer commit succeeds even while the reader holds a WAL snapshot.
        writer.execute("UPDATE approval_inbox SET issued=issued")
        writer.commit()
    for _ in range(10): snapshot(path,now=NOW)
    assert writer.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0]==0
    with pytest.raises(sqlite3.ProgrammingError): reader.execute('SELECT 1')
    writer.close()

def test_preview_serves_real_card_and_refuses_all_posts(tmp_path):
    from agents.desk.preview import make_server
    path,writer=database(tmp_path)
    server=make_server(path,port=0,clock=lambda:NOW)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        for route in ('/','/room','/portfolio','/money','/scoreboard','/controls','/health'):
            c=HTTPConnection('127.0.0.1',server.server_port,timeout=2); c.request('GET',route)
            response=c.getresponse(); body=response.read().decode(); c.close()
            assert response.status==200
            assert 'Preview — view only' in body
            assert '<form' not in body
            assert 'dashboard.js' not in body
            if route=='/':
                assert 'Recorded thesis' in body and 'Expired 10:30 AM ET' in body
                assert 'PRIVATE-ACCOUNT' not in body
        for route in ('/decision','/control','/views','/notifications/test','/tripwire/acknowledge','/anything'):
            c=HTTPConnection('127.0.0.1',server.server_port,timeout=2); c.request('POST',route,'decision=YES')
            response=c.getresponse(); assert response.status==405; response.read(); c.close()
        assert writer.execute('SELECT status FROM approval_inbox').fetchone()[0]=='PENDING'
    finally:
        server.shutdown();server.server_close();thread.join();writer.close()
