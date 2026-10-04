"""Dataset contract v2 for a future tournament, and the honest count of what it can hold today.

``pit-dataset-v2``. A row is (security, session T). It is a strict point-in-time sample only when all of these hold:

* the security is a member of the stored historical universe on T (membership formed from bars before it took effect);
* it has a bar on T and at least 252 bars of history, and the core features are available at T;
* every input is tier A (Firm Lab held it before the next session opened) or tier B (a publisher-dated historical bar);
* its label at the horizon exists (``targets``): entry at the close of T+1, never a price at or before T.

Tiers. The row's tier is the lowest among its bars, its universe membership and its label. A bar counts as held at the
time only if the value read today was stored, by this machine's clock, before the next session opened. A bar whose
value the vendor changed after it was first stored is a restated value: a row that reads it, in a feature or in its
label, is tier C and is not a strict sample. A universe formed from an archive is tier B, so every strict row built
today is tier B. Tier A needs forward capture of the bars and a universe formed from bars held at the time, and nothing
does that yet. The Checkpoint 7 retrospective samples are a different dataset and are never added to these counts.

What a row reads. Its features read its last 253 bars, and further back where the pivot or leg it stands on began
earlier; its label reads the bars from T+1 to its exit. The tier follows exactly those bars.

Sealed segments (``splits``). Nothing of a segment that may not be read leaves ``security_rows``: no label value and
no feature value of the historical holdout, the forward holdout, a purge or the burn-in. Only whether a row and its
label can be built is counted, which reads dates and bar existence. A readable row never reads a sealed price either:
the features of a row on or after the first burned session are computed from bars on or after that session only, so
the burned window carries nothing of the historical holdout that ends the session before it. (Universe membership in
the first months of the burned window does read the holdout's last bars, as one yes-or-no per security and month.)
The raw store itself is not sealed; the seal is on what this builder hands out.

High, low, open and volume. A vendor reprints adjusted prices and volumes after every later split, and the reprint can
be too coarse to give the shape of a bar or the size of a volume. Withholding those features only where the reprint is
coarse would mark the rows of stocks that split later, which is information from the future. So the features that read
a high, low or open are used for every row of a dataset or for none, and so are the features that read volume: for
none as soon as one row of the dataset would read a bar the reprint made unreadable. Whether a row exists at all is
decided from the exact close only.

Every dataset names the stored blocks, captures, universe, feature code, target and split it was built from, and has
one hash over all of that. The same inputs give the same hash.
"""
from __future__ import annotations

import hashlib

import numpy as np

from . import (BAR_KNOWN_AT_VERSION, HELD_AT_THE_TIME, POLICY_VERSION, PUBLISHER_DATED_HISTORICAL, RETROSPECTIVE, RETURN_BASIS, lowest_tier, adjust, calendar, features,
               panel as panels, splits, sufficiency, targets, universe)
from .ingest import current_securities
from .store import content_hash, when

DATASET_VERSION = 'pit-dataset-v2'
MINIMUM_HISTORY_BARS = 252
CORE_FEATURES = ('return20', 'realized_vol20')                # from the exact close only: whether a row exists must not depend on anything the vendor reprints
INPUT_WINDOW_BARS = features.LONGEST_FIXED_LOOKBACK            # 253: the 252-session return reads the bar 252 sessions back and the row's own
STRICT_TIERS = (HELD_AT_THE_TIME, PUBLISHER_DATED_HISTORICAL)
FEATURES_FROM = splits.BURNED_FIRST                            # a row on or after this session reads no bar before it: the session before is sealed
SEGMENTS = (splits.BURN_IN, splits.DEVELOPMENT, splits.PURGED, splits.HISTORICAL_HOLDOUT, splits.BURNED, splits.FORWARD_HOLDOUT)
_ELIGIBLE = {}


def _eligible_from(session) -> str:
    if session not in _ELIGIBLE:
        _ELIGIBLE[session] = calendar.eligible_from(session)
    return _ELIGIBLE[session]


def _actions_by_security(store, source=None) -> dict:
    out = {}
    for _, payload, _ in store.rows('history_actions'):
        if source is None or payload['source'] == source:
            out.setdefault(payload['security_id'], []).append(payload)
    return out


def _window_sum(flags, start, end) -> np.ndarray:
    """How many flags are set in [start[t], end[t]] for every t."""
    total = np.concatenate([[0], np.cumsum(flags)])
    return total[end + 1] - total[start]


def row_tiers(sessions, present, history, *, oldest=None, label_reach=targets.MAX_HORIZON + 1) -> np.ndarray:
    """The tier each session's row can claim from its bars alone. ``history`` is ``HistoryStore.bar_history``.

    A  every bar the row's features read was stored by this machine's clock before the next session opened, and none
       was changed afterwards. The row reads its last 253 bars, and further back where ``oldest`` says so.
    C  a bar the row reads, or a bar its longest label reads, was changed by the vendor after it was first stored, or
       was taken out by the vendor (the hole it left is the vendor's later doing, not the market's).
    B  otherwise: a publisher-dated historical bar."""
    count = len(sessions)
    if not count:
        return np.zeros(0, dtype=object)
    since, clock, revised = history['since'], history['clock'], history['revised']
    present = np.asarray(present, bool)
    held = np.zeros(count, bool)
    for t, s in enumerate(sessions):
        stamp = since.get(s)
        # a bar cannot be stored before its session closes, so only a time on the days up to the next open can qualify
        if stamp is not None and clock.get(s) == 'SYSTEM' and s <= stamp[:10] <= _eligible_from(s)[:10]:
            held[t] = when(stamp) <= when(_eligible_from(s))
    removed = history.get('removed') or ()
    changed = present & np.array([s in revised for s in sessions], bool) if revised else np.zeros(count, bool)
    if removed:
        changed = changed | np.array([s in removed for s in sessions], bool)
    t = np.arange(count)
    start = np.maximum(t - INPUT_WINDOW_BARS + 1, 0)
    if oldest is not None:
        start = np.minimum(start, np.asarray(oldest, int)).clip(0)
    bars = _window_sum(present, start, t)
    all_held = (_window_sum(present & ~held, start, t) == 0) & (bars >= INPUT_WINDOW_BARS)
    restated = _window_sum(changed, start, np.minimum(t + label_reach, count - 1)) > 0
    return np.where(restated, RETROSPECTIVE, np.where(all_held, HELD_AT_THE_TIME, PUBLISHER_DATED_HISTORICAL)).astype(object)


def row_tier(*tiers) -> str:
    """The tier of a row from the tiers of its parts: the lowest."""
    return lowest_tier(tiers)


def _tail(panel, k0) -> dict:
    """The panel from slot k0 on: what a row on or after that session is allowed to read."""
    out = {name: (value[k0:] if isinstance(value, np.ndarray) else value) for name, value in panel.items()}
    out['sessions'] = panel['sessions'][k0:]
    return out


def security_rows(store, sid, security, spans, actions, *, source=None, membership_tier=PUBLISHER_DATED_HISTORICAL, data_end=None) -> dict:
    """Everything one security contributes: per session, its features, whether the row is eligible, its tier, its segment
    and its labels. Label values and feature values are returned only for a segment that may be read (development and the
    burned window); for every other segment both are removed before anything leaves this function, and ``eligible`` and
    the label states say only whether they could be built. ``security`` is the master row and is not read: nothing about
    a past row depends on what the master says today. ``data_end`` is the last session stored for any security."""
    p = panels.load(store, sid, source=source)
    sessions = p['sessions']
    count = len(sessions)
    audit = adjust.breaks(p, actions)
    mask = adjust.break_mask(p, audit['breaks'])
    computed = features.compute(p, mask, splits=audit['splits'])
    values = {name: np.array(array, float) for name, array in computed['values'].items()}
    oldest = np.array(computed['oldest_bar_read'], int)
    k0 = panels.first_session_on_or_after(p, FEATURES_FROM) if count else None
    if k0:                                                              # rows after the sealed holdout: computed from their own side of the boundary only
        tail = _tail(p, k0)
        later = [a for a in actions if str(a['effective_date'])[:10] >= sessions[k0]]
        tail_audit = adjust.breaks(tail, later)
        again = features.compute(tail, adjust.break_mask(tail, tail_audit['breaks']), splits=tail_audit['splits'])
        for name in values:
            values[name][k0:] = again['values'][name]
        oldest[k0:] = again['oldest_bar_read'] + k0
    member = universe.member_mask(sessions, spans)
    history = np.cumsum(p['present'])
    core = np.all([np.isfinite(values[name]) for name in CORE_FEATURES], axis=0) if count else np.zeros(0, bool)
    eligible = member & p['present'] & (history >= MINIMUM_HISTORY_BARS) & core
    bar_tier = row_tiers(sessions, p['present'], store.bar_history(sid, source=source), oldest=oldest)
    tier = np.array([row_tier(t, membership_tier) for t in bar_tier], dtype=object) if count else np.zeros(0, dtype=object)
    segment = np.array([splits.segment(s) for s in sessions], dtype=object) if count else np.zeros(0, dtype=object)
    delisting = targets.delisted_at_last_bar(p, actions, data_end)
    labels = targets.build(p, mask, delisted=delisting, splits=audit['splits'])
    readable = np.array([splits.labels_allowed(name) for name in segment], bool) if count else np.zeros(0, bool)
    coarse = adjust.coarse_print(p)
    reads_coarse = _window_sum(coarse, oldest.clip(0, max(count - 1, 0)), np.arange(count)) > 0 if count else np.zeros(0, bool)
    thin = adjust.coarse_volume(p, audit['splits'])
    t = np.arange(count)
    floor = np.where(t >= (k0 or 0), k0 or 0, 0)                       # a row past the sealed holdout reads no bar before its own side
    reads_thin = _window_sum(thin, np.maximum(t - features.LONGEST_VOLUME_LOOKBACK + 1, floor), t) > 0 if count else np.zeros(0, bool)
    for h in labels:
        labels[h]['value'] = np.where(readable, labels[h]['value'], np.nan)        # sealed, purge and burn-in label values never leave this function
    for name in values:
        values[name] = np.where(readable, values[name], np.nan)                    # nor do their features: a price series is its own label
    # A break is returned as where and why. Its size is a price move, and for a sealed session that is not handed out.
    found = [{'session': b['session'], 'index': b['index'], 'reason': b['reason']} for b in audit['breaks']]
    return {'security_id': sid, 'sessions': sessions, 'present': p['present'], 'member': member, 'eligible': eligible, 'tier': tier, 'bar_tier': bar_tier,
            'segment': segment, 'coarse': coarse, 'reads_coarse': reads_coarse, 'reads_unreadable_volume': reads_thin, 'delisting': delisting,
            'features': values, 'labels': labels, 'breaks': found, 'blocks': p['blocks'],
            'audit': {**{k: v for k, v in audit.items() if k != 'breaks'}, 'structure': computed['audit']}, 'history_bars': history}


def contradictions(split_convention, dividend_basis) -> list:
    """What the visible cases say against the two readings of the action table that every decision rests on (a split's
    value is new shares per old share; a dividend's value is the amount paid per share on the day). Empty when nothing
    speaks against them. A dataset is not built while this is not empty: the adapter has to be corrected first."""
    found = []
    if split_convention.get('old_per_new'):
        found.append('SPLIT_VALUE_CONVENTION_CONTRADICTED')
    if dividend_basis.get('adjusted'):
        found.append('DIVIDEND_AMOUNT_BASIS_CONTRADICTED')
    return found


def _sources(store) -> list:
    return sorted(({'capture_id': p['capture_id'], 'kind': p['kind'], 'source': p['source'], 'sha256': p['sha256'], 'adapter': p['adapter']}
                   for _, p, _ in store.rows('history_captures')), key=lambda c: (c['kind'], c['sha256'], c['capture_id']))


def count(store, *, universe_hash=None, source=None, progress=None) -> dict:
    """The strict point-in-time sample count and the quantities of the sufficiency specification. Fits nothing. Refuses
    a universe that was built from bars or actions other than the ones stored now."""
    if not any(p.get('kind') == 'universe_manifest' for _, p, _ in store.rows('history_universe')):
        return {'dataset_version': DATASET_VERSION, 'universe': None, 'raw_member_rows': 0, 'strict_samples': {str(h): 0 for h in targets.HORIZONS},
                'strict_samples_by_segment': {str(h): {name: 0 for name in splits.SAMPLE_SEGMENTS} for h in targets.HORIZONS},
                'retrospective_samples': 0, 'reason': 'NO_STORED_UNIVERSE'}
    chosen = universe.load(store, universe_hash, require_current=True)
    spans = universe.membership(chosen['records'])
    securities = current_securities(store, source=source)
    actions = _actions_by_security(store, source)
    every = calendar.sessions(splits.FIRST_SAMPLE, splits.development_last())
    dev_position = {s: k for k, s in enumerate(every)}
    hold = calendar.sessions(splits.HOLDOUT_FIRST, splits.holdout_last_sample())
    hold_position = {s: k for k, s in enumerate(hold)}
    last_stored = store.bar_summary()['last_session']
    out = {'dataset_version': DATASET_VERSION, 'universe_hash': chosen['manifest']['universe_hash'], 'raw_member_rows': 0, 'eligible_feature_rows': 0,
           'by_segment': {s: {'eligible_feature_rows': 0, 'sessions': set(), 'instruments': set(), **{f'labelled_{h}': 0 for h in targets.HORIZONS}} for s in SEGMENTS},
           'strict_samples_by_tier': {str(h): {HELD_AT_THE_TIME: 0, PUBLISHER_DATED_HISTORICAL: 0} for h in targets.HORIZONS},
           'rows_not_strict_because_a_bar_was_revised': 0, 'bars_held_at_the_time_rows': 0, 'member_sessions': 0, 'by_year': {},
           'label_states': {str(h): {} for h in targets.HORIZONS}, 'delisting_exits_by_reason': {}, 'delisting_exits_by_year': {},
           'members_whose_bars_end_without_a_delisting_record': 0, 'breaks_by_reason': {}, 'splits_confirmed': 0,
           'split_convention': {'new_per_old': 0, 'old_per_new': 0},
           'dividend_basis': {'unadjusted': 0, 'adjusted': 0, 'neither': 0, 'no_total_return_factor': 0}, 'coarse_print_rows': 0, 'rows_reading_a_coarse_print': 0,
           'rows_reading_an_unreadable_volume': 0,
           'sample_sessions_per_instrument': [], 'sequence_ready': 0, 'splits_unchecked': 0, 'distributions_without_amount': 0}
    sample_sessions = set()                                             # sessions with at least one strict sample at the longest horizon
    tables = {h: {} for h in targets.HORIZONS}                           # horizon -> {security: {development window index: raw label}}
    totals = {h: {} for h in targets.HORIZONS}                           # horizon -> {window index: [sum, count]} for the cross-sectional mean
    hold_counts = {h: {} for h in targets.HORIZONS}                      # horizon -> {holdout window index: how many labels can be built}; a count, never a value
    for n, sid in enumerate(sorted(spans)):
        rows = security_rows(store, sid, securities.get(sid), spans[sid], actions.get(sid, []), source=source, data_end=last_stored)
        sessions, segment = rows['sessions'], rows['segment']
        restated = rows['eligible'] & (rows['tier'] == RETROSPECTIVE)
        out['rows_not_strict_because_a_bar_was_revised'] += int(restated.sum())
        eligible = rows['eligible'] & ~restated                          # a row that reads a restated bar is tier C: not a strict sample
        out['raw_member_rows'] += int((rows['member'] & rows['present']).sum())
        out['member_sessions'] += int(rows['member'].sum())
        out['eligible_feature_rows'] += int(eligible.sum())
        out['rows_reading_a_coarse_print'] += int((eligible & rows['reads_coarse']).sum())
        out['rows_reading_an_unreadable_volume'] += int((eligible & rows['reads_unreadable_volume']).sum())
        out['splits_confirmed'] += rows['audit']['splits_confirmed']
        out['splits_unchecked'] += rows['audit']['splits_unchecked']
        out['distributions_without_amount'] += rows['audit']['distributions_without_amount']
        own_samples = 0
        for key, value in rows['audit']['split_convention'].items():
            out['split_convention'][key] += value
        for key, value in rows['audit']['dividend_basis'].items():
            out['dividend_basis'][key] += value
        out['coarse_print_rows'] += int((eligible & rows['coarse']).sum())
        for b in rows['breaks']:
            out['breaks_by_reason'][b['reason']] = out['breaks_by_reason'].get(b['reason'], 0) + 1
        index = np.flatnonzero(eligible)
        run = 0
        for t in range(len(sessions)):
            run = run + 1 if eligible[t] else 0
            out['sequence_ready'] += int(run >= sufficiency.NETWORK_BAR['sequence_sessions'])
        reason = rows['delisting'] or 'NOT_RECORDED'
        if rows['delisting'] is None and sessions and last_stored and sessions[-1] < calendar.offset(last_stored, -(targets.MAX_HORIZON + 1)):
            out['members_whose_bars_end_without_a_delisting_record'] += 1       # their last labels are not built; the failures among them are missing
        for t in index:
            s, name = sessions[t], segment[t]
            part = out['by_segment'][name]
            part['eligible_feature_rows'] += 1
            part['sessions'].add(s)
            part['instruments'].add(sid)
            sample = name in splits.SAMPLE_SEGMENTS
            out['bars_held_at_the_time_rows'] += int(sample and rows['bar_tier'][t] == HELD_AT_THE_TIME)
            year = out['by_year'].setdefault(s[:4], {'eligible_feature_rows': 0, 'instruments': set()})
            year['eligible_feature_rows'] += 1
            year['instruments'].add(sid)
            for h in targets.HORIZONS:
                state = int(rows['labels'][h]['state'][t])
                text = targets.REASONS[state]
                out['label_states'][str(h)][text] = out['label_states'][str(h)].get(text, 0) + 1
                if state in (targets.OK, targets.DELISTED_EXIT):
                    part[f'labelled_{h}'] += 1
                    if sample:
                        out['strict_samples_by_tier'][str(h)][rows['tier'][t]] += 1
                        if h == targets.MAX_HORIZON:
                            own_samples += 1
                            sample_sessions.add(s)
                    if state == targets.DELISTED_EXIT and h == targets.MAX_HORIZON:
                        out['delisting_exits_by_reason'][reason] = out['delisting_exits_by_reason'].get(reason, 0) + 1
                        by_year = out['delisting_exits_by_year'].setdefault(s[:4], {})
                        by_year[reason] = by_year.get(reason, 0) + 1
                    k = dev_position.get(s)
                    if name == splits.DEVELOPMENT and k is not None and k % h == 0:      # non-overlapping windows, development only
                        value = float(rows['labels'][h]['value'][t])
                        tables[h].setdefault(sid, {})[k // h] = value
                        total = totals[h].setdefault(k // h, [0.0, 0])
                        total[0] += value
                        total[1] += 1
                    k = hold_position.get(s)
                    if name == splits.HISTORICAL_HOLDOUT and k is not None and k % h == 0:
                        hold_counts[h][k // h] = hold_counts[h].get(k // h, 0) + 1
        out['sample_sessions_per_instrument'].append(own_samples)
        if progress and n % 200 == 0:
            progress(n, len(spans))
    out['unique_sample_sessions'] = len(sample_sessions)
    out['sample_sessions_per_instrument_median'] = float(np.median(out.pop('sample_sessions_per_instrument'))) if spans else 0.0
    out['unique_instruments'] = len(set().union(*(p['instruments'] for p in out['by_segment'].values())))
    out['unique_sessions'] = len(set().union(*(p['sessions'] for p in out['by_segment'].values())))
    out['sequence_share'] = out.pop('sequence_ready') / out['eligible_feature_rows'] if out['eligible_feature_rows'] else None
    out['coarse_print_share'] = out['coarse_print_rows'] / out['eligible_feature_rows'] if out['eligible_feature_rows'] else None
    # all rows or none: one row that would read a coarsely printed bar withholds the high/low/open families from every row
    out['high_low_open_families_usable'] = bool(out['eligible_feature_rows']) and out['rows_reading_a_coarse_print'] == 0
    out['volume_features_usable'] = bool(out['eligible_feature_rows']) and out['rows_reading_an_unreadable_volume'] == 0
    out['member_bars_present_share'] = out['raw_member_rows'] / out['member_sessions'] if out['member_sessions'] else None
    out['action_table_contradictions'] = contradictions(out['split_convention'], out['dividend_basis'])
    # Burn-in and purge sessions yield no sample. The total is the sum of the four sample segments, shown one by one.
    out['strict_samples_by_segment'] = {str(h): {name: out['by_segment'][name][f'labelled_{h}'] for name in splits.SAMPLE_SEGMENTS} for h in targets.HORIZONS}
    out['strict_samples'] = {h: sum(parts.values()) for h, parts in out['strict_samples_by_segment'].items()}
    out['retrospective_samples'] = 0            # this builder reads no retrospective input; Checkpoint 7's retrospective dataset is separate and not added
    development = sorted(out['by_segment'][splits.DEVELOPMENT]['sessions'])
    out['development_first_sample_session'], out['development_last_sample_session'] = (development[0], development[-1]) if development else (None, None)
    measured = {}
    for h in targets.HORIZONS:
        windows = sorted(totals[h])
        column = {w: k for k, w in enumerate(windows)}
        table = np.full((len(windows), len(tables[h])), np.nan)
        for j, sid in enumerate(sorted(tables[h])):
            for w, value in tables[h][sid].items():
                table[column[w], j] = value - totals[h][w][0] / totals[h][w][1]          # excess over the equal-weighted mean of that window's rows
        b = sufficiency.breadth(table) if len(windows) else {'n_eff': None, 'instruments_per_window': 0.0, 'mean_squared_correlation': None, 'pairs': 0, 'measure': 'breadth_v2'}
        m = b['mean_squared_correlation'] if b['n_eff'] is not None else None
        e_dev = sufficiency.effective_by_window([totals[h][w][1] for w in windows], m)
        e_hold = sufficiency.effective_by_window(hold_counts[h].values(), m)
        measured[str(h)] = {'breadth': b, 'development_windows': len(windows), 'effective_observations_development': e_dev,
                            'detectable_ic_development': sufficiency.detectable_ic(e_dev), 'holdout_windows': len(hold_counts[h]),
                            'effective_observations_holdout': e_hold, 'detectable_ic_holdout': sufficiency.detectable_ic(e_hold),
                            'development_testability': sufficiency.testability(sufficiency.detectable_ic(e_dev)),
                            'holdout_testability': sufficiency.testability(sufficiency.detectable_ic(e_hold)),
                            'note': 'the correlation between instruments is measured on development labels only; each window counts the instruments it holds; '
                                    'for the holdout only how many labels can be built is counted, no value is read'}
    out['effective'] = measured
    for part in out['by_segment'].values():
        part['sessions'], part['instruments'] = len(part['sessions']), len(part['instruments'])
    for year in out['by_year'].values():
        year['instruments'] = len(year['instruments'])
    out['by_year'] = dict(sorted(out['by_year'].items()))
    out['delisting_exits_by_year'] = dict(sorted(out['delisting_exits_by_year'].items()))
    out['manifest'] = manifest(store, chosen['manifest'])
    return out


def manifest(store, universe_manifest) -> dict:
    """What a dataset is built from. Everything needed to build it again is named by version or hash."""
    body = {'dataset_version': DATASET_VERSION, 'policy_version': POLICY_VERSION, 'bar_known_at_version': BAR_KNOWN_AT_VERSION, 'return_basis': RETURN_BASIS,
            'universe_version': universe_manifest['universe_version'], 'universe_hash': universe_manifest['universe_hash'],
            'feature_set_version': features.FEATURE_SET_VERSION, 'feature_versions': sorted({d['version'] for d in features.DEFINITIONS}),
            'feature_code_hash': features.code_hash(), 'feature_names': list(features.NAMES), 'core_features': list(CORE_FEATURES),
            'target_version': targets.TARGET_VERSION, 'horizons': list(targets.HORIZONS), 'split_version': splits.SPLIT_VERSION,
            'minimum_history_bars': MINIMUM_HISTORY_BARS, 'input_window_bars': INPUT_WINDOW_BARS, 'features_of_burned_rows_read_from': FEATURES_FROM,
            'source_blocks_hash': universe_manifest['source_blocks_hash'],
            'actions_hash': universe_manifest['actions_hash'], 'captures': _sources(store)}
    body['dataset_spec_hash'] = content_hash(body)
    return body


def _array_hash(array) -> str:
    view = np.ascontiguousarray(np.where(np.isnan(array), -9.87654321e300, array).astype('<f8'))
    return hashlib.sha256(view.tobytes()).hexdigest()


def materialise(store, *, universe_hash=None, source=None, segments=(splits.DEVELOPMENT,), years=None) -> dict:
    """The strict rows of the named segments as arrays, with a manifest and one dataset hash. Refuses every segment that
    may not be read. Rows that read a restated bar (tier C) are left out and counted."""
    if any(not splits.labels_allowed(s) for s in segments):
        raise ValueError('SEALED_SEGMENT')
    chosen = universe.load(store, universe_hash, require_current=True)
    if chosen['manifest'] is None:
        raise ValueError('NO_STORED_UNIVERSE')
    spans = universe.membership(chosen['records'])
    securities = current_securities(store, source=source)
    actions = _actions_by_security(store, source)
    ids, sessions, tiers, feats, blocks, coarse, touched, restated, thin = [], [], [], [], set(), 0, 0, 0, 0
    convention, basis = {}, {}
    raw = {h: [] for h in targets.HORIZONS}
    states = {h: [] for h in targets.HORIZONS}
    data_end = store.bar_summary()['last_session']
    for sid in sorted(spans):
        rows = security_rows(store, sid, securities.get(sid), spans[sid], actions.get(sid, []), source=source, data_end=data_end)
        keep = rows['eligible'] & np.isin(rows['segment'], list(segments))
        if years is not None:
            keep &= np.array([s[:4] in years for s in rows['sessions']], bool)
        for tally, counts in ((convention, rows['audit']['split_convention']), (basis, rows['audit']['dividend_basis'])):
            for key, value in counts.items():
                tally[key] = tally.get(key, 0) + value
        restated += int((keep & (rows['tier'] == RETROSPECTIVE)).sum())
        keep &= np.isin(rows['tier'], STRICT_TIERS)
        index = np.flatnonzero(keep)
        if not len(index):
            continue
        blocks.update(rows['blocks'])
        coarse += int(rows['coarse'][index].sum())
        touched += int(rows['reads_coarse'][index].sum())
        thin += int(rows['reads_unreadable_volume'][index].sum())
        ids.extend([sid] * len(index))
        sessions.extend(rows['sessions'][t] for t in index)
        tiers.extend(rows['tier'][index])
        feats.append(np.column_stack([rows['features'][name][index] for name in features.NAMES]))
        for h in targets.HORIZONS:
            raw[h].append(rows['labels'][h]['value'][index])
            states[h].append(rows['labels'][h]['state'][index])
    against = contradictions(convention, basis)
    if against:
        raise ValueError(against[0])                                   # the vendor's action table does not mean what every decision here assumes
    X = np.vstack(feats) if feats else np.zeros((0, len(features.NAMES)))
    share = coarse / len(ids) if ids else 0.0
    usable = touched == 0
    if not usable:              # one row would read a coarsely printed bar: the high/low/open families are withheld from every row, never row by row
        X[:, [k for k, d in enumerate(features.DEFINITIONS) if d['uses_high_low_open']]] = np.nan
    if thin:                    # the same rule for volume: one row would read a volume a later reverse split made unreadable
        X[:, [k for k, d in enumerate(features.DEFINITIONS) if d['uses_volume']]] = np.nan
    order = np.lexsort((np.array(ids, dtype=object), np.array(sessions, dtype=object))) if ids else np.zeros(0, int)
    ids, sessions, tiers, X = [ids[k] for k in order], [sessions[k] for k in order], [tiers[k] for k in order], X[order]
    y, y_state, excess = {}, {}, {}
    _, group = np.unique(np.array(sessions, dtype=str), return_inverse=True) if sessions else (None, np.zeros(0, int))
    for h in targets.HORIZONS:
        y[h] = (np.concatenate(raw[h]) if raw[h] else np.zeros(0))[order]
        y_state[h] = (np.concatenate(states[h]) if states[h] else np.zeros(0, int))[order]
        excess[h] = np.full(len(y[h]), np.nan)
        finite = np.isfinite(y[h])
        if finite.any():                                              # excess over the equal-weighted mean of the same session's labelled rows
            sums = np.bincount(group[finite], weights=y[h][finite], minlength=group.max() + 1)
            counts = np.bincount(group[finite], minlength=group.max() + 1)
            excess[h][finite] = y[h][finite] - (sums / np.maximum(counts, 1))[group[finite]]
    body = manifest(store, chosen['manifest'])
    parts = {'rows': content_hash([list(pair) for pair in zip(ids, sessions)]), 'features': _array_hash(X),
             'labels': content_hash({str(h): [_array_hash(y[h]), _array_hash(excess[h]), _array_hash(y_state[h].astype(float))] for h in targets.HORIZONS}),
             'tiers': content_hash(list(tiers)), 'blocks': content_hash(sorted(blocks))}
    body.update({'segments': list(segments), 'years': sorted(years) if years else None, 'rows': len(ids), 'hashes': parts,
                 'coarse_print_share': share, 'rows_reading_a_coarse_print': touched, 'high_low_open_families_usable': usable,
                 'rows_reading_an_unreadable_volume': thin, 'volume_features_usable': thin == 0,
                 'rows_left_out_because_a_bar_was_revised': restated})
    body['dataset_hash'] = content_hash({'spec': body['dataset_spec_hash'], 'segments': body['segments'], 'years': body['years'], 'hashes': parts})
    return {'security_id': ids, 'session': sessions, 'tier': tiers, 'X': X, 'feature_names': list(features.NAMES), 'y': y, 'y_excess': excess, 'y_state': y_state,
            'manifest': body}


def register(store, data) -> bool:
    """Stores a dataset manifest (no rows, no prices). The same dataset registers once."""
    return store.put('history_datasets', data['manifest'], identity=data['manifest']['dataset_hash'])
