"""The Historical Data Readiness report: what is stored, how it is dated, and whether it meets the sufficiency bars.

Counts, dates, versions and hashes only. No price, no licensed value and no model output goes into the report, so the
small file the dashboard reads can sit outside the licensed database. Both databases are opened read-only here.

The report never rounds a missing thing up. With no validated historical bars stored, every market bar is "not met",
the strict sample count is 0 and every model family is INSUFFICIENT.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np

from . import (BAR_KNOWN_AT_BASIS, BAR_KNOWN_AT_VERSION, HELD_AT_THE_TIME, POLICY_VERSION, PUBLISHER_DATED_HISTORICAL, RETROSPECTIVE, RETURN_BASIS, SPLIT_ADJUSTED,
               TOTAL_RETURN_ADJUSTED, UNADJUSTED, WARNING, features, regimes, splits, sufficiency, targets, universe)
from .store import BAR_TABLE, HistoryStore, content_hash, now_utc

REPORT_VERSION = 'historical-data-readiness-v1'
MET, NOT_MET, NOT_MEASURABLE = 'MET', 'NOT_MET', 'NOT_MEASURABLE'
PROVIDER_DECISION = {
    'status': 'OPERATOR PURCHASE DECISION REQUIRED', 'selected_provider': 'Sharadar', 'product': 'Prices — Full History (Personal Use License)',
    'price': '$39 per month or $299 per year, read on the vendor page 2026-10-04', 'purchased': False,
    'licence': 'Personal use by a natural person. No redistribution. Raw data must be deleted within 30 days of cancelling; '
               'models, backtest results and other derived work that cannot reproduce the data may be kept.',
    'open_question': 'The terms do not name machine learning. They list "models" among what may be kept. The operator reads and accepts the terms.',
    'not_selected': {'Massive': 'individual plans are display-use only; non-display use needs a separate licence', 'Alpaca': 'history from 2016; delisted coverage not documented',
                     'Databento': 'daily history from 2018 or later', 'Norgate': 'the updater runs on Windows only',
                     'EODHD / Tiingo': 'no delisting reasons or ticker-change events; delisted coverage partial'},
    'document': 'docs/firm_lab/CHECKPOINT8_PROVIDER_DECISION.md'}


PROXY_SYMBOLS = ('SPY', 'VTI', 'IVV')
CROSS_CHECK_TOLERANCE = 1e-4


def _read_only(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
    db.execute('PRAGMA query_only=ON')
    return db


def _tables(db) -> set:
    return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _one(db, query, default=None):
    row = db.execute(query).fetchone()
    return row if row else default


def research_sources(path) -> dict:
    """What the research database already holds, with the tier each kind of row can honestly claim."""
    db = _read_only(path)
    try:
        names = _tables(db)
        if 'firm_meta' not in names or _one(db, "SELECT value FROM firm_meta WHERE key='mode'") != ('BUILD_OBSERVE',):
            raise ValueError('BUILD_OBSERVE_RESEARCH_DATABASE_REQUIRED')
        out = {}
        if 'fundamental_fact_observations' in names:
            n, companies, filings, restated, first, last, low, high, dated = _one(db, (
                'SELECT COUNT(*), COUNT(DISTINCT instrument), COUNT(DISTINCT accession_number), COALESCE(SUM(is_restatement), 0), MIN(accepted_timestamp), '
                'MAX(accepted_timestamp), MIN(period_end), MAX(period_end), SUM(accepted_timestamp IS NOT NULL) FROM fundamental_fact_observations'))
            out['fundamentals'] = {'companies': companies, 'filings': filings, 'facts': n, 'restatements': int(restated), 'first_acceptance': first, 'last_acceptance': last,
                                   'first_period_end': low, 'last_period_end': high, 'facts_with_acceptance_time': int(dated or 0),
                                   'tier': PUBLISHER_DATED_HISTORICAL if n and dated == n else RETROSPECTIVE if n else None,
                                   'known_at_methodology': 'SEC acceptance timestamp of the filing that reported the value; a restated value is a later version and is '
                                                           'invisible before its own filing was accepted',
                                   'source': 'SEC EDGAR XBRL company facts', 'version': 'normalization rules v2 (sec_xbrl_normalization.md)'}
        if 'earnings_event_observations' in names:
            n, companies, first, last, documents, transcripts = _one(db, (
                'SELECT COUNT(*), COUNT(DISTINCT instrument), MIN(accepted_timestamp), MAX(accepted_timestamp), SUM(release_document_url IS NOT NULL), '
                "SUM(transcript_available IN (1, '1', 'true', 'TRUE')) FROM earnings_event_observations"))
            out['earnings'] = {'events': n, 'companies': companies, 'first_acceptance': first, 'last_acceptance': last, 'release_documents': int(documents or 0),
                               'transcripts': int(transcripts or 0), 'tier': PUBLISHER_DATED_HISTORICAL if n else None,
                               'known_at_methodology': 'SEC acceptance timestamp of the 8-K (Item 2.02)', 'source': 'SEC EDGAR', 'version': 'earnings_events.md'}
        if 'macro_observations' in names:
            series = {}
            for name, n, first, last, revisions in db.execute('SELECT series, COUNT(*), MIN(published_at), MAX(published_at), MAX(revision) FROM macro_observations GROUP BY series'):
                series[name] = {'observations': n, 'first_published': first, 'last_published': last, 'highest_revision': revisions}
            out['macro'] = {'series': series, 'tier': PUBLISHER_DATED_HISTORICAL if series else None,
                            'known_at_methodology': 'the official release time of each value; a revision is a later row and is invisible before its own release',
                            'source': 'Federal Reserve Board and Bureau of Economic Analysis', 'version': 'macro store v1'}
        if 'feature_observations' in names:
            n, instruments, first, last, captured_first, captured_last = _one(db, (
                "SELECT COUNT(*), COUNT(DISTINCT instrument), MIN(exchange_session_date), MAX(exchange_session_date), MIN(known_at), MAX(known_at) "
                "FROM feature_observations WHERE feature_name='close'"))
            out['closes_held'] = {'closes': n, 'instruments': instruments, 'first_session': first, 'last_session': last, 'captured_from': captured_first,
                                  'captured_to': captured_last, 'fields': 'close only (no open, high, low or volume)', 'tier': RETROSPECTIVE if n else None,
                                  'known_at_methodology': 'captured after the fact from the registered read path; not held at the time and not a licensed archive',
                                  'source': 'Robinhood read gateway, as recorded by Control A'}
            proxy = db.execute("SELECT exchange_session_date, value FROM feature_observations WHERE feature_name='close' AND instrument='VTI' "
                               'ORDER BY exchange_session_date, known_at, revision').fetchall()
            latest = dict(proxy)                                       # the latest revision of a session wins, as in the feature loader
            out['_proxy'] = {'instrument': 'VTI', 'sessions': list(latest), 'closes': [float(v) for v in latest.values()]}
            held = {}
            for instrument, session, value in db.execute("SELECT instrument, exchange_session_date, value FROM feature_observations WHERE feature_name='close' "
                                                         'ORDER BY instrument, exchange_session_date, known_at, revision'):
                held.setdefault(instrument, {})[session] = float(value)
            out['_closes'] = held
        if 'corporate_action_observations' in names:
            n, instruments, benchmark = _one(db, 'SELECT COUNT(*), COUNT(DISTINCT instrument), COALESCE(SUM(benchmark_only), 0) FROM corporate_action_observations')
            out['corporate_actions_held'] = {'rows': n, 'instruments': instruments, 'benchmark_only_rows': int(benchmark)}
        decisions = []
        if 'macro_observations' in names:
            previous = None
            for period, value in db.execute("SELECT period, payload_json FROM macro_observations WHERE series='fed_target_upper' ORDER BY period, revision"):
                level = float(json.loads(value)['value'])
                if previous is not None:
                    decisions.append((period, level - previous))
                previous = level
        out['_decisions'] = decisions
        if 'data_capabilities' in names:
            out['capabilities'] = dict(db.execute('SELECT capability, status FROM data_capabilities'))
        return out
    finally:
        db.close()


def cross_check(store, securities, held) -> dict:
    """Compares stored closes with the closes Firm Lab already holds from another source, one (instrument, session) at a
    time. Returns counts and the identities of disagreements; no price."""
    by_symbol = {}
    for sid, sec in securities.items():
        by_symbol.setdefault(sec['symbol'], []).append(sid)
    compared = agreeing = 0
    disagreements, unmatched = [], []
    for symbol, closes in sorted(held.items()):
        ids = by_symbol.get(symbol, [])
        if len(ids) != 1:
            unmatched.append(symbol)
            continue
        columns = store.bars(ids[0])
        mine = dict(zip(columns['sessions'], columns['close']))
        for session, value in sorted(closes.items()):
            if session in mine:
                compared += 1
                if abs(float(mine[session]) / value - 1) <= CROSS_CHECK_TOLERANCE:
                    agreeing += 1
                elif len(disagreements) < 200:
                    disagreements.append([symbol, session])
    return {'compared': compared, 'agreeing': agreeing, 'share_agreeing': agreeing / compared if compared else None, 'disagreements': disagreements,
            'disagreements_listed': len(disagreements), 'instruments_not_matched': unmatched, 'tolerance': CROSS_CHECK_TOLERANCE}


def history_sources(path, research_closes=None) -> dict:
    """What the historical database holds. Read-only; no price leaves this function."""
    if not path or not Path(path).is_file():
        return {'exists': False}
    with HistoryStore(path, read_only=True) as store:
        db = store.db
        summary = store.bar_summary()
        securities = {}
        for _, payload, _ in store.rows('history_securities'):
            securities[payload['security_id']] = payload
        captures = [{k: p.get(k) for k in ('capture_id', 'kind', 'source', 'file', 'sha256', 'bytes', 'adapter', 'captured_at', 'rows_read', 'rows_stored', 'rows_rejected',
                                           'rejections_by_reason', 'blocks_by_change', 'first_session', 'last_session', 'price_table')}
                    for _, p, _ in store.rows('history_captures')]
        actions = {}
        for _, payload, _ in store.rows('history_actions'):
            actions[payload['type']] = actions.get(payload['type'], 0) + 1
        read = sum(c['rows_read'] or 0 for c in captures if c['kind'] == 'bars')
        rejected = sum(c['rows_rejected'] or 0 for c in captures if c['kind'] == 'bars')
        with_bars = set(store.security_ids())
        chosen = universe.load(store)
        reports = [(created, payload) for _, payload, created in store.rows('history_reports') if payload.get('kind') == 'strict_count']
        reservation = [payload for _, payload, _ in store.rows('history_reservations') if payload.get('kind') == 'holdout_reservation']
        index_events = store.count('history_index_events')
        last_by_year = {}
        for sid in with_bars:
            sec = securities.get(sid)
            if sec and sec['is_delisted']:
                last = db.execute(f'SELECT MAX(last_session) FROM {BAR_TABLE} WHERE security_id=?', (sid,)).fetchone()[0]
                last_by_year[last[:4]] = last_by_year.get(last[:4], 0) + 1
        proxy = None
        for symbol in PROXY_SYMBOLS:                                   # a broad-market fund, when the provider's fund table is stored
            match = [sid for sid, sec in securities.items() if sec['symbol'] == symbol and sec['price_table'] == 'funds' and sid in with_bars]
            if len(match) == 1:
                columns = store.bars(match[0])
                proxy = {'instrument': symbol, 'sessions': columns['sessions'], 'closes': [float(v) for v in columns['close']]}
                break
        return {'exists': True, 'bars': summary, 'captures': captures, 'rows_read': read, 'rows_rejected': rejected, '_proxy': proxy,
                '_cross_check': cross_check(store, securities, research_closes) if research_closes else None,
                'securities': len(securities), 'securities_with_bars': len(with_bars), 'delisted_securities': sum(1 for s in securities.values() if s['is_delisted']),
                'delisted_with_bars': sum(1 for sid in with_bars if securities.get(sid, {}).get('is_delisted')), 'last_bar_of_delisted_by_year': dict(sorted(last_by_year.items())),
                'funds': sum(1 for s in securities.values() if s['price_table'] == 'funds'), 'sources': sorted({s['source'] for s in securities.values()}),
                'actions_by_type': actions, 'index_events': index_events, 'universe': chosen['manifest'],
                'strict_count': max(reports, key=lambda r: r[0])[1] if reports else None, 'holdout_reservation_stored': bool(reservation)}


def _bar(identity, name, target, minimum, measured, status, note=''):
    return {'id': identity, 'name': name, 'target': target, 'minimum': minimum, 'measured': measured, 'status': status, 'note': note}


def _regimes(research, first=None, last=None) -> dict:
    proxy = research.get('_proxy') or {}
    if len(proxy.get('sessions', [])) < regimes.VOL_MINIMUM_HISTORY:
        return {'status': NOT_MEASURABLE, 'reason': 'no broad-market close series of at least a year is stored'}
    found = regimes.coverage(proxy['sessions'], proxy['closes'], research.get('_decisions', ()), first=first, last=last)
    return {'status': 'DESCRIBED', 'proxy': proxy['instrument'], 'proxy_tier': RETROSPECTIVE, **found,
            'note': 'the only close series stored today; it covers the Checkpoint 7 window, not a historical training period'}


def build(research_database, history_database=None, *, now=None) -> dict:
    research = research_sources(research_database)
    history = history_sources(history_database, research.get('_closes'))
    stored = history['exists'] and history['bars']['bars'] > 0
    check = history.get('_cross_check') if stored else None
    development = None
    if stored and history.get('_proxy'):
        segment = splits.reservation()['segments']
        development = regimes.coverage(history['_proxy']['sessions'], history['_proxy']['closes'], research.get('_decisions', ()),
                                       first=segment[splits.DEVELOPMENT][0], last=segment[splits.DEVELOPMENT][1])
    regime_bar = None if development is None else (len(development['bear_markets']) >= sufficiency.REGIME_BAR['bear_markets']
                                                   and len(development['corrections']) >= sufficiency.REGIME_BAR['corrections']
                                                   and development['high_volatility_episodes'] >= sufficiency.REGIME_BAR['high_volatility_episodes']
                                                   and len(development['rising_rate_periods']) >= sufficiency.REGIME_BAR['rising_rate_periods']
                                                   and len(development['falling_rate_periods']) >= sufficiency.REGIME_BAR['falling_rate_periods'])
    years = None if development is None or not development['sessions'] else development['sessions'] / 252.0
    counted = history.get('strict_count') if stored else None
    strict = {str(h): 0 for h in targets.HORIZONS}
    tiers = {HELD_AT_THE_TIME: 0, PUBLISHER_DATED_HISTORICAL: 0}
    if counted:
        strict, tiers = counted['strict_samples'], counted['by_tier']
    reservation = splits.reservation()
    holdout = {'checkpoint7_holdout_reused_as_pristine': False, 'split_version': splits.SPLIT_VERSION, 'segments': reservation['segments'],
               'historical_holdout': 'RESERVED_NO_DATA_YET' if not stored else 'RESERVED_SEALED', 'forward_holdout': 'RESERVED_SEALED_ACCUMULATING',
               'reservation_stored_in_database': bool(history.get('holdout_reservation_stored')), 'rules': reservation['rules'],
               'purge_sessions': reservation['purge_sessions'], 'document': 'docs/firm_lab/CHECKPOINT8_HOLDOUT_DESIGN.md'}
    verdicts = {}
    if counted and counted.get('effective'):
        for h in ('5', '20'):
            m = counted['effective'][h]
            verdicts[h] = {f: sufficiency.family_verdict(f, e_train=m['effective_observations_development'], holdout_ic=m['detectable_ic_holdout'],
                                                         regimes_met=bool(regime_bar), bear_markets_in_training=len(development['bear_markets']) if development else 0,
                                                         training_years=years or 0.0, sequence_share=counted.get('sequence_share')) for f in sufficiency.FAMILIES}
    else:
        verdicts = {h: sufficiency.no_data_verdicts() for h in ('5', '20')}
    bars = history['bars'] if stored else {}
    rejected = history['rows_rejected'] / history['rows_read'] if stored and history['rows_read'] else None
    # E1, E2, E3 and F2 are coverage shares against the historical universe. Until the collectors have been run for that
    # universe there is nothing to divide by, so they are not met; the number shown is what is stored today.
    spec = [
        _bar('H1', 'Years of daily history', 'from 1998-01', 'from 2005-01', bars.get('first_session'),
             MET if stored and bars['first_session'] <= sufficiency.HISTORY['minimum_first_session'] else NOT_MET),
        _bar('H3', 'Instruments per reconstitution', 1000, 500, (history.get('universe') or {}).get('member_count_min') if stored else None,
             MET if stored and history.get('universe') and history['universe']['member_count_min'] >= sufficiency.HISTORY['minimum_members'] else NOT_MET),
        _bar('H4', 'Delisted securities stored', 'counted', 'more than 0', history.get('delisted_with_bars') if stored else 0,
             MET if stored and history['delisted_with_bars'] > 0 else NOT_MET),
        _bar('H5', 'Sectors', '11 groups, 20 names each', 'reported', None, NOT_MEASURABLE, 'no historical sector classification is stored'),
        _bar('H6', 'Regimes inside training plus development', '2 bear markets, 4 corrections, rising and falling rates, 3 high-volatility episodes', 'the same',
             None if development is None else {'bear_markets': len(development['bear_markets']), 'corrections': len(development['corrections']),
                                               'high_volatility_episodes': development['high_volatility_episodes'],
                                               'rising_rate_periods': len(development['rising_rate_periods']), 'falling_rate_periods': len(development['falling_rate_periods'])},
             (MET if regime_bar else NOT_MET) if development is not None else NOT_MEASURABLE if stored else NOT_MET,
             'measured on a stored broad-market fund over the development period; rate periods need the full record of policy decisions'),
        _bar('P1', 'Strict point-in-time samples (tier B, 20-session label)', 'reported', 'more than 0', strict[str(targets.MAX_HORIZON)],
             MET if strict[str(targets.MAX_HORIZON)] > 0 else NOT_MET),
        _bar('O4', 'Rejected bar rows', 'at most 0.1%', 'at most 0.5%', None if rejected is None else f'{rejected:.3%}',
             NOT_MET if rejected is None else MET if rejected <= sufficiency.COVERAGE['rejected_minimum'] else NOT_MET),
        _bar('O7', 'Print precision of adjusted prices', 'at most 1% of member rows coarser than 0.05% of price', 'at most 5%',
             None if not counted or counted.get('coarse_print_share') is None else f'{counted["coarse_print_share"]:.3%}',
             NOT_MET if not counted or counted.get('coarse_print_share') is None else MET if counted['high_low_open_families_usable'] else NOT_MET,
             'above the minimum, no feature that reads a high, low or open is used for any row; close-based features use the unadjusted close and are not affected'),
        _bar('O6', 'Independent cross-check of closes', 'every overlap agrees', '99.5% agree',
             None if not check or not check['compared'] else f'{check["share_agreeing"]:.3%} of {check["compared"]:,}',
             NOT_MET if not check or not check['compared'] else MET if check['share_agreeing'] >= sufficiency.COVERAGE['cross_check_minimum'] else NOT_MET,
             'compares stored closes with the closes Firm Lab already holds from the registered read path, one instrument and session at a time'),
        _bar('E1', 'Earnings events with acceptance time', '80% of member-quarters from 2010', '60%', (research.get('earnings') or {}).get('events'), NOT_MET,
             'five companies, four events each; no universe to measure coverage against'),
        _bar('E2', 'Periodic filings with acceptance time', '90% of member periods from 2011', '75%', (research.get('fundamentals') or {}).get('filings'), NOT_MET,
             'five companies, four filings each'),
        _bar('E3', 'Macro releases, first-published value and official time', '98% of scheduled releases', '95%',
             sum(s['observations'] for s in (research.get('macro') or {}).get('series', {}).values()), NOT_MET,
             'Fed target and PCE for mid-2026 only; CPI, labor and Treasury yields are not stored'),
        _bar('F2', 'Restatement history', 'every reporting filing kept in acceptance order; one real restatement shown', 'the same',
             (research.get('fundamentals') or {}).get('restatements'), NOT_MET,
             'versions are stored and tested on synthetic filings; no real restatement is in the five-company sample'),
    ]
    provenance = [
        {'name': 'Historical daily OHLCV', 'provider': ', '.join(history.get('sources', [])) if stored else 'none stored (Sharadar selected, not purchased)',
         'date_range': [bars.get('first_session'), bars.get('last_session')] if stored else None, 'version': POLICY_VERSION,
         'known_at_methodology': f'{BAR_KNOWN_AT_VERSION}: a bar is usable no earlier than the open of the next exchange session ({BAR_KNOWN_AT_BASIS}); '
                                 'the time Firm Lab received it is stored separately',
         'adjustment_basis': f'open, high, low, close, volume: {SPLIT_ADJUSTED}; unadjusted close: {UNADJUSTED}; total-return close: {TOTAL_RETURN_ADJUSTED} (read only to size a recorded distribution)',
         'pit_eligibility': PUBLISHER_DATED_HISTORICAL if stored else None,
         'limitations': ['No source gives the time a historical bar was first published; the next open is a bound, not a measurement.',
                         'The vendor re-adjusts past prices after a split and may correct past prints; versioned captures record every change.',
                         'Reprinted adjusted prices are rounded. Close-based features use the unadjusted close and confirmed split ratios instead; features that read a '
                         'high, low or open are unavailable where the adjusted print is coarser than 0.05% of price.',
                         'No post-delisting return exists: a label that ends at a bankruptcy or regulatory delisting overstates what a holder recovered.']},
        {'name': 'Closes already held', 'provider': (research.get('closes_held') or {}).get('source'),
         'date_range': [(research.get('closes_held') or {}).get('first_session'), (research.get('closes_held') or {}).get('last_session')], 'version': 'Checkpoint 2 capture',
         'known_at_methodology': (research.get('closes_held') or {}).get('known_at_methodology'), 'adjustment_basis': 'split-adjusted closes as the read path reported them',
         'pit_eligibility': RETROSPECTIVE, 'limitations': ['Close only.', '23 instruments chosen today: a survivor list.', 'This is the burned Checkpoint 7 window.']},
        {'name': 'Fundamentals', 'provider': 'SEC EDGAR', 'date_range': [(research.get('fundamentals') or {}).get('first_acceptance'), (research.get('fundamentals') or {}).get('last_acceptance')],
         'version': (research.get('fundamentals') or {}).get('version'), 'known_at_methodology': (research.get('fundamentals') or {}).get('known_at_methodology'),
         'adjustment_basis': 'as filed; a later filing never replaces an earlier value', 'pit_eligibility': (research.get('fundamentals') or {}).get('tier'),
         'limitations': ['Five companies, four periodic reports each.', 'XBRL exists from 2009 to 2011 onward only.', 'Debt is unresolved for two of the five companies.']},
        {'name': 'Earnings events', 'provider': 'SEC EDGAR', 'date_range': [(research.get('earnings') or {}).get('first_acceptance'), (research.get('earnings') or {}).get('last_acceptance')],
         'version': (research.get('earnings') or {}).get('version'), 'known_at_methodology': (research.get('earnings') or {}).get('known_at_methodology'),
         'adjustment_basis': 'not applicable', 'pit_eligibility': (research.get('earnings') or {}).get('tier'),
         'limitations': ['Five companies, four events each.', 'No consensus estimate, so no surprise.', 'No transcript.']},
        {'name': 'Macro', 'provider': (research.get('macro') or {}).get('source'), 'date_range': None, 'version': (research.get('macro') or {}).get('version'),
         'known_at_methodology': (research.get('macro') or {}).get('known_at_methodology'), 'adjustment_basis': 'as first published; revisions are later rows',
         'pit_eligibility': (research.get('macro') or {}).get('tier'),
         'limitations': ['Fed target and PCE for mid-2026 only.', 'CPI, labor and Treasury yields are not stored.',
                         'FRED and ALFRED are not used: their terms prohibit storing the data and using it to train models without written consent.']},
        {'name': 'Historical universe', 'provider': 'formed by Firm Lab from stored bars', 'date_range': [history['universe']['first_formation'], history['universe']['last_formation']]
         if stored and history.get('universe') else None, 'version': universe.UNIVERSE_VERSION,
         'known_at_methodology': 'membership is formed on the last session of a month from bars up to that session and takes effect on the next session',
         'adjustment_basis': 'the minimum-price screen reads the unadjusted close', 'pit_eligibility': PUBLISHER_DATED_HISTORICAL if stored and history.get('universe') else None,
         'limitations': ['No sector, market value or index membership is read.', 'S&P 500 membership events are stored as a reference only.']},
    ]
    gaps = ['No licensed historical market data is stored: operator purchase decision required.' if not stored else None,
            'Historical sector classification: none stored; the vendor classification describes companies as they are today.',
            'Analyst estimates and revisions: no individually licensable point-in-time source found.',
            'Earnings transcripts: no licensed source selected; none is collected.',
            'Historical news: no adequate licensed point-in-time archive identified.',
            'Macro vintages: CPI, labor and Treasury yields need collectors against BLS, BEA, Treasury and the Philadelphia Fed real-time data set.',
            'Fundamentals and earnings history: five companies only; the collectors must be run for the historical universe.',
            'Post-delisting returns: no source.',
            'Intraday history: deferred; not needed before a daily tournament.']
    report = {
        'kind': 'historical_data_readiness', 'report_version': REPORT_VERSION, 'warning': WARNING, 'spec_version': sufficiency.SPEC_VERSION, 'policy_version': POLICY_VERSION,
        'market_data': {'status': 'STORED' if stored else 'NO_VALIDATED_HISTORICAL_BARS', 'provider': ', '.join(history.get('sources', [])) if stored else None,
                        'history_range': [bars.get('first_session'), bars.get('last_session')] if stored else None, 'securities_with_bars': history.get('securities_with_bars', 0),
                        'bars': bars.get('bars', 0), 'funds': history.get('funds', 0), 'delisted_with_bars': history.get('delisted_with_bars', 0),
                        'last_bar_of_delisted_by_year': history.get('last_bar_of_delisted_by_year', {}), 'block_versions': bars.get('block_versions', {}),
                        'rows_read': history.get('rows_read', 0), 'rows_rejected': history.get('rows_rejected', 0), 'captures': history.get('captures', []),
                        'adjustment_basis': SPLIT_ADJUSTED, 'return_basis': RETURN_BASIS, 'known_at_version': BAR_KNOWN_AT_VERSION,
                        'closes_held': research.get('closes_held')},
        'corporate_actions': {'historical_by_type': history.get('actions_by_type', {}), 'held_rows': (research.get('corporate_actions_held') or {}).get('rows', 0),
                              'held_note': 'the rows held today are VTI cash distributions, benchmark-only', 'index_events': history.get('index_events', 0)},
        'universe': history.get('universe') if stored else None,
        'feature_versions': {'feature_set_version': features.FEATURE_SET_VERSION, 'versions': sorted({d['version'] for d in features.DEFINITIONS}),
                             'features': len(features.DEFINITIONS), 'code_hash': features.code_hash(), 'computed_on_stored_bars': bool(counted),
                             'close_based_fibonacci_preserved': True},
        'fundamentals': research.get('fundamentals'), 'earnings': research.get('earnings'), 'macro': research.get('macro'),
        'strict_training': {'strict_samples': strict, 'by_tier': tiers, 'retrospective_samples_in_this_dataset': 0,
                            'checkpoint7_retrospective_samples': 6490, 'checkpoint7_note': 'a separate close-only dataset; never added to the strict count',
                            'raw_member_rows': (counted or {}).get('raw_member_rows', 0), 'unique_sessions': (counted or {}).get('unique_sessions', 0),
                            'unique_instruments': (counted or {}).get('unique_instruments', 0), 'by_segment': (counted or {}).get('by_segment'),
                            'effective': (counted or {}).get('effective'), 'label_states': (counted or {}).get('label_states'),
                            'delisting_exits_by_reason': (counted or {}).get('delisting_exits_by_reason'), 'dataset_version': 'pit-dataset-v2',
                            'breaks_by_reason': (counted or {}).get('breaks_by_reason'), 'splits_confirmed': (counted or {}).get('splits_confirmed'),
                            'split_convention': (counted or {}).get('split_convention'), 'dividend_basis': (counted or {}).get('dividend_basis'),
                            'coarse_print_share': (counted or {}).get('coarse_print_share'),
                            'target_version': targets.TARGET_VERSION, 'dataset_spec_hash': ((counted or {}).get('manifest') or {}).get('dataset_spec_hash')},
        'holdout': holdout, 'sufficiency': {'reference_ic': sufficiency.REFERENCE_IC, 'observations_needed': sufficiency.required_observations(), 'verdicts': verdicts},
        'specification_bars': spec, 'regimes': {'held_today': _regimes(research), 'development_period': development if development is not None else
                                                {'status': NOT_MEASURABLE, 'reason': 'no broad-market series is stored for the development period'}},
        'cross_check': check, 'provider_decision': PROVIDER_DECISION, 'provenance': provenance, 'gaps': [g for g in gaps if g],
        'limitations': ['Nothing on this page is a forecast, a ranking or a recommendation.', 'A row count is not evidence. The bars that matter are the effective observations.',
                        'Tier B says an authoritative source dates the value. It does not say Firm Lab held it at the time.'],
        'capabilities': {k: v for k, v in (research.get('capabilities') or {}).items()},
    }
    report['report_hash'] = content_hash(report)
    report['generated_at'] = now or now_utc()
    return report


def write(report, path) -> str:
    """Writes the small summary file the dashboard reads. Refuses anything that is not a readiness report."""
    if report.get('kind') != 'historical_data_readiness' or report.get('warning') != WARNING:
        raise ValueError('NOT_A_READINESS_REPORT')
    body = json.dumps(report, sort_keys=True, indent=1, allow_nan=False, default=_plain)
    Path(path).write_text(body)
    return str(path)


def _plain(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    raise TypeError(type(value).__name__)
