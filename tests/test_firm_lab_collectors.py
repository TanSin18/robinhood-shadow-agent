"""Checkpoint 3: the research data collectors. Every provider is exercised against fixture responses; no test opens a
network connection. What is proven here: raw data is validated, timestamped and stored with provenance or refused
whole; nothing is repaired or invented; and a collector cannot trade."""
import ast
import io
import json
import re
import sqlite3
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agents.desk import firm_lab_page
from firm_lab import boundary, capabilities, crosscheck, quality, rawstore, schemas, view
from firm_lab.errors import FirmLabError, NoFillInBuildObserve
from firm_lab.providers import OK, REJECTED, UNAVAILABLE
from firm_lab.store import FORBIDDEN_TABLE_WORDS, FirmLabStore
from firm_lab_collectors import cli, config, edgar, massive, runner, sharadar, thetadata
from firm_lab_collectors import treasury as treasury_source
from firm_lab_collectors.transport import HttpTransport, Response, TransportRefused, redact

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)
CLOCK = lambda: NOW
AGENT = {'FIRM_LAB_SEC_USER_AGENT': 'Example Research research@example.com'}
SECRET = 'SECRET-KEY-9f3a7c21'


def _lab(tmp_path):
    lab = FirmLabStore(tmp_path / 'diag' / 'firm_lab' / 'firm_lab.db')
    capabilities.seed(lab, NOW)
    return lab


def _rows(lab, table, columns='*', where=''):
    with lab.connect() as db:
        db.row_factory = sqlite3.Row
        return [dict(r) for r in db.execute(f'SELECT {columns} FROM {table} {where} ORDER BY id')]


def _codes(result):
    return sorted({i.code for i in result.issues})


class Fake:
    """Stands in for the network. ``routes`` is a list of (text the URL must contain, status, body); the first match answers."""

    def __init__(self, routes, at=None):
        self.routes, self.calls, self.requests, self.at = list(routes), [], 0, at or NOW

    def get(self, url, headers=None):
        self.requests += 1
        self.calls.append((url, dict(headers or {})))
        for key, status, body in self.routes:
            if key in url:
                raw = body if isinstance(body, bytes) else body.encode() if isinstance(body, str) else json.dumps(body).encode()
                return Response(status, raw if status == 200 else b'', redact(url), self.at.isoformat(), '' if status == 200 else f'HTTP {status}', {})
        return Response(404, b'', redact(url), self.at.isoformat(), 'HTTP 404', {})


# ====================================================================================================== transport
class _Reply(io.BytesIO):
    status = 200

    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = __import__('email').message_from_string(''.join(f'{k}: {v}\n' for k, v in (headers or {}).items()))


class _Opener:
    def __init__(self, answer):
        self.answer, self.seen = answer, []

    def open(self, request, timeout=None):
        self.seen.append(request)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_transport_only_reaches_named_https_hosts_and_never_stores_a_secret():
    opener = _Opener(_Reply(b'{}'))
    net = HttpTransport(['data.sec.gov'], user_agent='Example research@example.com', opener=opener, min_interval=0)
    for url in ('http://data.sec.gov/x', 'https://evil.example/x', 'https://data.sec.gov.evil.example/x', 'ftp://data.sec.gov/x',
                'http://127.0.0.1:25503/v3/x', 'https://api.robinhood.com/orders/'):
        with pytest.raises(TransportRefused):
            net.get(url)
    assert not opener.seen and net.requests == 0                                      # a refused request is never sent
    reply = net.get('https://data.sec.gov/x?api_key=' + SECRET + '&ticker=AAPL', {'Authorization': 'Bearer ' + SECRET})
    assert reply.ok and SECRET not in reply.url and 'api_key=REDACTED' in reply.url and 'ticker=AAPL' in reply.url
    sent = opener.seen[0]
    assert sent.get_method() == 'GET' and sent.get_header('User-agent') == 'Example research@example.com'
    assert redact('https://h/p?token=abc&key=def&x=1') == 'https://h/p?token=REDACTED&key=REDACTED&x=1'
    packed = HttpTransport(['data.sec.gov'], opener=_Opener(_Reply(__import__('gzip').compress(b'{"cik": "1"}'), {'content-encoding': 'gzip'})), min_interval=0)
    assert packed.get('https://data.sec.gov/y').body == b'{"cik": "1"}'                    # compressed answers are read whatever the header's case
    local = HttpTransport(['127.0.0.1:25503'], opener=_Opener(_Reply(b'[]')), min_interval=0)
    assert local.get('http://127.0.0.1:25503/v3/option/list/expirations?symbol=SPY').ok      # plain http only for the local terminal
    with pytest.raises(TransportRefused):
        local.get('http://127.0.0.1:9999/v3/x')


def test_transport_paces_requests_and_does_not_retry_a_failure():
    waits, now = [], [100.0]
    opener = _Opener(urllib.error.HTTPError('https://data.sec.gov/x', 429, 'Too Many Requests', {}, io.BytesIO(b'slow down')))
    net = HttpTransport(['data.sec.gov'], opener=opener, min_interval=0.5, clock=lambda: now[0], sleep=waits.append)
    first = net.get('https://data.sec.gov/x')
    assert first.status == 429 and not first.ok and first.error == 'HTTP 429' and len(opener.seen) == 1      # one attempt, no loop
    net.get('https://data.sec.gov/x')
    assert waits == [0.5] and len(opener.seen) == 2                                    # the second request waited its turn
    down = HttpTransport(['data.sec.gov'], opener=_Opener(urllib.error.URLError('no route')), min_interval=0).get('https://data.sec.gov/x')
    assert down.status == 0 and down.error == 'URLError' and down.body == b''


def test_configuration_reports_booleans_only_and_refuses_a_user_agent_without_a_contact():
    env = {'FIRM_LAB_SEC_USER_AGENT': 'NoContactHere', 'FIRM_LAB_MASSIVE_API_KEY': SECRET, 'FIRM_LAB_SHARADAR_API_KEY': SECRET,
           'FIRM_LAB_SHARADAR_CHANNEL': 'carrier-pigeon', 'FIRM_LAB_THETADATA_TERMINAL': 'yes'}
    assert config.sec_user_agent(env) is None and config.sec_user_agent({}) is None
    assert config.sec_user_agent(AGENT) == 'Example Research research@example.com'
    states = config.states(env)
    assert states == {'SEC EDGAR': False, 'Massive': True, 'Sharadar': False, 'ThetaData': False, 'U.S. Treasury Fiscal Data': True}
    assert SECRET not in json.dumps(states) and all(isinstance(v, bool) for v in states.values())
    assert config.states({}) == {'SEC EDGAR': False, 'Massive': False, 'Sharadar': False, 'ThetaData': False, 'U.S. Treasury Fiscal Data': True}


# ====================================================================================================== SEC EDGAR
TICKERS = {'0': {'cik_str': 1045810, 'ticker': 'NVDA', 'title': 'NVIDIA CORP'}, '1': {'cik_str': 320193, 'ticker': 'AAPL', 'title': 'Apple Inc.'}}
FUNDS = {'fields': ['cik', 'seriesId', 'classId', 'symbol'], 'data': [[36405, 'S000002848', 'C000007808', 'VTI']]}
# (accession, form, filing date, header New York clock, JSON text)
NVDA_FILINGS = (
    ('0001045810-26-000101', '10-Q', '2026-08-27', '20260827162015', '2026-08-27T20:20:15.000Z'),      # JSON really is UTC
    ('0001045810-26-000090', '8-K', '2026-08-27', '20260827162101', '2026-08-27T16:21:01.000Z'),       # JSON is the New York clock with a Z
    ('0001045810-26-000007', '4', '2026-01-15', '20260115083000', '2026-01-15T13:30:00.000Z'),         # winter: UTC-5
)


def _edgar_routes(filings=NVDA_FILINGS, *, cik=1045810, json_cik='0001045810', headers=True, drop=None, report_date='2026-07-26'):
    recent = {'accessionNumber': [f[0] for f in filings], 'form': [f[1] for f in filings], 'filingDate': [f[2] for f in filings],
              'acceptanceDateTime': [f[4] for f in filings], 'primaryDocument': [f'doc{i}.htm' for i, _ in enumerate(filings)],
              'reportDate': [report_date if f[1] == '10-Q' else '' for f in filings], 'items': ['' for _ in filings]}
    if drop:
        recent[drop] = recent[drop][:-1]
    routes = [('company_tickers.json', 200, TICKERS), ('company_tickers_mf.json', 200, FUNDS),
              (f'CIK{cik:010d}.json', 200, {'cik': json_cik, 'name': 'NVIDIA CORP', 'filings': {'recent': recent, 'files': []}})]
    if headers:
        routes += [(f[0] + '.hdr.sgml', 200, f'<SEC-HEADER>{f[0]}.hdr.sgml : 20260827\n<ACCEPTANCE-DATETIME>{f[3]}\n<TYPE>{f[1]}\n') for f in filings]
    return routes


def _filings(routes, symbol='NVDA', **kw):
    provider = edgar.EdgarFilingsProvider(Fake(routes), **kw)
    return provider, provider.filings(symbol, start='2025-10-02', end='2026-10-02', now=CLOCK)


def test_edgar_acceptance_time_is_the_filing_header_converted_to_utc_whichever_way_the_json_was_written():
    provider, result = _filings(_edgar_routes())
    assert result.status == OK and [r['accession_number'] for r in result.records()] == [f[0] for f in NVDA_FILINGS]
    q, k, four = result.records()
    assert q['accepted_timestamp'] == '2026-08-27T20:20:15+00:00' and q['accepted_timestamp_basis'] == edgar.BASIS_UTC
    assert k['accepted_timestamp'] == '2026-08-27T20:21:01+00:00' and k['accepted_timestamp_basis'] == edgar.BASIS_EASTERN
    assert four['accepted_timestamp'] == '2026-01-15T13:30:00+00:00'                    # 08:30 New York in January is 13:30 UTC
    for record, source in zip(result.records(), NVDA_FILINGS):
        assert record['accepted_timestamp_raw'] == source[4] and record['header_acceptance_raw'] == source[3]      # both originals are kept as sent
        assert record['cik'] == '0001045810' and record['instrument'] == 'NVDA' and record['form_type'] == source[1]
        assert record['url'].startswith('https://www.sec.gov/Archives/edgar/data/1045810/' + source[0].replace('-', '') + '/')
        assert record['ingestion_timestamp'] == NOW.isoformat()
    assert result.provenance.provider == 'SEC EDGAR' and result.provenance.source_id.endswith('CIK0001045810.json') and result.provenance.content_hash
    # filing metadata only: nothing from a document body, and no interpretation
    assert not {'text', 'body', 'summary', 'sentiment', 'score', 'tone'} & set(q)


# The two filings refused on the first live run (2026-10-02): the JSON time is the header time + 4 hours, matching neither reading.
LIVE_CONFLICTS = {'SOXX': (('0001193125-26-410688', '497K', '2026-10-01', '20261001161641', '2026-10-02T00:16:41.000Z'),),
                  'AAPL': (('0001140361-26-038307', '4', '2026-10-01', '20261001183011', '2026-10-02T02:30:11.000Z'),)}


def test_edgar_header_is_authoritative_when_the_json_disagrees_and_the_json_value_is_kept():
    conflict = (('0001045810-26-000101', '10-Q', '2026-08-27', '20260827162015', '2026-08-27T18:20:15.000Z'),) + NVDA_FILINGS[1:]
    _, result = _filings(_edgar_routes(conflict))
    assert result.status == OK and not result.issues                                    # the filing is not discarded because the JSON disagrees
    flagged, eastern, winter = result.records()
    assert flagged['acceptance_time_conflict'] is True and flagged['accepted_timestamp_basis'] == edgar.BASIS_CONFLICT
    assert flagged['accepted_timestamp_header'] == '2026-08-27T20:20:15+00:00'          # 16:20:15 New York, from the filing header
    assert flagged['accepted_timestamp'] == flagged['accepted_timestamp_header']        # the known-at Firm Lab uses is the header time
    assert flagged['accepted_timestamp_json'] == '2026-08-27T18:20:15.000Z' == flagged['accepted_timestamp_raw']      # exactly as the SEC sent it
    assert flagged['acceptance_time_json_offset_seconds'] == -7200 and flagged['header_acceptance_raw'] == '20260827162015'
    # no silent repair: the JSON value is not moved to agree with the header, and the header value is not moved toward the JSON
    assert '18:20:15' in flagged['accepted_timestamp_json'] and '18:20:15' not in flagged['accepted_timestamp']
    assert flagged['accepted_timestamp_json'] not in (flagged['accepted_timestamp'], '2026-08-27T20:20:15.000Z', '2026-08-27T16:20:15.000Z')
    for agreeing, offset in ((eastern, -14400), (winter, 0)):                           # filings whose JSON agrees are not flagged
        assert agreeing['acceptance_time_conflict'] is False and agreeing['acceptance_time_json_offset_seconds'] == offset
        assert agreeing['accepted_timestamp'] == agreeing['accepted_timestamp_header'] and agreeing['accepted_timestamp_json'].endswith('Z')
    assert edgar.EdgarFilingsProvider.reconcile('x', '2026-08-27T20:20:15.000Z', '20260827162015',
                                                datetime(2026, 8, 27, 20, 20, 15, tzinfo=timezone.utc)) == (edgar.BASIS_UTC, False, 0)


def test_edgar_still_refuses_what_it_cannot_verify_and_a_record_that_was_tampered_with():
    provider, result = _filings(_edgar_routes(headers=False))                           # neither the header file nor the header page exists
    assert result.status == REJECTED and _codes(result) == ['ACCEPTANCE_TIME_UNVERIFIED']
    with pytest.raises(FirmLabError):
        result.records()                                                                # nothing is kept from a refused response
    asked = [u for u, _ in provider.transport.calls if '0001045810-26-000101' in u]
    assert [u.rsplit('/', 1)[1] for u in asked] == ['0001045810-26-000101.hdr.sgml', '0001045810-26-000101-index-headers.html']
    bad_clock = (('0001045810-26-000101', '10-Q', '2026-08-27', '20261345996100', '2026-08-27T20:20:15.000Z'),)
    assert _codes(_filings(_edgar_routes(bad_clock))[1]) == ['ACCEPTANCE_TIME_UNVERIFIED']
    not_a_time = (('0001045810-26-000101', '10-Q', '2026-08-27', '20260827162015', '2026-13-45T99:61:00.000Z'),)
    assert _codes(_filings(_edgar_routes(not_a_time))[1]) == ['MALFORMED_FILING']       # a JSON value that is no time at all is still refused
    # the same header served as the filing's header page (HTML-escaped) is accepted
    page = _edgar_routes(NVDA_FILINGS[:1], headers=False) + [('0001045810-26-000101-index-headers.html', 200,
                                                             '<pre>&lt;SEC-HEADER&gt;\n&lt;ACCEPTANCE-DATETIME&gt;20260827162015\n</pre>')]
    _, result = _filings(page)
    assert result.status == OK and result.records()[0]['accepted_timestamp'] == '2026-08-27T20:20:15+00:00'
    # validation itself refuses a record whose known-at is not the header time, or whose JSON text was rewritten
    good = dict(result.records()[0])
    check = lambda record: quality.validate('filings', [record], now=NOW, provenance=result.provenance, expected_instrument='NVDA').codes()
    assert check(good) == []
    assert check(dict(good, accepted_timestamp='2026-08-27T18:20:15+00:00')) == ['KNOWN_AT_NOT_HEADER']       # timed by the JSON instead of the header
    assert check(dict(good, accepted_timestamp_json='2026-08-27T20:20:15+00:00')) == ['JSON_TIME_REWRITTEN']  # "tidied" JSON text
    assert 'MISSING_FIELD' in check({k: v for k, v in good.items() if k != 'acceptance_time_conflict'})
    assert 'VALUE_NOT_ALLOWED' in check(dict(good, acceptance_time_conflict='maybe'))


def test_the_live_soxx_and_aapl_conflicts_are_now_accepted_flagged_and_visible(tmp_path):
    lab = _lab(tmp_path)
    tickers = dict(TICKERS, **{'2': {'cik_str': 1100663, 'ticker': 'SOXX', 'title': 'iShares Trust'}})
    routes = [('company_tickers.json', 200, tickers)]
    for symbol, cik in (('SOXX', 1100663), ('AAPL', 320193)):
        routes += [r for r in _edgar_routes(LIVE_CONFLICTS[symbol], cik=cik, json_cik=str(cik)) if 'company_tickers' not in r[0]]
    routes += [r for r in _edgar_routes() if 'company_tickers' not in r[0]]
    report = runner.run_edgar(lab, symbols=('NVDA', 'SOXX', 'AAPL'), environ=AGENT, transport=Fake(routes), clock=CLOCK)
    assert [(r['status'], r['stored'], r['flags']) for r in report['runs']] == [(OK, 3, {}), (OK, 1, {'ACCEPTANCE_TIME_CONFLICT': 1}),
                                                                             (OK, 1, {'ACCEPTANCE_TIME_CONFLICT': 1})]
    assert lab.capability('sec_filings') == 'AVAILABLE'                                 # every symbol of the sample ingested
    stored = {r['instrument']: r for r in _rows(lab, 'filing_observations') if r['instrument'] != 'NVDA'}
    soxx, aapl = stored['SOXX'], stored['AAPL']
    assert soxx['accepted_timestamp_header'] == soxx['accepted_timestamp'] == '2026-10-01T20:16:41+00:00'      # 16:16:41 New York
    assert soxx['accepted_timestamp_json'] == '2026-10-02T00:16:41.000Z' and soxx['acceptance_time_conflict'] == 'true'
    assert aapl['accepted_timestamp_header'] == '2026-10-01T22:30:11+00:00' and aapl['accepted_timestamp_json'] == '2026-10-02T02:30:11.000Z'
    assert soxx['acceptance_time_json_offset_seconds'] == aapl['acceptance_time_json_offset_seconds'] == '14400'
    assert {r['acceptance_time_conflict'] for r in _rows(lab, 'filing_observations') if r['instrument'] == 'NVDA'} == {'false'}
    # the conflict is in the data-quality record of the run ...
    runs = {r['instrument']: json.loads(r['diagnostics_json']) for r in _rows(lab, 'provider_runs')}
    assert runs['SOXX']['acceptance_time_conflicts'] == [{'accession_number': '0001193125-26-410688', 'form_type': '497K', 'filing_date': '2026-10-01',
                                                         'accepted_timestamp_json': '2026-10-02T00:16:41.000Z',
                                                         'accepted_timestamp_header': '2026-10-01T20:16:41+00:00', 'json_minus_header_seconds': 14400}]
    assert runs['NVDA']['acceptance_time_conflicts'] == []
    # ... in the summary, and on the page
    assert rawstore.summary(lab)['filing_observations']['flags'] == {'ACCEPTANCE_TIME_CONFLICT': 2}
    sec = _cells(firm_lab_page.render({'firm_lab': view.load(path=lab.path)}), 'SEC filings')
    assert sec['Capability'] == 'AVAILABLE' and sec['Validation'].startswith('PASS') and sec['Stored'].startswith('5 ')
    assert sec['Quality failures and flags'].startswith('Kept and flagged: ACCEPTANCE_TIME_CONFLICT × 2') and 'header time is used and both are stored' in sec['Quality failures and flags']
    # known-at for anything that reads filings is the header time
    with lab.connect() as db:
        known = dict(db.execute("SELECT instrument, accepted_timestamp FROM filing_observations WHERE acceptance_time_conflict='true'").fetchall())
    assert known == {'SOXX': '2026-10-01T20:16:41+00:00', 'AAPL': '2026-10-01T22:30:11+00:00'}


def test_a_filing_table_from_the_first_live_run_is_extended_without_rewriting_its_rows(tmp_path):
    path = tmp_path / 'diag' / 'firm_lab' / 'firm_lab.db'
    path.parent.mkdir(parents=True)
    db = sqlite3.connect(path)                                                           # the table exactly as the 2026-10-02 10:23 run left it
    db.execute("CREATE TABLE filing_observations (id INTEGER PRIMARY KEY, instrument TEXT NOT NULL, cik TEXT NOT NULL, accession_number TEXT NOT NULL, "
               "form_type TEXT NOT NULL, filing_date TEXT NOT NULL, report_date TEXT, accepted_timestamp TEXT NOT NULL, accepted_timestamp_raw TEXT NOT NULL, "
               "accepted_timestamp_basis TEXT NOT NULL, header_acceptance_raw TEXT, url TEXT NOT NULL, primary_document TEXT, items TEXT, entity_name TEXT, "
               "series_id TEXT, class_id TEXT, provider TEXT NOT NULL, source_id TEXT NOT NULL, source_timestamp TEXT NOT NULL, known_at TEXT NOT NULL, "
               "ingested_at TEXT NOT NULL, schema_version TEXT NOT NULL, content_hash TEXT NOT NULL, run_id INTEGER NOT NULL, "
               "UNIQUE (accession_number, instrument, content_hash))")
    old = ('NVDA', '0001045810', '0001045810-26-000101', '10-Q', '2026-08-27', '2026-07-26', '2026-08-27T20:20:15+00:00', '2026-08-27T20:20:15.000Z',
           edgar.BASIS_UTC, '20260827162015', 'https://www.sec.gov/x', 'doc0.htm', None, 'NVIDIA CORP', None, None, 'SEC EDGAR', 's', NOW.isoformat(),
           NOW.isoformat(), NOW.isoformat(), 'firm-lab-data-v1', 'oldhash', 1)
    db.execute('INSERT INTO filing_observations VALUES (NULL,' + ','.join('?' * len(old)) + ')', old)
    db.commit()
    db.close()
    lab = FirmLabStore(path)
    capabilities.seed(lab, NOW)
    before = _rows(lab, 'filing_observations')[0]
    assert before['accepted_timestamp_header'] is None and before['acceptance_time_conflict'] is None and before['content_hash'] == 'oldhash'      # not back-filled
    with lab.connect() as db:
        change = [json.loads(r[0]) for r in db.execute("SELECT payload_json FROM events WHERE kind='SCHEMA_CHANGE'") if 'columns' in json.loads(r[0])]
    assert change == [{'table': 'filing_observations', 'change': 'columns added; existing rows not rewritten', 'rows_before': 1,
                       'columns': ['accepted_timestamp_header', 'accepted_timestamp_json', 'acceptance_time_conflict', 'acceptance_time_json_offset_seconds']}]
    runner.run_edgar(lab, symbols=('NVDA',), environ=AGENT, transport=Fake(_edgar_routes()), clock=CLOCK)
    rows = _rows(lab, 'filing_observations')
    assert len(rows) == 4 and rows[0] == before                                          # the old row is untouched; the new version sits beside it
    summary = rawstore.summary(lab)['filing_observations']
    assert summary['rows'] == 4 and summary['distinct'] == 3                             # four stored rows, three filings
    sec = _cells(firm_lab_page.render({'firm_lab': view.load(path=lab.path)}), 'SEC filings')
    assert sec['Stored'].startswith('3 ') and '4 stored rows including earlier versions' in sec['Stored']
    # fetched again later: the same filings are recognised as the same records, whatever the fetch time
    again = runner.run_edgar(lab, symbols=('NVDA',), environ=AGENT, transport=Fake(_edgar_routes(), at=NOW + timedelta(hours=3)),
                             clock=lambda: NOW + timedelta(hours=3))
    assert again['runs'][0]['stored'] == 0 and again['runs'][0]['duplicates'] == 3 and len(_rows(lab, 'filing_observations')) == 4


def test_edgar_refuses_malformed_filings_and_duplicate_accessions():
    assert _codes(_filings(_edgar_routes(drop='form'))[1]) == ['MALFORMED_FILING']                   # arrays of different lengths
    odd = (('1045810-26-101', '10-Q', '2026-08-27', '20260827162015', '2026-08-27T20:20:15.000Z'),)
    assert _codes(_filings(_edgar_routes(odd))[1]) == ['MALFORMED_FILING']                            # accession number not in the SEC form
    text = (('0001045810-26-000101', '10-Q', '2026-08-27', '20260827162015', '27 Aug 2026 4:20pm'),)
    assert _codes(_filings(_edgar_routes(text))[1]) == ['MALFORMED_FILING']
    twice = NVDA_FILINGS[:1] * 2
    result = _filings(_edgar_routes(twice))[1]
    assert result.status == REJECTED and 'DUPLICATE_RECORD' in _codes(result)
    assert _filings([('company_tickers.json', 200, TICKERS), ('CIK0001045810.json', 200, 'not json at all')])[1].status == REJECTED
    no_index = [('company_tickers.json', 200, TICKERS), ('CIK0001045810.json', 200, {'cik': '1045810', 'filings': {}})]
    assert _codes(_filings(no_index)[1]) == ['MALFORMED_FILING']


def test_edgar_identity_comes_from_the_sec_and_is_never_guessed():
    wrong = _filings(_edgar_routes(json_cik='0000320193'))[1]                            # asked for NVIDIA's CIK, answer is about another
    assert wrong.status == REJECTED and _codes(wrong) == ['CONFLICTING_INSTRUMENT_IDENTITY']
    provider, unknown = _filings(_edgar_routes(), symbol='ZZZZ')
    assert unknown.status == UNAVAILABLE and 'no CIK' in unknown.reason and 'none is guessed' in unknown.reason
    assert not [u for u, _ in provider.transport.calls if 'submissions' in u]            # nothing was fetched for a made-up identity
    fund_filing = (('0000036405-26-000300', '485BPOS', '2026-04-28', '20260428101500', '2026-04-28T14:15:00.000Z'),)
    _, fund = _filings(_edgar_routes(fund_filing, cik=36405, json_cik='36405'), symbol='VTI')
    record = fund.records()[0]
    assert fund.status == OK and record['cik'] == '0000036405' and record['series_id'] == 'S000002848' and record['class_id'] == 'C000007808'


@pytest.mark.parametrize('status', [403, 429])
def test_edgar_rate_limit_or_refusal_is_unavailable_and_is_not_retried(tmp_path, status):
    lab = _lab(tmp_path)
    net = Fake([('company_tickers.json', status, b'')])
    report = runner.run_edgar(lab, symbols=('NVDA',), environ=AGENT, transport=net, clock=CLOCK)
    assert net.requests == 1                                                             # one request, no retry, no second endpoint
    assert report['connection'] == 'ERROR' and str(status) in report['detail'] and report['runs'][0]['status'] == UNAVAILABLE
    assert not _rows(lab, 'filing_observations') and lab.capability('sec_filings') == 'PARTIAL_EXISTING'
    run = _rows(lab, 'provider_runs')[0]
    assert run['status'] == UNAVAILABLE and run['stored'] == 0 and run['provider'] == 'SEC EDGAR'


def test_edgar_without_a_declared_user_agent_fetches_nothing(tmp_path):
    lab = _lab(tmp_path)
    net = Fake(_edgar_routes())
    for env in ({}, {'FIRM_LAB_SEC_USER_AGENT': 'anonymous'}):
        report = runner.run_edgar(lab, environ=env, transport=net, clock=CLOCK)
        assert report['connection'] == 'NOT_CONFIGURED' and 'activation required' in report['detail'] and report['runs'] == []
    assert net.requests == 0 and not _rows(lab, 'provider_runs') and lab.capability('sec_filings') == 'PARTIAL_EXISTING'
    link = rawstore.summary(lab)['connections']['SEC EDGAR']
    assert link['state'] == 'NOT_CONFIGURED' and 'example.com' not in json.dumps(link)


def test_edgar_sample_is_stored_with_provenance_promoted_on_evidence_and_taken_back_when_validation_fails(tmp_path):
    lab = _lab(tmp_path)
    assert lab.capability('sec_filings') == 'PARTIAL_EXISTING'
    rawstore.set_connection(lab, 'SEC EDGAR', 'CONFIGURED', 'declared', NOW)
    assert capabilities.confirm_provider_data(lab, NOW)['sec_filings'] == 'PARTIAL_EXISTING'       # configuration alone promotes nothing
    report = runner.run_edgar(lab, symbols=('NVDA',), environ=AGENT, transport=Fake(_edgar_routes()), clock=CLOCK)
    assert report['connection'] == 'ACTIVE' and report['runs'][0] == {**report['runs'][0], 'status': OK, 'received': 3, 'stored': 3, 'duplicates': 0}
    stored = _rows(lab, 'filing_observations')
    assert len(stored) == 3 and {r['accession_number'] for r in stored} == {f[0] for f in NVDA_FILINGS}
    for row in stored:                                                                   # the provenance standard, on every row
        for column in ('provider', 'source_id', 'source_timestamp', 'known_at', 'ingested_at', 'schema_version', 'content_hash', 'run_id'):
            assert row[column], column
        assert row['provider'] == 'SEC EDGAR' and row['accepted_timestamp'].endswith('+00:00') and row['accepted_timestamp_raw'].endswith('Z')
    assert lab.capability('sec_filings') == 'AVAILABLE' and report['capabilities']['sec_filings'] == 'AVAILABLE'
    with lab.connect() as db:
        event = json.loads(db.execute("SELECT payload_json FROM events WHERE kind='CAPABILITY_STATUS' ORDER BY id DESC LIMIT 1").fetchone()[0])
    assert event['to'] == 'AVAILABLE' and event['evidence']['records'] == 3 and event['evidence']['validation_passed'] is True
    assert event['evidence']['runs'][0]['instruments'] == ['NVDA'] and 'example.com' not in json.dumps(event)
    # the same sample again: identical rows are ignored, nothing is rewritten
    later = NOW + timedelta(minutes=5)
    again = runner.run_edgar(lab, symbols=('NVDA',), environ=AGENT, transport=Fake(_edgar_routes(), at=later), clock=lambda: later)
    assert again['runs'][0]['stored'] == 0 and again['runs'][0]['duplicates'] == 3 and len(_rows(lab, 'filing_observations')) == 3
    assert lab.capability('sec_filings') == 'AVAILABLE'
    # a later sample that fails validation takes the capability back; the rows already stored are not touched
    unverifiable = (('0001045810-26-000200', '8-K', '2026-09-30', '20260930170000', '2026-09-30T21:00:00.000Z'),)
    bad = runner.run_edgar(lab, symbols=('NVDA',), environ=AGENT, transport=Fake(_edgar_routes(unverifiable, headers=False)),
                           clock=lambda: NOW + timedelta(minutes=9))
    assert bad['runs'][0]['status'] == REJECTED and bad['runs'][0]['issues'] == ['ACCEPTANCE_TIME_UNVERIFIED'] and bad['runs'][0]['stored'] == 0
    assert lab.capability('sec_filings') == 'PARTIAL_EXISTING' and len(_rows(lab, 'filing_observations')) == 3
    summary = rawstore.summary(lab)['filing_observations']
    assert summary['rows'] == 3 and summary['rejected_issue_counts'] == {'ACCEPTANCE_TIME_UNVERIFIED': 1} and summary['last_run']['status'] == REJECTED
    assert summary['oldest'] == '2026-01-15T13:30:00+00:00' and summary['newest'] == '2026-08-27T20:21:01+00:00'


def test_one_refused_symbol_keeps_the_whole_sample_from_being_called_available(tmp_path):
    lab = _lab(tmp_path)
    routes = _edgar_routes() + [('CIK0000320193.json', 200, {'cik': '999', 'filings': {}})]         # AAPL's answer is about someone else
    report = runner.run_edgar(lab, symbols=('NVDA', 'AAPL'), environ=AGENT, transport=Fake(routes), clock=CLOCK)
    assert [r['status'] for r in report['runs']] == [OK, REJECTED] and len(_rows(lab, 'filing_observations')) == 3
    assert lab.capability('sec_filings') == 'PARTIAL_EXISTING'                           # good rows are kept; the capability is not claimed
    row = next(r for r in view.load(path=lab.path)['data_readiness'] if r['capability'] == 'sec_filings')
    assert row['validation'] == 'FAIL' and row['validation_issues'] == ['CONFLICTING_INSTRUMENT_IDENTITY'] and row['observations'] == 3


# ====================================================================================================== Massive
DAY = '2026-10-01'


def _ms(clock):
    return int(datetime.fromisoformat(f'{DAY}T{clock}-04:00').timestamp() * 1000)


def _bar(clock, o=668.1, h=668.4, l=668.0, c=668.2, v=1200, **over):
    return {'t': _ms(clock), 'o': o, 'h': h, 'l': l, 'c': c, 'v': v, 'vw': 668.2, 'n': 15, **over}


def _aggs(bars, ticker='SPY', **over):
    return {'ticker': ticker, 'status': 'OK', 'adjusted': False, 'queryCount': len(bars), 'resultsCount': len(bars), 'request_id': 'r1',
            'results': bars, **over}


GOOD_BARS = [_bar('08:00:00'), _bar('09:29:00'), _bar('09:30:00'), _bar('15:59:00', c=669.05, h=669.1), _bar('16:00:00'), _bar('19:59:00')]


def _bars(body, symbol='SPY', key=SECRET):
    net = Fake([('/v2/aggs/ticker/', 200, body)]) if not isinstance(body, Fake) else body
    provider = massive.MassiveMarketDataProvider(net, key)
    return provider, provider.bars_1m(symbol, session_date=DAY, now=CLOCK)


def test_massive_one_minute_bars_keep_their_timestamps_and_session():
    provider, result = _bars(_aggs(GOOD_BARS))
    assert result.status == OK
    bars = result.records()
    assert [b['session'] for b in bars] == ['pre_market', 'pre_market', 'regular', 'regular', 'post_market', 'post_market']
    assert bars[2]['bar_start'] == '2026-10-01T13:30:00+00:00' and bars[2]['bar_start_raw'] == str(_ms('09:30:00'))      # converted, and as sent
    assert {b['exchange_session_date'] for b in bars} == {DAY} and {b['interval'] for b in bars} == {'1m'}
    assert {b['feed'] for b in bars} == {'massive:sip-consolidated'} and {b['adjusted'] for b in bars} == {False}
    url, headers = provider.transport.calls[0]
    assert 'adjusted=false' in url and '/range/1/minute/2026-10-01/2026-10-01' in url and SECRET not in url          # the key travels in a header
    assert headers == {'Authorization': 'Bearer ' + SECRET} and SECRET not in result.provenance.source_id
    assert quality.missing_regular_minutes(bars) == {DAY: 388}                           # a diagnostic, not a failure: two regular minutes present
    # nothing derived: no relative volume, opening range or flow field is produced
    assert not {'rvol', 'relative_volume', 'opening_range', 'flow', 'signal'} & set(bars[0])


@pytest.mark.parametrize('bars,code', [
    ([_bar('09:30:00'), _bar('09:30:00')], 'DUPLICATE_RECORD'),
    ([_bar('09:31:00'), _bar('09:30:00')], 'NON_MONOTONIC_TIMESTAMPS'),
    ([_bar('09:30:00', h=667.0)], 'IMPOSSIBLE_VALUE'),                                   # high below low
    ([_bar('09:30:00', c=670.0)], 'IMPOSSIBLE_VALUE'),                                   # close outside low/high
    ([_bar('09:30:00', v=-5)], 'IMPOSSIBLE_VALUE'),
    ([_bar('09:30:00', o=0)], 'IMPOSSIBLE_VALUE'),
    ([_bar('03:15:00')], 'OUTSIDE_SESSION_HOURS'),
    ([_bar('09:30:00', c=None)], 'MISSING_FIELD'),
    ([{**_bar('09:30:00'), 't': 'yesterday'}], 'MALFORMED_RESPONSE'),
    ([], 'NOT_A_RECORD'),
])
def test_massive_bars_that_cannot_be_trusted_are_refused_whole(bars, code):
    result = _bars(_aggs(bars))[1]
    assert result.status == REJECTED and code in _codes(result)
    with pytest.raises(FirmLabError):
        result.records()


def test_massive_future_bars_wrong_ticker_adjusted_data_and_truncated_answers_are_refused():
    future = {**_bar('09:30:00'), 't': int((NOW + timedelta(hours=2)).timestamp() * 1000)}
    assert 'FUTURE_TIMESTAMP' in _codes(_bars(_aggs([future]))[1])
    assert _codes(_bars(_aggs(GOOD_BARS, ticker='SPYG'))[1]) == ['CONFLICTING_INSTRUMENT_IDENTITY']       # feed identity: the answer names the symbol
    assert _codes(_bars(_aggs(GOOD_BARS, adjusted=True))[1]) == ['ADJUSTMENT_MISMATCH']
    assert _codes(_bars(_aggs(GOOD_BARS, status='ERROR'))[1]) == ['MALFORMED_RESPONSE']
    elsewhere = _bars(_aggs(GOOD_BARS, next_url='https://elsewhere.example/v2/aggs/next'))[1]
    assert _codes(elsewhere) == ['MALFORMED_RESPONSE']                                   # a continuation on another host is not followed
    net = Fake([('/v2/aggs/ticker/', 200, _aggs(GOOD_BARS, next_url='https://api.massive.com/v2/aggs/ticker/SPY/next'))])
    provider = massive.MassiveMarketDataProvider(net, SECRET, max_pages=1)
    assert _codes(provider.bars_1m('SPY', session_date=DAY, now=CLOCK)) == ['INCOMPLETE_HISTORICAL_WINDOW']
    assert _bars('<html>maintenance</html>')[1].status == REJECTED


def _ns(clock, extra=0):
    return int(datetime.fromisoformat(f'{DAY}T{clock}-04:00').timestamp()) * 1_000_000_000 + extra


def _trade(clock='10:00:00', extra=123456789, **over):
    return {'sip_timestamp': _ns(clock, extra), 'participant_timestamp': _ns(clock, extra - 1000), 'price': 668.21, 'size': 100, 'exchange': 4,
            'conditions': [12, 37], 'id': '52983525029461', 'sequence_number': 1001, 'tape': 2, **over}


def _quote(clock='10:00:00', extra=5, **over):
    return {'sip_timestamp': _ns(clock, extra), 'participant_timestamp': _ns(clock, extra), 'bid_price': 668.2, 'bid_size': 300, 'bid_exchange': 11,
            'ask_price': 668.21, 'ask_size': 200, 'ask_exchange': 12, 'sequence_number': 2001, 'tape': 2, **over}


def _ticks(kind, rows, symbol='SPY'):
    net = Fake([(f'/v3/{kind}/', 200, {'status': 'OK', 'request_id': 'r2', 'results': rows})])
    provider = massive.MassiveMarketDataProvider(net, SECRET)
    method = provider.trades if kind == 'trades' else provider.quote_snapshots
    return provider, method(symbol, start=f'{DAY}T10:00:00-04:00', end=f'{DAY}T10:00:02-04:00', now=CLOCK)


def test_massive_trades_keep_nanosecond_time_and_malformed_trades_are_refused():
    provider, result = _ticks('trades', [_trade(), _trade(extra=223456789, id='52983525029462', sequence_number=1002)])
    assert result.status == OK
    trade = result.records()[0]
    assert trade['trade_timestamp_raw'] == str(_ns('10:00:00', 123456789)) and trade['trade_timestamp'] == '2026-10-01T14:00:00.123456+00:00'
    assert trade['participant_timestamp_raw'] == str(_ns('10:00:00', 123455789)) and trade['exchange'] == 4 and trade['feed'] == 'massive:sip-consolidated'
    url = provider.transport.calls[0][0]
    assert f'timestamp.gte={_ns("10:00:00")}' in url and f'timestamp.lt={_ns("10:00:02")}' in url and 'order=asc' in url
    for rows, code in (([{**_trade(), 'sip_timestamp': None}], 'MALFORMED_RESPONSE'), ([{**_trade(), 'sip_timestamp': '2026-10-01'}], 'MALFORMED_RESPONSE'),
                       ([_trade(price=0)], 'IMPOSSIBLE_VALUE'), ([_trade(price='n/a')], 'IMPOSSIBLE_VALUE'), ([_trade(size=-1)], 'IMPOSSIBLE_VALUE'),
                       ([_trade(id=None)], 'MISSING_FIELD'), ([_trade(exchange=None)], 'MISSING_FIELD'), ([_trade(), _trade()], 'DUPLICATE_RECORD'),
                       (['not a trade'], 'MALFORMED_RESPONSE'),
                       ([_trade(extra=900), _trade(extra=100, id='x2')], 'NON_MONOTONIC_TIMESTAMPS')):
        bad = _ticks('trades', rows)[1]
        assert bad.status == REJECTED and code in _codes(bad), code


def test_massive_crossed_quotes_are_refused_and_a_one_sided_quote_is_kept_as_sent():
    crossed = _ticks('quotes', [_quote(bid_price=668.30, ask_price=668.21)])[1]
    assert crossed.status == REJECTED and 'CROSSED_MARKET' in _codes(crossed)
    one_sided = _ticks('quotes', [_quote(), _quote(extra=9, ask_price=0, ask_size=0, sequence_number=2002)])[1]
    assert one_sided.status == OK and one_sided.records()[1]['ask'] == 0                 # "no offer" is not repaired into a price
    locked = _ticks('quotes', [_quote(bid_price=668.21, ask_price=668.21)])[1]
    assert locked.status == OK                                                           # bid equal to ask is allowed: bid <= ask
    assert 'IMPOSSIBLE_VALUE' in _codes(_ticks('quotes', [_quote(bid_size=-100)])[1])
    assert 'MISSING_FIELD' in _codes(_ticks('quotes', [_quote(bid_price=None)])[1])


def test_massive_without_a_key_stays_unavailable_and_with_one_the_key_is_never_stored(tmp_path, capsys):
    lab = _lab(tmp_path)
    net = Fake([('/v2/aggs/ticker/', 200, _aggs(GOOD_BARS))])
    report = runner.run_massive(lab, environ={}, transport=net, clock=CLOCK, session_date=DAY)
    assert report['connection'] == 'NOT_CONFIGURED' and 'Credentials required' in report['detail'] and net.requests == 0
    assert lab.capability('intraday_bars') == 'UNAVAILABLE' and not _rows(lab, 'intraday_bar_observations')        # nothing fabricated
    env = {'FIRM_LAB_MASSIVE_API_KEY': SECRET}
    for status, text in ((401, 'did not accept the API key'), (403, 'plan does not include'), (429, 'rate limit')):
        refused = runner.run_massive(lab, symbols=('SPY',), environ=env, transport=Fake([('/v2/aggs/', status, b'')]), clock=CLOCK,
                                     session_date=DAY, ticks=False)
        assert refused['connection'] == 'ERROR' and text in refused['detail'] and refused['runs'][0]['status'] == UNAVAILABLE
    assert lab.capability('intraday_bars') == 'UNAVAILABLE'
    # a plan with bars but without trades or quotes: bars are stored and validated, ticks stay unavailable
    lab.add_feature(instrument='SPY', feature_name='close', value='669.00', source='control_a_decision_capsule', source_timestamp=f'{DAY}T00:00:00+00:00',
                    known_at='2026-10-01T20:05:00+00:00', exchange_session_date=DAY, feature_version='v1')
    net = Fake([('/v2/aggs/ticker/', 200, _aggs(GOOD_BARS)), ('/v3/trades/', 403, b''), ('/v3/quotes/', 403, b'')])
    report = runner.run_massive(lab, symbols=('SPY',), environ=env, transport=net, clock=CLOCK, session_date=DAY)
    assert [(r['domain'], r['status']) for r in report['runs']] == [('intraday_bars', OK), ('trades', UNAVAILABLE), ('quotes', UNAVAILABLE)]
    assert report['capabilities']['intraday_bars'] == 'AVAILABLE' and report['capabilities']['tick_trades_quotes'] == 'UNAVAILABLE'
    assert len(_rows(lab, 'intraday_bar_observations')) == 6 and not _rows(lab, 'trade_observations') and not _rows(lab, 'quote_observations')
    diagnostics = json.loads(_rows(lab, 'provider_runs', where="WHERE domain='intraday_bars' AND status='OK'")[0]['diagnostics_json'])
    daily = diagnostics['daily_comparison']
    assert daily['stored_daily_close'] == '669.00' and daily['last_regular_bar_close'] == '669.05' and daily['difference'] == '0.05'
    assert 'diagnostic only' in daily['note'] and diagnostics['bars_by_session'] == {'pre_market': 2, 'regular': 2, 'post_market': 2}
    assert diagnostics['missing_regular_minutes'] == {DAY: 388}
    # the diagnostic changed nothing that was stored, and the key is nowhere: not in the database, not in the report
    assert lab.feature_history('SPY', 'close', 'v1')[0]['value'] == '669.00'
    assert SECRET.encode() not in lab.path.read_bytes() and SECRET not in json.dumps(report, default=str)
    assert cli.main(['massive', '--path', str(lab.path), '--session-date', DAY, '--symbols', 'spy', '--no-ticks'], environ=env,
                    transport=Fake([('/v2/aggs/ticker/', 200, _aggs(GOOD_BARS))])) == 0
    printed = capsys.readouterr().out
    assert SECRET not in printed and json.loads(printed)['status']['configured_in_this_shell']['Massive'] is True


def test_validated_ticks_are_stored_raw_and_promote_only_when_both_trades_and_quotes_pass(tmp_path):
    lab = _lab(tmp_path)
    env = {'FIRM_LAB_MASSIVE_API_KEY': SECRET}
    good = [('/v2/aggs/ticker/', 200, _aggs(GOOD_BARS)), ('/v3/trades/', 200, {'status': 'OK', 'results': [_trade()]}),
            ('/v3/quotes/', 200, {'status': 'OK', 'results': [_quote(bid_price=668.30, ask_price=668.21)]})]
    report = runner.run_massive(lab, symbols=('SPY',), environ=env, transport=Fake(good), clock=CLOCK, session_date=DAY)
    assert [(r['domain'], r['status']) for r in report['runs']] == [('intraday_bars', OK), ('trades', OK), ('quotes', REJECTED)]
    assert len(_rows(lab, 'trade_observations')) == 1 and not _rows(lab, 'quote_observations')
    assert lab.capability('tick_trades_quotes') == 'UNAVAILABLE'                         # trades alone are not "trades and quotes"
    good[2] = ('/v3/quotes/', 200, {'status': 'OK', 'results': [_quote()]})
    report = runner.run_massive(lab, symbols=('SPY',), environ=env, transport=Fake(good), clock=lambda: NOW + timedelta(minutes=1), session_date=DAY)
    assert lab.capability('tick_trades_quotes') == 'AVAILABLE' and report['runs'][1]['duplicates'] == 1
    trade, quote = _rows(lab, 'trade_observations')[0], _rows(lab, 'quote_observations')[0]
    assert trade['trade_timestamp_raw'] == str(_ns('10:00:00', 123456789)) and trade['conditions_json'] == '[12,37]' and trade['price'] == '668.21'
    assert quote['bid'] == '668.2' and quote['ask'] == '668.21' and quote['quote_timestamp_raw'] == str(_ns('10:00:00', 5))
    # derived intraday measures stay unavailable: raw storage is not a feature
    for name in ('vwap', 'opening_range', 'time_of_day_rvol', 'trade_flow', 'order_book'):
        assert lab.capability(name) == 'UNAVAILABLE', name


# ====================================================================================================== Sharadar
SF1_COLUMNS = ['ticker', 'dimension', 'calendardate', 'datekey', 'reportperiod', 'fiscalperiod', 'lastupdated', 'revenue', 'netinc', 'epsdil',
               'sharesbas', 'grossmargin', 'fxusd']


def _table(columns, rows):
    return {'datatable': {'data': rows, 'columns': [{'name': c, 'type': 'String'} for c in columns]}, 'meta': {'next_cursor_id': None}}


ARQ = _table(SF1_COLUMNS, [['AAPL', 'ARQ', '2026-06-30', '2026-07-31', '2026-06-27', '2026-Q3', '2026-08-01', 94036000000, 23434000000, 1.57,
                            14935826000, 0.465, 1],
                           ['AAPL', 'ARQ', '2026-03-31', '2026-05-02', '2026-03-28', '2026-Q2', '2026-08-01', 95359000000, 24780000000, 1.65,
                            15000000000, 0.471, 1]])
MRQ = _table(SF1_COLUMNS, [['AAPL', 'MRQ', '2026-06-30', '2026-06-27', '2026-06-27', '2026-Q3', '2026-08-01', 94036000000, 23434000000, 1.57,
                            14935826000, 0.465, 1],
                           ['AAPL', 'MRQ', '2026-03-31', '2026-03-28', '2026-03-28', '2026-Q2', '2026-09-15', 95400000000, 24790000000, 1.66,
                            15000000000, 0.472, 1]])                                     # the March quarter was later restated
TICKER_COLUMNS = ['table', 'permaticker', 'ticker', 'name', 'isdelisted', 'currency']
ACTION_COLUMNS = ['date', 'action', 'ticker', 'name', 'value', 'contraticker', 'contraname']
ACTIONS = _table(ACTION_COLUMNS, [['2026-08-11', 'dividend', 'AAPL', 'Apple Inc', 0.26, None, None],
                                  ['2026-06-09', 'split', 'AAPL', 'Apple Inc', 4, None, None],
                                  ['2026-05-01', 'relation', 'AAPL', 'Apple Inc', None, 'XYZ', 'Some Co']])


def _sharadar_routes(*, currency='USD', delisted='N', arq=ARQ, mrq=MRQ, actions=ACTIONS):
    return [('TICKERS.json', 200, _table(TICKER_COLUMNS, [['SF1', 199059, 'AAPL', 'Apple Inc', delisted, currency]])),
            ('dimension=ARQ', 200, arq), ('dimension=MRQ', 200, mrq), ('ACTIONS.json', 200, actions)]


def _fundamentals(routes, channel='nasdaq'):
    provider = sharadar.SharadarFundamentalsProvider(Fake(routes), SECRET, channel)
    return provider, provider.financial_statements('AAPL', known_at=NOW.isoformat(), now=CLOCK)


def test_sharadar_keeps_as_reported_and_restated_values_apart():
    provider, result = _fundamentals(_sharadar_routes())
    assert result.status == OK
    rows = result.records()
    march = {(r['reporting_basis'], r['metric']): r for r in rows if r['period_end'] == '2026-03-28'}
    assert str(march[('as_reported', 'revenue')]['value']) == '95359000000' and str(march[('restated', 'revenue')]['value']) == '95400000000'
    assert march[('as_reported', 'revenue')]['dimension'] == 'ARQ' and march[('restated', 'revenue')]['dimension'] == 'MRQ'
    # filing date: the provider's datekey for as-reported rows, kept as sent; restated rows are indexed to the period, so no filing date is claimed
    assert march[('as_reported', 'revenue')]['filing_date'] == march[('as_reported', 'revenue')]['provider_datekey'] == '2026-05-02'
    assert march[('restated', 'revenue')]['filing_date'] == 'UNAVAILABLE' and march[('restated', 'revenue')]['provider_datekey'] == '2026-03-28'
    assert {r['filing_timestamp'] for r in rows} == {'UNAVAILABLE'}                      # a date is never turned into an acceptance time
    assert {r['last_updated'] for r in rows} == {'2026-08-01', '2026-09-15'} and {r['fiscal_period'] for r in rows} == {'2026-Q2', '2026-Q3'}
    units = {r['metric']: (r['units'], r['currency']) for r in rows}
    assert units == {'revenue': ('currency', 'USD'), 'net_income': ('currency', 'USD'), 'eps_diluted': ('currency_per_share', 'USD'),
                     'shares_basic': ('shares', None), 'gross_margin': ('ratio', None), 'fx_to_usd': ('ratio', None)}
    assert {r['provider_instrument_id'] for r in rows} == {199059} and {r['known_at'] for r in rows} == {NOW.isoformat()}
    assert not {'score', 'rank', 'quality_score', 'value_score', 'composite'} & set(rows[0])           # raw facts only
    assert all(headers == {'x-api-token': SECRET} and SECRET not in url for url, headers in provider.transport.calls)


def test_sharadar_restated_rows_never_overwrite_as_reported_rows_in_storage(tmp_path):
    lab = _lab(tmp_path)
    env = {'FIRM_LAB_SHARADAR_API_KEY': SECRET, 'FIRM_LAB_SHARADAR_CHANNEL': 'nasdaq'}
    report = runner.run_sharadar(lab, symbols=('AAPL',), environ=env, transport=Fake(_sharadar_routes()), clock=CLOCK)
    assert [(r['domain'], r['status']) for r in report['runs']] == [('fundamentals', OK), ('corporate_actions', OK)]
    stored = _rows(lab, 'fundamental_observations', where="WHERE metric='revenue' AND period_end='2026-03-28'")
    assert {(r['dimension'], r['reporting_basis'], r['value'], r['filing_date']) for r in stored} == {
        ('ARQ', 'as_reported', '95359000000', '2026-05-02'), ('MRQ', 'restated', '95400000000', 'UNAVAILABLE')}
    # a later restatement arrives: it is stored beside what is already there, and the as-reported row is untouched
    later = _table(SF1_COLUMNS, [['AAPL', 'MRQ', '2026-03-31', '2026-03-28', '2026-03-28', '2026-Q2', '2026-11-20', 95500000000, 24790000000, 1.66,
                                  15000000000, 0.472, 1]])
    runner.run_sharadar(lab, symbols=('AAPL',), environ=env, transport=Fake(_sharadar_routes(mrq=later)), clock=lambda: NOW + timedelta(days=60))
    stored = _rows(lab, 'fundamental_observations', where="WHERE metric='revenue' AND period_end='2026-03-28'")
    assert sorted((r['dimension'], r['value'], r['last_updated']) for r in stored) == [
        ('ARQ', '95359000000', '2026-08-01'), ('MRQ', '95400000000', '2026-09-15'), ('MRQ', '95500000000', '2026-11-20')]
    assert lab.capability('fundamentals') == 'AVAILABLE' and lab.capability('corporate_actions') == 'AVAILABLE'
    assert SECRET.encode() not in lab.path.read_bytes()
    for name in ('ml_ranker', 'sector_engine', 'portfolio_optimizer'):                   # raw fundamentals unlock no strategy component
        assert lab.capability(name) == 'NOT_STARTED'


def test_sharadar_accepts_a_delisted_ticker_and_refuses_money_without_a_currency():
    _, result = _fundamentals(_sharadar_routes(delisted='Y'))
    assert result.status == OK and {r['is_delisted'] for r in result.records()} == {True}
    _, result = _fundamentals(_sharadar_routes(currency=''))
    assert result.status == REJECTED and _codes(result) == ['MISSING_UNITS_OR_CURRENCY']         # an amount with no currency is not usable
    other = _table(SF1_COLUMNS, [['MSFT'] + ARQ['datatable']['data'][0][1:]])
    assert _codes(_fundamentals(_sharadar_routes(arq=other))[1]) == ['CONFLICTING_INSTRUMENT_IDENTITY']
    text = _table(SF1_COLUMNS, [['AAPL', 'ARQ', '2026-06-30', '2026-07-31', '2026-06-27', '2026-Q3', '2026-08-01', 'n/a', 1, 1, 1, 1, 1]])
    assert _codes(_fundamentals(_sharadar_routes(arq=text))[1]) == ['IMPOSSIBLE_VALUE']
    undated = _table(SF1_COLUMNS, [['AAPL', 'ARQ', '2026-06-30', '2026-07-31', '2026-06-27', '2026-Q3', None, 1, 1, 1, 1, 1, 1]])
    assert 'NOT_POINT_IN_TIME' in _codes(_fundamentals(_sharadar_routes(arq=undated))[1])        # no "last updated": not a dated snapshot
    more = dict(ARQ, meta={'next_cursor_id': 'abc'})
    assert _codes(_fundamentals(_sharadar_routes(arq=more))[1]) == ['INCOMPLETE_HISTORICAL_WINDOW']
    assert _fundamentals([('TICKERS.json', 200, {'quandl_error': {'code': 'QEPx04', 'message': 'no'}})])[1].status == REJECTED
    for status in (401, 403, 429):
        assert _fundamentals([('TICKERS.json', status, b'')])[1].status == UNAVAILABLE
    with pytest.raises(FirmLabError):
        sharadar.SharadarFundamentalsProvider(Fake([]), '', 'nasdaq')                    # never constructed without a key


def test_sharadar_direct_channel_reads_csv_by_column_name_and_hides_the_key():
    csv_rows = ('ticker,dimension,calendardate,date,reportperiod,fiscalperiod,lastupdated,revenue,epsdil\n'
                'AAPL,ARQ,2026-06-30,2026-07-31,2026-06-27,2026-Q3,2026-08-01,94036000000,1.57\n')
    routes = [('/data/tickers', 200, 'table,permaticker,ticker,isdelisted,currency\nSF1,199059,AAPL,N,USD\n'),
              ('dimension=ARQ', 200, csv_rows), ('dimension=MRQ', 200, csv_rows.replace('ARQ', 'MRQ'))]
    provider, result = _fundamentals(routes, channel='direct')
    assert result.status == OK
    first = result.records()[0]
    assert first['provider_datekey'] == first['filing_date'] == '2026-07-31' and str(first['value']) == '94036000000'       # "date" is the datekey here
    assert SECRET not in result.provenance.source_id and 'api_key=REDACTED' in result.provenance.source_id
    assert all(SECRET in url for url, _ in provider.transport.calls)                     # sent to the vendor, never written down


def test_sharadar_corporate_actions_are_raw_events_with_no_invented_announcement_time():
    provider = sharadar.SharadarCorporateActionsProvider(Fake(_sharadar_routes()), SECRET, 'nasdaq')
    result = provider.actions('AAPL', start='2026-01-01', end='2026-10-02', now=CLOCK)
    assert result.status == OK
    by = {r['provider_action']: r for r in result.records()}
    assert by['dividend']['action_type'] == 'cash_dividend' and by['split']['action_type'] == 'split' and by['relation']['action_type'] == 'other'
    assert {r['announcement_timestamp'] for r in result.records()} == {'UNAVAILABLE'}    # not manufactured from the effective date
    assert by['dividend']['effective_date'] == '2026-08-11' and 'not confirmed' in by['dividend']['effective_date_basis']
    assert str(by['split']['value']) == '4' and by['relation']['contra_instrument'] == 'XYZ'
    assert set(sharadar.ACTIONS.values()) == {'cash_dividend', 'split', 'symbol_change', 'delisting', 'spin_off', 'merger'}
    assert not {'adjusted_close', 'adjustment_factor', 'total_return'} & set(by['dividend'])       # events only: no price is adjusted here
    made_up = dict(by['dividend'], announcement_timestamp='2026-08-11')
    report = quality.validate('corporate_actions', [made_up], now=NOW, provenance=result.provenance)
    assert 'UNPARSEABLE_TIMESTAMP' in report.codes() or 'TIMEZONE_MISSING' in report.codes()       # a bare date is not accepted as a time
    window = provider.actions('AAPL', start='2026-08-01', end='2026-10-02', now=CLOCK)
    assert [r['provider_action'] for r in window.records()] == ['dividend']


def test_sec_cross_check_reads_the_acceptance_time_from_the_sec_record_and_invents_none(tmp_path):
    lab = _lab(tmp_path)
    env = {'FIRM_LAB_SHARADAR_API_KEY': SECRET, 'FIRM_LAB_SHARADAR_CHANNEL': 'nasdaq'}
    aapl = (('0000320193-26-000077', '10-Q', '2026-07-31', '20260730183005', '2026-07-30T22:30:05.000Z'),      # accepted after 5:30 p.m.: dated next day
            ('0000320193-26-000070', '8-K', '2026-07-31', '20260730163000', '2026-07-30T20:30:00.000Z'))
    edgar_report = runner.run_edgar(lab, symbols=('AAPL',), environ=AGENT, clock=CLOCK,
                                    transport=Fake(_edgar_routes(aapl, cik=320193, json_cik='320193', report_date='2026-06-27')))
    assert edgar_report['runs'][0]['status'] == OK
    report = runner.run_sharadar(lab, symbols=('AAPL',), environ=env, transport=Fake(_sharadar_routes()), clock=CLOCK)
    assert report['sec_cross_check'] == {'reports': 2, 'MATCH': 1, 'NO_SEC_FILING_STORED': 1, 'AMBIGUOUS': 0, 'period_end_disagreements': 0}
    with lab.connect() as db:
        entries = {e['period_end']: e for e in crosscheck.fundamentals_vs_filings(db, 'AAPL')}
    june, march = entries['2026-06-27'], entries['2026-03-28']
    assert june['status'] == 'MATCH' and june['sec_accepted_timestamp'] == '2026-07-30T22:30:05+00:00'      # from EDGAR; the 8-K is not a periodic report
    assert june['sec_filings'][0]['accession_number'] == '0000320193-26-000077' and june['provider_filing_date'] == '2026-07-31'
    assert march['status'] == 'NO_SEC_FILING_STORED' and 'sec_accepted_timestamp' not in march and march['sec_filings'] == []
    # the fundamental rows themselves are unchanged: no acceptance time was written into them
    assert {r['filing_timestamp'] for r in _rows(lab, 'fundamental_observations')} == {'UNAVAILABLE'}
    assert 'edgar_accepted_timestamp' not in _rows(lab, 'fundamental_observations')[0]
    html = firm_lab_page.render({'firm_lab': view.load(path=lab.path)})
    assert 'SEC cross-check: of 2 as-reported filings' in html and '1 match exactly one stored SEC filing' in html


# ====================================================================================================== ThetaData
def _eod(strike, right, bid, ask, **over):
    return {'symbol': 'SPY', 'expiration': '2026-10-16', 'strike': strike, 'right': right, 'created': '2026-10-01T17:15:02.123', 'bid': bid,
            'bid_size': 40, 'ask': ask, 'ask_size': 55, 'volume': 1200, **over}


def _oi(strike, right, n=5400):
    return {'symbol': 'SPY', 'expiration': '2026-10-16', 'strike': strike, 'right': right, 'timestamp': '2026-10-01T06:30:00', 'open_interest': n}


def _greeks(strike, right, **over):
    return {'symbol': 'SPY', 'expiration': '2026-10-16', 'strike': strike, 'right': right, 'timestamp': '2026-10-01T17:15:02.123', 'delta': 0.52,
            'theta': -0.21, 'vega': 0.44, 'rho': 0.11, 'implied_vol': 0.1432, 'underlying_price': 668.4, 'underlying_timestamp': '2026-10-01T16:00:00',
            **over}


def _theta_routes(eod=None, oi=None, greeks=None):
    eod = [_eod(665.0, 'call', 7.10, 7.18), _eod(665.0, 'put', 3.95, 4.02)] if eod is None else eod
    oi = [_oi(665.0, 'call'), _oi(665.0, 'put', 8100)] if oi is None else oi
    greeks = [_greeks(665.0, 'call'), _greeks(665.0, 'put', delta=-0.48)] if greeks is None else greeks
    return [('/option/list/expirations', 200, {'response': [{'symbol': 'SPY', 'expiration': '2026-09-18'}, {'symbol': 'SPY', 'expiration': '2026-10-16'},
                                                           {'symbol': 'SPY', 'expiration': '2026-11-20'}]}),
            ('/option/history/eod', 200, {'response': eod}), ('/option/history/open_interest', 200, {'response': oi}),
            ('/option/history/greeks/eod', 200, {'response': greeks})]


def _chain(routes, **kw):
    provider = thetadata.ThetaDataOptionsProvider(Fake(routes))
    return provider, provider.chain('SPY', as_of=DAY, now=CLOCK, **kw)


def test_thetadata_contracts_carry_identity_time_quote_and_vendor_named_greeks():
    provider, result = _chain(_theta_routes())
    assert result.status == OK
    call, put = result.records()
    assert call['contract_id'] == 'SPY261016C00665000' and put['contract_id'] == 'SPY261016P00665000'
    assert (call['underlying'], call['option_type'], str(call['strike']), call['expiration']) == ('SPY', 'call', '665.0', '2026-10-16')
    assert call['quote_timestamp'] == '2026-10-01T21:15:02.123000+00:00' and call['quote_timestamp_raw'] == '2026-10-01T17:15:02.123'      # New York clock, as sent
    assert str(call['bid']) == '7.1' and str(call['ask']) == '7.18' and call['open_interest'] == 5400 and put['open_interest'] == 8100
    assert str(call['thetadata_provider_delta']) == '0.52' and str(put['thetadata_provider_delta']) == '-0.48'
    assert str(call['thetadata_provider_implied_volatility']) == '0.1432' and 'thetadata_provider_gamma' not in call      # not sent, so not present
    assert not set(call) & schemas.BARE_GREEK_NAMES and 'implied_vol' not in call
    assert call['greeks_provider'] == 'ThetaData' and 'Black-Scholes' in call['greeks_model'] and 'SOFR' in call['greeks_model_version']
    assert str(call['underlying_price']) == '668.4' and call['underlying_timestamp'] == '2026-10-01T20:00:00+00:00'
    urls = [u for u, _ in provider.transport.calls]
    assert all(u.startswith('http://127.0.0.1:25503/v3/') for u in urls) and all('expiration=20261016' in u for u in urls[1:])      # nearest listed expiration
    assert not {'recommendation', 'score', 'rank', 'signal', 'strategy'} & set(call)


def test_a_bare_greek_is_refused_by_validation_and_again_by_storage(tmp_path):
    _, result = _chain(_theta_routes())
    record = dict(result.records()[0])
    bare = dict(record, delta=0.52)
    report = quality.validate('options_chain', [bare], now=NOW, provenance=result.provenance)
    assert 'UNNAMESPACED_GREEK' in report.codes()
    for name in ('gamma', 'iv', 'implied_volatility', 'theta', 'vega', 'rho'):
        assert 'UNNAMESPACED_GREEK' in quality.validate('options_chain', [dict(record, **{name: 1})], now=NOW, provenance=result.provenance).codes(), name
    lab = _lab(tmp_path)
    with pytest.raises(FirmLabError, match='BARE_GREEK_FIELD'):
        rawstore._row(bare, ['contract_id'], 'ThetaData')
    with pytest.raises(FirmLabError, match='GREEK_VENDOR_NOT_NAMED'):                    # a vendor-named Greek needs the vendor stated beside it
        rawstore._row(dict(record, greeks_provider='SomeoneElse'), ['contract_id'], 'ThetaData')
    with pytest.raises(ValueError):
        schemas.greek_field('delta', 'guess')
    assert schemas.greek_field('delta', 'provider', 'thetadata') == 'thetadata_provider_delta'
    assert schemas.greek_field('delta', 'model') == 'model_estimated_delta'
    assert not _rows(lab, 'option_chain_observations')


def test_thetadata_malformed_chains_are_refused():
    cases = (
        (_theta_routes(eod=[_eod(665.0, 'call', 7.10, 7.18, symbol='QQQ')]), 'CONFLICTING_INSTRUMENT_IDENTITY'),
        (_theta_routes(eod=[_eod(None, 'call', 7.10, 7.18)], oi=[], greeks=[]), 'MISSING_FIELD'),
        (_theta_routes(eod=[_eod(665.0, 'straddle', 7.10, 7.18)]), 'VALUE_NOT_ALLOWED'),
        (_theta_routes(eod=[_eod(665.0, 'call', 7.30, 7.18)]), 'CROSSED_MARKET'),
        (_theta_routes(eod=[_eod(665.0, 'call', 7.10, 7.18, created='yesterday evening')]), 'UNPARSEABLE_TIMESTAMP'),
        (_theta_routes(eod=[_eod(665.0, 'call', 7.10, 7.18), _eod(665.0, 'call', 7.10, 7.18)]), 'DUPLICATE_RECORD'),
        (_theta_routes(oi=[]), 'MISSING_FIELD'),                                         # no open interest: not filled with zero
        (_theta_routes(greeks=[]), 'MISSING_FIELD'),                                     # no provider implied volatility: none is estimated
        (_theta_routes(eod=[]), 'NOT_A_RECORD'),
    )
    for routes, code in cases:
        result = _chain(routes)[1]
        assert result.status == REJECTED and code in _codes(result), code
    not_a_list = _theta_routes()
    not_a_list[1] = ('/option/history/eod', 200, {'response': 'CSV,not,json'})
    assert _codes(_chain(not_a_list)[1]) == ['MALFORMED_RESPONSE']
    no_later = [('/option/list/expirations', 200, {'response': [{'symbol': 'SPY', 'expiration': '2026-09-18'}]})]
    assert _codes(_chain(no_later)[1]) == ['MALFORMED_RESPONSE']


def test_thetadata_needs_the_operators_terminal_and_tier(tmp_path):
    lab = _lab(tmp_path)
    net = Fake(_theta_routes())
    report = runner.run_thetadata(lab, environ={}, transport=net, clock=CLOCK, as_of=DAY)
    assert report['connection'] == 'NOT_CONFIGURED' and 'activation required' in report['detail'] and net.requests == 0
    env = {'FIRM_LAB_THETADATA_TERMINAL': '1'}

    class Down:
        requests = 0

        def get(self, url, headers=None):
            self.requests += 1
            return Response(0, b'', url, NOW.isoformat(), 'ConnectionRefusedError', {})

    report = runner.run_thetadata(lab, symbols=('SPY',), environ=env, transport=Down(), clock=CLOCK, as_of=DAY)
    assert report['connection'] == 'ERROR' and 'did not answer' in report['detail'] and report['runs'][0]['status'] == UNAVAILABLE
    tier = _theta_routes()
    tier[3] = ('/option/history/greeks/eod', 471, b'')
    report = runner.run_thetadata(lab, symbols=('SPY',), environ=env, transport=Fake(tier), clock=CLOCK, as_of=DAY)
    assert report['runs'][0]['status'] == UNAVAILABLE and 'tier does not include' in report['runs'][0]['reason']
    assert lab.capability('options_chain') == 'BUILD_ONLY' and lab.capability('options_greeks') == 'UNAVAILABLE'
    assert not _rows(lab, 'option_chain_observations')
    report = runner.run_thetadata(lab, symbols=('SPY',), environ=env, transport=Fake(_theta_routes()), clock=CLOCK, as_of=DAY)
    assert report['runs'][0]['status'] == OK and report['runs'][0]['stored'] == 2
    row = _rows(lab, 'option_chain_observations')[0]
    assert row['provider_delta'] == '0.52' and row['provider_implied_volatility'] == '0.1432' and row['provider_gamma'] is None
    assert row['greeks_provider'] == 'ThetaData' and row['greeks_model'] and row['greeks_model_version'] and row['greeks_timestamp']
    assert row['provider'] == 'ThetaData' and row['content_hash'] and row['quote_timestamp_raw'] == '2026-10-01T17:15:02.123'
    assert lab.capability('options_chain') == 'AVAILABLE' and lab.capability('options_greeks') == 'AVAILABLE'
    assert lab.capability('options_strategy') == 'NOT_STARTED'                           # stored chains recommend nothing


# ====================================================================================================== isolation
STDLIB_ALLOWED = {'__future__', 'argparse', 'csv', 'dataclasses', 'datetime', 'decimal', 'gzip', 'hashlib', 'html', 'io', 'json', 'os', 'pathlib', 're', 'time',
                  'typing', 'urllib'}
TRADING_MODULES = ('agents', 'broker', 'risk', 'data', 'research', 'eval', 'scripts', 'broker_proxy')
TRADING_WORDS = ('PaperBroker', 'PaperInbox', 'RiskEngine', 'issue_desk_entry', 'submit_order', 'place_order', 'robinhood.com', 'robinhood-shadow-agent', 'robinhood_', 'launchctl', 'plist',
                 'keychain_get', 'find-generic-password -s robinhood')


def _imports(path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield 0, alias.name
        elif isinstance(node, ast.ImportFrom):
            yield node.level, node.module or ''


def test_collectors_import_only_the_standard_library_and_the_research_package():
    files = sorted((ROOT / 'firm_lab_collectors').glob('*.py'))
    assert {f.name for f in files} >= {'__init__.py', 'cli.py', 'config.py', 'edgar.py', 'massive.py', 'runner.py', 'sharadar.py', 'thetadata.py',
                                       'transport.py', 'treasury.py', 'capture.py'}
    for path in files:
        for level, name in _imports(path):
            top = name.split('.')[0]
            if level:                                                                    # a sibling module of this package
                assert level == 1 and (top == '' or (ROOT / 'firm_lab_collectors' / f'{top}.py').is_file()), (path.name, name)
                continue
            assert top in STDLIB_ALLOWED | {'firm_lab'}, f'{path.name} imports {name}'
            assert top not in TRADING_MODULES, f'{path.name} imports {name}'
            if top == 'urllib' or top == 'gzip':                                         # the network lives in exactly one file
                assert path.name == 'transport.py', f'{path.name} imports {name}'
            if top == 'firm_lab':
                assert name.split('.')[-1] not in ('official', 'boundary', 'ingest', 'baseline'), f'{path.name} imports {name}'
        source = path.read_text()
        for word in TRADING_WORDS:
            assert word.lower() not in source.lower(), f'{path.name} mentions {word}'
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, (ast.Name, ast.Attribute)):
                ident = node.id if isinstance(node, ast.Name) else node.attr
                assert ident not in ('__import__', 'exec', 'eval', 'system', 'popen', 'Popen', 'import_module', 'urlretrieve'), f'{path.name} uses {ident}'
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == 'firm_lab':
                assert not {a.name for a in node.names} & {'official', 'boundary', 'ingest', 'baseline'}, path.name
    # the research package itself still opens no connection, and the dashboard page does not load the collectors
    for path in sorted((ROOT / 'firm_lab').glob('*.py')):
        for _, name in _imports(path):
            assert name.split('.')[0] not in ('urllib', 'socket', 'http', 'ssl', 'subprocess', 'firm_lab_collectors'), f'{path.name} imports {name}'
    assert 'firm_lab_collectors' not in (ROOT / 'agents' / 'desk' / 'firm_lab_page.py').read_text()


PUBLIC_SAMPLE_HOSTS = {'investor.vanguard.com', 'api.nasdaq.com'}       # public pages a hand-started capture or collector may ask


def test_collectors_name_only_research_hosts_and_post_nothing():
    hosts = set(edgar.HOSTS) | {massive.HOST, sharadar.DIRECT_HOST, sharadar.NASDAQ_HOST, thetadata.HOST, treasury_source.HOST}
    assert hosts == {'www.sec.gov', 'data.sec.gov', 'api.massive.com', 'api.sharadar.com', 'data.nasdaq.com', '127.0.0.1:25503',
                     'api.fiscaldata.treasury.gov'}
    for path in sorted((ROOT / 'firm_lab_collectors').glob('*.py')):
        source = path.read_text()
        for found in re.findall(r'https?://([A-Za-z0-9.\-:]+)', source):
            assert found in hosts | PUBLIC_SAMPLE_HOSTS | {'thetadata.net'} or found.startswith('{'), f'{path.name} names {found}'
        assert "method='POST'" not in source and 'data=' not in source.replace('metadata=', ''), path.name       # GET only; nothing is sent as a body
    assert "method='GET'" in (ROOT / 'firm_lab_collectors' / 'transport.py').read_text()


def test_no_schedule_or_service_starts_a_collector():
    for path in ROOT.rglob('*'):
        if path.is_file() and path.suffix in ('.plist', '.sh', '.command', '.service', '.timer', '.cron') and '.git' not in path.parts:
            assert 'firm_lab_collectors' not in path.read_text(errors='ignore'), path
    for path in sorted((ROOT / 'scripts').glob('*.py')) if (ROOT / 'scripts').is_dir() else []:
        assert 'firm_lab_collectors' not in path.read_text(errors='ignore'), path


def test_after_every_collector_ran_firm_lab_still_cannot_fill_and_holds_no_portfolio_state(tmp_path):
    lab = _lab(tmp_path)
    runner.run_edgar(lab, symbols=('NVDA',), environ=AGENT, transport=Fake(_edgar_routes()), clock=CLOCK)
    runner.run_massive(lab, symbols=('SPY',), environ={'FIRM_LAB_MASSIVE_API_KEY': SECRET}, clock=CLOCK, session_date=DAY, ticks=False,
                       transport=Fake([('/v2/aggs/ticker/', 200, _aggs(GOOD_BARS))]))
    runner.run_sharadar(lab, symbols=('AAPL',), environ={'FIRM_LAB_SHARADAR_API_KEY': SECRET, 'FIRM_LAB_SHARADAR_CHANNEL': 'nasdaq'},
                        transport=Fake(_sharadar_routes()), clock=CLOCK)
    runner.run_thetadata(lab, symbols=('SPY',), environ={'FIRM_LAB_THETADATA_TERMINAL': '1'}, transport=Fake(_theta_routes()), clock=CLOCK, as_of=DAY)
    assert lab.mode() == 'BUILD_OBSERVE' and not lab.active_experiments()
    assert not [t for t in lab.tables() for word in FORBIDDEN_TABLE_WORDS if word in t]
    with pytest.raises(NoFillInBuildObserve):
        boundary.ExecutionBoundary(lab).submit(instrument='SPY', asset_class='etf', side='buy', quantity='1')
    counts = lab.counts()
    assert counts['experiment_registry'] == 0 and counts['counterfactual_decisions'] == 0 and counts['benchmark_observations'] == 0
    state = view.load(path=lab.path)
    assert state['fills'] == 0 and state['firm_trading_trial'] == 'NOT REGISTERED' and state['has_execution_tables'] is False
    assert state['october_research_stop_superseded'] == 'NO' and state['real_execution'] == 'DISABLED' and state['official_lane_b'] == 'PAUSED'
    assert state['treasury_methodology']['status'] == 'APPROVED_AND_FROZEN' and state['treasury_index'] is None
    assert lab.capability('treasury_total_return') == 'UNAVAILABLE'                      # no auction record was ingested: nothing is computed


def test_the_collector_command_never_opens_the_registered_database(tmp_path, capsys):
    official = tmp_path / 'runtime' / 'data' / 'agent.db'
    official.parent.mkdir(parents=True)
    db = sqlite3.connect(official)
    db.execute('CREATE TABLE fills (id INTEGER PRIMARY KEY)')
    db.commit()
    db.close()
    before = (official.read_bytes(), official.stat().st_mtime_ns)
    lab = _lab(tmp_path)
    assert cli.main(['status', '--path', str(lab.path)], environ={}) == 0
    assert cli.main(['edgar', '--path', str(lab.path), '--symbols', 'NVDA'], environ=AGENT, transport=Fake(_edgar_routes())) == 0
    assert cli.main(['edgar', '--path', str(lab.path)], environ={}) == 0                 # not configured: says so and fetches nothing
    printed = capsys.readouterr().out
    assert 'research@example.com' not in printed and '"connection": "NOT_CONFIGURED"' in printed and '"firm_trading_trial": "NOT REGISTERED"' in printed
    assert (official.read_bytes(), official.stat().st_mtime_ns) == before
    source = (ROOT / 'firm_lab_collectors' / 'cli.py').read_text()
    assert '--official-database' not in source.replace('never given here', '') and 'agent.db' not in source
    assert cli.main(['edgar', '--path', str(tmp_path / 'nowhere' / 'firm_lab.db')], environ=AGENT, transport=Fake(_edgar_routes())) == 1
    assert 'NOT_INITIALISED' in capsys.readouterr().out and not (tmp_path / 'nowhere').exists()      # it never creates a database


# ====================================================================================================== the page
def _cells(html, label):
    section = html[html.index('id="fl-readiness"'):html.index('id="fl-capabilities"')]
    row = section[section.index(f'<b>{label}</b>'):]
    row = row[:row.index('</tr>')]
    return {name: re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', cell)).strip()
            for name, cell in re.findall(r'<td data-label="([^"]+)"[^>]*>(.*?)</td>', '<td data-label="Data">' + row, re.S)}


def test_data_readiness_shows_provider_connection_validation_and_what_is_stored(tmp_path):
    lab = _lab(tmp_path)
    html = firm_lab_page.render({'firm_lab': view.load(path=lab.path)})
    for flag in ('BUILD / OBSERVE', 'NO FILLS', 'NO FIRM TRADING TRACK RECORD'):
        assert f'<span class="fl-flag">{flag}</span>' in html
    before = _cells(html, 'SEC filings')
    assert before['Provider'] == 'SEC EDGAR' and before['Capability'] == 'PARTIAL_EXISTING' and before['Connection'].startswith('NOT CONFIGURED')
    assert 'Credentials or provider activation required' in before['Connection'] and before['Validation'] == 'NOT RUN'
    assert before['Stored'] == '0 nothing stored' and before['Last successful ingest'] == 'never' and before['Quality failures and flags'] == 'none recorded'
    runner.run_edgar(lab, symbols=('NVDA',), environ=AGENT, transport=Fake(_edgar_routes()), clock=CLOCK)
    runner.run_massive(lab, environ={}, clock=CLOCK, session_date=DAY)                   # Massive has no key on this machine
    html = firm_lab_page.render({'firm_lab': view.load(path=lab.path)})
    sec = _cells(html, 'SEC filings')
    assert sec['Capability'] == 'AVAILABLE' and sec['Connection'].startswith('ACTIVE') and sec['Validation'].startswith('PASS') and 'NVDA OK' in sec['Validation']
    assert sec['Stored'].startswith('3 ') and 'Jan 15' in sec['Stored'] and 'Aug 27' in sec['Stored'] and sec['Last successful ingest'] != 'never'
    bars = _cells(html, 'Intraday 1-minute bars')
    assert bars['Capability'] == 'UNAVAILABLE' and bars['Provider'] == 'Massive' and bars['Connection'].startswith('NOT CONFIGURED')
    assert 'Credentials required' in bars['Connection'] and bars['Stored'] == '0 nothing stored' and bars['Validation'] == 'NOT RUN'
    conflict = (('0001045810-26-000200', '8-K', '2026-09-30', '20260930170000', '2026-09-30T11:00:00.000Z'),)
    runner.run_edgar(lab, symbols=('NVDA',), environ=AGENT, transport=Fake(_edgar_routes(conflict)), clock=lambda: NOW + timedelta(minutes=3))
    sec = _cells(firm_lab_page.render({'firm_lab': view.load(path=lab.path)}), 'SEC filings')
    assert sec['Capability'] == 'AVAILABLE' and sec['Validation'].startswith('PASS') and sec['Stored'].startswith('4 ')      # kept, timed by its header
    assert sec['Quality failures and flags'].startswith('Kept and flagged: ACCEPTANCE_TIME_CONFLICT × 1')
    runner.run_edgar(lab, symbols=('NVDA',), environ=AGENT, transport=Fake(_edgar_routes(headers=False)), clock=lambda: NOW + timedelta(minutes=6))
    sec = _cells(firm_lab_page.render({'firm_lab': view.load(path=lab.path)}), 'SEC filings')
    assert sec['Capability'] == 'PARTIAL_EXISTING' and sec['Validation'].startswith('FAIL') and 'ACCEPTANCE_TIME_UNVERIFIED' in sec['Validation']
    assert 'Kept and flagged: ACCEPTANCE_TIME_CONFLICT × 1' in sec['Quality failures and flags']
    assert 'Refused: ACCEPTANCE_TIME_UNVERIFIED × 1' in sec['Quality failures and flags'] and sec['Stored'].startswith('4 ')
    treasury = _cells(html, 'T-bill total return')
    assert treasury['Capability'] == 'UNAVAILABLE' and treasury['Provider'] == 'U.S. Treasury Fiscal Data' and treasury['Stored'] == '0 nothing stored'
    assert treasury['Connection'].startswith('CONFIGURED') and 'frozen methodology' in html[html.index('<b>T-bill total return</b>'):].split('</tr>')[1].lower()
    for word in ('<form', '<svg', 'Trial 18', 'Trial 20', 'buy ', 'sell ', 'recommended'):
        assert word not in html, word


# ====================================================================================================== upgrading the Checkpoint 2 database
def test_a_checkpoint_2_database_is_upgraded_in_place_without_losing_or_inventing_anything(tmp_path):
    path = tmp_path / 'diag' / 'firm_lab' / 'firm_lab.db'
    path.parent.mkdir(parents=True)
    db = sqlite3.connect(path)                                                           # the option table as Checkpoint 1 created it: no provenance columns
    db.execute('CREATE TABLE option_chain_observations (id INTEGER PRIMARY KEY, contract_id TEXT NOT NULL, underlying TEXT NOT NULL, bid TEXT, ask TEXT)')
    db.commit()
    db.close()
    lab = FirmLabStore(path)
    with lab.connect() as db:
        columns = [r[1] for r in db.execute('PRAGMA table_info(option_chain_observations)')]
        events = [json.loads(r[0]) for r in db.execute("SELECT payload_json FROM events WHERE kind='SCHEMA_CHANGE'")]
        for capability, (provider, detail) in capabilities.V2_TEXT.items():              # the registry exactly as Checkpoint 2 left it
            status = next(s for c, s, *_ in capabilities.INITIAL if c == capability)
            db.execute('INSERT INTO data_capabilities VALUES (?,?,?,?,?)', (capability, status, provider, detail, NOW.isoformat()))
        db.execute("UPDATE data_capabilities SET detail='Edited by the operator on purpose.' WHERE capability='corporate_actions'")
        db.execute("INSERT INTO firm_meta VALUES ('capability_registry_version', '2', ?)", (NOW.isoformat(),))
    assert {'run_id', 'content_hash', 'greeks_provider', 'greeks_model', 'provider_delta'} <= set(columns) and len(events) == 1 and events[0]['rows_before'] == 0
    before = {c['capability']: c['status'] for c in lab.capabilities()}
    capabilities.seed(lab, NOW)
    after = {c['capability']: c for c in lab.capabilities()}
    assert {k: after[k]['status'] for k in before} == before                             # the upgrade changes descriptions, never a status
    assert 'Sharadar is chosen' in after['fundamentals']['detail'] and 'approved and frozen' in after['treasury_total_return']['detail']
    assert after['options_chain']['provider'] is None and 'ThetaData is chosen and not connected' in after['options_chain']['detail']
    assert after['corporate_actions']['detail'] == 'Edited by the operator on purpose.'  # a deliberate edit is left alone
    assert after['tick_trades_quotes']['status'] == 'UNAVAILABLE' and lab.meta('capability_registry_version') == '4'
    assert not [c for c in after.values() if c['status'] == 'AVAILABLE']                 # nothing became available by upgrading
    capabilities.seed(lab, NOW)
    assert {c['capability']: (c['status'], c['detail']) for c in lab.capabilities()} == {k: (v['status'], v['detail']) for k, v in after.items()}
    assert set(rawstore.DOMAIN_TABLE.values()) | {'provider_runs', 'provider_connections'} <= set(lab.tables())
    assert not [t for t in lab.tables() for word in FORBIDDEN_TABLE_WORDS if word in t]
    # an old-shape option table that holds rows is never replaced
    other = tmp_path / 'other' / 'firm_lab.db'
    other.parent.mkdir()
    db = sqlite3.connect(other)
    db.execute('CREATE TABLE option_chain_observations (id INTEGER PRIMARY KEY, contract_id TEXT NOT NULL)')
    db.execute("INSERT INTO option_chain_observations (contract_id) VALUES ('X')")
    db.commit()
    db.close()
    with pytest.raises(FirmLabError, match='OPTION_TABLE_HAS_ROWS'):
        FirmLabStore(other)


# ====================================================================================================== raw sample capture
def test_raw_capture_saves_what_arrived_asks_named_hosts_only_and_keeps_the_contact_address_for_the_sec(tmp_path):
    from firm_lab_collectors import capture
    recent = {'accessionNumber': ['0000320193-26-000090', '0000320193-26-000077'], 'form': ['8-K', '10-Q'], 'items': ['2.02,9.01', ''],
              'primaryDocument': ['a8k.htm', 'aapl-20260627.htm']}
    sec = Fake([('companyfacts', 200, {'cik': 320193, 'facts': {}}), ('submissions', 200, {'cik': '320193', 'filings': {'recent': recent}}),
                ('.hdr.sgml', 200, '<SEC-HEADER>'), ('index.json', 200, {'directory': {'item': []}}), ('aapl-20260627.htm', 200, '<html>')])
    plain = Fake([('profile/api/VTI/distribution', 200, {'x': 1}), ('DIVDAT_2026', 403, b'')])
    report = capture.run(tmp_path / 'samples', environ=AGENT, sec_transport=sec, plain_transport=plain)
    manifest = json.loads((tmp_path / 'samples' / 'manifest.json').read_text())
    assert report['requested'] == len(manifest) and report['sec_user_agent_declared'] is True
    assert (tmp_path / 'samples' / 'vanguard_vti_distribution.json').read_bytes() == b'{"x": 1}'      # exactly as received
    refused = {r['status'] for r in report['refused']}
    assert refused == {403, 404} and plain.requests == len(capture.PUBLIC)               # a refusal is recorded once, never retried
    names = {m['file'] for m in manifest if m['file']}
    assert {'sec_companyfacts_AAPL.json', 'sec_submissions_AAPL.json', 'sec_AAPL_periodic_0000320193-26-000077_aapl-20260627.htm',
            'sec_AAPL_earnings8k_0000320193-26-000090.hdr.sgml', 'sec_AAPL_earnings8k_0000320193-26-000090_index.json'} <= names
    assert all(m['sha256'] and m['bytes'] for m in manifest if m['file'])
    for url, _ in sec.calls:
        assert url.startswith(('https://www.sec.gov/', 'https://data.sec.gov/'))
    for url, _ in plain.calls:
        assert url.startswith(('https://investor.vanguard.com/', 'https://api.nasdaq.com/'))
    assert 'example.com' not in (tmp_path / 'samples' / 'manifest.json').read_text() and '@' not in capture.PLAIN_AGENT      # no contact address off the SEC
    without = capture.run(tmp_path / 'none', environ={}, sec_transport=Fake([]), plain_transport=Fake([]))
    assert without['sec_user_agent_declared'] is False and without['requested'] == len(capture.PUBLIC)         # the SEC is not asked anonymously
