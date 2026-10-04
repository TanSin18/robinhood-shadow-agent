"""The historical research universe: a versioned, deterministic liquidity screen formed only from the past.

``liquid-us-listed-v1``. On the last exchange session of each month (the formation session R), every security in the
provider's stock table, delisted ones included, is screened with bars up to and including R only:

1. at least 252 bars of history up to R;
2. a bar on R, with an unadjusted close of at least 5.00 U.S. dollars (the price printed that day, not an adjusted one);
3. a bar on at least 60 of the last 63 exchange sessions;
4. ranked by the median daily dollar volume of those 63 sessions (close times volume; a split leaves it unchanged),
   highest first, security identifier as the tie-break; the first 1,000 are members.

Membership takes effect on the next session and lasts through the next formation session. Everything the rule reads is
available by the open of that next session (``bar-known-at-v1``), so membership is known before it is used.

Not the S&P 500, and not today's list. No market capitalisation, sector or classification is read: the vendor's
classifications describe the company as it is today, and applying them to the past would be a present-day label.
A company that later failed or was acquired is a member for as long as it qualified.
"""
from __future__ import annotations

import numpy as np

from . import PUBLISHER_DATED_HISTORICAL, calendar, panel as panels
from .ingest import current_securities
from .store import content_hash

UNIVERSE_VERSION = 'liquid-us-listed-v1'
RULE = {'size': 1000, 'minimum_unadjusted_close': 5.0, 'minimum_history_bars': 252, 'liquidity_window_sessions': 63, 'minimum_bars_in_window': 60,
        'price_table': 'stocks', 'ranking': 'median daily dollar volume over the liquidity window, descending; security identifier ascending on ties',
        'formation': 'last exchange session of each calendar month', 'effective': 'from the next session through the next formation session'}
REASONS = ('NO_BAR_ON_FORMATION_SESSION', 'INSUFFICIENT_HISTORY', 'PRICE_BELOW_MINIMUM', 'TOO_FEW_BARS_IN_WINDOW', 'NO_DOLLAR_VOLUME', 'RANKED_BELOW_SIZE')


def formation_stats(panel, formations, rule=RULE) -> dict:
    """{formation session: (reason or None, median dollar volume)} for the formation sessions inside this security's span."""
    sessions = panel['sessions']
    if not sessions:
        return {}
    slot = {s: k for k, s in enumerate(sessions)}
    present = panel['present']
    history = np.cumsum(present)
    window = rule['liquidity_window_sessions']
    with np.errstate(invalid='ignore'):
        dollars = panel['close'] * panel['volume']
    out = {}
    for r in formations:
        k = slot.get(r)
        if k is None:
            continue
        if not present[k]:
            out[r] = ('NO_BAR_ON_FORMATION_SESSION', None)
        elif history[k] < rule['minimum_history_bars']:
            out[r] = ('INSUFFICIENT_HISTORY', None)
        elif not panel['close_unadjusted'][k] >= rule['minimum_unadjusted_close']:
            out[r] = ('PRICE_BELOW_MINIMUM', None)
        else:
            recent = dollars[max(0, k - window + 1):k + 1]
            valid = recent[np.isfinite(recent)]
            if len(valid) < rule['minimum_bars_in_window']:
                out[r] = ('TOO_FEW_BARS_IN_WINDOW', None)
            elif not np.median(valid) > 0:
                out[r] = ('NO_DOLLAR_VOLUME', None)
            else:
                out[r] = (None, float(np.median(valid)))
    return out


def build(store, start, end, *, rule=RULE, source=None, progress=None) -> dict:
    """Forms the universe for every month-end in [start, end] and stores one record per formation session, plus a
    manifest. Refuses a source with no delisted security: a universe drawn from survivors is not historical."""
    securities = {sid: s for sid, s in current_securities(store, source=source).items() if s['price_table'] == rule['price_table']}
    if not any(s['is_delisted'] for s in securities.values()):
        raise ValueError('SURVIVOR_ONLY_SOURCE')
    formations = calendar.month_ends(start, end)
    eligible = {r: [] for r in formations}
    screened = {r: {} for r in formations}
    blocks = []
    for n, sid in enumerate(sorted(securities)):
        p = panels.load(store, sid, source=source)
        blocks.extend(p['blocks'])
        for r, (reason, dollars) in formation_stats(p, formations, rule).items():
            if reason is None:
                eligible[r].append((-dollars, sid))
            else:
                screened[r][reason] = screened[r].get(reason, 0) + 1
        if progress and n % 500 == 0:
            progress(n, len(securities))
    rule_hash = content_hash(rule)
    records, ever = [], set()
    for k, r in enumerate(formations):
        ranked = sorted(eligible[r])
        members = sorted(sid for _, sid in ranked[:rule['size']])
        below = len(ranked) - len(members)
        if below:
            screened[r]['RANKED_BELOW_SIZE'] = below
        effective_from = calendar.offset(r, 1)
        record = {'universe_version': UNIVERSE_VERSION, 'rule_hash': rule_hash, 'formation_session': r, 'effective_from': effective_from,
                  'effective_to': formations[k + 1] if k + 1 < len(formations) else calendar.month_ends(effective_from, calendar.offset(effective_from, 30))[0],
                  'known_at': calendar.eligible_from(r), 'known_at_basis': 'every input is a bar on or before the formation session (bar-known-at-v1)',
                  'tier': PUBLISHER_DATED_HISTORICAL, 'members': members, 'member_count': len(members), 'eligible_count': len(ranked),
                  'screened_out': screened[r],
                  'smallest_member_median_dollar_volume': -ranked[len(members) - 1][0] if members else None}
        store.put('history_universe', record)
        records.append(record)
        ever.update(members)
    delisted = sum(1 for sid in ever if securities[sid]['is_delisted'])
    manifest = {'kind': 'universe_manifest', 'universe_version': UNIVERSE_VERSION, 'rule': rule, 'rule_hash': rule_hash, 'start': start, 'end': end,
                'formation_sessions': len(formations), 'first_formation': formations[0] if formations else None, 'last_formation': formations[-1] if formations else None,
                'securities_screened': len(securities), 'distinct_members': len(ever), 'members_later_delisted': delisted,
                'member_count_min': min((r['member_count'] for r in records), default=0), 'member_count_max': max((r['member_count'] for r in records), default=0),
                'source_blocks_hash': content_hash(sorted(set(blocks))), 'records_hash': content_hash([content_hash(r) for r in records]),
                'survivorship': 'formed from every stored security including delisted ones; no present-day list, classification or market value is read',
                'tier': PUBLISHER_DATED_HISTORICAL}
    manifest['universe_hash'] = content_hash({k: manifest[k] for k in ('universe_version', 'rule_hash', 'start', 'end', 'source_blocks_hash', 'records_hash')})
    store.put('history_universe', manifest)
    return manifest


def load(store, universe_hash=None) -> dict:
    """{'manifest': ..., 'records': [formation records in order]} for the newest stored universe (or the one named)."""
    manifests, records = [], []
    for _, payload, created in store.rows('history_universe'):
        if payload.get('kind') == 'universe_manifest':
            manifests.append((created, payload))
        else:
            records.append(payload)
    if not manifests:
        return {'manifest': None, 'records': []}
    chosen = next((m for _, m in manifests if m['universe_hash'] == universe_hash), None) if universe_hash else max(manifests, key=lambda m: m[0])[1]
    if chosen is None:
        raise ValueError('UNKNOWN_UNIVERSE')
    mine = sorted((r for r in records if r['rule_hash'] == chosen['rule_hash'] and chosen['start'] <= r['formation_session'] <= chosen['end']),
                  key=lambda r: r['formation_session'])
    if content_hash([content_hash(r) for r in mine]) != chosen['records_hash']:
        raise ValueError('UNIVERSE_RECORDS_DO_NOT_MATCH_MANIFEST')
    return {'manifest': chosen, 'records': mine}


def membership(records) -> dict:
    """{security_id: [(effective_from, effective_to), ...]} from formation records."""
    out = {}
    for r in records:
        for sid in r['members']:
            out.setdefault(sid, []).append((r['effective_from'], r['effective_to']))
    return out


def member_mask(sessions, spans) -> np.ndarray:
    """True for each session that lies inside one of this security's membership spans."""
    mask = np.zeros(len(sessions), bool)
    arr = np.asarray(sessions)
    for first, last in spans:
        mask |= (arr >= first) & (arr <= last)
    return mask
