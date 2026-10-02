"""Data-provider interfaces. Definitions only: no provider is connected at this checkpoint.

Every method returns a ``ProviderResult``. With no provider behind it the status is ``UNAVAILABLE`` and there are
no records: never a guessed value, a stale hard-coded value, a web search or a model-written number. A connected
provider (a later, deliberate step) supplies raw records plus their provenance through ``_fetch``; the records
are checked against the domain schema and the data-quality checks and are either passed on unchanged (``OK``) or
refused as a whole (``REJECTED``). Nothing is repaired.

Nothing in this module is read by a ranking, a selection or an execution path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import quality
from .errors import CapabilityUnavailable
from .provenance import Provenance
from .schemas import SCHEMA_VERSION

OK, UNAVAILABLE, REJECTED = 'OK', 'UNAVAILABLE', 'REJECTED'


@dataclass(frozen=True)
class ProviderResult:
    status: str                                   # OK, UNAVAILABLE or REJECTED
    domain: str
    method: str
    reason: str = ''
    provenance: Optional[Provenance] = None
    issues: tuple = field(default_factory=tuple)
    _records: tuple = field(default_factory=tuple, repr=False)

    @property
    def available(self) -> bool:
        return self.status == OK

    def records(self) -> tuple:
        """The records, only when the status is OK. Anything else raises: "no data" is never mistaken for "no provider"."""
        if self.status != OK:
            raise CapabilityUnavailable(f'{self.domain}.{self.method}: {self.status}' + (f' ({self.reason})' if self.reason else ''))
        return self._records

    def summary(self) -> dict:
        return {'status': self.status, 'domain': self.domain, 'method': self.method, 'reason': self.reason,
                'records': len(self._records) if self.status == OK else 0, 'issues': sorted({i.code for i in self.issues})}


def unavailable(domain, method, reason='no provider is connected') -> ProviderResult:
    return ProviderResult(UNAVAILABLE, domain, method, reason)


def deliver(domain, method, records, provenance, *, now, expected_instrument=None, max_age=None, expected_window=None,
            window_field=None) -> ProviderResult:
    """Checks a provider response. Returns OK with the records exactly as received, or REJECTED with every reason."""
    report = quality.validate(domain, records, now=now, provenance=provenance, expected_instrument=expected_instrument, max_age=max_age,
                              expected_window=expected_window, window_field=window_field)
    if not isinstance(records, (list, tuple)) or not records:
        issues = report.issues or (quality.Issue(quality.NOT_A_RECORD, 'the response holds no records'),)
        return ProviderResult(REJECTED, domain, method, 'empty or malformed response', provenance, tuple(issues))
    if report.issues:
        return ProviderResult(REJECTED, domain, method, f'{len(report.issues)} data-quality issue(s); nothing was repaired', provenance, report.issues)
    return ProviderResult(OK, domain, method, '', provenance, (), tuple(records))


class Provider:
    """Base of every interface. ``name`` stays None until a real provider is connected on purpose."""
    domain = 'unknown'
    capability = 'unknown'
    name = None
    schema_version = SCHEMA_VERSION

    @property
    def connected(self) -> bool:
        return bool(self.name)

    def _fetch(self, method, **request):
        """A connected provider returns ``(records, Provenance)``. The base class has nothing to fetch."""
        raise NotImplementedError

    def _call(self, method, domain=None, *, now=None, expected_instrument=None, **request) -> ProviderResult:
        domain = domain or self.domain
        if not self.connected:
            return unavailable(domain, method)
        if now is None:
            return ProviderResult(REJECTED, domain, method, 'the caller did not say what time it is (now=...)')
        try:
            records, provenance = self._fetch(method, **request)
        except NotImplementedError:
            return unavailable(domain, method, f'{self.name} does not supply {method}')
        return deliver(domain, method, records, provenance, now=now, expected_instrument=expected_instrument,
                       max_age=request.get('max_age'), expected_window=request.get('expected_window'), window_field=request.get('window_field'))


class FundamentalsProvider(Provider):
    """Reported financials with their filing and known-at timestamps. No ratio or score is computed here."""
    domain = capability = 'fundamentals'

    def financial_statements(self, instrument, *, known_at, now=None):
        return self._call('financial_statements', now=now, expected_instrument=instrument, instrument=instrument, known_at=known_at)

    def valuation_inputs(self, instrument, *, known_at, now=None):
        return self._call('valuation_inputs', now=now, expected_instrument=instrument, instrument=instrument, known_at=known_at)

    def profitability(self, instrument, *, known_at, now=None):
        return self._call('profitability', now=now, expected_instrument=instrument, instrument=instrument, known_at=known_at)

    def leverage(self, instrument, *, known_at, now=None):
        return self._call('leverage', now=now, expected_instrument=instrument, instrument=instrument, known_at=known_at)

    def cash_flow(self, instrument, *, known_at, now=None):
        return self._call('cash_flow', now=now, expected_instrument=instrument, instrument=instrument, known_at=known_at)


class EstimatesProvider(Provider):
    """Consensus estimates and their revisions. Point-in-time snapshots are mandatory: today's consensus alone is refused."""
    domain = 'estimates'
    capability = 'analyst_revisions'

    def consensus(self, instrument, metric, fiscal_period, *, known_at, now=None):
        return self._call('consensus', now=now, expected_instrument=instrument, instrument=instrument, metric=metric,
                          fiscal_period=fiscal_period, known_at=known_at)

    def revisions(self, instrument, metric, fiscal_period, *, start, end, now=None):
        return self._call('revisions', now=now, expected_instrument=instrument, instrument=instrument, metric=metric,
                          fiscal_period=fiscal_period, start=start, end=end)


class EarningsProvider(Provider):
    """Earnings events, releases, transcripts and guidance, each with its timestamp and source URL."""
    domain = 'earnings'
    capability = 'earnings_transcripts'

    def events(self, instrument, *, start, end, now=None):
        return self._call('events', now=now, expected_instrument=instrument, instrument=instrument, start=start, end=end)

    def release(self, instrument, fiscal_period, *, now=None):
        return self._call('release', now=now, expected_instrument=instrument, instrument=instrument, fiscal_period=fiscal_period)

    def transcript(self, instrument, fiscal_period, *, now=None):
        return self._call('transcript', now=now, expected_instrument=instrument, instrument=instrument, fiscal_period=fiscal_period)

    def guidance(self, instrument, fiscal_period, *, now=None):
        return self._call('guidance', now=now, expected_instrument=instrument, instrument=instrument, fiscal_period=fiscal_period)


class FilingsProvider(Provider):
    """Regulatory filings (the index entry and its acceptance timestamp), not financial data extracted from them."""
    domain = 'filings'
    capability = 'sec_filings'

    def filings(self, instrument, *, start, end, now=None):
        return self._call('filings', now=now, expected_instrument=instrument, instrument=instrument, start=start, end=end)


class NewsProvider(Provider):
    """Headlines with source, publication time, URL, entity mapping and a deduplication key. Nothing is scored."""
    domain = 'news'
    capability = 'news_catalysts'

    def headlines(self, *, start, end, instrument=None, now=None):
        return self._call('headlines', now=now, instrument=instrument, start=start, end=end)


class IntradayMarketDataProvider(Provider):
    """1-minute bars, quote snapshots and trades. No VWAP, RVOL, opening range or flow measure is derived here."""
    domain = 'intraday_bars'
    capability = 'intraday_bars'

    def bars_1m(self, instrument, *, session_date, now=None):
        return self._call('bars_1m', 'intraday_bars', now=now, expected_instrument=instrument, instrument=instrument, session_date=session_date)

    def quote_snapshots(self, instrument, *, start, end, now=None):
        return self._call('quote_snapshots', 'quotes', now=now, expected_instrument=instrument, instrument=instrument, start=start, end=end)

    def trades(self, instrument, *, start, end, now=None):
        return self._call('trades', 'trades', now=now, expected_instrument=instrument, instrument=instrument, start=start, end=end)


class OptionsMarketDataProvider(Provider):
    """Option chains and quotes. Greeks and implied volatility are stored only as ``provider_*`` when the source
    supplies them; this interface never estimates them and never recommends a contract."""
    domain = 'options_chain'
    capability = 'options_chain'

    def chain(self, underlying, *, as_of, now=None):
        return self._call('chain', now=now, underlying=underlying, as_of=as_of)

    def quotes(self, contract_ids, *, as_of, now=None):
        return self._call('quotes', now=now, contract_ids=tuple(contract_ids), as_of=as_of)


class RiskFreeBenchmarkProvider(Provider):
    """A 3-month Treasury-bill TOTAL RETURN series. A yield or discount-rate series is refused, not converted."""
    domain = 'risk_free'
    capability = 'treasury_total_return'

    def total_return_series(self, *, start, end, known_at, now=None):
        return self._call('total_return_series', now=now, start=start, end=end, known_at=known_at)


class CorporateActionsProvider(Provider):
    """Cash dividends, splits, spin-offs, symbol changes, mergers and delistings, each with its announcement time."""
    domain = capability = 'corporate_actions'

    def actions(self, instrument, *, start, end, now=None):
        return self._call('actions', now=now, expected_instrument=instrument, instrument=instrument, start=start, end=end)


INTERFACES = (FundamentalsProvider, EstimatesProvider, EarningsProvider, FilingsProvider, NewsProvider, IntradayMarketDataProvider,
              OptionsMarketDataProvider, RiskFreeBenchmarkProvider, CorporateActionsProvider)
