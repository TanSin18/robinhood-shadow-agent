"""What Firm Lab can and cannot see today. A capability without a real source is UNAVAILABLE: no value, no estimate.

A capability becomes AVAILABLE only through ``promote``/``confirm_daily_data``: actual stored data plus a passed
validation. Nothing is inferred at run time and nothing falls back to a substitute.
"""
from __future__ import annotations

from . import quality
from .errors import CapabilityUnavailable, FirmLabError
from .store import canonical, now_utc

AVAILABLE, UNAVAILABLE, NOT_STARTED, BUILD_ONLY = 'AVAILABLE', 'UNAVAILABLE', 'NOT_STARTED', 'BUILD_ONLY'
PARTIAL_EXISTING, BLOCKED = 'PARTIAL_EXISTING', 'BLOCKED'
# PARTIAL_EXISTING: a source exists somewhere in the system but is not sufficient for, or not connected to, Firm Lab.
# BLOCKED: no candidate provider can supply it cleanly.
STATUSES = (AVAILABLE, UNAVAILABLE, NOT_STARTED, BUILD_ONLY, PARTIAL_EXISTING, BLOCKED)
REGISTRY_VERSION = 2
CONTROL_A_CLOSES = 'Robinhood read gateway, as recorded by Control A'

# (capability, status, provider, detail). Edited only by a deliberate change here, never inferred at run time.
# daily_closes and daily_baseline_features start UNAVAILABLE and are promoted only when stored data passes validation.
INITIAL = (
    ('daily_closes', UNAVAILABLE, CONTROL_A_CLOSES,
     'Completed-session closes for the registered names, read from Control A’s decision capsules (read-only). None is stored yet.'),
    ('daily_baseline_features', UNAVAILABLE, 'Firm Lab feature store',
     'Completed-session count, 200-session average, above-average flag and 126-session momentum. None is stored yet.'),
    ('fundamentals', UNAVAILABLE, None, 'No provider is connected. No fundamental value is stored or estimated.'),
    ('analyst_revisions', UNAVAILABLE, None, 'No provider is connected. No estimate or revision value is stored or estimated.'),
    ('earnings_transcripts', UNAVAILABLE, None, 'No earnings-event or transcript source is connected.'),
    ('intraday_bars', UNAVAILABLE, None, 'The registered read path supplies daily bars only.'),
    ('vwap', UNAVAILABLE, None, 'Needs intraday bars.'),
    ('opening_range', UNAVAILABLE, None, 'Needs intraday bars.'),
    ('time_of_day_rvol', UNAVAILABLE, None, 'Needs intraday bars.'),
    ('trade_flow', UNAVAILABLE, None, 'Aggressive buying and selling, signed volume: needs trade and quote data.'),
    ('order_book', UNAVAILABLE, None, 'Quote and order-book imbalance: needs depth data.'),
    ('options_chain', BUILD_ONLY, 'Robinhood read gateway',
     'Storage schema only. The registered read path can list contracts and bid/ask quotes, but Firm Lab ingests none yet, and implied '
     'volatility and Greeks have never been captured from the provider.'),
    ('options_strategy', NOT_STARTED, None, 'No option recommendation, scenario engine or matched book exists.'),
    ('news_catalysts', PARTIAL_EXISTING, 'Google News RSS (Control A’s advisory desk only)',
     'Headlines are fetched for the advisory notes. No archive, coarse timestamps, aggregator links and no ticker mapping. Firm Lab ingests none.'),
    ('sec_filings', PARTIAL_EXISTING, 'SEC EDGAR submissions API (Control A’s advisory desk only)',
     'Recent filing index entries are read for the advisory notes. Authoritative for filings; not a fundamentals or estimates source. '
     'Firm Lab ingests none.'),
    ('sector_engine', NOT_STARTED, None, 'Not built.'),
    ('ml_ranker', NOT_STARTED, None, 'No model is fitted. Model, target and features are strategy choices for a registered recipe.'),
    ('portfolio_optimizer', NOT_STARTED, None, 'Not built.'),
    ('live_quotes', PARTIAL_EXISTING, 'Robinhood read gateway (Control A’s runs only)',
     'Control A reads bid/ask snapshots during its own runs. There is no streaming feed and no trade data, and Firm Lab ingests none.'),
    ('options_greeks', UNAVAILABLE, None, 'No provider-supplied Greeks or implied volatility have ever been captured; none is estimated.'),
    ('treasury_total_return', UNAVAILABLE, None,
     'No 3-month Treasury-bill total-return source is chosen. The free official series are yields, not total return.'),
    ('corporate_actions', UNAVAILABLE, None,
     'Stored closes are split-adjusted by the provider. Dividends, spin-offs, symbol changes, mergers and delistings are not recorded, so '
     'nothing here is a total return.'),
)
# Registry version 2 (2026-10-01): (capability, status it must currently have, new status). Applied once to an existing database.
CHANGES_V2 = (('news_catalysts', NOT_STARTED, PARTIAL_EXISTING), ('sec_filings', NOT_STARTED, PARTIAL_EXISTING))

# The Data Readiness view: (label, capability, what is required next). Infrastructure readiness, not a trading feature.
DATA_READINESS = (
    ('Daily closes', 'daily_closes', 'A direct, research-only read of provider daily bars, so raw timestamps are stored instead of reconstructed ones.'),
    ('Fundamentals', 'fundamentals', 'Choose a provider with as-originally-reported history and filing timestamps.'),
    ('Analyst estimates and revisions', 'analyst_revisions', 'A feed with dated historical consensus snapshots. Today’s consensus alone is not enough.'),
    ('Earnings and transcripts', 'earnings_transcripts', 'Choose a source with event timestamps, before/after-market timing and source URLs.'),
    ('SEC filings', 'sec_filings', 'A research-only EDGAR reader for Firm Lab that stores acceptance timestamps.'),
    ('General news', 'news_catalysts', 'A licensed news source with a stable archive, precise publication times and ticker mapping.'),
    ('Intraday 1-minute bars', 'intraday_bars', 'Choose an intraday provider (consolidated feed, session flags, deep history).'),
    ('Live quotes and trades', 'live_quotes', 'A streaming quote and trade feed with exchange timestamps and condition codes.'),
    ('Order flow and microstructure', 'trade_flow', 'Tick trades and quotes (to sign trades) and, for book imbalance, depth data.'),
    ('Options chains', 'options_chain', 'Choose an options source; ingest raw chains with quote timestamps, volume and open interest.'),
    ('Options Greeks', 'options_greeks', 'Provider-supplied Greeks stored as provider_*; any Firm Lab estimate would be model_estimated_*.'),
    ('T-bill total return', 'treasury_total_return', 'Choose a 3-month Treasury-bill total-return source on purpose. A yield series does not qualify.'),
    ('Corporate actions and dividends', 'corporate_actions', 'A point-in-time corporate-actions source, before anything is called a total return.'),
)
READINESS_KEYS = tuple(c for _, c, _ in DATA_READINESS)


def _evidence_ok(evidence) -> bool:
    return (isinstance(evidence, dict) and bool(str(evidence.get('provider') or '').strip()) and evidence.get('validation_passed') is True
            and isinstance(evidence.get('records'), int) and evidence['records'] > 0 and bool(evidence.get('validated_at')))


def set_status(store, capability, status, provider=None, detail=None, now=None, *, evidence=None, reason=''):
    """The only way a status is written. AVAILABLE needs evidence: a named source, stored records and a passed validation."""
    if status not in STATUSES:
        raise FirmLabError(f'UNKNOWN_CAPABILITY_STATUS:{status}')
    if status == AVAILABLE and not _evidence_ok(evidence):
        raise FirmLabError(f'AVAILABLE_REQUIRES_A_VALIDATED_SOURCE:{capability}')
    at = (now or now_utc()).isoformat()
    with store.connect() as db:
        row = db.execute('SELECT status FROM data_capabilities WHERE capability=?', (capability,)).fetchone()
        db.execute('INSERT INTO data_capabilities VALUES (?,?,?,?,?) ON CONFLICT(capability) DO UPDATE SET status=excluded.status, '
                   'provider=excluded.provider, detail=excluded.detail, updated_at=excluded.updated_at', (capability, status, provider, detail, at))
        if row is None or row[0] != status or evidence:
            db.execute('INSERT INTO events(at, kind, payload_json) VALUES (?,?,?)',
                       (at, 'CAPABILITY_STATUS', canonical({'capability': capability, 'from': row[0] if row else None, 'to': status,
                                                            'provider': provider, 'evidence': evidence, 'reason': reason})))


def promote(store, capability, provider, detail, *, report, records, now=None):
    """Marks a capability AVAILABLE from a validation report over stored records. Refuses unless the report passed."""
    if not isinstance(report, quality.Report) or not report.passed or not isinstance(records, int) or records <= 0:
        raise FirmLabError(f'AVAILABLE_REQUIRES_A_VALIDATED_SOURCE:{capability}')
    at = now or now_utc()
    set_status(store, capability, AVAILABLE, provider, detail, at, reason='validated stored data',
               evidence={'provider': provider, 'records': records, 'validation_passed': True, 'validated_at': at.isoformat(),
                         'records_checked': report.records_checked})


def confirm_daily_data(store, now=None):
    """daily_closes and daily_baseline_features follow the stored data: AVAILABLE when it validates, UNAVAILABLE when it does not."""
    at = now or now_utc()
    with store.connect() as db:
        rows = db.execute("SELECT instrument, exchange_session_date, value, known_at, source, MAX(revision) FROM feature_observations "
                          "WHERE feature_name='close' GROUP BY instrument, exchange_session_date ORDER BY instrument, exchange_session_date").fetchall()
        derived = db.execute("SELECT COUNT(*) FROM feature_observations WHERE feature_name IN ('ma200','momentum_126d','above_ma200',"
                             "'completed_session_count') AND value IS NOT NULL").fetchone()[0]
    records = [{'instrument': i, 'exchange_session_date': s, 'close': v, 'known_at': k, 'source': src} for i, s, v, k, src, _ in rows]
    report = quality.validate('daily_closes', records, now=at, require_provenance=False)
    current = {c['capability']: c for c in store.capabilities()}
    outcome = {}
    for capability, count, good_detail, base in (
            ('daily_closes', len(records), f'{len(records):,} completed-session closes stored for {len({r["instrument"] for r in records})} '
                                           'instruments, read from Control A’s decision capsules (read-only). Split-adjusted by the provider; '
                                           'not adjusted for dividends.', CONTROL_A_CLOSES),
            ('daily_baseline_features', derived, f'{derived:,} stored values: completed-session count, 200-session average, above-average flag and '
                                                 '126-session momentum, computed from the stored closes.', 'Firm Lab feature store')):
        if report.passed and count > 0:
            if current.get(capability, {}).get('status') != AVAILABLE or current[capability].get('detail') != good_detail:
                promote(store, capability, base, good_detail, report=report, records=count, now=at)
            outcome[capability] = AVAILABLE
        else:
            why = 'nothing is stored yet' if not records else 'stored closes failed validation: ' + ', '.join(report.codes())
            if current.get(capability, {}).get('status') == AVAILABLE or capability not in current:
                set_status(store, capability, UNAVAILABLE, base, f'Not available: {why}.', at, reason=why)
            outcome[capability] = UNAVAILABLE
    return outcome


def seed(store, now=None):
    """Adds registry rows that are missing, applies registry upgrades once, and re-confirms the daily data.
    Existing rows are otherwise left alone, so a deliberate edit is not undone."""
    known = {c['capability']: c['status'] for c in store.capabilities()}
    for capability, status, provider, detail in INITIAL:
        if capability not in known:
            set_status(store, capability, status, provider, detail, now, reason='initial registry')
    version = int(store.meta('capability_registry_version', '1'))
    if version < 2:
        initial = {c: (p, d) for c, _, p, d in INITIAL}
        for capability, old, new in CHANGES_V2:
            if known.get(capability) == old:
                set_status(store, capability, new, *initial[capability], now, reason='registry version 2: current sources documented')
        store.set_meta('capability_registry_version', REGISTRY_VERSION, now)
    confirm_daily_data(store, now)


def require(store, capability):
    """Returns nothing; raises unless the capability is AVAILABLE. Callers never get a stand-in value."""
    status = store.capability(capability)
    if status != AVAILABLE:
        raise CapabilityUnavailable(f'{capability}: {status}')
