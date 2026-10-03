import socket
from dataclasses import replace


def test_engine_registry_coverage_and_no_network(monkeypatch):
    from firm_lab.research_features.engine import compute
    from firm_lab.research_features.registry import definitions
    from firm_lab.research_features.types import Request,content_hash
    def forbidden(*args,**kwargs):
        raise AssertionError('Network forbidden')
    monkeypatch.setattr(socket,'socket',forbidden)
    request=Request('VTI','2026-09-30','2026-10-03T20:00:00Z')
    snap={k:[] for k in ('closes','ohlcv','facts','filings','earnings','macro','mappings','missing_reasons')}
    a=compute(snap,request)
    b=compute(dict(reversed(list(snap.items()))),request)
    assert [content_hash(r) for r in a]==[content_hash(r) for r in b]
    assert {r.name for r in a}=={d['name'] for d in definitions()}
    assert all(r.value is None for r in a)


def test_engine_blocks_future_bar_input():
    from firm_lab.research_features.engine import compute
    from firm_lab.research_features.types import Request,SourceRef
    bar=dict(session='2026-09-30',value='100',known_at='2026-10-03T20:00:00+00:00',
             ref=SourceRef('feature_observations','1','a'*64,'2026-10-03T20:00:00+00:00'))
    snap={k:[] for k in ('closes','ohlcv','facts','filings','earnings','macro','mappings','missing_reasons')}
    snap['closes']=[bar]*200
    rows=compute(snap,Request('VTI','2026-09-30','2026-09-30T20:00:00Z'))
    assert all(r.value is None for r in rows)


def test_reference_history_after_session_cannot_contaminate_returns():
    from firm_lab.research_features.engine import compute
    from firm_lab.research_features.types import Request,SourceRef
    from firm_lab.research_features.calendar import session_dates
    days=session_dates('2026-08-27','2026-09-30')
    def bars(end):
        return [dict(session=day,value=str(i+1),known_at='2026-10-03T20:00:00Z',
                     ref=SourceRef('feature_observations',str(i),'a'*64,'2026-10-03T20:00:00Z')) for i,day in enumerate(days[:end])]
    snap={k:[] for k in ('closes','ohlcv','facts','filings','earnings','macro','macro_events','mappings')}
    snap.update(closes=bars(10),reference_closes={'VTI':bars(20)})
    rows=compute(snap,Request('AAPL',days[9],'2026-10-03T20:00:00Z'))
    assert next(r for r in rows if r.name=='excess_vti_price_return5').value=='0'


def test_engine_rejects_non_session_gapped_or_stale_bars():
    import pytest
    from firm_lab.research_features.engine import compute
    from firm_lab.research_features.types import Request,SourceRef
    from firm_lab.research_features.calendar import session_dates
    def bars(days):
        return [dict(session=day,value='10',known_at='2026-10-03T20:00:00Z',
                ref=SourceRef('feature_observations',day,'a'*64,'2026-10-03T20:00:00Z')) for day in days]
    days=list(session_dates('2026-08-01','2026-09-30'))
    for dates in (days[:-1],days[:10]+days[11:],days+['2026-09-27']):
        for key in ('closes','ohlcv','reference_closes'):
            snapshot={k:[] for k in ('closes','ohlcv','facts','filings','earnings','macro','mappings')}
            snapshot[key]={'VTI':bars(dates)} if key=='reference_closes' else bars(dates)
            with pytest.raises(ValueError,match='INVALID_SESSION_WINDOW'):
                compute(snapshot,Request('VTI','2026-09-30','2026-10-03T20:00:00Z'))


def test_no_forbidden_imports_in_research_package():
    import ast
    from pathlib import Path
    forbidden={'agents','broker','broker_proxy','openai','requests','httpx','urllib','socket'}
    for file in Path('firm_lab/research_features').glob('*.py'):
        for node in ast.walk(ast.parse(file.read_text())):
            modules=[n.name for n in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
            assert not {m.split('.')[0] for m in modules}&forbidden, file


def test_catalog_covers_each_versioned_result():
    from pathlib import Path
    from firm_lab.research_features.registry import definitions
    catalog=Path('docs/firm_lab/feature_catalog.md').read_text()
    for d in definitions():
        assert d['name'] in catalog and d['version'] in catalog
