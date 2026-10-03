from datetime import datetime, timezone
from decimal import Decimal
import pytest
from firm_lab.errors import FirmLabError
from firm_lab_collectors.transport import Response

NOW = datetime(2026, 10, 3, 21, tzinfo=timezone.utc)
FED = '''<p class="article__time">September 16, 2026</p><p>For release at 2:00 p.m. EDT</p>
<h1>Federal Reserve issues FOMC statement</h1><p>The Committee decided to raise the target range for the federal funds rate by 1/4 percentage point to 3-3/4 to 4 percent.</p>'''
PCE = '''<h1>Personal Income and Outlays, August 2026</h1>
<a href="https://www.bea.gov/news/pio-release-additional-information">Additional Information</a>
<p>EMBARGOED UNTIL RELEASE AT 8:30 a.m. EDT, Wednesday, September 30, 2026</p>
<table><tr><th colspan="3">Personal Income and Related Measures [Percent change from preceding month]</th></tr><tr><th></th><th>July</th><th>August</th></tr>
<tr><td>PCE price index</td><td>0.1</td><td>0.3</td></tr>
<tr><td>PCE price index excluding food and energy</td><td>0.1</td><td>0.2</td></tr></table>'''
CPI = '''<p>Transmission of material in this release is embargoed until 8:30 a.m. (ET) Friday, September 11, 2026</p>
<h1>CONSUMER PRICE INDEX - AUGUST 2026</h1><table><caption>Table 1. Consumer Price Index for All Urban Consumers (CPI-U): U.S. city average, August 2026 [1982-84=100]</caption>
<tr><th>Unadjusted indexes</th><th>Aug. 2025</th><th>Jul. 2026</th><th>Aug. 2026</th><th>Seasonally adjusted percent change</th></tr>
<tr><td>All items</td><td>100.0</td><td>323.964</td><td>333.907</td><td>334.980</td><td>3.4</td><td>0.3</td><td>0.5</td><td>0.1</td><td>0.4</td></tr>
<tr><td>All items less food and energy</td><td>78.0</td><td>320.000</td><td>330.000</td><td>331.000</td><td>2.4</td><td>0.3</td><td>0.5</td><td>0.2</td><td>0.3</td></tr></table>'''
LABOR = '''<p>Transmission of material in this release is embargoed until 8:30 a.m. (ET) Friday, September 4, 2026</p>
<h1>THE EMPLOYMENT SITUATION — AUGUST 2026</h1><p>Seasonally adjusted</p>
<p>Total nonfarm payroll employment increased by 162,000 in August, and the unemployment rate was unchanged at 4.3 percent.</p>'''

def reply(kind, body):
    urls = {'fed':'https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm',
            'pce':'https://www.bea.gov/news/2026/personal-income-and-outlays-august-2026',
            'cpi':'https://www.bls.gov/news.release/archives/cpi_09112026.htm',
            'labor':'https://www.bls.gov/news.release/archives/empsit_09042026.htm'}
    return Response(200,body.encode(),urls[kind],NOW.isoformat())

def parse(kind, body):
    from firm_lab_collectors.macro import parse_release
    return parse_release(kind,reply(kind,body),now=NOW)

def test_fomc_exact_timestamp_target_and_publisher_change():
    b=parse('fed',FED)
    assert [o['value'] for o in b['observations']] == ['3.75','4']
    assert b['observations'][0]['published_at'] == '2026-09-16T18:00:00+00:00'
    assert b['metadata']['change_basis_points'] == '25'
    assert b['metadata']['meeting_date'] == '2026-09-16'

def test_unchanged_fomc_and_ambiguous_timing():
    b=parse('fed',FED.replace('raise','maintain').replace('by 1/4 percentage point to','at'))
    assert b['metadata']['change_basis_points'] == '0'
    with pytest.raises(FirmLabError,match='PUBLICATION'):
        parse('fed',FED.replace('For release at 2:00 p.m. EDT','For release today'))

def test_pce_preserves_monthly_change_not_index_level():
    b=parse('pce',PCE)
    assert [(r['series'],r['value'],r['unit']) for r in b['observations']] == [
        ('pce_headline_mom_sa','0.3','percent_change_mom_sa'),('pce_core_mom_sa','0.2','percent_change_mom_sa')]
    assert b['observations'][0]['period'] == '2026-08'
    assert b['metadata']['underlying_source'] == 'BEA'

def test_cpi_does_not_relabel_unadjusted_index_as_sa():
    b=parse('cpi',CPI)
    assert [o['series'] for o in b['observations']] == ['cpi_headline_nsa','cpi_core_nsa']
    assert [o['value'] for o in b['observations']] == ['334.980','331.000']
    assert b['metadata']['source_series_ids'] == ['CUUR0000SA0','CUUR0000SA0L1E']

def test_labor_payroll_change_not_level():
    b=parse('labor',LABOR)
    assert [(o['series'],o['value']) for o in b['observations']] == [('unemployment_rate','4.3'),('nonfarm_payroll_change','162')]
    assert b['metadata']['source_series_ids'] == ['LNS14000000','CES0000000001:publisher_reported_monthly_change']

@pytest.mark.parametrize('kind,body',[('cpi',CPI),('labor',LABOR),('pce',PCE)])
def test_publication_evidence_is_required_for_all_release_parsers(kind,body):
    with pytest.raises(FirmLabError,match='PUBLICATION'):
        parse(kind,body.replace('8:30 a.m.','morning'))

def test_unknown_or_ambiguous_tables_refused():
    with pytest.raises(FirmLabError):
        parse('pce',PCE.replace('Percent change from preceding month','Index level'))
    with pytest.raises(FirmLabError):
        parse('cpi',CPI.replace('Unadjusted indexes','Adjusted indexes'))

def test_fred_vintage_date_is_not_publication_time():
    from firm_lab_collectors.macro import parse_fred
    with pytest.raises(FirmLabError,match='EXACT_PUBLICATION_UNAVAILABLE'):
        parse_fred({'observations':[{'date':'2026-08-01','realtime_start':'2026-09-30','value':'125.3'}]})

def test_treasury_daily_date_is_not_publication_time():
    from firm_lab_collectors.macro import parse_treasury
    with pytest.raises(FirmLabError,match='EXACT_PUBLICATION_UNAVAILABLE'):
        parse_treasury(b'Date,2 Yr,10 Yr\n10/02/2026,4.01,4.12\n')

def test_event_links_reject_period_source_value_revision_mismatch():
    from firm_lab_collectors.macro import validate_links
    b=parse('fed',FED)
    validate_links(b)
    for key,value in [('period','2025-01'),('source','FRED'),('released_value','99'),('revision',2)]:
        bad={**b,'events':[dict(e) for e in b['events']]}
        bad['events'][0][key]=value
        with pytest.raises(FirmLabError,match='EVENT_OBSERVATION_MISMATCH'):
            validate_links(bad)


def test_pce_prior_period_is_a_new_release_vintage_not_backdated():
    from firm_lab_collectors.macro import parse_release
    b=parse_release('pce',reply('pce',PCE),now=NOW,include_prior=True)
    prior=[o for o in b['observations'] if o['period']=='2026-07']
    assert len(prior)==2
    assert [o['value'] for o in prior]==['0.1','0.1']
    assert all(o['published_at']=='2026-09-30T12:30:00+00:00' for o in prior)


def test_treasury_candidates_preserve_cmt_identity_but_are_not_pit_rows():
    from firm_lab_collectors.macro import treasury_candidates
    rows=treasury_candidates(b'Date,2 Yr,10 Yr,3 Mo\n10/02/2026,4.83,5.28,4.19\n',now=NOW)
    assert [(r['series'],r['value']) for r in rows]==[('treasury_2y','4.83'),('treasury_10y','5.28'),('treasury_3m','4.19')]
    assert all(r['unit']=='percent' and r['period']=='2026-10-02' and r['publication_status']=='UNAVAILABLE' for r in rows)
    with pytest.raises(FirmLabError,match='TREASURY_SERIES_IDENTITY'):
        treasury_candidates(b'auction_date,high_yield\n10/02/2026,4.2',now=NOW)
    with pytest.raises(FirmLabError,match='FUTURE_OBSERVATION_PERIOD'):
        treasury_candidates(b'Date,2 Yr,10 Yr\n10/05/2026,4,5',now=NOW)


def test_cpi_rejects_mismatched_table_period():
    with pytest.raises(FirmLabError,match='TABLE_PERIOD_MISMATCH'):
        parse('cpi',CPI.replace('average, August 2026','average, July 2026'))


def test_unrelated_pce_unit_text_cannot_validate_a_different_measure():
    bad=PCE.replace('[Percent change from preceding month]','[Index level]')+'<p>Percent change from preceding month</p>'
    with pytest.raises(FirmLabError,match='PCE_TABLE_IDENTITY_UNAVAILABLE'): parse('pce',bad)


def test_cpi_column_dates_cannot_be_swapped_or_missing():
    for bad in (CPI.replace('<th>Jul. 2026</th><th>Aug. 2026</th>','<th>Aug. 2026</th><th>Jul. 2026</th>'),
                CPI.replace('<th>Aug. 2026</th>','<th>Unknown</th>')):
        with pytest.raises(FirmLabError,match='TABLE_COLUMN_IDENTITY_UNAVAILABLE'): parse('cpi',bad)


def test_invalid_12_hour_clock_is_not_normalized():
    with pytest.raises(FirmLabError,match='INVALID_PUBLICATION_CLOCK'):
        parse('fed',FED.replace('2:00 p.m.','14:00 p.m.'))


def test_pce_requires_linked_publisher_conventions_and_rejects_nsa_table():
    for bad in (PCE.replace('/news/pio-release-additional-information','/unrelated'),
                PCE.replace('[Percent change from preceding month]','[Percent change from preceding month, unadjusted]')):
        with pytest.raises(FirmLabError,match='PCE_SEASONAL_IDENTITY_UNAVAILABLE'): parse('pce',bad)
