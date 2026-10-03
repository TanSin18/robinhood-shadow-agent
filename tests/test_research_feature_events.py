def test_filing_age_counts_and_duplicates():
    from firm_lab.research_features.events import event_features
    from firm_lab.research_features.types import Request,SourceRef
    row=dict(form_type='8-K',accession_number='x',accepted_timestamp='2026-09-29T20:30:00+00:00',
        known_at='2026-10-01T20:00:00+00:00',ref=SourceRef('filing_observations','1','a'*64,'2026-10-01T20:00:00+00:00'))
    rows={r.name:r for r in event_features({'filings':[row,row],'earnings':[]},Request('AAPL','2026-09-30','2026-10-03T20:00:00Z'))}
    assert rows['days_since_8k'].value=='1'
    assert rows['filing_count30'].value=='1'
    assert rows['sessions_until_earnings'].value is None


def test_no_earnings_release_time_inferred_from_filing():
    from firm_lab.research_features.events import event_features
    from firm_lab.research_features.types import Request,SourceRef
    event=dict(event_date='2026-09-29',accepted_timestamp='2026-09-30T10:00:00+00:00',
        known_at='2026-10-01T20:00:00+00:00',ref=SourceRef('earnings_event_observations','1','a'*64,'2026-10-01T20:00:00+00:00'))
    rows={r.name:r for r in event_features({'filings':[],'earnings':[event]},Request('AAPL','2026-09-30','2026-10-03T20:00:00Z'))}
    assert rows['earnings_timing'].value is None


def test_result_known_at_respects_acceptance_even_if_capture_field_is_earlier():
    from firm_lab.research_features.events import event_features
    from firm_lab.research_features.types import Request,SourceRef
    row=dict(form_type='8-K',accession_number='x',accepted_timestamp='2026-09-30T19:00:00+00:00',
        known_at='2026-09-30T18:00:00+00:00',ref=SourceRef('filing_observations','1','a'*64,'2026-09-30T18:00:00+00:00'))
    r=next(r for r in event_features({'filings':[row],'earnings':[]},Request('AAPL','2026-09-30','2026-09-30T20:00:00Z')) if r.name=='days_since_8k')
    assert r.known_at=='2026-09-30T19:00:00+00:00'
