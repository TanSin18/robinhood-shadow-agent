"""What Firm Lab can and cannot see today. A capability without a real source is UNAVAILABLE: no value, no estimate.

A capability becomes AVAILABLE only through ``promote``/``confirm_daily_data``: actual stored data plus a passed
validation. Nothing is inferred at run time and nothing falls back to a substitute.
"""
from __future__ import annotations

import json

from . import quality
from .errors import CapabilityUnavailable, FirmLabError
from .store import canonical, now_utc

AVAILABLE, UNAVAILABLE, NOT_STARTED, BUILD_ONLY = 'AVAILABLE', 'UNAVAILABLE', 'NOT_STARTED', 'BUILD_ONLY'
PARTIAL_EXISTING, BLOCKED = 'PARTIAL_EXISTING', 'BLOCKED'
# PARTIAL_EXISTING: a source exists somewhere in the system but is not sufficient for, or not connected to, Firm Lab.
# BLOCKED: no candidate provider can supply it cleanly.
STATUSES = (AVAILABLE, UNAVAILABLE, NOT_STARTED, BUILD_ONLY, PARTIAL_EXISTING, BLOCKED)
REGISTRY_VERSION = 5
CONTROL_A_CLOSES = 'Robinhood read gateway, as recorded by Control A'
TREASURY_PROVIDER = 'U.S. Treasury Fiscal Data'
SEC_PROVIDER = 'SEC EDGAR'
ISSUER_PROVIDER = 'Vanguard'

# (capability, status, provider, detail). Edited only by a deliberate change here, never inferred at run time.
# daily_closes and daily_baseline_features start UNAVAILABLE and are promoted only when stored data passes validation.
INITIAL = (
    ('daily_closes', UNAVAILABLE, CONTROL_A_CLOSES,
     'Completed-session closes for the registered names, read from Control A’s decision capsules (read-only). None is stored yet.'),
    ('daily_baseline_features', UNAVAILABLE, 'Firm Lab feature store',
     'Completed-session count, 200-session average, above-average flag and 126-session momentum. None is stored yet.'),
    ('fundamentals', UNAVAILABLE, None,
     'SEC XBRL company facts (free, authoritative) are the chosen source for a small normalized set of reported values. Nothing is stored '
     'yet. No value is estimated or derived, and no paid provider is connected.'),
    ('analyst_revisions', UNAVAILABLE, None, 'No provider is connected. No estimate or revision value is stored or estimated.'),
    ('earnings_transcripts', UNAVAILABLE, None, 'No transcript source is connected and none is collected. Earnings-release filings are a separate, '
                                                'factual row (earnings events).'),
    ('earnings_events', UNAVAILABLE, None,
     'Earnings-release filings (8-K, Item 2.02) from SEC EDGAR: what was filed and when it was accepted. Facts about the filing only: '
     'nothing is scored, interpreted or predicted, and no transcript is collected. Nothing is stored yet.'),
    ('intraday_bars', UNAVAILABLE, None, 'Massive is chosen; it is not connected and nothing is stored. The registered read path supplies daily bars only.'),
    ('vwap', UNAVAILABLE, None, 'Needs intraday bars.'),
    ('opening_range', UNAVAILABLE, None, 'Needs intraday bars.'),
    ('time_of_day_rvol', UNAVAILABLE, None, 'Needs intraday bars.'),
    ('trade_flow', UNAVAILABLE, None, 'Aggressive buying and selling, signed volume: needs trade and quote data.'),
    ('order_book', UNAVAILABLE, None, 'Quote and order-book imbalance: needs depth data.'),
    ('options_chain', BUILD_ONLY, None,
     'Storage and an adapter exist; ThetaData is chosen and not connected, and nothing is stored. Control A’s read path can list contracts and '
     'quotes for its own runs; Firm Lab does not use it.'),
    ('options_strategy', NOT_STARTED, None, 'No option recommendation, scenario engine or matched book exists.'),
    ('news_catalysts', PARTIAL_EXISTING, 'Google News RSS (Control A’s advisory desk only)',
     'Headlines are fetched for the advisory notes. No archive, coarse timestamps, aggregator links and no ticker mapping. Firm Lab ingests none.'),
    ('sec_filings', PARTIAL_EXISTING, 'SEC EDGAR submissions API (Control A’s advisory desk only)',
     'Control A’s advisory desk reads recent filing index entries for its notes. Firm Lab has its own research-only EDGAR reader; nothing is '
     'stored until the operator runs it. Authoritative for filings; not a fundamentals or estimates source.'),
    ('sector_engine', NOT_STARTED, None, 'Not built.'),
    ('ml_ranker', NOT_STARTED, None, 'No model is fitted. Model, target and features are strategy choices for a registered recipe.'),
    ('portfolio_optimizer', NOT_STARTED, None, 'Not built.'),
    ('live_quotes', PARTIAL_EXISTING, 'Robinhood read gateway (Control A’s runs only)',
     'Control A reads bid/ask snapshots during its own runs. There is no streaming feed and no trade data, and Firm Lab ingests none.'),
    ('options_greeks', UNAVAILABLE, None, 'ThetaData is chosen and not connected. No provider-supplied Greeks or implied volatility are stored; none is estimated.'),
    ('treasury_total_return', UNAVAILABLE, None,
     'Official U.S. Treasury 13-week bill auction records are the input. The construction methodology is approved and frozen; the index is '
     'an accrual between auction and maturity, not a market value. A yield series is not a total return. No auction record is stored yet.'),
    ('corporate_actions', UNAVAILABLE, None,
     'The only free source chosen is the fund issuer’s published cash distributions for VTI (for the total-return ruler); nothing is stored '
     'yet. Splits, symbol changes, spin-offs, mergers and delistings have no source. Stored closes are split-adjusted by their provider.'),
    ('vti_total_return', UNAVAILABLE, None,
     'VTI with each cash distribution reinvested at the close of its ex-dividend session, beside the price-return series. Not computed: no '
     'validated distribution history is stored.'),
    ('total_return_ruler', UNAVAILABLE, None,
     'TOTAL_RETURN_RULER: 70% VTI total return + 30% frozen Treasury-bill accrual index, rebalanced monthly. Not computed until the VTI '
     'distributions pass validation. The earlier price-return ruler is kept unchanged as LEGACY_PRICE_RETURN_RULER.'),
    ('tick_trades_quotes', UNAVAILABLE, None, 'No historical trades or NBBO quotes are stored.'),
)
# The research data stack the operator chose on 2026-10-01. A choice is not a connection and not a capability:
# (capability, chosen provider, raw domains whose stored rows are the evidence, what is still needed).
PROVIDER_PLAN = {
    'sec_filings': ('SEC EDGAR', ('filings',), 'a declared User-Agent (FIRM_LAB_SEC_USER_AGENT), set by the operator'),
    'intraday_bars': ('Massive', ('intraday_bars',), 'an operator-purchased plan and API key'),
    'tick_trades_quotes': ('Massive', ('trades', 'quotes'), 'a plan that includes trades and NBBO quotes, and an API key'),
    'fundamentals': (SEC_PROVIDER, ('xbrl_facts',), 'a declared User-Agent (FIRM_LAB_SEC_USER_AGENT), set by the operator'),
    'earnings_events': (SEC_PROVIDER, ('earnings_events',), 'a declared User-Agent (FIRM_LAB_SEC_USER_AGENT), set by the operator'),
    'corporate_actions': (ISSUER_PROVIDER, ('corporate_actions',), 'nothing: public issuer data, no credential'),
    'vti_total_return': (ISSUER_PROVIDER, ('corporate_actions',), 'nothing: public issuer data, no credential'),
    'total_return_ruler': (ISSUER_PROVIDER, ('corporate_actions',), 'nothing: public issuer data, no credential'),
    'options_chain': ('ThetaData', ('options_chain',), 'an operator-purchased subscription and a running Theta Terminal'),
    'options_greeks': ('ThetaData', ('options_chain',), 'a ThetaData tier that includes implied volatility and Greeks'),
    'treasury_total_return': (TREASURY_PROVIDER, ('treasury_auctions',), 'nothing: public data, no credential'),
}
# Providers that need no credential: before their first run they are ready, not "not configured".
NO_CREDENTIAL_PROVIDERS = (TREASURY_PROVIDER, ISSUER_PROVIDER)
# Capabilities that say PARTIAL_EXISTING, with the reason, when rows are stored but the evidence does not justify AVAILABLE.
PARTIAL_WHEN_STORED = ('fundamentals', 'earnings_events', 'corporate_actions')
CORPORATE_ACTIONS_SCOPE = ('covers VTI cash distributions only; splits, symbol changes, spin-offs, mergers and delistings have no source')
NOT_SELECTED = {
    'analyst_revisions': 'No provider selected: no inferior substitute is connected.',
    'earnings_transcripts': 'Not collected. Deferred until storage and licensing terms are settled.',
    'news_catalysts': 'No paid provider yet. Google News RSS stays advisory and discovery only.',
    'trade_flow': 'Needs validated trades and quotes first.',
    'order_book': 'Depth provider (Databento) deliberately not connected yet.',
    'live_quotes': 'No streaming feed selected; Control A’s run-time snapshots only.',
    'daily_closes': '',
}
# Registry version 3 (research data stack chosen, 2026-10-01): the description of these rows changes, their status does not.
# capability -> (provider, detail) exactly as version 2 wrote them. A row is rewritten only while it still holds exactly this.
V2_TEXT = {
    'fundamentals': (None, 'No provider is connected. No fundamental value is stored or estimated.'),
    'intraday_bars': (None, 'The registered read path supplies daily bars only.'),
    'options_chain': ('Robinhood read gateway',
                      'Storage schema only. The registered read path can list contracts and bid/ask quotes, but Firm Lab ingests none yet, and implied '
                      'volatility and Greeks have never been captured from the provider.'),
    'sec_filings': ('SEC EDGAR submissions API (Control A’s advisory desk only)',
                    'Recent filing index entries are read for the advisory notes. Authoritative for filings; not a fundamentals or estimates source. '
                    'Firm Lab ingests none.'),
    'options_greeks': (None, 'No provider-supplied Greeks or implied volatility have ever been captured; none is estimated.'),
    'treasury_total_return': (None, 'No 3-month Treasury-bill total-return source is chosen. The free official series are yields, not total return.'),
    'corporate_actions': (None, 'Stored closes are split-adjusted by the provider. Dividends, spin-offs, symbol changes, mergers and delistings are not '
                                'recorded, so nothing here is a total return.'),
}
# Registry version 4 (Treasury methodology approved and frozen, 2026-10-02): one description changes, no status does.
V3_TEXT = {
    'treasury_total_return': (None, 'Official U.S. Treasury auction and bill-rate data are the chosen inputs. The construction methodology is a draft '
                                    'awaiting operator approval, so nothing is computed. A yield series is not a total return.'),
}
# Registry version 5 (free research data foundation, 2026-10-02): fundamentals come from SEC XBRL company facts and earnings
# events become their own factual row. Descriptions change; no status does.
V4_TEXT = {
    'fundamentals': (None, 'Sharadar is chosen; it is not connected and nothing is stored. No fundamental value is stored or estimated.'),
    'earnings_transcripts': (None, 'No earnings-event or transcript source is connected.'),
    'corporate_actions': (None, 'Sharadar is chosen; it is not connected and nothing is stored. Stored closes are split-adjusted by their provider; '
                                'dividends, spin-offs, symbol changes, mergers and delistings are not recorded, so nothing here is a total return.'),
}
# Registry versions: (capability, status it must currently have, new status). Each is applied once to an existing database.
CHANGES_V2 = (('news_catalysts', NOT_STARTED, PARTIAL_EXISTING), ('sec_filings', NOT_STARTED, PARTIAL_EXISTING))

# The Data Readiness view: (label, capability, what is required next). Infrastructure readiness, not a trading feature.
DATA_READINESS = (
    ('Daily closes', 'daily_closes', 'A direct, research-only read of provider daily bars, so raw timestamps are stored instead of reconstructed ones.'),
    ('Fundamentals', 'fundamentals', 'A hand-started SEC XBRL sample for a few companies. Each value is timed by its filing header and checked against the filing’s own document; a field without an explicit mapping rule stays unresolved.'),
    ('Analyst estimates and revisions', 'analyst_revisions', 'A feed with dated historical consensus snapshots. Today’s consensus alone is not enough.'),
    ('Earnings events', 'earnings_events', 'A hand-started sample of earnings-release filings (8-K, Item 2.02). Factual event data only: nothing is scored or interpreted.'),
    ('Earnings transcripts', 'earnings_transcripts', 'Storage and licensing terms for transcripts. None is collected.'),
    ('SEC filings', 'sec_filings', 'The operator declares a User-Agent and runs the research-only EDGAR sample. Each acceptance time is checked against the filing’s own header.'),
    ('General news', 'news_catalysts', 'A licensed news source with a stable archive, precise publication times and ticker mapping.'),
    ('Intraday 1-minute bars', 'intraday_bars', 'Operator access to Massive, then a small validated sample of unadjusted 1-minute bars.'),
    ('Historical trades and quotes', 'tick_trades_quotes', 'Operator access to Massive, then a small validated sample of trades and NBBO quotes.'),
    ('Live quotes and trades', 'live_quotes', 'A streaming quote and trade feed with exchange timestamps and condition codes.'),
    ('Order flow and microstructure', 'trade_flow', 'Tick trades and quotes (to sign trades) and, for book imbalance, depth data.'),
    ('Options chains', 'options_chain', 'Operator access to ThetaData (subscription and a running Theta Terminal), then a small validated sample.'),
    ('Options Greeks', 'options_greeks', 'A ThetaData tier with implied volatility and Greeks. Stored under the vendor’s name with its model; never as a bare Greek.'),
    ('T-bill total return', 'treasury_total_return', 'A hand-started auction sample, then the accrual index under the frozen methodology. A ruler only; a yield series does not qualify.'),
    ('Corporate actions and dividends', 'corporate_actions', 'A hand-started read of the issuer’s published VTI distributions, for the total-return ruler. Splits, symbol changes and other actions need a source that is not chosen yet.'),
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
    if version < 3:
        rows = {c['capability']: c for c in store.capabilities()}
        initial = {c: (s, p, d) for c, s, p, d in INITIAL}
        for capability, before in V2_TEXT.items():
            row = rows.get(capability)
            status, provider, detail = initial[capability]
            if row and row['status'] == status and (row['provider'], row['detail']) == before:
                set_status(store, capability, status, provider, detail, now, reason='registry version 3: research data stack chosen')
    if version < 4:
        rows = {c['capability']: c for c in store.capabilities()}
        initial = {c: (s, p, d) for c, s, p, d in INITIAL}
        for capability, before in V3_TEXT.items():
            row = rows.get(capability)
            status, provider, detail = initial[capability]
            if row and row['status'] == status and (row['provider'], row['detail']) == before:
                set_status(store, capability, status, provider, detail, now, reason='registry version 4: Treasury methodology approved and frozen')
    if version < 5:
        rows = {c['capability']: c for c in store.capabilities()}
        initial = {c: (s, p, d) for c, s, p, d in INITIAL}
        for capability, before in V4_TEXT.items():
            row = rows.get(capability)
            status, provider, detail = initial[capability]
            if row and row['status'] == status and (row['provider'], row['detail']) == before:
                set_status(store, capability, status, provider, detail, now, reason='registry version 5: free research data foundation')
    if version < REGISTRY_VERSION:
        store.set_meta('capability_registry_version', REGISTRY_VERSION, now)
    confirm_daily_data(store, now)
    confirm_provider_data(store, now)


def confirm_provider_data(store, now=None):
    """Provider-backed capabilities follow the stored evidence. A capability is AVAILABLE only when, for each of its raw
    domains, every run of the chosen provider's latest sample is OK, rows are actually stored, and each run carries
    complete provenance.
    Configuration alone promotes nothing; a failed validation or missing data leaves (or returns) it below AVAILABLE."""
    from . import rawstore
    at = now or now_utc()
    current = {c['capability']: c for c in store.capabilities()}
    base = {c: (s, p, d) for c, s, p, d in INITIAL}
    outcome = {}
    with store.connect() as db:
        evidence = {}
        for capability, (provider, domains, _) in PROVIDER_PLAN.items():
            rows, proof, problem = 0, [], ''
            for domain in domains:
                table = rawstore.DOMAIN_TABLE[domain]
                count = db.execute(f'SELECT COUNT(*) FROM {table} WHERE provider=?', (provider,)).fetchone()[0]
                batch = rawstore.latest_batch(db, provider, domain)          # one run per instrument of the latest sample
                bad = [r for r in batch if r['status'] != 'OK']
                if not batch:
                    problem = problem or f'no {domain} run recorded'
                elif bad:
                    codes = sorted({c for r in bad for c in r['issues']})
                    first = bad[0]
                    problem = problem or (f'latest {domain} sample: {len(bad)} of {len(batch)} runs not OK ({first["instrument"]}: {first["status"]}'
                                          + (': ' + ', '.join(codes) if codes else f', {first["reason"]}' if first['reason'] else '') + ')')
                elif not count:
                    problem = problem or f'no {domain} rows stored'
                elif any(not r['provenance'] or any(not r['provenance'].get(k) for k in ('provider', 'source_id', 'source_timestamp', 'known_at',
                                                                                         'ingested_at', 'schema_version')) for r in batch):
                    problem = problem or f'{domain} provenance incomplete'
                else:
                    proof.append({'domain': domain, 'run_ids': [r['run_id'] for r in batch], 'instruments': [r['instrument'] for r in batch],
                                  'finished_at': batch[-1]['finished_at'], 'rows': count})
                rows += count
            if capability == 'options_greeks' and not problem:
                greeks = db.execute('SELECT COUNT(*) FROM option_chain_observations WHERE provider=? AND provider_implied_volatility IS NOT NULL '
                                    'AND greeks_provider IS NOT NULL AND greeks_model IS NOT NULL', (provider,)).fetchone()[0]
                problem = '' if greeks else 'no provider Greeks stored with their model named'
                rows = greeks
            if capability == 'treasury_total_return' and not problem:
                # Auction records alone are not a total return: the index must have been computed, without a gap, under the frozen methodology.
                state = db.execute("SELECT value FROM firm_meta WHERE key='treasury_index_status'").fetchone()
                state = json.loads(state[0]) if state else {}
                observations = db.execute("SELECT COUNT(*) FROM benchmark_observations WHERE kind='tbill_13w_accrual_index'").fetchone()[0]
                if state.get('status') != 'OK':
                    problem = 'the bill index is not computed' if not state else f'the bill index stopped: {state.get("gap_reason") or state.get("status")}'
                elif not observations:
                    problem = 'no bill-index observation is stored'
            note = ''
            if capability == 'fundamentals' and not problem:
                problem, note = _fundamentals_evidence(db, provider, proof)
            if capability == 'corporate_actions' and not problem:
                problem = CORPORATE_ACTIONS_SCOPE          # real rows, narrow scope: never called available as a whole
            if capability in ('vti_total_return', 'total_return_ruler') and not problem:
                state = db.execute("SELECT value FROM firm_meta WHERE key='vti_total_return_status'").fetchone()
                state = json.loads(state[0]) if state else {}
                kind = 'vti_total_return_index' if capability == 'vti_total_return' else 'index_70_30_vti_total_return'
                rows = db.execute('SELECT COUNT(*) FROM benchmark_observations WHERE kind=?', (kind,)).fetchone()[0]
                if state.get('status') != 'OK':
                    codes = ', '.join(sorted({i.get('code', '') for i in state.get('issues') or []}))
                    problem = ('the total return is not computed' if not state else
                               f'the total return stopped: {codes or state.get("gap_reason") or state.get("status")}')
                elif capability == 'total_return_ruler' and state.get('ruler_status') != 'OK':
                    problem = f'the total-return ruler stopped: {state.get("ruler_gap_reason") or state.get("ruler_status")}'
                elif not rows:
                    problem = 'no total-return observation is stored'
                else:
                    applied = len(state.get('distributions_applied') or [])
                    note = (f'={rows:,} sessions computed through {state.get("last_session")} from the stored closes and {applied} issuer '
                            f'distributions ({provider}), each checked against the stored close on its ex-date. Independent confirmation of the '
                            'amounts: ' + ('compared and equal' if state.get('independent_confirmation') == 'COMPARED' else 'none stored') + '.')
            evidence[capability] = (provider, rows, proof, problem, note)
    for capability, (provider, rows, proof, problem, note) in evidence.items():
        status_now = current.get(capability, {}).get('status')
        if not problem and rows > 0:
            detail = note[1:] if note.startswith('=') else (f'{rows:,} validated rows stored from {provider}; last run '
                                                            f'{proof[-1]["finished_at"][:19]} UTC.' + (' ' + note if note else ''))
            if status_now != AVAILABLE or current[capability].get('detail') != detail:
                set_status(store, capability, AVAILABLE, provider, detail, at, reason='validated provider data',
                           evidence={'provider': provider, 'records': rows, 'validation_passed': True, 'validated_at': at.isoformat(), 'runs': proof})
            outcome[capability] = AVAILABLE
        else:
            floor, source, text = base[capability]
            if capability in PARTIAL_WHEN_STORED and rows > 0:
                # Something real is stored, but not enough to call the capability available. Say so, with the reason.
                detail = f'{rows:,} rows stored from {provider}, not sufficient: {problem}.'
                if status_now != PARTIAL_EXISTING or current[capability].get('detail') != detail:
                    set_status(store, capability, PARTIAL_EXISTING, provider, detail, at, reason=problem)
                outcome[capability] = PARTIAL_EXISTING
                continue
            if status_now == AVAILABLE or (capability in PARTIAL_WHEN_STORED and status_now == PARTIAL_EXISTING):
                # the evidence is gone or the latest validation failed: take it back
                set_status(store, capability, floor, source, f'{text} Not available: {problem}.', at, reason=problem)
                outcome[capability] = floor
                continue
            outcome[capability] = status_now
    return outcome


def _fundamentals_evidence(db, provider, proof):
    """(problem, note) for the company-facts sample. Stored rows are not enough: every company of the latest sample must
    have its critical fields resolved for the current period of every filing read and confirmed in the filing's own
    document, and every stored fact must carry its SEC acceptance time. Fields that stay unresolved are named in the note."""
    run_ids = [i for p in proof for i in p['run_ids']]
    marks = ','.join('?' * len(run_ids))
    undated = db.execute("SELECT COUNT(*) FROM fundamental_fact_observations WHERE provider=? AND (accepted_timestamp IS NULL OR accepted_timestamp='')",
                         (provider,)).fetchone()[0]
    if undated:
        return f'{undated} stored facts carry no SEC acceptance time', ''
    failing, empty = [], {}
    for instrument, text in db.execute(f'SELECT instrument, diagnostics_json FROM provider_runs WHERE id IN ({marks}) ORDER BY id', run_ids):
        report = (json.loads(text or '{}') or {}).get('validation') or {}
        verdict = report.get('quality') or {}
        if verdict.get('passes') is not True:
            fields = sorted({x['field'] for x in (verdict.get('critical_unresolved') or []) + (verdict.get('critical_not_confirmed_in_filing') or [])})
            failing.append(f'{instrument}: ' + (', '.join(fields) if fields else 'no validation report'))
        for name in (verdict.get('unresolved_by_field') or {}):
            if not (report.get('accepted_by_field') or {}).get(name):
                empty.setdefault(name, []).append(instrument)
    if failing:
        return 'critical fields unresolved or not confirmed in the filing (' + '; '.join(failing) + ')', ''
    note = ''
    if empty:
        note = 'Left unresolved, never derived: ' + '; '.join(f'{name} ({", ".join(who)})' for name, who in sorted(empty.items())) + '.'
    return '', note


def require(store, capability):
    """Returns nothing; raises unless the capability is AVAILABLE. Callers never get a stand-in value."""
    status = store.capability(capability)
    if status != AVAILABLE:
        raise CapabilityUnavailable(f'{capability}: {status}')
