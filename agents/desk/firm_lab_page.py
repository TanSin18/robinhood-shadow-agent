"""Firm Lab: read-only status page. BUILD / OBSERVE, no fills, no track record.

Shows only what is recorded in the Firm Lab database (opened read-only) plus the fixed statements that
cannot change without an operator decision. It has no form and no action of its own.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from .components import esc

ET = ZoneInfo('America/New_York')
STATUS_TONE = {'AVAILABLE': 'good', 'UNAVAILABLE': 'stop', 'NOT_STARTED': 'neutral', 'BUILD_ONLY': 'warn', 'PARTIAL_EXISTING': 'warn',
               'BLOCKED': 'stop'}
LABELS = {
    'daily_closes': 'Daily closes', 'daily_baseline_features': 'Daily baseline features', 'fundamentals': 'Fundamentals',
    'analyst_revisions': 'Analyst revisions', 'earnings_transcripts': 'Earnings-call transcripts', 'intraday_bars': 'Intraday bars',
    'vwap': 'VWAP', 'opening_range': 'Opening range', 'time_of_day_rvol': 'Time-of-day RVOL', 'trade_flow': 'Aggressive order flow',
    'order_book': 'Quote and order-book imbalance', 'options_chain': 'Option chain data', 'options_strategy': 'Options strategy',
    'news_catalysts': 'News and catalysts', 'sec_filings': 'SEC filings', 'sector_engine': 'Sector engine', 'ml_ranker': 'ML ranker',
    'portfolio_optimizer': 'Portfolio optimizer',
}
WARNING = ('Counterfactual results generated during Firm Lab development are development data. They are not an untouched forward test '
           'and do not count as results of any registered Firm trading trial.')


def _view():
    """firm_lab.view, the package's read-only view. Nothing else of the package is used by the dashboard.

    The dashboard service runs the frozen runtime and overlays only the ``agents`` package, so the research package that
    sits beside it is not on the import path there. In that case exactly that one package is loaded from its own folder;
    the import path itself is left as it is."""
    try:
        from firm_lab import view
    except ModuleNotFoundError as error:
        if error.name != 'firm_lab':
            raise
        import importlib.util
        import sys
        folder = Path(__file__).resolve().parents[2] / 'firm_lab'
        spec = importlib.util.spec_from_file_location('firm_lab', folder / '__init__.py', submodule_search_locations=[str(folder)])
        if spec is None or not (folder / '__init__.py').is_file():
            raise
        module = importlib.util.module_from_spec(spec)
        sys.modules['firm_lab'] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop('firm_lab', None)
            raise
        from firm_lab import view
    return view


def load(official_db):
    return _view().load(official_db=official_db)


def _when(value):
    try:
        d = datetime.fromisoformat(str(value))
        return d.astimezone(ET).strftime('%a %b %-d, %-I:%M %p ET') if d.tzinfo else 'not recorded'
    except (TypeError, ValueError):
        return 'not recorded'


def _num(value, places=2, pct=False):
    try:
        v = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return '—'
    return f'{v * 100:+.{places}f}%' if pct else f'{v:,.{places}f}'


def _chip(status):
    """The exact registry status. An unknown status is shown as UNAVAILABLE, never as something better."""
    status = status if status in STATUS_TONE else 'UNAVAILABLE'
    return f'<span class="cat cat-{STATUS_TONE[status]}">{esc(status)}</span>'


def _facts(rows):
    return '<dl class="v10-facts fl-facts">' + ''.join(f'<div><dt>{esc(k)}</dt><dd>{v}</dd></div>' for k, v in rows) + '</dl>'


def _registry(fl):
    rows = fl.get('capabilities')
    if rows:
        return rows, fl.get('data_readiness') or _view().readiness(rows), ''
    defaults = _view().defaults()
    return (defaults['capabilities'], defaults['data_readiness'],
            '<p class="v10-note">The Firm Lab database is not created on this machine yet; this is the registry it starts with.</p>')


CONNECTION_TONE = {'ACTIVE': 'good', 'CONFIGURED': 'warn', 'NOT CONFIGURED': 'stop', 'ERROR': 'stop', 'NOT SELECTED': 'neutral'}
VALIDATION_TONE = {'PASS': 'good', 'FAIL': 'stop', 'INCOMPLETE': 'warn', 'NOT RUN': 'neutral'}


def _stamp(value):
    """A stored time in New York time when it is a full timestamp; a stored date is shown as the date it is."""
    if not value:
        return ''
    text = _when(value)
    return str(value) if text == 'not recorded' else text


def _tag(text, tones, fallback):
    """A state word with its tone. An unknown word is shown with the cautious fallback tone, never a better one."""
    return f'<span class="cat cat-{tones.get(text, fallback)}">{esc(text)}</span>'


def _readiness(fl):
    """Data Readiness: per data domain, the chosen provider, whether it is connected, whether its data passed validation,
    what is actually stored, and the capability state. Infrastructure, not a trading feature."""
    _, ready, note = _registry(fl)
    body = ''
    for r in ready:
        provider = r.get('provider')
        connection = str(r.get('connection') or 'NOT SELECTED')
        validation = str(r.get('validation') or 'NOT RUN')
        count = int(r.get('observations') or 0)
        span = ' to '.join(x for x in (_stamp(r.get('oldest')), _stamp(r.get('newest'))) if x)
        failures = r.get('failures') or {}
        issues = ', '.join(r.get('validation_issues') or [])
        sample = ' · '.join(f'{s.get("instrument")} {s.get("status")}' for s in (r.get('sample') or [])[:12])
        body += (
            f'<tr><td data-label="Data"><b>{esc(r["domain"])}</b></td><td data-label="Capability">{_chip(r["status"])}</td>'
            f'<td data-label="Provider">{esc(provider) if provider else "none selected"}</td>'
            f'<td data-label="Connection">{_tag(connection, CONNECTION_TONE, "stop")}'
            f'<span class="small fl-sub">{esc(r.get("connection_detail") or "")}</span></td>'
            f'<td data-label="Validation">{_tag(validation, VALIDATION_TONE, "neutral")}'
            f'<span class="small fl-sub">{esc(issues or sample)}</span></td>'
            f'<td data-label="Stored"><b>{count:,}</b><span class="small fl-sub">{esc(span) if count else "nothing stored"}</span></td>'
            f'<td data-label="Last successful ingest">{esc(_stamp(r.get("last_successful_ingest")) or "never")}</td>'
            f'<td data-label="Quality failures" class="small">'
            f'{esc("; ".join(f"{code} × {n}" for code, n in sorted(failures.items()))) if failures else "none recorded"}</td></tr>'
            f'<tr class="fl-ready-note"><td colspan="8" class="small"><b>Limitation.</b> <span class="fl-limit">{esc(r.get("limitation") or "")}</span> '
            f'<b>Required next.</b> <span class="fl-next">{esc(r.get("required_next") or "")}</span></td></tr>')
    cross = fl.get('sec_cross_check')
    cross_note = ''
    if cross:
        cross_note = ('<p class="v10-note">SEC cross-check: of '
                      f'{esc(cross.get("reports", 0))} as-reported filings stored from the fundamentals provider, {esc(cross.get("MATCH", 0))} match exactly one '
                      f'stored SEC filing on the filing date, {esc(cross.get("NO_SEC_FILING_STORED", 0))} have no stored SEC filing and '
                      f'{esc(cross.get("AMBIGUOUS", 0))} are ambiguous. An acceptance time is read from the SEC record only; none is built from a date.</p>')
    return (note + '<p class="v10-note">Infrastructure readiness only: which raw data Firm Lab holds, from which provider, and whether it passed validation. '
            'Choosing a provider is not a connection, and a connection is not a capability: a row becomes AVAILABLE only after real rows are stored and '
            'validated. Nothing on this list feeds a ranking, a selection or a trade.</p>'
            '<div class="table-wrap"><table class="mini fl-ready"><colgroup><col class="fl-r1"><col class="fl-r2"><col class="fl-r3"><col class="fl-r4">'
            '<col class="fl-r5"><col class="fl-r6"><col class="fl-r7"><col></colgroup>'
            '<thead><tr><th>Data</th><th>Capability</th><th>Provider</th><th>Connection</th><th>Validation</th><th>Stored</th>'
            '<th>Last successful ingest</th><th>Quality failures</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div>' + cross_note +
            '<p class="v10-note">Capability — AVAILABLE: stored data that passed validation. PARTIAL_EXISTING: a source exists elsewhere in the system but is '
            'not sufficient for, or not connected to, Firm Lab. BUILD_ONLY: storage exists and nothing reads it. UNAVAILABLE: no value is stored, estimated '
            'or filled in. Connection — NOT CONFIGURED: credentials or provider activation by the operator are required. Validation — PASS: every run of the '
            'latest sample was accepted; FAIL: a response was refused whole and nothing from it was kept. Details: docs/firm_lab/data_sources.md and '
            'docs/firm_lab/provider_matrix.md.</p>')


def _capabilities(fl):
    """Everything in the registry that is not a data domain: derived measures and strategy components."""
    rows, ready, _ = _registry(fl)
    data_keys = {r['capability'] for r in ready}
    body = ''.join(f'<tr><td><b>{esc(LABELS.get(r["capability"], r["capability"]))}</b></td><td>{_chip(r["status"])}</td>'
                   f'<td>{esc(r.get("provider") or "none")}</td><td class="small">{esc(r.get("detail") or "")}</td></tr>'
                   for r in rows if r['capability'] not in data_keys)
    return ('<div class="table-wrap"><table class="mini fl-cap"><colgroup><col class="fl-c1"><col class="fl-c2"><col class="fl-c3"><col></colgroup>'
            '<thead><tr><th>Component</th><th>Status</th><th>Source</th><th>What that means</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div>'
            '<p class="v10-note">Measures that need intraday data are not calculated from daily bars. NOT_STARTED means nothing is built.</p>')


def _baseline(fl):
    b = fl.get('baseline')
    if not b:
        return '<p class="v10-empty">No baseline evaluation is recorded yet.</p>'
    prov = b.get('provenance') or {}
    check = prov.get('plumbing_check') or {}
    ranked = sorted(b.get('candidates') or [], key=lambda c: (c.get('rank') is None, c.get('rank') or 0, c.get('instrument')))
    rows = ''.join(
        f'<tr class="{"fl-pick" if c.get("instrument") == b.get("selected_instrument") else ""}"><td><b>{esc(c.get("instrument"))}</b></td>'
        f'<td class="num">{esc(c.get("rank") or "—")}</td><td class="num">{_num(c.get("momentum_126d"), 2, True)}</td>'
        f'<td class="num">{_num(c.get("close"))}</td><td class="num">{_num(c.get("ma200"))}</td>'
        f'<td>{"yes" if c.get("above_ma200") is True else "no" if c.get("above_ma200") is False else "—"}</td>'
        f'<td class="num">{esc(c.get("completed_session_count"))}</td><td class="small">{esc(c.get("eligibility_reason"))}</td></tr>' for c in ranked)
    if check:
        same = check.get('matches_control_a')
        compare = (('Control A’s own record for that run', esc(check.get('control_a_recorded_selection') or 'no selection')),
                   ('Same selection from the new store', '<b>Yes</b>' if same else '<b>No — investigate before relying on this data path</b>'),
                   ('Same ranking order', 'Yes' if check.get('firm_lab_ranking') == check.get('control_a_recorded_ranking') else 'No'),
                   ('Largest momentum difference', esc(_num(check.get('largest_momentum_difference'), 6))))
    else:
        compare = (('Comparison with Control A’s record', 'not recorded'),)
    facts = (('Evaluated as of', esc(_when(b.get('timestamp')))), ('Exchange session date', esc(b.get('exchange_session_date'))),
             ('Rule would select', f'<b>{esc(b.get("selected_instrument") or "nothing")}</b>'),
             ('Record label', f'<span class="cat cat-warn">{esc(b.get("label"))}</span>'), *compare,
             ('Data', esc(prov.get('data') or 'not recorded')),
             ('Source', esc(f'Control A decision capsule {str(prov.get("capsule_hash") or "")[:12]}…, read-only') if prov.get('capsule_hash') else 'not recorded'))
    return (f'<p class="fl-stamp">{esc(b.get("title"))}</p>'
            '<p class="v10-note">This applies Control A’s existing rule (at least 253 completed closes, last close above its 200-session average, positive '
            '126-session momentum, the single strongest) to closes held in Firm Lab’s own point-in-time store. It checks that the new data path reproduces '
            'what Control A recorded. It is not a Firm strategy, it created no order, and nothing was bought.</p>'
            + _facts(facts)
            + '<div class="table-wrap"><table class="mini fl-base"><thead><tr><th>Candidate</th><th class="num">Rank</th><th class="num">Momentum, 126 sessions</th>'
              '<th class="num">Close</th><th class="num">Average, 200 sessions</th><th>Above average</th><th class="num">Closes</th><th>Eligibility</th></tr></thead>'
              f'<tbody>{rows}</tbody></table></div>')


def _benchmarks(fl):
    rows = fl.get('benchmarks')
    if not rows:                                          # database not created yet: show the definitions it starts with
        rows = _view().defaults()['benchmarks']
    method = fl.get('treasury_methodology') or _view().defaults().get('treasury_methodology') or {}
    out = ''
    for b in rows:
        if b['benchmark_id'] == 'VTI_100':
            latest = b.get('latest')
            body = _facts((('Status', '<span class="cat cat-neutral">Fixed benchmark</span>'),
                           ('Definition', '100% VTI, the 100% equity benchmark. Never rebalanced, never traded by the Firm.'),
                           ('Basis', 'price return (dividends are not included yet)'),
                           ('Completed-session closes stored', esc(b.get('observations'))),
                           ('Latest stored close', esc(f'{_num(latest[1])} for the {latest[0]} session') if latest else 'none')))
            out += f'<article class="fl-bench"><h3>VTI</h3>{body}</article>'
        else:
            definition = b.get('definition') or {}
            rules = '; '.join(definition.get('rules') or [])
            rebalancing = definition.get('rebalancing')
            body = _facts((('Status', '<span class="cat cat-neutral">Fixed benchmark</span>'),
                           ('Definition', f'<b>{esc(b.get("name"))}</b>'),
                           ('Implementation status', f'<span class="cat cat-warn">{esc(b.get("implementation_status") or "DATA_SOURCE_PENDING")}</span>'),
                           ('Treasury-bill data', 'Official U.S. Treasury auction and bill-rate data are the chosen inputs. A yield series is not a '
                                                  'total return, and no fund or other asset stands in for the bill.'),
                           ('Methodology', f'<span class="cat cat-warn">{esc(method.get("status", "DRAFT_FOR_OPERATOR_REVIEW"))}</span> '
                                           f'{esc(method.get("document", ""))}. Not approved and not frozen.'),
                           ('Computation', f'<span class="cat cat-neutral">{esc(method.get("computation", "NOT_COMPUTED"))}</span> '
                                           'Nothing is calculated until the methodology is approved and frozen.'),
                           ('Rules', esc(rules[:1].upper() + rules[1:] + '.') if rules else 'not recorded'),
                           ('Rebalancing', esc(f'{rebalancing.get("frequency")}, on {rebalancing.get("on")}') if isinstance(rebalancing, dict)
                            and rebalancing.get('frequency') else 'not specified by the operator yet'),
                           ('Defined by', esc(b.get('defined_by') or 'not recorded')),
                           ('Observations stored', esc(b.get('observations') or 0))))
            out += f'<article class="fl-bench"><h3>70/30</h3>{body}</article>'
    return (f'<div class="fl-benches">{out}</div><p class="v10-note">The Firm cannot trade a ruler, change it, or choose it after seeing results. '
            'No outperformance figure is reported while Firm Lab is in BUILD / OBSERVE.</p>')


def render(state):
    fl = state.get('firm_lab') or {'exists': False, 'mode': 'BUILD_OBSERVE', 'fills': 0, 'firm_trading_trial': 'NOT REGISTERED'}
    head = ('<div class="room-head fl-head"><div><h1>Firm Lab</h1>'
            '<p class="fl-flags"><span class="fl-flag">BUILD / OBSERVE</span><span class="fl-flag">NO FILLS</span>'
            '<span class="fl-flag">NO FIRM TRADING TRACK RECORD</span></p>'
            '<p><b>Development data only. No Firm trading track record exists.</b> Firm Lab is the foundation of the next system, built beside the registered paper run '
            '(Control A) and kept separate from it. It stores data and checks its own plumbing. It cannot place a paper trade or a real one.</p></div></div>')
    if fl.get('error'):
        return head + ('<section class="v10-panel"><h2>System status</h2><p class="v10-empty">The Firm Lab database could not be read '
                       f'({esc(fl["error"])}). Nothing is assumed: no mode is shown as healthy, and Firm Lab still cannot fill.</p></section>')
    mode = fl.get('mode')
    mode_text = 'BUILD / OBSERVE' if mode == 'BUILD_OBSERVE' else f'UNEXPECTED ({mode})'
    tables_ok = not fl.get('has_execution_tables')
    fills = ('0' if tables_ok else 'UNEXPECTED: an execution table exists')
    last = fl.get('last_ingest') or {}
    base = fl.get('baseline') or {}
    status = [('Mode', f'<b>{esc(mode_text)}</b>'),
              ('Database', esc(fl.get('database') or 'robinhood-diagnostics/firm_lab/firm_lab.db') + (' (separate from the registered database)' if fl.get('exists') else ' (not created on this machine yet)')),
              ('Last data update', esc(_when(last.get('finished_at'))) + (f' · {esc(last.get("status"))}' if last else '')),
              ('Last feature update', esc(_when(fl.get('last_feature_update')))),
              ('Latest completed session stored', esc(fl.get('latest_session') or 'none')),
              ('Latest baseline evaluation', esc(_when(base.get('timestamp'))) if base else 'none'),
              ('Feature rows', esc(f'{fl.get("feature_rows", 0):,} across {fl.get("instruments", 0)} instruments') if fl.get('exists') else '0'),
              ('Firm fills', f'<b>{fills}</b> (Firm Lab has no order, fill, position or cash table)'),
              ('Firm trading trial', f'<b>{esc(fl.get("firm_trading_trial", "NOT REGISTERED"))}</b> (it takes the next unused experiment ID when it is registered)'),
              ('Active Firm experiments', esc(sum(1 for e in fl.get('experiments') or [] if e.get('status') == 'ACTIVE'))),
              ('October research stop superseded', esc(fl.get('october_research_stop_superseded', 'NO'))),
              ('Real execution', esc(fl.get('real_execution', 'DISABLED')))]
    return (head
            + f'<section class="v10-panel" id="fl-status"><h2>System status</h2>{_facts(status)}</section>'
            + f'<section class="v10-panel" id="fl-readiness"><h2>Data Readiness</h2>{_readiness(fl)}</section>'
            + f'<section class="v10-panel" id="fl-capabilities"><h2>Derived measures and strategy components</h2>{_capabilities(fl)}</section>'
            + f'<section class="v10-panel" id="fl-baseline"><h2>Control A baseline — counterfactual plumbing test</h2>{_baseline(fl)}</section>'
            + f'<section class="v10-panel" id="fl-benchmarks"><h2>Benchmarks</h2>{_benchmarks(fl)}</section>'
            + f'<section class="v10-panel fl-warning" id="fl-warning"><h2>Development warning</h2><p>{esc(WARNING)}</p></section>')
