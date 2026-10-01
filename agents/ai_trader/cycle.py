"""The firm's day: morning run (exits, management cards, new tickets), operator answers, 15:50 check.

All functions take a ``snapshot`` built read-only from the Official reads:
  {'session': 'YYYY-MM-DD', 'next_session': 'YYYY-MM-DD',
   'quotes': {T: {'bid','ask','ts'}}, 'closes': {T: [(day, close)]}, 'volumes': {T: [(day, vol)]},
   'screen': {T: row} (optional), 'official_value': Decimal (optional)}
Nothing here talks to a broker. In WATCH_ONLY mode the seats run and tickets are recorded, but no
book is filled and no value is scored.
"""
from __future__ import annotations

import time as _time
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from agents.ai_trader import control, risk, seats, tools
from agents.ai_trader.model import BudgetedModels, BudgetExhausted, ModelError
from agents.ai_trader.store import BOOKS, StoreError

D = Decimal
ET = ZoneInfo('America/New_York')
ENTRY_DEADLINE = time(15, 30)
QUOTE_CLOCK_SKEW_SECONDS = 5
MORNING_TIME_BUDGET_SECONDS = 360   # stop starting new model calls after six minutes


class CycleError(RuntimeError):
    pass


# ---------------------------------------------------------------- helpers
def _marks(snapshot):
    return {t: D(str(q['bid'])) for t, q in snapshot['quotes'].items() if q.get('bid')}


def _fresh(snapshot, t, now):
    q = snapshot['quotes'].get(t)
    if not q or not q.get('bid') or not q.get('ask') or not 0 < q['bid'] <= q['ask']:
        return False
    age = (now - q['ts']).total_seconds()
    return -QUOTE_CLOCK_SKEW_SECONDS <= age <= 60


def _ma200(snapshot, t):
    rows = [c for _, c in sorted(snapshot['closes'].get(t, []))]
    return D(str(sum(rows[-200:]) / 200)) if len(rows) >= 200 else None


def sessions_between(entry_day: str, today: str, sessions=None) -> int:
    """Market sessions after the entry day up to and including today."""
    if sessions is not None:
        return sum(1 for d in sessions if entry_day < d <= today)
    from agents.operator import MarketSchedule
    schedule = MarketSchedule()
    d, end, n = date.fromisoformat(entry_day) + timedelta(days=1), date.fromisoformat(today), 0
    while d <= end:
        if schedule.should_run(datetime.combine(d, time(10, 0), ET), asset_class='stock', stage=1):
            n += 1
        d += timedelta(days=1)
    return n


def _prepare(store, spec, snapshot):
    pinned = store.meta('prompts_sha256')
    current = seats.prompts_sha256()
    if pinned and pinned != current:
        raise CycleError('PROMPT_CHANGED_THIS_IS_A_NEW_TRIAL')
    store.bind_spec(spec)
    if not pinned:
        store.set_meta('prompts_sha256', current)
    if store.mode() == 'RETIRED':
        raise CycleError('BOOK_RETIRED')


def _sell(store, book, t, qty, snapshot, now, ticket_id, reason, settle_day):
    q = snapshot['quotes'][t]
    price = D(str(q['bid']))
    realized = book.sell(t, qty, price, settle_day)
    store.record_fill(now, book.name, t, 'sell', qty, price, price, ticket_id, reason, realized)


def _mirror_c(store, a_ticket, snapshot, now, reason, fraction=None):
    """Book C mirrors book A's exit day (and trim fraction). If C's quote is unusable now, the order is
    parked on the position and the C sweep completes it at the next check."""
    c = store.book('C')
    for t, p in list(c.positions.items()):
        if p.get('a_ticket') != a_ticket:
            continue
        if _fresh(snapshot, t, now):
            qty = D(p['quantity']) * (D(str(fraction)) if fraction else 1)
            _sell(store, c, t, qty, snapshot, now, a_ticket, 'MIRROR_' + reason, snapshot['next_session'])
        else:
            p['pending_mirror'] = 'exit' if not fraction else str(fraction)
    store.save_book(c)


def _sweep_c(store, snapshot, now):
    """Close C positions whose A trade is gone, and complete parked mirror orders."""
    a_tickets = {p['ticket_id'] for p in store.book('A').positions.values()}
    c, out = store.book('C'), []
    for t, p in list(c.positions.items()):
        pending = p.get('pending_mirror')
        if (p['a_ticket'] not in a_tickets or pending) and _fresh(snapshot, t, now):
            if p['a_ticket'] not in a_tickets or pending == 'exit':
                qty = D(p['quantity'])
            else:
                qty = D(p['quantity']) * D(pending)
            p.pop('pending_mirror', None)
            _sell(store, c, t, qty, snapshot, now, p['a_ticket'], 'MIRROR_SWEEP', snapshot['next_session'])
            out.append({'book': 'C', 'ticker': t, 'action': 'EXIT', 'reason': 'MIRROR_SWEEP'})
    store.save_book(c)
    return out


# ---------------------------------------------------------------- code-owned exits
def code_exits(store, spec, snapshot, now, *, protective=False):
    """The ticket's invalidation price and time stop, and (at 15:50) the v1.6 protective rule.
    Books A and B; book C only mirrors A. Missing or stale quotes hold and are recorded."""
    out = []
    for name in ('A', 'B'):
        book = store.book(name)
        for t, p in list(book.positions.items()):
            if not _fresh(snapshot, t, now):
                out.append({'book': name, 'ticker': t, 'action': 'HOLD_QUOTE_UNAVAILABLE'})
                continue
            bid = D(str(snapshot['quotes'][t]['bid']))
            reason = None
            if bid <= D(p['invalidation_price']):
                reason = 'INVALIDATION_PRICE'
            elif not protective and int(p['sessions_held']) >= int(p['time_stop_sessions']):
                reason = 'TIME_STOP'
            elif protective:
                ma = _ma200(snapshot, t)
                if bid <= D(p['average_cost']) * (1 - spec.protective_stop):
                    reason = 'PROTECTIVE_HARD_STOP'
                elif ma is not None and bid <= ma:
                    reason = 'PROTECTIVE_MA200'
            if reason:
                _sell(store, book, t, D(p['quantity']), snapshot, now, p['ticket_id'], reason, snapshot['next_session'])
                out.append({'book': name, 'ticker': t, 'action': 'EXIT', 'reason': reason})
                if name == 'A':
                    store.save_book(book)
                    _mirror_c(store, p['ticket_id'], snapshot, now, reason)
                    book = store.book('A')
        store.save_book(book)
    out += _sweep_c(store, snapshot, now)
    return out


# ---------------------------------------------------------------- morning run
def morning(store, spec, snapshot, client, now, *, prices=None, sessions=None, started=None):
    _prepare(store, spec, snapshot)
    started = started if started is not None else _time.monotonic()
    day, marks, mode = snapshot['session'], _marks(snapshot), store.mode()
    report = {'day': day, 'mode': mode, 'exits': [], 'management': [], 'tickets': [], 'fills': [], 'stopped': None}
    for name in BOOKS:   # settle T+1, roll the stop baselines, count market sessions held
        book = store.book(name)
        book.settle(day)
        for p in book.positions.values():
            p['sessions_held'] = sessions_between(p['entry_day'], day, sessions)
        book.roll(day, book.value(marks))
        store.save_book(book)
    if mode == 'PAPER':
        report['exits'] = code_exits(store, spec, snapshot, now)
    models = BudgetedModels(store, spec, client, day=day, now=now, prices=prices)

    def time_left():
        return _time.monotonic() - started < MORNING_TIME_BUDGET_SECONDS

    # Management cards, once per day, for every holding (no silent holds).
    held = sorted(set(store.book('A').positions) | set(store.book('B').positions)) if mode == 'PAPER' else []
    if held and store.meta(f'manage_done:{day}') != '1':
        store.set_meta(f'manage_done:{day}', '1')     # before acting, so a retry can't trim twice
        a = store.book('A')
        pack = tools.packet(snapshot, held, a, marks, spec, store, now)
        positions = {t: {k: v for k, v in (a.positions.get(t) or store.book('B').positions.get(t)).items()
                         if k in ('average_cost', 'entry_day', 'sessions_held', 'invalidation_price', 'time_stop_sessions', 'thesis')}
                     for t in held}
        try:
            if not time_left():
                raise BudgetExhausted('time')
            cards = models.run('manage', seats.build('manage', spec=spec, tools=pack, extra={'holdings': positions}),
                               seats.SCHEMAS['manage'])['cards']
        except (BudgetExhausted, ModelError) as error:
            cards, report['stopped'] = [], f'MANAGE_{type(error).__name__}'
        by_ticker = {c['ticker']: c for c in cards if c['ticker'] in held}
        for name in ('A', 'B'):
            book = store.book(name)
            for t, p in list(book.positions.items()):
                card = by_ticker.get(t)
                frac = None
                if card is None:
                    p['unreviewed_days'] = int(p.get('unreviewed_days', 0)) + 1
                    action = 'UNREVIEWED'
                    if p['unreviewed_days'] >= 2:
                        action, frac = 'EXIT_TWO_SESSIONS_WITHOUT_A_CARD', D(1)
                else:
                    p['unreviewed_days'] = 0
                    action = card['action']
                    if action == 'exit':
                        frac = D(1)
                    elif action == 'trim':
                        frac = D(str(min(max(card.get('trim_fraction') or 0, 0.1), 0.9)))
                if frac is not None and _fresh(snapshot, t, now):
                    reason = action if action.startswith('EXIT_') else 'AI_' + action.upper()
                    _sell(store, book, t, D(p['quantity']) * frac, snapshot, now, p['ticket_id'], reason, snapshot['next_session'])
                    if name == 'A':
                        store.save_book(book)
                        _mirror_c(store, p['ticket_id'], snapshot, now, reason, None if frac == 1 else frac)
                        book = store.book('A')
                with store.connect() as db:
                    db.execute('INSERT INTO management (at,day,book,ticker,action,reason) VALUES (?,?,?,?,?,?)',
                               (now.isoformat(), day, name, t, action, (card or {}).get('reason', 'no card')))
                report['management'].append({'book': name, 'ticker': t, 'action': action})
            store.save_book(book)

    # New tickets.
    a = store.book('A')
    entries_today = len([t for t in store.tickets(day) if t['status'] in ('FILLED', 'WATCH_APPROVED')])
    allowed, why = risk.can_enter(a, spec, entries_today, a.value(marks))
    if now.astimezone(ET).time() >= ENTRY_DEADLINE:
        allowed, why = False, 'AFTER_ENTRY_DEADLINE'
    if not allowed:
        report['stopped'] = report['stopped'] or why
        return _close_day(store, spec, snapshot, now, report)
    pack = tools.packet(snapshot, list(spec.universe), a, marks, spec, store, now)
    try:
        if not time_left():
            raise BudgetExhausted('time')
        scout = models.run('scout', seats.build('scout', spec=spec, tools=pack, extra={}), seats.SCHEMAS['scout'])
    except (BudgetExhausted, ModelError) as error:
        report['stopped'] = f'SCOUT_{type(error).__name__}'
        return _close_day(store, spec, snapshot, now, report)
    seen, candidates = set(), []
    for cand in scout['candidates']:
        if cand['ticker'] in spec.universe and cand['ticker'] not in seen:
            seen.add(cand['ticker'])
            candidates.append(cand)
    candidates = candidates[: max(0, spec.entries_per_day - entries_today)]
    if len(candidates) < len(scout['candidates']):
        store.journal('scout_names_dropped', {'names': [c['ticker'] for c in scout['candidates']]}, now)
    tickets = []
    for n, cand in enumerate(candidates):
        tid = f"{day}-{cand['ticker']}-{n}"
        if any(t['ticker'] == cand['ticker'] for t in store.tickets(day)):
            continue   # one ticket per name per day: no retry after a fail, no duplicate after a crash
        if not time_left():
            report['stopped'] = 'PM_TIME_BUDGET'
            break
        try:
            ticket = models.run('pm', seats.build('pm', spec=spec, tools=pack, extra={'candidate': cand}), seats.SCHEMAS['pm'])
        except (BudgetExhausted, ModelError) as error:
            report['stopped'] = f'PM_{type(error).__name__}'
            break
        ticket['ticker'] = cand['ticker']
        fresh_quote = tools.get_quote(snapshot, cand['ticker'], now)
        fails = seats.check_ticket(ticket, spec=spec, tools=pack, book=a, entries_today=entries_today + len(tickets),
                                   now_quote=fresh_quote, weekly_hit=risk.stops(a, a.value(marks), spec)[1])
        status = 'CODE_FAILED' if fails else 'TO_CRITIC'
        store.save_ticket(tid, day, now, cand['ticker'], status, {**ticket, 'scout': cand}, {'fails': fails})
        report['tickets'].append({'id': tid, 'ticker': cand['ticker'], 'status': status, 'fails': fails})
        if not fails:
            tickets.append((tid, ticket))
    if tickets:
        try:
            if not time_left():
                raise BudgetExhausted('time')
            verdicts = models.run('critic', seats.build('critic', spec=spec, tools=pack, extra={
                'tickets': [{'ticket_id': tid, **tk} for tid, tk in tickets]}), seats.SCHEMAS['critic'])['tickets']
        except (BudgetExhausted, ModelError) as error:
            verdicts, report['stopped'] = [], f'CRITIC_{type(error).__name__}'
        by_id = {v['ticket_id']: v for v in verdicts}
        for tid, tk in tickets:
            v = by_id.get(tid) or {'verdict': 'fail', 'fail_codes': ['POLICY_VIOLATION'], 'reason': 'no critic verdict'}
            if v['verdict'] != 'pass':
                store.save_ticket(tid, day, now, tk['ticker'], 'CRITIC_FAILED', tk, {'fails': []}, v)
                _set_report(report, tid, 'CRITIC_FAILED')
                continue
            try:
                status = _approve(store, spec, snapshot, now, tid, tk, marks, mode, report)
            except StoreError as error:
                status = 'APPROVED_RISK_BLOCKED'
                store.journal('approve_blocked', {'ticket': tid, 'error': str(error)}, now)
            store.save_ticket(tid, day, now, tk['ticker'], status, tk, {'fails': []}, v)
            _set_report(report, tid, status)
    return _close_day(store, spec, snapshot, now, report)


def _set_report(report, tid, status):
    for t in report['tickets']:
        if t['id'] == tid:
            t['status'] = status


def _approve(store, spec, snapshot, now, tid, tk, marks, mode, report):
    t = tk['ticker']
    if mode != 'PAPER':
        return 'WATCH_APPROVED'
    a = store.book('A')            # reload: earlier fills today count against the caps
    entries_today = len([x for x in store.tickets(snapshot['session']) if x['status'] == 'FILLED'])
    allowed, _ = risk.can_enter(a, spec, entries_today, a.value(marks))
    if not allowed or t in a.positions or not _fresh(snapshot, t, now):
        return 'APPROVED_RISK_BLOCKED'
    ask = D(str(snapshot['quotes'][t]['ask']))
    qty, fill = risk.size(a, spec, marks, ask)
    if qty is None:
        return 'APPROVED_NOT_SIZED'
    fraction = qty * fill / a.value(marks)
    tk['a_fraction'] = str(fraction)      # book B sizes from this, not from A's starting capital
    extra = {'ticket_id': tid, 'invalidation_price': str(tk['invalidation_price']), 'time_stop_sessions': tk['time_stop_sessions'],
             'thesis': tk['thesis'], 'reference_ask': str(ask), 'a_fraction': str(fraction)}
    a.buy(t, qty, fill, snapshot['session'], extra)
    store.save_book(a)
    store.record_fill(now, 'A', t, 'buy', qty, fill, ask, tid, 'AI_ENTRY')
    report['fills'].append({'book': 'A', 'ticker': t, 'quantity': str(qty)})
    deadline = datetime.combine(now.astimezone(ET).date(), ENTRY_DEADLINE, ET)
    with store.connect() as db:
        db.execute('INSERT OR IGNORE INTO operator_cards (id,ticket_id,issued_at,expires_at) VALUES (?,?,?,?)',
                   ('B-' + tid, tid, now.isoformat(), deadline.isoformat()))
    c = store.book('C')
    eligible = [s for s in spec.universe if s not in c.positions and _fresh(snapshot, s, now)]
    pick = control.draw(spec, tid, eligible)
    if pick:
        c_ask = D(str(snapshot['quotes'][pick]['ask']))
        c_qty, c_fill = risk.size(c, spec, marks, c_ask, fraction=fraction)
        if c_qty is not None:
            c.buy(pick, c_qty, c_fill, snapshot['session'], {'ticket_id': 'C-' + tid, 'a_ticket': tid,
                                                              'invalidation_price': '0', 'time_stop_sessions': 9999})
            store.save_book(c)
            store.record_fill(now, 'C', pick, 'buy', c_qty, c_fill, c_ask, 'C-' + tid, 'RANDOM_MATCH')
            report['fills'].append({'book': 'C', 'ticker': pick, 'quantity': str(c_qty)})
    return 'FILLED'


def _close_day(store, spec, snapshot, now, report):
    """Score only paper days, and charge the AI bill from the paper start."""
    marks = _marks(snapshot)
    if store.mode() == 'PAPER':
        spent = store.spent(since=store.meta('paper_started_at'))
        vti = snapshot['quotes'].get('VTI', {}).get('bid')
        for name in BOOKS:
            book = store.book(name)
            value = book.value(marks)
            book.mark(snapshot['session'], value)
            store.save_book(book)
            store.record_value(now, snapshot['session'], name, value, spent if name in ('A', 'B') else D(0), vti,
                               snapshot.get('official_value'))
    store.journal('morning', report, now)
    return report


# ---------------------------------------------------------------- operator (book B)
def decide(store, card_id, decision, *, now, cut_fraction=None, by='operator'):
    """Record the operator's answer from the dashboard. YES/CUT wait for a fresh quote (filled by the
    scheduled tick); NO/SKIP are final. The operator may only skip or cut, never add size or a name."""
    if by != 'operator':
        raise StoreError('ONLY_THE_OPERATOR_ANSWERS')
    if decision not in ('YES', 'NO', 'SKIP', 'CUT'):
        raise StoreError('DECISION_INVALID')
    with store.connect() as db:
        card = db.execute('SELECT * FROM operator_cards WHERE id=?', (card_id,)).fetchone()
    if card is None or card['status'] != 'PENDING':
        raise StoreError('CARD_NOT_PENDING')
    if now >= datetime.fromisoformat(card['expires_at']):
        _resolve(store, card_id, 'EXPIRED', now)
        raise StoreError('CARD_EXPIRED')
    if decision in ('NO', 'SKIP'):
        return _resolve(store, card_id, decision, now)
    frac = D(1)
    if decision == 'CUT':
        frac = D(str(cut_fraction or 0))
        if not D('0.1') <= frac < D(1):
            raise StoreError('CUT_MUST_BE_SMALLER')
    return _resolve(store, card_id, 'APPROVED_AWAITING_FILL', now, cut_fraction=frac)


def fill_pending(store, spec, snapshot, now):
    """Fill approved book-B cards at a fresh quote within the limit band, before the deadline."""
    import json
    with store.connect() as db:
        cards = [dict(r) for r in db.execute("SELECT * FROM operator_cards WHERE status='APPROVED_AWAITING_FILL'")]
    out = []
    for card in cards:
        if now >= datetime.fromisoformat(card['expires_at']):
            out.append((card['id'], _resolve(store, card['id'], 'APPROVED_NOT_FILLED', now, D(card['cut_fraction']))))
            continue
        ticket = next(t for t in store.tickets() if t['id'] == card['ticket_id'])
        tk = json.loads(ticket['payload_json'])
        t = tk['ticker']
        if not _fresh(snapshot, t, now):
            continue    # try again on the next tick
        ask = D(str(snapshot['quotes'][t]['ask']))
        a_fill = next(f for f in _fills(store, 'A') if f['ticket_id'] == card['ticket_id'] and f['side'] == 'buy')
        if ask * (1 + spec.slippage) > D(a_fill['mark']) * (1 + spec.limit_band):
            continue    # price ran away; retried until the deadline, then APPROVED_NOT_FILLED
        b = store.book('B')
        b.settle(snapshot['session'])
        frac = D(card['cut_fraction'])
        a_fraction = D(tk['a_fraction']) if tk.get('a_fraction') else D(a_fill['quantity']) * D(a_fill['price']) / store.book('A').start
        marks = _marks(snapshot)
        b_entries = len([f for f in _fills(store, 'B') if f['side'] == 'buy' and f['at'][:10] == now.date().isoformat()])
        allowed, _ = risk.can_enter(b, spec, b_entries, b.value(marks))
        qty, fill = risk.size(b, spec, marks, ask, fraction=min(a_fraction, spec.max_fraction) * frac)
        if qty is None or t in b.positions or not allowed:
            out.append((card['id'], _resolve(store, card['id'], 'APPROVED_RISK_BLOCKED', now, frac)))
            continue
        b.buy(t, qty, fill, snapshot['session'], {'ticket_id': card['ticket_id'], 'invalidation_price': str(tk['invalidation_price']),
                                                   'time_stop_sessions': tk['time_stop_sessions'], 'thesis': tk['thesis']})
        store.save_book(b)
        store.record_fill(now, 'B', t, 'buy', qty, fill, ask, card['ticket_id'], 'OPERATOR_' + ('YES' if frac == 1 else 'CUT'))
        out.append((card['id'], _resolve(store, card['id'], 'YES' if frac == 1 else 'CUT', now, frac)))
    return out


def _fills(store, book):
    with store.connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM fills WHERE book=? ORDER BY id', (book,))]


def _resolve(store, card_id, status, now, cut_fraction=None):
    with store.connect() as db:
        db.execute('UPDATE operator_cards SET status=?, decided_at=?, cut_fraction=? WHERE id=?',
                   (status, now.isoformat(), None if cut_fraction is None else str(cut_fraction), card_id))
    return status


def expire_cards(store, now):
    with store.connect() as db:
        rows = db.execute("SELECT id, expires_at FROM operator_cards WHERE status='PENDING'").fetchall()
    out = []
    for r in rows:
        if now >= datetime.fromisoformat(r['expires_at']):
            _resolve(store, r['id'], 'EXPIRED', now)   # unanswered counts as a skip
            out.append(r['id'])
    return out


# ---------------------------------------------------------------- 15:50 protective check
def protective(store, spec, snapshot, now):
    _prepare(store, spec, snapshot)
    if store.mode() != 'PAPER':
        return []
    expire_cards(store, now)
    out = code_exits(store, spec, snapshot, now, protective=True)
    marks = _marks(snapshot)
    for name in BOOKS:      # end-of-day baseline for tomorrow's daily stop
        book = store.book(name)
        book.mark(snapshot['session'], book.value(marks))
        store.save_book(book)
    store.journal('protective', out, now)
    return out
