"""Dataset contract v2 for a future tournament, and the honest count of what it can hold today.

``pit-dataset-v2``. A row is (security, session T). It is a strict point-in-time sample only when all of these hold:

* the security is a member of the stored historical universe on T (membership formed from bars before it took effect);
* it has a bar on T and at least 252 bars of history, and the core features are available at T;
* every input is tier A (Firm Lab held it before the next session opened) or tier B (a publisher-dated historical bar);
* its label at the horizon exists (``targets``): entry at the open of T+1, never a price at or before T.

The row's tier is the lowest among its inputs. Tier A needs every one of the last 252 bars to have been held at the
time, so a row built from a licensed archive is tier B. Retrospective inputs (tier C) are not used by this builder at
all; the Checkpoint 7 retrospective samples are a different dataset and are never added to these counts.

Sealed segments (``splits``): label VALUES of the historical holdout and of the forward holdout are never returned,
averaged or correlated here. Only whether a label can be built is counted, which reads dates and bar existence.

Every dataset names the stored blocks, captures, universe, feature code, target and split it was built from, and has
one hash over all of that. The same inputs give the same hash.
"""
from __future__ import annotations

import hashlib

import numpy as np

from . import BAR_KNOWN_AT_VERSION, HELD_AT_THE_TIME, POLICY_VERSION, PUBLISHER_DATED_HISTORICAL, RETURN_BASIS, adjust, calendar, features, panel as panels, splits, sufficiency, targets, universe
from .ingest import current_securities
from .store import content_hash

DATASET_VERSION = 'pit-dataset-v2'
MINIMUM_HISTORY_BARS = 252
CORE_FEATURES = ('return20', 'realized_vol20', 'atr14_fraction', 'rvol20')
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


def row_tiers(sessions, present, first_seen) -> np.ndarray:
    """The tier of each session's row. A bar was held at the time when Firm Lab stored it before the next session opened.
    A row is tier A only when every one of its last 252 bars was held at the time; otherwise it is tier B."""
    count = len(sessions)
    held = np.array([first_seen.get(s, '9') <= _eligible_from(s) for s in sessions], bool) if count else np.zeros(0, bool)
    run, bars = 0, np.zeros(count, int)
    for t in range(count):
        if present[t]:
            run = run + 1 if held[t] else 0
        bars[t] = run
    return np.where(bars >= MINIMUM_HISTORY_BARS, HELD_AT_THE_TIME, PUBLISHER_DATED_HISTORICAL)


def security_rows(store, sid, security, spans, actions, *, source=None) -> dict:
    """Everything one security contributes: per session, its features, whether the row is eligible, its tier, its segment
    and its labels. Label values inside a sealed segment are removed before anything is returned."""
    p = panels.load(store, sid, source=source)
    sessions = p['sessions']
    count = len(sessions)
    audit = adjust.breaks(p, actions)
    mask = adjust.break_mask(p, audit['breaks'])
    computed = features.compute(p, mask)
    values = computed['values']
    member = universe.member_mask(sessions, spans)
    history = np.cumsum(p['present'])
    core = np.all([np.isfinite(values[name]) for name in CORE_FEATURES], axis=0) if count else np.zeros(0, bool)
    eligible = member & p['present'] & (history >= MINIMUM_HISTORY_BARS) & core
    tier = row_tiers(sessions, p['present'], store.first_seen(sid, source=source))
    segment = np.array([splits.segment(s) for s in sessions], dtype=object) if count else np.zeros(0, dtype=object)
    labels = targets.build(p, mask, delisted=bool(security.get('is_delisted')))
    sealed = np.isin(segment, splits.SEALED) if count else np.zeros(0, bool)
    for h in labels:
        labels[h]['value'] = np.where(sealed, np.nan, labels[h]['value'])          # a sealed label value never leaves this function
    return {'security_id': sid, 'sessions': sessions, 'present': p['present'], 'member': member, 'eligible': eligible, 'tier': tier, 'segment': segment,
            'features': values, 'labels': labels, 'breaks': audit['breaks'], 'blocks': p['blocks'], 'audit': {**audit, 'structure': computed['audit']},
            'history_bars': history}


def _sources(store) -> list:
    return sorted(({'capture_id': p['capture_id'], 'kind': p['kind'], 'source': p['source'], 'sha256': p['sha256'], 'adapter': p['adapter']}
                   for _, p, _ in store.rows('history_captures')), key=lambda c: (c['kind'], c['sha256'], c['capture_id']))


def count(store, *, universe_hash=None, source=None, progress=None) -> dict:
    """The strict point-in-time sample count and the quantities of the sufficiency specification. Fits nothing."""
    chosen = universe.load(store, universe_hash)
    if chosen['manifest'] is None:
        return {'dataset_version': DATASET_VERSION, 'universe': None, 'raw_member_rows': 0, 'strict_samples': {str(h): 0 for h in targets.HORIZONS},
                'retrospective_samples': 0, 'reason': 'NO_STORED_UNIVERSE'}
    spans = universe.membership(chosen['records'])
    securities = current_securities(store, source=source)
    actions = _actions_by_security(store, source)
    every = calendar.sessions(splits.FIRST_SAMPLE, splits.development_last())
    dev_position = {s: k for k, s in enumerate(every)}
    out = {'dataset_version': DATASET_VERSION, 'universe_hash': chosen['manifest']['universe_hash'], 'raw_member_rows': 0, 'eligible_feature_rows': 0,
           'by_segment': {s: {'eligible_feature_rows': 0, 'sessions': set(), 'instruments': set(), **{f'labelled_{h}': 0 for h in targets.HORIZONS}} for s in SEGMENTS},
           'by_tier': {HELD_AT_THE_TIME: 0, PUBLISHER_DATED_HISTORICAL: 0}, 'by_year': {}, 'label_states': {str(h): {} for h in targets.HORIZONS},
           'delisting_exits_by_reason': {}, 'breaks_by_reason': {}, 'splits_confirmed': 0, 'split_convention': {'new_per_old': 0, 'old_per_new': 0},
           'sample_sessions_per_instrument': [], 'sequence_ready': 0}
    tables = {h: {} for h in targets.HORIZONS}                           # horizon -> {security: {development window index: raw label}}
    totals = {h: {} for h in targets.HORIZONS}                           # horizon -> {window index: [sum, count]} for the cross-sectional mean
    for n, sid in enumerate(sorted(spans)):
        rows = security_rows(store, sid, securities[sid], spans[sid], actions.get(sid, []), source=source)
        sessions, eligible, segment = rows['sessions'], rows['eligible'], rows['segment']
        out['raw_member_rows'] += int((rows['member'] & rows['present']).sum())
        out['eligible_feature_rows'] += int(eligible.sum())
        out['splits_confirmed'] += rows['audit']['splits_confirmed']
        for key, value in rows['audit']['split_convention'].items():
            out['split_convention'][key] += value
        for b in rows['breaks']:
            out['breaks_by_reason'][b['reason']] = out['breaks_by_reason'].get(b['reason'], 0) + 1
        index = np.flatnonzero(eligible)
        out['sample_sessions_per_instrument'].append(int(len(index)))
        run = 0
        for t in range(len(sessions)):
            run = run + 1 if eligible[t] else 0
            out['sequence_ready'] += int(run >= sufficiency.NETWORK_BAR['sequence_sessions'])
        reasons = {a['effective_date']: a.get('provider_code') for a in actions.get(sid, []) if a['type'] == 'delisting'}
        reason = reasons[max(reasons)] if reasons else 'NOT_RECORDED'
        for t in index:
            s, name = sessions[t], segment[t]
            part = out['by_segment'][name]
            part['eligible_feature_rows'] += 1
            part['sessions'].add(s)
            part['instruments'].add(sid)
            out['by_tier'][rows['tier'][t]] += 1
            year = out['by_year'].setdefault(s[:4], {'eligible_feature_rows': 0, 'instruments': set()})
            year['eligible_feature_rows'] += 1
            year['instruments'].add(sid)
            for h in targets.HORIZONS:
                state = int(rows['labels'][h]['state'][t])
                text = targets.REASONS[state]
                out['label_states'][str(h)][text] = out['label_states'][str(h)].get(text, 0) + 1
                if state in (targets.OK, targets.DELISTED_EXIT):
                    part[f'labelled_{h}'] += 1
                    if state == targets.DELISTED_EXIT and h == targets.MAX_HORIZON:
                        out['delisting_exits_by_reason'][reason] = out['delisting_exits_by_reason'].get(reason, 0) + 1
                    k = dev_position.get(s)
                    if name == splits.DEVELOPMENT and k is not None and k % h == 0:      # non-overlapping windows, development only
                        value = float(rows['labels'][h]['value'][t])
                        tables[h].setdefault(sid, {})[k // h] = value
                        total = totals[h].setdefault(k // h, [0.0, 0])
                        total[0] += value
                        total[1] += 1
        if progress and n % 200 == 0:
            progress(n, len(spans))
    out['sample_sessions_per_instrument_median'] = float(np.median(out.pop('sample_sessions_per_instrument'))) if spans else 0.0
    out['unique_instruments'] = len(set().union(*(p['instruments'] for p in out['by_segment'].values())))
    out['unique_sessions'] = len(set().union(*(p['sessions'] for p in out['by_segment'].values())))
    out['sequence_share'] = out.pop('sequence_ready') / out['eligible_feature_rows'] if out['eligible_feature_rows'] else None
    out['strict_samples'] = {str(h): sum(p[f'labelled_{h}'] for p in out['by_segment'].values()) for h in targets.HORIZONS}
    out['retrospective_samples'] = 0            # this builder reads no retrospective input; Checkpoint 7's retrospective dataset is separate and not added
    measured = {}
    for h in targets.HORIZONS:
        windows = sorted(totals[h])
        column = {w: k for k, w in enumerate(windows)}
        table = np.full((len(windows), len(tables[h])), np.nan)
        for j, sid in enumerate(sorted(tables[h])):
            for w, value in tables[h][sid].items():
                table[column[w], j] = value - totals[h][w][0] / totals[h][w][1]          # excess over the equal-weighted mean of that window's rows
        b = sufficiency.breadth(table) if len(windows) else {'n_eff': None, 'instruments_per_window': 0.0, 'mean_squared_correlation': None, 'pairs': 0, 'measure': 'breadth_v2'}
        dev_sessions = len(out['by_segment'][splits.DEVELOPMENT]['sessions'])
        hold_sessions = len(out['by_segment'][splits.HISTORICAL_HOLDOUT]['sessions'])
        e_dev = sufficiency.effective_observations(dev_sessions, h, b['n_eff'])
        e_hold = sufficiency.effective_observations(hold_sessions, h, b['n_eff'])
        measured[str(h)] = {'breadth': b, 'development_sessions': dev_sessions, 'development_windows': dev_sessions / h, 'effective_observations_development': e_dev,
                            'detectable_ic_development': sufficiency.detectable_ic(e_dev), 'holdout_sessions': hold_sessions, 'holdout_windows': hold_sessions / h,
                            'effective_observations_holdout': e_hold, 'detectable_ic_holdout': sufficiency.detectable_ic(e_hold),
                            'holdout_testability': sufficiency.testability(sufficiency.detectable_ic(e_hold)),
                            'note': 'breadth is measured on development sessions only and applied to the holdout session count; no holdout label value is read'}
    out['effective'] = measured
    for part in out['by_segment'].values():
        part['sessions'], part['instruments'] = len(part['sessions']), len(part['instruments'])
    for year in out['by_year'].values():
        year['instruments'] = len(year['instruments'])
    out['by_year'] = dict(sorted(out['by_year'].items()))
    out['manifest'] = manifest(store, chosen['manifest'])
    return out


def manifest(store, universe_manifest) -> dict:
    """What a dataset is built from. Everything needed to build it again is named by version or hash."""
    body = {'dataset_version': DATASET_VERSION, 'policy_version': POLICY_VERSION, 'bar_known_at_version': BAR_KNOWN_AT_VERSION, 'return_basis': RETURN_BASIS,
            'universe_version': universe_manifest['universe_version'], 'universe_hash': universe_manifest['universe_hash'],
            'feature_set_version': features.FEATURE_SET_VERSION, 'feature_versions': sorted({d['version'] for d in features.DEFINITIONS}),
            'feature_code_hash': features.code_hash(), 'feature_names': list(features.NAMES), 'core_features': list(CORE_FEATURES),
            'target_version': targets.TARGET_VERSION, 'horizons': list(targets.HORIZONS), 'split_version': splits.SPLIT_VERSION,
            'minimum_history_bars': MINIMUM_HISTORY_BARS, 'source_blocks_hash': universe_manifest['source_blocks_hash'], 'captures': _sources(store)}
    body['dataset_spec_hash'] = content_hash(body)
    return body


def _array_hash(array) -> str:
    view = np.ascontiguousarray(np.where(np.isnan(array), -9.87654321e300, array).astype('<f8'))
    return hashlib.sha256(view.tobytes()).hexdigest()


def materialise(store, *, universe_hash=None, source=None, segments=(splits.DEVELOPMENT,), years=None) -> dict:
    """The rows of the named segments as arrays, with a manifest and one dataset hash. Refuses a sealed segment."""
    if any(not splits.labels_allowed(s) for s in segments):
        raise ValueError('SEALED_SEGMENT')
    chosen = universe.load(store, universe_hash)
    if chosen['manifest'] is None:
        raise ValueError('NO_STORED_UNIVERSE')
    spans = universe.membership(chosen['records'])
    securities = current_securities(store, source=source)
    actions = _actions_by_security(store, source)
    ids, sessions, tiers, feats, blocks = [], [], [], [], set()
    raw = {h: [] for h in targets.HORIZONS}
    states = {h: [] for h in targets.HORIZONS}
    for sid in sorted(spans):
        rows = security_rows(store, sid, securities[sid], spans[sid], actions.get(sid, []), source=source)
        keep = rows['eligible'] & np.isin(rows['segment'], list(segments))
        if years is not None:
            keep &= np.array([s[:4] in years for s in rows['sessions']], bool)
        index = np.flatnonzero(keep)
        if not len(index):
            continue
        blocks.update(rows['blocks'])
        ids.extend([sid] * len(index))
        sessions.extend(rows['sessions'][t] for t in index)
        tiers.extend(rows['tier'][index])
        feats.append(np.column_stack([rows['features'][name][index] for name in features.NAMES]))
        for h in targets.HORIZONS:
            raw[h].append(rows['labels'][h]['value'][index])
            states[h].append(rows['labels'][h]['state'][index])
    X = np.vstack(feats) if feats else np.zeros((0, len(features.NAMES)))
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
             'labels': content_hash({str(h): [_array_hash(y[h]), _array_hash(excess[h])] for h in targets.HORIZONS}), 'blocks': content_hash(sorted(blocks))}
    body.update({'segments': list(segments), 'years': sorted(years) if years else None, 'rows': len(ids), 'hashes': parts})
    body['dataset_hash'] = content_hash({'spec': body['dataset_spec_hash'], 'segments': body['segments'], 'years': body['years'], 'hashes': parts})
    return {'security_id': ids, 'session': sessions, 'tier': tiers, 'X': X, 'feature_names': list(features.NAMES), 'y': y, 'y_excess': excess, 'y_state': y_state,
            'manifest': body}


def register(store, data) -> bool:
    """Stores a dataset manifest (no rows, no prices). The same dataset registers once."""
    return store.put('history_datasets', data['manifest'], identity=data['manifest']['dataset_hash'])
