"""Massive (formerly Polygon.io) stock market data, for Firm Lab research only: 1-minute bars, trades and NBBO quotes.

Raw storage and data-quality diagnostics only. No VWAP signal, relative volume, opening range or flow measure is
derived from anything fetched here.

Without an operator-supplied API key this adapter is never constructed and the capability stays UNAVAILABLE.
Request and response formats follow the vendor documentation read on 2026-10-01; no live call has been made, so a
response that does not match is refused rather than adapted.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from firm_lab import quality
from firm_lab.errors import ProviderRejected, ProviderUnavailable
from firm_lab.provenance import Provenance, content_hash
from firm_lab.providers import IntradayMarketDataProvider
from firm_lab.schemas import SCHEMA_VERSION
from firm_lab.sessions import ET

HOST = 'api.massive.com'
BASE = 'https://' + HOST
FEED = 'massive:sip-consolidated'
MAX_PAGES = 4


def _when(nanoseconds) -> str:
    """UTC ISO time (microsecond precision) from integer nanoseconds. The exact integer is stored beside it as text."""
    whole, rest = divmod(int(nanoseconds), 1_000_000_000)
    return (datetime.fromtimestamp(whole, timezone.utc) + timedelta(microseconds=rest // 1000)).isoformat()


class MassiveMarketDataProvider(IntradayMarketDataProvider):
    name = 'Massive'

    def __init__(self, transport, api_key, *, page_limit=50000, max_pages=MAX_PAGES):
        if not api_key:
            raise ProviderUnavailable('no Massive API key is configured', 'NOT_CONFIGURED')
        self.transport = transport
        self._headers = {'Authorization': 'Bearer ' + api_key}
        self.page_limit, self.max_pages = int(page_limit), int(max_pages)

    # ---------------------------------------------------------------- HTTP
    def _pages(self, url, what):
        """Follows ``next_url`` on the same host, a bounded number of times. Returns (result rows, first body, first reply)."""
        rows, first, first_body, pages = [], None, None, 0
        while url and pages < self.max_pages:
            reply = self.transport.get(url, self._headers)
            if reply.status == 401:
                raise ProviderUnavailable('Massive did not accept the API key (HTTP 401)', 'ERROR')
            if reply.status == 403:
                raise ProviderUnavailable(f'the Massive plan does not include {what} (HTTP 403)', 'ERROR')
            if reply.status == 429:
                raise ProviderUnavailable('Massive rate limit reached (HTTP 429); not retried', 'ERROR')
            if not reply.ok:
                raise ProviderUnavailable(f'no usable answer from Massive for {what} ({reply.error or "HTTP " + str(reply.status)})', 'ERROR')
            try:
                body = json.loads(reply.body, parse_float=Decimal)
            except (ValueError, UnicodeDecodeError):
                raise ProviderRejected([('MALFORMED_RESPONSE', f'{what}: not JSON')]) from None
            if not isinstance(body, dict) or body.get('status') not in ('OK', 'DELAYED'):
                raise ProviderRejected([('MALFORMED_RESPONSE', f'{what}: status {body.get("status") if isinstance(body, dict) else "?"!r}')])
            if first is None:
                first, first_body = reply, body
            results = body.get('results') or []
            if not isinstance(results, list):
                raise ProviderRejected([('MALFORMED_RESPONSE', f'{what}: results is not a list')])
            rows.extend(results)
            url = body.get('next_url')
            if url and not str(url).startswith(BASE + '/'):
                raise ProviderRejected([('MALFORMED_RESPONSE', f'{what}: next_url points to another host')])
            pages += 1
        truncated = bool(url)
        return rows, first_body, first, truncated

    def _provenance(self, reply, rows, session_date=None):
        return Provenance(provider=self.name, source_id=reply.url, source_timestamp=reply.fetched_at, ingested_at=reply.fetched_at,
                          known_at=reply.fetched_at, schema_version=SCHEMA_VERSION, exchange_session_date=session_date,
                          content_hash=content_hash(json.dumps(rows, sort_keys=True, default=str)))

    # ---------------------------------------------------------------- interface methods
    def _fetch(self, method, *, instrument, session_date=None, start=None, end=None, **_):
        symbol = str(instrument).upper()
        if method == 'bars_1m':
            return self._bars(symbol, str(session_date))
        if method in ('trades', 'quote_snapshots'):
            return self._ticks(symbol, method, start, end)
        raise NotImplementedError

    def _bars(self, symbol, day):
        url = f'{BASE}/v2/aggs/ticker/{symbol}/range/1/minute/{day}/{day}?adjusted=false&sort=asc&limit={self.page_limit}'
        rows, body, reply, truncated = self._pages(url, '1-minute bars')
        provenance = self._provenance(reply, rows, day)
        if str(body.get('ticker', '')).upper() != symbol:
            raise ProviderRejected([('CONFLICTING_INSTRUMENT_IDENTITY', f'asked for {symbol}, the answer is for {body.get("ticker")!r}')], provenance)
        if body.get('adjusted') is not False:
            raise ProviderRejected([('ADJUSTMENT_MISMATCH', 'unadjusted bars were requested; the answer is not marked unadjusted')], provenance)
        if truncated:
            raise ProviderRejected([('INCOMPLETE_HISTORICAL_WINDOW', 'more pages remained than this sample allows')], provenance)
        records = []
        for bar in rows:
            if not isinstance(bar, dict) or not isinstance(bar.get('t'), int):
                raise ProviderRejected([('MALFORMED_RESPONSE', 'a bar has no integer start time')], provenance)
            start = datetime.fromtimestamp(bar['t'] / 1000, timezone.utc)
            records.append({'instrument': symbol, 'bar_start': start.isoformat(), 'bar_start_raw': str(bar['t']), 'interval': '1m',
                            'open': bar.get('o'), 'high': bar.get('h'), 'low': bar.get('l'), 'close': bar.get('c'), 'volume': bar.get('v'),
                            'vwap': bar.get('vw'), 'trade_count': bar.get('n'), 'session': quality.session_of(start) or 'outside_hours',
                            'exchange_session_date': start.astimezone(ET).date().isoformat(), 'adjusted': False, 'feed': FEED})
        return records, provenance

    def _ticks(self, symbol, method, start, end):
        kind = 'trades' if method == 'trades' else 'quotes'
        low, high = quality.parse_timestamp(start)[0], quality.parse_timestamp(end)[0]
        if low is None or high is None:
            raise ProviderRejected([('MALFORMED_REQUEST', 'start and end must be timezone-aware timestamps')])
        ns = lambda moment: int(moment.timestamp()) * 1_000_000_000 + moment.microsecond * 1000
        url = (f'{BASE}/v3/{kind}/{symbol}?timestamp.gte={ns(low)}&timestamp.lt={ns(high)}&order=asc&sort=timestamp'
               f'&limit={min(self.page_limit, 50000)}')
        rows, _, reply, truncated = self._pages(url, 'trades' if kind == 'trades' else 'NBBO quotes')
        provenance = self._provenance(reply, rows)
        if truncated:
            raise ProviderRejected([('INCOMPLETE_HISTORICAL_WINDOW', 'more pages remained than this sample allows')], provenance)
        records, last = [], None
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('sip_timestamp'), int) or isinstance(row.get('sip_timestamp'), bool):
                raise ProviderRejected([('MALFORMED_RESPONSE', f'a {kind[:-1]} has no integer sip_timestamp')], provenance)
            if last is not None and row['sip_timestamp'] < last:                  # checked on the exact nanoseconds, before any conversion
                raise ProviderRejected([('NON_MONOTONIC_TIMESTAMPS', f'sip_timestamp goes backwards at {row["sip_timestamp"]}')], provenance)
            last = row['sip_timestamp']
            common = {'instrument': symbol, 'feed': FEED, 'conditions': row.get('conditions'), 'sequence_number': row.get('sequence_number'),
                      'tape': row.get('tape'),
                      'participant_timestamp_raw': None if row.get('participant_timestamp') is None else str(row['participant_timestamp'])}
            if kind == 'trades':
                records.append({**common, 'trade_timestamp': _when(row['sip_timestamp']), 'trade_timestamp_raw': str(row['sip_timestamp']),
                                'price': row.get('price'), 'size': row.get('size'), 'decimal_size': row.get('decimal_size'),
                                'exchange': row.get('exchange'), 'trade_id': row.get('id'), 'trf_id': row.get('trf_id'),
                                'correction': row.get('correction')})
            else:
                records.append({**common, 'quote_timestamp': _when(row['sip_timestamp']), 'quote_timestamp_raw': str(row['sip_timestamp']),
                                'bid': row.get('bid_price'), 'bid_size': row.get('bid_size'), 'bid_exchange': row.get('bid_exchange'),
                                'ask': row.get('ask_price'), 'ask_size': row.get('ask_size'), 'ask_exchange': row.get('ask_exchange'),
                                'indicators': row.get('indicators')})
        return records, provenance
