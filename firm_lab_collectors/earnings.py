"""Earnings-release filings as facts, for Firm Lab research only: which 8-K with Item 2.02 ("Results of Operations and
Financial Condition") was filed, when the SEC accepted it, and where the release document is.

FACTUAL EVENT DATA ONLY. The release is not read, summarised, scored or compared with anything. There is no sentiment,
no tone, no surprise, no prediction and no transcript here, and no field for one.

What each field is:

  * ``event_date``: the SEC's "period of report" for the 8-K (the date of the event being reported).
  * ``accepted_timestamp``: the filing-header acceptance time (authoritative, as for all filing metadata).
  * ``acceptance_session``: where that time falls on the New York clock (before 09:30, 09:30 to 16:00, 16:00 or later).
    Clock only: holidays and early closes are not known here.
  * ``release_document_url``: the first EX-99 exhibit in the filing's own document list, or UNAVAILABLE. The short header
    file (``.hdr.sgml``) carries no document list (seen live, 2026-10-03), so the list is read from the filing's
    ``-index-headers.html`` page; when that page gives no list the field is UNAVAILABLE. A file name is never guessed.
  * The header's own ``<ITEMS>`` and ``<PERIOD>`` lines are compared with the filing index: a filing the index calls an
    Item 2.02 report but whose header does not, or whose event date differs, is refused.
  * ``fiscal_period_end``: the period end of the periodic report (10-Q or 10-K) that this release is taken to be
    about, or UNAVAILABLE. The link is a stated rule, not a reading of the release: the periodic report with the
    latest period end before the event date, at most 100 days before it, and itself filed no earlier than 7 days
    before the event. The periodic report may have been filed after the release; ``periodic_accession_number`` names it
    so its own acceptance time can be looked up.
"""
from __future__ import annotations

import html
import re
from datetime import date

from firm_lab.errors import ProviderRejected
from firm_lab.fundamentals import PERIODIC_FORMS
from firm_lab.providers import EarningsEventsProvider
from firm_lab.schemas import UNAVAILABLE
from firm_lab.sessions import ET

from .edgar import ARCHIVE, EdgarFilingsProvider, _fail

EARNINGS_FORMS = ('8-K', '8-K/A')
EARNINGS_ITEM = '2.02'
MAX_DAYS_AFTER_PERIOD_END = 100
MAX_DAYS_REPORT_BEFORE_EVENT = 7
BASIS = ('the periodic report with the latest period end before the event date (at most 100 days before it), filed no earlier than '
         '7 days before the event; linked at ingestion, not read from the release')
_DOCUMENT = re.compile(r'<DOCUMENT>\s*<TYPE>([^\s<]+)\s*<SEQUENCE>(\d+)\s*<FILENAME>\s*(?:<a\b[^>]*>)?([^\s<]+)', re.I)
_ITEMS = re.compile(r'<ITEMS>\s*([0-9.]+)', re.I)
_PERIOD = re.compile(r'<PERIOD>\s*(\d{8})', re.I)
_SAFE_NAME = re.compile(r'^[A-Za-z0-9._-]+$')


def documents(header_text) -> list:
    """[(type, sequence, file name)] from the filing header, in the header's order. Empty when the header lists none."""
    text = html.unescape(header_text) if '&lt;' in header_text else header_text
    return [(kind.upper(), int(sequence), name) for kind, sequence, name in _DOCUMENT.findall(text) if _SAFE_NAME.match(name)]


def acceptance_session(header_utc) -> str:
    local = header_utc.astimezone(ET)
    minutes = local.hour * 60 + local.minute
    return 'before_market_open' if minutes < 570 else 'during_market_hours' if minutes < 960 else 'after_market_close'


def _day(text):
    try:
        return date.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None


def fiscal_period(event_date, periodic_rows):
    """(period end, accession) of the periodic report this event is linked to by the stated rule, or (None, None)."""
    event = _day(event_date)
    if event is None:
        return None, None
    best = None
    for row in periodic_rows:
        end, filed = _day(row.get('report_date')), _day(row.get('filing_date'))
        if end is None or filed is None or not (end < event) or (event - end).days > MAX_DAYS_AFTER_PERIOD_END:
            continue
        if (event - filed).days > MAX_DAYS_REPORT_BEFORE_EVENT:
            continue
        if best is None or end > best[0] or (end == best[0] and row['accession_number'] < best[1]):
            best = (end, row['accession_number'])
    return (best[0].isoformat(), best[1]) if best else (None, None)


class EdgarEarningsEventsProvider(EarningsEventsProvider):
    name = 'SEC EDGAR'

    def __init__(self, transport, *, max_events=4, filings_reader=None):
        self.transport = transport
        self.max_events = int(max_events)
        self.filings_reader = filings_reader or EdgarFilingsProvider(transport)

    def _fetch(self, method, *, instrument, start=None, end=None, limit=None, **_):
        if method != 'events':
            raise NotImplementedError
        symbol = str(instrument).upper()
        index = self.filings_reader.recent_filings(symbol)
        cik, provenance, reply = index['cik'], index['provenance'], index['reply']
        periodic = [r for r in index['rows'] if r['form'] in PERIODIC_FORMS]
        keep = int(limit or self.max_events)
        records = []
        for row in index['rows']:
            if row['form'] not in EARNINGS_FORMS or EARNINGS_ITEM not in [x.strip() for x in str(row.get('items') or '').split(',')]:
                continue
            if (start and row['filing_date'] < str(start)[:10]) or (end and row['filing_date'] > str(end)[:10]):
                continue
            accession = row['accession_number']
            if _day(row.get('report_date')) is None:
                raise ProviderRejected([('MALFORMED_FILING', f'{accession}: the SEC gives no event date (period of report)')], provenance)
            try:
                header_raw, header_utc, header_text = self.filings_reader.header(cik, accession)
                basis, conflict, offset = self.filings_reader.reconcile(accession, row['json_time'], header_raw, header_utc)
            except ProviderRejected as error:
                raise ProviderRejected(error.issues, provenance) from None
            header_items, header_period = _ITEMS.findall(header_text), _PERIOD.search(header_text)
            if header_items and EARNINGS_ITEM not in header_items:
                raise ProviderRejected([('ITEMS_DISAGREE', f'{accession}: the filing index says Item {EARNINGS_ITEM}, the filing header lists '
                                                           + ', '.join(header_items))], provenance)
            if header_period and header_period.group(1) != row['report_date'].replace('-', ''):
                raise ProviderRejected([('EVENT_DATE_DISAGREES', f'{accession}: the filing index says {row["report_date"]}, the filing header '
                                                                 f'says {header_period.group(1)}')], provenance)
            folder = ARCHIVE.format(cik=cik, folder=accession.replace('-', ''))
            listed = documents(header_text)
            if not listed:                                  # the short header file has no document list: ask for the page that does
                page = self.transport.get(folder + accession + '-index-headers.html')
                if page.status in (403, 429):
                    _fail(page, 'a filing document list')
                listed = documents(page.body.decode('utf-8', 'replace')) if page.ok else []
            release = next(((kind, name) for kind, _, name in sorted(listed, key=lambda d: d[1]) if kind.startswith('EX-99')), None)
            period_end, periodic_accession = fiscal_period(row['report_date'], periodic)
            records.append({
                'instrument': symbol, 'cik': f'{cik:010d}', 'accession_number': accession, 'form': row['form'], 'items': row['items'],
                'event_date': row['report_date'], 'filing_date': row['filing_date'], 'accepted_timestamp': header_utc.isoformat(),
                'accepted_timestamp_header': header_utc.isoformat(), 'accepted_timestamp_json': row['json_time'], 'accepted_timestamp_raw': row['json_time'],
                'acceptance_time_conflict': conflict, 'acceptance_time_json_offset_seconds': offset, 'accepted_timestamp_basis': basis,
                'acceptance_session': acceptance_session(header_utc), 'filing_url': folder + accession + '-index.htm',
                'primary_document_url': folder + row['primary_document'] if row.get('primary_document') else None,
                'release_document_url': folder + release[1] if release else UNAVAILABLE, 'release_document_type': release[0] if release else None,
                'fiscal_period_end': period_end or UNAVAILABLE, 'fiscal_period_basis': BASIS if period_end else None,
                'periodic_accession_number': periodic_accession, 'transcript_available': False, 'entity_name': index['entity_name'],
                'ingestion_timestamp': reply.fetched_at})
            if len(records) >= keep:
                break
        if not records:
            raise ProviderRejected([('INCOMPLETE_HISTORICAL_WINDOW', f'the SEC lists no 8-K with Item {EARNINGS_ITEM} for {symbol} between {start} and {end}')],
                                   provenance)
        return records, provenance
