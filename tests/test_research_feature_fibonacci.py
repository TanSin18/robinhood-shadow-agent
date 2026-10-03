from decimal import Decimal as D
from test_research_feature_structure import bars


def test_directed_levels_both_directions():
    from firm_lab.research_features.fibonacci import directed_levels
    up=directed_levels(D(100),D(120))
    assert up['retracement_0.618']==D('107.640')
    assert up['extension_1.618']==D('132.360')
    assert directed_levels(D(120),D(100))['retracement_0.618']==D('112.360')


def test_close_names_and_anchors_not_visible_early():
    from firm_lab.research_features.fibonacci import fibonacci_features
    from firm_lab.research_features.types import Request
    seq=[5,4,3,1,2,3,4,9,8,7,6]
    req=Request('VTI','2026-09-11','2026-09-11T20:00:00Z')
    early=fibonacci_features({'closes':bars(seq[:10]),'missing_reasons':[]},req)
    assert all(r.value is None for r in early)
    ready=fibonacci_features({'closes':bars(seq),'missing_reasons':[]},req)
    row=next(r for r in ready if r.name=='close_fib_retracement_0.618')
    assert D(row.value)==D('4.056')
    assert row.audit['start']['session']=='2026-09-04'
    assert row.audit['end']['confirmed_session']=='2026-09-11'
    assert row.known_at=='2026-09-11T20:00:00+00:00'
    assert all(r.name.startswith('close_fib_') for r in ready)
    atr=next(r for r in ready if r.name=='close_fib_retracement_0.618_atr_distance')
    assert atr.value is None and atr.missing_reason=='NO_VALIDATED_ATR'


def test_nonpositive_extension_does_not_break_nearest():
    from firm_lab.research_features.fibonacci import fibonacci_features
    from firm_lab.research_features.types import Request
    seq=[50,60,70,100,90,80,70,10,11,12,13]
    rows=fibonacci_features({'closes':bars(seq),'missing_reasons':[]},Request('VTI','2026-09-11','2026-09-11T20:00:00Z'))
    extension=next(r for r in rows if r.name=='close_fib_extension_1.618')
    assert extension.value is None and extension.missing_reason=='NONPOSITIVE_PROJECTED_LEVEL'


def test_structure_definitions_cover_outputs():
    from firm_lab.research_features.registry import definitions
    from firm_lab.research_features.structure import structure_features
    from firm_lab.research_features.fibonacci import fibonacci_features
    from firm_lab.research_features.types import Request
    req=Request('VTI','2026-09-11','2026-09-11T20:00:00Z')
    snap={'closes':bars([5,4,3,1,2,3,4,9,8,7,6]),'missing_reasons':[]}
    registered={d['name'] for d in definitions()}
    assert {r.name for r in structure_features(snap,req)+fibonacci_features(snap,req)} <= registered


def test_cluster_members_are_auditable():
    from firm_lab.research_features.fibonacci import fibonacci_features
    from firm_lab.research_features.types import Request
    rows=fibonacci_features({'closes':bars([5,4,3,1,2,3,4,9,8,7,6]),'missing_reasons':[]},Request('VTI','2026-09-11','2026-09-11T20:00:00Z'))
    cluster=next(r for r in rows if r.name=='close_fib_clusters')
    assert cluster.value['nearest_cluster_distance'] is not None
    assert all('members' in c and 'sma_overlaps' in c and 'structure_overlaps' in c for c in cluster.value['clusters'])


def test_atr_distance_uses_validated_aligned_ohlc_without_changing_close_anchors():
    from firm_lab.research_features.fibonacci import fibonacci_features
    from firm_lab.research_features.types import Request
    close=bars([5,4,3,1,2,3,4,9,8,7,6,6,6,6,6,6])
    ohlc=[dict(b,open=b['value'],close=b['value'],high='20',low='1',volume='100') for b in close]
    snap={'closes':close,'ohlcv':ohlc,'missing_reasons':[]}
    request=Request('VTI','2026-09-16','2026-09-16T20:00:00Z')
    row=next(r for r in fibonacci_features(snap,request) if r.name=='close_fib_retracement_0.618_atr_distance')
    assert row.value is not None
    assert abs(D(row.value)-D('1.944')/19)<D('1e-25')
    snap['ohlcv']=ohlc[:-1]
    assert next(r for r in fibonacci_features(snap,request) if r.name==row.name).value is None
