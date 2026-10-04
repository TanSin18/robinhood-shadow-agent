"""Capability rows for the historical data foundation. Standard library only.

Each status is read off the stored readiness report; nothing is inferred. A row is AVAILABLE only when stored data
passed the bars that define it, and the evidence is recorded with the status. A row with data that does not yet meet
its bars is PARTIAL_EXISTING. A row with nothing stored is UNAVAILABLE. No row here makes anything available to a
strategy: these describe research data, and the model rows (ml_ranker and the rest) are not touched.
"""
from __future__ import annotations

from .capabilities import AVAILABLE, PARTIAL_EXISTING, UNAVAILABLE, set_status
from .history_view import problem

ROWS = ('historical_ohlcv', 'historical_universe', 'pit_fundamentals', 'pit_earnings', 'pit_macro', 'strict_pit_training_data')
HISTORY_PROVIDER = 'Firm Lab historical research database'


def _met(report, *ids) -> bool:
    bars = {b['id']: b['status'] for b in report['specification_bars']}
    return all(bars.get(i) == 'MET' for i in ids)


def statuses(report) -> dict:
    """{capability: (status, provider, detail, evidence or None)} from a readiness report. A report that is damaged,
    incomplete or not a readiness report is refused; the registry is never written from one."""
    reason = problem(report)
    if reason:
        raise ValueError(reason)
    market, strict = report['market_data'], report['strict_training']
    stored = market.get('status') == 'STORED'
    decision = report['provider_decision']
    fundamentals, earnings, macro = report.get('fundamentals') or {}, report.get('earnings') or {}, report.get('macro') or {}
    universe = report.get('universe') or {}
    samples = ((strict.get('strict_samples_by_segment') or {}).get('20') or {}).get('DEVELOPMENT', 0)      # what a model may learn from today
    at = report.get('generated_at')
    out = {}
    if not stored:
        out['historical_ohlcv'] = (UNAVAILABLE, None, 'No historical daily bars are stored. ' + decision.get('status', '') + ': ' + str(decision.get('selected_provider'))
                                   + ' ' + str(decision.get('product')) + '. Storage, validation and the new feature versions are built and tested on synthetic files only.', None)
    else:
        good = _met(report, 'H1', 'O4', 'O6')
        detail = (f'{market["bars"]:,} daily bars stored (each passed the row checks) for {market["securities_with_bars"]:,} securities, {market["history_range"][0]} to {market["history_range"][1]}; '
                  f'{market["delisted_with_bars"]:,} delisted. Split-adjusted price basis; a bar is usable from the next session open. '
                  + ('' if good else 'Not every bar of the sufficiency specification is met (history start, rejected rows, independent cross-check).'))
        out['historical_ohlcv'] = (AVAILABLE if good else PARTIAL_EXISTING, market.get('provider'), detail,
                                   {'provider': market.get('provider'), 'records': market['bars'], 'validation_passed': True, 'validated_at': at} if good else None)
    if stored and universe:
        good = _met(report, 'H3', 'H4')
        out['historical_universe'] = (AVAILABLE if good else PARTIAL_EXISTING, HISTORY_PROVIDER,
                                      f'{universe["universe_version"]}: {universe["formation_sessions"]} monthly formations, {universe["distinct_members"]:,} distinct members, '
                                      f'{universe["members_later_delisted"]:,} later delisted. Formed only from bars before each formation; no present-day list or classification.',
                                      {'provider': HISTORY_PROVIDER, 'records': universe['formation_sessions'], 'validation_passed': True, 'validated_at': at} if good else None)
    else:
        out['historical_universe'] = (UNAVAILABLE, None, 'No historical universe is stored: it is formed from stored bars, and none are stored. The rule '
                                                         '(monthly liquidity screen from past bars only, delisted securities included) is defined and tested.', None)
    facts = fundamentals.get('facts') or 0
    out['pit_fundamentals'] = ((PARTIAL_EXISTING if facts else UNAVAILABLE), 'SEC EDGAR' if facts else None,
                               (f'{facts:,} facts from {fundamentals.get("filings")} filings of {fundamentals.get("companies")} companies, each dated by the SEC acceptance time of '
                                'the filing that reported it. A sample, not a history: the collectors have not been run for a historical universe.') if facts
                               else 'No point-in-time fundamental fact is stored.', None)
    events = earnings.get('events') or 0
    out['pit_earnings'] = ((PARTIAL_EXISTING if events else UNAVAILABLE), 'SEC EDGAR' if events else None,
                           (f'{events:,} earnings-release filings of {earnings.get("companies")} companies with SEC acceptance times. No consensus estimate, no surprise, '
                            'no transcript. A sample, not a history.') if events else 'No earnings event is stored.', None)
    series = macro.get('series') or {}
    out['pit_macro'] = ((PARTIAL_EXISTING if series else UNAVAILABLE), macro.get('source') if series else None,
                        ('First-published values with official release times for: ' + ', '.join(sorted(series)) + '. CPI, labor and Treasury yields are not stored. '
                         'FRED and ALFRED are not used: their terms prohibit storing the data and using it to train models without written consent.') if series
                        else 'No macro release is stored.', None)
    tiers = (strict.get('strict_samples_by_tier') or {}).get('20') or {}
    every = (strict.get('strict_samples') or {}).get('20') or 0
    if samples and out['historical_ohlcv'][0] == AVAILABLE and out['historical_universe'][0] == AVAILABLE:
        state = AVAILABLE
    else:
        state = PARTIAL_EXISTING if samples else UNAVAILABLE
    out['strict_pit_training_data'] = (state, HISTORY_PROVIDER if samples else None,
                                       (f'{samples:,} strict point-in-time samples in the development period with a 20-session label. Across all four sample '
                                        f'segments there are {every:,}: held at the time {tiers.get("HELD_AT_THE_TIME", 0):,}; publisher-dated historical '
                                        f'{tiers.get("PUBLISHER_DATED_HISTORICAL", 0):,}. Both holdouts are sealed: their rows are counted, never read. '
                                        'Sufficiency per model family is reported separately; a count is not sufficiency. ')
                                       if samples else '0 strict point-in-time samples. The 6,490 retrospective samples of the modeling laboratory are a separate dataset and are '
                                                       'not counted. Both holdouts are reserved and sealed.',
                                       {'provider': HISTORY_PROVIDER, 'records': samples, 'validation_passed': True, 'validated_at': at} if state == AVAILABLE else None)
    return out


def record(store, report, *, now=None) -> dict:
    """Writes the rows from a readiness report. Returns {capability: status}. Touches no other row."""
    rows = statuses(report)
    for name, (status, provider, detail, evidence) in rows.items():
        set_status(store, name, status, provider, detail, now, evidence=evidence, reason='Checkpoint 8 historical data readiness ' + str(report.get('report_hash', ''))[:12])
    return {name: row[0] for name, row in rows.items()}
