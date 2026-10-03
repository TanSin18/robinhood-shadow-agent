import json
import sqlite3
from dataclasses import replace
import pytest
from test_research_feature_contract import research_db,result


def recorded(tmp_path):
    from firm_lab.research_features.store import FeatureStore
    from firm_lab.research_features.types import Request
    db,official=research_db(tmp_path)
    req=Request('VTI','2026-09-30','2026-10-03T20:00:00Z')
    with FeatureStore(db,official) as s:
        run=s.start_run(req)
        s.append(result(audit={'knowledge_cutoff':req.knowledge_cutoff}))
        s.finish_run(run,{'instrument':'VTI','session':req.as_of_session,'knowledge_cutoff':req.knowledge_cutoff,'calculation_hash':'b'*64})
    return db


def test_warning_and_missing_data_visible():
    from agents.desk.feature_explorer import render_features
    html=render_features({'rows':[],'missing_reason':'NO_VALIDATED_OHLC'})
    assert 'RESEARCH FEATURES ONLY — NOT A TRADE SIGNAL' in html
    assert 'NO_VALIDATED_OHLC' in html


def test_close_anchor_visual_audit_has_prices_dates_and_confirmations():
    from dataclasses import asdict
    from agents.desk.feature_explorer import render_features
    from firm_lab.research_features.fibonacci import fibonacci_features
    from firm_lab.research_features.types import Request
    from test_research_feature_structure import bars
    rows=fibonacci_features({'closes':bars([5,4,3,1,2,3,4,9,8,7,6]),'missing_reasons':[]},
        Request('VTI','2026-09-11','2026-09-11T20:00:00Z'))
    html=render_features({'rows':[asdict(r) for r in rows]})
    assert '<svg' in html and 'Stored level values' in html
    assert 'Start anchor' in html and 'End anchor' in html and 'Confirmed session' in html
    assert '2026-09-04' in html and '2026-09-11' in html


def test_read_only_projection_filters_cutoff_and_escapes_provenance(tmp_path):
    from firm_lab.research_features.view import feature_view
    from agents.desk.feature_explorer import render_features
    db=recorded(tmp_path)
    before=db.read_bytes()
    with sqlite3.connect(db) as c:
        state=feature_view(c)
        assert len(state['rows'])==1
        assert feature_view(c,{'instrument':'VTI','session':'2026-09-30','known_by':'2026-09-30T20:00:00Z'})['rows']==[]
        with pytest.raises(sqlite3.OperationalError):
            c.execute('CREATE TABLE attempted_write(id)')
    state['rows'][0]['audit']['untrusted']='<script>alert(1)</script>'
    html=render_features(state)
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'Known at' in html and 'Source references' in html and 'sma20_v1' in html
    assert 'Retrospective' in html and '<details' in html
    assert 'method="get"' in html and 'method="post"' not in html
    assert db.read_bytes()==before


def test_unfinished_or_malformed_results_not_available(tmp_path):
    from firm_lab.research_features.view import feature_view
    db=recorded(tmp_path)
    with sqlite3.connect(db) as c:
        payload=json.loads(c.execute('SELECT payload FROM research_feature_results').fetchone()[0])
        payload['name']='uncited'; payload['refs']=[]
        c.execute('INSERT INTO research_feature_results VALUES(?,?,?)',('bad',json.dumps(payload),'2026-10-03T21:00:00Z'))
        c.commit()
        state=feature_view(c)
    assert len(state['rows'])==1 and state['invalid_rows']==1


def test_page_integrates_feature_view_without_generator(tmp_path,monkeypatch):
    from firm_lab import view
    from agents.desk.firm_lab_page import render
    import firm_lab.research_features.engine as engine
    monkeypatch.setattr(engine,'compute',lambda *a:pytest.fail('GET cannot generate'))
    db=recorded(tmp_path)
    before=db.read_bytes()
    html=render({'firm_lab':view.load(path=db)})
    assert 'Research feature explorer' in html and 'sma20' in html
    assert db.read_bytes()==before


def test_preview_get_filters_work_and_post_stays_disabled(tmp_path,monkeypatch):
    import threading
    from http.client import HTTPConnection
    from agents.desk.preview import make_server
    from firm_lab import view
    from test_desk_preview import database,NOW
    research=recorded(tmp_path)
    monkeypatch.setattr(view,'default_path',lambda _:research)
    official,writer=database(tmp_path)
    before=research.read_bytes()
    server=make_server(official,port=0,clock=lambda:NOW)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    client=HTTPConnection(*server.server_address,timeout=5)
    try:
        client.request('GET','/firm-lab?instrument=VTI&session=2026-09-30&known_by=2026-09-30T20%3A00%3A00Z')
        response=client.getresponse();page=response.read().decode()
        assert response.status==200 and 'NO_COMPLETED_RUN_AT_CUTOFF' in page
        assert "form-action 'self'" in response.headers['Content-Security-Policy']
        client.request('POST','/firm-lab',body=b'write=1')
        response=client.getresponse();response.read()
        assert response.status==405
        assert research.read_bytes()==before
    finally:
        client.close();server.shutdown();server.server_close();thread.join();writer.close()
