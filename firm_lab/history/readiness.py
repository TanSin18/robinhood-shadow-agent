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

from . import (BAR_KNOWN_AT_BASIS, BAR_KNOWN_AT_VERSION, HELD_AT_THE_TIME, POLICY_VERSION, PUBLISHER_DATED_HISTORICAL, READINESS_FILE, RETROSPECTIVE, RETURN_BASIS,
               SPLIT_ADJUSTED, TOTAL_RETURN_ADJUSTED, UNADJUSTED, WARNING, calendar, features, regimes, splits, sufficiency, targets, universe)
from .store import BAR_TABLE, HistoryStore, content_hash, now_utc, refuse_private_location

REPORT_VERSION = 'historical-data-readiness-v1'
MET, NOT_MET, NOT_MEASURABLE = 'MET', 'NOT_MET', 'NOT_MEASURABLE'
def provider_decision(sources) -> dict:
    """What the report can say about the provider. It can see which files are stored. It cannot see a subscription."""
    selected = {'selected_provider': 'Sharadar', 'product': 'Prices — Full History (Personal Use License)',
                'price': '$39 per month or $299 per year, read on the vendor page 2026-10-04',
                'licence': 'Personal use by a natural person. No redistribution. Raw data must be deleted within 30 days of cancelling; '
                           'models, backtest results and other derived work that cannot reproduce the data may be kept.',
                'open_question': 'The terms do not name machine learning. They list "models" among what may be kept. The operator reads and accepts the terms.',
                'not_selected': {'Massive': 'individual plans are display-use only; non-display use needs a separate licence',
                                 'Alpaca': 'history from 2016; delisted coverage not documented', 'Databento': 'daily history from 2018 or later',
                                 'Norgate': 'the updater runs on Windows only', 'EODHD / Tiingo': 'no delisting reasons or ticker-change events; delisted coverage partial'},
                'document': 'docs/firm_lab/CHECKPOINT8_PROVIDER_DECISION.md'}
    if sources:
        return {'status': 'FILES_STORED_SUBSCRIPTION_NOT_VERIFIED', 'stored_sources': list(sources),
                'statement': 'Files from ' + ', '.join(sources) + ' are stored. Whether a subscription is active is the operator\'s to confirm; this report cannot see it.',
                **selected}
    return {'status': 'OPERATOR PURCHASE DECISION REQUIRED', 'stored_sources': [], 'statement': 'No vendor file is stored. Nothing has been purchased by this system.', **selected}


def worst_rejected_share(captures):
    """The largest share of rejected rows in any one bar file. Ingesting a clean file again cannot dilute a bad one."""
    shares = [c['rows_rejected'] / c['rows_read'] for c in captures if c.get('kind') == 'bars' and c.get('rows_read')]
    return max(shares) if shares else None


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
        stock_bars = set(store.security_ids(price_table='stocks'))
        reports = [(created, payload) for _, payload, created in store.rows('history_reports') if payload.get('kind') == 'strict_count']
        stored_universes = universe.manifests(store)
        current = [m for m in stored_universes if universe.is_current(store, m)]
        stale = bool(stored_universes) and not current                  # every stored universe was built from other bars: none is shown
        counted_hashes = [r.get('universe_hash') for _, r in sorted(reports, key=lambda r: r[0])]
        # several universes can fit the stored bars (another period, another rule): the one counted last is shown, else the one built last
        ranked = sorted(current, key=lambda m: (max((k for k, h in enumerate(counted_hashes) if h == m['universe_hash']), default=-1), stored_universes.index(m)))
        chosen = {'manifest': ranked[-1] if ranked else None}
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
        listed = [sid for sid, sec in securities.items() if sec['price_table'] == 'stocks']
        spans = store.spans()
        expected = sum(calendar.position(last) - calendar.position(first) + 1 for first, last, _ in spans)
        conflicts = sum((c.get('rejections_by_reason') or {}).get('CONFLICTING_DUPLICATE', 0) for c in captures if c['kind'] == 'bars')
        return {'exists': True, 'bars': summary, 'captures': captures, 'rows_read': read, 'rows_rejected': rejected, '_proxy': proxy,
                'stock_securities_listed': len(listed), 'stock_securities_listed_with_bars': sum(1 for sid in listed if sid in with_bars),
                'sessions_expected_between_first_and_last_bar': expected, 'bars_present_between_first_and_last_bar': sum(n for _, _, n in spans),
                'conflicting_rows_rejected': conflicts, 'universes_current': len(current), 'universes_stored': len(stored_universes),
                '_cross_check': cross_check(store, securities, research_closes) if research_closes else None,
                'securities': len(securities), 'securities_with_bars': len(with_bars), 'delisted_securities': sum(1 for s in securities.values() if s['is_delisted']),
                'delisted_with_bars': sum(1 for sid in with_bars if securities.get(sid, {}).get('is_delisted')), 'last_bar_of_delisted_by_year': dict(sorted(last_by_year.items())),
                'funds': sum(1 for s in securities.values() if s['price_table'] == 'funds'), 'sources': sorted({s['source'] for s in securities.values()}),
                'actions_by_type': actions, 'index_events': index_events, 'universe': chosen['manifest'], 'universe_stale': stale,
                'stock_securities_with_bars': len(stock_bars),
                'strict_count': next((r for _, r in sorted(reports, key=lambda r: r[0], reverse=True)
                                      if chosen['manifest'] and r.get('universe_hash') == chosen['manifest']['universe_hash']), None),
                'holdout_reservation_stored': bool(reservation)}


def _bar(identity, name, target, minimum, measured, status, note=''):
    return {'id': identity, 'name': name, 'target': target, 'minimum': minimum, 'measured': measured, 'status': status, 'note': note}


def _regimes(research) -> dict:
    proxy = research.get('_proxy') or {}
    if len(proxy.get('sessions', [])) < regimes.VOL_MINIMUM_HISTORY:
        return {'status': NOT_MEASURABLE, 'reason': 'no broad-market close series of at least a year is stored'}
    found = regimes.coverage(proxy['sessions'], proxy['closes'], research.get('_decisions', ()))
    return {'status': 'DESCRIBED', 'proxy': proxy['instrument'], 'proxy_tier': RETROSPECTIVE, **found,
            'note': 'the only close series held outside the historical database; it covers the Checkpoint 7 window, not a historical training period'}


def build(research_database, history_database=None, *, now=None) -> dict:
    research = research_sources(research_database)
    history = history_sources(history_database, research.get('_closes'))
    stored = history['exists'] and history['bars']['bars'] > 0
    check = history.get('_cross_check') if stored else None
    counted = history.get('strict_count') if stored else None
    development = None
    if stored and history.get('_proxy') and counted and counted.get('development_first_sample_session'):
        # regimes are counted where development samples exist, not over the whole calendar period
        development = regimes.coverage(history['_proxy']['sessions'], history['_proxy']['closes'], research.get('_decisions', ()),
                                       first=counted['development_first_sample_session'], last=counted['development_last_sample_session'])
    regime_bar = None if development is None else all(development[key] >= value for key, value in sufficiency.REGIME_BAR.items())
    # "Training alone" (the network bar): development without the sessions the walk-forward folds need for validation.
    training = None
    if development is not None and development['sessions'] > splits.MINIMUM_FOLDS * splits.MINIMUM_FOLD_SESSIONS:
        training_last = calendar.offset(counted['development_last_sample_session'], -splits.MINIMUM_FOLDS * splits.MINIMUM_FOLD_SESSIONS)
        training = regimes.coverage(history['_proxy']['sessions'], history['_proxy']['closes'], research.get('_decisions', ()),
                                    first=counted['development_first_sample_session'], last=training_last)
    years = None if training is None or not training['sessions'] else training['sessions'] / 252.0
    strict = {str(h): 0 for h in targets.HORIZONS}
    by_segment = {str(h): {name: 0 for name in splits.SAMPLE_SEGMENTS} for h in targets.HORIZONS}
    tiers = {str(h): {HELD_AT_THE_TIME: 0, PUBLISHER_DATED_HISTORICAL: 0} for h in targets.HORIZONS}
    if counted:
        strict, tiers, by_segment = counted['strict_samples'], counted['strict_samples_by_tier'], counted['strict_samples_by_segment']
    reservation = splits.reservation()
    holdout = {'checkpoint7_holdout_reused_as_pristine': False, 'split_version': splits.SPLIT_VERSION, 'segments': reservation['segments'],
               'historical_holdout': 'RESERVED_NO_DATA_YET' if not stored else 'RESERVED_SEALED',
               'forward_holdout': 'RESERVED_NO_DATA_YET' if not stored else 'RESERVED_SEALED_ACCUMULATING',
               'reservation_stored_in_database': bool(history.get('holdout_reservation_stored')), 'rules': reservation['rules'],
               'label_values_readable_in': reservation['label_values_readable_in'],
               'purge_sessions': reservation['purge_sessions'], 'document': 'docs/firm_lab/CHECKPOINT8_HOLDOUT_DESIGN.md'}
    verdicts = {}
    if counted and counted.get('effective'):
        longest = counted['effective'][str(targets.MAX_HORIZON)]
        for h in ('5', '20'):
            m = counted['effective'][h]
            verdicts[h] = {}
            for f in sufficiency.FAMILIES:
                used = longest if f in sufficiency.E_AT_LONGEST_HORIZON else m      # one head per horizon: judged on the fewest observations any head has
                verdicts[h][f] = sufficiency.family_verdict(
                    f, e_train=used['effective_observations_development'], development_ic=used['detectable_ic_development'], holdout_ic=used['detectable_ic_holdout'],
                    regimes_met=bool(regime_bar), bear_markets_in_training=training['bear_markets'] if training else 0, training_years=years or 0.0,
                    sequence_share=counted.get('sequence_share'))
    else:
        verdicts = {h: sufficiency.no_data_verdicts() for h in ('5', '20')}
    bars = history['bars'] if stored else {}
    rejected = worst_rejected_share(history['captures']) if stored else None
    fundamentals, earnings, macro = research.get('fundamentals') or {}, research.get('earnings') or {}, research.get('macro') or {}
    held = research.get('closes_held') or {}
    members = (history.get('universe') or {}).get('member_count_max') if stored else None
    distinct = history.get('stock_securities_with_bars', 0) if stored else 0
    manifest = (history.get('universe') or {}) if stored else {}
    from_minimum = (manifest.get('first_formation_with_members') or {}).get(str(sufficiency.HISTORY['minimum_members']))
    effective = (counted or {}).get('effective') or {}
    horizons = [str(h) for h in targets.HORIZONS]
    e_dev = {h: effective[h]['effective_observations_development'] for h in horizons} if effective else None
    ic_dev = {h: effective[h]['detectable_ic_development'] for h in horizons} if effective else None
    ic_hold = {h: effective[h]['detectable_ic_holdout'] for h in horizons} if effective else None
    largest_smallest = max(v[1] for v in sufficiency.FAMILIES.values())
    known = lambda values: values is not None and all(v is not None for v in values.values())
    rounded = lambda values, digits: None if values is None else {h: None if v is None else round(v, digits) for h, v in values.items()}
    sessions_counted = (counted or {}).get('unique_sample_sessions')
    median_sessions = (counted or {}).get('sample_sessions_per_instrument_median')
    by_year = manifest.get('member_count_min_by_year') or {}
    complete = (counted or {}).get('member_bars_present_share')
    touched = (counted or {}).get('rows_reading_a_coarse_print')
    listed, listed_with = history.get('stock_securities_listed', 0), history.get('stock_securities_listed_with_bars', 0)
    expected, present_bars = history.get('sessions_expected_between_first_and_last_bar', 0), history.get('bars_present_between_first_and_last_bar', 0)
    not_built = 'this measurement is not built yet; the bar cannot be met until it is'
    # E1, E2, E3, F1 and F2 are coverage shares against the historical universe. Until the collectors have been run for
    # that universe there is nothing to divide by, so they are not met; the number shown is what is stored today.
    spec = [
        _bar('H1', 'Years of daily history', 'from 1998-01', 'from 2005-01', from_minimum if stored else None,
             MET if from_minimum and from_minimum[:7] <= sufficiency.HISTORY['minimum_first_session'][:7] else NOT_MET,
             f'the first month-end at which the universe holds at least {sufficiency.HISTORY["minimum_members"]} members; one early bar of one security is not a history'),
        _bar('H2', 'Unique sessions with samples', 'about 7,230', 'about 5,470', sessions_counted if stored else None,
             MET if sessions_counted and sessions_counted >= 5470 else NOT_MET,
             'sessions that have at least one strict sample with a 20-session label; purge and burn-in sessions are not among them'),
        _bar('H3', 'Instruments per reconstitution', 1000, 500, manifest.get('member_count_min') if stored else None,
             MET if manifest and manifest['member_count_min'] >= sufficiency.HISTORY['minimum_members'] else NOT_MET),
        _bar('H4', 'Distinct securities over the history, delisted included', 'counted', 'at least twice the members per reconstitution, and delisted ones among them',
             {'securities_with_bars': distinct, 'delisted_with_bars': history.get('delisted_with_bars', 0) if stored else 0},
             MET if stored and members and distinct >= 2 * members and history['delisted_with_bars'] > 0 else NOT_MET,
             'a universe that never loses a member is a survivor list'),
        _bar('H5', 'Sectors', '11 groups, 20 names each', 'reported', None, NOT_MEASURABLE, 'no historical sector classification is stored'),
        _bar('H6', 'Regimes inside training plus development', '2 bear markets, 4 corrections, rising and falling rates, 3 high-volatility episodes', 'the same',
             None if development is None else {key: development[key] for key in sufficiency.REGIME_BAR},
             (MET if regime_bar else NOT_MET) if development is not None else NOT_MEASURABLE if stored else NOT_MET,
             'counted on a stored broad-market fund over the sessions that have development samples; rate periods need the full record of policy decisions'),
        _bar('P1', 'Strict point-in-time samples in development (tier B, 20-session label)', 'reported', 'more than 0',
             by_segment[str(targets.MAX_HORIZON)][splits.DEVELOPMENT], MET if by_segment[str(targets.MAX_HORIZON)][splits.DEVELOPMENT] > 0 else NOT_MET,
             'development is the only segment a model may learn from; the sealed holdouts are counted, never read'),
        _bar('P2', 'Effective observations in development, by horizon', '10 x the reference parameters of the family', '10 x its smallest configuration',
             rounded(e_dev, 0), MET if known(e_dev) and min(e_dev.values()) >= sufficiency.PER_PARAMETER * largest_smallest else NOT_MET,
             f'met here only when every horizon carries the largest of the smallest configurations ({largest_smallest:,} parameters); each family is judged in its own table'),
        _bar('P3', 'Smallest detectable rank correlation in development, by horizon', 'at most 0.03', 'at most 0.05', rounded(ic_dev, 4),
             MET if known(ic_dev) and max(ic_dev.values()) <= sufficiency.WEAK_IC else NOT_MET),
        _bar('P4', 'Smallest detectable rank correlation in the reserved holdout, by horizon', 'at most 0.03', 'at most 0.05', rounded(ic_hold, 4),
             MET if known(ic_hold) and max(ic_hold.values()) <= sufficiency.WEAK_IC else NOT_MET,
             'from how many labels can be built there and the breadth measured in development; no holdout value is read'),
        _bar('P5', 'Sample sessions of the median member', 'at least 500', 'the same', median_sessions if counted else None,
             MET if median_sessions and median_sessions >= 500 else NOT_MET,
             'strict samples with a 20-session label per member; every member also has 252 bars before its first sample, by construction'),
        _bar('P6', 'Members in the thinnest month of each year', 'at least 950 in every year', 'at least 900', min(by_year.values()) if by_year else None,
             MET if by_year and min(by_year.values()) >= 900 else NOT_MET, 'a member has a bar on the formation session and on 60 of the 63 before it'),
        _bar('P7', 'Non-overlapping 20-session windows per regime class', 'at least 12 in each class', 'reported if not met', None, NOT_MET, not_built),
        _bar('O1', 'Listed stock securities stored', 'every security the provider lists', 'the same',
             f'{listed_with:,} of {listed:,}' if stored else None, MET if stored and listed and listed_with == listed else NOT_MET),
        _bar('O2', 'Bars on the sessions between each security\'s first and last bar', 'every session', 'the same',
             f'{present_bars / expected:.3%}' if stored and expected else None, MET if stored and expected and present_bars == expected else NOT_MET,
             'a session without a bar is left empty, never filled'),
        _bar('O3', 'Bars present on member sessions', 'at least 99.5%', 'at least 99.0%', None if complete is None else f'{complete:.3%}',
             MET if complete is not None and complete >= sufficiency.COVERAGE['bars_complete_minimum'] else NOT_MET,
             'counted between each member\'s first and last stored bar; sessions after its bars stop are not expected'),
        _bar('O4', 'Rejected bar rows, worst file', 'at most 0.1%', 'at most 0.5%', None if rejected is None else f'{rejected:.3%}',
             NOT_MET if rejected is None else MET if rejected <= sufficiency.COVERAGE['rejected_minimum'] else NOT_MET,
             'the largest share in any one bar file, so ingesting a clean file again cannot dilute a bad one'),
        _bar('O5', 'Conflicting rows for one security and session', '0', '0', history.get('conflicting_rows_rejected') if stored else None,
             MET if stored and history.get('conflicting_rows_rejected') == 0 else NOT_MET, 'both rows of a conflict are rejected; neither is stored as a bar'),
        _bar('O6', 'Independent cross-check of closes', 'every overlap agrees', '99.5% agree',
             None if not check or not check['compared'] else f'{check["share_agreeing"]:.3%} of {check["compared"]:,}',
             NOT_MET if not check or not check['compared'] else MET if check['share_agreeing'] >= sufficiency.COVERAGE['cross_check_minimum'] else NOT_MET,
             'compares stored closes with the closes Firm Lab already holds from the registered read path, one instrument and session at a time'),
        _bar('O7', 'Print precision of adjusted prices', 'at most 1% of member rows coarser than 0.05% of price', 'at most 5%',
             None if not counted or counted.get('coarse_print_share') is None else f'{counted["coarse_print_share"]:.3%}',
             NOT_MET if not counted or counted.get('coarse_print_share') is None
             else MET if counted['coarse_print_share'] <= sufficiency.COVERAGE['coarse_print_minimum'] else NOT_MET,
             'features that read a high, low or open are used for every row or for none: '
             + ('no row reads a coarsely printed bar, so they are usable' if counted and counted.get('high_low_open_families_usable')
                else f'{touched:,} rows would read a coarsely printed bar, so they are withheld from every row' if touched
                else 'not decided until rows are counted') + '; close-based features use the unadjusted close and are not affected'),
        _bar('E1', 'Earnings events with acceptance time', '80% of member-quarters from 2010', '60%', earnings.get('events'), NOT_MET,
             f'{earnings.get("events") or 0} events of {earnings.get("companies") or 0} companies are stored; coverage of a historical universe is not measured'),
        _bar('E2', 'Periodic filings with acceptance time', '90% of member periods from 2011', '75%', fundamentals.get('filings'), NOT_MET,
             f'{fundamentals.get("filings") or 0} filings of {fundamentals.get("companies") or 0} companies are stored; coverage of a historical universe is not measured'),
        _bar('E3', 'Macro releases, first-published value and official time', '98% of scheduled releases', '95%',
             sum(v['observations'] for v in macro.get('series', {}).values()), NOT_MET,
             'stored series: ' + (', '.join(sorted(macro.get('series', {}))) or 'none') + '; coverage of the scheduled releases of the period is not measured'),
        _bar('F1', 'Filings whose required fields resolve', '70% of the filings counted in E2', 'reported', fundamentals.get('facts'), NOT_MET,
             f'{fundamentals.get("facts") or 0} facts are stored; the share of a historical universe\'s filings is not measured'),
        _bar('F2', 'Restatement history', 'every reporting filing kept in acceptance order; one real restatement shown', 'the same',
             fundamentals.get('restatements'), NOT_MET,
             f'versions are stored and tested on synthetic filings; {fundamentals.get("restatements") or 0} real restatements are stored'),
    ]
    provenance = [
        {'name': 'Historical daily OHLCV', 'provider': ', '.join(history.get('sources', [])) if stored else 'none stored',
         'date_range': [bars.get('first_session'), bars.get('last_session')] if stored else None, 'version': POLICY_VERSION,
         'known_at_methodology': f'{BAR_KNOWN_AT_VERSION}: a bar is usable no earlier than the open of the next exchange session ({BAR_KNOWN_AT_BASIS}); '
                                 'the time Firm Lab received it is stored separately',
         'adjustment_basis': f'open, high, low, close, volume: {SPLIT_ADJUSTED}; unadjusted close: {UNADJUSTED}; total-return close: {TOTAL_RETURN_ADJUSTED} (read only to size a recorded distribution)',
         'pit_eligibility': PUBLISHER_DATED_HISTORICAL if stored else None,
         'limitations': ['No source gives the time a historical bar was first published; the next open is a bound, not a measurement.',
                         'The vendor re-adjusts past prices after a split and may correct past prints; versioned captures record every change.',
                         'Reprinted adjusted prices are rounded. Close-based features use the unadjusted close and confirmed split ratios instead; features that read a '
                         'high, low or open are used for every row of a dataset or for none, and for none once any row would read a print coarser than 0.05% of price.',
                         'No post-delisting return exists: a label that ends at a bankruptcy or regulatory delisting overstates what a holder recovered.']},
        {'name': 'Closes already held', 'provider': (research.get('closes_held') or {}).get('source'),
         'date_range': [(research.get('closes_held') or {}).get('first_session'), (research.get('closes_held') or {}).get('last_session')], 'version': 'Checkpoint 2 capture',
         'known_at_methodology': (research.get('closes_held') or {}).get('known_at_methodology'), 'adjustment_basis': 'split-adjusted closes as the read path reported them',
         'pit_eligibility': RETROSPECTIVE, 'limitations': ['Close only.', f'{held.get("instruments") or 0} instruments chosen today: a survivor list.',
                                                             'This is the burned Checkpoint 7 window.']},
        {'name': 'Fundamentals', 'provider': 'SEC EDGAR', 'date_range': [(research.get('fundamentals') or {}).get('first_acceptance'), (research.get('fundamentals') or {}).get('last_acceptance')],
         'version': (research.get('fundamentals') or {}).get('version'), 'known_at_methodology': (research.get('fundamentals') or {}).get('known_at_methodology'),
         'adjustment_basis': 'as filed; a later filing never replaces an earlier value', 'pit_eligibility': (research.get('fundamentals') or {}).get('tier'),
         'limitations': [f'{fundamentals.get("companies") or 0} companies, {fundamentals.get("filings") or 0} filings: a sample, not a history.',
                         'XBRL exists from 2009 to 2011 onward only.', 'The reader takes recent filings of companies listed today; a history needs a reader keyed by CIK.']},
        {'name': 'Earnings events', 'provider': 'SEC EDGAR', 'date_range': [(research.get('earnings') or {}).get('first_acceptance'), (research.get('earnings') or {}).get('last_acceptance')],
         'version': (research.get('earnings') or {}).get('version'), 'known_at_methodology': (research.get('earnings') or {}).get('known_at_methodology'),
         'adjustment_basis': 'not applicable', 'pit_eligibility': (research.get('earnings') or {}).get('tier'),
         'limitations': [f'{earnings.get("events") or 0} events of {earnings.get("companies") or 0} companies: a sample, not a history.',
                         'No consensus estimate, so no surprise.', 'No transcript.']},
        {'name': 'Macro', 'provider': (research.get('macro') or {}).get('source'), 'date_range': None, 'version': (research.get('macro') or {}).get('version'),
         'known_at_methodology': (research.get('macro') or {}).get('known_at_methodology'), 'adjustment_basis': 'as first published; revisions are later rows',
         'pit_eligibility': (research.get('macro') or {}).get('tier'),
         'limitations': ['Stored series: ' + (', '.join(sorted(macro.get('series', {}))) or 'none') + '.', 'CPI, labor and Treasury yields are not stored.',
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
            'Fundamentals and earnings history: a small sample only; a reader keyed by CIK must be built and run for the historical universe.',
            'Post-delisting returns: no source.',
            'Intraday history: deferred; not needed before a daily tournament.']
    report = {
        'kind': 'historical_data_readiness', 'report_version': REPORT_VERSION, 'warning': WARNING, 'spec_version': sufficiency.SPEC_VERSION, 'policy_version': POLICY_VERSION,
        'market_data': {'status': 'STORED' if stored else 'NO_VALIDATED_HISTORICAL_BARS', 'provider': ', '.join(history.get('sources', [])) if stored else None,
                        'history_range': [bars.get('first_session'), bars.get('last_session')] if stored else None, 'securities_with_bars': history.get('securities_with_bars', 0),
                        'bars': bars.get('bars', 0), 'funds': history.get('funds', 0), 'delisted_with_bars': history.get('delisted_with_bars', 0),
                        'last_bar_of_delisted_by_year': history.get('last_bar_of_delisted_by_year', {}), 'block_versions': bars.get('block_versions', {}),
                        'rows_read': history.get('rows_read', 0), 'rows_rejected': history.get('rows_rejected', 0), 'captures': history.get('captures', []),
                        'universe_stale': bool(history.get('universe_stale')), 'universes_stored': history.get('universes_stored', 0),
                        'universes_current': history.get('universes_current', 0), 'stock_securities_with_bars': history.get('stock_securities_with_bars', 0),
                        'adjustment_basis': SPLIT_ADJUSTED, 'return_basis': RETURN_BASIS, 'known_at_version': BAR_KNOWN_AT_VERSION,
                        'closes_held': research.get('closes_held')},
        'corporate_actions': {'historical_by_type': history.get('actions_by_type', {}), 'held_rows': (research.get('corporate_actions_held') or {}).get('rows', 0),
                              'held_instruments': (research.get('corporate_actions_held') or {}).get('instruments', 0),
                              'held_benchmark_only_rows': (research.get('corporate_actions_held') or {}).get('benchmark_only_rows', 0),
                              'index_events': history.get('index_events', 0)},
        'universe': history.get('universe') if stored else None,
        'feature_versions': {'feature_set_version': features.FEATURE_SET_VERSION, 'versions': sorted({d['version'] for d in features.DEFINITIONS}),
                             'features': len(features.DEFINITIONS), 'code_hash': features.code_hash(), 'computed_on_stored_bars': bool(counted),
                             'close_based_fibonacci_preserved': True},
        'fundamentals': research.get('fundamentals'), 'earnings': research.get('earnings'), 'macro': research.get('macro'),
        'strict_training': {'strict_samples': strict, 'strict_samples_by_segment': by_segment, 'strict_samples_by_tier': tiers,
                            'bars_held_at_the_time_rows': (counted or {}).get('bars_held_at_the_time_rows', 0), 'retrospective_samples_in_this_dataset': 0,
                            'rows_not_strict_because_a_bar_was_revised': (counted or {}).get('rows_not_strict_because_a_bar_was_revised', 0),
                            'rows_reading_a_coarse_print': (counted or {}).get('rows_reading_a_coarse_print'),
                            'high_low_open_families_usable': (counted or {}).get('high_low_open_families_usable'),
                            'delisting_exits_by_year': (counted or {}).get('delisting_exits_by_year'),
                            'members_whose_bars_end_without_a_delisting_record': (counted or {}).get('members_whose_bars_end_without_a_delisting_record'),
                            'checkpoint7_retrospective_samples': 6490, 'checkpoint7_note': 'a separate close-only dataset; never added to the strict count',
                            'raw_member_rows': (counted or {}).get('raw_member_rows', 0), 'unique_sessions': (counted or {}).get('unique_sessions', 0),
                            'unique_instruments': (counted or {}).get('unique_instruments', 0), 'by_segment': (counted or {}).get('by_segment'),
                            'effective': (counted or {}).get('effective'), 'label_states': (counted or {}).get('label_states'),
                            'delisting_exits_by_reason': (counted or {}).get('delisting_exits_by_reason'), 'dataset_version': 'pit-dataset-v2',
                            'breaks_by_reason': (counted or {}).get('breaks_by_reason'), 'splits_confirmed': (counted or {}).get('splits_confirmed'),
                            'splits_unchecked': (counted or {}).get('splits_unchecked'),
                            'distributions_without_amount': (counted or {}).get('distributions_without_amount'),
                            'action_table_contradictions': (counted or {}).get('action_table_contradictions') or [],
                            'split_convention': (counted or {}).get('split_convention'), 'dividend_basis': (counted or {}).get('dividend_basis'),
                            'coarse_print_share': (counted or {}).get('coarse_print_share'),
                            'target_version': targets.TARGET_VERSION, 'dataset_spec_hash': ((counted or {}).get('manifest') or {}).get('dataset_spec_hash')},
        'holdout': holdout, 'sufficiency': {'reference_ic': sufficiency.REFERENCE_IC, 'observations_needed': sufficiency.required_observations(), 'verdicts': verdicts},
        'specification_bars': spec, 'regimes': {'held_today': _regimes(research), 'development_period': development if development is not None else
                                                {'status': NOT_MEASURABLE, 'reason': 'no broad-market series with development samples is stored'},
                                                'training_alone': training if training is not None else
                                                {'status': NOT_MEASURABLE, 'reason': 'development is shorter than the validation the walk-forward folds need, or is not stored'}},
        'cross_check': check, 'provider_decision': provider_decision(history.get('sources', []) if stored else []),
        'integrity': 'The report hash detects accidental damage to this file. It is an integrity check, not a signature: it does not prove who wrote the file.', 'provenance': provenance, 'gaps': [g for g in gaps if g],
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
    target = refuse_private_location(path)              # never the registered database, never beside it, never inside a repository
    if target.name != READINESS_FILE:
        raise ValueError('NOT_THE_READINESS_FILE')      # one name only, so this can never overwrite a database or any other file
    body = json.dumps(report, sort_keys=True, indent=1, allow_nan=False, default=_plain)
    target.write_text(body)
    return str(path)


def _plain(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    raise TypeError(type(value).__name__)
