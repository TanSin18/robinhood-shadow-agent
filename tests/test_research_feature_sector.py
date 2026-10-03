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
