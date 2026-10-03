import sqlite3
from firm_lab.view import load
from agents.desk.firm_lab_page import render
from firm_lab_collectors.macro_ingest import ingest_responses
from test_macro_parsers import NOW, FED, reply


def test_macro_ui_is_read_only_factual_and_exposes_provenance(tmp_path):
    path=tmp_path/'research'/'firm.db'; official=tmp_path/'official'/'agent.db'
    from dataclasses import replace
    response=replace(reply('fed',FED),fetched_at='2026-09-17T12:00:00+00:00')
    ingest_responses([('fed',response)],path,official_db=official,now=NOW)
    before=path.read_bytes()
    state=load(official,path)
    html=render({'firm_lab':state})
    assert 'Macro / Regime Readiness' in html
    assert 'FACTUAL MACRO DATA ONLY — NO MACRO TRADING SIGNAL' in html
    assert 'macro_regime = NOT_STARTED' in html and 'NO TRADES' in html
    assert 'Known locally at' in html and 'Publication time' in html
    assert 'Local revision 0' in html and 'federalreserve.gov' in html
    assert len(state['macro']['latest'])==2
    assert path.read_bytes()==before
    with sqlite3.connect(path) as db:
        assert not any(r[0] in ('orders','fills') for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'"))


def test_macro_absent_schema_reports_missing_not_green(tmp_path):
    from firm_lab.store import FirmLabStore
    path=tmp_path/'research'/'firm.db'; official=tmp_path/'official'/'agent.db'
    FirmLabStore(path,official_db=official)
    state=load(official,path)
    assert state['macro']['latest']==[]
    html=render({'firm_lab':state})
    assert 'No validated observation stored' in html
