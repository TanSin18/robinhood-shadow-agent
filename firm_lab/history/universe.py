"""The historical research universe: a versioned, deterministic liquidity screen formed only from the past.

``liquid-us-listed-v1``. On the last exchange session of each month (the formation session R), every security in the
provider's stock table, delisted ones included, is screened with bars up to and including R only:

1. at least 252 bars of history up to R;
2. a bar on R, with an unadjusted close of at least 5.00 U.S. dollars (the price printed that day, not an adjusted one);
3. a bar on at least 60 of the last 63 exchange sessions;
4. ranked by the median daily dollar volume of those 63 sessions (the price printed on the day times the shares traded
   on the day, which no later split changes), highest first, security identifier as the tie-break; the first 1,000 are
   members.

Membership takes effect on the next session and lasts through the next formation session. Everything the rule reads is
available by the open of that next session (``bar-known-at-v1``), so membership is known before it is used.

Not the S&P 500, and not today's list. No market capitalisation, sector or classification is read, and no row of the
security master: the master describes a company as it is today. Which securities are screened is decided by the bars
themselves (those that came from the stock-price file). A company that later failed or was acquired is a member for as
long as it qualified.

A universe is built from the bars as they are stored today. If the vendor later revises a past bar, that universe is
stale: it is refused, and a new one is built with its own hash. Both stay in the database.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from . import PUBLISHER_DATED_HISTORICAL, adjust, calendar, panel as panels
from .ingest import current_securities
from .store import content_hash

UNIVERSE_VERSION = 'liquid-us-listed-v1'
RULE = {'size': 1000, 'minimum_unadjusted_close': 5.0, 'minimum_history_bars': 252, 'liquidity_window_sessions': 63, 'minimum_bars_in_window': 60,
        'price_table': 'stocks', 'ranking': 'median daily dollar volume over the liquidity window, descending; security identifier ascending on ties',
        'formation': 'last exchange session of each calendar month', 'effective': 'from the next session through the next formation session'}
REASONS = ('NO_BAR_ON_FORMATION_SESSION', 'INSUFFICIENT_HISTORY', 'PRICE_BELOW_MINIMUM', 'VOLUME_REPRINT_TOO_COARSE', 'TOO_FEW_BARS_IN_WINDOW', 'NO_DOLLAR_VOLUME',
           'RANKED_BELOW_SIZE')
UNREADABLE_VOLUME = 'VOLUME_REPRINT_TOO_COARSE'


def formation_stats(panel, formations, rule=RULE, actions=()) -> dict:
    """{formation session: (reason or None, median dollar volume)} for the formation sessions inside this security's span.
    Dollar volume is the unadjusted close times the shares traded on the day (the vendor's adjusted volume divided by the
    split factor), so it does not depend on how the vendor rounded prices it reprinted after a later split.

    One thing a later split can still take away is the volume itself: after a large later reverse split the re-counted
    volume of an early session can be too small a number to read (``adjust.coarse_volume``). A security cannot be ranked
    on such a window. It is screened out under its own reason and counted, so that the candidates lost this way (they
    are stocks that later collapsed) are a known number and not a silent gap."""
    sessions = panel['sessions']
    if not sessions:
        return {}
    slot = {s: k for k, s in enumerate(sessions)}
    present = panel['present']
    history = np.cumsum(present)
    window = rule['liquidity_window_sessions']
    splits = adjust.breaks(panel, actions)['splits'] if actions else ()
    with np.errstate(invalid='ignore', divide='ignore'):
        dollars = panel['close_unadjusted'] * panel['volume'] / adjust.share_divisor(panel, splits)
    unreadable = np.cumsum(adjust.coarse_volume(panel, splits))
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
        elif unreadable[k] - (unreadable[k - window] if k >= window else 0) > 0:
            out[r] = (UNREADABLE_VOLUME, None)
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


def actions_hash(store, source=None) -> str:
    """One hash over every stored corporate action: a universe or a dataset built with other actions is another one."""
    return content_hash(sorted(identity for identity, payload, _ in store.rows('history_actions') if source is None or payload['source'] == source))


def code_hash() -> str:
    """The hash of this module's source: a universe formed by other code is another universe."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def build(store, start, end, *, rule=RULE, version=UNIVERSE_VERSION, source=None, progress=None) -> dict:
    """Forms the universe for every month-end in [start, end] and stores one record per formation session, plus a
    manifest. Refuses a source in which no delisted security has bars: a universe drawn from survivors is not historical.
    A rule other than the registered one must be given a version name of its own."""
    if content_hash(rule) != content_hash(RULE) and version == UNIVERSE_VERSION:
        raise ValueError('RULE_NEEDS_ITS_OWN_VERSION')
    screened = store.security_ids(price_table=rule['price_table'])      # decided by where the bars came from, not by today's master row
    master = current_securities(store, source=source)
    if not any(master.get(sid, {}).get('is_delisted') for sid in screened):
        raise ValueError('SURVIVOR_ONLY_SOURCE')
    by_security = {}
    for _, payload, _ in store.rows('history_actions'):
        if source is None or payload['source'] == source:
            by_security.setdefault(payload['security_id'], []).append(payload)
    formations = calendar.month_ends(start, end)
    eligible = {r: [] for r in formations}
    screened_out = {r: {} for r in formations}
    for n, sid in enumerate(screened):
        p = panels.load(store, sid, source=source)
        for r, (reason, dollars) in formation_stats(p, formations, rule, by_security.get(sid, ())).items():
            if reason is None:
                eligible[r].append((-dollars, sid))
            else:
                screened_out[r][reason] = screened_out[r].get(reason, 0) + 1
        if progress and n % 500 == 0:
            progress(n, len(screened))
    rule_hash = content_hash(rule)
    blocks, acts = store.current_blocks_hash(price_table=rule['price_table']), actions_hash(store, source)
    records, ever = [], set()
    for k, r in enumerate(formations):
        ranked = sorted(eligible[r])
        members = sorted(sid for _, sid in ranked[:rule['size']])
        below = len(ranked) - len(members)
        if below:
            screened_out[r]['RANKED_BELOW_SIZE'] = below
        effective_from = calendar.offset(r, 1)
        records.append({'universe_version': version, 'rule_hash': rule_hash, 'formation_session': r, 'effective_from': effective_from,
                        'effective_to': formations[k + 1] if k + 1 < len(formations) else calendar.month_ends(effective_from, calendar.offset(effective_from, 30))[0],
                        'known_at': calendar.eligible_from(r), 'known_at_basis': 'every input is a bar on or before the formation session (bar-known-at-v1)',
                        'tier': PUBLISHER_DATED_HISTORICAL, 'members': members, 'member_count': len(members), 'eligible_count': len(ranked),
                        'screened_out': screened_out[r],
                        'smallest_member_median_dollar_volume': -ranked[len(members) - 1][0] if members else None})
        ever.update(members)
    delisted = sum(1 for sid in ever if master.get(sid, {}).get('is_delisted'))
    by_year = {}
    for r in records:
        by_year[r['formation_session'][:4]] = min(by_year.get(r['formation_session'][:4], r['member_count']), r['member_count'])
    manifest = {'kind': 'universe_manifest', 'universe_version': version, 'rule': rule, 'rule_hash': rule_hash, 'builder_code_hash': code_hash(), 'start': start, 'end': end,
                'formation_sessions': len(formations), 'first_formation': formations[0] if formations else None, 'last_formation': formations[-1] if formations else None,
                'securities_screened': len(screened), 'distinct_members': len(ever), 'members_later_delisted': delisted,
                'member_count_min': min((r['member_count'] for r in records), default=0), 'member_count_max': max((r['member_count'] for r in records), default=0),
                'member_count_min_by_year': by_year,
                'security_months_screened_out_for_unreadable_volume': sum(r['screened_out'].get(UNREADABLE_VOLUME, 0) for r in records),
                'first_formation_with_members': {str(n): next((r['formation_session'] for r in records if r['member_count'] >= n), None) for n in (500, 1000)},
                'source_blocks_hash': blocks, 'actions_hash': acts, 'records_hash': content_hash([content_hash(r) for r in records]),
                'survivorship': 'formed from every stored stock-file security including delisted ones; no present-day list, classification, master row or market '
                                'value is read',
                'tier': PUBLISHER_DATED_HISTORICAL}
    manifest['universe_hash'] = content_hash({k: manifest[k] for k in ('universe_version', 'rule_hash', 'builder_code_hash', 'start', 'end', 'source_blocks_hash', 'actions_hash',
                                                                       'records_hash')})
    with store.transaction():                                           # the records and their manifest are stored together or not at all
        for record in records:
            store.put('history_universe', {**record, 'universe_hash': manifest['universe_hash']})
        store.put('history_universe', manifest)
    return manifest


def is_current(store, manifest) -> bool:
    """Whether the bars and actions a universe was built from are the ones stored now. The bars are every current block
    of every screened security, from whichever price table each block came."""
    return (manifest['source_blocks_hash'] == store.current_blocks_hash(price_table=manifest['rule']['price_table'])
            and manifest['actions_hash'] == actions_hash(store))


def manifests(store) -> list:
    """Every stored universe manifest, oldest first."""
    return [payload for _, payload, _ in store.rows('history_universe') if payload.get('kind') == 'universe_manifest']


def load(store, universe_hash=None, *, require_current=False) -> dict:
    """{'manifest': ..., 'records': [formation records in order]}. Without a hash: the one stored universe that was built
    from the bars and actions stored now. A universe built from other bars is stale and is never chosen by default; it
    stays in the database and loads intact when it is named. Records belong to a universe by its hash, so two builds can
    never be mistaken for each other."""
    found, records = [], {}
    for _, payload, _ in store.rows('history_universe'):
        if payload.get('kind') == 'universe_manifest':
            found.append(payload)
        else:
            records.setdefault(payload.get('universe_hash'), []).append(payload)
    if not found:
        return {'manifest': None, 'records': []}
    if universe_hash:
        chosen = next((m for m in found if m['universe_hash'] == universe_hash), None)
        if chosen is None:
            raise ValueError('UNKNOWN_UNIVERSE')
        if require_current and not is_current(store, chosen):
            raise ValueError('UNIVERSE_IS_STALE')
    else:
        current = [m for m in found if is_current(store, m)]
        if not current:
            raise ValueError('UNIVERSE_IS_STALE')                       # the stored bars or actions changed since every stored universe was built
        if len({m['universe_hash'] for m in current}) > 1:
            raise ValueError('UNIVERSE_HASH_REQUIRED')                  # more than one rule or period fits the stored bars: say which
        chosen = current[0]
    mine = sorted(({k: v for k, v in r.items() if k != 'universe_hash'} for r in records.get(chosen['universe_hash'], [])), key=lambda r: r['formation_session'])
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
