"""Presentation contracts independent of broker and database dependencies."""
from agents.desk.components import shell, ROUTES
from agents.desk.today import render
from agents.desk.decision_room import render as room
from agents.desk.router import render as page
from pathlib import Path


def test_seven_routes_are_readable_without_script_and_safety_is_explicit():
    page = shell('Today', '<p>Recorded content</p>', '/', {'paused': True})
    assert len(ROUTES) == 14
    for path, label in ROUTES:
        assert f'href="{path}"' in page
        assert label in page
    assert 'Safety stop or pause active' in page
    assert 'style=' not in page and '<script>' not in page
    assert 'Recorded content' in page


def test_missing_today_data_never_becomes_zero_or_official():
    page = render({'history': [], 'cards': []}, None, 'token')
    assert 'Not recorded' in page and 'Not tracked yet' in page
    assert '$0' not in page
    assert 'Ask the Explainer' not in page


def test_historical_room_exposes_all_stages_without_js_and_escapes_records():
    stages = [{'key': key, 'label': key, 'summary': '<script>bad()</script>',
               'status_label': 'Not recorded', 'inspector': {}}
              for key in ('evidence', 'research', 'portfolio', 'critic', 'risk', 'final')]
    page = room({'decision_room': [{'review_id': 'old', 'stages': stages,
                                  'outcome': {'reason': 'Saved reason'}}]})
    assert 'This run predates idea-by-idea records.' in page
    assert ' hidden' not in page
    assert '<script>bad()' not in page
    assert '&lt;script&gt;' in page
    assert 'Rules, not AI' in page
    assert 'Not active yet' in page
    assert 'Talk' not in page


def test_all_seven_pages_have_server_rendered_content():
    for path, title in ROUTES:
        result = page(path, {'history': [], 'cards': []}, None, 'token')
        assert f'<h1>{title}</h1>' in result
        assert ' hidden' not in result
        assert 'style=' not in result


def test_self_hosted_fonts_and_original_avatars_exist():
    assets = Path(__file__).resolve().parents[1] / 'agents' / 'static'
    for name in ('Geist', 'GeistMono'):
        assert (assets / 'fonts' / (name+'.woff2')).read_bytes()[:4] == b'wOF2'
    assert len(list((assets / 'avatars').glob('*.svg'))) == 6


def test_incident_cannot_show_green_safety_status_when_pause_flag_false():
    result = shell('Today', '', state={'paused': False, 'tripwire': [{'incident_id': 'incident'}]})
    assert 'Safety stop or pause active' in result


def test_guide_walks_through_every_step_and_needs_no_records():
    from agents.desk.router import render
    from agents.desk import guide_content as C
    html = render('/guide', {'preview': True}, None, '')
    for step in C.STEPS:
        assert f'id="step-{step["id"]}"' in html
    for key, *_ in C.FLOW:
        assert f'href="#step-{key}"' in html
    assert '/assets/guide.css' in html and '/assets/guide.js' in html
    assert ' style=' not in html and '<script>' not in html   # strict CSP: no inline style or script


def test_capital_note_follows_the_ledger():
    from agents.desk.components import capital_note
    before = {'portfolio': {'paper': [{'lane': 'A', 'track': 'agent_alone', 'start': '500'}]}, 'research': {'rebase': None}}
    after = {'portfolio': {'paper': [{'lane': 'A', 'track': 'agent_alone', 'start': '25000.00', 'capital_version': '1.6.0'}]},
             'research': {'rebase': {'timestamp': '2026-10-01T14:00:05+00:00', 'capital': '25000.00', 'lane': 'A'}}}
    assert 'becomes <strong>$25,000 per account</strong>' in capital_note(before) and 'is-scheduled' in capital_note(before)
    assert 'is-live' in capital_note(after) and '$25,000 per account under v1.6, since 2026-10-01 14:00 UTC' in capital_note(after)
