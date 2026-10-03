from decimal import Decimal as D
import pytest


def test_mapping_never_backdates():
    from firm_lab.research_features.sector import mapping_at
    row=dict(instrument='AAPL',known_at='2026-10-03T20:00:00Z',effective_from='2026-10-03',effective_to=None,sector='technology',etf='XLK',version='internal-v1')
    assert mapping_at([row],'AAPL','2026-09-30T20:00:00Z','2026-09-30') is None
    assert mapping_at([row],'AAPL','2026-10-04T20:00:00Z','2026-09-30') is None
    assert mapping_at([row],'AAPL','2026-10-04T20:00:00Z','2026-10-04')['etf']=='XLK'


def test_aligned_relative_returns_and_missing_reference():
    from firm_lab.research_features.sector import relative_return
    a=[{'session':str(i),'value':str(100+i)} for i in range(6)]
    b=[{'session':str(i),'value':'100'} for i in range(6)]
    assert relative_return(a,b,5)==D('.05')
    assert relative_return(a,b[:-1],5) is None
    assert relative_return(a,[],5) is None


def test_fixed_set_ties_and_membership_change():
    from firm_lab.research_features.sector import leadership
    assert leadership({'XLK':D('.1'),'XLY':D('.1'),'XLC':D(0)},('XLK','XLY','XLC'))=={'XLK':D('1.5'),'XLY':D('1.5'),'XLC':D(3)}
    assert leadership({'XLK':D('.1')},('XLK','XLY','XLC')) is None


def test_missing_mapping_and_breadth_do_not_imply_zero():
    from firm_lab.research_features.sector import sector_features
    from firm_lab.research_features.types import Request
    rows=sector_features({'closes':[],'mappings':[],'missing_reasons':[]},Request('VTI','2026-09-30','2026-10-03T20:00:00Z'))
    assert rows and all(r.value is None for r in rows)
    assert any(r.missing_reason=='NO_POINT_IN_TIME_CONSTITUENTS' for r in rows)


def test_current_mapping_is_versioned_and_not_historical():
    from firm_lab.research_features.sector import current_mappings, mapping_at
    rows=current_mappings()
    assert mapping_at(rows,'MSFT','2026-09-30T20:00:00Z','2026-09-30') is None
    current=mapping_at(rows,'MSFT','2026-10-05T20:00:00Z','2026-10-05')
    assert current['etf']=='XLK' and current['source_urls'] and current['content_hash']
    assert mapping_at(rows,'VTI','2026-10-05T20:00:00Z','2026-10-05') is None


def test_all_proposed_current_issuer_mappings_have_dated_evidence():
    from firm_lab.research_features.sector import current_mappings,mapping_at
    rows=current_mappings()
    for symbol,etf in {'AAPL':'XLK','MSFT':'XLK','NVDA':'XLK','AMZN':'XLY','GOOGL':'XLC','META':'XLC'}.items():
        mapped=mapping_at(rows,symbol,'2026-10-05T20:00:00Z','2026-10-05')
        assert mapped and mapped['etf']==etf and mapped['evidence'] and len(mapped['source_urls'])==2
        assert mapping_at(rows,symbol,'2026-10-05T20:00:00Z','2026-09-30') is None


def test_leadership_carries_every_competitor_and_membership_source():
    from firm_lab.research_features.sector import sector_features
    from firm_lab.research_features.types import Request,SourceRef,content_hash
    from firm_lab.research_features.calendar import session_dates
    days=session_dates('2026-08-01','2026-09-30')
    refs={}
    for symbol,known in [('XLK','2026-10-01T20:00:00Z'),('XLY','2026-10-03T20:00:00Z')]:
        refs[symbol]=[dict(session=day,value=str(100+i*(1 if symbol=='XLK' else 2)),known_at=known,
            ref=SourceRef('feature_observations',symbol+day,'a'*64,known)) for i,day in enumerate(days)]
    membership=dict(kind='ETF_MEMBERSHIP',members=['XLK','XLY'],version='test-v1',
        effective_from='2026-01-01',effective_to=None,known_at='2026-10-01T20:00:00Z',source_urls=['https://www.ssga.com/'])
    membership['content_hash']=content_hash(membership)
    snapshot={'closes':refs['XLK'],'reference_closes':refs,'sector_membership':['XLK','XLY'],
        'sector_membership_record':membership,'mappings':[]}
    result=next(r for r in sector_features(snapshot,Request('XLK','2026-09-30','2026-10-03T20:00:00Z')) if r.name=='sector_leadership_rank20')
    assert result.value=='2' and result.known_at=='2026-10-03T20:00:00+00:00'
    assert any(r.row_id.startswith('XLY') for r in result.refs)
    assert any(r.table=='research_sector_mappings' for r in result.refs)


def test_breadth_requires_complete_effective_dated_constituents():
    from firm_lab.research_features.sector import sector_features
    from firm_lab.research_features.types import Request,SourceRef,content_hash
    from firm_lab.research_features.calendar import session_dates
    days=session_dates('2026-07-01','2026-09-30')
    known='2026-10-03T20:00:00Z'
    refs={s:[dict(session=day,value=str(100+i*direction),known_at=known,
            ref=SourceRef('feature_observations',s+day,'a'*64,known)) for i,day in enumerate(days)]
          for s,direction in [('AAA',1),('BBB',-1)]}
    record=dict(kind='CONSTITUENTS',members=['AAA','BBB'],sector='technology',version='test-v1',
        effective_from='2026-01-01',effective_to=None,known_at=known,source_urls=['https://www.ssga.com/'])
    record['content_hash']=content_hash(record)
    snapshot={'closes':[],'reference_closes':refs,'constituent_record':record,'mappings':[]}
    request=Request('XLK','2026-09-30',known)
    results={r.name:r for r in sector_features(snapshot,request)}
    assert results['sector_breadth'].value=='0.5'
    assert results['sector_sma50_participation'].value=='0.5'
    snapshot['reference_closes']={'AAA':refs['AAA']}
    assert next(r for r in sector_features(snapshot,request) if r.name=='sector_breadth').value is None
