"""Firm Lab: read-only status page. BUILD / OBSERVE, no fills, no track record.

Shows only what is recorded in the Firm Lab database (opened read-only) plus the fixed statements that
cannot change without an operator decision. It has no form and no action of its own.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from .components import esc
from .feature_explorer import render_features
from .modeling_lab import render_modeling

ET = ZoneInfo('America/New_York')
STATUS_TONE = {'AVAILABLE': 'good', 'UNAVAILABLE': 'stop', 'NOT_STARTED': 'neutral', 'BUILD_ONLY': 'warn', 'PARTIAL_EXISTING': 'warn',
               'BLOCKED': 'stop', 'RESEARCH_ONLY': 'neutral'}
LABELS = {
    'research_modeling': 'Research modeling laboratory', 'deep_learning': 'Deep-learning models', 'transformer_models': 'Transformer models',
    'rl_policy': 'Reinforcement-learning policy',
    'daily_closes': 'Daily closes', 'daily_baseline_features': 'Daily baseline features', 'fundamentals': 'Fundamentals',
    'analyst_revisions': 'Analyst revisions', 'earnings_transcripts': 'Earnings-call transcripts', 'intraday_bars': 'Intraday bars',
    'vwap': 'VWAP', 'opening_range': 'Opening range', 'time_of_day_rvol': 'Time-of-day RVOL', 'trade_flow': 'Aggressive order flow',
    'order_book': 'Quote and order-book imbalance', 'options_chain': 'Option chain data', 'options_strategy': 'Options strategy',
    'news_catalysts': 'News and catalysts', 'sec_filings': 'SEC filings', 'sector_engine': 'Sector engine', 'ml_ranker': 'ML ranker',
    'portfolio_optimizer': 'Portfolio optimizer', 'earnings_events': 'Earnings events', 'macro_regime': 'Macro regime', 'vti_total_return': 'VTI total return',
    'total_return_ruler': '70/30 total-return ruler', 'corporate_actions': 'Corporate actions and dividends', 'vwap': 'VWAP',
    'options_greeks': 'Options Greeks', 'treasury_total_return': 'T-bill total return', 'tick_trades_quotes': 'Historical trades and quotes',
    'live_quotes': 'Live quotes and trades',
}
EVENT_BANNER = 'FACTUAL EVENT DATA ONLY — NO EARNINGS SIGNAL'
REQUIRED = ('revenue', 'operating_income', 'net_income', 'eps_diluted', 'operating_cash_flow', 'cash_and_equivalents', 'total_debt',
            'diluted_shares_weighted_average')
OPTIONAL = ('gross_profit', 'capital_expenditure')
FIELD_NAMES = {'revenue': 'revenue', 'gross_profit': 'gross profit', 'operating_income': 'operating income', 'net_income': 'net income',
               'eps_diluted': 'diluted EPS', 'operating_cash_flow': 'operating cash flow', 'capital_expenditure': 'capital expenditure',
               'cash_and_equivalents': 'cash and cash equivalents', 'total_debt': 'total debt',
               'diluted_shares_weighted_average': 'diluted shares (weighted average)'}
SESSION_NAMES = {'before_market_open': 'before 9:30 AM ET', 'during_market_hours': '9:30 AM to 4:00 PM ET', 'after_market_close': '4:00 PM ET or later'}
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


def load(official_db,feature_filters=None):
    return _view().load(official_db=official_db,feature_filters=feature_filters)


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


FLAG_NOTE = {'ACCEPTANCE_TIME_CONFLICT': ' (the SEC JSON time disagrees with the filing header; the header time is used and both are stored)'}
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
        failures, flags = r.get('failures') or {}, r.get('flags') or {}
        issues = ', '.join(r.get('validation_issues') or [])
        sample = ' · '.join(f'{s.get("instrument")} {s.get("status")}' for s in (r.get('sample') or [])[:12])
        rows = int(r.get('rows') or 0)
        versions = f' · {rows:,} stored rows including earlier versions' if rows > count else ''
        quality = []
        if flags:                                             # rows that were kept, with what was flagged on them
            quality.append('Kept and flagged: ' + '; '.join(f'{code} × {n}' for code, n in sorted(flags.items())) + FLAG_NOTE.get(next(iter(flags)), ''))
        if failures:                                          # responses that were refused whole, over all runs
            quality.append('Refused: ' + '; '.join(f'{code} × {n}' for code, n in sorted(failures.items())))
        body += (
            f'<tr><td data-label="Data"><b>{esc(r["domain"])}</b></td><td data-label="Capability">{_chip(r["status"])}</td>'
            f'<td data-label="Provider">{esc(provider) if provider else "none selected"}</td>'
            f'<td data-label="Connection">{_tag(connection, CONNECTION_TONE, "stop")}'
            f'<span class="small fl-sub">{esc(r.get("connection_detail") or "")}</span></td>'
            f'<td data-label="Validation">{_tag(validation, VALIDATION_TONE, "neutral")}'
            f'<span class="small fl-sub">{esc(issues or sample)}</span></td>'
            f'<td data-label="Stored"><b>{count:,}</b><span class="small fl-sub">{esc(span + versions) if count else "nothing stored"}</span></td>'
            f'<td data-label="Last successful ingest">{esc(_stamp(r.get("last_successful_ingest")) or "never")}</td>'
            f'<td data-label="Quality failures and flags" class="small">{esc(". ".join(quality)) if quality else "none recorded"}</td></tr>'
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
            '<th>Last successful ingest</th><th>Quality failures and flags</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div>' + cross_note +
            '<p class="v10-note">Capability — AVAILABLE: stored data that passed validation. PARTIAL_EXISTING: a source exists elsewhere in the system but is '
            'not sufficient for, or not connected to, Firm Lab. BUILD_ONLY: storage exists and nothing reads it. UNAVAILABLE: no value is stored, estimated '
            'or filled in. Connection — NOT CONFIGURED: credentials or provider activation by the operator are required. Validation — PASS: every run of the '
            'latest sample was accepted; FAIL: a response was refused whole and nothing from it was kept. A flag marks rows that were kept with a '
            'known disagreement between two sources; the value used and the value set aside are both stored. Details: docs/firm_lab/data_sources.md and '
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


def _benchmark_readiness(fl):
    """One row per ruler series: the capability state, how many observations are stored, their span and whether they validated."""
    rows = fl.get('benchmark_readiness') or _view().defaults()['benchmark_readiness']
    body = ''
    for r in rows:
        count = int(r.get('observations') or 0)
        label = f'<span class="small fl-sub">{esc(r["label"])}</span>' if r.get('label') else ''
        what = 'latest close' if r.get('kind') == 'close_price_return_basis' else 'latest level'
        places = 2 if r.get('kind') == 'close_price_return_basis' else 6
        latest = f'<span class="small fl-sub">{what} {esc(_num(r.get("latest_value"), places))}</span>' if count and r.get('latest_value') else ''
        body += (f'<tr><td data-label="Series"><b>{esc(r["series"])}</b>{label}</td><td data-label="Capability">{_chip(r["status"])}</td>'
                 f'<td data-label="Observations" class="num"><b>{count:,}</b></td><td data-label="Oldest">{esc(r.get("oldest") or "—")}</td>'
                 f'<td data-label="Newest">{esc(r.get("newest") or "—")}{latest}</td>'
                 f'<td data-label="Validation">{_tag(str(r.get("validation") or "NOT RUN"), VALIDATION_TONE, "neutral")}'
                 f'<span class="small fl-sub">{esc(r.get("validation_note") or "")}</span></td></tr>')
    run = fl.get('total_return') or {}
    notes = ''
    if run:
        checked = run.get('distributions_checked') or []
        if checked:
            items = '; '.join(f'{c.get("ex_date")}: ${c.get("amount")} per share (issuer reinvestment price {c.get("issuer_reinvestment_price")}, stored close '
                              f'{_num(c.get("stored_close_on_ex_date"))})' for c in checked)
            notes += f'<p class="v10-note">VTI distributions used, by ex-dividend date: {esc(items)}.</p>'
        issues = '; '.join(f'{i.get("code")}: {i.get("detail")}' for i in run.get('issues') or [])
        if issues:
            notes += f'<p class="v10-note"><b>Validation issues.</b> {esc(issues)}. Nothing was computed from data that did not validate.</p>'
        for text in run.get('notes') or []:
            notes += f'<p class="v10-note">{esc(text)}</p>'
    return ('<p class="v10-note">Rulers only. The price-return series stored earlier are kept exactly as they were; the total-return series are '
            'separate and are computed only from distributions that passed validation. No vendor adjusted close or vendor total-return index is used.</p>'
            '<p class="v10-note"><b>BENCHMARK ONLY.</b> The VTI distributions are used to rebuild an after-the-fact ruler. They carry no validated '
            'announcement time, so they are not treated as information that was known on their ex-dates, and they never enter the feature store '
            'or any model feature.</p>'
            '<div class="table-wrap"><table class="mini fl-ready fl-benchready"><colgroup><col class="fl-b1"><col class="fl-b2"><col class="fl-b3">'
            '<col class="fl-b4"><col class="fl-b5"><col></colgroup><thead><tr><th>Series</th><th>Capability</th><th class="num">Observations</th>'
            '<th>Oldest</th><th>Newest</th><th>Validation</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div>' + notes)


def _fundamentals(fl):
    """Fundamentals readiness: what the latest SEC XBRL sample found, and what stayed unresolved. Facts only."""
    data = fl.get('fundamentals') or {'source': 'SEC XBRL company facts (SEC EDGAR)', 'normalized_fields': list(FIELD_NAMES), 'companies': []}
    rows, _, _ = _registry(fl)
    state = next((r for r in rows if r['capability'] == 'fundamentals'), {'status': 'UNAVAILABLE', 'detail': ''})
    companies = data.get('companies') or []
    mappings = data.get('unresolved_mappings') or {}
    unresolved = '; '.join(f'{FIELD_NAMES.get(name, name)}: ' + ', '.join(f'{reason} ({", ".join(who)})' for reason, who in sorted(reasons.items()))
                           for name, reasons in sorted(mappings.items()))
    facts = (('Source', esc(data.get('source'))),
             ('Sample companies', esc(', '.join(c['instrument'] for c in companies) or 'none read yet')),
             ('Required for AVAILABLE', esc(', '.join(FIELD_NAMES.get(f, f) for f in data.get('required_fields') or REQUIRED) +
                                            '. Each must be resolved and confirmed for every company and every filing read.')),
             ('Optional, company-dependent', esc(', '.join(FIELD_NAMES.get(f, f) for f in data.get('optional_fields') or OPTIONAL) +
                                                 '. One that is not reported is recorded and does not block. Not collected and never synthesized: free cash flow, EBITDA.')),
             ('Debt rule', 'The combined debt figure when the company reports one; otherwise current plus non-current long-term debt plus '
                           'short-term borrowings (or commercial paper), each as reported. A part that is not reported is not taken as zero, and '
                           'lease liabilities are not included.'),
             ('Accepted facts in the latest sample', esc(f'{int(data.get("accepted") or 0):,} ({int(data.get("stored_rows") or 0):,} rows stored in all)')),
             ('Rejected', esc(f'{data.get("rejected_runs", 0)} company answers refused whole') + (f'; {esc(data.get("not_found_in_filing", 0))} stored facts not found in the filing document' if data.get('not_found_in_filing') else '')),
             ('Unresolved mappings', esc(unresolved) if unresolved else ('none' if companies else 'nothing read yet')),
             ('Restatements stored as new versions', esc(data.get('restatements', 0))),
             ('Capability', _chip(state.get('status')) + f' <span class="small">{esc(state.get("detail") or "")}</span>'))
    body = ''
    for c in companies:
        filings = ', '.join(f'{f.get("form")} {f.get("report_date")}' for f in c.get('filings') or [])
        checks = ', '.join(f'{k} {v}' for k, v in sorted((c.get('checked_against_filing') or {}).items()))
        left = '; '.join(f'{FIELD_NAMES.get(name, name)} ({", ".join(sorted(reasons))})' for name, reasons in sorted((c.get('unresolved_by_field') or {}).items()))
        verdict = 'PASS' if c.get('quality_passes') else 'FAIL'
        refused = ', '.join(c.get('issues') or [])
        body += (f'<tr><td data-label="Company"><b>{esc(c["instrument"])}</b></td><td data-label="Filings read" class="small">{esc(filings or "none")}</td>'
                 f'<td data-label="Raw facts" class="num">{esc(c.get("raw_facts") if c.get("raw_facts") is not None else "—")}</td>'
                 f'<td data-label="Accepted" class="num">{esc(c.get("accepted", 0))}</td>'
                 f'<td data-label="Unresolved" class="small">{esc(str(c.get("unresolved", 0)) + (": " + left if left else ""))}</td>'
                 f'<td data-label="Checked against the filing" class="small">{esc(checks or "—")}</td>'
                 f'<td data-label="Quality">{_tag(verdict if c.get("status") == "OK" else "FAIL", VALIDATION_TONE, "neutral")}'
                 f'<span class="small fl-sub">{esc(refused)}</span></td></tr>')
    table = ('<div class="table-wrap"><table class="mini fl-ready fl-fund"><colgroup><col class="fl-f1"><col class="fl-f2"><col class="fl-f3">'
             '<col class="fl-f4"><col class="fl-f5"><col class="fl-f6"><col></colgroup><thead><tr><th>Company</th><th>Filings read</th><th class="num">Raw facts</th>'
             '<th class="num">Accepted</th><th>Unresolved</th><th>Checked against the filing</th><th>Quality</th></tr></thead>'
             f'<tbody>{body}</tbody></table></div>') if companies else '<p class="v10-empty">No company-facts sample has been run yet.</p>'
    return ('<p class="v10-note">Reported values exactly as each company tagged them in its own SEC filings. A value is known from the moment the SEC '
            'accepted the filing that carries it; a later filing with a different value is stored as a new version beside the first. A field is filled '
            'only by a written mapping rule, and is otherwise left unresolved: nothing is derived, estimated, scored or ranked.</p>'
            + _facts(facts) + table)


def _earnings(fl):
    """Earnings-release filings: what was filed and when. No sentiment, score, signal or transcript."""
    data = fl.get('earnings_events') or {'events': [], 'stored': 0}
    body = ''
    for e in data.get('events') or []:
        values = e.get('reported_values') or {}
        shown = '; '.join(f'{FIELD_NAMES.get(name, name)} {_num(v.get("value"), 2 if name == "eps_diluted" else 0)} {v.get("unit")} ({v.get("period_type")})'
                          for name, v in values.items())
        if shown:
            first = next(iter(values.values()))
            shown += f' — from periodic report {e.get("periodic_accession_number")}, accepted {_when(first.get("accepted_timestamp"))}'
        link = lambda url, text: (f'<a href="{esc(url)}" rel="noopener noreferrer" target="_blank">{esc(text)}</a>'
                                  if str(url or '').startswith('https://www.sec.gov/') else esc(text if url in (None, '') else str(url)))
        flag = ('<span class="small fl-sub">flagged: the SEC JSON time disagrees with the filing header; the header time is used</span>'
                if e.get('acceptance_time_conflict') else '')
        body += (f'<tr><td data-label="Company"><b>{esc(e["instrument"])}</b></td><td data-label="Fiscal period end">{esc(e.get("fiscal_period_end"))}</td>'
                 f'<td data-label="Event date">{esc(e.get("event_date"))}</td>'
                 f'<td data-label="SEC accepted">{esc(_when(e.get("accepted_timestamp")))}'
                 f'<span class="small fl-sub">{esc(SESSION_NAMES.get(e.get("acceptance_session"), e.get("acceptance_session")))}</span>{flag}</td>'
                 f'<td data-label="Form">{esc(e.get("form"))}<span class="small fl-sub">{esc(e.get("accession_number"))}</span></td>'
                 f'<td data-label="Reported values" class="small">{esc(shown) if shown else "not stored"}</td>'
                 f'<td data-label="Links" class="small">{link(e.get("filing_url"), "filing")} · '
                 f'{link(e.get("release_document_url"), "release document") if e.get("release_document_url") != "UNAVAILABLE" else "release document unavailable"}</td></tr>')
    table = ('<div class="table-wrap"><table class="mini fl-ready fl-events"><colgroup><col class="fl-e1"><col class="fl-e2"><col class="fl-e3">'
             '<col class="fl-e4"><col class="fl-e5"><col class="fl-e6"><col></colgroup><thead><tr><th>Company</th><th>Fiscal period end</th><th>Event date</th>'
             '<th>SEC accepted</th><th>Form</th><th>Reported values</th><th>Links</th></tr></thead>'
             f'<tbody>{body}</tbody></table></div>') if body else '<p class="v10-empty">No earnings-release filing is stored yet.</p>'
    return (f'<p class="fl-stamp">{esc(EVENT_BANNER)}</p>'
            '<p class="v10-note">Each row is a filing: an 8-K with Item 2.02, timed by its SEC filing header. The release is not read, summarised or '
            'scored, and no transcript is collected. The fiscal period is linked by a stated rule to the periodic report for that period, and the '
            'reported values shown are taken from that periodic report with its own acceptance time, not from the release. The time-of-day label is '
            'the New York clock time of the SEC acceptance only.</p>'
            + _facts((('Events stored', esc(data.get('stored', 0))), ('Source', esc(data.get('source') or 'SEC EDGAR (8-K, Item 2.02)')),
                      ('Transcripts', '<span class="cat cat-stop">UNAVAILABLE</span> none is collected'),
                      ('Signal or model', '<b>NONE</b> no sentiment, tone, surprise, score or prediction exists')))
            + table)


def _benchmarks(fl):
    rows = fl.get('benchmarks')
    if not rows:                                          # database not created yet: show the definitions it starts with
        rows = _view().defaults()['benchmarks']
    total = fl.get('total_return') or {}
    method = fl.get('treasury_methodology') or _view().defaults().get('treasury_methodology') or {}
    index = fl.get('treasury_index')
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
        elif b['benchmark_id'] in ('VTI_TOTAL_RETURN', 'FIXED_70_30_TOTAL_RETURN'):
            series = b.get('series') or {}
            is_ruler = b['benchmark_id'] == 'FIXED_70_30_TOTAL_RETURN'
            kind = series.get('index_70_30_vti_total_return' if is_ruler else 'vti_total_return_index')
            price = series.get('vti_price_return_index')
            if not total:
                computed = '<span class="cat cat-neutral">NOT COMPUTED</span> No validated VTI distribution history is stored yet.'
            elif total.get('status') == 'OK' and is_ruler and total.get('ruler_status') != 'OK':
                computed = (f'<span class="cat cat-stop">{esc(total.get("ruler_status") or "DATA_GAP")}</span> '
                            f'{esc(total.get("ruler_gap_reason") or "no reason recorded")}. Nothing is filled in.')
            elif total.get('status') == 'OK':
                computed = (f'<span class="cat cat-good">OK</span> through the {esc(total.get("last_session"))} session; '
                            f'{esc(len(total.get("distributions_applied") or []))} distributions reinvested.')
            else:
                why = ', '.join(sorted({i.get('code', '') for i in total.get('issues') or []})) or total.get('gap_reason') or 'no reason recorded'
                computed = f'<span class="cat cat-stop">{esc(total.get("status"))}</span> {esc(why)}. Nothing is filled in.'
            level = lambda s: esc(f'{_num(s["latest"][1], 6)} on the {s["latest"][0]} session (base {s["first"]} = 100; {s["observations"]:,} sessions)') if s else 'none'
            facts = [('Status', '<span class="cat cat-neutral">Fixed benchmark</span>'), ('Definition', f'<b>{esc(b.get("name"))}</b>')]
            if is_ruler:
                facts.append(('Label', '<span class="cat cat-neutral">TOTAL_RETURN_RULER</span>'))
            facts += [('Implementation status', f'<span class="cat cat-neutral">{esc(b.get("implementation_status"))}</span>'),
                      ('Method', 'Each cash distribution is reinvested at the close of its ex-dividend session. Stored closes are used as they are; '
                                 'no vendor adjusted close and no vendor total-return index is used. docs/firm_lab/vti_total_return_methodology.md'),
                      ('Computation', computed),
                      ('70/30 total-return level' if is_ruler else 'VTI total-return index', level(kind))]
            if not is_ruler:
                facts.append(('VTI price-return index', level(price)))
            else:
                facts.append(('Treasury-bill leg', 'The frozen 13-week bill accrual index, unchanged.'))
            facts.append(('Defined by', esc(b.get('defined_by') or 'not recorded')))
            out += f'<article class="fl-bench"><h3>{"70/30 total return" if is_ruler else "VTI total return"}</h3>{_facts(facts)}</article>'
        else:
            definition = b.get('definition') or {}
            rules = '; '.join(definition.get('rules') or [])
            rebalancing = definition.get('rebalancing')
            series = b.get('series') or {}
            bill, ruler = series.get('tbill_13w_accrual_index'), series.get('index_70_30_vti_price_return_basis')
            frozen = method.get('status') == 'APPROVED_AND_FROZEN'
            if not index:
                computed = '<span class="cat cat-neutral">NOT COMPUTED</span> No auction record has been ingested yet.'
            elif index.get('status') == 'OK':
                computed = (f'<span class="cat cat-good">OK</span> through the {esc(index.get("last_session"))} session; '
                            f'{esc(index.get("bills_stored", 0))} auction records stored, {esc(len(index.get("bills_used") or []))} bills held in turn, '
                            f'{esc(len(index.get("rebalances") or []))} monthly rebalances.')
            else:
                computed = (f'<span class="cat cat-stop">{esc(index.get("status") or "DATA_GAP")}</span> stopped'
                            + (f' from {esc(index.get("gap_date"))}' if index.get('gap_date') else '') + f': {esc(index.get("gap_reason") or "no reason recorded")}. '
                              'Nothing is filled in.')
            level = lambda s: esc(f'{_num(s["latest"][1], 6)} on the {s["latest"][0]} session (base {s["first"]} = 100; {s["observations"]:,} sessions)') if s else 'none'
            body = _facts((('Status', '<span class="cat cat-neutral">Fixed benchmark</span>'),
                           ('Definition', f'<b>{esc(b.get("name"))}</b>'),
                           ('Label', '<span class="cat cat-neutral">LEGACY_PRICE_RETURN_RULER</span> kept as first computed; the total-return ruler is separate'),
                           ('Implementation status', f'<span class="cat cat-{"neutral" if frozen else "warn"}">{esc(b.get("implementation_status") or "DATA_SOURCE_PENDING")}</span>'),
                           ('Treasury-bill data', 'Official U.S. Treasury 13-week bill auction records. Each bill enters at its auction price, is held to '
                                                  'maturity and is rolled into the next. Between auction and maturity the value is an accrual, not a market price. No fund, '
                                                  'yield series or other asset stands in for the bill.'),
                           ('Methodology', f'<span class="cat cat-{"good" if frozen else "warn"}">{esc(method.get("status", "NOT_APPROVED"))}</span> '
                                           f'{esc(method.get("document", ""))}'
                                           + (f', version {esc(method.get("version"))}, approved {esc(_when(method.get("approved_at")))}. '
                                              f'SHA-256 {esc(str(method.get("sha256"))[:16])}…. The frozen file is never edited; a change is a new version.'
                                              if frozen else '. Not approved and not frozen.')),
                           ('Computation', computed),
                           ('13-week bill accrual index', level(bill)),
                           ('70/30 level', level(ruler)),
                           ('VTI leg', 'Price return. Dividends are not included until a validated dividend source exists, so this is not yet a total '
                                       'return on the VTI side.'),
                           ('Days uninvested', esc(len((index or {}).get('uninvested_days') or [])) + ' (a day with no 13-week bill to roll into earns nothing)'),
                           ('Development base', 'The base date is the first stored VTI session. The ruler is rebased when a Firm trading trial is '
                                                'registered; none is.'),
                           ('Rules', esc(rules[:1].upper() + rules[1:] + '.') if rules else 'not recorded'),
                           ('Rebalancing', esc(f'{rebalancing.get("frequency")}, on {rebalancing.get("on")}; no settlement lag, no transaction cost')
                            if isinstance(rebalancing, dict) and rebalancing.get('frequency') else 'not specified by the operator yet'),
                           ('Defined by', esc(b.get('defined_by') or 'not recorded')),
                           ('Observations stored', esc(f'{sum(s["observations"] for s in series.values()):,}' if series else (b.get('observations') or 0)))))
            out += f'<article class="fl-bench"><h3>70/30</h3>{body}</article>'
    return (f'<div class="fl-benches">{out}</div><p class="v10-note">The Firm cannot trade a ruler, change it, or choose it after seeing results. '
            'These are rulers only: nothing reads them to rank, select or trade. No outperformance figure is reported while Firm Lab is in BUILD / OBSERVE.</p>')


def _macro(fl):
    macro=fl.get('macro') or {}
    rows={r['series']:r for r in macro.get('latest',[])}
    caps={r['capability']:r for r in fl.get('capabilities',[])}
    labels=[('fed_target_lower','Fed target lower','fed_policy_data'),('fed_target_upper','Fed target upper','fed_policy_data'),
            ('treasury_2y','2-year constant maturity yield','treasury_yields'),('treasury_10y','10-year constant maturity yield','treasury_yields'),
            ('cpi_headline_nsa','CPI headline · unadjusted index','cpi'),('cpi_core_nsa','CPI core · unadjusted index','cpi'),
            ('pce_headline_mom_sa','PCE headline · monthly change, seasonally adjusted','pce'),
            ('pce_core_mom_sa','PCE core · monthly change, seasonally adjusted','pce'),
            ('unemployment_rate','Unemployment rate · seasonally adjusted','labor_data'),
            ('nonfarm_payroll_change','Payroll change · thousands, seasonally adjusted','labor_data')]
    cards=[]
    for series,label,cap in labels:
        row=rows.get(series); capability=caps.get(cap,{})
        if not row:
            body=f'<p>No validated observation stored · {esc(capability.get("status","UNAVAILABLE"))}</p><p>{esc(capability.get("detail","Publication evidence not confirmed."))}</p>'
        else:
            metadata=row.get('source_metadata') or {}
            details=_facts([('Observation period',esc(row['period'])),('Unit',esc(row['unit'])),('Source',esc(row['source'])),
                            ('Publisher identities',esc('; '.join(metadata.get('source_series_ids',[])) or 'Not recorded')),
                            ('Seasonal adjustment',esc(metadata.get('seasonal_adjustment','Not recorded'))),
                            ('Change versus previous decision (basis points)',esc(metadata.get('change_basis_points','Not applicable'))),
                            ('Source URL',esc(row['source_url'])),('Publication time',esc(row['published_at'])),
                            ('Known locally at',esc(row['known_at'])),('Captured at',esc(row['ingested_at'])),
                            ('Revision',f'Local revision {esc(row["revision"])} — not proof of original economic vintage'),
                            ('Content hash',esc(row['source_hash'])),('Capability',esc(capability.get('status','UNAVAILABLE')))])
            body=f'<p><strong>{esc(row["value"])}</strong> · {esc(row["unit"])} · {esc(row["period"])}</p><details><summary>Source and timing</summary>{details}</details>'
        cards.append(f'<article class="fl-bench"><h3>{esc(label)}</h3>{body}</article>')
    events=[]
    for row in macro.get('events',[]):
        facts=_facts([('Period',esc(row['period'])),('Released value',esc(str(row.get('released_value'))+' '+row['unit'])),
                      ('Scheduled time',esc(row.get('scheduled_at') or 'UNAVAILABLE')),
                      ('Actual publication',esc(row.get('actual_published_at') or 'UNAVAILABLE')),
                      ('Known locally at',esc(row['known_at'])),('Prior value',esc(row.get('prior_value') or 'UNAVAILABLE')),
                      ('Previous local vintage value',esc(row.get('previous_local_value') if row.get('previous_local_value') is not None else 'UNAVAILABLE')),
                      ('Revision',f'Local revision {esc(row["revision"])}'),('Source',esc(row['source_url'])),('Consensus','UNAVAILABLE')])
        events.append(f'<details><summary>{esc(row["event_type"])} · {esc(row["series"])} · {esc(row["period"])}</summary>{facts}</details>')
    return ('<p><b>FACTUAL MACRO DATA ONLY — NO MACRO TRADING SIGNAL</b></p>'
            '<p>Data state: validated facts below. Model state: <b>macro_regime = NOT_STARTED</b>. Trading state: <b>NO TRADES</b>.</p>'
            '<p>Capture is local availability, not a historical backtest permission. Monthly changes and index levels are different measures.</p>'
            +'<div class="fl-benches">'+''.join(cards)+'</div><h3>Recent factual events</h3>'
            '<p>One record per series and local vintage; multiple records can belong to one release. No future schedule is inferred.</p>'
            +(''.join(events) or '<p>No validated events stored.</p>'))


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
            + f'<section class="v10-panel" id="fl-macro"><h2>Macro / Regime Readiness</h2>{_macro(fl)}</section>'
            + render_features(fl.get('research_features') or {'missing_reason':'NO_STORED_FEATURE_RUN'})
            + f'<section class="v10-panel" id="fl-modeling"><h2>Modeling Laboratory</h2>{render_modeling(fl)}</section>'
            + f'<section class="v10-panel" id="fl-capabilities"><h2>Derived measures and strategy components</h2>{_capabilities(fl)}</section>'
            + f'<section class="v10-panel" id="fl-fundamentals"><h2>Fundamentals readiness</h2>{_fundamentals(fl)}</section>'
            + f'<section class="v10-panel" id="fl-earnings"><h2>Earnings events</h2>{_earnings(fl)}</section>'
            + f'<section class="v10-panel" id="fl-baseline"><h2>Control A baseline — counterfactual plumbing test</h2>{_baseline(fl)}</section>'
            + f'<section class="v10-panel" id="fl-benchready"><h2>Benchmark readiness</h2>{_benchmark_readiness(fl)}</section>'
            + f'<section class="v10-panel" id="fl-benchmarks"><h2>Benchmarks</h2>{_benchmarks(fl)}</section>'
            + f'<section class="v10-panel fl-warning" id="fl-warning"><h2>Development warning</h2><p>{esc(WARNING)}</p></section>')
