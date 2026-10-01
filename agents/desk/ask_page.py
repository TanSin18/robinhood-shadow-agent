"""Ask Bubbles: ask a question about anything the desk did, from any page.

How a question travels:
  1. A form on the page posts the question to the front door (same-origin, form token, 500 characters at most).
  2. This module builds a packet from local records only: today's activity, the chosen run and step, holdings,
     checks, the team's notes, the schedule and the rule-book entries that match the question.
  3. The front door runs the installed runtime's own `python -m agents.analyst.cli ask` as a separate process.
     That code (not the dashboard) calls the model: no tools, a reserved budget, strict JSON, and every number
     in the answer checked against the packet by code. It stores the question, the answer and the checks.
  4. The browser is sent to /ask, which shows the conversation from the analyst database (read-only).

Nothing here can trade, and no answer is read by the trading path. The public read-only mirror never routes
this page and never shows a form.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .analyst_page import default_path
from .charts import esc, short_time
from .rulebook import LIMITS, catalogue
from .team import TEAM

ET = ZoneInfo('America/New_York')
SUGGESTED = ('What did the desk do today, and why?', 'Why this pick and not the others?', 'What would make us sell what we hold?',
             'How is my paper book doing against the market?', 'What is the market regime and what does it mean?',
             'Which agents ran today and what did each one say?', 'What is the next thing that will happen, and when?')
SCHEDULE = ((time(10, 0), '10:00 ET', 'official run: read market, signals, AI gate, risk checks, paper fills, decision record'),
            (time(10, 5), '10:05-12:00 ET', 'team morning notes (advisory), written after the official run completed'),
            (time(15, 30), '15:30 ET', 'last moment to answer an approval card; it fills only at a fresh price within the limit'),
            (time(15, 50), '15:50-15:58 ET', 'protective check: sell at the bid if 8% below cost, at/below the 200-day average, or ETF momentum not positive'),
            (time(16, 15), '16:15-19:30 ET', 'after-close job: daily bars, regime model, shadow Kelly, exit guard, chop gate, news, team close notes'),
            (time(16, 50), '16:50 ET', 'nightly S&P 500 screen (research only)'))
WEEKLY = 'Friday 16:30 ET: weekly report'
WORD = re.compile(r'[a-z0-9%]{4,}')
STOP = {'what', 'when', 'where', 'which', 'this', 'that', 'with', 'from', 'have', 'does', 'will', 'would', 'about', 'today', 'they', 'there',
        'were', 'your', 'make', 'much', 'many', 'into', 'than', 'then', 'them', 'been', 'being', 'could', 'should', 'step', 'this', 'done'}
SEATS = {'pip': 'Blossom (research)', 'biscuit': 'Buttercup (filings and news)', 'maple': 'Mayor (portfolio)', 'pickle': 'Mojo Jojo (critic)'}
STEP_WHO = {'evidence': 'Scanners (code)', 'research': 'Blossom (research, AI)', 'portfolio': 'Mayor (portfolio, AI)', 'critic': 'Mojo Jojo (critic, AI)',
            'risk': 'Prof. X (safety rules, code)', 'final': 'Recorded outcome'}
NOTICES = {
    'BUSY': 'Bubbles is still answering the previous question. Give it a few seconds and ask again.',
    'TIMEOUT': 'The model took too long and the question was dropped. Nothing was guessed; ask again.',
    'RUNTIME_NOT_READY': 'Asking needs the latest runtime release and the analyst desk set up. Install the release shown in the handoff, then ask again.',
    'ANALYST_PAUSED': 'The analyst desk is paused, so no model is called. Resume it with: python -m agents.analyst.cli resume --official-database …/data/agent.db',
    'DAILY_QUESTION_LIMIT': 'Today’s limit of 40 questions is used up. It resets tomorrow (New York time).',
    'DAILY_QUESTION_BUDGET': 'Questions have used their share of today’s AI budget ($0.50 of the $1 cap; the rest is kept for the team’s notes). It resets tomorrow.',
    'EMPTY_QUESTION': 'Type a question first.',
    'QUESTION_TOO_LONG': 'Keep the question under 500 characters.',
    'INVALID_REQUEST': 'The question could not be read. Try again.',
    'RECORDS_UNAVAILABLE': 'The records could not be read just now, so nothing was asked. Try again in a minute.',
}
TOKEN_BUDGET_CHARS = 52000        # about 13,000 tokens of packet; the model's registered input cap is 18,000


# ------------------------------------------------------------------ records
def load(official_db, limit=30):
    path = default_path(official_db)
    if not path.is_file():
        return {'exists': False, 'qa': []}
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=0.2)
    try:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='qa'").fetchone():
            return {'exists': True, 'qa': []}
        rows = db.execute('SELECT at, context, question, payload_json, checks_json, status FROM qa ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return {'exists': True, 'qa': [{**json.loads(p or '{}'), 'at': a, 'context': c, 'question': q, '_checks': json.loads(k or '{}'), 'status': s}
                                       for a, c, q, p, k, s in rows]}
    except (sqlite3.Error, ValueError) as error:
        return {'exists': True, 'qa': [], 'error': type(error).__name__}
    finally:
        db.close()


def _num(v):
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return None


def _et(stamp, fmt='%a %b %-d, %-I:%M %p ET'):
    try:
        return datetime.fromisoformat(str(stamp)).astimezone(ET).strftime(fmt)
    except (TypeError, ValueError):
        return None


def _today(stamp, now):
    try:
        return datetime.fromisoformat(str(stamp)).astimezone(ET).date() == now.date()
    except (TypeError, ValueError):
        return False


def _rules_for(question, limit=8):
    words = {w for w in WORD.findall(question.lower()) if w not in STOP}
    scored = []
    cat = catalogue()
    for g in cat.get('rule_groups') or []:
        for r in g.get('rules') or []:
            text = ' '.join(str(r.get(k) or '') for k in ('name', 'condition', 'action', 'when', 'applies_to')).lower() + ' ' + g.get('title', '').lower()
            score = sum(1 for w in words if w in text)
            if score:
                scored.append((score, {'group': g.get('title'), 'name': r.get('name'), 'when': r.get('when'), 'condition': r.get('condition'),
                                       'what_happens': r.get('action'), 'status': r.get('status'), 'source': r.get('source')}))
    scored.sort(key=lambda x: -x[0])
    issues = [{'issue': i.get('issue'), 'severity': i.get('severity')} for i in cat.get('known_issues') or []
              if any(w in str(i.get('issue')).lower() for w in words)][:4]
    return [r for _, r in scored[:limit]], issues


def _next_event(now):
    """The next scheduled thing after `now` (New York time). Weekends roll to Monday; exchange holidays are not known here."""
    day = now.date()
    if now.weekday() < 5:
        for at, label, what in SCHEDULE:
            if now.time() < at:
                return f'today {label}: {what}'
    day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return f'{day.strftime("%A %b %-d")} {SCHEDULE[0][1]}: {SCHEDULE[0][2]} (if the market is open that day)'


def _activity(state, now):
    """Everything recorded today, oldest first, with New York times."""
    pf = state.get('portfolio') or {}
    a = state.get('analyst') or {}
    events = []

    def add(stamp, what):
        if _today(stamp, now):
            events.append((str(stamp), {'time': _et(stamp, '%-I:%M %p ET'), 'what': what}))
    for t in pf.get('tripwire') or []:
        add(t.get('created_at'), f'Account tripwire check: {t.get("status")}' + (f' ({t.get("change_class")})' if t.get('change_class') else ''))
    for r in state.get('decision_room') or []:
        group = (r.get('category') or {}).get('group')
        add(r.get('timestamp'), ('Official run finished: ' if group == 'official' else 'Build/test run finished: ') + str((r.get('header') or {}).get('outcome') or r.get('decision_type'))
            + '. ' + str(r.get('decision_reason') or '')[:220])
    for f in pf.get('fills') or []:
        add(f.get('timestamp'), f'Paper fill, account {f.get("track")}: {f.get("side")} {f.get("quantity")} {f.get("ticker")} at {f.get("price")} ({f.get("status")})')
    for p in (state.get('research') or {}).get('protective') or []:
        add(p.get('timestamp'), 'Protective check: ' + (f'sold {p.get("fired")} position(s)' if p.get('fired') else 'nothing sold')
            + (f'; still holding {", ".join(p.get("held") or [])}' if p.get('held') else '') + (f'; status {p.get("status")}' if p.get('status') else '')
            + (f'; error {p.get("error_type")}' if p.get('error_type') else ''))
    for key, label in (('morning', 'Bubbles wrote the morning note'), ('close', 'Bubbles wrote the after-close note')):
        n = a.get(key) or {}
        add(n.get('at'), f'{label}: {str(n.get("headline") or "")[:160]}')
    for seat, n in (a.get('team') or {}).items():
        add(n.get('at'), f'{SEATS.get(seat, seat)} wrote a note')
    for key, label in (('regime', 'Regime model refit'), ('guard', 'Exit guard and chop gate computed')):
        add((a.get(key) or {}).get('at'), label)
    events.sort(key=lambda e: e[0])
    return [e for _, e in events][-30:]


def _run(review, step):
    from .workspace import outcome
    checks = review.get('checks') or {}
    stages = [{'step': s.get('label') or s.get('key'), 'who': STEP_WHO.get(s.get('key')), 'status': s.get('status_label'),
               'summary': str(s.get('summary') or '')[:320]} for s in review.get('stages') or []]
    log = [{'time': _et(e.get('time'), '%-I:%M:%S %p ET'), 'who': STEP_WHO.get(e.get('actor'), e.get('actor')), 'event': e.get('title'),
            'detail': [str(d)[:220] for d in (e.get('detail') or [])[:4]]} for e in (review.get('log') or [])[:24]]
    gate = review.get('ai_gate') or {}
    head = review.get('header') or {}
    out = {'id': 'run', 'when': _et(review.get('timestamp')), 'kind': (review.get('category') or {}).get('group'),
           'counts_toward_results': (review.get('category') or {}).get('counts'), 'outcome': outcome(review),
           'decision_type': review.get('decision_type'), 'decision_reason': review.get('decision_reason'),
           'signal_instruments': review.get('signal_instruments'), 'ai_gate': {'open': gate.get('open'), 'reason': gate.get('reason')},
           'took': head.get('duration'), 'ai_cost_usd': _num(head.get('api_cost_estimate_usd')), 'desk_rule': review.get('desk'),
           'exit_checks_in_run': review.get('desk_exits'), 'steps': stages, 'log': log,
           'risk_checks': checks.get('risk'), 'missing_evidence': checks.get('missing_evidence'),
           'checks_needing_attention': [{k: o.get(k) for k in ('check', 'value', 'status', 'note')} for o in checks.get('operational') or []
                                        if o.get('status') in ('warn', 'fail')],
           'ideas': [{k: c.get(k) for k in ('instrument', 'lane', 'state', 'reason', 'strategy_signal')} for lane in (review.get('lanes') or {}).values() for c in lane][:8],
           'screened_out_sample': (review.get('strategy_blocked') or [])[:8]}
    if step:
        stage = next((s for s in review.get('stages') or [] if s.get('key') == step), None)
        out['asked_about_step'] = {'step': (stage or {}).get('label') or step, 'who': STEP_WHO.get(step), 'status': (stage or {}).get('status_label'),
                                   'mandate': (stage or {}).get('mandate'), 'report': str((stage or {}).get('summary') or '')[:1200],
                                   'events': [{'event': e.get('title'), 'detail': [str(d)[:300] for d in (e.get('detail') or [])[:6]]}
                                              for e in review.get('log') or [] if e.get('actor') == step][:10]}
    return out


def build_packet(state, question, context='', run=None, step=None, now=None):
    """Records the explainer may use. Numeric blocks carry an id; code later checks every number in the answer against this packet."""
    pf = state.get('portfolio') or {}
    cap = pf.get('capsule') or {}
    a = state.get('analyst') or {}
    feats = cap.get('features') or {}
    try:
        now = (now or datetime.fromisoformat(state.get('updated_at'))).astimezone(ET)
    except (TypeError, ValueError):
        now = datetime.now(ET)
    asked = {t for t in re.findall(r'\b[A-Z]{2,5}\b', question) if t in feats}
    held = {x.get('ticker') for p in pf.get('paper') or [] for x in p.get('positions') or []}
    signals = set((cap.get('decision') or {}).get('signal_instruments') or [])
    focus = sorted(asked | held | signals | {'VTI'})
    pkt = {'context': {'id': 'context', 'asked_from': context, 'now': now.strftime('%A %b %-d %Y, %-I:%M %p ET'), 'next_scheduled': _next_event(now),
                       'safety': 'A safety stop or pause is ACTIVE' if state.get('paused') else 'paper only; real orders are blocked'},
           'schedule': {'id': 'schedule', 'every_trading_day': [{'time': label, 'what': what} for _, label, what in SCHEDULE], 'weekly': WEEKLY},
           'limits': {'id': 'limits', 'items': [{'value': v, 'meaning': m} for v, m in LIMITS]},
           'activity_today': {'id': 'activity_today', 'events': _activity(state, now)}}
    runs = state.get('decision_room') or []
    review = next((r for r in runs if run and r.get('review_id') == run), None) or (runs[0] if runs else None)
    if review:
        pkt['run'] = _run(review, step if step in STEP_WHO else None)
    if cap:
        strat = cap.get('strategies') or {}
        pkt['screen'] = {'id': 'screen', 'observed_at': _et(cap.get('observed_at')), 'momentum_ranked': (strat.get('momentum_rotation') or {}).get('ranked'),
                         'momentum_blocked': (strat.get('momentum_rotation') or {}).get('blocked'),
                         'dip_blocked_sample': dict(list(((strat.get('mean_reversion') or {}).get('blocked') or {}).items())[:6])}
    for t in focus:
        f = feats.get(t)
        if f:
            price, ma, mom, day = _num(f.get('price')), _num(f.get('ma200')), _num(f.get('momentum_126d')), _num(f.get('one_day_return'))
            pkt[f'feature:{t}'] = {'id': f'feature:{t}', 'price': price, 'ma200': ma,
                                   'pct_vs_ma200': round((price / ma - 1) * 100, 2) if price and ma else None,
                                   'momentum_126d_pct': round(mom * 100, 2) if mom is not None else None,
                                   'one_day_pct': round(day * 100, 2) if day is not None else None}
    for p in pf.get('paper') or []:
        cash = (_num(p.get('settled_cash')) or 0) + (_num(p.get('unsettled_cash')) or 0)
        positions, value = [], cash
        for x in p.get('positions') or []:
            mark = _num((p.get('marks') or {}).get(x.get('ticker'))) or _num(x.get('average_cost')) or 0
            q = _num(x.get('quantity')) or 0
            value += q * mark * (_num(x.get('multiplier')) or 1)
            positions.append({'ticker': x.get('ticker'), 'quantity': q, 'average_cost': _num(x.get('average_cost')), 'last_bid': mark})
        key = f'account:{p.get("lane")}:{p.get("track")}'
        start = _num(p.get('start')) or 0
        pkt[key] = {'id': key, 'start': start, 'cash': round(cash, 2), 'value': round(value, 2), 'change_since_start': round(value - start, 2),
                    'cash_pct_of_value': round(cash / value * 100, 1) if value else None, 'positions': positions,
                    'loss_latch_on': bool(p.get('peak_breaker_latched'))}
    real = pf.get('real')
    if real:
        last = real.get('last_check') or {}
        pkt['real_account'] = {'id': 'real_account', 'positions_held': len(real.get('positions') or []), 'last_tripwire_check': last.get('status'),
                               'note': 'the real Agentic account is read-only here; real orders are blocked; balances are shown on the Portfolio tab and are not sent to the model'}
    reg = a.get('regime') or {}
    if reg.get('status') == 'OK':
        pkt['regime'] = {'id': 'regime', 'current': reg.get('current'), **{f'p_{k}': v for k, v in (reg.get('current_probabilities') or {}).items()},
                         'sessions_in_a_row': reg.get('current_run_sessions'), 'bars_through': reg.get('last_day')}
    g = a.get('guard') or {}
    for e in g.get('exits') or []:
        if e.get('status') == 'OK':
            key = f'guard:{e.get("account")}:{e.get("ticker")}'
            pkt[key] = {'id': key, **{k: e.get(k) for k in ('last_close', 'gain_pct', 'peak_gain_pct', 'guard_stop', 'guard_stop_rule',
                                                           'distance_to_guard_pct', 'verdict', 'triggers')}}
    for t in focus:
        c = (g.get('chop') or {}).get(t)
        if c and c.get('status') == 'OK':
            pkt[f'chop:{t}'] = {'id': f'chop:{t}', **{k: c.get(k) for k in ('label', 'adx14', 'atr14_pct', 'stretch_vs_ma50_atr', 'gate')}}
        k = ((a.get('kelly') or {}).get('tickers') or {}).get(t)
        if k:
            best = k.get('regime') or {}
            pkt[f'kelly:{t}'] = {'id': f'kelly:{t}', 'risk_engine_fraction': k.get('risk_engine_fraction'),
                                 'kelly_disciplined': best.get('kelly_disciplined'), 'kelly_half': best.get('kelly_half'), 't_stat': best.get('t_stat')}
    notes = {}
    for key in ('morning', 'close'):
        n = a.get(key)
        if n:
            notes[f'bubbles_{key}_note'] = {'written': _et(n.get('at')), **{k: n.get(k) for k in ('headline', 'market_read', 'decision_read', 'regime_read',
                                                                                              'auction_read', 'watch')},
                                            'news': [{k: x.get(k) for k in ('ticker', 'sentiment', 'note')} for x in (n.get('news') or [])[:6]]}
    for seat, n in (a.get('team') or {}).items():
        notes[SEATS.get(seat, seat)] = {'written': _et(n.get('at')), **{k: v for k, v in n.items() if k not in ('cited_numbers', '_checks', 'day', 'at')}}
    waiting = [name for seat, name in SEATS.items() if seat not in (a.get('team') or {})]
    pkt['team_status'] = {'id': 'team_status', 'prof_x': 'safety rules (code, not a model): checks every order inside each run',
                          'wrote_notes': [SEATS[s] for s in (a.get('team') or {})] + (['Bubbles (explainer)'] if a.get('morning') or a.get('close') else []),
                          'not_written_yet': waiting,
                          'when_they_write': 'every trading day: after the 10:00 ET official run, and again in the after-close job; advisory only, no trade reads their notes'}
    if notes:
        pkt['TEAM_NOTES'] = notes
    mem = a.get('memory') or {}
    if mem.get('scorecard') or mem.get('lessons'):
        card = mem.get('scorecard') or {}
        pkt['memory'] = {'id': 'memory', 'what': 'calls made after the close are scored at the next close; no verdict before 60 scored calls',
                         **{k: card.get(k) for k in ('sentiment_calls_scored', 'hits', 'hit_rate_pct', 'needed_before_any_verdict', 'verdict',
                                                     'calls_waiting_for_next_close')},
                         'recent_calls': [{k: c.get(k) for k in ('day', 'ticker', 'call', 'next_day_return_pct', 'hit')} for c in (mem.get('calls') or [])
                                          if c.get('kind') == 'sentiment'][:8],
                         'lessons': [{k: x.get(k) for k in ('day', 'lesson', 'check_next')} for x in (mem.get('lessons') or [])[:5]]}
    spent = a.get('spent') or {}
    pkt['ai_budget'] = {'id': 'ai_budget', 'analyst_spend_today_usd': (_num(spent.get('usd')) or 0) if spent.get('day') == now.date().isoformat() else 0,
                        'analyst_daily_cap_usd': 1.0, 'questions_share_usd': 0.5, 'official_daily_cap_usd': 0.4}
    rules, issues = _rules_for(question + ' ' + context)
    pkt['rule_book_matches'] = rules
    if issues:
        pkt['known_issues'] = issues
    # Keep the packet inside the model's registered input size: drop the bulkiest optional blocks first.
    for drop in ('screen', 'rule_book_matches', 'TEAM_NOTES'):
        if len(json.dumps(pkt, default=str)) <= TOKEN_BUDGET_CHARS:
            break
        if drop == 'rule_book_matches':
            pkt[drop] = pkt[drop][:3]
        elif drop == 'TEAM_NOTES' and drop in pkt:
            pkt[drop] = {k: {x: (str(y)[:400] if isinstance(y, str) else y) for x, y in v.items() if x in ('written', 'headline', 'decision_read', 'base_rate',
                                                                                                          'summary', 'portfolio_read', 'verdicts')}
                         for k, v in pkt[drop].items()}
        else:
            pkt.pop(drop, None)
    return pkt


# ------------------------------------------------------------------ asking (the front door calls this)
def submit(official_db, question, context, packet, *, timeout=120):
    """Hands the question to the installed runtime in a separate process and returns its status word.
    The dashboard itself never talks to a model and never sees the API key."""
    root = Path(official_db).resolve().parents[1]
    python = root / '.venv' / 'bin' / 'python'
    env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}        # the runtime's own code, not this dashboard copy
    try:
        done = subprocess.run([str(python) if python.is_file() else sys.executable, '-m', 'agents.analyst.cli', 'ask', '--official-database', str(official_db)],
                              input=json.dumps({'question': question, 'context': context, 'packet': packet}, default=str),
                              capture_output=True, text=True, timeout=timeout, cwd=str(root), env=env, check=False)
    except subprocess.TimeoutExpired:
        return 'TIMEOUT'
    except OSError:
        return 'RUNTIME_NOT_READY'
    if done.returncode != 0:
        return 'RUNTIME_NOT_READY'
    try:
        return str(json.loads(done.stdout.strip().splitlines()[-1])['status'])
    except (ValueError, IndexError, KeyError, TypeError):
        return 'RUNTIME_NOT_READY'


# ------------------------------------------------------------------ page pieces
def _form(token, context, *, run='', step='', question=None, label='Ask', cls='ask-bar', placeholder='', uid='q'):
    hidden = (f'<input type="hidden" name="csrf" value="{esc(token)}"><input type="hidden" name="context" value="{esc(context)}">'
              + (f'<input type="hidden" name="run" value="{esc(run)}">' if run else '') + (f'<input type="hidden" name="step" value="{esc(step)}">' if step else ''))
    if question is not None:
        return (f'<form class="ask-preset ask-form" method="post" action="/ask/question">{hidden}<input type="hidden" name="question" value="{esc(question)}">'
                f'<button type="submit" class="ask-chip">{esc(question)}</button></form>')
    return (f'<form class="{cls} ask-form" method="post" action="/ask/question">{hidden}<label class="ask-label" for="ask-{esc(uid)}">{esc(label)}</label>'
            f'<input id="ask-{esc(uid)}" name="question" type="text" maxlength="500" required placeholder="{esc(placeholder)}" autocomplete="off">'
            '<button type="submit">Ask</button></form>')


def ask_bar(state, context, placeholder='Ask about anything the desk did, is doing or will do…', uid='page'):
    """The question box. Rendered only when the front door supplied a form token (never on the public mirror)."""
    token = (state or {}).get('inbox_csrf')
    return _form(token, context, label='Ask Bubbles', placeholder=placeholder, uid=uid) if token else ''


def floating(token, context):
    """A small 'Ask Bubbles' button in the corner of every page; it opens a question box without leaving the page."""
    if not token:
        return ''
    return ('<details class="ask-fab"><summary><img src="/assets/avatars/bubbles-explainer.svg" width="28" height="28" alt="">Ask Bubbles</summary>'
            '<div class="ask-pop"><p>Ask about anything on this page or anything the desk did today. Answers come from the records only.</p>'
            + _form(token, context, label='Your question', cls='ask-bar ask-bar-pop', placeholder='e.g. Why did we buy SOXX?', uid='fab')
            + '<a href="/ask">See earlier questions →</a></div></details>')


def step_ask(token, review, key, who, when):
    """Inside the Decision room: ask about one step of one run."""
    if not token:
        return ''
    who = {'final': 'the final outcome', 'evidence': 'the scanners'}.get(key, who)
    context = f'Decision room · {who} · run of {when}'
    run = str(review.get('review_id') or '')
    presets = (('Why did this run end the way it did?', 'What would have changed the outcome?') if key == 'final' else
               (f'What did {who} do in this run, and why?', f'What would have changed the result of {who}?'))
    return ('<div class="ask-step"><h4>Ask Bubbles about this step</h4>'
            + _form(token, context, run=run, step=key, label='Your question', cls='ask-bar', placeholder='e.g. Why was this step skipped?', uid=f'{run[:8]}-{key}')
            + '<div class="ask-chips">' + ''.join(_form(token, context, run=run, step=key, question=q) for q in presets) + '</div></div>')


def render(state):
    data = state.get('ask') or {'exists': False, 'qa': []}
    token = state.get('inbox_csrf')
    head = ('<div class="room-head"><div><h1>Ask Bubbles</h1><p>Ask anything about what the desk did, is doing or will do next. Bubbles answers '
            'from the records and the rule book only, names its sources, and says so when the records do not hold the answer. '
            'It cannot trade and nothing it says is read by the trading rules.</p></div></div>')
    notice = NOTICES.get(state.get('ask_notice'))
    banner = f'<p class="ask-notice" role="status">{esc(notice)}</p>' if notice else ''
    if not data.get('exists'):
        return head + banner + ('<section class="v10-panel"><h3>Not set up yet</h3><p>Asking needs the analyst desk. Install the latest release and run '
                                '<code>python -m agents.analyst.cli init --official-database …/data/agent.db</code>.</p></section>')
    form = ask_bar(state, 'Ask page', uid='main') or '<p class="v10-empty">Questions can be asked on your own dashboard. This view is read-only.</p>'
    chips = '<div class="ask-chips">' + ''.join(_form(token, 'Ask page', question=q) if token else f'<span class="ask-chip">{esc(q)}</span>' for q in SUGGESTED) + '</div>'
    items = ''
    for i, x in enumerate(data.get('qa') or []):
        flags = (x.get('_checks') or {}).get('flags') or []
        if x.get('status') == 'ANSWERED':
            follow = [q for q in (x.get('follow_ups') or [])[:3] if isinstance(q, str) and q.strip()]
            body = (f'<p class="ask-a">{esc(x.get("answer"))}</p>'
                    + (f'<p class="ask-missing"><b>Not in the records:</b> {esc(x.get("missing"))}</p>' if str(x.get('missing') or '').strip() else '')
                    + ('<p class="an-ok">Code check passed: every number in this answer appears in the records.</p>' if not flags else
                       f'<p class="an-flag">Code flagged this answer, treat it with care: {esc(", ".join(flags))}</p>')
                    + (f'<p class="ask-src">Sources: {esc(", ".join(str(s) for s in x.get("sources") or []))}</p>' if x.get('sources') else '')
                    + ('<div class="ask-chips">' + ''.join(_form(token, 'Ask page', question=q[:500]) if token else f'<span class="ask-chip">{esc(q)}</span>'
                                                        for q in follow) + '</div>' if follow else ''))
        else:
            body = (f'<p class="an-flag">No answer ({esc(x.get("status"))}' + (f': {esc(x.get("reason"))}' if x.get('reason') else '')
                    + '). Nothing was guessed. Ask again in a minute, or rephrase.</p>')
        items += (f'<li class="ask-item"{" id=latest" if i == 0 else ""}><div class="ask-q"><span>You</span><p>{esc(x.get("question"))}</p>'
                  f'<small>{esc(short_time(x.get("at")))}' + (f' · {esc(x.get("context"))}' if x.get('context') else '') + '</small></div>'
                  f'<div class="ask-ans"><img src="/assets/avatars/bubbles-explainer.svg" width="36" height="36" alt="Bubbles"><div>{body}</div></div></li>')
    history = f'<ol class="ask-list">{items}</ol>' if items else '<p class="v10-empty">No questions yet. Try one of the suggestions above.</p>'
    how = ('<details class="ask-how"><summary>How an answer is made</summary><ol><li>Your question and a packet of today’s records (the run and its steps, '
           'fills, holdings, checks, the team’s notes, the schedule, matching rule-book entries) go to one model call. No tools, no web, no broker.</li>'
           '<li>The model must answer from the packet and list its sources. If the packet does not hold the answer it must say what is missing.</li>'
           '<li>Code then checks every number in the answer against the packet and flags any it cannot find, plus hype or order-like wording.</li>'
           '<li>The question, answer and checks are stored in the analyst database. Each question costs about one cent; questions may use at most '
           '$0.50 of the analyst desk’s $1 daily cap, 40 a day.</li></ol></details>')
    return (head + banner + f'<section class="v10-panel ask-panel">{form}{chips}{how}</section>'
            + f'<section class="v10-panel"><h3>Conversation <small>newest first</small></h3>{history}</section>')
