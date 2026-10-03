"""Cash distributions of an exchange-traded fund, from the fund's own issuer, for Firm Lab research only. Used for one
thing: the total-return ruler. Nothing here is a feature, a signal or a selection, and nothing here can trade.

Issuer source (Vanguard). The fund page's own public data, ``/vmf/api/<TICKER>/distribution`` on investor.vanguard.com,
as seen on 2026-10-03:

    {"divCapGain": {"distributionFrequency": "Quarterly", "item": [
        {"type": "Dividend", "perShareAmount": "$0.955500", "isPerShareAmtPct": false,
         "recordDate": "2026-09-28T00:00:00-04:00", "reinvestmentDate": "2026-09-28T00:00:00-04:00",
         "payableDate": "2026-09-30T00:00:00-04:00", "reinvestPrice": "375.82", ...}, ...]}, ...}

  * The ex-dividend date is the feed's ``reinvestmentDate``: the issuer's own page shows that field under the heading
    "Ex-dividend date" for an ETF. It is not assumed from the record date.
  * The amount is the published text without the dollar sign; the dollar sign is the only statement of currency.
  * The feed gives no declaration or announcement time, so none is stored (UNAVAILABLE). What Firm Lab knows is that the
    record existed when it was fetched.
  * The feed holds only the most recent distributions. Older ones are not reconstructed from anywhere else.
  * Only the type "Dividend" is understood. Any other type (for example a capital-gain distribution) makes the answer
    unusable until a rule for it is written: it is not skipped and not guessed.

A response that is not in this form is refused whole. Nothing is repaired.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime

from firm_lab.errors import ProviderRejected, ProviderUnavailable
from firm_lab.provenance import Provenance, content_hash
from firm_lab.providers import CorporateActionsProvider
from firm_lab.schemas import SCHEMA_VERSION, UNAVAILABLE
from firm_lab.store import canonical

VANGUARD_HOST = 'investor.vanguard.com'
VANGUARD_URL = 'https://' + VANGUARD_HOST + '/vmf/api/{symbol}/distribution'
RESEARCH_AGENT = 'FirmLabResearch/1.0 (personal research; hand-started single requests)'
AMOUNT = re.compile(r'^\$(\d+\.\d+)$')
SYMBOL = re.compile(r'^[A-Z]{1,6}$')
KNOWN_TYPES = {'Dividend': 'income_dividend'}
EX_DATE_BASIS = 'ex-dividend date: the issuer feed’s reinvestmentDate, which the issuer’s own page labels "Ex-dividend date" for an ETF'
KEPT = ('type', 'perShareAmount', 'isPerShareAmtPct', 'recordDate', 'reinvestmentDate', 'payableDate', 'reinvestPrice')


def _day(text, what):
    try:
        return datetime.fromisoformat(str(text)).date()
    except (TypeError, ValueError):
        raise ProviderRejected([('MALFORMED_RESPONSE', f'{what} {text!r} is not a date')]) from None


class VanguardDistributionsProvider(CorporateActionsProvider):
    """The issuer's published distributions for one of its ETFs."""
    name = 'Vanguard'

    def __init__(self, transport):
        self.transport = transport
        self.frequency = None

    def _fetch(self, method, *, instrument, start=None, end=None, **_):
        if method != 'actions':
            raise NotImplementedError
        symbol = str(instrument).upper()
        if not SYMBOL.match(symbol):
            raise ProviderRejected([('MALFORMED_REQUEST', f'{instrument!r} is not a ticker')])
        reply = self.transport.get(VANGUARD_URL.format(symbol=symbol), {'Accept': 'application/json'})
        if reply.status in (401, 403, 429):
            raise ProviderUnavailable(f'the issuer refused the request (HTTP {reply.status}); not retried and not worked around', 'ERROR')
        if not reply.ok:
            raise ProviderUnavailable(f'no usable answer from the issuer ({reply.error or "HTTP " + str(reply.status)})', 'ERROR')
        provenance = Provenance(provider=self.name, source_id=reply.url, source_timestamp=reply.fetched_at, ingested_at=reply.fetched_at,
                                known_at=reply.fetched_at, schema_version=SCHEMA_VERSION, content_hash=content_hash(reply.body))
        try:
            body = json.loads(reply.body)
        except (ValueError, UnicodeDecodeError):
            raise ProviderRejected([('MALFORMED_RESPONSE', 'the answer is not JSON (the issuer may have sent a web page instead)')], provenance) from None
        section = body.get('divCapGain') if isinstance(body, dict) else None
        items = section.get('item') if isinstance(section, dict) else None
        if not isinstance(items, list) or not items or any(not isinstance(i, dict) for i in items):
            raise ProviderRejected([('MALFORMED_RESPONSE', 'the answer has no "divCapGain.item" list of distributions')], provenance)
        self.frequency = section.get('distributionFrequency')
        low = date.fromisoformat(str(start)[:10]) if start else None
        high = date.fromisoformat(str(end)[:10]) if end else None
        records = []
        try:
            for item in items:
                kind = item.get('type')
                if kind not in KNOWN_TYPES:
                    raise ProviderRejected([('UNKNOWN_DISTRIBUTION_TYPE', f'{kind!r}: no rule is written for this kind of distribution')])
                amount = AMOUNT.match(str(item.get('perShareAmount') or ''))
                if not amount or item.get('isPerShareAmtPct') is not False:
                    raise ProviderRejected([('MALFORMED_RESPONSE', f'perShareAmount {item.get("perShareAmount")!r} is not a dollar amount per share')])
                ex_date = _day(item.get('reinvestmentDate'), 'reinvestmentDate')
                record_date = _day(item.get('recordDate'), 'recordDate')
                pay_date = _day(item.get('payableDate'), 'payableDate')
                if pay_date < ex_date:
                    raise ProviderRejected([('IMPOSSIBLE_VALUE', f'payable {pay_date} is before the ex-dividend date {ex_date}')])
                if (low and ex_date < low) or (high and ex_date > high):
                    continue
                records.append({
                    'instrument': symbol, 'action_type': 'cash_dividend', 'provider_action': kind, 'effective_date': ex_date.isoformat(),
                    'effective_date_basis': EX_DATE_BASIS, 'announcement_timestamp': UNAVAILABLE, 'value': amount.group(1),
                    'value_meaning': 'cash per share, as paid', 'currency': 'USD', 'contra_instrument': '', 'name': None,
                    'record_date': record_date.isoformat(), 'pay_date': pay_date.isoformat(), 'distribution_type': KNOWN_TYPES[kind],
                    'source_record': canonical({k: item.get(k) for k in KEPT})})
        except ProviderRejected as error:
            raise ProviderRejected(error.issues, provenance) from None
        if not records:
            raise ProviderRejected([('INCOMPLETE_HISTORICAL_WINDOW', f'the issuer lists no distribution of {symbol} between {start} and {end}')], provenance)
        return records, provenance
