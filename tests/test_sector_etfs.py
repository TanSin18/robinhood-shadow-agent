"""v1.5 sector ETFs: registered, but used only when the amendment is active."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from research.strategy_signals import (ETF_UNIVERSE, ETF_UNIVERSE_V142, REGISTERED_DISCOVERY_UNIVERSE,
                                       SECTOR_ETFS_V15, active_etf_universe)


def test_registered_sets():
    assert len(ETF_UNIVERSE_V142) == 8 and len(SECTOR_ETFS_V15) == 9 and len(REGISTERED_DISCOVERY_UNIVERSE) == 23
    assert active_etf_universe(False) == ETF_UNIVERSE_V142 and active_etf_universe(True) == ETF_UNIVERSE


def test_registered_only_removes_inactive_symbols_everywhere():
    from agents.daily_cycle import registered_only
    snap = {'quotes': {'XLK': 1, 'SPY': 2, 'opt-xlk': 3, 'opt-spy': 4}, 'vols': {'XLK': 1, 'SPY': 1},
            'contracts': {'opt-xlk': {'chain_symbol': 'XLK'}, 'opt-spy': {'chain_symbol': 'SPY'}},
            'session_closes': {'XLK': {}, 'SPY': {}}, 'median_dollar_volume_20d': {'XLK': 1, 'SPY': 1}, 'benchmark': None}
    out = registered_only(snap, SECTOR_ETFS_V15)
    assert set(out['quotes']) == {'SPY', 'opt-spy'} and set(out['contracts']) == {'opt-spy'}
    assert set(out['vols']) == set(out['session_closes']) == set(out['median_dollar_volume_20d']) == {'SPY'}


def test_reader_accepts_registered_23_and_refuses_anything_else():
    from agents.market_reader import MarketReader
    from broker.base import BrokerError

    class Config:
        class risk:
            agentic_account_id = 'acct'
            instrument_whitelist = frozenset(REGISTERED_DISCOVERY_UNIVERSE | {'TSLA'})

    class Gateway:
        def call(self, tool, args):
            if tool == 'get_accounts':
                return {'tool': tool, 'data': {'accounts': [{'account_number': 'acct', 'agentic_allowed': True}]}}
            raise AssertionError('should stop before market reads')
    with pytest.raises(BrokerError):
        MarketReader(Gateway(), Config()).collect(datetime(2026, 10, 1, 14, tzinfo=timezone.utc), {}, account_reads=[])
