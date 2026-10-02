"""U.S. Treasury 13-week bill auction results, for the bill leg of the fixed 70/30 ruler. Research storage only.

Source: Fiscal Data, "Treasury Securities Auctions Data" (public; no credential). Every value arrives as text and is
stored as text; the published price is checked against the official formula by ``firm_lab.treasury`` and a record that
fails is refused with the whole response. Nothing is computed here: the index lives in ``firm_lab.treasury``.

Two kinds of record are left out, and counted, rather than stored:
  * an auction that has been announced but whose result does not count as known yet (before 5:00 p.m. New York time on
    its auction date, the known-at rule of the frozen methodology);
  * nothing else. A past auction with a missing price is not skipped: it makes the response fail.

The response format follows the Fiscal Data API documentation; values such as a missing number arrive as the text
"null". A response that is not in that form is refused, not adapted.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from firm_lab import treasury
from firm_lab.errors import ProviderRejected, ProviderUnavailable
from firm_lab.provenance import Provenance, content_hash
from firm_lab.providers import TreasuryAuctionsProvider
from firm_lab.schemas import SCHEMA_VERSION

HOST = 'api.fiscaldata.treasury.gov'
ENDPOINT = 'https://' + HOST + '/services/api/fiscal_service/v1/accounting/od/auctions_query'
REQUIRED = ('cusip', 'security_type', 'security_term', 'auction_date', 'issue_date', 'maturity_date')
FEED = 'fiscaldata:auctions_query'
PAGE_SIZE, MAX_PAGES = 500, 4


def _text(value):
    """The published text, or None for the API's "null"."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text == '' or text.lower() == 'null' else text


class FiscalDataAuctionsProvider(TreasuryAuctionsProvider):
    name = 'U.S. Treasury Fiscal Data'

    def __init__(self, transport, *, page_size=PAGE_SIZE, max_pages=MAX_PAGES):
        self.transport = transport
        self.page_size, self.max_pages = int(page_size), int(max_pages)
        self.skipped = {'not_yet_known': 0}

    def _fetch(self, method, *, start=None, **_):
        if method != 'auctions':
            raise NotImplementedError
        try:
            since = date.fromisoformat(str(start)[:10])
        except ValueError:
            raise ProviderRejected([('MALFORMED_REQUEST', f'start={start!r} is not a date')]) from None
        rows, first, bodies, page = [], None, [], 1
        while True:
            url = (f'{ENDPOINT}?filter=security_type:eq:{treasury.SECURITY_TYPE},security_term:eq:{treasury.SECURITY_TERM},'
                   f'issue_date:gte:{since.isoformat()}&sort=auction_date,cusip&page%5Bnumber%5D={page}&page%5Bsize%5D={self.page_size}&format=json')
            reply = self.transport.get(url)
            if reply.status in (403, 429):
                raise ProviderUnavailable(f'Fiscal Data refused the request (HTTP {reply.status}); not retried', 'ERROR')
            if not reply.ok:
                raise ProviderUnavailable(f'no usable answer from Fiscal Data ({reply.error or "HTTP " + str(reply.status)})', 'ERROR')
            try:
                body = json.loads(reply.body)
            except (ValueError, UnicodeDecodeError):
                raise ProviderRejected([('MALFORMED_RESPONSE', 'the answer is not JSON')]) from None
            data = body.get('data') if isinstance(body, dict) else None
            meta = body.get('meta') if isinstance(body, dict) else None
            if not isinstance(data, list) or any(not isinstance(r, dict) for r in data) or not isinstance(meta, dict):
                raise ProviderRejected([('MALFORMED_RESPONSE', 'the answer has no "data" list of records and "meta"')])
            first = first or reply
            bodies.append(reply.body)
            rows.extend(data)
            try:
                pages = int(meta.get('total-pages'))
            except (TypeError, ValueError):
                raise ProviderRejected([('MALFORMED_RESPONSE', 'meta.total-pages is missing')]) from None
            if page >= pages:
                break
            page += 1
            if page > self.max_pages:
                raise ProviderRejected([('INCOMPLETE_HISTORICAL_WINDOW', f'{pages} pages; this sample reads at most {self.max_pages}')])
        provenance = Provenance(provider=self.name, source_id=first.url, source_timestamp=first.fetched_at, ingested_at=first.fetched_at,
                                known_at=first.fetched_at, schema_version=SCHEMA_VERSION, content_hash=content_hash(b''.join(bodies)))
        fetched = datetime.fromisoformat(first.fetched_at)
        records = []
        for row in rows:
            if any(_text(row.get(k)) is None for k in REQUIRED):
                raise ProviderRejected([('MALFORMED_RESPONSE', f'a record lacks one of {", ".join(REQUIRED)}')], provenance)
            if row.get('security_type') != treasury.SECURITY_TYPE or row.get('security_term') != treasury.SECURITY_TERM:
                raise ProviderRejected([('CONFLICTING_INSTRUMENT_IDENTITY', f'asked for 13-week bills, a record is {row.get("security_type")!r} '
                                                                           f'{row.get("security_term")!r}')], provenance)
            try:
                known = treasury.result_known_at(row['auction_date'])
            except ValueError:
                raise ProviderRejected([('MALFORMED_RESPONSE', f'auction_date {row.get("auction_date")!r} is not a date')], provenance) from None
            if known > fetched:
                self.skipped['not_yet_known'] += 1               # announced, or auctioned today before 5:00 p.m.: not known yet
                continue
            records.append({'cusip': _text(row.get('cusip')), 'security_type': row['security_type'], 'security_term': row['security_term'],
                            'auction_date': _text(row.get('auction_date')), 'issue_date': _text(row.get('issue_date')),
                            'maturity_date': _text(row.get('maturity_date')), 'high_discount_rate': _text(row.get('high_discnt_rate')),
                            'price_per100': _text(row.get('price_per100')), 'closing_time_comp': _text(row.get('closing_time_comp')),
                            'reopening': _text(row.get('reopening')), 'original_security_term': _text(row.get('original_security_term')),
                            'record_date': _text(row.get('record_date')), 'result_known_at': known.isoformat(), 'feed': FEED})
        return records, provenance
