"""Sharadar fundamentals and corporate actions, for Firm Lab research only. Raw reported facts: no ratio, score or
rank is computed from them.

Two delivery channels exist: Sharadar Direct (api.sharadar.com, CSV with a header row) and Nasdaq Data Link
(datatables JSON). Both are read by column NAME. Without an operator-supplied key this adapter is never
constructed. Formats follow the vendor documentation read on 2026-10-02; no live call has been made.

As reported and restated are kept apart. Sharadar's AR dimensions (ARQ, ARY, ART) exclude restatements and are
indexed to the filing date; its MR dimensions (MRQ, MRY, MRT) include restatements and are indexed to the report
period. Each row keeps its dimension, and a restated value never replaces an as-reported one.

Filing time. Sharadar supplies a filing DATE only. ``filing_timestamp`` is therefore stored as UNAVAILABLE; an
acceptance time is never derived from the date. The precise time belongs to EDGAR and is kept in its own field.
"""
from __future__ import annotations

import csv
import io
import json
from decimal import Decimal

from firm_lab.errors import ProviderRejected, ProviderUnavailable
from firm_lab.provenance import Provenance, content_hash
from firm_lab.providers import CorporateActionsProvider, FundamentalsProvider
from firm_lab.schemas import SCHEMA_VERSION, UNAVAILABLE

DIRECT_HOST, NASDAQ_HOST = 'api.sharadar.com', 'data.nasdaq.com'
AS_REPORTED, RESTATED = ('ARQ', 'ARY', 'ART'), ('MRQ', 'MRY', 'MRT')
# provider column -> (Firm Lab metric, units, currency rule). "reporting" = the company's reporting currency (from TICKERS).
METRICS = {
    'revenue': ('revenue', 'currency', 'reporting'), 'gp': ('gross_profit', 'currency', 'reporting'),
    'opinc': ('operating_income', 'currency', 'reporting'), 'ebit': ('ebit', 'currency', 'reporting'),
    'ebitda': ('ebitda', 'currency', 'reporting'), 'netinc': ('net_income', 'currency', 'reporting'),
    'eps': ('eps_basic', 'currency_per_share', 'reporting'), 'epsdil': ('eps_diluted', 'currency_per_share', 'reporting'),
    'fcf': ('free_cash_flow', 'currency', 'reporting'), 'ncfo': ('operating_cash_flow', 'currency', 'reporting'),
    'capex': ('capital_expenditure', 'currency', 'reporting'), 'debt': ('total_debt', 'currency', 'reporting'),
    'cashneq': ('cash_and_equivalents', 'currency', 'reporting'), 'equity': ('total_equity', 'currency', 'reporting'),
    'assets': ('total_assets', 'currency', 'reporting'), 'liabilities': ('total_liabilities', 'currency', 'reporting'),
    'invcap': ('invested_capital', 'currency', 'reporting'), 'taxexp': ('tax_expense', 'currency', 'reporting'),
    'sharesbas': ('shares_basic', 'shares', None), 'shareswa': ('shares_weighted', 'shares', None),
    'shareswadil': ('shares_weighted_diluted', 'shares', None),
    'marketcap': ('market_capitalization', 'currency', 'USD'), 'ev': ('enterprise_value', 'currency', 'USD'),
    'grossmargin': ('gross_margin', 'ratio', None), 'netmargin': ('net_margin', 'ratio', None), 'fxusd': ('fx_to_usd', 'ratio', None),
}
# provider action code -> Firm Lab action type. Anything not listed is kept as "other" with its own code.
ACTIONS = {
    'dividend': 'cash_dividend', 'split': 'split',
    'tickerchangefrom': 'symbol_change', 'tickerchangeto': 'symbol_change',
    'delisted': 'delisting', 'regulatorydelisting': 'delisting', 'voluntarydelisting': 'delisting', 'bankruptcyliquidation': 'delisting',
    'spinoff': 'spin_off', 'spunofffrom': 'spin_off', 'spinoffdividend': 'spin_off',
    'acquisitionby': 'merger', 'acquisitionof': 'merger', 'mergerfrom': 'merger', 'mergerto': 'merger',
}
VALUE_MEANING = {'dividend': 'cash dividend per share as supplied (adjustment basis not confirmed by the vendor documentation)',
                 'split': 'resulting shares per original share, as supplied', 'spinoffdividend': 'value of spun-off shares per parent share, as supplied'}
DATE_BASIS = 'provider action date, date only; whether it is the ex-date is not confirmed by the vendor documentation'


def _number(text):
    if text is None or str(text).strip() == '':
        return None
    try:
        value = Decimal(str(text))
    except Exception:
        raise ProviderRejected([('IMPOSSIBLE_VALUE', f'{text!r} is not a number')]) from None
    if not value.is_finite():
        raise ProviderRejected([('IMPOSSIBLE_VALUE', f'{text!r} is not a finite number')])
    return value


class _Sharadar:
    """Shared request and parsing code for both channels."""
    name = 'Sharadar'

    def __init__(self, transport, api_key, channel):
        if not api_key or channel not in ('direct', 'nasdaq'):
            raise ProviderUnavailable('no Sharadar access is configured (key and channel)', 'NOT_CONFIGURED')
        self.transport, self._key, self.channel = transport, api_key, channel
        self._ticker_rows = {}

    def _table(self, table, **filters):
        """Rows of one Sharadar table as dicts keyed by column name, plus the reply. ``table`` is one of
        fundamentals, tickers, actions."""
        query = '&'.join(f'{k}={v}' for k, v in filters.items() if v is not None)
        if self.channel == 'direct':
            url = f'https://{DIRECT_HOST}/v1.0/data/{table}?{query}&format=csv&api_key={self._key}'
            reply = self.transport.get(url)
        else:
            code = {'fundamentals': 'SF1', 'tickers': 'TICKERS', 'actions': 'ACTIONS'}[table]
            url = f'https://{NASDAQ_HOST}/api/v3/datatables/SHARADAR/{code}.json?{query}'
            reply = self.transport.get(url, {'x-api-token': self._key})
        if reply.status in (401, 403):
            raise ProviderUnavailable(f'Sharadar did not grant access to {table} (HTTP {reply.status}): key or subscription', 'ERROR')
        if reply.status == 429:
            raise ProviderUnavailable('Sharadar rate limit reached (HTTP 429); not retried', 'ERROR')
        if not reply.ok:
            raise ProviderUnavailable(f'no usable answer from Sharadar for {table} ({reply.error or "HTTP " + str(reply.status)})', 'ERROR')
        try:
            if self.channel == 'direct':
                rows = list(csv.DictReader(io.StringIO(reply.body.decode('utf-8'))))
                if rows and 'ticker' not in rows[0]:
                    raise ValueError('no ticker column')
            else:
                body = json.loads(reply.body, parse_float=Decimal)
                columns = [c['name'] for c in body['datatable']['columns']]
                rows = [dict(zip(columns, values)) for values in body['datatable']['data']]
                if (body.get('meta') or {}).get('next_cursor_id'):
                    raise ProviderRejected([('INCOMPLETE_HISTORICAL_WINDOW', f'{table}: more pages remained than this sample reads')])
        except ProviderRejected:
            raise
        except (ValueError, KeyError, TypeError, UnicodeDecodeError):
            raise ProviderRejected([('MALFORMED_RESPONSE', f'{table}: the answer is not in the documented form')]) from None
        return rows, reply

    def _ticker(self, symbol):
        if symbol not in self._ticker_rows:
            rows, _ = self._table('tickers', ticker=symbol)
            mine = [r for r in rows if str(r.get('ticker', '')).upper() == symbol and str(r.get('table', 'SF1')).upper() in ('SF1', 'SEP', '')]
            self._ticker_rows[symbol] = mine[0] if mine else {}
        return self._ticker_rows[symbol]

    def _provenance(self, reply):
        return Provenance(provider=self.name, source_id=reply.url, source_timestamp=reply.fetched_at, ingested_at=reply.fetched_at,
                          known_at=reply.fetched_at, schema_version=SCHEMA_VERSION, content_hash=content_hash(reply.body))


class SharadarFundamentalsProvider(_Sharadar, FundamentalsProvider):
    """All reported values come through ``financial_statements``; the other interface methods are not supplied
    separately, so nothing is fetched twice under another name."""

    def __init__(self, transport, api_key, channel, *, dimensions=('ARQ', 'MRQ'), since=None):
        super().__init__(transport, api_key, channel)
        self.dimensions, self.since = tuple(dimensions), since

    def _fetch(self, method, *, instrument, known_at=None, **_):
        if method != 'financial_statements':
            raise NotImplementedError
        symbol = str(instrument).upper()
        meta = self._ticker(symbol)
        currency = (meta.get('currency') or '').strip() or None
        records, reply = [], None
        for dimension in self.dimensions:
            window = {} if not self.since else {'from': self.since} if self.channel == 'direct' else {'calendardate.gte': self.since}
            rows, reply = self._table('fundamentals', ticker=symbol, dimension=dimension, **window)
            for row in rows:
                if str(row.get('ticker', '')).upper() != symbol:
                    raise ProviderRejected([('CONFLICTING_INSTRUMENT_IDENTITY', f'asked for {symbol}, a row is for {row.get("ticker")!r}')],
                                           self._provenance(reply))
                dim = str(row.get('dimension') or '').upper()
                datekey = row.get('datekey') or row.get('date')        # Sharadar Direct calls the same column "date"
                as_reported = dim in AS_REPORTED
                base = {'instrument': symbol, 'provider_instrument_id': meta.get('permaticker'), 'dimension': dim,
                        'reporting_basis': 'as_reported' if as_reported else 'restated' if dim in RESTATED else dim,
                        'fiscal_period': row.get('fiscalperiod') or None, 'period_end': row.get('reportperiod'),
                        'calendar_date': row.get('calendardate'), 'provider_datekey': datekey,
                        'filing_date': datekey if as_reported else UNAVAILABLE,      # restated rows are indexed to the period, not a filing
                        'filing_timestamp': UNAVAILABLE,                             # a date is not a time; EDGAR's time is a separate field
                        'last_updated': row.get('lastupdated'), 'known_at': reply.fetched_at,
                        'is_delisted': str(meta.get('isdelisted', '')).upper() == 'Y' if meta else None}
                for column, (metric, units, rule) in METRICS.items():
                    value = _number(row.get(column))
                    if value is None:
                        continue                                                     # not reported: no row, nothing filled in
                    records.append({**base, 'metric': metric, 'provider_metric': column, 'value': value, 'units': units,
                                    'currency': 'USD' if rule == 'USD' else currency if rule == 'reporting' else None})
        return records, self._provenance(reply)


class SharadarCorporateActionsProvider(_Sharadar, CorporateActionsProvider):
    def _fetch(self, method, *, instrument, start=None, end=None, **_):
        if method != 'actions':
            raise NotImplementedError
        symbol = str(instrument).upper()
        window = {'from': str(start)[:10] if start else None, 'to': str(end)[:10] if end else None} if self.channel == 'direct' else {}
        rows, reply = self._table('actions', ticker=symbol, **window)
        records = []
        for row in rows:
            if str(row.get('ticker', '')).upper() != symbol:
                raise ProviderRejected([('CONFLICTING_INSTRUMENT_IDENTITY', f'asked for {symbol}, a row is for {row.get("ticker")!r}')],
                                       self._provenance(reply))
            when = str(row.get('date') or '')
            if (start and when < str(start)[:10]) or (end and when > str(end)[:10]):
                continue
            code = str(row.get('action') or '').lower()
            records.append({'instrument': symbol, 'action_type': ACTIONS.get(code, 'other'), 'provider_action': code or None,
                            'effective_date': when or None, 'effective_date_basis': DATE_BASIS,
                            'announcement_timestamp': UNAVAILABLE,                   # Sharadar gives no announcement time; none is made up
                            'value': _number(row.get('value')), 'value_meaning': VALUE_MEANING.get(code, 'not documented by the vendor'),
                            'contra_instrument': row.get('contraticker') or None, 'contra_name': row.get('contraname') or None,
                            'name': row.get('name') or None})
        return records, self._provenance(reply)
