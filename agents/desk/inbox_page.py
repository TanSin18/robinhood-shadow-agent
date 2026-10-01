"""Inbox: cards from the Official rule and S&P watch notes, your answers, and the journal.

Never shows Official paper P&L: Official results live on Portfolio and the scoreboard.
Answers post to /inbox/answer (front door, its own token). Nothing here places an order.
"""
from .components import esc
from agents.cards import LIVE_COPY_ENABLED

ANSWER_TEXT = {'paper_only': 'Paper only', 'may_copy_live': 'I may copy live', 'skip': 'Skip'}


def _record(rec):
    if not rec or rec.get('status') == 'NO_RECORD_YET':
        return '<p class="ib-record none">Record: <strong>No record yet.</strong> Nothing has closed from this source.</p>'
    ratio = rec.get('premium_out_over_in')
    return (f'<p class="ib-record">Record (from the journal): {esc(rec.get("fires"))} closed · {esc(rec.get("wins"))} won · '
            f'{esc(rec.get("losses"))} lost · {esc(rec.get("zeros"))} went to zero'
            + (f' · premium out/in {esc(ratio)}' if ratio else '')
            + (f' · mean excess vs cash {esc(rec.get("mean_excess_vs_cash"))}' if rec.get('mean_excess_vs_cash') else '') + '</p>')


def _card(c, csrf):
    order = ''
    if c.get('side'):
        order = (f'<dl class="ib-order"><div><dt>Side</dt><dd>{esc(c["side"])}</dd></div><div><dt>Quantity</dt><dd>{esc(c["quantity"])}</dd></div>'
                 f'<div><dt>Est. cost</dt><dd>${esc(c["est_cost_usd"])}</dd></div><div><dt>Max loss</dt><dd>${esc(c["max_loss_usd"])}</dd></div></dl>')
    facts = ''.join(f'<li>{esc(f)}</li>' for f in c.get('facts', []))
    opinion = f'<p class="ib-opinion"><span class="ib-tag">AI opinion</span> {esc(c["opinion"])}</p>' if c.get('opinion') else ''
    if c.get('answer'):
        action = f'<p class="ib-answered">You answered: <strong>{esc(ANSWER_TEXT.get(c["answer"]["answer"], c["answer"]["answer"]))}</strong> · {esc(c["answer"]["answered_at"][:16])}</p>'
    else:
        buttons = ''
        for value, text in ANSWER_TEXT.items():
            disabled = value == 'may_copy_live' and (not c.get('copyable') or not LIVE_COPY_ENABLED)
            buttons += (f'<button type="submit" name="answer" value="{value}"' + (' disabled' if disabled else '') + f'>{esc(text)}</button>')
        reason = c.get('copy_block_reason') if not c.get('copyable') else (None if LIVE_COPY_ENABLED else
                 'Live copy turns on once the account safety check accepts acknowledgements.')
        why = f'<p class="ib-why">{esc(reason)}</p>' if reason else ''
        action = (f'<form method="post" action="/inbox/answer" class="ib-actions"><input type="hidden" name="csrf" value="{esc(csrf)}">'
                  f'<input type="hidden" name="card" value="{esc(c["id"])}">{buttons}</form>{why}')
    return (f'<article class="ib-card"><header><strong class="code">{esc(c["ticker"])}</strong><span>{esc(c["instrument"])}</span>'
            f'<span class="ib-src">{esc(c["recipe_id"])}</span></header><p class="ib-label">{esc(c["label"])}</p>{order}'
            f'<h4>Why it matched (facts)</h4><ul>{facts}</ul><p><strong>What kills it:</strong> {esc(c["kills"])}</p>{opinion}'
            f'{_record(c.get("record"))}{action}</article>')


def render(state):
    inbox = state.get('card_inbox') or {'cards': [], 'journal': [], 'acks': []}
    csrf = state.get('inbox_csrf', '')
    official = [c for c in inbox['cards'] if c['source'] == 'official_rule']
    watch = [c for c in inbox['cards'] if c['source'] == 'watch']
    col = lambda items, empty: ''.join(_card(c, csrf) for c in items) or f'<p class="muted">{esc(empty)}</p>'
    journal = ''.join(f'<tr><td>{esc(j["at"][:16])}</td><td class="code">{esc(j["recipe_id"])}</td><td>{esc(j["event"])}</td>'
                      f'<td class="code">{esc(j.get("card_id") or "")}</td></tr>' for j in inbox['journal'])
    acks = ''.join(f'<tr><td class="code">{esc(a["ticker"])}</td><td>{esc(a["side"])}</td><td>{esc(a["quantity"])}</td>'
                   f'<td>{esc(a["window_start"][:16])} → {esc(a["window_end"][11:16])}</td><td>{esc(a["status"].replace("_", " ").lower())}</td></tr>'
                   for a in inbox['acks'])
    return ('<div class="room-head"><div><h1>Inbox</h1><p>Cards the desk may show you. Not recommendations, never orders. '
            'Official results are on Portfolio and are never mixed in here.</p></div></div>'
            '<p class="capital-note is-scheduled"><strong>Research freeze until Oct 31:</strong> cards come only from the Official '
            'rule and S&amp;P 500 watch notes. Explore ideas start in November, each as a logged trial. '
            '"I may copy live" stays off until the account safety check accepts acknowledgements.</p>'
            '<div class="ib-cols"><section><h2>From the Official rule</h2>'
            + col(official, 'No cards yet.') + '</section><section><h2>Watch notes · no orders</h2>'
            + col(watch, 'No watch notes yet. Up to five, from the S&P 500 screen.') + '</section></div>'
            '<section class="room-card"><div class="card-head"><h3>Journal</h3><span class="muted small">every card, answer and outcome</span></div>'
            + (f'<div class="table-wrap"><table class="mini"><thead><tr><th>When (UTC)</th><th>Source</th><th>Event</th><th>Card</th></tr></thead><tbody>{journal}</tbody></table></div>'
               if journal else '<p class="muted">Empty. Every card you get, every answer and every result will be listed here, including losses and zeros.</p>')
            + '</section><section class="room-card"><div class="card-head"><h3>Live-copy acknowledgements</h3><span class="muted small">recorded, not yet enforced</span></div>'
            + (f'<div class="table-wrap"><table class="mini"><thead><tr><th>Ticker</th><th>Side</th><th>Quantity</th><th>Window</th><th>Status</th></tr></thead><tbody>{acks}</tbody></table></div>'
               if acks else '<p class="muted">None.</p>') + '</section>')
