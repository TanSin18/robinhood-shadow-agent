from agents.desk.run_category import categorize
from agents.desk.router import render


def review(ts, status='completed', mode='live_readonly'):
    return {'review_id': 'r', 'timestamp': ts, 'status': status, 'data_mode': mode, 'stages': [], 'header': {}}


def test_build_phase_runs_never_count_and_are_labelled():
    c = categorize(review('2026-09-30T14:00:47+00:00'), {'trigger': 'scheduled'})
    assert c['group'] == 'build' and c['counts'] is False
    assert [t['label'] for t in c['tags']] == ['Build phase', 'Scheduled', 'Completed']
    m = categorize(review('2026-09-28T14:20:17+00:00'), {'trigger': 'manual', 'recovery_of': 'x', 'temporary_api_budget_usd': '5'})
    assert {'Manual re-run', 'Budget override'} <= {t['label'] for t in m['tags']}
    i = categorize(review('2026-09-28T14:02:21+00:00', status='not_issued_budget'), {'trigger': 'scheduled'})
    assert 'Interrupted' in {t['label'] for t in i['tags']}


def test_official_scheduled_completed_run_counts():
    c = categorize(review('2026-10-01T14:01:00+00:00'), {'trigger': 'scheduled'})
    assert c['group'] == 'official' and c['counts'] is True and c['tags'][0]['label'] == 'Official · v1.5'
    assert categorize(review('2026-10-01T14:01:00+00:00'), {'trigger': 'manual'})['counts'] is False


def test_pages_show_categories():
    r = {**review('2026-09-30T14:00:47+00:00'), 'category': categorize(review('2026-09-30T14:00:47+00:00'), {'trigger': 'scheduled'})}
    for path in ('/room', '/checks', '/'):
        html = render(path, {'preview': True, 'decision_room': [r]}, None, '')
        assert 'Build phase' in html and 'style=' not in html
    assert '[Build]' in render('/room', {'preview': True, 'decision_room': [r]}, None, '')


def test_desk_exit_headline():
    from agents.desk.workspace import outcome
    r = {'desk_exits': [{'instrument': 'SOXX', 'status': 'filled', 'exit_reason': 'MOMENTUM_126D_NOT_POSITIVE'},
                        {'instrument': 'SOXX', 'status': 'PENDING', 'exit_reason': 'MOMENTUM_126D_NOT_POSITIVE'}]}
    assert outcome(r) == 'Desk rule (no AI) sold SOXX because its 126-day momentum turned negative. Your SELL card is waiting.'
