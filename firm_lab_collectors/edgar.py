"""SEC EDGAR filing metadata, for Firm Lab research only. Nothing in a filing is read or interpreted.

Separate from Control A's advisory EDGAR reader, which is not touched.

Acceptance time. The submissions API writes ``acceptanceDateTime`` as ``2024-11-01T10:01:36.000Z``, but that text is
not reliably UTC: some responses carry the New York clock time with a ``Z`` on the end, sometimes mixed within one
file, and some recent filings carry a third value that matches neither reading (seen live on 2026-10-02: exactly
four hours later than the header time). So the JSON value is never trusted. For every filing kept, the filing's own SGML header is read
(``<ACCEPTANCE-DATETIME>YYYYMMDDHHMMSS``, the New York clock time EDGAR stamped; taken from the ``.hdr.sgml`` file, or
from the filing's ``-index-headers.html`` page when that file is absent), and

  * ``accepted_timestamp_header`` is that header time converted to UTC. It is authoritative (operator rule, 2026-10-02);
  * ``accepted_timestamp`` is the same value: the time Firm Lab treats the filing as known;
  * ``accepted_timestamp_json`` (and ``accepted_timestamp_raw``) is the JSON text exactly as sent. It is never rewritten;
  * ``acceptance_time_conflict`` is true when the JSON text agrees with the header under neither reading;
  * ``acceptance_time_json_offset_seconds`` is the JSON text read as UTC minus the header time, for the record;
  * ``accepted_timestamp_basis`` says in words which case applied.

A filing is not refused because the JSON disagrees: it is kept, flagged, and timed by its header. A filing whose
header cannot be read is still refused, and so is a JSON value that is not a timestamp at all: no acceptance time is
guessed.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from firm_lab.errors import ProviderRejected, ProviderUnavailable
from firm_lab.provenance import Provenance, content_hash
from firm_lab.providers import FilingsProvider
from firm_lab.schemas import SCHEMA_VERSION
from firm_lab.sessions import ET

HOSTS = ('www.sec.gov', 'data.sec.gov')
TICKERS_URL = 'https://www.sec.gov/files/company_tickers.json'
FUND_TICKERS_URL = 'https://www.sec.gov/files/company_tickers_mf.json'
SUBMISSIONS_URL = 'https://data.sec.gov/submissions/CIK{cik:010d}.json'
ARCHIVE = 'https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/'
HEADER_TAG = re.compile(rb'(?:<|&lt;)ACCEPTANCE-DATETIME(?:>|&gt;)\s*(\d{14})')
ACCESSION = re.compile(r'^\d{10}-\d{2}-\d{6}$')
JSON_TIME = re.compile(r'^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?Z$')
REQUIRED_ARRAYS = ('accessionNumber', 'filingDate', 'acceptanceDateTime', 'form', 'primaryDocument')
BASIS_UTC = 'SGML header (New York clock) converted to UTC; the JSON text matched it read as UTC'
BASIS_EASTERN = 'SGML header (New York clock) converted to UTC; the JSON text matched the New York clock with a Z on it'
BASIS_CONFLICT = 'SGML header (New York clock) converted to UTC; the JSON text matched neither reading and is kept as sent'


def _fail(response, what):
    """Turns a failed HTTP answer into the reason the provider is unavailable. Never retried here."""
    if response.status in (403, 429):
        raise ProviderUnavailable(f'SEC refused the request for {what} (HTTP {response.status}): rate limit or undeclared automated tool', 'ERROR')
    if response.status == 404:
        raise ProviderUnavailable(f'{what} not found at SEC (HTTP 404)', 'ACTIVE')
    raise ProviderUnavailable(f'no usable answer from SEC for {what} ({response.error or "HTTP " + str(response.status)})', 'ERROR')


def _json(response, what):
    try:
        return json.loads(response.body)
    except (ValueError, UnicodeDecodeError):
        raise ProviderRejected([('MALFORMED_RESPONSE', f'{what} is not JSON')]) from None


class EdgarFilingsProvider(FilingsProvider):
    name = 'SEC EDGAR'

    def __init__(self, transport, *, max_filings=10):
        self.transport = transport
        self.max_filings = int(max_filings)
        self._tickers = None
        self._funds = None

    # ---------------------------------------------------------------- identity
    def identity(self, instrument) -> dict:
        """Ticker -> CIK from SEC's own files. A ticker SEC does not list is not guessed."""
        symbol = str(instrument).upper()
        if self._tickers is None:
            reply = self.transport.get(TICKERS_URL)
            if not reply.ok:
                _fail(reply, 'the ticker list')
            data = _json(reply, 'the ticker list')
            rows = data.values() if isinstance(data, dict) else data if isinstance(data, list) else []
            self._tickers = {str(r.get('ticker', '')).upper(): r for r in rows if isinstance(r, dict)}
        row = self._tickers.get(symbol)
        if row and str(row.get('cik_str', '')).isdigit():
            return {'cik': int(row['cik_str']), 'entity_name': row.get('title'), 'series_id': None, 'class_id': None}
        if self._funds is None:
            reply = self.transport.get(FUND_TICKERS_URL)
            if not reply.ok:
                _fail(reply, 'the fund ticker list')
            data = _json(reply, 'the fund ticker list')
            fields, rows = (data.get('fields'), data.get('data')) if isinstance(data, dict) else (None, None)
            self._funds = {}
            if isinstance(fields, list) and isinstance(rows, list):
                for r in rows:
                    item = dict(zip(fields, r)) if isinstance(r, list) else {}
                    if item.get('symbol'):
                        self._funds[str(item['symbol']).upper()] = item
        fund = self._funds.get(symbol)
        if fund and str(fund.get('cik', '')).isdigit():
            return {'cik': int(fund['cik']), 'entity_name': None, 'series_id': fund.get('seriesId'), 'class_id': fund.get('classId')}
        raise ProviderUnavailable(f'SEC lists no CIK for {symbol}; none is guessed', 'ACTIVE')

    # ---------------------------------------------------------------- acceptance time
    def header_time(self, cik, accession):
        """(raw 14 digits, UTC ISO) from the filing's SGML header, or raises: the time is never assumed."""
        folder = accession.replace('-', '')
        match = None
        for name in (accession + '.hdr.sgml', accession + '-index-headers.html'):      # the same SEC header, as a file or as a page
            reply = self.transport.get(ARCHIVE.format(cik=cik, folder=folder) + name)
            if reply.status in (403, 429):
                _fail(reply, 'a filing header')
            match = HEADER_TAG.search(reply.body) if reply.ok else None
            if match or reply.status != 404:
                break
        if not match:
            raise ProviderRejected([('ACCEPTANCE_TIME_UNVERIFIED', f'{accession}: the filing header gave no acceptance time '
                                                                  f'({reply.error or "HTTP " + str(reply.status)})')])
        raw = match.group(1).decode()
        try:
            local = datetime.strptime(raw, '%Y%m%d%H%M%S').replace(tzinfo=ET)
        except ValueError:
            raise ProviderRejected([('ACCEPTANCE_TIME_UNVERIFIED', f'{accession}: unreadable header time {raw!r}')]) from None
        return raw, local.astimezone(timezone.utc)

    @staticmethod
    def reconcile(accession, json_text, header_raw, header_utc):
        """(basis, conflict, offset in seconds). The header is authoritative; the JSON text is only compared with it.
        A JSON value that is not a timestamp at all is still refused."""
        match = JSON_TIME.match(str(json_text or ''))
        if not match:
            raise ProviderRejected([('MALFORMED_FILING', f'{accession}: acceptanceDateTime {json_text!r} is not in the expected form')])
        clock = ''.join(match.groups())
        try:
            as_utc = datetime.strptime(clock, '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
        except ValueError:
            raise ProviderRejected([('MALFORMED_FILING', f'{accession}: acceptanceDateTime {json_text!r} is not a real time')]) from None
        offset = int((as_utc - header_utc).total_seconds())
        if clock == header_utc.strftime('%Y%m%d%H%M%S'):
            return BASIS_UTC, False, offset
        if clock == header_raw:
            return BASIS_EASTERN, False, offset
        return BASIS_CONFLICT, True, offset

    # ---------------------------------------------------------------- the interface method
    def _fetch(self, method, *, instrument, start=None, end=None, limit=None, **_):
        if method != 'filings':
            raise NotImplementedError
        who = self.identity(instrument)
        cik = who['cik']
        url = SUBMISSIONS_URL.format(cik=cik)
        reply = self.transport.get(url)
        if not reply.ok:
            _fail(reply, f'the filing index of {instrument}')
        data = _json(reply, 'the filing index')
        provenance = Provenance(provider=self.name, source_id=reply.url, source_timestamp=reply.fetched_at, ingested_at=reply.fetched_at,
                                known_at=reply.fetched_at, schema_version=SCHEMA_VERSION, content_hash=content_hash(reply.body))
        if not isinstance(data, dict) or str(data.get('cik', '')).lstrip('0') != str(cik):
            raise ProviderRejected([('CONFLICTING_INSTRUMENT_IDENTITY', f'asked for CIK {cik}, the answer is for {data.get("cik") if isinstance(data, dict) else "?"}')],
                                   provenance)
        recent = (data.get('filings') or {}).get('recent') if isinstance(data.get('filings'), dict) else None
        if not isinstance(recent, dict) or any(not isinstance(recent.get(k), list) for k in REQUIRED_ARRAYS):
            raise ProviderRejected([('MALFORMED_FILING', 'the filing index lacks one of ' + ', '.join(REQUIRED_ARRAYS))], provenance)
        count = len(recent['accessionNumber'])
        if any(len(recent[k]) != count for k in REQUIRED_ARRAYS):
            raise ProviderRejected([('MALFORMED_FILING', 'the filing index arrays have different lengths')], provenance)
        optional = lambda key, i: (recent.get(key)[i] if isinstance(recent.get(key), list) and len(recent[key]) == count else None) or None
        keep = int(limit or self.max_filings)
        records = []
        for i in range(count):
            filed = str(recent['filingDate'][i])
            if (start and filed < str(start)[:10]) or (end and filed > str(end)[:10]):
                continue
            accession = str(recent['accessionNumber'][i])
            if not ACCESSION.match(accession):
                raise ProviderRejected([('MALFORMED_FILING', f'accession number {accession!r} is not in the expected form')], provenance)
            try:
                header_raw, header_utc = self.header_time(cik, accession)
                basis, conflict, offset = self.reconcile(accession, recent['acceptanceDateTime'][i], header_raw, header_utc)
            except ProviderRejected as error:
                raise ProviderRejected(error.issues, provenance) from None
            document = str(recent['primaryDocument'][i] or '')
            folder = ARCHIVE.format(cik=cik, folder=accession.replace('-', ''))
            records.append({
                'instrument': str(instrument).upper(), 'cik': f'{cik:010d}', 'accession_number': accession, 'form_type': str(recent['form'][i]),
                'filing_date': filed, 'report_date': optional('reportDate', i), 'accepted_timestamp': header_utc.isoformat(),
                'accepted_timestamp_header': header_utc.isoformat(), 'accepted_timestamp_json': str(recent['acceptanceDateTime'][i]),
                'acceptance_time_conflict': conflict, 'acceptance_time_json_offset_seconds': offset,
                'accepted_timestamp_raw': str(recent['acceptanceDateTime'][i]), 'accepted_timestamp_basis': basis,
                'header_acceptance_raw': header_raw, 'url': folder + document if document else folder + accession + '-index.htm',
                'primary_document': document or None, 'items': optional('items', i), 'entity_name': data.get('name') or who.get('entity_name'),
                'series_id': who.get('series_id'), 'class_id': who.get('class_id'), 'ingestion_timestamp': reply.fetched_at})
            if len(records) >= keep:
                break
        return records, provenance
