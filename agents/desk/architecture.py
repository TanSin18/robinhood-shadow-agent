"""Architecture: a reviewer's map of the whole system on one page.

Written for an outside expert in agentic AI and trading: what runs where, who can do what, how a
decision is made, how it is checked, how results are judged, what is known to be wrong, and the
open questions. Static content plus a few live counts from the records. No inline style or script.
"""
from __future__ import annotations

from .charts import esc, money
from .rulebook import catalogue

# ------------------------------------------------------------------ system map (SVG units)
# Three rows of services on the Mac, the proxy under its own macOS user, and the two outside services.
# Edges are routed by hand through the gaps between rows/columns so no line crosses a box.
BOXES = {
    'push':     (30, 300, 190, 64, 'Notifications', 'Pushover: alerts, weekly report', 'ext'),
    'you':      (30, 420, 190, 64, 'You (operator)', 'answer cards YES / NO · browser', 'you'),
    'daily':    (290, 60, 200, 64, 'Daily service', 'launchd · 60 s tick · starts runs', 'code'),
    'maint':    (530, 60, 200, 64, 'Maintenance', 'every 5 min: settle, expire, alert', 'code'),
    'screen':   (770, 60, 200, 64, 'Nightly S&P screen', '16:50 ET · research only', 'code'),
    'cycle':    (290, 180, 200, 64, 'Official 10:00 run', 'read → signals → AI gate', 'code'),
    'protect':  (530, 180, 200, 64, '15:50 protective check', 'v1.6 stop / trend / momentum', 'code'),
    'trader':   (770, 180, 200, 64, 'Analyst desk', 'commentary · news · regime', 'ai'),
    'models':   (290, 300, 200, 64, 'AI stages (official)', 'Research · Portfolio · Critic', 'ai'),
    'risk':     (530, 300, 200, 64, 'Risk engine', '26 checks on every order', 'code'),
    'ledger':   (770, 300, 200, 64, 'Paper ledger', '3 accounts × 2 lanes', 'code'),
    'dash':     (290, 420, 200, 64, 'Dashboard :8765', 'read-only views + card answers', 'code'),
    'db':       (530, 420, 200, 64, 'agent.db (official)', 'append-only, hashed capsules', 'store'),
    'tdb':      (770, 420, 200, 64, 'analyst.db · trial log', 'separate from official', 'store'),
    'proxy':    (1050, 180, 190, 64, 'Read-only proxy', '11 read tools · caller uid check', 'ext'),
    'oauth':    (1050, 300, 190, 64, 'Robinhood sign-in', 'tokens live only here', 'ext'),
    'openai':   (1300, 60, 170, 64, 'OpenAI API', 'dated gpt-5.4 models', 'ai'),
    'rh':       (1300, 180, 170, 64, 'Robinhood', 'Agentic account only', 'ext'),
}
ZONES = (('you', 14, 20, 222, 520, 'You'), ('mac', 270, 20, 720, 520, 'Your Mac · operator user'),
         ('proxy', 1030, 150, 230, 240, 'Separate macOS user'), ('cloud', 1285, 20, 200, 520, 'Internet'))
# (class, label, label x, label y, points)
EDGES = (
    ('write', 'starts', 418, 156, ((390, 124), (390, 180))),
    ('read', 'reads quotes, history, account', 760, 146, ((490, 196), (510, 196), (510, 152), (1010, 152), (1010, 200), (1050, 200))),
    ('read', 'daily bars', 1010, 236, ((970, 228), (1050, 228))),
    ('read', 'read only', 1270, 206, ((1240, 212), (1300, 212))),
    ('read', '', 0, 0, ((1145, 300), (1145, 248))),
    ('ai', 'only if a stock idea or holding', 485, 276, ((390, 244), (390, 300))),
    ('ai', 'AI calls · ≤ $0.40 a day', 640, 386, ((360, 364), (360, 392), (1272, 392), (1272, 100), (1300, 100))),
    ('ai', 'AI calls · ≤ $1 a day', 1120, 264, ((870, 244), (870, 270), (1262, 270), (1262, 84), (1300, 84))),
    ('write', '', 0, 0, ((490, 332), (530, 332))),
    ('write', 'fills', 750, 326, ((730, 332), (770, 332))),
    ('write', 'records', 700, 412, ((830, 364), (830, 406), (640, 406), (640, 420))),
    ('write', '', 0, 0, ((970, 340), (982, 340), (982, 452), (970, 452))),
    ('read', 'reads', 510, 446, ((530, 452), (490, 452))),
    ('you', 'uses', 255, 444, ((220, 452), (290, 452))),
    ('you', '', 0, 0, ((125, 364), (125, 420))),
    ('blocked', 'orders: no such tool exists', 1150, 512, ((870, 364), (870, 372), (1000, 372), (1000, 518), (1385, 518), (1385, 248))),
)


def system_map():
    p = ['<svg class="ar-svg" viewBox="0 0 1500 560" role="img" aria-labelledby="ar-map-title">'
         '<title id="ar-map-title">System map: services on your Mac read Robinhood only through a read-only proxy under a separate macOS user, '
         'call OpenAI under fixed budgets, and write paper trades to local databases. No path places a real order.</title>'
         '<defs><marker id="ar-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
         '<path class="ar-arrow" d="M0 0L10 5L0 10z"/></marker></defs>']
    for cls, x, y, w, h, label in ZONES:
        p.append(f'<rect class="ar-zone {cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="16"/>'
                 f'<text class="ar-zone-label {cls}" x="{x + 12}" y="{y + 22}">{esc(label)}</text>')
    for cls, label, lx, ly, pts in EDGES:
        d = 'M' + ' L'.join(f'{x} {y}' for x, y in pts)
        p.append(f'<path class="ar-edge {cls}" d="{d}" marker-end="url(#ar-arrow)"/>')
        if label:
            p.append(f'<text class="ar-edge-label {cls}" x="{lx}" y="{ly}">{esc(label)}</text>')
    for key, (x, y, w, h, title, sub, kind) in BOXES.items():
        p.append(f'<g class="ar-box k-{kind}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12"/>'
                 f'<text x="{x + w / 2}" y="{y + 27}">{esc(title)}</text><text class="sub" x="{x + w / 2}" y="{y + 45}">{esc(sub)}</text></g>')
    p.append('</svg>')
    return ''.join(p)


# ------------------------------------------------------------------ content
SEATS_OFFICIAL = (
    ('code', 'Signal rules', 'code', 'Momentum (ETFs, top 1) and 3% dip rules on the 23 registered names. Options rule paused.'),
    ('code', 'AI gate', 'code', 'Calls the models only if there is a stock signal or a held stock/option to review. Most days: no AI call, $0.'),
    ('ai', 'Research', 'gpt-5.4-nano (dated)', 'Summarises the evidence packet for stock ideas. Cannot trade.'),
    ('ai', 'Portfolio', 'gpt-5.4-mini (dated)', 'Proposes at most one Lane A stock buy or a sell of a holding, with thesis and invalidation.'),
    ('ai', 'Critic', 'gpt-5.4 (dated)', 'Sees a blind packet and can reject. Returns free text plus rejected tickers.'),
    ('code', 'Desk rule', 'code, never credited to AI', 'Buys the single strongest ETF signal if liquidity, spread, trigger and sizing pass.'),
    ('code', 'Risk engine', 'code', '26 checks on every order in every account: size, cash, limits, losses, kill switch, whitelist.'),
    ('you', 'You', 'operator', 'Answer cards for the “AI + your approval” account. You alone sign in, sign rules and install releases.'),
)
SEATS_TRADER = (
    ('ai', 'Commentator', 'gpt-5.4-mini', 'Morning and after-close notes on the official decision, the regime and the day. Cannot trade.'),
    ('ai', 'News reader', 'same call', 'Summarises free headlines (Google News RSS, SEC filings) per ticker with a sentiment label. Headlines are untrusted data.'),
    ('code', 'Regime model', 'code · after the close', '3-state Gaussian HMM on VTI daily returns, retrained every night; labels calm / normal / stressed.'),
    ('code', 'Shadow Kelly', 'code · after the close', 'Raw, half and disciplined Kelly per name beside the size the risk engine uses. Never sizes a trade.'),
    ('code', 'Checker', 'code', 'Every number the model cites must match the records; uncited numbers, hype and order-like language are flagged.'),
    ('code', 'AI trader (retired)', 'never started', 'The AI-picks-trades book was retired on Oct 1 before paper trading, following the advice to keep agents off the trading path.'),
)
LAYERS = (
    ('Separate identities', 'Robinhood sign-in and tokens live under a separate macOS user. The trading code reaches only a local proxy, which checks '
     'the caller’s user id on the socket.'),
    ('Read-only tool list', 'The proxy exposes exactly 11 read methods, pinned by hash. There is no place, replace, cancel, transfer or deposit call.'),
    ('Paper-only config', 'Stage 1 requires the paper broker; the inbox and the scheduled bridge refuse anything else.'),
    ('Signed, byte-pinned rules', 'Rule files count only if byte-identical to the signed copy and only after their start time. No switch in the '
     'dashboard or environment can turn a rule on.'),
    ('Account tripwire', 'Each 10:00 run reads the Agentic account; any unexpected change in cash, positions or orders stops trading and records an incident.'),
    ('Cash bound', 'If the Agentic account ever holds more than $1,200, the run fails closed.'),
    ('Budgets with reservations', 'Every model call reserves its worst case first. Official runs: $0.40/day; analyst desk: $1/day.'),
    ('One runner', 'One launchd daily service claims each day’s run under a file lock; a second runner is refused.'),
    ('Releases with rollback', 'Installs are manifest-checked (file hashes, before/after fingerprint), then the full test suite runs on the Mac; any '
     'failure rolls back automatically.'),
)
EVIDENCE = (
    ('Three decision-makers, same money', 'AI alone, AI + your approval and Rules only start with the same $25,000 and see the same prices. '
     'The AI is only interesting if it beats Rules only after costs.'),
    ('Benchmarks', 'VTI (do nothing clever), cash, and planned seeded-random and exposure-matched VTI arms (registered, not yet in code).'),
    ('Costs counted', 'Buys pay the ask, holdings are valued at the bid, AI spend is charged to the AI accounts, and a 35% tax is applied to gains '
     'in the promotion test.'),
    ('Promotion gate', 'At least 200 filled decisions or 252 sessions, then a block bootstrap (block 21, 2,000 draws) of daily excess log return '
     'over VTI; the lower end of the 90% interval must be above zero. Even then it only reports, it does not unlock real money.'),
    ('Every look counts', 'The research harness logs every backtest, including early peeks, and deflates the Sharpe ratio by the number of trials '
     '(18 rows so far). Research is frozen until Oct 31.'),
    ('Records you can replay', 'Each run writes a decision capsule (inputs, features, signals, decision) with a hash, so any decision can be '
     're-derived later.'),
)
TRIALS = (
    ('14', 'Registered momentum 126/200, top 1', '−8.2%/yr vs VTI', 'Latch froze buying from Jul 2010'),
    ('15', 'Dual trend, volatility-targeted, 17 ETFs', '−5.0%/yr vs VTI', 'Sharpe 0.47, max drawdown 17.8%'),
    ('16', 'GEM dual momentum (VTI/EFA/AGG)', '−4.75%/yr vs VTI', 'Max drawdown 40.9%'),
    ('17', 'Sector top-3, 12-1 momentum, 10-month trend', '−3.55%/yr vs VTI', '90% interval −8.1% to +0.9%'),
)
QUESTIONS = (
    ('Is a forward paper test of this size able to show anything?', 'At ~1 trade a week, 200 decisions takes years. Would you change the metric, '
     'the sample rule, or the universe to get a usable answer in 6–12 months?'),
    ('Where should the AI sit?', 'Rules pick ETFs; the AI may still propose one single stock in the official run, and everything else it does is '
     'commentary, news and regime notes. Should the official stock path also become rules-only, with the AI purely advisory?'),
    ('Are the AI guardrails the right ones?', 'Citations must match tool numbers, a Critic can veto, code owns sizing and exits, and there is no news input. '
     'What would you add or remove, for example news, a model-free placebo per seat, or calibration scoring?'),
    ('Regime model and Kelly', 'A 3-state Gaussian HMM on VTI retrained nightly, and half-Kelly that is zero unless t ≥ 2. Would you use other '
     'features (breadth, credit spreads, VIX), a fixed refit window, or a different way to stop Kelly overbetting an unproven edge?'),
    ('How should the drawdown latch reset?', 'The 10% latch never clears today (it froze the backtest for 16 years). The draft offers “clear at 5% off '
     'peak” or “re-base the peak after 20 latched sessions”.'),
    ('Is the promotion test right?', 'Block bootstrap with a fixed 21-day block, 90% one-sided, VTI benchmark, 35% tax. Would you use a different '
     'test, a different benchmark, or a multiple-testing correction across the three accounts?'),
    ('What is missing from the risk model?', 'There are no intraday stops (checks only at 10:00 and 15:50), no correlation limit across holdings, '
     'no earnings or event filter, and sizing is volatility-based only.'),
    ('Operational risk', 'One Mac, launchd, SQLite in WAL mode, a local proxy and a private network for the dashboard. What would you harden before '
     'trusting it with real money, even small?'),
)
ROSTER = (
    ('Prof. X', 'Safety rules (code)', 'active · decides', 'The 26 coded risk checks on every order, the breakers, the tripwire and the checks on every AI note.'),
    ('Blossom', 'Research (gpt-5.4-nano)', 'active · advisory daily', 'Every day: base rate first, then the setup read for signal names and holdings. Also the first '
     'official AI stage when a stock signal or held stock appears (not triggered yet).'),
    ('Buttercup', 'Filings & news (gpt-5.4-nano)', 'active · advisory daily', 'Every day: free headlines and SEC filings per ticker, with sentiment. '
     'Never read by a trade decision.'),
    ('Mayor', 'Portfolio (gpt-5.4-mini)', 'active · advisory daily', 'Every day: reviews the whole paper book, cash drag, exit guard, chop and Kelly vs actual. '
     'Also the official Portfolio stage for single stocks (not triggered yet).'),
    ('Mojo Jojo', 'Critic (gpt-5.4-mini daily; gpt-5.4 official)', 'active · advisory daily', 'Every day: attacks the official decision and the team’s notes with fixed '
     'fail codes. Also the official Critic with veto for single stocks (not triggered yet).'),
    ('Bubbles', 'Explainer (gpt-5.4-mini)', 'active · advisory daily', 'Writes the morning and after-close note you read, last, from everyone else. Also answers your questions on the Ask Bubbles page: '
     'one model call per question, no tools, records only, every number checked by code, never read by the trading rules.'),
)
FILES = (
    ('agents/daily_cycle.py', 'The 10:00 official run and the 15:50 protective check'),
    ('research/strategy_signals.py', 'The momentum, dip and option signal rules'),
    ('agents/etf_desk_policy.py · agents/etf_exit.py', 'Desk entry rule and ETF exits (v1.5 / v1.5.1)'),
    ('risk/engine.py · risk/models.py', 'The 26 risk checks'),
    ('agents/inbox.py · broker/paper.py', 'Paper ledger, fills, settlement, breakers'),
    ('agents/scheduled_inference.py · agents/bounded_inference.py', 'Model calls, budgets and reservations'),
    ('broker_proxy/ · broker/read_gateway.py', 'Read-only proxy and the 11 allowed read methods'),
    ('agents/analyst/', 'Analyst desk: commentary, news, HMM regime, shadow Kelly, auction read'),
    ('agents/ai_trader/', 'The retired AI trader (kept for the record)'),
    ('eval/promotion_stats.py · research/harness.py', 'Promotion test and the research trial log'),
    ('preregistration.yaml + amendments', 'The signed rules (v1.4.2 root, v1.5.0–v1.6.0 layers)'),
    ('scripts/release_install.py', 'Manifest-checked install with automatic rollback'),
)


def _live(state):
    pf = state.get('portfolio') or {}
    fills = pf.get('fills') or []
    runs = [h for h in state.get('history') or [] if h.get('kind') == 'cycle']
    firm = state.get('firm') or {}
    lane_a = [p for p in pf.get('paper') or [] if p.get('lane') == 'A']
    real = pf.get('real') or {}
    facts = [('Mode', 'Stage 1 · paper only · real orders blocked'),
             ('Official runs recorded', str(len(runs)) if runs else 'not recorded'),
             ('Paper fills so far', str(len(fills))),
             ('Lane A capital per account', '$25,000 (v1.6, since Oct 1)' if any(str(p.get('start', '')).startswith('25000') for p in lane_a) else 'see Portfolio'),
             ('Real Agentic account', f'{money(real.get("cash"))} cash, never traded' if real else 'not recorded'),
             ('Analyst desk', 'set up' if (state.get('analyst') or {}).get('exists') else 'not set up yet'),
             ('AI trader', 'retired before it started (Oct 1)')]
    return ''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in facts)


def _section(sid, title, intro, body):
    return (f'<section class="ar-section" id="{sid}"><header><h2>{esc(title)}</h2>' + (f'<p>{intro}</p>' if intro else '')
            + f'</header>{body}</section>')


def _seats(items):
    return '<div class="ar-seats">' + ''.join(f'<div class="ar-seat k-{k}"><b>{esc(n)}</b><span>{esc(m)}</span><p>{esc(d)}</p></div>'
                                              for k, n, m, d in items) + '</div>'


def _cards(items):
    return '<div class="ar-cards">' + ''.join(f'<details class="ar-card"><summary><b>{esc(t)}</b><small>{esc(d)}</small></summary></details>'
                                              for t, d in items) + '</div>'


def render(state):
    c = catalogue()
    issues = [i for i in c.get('known_issues') or [] if i.get('severity') == 'high']
    toc = (('map', 'System map'), ('run', 'One trading day'), ('seats', 'Who decides'), ('roster', 'Agent roster'), ('safety', 'Safety layers'),
           ('evidence', 'How results are judged'), ('research', 'Research so far'), ('issues', 'Known issues'),
           ('questions', 'Questions for you'), ('files', 'Where to look in the code'))
    flow = ('Read', 'Features', 'Signals', 'AI gate', 'AI stages or desk rule', 'Risk engine', 'Three accounts', 'Valuation + capsule', 'Exits', 'Reports')
    return ''.join([
        '<div class="ar">',
        '<header><p class="v10-eyebrow">For reviewers · agentic AI and trading</p><h1>Architecture</h1>'
        '<p class="ar-lede">A paper-trading research desk on one Mac. Fixed rules and AI agents trade the same simulated money side by side, using real '
        'Robinhood quotes read through a read-only proxy, so the AI can be measured against a rules-only control. Real orders cannot be placed. '
        'Everything below links to the Rule book, where every number has its source file and line.</p>'
        f'<dl class="v10-stats">{_live(state)}</dl></header>',
        '<nav class="rb-toc" aria-label="Architecture sections">' + ''.join(f'<a href="#{i}">{esc(t)}</a>' for i, t in toc)
        + '<a href="/rules">Open the Rule book →</a></nav>',
        _section('map', 'System map', 'What runs where, and which way data may move. The red dashed line is the order path that does not exist.',
                 f'<div class="ar-diagram">{system_map()}</div><ul class="ar-legend"><li><i class="read"></i>reads market or account data</li>'
                 '<li><i class="write"></i>internal writes</li><li><i class="ai"></i>model calls (budgeted)</li><li><i class="you"></i>you</li>'
                 '<li><i class="blocked"></i>blocked: no such capability</li></ul>'),
        _section('run', 'One trading day', 'Every weekday the same sequence runs once. The full minute-by-minute day and each stage’s gates are in '
                 'the Rule book.',
                 '<p class="rb-toc">' + ''.join(f'<a href="/rules#cycle">{i + 1}. {esc(s)}</a>' for i, s in enumerate(flow)) + '</p>'
                 '<div class="ar-cards">'
                 '<details class="ar-card"><summary><b>10:00 ET · official run</b><small>Claims the day under a lock, reads the account and the market, '
                 'computes features from completed sessions only, runs the rules, calls the AI only if needed, checks every order, fills the three paper '
                 'accounts and writes a hashed decision capsule.</small></summary></details>'
                 '<details class="ar-card"><summary><b>10:00–15:30 · your answers</b><small>Cards for the approval account fill only at a fresh price at '
                 'or under the limit, and expire at 15:30 ET.</small></summary></details>'
                 '<details class="ar-card"><summary><b>After 10:00 · analyst morning note</b><small>Inside the same service tick, after the official run '
                 'completed: free headlines are fetched and a model writes commentary and news notes. It cannot trade.</small></summary></details>'
                 '<details class="ar-card"><summary><b>16:15 ET · analyst after-close job</b><small>Daily bars for the 23 names, regime model retrained, '
                 'shadow Kelly, daily auction read, news and the close note.</small></summary></details>'
                 '<details class="ar-card"><summary><b>15:50 ET · protective check</b><small>Sells a holding at the bid if it is 8% below cost, at or '
                 'below its 200-day average, or (ETFs) momentum turned non-positive.</small></summary></details>'
                 '<details class="ar-card"><summary><b>16:50 ET · nightly screen</b><small>Shadow-only scan of the S&P 500 for research notes. It never '
                 'trades and never changes the 23 registered names.</small></summary></details>'
                 '<details class="ar-card"><summary><b>Friday 16:30 · weekly report</b><small>Accounts vs VTI and cash, costs, decisions and incidents, '
                 'sent as a notification.</small></summary></details></div>'),
        _section('seats', 'Who decides', 'The official desk is what counts. Since Oct 1 the other AI work is advisory only: it explains, it does not decide.',
                 '<h3>Official desk</h3>' + _seats(SEATS_OFFICIAL) + '<h3>Analyst desk (AI off the trading path)</h3>' + _seats(SEATS_TRADER)
                 + '<p class="v10-note">Model ids are pinned to dated versions; a different model id is refused. Prompts and specs are '
                 'hashed; changing either starts a new trial.</p>'),
        _section('roster', 'Agent roster, as it really is today', 'Decides = can stop or allow a trade; advisory = writes every trading day but no trade reads it '
                 '(AI stays off the trading path). Blossom, Mayor and Mojo Jojo also hold their official single-stock roles, which run only when needed.',
                 '<div class="ar-seats">' + ''.join(f'<div class="ar-seat k-{"code" if "decides" in st else "ai"}">'
                                                    f'<b>{esc(n)} · {esc(r)}</b><span>{esc(st)}</span><p>{esc(d)}</p></div>' for n, r, st, d in ROSTER) + '</div>'),
        _section('safety', 'Safety layers', 'Independent layers. Any one of them is enough to stop a real order.', _cards(LAYERS)),
        _section('evidence', 'How results are judged', 'Designed so a lucky streak or a tuned backtest cannot be mistaken for skill.', _cards(EVIDENCE)),
        _section('research', 'Research so far', 'Every registered backtest since the harness existed. None beat simply holding VTI after costs and tax.',
                 '<div class="table-wrap"><table class="mini ar-table"><thead><tr><th>Trial</th><th>Recipe</th><th>Excess vs VTI</th><th>Note</th>'
                 '<th>Verdict</th></tr></thead><tbody>'
                 + ''.join(f'<tr><td>{esc(n)}</td><td>{esc(r)}</td><td class="neg">{esc(x)}</td><td>{esc(note)}</td><td>NOT PROVEN</td></tr>'
                           for n, r, x, note in TRIALS)
                 + '<tr><td>18</td><td>AI trader forward book (ai_trader_fwd_v1)</td><td>—</td><td>Retired before start on Oct 1 (agents kept off the trading path)'
                   '</td><td>WITHDRAWN</td></tr></tbody></table></div>'
                 '<p class="v10-note">Backtests are price-only (no dividends), on Robinhood daily bars from 2005; rows 1–13 are early looks that still '
                 'count against the deflated Sharpe.</p>'),
        _section('issues', 'Known issues (high severity)', 'Found while writing the Rule book; the full list, with medium and low items, is there.',
                 '<div class="rb-groupgrid">' + ''.join(
                     f'<details class="rb-rule rb-issue sev-high"><summary><b>{esc(i.get("id", "").replace("ki-", "").replace("-", " "))}</b>'
                     f'<span class="rb-status missing">high</span><span class="rb-plain">{esc((i.get("issue") or "")[:220])}…</span></summary>'
                     f'<div class="rb-body"><p>{esc(i.get("issue"))}</p><p class="rb-src">{esc(i.get("source"))}</p></div></details>' for i in issues)
                 + '</div><p><a href="/rules#issues">All known issues →</a></p>'),
        _section('questions', 'Questions for you', 'Where a second opinion would change the most.',
                 '<ol class="ar-q">' + ''.join(f'<li><b>{esc(q)}</b><small>{esc(d)}</small></li>' for q, d in QUESTIONS) + '</ol>'),
        _section('files', 'Where to look in the code', 'The repository is on GitHub; these are the files that matter most.',
                 '<div class="table-wrap"><table class="mini ar-table"><tbody>'
                 + ''.join(f'<tr><td><code>{esc(f)}</code></td><td>{esc(d)}</td></tr>' for f, d in FILES) + '</tbody></table></div>'),
        '</div>'])
