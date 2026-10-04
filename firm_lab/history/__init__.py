"""Checkpoint 8: historical data foundation. Research only.

DATA READINESS ONLY — NO TRADING MODEL IS ACTIVE. This package stores licensed and public historical observations,
validates them, forms a point-in-time universe, computes descriptive features and counts how many training rows can be
built honestly. It fits no model, ranks nothing for trading, sizes nothing and cannot place, schedule or simulate an
order. Nothing in the trading runtime imports it and it imports nothing from the trading runtime.

Evidence tiers (``CHECKPOINT8_DATA_SUFFICIENCY_SPEC.md``): a row is a strict point-in-time sample only when every
input, its universe membership and its label are tier A or tier B. Tier C is retrospective and is never counted as
strict.
"""
WARNING = 'DATA READINESS ONLY — NO TRADING MODEL IS ACTIVE'
DATABASE_ROLE = 'CHECKPOINT8_HISTORICAL_RESEARCH'
FILE_NAME = 'firm_lab_history.db'
READINESS_FILE = 'firm_lab_history_readiness.json'
POLICY_VERSION = 'historical-market-data-v1'
BAR_KNOWN_AT_VERSION = 'bar-known-at-v1'
BAR_KNOWN_AT_BASIS = 'EXCHANGE_SESSION_COMPLETE_NEXT_OPEN_BOUND'

HELD_AT_THE_TIME, PUBLISHER_DATED_HISTORICAL, RETROSPECTIVE = 'HELD_AT_THE_TIME', 'PUBLISHER_DATED_HISTORICAL', 'RETROSPECTIVE'
TIERS = {HELD_AT_THE_TIME: 'A', PUBLISHER_DATED_HISTORICAL: 'B', RETROSPECTIVE: 'C'}
STRICT_TIERS = (HELD_AT_THE_TIME, PUBLISHER_DATED_HISTORICAL)

SPLIT_ADJUSTED, UNADJUSTED, TOTAL_RETURN_ADJUSTED = 'SPLIT_ADJUSTED_AS_OF_CAPTURE', 'UNADJUSTED', 'SPLIT_DIVIDEND_SPINOFF_ADJUSTED_AS_OF_CAPTURE'
RETURN_BASIS = 'PRICE_RETURN_SPLIT_ADJUSTED'


def lowest_tier(tiers) -> str:
    """The tier of a row: the weakest among its parts. An unknown or missing tier is retrospective."""
    order = (HELD_AT_THE_TIME, PUBLISHER_DATED_HISTORICAL, RETROSPECTIVE)
    tiers = list(tiers)
    if not tiers:
        return RETROSPECTIVE
    return max((t if t in order else RETROSPECTIVE for t in tiers), key=order.index)
