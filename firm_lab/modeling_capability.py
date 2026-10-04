"""Capability rows for the modeling laboratory. Research-specific states only. Standard library only.

RESEARCH_ONLY means: offline research evidence exists. It is never AVAILABLE to a strategy, and ``capabilities.require``
refuses it. Nothing here marks a model live or in production; no such state exists.
"""
from __future__ import annotations

from .capabilities import NOT_STARTED, RESEARCH_ONLY, set_status

ROWS = ('research_modeling', 'ml_ranker', 'deep_learning', 'transformer_models', 'macro_regime', 'portfolio_optimizer', 'options_strategy', 'rl_policy')


def _best(report, key):
    """One highest-development-score row, always with its holdout number, its status and (for a network) its gate label."""
    best = (report.get('best_research_models') or {}).get(key) or {}
    ic, holdout = best.get('dev_mean_ic'), best.get('holdout_mean_ic')
    if not isinstance(ic, (int, float)):
        return 'none'
    gate = f', {best["sufficiency"]}' if best.get('sufficiency') not in (None, 'sufficient') else ''
    after = f'{holdout:+.3f}' if isinstance(holdout, (int, float)) else 'not measured'
    return (f'{best.get("name", "none")} (development rank correlation {ic:+.3f}, holdout {after}, research status {best.get("status")}{gate}; '
            f'the highest of {best.get("highest_of", "several")} compared, so biased upward)')


def record(store, report, *, models, now=None) -> dict:
    """Writes the eight rows from a stored laboratory report. Returns {capability: status}."""
    data, fib = report['dataset'], report['ablation']['fibonacci']
    windows = data['evaluation_windows']
    gates = report.get('sufficiency') or {}
    failed = sorted(k for k, v in gates.items() if v.get('label') != 'sufficient')
    networks = (f'{len(gates)} network configurations were run under {report["plan_version"]}; {len(failed)} failed the data-sufficiency gate and are '
                'labelled EXPERIMENTAL_INSUFFICIENT_DATA. None can be a challenger. Offline research only.')
    transformers = sorted(k for k in gates if 'transformer' in k)
    rows = {
        'research_modeling': (RESEARCH_ONLY, 'Firm Lab modeling laboratory',
                              f'{models} research models evaluated under {report["plan_version"]} on {data["usable_samples"]:,} retrospective samples '
                              f'({data["usable_sessions"]} sessions; {windows["development"]["non_overlapping_windows"].get("10")} development and '
                              f'{windows["holdout"]["non_overlapping_windows"].get("10")} holdout non-overlapping 10-session windows are predicted; '
                              f'{data.get("strict_point_in_time_samples")} strict point-in-time samples). '
                              f'Purged walk-forward with a final holdout. {fib["statement"]}. No validated trading model exists. '
                              + ('The holdout was read by more than one run and is no longer an untouched test set for future model selection. ' if report.get('supersedes') else '')
                              + 'No model is in use and no output reaches a trading path.'),
        'ml_ranker': (RESEARCH_ONLY, 'Firm Lab modeling laboratory',
                      'Rank models were evaluated offline. Highest development score on the 10-session target: ' + _best(report, 'best_10d')
                      + '; strongest advanced candidate: ' + _best(report, 'strongest_advanced_candidate')
                      + '. There is no production or live status, nothing is promoted, and no ranker feeds a selection.'),
        'deep_learning': (RESEARCH_ONLY, 'Firm Lab modeling laboratory', networks),
        'transformer_models': (RESEARCH_ONLY, 'Firm Lab modeling laboratory',
                               f'A compact encoder-only transformer was run ({len(transformers)} configurations): '
                               + ('EXPERIMENTAL_INSUFFICIENT_DATA' if any(gates[k].get('label') != 'sufficient' for k in transformers) or not transformers else 'passed the gate')
                               + '. Offline research only; it must beat simpler models robustly before any further consideration.'),
        'macro_regime': (NOT_STARTED, None, 'Not built. No macro regime, classifier or score exists; conditional research views use directly observed facts only.'),
        'portfolio_optimizer': (NOT_STARTED, None, 'Not built. No prediction is turned into a position size, an allocation or a limit.'),
        'options_strategy': (NOT_STARTED, None, 'No option recommendation, scenario engine or matched book exists. No shares-versus-options model was trained.'),
        'rl_policy': (NOT_STARTED, None, 'Not started. Documented only as a later research track for sequential decisions, after forecast models and a simulator exist.'),
    }
    for name, (status, provider, detail) in rows.items():
        set_status(store, name, status, provider, detail, now, reason='Checkpoint 7 modeling laboratory')
    return {name: status for name, (status, _, _) in rows.items()}
