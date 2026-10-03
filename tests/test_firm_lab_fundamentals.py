"""Checkpoint 4: reported company facts from SEC XBRL data and factual earnings-release events. Fixture SEC answers only;
no test opens a network connection. What is proven here: normalization fails closed, every fact is known from its SEC
acceptance time, a restatement is a new version and never an overwrite, each value is checked against the filing's own
document, and an earnings event is a fact about a filing with no sentiment, score, signal or transcript."""
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal as D

import pytest

from agents.desk import firm_lab_page
from firm_lab import capabilities, fundamentals, ixbrl, quality, rawstore, schemas, view
from firm_lab.errors import FirmLabError
from firm_lab.providers import OK, REJECTED, UNAVAILABLE
from firm_lab.store import FORBIDDEN_TABLE_WORDS
from firm_lab_collectors import cli, earnings, runner, xbrl
from test_firm_lab_collectors import AGENT, CLOCK, NOW, TICKERS, Fake, _codes, _lab, _rows

CIK = 320193
Q3, Q2, K25, Q3_25 = '0000320193-26-000081', '0000320193-26-000060', '0000320193-25-000120', '0000320193-25-000073'
E_Q3, E_Q2, E_K25, OTHER_8K = '0000320193-26-000079', '0000320193-26-000058', '0000320193-25-000118', '0000320193-26-000070'
# (accession, form, filing date, report date, header New York clock, JSON text, items) newest first, as the SEC lists them
FILINGS = (
    (Q3, '10-Q', '2026-07-31', '2026-06-27', '20260731180132', '2026-07-31T22:01:32.000Z', ''),
    (E_Q3, '8-K', '2026-07-30', '2026-07-30', '20260730163004', '2026-07-30T20:30:04.000Z', '2.02,9.01'),
    (OTHER_8K, '8-K', '2026-06-10', '2026-06-09', '20260610080000', '2026-06-10T12:00:00.000Z', '5.02'),
    (Q2, '10-Q', '2026-05-01', '2026-03-28', '20260501060215', '2026-05-01T14:02:15.000Z', ''),          # JSON = header + 4 hours: flagged
    (E_Q2, '8-K', '2026-04-30', '2026-04-30', '20260430092959', '2026-04-30T13:29:59.000Z', '2.02,9.01'),
    (K25, '10-K', '2025-10-31', '2025-09-27', '20251031060136', '2025-10-31T10:01:36.000Z', ''),
    (E_K25, '8-K', '2025-10-30', '2025-10-30', '20251030120000', '2025-10-30T16:00:00.000Z', '2.02,9.01'),
    (Q3_25, '10-Q', '2025-08-01', '2025-06-28', '20250801060105', '2025-08-01T10:01:05.000Z', ''),
)
FORM = {f[0]: f for f in FILINGS}


def fact(accn, value, end, start=None, frame=None):
    form, filed = FORM[accn][1], FORM[accn][2]
    row = {'end': end, 'val': value, 'accn': accn, 'fy': int(FORM[accn][3][:4]), 'fp': 'FY' if form == '10-K' else 'Q3', 'form': form, 'filed': filed}
    if start:
        row['start'] = start
    if frame:
        row['frame'] = frame
    return row


def company_facts():
    """A cut-down company-facts file in the SEC's shape. Values are invented for the test."""
    usd, per_share, shares = {}, {}, {}

    def put(table, concept, unit, *rows):
        table.setdefault(concept, {'label': concept, 'description': '', 'units': {}})['units'].setdefault(unit, []).extend(rows)

    revenue = 'RevenueFromContractWithCustomerExcludingAssessedTax'
    put(usd, revenue, 'USD',
        fact(Q3_25, 85777000000, '2025-06-28', '2025-03-30'),                                  # first reported
        fact(K25, 416161000000, '2025-09-27', '2024-09-29', 'CY2025'),
        fact(Q2, 95359000000, '2026-03-28', '2025-12-28'), fact(Q2, 219659000000, '2026-03-28', '2025-09-28'),
        fact(Q3, 94036000000, '2026-06-27', '2026-03-29', 'CY2026Q2'), fact(Q3, 313695000000, '2026-06-27', '2025-09-28'),
        fact(Q3, 85800000000, '2025-06-28', '2025-03-30'))                                      # the comparative, restated a year later
    for accn, end, start, value in ((Q3_25, '2025-06-28', '2025-03-30', 23434000000), (K25, '2025-09-27', '2024-09-29', 112010000000),
                                    (Q2, '2026-03-28', '2025-12-28', 24780000000), (Q3, '2026-06-27', '2026-03-29', 25100000000)):
        put(usd, 'NetIncomeLoss', 'USD', fact(accn, value, end, start))
        put(usd, 'GrossProfit', 'USD', fact(accn, value * 2, end, start))
        put(usd, 'OperatingIncomeLoss', 'USD', fact(accn, value + 4000000000, end, start))
    for accn, end, start, value in ((Q3_25, '2025-06-28', '2025-03-30', 1.57), (K25, '2025-09-27', '2024-09-29', 7.46),
                                    (Q2, '2026-03-28', '2025-12-28', 1.65), (Q3, '2026-06-27', '2026-03-29', 1.68)):
        put(per_share, 'EarningsPerShareDiluted', 'USD/shares', fact(accn, value, end, start))
        put(shares, 'WeightedAverageNumberOfDilutedSharesOutstanding', 'shares', fact(accn, 14948179000, end, start))
    # the cash-flow statement of a quarterly report covers the fiscal year to date
    for accn, end, start, value in ((Q3_25, '2025-06-28', '2024-09-29', 81754000000), (K25, '2025-09-27', '2024-09-29', 111482000000),
                                    (Q2, '2026-03-28', '2025-09-28', 53887000000), (Q3, '2026-06-27', '2025-09-28', 84000000000)):
        put(usd, 'NetCashProvidedByUsedInOperatingActivities', 'USD', fact(accn, value, end, start))
        put(usd, 'PaymentsToAcquirePropertyPlantAndEquipment', 'USD', fact(accn, 9000000000, end, start))
    for accn, end in ((Q3_25, '2025-06-28'), (K25, '2025-09-27'), (Q2, '2026-03-28'), (Q3, '2026-06-27')):
        put(usd, 'CashAndCashEquivalentsAtCarryingValue', 'USD', fact(accn, 36269000000, end))
        put(usd, 'LongTermDebtNoncurrent', 'USD', fact(accn, 78328000000, end))                # debt is reported in parts only
        put(usd, 'CommercialPaper', 'USD', fact(accn, 9967000000, end))
    put(usd, 'Liabilities', 'USD', fact(Q3, 264904000000, '2026-06-27'))                       # not a watched concept: never read
    return {'cik': CIK, 'entityName': 'Apple Inc.', 'facts': {'dei': {}, 'us-gaap': {**usd, **per_share, **shares}}}


def flat_rows(data=None):
    return xbrl.flatten((data or company_facts())['facts']['us-gaap'])


def document(data, accn, *, wrong=None, drop=None):
    """The filing's own primary document, tagged the way a company tags it: values in millions, a context per period, and one
    product-line (dimension) context that must not be mistaken for the company total."""
    contexts, body, ids = [], [], {}
    try:
        tagged = xbrl.flatten(data['facts']['us-gaap'])
    except Exception:                                    # a deliberately broken facts file: the document itself stays well formed
        tagged = xbrl.flatten(company_facts()['facts']['us-gaap'])
    for row in tagged:
        if row['accn'] != accn or row['concept'] == drop:
            continue
        period = (row.get('start'), row['end'])
        if period not in ids:
            ids[period] = f'c-{len(ids) + 1}'
            inner = (f'<xbrli:startDate>{period[0]}</xbrli:startDate><xbrli:endDate>{period[1]}</xbrli:endDate>' if period[0]
                     else f'<xbrli:instant>{period[1]}</xbrli:instant>')
            contexts.append(f'<xbrli:context id="{ids[period]}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000320193'
                            f'</xbrli:identifier></xbrli:entity><xbrli:period>{inner}</xbrli:period></xbrli:context>')
        value = D(str(row['val'])) if row['concept'] != wrong else D(str(row['val'])) + 1000000
        if row['unit'] == 'USD/shares':
            text, scale = f'{value}', '0'
        elif row['unit'] == 'shares':
            text, scale = f'{value / 1000:,.0f}', '3'
        else:
            text, scale = f'{abs(value) / 1000000:,.0f}', '6'
        body.append(f'<td><ix:nonFraction unitRef="u" contextRef="{ids[period]}" decimals="-6" name="us-gaap:{row["concept"]}" '
                    f'format="ixt:num-dot-decimal" scale="{scale}" id="f-{len(body)}"><span>{text}</span></ix:nonFraction></td>')
    contexts.append('<xbrli:context id="c-seg"><xbrli:entity><xbrli:identifier scheme="x">0000320193</xbrli:identifier><xbrli:segment>'
                    '<xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">aapl:IPhoneMember</xbrldi:explicitMember></xbrli:segment>'
                    f'</xbrli:entity><xbrli:period><xbrli:startDate>2026-03-29</xbrli:startDate><xbrli:endDate>2026-06-27</xbrli:endDate>'
                    '</xbrli:period></xbrli:context>')
    body.append('<ix:nonFraction contextRef="c-seg" name="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax" scale="6" '
                'format="ixt:num-dot-decimal">44,582</ix:nonFraction>')
    return '<html><body><ix:header><ix:resources>' + ''.join(contexts) + '</ix:resources></ix:header><table>' + ''.join(body) + '</table></body></html>'


def header(accn):
    """The short header file as the SEC serves it (seen live): the filing's facts, and no list of its documents."""
    items = ''.join(f'<ITEMS>{item}\n' for item in FORM[accn][6].split(',') if item)
    return (f'<SEC-HEADER>{accn}.hdr.sgml : {FORM[accn][2].replace("-", "")}\n<ACCEPTANCE-DATETIME>{FORM[accn][4]}\n<ACCESSION-NUMBER>{accn}\n'
            f'<TYPE>{FORM[accn][1]}\n<PERIOD>{FORM[accn][3].replace("-", "")}\n{items}<FILING-DATE>{FORM[accn][2].replace("-", "")}\n</SEC-HEADER>\n')


def header_page(accn, documents):
    """The filing's -index-headers.html page: the same header followed by its document list, written as escaped text with links."""
    listed = ''.join(f'&lt;DOCUMENT&gt;\n&lt;TYPE&gt;{kind}\n&lt;SEQUENCE&gt;{n}\n&lt;FILENAME&gt;<a href="{name}">{name}</a>\n&lt;DESCRIPTION&gt;{kind}\n'
                     f'&lt;/DOCUMENT&gt;\n' for n, (kind, name) in enumerate(documents, 1))
    return '<html><body><pre>' + header(accn).replace('<', '&lt;').replace('>', '&gt;') + listed + '</pre></body></html>'


RELEASES = {E_Q3: (('8-K', 'aapl-20260730.htm'), ('EX-99.1', 'a8-kex991q3202606272026.htm'), ('EX-101.SCH', 'aapl-20260730.xsd')),
            E_Q2: (('8-K', 'aapl-20260430.htm'), ('EX-99.1', 'a8-kex991q2202603282026.htm')),
            E_K25: (('8-K', 'aapl-20251030.htm'),)}                                             # this one names no exhibit


def routes(data=None, *, filings=FILINGS, wrong=None, drop=None, missing_document=None, json_cik=None):
    data = data or company_facts()
    recent = {'accessionNumber': [f[0] for f in filings], 'form': [f[1] for f in filings], 'filingDate': [f[2] for f in filings],
              'reportDate': [f[3] for f in filings], 'acceptanceDateTime': [f[5] for f in filings], 'items': [f[6] for f in filings],
              'primaryDocument': [f'main-{f[0][-6:]}.htm' for f in filings]}
    out = [('company_tickers.json', 200, TICKERS),
           ('companyfacts/CIK0000320193.json', 200, data if json_cik is None else {**data, 'cik': json_cik}),
           ('submissions/CIK0000320193.json', 200, {'cik': '0000320193', 'name': 'Apple Inc.', 'filings': {'recent': recent, 'files': []}})]
    for f in filings:
        out.append((f[0] + '.hdr.sgml', 200, header(f[0])))
        if f[0] in RELEASES:
            out.append((f[0] + '-index-headers.html', 200, header_page(f[0], RELEASES[f[0]])))
        if f[1].startswith('10-') and f[0] != missing_document:
            out.append((f'main-{f[0][-6:]}.htm', 200, document(data, f[0], wrong=wrong if f[0] == Q3 else None, drop=drop if f[0] == Q3 else None)))
    return out


def _facts(route_list=None, **kw):
    provider = xbrl.SecXbrlFactsProvider(Fake(route_list or routes()), **kw)
    return provider, provider.facts('AAPL', since='2025-09-01', now=CLOCK)


def _pick(records, field, accn, start=None, end=None):
    found = [r for r in records if r['normalized_field'] == field and r['accession_number'] == accn
             and (end is None or r['period_end'] == end) and (start is None or r['period_start'] == start)]
    assert len(found) == 1, (field, accn, start, end, len(found))
    return found[0]


# ====================================================================================================== normalization
def _filings_for(*accessions):
    return {a: {'form': FORM[a][1], 'report_date': FORM[a][3], 'filing_date': FORM[a][2], 'accepted_timestamp': '2026-01-01T00:00:00+00:00'}
            for a in accessions}


def test_the_ten_fields_are_filled_only_by_their_written_rules():
    assert fundamentals.FIELDS == ('revenue', 'gross_profit', 'operating_income', 'net_income', 'eps_diluted', 'operating_cash_flow',
                                   'capital_expenditure', 'cash_and_equivalents', 'total_debt', 'diluted_shares_weighted_average')
    assert set(schemas.SCHEMAS['xbrl_facts'].allowed['normalized_field']) == set(fundamentals.FIELDS)
    out = fundamentals.normalize(flat_rows(), _filings_for(Q3), instrument='AAPL', cik=CIK)
    got = {(r['normalized_field'], r['period_type'], r['relation_to_filing']): r for r in out['accepted']}
    quarter = got[('revenue', '3M', 'current')]
    assert quarter['value'] == '94036000000' and quarter['concept'] == 'RevenueFromContractWithCustomerExcludingAssessedTax'
    assert quarter['unit'] == 'USD' and quarter['mapping_rule'] == 'sec-xbrl-normalization-v1:revenue' and quarter['frame'] == 'CY2026Q2'
    assert (quarter['period_start'], quarter['period_end'], quarter['accession_number'], quarter['form']) == ('2026-03-29', '2026-06-27', Q3, '10-Q')
    assert got[('revenue', '9M', 'current')]['value'] == '313695000000'                         # year to date is its own fact, not merged with the quarter
    assert got[('revenue', '3M', 'comparative')]['period_end'] == '2025-06-28'                  # last year's quarter, as this filing reports it
    assert got[('eps_diluted', '3M', 'current')]['unit'] == 'USD/shares' and got[('eps_diluted', '3M', 'current')]['value'] == '1.68'
    assert got[('cash_and_equivalents', 'instant', 'current')]['period_start'] is None
    # the cash-flow statement of a 10-Q is year to date; it stays year to date and no single quarter is computed from it
    assert got[('operating_cash_flow', '9M', 'current')]['value'] == '84000000000' and ('operating_cash_flow', '3M', 'current') not in got
    # total debt is reported in parts only: no sum is formed
    debt = [u for u in out['unresolved'] if u['field'] == 'total_debt']
    assert [u['reason'] for u in debt] == ['NEEDS_COMPONENT_RULE'] and debt[0]['concepts'] == ['CommercialPaper', 'LongTermDebtNoncurrent']
    assert not [r for r in out['accepted'] if r['normalized_field'] == 'total_debt']
    assert out['raw_facts'] == len([f for f in flat_rows() if f['accn'] == Q3]) and 'Liabilities' not in out['concepts_seen']
    # nothing is derived: every accepted value is a value the company itself tagged
    tagged = {str(D(str(f['val']))) for f in flat_rows()}
    assert all(str(D(r['value'])) in tagged for r in out['accepted'])
    assert not {'margin', 'growth', 'ratio', 'score', 'rank'} & {k for r in out['accepted'] for k in r}


def test_normalization_fails_closed_instead_of_guessing():
    base = [f for f in flat_rows() if f['accn'] == Q3]
    filings = _filings_for(Q3)
    reasons = lambda rows, field: sorted({u['reason'] for u in fundamentals.normalize(rows, filings, instrument='AAPL', cik=CIK)['unresolved']
                                         if u['field'] == field})
    accepted = lambda rows, field: [r for r in fundamentals.normalize(rows, filings, instrument='AAPL', cik=CIK)['accepted'] if r['normalized_field'] == field]
    quarter = {'taxonomy': 'us-gaap', 'unit': 'USD', 'start': '2026-03-29', 'end': '2026-06-27', 'accn': Q3, 'fy': 2026, 'fp': 'Q3', 'form': '10-Q',
               'filed': '2026-07-31', 'frame': None}
    # two accepted revenue concepts with different numbers for one period: neither is chosen
    two = base + [{**quarter, 'concept': 'Revenues', 'val': 94999000000}]
    assert reasons(two, 'revenue') == ['CONFLICTING_CONCEPTS']
    assert not [r for r in accepted(two, 'revenue') if r['period_start'] == '2026-03-29']
    # the same number under two accepted concepts is one fact, and the agreement is recorded
    same = base + [{**quarter, 'concept': 'Revenues', 'val': 94036000000}]
    agreed = [r for r in accepted(same, 'revenue') if r['period_start'] == '2026-03-29'][0]
    assert agreed['concept'] == 'Revenues' and agreed['agreeing_concepts'] == ['RevenueFromContractWithCustomerExcludingAssessedTax']
    # a unit that is not the expected one is not converted
    euros = [dict(f, unit='EUR') if f['concept'] == 'NetIncomeLoss' else f for f in base]
    assert reasons(euros, 'net_income') == ['UNEXPECTED_UNIT'] and not accepted(euros, 'net_income')
    # a broader capital-spending line is not treated as purchases of property, plant and equipment
    broad = [dict(f, concept='PaymentsToAcquireProductiveAssets') if f['concept'] == 'PaymentsToAcquirePropertyPlantAndEquipment' else f for f in base]
    assert reasons(broad, 'capital_expenditure') == ['BROADER_CONCEPT_NOT_MAPPED'] and not accepted(broad, 'capital_expenditure')
    # profit including non-controlling interests is not net income attributable to the company
    profit = [dict(f, concept='ProfitLoss') if f['concept'] == 'NetIncomeLoss' else f for f in base]
    assert reasons(profit, 'net_income') == ['NOT_REPORTED_UNDER_A_MAPPED_CONCEPT'] and not accepted(profit, 'net_income')
    # a period that is not 3, 6, 9 or 12 months long is not given a name
    odd = base + [{**quarter, 'concept': 'GrossProfit', 'start': '2026-05-01', 'val': 1}]
    assert 'UNCLASSIFIED_PERIOD' in reasons(odd, 'gross_profit')
    # a value that is not a number, and a duration where a balance is expected
    assert 'UNPARSEABLE_VALUE' in reasons([dict(f, val='n/a') if f['concept'] == 'OperatingIncomeLoss' else f for f in base], 'operating_income')
    assert 'UNEXPECTED_PERIOD_KIND' in reasons([dict(f, start='2026-03-29') if f['concept'] == 'CashAndCashEquivalentsAtCarryingValue' else f for f in base],
                                               'cash_and_equivalents')
    # a 12-month period is called 12M, not a fiscal year: a trailing twelve months in a quarterly report is not mislabelled
    assert fundamentals.period_type('2025-07-01', '2026-06-30') == '12M' and fundamentals.period_type('2026-04-01', '2026-06-30') == '3M'
    assert fundamentals.period_type(None, '2026-06-30') == 'instant' and fundamentals.period_type('2026-06-01', '2026-06-30') == ''
    assert fundamentals.normalize(flat_rows(), filings, instrument='AAPL', cik=CIK) == fundamentals.normalize(flat_rows(), filings, instrument='AAPL', cik=CIK)


def test_a_restatement_is_a_new_version_and_point_in_time_reads_never_see_it_early():
    history = fundamentals.normalize(flat_rows(), _filings_for(Q3_25, K25, Q2, Q3), instrument='AAPL', cik=CIK)['accepted']
    times = {Q3_25: '2025-08-01T10:01:05+00:00', K25: '2025-10-31T10:01:36+00:00', Q2: '2026-05-01T10:02:15+00:00', Q3: '2026-07-31T22:01:32+00:00'}
    versioned = fundamentals.assign_versions([dict(r, accepted_timestamp=times[r['accession_number']]) for r in history])
    first = _pick(versioned, 'revenue', Q3_25, '2025-03-30', '2025-06-28')
    again = _pick(versioned, 'revenue', Q3, '2025-03-30', '2025-06-28')
    assert (first['version'], first['is_restatement'], first['value'], first['prior_value']) == (1, False, '85777000000', None)
    assert (again['version'], again['is_restatement'], again['value'], again['prior_value']) == (2, True, '85800000000', '85777000000')
    assert first['value'] == '85777000000'                                                   # the first observation is not rewritten
    unchanged = _pick(versioned, 'net_income', Q3, '2026-03-29', '2026-06-27')
    assert (unchanged['version'], unchanged['is_restatement']) == (1, False)
    # the numbering comes from the complete filing history, so it does not depend on the order the filings are handed over
    shuffled = fundamentals.assign_versions(list(reversed([dict(r, accepted_timestamp=times[r['accession_number']]) for r in history])))
    assert {(r['accession_number'], r['normalized_field'], r['period_start'], r['period_end'], r['version']) for r in shuffled} == \
           {(r['accession_number'], r['normalized_field'], r['period_start'], r['period_end'], r['version']) for r in versioned}
    key = ('AAPL', 'revenue', '2025-03-30', '2025-06-28')
    before = fundamentals.as_of(versioned, '2026-07-31T22:01:31+00:00')[key]                 # one second before the restating filing was accepted
    after = fundamentals.as_of(versioned, '2026-07-31T22:01:32+00:00')[key]
    assert (before['value'], before['accession_number']) == ('85777000000', Q3_25) and (after['value'], after['version']) == ('85800000000', 2)
    assert key not in fundamentals.as_of(versioned, '2025-08-01T10:01:04+00:00')              # before the first filing: nothing is known
    assert ('AAPL', 'revenue', '2026-03-29', '2026-06-27') not in fundamentals.as_of(versioned, '2026-07-31T22:00:00+00:00')      # no look-ahead


# ====================================================================================================== the filing's own document
def test_the_filing_document_reader_takes_company_totals_only_and_never_guesses_a_number():
    tagged = ixbrl.numeric_facts(document(company_facts(), Q3))
    revenue = ('RevenueFromContractWithCustomerExcludingAssessedTax', '2026-03-29', '2026-06-27')
    assert tagged[revenue] == {D('94036000000')}                                             # "94,036" at scale 6; the product-line value is left out
    assert tagged[('EarningsPerShareDiluted', '2026-03-29', '2026-06-27')] == {D('1.68')}
    assert tagged[('CashAndCashEquivalentsAtCarryingValue', None, '2026-06-27')] == {D('36269000000')}
    page = ('<xbrli:context id="a"><xbrli:period><xbrli:startDate>2026-01-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period>'
            '</xbrli:context>'
            '<ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="a" scale="6" sign="-" format="ixt:num-dot-decimal">(1,234.5)</ix:nonFraction>'
            '<ix:nonFraction name="us-gaap:GrossProfit" contextRef="a" scale="3" format="ixt:num-comma-decimal">1.234,5</ix:nonFraction>'
            '<ix:nonFraction name="us-gaap:OperatingIncomeLoss" contextRef="a" scale="6" format="ixt:fixed-zero">&#8212;</ix:nonFraction>'
            '<ix:nonFraction name="us-gaap:Revenues" contextRef="a" scale="6" format="ixt-sec:numwordsen">twelve</ix:nonFraction>'
            '<ix:nonFraction name="us-gaap:CostOfRevenue" contextRef="missing" scale="6" format="ixt:num-dot-decimal">5</ix:nonFraction>'
            '<ix:nonFraction name="aapl:CustomThing" contextRef="a" scale="6" format="ixt:num-dot-decimal">7</ix:nonFraction>')
    got = ixbrl.numeric_facts(page.encode())
    period = ('2026-01-01', '2026-03-31')
    assert got == {('NetIncomeLoss', *period): {D('-1234500000')}, ('GrossProfit', *period): {D('1234500')}, ('OperatingIncomeLoss', *period): {D(0)}}
    record = {'concept': 'NetIncomeLoss', 'period_start': '2026-01-01', 'period_end': '2026-03-31', 'value': '-1234500000'}
    assert ixbrl.check(record, got) == 'CONFIRMED' and ixbrl.check({**record, 'value': '-1234500001'}, got) == 'MISMATCH'
    assert ixbrl.check({**record, 'concept': 'Revenues'}, got) == 'NOT_FOUND' and ixbrl.check(record, None) == 'NOT_CHECKED'


# ====================================================================================================== the provider
def test_company_facts_are_timed_by_the_filing_header_and_confirmed_in_the_filing_document():
    provider, result = _facts(max_filings=3)
    assert result.status == OK and not result.issues
    records = result.records()
    assert {r['accession_number'] for r in records} == {Q3, Q2, K25}                          # the three most recent periodic reports, nothing older
    assert all(r['confirmed_in_filing'] == 'CONFIRMED' and r['instrument'] == 'AAPL' and r['cik'] == '0000320193' for r in records)
    quarter = _pick(records, 'revenue', Q3, '2026-03-29', '2026-06-27')
    assert quarter['accepted_timestamp'] == '2026-07-31T22:01:32+00:00'                       # 18:01:32 New York, from the filing header
    assert quarter['accepted_timestamp_json'] == '2026-07-31T22:01:32.000Z' and quarter['acceptance_time_conflict'] is False
    assert quarter['source_url'].endswith('/api/xbrl/companyfacts/CIK0000320193.json')
    assert quarter['filing_document_url'] == 'https://www.sec.gov/Archives/edgar/data/320193/000032019326000081/main-000081.htm'
    assert quarter['filing_fiscal_year'] == 2026 and quarter['form'] == '10-Q' and quarter['filing_date'] == '2026-07-31'
    assert quarter['entity_name'] == 'Apple Inc.' and quarter['ingestion_timestamp'] == NOW.isoformat()
    flagged = _pick(records, 'net_income', Q2, '2025-12-28', '2026-03-28')
    assert flagged['acceptance_time_conflict'] is True and flagged['accepted_timestamp'] == '2026-05-01T10:02:15+00:00'      # the header, not the JSON
    assert flagged['accepted_timestamp_json'] == '2026-05-01T14:02:15.000Z'                   # kept exactly as sent
    # the restated comparative carries version 2 although the filing that first reported it was not among those read
    restated = _pick(records, 'revenue', Q3, '2025-03-30', '2025-06-28')
    assert (restated['version'], restated['is_restatement'], restated['prior_value'], restated['relation_to_filing']) == (2, True, '85777000000', 'comparative')
    assert Q3_25 not in {r['accession_number'] for r in records}
    assert result.provenance.provider == 'SEC EDGAR' and result.provenance.content_hash and not result.provenance.missing()
    report = provider.reports['AAPL']
    assert report['normalized_accepted'] == len(records) and report['restatements'] == 1 and report['checked_against_filing'] == {'CONFIRMED': len(records)}
    assert report['quality']['passes'] is True and report['quality']['critical_unresolved'] == []
    assert report['quality']['unresolved_by_field'] == {'total_debt': {'NEEDS_COMPONENT_RULE': 3}} and report['unresolved'] == 3
    assert [f['accession_number'] for f in report['filings']] == [Q3, Q2, K25] and report['filings'][1]['conflict'] is True
    assert report['units'].keys() == {'USD', 'USD/shares', 'shares'} and report['raw_facts_in_filings_read'] > report['normalized_accepted'] - 1
    # only SEC hosts were asked, and no fact came from anywhere else
    assert {u.split('/')[2] for u, _ in provider.transport.calls} == {'www.sec.gov', 'data.sec.gov'}
    assert not {'ratio', 'margin', 'growth', 'estimate', 'consensus'} & {k for r in records for k in r}


def test_a_value_that_differs_from_the_filing_document_refuses_the_whole_answer():
    provider, result = _facts(routes(wrong='NetIncomeLoss'), max_filings=3)
    assert result.status == REJECTED and _codes(result) == ['FACT_DIFFERS_FROM_FILING']
    with pytest.raises(FirmLabError):
        result.records()                                                                    # nothing is kept, not even the facts that did match
    assert provider.reports['AAPL']['checked_against_filing']['MISMATCH'] == 1
    # a fact the document does not carry at all is kept, flagged, and a critical one stops the quality check
    provider, result = _facts(routes(drop='EarningsPerShareDiluted'), max_filings=3)
    assert result.status == OK
    lost = _pick(result.records(), 'eps_diluted', Q3, '2026-03-29', '2026-06-27')
    assert lost['confirmed_in_filing'] == 'NOT_FOUND'
    verdict = provider.reports['AAPL']['quality']
    assert verdict['passes'] is False and verdict['critical_not_confirmed_in_filing'] == [{'accession_number': Q3, 'field': 'eps_diluted'}]
    # a filing whose document cannot be read is not waved through
    _, result = _facts(routes(missing_document=Q2), max_filings=3)
    assert result.status == REJECTED and _codes(result) == ['FILING_DOCUMENT_UNREADABLE']


def test_company_facts_refuse_the_wrong_company_a_bad_shape_and_an_unverifiable_time():
    assert _codes(_facts(routes(json_cik=789019))[1]) == ['CONFLICTING_INSTRUMENT_IDENTITY']
    broken = company_facts()
    broken['facts']['us-gaap']['NetIncomeLoss']['units']['USD'][0].pop('accn')
    assert _codes(_facts(routes(broken))[1]) == ['MALFORMED_RESPONSE']
    no_gaap = {'cik': CIK, 'entityName': 'Apple Inc.', 'facts': {'dei': {}}}
    assert _codes(_facts(routes(no_gaap))[1]) == ['MALFORMED_RESPONSE']
    headerless = [r for r in routes() if not r[0].endswith('.hdr.sgml')]
    assert _codes(_facts(headerless)[1]) == ['ACCEPTANCE_TIME_UNVERIFIED']
    # an original report the facts file knows nothing about makes the answer unusable; an amendment without financial data is left out and named
    gone = company_facts()
    for entry in gone['facts']['us-gaap'].values():
        for unit in entry['units']:
            entry['units'][unit] = [r for r in entry['units'][unit] if r['accn'] != Q2]
    assert _codes(_facts(routes(gone), max_filings=3)[1]) == ['NO_FACTS_FOR_FILING']
    amended = (('0000320193-26-000090', '10-K/A', '2026-08-15', '2025-09-27', '20260815090000', '2026-08-15T13:00:00.000Z', ''),) + FILINGS
    FORM[amended[0][0]] = amended[0]
    provider, result = _facts(routes(filings=amended), max_filings=2)
    assert result.status == OK and {r['accession_number'] for r in result.records()} == {Q3}
    assert provider.reports['AAPL']['amendments_without_financial_facts'] == ['0000320193-26-000090']
    for status in (403, 429):
        assert _facts([('company_tickers.json', status, b'')])[1].status == UNAVAILABLE
    sneaky = dict(_facts(max_filings=1)[1].records()[0], earnings_surprise_score=0.9)
    assert 'SIGNAL_FIELD_NOT_ALLOWED' in quality.validate('xbrl_facts', [sneaky], now=NOW, provenance=_facts(max_filings=1)[1].provenance).codes()
    assert 'VALUE_NOT_ALLOWED' in quality.validate('xbrl_facts', [dict(sneaky, confirmed_in_filing='MISMATCH')], now=NOW,
                                                   provenance=_facts(max_filings=1)[1].provenance).codes()


# ====================================================================================================== the sample run
def test_the_fundamentals_capability_follows_the_evidence(tmp_path):
    lab = _lab(tmp_path)
    assert lab.capability('fundamentals') == 'UNAVAILABLE'
    idle = Fake(routes())
    assert runner.run_xbrl(lab, symbols=('AAPL',), environ={}, transport=idle, clock=CLOCK)['connection'] == 'NOT_CONFIGURED' and idle.requests == 0
    report = runner.run_xbrl(lab, symbols=('AAPL',), environ=AGENT, transport=Fake(routes()), clock=CLOCK, max_filings=3)
    assert [(r['status'], r['quality_passes']) for r in report['runs']] == [(OK, True)] and report['capabilities']['fundamentals'] == 'AVAILABLE'
    rows = _rows(lab, 'fundamental_fact_observations')
    assert len(rows) == report['runs'][0]['stored'] == report['validation']['AAPL']['normalized_accepted'] and report['runs'][0]['duplicates'] == 0
    row = [r for r in rows if r['normalized_field'] == 'revenue' and r['accession_number'] == Q3 and r['period_start'] == '2026-03-29'][0]
    assert row['value'] == '94036000000' and row['accepted_timestamp'] == '2026-07-31T22:01:32+00:00' and row['confirmed_in_filing'] == 'CONFIRMED'
    for column in ('provider', 'source_id', 'source_timestamp', 'known_at', 'ingested_at', 'schema_version', 'content_hash', 'run_id', 'taxonomy',
                   'concept', 'unit', 'form', 'accession_number', 'mapping_rule', 'source_url', 'version'):
        assert all(r[column] not in (None, '') for r in rows), column
    detail = {c['capability']: c for c in lab.capabilities()}['fundamentals']
    assert detail['provider'] == 'SEC EDGAR' and 'Left unresolved, never derived: total_debt (AAPL).' in detail['detail']
    with lab.connect() as db:
        diagnostics = json.loads(db.execute('SELECT diagnostics_json FROM provider_runs ORDER BY id DESC LIMIT 1').fetchone()[0])
    assert diagnostics['validation']['quality']['passes'] is True and diagnostics['validation']['unresolved_detail'][0]['reason'] == 'NEEDS_COMPONENT_RULE'
    # the same sample again stores nothing new: an observation is never duplicated and never changed
    again = runner.run_xbrl(lab, symbols=('AAPL',), environ=AGENT, transport=Fake(routes()), clock=CLOCK, max_filings=3)
    assert again['runs'][0]['stored'] == 0 and again['runs'][0]['duplicates'] == len(rows) and _rows(lab, 'fundamental_fact_observations') == rows
    # the restatement is a second row beside the first; reading the older filing later does not disturb the numbering
    wider = runner.run_xbrl(lab, symbols=('AAPL',), environ=AGENT, transport=Fake(routes()), clock=CLOCK, max_filings=4, days=700)
    assert wider['runs'][0]['stored'] > 0
    both = _rows(lab, 'fundamental_fact_observations', where="WHERE normalized_field='revenue' AND period_start='2025-03-30' AND period_end='2025-06-28'")
    assert sorted((r['accession_number'], r['value'], r['version'], r['is_restatement']) for r in both) == \
           [(Q3_25, '85777000000', 1, 'false'), (Q3, '85800000000', 2, 'true')]
    assert rawstore.summary(lab)['fundamental_fact_observations']['flags'] == {'ACCEPTANCE_TIME_CONFLICT': len([r for r in rows if r['accession_number'] == Q2]),
                                                                                'RESTATEMENT': 1}
    # stored rows with a failed quality check are not called available: the capability says partial, and why
    weak = runner.run_xbrl(lab, symbols=('AAPL',), environ=AGENT, transport=Fake(routes(drop='EarningsPerShareDiluted')), clock=CLOCK, max_filings=3)
    assert weak['runs'][0]['status'] == OK and weak['runs'][0]['quality_passes'] is False and weak['capabilities']['fundamentals'] == 'PARTIAL_EXISTING'
    detail = {c['capability']: c for c in lab.capabilities()}['fundamentals']['detail']
    assert 'not sufficient' in detail and 'AAPL: eps_diluted' in detail
    # a refused answer stores nothing and the capability stays below available
    count = len(_rows(lab, 'fundamental_fact_observations'))
    refused = runner.run_xbrl(lab, symbols=('AAPL',), environ=AGENT, transport=Fake(routes(wrong='NetIncomeLoss')), clock=CLOCK, max_filings=3)
    assert refused['runs'][0]['status'] == REJECTED and len(_rows(lab, 'fundamental_fact_observations')) == count
    assert refused['capabilities']['fundamentals'] == 'PARTIAL_EXISTING' and 'FACT_DIFFERS_FROM_FILING' in \
        {c['capability']: c for c in lab.capabilities()}['fundamentals']['detail']
    good = runner.run_xbrl(lab, symbols=('AAPL',), environ=AGENT, transport=Fake(routes()), clock=CLOCK, max_filings=3)
    assert good['capabilities']['fundamentals'] == 'AVAILABLE'
    for name in ('ml_ranker', 'sector_engine', 'portfolio_optimizer', 'options_strategy'):   # reported facts unlock no strategy component
        assert lab.capability(name) == 'NOT_STARTED'
    state = view.load(path=lab.path)
    assert state['mode'] == 'BUILD_OBSERVE' and state['experiments'] == [] and state['fills'] == 0 and not state['has_execution_tables']


# ====================================================================================================== earnings events
def _events(route_list=None, **kw):
    provider = earnings.EdgarEarningsEventsProvider(Fake(route_list or routes()), **kw)
    return provider, provider.events('AAPL', start='2025-04-01', end='2026-10-02', now=CLOCK)


def test_an_earnings_event_is_a_fact_about_a_filing_and_nothing_more():
    provider, result = _events()
    assert result.status == OK
    q3, q2, k25 = result.records()
    assert [r['accession_number'] for r in (q3, q2, k25)] == [E_Q3, E_Q2, E_K25]                # the 8-K without Item 2.02 is not an earnings event
    assert q3['form'] == '8-K' and q3['items'] == '2.02,9.01' and q3['event_date'] == '2026-07-30' and q3['filing_date'] == '2026-07-30'
    assert q3['accepted_timestamp'] == q3['accepted_timestamp_header'] == '2026-07-30T20:30:04+00:00' and q3['acceptance_time_conflict'] is False
    assert q3['acceptance_session'] == 'after_market_close'                                  # 16:30:04 New York
    assert q2['acceptance_session'] == 'before_market_open' and k25['acceptance_session'] == 'during_market_hours'       # 09:29:59 and 12:00:00
    base = 'https://www.sec.gov/Archives/edgar/data/320193/000032019326000079/'
    assert q3['filing_url'] == base + E_Q3 + '-index.htm' and q3['release_document_url'] == base + 'a8-kex991q3202606272026.htm'
    assert q3['release_document_type'] == 'EX-99.1' and q3['primary_document_url'] == base + 'main-000079.htm'
    # the fiscal period is the stated link to the periodic report, with the report named; it is not read from the release
    assert (q3['fiscal_period_end'], q3['periodic_accession_number']) == ('2026-06-27', Q3) and 'not read from the release' in q3['fiscal_period_basis']
    assert (q2['fiscal_period_end'], q2['periodic_accession_number']) == ('2026-03-28', Q2)
    assert (k25['fiscal_period_end'], k25['periodic_accession_number']) == ('2025-09-27', K25)
    assert k25['release_document_url'] == 'UNAVAILABLE' and k25['release_document_type'] is None      # no exhibit named: not guessed
    assert all(r['transcript_available'] is False for r in result.records())
    banned = ('sentiment', 'tone', 'score', 'signal', 'surprise', 'prediction', 'transcript_text', 'summary', 'guidance', 'estimate')
    assert not [k for r in result.records() for k in r if any(word in k for word in banned)]
    assert {u.split('/')[2] for u, _ in provider.transport.calls} == {'www.sec.gov', 'data.sec.gov'}
    assert not [u for u, _ in provider.transport.calls if 'ex991' in u or u.endswith('.htm')]      # the release itself is never opened
    # the SEC's own header is compared with its filing index: a disagreement about what the filing is refuses it
    wrong_item = [(k, s, b.replace('<ITEMS>2.02', '<ITEMS>7.01') if k == E_Q3 + '.hdr.sgml' else b) for k, s, b in routes()]
    assert _codes(_events(wrong_item)[1]) == ['ITEMS_DISAGREE']
    wrong_day = [(k, s, b.replace('<PERIOD>20260730', '<PERIOD>20260729') if k == E_Q3 + '.hdr.sgml' else b) for k, s, b in routes()]
    assert _codes(_events(wrong_day)[1]) == ['EVENT_DATE_DISAGREES']
    no_list = [r for r in routes() if not r[0].endswith('-index-headers.html')]               # no document list anywhere: unavailable, not guessed
    assert {r['release_document_url'] for r in _events(no_list)[1].records()} == {'UNAVAILABLE'}
    # the rule behind the fiscal period, on its own
    periodic = [{'accession_number': Q3, 'report_date': '2026-06-27', 'filing_date': '2026-07-31'},
                {'accession_number': Q2, 'report_date': '2026-03-28', 'filing_date': '2026-05-01'}]
    assert earnings.fiscal_period('2026-07-30', periodic) == ('2026-06-27', Q3)
    assert earnings.fiscal_period('2026-07-30', periodic[1:]) == (None, None)                 # the quarter's report is not filed yet: unavailable
    assert earnings.fiscal_period('2026-09-15', periodic) == (None, None)                     # filed long before the event: not this quarter's release
    assert earnings.documents('&lt;DOCUMENT&gt;\n&lt;TYPE&gt;EX-99.1\n&lt;SEQUENCE&gt;2\n&lt;FILENAME&gt;x.htm\n') == [('EX-99.1', 2, 'x.htm')]
    assert earnings.documents('<DOCUMENT>\n<TYPE>EX-99.1\n<SEQUENCE>2\n<FILENAME>../../etc/passwd\n') == []


def test_earnings_events_refuse_signals_and_unverifiable_times_and_store_facts_only(tmp_path):
    record = dict(_events()[1].records()[0])
    provenance = _events()[1].provenance
    for extra in ('sentiment', 'management_tone', 'surprise_pct', 'llm_prediction', 'earnings_score', 'signal'):
        assert 'SIGNAL_FIELD_NOT_ALLOWED' in quality.validate('earnings_events', [dict(record, **{extra: 1})], now=NOW, provenance=provenance).codes()
    assert 'KNOWN_AT_NOT_HEADER' in quality.validate('earnings_events', [dict(record, accepted_timestamp='2026-07-30T20:00:00+00:00')], now=NOW,
                                                     provenance=provenance).codes()
    assert 'VALUE_NOT_ALLOWED' in quality.validate('earnings_events', [dict(record, acceptance_session='bullish_open')], now=NOW,
                                                   provenance=provenance).codes()
    headerless = [r for r in routes() if not r[0].endswith(('.hdr.sgml', '-index-headers.html'))]
    assert _codes(_events(headerless)[1]) == ['ACCEPTANCE_TIME_UNVERIFIED']
    page_only = [r for r in routes() if not r[0].endswith('.hdr.sgml') and E_K25 not in r[0]]  # the header page alone still gives the time
    assert _events(page_only, max_events=2)[1].records()[0]['accepted_timestamp'] == '2026-07-30T20:30:04+00:00'
    none = tuple(f for f in FILINGS if '2.02' not in f[6])
    assert _codes(_events(routes(filings=none))[1]) == ['INCOMPLETE_HISTORICAL_WINDOW']
    lab = _lab(tmp_path)
    assert lab.capability('earnings_events') == 'UNAVAILABLE' and lab.capability('earnings_transcripts') == 'UNAVAILABLE'
    report = runner.run_earnings(lab, symbols=('AAPL',), environ=AGENT, transport=Fake(routes()), clock=CLOCK)
    assert report['runs'][0]['status'] == OK and report['runs'][0]['stored'] == 3 and report['capabilities']['earnings_events'] == 'AVAILABLE'
    rows = _rows(lab, 'earnings_event_observations')
    assert [(r['accession_number'], r['fiscal_period_end'], r['acceptance_session'], r['transcript_available']) for r in rows] == \
           [(E_Q3, '2026-06-27', 'after_market_close', 'false'), (E_Q2, '2026-03-28', 'before_market_open', 'false'),
            (E_K25, '2025-09-27', 'during_market_hours', 'false')]
    columns = set(rows[0])
    assert not [c for c in columns if any(word in c for word in quality.SIGNAL_WORDS)]         # the table has no place for an opinion
    assert lab.capability('earnings_transcripts') == 'UNAVAILABLE'                             # events do not make transcripts available
    again = runner.run_earnings(lab, symbols=('AAPL',), environ=AGENT, transport=Fake(routes()), clock=CLOCK)
    assert again['runs'][0]['stored'] == 0 and again['runs'][0]['duplicates'] == 3
    with lab.connect() as db:
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert not [t for t in tables if any(word in t for word in FORBIDDEN_TABLE_WORDS)]         # still no order, fill, position or cash table
    for name in ('ml_ranker', 'options_strategy'):
        assert lab.capability(name) == 'NOT_STARTED'


def test_the_cli_runs_the_two_sec_samples_and_prints_no_setting(tmp_path, capsys):
    lab = _lab(tmp_path)
    assert cli.main(['xbrl', '--path', str(lab.path), '--symbols', 'AAPL', '--max-filings', '3'], environ=AGENT, transport=Fake(routes())) == 0
    out = capsys.readouterr().out
    printed = json.loads(out)
    assert printed['run']['runs'][0]['status'] == OK and printed['run']['validation']['AAPL']['quality']['passes'] is True
    assert 'research@example.com' not in out
    assert cli.main(['earnings', '--path', str(lab.path), '--symbols', 'AAPL', '--max-events', '2'], environ=AGENT, transport=Fake(routes())) == 0
    out = capsys.readouterr().out
    assert json.loads(out)['run']['runs'][0]['stored'] == 2 and 'research@example.com' not in out
    assert sqlite3.connect(lab.path).execute('SELECT COUNT(*) FROM earnings_event_observations').fetchone()[0] == 2


# ====================================================================================================== the page and the boundary
def test_the_page_shows_what_was_found_and_makes_no_claim_about_it(tmp_path):
    lab = _lab(tmp_path)
    empty = firm_lab_page.render({'firm_lab': view.load(path=lab.path)})
    assert 'No company-facts sample has been run yet.' in empty and 'No earnings-release filing is stored yet.' in empty
    assert '<p class="fl-stamp">FACTUAL EVENT DATA ONLY — NO EARNINGS SIGNAL</p>' in empty      # the banner is there before any data is
    runner.run_xbrl(lab, symbols=('AAPL',), environ=AGENT, transport=Fake(routes()), clock=CLOCK, max_filings=3)
    runner.run_earnings(lab, symbols=('AAPL',), environ=AGENT, transport=Fake(routes()), clock=CLOCK)
    state = view.load(path=lab.path)
    html = firm_lab_page.render({'firm_lab': state})
    facts = html[html.index('id="fl-fundamentals"'):html.index('id="fl-earnings"')]
    assert '<h2>Fundamentals readiness</h2>' in facts and 'SEC XBRL company facts (SEC EDGAR)' in facts and '<b>AAPL</b>' in facts
    assert 'revenue, gross profit, operating income, net income, diluted EPS, operating cash flow, capital expenditure' in facts
    assert 'total debt: NEEDS_COMPONENT_RULE (AAPL)' in facts and '>AVAILABLE</span>' in facts and '>PASS</span>' in facts
    assert f'CONFIRMED {state["fundamentals"]["companies"][0]["accepted"]}' in facts and '10-Q 2026-06-27, 10-Q 2026-03-28, 10-K 2025-09-27' in facts
    assert state['fundamentals']['restatements'] == 1 and state['fundamentals']['rejected_runs'] == 0 and state['fundamentals']['unresolved'] == 3
    events = html[html.index('id="fl-earnings"'):html.index('id="fl-baseline"')]
    assert '<h2>Earnings events</h2>' in events and 'FACTUAL EVENT DATA ONLY — NO EARNINGS SIGNAL' in events
    assert '<dt>Transcripts</dt><dd><span class="cat cat-stop">UNAVAILABLE</span> none is collected</dd>' in events
    assert '<dt>Signal or model</dt><dd><b>NONE</b>' in events and '<dt>Events stored</dt><dd>3</dd>' in events
    row = events[events.index(E_Q3) - 900:events.index(E_Q3) + 900]
    assert '2026-06-27' in row and '2026-07-30' in row and '4:30 PM ET' in row and '4:00 PM ET or later' in row
    # the reported values come from the periodic report, with that report's own acceptance time, not from the release
    assert 'revenue 94,036,000,000 USD (3M)' in events and 'diluted EPS 1.68 USD/shares (3M)' in events
    assert f'from periodic report {Q3}, accepted Fri Jul 31, 6:01 PM ET' in events
    assert 'href="https://www.sec.gov/Archives/edgar/data/320193/000032019326000079/a8-kex991q3202606272026.htm"' in events
    assert 'release document unavailable' in events                                           # the one filing that names no exhibit
    # the year-end event shows the full-year figures of its 10-K, labelled as twelve months
    assert state['earnings_events']['events'][-1]['reported_values']['revenue']['period_type'] == '12M'
    lowered = (facts + events).lower()
    for word in ('sentiment', 'bullish', 'bearish', 'beat', 'miss', 'surprise', 'expected', 'consensus', 'outperform', 'buy ', 'sell ', '<form', '<button',
                 '<script', 'recommend'):
        assert word not in lowered.replace('no sentiment, tone, surprise, score or prediction exists', ''), word
    assert state['fills'] == 0 and state['firm_trading_trial'] == 'NOT REGISTERED' and state['mode'] == 'BUILD_OBSERVE'
    # a database from before this checkpoint still renders: the new sections say nothing is stored
    old = dict(state, fundamentals=None, earnings_events=None, benchmark_readiness=None, total_return=None)
    assert 'No earnings-release filing is stored yet.' in firm_lab_page.render({'firm_lab': old})


def test_the_new_research_modules_cannot_trade_and_cannot_reach_the_network_themselves():
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    banned = ('agents.paper', 'agents.orders', 'agents.execution', 'broker', 'broker_proxy', 'risk', 'agents.inbox', 'agents.codex_bridge',
              'agents.isolated_session', 'robin_stocks', 'alpaca')
    for name in ('fundamentals.py', 'ixbrl.py', 'total_return.py'):                           # pure: no network, no file, no database
        tree = ast.parse((root / 'firm_lab' / name).read_text())
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
                   {('.' * n.level) + (n.module or '') for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert imported <= {'__future__', 'dataclasses', 'datetime', 'decimal', 'html', 're', '.treasury'}, (name, imported)
    for name in ('xbrl.py', 'earnings.py', 'distributions.py'):                               # collectors: Firm Lab and the standard library only
        tree = ast.parse((root / 'firm_lab_collectors' / name).read_text())
        modules = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
                  {n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and not n.level}
        assert not [m for m in modules if m.split('.')[0] in ('agents', 'urllib', 'socket', 'http', 'ssl', 'subprocess') or m.startswith(banned)], (name, modules)
        text = (root / 'firm_lab_collectors' / name).read_text()
        assert 'self.transport.get(' in text and 'post(' not in text.lower() and 'sqlite3' not in text
    hosts = (root / 'firm_lab_collectors' / 'distributions.py').read_text()
    assert "VANGUARD_HOST = 'investor.vanguard.com'" in hosts and 'robinhood' not in hosts.lower()
    assert 'run_xbrl' in runner.RUNS['xbrl'].__name__ and set(runner.RUNS) == {'edgar', 'xbrl', 'earnings', 'distributions', 'massive', 'sharadar',
                                                                               'thetadata', 'treasury'}
    for path in sorted((root / 'agents').rglob('*.py')):                                      # the trading side never imports a collector
        if path.name != 'firm_lab_page.py':
            assert 'firm_lab_collectors' not in path.read_text(errors='ignore'), path
    assert not list(root.glob('**/*firm_lab*.plist')) and not list(root.glob('**/*collector*.plist'))      # nothing schedules a collector
