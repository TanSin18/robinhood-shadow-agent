"""Desk memory: the team's notes build on the day before instead of starting from nothing.

Three things, all advisory (nothing here is read by the trading path):

  calls      every checkable call made after the close is written down: each news-sentiment call per ticker
             (Bubbles and Buttercup) and the regime label. At the next close, code scores it against what the
             market actually did (the ticker's next close-to-close move, and the same move for SPY).
  scorecard  the running record of those scores. It says TOO_FEW_TO_JUDGE until there are MIN_SAMPLE scored
             calls; only then can it say whether the calls beat a coin flip. This is the evidence that would be
             needed before news could ever be proposed as a trading filter.
  lessons    at most two process lessons a day from the critic, carried forward for LESSON_SESSIONS days.

`block()` returns packet entries (the last note, how its calls turned out, the scorecard, open lessons) that are
added to every seat's packet, so each note starts from what was said and what then happened.
"""
from __future__ import annotations

import json
import math

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY, day TEXT, at TEXT, seat TEXT, kind TEXT, ticker TEXT, call TEXT, "
    "basis_day TEXT, note TEXT, scored_day TEXT, outcome_json TEXT, UNIQUE(day, seat, kind, ticker))",
    "CREATE TABLE IF NOT EXISTS lessons (id INTEGER PRIMARY KEY, day TEXT, at TEXT, job TEXT, seat TEXT, lesson TEXT, check_next TEXT, "
    "UNIQUE(day, job, lesson))",
)
MIN_SAMPLE = 60           # scored calls needed before the scorecard may say anything
LESSON_SESSIONS = 5       # how many days a lesson stays in front of the team
SEATS = {'bubbles': '{job}', 'biscuit': '{job}:biscuit'}


def ensure(store):
    with store.connect() as db:
        for stmt in SCHEMA:
            db.execute(stmt)


def _note(store, day, kind):
    with store.connect() as db:
        row = db.execute('SELECT payload_json FROM notes WHERE day=? AND kind=? ORDER BY id DESC LIMIT 1', (day, kind)).fetchone()
    try:
        return json.loads(row[0]) if row else None
    except ValueError:
        return None


def record(store, day, job, basis_day, now, *, regime=None):
    """After a job's notes are written: store the critic's lessons, and (after the close only, where the next
    close-to-close move is a clean test) every sentiment call and the regime label."""
    ensure(store)
    stored = {'calls': 0, 'lessons': 0}
    critic = _note(store, day, f'{job}:pickle') or {}
    with store.connect() as db:
        for x in (critic.get('lessons') or [])[:2]:
            lesson = ' '.join(str(x.get('lesson') or '').split())[:300]
            if lesson:
                cur = db.execute('INSERT OR IGNORE INTO lessons(day,at,job,seat,lesson,check_next) VALUES (?,?,?,?,?,?)',
                                 (day, now.isoformat(), job, 'pickle', lesson, ' '.join(str(x.get('check_next') or '').split())[:300]))
                stored['lessons'] += cur.rowcount
        if job != 'close' or not basis_day:
            return stored
        for seat, kind in SEATS.items():
            note = _note(store, day, kind.format(job=job)) or {}
            for n in note.get('news') or []:
                if n.get('sentiment') in ('positive', 'negative') and n.get('ticker'):
                    db.execute('INSERT OR REPLACE INTO calls(day,at,seat,kind,ticker,call,basis_day,note) VALUES (?,?,?,?,?,?,?,?)',
                               (day, now.isoformat(), seat, 'sentiment', str(n['ticker'])[:12], n['sentiment'], basis_day, str(n.get('note') or '')[:240]))
                    stored['calls'] += 1
        if regime:
            db.execute('INSERT OR REPLACE INTO calls(day,at,seat,kind,ticker,call,basis_day,note) VALUES (?,?,?,?,?,?,?,?)',
                       (day, now.isoformat(), 'model', 'regime', 'VTI', str(regime), basis_day, ''))
            stored['calls'] += 1
    return stored


def _next_move(bars, basis_day):
    """Close-to-close % move of the first session after basis_day, or None when that session's bar is not in yet."""
    closes = [(b['day'], b['close']) for b in bars or [] if b.get('close')]
    for i, (d, c) in enumerate(closes):
        if d == basis_day and i + 1 < len(closes) and c:
            return closes[i + 1][0], round((closes[i + 1][1] / c - 1) * 100, 3)
    return None


def score(store, bars):
    """Scores every call whose next session has closed. Returns how many were scored."""
    ensure(store)
    with store.connect() as db:
        open_calls = db.execute('SELECT id, kind, ticker, call, basis_day FROM calls WHERE scored_day IS NULL').fetchall()
    done = 0
    for call_id, kind, ticker, call, basis in open_calls:
        move = _next_move(bars.get(ticker), basis)
        if not move:
            continue
        scored_day, ret = move
        out = {'next_day_return_pct': ret}
        if kind == 'sentiment':
            spy = _next_move(bars.get('SPY'), basis)
            out['spy_return_pct'] = spy[1] if spy else None
            out['hit'] = (ret > 0) if call == 'positive' else (ret < 0)
            if spy:
                out['hit_vs_spy'] = (ret > spy[1]) if call == 'positive' else (ret < spy[1])
        with store.connect() as db:
            db.execute('UPDATE calls SET scored_day=?, outcome_json=? WHERE id=?', (scored_day, json.dumps(out), call_id))
        done += 1
    return done


def _rows(store, where='', args=()):
    with store.connect() as db:
        rows = db.execute('SELECT day, seat, kind, ticker, call, basis_day, note, scored_day, outcome_json FROM calls ' + where, args).fetchall()
    return [{'day': d, 'seat': s, 'kind': k, 'ticker': t, 'call': c, 'basis_day': b, 'note': n, 'scored_day': sd,
             **(json.loads(o) if o else {})} for d, s, k, t, c, b, n, sd, o in rows]


def scorecard(store):
    """The running record, by code. Deliberately modest: no verdict below MIN_SAMPLE scored calls."""
    ensure(store)
    scored = _rows(store, "WHERE scored_day IS NOT NULL")
    sent = [r for r in scored if r['kind'] == 'sentiment']
    n, hits = len(sent), sum(1 for r in sent if r.get('hit'))
    rel = [r for r in sent if r.get('hit_vs_spy') is not None]
    avg = lambda xs: round(sum(xs) / len(xs), 3) if xs else None
    z = (hits - n / 2) / math.sqrt(n / 4) if n else 0.0
    verdict = ('TOO_FEW_TO_JUDGE' if n < MIN_SAMPLE else 'BETTER_THAN_A_COIN_FLIP' if z >= 2 else 'WORSE_THAN_A_COIN_FLIP' if z <= -2
               else 'NO_EVIDENCE_IT_BEATS_A_COIN_FLIP')
    regimes = {}
    for r in scored:
        if r['kind'] == 'regime' and r.get('next_day_return_pct') is not None:
            regimes.setdefault(r['call'], []).append(abs(r['next_day_return_pct']))
    with store.connect() as db:
        waiting = db.execute('SELECT COUNT(*) FROM calls WHERE scored_day IS NULL').fetchone()[0]
    return {'sentiment_calls_scored': n, 'hits': hits, 'hit_rate_pct': round(hits / n * 100, 1) if n else None,
            'hits_vs_spy': sum(1 for r in rel if r['hit_vs_spy']), 'scored_vs_spy': len(rel),
            'avg_next_day_pct_after_positive': avg([r['next_day_return_pct'] for r in sent if r['call'] == 'positive']),
            'avg_next_day_pct_after_negative': avg([r['next_day_return_pct'] for r in sent if r['call'] == 'negative']),
            'needed_before_any_verdict': MIN_SAMPLE, 'verdict': verdict, 'calls_waiting_for_next_close': waiting,
            'regime_avg_abs_next_day_move_pct': {k: {'sessions': len(v), 'avg_abs_move_pct': avg(v)} for k, v in sorted(regimes.items())}}


def lessons(store, day, limit=6):
    ensure(store)
    with store.connect() as db:
        days = [r[0] for r in db.execute('SELECT DISTINCT day FROM lessons WHERE day<=? ORDER BY day DESC LIMIT ?', (day, LESSON_SESSIONS)).fetchall()]
        if not days:
            return []
        rows = db.execute(f'SELECT day, job, lesson, check_next FROM lessons WHERE day IN ({",".join("?" * len(days))}) ORDER BY id DESC LIMIT ?',
                          (*days, limit)).fetchall()
    return [{'day': d, 'job': j, 'lesson': x, 'check_next': c} for d, j, x, c in rows]


def block(store, day):
    """Packet entries for every seat. Each numeric entry has its own id so cited numbers can be checked."""
    ensure(store)
    out = {}
    with store.connect() as db:
        row = db.execute("SELECT day, kind, at, payload_json FROM notes WHERE kind IN ('morning','close') ORDER BY id DESC LIMIT 1").fetchone()
        last_scored = db.execute("SELECT MAX(scored_day) FROM calls").fetchone()[0]
    if row:
        try:
            n = json.loads(row[3])
        except ValueError:
            n = {}
        out['memory:last_note'] = {'id': 'memory:last_note', 'day': row[0], 'kind': row[1], 'headline': n.get('headline'),
                                   'decision_read': n.get('decision_read'), 'watch': n.get('watch') or []}
    if last_scored:
        for r in _rows(store, "WHERE scored_day=? AND kind='sentiment' AND seat='bubbles' ORDER BY id", (last_scored,))[:10]:
            key = f'memory:call:{r["ticker"]}'
            out[key] = {'id': key, 'called_on': r['day'], 'call': r['call'], 'scored_on': r['scored_day'],
                        'next_day_return_pct': r.get('next_day_return_pct'), 'spy_return_pct': r.get('spy_return_pct'), 'hit': r.get('hit')}
    card = scorecard(store)
    out['memory:scorecard'] = {'id': 'memory:scorecard', **{k: v for k, v in card.items() if k != 'regime_avg_abs_next_day_move_pct'}}
    open_lessons = lessons(store, day)
    if open_lessons:
        out['MEMORY_LESSONS'] = open_lessons
    return out
