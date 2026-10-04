"""Reads Sharadar bulk files the operator downloaded. File reader only: no network, no key, no login.

Column names follow the vendor documentation read on 2026-10-04. NO REAL FILE HAS BEEN READ YET: the layout is unproven
until the validation sample is ingested. A file whose header lacks a documented column is refused whole.

Vendor facts this reader relies on (``historical_market_data_policy.md``): open, high, low, close and volume are
split-adjusted as of the download; ``closeunadj`` is the price printed on the day; ``closeadj`` is the vendor's
split, dividend and spin-off adjusted close. The permanent identifier ``permaticker`` is the security key; a ticker is
only a label and can change or be reused.
"""
from __future__ import annotations

import csv
import re

ADAPTER = 'sharadar-files-v1'
SOURCE = 'Sharadar'
PRICE_COLUMNS = ('ticker', 'date', 'open', 'high', 'low', 'close', 'volume', 'closeadj', 'closeunadj', 'lastupdated')
TICKER_COLUMNS = ('table', 'permaticker', 'ticker', 'name', 'exchange', 'isdelisted', 'category', 'currency', 'firstpricedate', 'lastpricedate')
ACTION_COLUMNS = ('date', 'action', 'ticker', 'name', 'value', 'contraticker', 'contraname')
SP500_COLUMNS = ('date', 'action', 'ticker', 'name')
PRICE_TABLES = {'SEP': 'stocks', 'STOCKS': 'stocks', 'SFP': 'funds', 'FUNDS': 'funds'}
# provider action code -> Firm Lab type. A code not listed is kept as "other" with the provider's own code.
ACTIONS = {'dividend': 'cash_dividend', 'split': 'split', 'adrratiosplit': 'split',
           'tickerchangefrom': 'symbol_change', 'tickerchangeto': 'symbol_change',
           'delisted': 'delisting', 'regulatorydelisting': 'delisting', 'voluntarydelisting': 'delisting', 'bankruptcyliquidation': 'delisting',
           'spinoff': 'spin_off', 'spunofffrom': 'spin_off', 'spinoffdividend': 'spin_off',
           'acquisitionby': 'merger', 'acquisitionof': 'merger', 'mergerfrom': 'merger', 'mergerto': 'merger',
           'listed': 'listing', 'relation': 'other', 'initiated': 'other'}
_CIK = re.compile(r'CIK=0*(\d+)', re.I)


class UnexpectedFileLayout(ValueError):
    pass


def _reader(path, required):
    handle = open(path, newline='', encoding='utf-8-sig')
    reader = csv.DictReader(handle)
    header = [h.strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in required if c not in header]
    if missing:
        handle.close()
        raise UnexpectedFileLayout('UNEXPECTED_FILE_LAYOUT: missing ' + ', '.join(missing))
    reader.fieldnames = header
    return handle, reader


def prices(path):
    """Neutral bar rows from a stock-price or fund-price file."""
    handle, reader = _reader(path, PRICE_COLUMNS)
    with handle:
        for row in reader:
            yield {'symbol': (row['ticker'] or '').strip(), 'session': (row['date'] or '').strip(), 'open': row['open'], 'high': row['high'], 'low': row['low'],
                   'close': row['close'], 'volume': row['volume'], 'close_unadjusted': row['closeunadj'], 'close_total_return': row['closeadj'],
                   'provider_updated': row['lastupdated']}


def securities(path):
    handle, reader = _reader(path, TICKER_COLUMNS)
    with handle:
        for row in reader:
            table = PRICE_TABLES.get((row['table'] or '').strip().upper())
            if table is None:
                continue                                              # a row that describes another table (fundamentals coverage), not a price series
            cik = _CIK.search(row.get('secfilings') or '')
            yield {'security_id': (row['permaticker'] or '').strip(), 'symbol': (row['ticker'] or '').strip(), 'name': row['name'], 'exchange': row['exchange'],
                   'category': row['category'], 'currency': (row['currency'] or '').strip() or None, 'is_delisted': (row['isdelisted'] or '').strip().upper() == 'Y',
                   'first_price_date': row['firstpricedate'] or None, 'last_price_date': row['lastpricedate'] or None, 'price_table': table,
                   'cik': cik.group(1) if cik else None, 'sector_current': row.get('sector') or None, 'industry_current': row.get('industry') or None,
                   'sic_code_current': row.get('siccode') or None, 'provider_updated': row.get('lastupdated') or None,
                   'related_symbols': row.get('relatedtickers') or None}


def actions(path):
    handle, reader = _reader(path, ACTION_COLUMNS)
    with handle:
        for row in reader:
            code = (row['action'] or '').strip().lower()
            yield {'symbol': (row['ticker'] or '').strip(), 'type': ACTIONS.get(code, 'other'), 'provider_code': code, 'effective_date': (row['date'] or '').strip(),
                   'value': (row['value'] or '').strip() or None, 'contra_symbol': (row['contraticker'] or '').strip() or None,
                   'contra_name': (row['contraname'] or '').strip() or None, 'name': row['name'],
                   'announcement_timestamp': 'UNAVAILABLE'}            # the vendor gives a date and no announcement time; none is made up


def index_events(path, index='S&P 500'):
    handle, reader = _reader(path, SP500_COLUMNS)
    with handle:
        for row in reader:
            yield {'symbol': (row['ticker'] or '').strip(), 'index': index, 'type': (row['action'] or '').strip().lower(), 'effective_date': (row['date'] or '').strip(),
                   'name': row['name'], 'note': row.get('note') or None}
