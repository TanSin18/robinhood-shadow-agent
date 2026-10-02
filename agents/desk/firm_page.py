"""AI trader (forward paper book ai_trader_fwd_v1): scoreboard, today's tickets, book-B cards, positions.

Separate from Official everywhere: its own database, its own page. Book-B answers post to
/firm/answer (front door, its own token): YES, CUT to half, NO or SKIP. Never adds size or a name.
"""
import json

from .components import esc


def _pct(v):
    return '—' if v is None else f'{float(v) * 100:+.2f}%'


def _line(name, label, line):
    if not line:
        return f'<tr><td>{esc(label)}</td><td colspan="4" class="muted">No values yet</td></tr>'
    vv = line.get('vs_vti') or {}
    ci = vv.get('ci90')
    off = (line.get('vs_official') or {}).get('annual_excess')
    return (f'<tr><td>{esc(label)}</td><td class="num">${esc(line["value_after_costs"])}</td>'
            f'<td class="num">{_pct(vv.get("annual_excess"))}' + (f' <small>({_pct(ci[0])} to {_pct(ci[1])})</small>' if ci else '') + '</td>'
            f'<td class="num">{_pct(off)}</td><td class="num">${esc(line["vs_cash"]["excess_usd"])}</td></tr>')


def render(state):
    firm = state.get('firm')
    csrf = state.get('inbox_csrf', '')
    head = ('<div class="room-head"><div><h1>AI trader</h1><p>A forward paper experiment: can a team of AI models pick trades '
            'that beat VTI and beat random picks, after spreads, tax and its own AI bill? Separate from the registered paper run.</p></div></div>')
    if not firm or not firm.get('exists'):
        return head + ('<p class="capital-note is-scheduled"><strong>Not set up yet.</strong> The book is registered as '
                       '<code>ai_trader_fwd_v1</code> and can start paper trading on Monday Oct 5 at the earliest, after '
                       'Thursday\'s registered paper run is confirmed. Until it is initialised nothing runs.</p>')
    board = firm['board']
    mode_note = {'WATCH_ONLY': 'Watch-only: the seats run and tickets are recorded, but nothing is bought.',
                 'PAPER': 'Paper trading: book A fills, book B waits for you, book C copies with a random ticker.',
                 'RETIRED': 'Retired: nothing runs.'}.get(firm['mode'], firm['mode'])
    html = head + (f'<p class="capital-note {"is-live" if firm["mode"] == "PAPER" else "is-scheduled"}"><strong>{esc(firm["mode"].replace("_", " ").title())}.</strong> '
                   f'{esc(mode_note)} Verdict so far: <strong>{esc(board["verdict"].replace("_", " "))}</strong> '
                   f'({esc(board["closed_trades_A"])} closed trades in book A; needs 200 or a full year). AI bill so far: ${esc(board["ai_bill_usd"])}.</p>')
    lines = board.get('lines', {})
    ac = (board.get('A_vs_C') or {})
    html += ('<section class="room-card"><div class="card-head"><h3>Scoreboard</h3><span class="muted small">after spreads, AI bill and estimated tax</span></div>'
             '<div class="table-wrap"><table class="mini"><thead><tr><th>Book</th><th>Value</th><th>vs VTI per year (90% range)</th>'
             '<th>vs registered run per year</th><th>vs cash</th></tr></thead><tbody>'
             + _line('A', 'A · automatic', lines.get('A')) + _line('B', 'B · with operator approval', lines.get('B'))
             + _line('C', 'C · random picks (control)', lines.get('C')) + '</tbody></table></div>'
             f'<p class="small">Book A vs random picks: {_pct(ac.get("annual_excess"))} per year'
             + (f' (90% {_pct(ac["ci90"][0])} to {_pct(ac["ci90"][1])})' if ac.get('ci90') else '') + '. If AI does not beat random, '
             'any win over VTI is labelled luck or market exposure.</p></section>')
    cards = ''
    for c in firm['cards']:
        tk = c['ticket']
        if c['status'] == 'PENDING':
            act = (f'<form method="post" action="/firm/answer" class="ib-actions"><input type="hidden" name="csrf" value="{esc(csrf)}">'
                   f'<input type="hidden" name="card" value="{esc(c["id"])}">'
                   '<button type="submit" name="answer" value="YES">Yes</button><button type="submit" name="answer" value="CUT">Yes, half size</button>'
                   '<button type="submit" name="answer" value="NO">No</button><button type="submit" name="answer" value="SKIP">Skip</button></form>')
        else:
            act = f'<p class="ib-answered">Status: <strong>{esc(c["status"].replace("_", " ").lower())}</strong></p>'
        cited = ''.join(f'<li><code>{esc(n.get("tool_id"))}</code> {esc(n.get("field"))} = {esc(n.get("value"))}</li>' for n in tk.get('cited_numbers', []))
        cards += (f'<article class="ib-card"><header><strong class="code">{esc(tk.get("ticker"))}</strong><span>{esc(tk.get("setup_tag"))}</span>'
                  f'<span class="ib-src">expires {esc(c["expires_at"][11:16])} UTC</span></header><p class="ib-label">NOT A RECOMMENDATION — your click</p>'
                  f'<p>{esc(tk.get("thesis"))}</p><dl class="ib-order"><div><dt>Wrong below</dt><dd>${esc(tk.get("invalidation_price"))}</dd></div>'
                  f'<div><dt>Time stop</dt><dd>{esc(tk.get("time_stop_sessions"))} sessions</dd></div></dl>'
                  f'<p class="small"><strong>False tomorrow if:</strong> {esc(tk.get("false_tomorrow_if"))}</p><h4>Numbers it relies on</h4><ul>{cited}</ul>{act}</article>')
    html += ('<section><h2 class="section-title">Book B · your cards</h2><div class="ib-cols"><section>'
             + (cards or '<p class="muted">No cards. A card appears when the team approves a trade; book A has already taken it.</p>')
             + '</section></div></section>')
    rows = ''.join(f'<tr><td>{esc(t["day"])}</td><td class="code">{esc(t["ticker"])}</td><td>{esc(t["status"].replace("_", " ").lower())}</td>'
                   f'<td class="small">{esc(", ".join(t["fails"]) or (t.get("critic_reason") or ""))}</td></tr>' for t in firm['tickets'])
    html += ('<section class="room-card"><div class="card-head"><h3>Tickets</h3><span class="muted small">every idea, including the ones that failed</span></div>'
             + (f'<div class="table-wrap"><table class="mini"><thead><tr><th>Day</th><th>Ticker</th><th>Status</th><th>Why</th></tr></thead><tbody>{rows}</tbody></table></div>'
                if rows else '<p class="muted">None yet. "Nothing today" is a normal answer.</p>') + '</section>')
    pos = ''.join(f'<tr><td>{b}</td><td class="code">{esc(t)}</td><td class="num">{esc(p["quantity"])}</td><td class="num">${esc(p["average_cost"])}</td>'
                  f'<td class="num">${esc(p.get("invalidation_price", "—"))}</td><td class="num">{esc(p.get("sessions_held"))}/{esc(p.get("time_stop_sessions"))}</td></tr>'
                  for b, ps in firm['positions'].items() for t, p in ps.items())
    html += ('<section class="room-card"><div class="card-head"><h3>Open positions</h3></div>'
             + (f'<div class="table-wrap"><table class="mini"><thead><tr><th>Book</th><th>Ticker</th><th>Quantity</th><th>Cost</th><th>Wrong below</th><th>Sessions / limit</th></tr></thead><tbody>{pos}</tbody></table></div>'
                if pos else '<p class="muted">None.</p>') + '</section>')
    return html


def load(official_db):
    """Read the firm's records for the page. Missing database = not set up."""
    from agents.ai_trader.hook import default_path
    path = default_path(official_db)
    if not path.is_file():
        return {'exists': False}
    from agents.ai_trader.scoring import scoreboard
    from agents.ai_trader.spec import load_spec
    from agents.ai_trader.store import TraderStore
    store = TraderStore(path, official_db)
    spec = load_spec()
    with store.connect() as db:
        cards = [dict(r) for r in db.execute('SELECT * FROM operator_cards ORDER BY issued_at DESC LIMIT 20')]
    tickets = {t['id']: t for t in store.tickets()}
    for c in cards:
        t = tickets.get(c['ticket_id'])
        c['ticket'] = json.loads(t['payload_json']) if t else {}
    recent = []
    for t in list(tickets.values())[-40:][::-1]:
        checks = json.loads(t['checks_json'] or '{}')
        critic = json.loads(t['critic_json'] or '{}')
        recent.append({'day': t['day'], 'ticker': t['ticker'], 'status': t['status'], 'fails': checks.get('fails', []),
                       'critic_reason': critic.get('reason')})
    return {'exists': True, 'mode': store.mode(), 'board': scoreboard(store, spec), 'cards': cards, 'tickets': recent,
            'positions': {b: store.book(b).positions for b in ('A', 'B', 'C')}}
