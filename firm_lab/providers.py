"""Future data-provider interfaces. None is connected. Each method raises CapabilityUnavailable until a real,
operator-chosen provider implements it; nothing here returns a placeholder number."""
from __future__ import annotations

from .errors import CapabilityUnavailable


class _Unconnected:
    capability = 'unknown'

    def _blocked(self, what):
        raise CapabilityUnavailable(f'{self.capability}: UNAVAILABLE ({what} has no connected provider)')


class FundamentalsProvider(_Unconnected):
    capability = 'fundamentals'

    def snapshot(self, instrument, as_of):
        self._blocked('fundamentals')


class AnalystRevisionsProvider(_Unconnected):
    capability = 'analyst_revisions'

    def revisions(self, instrument, as_of):
        self._blocked('analyst revisions')


class IntradayMarketDataProvider(_Unconnected):
    capability = 'intraday_bars'

    def historical_bars(self, instrument, start, end, interval='1m'):
        self._blocked('intraday bars')

    def live_bars(self, instrument, interval='1m'):
        self._blocked('intraday bars')

    def quotes(self, instrument):
        self._blocked('intraday quotes')

    def trades(self, instrument):
        self._blocked('trade data')

    def option_quotes(self, contract_id):
        self._blocked('intraday option quotes')
