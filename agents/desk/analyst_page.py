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


SEATS = (('pip', 'Blossom', 'Research', 'blossom-research.svg'), ('biscuit', 'Buttercup', 'Filings & news', 'buttercup-news.svg'),
         ('maple', 'Mayor', 'Portfolio', 'mayor-portfolio.svg'), ('pickle', 'Mojo Jojo', 'Critic', 'mojojojo-critic.svg'))
VERDICT_CLS = {'sound': 'pos', 'weak': 'mixed', 'flawed': 'neg'}


def _team(team):
    cards = ''
    for key, name, role, avatar in SEATS:
        n = (team or {}).get(key)
        if not n:
            body = '<p class="v10-empty">No note yet. Writes after the official run and after the close.</p>'
        elif key == 'pip':
            body = (f'<p><b>Base rate:</b> {esc(n.get("base_rate"))}</p><ul class="v10-list">'
                    + ''.join(f'<li><b>{esc(x.get("ticker"))}</b> {esc(x.get("read"))} <small>Wrong if: {esc(x.get("wrong_if"))}</small></li>'
                              for x in n.get('setups') or []) + '</ul>')
        elif key == 'biscuit':
            body = (f'<p>{esc(n.get("summary"))}</p><ul class="an-news">'
                    + ''.join(f'<li><span class="an-sent {SENT_CLS.get(x.get("sentiment"), "")}">{esc(x.get("sentiment"))}</span><b>{esc(x.get("ticker"))}</b>'
                              f'<p>{esc(x.get("note"))}</p></li>' for x in n.get('news') or []) + '</ul>')
        elif key == 'maple':
            body = (f'<p>{esc(n.get("portfolio_read"))}</p><ul class="v10-list">'
                    + ''.join(f'<li><b>{esc(x.get("topic"))}</b> {esc(x.get("note"))}</li>' for x in n.get('points') or []) + '</ul>')
        else:
            body = '<ul class="v10-list">' + ''.join(
                f'<li><span class="an-sent {VERDICT_CLS.get(v.get("verdict"), "")}">{esc(v.get("verdict"))}</span><b>{esc((v.get("target") or "").replace("_", " "))}</b> '
                f'{esc("; ".join(v.get("reasons") or []))}' + (f' <small>{esc(", ".join(v.get("fail_codes") or []))}</small>' if v.get('fail_codes') else '')
                + '</li>' for v in n.get('verdicts') or []) + '</ul>'
        flags = ((n or {}).get('_checks') or {}).get('flags') or []
        when = f'<small>{esc(short_time(n.get("at")))}</small>' if n else ''
        cards += (f'<section class="v10-panel an-seat"><header><img src="/assets/avatars/{avatar}" width="44" height="44" alt="">'
                  f'<div><b>{esc(name)}</b><span>{esc(role)} · advisory</span></div>{when}</header>{body}'
                  + (f'<p class="an-flag">Code flagged: {esc(", ".join(flags))}</p>' if flags else '') + '</section>')
    cards += ('<section class="v10-panel an-seat"><header><img src="/assets/avatars/profx-safety.svg" width="44" height="44" alt="">'
              '<div><b>Prof. X</b><span>Safety rules · code · decides</span></div></header>'
              '<p>Runs inside every order: 26 risk checks, the loss breakers and the account tripwire. Also checks every note on this page '
              'for uncited numbers, win-rate talk, hype and order-like language.</p></section>'
              '<section class="v10-panel an-seat"><header><img src="/assets/avatars/bubbles-explainer.svg" width="44" height="44" alt="">'
              '<div><b>Bubbles</b><span>Explainer · advisory</span></div></header>'
              '<p>Writes last, from everyone above, the morning and after-close notes just below.</p></section>')
    return f'<div class="an-team">{cards}</div>'


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
        team = {}
        for job in ('morning', 'close'):
            for seat in ('pip', 'biscuit', 'maple', 'pickle'):
                n = latest('notes', f'{job}:{seat}')
                if n and (seat not in team or n['at'] > team[seat]['at']):
                    team[seat] = n
        spent = db.execute("SELECT day, SUM(COALESCE(actual, reserved)) FROM budget GROUP BY day ORDER BY day DESC LIMIT 1").fetchone()
        return {'exists': True, 'meta': {k: v for k, v in meta.items() if not k.endswith(('_attempts', 'attempts'))},
                'team': team, 'morning': latest('notes', 'morning'), 'close': latest('notes', 'close'), 'regime': latest('regimes'),
                'kelly': latest('kelly'), 'auction': latest('auction'), 'guard': latest('guard') if _has(db, 'guard') else None, 'news_morning': latest('news', 'morning'),
                'news_close': latest('news', 'close'), 'spent': {'day': spent[0], 'usd': spent[1]} if spent and spent[0] else None}
    except sqlite3.Error as error:
        return {'exists': True, 'error': type(error).__name__}
    finally:
        db.close()


def _note(n, news_items, title, when_written=''):
    """One note, laid out to be read in a minute: the headline, four short reads, news by ticker (headlines folded), what to watch."""
    if not n:
        return (f'<article class="nb nb-empty"><p class="nb-meta">{esc(title)}</p><h2>Not written yet</h2>'
                f'<p class="v10-empty">{esc(when_written)}</p></article>')
    by_id = {i.get('id'): i for i in news_items or []}
    flags = (n.get('_checks') or {}).get('flags') or []
    checks = ('<p class="an-ok">Code checks passed: every number cited matches the records; no order-like or hype language.</p>' if not flags else
              '<p class="an-flag">Code flagged: ' + esc(', '.join(flags)) + '</p>')
    reads = ''.join(f'<section><h4>{esc(k)}</h4><p>{esc(n.get(f))}</p></section>' for k, f in
                    (('Market', 'market_read'), ('Official decision', 'decision_read'), ('Regime', 'regime_read'), ('Auction', 'auction_read'))
                    if n.get(f))
    order = {'high': 0, 'medium': 1, 'low': 2}
    notes = ''
    for x in sorted(n.get('news') or [], key=lambda x: order.get(x.get('relevance'), 3)):
        links = ''.join(f'<li><a href="{esc(by_id[h]["url"])}" rel="noreferrer noopener" target="_blank">{esc(by_id[h]["title"])}</a>'
                        f'<small>{esc(by_id[h].get("source"))}</small></li>' for h in x.get('headline_ids') or [] if h in by_id)
        count = links.count('<li>')
        head = (f'<span class="an-sent {SENT_CLS.get(x.get("sentiment"), "")}">{esc(x.get("sentiment"))}</span>'
                f'<b class="nb-tk">{esc(x.get("ticker"))}</b><p>{esc(x.get("note"))}</p>')
        notes += (f'<li><details><summary>{head}<span class="nb-more">{count} headline{"s" if count != 1 else ""}</span></summary>'
                  f'<ul class="an-links">{links}</ul></details></li>' if links else f'<li><div class="nb-row">{head}</div></li>')
    watch = ''.join(f'<li>{esc(w)}</li>' for w in n.get('watch') or [])
    return (f'<article class="nb"><p class="nb-meta">{esc(title)} · {esc(short_time(n.get("at")))}</p>'
            f'<h2>{esc(n.get("headline"))}</h2><div class="nb-reads">{reads}</div>'
            + (f'<section class="nb-sec"><h3>News and sentiment <small>most relevant first · open a row for the headlines</small></h3>'
               f'<ul class="nb-news">{notes}</ul></section>' if notes else '')
            + (f'<section class="nb-sec"><h3>Watch next</h3><ul class="nb-watch">{watch}</ul></section>' if watch else '') + checks + '</article>')


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


def _ladder(e):
    """One line showing where the stop, your cost, the last close and the best close sit relative to each other."""
    pts = [('stop', e.get('guard_stop'), 'stop'), ('cost', e.get('average_cost'), 'cost'), ('peak', e.get('high_since_entry'), 'peak'),
           ('last', e.get('last_close'), 'last')]
    vals = [v for _, v, _ in pts if isinstance(v, (int, float))]
    if len(vals) < 2:
        return ''
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    lo, hi = lo - span * .12, hi + span * .12
    x = lambda v: 16 + (v - lo) / (hi - lo) * 328
    rows = {'last': (14, True), 'peak': (28, True), 'cost': (66, False), 'stop': (80, False)}   # label rows never collide
    marks = ''
    for name, v, cls in pts:
        if not isinstance(v, (int, float)):
            continue
        ty, up = rows[name]
        anchor = 'start' if x(v) < 70 else 'end' if x(v) > 290 else 'middle'
        marks += (f'<g class="ld-{cls}"><line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{ty + 3 if up else 44}" y2="{44 if up else ty - 11}"/>'
                  f'<circle cx="{x(v):.1f}" cy="44" r="{5.5 if name == "last" else 4}"/>'
                  f'<text x="{x(v):.1f}" y="{ty}" text-anchor="{anchor}">{name} ${v:,.2f}</text></g>')
    return (f'<svg class="an-ladder" viewBox="0 0 360 86" role="img" aria-label="Stop, cost, last close and best close for {esc(e.get("ticker"))}">'
            f'<line class="ld-axis" x1="16" x2="344" y1="44" y2="44"/>{marks}</svg>')


def _guard_cards(g):
    if not g:
        return '<p class="v10-empty">No exit-guard check yet. It runs after the close, with the regime model.</p>'
    cards = ''
    for e in g.get('exits') or []:
        if e.get('status') != 'OK':
            continue
        lane, _, track = (e.get('account') or '').partition(':')
        sell = e.get('verdict') == 'WOULD_SELL'
        first = e.get('first_would_sell') or {}
        cards += (f'<section class="v10-panel an-guard {"is-sell" if sell else "is-hold"}"><header><div><b>{esc(e.get("ticker"))}</b>'
                  f'<small>{esc(ACCOUNTS.get(track, track))} · lane {esc(lane)}</small></div>'
                  f'<span class="an-sent {"neg" if sell else "pos"}">{"would sell" if sell else "hold"}</span></header>{_ladder(e)}'
                  f'<dl class="v10-stats"><div><dt>Gain now</dt><dd class="{"pos" if (e.get("gain_pct") or 0) > 0 else "neg"}">{pct(e.get("gain_pct"))}</dd></div>'
                  f'<div><dt>Best gain so far</dt><dd>{pct(e.get("peak_gain_pct"))}</dd></div>'
                  f'<div><dt>Room before the stop</dt><dd>{pct(e.get("distance_to_guard_pct"))}</dd></div>'
                  f'<div><dt>Active stop rule</dt><dd>{esc(e.get("guard_stop_rule"))}</dd></div></dl>'
                  + (f'<p class="an-flag">Why: {esc("; ".join(e.get("triggers") or []))}</p>' if sell else '')
                  + (f'<p class="v10-note">First flagged {esc(first.get("day"))} at ${first.get("price"):,.2f}. The record will show whether selling there beat holding.</p>'
                     if first.get('price') else '') + '</section>')
    gate = ''.join(f'<li><b>{esc(x.get("ticker"))}</b>: tape was {esc((x.get("label") or "unknown").replace("_", " ").lower())}, so a chop gate would have '
                   f'{"<b>blocked</b>" if x.get("would_block") else "allowed"} today’s official entry.</li>' for x in g.get('entry_gate') or [])
    return ((f'<div class="an-guards">{cards}</div>' if cards else '<p class="v10-empty">No holdings to guard.</p>')
            + (f'<ul class="v10-list">{gate}</ul>' if gate else ''))


def _tape(g, a):
    chop, auc = (g or {}).get('chop') or {}, (a or {}).get('tickers') or {}
    names = sorted(set(chop) | set(auc), key=lambda t: -abs((auc.get(t) or {}).get('change_pct') or 0))
    if not names:
        return '<p class="v10-empty">No tape read yet. It is written after the close.</p>'
    rows = ''
    for t in names:
        c, v = chop.get(t) or {}, auc.get(t) or {}
        label = c.get('label')
        rows += (f'<tr><td><b>{esc(t)}</b></td><td><span class="an-sent {CHOP_CLS.get(label, "")}">{esc((label or "—").replace("_", " ").lower())}</span></td>'
                 f'<td class="num">{pct(v.get("change_pct"))}</td><td>{esc(v.get("day_type") or "—")}</td><td class="num">{c.get("adx14", "—")}</td>'
                 f'<td class="num">{v.get("range_vs_atr20", "—")}×</td><td class="num">{v.get("close_location", "—")}</td>'
                 f'<td class="num">{v.get("volume_vs_avg20", "—")}×</td></tr>')
    trending = sum(1 for c in chop.values() if c.get('label') == 'TRENDING')
    return (f'<p class="an-lead">{trending} of {len(chop)} names are trending tonight. Only trending names would pass a chop gate.</p>'
            '<div class="table-wrap"><table class="mini"><thead><tr><th>Name</th><th>Tape</th><th>Today</th><th>Day type</th><th>Trend strength (ADX)</th>'
            f'<th>Range vs normal</th><th>Closed near (−1 low, +1 high)</th><th>Volume vs normal</th></tr></thead><tbody>{rows}</tbody></table></div>')


def _sizing(k, held):
    if not k:
        return '<p class="v10-empty">No Kelly sizes yet. They are computed after the close.</p>'
    def f(x):
        return '—' if x is None else f'{x * 100:.1f}%'
    def row(t, v):
        reg, al = v.get('regime') or {}, v.get('all') or {}
        return (f'<tr class="{"an-held" if t in held else ""}"><td><b>{esc(t)}</b>{" <small>held</small>" if t in held else ""}</td>'
                f'<td class="num">{f(v.get("risk_engine_fraction"))}</td><td class="num"><b>{f(reg.get("kelly_disciplined"))}</b></td>'
                f'<td class="num">{f(reg.get("kelly_half"))}</td><td class="num">{reg.get("t_stat", "—")}</td><td class="num">{al.get("t_stat", "—")}</td></tr>')
    items = sorted((k.get('tickers') or {}).items(), key=lambda kv: (kv[0] not in held, -((kv[1].get('regime') or {}).get('kelly_disciplined') or 0), kv[0]))
    top = [x for x in items if x[0] in held or ((x[1].get('regime') or {}).get('kelly_disciplined') or 0) > 0]
    rest = [x for x in items if x not in top]
    head = ('<thead><tr><th>Name</th><th>Size actually used</th><th>Disciplined Kelly</th><th>Half-Kelly (raw idea)</th>'
            '<th>Edge strength in this regime (t)</th><th>Edge strength, all history (t)</th></tr></thead>')
    out = (f'<p class="an-lead">Regime tonight: {esc(k.get("regime"))}. Disciplined Kelly is zero unless the edge is statistically real '
           'both in this regime and over all history.</p>'
           f'<div class="table-wrap"><table class="mini">{head}<tbody>{"".join(row(t, v) for t, v in top) or "<tr><td colspan=6>Nothing held and no name has a proven edge tonight.</td></tr>"}</tbody></table></div>')
    if rest:
        out += (f'<details class="an-more"><summary>All other names ({len(rest)}), disciplined size 0%</summary><div class="table-wrap"><table class="mini">{head}'
                f'<tbody>{"".join(row(t, v) for t, v in rest)}</tbody></table></div></details>')
    return out


def _kpis(a):
    r, g, sp = a.get('regime') or {}, a.get('guard') or {}, a.get('spent') or {}
    exits = [e for e in g.get('exits') or [] if e.get('status') == 'OK']
    sells = sum(1 for e in exits if e.get('verdict') == 'WOULD_SELL')
    chop = g.get('chop') or {}
    trending = sum(1 for c in chop.values() if c.get('label') == 'TRENDING')
    written = sum(1 for k in ('morning', 'close') if a.get(k)) + len(a.get('team') or {})
    tiles = (('Market regime', (r.get('current') or 'not fitted yet').capitalize() if r.get('status') == 'OK' else 'Not fitted yet',
              f'{(r.get("current_probabilities") or {}).get(r.get("current"), 0) * 100:.0f}% confident' if r.get('status') == 'OK' else 'first fit after the close'),
             ('Exit guard', f'{len(exits) - sells} hold · {sells} would sell' if exits else 'Not run yet', 'shadow only, nothing is sold'),
             ('Trending names', f'{trending} of {len(chop)}' if chop else '—', 'the rest would sit out'),
             ('Team notes', str(written) if written else 'None yet', 'latest from each agent'),
             ('AI spend today', f'${float(sp.get("usd") or 0):.3f}', 'cap $1.00 a day'))
    return '<div class="an-kpis">' + ''.join(f'<div class="an-kpi"><span>{esc(t)}</span><b>{esc(v)}</b><small>{esc(n)}</small></div>' for t, v, n in tiles) + '</div>'


TABS = (('an-brief', 'Brief', 'The note you read'), ('an-team', 'Team', 'What each agent said'), ('an-guard', 'Exit guard', 'Protect gains, stop losses'),
        ('an-regime', 'Regime', 'Calm, normal or stressed'), ('an-sizing', 'Sizing', 'Kelly vs actual'), ('an-tape', 'Tape', 'Trend or chop, per name'),
        ('an-news', 'News', 'Headlines the team read'))


def _panel(tab_id, what, body, active=False):
    return (f'<div class="v10-tabpanel an-tab" id="{tab_id}" data-tabpanel{" data-active" if active else ""}>'
            f'<p class="an-what">{what}</p>{body}</div>')


def render(state):
    a = state.get('analyst') or {}
    head = ('<div class="room-head"><div><h1>Analyst desk</h1><p>The team’s daily read on the market and your book. They explain and warn; '
            'they never place, size or block a trade.</p></div></div>')
    if not a.get('exists'):
        return head + ('<section class="v10-panel"><h3>Not set up yet</h3><p>Install the latest release, then run '
                       '<code>python -m agents.analyst.cli init --official-database …/data/agent.db</code>. The first morning note follows the next '
                       'official run; the first regime fit runs after the close.</p></section>')
    if a.get('error'):
        return head + f'<p class="v10-empty">Analyst records unavailable ({esc(a["error"])}). No status is assumed.</p>'
    held = {f.get('ticker') for f in (state.get('portfolio') or {}).get('fills') or []}
    news_m, news_c = a.get('news_morning') or {}, a.get('news_close') or {}
    tabs = ''.join(f'<a role="tab" href="#{i}" data-tab="{i}" aria-selected="{"true" if n == 0 else "false"}">{esc(t)}<small>{esc(sub)}</small></a>'
                   for n, (i, t, sub) in enumerate(TABS))
    morning, close = a.get('morning'), a.get('close')
    latest = 'close' if close and (not morning or str(close.get('at')) >= str(morning.get('at'))) else 'morning'
    subs = (('close', 'After close', close, 'Written in the after-close job, 4:15 PM ET at the earliest, once the day’s bars are in.'),
            ('morning', 'Morning', morning, 'Written after the 10:00 AM ET official run completes.'))
    seg = ''.join(f'<a role="tab" href="#an-brief-{k}" data-tab="an-brief-{k}" aria-selected="{"true" if k == latest else "false"}">{esc(label)}'
                  f'<small>{esc(short_time(n.get("at"))) if n else "not written yet"}</small></a>' for k, label, n, _ in subs)
    brief = (f'<nav class="v10-seg" role="tablist" aria-label="Which note" data-tabgroup="brief">{seg}</nav>'
             + ''.join(f'<div class="v10-subpanel" id="an-brief-{k}" data-tabpanel="brief"{" data-active" if k == latest else ""}>'
                       + _note(n, (news_c.get('items') or news_m.get('items')) if k == 'close' else news_m.get('items'),
                               'After-close note' if k == 'close' else 'Morning note', hint) + '</div>' for k, label, n, hint in subs))
    return ''.join([
        head, _kpis(a), f'<nav class="v10-tabs an-tabs" role="tablist" aria-label="Analyst desk sections">{tabs}</nav>',
        _panel('an-brief', 'Bubbles writes two short notes a day from everything the team produced: one after the 10:00 run, one after the close.', brief, True),
        _panel('an-team', 'Each agent has one job and writes every trading day. Mojo Jojo’s job is to find fault with the others.', _team(a.get('team'))),
        _panel('an-guard', 'For each holding: where a volatility-aware stop would sit tonight and whether it would sell. The stop only ever moves up. '
               'Shadow only; it becomes real only if you sign it in.', _guard_cards(a.get('guard'))),
        _panel('an-regime', 'A statistical model labels the whole market from VTI’s daily moves and is refitted every night.', _regime(a.get('regime'))),
        _panel('an-sizing', 'What the Kelly formula would bet, next to what the risk engine actually uses. Raw Kelly trusts history too much, '
               'so only the disciplined column is worth reading.', _sizing(a.get('kelly'), held)),
        _panel('an-tape', 'How each name traded today and whether it is trending or just chopping around.', _tape(a.get('guard'), a.get('auction'))),
        _panel('an-news', 'Free headlines and filings the team read. They are untrusted text: stored with links, summarised, never acted on.',
               _news(news_m, news_c)),
    ])
