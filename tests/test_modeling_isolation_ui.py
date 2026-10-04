"""Checkpoint 7 isolation and the Modeling Laboratory page.

What is proven here: the modeling package cannot reach a broker, an order path or the registered database; nothing in
the trading side imports it; no schedule starts it; the page carries the permanent research-only warning, shows model
provenance, and never shows a buy/sell/enter/exit label or a production status."""
import ast
import json
import re
import sqlite3
from pathlib import Path

import pytest

from agents.desk import firm_lab_page, modeling_lab
from firm_lab import capabilities, modeling, modeling_view

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'firm_lab' / 'modeling'
BANNED_IMPORTS = ('agents', 'broker', 'broker_proxy', 'risk', 'config', 'data', 'eval', 'prompts', 'scripts', 'research', 'robin_stocks', 'alpaca', 'urllib',
                  'socket', 'http', 'ssl', 'requests', 'subprocess', 'firm_lab_collectors')
ACTION_WORDS = ('BUY', 'SELL', 'ENTER', 'EXIT', 'STRONG BUY', 'CONVICTION TRADE', 'GO LONG', 'GO SHORT', 'OVERWEIGHT', 'UNDERWEIGHT')


def _imports(path):
    tree = ast.parse(path.read_text())
    return ({a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
            | {n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and not n.level})


def test_the_modeling_package_cannot_reach_a_broker_the_network_or_the_trading_side():
    files = sorted(PACKAGE.glob('*.py')) + [ROOT / 'firm_lab' / 'modeling_view.py']
    assert len(files) >= 14
    for path in files:
        modules = _imports(path)
        assert not [m for m in modules if m.split('.')[0] in BANNED_IMPORTS], (path.name, modules)
        allowed_firm_lab = [m for m in modules if m.startswith('firm_lab')]
        assert all(m.startswith('firm_lab.research_features') for m in allowed_firm_lab), (path.name, allowed_firm_lab)      # only the accepted calculators
        text = path.read_text()
        for word in ('agent.db', 'paper_accounts', 'submit(', 'place_order', 'ExecutionBoundary', 'launchctl', 'crontab', 'schedule.every'):
            assert word not in text, (path.name, word)
    # the projection the dashboard loads is standard library only: no model code, no numpy
    assert _imports(ROOT / 'firm_lab' / 'modeling_view.py') <= {'__future__', 'json', 'sqlite3', 'pathlib'}
    # write-capable modeling code opens its database through one checked path
    for name in ('registry.py', 'dataset.py', 'history.py'):
        assert 'timeview.check(' in (PACKAGE / name).read_text(), name


def test_nothing_on_the_trading_side_imports_the_modeling_package_and_nothing_schedules_it():
    for folder in ('agents', 'broker', 'broker_proxy', 'risk', 'config', 'eval', 'scripts', 'data', 'research'):
        for path in sorted((ROOT / folder).rglob('*.py')) if (ROOT / folder).is_dir() else []:
            text = path.read_text(errors='ignore')
            if path.name in ('firm_lab_page.py', 'modeling_lab.py'):
                continue
            assert 'firm_lab.modeling' not in text and 'modeling_view' not in text and 'firm_lab_modeling' not in text, path
    page = (ROOT / 'agents' / 'desk' / 'modeling_lab.py').read_text()
    assert _imports(ROOT / 'agents' / 'desk' / 'modeling_lab.py') == set() and 'from .components import esc' in page      # the renderer imports only the escaper
    assert 'firm_lab.modeling' not in (ROOT / 'agents' / 'desk' / 'firm_lab_page.py').read_text()   # the page never loads model code
    for path in ROOT.rglob('*'):
        if path.is_file() and path.suffix in ('.plist', '.sh', '.command', '.service', '.timer', '.cron') and '.git' not in path.parts:
            assert 'firm_lab.modeling' not in path.read_text(errors='ignore'), path
    view = (ROOT / 'firm_lab' / 'view.py').read_text()
    assert 'from .modeling_view import summary' in view and 'from .modeling ' not in view and 'modeling.lab' not in view


def test_there_is_no_production_or_live_status_and_no_action_output_anywhere_in_the_package():
    assert modeling.STATUSES == ('EXPERIMENTAL', 'CHALLENGER', 'REJECTED', 'ELIGIBLE_FOR_FUTURE_REVIEW')
    assert modeling_view.ALLOWED_STATUSES == modeling.STATUSES and modeling.WARNING == modeling_view.WARNING == modeling_lab.WARNING
    assert modeling.WARNING == 'MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE'
    for path in sorted(PACKAGE.glob('*.py')) + [ROOT / 'agents' / 'desk' / 'modeling_lab.py', ROOT / 'firm_lab' / 'modeling_view.py']:
        text = path.read_text()
        for literal in re.findall(r"'([A-Z][A-Z_ ]{2,})'", text):
            assert literal not in ('PRODUCTION', 'LIVE', 'DEPLOYED', 'PROMOTED', 'CHAMPION') or path.name == 'registry.py', (path.name, literal)
            assert literal not in ACTION_WORDS, (path.name, literal)
        assert 'position_size' not in text and 'kelly' not in text.lower() and 'order_quantity' not in text, path.name
    forbidden = (PACKAGE / 'registry.py').read_text()
    assert "FORBIDDEN_STATUS_WORDS = ('PRODUCTION', 'LIVE', 'DEPLOYED', 'ACTIVE', 'CHAMPION_LIVE')" in forbidden      # named only to be refused
    assert capabilities.RESEARCH_ONLY in capabilities.STATUSES and capabilities.RESEARCH_ONLY != capabilities.AVAILABLE


# ====================================================================================================== the page
def _row(name, role='CANDIDATE', status='EXPERIMENTAL', family='B_linear', **kw):
    return {'key': f'{name}/excess_return_10', 'name': name, 'family': family, 'role': role, 'status': status, 'status_reasons': ['compared with the strongest naive baseline: momentum_20'],
            'target': 'excess_return_10', 'dev_mean_ic': 0.012, 'dev_ic_interval_90': [-0.03, 0.05], 'fold_ics': [0.02, -0.01, 0.03, 0.0, 0.02], 'folds_positive': 3, 'folds': 5,
            'holdout_mean_ic': -0.004, 'holdout_ic_interval_90': [-0.06, 0.05], 'dev_rmse': 0.0312, 'holdout_rmse': 0.0298, 'dev_top_minus_bottom': 0.0011,
            'holdout_top_minus_bottom': -0.0004, **kw}


def _report():
    block = lambda name, a, b, c, d, n: {'name': name, 'train': [a, b], 'train_sessions': n, 'validation': [c, d], 'validation_sessions': 26, 'purged': [b, c], 'purged_sessions': 20}
    classifier = _row('logistic', dev_log_loss=0.6931, holdout_log_loss=0.6940)
    classifier.pop('dev_rmse')
    return {
        'warning': modeling.WARNING, 'report_id': 'r' * 64, 'plan_version': 'checkpoint7-tournament-plan-v2', 'time_policy': 'SESSION_TIME_RETROSPECTIVE', 'code_hash': 'c' * 64,
        'supersedes': {'report_id': 'e' * 64, 'reason': 'repairs after the independent review'},
        'dataset': {'dataset_hash': 'd' * 64, 'calculation_hash': 'f' * 64, 'instruments': ['AAPL', 'XLK'], 'usable_samples': 6468, 'usable_sessions': 294,
                    'first_usable_session': '2025-06-30', 'last_usable_session': '2026-09-01', 'strict_point_in_time_samples': 0, 'closes_held_at_their_own_session_close': 0,
                    'features': 159, 'features_in_a_model_group': 140, 'features_ever_available': 95, 'excluded_features': 60,
                    'evaluation_windows': {'development': {'sessions': 131, 'non_overlapping_windows': {'5': 26, '10': 13, '20': 6}},
                                           'holdout': {'sessions': 59, 'non_overlapping_windows': {'5': 11, '10': 5, '20': 2}},
                                           'note': 'Non-overlapping is not the same as independent.'}, 'effective_independent_instruments': 5.8,
                    'limitations': ['Retrospective: every input was captured on 2026-10-01 to 2026-10-03.', 'Labels are price returns on both legs.']},
        'validation': {'split_method': 'expanding-walk-forward-purged-v1', 'walk_forward_folds': 5, 'purge_sessions': 20, 'embargo_sessions': 5, 'gap_before_holdout_sessions': 25,
                       'blocks': [block('fold_1', '2025-06-30', '2025-09-23', '2025-10-22', '2025-11-26', 60), block('final_holdout', '2025-06-30', '2026-04-30', '2026-06-08', '2026-09-01', 210)],
                       'inner_tuning': 'the last quarter of each training window, purged', 'configurations_fitted': 1234,
                       'interval_method': 'Student t on the means of consecutive batches', 'unranked_sessions': 'a session a model does not rank counts as rank correlation 0',
                       'multiple_testing': 'Holm at 10%', 'holm_family_sizes': {'excess_return_10': 54, 'excess_return_5': 16, 'excess_return_20': 16}},
        'tables': {'excess_return_10': [_row('momentum_20', role='BASELINE', family='A_baseline', dev_batches=6, dev_sessions=131, dev_sessions_ranked=104), _row('ridge'),
                                        _row('transformer_encoder', family='F_transformer', sufficiency='EXPERIMENTAL_INSUFFICIENT_DATA'),
                                        {'key': 'catboost/excess_return_10', 'name': 'catboost', 'role': 'CANDIDATE', 'status': None, 'not_run': 'dependency unavailable: catboost', 'target': 'excess_return_10'}],
                   'excess_return_5': [_row('ridge', status='REJECTED')], 'excess_return_20': [_row('ridge', status='CHALLENGER')], 'positive_excess_10': [classifier]},
        'strongest_baseline': {'excess_return_5': 'momentum_20', 'excess_return_10': 'momentum_20', 'excess_return_20': 'momentum_63', 'positive_excess_10': 'momentum_20'},
        'risk_baselines': {'close_mae_10': 'historical_mean'},
        'distribution': {'models': {'train_quantile': {'status': 'EXPERIMENTAL', 'mean_dev_pinball': 0.0101, 'mean_holdout_pinball': 0.0099,
                                                       'coverage': {k: {'coverage': 0.78} for k in ('10-90 dev', '10-90 holdout', '25-75 dev', '25-75 holdout')}},
                                    'lightgbm_quantile': {'not_run': 'dependency unavailable: lightgbm'}}},
        'risk': {'close_mae_10': {'historical_mean': {'role': 'BASELINE', 'status': 'EXPERIMENTAL', 'dev_rmse': 0.021, 'holdout_rmse': 0.02},
                                  'ridge': {'role': 'CANDIDATE', 'status': 'REJECTED', 'dev_rmse': 0.022, 'holdout_rmse': 0.021, 'compared_with': 'historical_mean'}}},
        'ablation': {'note': 'The "sector" set holds only trailing returns relative to VTI.', 'rows': [{'model': 'ridge', 'set': 'technical_baseline', 'features': 30, 'dev_mean_ic': 0.01, 'holdout_mean_ic': 0.0},
                              {'model': 'ridge', 'set': 'technical+fibonacci', 'features': 55, 'dev_mean_ic': 0.012, 'holdout_mean_ic': -0.01, 'dev_ic_change': 0.002,
                               'dev_ic_change_interval_90': [-0.02, 0.03], 'holdout_ic_change': -0.01}],
                     'fibonacci': {'answer': 'INCONCLUSIVE', 'statement': 'FIBONACCI ADDS INCREMENTAL OOS VALUE = INCONCLUSIVE', 'why': 'the intervals include both',
                                   'by_reference_model': {'ridge': {'dev_ic_change': 0.002, 'dev_interval_90': [-0.02, 0.03], 'holdout_ic_change': -0.01}}}},
        'specialists': {'rows': [{'specialist': 'macro', 'features': 8, 'dev_mean_ic': None, 'holdout_mean_ic': None, 'note': 'cannot rank within a session'}],
                        'combinations': [{'name': 'specialist_equal_weight', 'dev_mean_ic': 0.01, 'holdout_mean_ic': 0.0, 'status': 'EXPERIMENTAL'}],
                        'unified_model': {'model': 'lightgbm on the full feature set', 'dev_mean_ic': 0.01, 'holdout_mean_ic': 0.0}},
        'sufficiency': {'transformer_encoder/excess_return_10': {'parameters': 2500, 'effective_independent_observations': 110.0, 'observations_per_parameter': 0.044,
                                                               'seed_ic_range': 0.03, 'label': 'EXPERIMENTAL_INSUFFICIENT_DATA'}},
        'calibration': {'logistic': {'dev': {'log_loss': 0.693, 'brier': 0.25, 'calibration_error': 0.02, 'roc_auc': 0.51,
                                             'reliability': [{'bucket': '0.4-0.5', 'n': 100, 'mean_probability': 0.47, 'observed_rate': 0.49}]},
                                     'holdout': {'log_loss': 0.694, 'brier': 0.25, 'calibration_error': 0.03, 'roc_auc': 0.5}}},
        'disagreement': {'models': ['ridge/excess_return_10', 'xgboost/excess_return_10'], 'note': 'A diagnostic. Disagreement is not converted into any rule.',
                         'dev': {'share_with_sign_disagreement': 0.61, 'dispersion_vs_absolute_error_spearman': 0.03},
                         'holdout': {'share_with_sign_disagreement': 0.58, 'dispersion_vs_absolute_error_spearman': 0.01}},
        'uncertainty': {'epistemic_bootstrap_ensemble': {'method': 'LightGBM refitted on resamples', 'spread_vs_absolute_error_spearman': 0.05}, 'note': 'A model’s own confidence is not a probability.'},
        'importance': {'ridge': {'method': 'absolute standardised coefficients', 'family_share': {'momentum': 0.4, 'trend': 0.3}}, 'limits': 'Importance is not causal.'},
        'meta_label': {'note': 'Research diagnostic. Not a trade filter; nothing is acted on.', 'question': 'is the direction right?',
                       'dev': {'meta_model_auc': 0.51, 'prediction_size_rule_auc': 0.5, 'primary_direction_right_rate': 0.5}},
        'conditional': {'note': 'No macro regime exists and none is created.',
                        'vti_volatility_terciles': {'comparison_possible': False, 'result': 'INSUFFICIENT_DATA: Too few sessions fall in two groups.',
                                                    'groups': [{'group': 'low', 'sessions': 40, 'non_overlapping_windows': 4, 'mean_ic': 0.01, 'meaningful': False}]},
                        'fed': {'result': 'INSUFFICIENT_DATA: too few sessions'}, 'pce': {'result': 'INSUFFICIENT_DATA: too few sessions'}},
        'economic': {'statement': 'Not net strategy P&L.', 'cost_range_round_trip_two_legs': [0.001, 0.004],
                     'rows': [{'name': 'ridge', 'dev_spread': 0.0011, 'dev_interval_90': [-0.004, 0.006], 'holdout_spread': -0.0004, 'development_interval_above_stated_cost_range': False}]},
        'best_research_models': {'note': '"Highest" is the highest development score among the rows compared. It is not a selection for use.',
                                 'best_10d': {'name': 'mlp_sequence_features', 'role': 'CANDIDATE', 'status': 'EXPERIMENTAL', 'dev_mean_ic': 0.12, 'holdout_mean_ic': 0.003,
                                              'sufficiency': 'EXPERIMENTAL_INSUFFICIENT_DATA', 'highest_of': 25},
                                 'strongest_baseline': {'name': 'momentum_20', 'role': 'BASELINE', 'status': 'EXPERIMENTAL', 'dev_mean_ic': 0.02, 'holdout_mean_ic': 0.0, 'highest_of': 7},
                                 'strongest_advanced_candidate': {'name': 'xgboost', 'role': 'CANDIDATE', 'status': 'REJECTED', 'dev_mean_ic': 0.0, 'holdout_mean_ic': 0.0, 'highest_of': 14}},
        'examples': [{'instrument': 'XLK', 'session': '2026-09-01', 'label': 'RESEARCH ONLY — NOT A RECOMMENDATION',
                      'shown_because': 'the six rows of the last holdout session whose prediction is furthest from zero', 'predicted_excess_return_10': 0.004, 'benchmark_prediction': 0.0,
                      'interval_10_90': [-0.03, 0.04], 'predictions_by_model': {'ridge': 0.001, 'lightgbm': 0.004}, 'model_dispersion': 0.002, 'realized_excess_return_10': -0.01,
                      'family_contributions': {'momentum': 0.003, 'fibonacci': -0.0004}, 'largest_features': [{'feature': 'return20', 'contribution': 0.002}],
                      'explanation_model': 'LightGBM (TreeSHAP)', 'feature_snapshot_id': 'a' * 64, 'calculation_hash': 'f' * 64}],
    }


def _lab_file(folder, report, statuses=('EXPERIMENTAL', 'REJECTED')):
    path = folder / modeling_view.FILE_NAME
    db = sqlite3.connect(path)
    with db:
        db.execute('CREATE TABLE firm_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)')
        db.executemany('INSERT INTO firm_meta VALUES (?,?,?)', [('mode', 'BUILD_OBSERVE', ''), ('database_role', 'CHECKPOINT7_MODELING_RESEARCH', '')])
        for table in ('modeling_reports', 'modeling_models'):
            db.execute(f'CREATE TABLE {table} (id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL)')
        db.execute('INSERT INTO modeling_reports VALUES (?,?,?)', ('r1', json.dumps(report), '2026-10-03T23:00:00+00:00'))
        for k, status in enumerate(statuses):
            db.execute('INSERT INTO modeling_models VALUES (?,?,?)', (f'm{k}', json.dumps({'status': status, 'report_id': report.get('report_id')}), '2026-10-03T23:00:00+00:00'))
    db.close()
    return path


def test_the_laboratory_projection_reads_only_a_stored_report_and_refuses_anything_else(tmp_path):
    research = tmp_path / 'firm_lab.db'
    assert modeling_view.summary(research) == {'exists': False, 'warning': modeling.WARNING, 'missing_reason': 'NO_STORED_LABORATORY_RUN', 'report': None, 'models': 0}
    path = _lab_file(tmp_path, _report())
    before = path.read_bytes()
    state = modeling_view.summary(research)
    assert state['exists'] and state['models'] == 2 and state['registry_statuses'] == {'EXPERIMENTAL': 1, 'REJECTED': 1} and state['report']['plan_version']
    assert path.read_bytes() == before                                                             # read-only: nothing is written by looking
    path.unlink()
    _lab_file(tmp_path, _report(), statuses=('EXPERIMENTAL', 'PRODUCTION'))
    assert modeling_view.summary(research)['missing_reason'] == 'UNEXPECTED_MODEL_STATUS'           # a status this laboratory cannot give is never shown
    path.unlink()
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE firm_meta (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)')
    db.executemany('INSERT INTO firm_meta VALUES (?,?,?)', [('mode', 'BUILD_OBSERVE', ''), ('database_role', 'CHECKPOINT7_MODELING_RESEARCH', '')])
    db.execute('CREATE TABLE fills (id INTEGER)')
    db.commit()
    db.close()
    assert modeling_view.summary(research)['missing_reason'] == 'NOT_A_MODELING_DATABASE'           # a file with an execution table is not read


def test_the_page_shows_research_measurements_with_provenance_and_no_instruction(tmp_path):
    nothing = modeling_lab.render_modeling({'modeling': modeling_view.empty()})
    assert modeling.WARNING in nothing and 'No laboratory run is stored on this machine' in nothing
    assert modeling.WARNING in modeling_lab.render_modeling({}) and modeling.WARNING in modeling_lab.render_modeling(None)
    _lab_file(tmp_path, _report())
    html = modeling_lab.render_modeling({'modeling': modeling_view.summary(tmp_path / 'firm_lab.db')})
    assert html.count(modeling.WARNING) == 1 and html.startswith('<p class="fl-stamp">MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE</p>')
    assert html.index('No validated trading model exists.') < html.index('Highest development scores') < html.index('Feature-family ablation')      # the conclusion comes before any score
    for text in ('SESSION_TIME_RETROSPECTIVE', 'Strict point-in-time samples', '<b>0</b> under the strict known-at rule', 'FIBONACCI ADDS INCREMENTAL OOS VALUE = INCONCLUSIVE',
                 'expanding-walk-forward-purged-v1', '20 sessions before every predicted block', 'final_holdout', 'Strongest naive baseline on development sessions',
                 'EXPERIMENTAL_INSUFFICIENT_DATA', 'dependency unavailable: catboost', 'Feature-family ablation', 'technical+fibonacci', 'Specialist models and combinations',
                 'Neural models: is there enough data?', 'Return distribution', 'Calibration', 'Model disagreement', 'Uncertainty', 'Meta-label research',
                 'Results by factual context', 'Prediction examples — research only', 'RESEARCH ONLY — NOT A RECOMMENDATION', 'checkpoint7-tournament-plan-v2',
                 'It is not a selection for use', 'Not net strategy P&amp;L',
                 # what the operator asked the page to say first
                 'No validated trading model exists.', 'Strict point-in-time samples: 0.', 'All 6,468 samples are retrospective',
                 'This cannot establish a genuine historical point-in-time trading edge', 'Deep learning and transformers: insufficient data.',
                 'The current holdout is no longer an untouched final test set for future model selection.',
                 'Future model research needs a newly accumulated or separately reserved untouched evaluation period.',
                 'research measurements, not recommended models', 'None of the rows below is a validated or recommended trading model.',
                 # what the review asked the page to show
                 '131 development, 59 holdout', 'development: 26 of 5 sessions, 13 of 10, 6 of 20; holdout: 11, 5, 2', 'Non-overlapping is not the same as independent',
                 '6 batches', 'ranked 104 of 131 sessions', 'highest of 25 compared', 'What a research status means', 'Student t on the means of consecutive batches',
                 'family sizes: excess_return_10 54', 'Which rows: the six rows of the last holdout session', 'a description, not a signal',
                 'compared with historical_mean', 'eeeeeeeeeeeeeeee — repairs after the independent review', '159 encoded as numbers, 140 of them offered to a model'):
        assert text in html, text
    # provenance: dataset, feature calculation and code hashes, and the feature snapshot behind an example
    assert '<code>dddddddddddddddd</code>' in html and '<code>ffffffffffffffff</code>' in html and '<code>cccccccccccccccc</code>' in html and '<code>aaaaaaaaaaaaaaaa</code>' in html
    # one neutral style for every research status; nothing green or red says what to do
    assert set(re.findall(r'<span class="cat cat-(\w+)">(?:EXPERIMENTAL|CHALLENGER|REJECTED|ELIGIBLE_FOR_FUTURE_REVIEW|NOT RUN|EXPERIMENTAL_INSUFFICIENT_DATA)', html)) == {'neutral'}
    best_row = html.split('10-session excess return</td>')[1].split('</tr>')[0]
    assert 'mlp_sequence_features' in best_row and 'EXPERIMENTAL_INSUFFICIENT_DATA' in best_row and '+0.0030' in best_row      # a highest score is never shown without its gate label and its holdout
    assert 'cat-good' not in html and 'cat-stop' not in html and 'cat-warn' not in html
    words = re.sub(r'<[^>]+>', ' ', html)
    for word in ACTION_WORDS:
        assert not re.search(r'\b' + word + r'\b', words), word                                     # as a label, in capitals
    lowered = words.lower().replace('none has a production or live status', '')                    # the one sentence that says there is no such status
    for phrase in ('strong buy', 'conviction', 'buy ', 'sell ', 'we recommend', 'should buy', 'should sell', 'target price', 'position size', 'take profit', 'stop loss',
                   'production', 'deployed', 'promoted', 'trial 18'):
        assert phrase not in lowered, phrase
    assert '<form' not in html and '<button' not in html and '<input' not in html and '<script' not in html and 'style=' not in html
    # the whole Firm Lab page carries the section, and still says what it always said
    state = {'firm_lab': {'exists': False, 'mode': 'BUILD_OBSERVE', 'fills': 0, 'firm_trading_trial': 'NOT REGISTERED', 'modeling': modeling_view.summary(tmp_path / 'firm_lab.db')}}
    page = firm_lab_page.render(state)
    assert '<section class="v10-panel" id="fl-modeling"><h2>Modeling Laboratory</h2>' in page and modeling.WARNING in page
    assert 'Firm fills</dt><dd><b>0</b>' in page and 'Firm trading trial</dt><dd><b>NOT REGISTERED</b>' in page
    old = firm_lab_page.render({'firm_lab': {'exists': False, 'mode': 'BUILD_OBSERVE', 'fills': 0}})
    assert 'No laboratory run is stored on this machine' in old                                     # a machine without the laboratory file still renders


def test_research_only_capabilities_are_never_available_to_a_strategy(tmp_path):
    from firm_lab.errors import CapabilityUnavailable, FirmLabError
    from firm_lab.modeling_capability import ROWS, record
    from firm_lab.store import FirmLabStore
    lab = FirmLabStore(tmp_path / 'diag' / 'firm_lab' / 'firm_lab.db')
    capabilities.seed(lab)
    before = {c['capability']: c['status'] for c in lab.capabilities()}
    report = _report()
    report['sufficiency']['mlp/excess_return_10'] = {'label': 'EXPERIMENTAL_INSUFFICIENT_DATA', 'sufficient': False}
    written = record(lab, report, models=57)
    status = {c['capability']: c['status'] for c in lab.capabilities()}
    assert written == {'research_modeling': 'RESEARCH_ONLY', 'ml_ranker': 'RESEARCH_ONLY', 'deep_learning': 'RESEARCH_ONLY', 'transformer_models': 'RESEARCH_ONLY',
                       'macro_regime': 'NOT_STARTED', 'portfolio_optimizer': 'NOT_STARTED', 'options_strategy': 'NOT_STARTED', 'rl_policy': 'NOT_STARTED'}
    assert all(status[name] == state for name, state in written.items()) and set(ROWS) == set(written)
    assert {k: status[k] for k in before if k not in written} == {k: v for k, v in before.items() if k not in written}      # nothing else moved
    details = {c['capability']: c['detail'] for c in lab.capabilities()}
    assert 'no production or live status' in details['ml_ranker'] and 'EXPERIMENTAL_INSUFFICIENT_DATA' in details['deep_learning']
    assert 'INCONCLUSIVE' in details['research_modeling'] and 'retrospective' in details['research_modeling'].lower()
    assert 'No validated trading model exists' in details['research_modeling'] and 'no longer an untouched test set' in details['research_modeling']
    for name in ('research_modeling', 'ml_ranker', 'deep_learning', 'transformer_models'):
        with pytest.raises(CapabilityUnavailable):
            capabilities.require(lab, name)                                                         # research-only is not "available" to anything
    with pytest.raises(FirmLabError):
        capabilities.set_status(lab, 'ml_ranker', 'PRODUCTION')
    assert lab.mode() == 'BUILD_OBSERVE' and not lab.active_experiments()
