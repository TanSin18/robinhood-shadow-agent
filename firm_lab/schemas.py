"""Minimum record schemas for each data domain Firm Lab may use later. Definitions only: nothing is fetched,
computed or ranked from them at this checkpoint.

A schema says which fields a provider record must carry, which field identifies the instrument, which fields are
timestamps, which carry money (and therefore need a currency), and which field proves point-in-time history.
"""
from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = 'firm-lab-data-v1'

# Greeks and implied volatility always say where they came from. A bare "delta" is never stored.
GREEKS = ('delta', 'gamma', 'theta', 'vega', 'rho', 'implied_volatility')
PROVIDER_PREFIX, MODEL_PREFIX = 'provider_', 'model_estimated_'
BARE_GREEK_NAMES = frozenset(GREEKS) | {'iv'}


@dataclass(frozen=True)
class Schema:
    domain: str
    required: tuple                      # fields every record must carry (a present key with a None value counts as missing)
    identifier: str                      # the field naming the instrument, contract or document
    timestamps: tuple = ()               # fields that must be timezone-aware timestamps
    order_by: str = ''                   # timestamp field that must not go backwards within one response
    key: tuple = ()                      # fields that together must be unique within one response
    money: tuple = ()                    # fields that are amounts of money: the record must also carry `currency`
    positive: tuple = ()                 # must be > 0 when present
    non_negative: tuple = ()             # must be >= 0 when present
    optional: tuple = ()                 # documented, not required
    point_in_time: str = ''              # field proving the value is a dated snapshot, not "today's" value
    allowed: dict = None                 # field -> allowed values


SCHEMAS = {
    # Stored closes, checked before daily_closes may be called AVAILABLE.
    'daily_closes': Schema('daily_closes', required=('instrument', 'exchange_session_date', 'close', 'known_at', 'source'), identifier='instrument',
                           timestamps=('known_at',), key=('instrument', 'exchange_session_date'), positive=('close',)),
    'fundamentals': Schema(
        'fundamentals',
        required=('instrument', 'fiscal_period', 'period_end', 'statement', 'filing_timestamp', 'known_at', 'currency', 'units'),
        identifier='instrument', timestamps=('filing_timestamp', 'known_at'), key=('instrument', 'fiscal_period', 'statement', 'filing_timestamp'),
        money=('revenue', 'operating_income', 'ebitda', 'gross_profit', 'net_income', 'free_cash_flow', 'operating_cash_flow', 'capital_expenditure',
               'total_debt', 'cash_and_equivalents', 'total_equity', 'invested_capital', 'tax_expense', 'market_capitalization', 'enterprise_value'),
        positive=('shares_outstanding',), non_negative=('total_debt', 'cash_and_equivalents'),
        optional=('revenue', 'operating_income', 'ebitda', 'eps_diluted', 'gross_profit', 'gross_margin', 'operating_margin', 'net_income',
                  'free_cash_flow', 'operating_cash_flow', 'capital_expenditure', 'total_debt', 'cash_and_equivalents', 'total_equity',
                  'shares_outstanding', 'invested_capital', 'tax_expense', 'market_capitalization', 'enterprise_value', 'restated', 'form_type',
                  'accession_number'),
        point_in_time='filing_timestamp', allowed={'statement': ('income', 'balance_sheet', 'cash_flow', 'valuation_inputs')}),
    'estimates': Schema(
        'estimates',
        required=('instrument', 'fiscal_period', 'metric', 'consensus_estimate', 'analyst_count', 'effective_timestamp', 'snapshot_timestamp'),
        identifier='instrument', timestamps=('effective_timestamp', 'snapshot_timestamp'), order_by='snapshot_timestamp',
        key=('instrument', 'fiscal_period', 'metric', 'snapshot_timestamp'), money=('consensus_estimate', 'prior_consensus'),
        non_negative=('analyst_count', 'dispersion'), optional=('prior_consensus', 'revision_magnitude', 'dispersion', 'high', 'low', 'currency'),
        point_in_time='snapshot_timestamp', allowed={'metric': ('eps', 'revenue')}),
    'earnings': Schema(
        'earnings',
        required=('instrument', 'fiscal_period', 'event_timestamp', 'session_timing', 'release_source_url'),
        identifier='instrument', timestamps=('event_timestamp',), key=('instrument', 'fiscal_period'),
        optional=('transcript_source_url', 'transcript_timestamp', 'guidance_sections', 'prior_fiscal_period', 'release_timestamp', 'confirmed'),
        point_in_time='event_timestamp', allowed={'session_timing': ('pre_market', 'during_market', 'post_market', 'unknown')}),
    'filings': Schema(
        'filings',
        required=('instrument', 'accession_number', 'form_type', 'accepted_timestamp', 'url'),
        identifier='instrument', timestamps=('accepted_timestamp',), key=('accession_number',),
        optional=('filing_date', 'report_date', 'primary_document', 'items'), point_in_time='accepted_timestamp'),
    'news': Schema(
        'news',
        required=('source', 'headline', 'published_timestamp', 'ingestion_timestamp', 'url', 'deduplication_key'),
        identifier='deduplication_key', timestamps=('published_timestamp', 'ingestion_timestamp'), key=('deduplication_key',),
        optional=('snippet', 'body', 'body_licensed', 'instruments', 'entities', 'event_type', 'duplicate_group'), point_in_time='published_timestamp'),
    'intraday_bars': Schema(
        'intraday_bars',
        required=('instrument', 'bar_start', 'interval', 'open', 'high', 'low', 'close', 'volume', 'session', 'exchange_session_date'),
        identifier='instrument', timestamps=('bar_start',), order_by='bar_start', key=('instrument', 'bar_start'),
        positive=('open', 'high', 'low', 'close'), non_negative=('volume', 'trade_count', 'vwap'),
        optional=('trade_count', 'vwap', 'adjusted', 'feed'), allowed={'interval': ('1m',), 'session': ('pre_market', 'regular', 'post_market')}),
    'quotes': Schema(
        'quotes',
        required=('instrument', 'quote_timestamp', 'bid', 'ask', 'bid_size', 'ask_size', 'feed'),
        identifier='instrument', timestamps=('quote_timestamp',), order_by='quote_timestamp', positive=('bid', 'ask'),
        non_negative=('bid_size', 'ask_size'), optional=('bid_exchange', 'ask_exchange', 'conditions', 'nbbo')),
    'trades': Schema(
        'trades',
        required=('instrument', 'trade_timestamp', 'price', 'size', 'feed'),
        identifier='instrument', timestamps=('trade_timestamp',), order_by='trade_timestamp', positive=('price', 'size'),
        optional=('exchange', 'conditions', 'trade_id', 'tape')),
    'options_chain': Schema(
        'options_chain',
        required=('contract_id', 'underlying', 'option_type', 'strike', 'expiration', 'bid', 'ask', 'quote_timestamp', 'volume', 'open_interest',
                  'provider_implied_volatility'),
        identifier='contract_id', timestamps=('quote_timestamp',), key=('contract_id', 'quote_timestamp'), positive=('strike',),
        non_negative=('bid', 'ask', 'volume', 'open_interest', 'provider_implied_volatility'),
        optional=('provider_delta', 'provider_gamma', 'provider_theta', 'provider_vega', 'provider_rho', 'underlying_bid', 'underlying_ask',
                  'provider_theoretical_price', 'multiplier', 'feed'),
        allowed={'option_type': ('call', 'put')}),
    'risk_free': Schema(
        'risk_free',
        required=('series_id', 'measure', 'observation_date', 'value', 'published_timestamp'),
        identifier='series_id', timestamps=('published_timestamp',), key=('series_id', 'observation_date'), positive=('value',),
        optional=('base_date', 'base_value', 'methodology_url'), point_in_time='published_timestamp',
        # A yield or a discount rate is not a total return. Only these two measures are accepted.
        allowed={'measure': ('TOTAL_RETURN_INDEX', 'PERIOD_TOTAL_RETURN')}),
    'corporate_actions': Schema(
        'corporate_actions',
        required=('instrument', 'action_type', 'effective_date', 'announced_timestamp'),
        identifier='instrument', timestamps=('announced_timestamp',), key=('instrument', 'action_type', 'effective_date'),
        money=('cash_amount',), non_negative=('cash_amount',), positive=('split_ratio',),
        optional=('cash_amount', 'currency', 'split_ratio', 'new_instrument', 'counterparty', 'ex_date', 'record_date', 'pay_date', 'terms'),
        point_in_time='announced_timestamp',
        allowed={'action_type': ('cash_dividend', 'split', 'spin_off', 'symbol_change', 'merger', 'delisting')}),
}
NOT_A_TOTAL_RETURN = ('YIELD', 'DISCOUNT_RATE', 'COUPON_EQUIVALENT', 'PRICE')


def greek_field(name: str, origin: str) -> str:
    """The stored field name for a Greek: ``provider_delta`` when the source supplied it, ``model_estimated_delta``
    when Firm Lab computed it. There is no third spelling, and the two are never written into each other."""
    if name not in GREEKS:
        raise ValueError(f'UNKNOWN_GREEK:{name}')
    if origin == 'provider':
        return PROVIDER_PREFIX + name
    if origin == 'model':
        return MODEL_PREFIX + name
    raise ValueError(f'GREEK_ORIGIN_MUST_BE_provider_OR_model:{origin}')
