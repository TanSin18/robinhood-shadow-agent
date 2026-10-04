"""Historical Data Readiness: a read-only view of the stored readiness report. Escaped text and plain tables only.

DATA READINESS ONLY — NO TRADING MODEL IS ACTIVE. The page shows what historical data is stored, how each source is
dated, how many strict point-in-time samples exist and whether the sufficiency bars are met. It has no form, no action,
no price, no forecast and no instruction to do anything with a security.
"""
from .components import esc

WARNING = 'DATA READINESS ONLY — NO TRADING MODEL IS ACTIVE'
FAMILY_NAMES = (('linear', 'Linear'), ('xgboost', 'XGBoost'), ('lightgbm', 'LightGBM'), ('catboost', 'CatBoost'), ('mlp', 'MLP'), ('tcn', 'TCN'),
                ('lstm_gru', 'LSTM / GRU'), ('transformer', 'Transformer'), ('multi_task', 'Multi-task'))
TIER_NAMES = {'HELD_AT_THE_TIME': 'Tier A — held at the time', 'PUBLISHER_DATED_HISTORICAL': 'Tier B — publisher-dated historical', 'RETROSPECTIVE': 'Tier C — retrospective'}


def _count(value):
    if isinstance(value, bool) or value is None:
        return '—'
    if isinstance(value, int):
        return f'{value:,}'
    if isinstance(value, float):
        return f'{value:,.4f}' if abs(value) < 10 else f'{value:,.1f}'
    return esc(str(value))


def _chip(text):
    """One neutral style for every status: the page describes data, it does not signal."""
    return f'<span class="cat cat-neutral">{esc(str(text).replace("_", " "))}</span>'


def _table(head, rows, klass='fl-lab'):
    if not rows:
        return '<p class="v10-empty">Nothing stored.</p>'
    return (f'<div class="table-wrap"><table class="mini fl-ready {klass}"><thead><tr>' + ''.join(f'<th>{esc(h)}</th>' for h in head) + '</tr></thead><tbody>'
            + ''.join('<tr>' + ''.join(f'<td data-label="{esc(h)}">{cell}</td>' for h, cell in zip(head, row)) + '</tr>' for row in rows) + '</tbody></table></div>')


def _fold(title, body, hint=''):
    return f'<details class="fl-fold"><summary>{esc(title)}' + (f'<span>{esc(hint)}</span>' if hint else '') + f'</summary>{body}</details>'


def _facts(rows):
    return '<dl class="v10-facts fl-facts">' + ''.join(f'<div><dt>{esc(k)}</dt><dd>{v}</dd></div>' for k, v in rows) + '</dl>'


def _span(pair):
    if not pair or pair[0] is None:
        return 'none stored'
    return f'{esc(str(pair[0])[:10])} to {esc(str(pair[1])[:10]) if pair[1] else "open"}'


def _measured(value):
    if isinstance(value, dict):
        return '; '.join(f'{esc(str(k).replace("_", " "))} {_count(v)}' for k, v in value.items())
    return _count(value)


SEGMENT_NAMES = (('DEVELOPMENT', 'development'), ('HISTORICAL_HOLDOUT', 'historical holdout, sealed'), ('BURNED_CHECKPOINT7', 'burned Checkpoint 7 window'),
                 ('FORWARD_HOLDOUT', 'forward holdout, sealed'))


def _stands(r):
    market, strict, holdout, decision = r['market_data'], r['strict_training'], r['holdout'], r['provider_decision']
    tiers = (strict.get('strict_samples_by_tier') or {}).get('20') or {}
    samples = strict.get('strict_samples') or {}
    revised = strict.get('rows_not_strict_because_a_bar_was_revised') or 0
    parts = (strict.get('strict_samples_by_segment') or {}).get('20') or {}
    verdicts = [v.get('verdict') for families in (r['sufficiency'].get('verdicts') or {}).values() for v in families.values()]
    unmet = sum(1 for b in r['specification_bars'] if b.get('status') != 'MET')
    stored = market.get('status') == 'STORED'
    items = []
    if stored:
        items.append(f'<b>Historical market data:</b> {_count(market.get("bars"))} daily bars stored; each passed the row checks. '
                     f'{_count(market.get("securities_with_bars"))} securities, {_span(market.get("history_range"))}; {_count(market.get("delisted_with_bars"))} of them delisted. '
                     f'{_count(unmet)} of {_count(len(r["specification_bars"]))} sufficiency bars are not met. {esc(str(decision.get("statement", "")))}')
    else:
        items.append('<b>No historical market data is stored.</b> The only prices held are '
                     f'{_count((market.get("closes_held") or {}).get("closes"))} closes for {_count((market.get("closes_held") or {}).get("instruments"))} instruments, '
                     'close only, captured after the fact.')
        items.append(f'<b>{esc(decision.get("status", ""))}:</b> {esc(decision.get("selected_provider", ""))} {esc(decision.get("product", ""))}, '
                     f'{esc(decision.get("price", ""))}. {esc(str(decision.get("statement", "")))}')
    split = '; '.join(f'{esc(label)} {_count(parts.get(key))}' for key, label in SEGMENT_NAMES)
    items.append(f'<b>Strict point-in-time samples:</b> {_count(samples.get("20"))} with a 20-session label ({_count(samples.get("10"))} at 10, {_count(samples.get("5"))} at 5). '
                 f'By segment: {split}. Of these, held at the time: {_count(tiers.get("HELD_AT_THE_TIME"))}; publisher-dated historical: '
                 f'{_count(tiers.get("PUBLISHER_DATED_HISTORICAL"))}. '
                 + (f'{_count(revised)} further rows read a bar the vendor changed after it was first stored and are not counted. ' if revised else '')
                 + f'The {_count(strict.get("checkpoint7_retrospective_samples"))} retrospective samples of the Modeling Laboratory (its closing report) are a separate '
                 'dataset and are not counted here.')
    first = esc(str(((holdout.get("segments") or {}).get("FORWARD_HOLDOUT") or [""])[0]))
    state = ('are sealed: label and feature values of both are removed before any row leaves the dataset builder, and no model has been measured on either' if stored
             else 'are reserved; no data exists for either yet')
    items.append('<b>Fresh holdout:</b> the Checkpoint 7 holdout is not reused. Historical holdout '
                 f'{_span((holdout.get("segments") or {}).get("HISTORICAL_HOLDOUT"))} and forward holdout from {first} {state}.')
    if verdicts and all(v == 'INSUFFICIENT' for v in verdicts):
        items.append('<b>Data sufficiency:</b> INSUFFICIENT for every model family. A larger model does not change that; more historically truthful data does.')
    else:
        items.append('<b>Data sufficiency:</b> see the table by model family below. A verdict is about the data, not about any model.')
    return '<ul class="fl-stands">' + ''.join(f'<li>{i}</li>' for i in items) + '</ul>'


def _bars(r):
    return _table(['Bar', 'What is measured', 'Target', 'Minimum', 'Measured', 'Status'], klass='fl-lab fl-bars', rows=
                  [[esc(b.get('id', '')), esc(b.get('name', '')) + (f'<span class="small fl-sub">{esc(b["note"])}</span>' if b.get('note') else ''),
                    esc(str(b.get('target', ''))), esc(str(b.get('minimum', ''))), _measured(b.get('measured')), _chip(b.get('status'))] for b in r['specification_bars']])


def _coverage(r):
    market, actions, universe = r['market_data'], r.get('corporate_actions') or {}, r.get('universe') or {}
    fundamentals, earnings, macro = r.get('fundamentals') or {}, r.get('earnings') or {}, r.get('macro') or {}
    series = macro.get('series') or {}
    return _facts([
        ('Market history', _span(market.get('history_range'))),
        ('OHLCV coverage', f'{_count(market.get("bars"))} bars, {_count(market.get("securities_with_bars"))} securities; {_count(market.get("rows_rejected"))} rows rejected of '
                           f'{_count(market.get("rows_read"))} read'),
        ('Corporate actions', ('; '.join(f'{esc(k.replace("_", " "))} {_count(v)}' for k, v in sorted((actions.get('historical_by_type') or {}).items())) or 'none stored')
         + f'. In the research database: {_count(actions.get("held_rows"))} rows for {_count(actions.get("held_instruments"))} instruments, '
           f'{_count(actions.get("held_benchmark_only_rows"))} of them benchmark-only.'),
        ('Delisted coverage', f'{_count(market.get("delisted_with_bars"))} delisted securities with bars; '
                              f'{_count((r["strict_training"] or {}).get("members_whose_bars_end_without_a_delisting_record"))} members whose bars end with no delisting record'),
        ('Stored versions', '; '.join(f'{esc(k.replace("_", " ").lower())} {_count(v)}' for k, v in sorted((market.get('block_versions') or {}).items())) or 'none'),
        ('Universe history', f'{esc(universe.get("universe_version", "none stored"))}'
                             + (f': {_count(universe.get("formation_sessions"))} monthly formations, {_count(universe.get("distinct_members"))} distinct members, '
                                f'{_count(universe.get("members_later_delisted"))} later delisted' if universe else '')),
        ('Fundamentals history', f'{_count(fundamentals.get("facts"))} facts, {_count(fundamentals.get("filings"))} filings, {_count(fundamentals.get("companies"))} companies; '
                                 f'{_count(fundamentals.get("restatements"))} restatements; every fact dated by SEC acceptance time'),
        ('Earnings history', f'{_count(earnings.get("events"))} events, {_count(earnings.get("companies"))} companies; {_count(earnings.get("release_documents"))} release documents; '
                             f'transcripts {_count(earnings.get("transcripts"))}'),
        ('Macro history', '; '.join(f'{esc(k.replace("_", " "))} {_count(v.get("observations"))}' for k, v in sorted(series.items())) or 'none stored'),
        ('OHLCV feature versions', esc(', '.join((r['feature_versions'].get('versions') or []))) + ('' if r['feature_versions'].get('computed_on_stored_bars')
                                                                                                    else ' — defined and tested; not yet computed on stored bars')),
    ])


def _sufficiency(r):
    verdicts = r['sufficiency'].get('verdicts') or {}
    rows = []
    for key, name in FAMILY_NAMES:
        cells = [f'<b>{esc(name)}</b>']
        for horizon in ('5', '20'):
            v = (verdicts.get(horizon) or {}).get(key) or {}
            cells.append(_chip(v.get('verdict', 'NOT MEASURED')) + f'<span class="small fl-sub">{esc("; ".join(v.get("reasons") or []))}</span>')
        rows.append(cells)
    note = (f'<p class="small">A period can confirm a model only if it can detect a mean rank correlation of {esc(str(r["sufficiency"].get("reference_ic")))}; that takes '
            f'{_count(r["sufficiency"].get("observations_needed"))} effective independent observations (non-overlapping label windows times effective independent '
            'instruments). Row counts are not used.</p>')
    return note + _table(['Model family', '5-session label', '20-session label'], rows)


def _holdout(r):
    h = r['holdout']
    rows = [[esc(name.replace('_', ' ')), _span(span)] for name, span in (h.get('segments') or {}).items()]
    return (_facts([('Checkpoint 7 holdout reused as pristine', 'NO'), ('Historical holdout', _chip(h.get('historical_holdout'))),
                    ('Forward holdout', _chip(h.get('forward_holdout'))), ('Split version', esc(h.get('split_version', ''))),
                    ('Purge before the holdout', f'{_count(h.get("purge_sessions"))} sessions')])
            + _table(['Segment', 'Sessions'], rows) + '<ul class="small">' + ''.join(f'<li>{esc(rule)}</li>' for rule in h.get('rules') or []) + '</ul>')


def _regimes(r):
    out = []
    for title, key in (('Development period, where samples exist', 'development_period'), ('Closes held outside the historical database (the burned Checkpoint 7 window)', 'held_today')):
        g = (r.get('regimes') or {}).get(key) or {}
        if g.get('status') == 'NOT_MEASURABLE' or 'sessions' not in g:
            out.append(f'<p class="small"><b>{esc(title)}:</b> not measurable — {esc(str(g.get("reason", "no series stored")))}.</p>')
            continue
        out.append(f'<p class="small"><b>{esc(title)}</b> ({_span([g.get("first"), g.get("last")])}, {_count(g.get("sessions"))} sessions)</p>'
                   + _facts([('Bear markets (20% or more)', _count(g.get('bear_markets'))), ('Corrections (10% to 20%)', _count(g.get('corrections'))),
                             ('High-volatility episodes', _count(g.get('high_volatility_episodes'))), ('Low-volatility episodes', _count(g.get('low_volatility_episodes'))),
                             ('Rising-rate periods', _count(g.get('rising_rate_periods'))), ('Falling-rate periods', _count(g.get('falling_rate_periods')))]))
    return ''.join(out) + ('<p class="small">A description of the past made with hindsight, as counts. An episode is at least 20 sessions. '
                           'It is not a regime model and feeds nothing.</p>')


def _provenance(r):
    out = []
    for p in r['provenance']:
        body = _facts([('Provider / source', esc(str(p.get('provider') or 'none'))), ('Date range', _span(p.get('date_range'))), ('Version', esc(str(p.get('version') or '—'))),
                       ('Known-at methodology', esc(str(p.get('known_at_methodology') or '—'))), ('Adjustment basis', esc(str(p.get('adjustment_basis') or '—'))),
                       ('Point-in-time eligibility', esc(TIER_NAMES.get(p.get('pit_eligibility'), 'none: nothing stored')))])
        body += '<ul class="small">' + ''.join(f'<li>{esc(x)}</li>' for x in p.get('limitations') or []) + '</ul>'
        out.append(_fold(p.get('name', 'Source'), body, TIER_NAMES.get(p.get('pit_eligibility'), 'nothing stored')))
    return ''.join(out)


def _decision(r):
    d = r['provider_decision']
    rows = [[esc(name), esc(why)] for name, why in (d.get('not_selected') or {}).items()]
    return (_facts([('Status', _chip(d.get('status'))), ('What this report can see', esc(str(d.get('statement')))), ('Selected provider', esc(str(d.get('selected_provider')))),
                    ('Product', esc(str(d.get('product')))), ('Price', esc(str(d.get('price')))), ('Licence', esc(str(d.get('licence')))),
                    ('Open question', esc(str(d.get('open_question'))))]) + _table(['Not selected', 'Why'], rows))


def _captures(r):
    rows = [[esc(str(c.get('kind'))), esc(str(c.get('file'))), esc(str(c.get('sha256', ''))[:12]), esc(str(c.get('captured_at', ''))[:19]), _count(c.get('rows_read')),
             _count(c.get('rows_stored')), _count(c.get('rows_rejected'))] for c in r['market_data'].get('captures') or []]
    return _table(['Kind', 'File', 'SHA-256', 'Captured (UTC)', 'Read', 'Stored', 'Rejected'], rows)


def _render(state):
    if not state or not state.get('exists'):
        reason = (state or {}).get('missing_reason', 'NO_STORED_READINESS_REPORT')
        return (f'<p class="fl-stamp">{esc(WARNING)}</p><p class="v10-empty">No historical data readiness report is stored ({esc(reason)}). '
                'Nothing is assumed: no historical market data is shown as available, and the strict point-in-time sample count is not shown as anything but unknown.</p>')
    r = state['report']
    head = (f'<p class="fl-stamp">{esc(WARNING)}</p>'
            '<p class="v10-note">What historical data is stored, how each source is dated, and whether it is enough to test a model honestly. '
            'Counts, dates and versions only: no price, no forecast, no ranking.</p>')
    return (head + '<h3>What stands</h3>' + _stands(r)
            + '<h3>Coverage</h3>' + _coverage(r)
            + _fold('Sufficiency bars', _bars(r), f'{sum(1 for b in r["specification_bars"] if b.get("status") == "MET")} of {len(r["specification_bars"])} met; '
                                                  'set before any data was collected')
            + _fold('Data sufficiency by model family', _sufficiency(r), 'no model is trained here')
            + _fold('Fresh holdout', _holdout(r), 'sealed')
            + _fold('Market regime coverage', _regimes(r), 'descriptive only')
            + _fold('Source provenance', _provenance(r), 'provider, dates, version, known-at, adjustment, eligibility, limitations')
            + _fold('Provider decision', _decision(r), esc(str(r['provider_decision'].get('status', ''))))
            + _fold('Ingested files', _captures(r), 'validation receipts')
            + _fold('Remaining gaps', '<ul class="small">' + ''.join(f'<li>{esc(g)}</li>' for g in r['gaps']) + '</ul>'
                    + '<ul class="small">' + ''.join(f'<li>{esc(x)}</li>' for x in r.get('limitations') or []) + '</ul>', f'{len(r["gaps"])} named')
            + f'<p class="small fl-sub">Report {esc(str(r.get("report_hash", ""))[:12])}, specification {esc(str(r.get("spec_version", "")))}, '
              f'generated {esc(str(r.get("generated_at", ""))[:19])} UTC. File {esc(str(state.get("file", "")))}. '
              'The hash is an integrity check, not a signature: it detects a damaged file, not who wrote it.</p>')


def render_history(fl):
    """The section body. A report the page cannot draw is shown as unavailable; it never takes the page down."""
    try:
        return _render((fl or {}).get('history'))
    except Exception as error:                                         # noqa: BLE001 - a damaged report must not break the rest of the page
        return (f'<p class="fl-stamp">{esc(WARNING)}</p><p class="v10-empty">The stored readiness report could not be drawn '
                f'({esc(type(error).__name__)}). Nothing is assumed from it.</p>')
