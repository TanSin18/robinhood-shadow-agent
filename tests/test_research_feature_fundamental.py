from decimal import Decimal as D


def test_growth_negative_base_and_zero():
    from firm_lab.research_features.fundamental import signed_growth
    assert signed_growth(D(-5),D(-10))==D('.5')
    assert signed_growth(D(1),D(0)) is None


def fact(field,value,period='3M',end='2026-06-30',start='2026-04-01',year='2026',unit='USD'):
    from firm_lab.research_features.types import SourceRef
    return dict(normalized_field=field,value=value,unit=unit,period_type=period,period_start=start,period_end=end,
        filing_fiscal_year=year,filing_fiscal_period='Q2',accepted_timestamp='2026-08-01T20:00:00+00:00',
        known_at='2026-10-03T20:00:00+00:00',confirmed_in_filing='CONFIRMED',accession_number=year,
        ref=SourceRef('fundamental_fact_observations',field+year,'a'*64,'2026-10-03T20:00:00+00:00'))


def test_matching_margin_and_debt_missing():
    from firm_lab.research_features.fundamental import fundamental_features
    from firm_lab.research_features.types import Request
    facts=[fact('revenue','100'),fact('operating_income','20'),fact('operating_cash_flow','50','6M',start='2026-01-01')]
    req=Request('AAPL','2026-09-30','2026-10-03T20:00:00Z')
    rows={r.name:r for r in fundamental_features({'facts':facts},req)}
    assert D(rows['operating_margin'].value)==D('.2')
    assert rows['ocf_margin'].value is None
    assert rows['debt_revenue'].value is None


def test_unconfirmed_and_later_accepted_fact_cannot_enter():
    from firm_lab.research_features.fundamental import fundamental_features
    from firm_lab.research_features.types import Request
    facts=[fact('revenue','100'),dict(fact('operating_income','20'),confirmed_in_filing='NOT_FOUND')]
    req=Request('AAPL','2026-09-30','2026-10-03T20:00:00Z')
    assert next(r for r in fundamental_features({'facts':facts},req) if r.name=='operating_margin').value is None
    facts[1]=dict(fact('operating_income','20'),accepted_timestamp='2026-10-04T20:00:00Z')
    assert next(r for r in fundamental_features({'facts':facts},req) if r.name=='operating_margin').value is None


def test_yoy_and_qoq_not_synthesized_from_ytd():
    from firm_lab.research_features.fundamental import fundamental_features
    from firm_lab.research_features.types import Request
    facts=[fact('revenue','120'),fact('revenue','100',end='2025-06-30',start='2025-04-01',year='2025')]
    rows={r.name:r for r in fundamental_features({'facts':facts},Request('AAPL','2026-09-30','2026-10-03T20:00:00Z'))}
    assert D(rows['revenue_yoy'].value)==D('.2')
    assert rows['revenue_qoq'].value is None
