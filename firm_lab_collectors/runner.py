"""Small, hand-started sample runs: one provider at a time, a handful of symbols, no backfill and no schedule.

Each run does the same four things and nothing else:

  1. checks that the operator has configured the provider (otherwise records NOT_CONFIGURED and fetches nothing),
  2. asks the provider through its Firm Lab interface, which validates the answer and refuses it whole if anything is wrong,
  3. records the run, and stores the rows only when the answer was accepted,
  4. lets the capability registry follow the stored evidence.

Diagnostics written beside a run (missing minutes, the comparison with stored daily closes, the SEC cross-check) are
data-quality observations. Nothing here is a feature, a signal, a score or a selection.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from firm_lab import capabilities, crosscheck, quality, rawstore
from firm_lab.errors import FirmLabError
from firm_lab.providers import OK, UNAVAILABLE
from firm_lab.sessions import ET
from firm_lab.store import now_utc

from . import config, edgar, massive, sharadar, thetadata
from .transport import HttpTransport

EQUITY_SAMPLE = ('SPY', 'VTI', 'SOXX', 'AAPL', 'NVDA')
COMPANY_SAMPLE = ('AAPL', 'NVDA')                       # fundamentals exist for operating companies, not for the ETFs in the sample
OPTIONS_SAMPLE = ('SPY', 'QQQ', 'NVDA')
NEEDS = {
    'SEC EDGAR': 'Provider activation required: the operator declares a User-Agent with a contact address (FIRM_LAB_SEC_USER_AGENT).',
    'Massive': 'Credentials required: an operator-purchased Massive plan and API key (FIRM_LAB_MASSIVE_API_KEY).',
    'Sharadar': 'Credentials required: an operator-purchased Sharadar subscription, its API key (FIRM_LAB_SHARADAR_API_KEY) and channel '
                '(FIRM_LAB_SHARADAR_CHANNEL = direct or nasdaq).',
    'ThetaData': 'Provider activation required: an operator-purchased ThetaData subscription and a running Theta Terminal '
                 '(then FIRM_LAB_THETADATA_TERMINAL=1).',
}


def latest_stored_session(store):
    """The newest completed session Firm Lab already holds daily closes for, or None."""
    with store.connect() as db:
        return db.execute("SELECT MAX(exchange_session_date) FROM feature_observations WHERE feature_name='close'").fetchone()[0]


def _not_configured(store, provider, clock) -> dict:
    rawstore.set_connection(store, provider, 'NOT_CONFIGURED', NEEDS[provider], clock())
    return {'provider': provider, 'connection': 'NOT_CONFIGURED', 'detail': NEEDS[provider], 'runs': [], 'requests': 0,
            'capabilities': capabilities.confirm_provider_data(store, clock())}


def _finish(store, provider, outcomes, transport, clock) -> dict:
    answered = [o for o in outcomes if o['status'] != UNAVAILABLE]
    if answered:
        state, detail = 'ACTIVE', f'Answered {len(answered)} of {len(outcomes)} sample requests.'
    else:
        state, detail = 'ERROR', (outcomes[0]['reason'] if outcomes else 'No request was made.')
    rawstore.set_connection(store, provider, state, detail, clock())
    return {'provider': provider, 'connection': state, 'detail': detail, 'runs': outcomes, 'requests': getattr(transport, 'requests', None),
            'capabilities': capabilities.confirm_provider_data(store, clock())}


# ---------------------------------------------------------------------------- SEC EDGAR
def run_edgar(store, *, symbols=EQUITY_SAMPLE, environ=None, transport=None, clock=now_utc, days=365, max_filings=5) -> dict:
    """Filing metadata for a few symbols: identity, accession, form, verified acceptance time. No document is read."""
    agent = config.sec_user_agent(environ)
    if not agent:
        return _not_configured(store, 'SEC EDGAR', clock)
    transport = transport or HttpTransport(edgar.HOSTS, user_agent=agent, min_interval=0.2)      # at most 5 requests a second; SEC allows 10
    provider = edgar.EdgarFilingsProvider(transport, max_filings=max_filings)
    started, batch = clock().isoformat(), rawstore.new_batch(store, provider.name, clock())
    end = clock().astimezone(ET).date()
    start = end - timedelta(days=int(days))
    outcomes = []
    for symbol in symbols:
        result = provider.filings(symbol, start=start.isoformat(), end=end.isoformat(), now=clock)
        outcomes.append(rawstore.store_result(store, provider.name, result, started_at=started, batch=batch, instrument=symbol,
                                              diagnostics={'window': [start.isoformat(), end.isoformat()], 'max_filings': int(max_filings)}, now=clock()))
    return _finish(store, provider.name, outcomes, transport, clock)


# ---------------------------------------------------------------------------- Massive
def _decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def bar_diagnostics(store, symbol, day, result) -> dict:
    """What the accepted bars look like next to what is already stored. A diagnostic only: nothing is corrected and no
    figure here is used for anything else."""
    if result.status != OK:
        return {}
    records = result.records()
    by_session = {}
    for r in records:
        by_session[r['session']] = by_session.get(r['session'], 0) + 1
    regular = [r for r in records if r['session'] == 'regular' and r['exchange_session_date'] == day]
    with store.connect() as db:
        row = db.execute("SELECT value, source FROM feature_observations WHERE instrument=? AND feature_name='close' AND exchange_session_date=? "
                         'ORDER BY id DESC LIMIT 1', (symbol, day)).fetchone()
    comparison = {'exchange_session_date': day, 'stored_daily_close': row[0] if row else None, 'stored_daily_close_source': row[1] if row else None,
                  'note': 'Quality diagnostic only. The last regular-session 1-minute bar is not the official closing-auction price, and the stored '
                          'close is split-adjusted by its own provider, so a small difference is expected.'}
    if regular:
        last, volume = regular[-1], sum((_decimal(r['volume']) or Decimal(0)) for r in regular)
        comparison.update(last_regular_bar_start=last['bar_start'], last_regular_bar_close=str(last['close']), regular_session_volume=str(volume),
                          regular_session_high=str(max(_decimal(r['high']) for r in regular)), regular_session_low=str(min(_decimal(r['low']) for r in regular)))
        stored, close = _decimal(row[0]) if row else None, _decimal(last['close'])
        if stored is not None and close is not None:
            comparison['difference'] = str(close - stored)
    return {'bars_by_session': by_session, 'missing_regular_minutes': quality.missing_regular_minutes(records), 'daily_comparison': comparison}


def run_massive(store, *, symbols=EQUITY_SAMPLE, environ=None, transport=None, clock=now_utc, session_date=None, ticks=True,
                tick_start='10:00:00', tick_seconds=2, min_interval=0.25) -> dict:
    """One session of unadjusted 1-minute bars per symbol and, when ``ticks`` is set, a few seconds of trades and NBBO quotes."""
    key = config.value(config.MASSIVE_API_KEY, environ)
    if not key:
        return _not_configured(store, 'Massive', clock)
    day = session_date or latest_stored_session(store)
    if not day:
        raise FirmLabError('NO_SESSION_DATE: name one with --session-date')
    transport = transport or HttpTransport([massive.HOST], min_interval=min_interval)
    provider = massive.MassiveMarketDataProvider(transport, key)
    started, batch = clock().isoformat(), rawstore.new_batch(store, provider.name, clock())
    outcomes = []
    for symbol in symbols:
        result = provider.bars_1m(symbol, session_date=day, now=clock)
        outcomes.append(rawstore.store_result(store, provider.name, result, started_at=started, batch=batch, instrument=symbol,
                                              diagnostics=bar_diagnostics(store, symbol, day, result), now=clock()))
    if ticks:
        low = datetime.fromisoformat(f'{day}T{tick_start}').replace(tzinfo=ET)
        high = low + timedelta(seconds=int(tick_seconds))
        window = {'window': [low.isoformat(), high.isoformat()]}
        for symbol in symbols:
            for method in (provider.trades, provider.quote_snapshots):
                result = method(symbol, start=low.isoformat(), end=high.isoformat(), now=clock)
                outcomes.append(rawstore.store_result(store, provider.name, result, started_at=started, batch=batch, instrument=symbol, diagnostics=window, now=clock()))
    return _finish(store, provider.name, outcomes, transport, clock)


# ---------------------------------------------------------------------------- Sharadar
def run_sharadar(store, *, symbols=COMPANY_SAMPLE, environ=None, transport=None, clock=now_utc, years=3) -> dict:
    """A few years of as-reported and restated quarterly values, and raw corporate-action events, for a few companies."""
    key, channel = config.value(config.SHARADAR_API_KEY, environ), config.sharadar_channel(environ)
    if not key or not channel:
        return _not_configured(store, 'Sharadar', clock)
    transport = transport or HttpTransport([sharadar.DIRECT_HOST if channel == 'direct' else sharadar.NASDAQ_HOST], min_interval=0.5)
    today = clock().astimezone(ET).date()
    since = today.replace(year=today.year - int(years), day=1).isoformat()
    fundamentals = sharadar.SharadarFundamentalsProvider(transport, key, channel, since=since)
    actions = sharadar.SharadarCorporateActionsProvider(transport, key, channel)
    started, batch = clock().isoformat(), rawstore.new_batch(store, 'Sharadar', clock())
    outcomes = []
    for symbol in symbols:
        result = fundamentals.financial_statements(symbol, known_at=clock().isoformat(), now=clock)
        outcomes.append(rawstore.store_result(store, fundamentals.name, result, started_at=started, batch=batch, instrument=symbol,
                                              diagnostics={'since': since, 'dimensions': list(fundamentals.dimensions)}, now=clock()))
        result = actions.actions(symbol, start=since, end=today.isoformat(), now=clock)
        outcomes.append(rawstore.store_result(store, actions.name, result, started_at=started, batch=batch, instrument=symbol,
                                              diagnostics={'window': [since, today.isoformat()]}, now=clock()))
    with store.connect() as db:
        check = crosscheck.summarise(crosscheck.fundamentals_vs_filings(db))
    store.event('FUNDAMENTALS_VS_SEC_FILINGS', check, clock())           # how many filing dates line up with a stored SEC filing
    report = _finish(store, 'Sharadar', outcomes, transport, clock)
    report['sec_cross_check'] = check
    return report


# ---------------------------------------------------------------------------- ThetaData
def run_thetadata(store, *, symbols=OPTIONS_SAMPLE, environ=None, transport=None, clock=now_utc, as_of=None, expiration=None) -> dict:
    """One expiration of end-of-day option quotes per underlying, with open interest and the provider's own Greeks. Stored raw."""
    if config.value(config.THETADATA_TERMINAL, environ) != '1':
        return _not_configured(store, 'ThetaData', clock)
    day = as_of or latest_stored_session(store)
    if not day:
        raise FirmLabError('NO_SESSION_DATE: name one with --session-date')
    transport = transport or HttpTransport([thetadata.HOST], min_interval=0.05, timeout=60)
    provider = thetadata.ThetaDataOptionsProvider(transport)
    started, batch = clock().isoformat(), rawstore.new_batch(store, provider.name, clock())
    outcomes = []
    for symbol in symbols:
        result = provider.chain(symbol, as_of=day, expiration=expiration, now=clock)
        outcomes.append(rawstore.store_result(store, provider.name, result, started_at=started, batch=batch, instrument=symbol,
                                              diagnostics={'as_of': day, 'expiration': expiration or 'nearest listed on or after as_of'}, now=clock()))
    return _finish(store, provider.name, outcomes, transport, clock)


RUNS = {'edgar': run_edgar, 'massive': run_massive, 'sharadar': run_sharadar, 'thetadata': run_thetadata}
