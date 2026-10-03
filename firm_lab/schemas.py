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
    timestamp_or_unavailable: tuple = () # must be a timezone-aware timestamp or the literal UNAVAILABLE (never left out, never invented)
    numeric: tuple = ()                  # must be a finite number when present (may be negative)
    any_of: tuple = ()                   # groups of field names: at least one of each group must be present


# The reported values Firm Lab keeps. Raw facts only: no score, rank or composite is derived from them.
FUNDAMENTAL_METRICS = ('revenue', 'gross_profit', 'operating_income', 'ebit', 'ebitda', 'net_income', 'eps_basic', 'eps_diluted',
                       'free_cash_flow', 'operating_cash_flow', 'capital_expenditure', 'total_debt', 'cash_and_equivalents', 'total_equity',
                       'total_assets', 'total_liabilities', 'shares_basic', 'shares_weighted', 'shares_weighted_diluted', 'invested_capital',
                       'tax_expense', 'market_capitalization', 'enterprise_value', 'gross_margin', 'net_margin', 'fx_to_usd')
MONEY_UNITS = ('currency', 'currency_per_share')
UNAVAILABLE = 'UNAVAILABLE'

SCHEMAS = {
    # Stored closes, checked before daily_closes may be called AVAILABLE.
    'daily_closes': Schema('daily_closes', required=('instrument', 'exchange_session_date', 'close', 'known_at', 'source'), identifier='instrument',
                           timestamps=('known_at',), key=('instrument', 'exchange_session_date'), positive=('close',)),
    # One row per reported value. As-reported and restated values are different rows and never overwrite each other.
    # `filing_date` is the provider's date-only filing date (UNAVAILABLE for restated rows, which are indexed to the period);
    # `filing_timestamp` is UNAVAILABLE: the provider gives a date, not a time. EDGAR's acceptance time stays in the filing table and is
    # joined at read time (firm_lab.crosscheck); it is never copied into this record.
    'fundamentals': Schema(
        'fundamentals',
        required=('instrument', 'dimension', 'reporting_basis', 'period_end', 'filing_date', 'filing_timestamp', 'last_updated', 'metric', 'value',
                  'units', 'known_at'),
        identifier='instrument', timestamps=('known_at',), key=('instrument', 'dimension', 'period_end', 'filing_date', 'metric'),
        numeric=('value',), timestamp_or_unavailable=('filing_timestamp',),
        optional=('fiscal_period', 'calendar_date', 'currency', 'provider_datekey', 'provider_metric', 'is_delisted', 'provider_instrument_id'),
        point_in_time='last_updated',
        allowed={'reporting_basis': ('as_reported', 'restated'),
                 'units': ('currency', 'currency_per_share', 'shares', 'ratio'),
                 'metric': FUNDAMENTAL_METRICS}),
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
    # The filing header's acceptance time is authoritative. `accepted_timestamp` (the known-at Firm Lab uses) must equal
    # `accepted_timestamp_header`; `accepted_timestamp_json` is the SEC JSON text exactly as sent and is never rewritten;
    # `acceptance_time_conflict` says whether the two disagree under every reading.
    'filings': Schema(
        'filings',
        required=('instrument', 'cik', 'accession_number', 'form_type', 'accepted_timestamp', 'accepted_timestamp_header', 'accepted_timestamp_json',
                  'acceptance_time_conflict', 'accepted_timestamp_raw', 'accepted_timestamp_basis', 'filing_date', 'url', 'ingestion_timestamp'),
        identifier='instrument', timestamps=('accepted_timestamp', 'accepted_timestamp_header', 'ingestion_timestamp'), key=('accession_number',),
        optional=('report_date', 'primary_document', 'items', 'header_acceptance_raw', 'series_id', 'class_id', 'entity_name',
                  'acceptance_time_json_offset_seconds'),
        point_in_time='accepted_timestamp_header', numeric=('acceptance_time_json_offset_seconds',)),
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
    # A side with price 0 and size 0 means "no quote on that side" and is kept as sent; a crossed market needs both sides.
    'quotes': Schema(
        'quotes',
        required=('instrument', 'quote_timestamp', 'quote_timestamp_raw', 'bid', 'ask', 'bid_size', 'ask_size', 'feed'),
        identifier='instrument', timestamps=('quote_timestamp',), order_by='quote_timestamp', key=('instrument', 'quote_timestamp_raw', 'sequence_number'),
        non_negative=('bid', 'ask', 'bid_size', 'ask_size'),
        optional=('bid_exchange', 'ask_exchange', 'conditions', 'indicators', 'sequence_number', 'tape', 'participant_timestamp_raw')),
    'trades': Schema(
        'trades',
        required=('instrument', 'trade_timestamp', 'trade_timestamp_raw', 'price', 'size', 'feed', 'trade_id', 'exchange'),
        identifier='instrument', timestamps=('trade_timestamp',), order_by='trade_timestamp',
        key=('instrument', 'exchange', 'trade_id', 'trade_timestamp_raw'), positive=('price',), non_negative=('size',),
        optional=('conditions', 'sequence_number', 'tape', 'trf_id', 'correction', 'decimal_size', 'participant_timestamp_raw')),
    # Implied volatility must be present under a name that says who produced it: provider_implied_volatility or
    # <vendor>_provider_implied_volatility. Greeks follow the same rule; a bare "delta" is rejected.
    'options_chain': Schema(
        'options_chain',
        required=('contract_id', 'underlying', 'option_type', 'strike', 'expiration', 'bid', 'ask', 'quote_timestamp', 'volume', 'open_interest'),
        identifier='contract_id', timestamps=('quote_timestamp',), key=('contract_id', 'quote_timestamp'), positive=('strike',),
        non_negative=('bid', 'ask', 'volume', 'open_interest', 'bid_size', 'ask_size'),
        optional=('provider_implied_volatility', 'provider_delta', 'provider_gamma', 'provider_theta', 'provider_vega', 'provider_rho',
                  'underlying_bid', 'underlying_ask', 'provider_theoretical_price', 'multiplier', 'feed', 'bid_size', 'ask_size',
                  'quote_timestamp_raw', 'greeks_provider', 'greeks_model', 'greeks_model_version', 'greeks_timestamp', 'underlying_price',
                  'underlying_timestamp', 'open_interest_timestamp'),
        allowed={'option_type': ('call', 'put')}, any_of=(('provider_implied_volatility', '*_provider_implied_volatility'),)),
    'risk_free': Schema(
        'risk_free',
        required=('series_id', 'measure', 'observation_date', 'value', 'published_timestamp'),
        identifier='series_id', timestamps=('published_timestamp',), key=('series_id', 'observation_date'), positive=('value',),
        optional=('base_date', 'base_value', 'methodology_url'), point_in_time='published_timestamp',
        # A yield or a discount rate is not a total return. Only these two measures are accepted.
        allowed={'measure': ('TOTAL_RETURN_INDEX', 'PERIOD_TOTAL_RETURN')}),
    # U.S. Treasury 13-week bill auction results, as published. `result_known_at` is 5:00 p.m. New York time on the auction
    # date (frozen methodology, section 10). The price is checked against the official formula by firm_lab.treasury.
    'treasury_auctions': Schema(
        'treasury_auctions',
        required=('cusip', 'security_type', 'security_term', 'auction_date', 'issue_date', 'maturity_date', 'high_discount_rate', 'price_per100',
                  'result_known_at'),
        identifier='cusip', timestamps=('result_known_at',), key=('cusip', 'auction_date'), positive=('price_per100',),
        non_negative=('high_discount_rate',),
        optional=('closing_time_comp', 'reopening', 'original_security_term', 'record_date', 'feed'),
        allowed={'security_type': ('Bill',), 'security_term': ('13-Week',)}),
    # One appearance of a company fact in a filing, normalized by firm_lab.fundamentals. Known-at is the SEC acceptance time.
    # A fact whose value differs from the filing's own document (MISMATCH) is not an allowed state: the response is refused.
    'xbrl_facts': Schema(
        'xbrl_facts',
        required=('instrument', 'cik', 'taxonomy', 'concept', 'normalized_field', 'mapping_rule', 'unit', 'value', 'period_type', 'period_end',
                  'relation_to_filing', 'form', 'accession_number', 'filing_date', 'accepted_timestamp', 'version', 'is_restatement',
                  'confirmed_in_filing', 'source_url', 'ingestion_timestamp'),
        identifier='instrument', timestamps=('accepted_timestamp', 'ingestion_timestamp'),
        key=('normalized_field', 'period_start', 'period_end', 'accession_number'), numeric=('value',), positive=('version',),
        optional=('period_start', 'agreeing_concepts', 'filing_fiscal_year', 'filing_fiscal_period', 'frame', 'prior_value', 'entity_name',
                  'accepted_timestamp_json', 'acceptance_time_conflict', 'filing_document_url'),
        point_in_time='accepted_timestamp',
        allowed={'unit': ('USD', 'USD/shares', 'shares'), 'taxonomy': ('us-gaap',), 'period_type': ('instant', '3M', '6M', '9M', '12M'),
                 'relation_to_filing': ('current', 'comparative'), 'form': ('10-K', '10-Q', '10-K/A', '10-Q/A'),
                 'confirmed_in_filing': ('CONFIRMED', 'NOT_FOUND', 'NOT_CHECKED'),
                 'normalized_field': ('revenue', 'gross_profit', 'operating_income', 'net_income', 'eps_diluted', 'operating_cash_flow',
                                      'capital_expenditure', 'cash_and_equivalents', 'total_debt', 'diluted_shares_weighted_average')}),
    # An earnings-release filing. Facts about the filing only. `fiscal_period_end` and `release_document_url` are a value or
    # the literal UNAVAILABLE; `acceptance_session` is the New York clock time of the SEC acceptance, not a market-hours claim.
    'earnings_events': Schema(
        'earnings_events',
        required=('instrument', 'cik', 'accession_number', 'form', 'items', 'event_date', 'filing_date', 'accepted_timestamp',
                  'accepted_timestamp_header', 'accepted_timestamp_json', 'acceptance_time_conflict', 'acceptance_session', 'filing_url',
                  'release_document_url', 'fiscal_period_end', 'transcript_available', 'ingestion_timestamp'),
        identifier='instrument', timestamps=('accepted_timestamp', 'accepted_timestamp_header', 'ingestion_timestamp'), key=('accession_number',),
        optional=('primary_document_url', 'release_document_type', 'fiscal_period_basis', 'periodic_accession_number', 'entity_name',
                  'accepted_timestamp_raw', 'accepted_timestamp_basis', 'acceptance_time_json_offset_seconds'),
        point_in_time='accepted_timestamp_header',
        allowed={'form': ('8-K', '8-K/A'), 'acceptance_session': ('before_market_open', 'during_market_hours', 'after_market_close')}),
    # The announcement time is a timestamp or the literal UNAVAILABLE. It is never derived from the effective date.
    'corporate_actions': Schema(
        'corporate_actions',
        required=('instrument', 'action_type', 'effective_date', 'announcement_timestamp', 'provider_action'),
        identifier='instrument', key=('instrument', 'provider_action', 'effective_date', 'contra_instrument'),
        timestamp_or_unavailable=('announcement_timestamp',), numeric=('value',),
        optional=('value', 'value_meaning', 'currency', 'contra_instrument', 'contra_name', 'name', 'effective_date_basis', 'cash_amount',
                  'split_ratio', 'new_instrument', 'ex_date', 'record_date', 'pay_date', 'terms', 'distribution_type', 'source_record'),
        allowed={'action_type': ('cash_dividend', 'split', 'spin_off', 'symbol_change', 'merger', 'delisting', 'other')}),
}
NOT_A_TOTAL_RETURN = ('YIELD', 'DISCOUNT_RATE', 'COUPON_EQUIVALENT', 'PRICE')


def greek_field(name: str, origin: str, vendor: str = '') -> str:
    """The stored field name for a Greek: ``provider_delta`` (or ``<vendor>_provider_delta``) when a source supplied it,
    ``model_estimated_delta`` when Firm Lab computed it. There is no bare spelling, and the two are never written into
    each other."""
    if name not in GREEKS:
        raise ValueError(f'UNKNOWN_GREEK:{name}')
    if vendor and not vendor.isidentifier():
        raise ValueError(f'VENDOR_NAME_MUST_BE_A_SIMPLE_WORD:{vendor}')
    if origin == 'provider':
        return (vendor.lower() + '_' if vendor else '') + PROVIDER_PREFIX + name
    if origin == 'model':
        return MODEL_PREFIX + name
    raise ValueError(f'GREEK_ORIGIN_MUST_BE_provider_OR_model:{origin}')
