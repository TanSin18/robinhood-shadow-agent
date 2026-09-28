from agents.desk.router import render


def state():
    return {'preview': True, 'cards': [], 'decision_room': [
        {'review_id': 'latest', 'timestamp': '2026-09-28T14:20:00+00:00',
         'status': 'completed', 'proposal_state': 'none', 'selection_recorded': False,
         'outcome': {'reason': 'No picks. Quotes are stale.'},
         'stages': [
             {'key': 'research', 'status': 'completed', 'status_label': 'Completed',
              'summary': '<b>Untrusted research</b>',
              'inspector': {'blockers': ['News collection disabled'], 'sources': ['Not recorded']}},
             {'key': 'risk', 'status': 'not_applicable', 'status_label': 'Not needed',
              'summary': 'No proposal entered risk checks.', 'inspector': {}}],
         'lanes': {'A': [], 'B': []}},
        {'review_id': 'older', 'stages': [], 'outcome': {'reason': 'Older review'}}]}


def test_preview_opens_one_connected_review_with_reports_closed():
    html = render('/', state(), None, '')
    assert 'Your team' in html
    assert 'data-team-flow' in html
    assert 'Expected workflow' in html
    assert 'Review finished. No trade proposed.' in html
    assert 'News was not collected' not in html
    assert 'Original report' in html
    assert '<details open' not in html
    assert 'Show evidence' in html
    assert '<b>Untrusted research</b>' not in html
    assert '&lt;b&gt;Untrusted research&lt;/b&gt;' in html
    assert '<form' not in html
    assert 'data-review="1" hidden' in html


def test_incomplete_review_does_not_claim_hold_or_live_progress():
    html = render('/', {'preview': True, 'cards': [], 'decision_room': [
        {'review_id': 'incomplete', 'stages': [], 'outcome': {}, 'proposal_state': 'unknown'}]}, None, '')
    assert 'Outcome not confirmed' in html
    assert 'Review finished. No trade proposed.' not in html
    assert 'Live now' not in html


def test_candidate_details_are_clickable_and_escaped():
    data = state()
    data['decision_room'][0]['selection_recorded'] = True
    data['decision_room'][0]['lanes']['A'] = [
        {'instrument': 'VTI', 'state': 'risk_blocked', 'reason': '<script>bad()</script>'}]
    html = render('/room', data, None, '')
    assert 'VTI' in html and 'Original report' in html
    assert '<script>bad()</script>' not in html


def test_no_records_are_not_presented_as_a_success():
    html = render('/', {'preview': True, 'cards': [], 'decision_room': []}, None, '')
    assert 'No saved review yet' in html
    assert 'Review finished' not in html
