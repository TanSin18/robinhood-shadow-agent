"""Analyst desk page (/analyst): AI commentary and news notes, the post-close regime model and
shadow Kelly sizes. Read-only view of robinhood-diagnostics/analyst/analyst.db; nothing on this page
can trade. Missing data is shown as missing."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .charts import esc, pct, short_time

STATE_CLS = {'calm': 'st-calm', 'normal': 'st-normal', 'stressed': 'st-stressed'}
SENT_CLS = {'positive': 'pos', 'negative': 'neg', 'mixed': 'mixed', 'neutral': 'neutral'}


def default_path(official_db):
    return Path(official_db).resolve().parents[2] / 'robinhood-diagnostics' / 'analyst' / 'analyst.db'


def _has(db, table):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


ACCOUNTS = {'agent_alone': 'AI alone', 'with_approvals': 'AI + your approval', 'deterministic_no_ai': 'Rules only'}
CHOP_CLS = {'TRENDING': 'pos', 'CHOPPY': 'mixed', 'LOW_VOL': 'neutral', 'OVEREXTENDED': 'neg'}


def _guard(g):
    if not g:
        return '<p class="v10-empty">No exit-guard check yet; it runs after the close with the regime model.</p>'
    rows = ''
    for e in g.get('exits') or []:
        if e.get('status') != 'OK':
            continue
        lane, _, track = (e.get('account') or '').partition(':')
        first = e.get('first_would_sell') or {}
        trig = '; '.join(e.get('triggers') or []) or 'none'
        rows += (f'<tr class="{"an-sell" if e.get("verdict") == "WOULD_SELL" else ""}"><td><b>{esc(e.get("ticker"))}</b><small> {esc(ACCOUNTS.get(track, track))} · {esc(lane)}</small></td>'
                 f'<td class="num">${e.get("average_cost"):,.2f}</td><td class="num">${e.get("last_close"):,.2f}</td>'
                 f'<td class="num">{pct(e.get("gain_pct"))}<small> peak {pct(e.get("peak_gain_pct"))}</small></td>'
                 f'<td class="num">${e.get("guard_stop"):,.2f}<small> {esc(e.get("guard_stop_rule"))}</small></td>'
                 f'<td class="num">{pct(e.get("distance_to_guard_pct"))}</td>'
                 f'<td><span class="an-sent {"neg" if e.get("verdict") == "WOULD_SELL" else "pos"}">{esc((e.get("verdict") or "").replace("_", " ").lower())}</span>'
                 f'<small> {esc(trig)}</small>' + (f'<small> · first flagged {esc(first.get("day"))} at ${first.get("price"):,.2f}</small>' if first.get('price') else '')
                 + '</td></tr>')
    gate = ''.join(f'<li><b>{esc(x.get("ticker"))}</b>: {esc(x.get("label"))} → a chop gate would have '
                   f'{"<b>blocked</b>" if x.get("would_block") else "allowed"} today’s official entry</li>' for x in g.get('entry_gate') or [])
    return ('<div class="table-wrap"><table class="mini"><thead><tr><th>Holding</th><th>Cost</th><th>Last close</th><th>Gain</th>'
            '<th>Guard stop (highest of the rules)</th><th>Room to stop</th><th>Verdict</th></tr></thead>'
            f'<tbody>{rows or "<tr><td colspan=7>No holdings.</td></tr>"}</tbody></table></div>'
            + (f'<ul class="v10-list">{gate}</ul>' if gate else '')
            + '<p class="v10-note">Rules: chandelier stop = highest close since entry − 3 × ATR(22), trailing up only; profit lock = break-even once '
              'the gain reaches 2 × ATR, cost + 2 × ATR at 4 × ATR; give-back = sell if half of a 10%+ peak gain is gone; fast trend break = below '
              'the 50-day average in a stressed regime; plus the official 8% stop and 200-day exit. The guard stop shown is the highest of them. '
              'Shadow only: nothing is sold. Each first “would sell” keeps its price so the record shows whether the guard saved money or cut a '
              'winner early; it becomes real only through a signed amendment.</p>')


def _chop(g):
    chop = (g or {}).get('chop') or {}
    if not chop:
        return '<p class="v10-empty">No chop labels yet; written after the close.</p>'
    rows = ''.join(f'<tr><td><b>{esc(t)}</b></td><td><span class="an-sent {CHOP_CLS.get(c.get("label"), "")}">{esc((c.get("label") or "").replace("_", " ").lower())}</span></td>'
                   f'<td class="num">{c.get("adx14", "—")}</td><td class="num">{c.get("atr14_pct", "—")}%</td>'
                   f'<td class="num">{c.get("stretch_vs_ma50_atr", "—")}</td><td>{esc(c.get("gate"))}</td></tr>'
                   for t, c in sorted(chop.items()) if c.get('status') == 'OK')
    return ('<div class="table-wrap"><table class="mini"><thead><tr><th>Name</th><th>Tape</th><th>ADX(14)</th><th>ATR(14) % of price</th>'
            f'<th>Distance from 50-day avg (ATRs)</th><th>Gate</th></tr></thead><tbody>{rows}</tbody></table></div>'
            '<p class="v10-note">Trending = ADX ≥ 20; choppy = ADX < 20; low vol = ATR% in the bottom fifth of its own last year; overextended = more '
            'than 3 ATRs from the 50-day average. Only “trending” would pass a chop gate. Shadow only: the official run does not read it yet.</p>')


def load(official_db):
    path = default_path(official_db)
    if not path.is_file():
        return {'exists': False}
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=0.2)
    try:
        def latest(table, kind=None):
            q = f'SELECT day, at, payload_json' + (', checks_json' if table == 'notes' else '') + f' FROM {table}'
            q += (' WHERE kind=?' if kind else '') + ' ORDER BY id DESC LIMIT 1'
            row = db.execute(q, (kind,) if kind else ()).fetchone()
            if not row:
                return None
            out = {'day': row[0], 'at': row[1], **json.loads(row[2])}
            if table == 'notes':
                out['_checks'] = json.loads(row[3] or '{}')
            return out
        meta = dict(db.execute('SELECT key, value FROM meta').fetchall())
        spent = db.execute("SELECT day, SUM(COALESCE(actual, reserved)) FROM budget GROUP BY day ORDER BY day DESC LIMIT 1").fetchone()
        return {'exists': True, 'meta': {k: v for k, v in meta.items() if not k.endswith(('_attempts', 'attempts'))},
                'morning': latest('notes', 'morning'), 'close': latest('notes', 'close'), 'regime': latest('regimes'),
                'kelly': latest('kelly'), 'auction': latest('auction'), 'guard': latest('guard') if _has(db, 'guard') else None, 'news_morning': latest('news', 'morning'),
                'news_close': latest('news', 'close'), 'spent': {'day': spent[0], 'usd': spent[1]} if spent and spent[0] else None}
    except sqlite3.Error as error:
        return {'exists': True, 'error': type(error).__name__}
    finally:
        db.close()


def _note(n, news_items, title):
    if not n:
        return f'<section class="v10-panel"><h3>{esc(title)}</h3><p class="v10-empty">Not written yet.</p></section>'
    by_id = {i.get('id'): i for i in news_items or []}
    flags = (n.get('_checks') or {}).get('flags') or []
    checks = ('<p class="an-ok">Code checks passed: every number cited matches the records; no order-like or hype language.</p>' if not flags else
              '<p class="an-flag">Code flagged: ' + esc(', '.join(flags)) + '</p>')
    rows = ''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(n.get(f))}</dd></div>' for k, f in
                   (('Market', 'market_read'), ('Official decision', 'decision_read'), ('Regime', 'regime_read'), ('Auction', 'auction_read'))
                   if n.get(f))
    notes = ''
    for x in n.get('news') or []:
        links = ''.join(f'<li><a href="{esc(by_id[h]["url"])}" rel="noreferrer noopener" target="_blank">{esc(by_id[h]["title"])}</a>'
                        f'<small> · {esc(by_id[h].get("source"))}</small></li>' for h in x.get('headline_ids') or [] if h in by_id)
        notes += (f'<li><span class="an-sent {SENT_CLS.get(x.get("sentiment"), "")}">{esc(x.get("sentiment"))}</span>'
                  f'<b>{esc(x.get("ticker"))}</b> <small>{esc(x.get("relevance"))} relevance</small><p>{esc(x.get("note"))}</p>'
                  + (f'<ul class="an-links">{links}</ul>' if links else '') + '</li>')
    watch = ''.join(f'<li>{esc(w)}</li>' for w in n.get('watch') or [])
    return (f'<section class="v10-panel an-note"><p class="v10-eyebrow">{esc(title)} · {esc(short_time(n.get("at")))}</p>'
            f'<h3>{esc(n.get("headline"))}</h3><dl class="v10-why">{rows}</dl>'
            + (f'<h4>News and sentiment</h4><ul class="an-news">{notes}</ul>' if notes else '')
            + (f'<h4>Watch</h4><ul class="v10-list">{watch}</ul>' if watch else '') + checks + '</section>')


def _regime(r):
    if not r:
        return '<p class="v10-empty">No regime fit yet. The first one runs after today’s close (16:15 ET).</p>'
    if r.get('status') != 'OK':
        return f'<p class="v10-empty">Last fit: {esc(r.get("status"))}.</p>'
    path = r.get('path') or []
    w, h = 1000, 46
    step = w / max(1, len(path))
    strip = ''.join(f'<rect class="{STATE_CLS.get(s, "")}" x="{i * step:.2f}" y="0" width="{step + 0.3:.2f}" height="{h}"><title>{esc(d)}: {esc(s)}</title></rect>'
                    for i, (d, s) in enumerate(path))
    probs = ''.join(f'<li><span>{esc(k)}</span><span class="v10-meter"><span class="v10-meter-fill {STATE_CLS.get(k, "")} w{int(round(v * 20))}"></span></span>'
                    f'<b>{v * 100:.0f}%</b><small>tomorrow {r["tomorrow_probabilities"].get(k, 0) * 100:.0f}%</small></li>'
                    for k, v in (r.get('current_probabilities') or {}).items())
    states = ''.join(f'<tr><td><i class="key {STATE_CLS.get(s["name"], "")}"></i>{esc(s["name"])}</td><td class="num">{pct(s["ann_return_pct"])}</td>'
                     f'<td class="num">{pct(s["ann_vol_pct"], False)}</td><td class="num">{s["expected_duration_sessions"]}</td>'
                     f'<td class="num">{s["share_of_days"] * 100:.0f}%</td></tr>' for s in r.get('states') or [])
    names = [s['name'] for s in r.get('states') or []]
    trans = ''.join(f'<tr><th>{esc(names[i])}</th>' + ''.join(f'<td class="num">{v * 100:.1f}%</td>' for v in row) + '</tr>'
                    for i, row in enumerate(r.get('transition') or []))
    stab = r.get('stability_vs_last_fit') or {}
    return (f'<div class="an-regime-head"><div><p class="v10-eyebrow">Current regime</p><b class="an-state {STATE_CLS.get(r["current"], "")}">{esc(r["current"])}</b>'
            f'<small>{r.get("current_run_sessions")} sessions in a row · fit on {r.get("sessions")} sessions ({esc(r.get("first_day"))} to {esc(r.get("last_day"))})</small></div>'
            f'<ul class="an-probs">{probs}</ul></div>'
            f'<svg class="an-strip" viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img" aria-label="Regime label for each of the last {len(path)} sessions">{strip}</svg>'
            f'<p class="v10-note">Each bar is one session over the last {len(path)} (oldest left). '
            + (f'Since last night’s fit, {stab.get("relabelled")} of the last {stab.get("compared_sessions")} labels changed.' if stab else '')
            + '</p><div class="v10-two"><div class="table-wrap"><table class="mini"><thead><tr><th>State</th><th>Annual return</th><th>Annual vol</th>'
              f'<th>Typical run (sessions)</th><th>Share of days</th></tr></thead><tbody>{states}</tbody></table></div>'
              '<div class="table-wrap"><table class="mini an-trans"><thead><tr><th>From \\ to</th>' + ''.join(f'<th>{esc(n)}</th>' for n in names)
            + f'</tr></thead><tbody>{trans}</tbody></table></div></div>'
              f'<p class="v10-note">Model: {esc(r.get("model"))}; {r.get("iterations")} iterations, converged {esc(r.get("converged"))}, '
              f'log-likelihood {r.get("log_likelihood")}. Retrained after every close. Shadow only: no trading rule reads it.</p>')


def _kelly(k, held):
    if not k:
        return '<p class="v10-empty">No Kelly sizes yet; computed after the close with the regime fit.</p>'
    rows = ''
    for t, v in sorted((k.get('tickers') or {}).items(), key=lambda kv: (kv[0] not in held, kv[0])):
        reg, al = v.get('regime') or {}, v.get('all') or {}
        def f(x):
            return '—' if x is None else f'{x * 100:.1f}%'
        rows += (f'<tr class="{"an-held" if t in held else ""}"><td><b>{esc(t)}</b>{" <small>held</small>" if t in held else ""}</td>'
                 f'<td class="num">{f(v.get("risk_engine_fraction"))}</td>'
                 f'<td class="num">{f(reg.get("kelly_raw"))}</td><td class="num">{f(reg.get("kelly_half"))}</td>'
                 f'<td class="num"><b>{f(reg.get("kelly_disciplined"))}</b></td><td class="num">{reg.get("t_stat", "—")}</td>'
                 f'<td class="num">{reg.get("sessions", "—")}</td><td class="num">{f(al.get("kelly_half"))}</td><td class="num">{al.get("t_stat", "—")}</td></tr>')
    return ('<div class="table-wrap"><table class="mini an-kelly"><thead><tr><th>Name</th><th>Size the risk engine uses</th>'
            f'<th>Kelly raw (in {esc(k.get("regime"))})</th><th>Half-Kelly</th><th>Disciplined</th><th>t-stat</th><th>Sessions</th>'
            f'<th>Half-Kelly, all history</th><th>t-stat, all</th></tr></thead><tbody>{rows}</tbody></table></div>'
            f'<p class="v10-note">{esc(k.get("method"))}. Raw Kelly is often absurd (hundreds of percent) because it trusts the historical average '
            'completely; that is why only the disciplined column could ever be considered, and only after the edge is proven. Shadow only.</p>')


def _auction(a):
    if not a:
        return '<p class="v10-empty">No auction read yet; written after the close.</p>'
    rows = ''.join(f'<tr><td><b>{esc(t)}</b></td><td>{esc(v.get("day_type"))}</td><td class="num">{pct(v.get("change_pct"))}</td>'
                   f'<td class="num">{pct(v.get("gap_pct"))}</td><td class="num">{v.get("range_vs_atr20", "—")}×</td>'
                   f'<td class="num">{v.get("close_location", "—")}</td><td class="num">{v.get("volume_vs_avg20", "—")}×</td></tr>'
                   for t, v in sorted((a.get('tickers') or {}).items(), key=lambda kv: -abs(kv[1].get('change_pct') or 0)) if v.get('status') == 'OK')
    return ('<div class="table-wrap"><table class="mini"><thead><tr><th>Name</th><th>Day type</th><th>Change</th><th>Gap</th>'
            f'<th>Range vs 20-day ATR</th><th>Close location (−1 low … +1 high)</th><th>Volume vs 20-day avg</th></tr></thead><tbody>{rows}</tbody></table></div>'
            '<p class="v10-note">Built from completed daily bars only: the registered read gateway does not allow intraday bars, so this is a daily '
            'approximation of an auction read, not an intraday value area.</p>')


def _news(*batches):
    items = [i for b in batches if b for i in (b.get('items') or [])]
    if not items:
        return '<p class="v10-empty">No headlines stored yet.</p>'
    seen, rows = set(), ''
    for i in items:
        if i.get('url') in seen:
            continue
        seen.add(i.get('url'))
        rows += (f'<li><span class="v10-chip">{esc(i.get("ticker"))}</span><a href="{esc(i.get("url"))}" rel="noreferrer noopener" target="_blank">'
                 f'{esc(i.get("title"))}</a><small> · {esc(i.get("source"))} · {esc(short_time(i.get("published")))}</small></li>')
    problems = [p for b in batches if b for p in (b.get('problems') or [])]
    return (f'<ul class="an-headlines">{rows}</ul>'
            + (f'<p class="v10-note">Feed problems: {esc(", ".join(sorted({p.get("error", "") for p in problems})))}.</p>' if problems else ''))


def render(state):
    a = state.get('analyst') or {}
    head = ('<div class="room-head"><div><h1>Analyst desk</h1><p>AI off the trading path: language models write commentary and news notes; '
            'code computes the market regime and shadow Kelly sizes after the close. Nothing here can place, size or block a trade.</p></div></div>')
    if not a.get('exists'):
        return head + ('<section class="v10-panel"><h3>Not set up yet</h3><p>Install release G, then run '
                       '<code>python -m agents.analyst.cli init --official-database …/data/agent.db</code>. The first morning note follows the next '
                       'official run; the first regime fit runs after the close.</p></section>')
    if a.get('error'):
        return head + f'<p class="v10-empty">Analyst records unavailable ({esc(a["error"])}). No status is assumed.</p>'
    held = {h for h in ((state.get('portfolio') or {}).get('fills') and [f.get('ticker') for f in state['portfolio']['fills']] or [])}
    spent = a.get('spent') or {}
    meta = a.get('meta') or {}
    status = ('paused' if meta.get('paused') == '1' else 'running') + (f' · AI spend {esc(spent.get("day"))}: ${float(spent.get("usd") or 0):.4f} of $1.00' if spent else ' · no AI spend yet')
    news_all = ((a.get('news_morning') or {}).get('items') or []) + ((a.get('news_close') or {}).get('items') or [])
    return ''.join([head, f'<p class="capital-note is-live"><strong>Status:</strong> {status}. Model gpt-5.4-mini (dated), strict JSON, no tools.</p>',
                    '<div class="v10-grid an-notes">', _note(a.get('morning'), (a.get('news_morning') or {}).get('items'), 'Morning note'),
                    _note(a.get('close'), (a.get('news_close') or {}).get('items') or news_all, 'After-close note'), '</div>',
                    f'<section class="v10-panel"><h3>Market regime <small>3-state hidden Markov model on VTI, retrained after every close</small></h3>{_regime(a.get("regime"))}</section>',
                    f'<section class="v10-panel"><h3>Exit guard <small>protect gains, stop losses: what adaptive exits would do with each holding</small></h3>{_guard(a.get("guard"))}</section>',
                    f'<section class="v10-panel"><h3>Chop gate <small>trend or chop, per name: when a gate would sit out</small></h3>{_chop(a.get("guard"))}</section>',
                    f'<section class="v10-panel"><h3>Shadow Kelly sizes <small>what Kelly would say, next to what the risk engine actually uses</small></h3>{_kelly(a.get("kelly"), held)}</section>',
                    f'<section class="v10-panel"><h3>Daily auction read</h3>{_auction(a.get("auction"))}</section>',
                    f'<section class="v10-panel"><h3>Headlines <small>untrusted text, stored with links; the AI only summarises them</small></h3>'
                    f'{_news(a.get("news_morning"), a.get("news_close"))}</section>'])
