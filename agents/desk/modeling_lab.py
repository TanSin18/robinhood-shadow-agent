"""Modeling Laboratory: a read-only view of the stored research report. Escaped text and plain tables only.

MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE. The page shows predicted excess returns, probabilities,
uncertainty, ranks and model disagreement as research measurements. It has no form, no action and no instruction to
do anything with a security, and a research status is shown in one neutral style whatever it is.
"""
from .components import esc

WARNING = 'MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE'
STATUS_NOTE = (('REJECTED', 'not better than the strongest naive baseline on development sessions'),
               ('EXPERIMENTAL', 'not established: a gate was missed, or the model failed the data-sufficiency gate, in which case its result is not evidence either way'),
               ('CHALLENGER', 'better than every naive baseline on development sessions and not worse on the holdout; not established after adjustment for the number of models compared'),
               ('ELIGIBLE_FOR_FUTURE_REVIEW', 'passed every research gate; eligible for a later human review, nothing more'))
FAMILY_NAMES = {'A_baseline': 'naive baseline', 'B_linear': 'linear', 'C_boosted_trees': 'boosted trees', 'D_neural': 'feed-forward network', 'E_sequence': 'sequence network',
                'F_transformer': 'transformer', 'ensemble': 'combination'}
TARGET_NAMES = {'excess_return_5': '5-session excess return vs VTI', 'excess_return_10': '10-session excess return vs VTI (primary)',
                'excess_return_20': '20-session excess return vs VTI', 'positive_excess_10': 'Probability the 10-session excess return is above zero',
                'close_mae_10': 'Largest adverse close excursion, next 10 sessions', 'close_mfe_10': 'Largest favourable close excursion, next 10 sessions',
                'future_realized_vol_10': 'Realised close-to-close volatility, next 10 sessions'}


def _n(value, places=3, signed=True):
    if value is None or isinstance(value, bool):
        return '—'
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return '—'
    if number != number:
        return '—'
    return f'{number:+.{places}f}' if signed else f'{number:.{places}f}'


def _pct(value, places=2):
    return '—' if value is None else _n(float(value) * 100, places) + '%'


def _interval(pair, places=3):
    if not pair or pair[0] is None or pair[1] is None:
        return 'no interval'
    return f'{_n(pair[0], places)} to {_n(pair[1], places)}'


def _status(status):
    """One neutral style for every research status: no colour says "good" or "bad" about a model."""
    return f'<span class="cat cat-neutral">{esc(status or "NOT RUN")}</span>'


def _table(head, rows, klass='fl-lab'):
    if not rows:
        return '<p class="v10-empty">Nothing stored.</p>'
    return (f'<div class="table-wrap"><table class="mini fl-ready {klass}"><thead><tr>' + ''.join(f'<th>{esc(h)}</th>' for h in head) + '</tr></thead><tbody>'
            + ''.join('<tr>' + ''.join(f'<td data-label="{esc(h)}">{cell}</td>' for h, cell in zip(head, row)) + '</tr>' for row in rows) + '</tbody></table></div>')


def _fold(title, body, hint=''):
    """A section that starts closed: the page is long, and the detail is there for whoever wants it."""
    return f'<details class="fl-fold"><summary>{esc(title)}' + (f'<span>{esc(hint)}</span>' if hint else '') + f'</summary>{body}</details>'


def _facts(rows):
    return '<dl class="v10-facts fl-facts">' + ''.join(f'<div><dt>{esc(k)}</dt><dd>{v}</dd></div>' for k, v in rows) + '</dl>'


def _leaderboard(rows):
    out = []
    for r in rows:
        if r.get('not_run'):
            out.append([f'<b>{esc(r["name"])}</b>', esc(r.get('family') or ''), _status(None) + f'<span class="small fl-sub">{esc(r["not_run"])}</span>', '—', '—', '—', '—', '—'])
            continue
        folds = ' / '.join(_n(x, 2) for x in r.get('fold_ics') or [])
        role = 'naive baseline' if r['role'] == 'BASELINE' else esc(FAMILY_NAMES.get(r.get('family'), r.get('family') or ''))
        reasons = '; '.join(r.get('status_reasons') or [])
        gate = f'<span class="small fl-sub">{esc(r["sufficiency"])}</span>' if r.get('sufficiency') and r['sufficiency'] != 'sufficient' else ''
        out.append([f'<b>{esc(r["name"])}</b>', role,
                    _status(r['status']) + gate + f'<details class="small"><summary>why</summary>{esc(reasons)}</details>',
                    f'{_n(r.get("dev_mean_ic"))}<span class="small fl-sub">{esc(_evidence(r, "dev"))}</span>',
                    f'{esc(str(r.get("folds_positive", 0)))} of {esc(str(r.get("folds", 0)))}<span class="small fl-sub">{esc(folds)}</span>',
                    f'{_n(r.get("holdout_mean_ic"))}<span class="small fl-sub">{esc(_evidence(r, "holdout"))}</span>',
                    (_n(r.get('dev_rmse'), 4, False) + ' / ' + _n(r.get('holdout_rmse'), 4, False)) if r.get('dev_rmse') is not None else
                    (_n(r.get('dev_log_loss'), 4, False) + ' / ' + _n(r.get('holdout_log_loss'), 4, False)) if r.get('dev_log_loss') is not None else
                    '<span class="small fl-sub">a rank score: no error in return units</span>',
                    _pct(r.get('dev_top_minus_bottom')) + ' / ' + _pct(r.get('holdout_top_minus_bottom'))])
    return out


def _evidence(r, part):
    """What stands behind one rank-correlation number: its interval, how many batches the interval rests on, and how many
    sessions the model ranked at all."""
    batches, sessions, ranked = r.get(f'{part}_batches'), r.get(f'{part}_sessions'), r.get(f'{part}_sessions_ranked')
    text = _interval(r.get(f'{part}_ic_interval_90'))
    if batches is not None:
        text += f' · {batches} batches'
    if sessions is not None and ranked is not None and ranked < sessions:
        text += f' · ranked {ranked} of {sessions} sessions'
    return text


STAMP = f'<p class="fl-stamp">{esc(WARNING)}</p>'
INTRO = ('<p class="v10-note">A research laboratory. It asks one question: do any descriptors or model families carry out-of-sample information about the '
         '10-session excess return against VTI? It does not say what to hold, how much, or when. No model here is in use, and none has a production or live status.</p>')


def render_modeling(fl):
    """The laboratory section. A stored report that is incomplete or of an older shape never takes the page down: the
    section says the report could not be shown, and shows nothing from it."""
    lab = (fl or {}).get('modeling') if isinstance(fl, dict) else None
    lab = lab if isinstance(lab, dict) else {}
    report = lab.get('report')
    if not lab.get('exists') or not report:
        return STAMP + INTRO + f'<p class="v10-empty">No laboratory run is stored on this machine ({esc(lab.get("missing_reason") or "NO_STORED_LABORATORY_RUN")}).</p>'
    try:
        return _render(lab, report)
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, ArithmeticError) as error:
        return STAMP + INTRO + ('<p class="v10-empty">A laboratory report is stored but could not be shown: it is incomplete or has a shape this page does not know '
                                f'({esc(type(error).__name__)}). Nothing from it is displayed.</p>')


def _render(lab, report):
    stamp, intro = STAMP, INTRO
    data, validation, champions = report['dataset'], report['validation'], report['best_research_models']
    fib = report['ablation']['fibonacci']
    windows = data['evaluation_windows']
    dev_w, hold_w = windows['development']['non_overlapping_windows'], windows['holdout']['non_overlapping_windows']
    strict = data.get('strict_point_in_time_samples')
    summary = _facts((
        ('Time rule', f'<b>{esc(report["time_policy"])}</b> every input was captured on 2026-10-01 to 2026-10-03; nothing here proves it was held earlier'),
        ('Strict point-in-time samples', (f'<b>{esc(str(strict))}</b> under the strict known-at rule' if strict is not None else 'not measured')
         + esc(f' ({data.get("closes_held_at_their_own_session_close")} stored closes were held at their own session close)')),
        ('Research samples', esc(f'{data["usable_samples"]:,} rows: {len(data["instruments"])} instruments × {data["usable_sessions"]} sessions '
                                 f'({data["first_usable_session"]} to {data["last_usable_session"]})')),
        ('Predicted sessions', esc(f'{windows["development"]["sessions"]} development, {windows["holdout"]["sessions"]} holdout')),
        ('Non-overlapping label windows in them', esc(f'development: {dev_w.get("5")} of 5 sessions, {dev_w.get("10")} of 10, {dev_w.get("20")} of 20; '
                                                       f'holdout: {hold_w.get("5")}, {hold_w.get("10")}, {hold_w.get("20")}. {windows.get("note", "")}')),
        ('Effective independent instruments', esc(_n(data.get('effective_independent_instruments'), 1, False))),
        ('Descriptors', esc(f'{data["features"]} encoded as numbers, {data.get("features_in_a_model_group")} of them offered to a model, '
                            f'{data.get("features_ever_available")} of those ever available; {data["excluded_features"]} left out by rule (dollar levels, structured values)')),
        ('Dataset hash', f'<code>{esc(data["dataset_hash"][:16])}</code>'),
        ('Feature calculation hash', f'<code>{esc(data["calculation_hash"][:16])}</code>'),
        ('Code hash', f'<code>{esc(report["code_hash"][:16])}</code>'),
        ('Plan', esc(report['plan_version']) + (' (v1 was fixed before any model was fitted; later versions record the repairs made after the first run and after each review)'
                                                 if report.get('supersedes') else ' (fixed before any model was fitted)')),
        ('Replaces', esc(str((report.get('supersedes') or {}).get('report_id', ''))[:16] + ' — ' + str((report.get('supersedes') or {}).get('reason', ''))) if report.get('supersedes') else 'nothing'),
        ('Models in the registry', esc(str(lab.get('models', 0))) + ' — ' + esc(', '.join(f'{k} {v}' for k, v in sorted((lab.get('registry_statuses') or {}).items())))
         + (esc(f' ({lab["models_from_other_runs"]} rows of other runs are kept in the file and not counted)') if lab.get('models_from_other_runs') else '')),
        ('Configurations fitted', esc(f'{validation["configurations_fitted"]:,}')),
        ('Fibonacci', f'<b>{esc(fib["statement"])}</b>'),
    ))
    limits = '<ul>' + ''.join(f'<li>{esc(x)}</li>' for x in data['limitations']) + '</ul>'
    folds = _table(('Block', 'Training sessions', 'Removed by the purge', 'Predicted sessions'),
                   [[f'<b>{esc(b["name"])}</b>', esc(f'{b["train"][0]} to {b["train"][1]} ({b["train_sessions"]})') if b['train'] else '—',
                     esc(f'{b["purged_sessions"]} sessions'), esc(f'{b["validation"][0]} to {b["validation"][1]} ({b["validation_sessions"]})')] for b in validation['blocks']])
    design = _facts((('Split', esc(validation['split_method'])), ('Purge', esc(f'{validation["purge_sessions"]} sessions before every predicted block')),
                     ('Embargo', esc(f'{validation["embargo_sessions"]} sessions')), ('Gap before the holdout', esc(f'{validation["gap_before_holdout_sessions"]} sessions')),
                     ('Tuning', esc(validation['inner_tuning'])), ('Intervals', esc(validation['interval_method'])),
                     ('Sessions without a ranking', esc(validation['unranked_sessions'])),
                     ('Many comparisons', esc(validation['multiple_testing']) + esc('; family sizes: ' + ', '.join(f'{k} {v}' for k, v in sorted(validation['holm_family_sizes'].items()))))))
    meanings = '<ul>' + ''.join(f'<li>{_status(name)} {esc(text)}</li>' for name, text in STATUS_NOTE) + '</ul>'
    head = ('Model', 'Family', 'Research status', 'Development rank correlation', 'Folds above zero', 'Holdout rank correlation', 'Error, development / holdout',
            'Top 5 minus bottom 5, development / holdout')
    boards = ''
    for target in ('excess_return_10', 'excess_return_5', 'excess_return_20', 'positive_excess_10'):
        rows = report['tables'].get(target) or []
        strongest = (report.get('strongest_baseline') or {}).get(target)
        note = '<p class="v10-note">' + (f'Strongest naive baseline on development sessions: <b>{esc(strongest)}</b>. A model is compared with it, per session, '
                                         'with overlapping labels respected. ' if strongest else '')
        if target == 'positive_excess_10':
            note += ('Error is log loss; the base rate is the training share of positive outcomes. The rank correlation ranks the 10-session excess return by the '
                     'predicted probability, so a classifier is compared with the same naive baseline as the 10-session models.')
        note += '</p>'
        counts = {}
        for r in rows:
            if r.get('role') == 'CANDIDATE' and r.get('status'):
                counts[r['status']] = counts.get(r['status'], 0) + 1
        hint = ', '.join(f'{k} {v}' for k, v in sorted(counts.items())) or 'nothing judged'
        body = note + _table(head, _leaderboard(rows), 'fl-lab fl-board')
        boards += (f'<h3>{esc(TARGET_NAMES[target])}</h3><p class="v10-note">Candidates: {esc(hint)}.</p>{body}' if target == 'excess_return_10'
                   else _fold(TARGET_NAMES[target], body, 'candidates: ' + hint))
    ablation = _table(('Reference model', 'Descriptor set', 'Descriptors', 'Development rank correlation', 'Change against technical baseline', 'Holdout rank correlation', 'Holdout change'),
                      [[esc(r['model']), f'<b>{esc(r["set"])}</b>', esc(str(r.get('features', '—'))), _n(r.get('dev_mean_ic')),
                        (_n(r.get('dev_ic_change')) + f'<span class="small fl-sub">{esc(_interval(r.get("dev_ic_change_interval_90")))}</span>') if 'dev_ic_change' in r else 'reference',
                        _n(r.get('holdout_mean_ic')), _n(r.get('holdout_ic_change')) if 'holdout_ic_change' in r else 'reference'] for r in report['ablation']['rows']])
    fib_detail = '; '.join(f'{m}: development {_n(v["dev_ic_change"])} ({_interval(v["dev_interval_90"])}), holdout {_n(v["holdout_ic_change"])}' for m, v in fib['by_reference_model'].items())
    specialists = report['specialists']
    special = _table(('Specialist', 'Descriptors', 'Development rank correlation', 'Holdout rank correlation', 'Note'),
                     [[f'<b>{esc(r["specialist"])}</b>', esc(str(r['features'])), _n(r['dev_mean_ic']), _n(r['holdout_mean_ic']), esc(r.get('note') or '')] for r in specialists['rows']]
                     + [[f'<b>{esc(r["name"])}</b>', 'combination', _n(r['dev_mean_ic']), _n(r['holdout_mean_ic']), _status(r['status'])] for r in specialists['combinations']]
                     + [['<b>one unified model</b>', esc(specialists['unified_model']['model']), _n(specialists['unified_model']['dev_mean_ic']),
                         _n(specialists['unified_model']['holdout_mean_ic']), 'for comparison']])
    sufficiency = _table(('Network', 'Trainable parameters', 'Effective independent observations', 'Per parameter (10 needed)', 'Seed-to-seed range of development rank correlation', 'Gate'),
                         [[f'<b>{esc(k)}</b>'] + ([esc('inherited from ' + ', '.join(v['inherited_from'])), '—', '—', '—'] if v.get('inherited_from') else
                                                   [esc(f'{v["parameters"]:,}'), esc(str(v['effective_independent_observations'])), esc(str(v['observations_per_parameter'])),
                                                    _n(v.get('seed_ic_range'), 3, False)]) + [_status(v['label'])] for k, v in sorted(report['sufficiency'].items())])
    distribution = report['distribution']
    dist_rows = []
    for name, body in distribution['models'].items():
        if 'not_run' in body:
            dist_rows.append([f'<b>{esc(name)}</b>', _status(None), esc(body['not_run']), '—', '—'])
            continue
        cover = body['coverage']
        dist_rows.append([f'<b>{esc(name)}</b>', _status(body.get('status')), _n(body['mean_dev_pinball'], 5, False) + ' / ' + _n(body['mean_holdout_pinball'], 5, False),
                          esc(f'{cover["10-90 dev"]["coverage"]:.0%} / {cover["10-90 holdout"]["coverage"]:.0%} (nominal 80%)'),
                          esc(f'{cover["25-75 dev"]["coverage"]:.0%} / {cover["25-75 holdout"]["coverage"]:.0%} (nominal 50%)')])
    dist = _table(('Quantile model', 'Research status', 'Mean pinball loss, development / holdout', '10%–90% interval coverage', '25%–75% interval coverage'), dist_rows)
    risk_rows = []
    for target, body in report['risk'].items():
        for name, r in body.items():
            if 'not_run' in r:
                continue
            strongest = (report.get('risk_baselines') or {}).get(target)
            state = (('strongest naive baseline' if name == strongest else 'naive baseline') if r['role'] == 'BASELINE' else
                     _status(r['status']) + (f'<span class="small fl-sub">compared with {esc(r["compared_with"])}</span>' if r.get('compared_with') else ''))
            risk_rows.append([esc(TARGET_NAMES[target]), f'<b>{esc(name)}</b>', state,
                              _n(r['dev_rmse'], 4, False) + ' / ' + _n(r['holdout_rmse'], 4, False)])
    risk = _table(('Risk target (close-based)', 'Model', 'Research status', 'RMSE, development / holdout'), risk_rows)
    calibration = report['calibration']
    cal = _table(('Classifier', 'Log loss, development / holdout', 'Brier, development / holdout', 'Calibration error, development / holdout', 'ROC-AUC, development / holdout'),
                 [[f'<b>{esc(name)}</b>'] + [_n(parts.get('dev', {}).get(k), 4, False) + ' / ' + _n(parts.get('holdout', {}).get(k), 4, False)
                                             for k in ('log_loss', 'brier', 'calibration_error', 'roc_auc')] for name, parts in calibration.items()])
    reliability = ''
    for name in ('lightgbm', 'logistic'):
        table = (calibration.get(name, {}).get('dev') or {}).get('reliability')
        if table:
            reliability += (f'<details class="small"><summary>Reliability buckets, {esc(name)}, development</summary>'
                            + _table(('Predicted probability', 'Rows', 'Mean predicted', 'Observed share'), [[esc(b['bucket']), esc(str(b['n'])), _n(b['mean_probability'], 3, False),
                                                                                                             _n(b['observed_rate'], 3, False)] for b in table]) + '</details>')
    disagreement = report['disagreement']
    dis = _facts([(f'{part.capitalize()}: models disagree on the direction', esc(f'{body["share_with_sign_disagreement"]:.0%} of rows')) for part, body in disagreement.items() if isinstance(body, dict)]
                 + [(f'{part.capitalize()}: dispersion against the size of the error (rank correlation)', _n(body['dispersion_vs_absolute_error_spearman'])) for part, body in disagreement.items() if isinstance(body, dict)]
                 + [('Models compared', esc(', '.join(k.split('/')[0] for k in disagreement['models']))), ('Use', esc(disagreement['note']))])
    uncertainty = report['uncertainty']
    unc = _facts([(k.replace('_', ' ').capitalize(), esc(v['method']) + f' — against the size of the error: {_n(v.get("spread_vs_absolute_error_spearman", v.get("width_vs_absolute_error_spearman")))}')
                  for k, v in uncertainty.items() if isinstance(v, dict)] + [('Caution', esc(uncertainty.get('note', '')))])
    importance = report['importance']
    imp_rows = []
    for name in ('ridge', 'lightgbm'):
        body = importance.get(name)
        if not body:
            continue
        share = body.get('family_share') or body.get('tree_shap_family_share') or {}
        imp_rows.append([f'<b>{esc(name)}</b>', esc(body['method']), esc(', '.join(f'{k} {v:.0%}' for k, v in list(share.items())[:6])),
                         esc(', '.join(f'{k} {_n(v)}' for k, v in list((body.get('permutation_ic_loss_by_family') or {}).items())[:6]) or 'not computed')])
    imp = _table(('Reference model', 'Method', 'Share of reliance by family', 'Rank correlation lost when a family is shuffled'), imp_rows)
    meta = report['meta_label']
    meta_rows = [[esc(part), _n(body.get('meta_model_auc'), 3, False), _n(body.get('prediction_size_rule_auc'), 3, False), _n(body.get('primary_direction_right_rate'), 3, False)]
                 for part, body in meta.items() if isinstance(body, dict) and 'meta_model_auc' in body]
    conditional = report['conditional']
    cond = _table(('VTI volatility group (cut-offs from the first training window)', 'Sessions', 'Independent windows', 'Mean rank correlation', 'Enough to read?'),
                  [[esc(g['group']), esc(str(g['sessions'])), esc(str(g['non_overlapping_windows'])), _n(g['mean_ic']), 'yes' if g['meaningful'] else 'no'] for g in conditional['vti_volatility_terciles']['groups']])
    economic = report['economic']
    eco = _table(('Model', 'Top 5 minus bottom 5, development', 'Holdout', 'Whole development interval above the stated cost range? (a description, not a signal)'),
                 [[f'<b>{esc(r["name"])}</b>', _pct(r['dev_spread']) + f'<span class="small fl-sub">{esc(_interval([None if x is None else x * 100 for x in (r["dev_interval_90"] or [None, None])], 2))} %</span>',
                   _pct(r['holdout_spread']), 'yes' if r['development_interval_above_stated_cost_range'] else 'no'] for r in economic['rows']])
    best_rows = []
    for label, key, a, b, loss in (('5-session excess return', 'best_5d', 'dev_mean_ic', 'holdout_mean_ic', False), ('10-session excess return', 'best_10d', 'dev_mean_ic', 'holdout_mean_ic', False),
                                   ('20-session excess return', 'best_20d', 'dev_mean_ic', 'holdout_mean_ic', False), ('Classifier (log loss)', 'best_classifier', 'dev_log_loss', 'holdout_log_loss', True),
                                   ('Distribution (pinball loss)', 'best_distribution_model', 'mean_dev_pinball', 'mean_holdout_pinball', True),
                                   ('Downside (RMSE)', 'best_downside_model', 'dev_rmse', 'holdout_rmse', True), ('Strongest naive baseline', 'strongest_baseline', 'dev_mean_ic', 'holdout_mean_ic', False),
                                   ('Strongest advanced candidate', 'strongest_advanced_candidate', 'dev_mean_ic', 'holdout_mean_ic', False)):
        row = champions.get(key) or {}
        best_rows.append([esc(label), f'<b>{esc(row.get("name") or "none")}</b>'
                          + ('<span class="small fl-sub">naive baseline</span>' if row.get('role') == 'BASELINE' else '')
                          + f'<span class="small fl-sub">{"lowest loss" if loss else "highest"} of {esc(str(row.get("highest_of", "—")))} compared</span>',
                          _status(row.get('status')) + (f'<span class="small fl-sub">{esc(row["sufficiency"])}</span>' if row.get('sufficiency') not in (None, 'sufficient') else ''),
                          _n(row.get(a), 4, not loss), _n(row.get(b), 4, not loss)])
    best = _table(('Question', 'Best development score', 'Research status', 'Development', 'Holdout'), best_rows)
    examples = ''
    for e in report.get('examples') or []:
        contributions = ', '.join(f'{k} {_n(v, 4)}' for k, v in list(e['family_contributions'].items())[:5])
        features = ', '.join(f'{f["feature"]} {_n(f["contribution"], 4)}' for f in e['largest_features'])
        models_line = ', '.join(f'{k} {_pct(v)}' for k, v in e['predictions_by_model'].items())
        examples += (f'<details class="small"><summary>{esc(e["instrument"])} · {esc(e["session"])} · {esc(e["label"])}</summary>'
                     + _facts((('Predicted 10-session excess return', _pct(e['predicted_excess_return_10'])), ('Benchmark prediction', _pct(e['benchmark_prediction'])),
                               ('10%–90% interval', esc(_interval([None if x is None else x * 100 for x in e['interval_10_90']], 2)) + ' %'),
                               ('By model', esc(models_line)), ('Dispersion across models', _pct(e['model_dispersion'])),
                               ('What happened afterwards', _pct(e['realized_excess_return_10'])),
                               ('Contribution by descriptor family', esc(contributions)), ('Largest single descriptors', esc(features)),
                               ('How the contributions were computed', esc(e['explanation_model'])),
                               ('Feature snapshot', f'<code>{esc(e["feature_snapshot_id"][:16])}</code> · calculation <code>{esc(e["calculation_hash"][:16])}</code>'))) + '</details>')
    return (stamp + intro + summary
            + '<h3>What this data cannot support</h3>' + limits
            + '<h3>Best development scores, with what the holdout said</h3><p class="v10-note">' + esc(champions['note']) + '</p>' + best
            + boards
            + '<h3>Feature-family ablation</h3><p class="v10-note">Each family is added to the technical baseline (trend, momentum, volatility) and compared with it per session. '
            + f'<b>{esc(fib["statement"])}</b>: {esc(fib["why"])}. {esc(fib_detail)}. {esc(report["ablation"].get("note", ""))}</p>' + ablation
            + '<h3>Neural models: is there enough data?</h3><p class="v10-note">A network that fails the gate is still shown, labelled, and cannot be a challenger.</p>' + sufficiency
            + '<h3>More detail</h3>'
            + _fold('Validation design', design + folds + '<h3>What a research status means</h3>' + meanings)
            + _fold('Specialist models and combinations', special)
            + _fold('Return distribution', dist)
            + _fold('Risk targets', risk)
            + _fold('Calibration', cal + reliability)
            + _fold('Model disagreement', dis)
            + _fold('Uncertainty', unc)
            + _fold('What the reference models leaned on', '<p class="v10-note">' + esc(importance.get('limits', '')) + '</p>' + imp)
            + _fold('Meta-label research', '<p class="v10-note">' + esc(meta.get('note', '')) + ' ' + esc(meta.get('question', '')) + '</p>'
                    + _table(('Period', 'Meta model AUC', 'Prediction-size rule AUC', 'Share of rows where the primary direction was right'), meta_rows))
            + _fold('Results by factual context', '<p class="v10-note">' + esc(conditional.get('note', '')) + '</p>' + cond
                    + _facts((('Volatility groups', esc(conditional['vti_volatility_terciles'].get('result') or 'not stated')),
                              ('Fed context', esc(conditional['fed']['result'])), ('PCE context', esc(conditional['pce']['result'])))))
            + _fold('Size of the ranking spread', '<p class="v10-note">' + esc(economic['statement'])
                    + f' Stated cost range: {_pct(economic["cost_range_round_trip_two_legs"][0])} to {_pct(economic["cost_range_round_trip_two_legs"][1])}.</p>' + eco)
            + _fold('Prediction examples — research only', '<p class="v10-note">Shown so the provenance of a prediction can be followed. Which rows: '
                    + esc(((report.get('examples') or [{}])[0] or {}).get('shown_because') or 'none stored')
                    + '. They are measurements of a research model, not advice of any kind.</p>' + (examples or '<p class="v10-empty">None stored.</p>')))
