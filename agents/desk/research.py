"""Measurement panel: is there an edge, and how would we know?

Four record-backed cards for the Checks page: the ETF-rule backtest, the
pre-declared statistical promotion gate, the v1.6 same-day protective exit, and
the nightly S&P 500 shadow screen. Missing is shown as missing, never as a pass.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from .components import esc

ET = ZoneInfo('America/New_York')
ARMS = {'agent_alone': 'AI alone', 'with_approvals': 'AI + your approval', 'deterministic_no_ai': 'Rules only (no AI)'}


def _when(value):
    try:
        dt = datetime.fromisoformat(str(value))
        return dt.astimezone(ET).strftime('%a %b %-d, %-I:%M %p ET') if dt.tzinfo else 'time not recorded'
    except (TypeError, ValueError):
        return 'not recorded'


def _pct(v, signed=True):
    try:
        return f'{float(v) * 100:+.1f}%' if signed else f'{float(v) * 100:.1f}%'
    except (TypeError, ValueError):
        return '—'


def _card(title, sub, body, tone=''):
    return (f'<section class="room-card measure {tone}"><div class="card-head"><h3>{esc(title)}</h3>'
            f'<span class="muted small">{esc(sub)}</span></div>{body}</section>')


def backtest_card(report):
    if not report:
        return _card('Is there an edge? · backtest', 'The registered ETF rule vs VTI, sectors and cash',
                     '<p class="muted">Not run yet. It needs the long price history (research backfill), then '
                     '<code>research.backtest_etf_rule</code>. Until then nothing here claims an edge.</p>')
    s = report.get('summary') or {}
    rows = ''
    for key, label in (('registered_rule', 'Registered rule (as sized live)'), ('signal_full_invest_top1', 'Signal alone, fully invested'),
                       ('vti_buy_hold', 'VTI buy & hold'), ('equal_weight_spdr_sectors', 'Equal-weight sectors')):
        x = s.get(key) or {}
        rows += (f'<tr><td>{esc(label)}</td><td class="num">{_pct(x.get("cagr_after_all_tax"))}</td><td class="num">{esc(x.get("sharpe_rf0", "—"))}</td>'
                 f'<td class="num">{_pct(x.get("max_drawdown"), False)}</td><td class="num">{esc(x.get("trades", "—"))}</td></tr>')
    ex = (report.get('excess_vs_vti') or {}).get('signal_full_invest_top1') or {}
    ci = ex.get('ci90') or [None, None]
    verdict = report.get('verdict') or []
    passed = bool(verdict) and str(verdict[-1]).startswith('PASS')
    data = report.get('data') or {}
    body = (f'<p class="measure-verdict {"ok" if passed else "no"}">{esc(verdict[-1] if verdict else "No verdict recorded")}</p>'
            '<div class="table-wrap"><table class="mini"><thead><tr><th>Line</th><th>Growth / yr after tax</th><th>Sharpe</th><th>Worst drop</th><th>Trades</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>'
            f'<p class="small">Signal vs VTI, 90% range of yearly excess: {_pct(ci[0])} to {_pct(ci[1])}.</p>'
            f'<p class="muted small">Data {esc(data.get("first_session", "?"))} → {esc(data.get("last_session", "?"))}, split-adjusted prices without dividends. '
            'Costs, one-day delay and tax included.</p>')
    return _card('Is there an edge? · backtest', 'The registered ETF rule vs VTI, sectors and cash', body, 'ok' if passed else 'warn')


def promotion_card(gate):
    if not gate or gate.get('unavailable'):
        return _card('Scoreboard · statistical gate', 'Official runs only, from Oct 1 09:30 ET',
                     '<p class="muted">Installs with tonight’s runtime release. Until it reports, nothing counts as proven.</p>')
    rows = ''
    for arm, r in (gate.get('arms') or {}).items():
        ci = r.get('ci90')
        rows += (f'<tr><td>{esc(ARMS.get(arm, arm))}</td><td class="num">{esc(r.get("sessions"))}</td><td class="num">{esc(r.get("decisions"))}</td>'
                 f'<td class="num">{_pct(r.get("annual_excess")) if r.get("annual_excess") is not None else "—"}</td>'
                 f'<td class="num">{(_pct(ci[0]) + " to " + _pct(ci[1])) if ci else "—"}</td>'
                 f'<td><span class="pill-{"real" if r.get("verdict") == "EDGE_SHOWN" else "paper"}">{esc(r.get("verdict", "").replace("_", " ").lower())}</span></td></tr>')
    body = ('<div class="table-wrap"><table class="mini"><thead><tr><th>Account</th><th>Sessions</th><th>Decisions</th><th>Yearly excess vs VTI</th><th>90% range</th><th>Verdict</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>'
            f'<p class="muted small">{esc(gate.get("rule", ""))}. After spread, AI cost and an estimated 35% tax. Never unlocks real money.</p>')
    return _card('Scoreboard · statistical gate', 'Official runs only, from Oct 1 09:30 ET', body)


def protective_card(items, rebase):
    latest = sorted(items or [], key=lambda x: str(x.get('timestamp')), reverse=True)[:5]
    rows = ''.join(f'<tr><td>{esc(_when(x.get("timestamp")))}</td><td>{esc(x.get("status") or "CHECKED")}</td>'
                   f'<td class="num">{esc(x.get("fired", "—"))}</td><td>{esc(", ".join(x.get("held") or []) or "—")}</td></tr>' for x in latest)
    body = ('<p class="small">Every trading day at 3:50 PM ET: sell a holding whose live price is at or below its 200-day average, an ETF whose '
            '126-day momentum has turned, or anything 8% below its average cost. Agents sell at once; your approval account gets a SELL card.</p>')
    body += (('<div class="table-wrap"><table class="mini"><thead><tr><th>Checked</th><th>Status</th><th>Sold</th><th>Holdings checked</th></tr></thead>'
              f'<tbody>{rows}</tbody></table></div>') if rows else '<p class="muted">No check recorded yet. The first one runs Thursday at 3:50 PM ET.</p>')
    if rebase:
        body += f'<p class="muted small">Paper capital reset to ${esc(rebase.get("capital"))} for lane {esc(rebase.get("lane"))} at {esc(_when(rebase.get("timestamp")))}; the earlier build-phase ledger is archived.</p>'
    return _card('Same-day protective exit', 'v1.6 · 3:50 PM ET, once per session', body)


def screen_card(screen):
    if not screen:
        return _card('S&P 500 shadow screen', 'Nightly 4:50 PM ET · never trades',
                     '<p class="muted">No night recorded yet. It starts once the nightly service is installed.</p>')
    funnel = screen.get('funnel') or {}
    steps = ''.join(f'<li><b>{esc(v)}</b> {esc(k.replace("_", " "))}</li>' for k, v in funnel.items())
    short = ', '.join(screen.get('shortlist') or []) or 'none'
    body = (f'<p class="small">Last run {esc(_when(screen.get("at")))} · {esc(screen.get("status"))}</p>'
            + (f'<ol class="funnel-steps">{steps}</ol>' if steps else '')
            + f'<p class="small">Shortlist: <span class="code">{esc(short)}</span></p>'
            '<p class="muted small">Shadow only: the official run still uses the 23 registered tickers until a later amendment after 20+ clean nights. '
            'Current constituents only, so any history drawn from it is survivorship-biased.</p>')
    return _card('S&P 500 shadow screen', 'Nightly 4:50 PM ET · never trades', body)


def render(research):
    research = research or {}
    return ('<section class="measure-grid" aria-label="Measurement">'
            + backtest_card(research.get('backtest')) + promotion_card(research.get('promotion'))
            + protective_card(research.get('protective'), research.get('rebase')) + screen_card(research.get('screen'))
            + '</section>')
