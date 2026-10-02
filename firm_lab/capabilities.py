"""What Firm Lab can and cannot see today. A capability without a real source is UNAVAILABLE: no value, no estimate."""
from __future__ import annotations

from .errors import CapabilityUnavailable

AVAILABLE, UNAVAILABLE, NOT_STARTED, BUILD_ONLY = 'AVAILABLE', 'UNAVAILABLE', 'NOT_STARTED', 'BUILD_ONLY'
STATUSES = (AVAILABLE, UNAVAILABLE, NOT_STARTED, BUILD_ONLY)

# (capability, status, provider, detail). Edited only by a deliberate change here, never inferred at run time.
INITIAL = (
    ('daily_closes', AVAILABLE, 'Robinhood read gateway, as recorded by Control A',
     'Completed-session closes for the registered names, read from Control A’s decision capsules (read-only).'),
    ('daily_baseline_features', AVAILABLE, 'Firm Lab feature store',
     'Completed-session count, 200-session average, above-average flag and 126-session momentum.'),
    ('fundamentals', UNAVAILABLE, None, 'No provider is connected. No fundamental value is stored or estimated.'),
    ('analyst_revisions', UNAVAILABLE, None, 'No provider is connected. No revision value is stored or estimated.'),
    ('earnings_transcripts', UNAVAILABLE, None, 'No transcript source is connected.'),
    ('intraday_bars', UNAVAILABLE, None, 'The registered read path supplies daily bars only.'),
    ('vwap', UNAVAILABLE, None, 'Needs intraday bars.'),
    ('opening_range', UNAVAILABLE, None, 'Needs intraday bars.'),
    ('time_of_day_rvol', UNAVAILABLE, None, 'Needs intraday bars.'),
    ('trade_flow', UNAVAILABLE, None, 'Aggressive buying and selling, signed volume: needs trade data.'),
    ('order_book', UNAVAILABLE, None, 'Quote and order-book imbalance: needs depth data.'),
    ('options_chain', BUILD_ONLY, 'Robinhood read gateway',
     'Storage schema only. The registered read path can list contracts and bid/ask quotes, but Firm Lab ingests none yet, and implied '
     'volatility and Greeks have never been captured from the provider.'),
    ('options_strategy', NOT_STARTED, None, 'No option recommendation, scenario engine or matched book exists.'),
    ('news_catalysts', NOT_STARTED, None, 'Control A’s advisory desk reads headlines; Firm Lab has no news pipeline yet.'),
    ('sec_filings', NOT_STARTED, None, 'Not built.'),
    ('sector_engine', NOT_STARTED, None, 'Not built.'),
    ('ml_ranker', NOT_STARTED, None, 'No model is fitted. Model, target and features are strategy choices for a registered recipe.'),
    ('portfolio_optimizer', NOT_STARTED, None, 'Not built.'),
)


def seed(store, now=None):
    """Writes the initial registry once. Existing rows are left alone so a later deliberate edit is not undone."""
    known = {c['capability'] for c in store.capabilities()}
    for capability, status, provider, detail in INITIAL:
        if capability not in known:
            store.set_capability(capability, status, provider, detail, now)


def require(store, capability):
    """Returns nothing; raises unless the capability is AVAILABLE. Callers never get a stand-in value."""
    status = store.capability(capability)
    if status != AVAILABLE:
        raise CapabilityUnavailable(f'{capability}: {status}')
