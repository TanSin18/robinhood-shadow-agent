from agents.desk.router import render


def test_lane_guide_never_claims_unrecorded_checks_passed():
    html = render('/portfolio', {'preview': True}, None, '')
    assert 'Shares &amp; ETFs' in html
    assert 'Defined-risk options' in html
    assert 'Not recorded' in html
    assert 'No result loaded' in html
    assert 'data-lane-view="guide"' in html
    assert 'data-lane-view="record"' in html
    assert 'All checks passed' not in html


def test_recorded_review_preserves_scope_and_escapes_prose():
    html = render('/portfolio', {'preview': True, 'decision_room': [{
        'timestamp': '2026-09-28T14:20:00+00:00',
        'stages': [{'key': 'risk', 'status_label': 'Not needed',
                    'summary': '<script>unsafe</script>', 'inspector': {}}],
        'lanes': {'A': [{'instrument': 'VTI', 'state': 'risk_blocked', 'reason': 'Cash check'}]},
        'selection_recorded': True}]}, None, '')
    assert 'Not needed' in html
    assert '&lt;script&gt;unsafe&lt;/script&gt;' in html
    assert '<script>unsafe</script>' not in html
    assert 'Shared review record' in html
    assert 'VTI' in html and 'Cash check' in html


def test_guide_stays_out_of_operational_dashboard():
    assert 'data-lane-view' not in render('/portfolio', {}, None, '')
