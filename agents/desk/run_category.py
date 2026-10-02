"""Categorize every recorded run so real experiment runs stand apart from build-phase ones.

Rules use recorded fields only (trigger, data mode, terminal status, recovery or
temporary-budget markers) plus the registered milestone: v1.5 took effect at
2026-10-01 09:30 ET. Runs before that were made while the system was being built
and never count toward results.
"""
from datetime import datetime

OFFICIAL_FROM = datetime.fromisoformat('2026-10-01T09:30:00-04:00')


def categorize(review, meta=None):
    meta = meta or {}
    tags = []
    try:
        when = datetime.fromisoformat(review.get('timestamp') or '')
        when = when if when.tzinfo else None
    except ValueError:
        when = None
    trigger = meta.get('trigger') or review.get('trigger')
    mode = review.get('data_mode')
    status = (review.get('status') or '').upper()
    build = when is None or when < OFFICIAL_FROM
    tags.append(('Build phase', 'build', 'Before v1.5 took effect (Oct 1, 9:30 AM ET). The system was still being built; never counted.')
                if build else ('Registered paper run', 'neutral', 'Scheduled paper run under the registered rules in force (v1.5 entry and exit rules, v1.6 capital and protective check). Registered describes the process, not the quality of the result.'))
    if mode == 'fixture':
        tags.append(('Test data', 'warn', 'Fixture data, not live market data.'))
    elif mode == 'whatif':
        tags.append(('Rehearsal', 'warn', 'What-if rehearsal in a disposable copy.'))
    if meta.get('recovery_of') or trigger == 'manual':
        tags.append(('Manual re-run', 'warn', 'Started by hand' + (' to recover an earlier attempt.' if meta.get('recovery_of') else '.')))
    elif trigger == 'scheduled':
        tags.append(('Scheduled', 'neutral', 'Started by the 10:00 AM ET schedule.'))
    if meta.get('temporary_api_budget_usd'):
        tags.append(('Budget override', 'warn', f"Temporary AI budget ${meta['temporary_api_budget_usd']} for this run."))
    if status == 'COMPLETED' and not review.get('record_incomplete'):
        tags.append(('Completed', 'good', 'Recorded a final outcome.'))
    elif status.startswith('NOT_ISSUED') or status.startswith('FAILED'):
        tags.append(('Interrupted', 'stop', f'Ended early: {status.replace("_", " ").lower()}.'))
    else:
        tags.append(('Unconfirmed', 'stop', 'No complete final record.'))
    counts = (not build and trigger == 'scheduled' and mode == 'live_readonly' and status == 'COMPLETED'
              and not meta.get('recovery_of') and not meta.get('temporary_api_budget_usd'))
    return {'tags': [{'label': l, 'tone': t, 'title': d} for l, t, d in tags], 'counts': counts,
            'group': 'official' if not build else 'build',
            'counts_reason': 'Counts toward the experiment' if counts else
            ('Build phase: does not count' if build else 'Does not count: not a clean scheduled live run')}
