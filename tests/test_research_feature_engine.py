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
    def bars(end):
        return [dict(session=f'2026-09-{i:02}',value=str(i),known_at='2026-10-03T20:00:00Z',
                     ref=SourceRef('feature_observations',str(i),'a'*64,'2026-10-03T20:00:00Z')) for i in range(1,end+1)]
    snap={k:[] for k in ('closes','ohlcv','facts','filings','earnings','macro','macro_events','mappings')}
    snap.update(closes=bars(10),reference_closes={'VTI':bars(20)})
    rows=compute(snap,Request('AAPL','2026-09-10','2026-10-03T20:00:00Z'))
    assert next(r for r in rows if r.name=='excess_vti_price_return5').value=='0'


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
