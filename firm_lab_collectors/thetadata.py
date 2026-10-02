"""ThetaData option chains, for Firm Lab research storage only. No option is scored, ranked, recommended or filled.

ThetaData is reached through the vendor's own Theta Terminal running on the operator's machine (127.0.0.1:25503,
API v3). This adapter holds no ThetaData credential: the terminal is started and signed in by the operator.

Greeks and implied volatility are ThetaData's calculations, not facts of the market. Each one is carried under a
name that says so (``thetadata_provider_delta``, ``thetadata_provider_implied_volatility``, ...) together with who
computed it, under which documented model and settings, and when. A bare ``delta`` never leaves this module, and a
Greek ThetaData did not send is left out, not estimated.

Formats follow the vendor documentation read on 2026-10-02. The v3 field names for end-of-day quotes and Greeks
could not be confirmed from the documentation, and no live call has been made. Fields are therefore read by name
(with the documented v2 spellings accepted as alternatives), and a response missing a required field is refused.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal

from firm_lab.errors import ProviderRejected, ProviderUnavailable
from firm_lab.provenance import Provenance, content_hash
from firm_lab.providers import OptionsMarketDataProvider
from firm_lab.schemas import SCHEMA_VERSION, UNAVAILABLE, greek_field
from firm_lab.sessions import ET

HOST = '127.0.0.1:25503'
BASE = 'http://' + HOST + '/v3'
VENDOR = 'thetadata'
MODEL = 'Black-Scholes, European exercise (ThetaData standard Greeks)'
MODEL_VERSION = ('ThetaData greeks version 2 (vendor default); rate: SOFR, most recent published; dividends: ignored; '
                 'no override sent by Firm Lab; documented at thetadata.net/docs/Articles/Data-And-Requests/Option-Greeks.html (read 2026-10-02)')
ERRORS = {471: 'the ThetaData subscription tier does not include this data', 474: 'Theta Terminal is not connected to ThetaData',
          476: 'Theta Terminal saw a different local address than before (use 127.0.0.1 consistently)', 571: 'ThetaData server is starting'}
GREEK_ALIASES = {'delta': ('delta',), 'gamma': ('gamma',), 'theta': ('theta',), 'vega': ('vega',), 'rho': ('rho',),
                 'implied_volatility': ('implied_vol', 'implied_volatility', 'iv')}
LOCAL_TIME = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$')


def _first(row, *names):
    for name in names:
        if row.get(name) not in (None, ''):
            return row[name]
    return None


def _local_to_utc(text):
    """ThetaData v3 timestamps carry no offset and are documented (for v2) as New York time. Returns (UTC ISO, raw)."""
    raw = str(text)
    if not LOCAL_TIME.match(raw):
        return raw, raw                                    # left as sent; validation will refuse it if it is not a timestamp
    return datetime.fromisoformat(raw[:26]).replace(tzinfo=ET).astimezone(timezone.utc).isoformat(), raw


def _right(value):
    text = str(value or '').strip().lower()
    return {'c': 'call', 'call': 'call', 'p': 'put', 'put': 'put'}.get(text, text or None)


def _expiration(value):
    text = str(value or '')
    return f'{text[:4]}-{text[4:6]}-{text[6:8]}' if re.fullmatch(r'\d{8}', text) else text or None


def contract_id(symbol, expiration, right, strike):
    """An OCC-style identifier built only from the four identity fields the provider sent."""
    try:
        thousandths = int((Decimal(str(strike)) * 1000).to_integral_exact())
        return f'{symbol}{expiration[2:4]}{expiration[5:7]}{expiration[8:10]}{right[0].upper()}{thousandths:08d}'
    except Exception:
        return None


class ThetaDataOptionsProvider(OptionsMarketDataProvider):
    name = 'ThetaData'

    def __init__(self, transport, *, terminal_declared=True, whole_chain=False):
        if not terminal_declared:
            raise ProviderUnavailable('no ThetaData access is configured (subscription and a running Theta Terminal)', 'NOT_CONFIGURED')
        self.transport = transport
        self.whole_chain = bool(whole_chain)

    def nearest_expiration(self, symbol, day):
        """The first listed expiration on or after ``day`` (YYYYMMDD), as the provider lists it. A sample size, not a selection."""
        rows, _ = self._rows('/option/list/expirations', 'expirations', symbol=symbol)
        listed = sorted(str(_first(r, 'expiration', 'exp') or '').replace('-', '') for r in rows)
        later = [e for e in listed if re.fullmatch(r'\d{8}', e) and e >= day]
        if not later:
            raise ProviderRejected([('MALFORMED_RESPONSE', f'no listed expiration on or after {day} for {symbol}')])
        return later[0]

    def _rows(self, path, what, **params):
        query = '&'.join(f'{k}={v}' for k, v in params.items() if v is not None)
        reply = self.transport.get(f'{BASE}{path}?{query}&format=json')
        if reply.status == 0:
            raise ProviderUnavailable(f'Theta Terminal did not answer on {HOST} ({reply.error})', 'ERROR')
        if reply.status in ERRORS:
            raise ProviderUnavailable(f'{ERRORS[reply.status]} (code {reply.status}, {what})', 'ERROR')
        if reply.status == 472:
            return [], reply                               # NO_DATA: an empty answer, refused later as an empty response
        if not reply.ok:
            raise ProviderUnavailable(f'ThetaData refused the {what} request (code {reply.status})', 'ERROR')
        try:
            body = json.loads(reply.body, parse_float=Decimal)
        except (ValueError, UnicodeDecodeError):
            raise ProviderRejected([('MALFORMED_RESPONSE', f'{what}: not JSON')]) from None
        rows = body.get('response') if isinstance(body, dict) else body
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise ProviderRejected([('MALFORMED_RESPONSE', f'{what}: expected a list of objects with named fields')])
        return rows, reply

    @staticmethod
    def _key(row):
        return (_expiration(_first(row, 'expiration', 'exp')), str(_first(row, 'strike')), _right(_first(row, 'right')))

    def _fetch(self, method, *, underlying=None, as_of=None, expiration=None, **_):
        if method != 'chain':
            raise NotImplementedError
        symbol = str(underlying).upper()
        day = str(as_of)[:10].replace('-', '')
        if expiration:
            wanted = str(expiration).replace('-', '')
        else:
            wanted = '*' if self.whole_chain else self.nearest_expiration(symbol, day)
        common = {'symbol': symbol, 'expiration': wanted, 'date': day}
        quotes, reply = self._rows('/option/history/eod', 'end-of-day quotes', **common)
        interest, reply_oi = self._rows('/option/history/open_interest', 'open interest', **common)
        greeks, reply_greeks = self._rows('/option/history/greeks/eod', 'end-of-day Greeks', **common)
        provenance = Provenance(provider=self.name, source_id=reply.url, source_timestamp=reply.fetched_at, ingested_at=reply.fetched_at,
                                known_at=reply.fetched_at, schema_version=SCHEMA_VERSION, exchange_session_date=str(as_of)[:10],
                                content_hash=content_hash(reply.body + reply_oi.body + reply_greeks.body))
        oi_by = {self._key(r): r for r in interest}
        greeks_by = {self._key(r): r for r in greeks}
        records = []
        for row in quotes:
            if str(_first(row, 'symbol', 'root') or '').upper() != symbol:
                raise ProviderRejected([('CONFLICTING_INSTRUMENT_IDENTITY', f'asked for {symbol}, a contract is on {_first(row, "symbol", "root")!r}')],
                                       provenance)
            exp, strike, right = self._key(row)
            when, raw = _local_to_utc(_first(row, 'created', 'timestamp', 'last_trade'))
            record = {'contract_id': contract_id(symbol, exp or '', right or ' ', strike), 'underlying': symbol, 'option_type': right,
                      'strike': strike, 'expiration': exp, 'bid': _first(row, 'bid'), 'bid_size': _first(row, 'bid_size'), 'ask': _first(row, 'ask'),
                      'ask_size': _first(row, 'ask_size'), 'quote_timestamp': when, 'quote_timestamp_raw': raw, 'volume': _first(row, 'volume'),
                      'feed': 'thetadata:opra-end-of-day'}
            oi = oi_by.get((exp, strike, right))
            if oi is not None:
                record['open_interest'] = _first(oi, 'open_interest')
                record['open_interest_timestamp'] = _local_to_utc(_first(oi, 'timestamp'))[0] if _first(oi, 'timestamp') else UNAVAILABLE
            g = greeks_by.get((exp, strike, right))
            if g is not None:
                sent = False
                for greek, names in GREEK_ALIASES.items():
                    value = _first(g, *names)
                    if value is not None:
                        record[greek_field(greek, 'provider', VENDOR)] = value          # e.g. thetadata_provider_delta
                        sent = True
                if sent:
                    stamp = _first(g, 'timestamp', 'created')
                    under = _first(g, 'underlying_timestamp')
                    record.update(greeks_provider='ThetaData', greeks_model=MODEL, greeks_model_version=MODEL_VERSION,
                                  greeks_timestamp=_local_to_utc(stamp)[0] if stamp else UNAVAILABLE,
                                  underlying_price=_first(g, 'underlying_price'),
                                  underlying_timestamp=_local_to_utc(under)[0] if under else UNAVAILABLE)
            records.append(record)
        return records, provenance
