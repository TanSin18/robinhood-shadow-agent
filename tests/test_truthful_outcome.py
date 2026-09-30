"""Regression: 2026-09-29 official run proposed SOXX and the Critic rejected it.

The Agent Desk previously said "Review finished. No trade proposed." and
"Did not propose a trade." Both contradict the saved record.
"""
from agents.decision_room import project_decision_room
from agents.desk.workspace import outcome, review_view


def _records(critic_rejected=('SOXX',), result_status='REJECTED'):
    return [
        {'trace_id': 'sep29', 'event': 'cycle_started', 'timestamp': '2026-09-29T14:00:08+00:00'},
        {'trace_id': 'sep29', 'event': 'cycle_terminal', 'timestamp': '2026-09-29T14:01:29+00:00',
         'payload': {
             'status': 'COMPLETED',
             'decision': {'picks': [{'instrument': 'SOXX', 'side': 'buy'}],
                          'reason': 'Lane A: choosing SOXX.'},
             'critic': {'counterargument': 'Reject SOXX despite a matching signal: the record does not prove '
                                           'the trade is executable within a $500 lane. More detail follows.',
                        'rejected_instruments': list(critic_rejected)},
             'results': [{'status': result_status, 'instrument': 'SOXX'}],
         }},
    ]


def test_critic_rejection_is_projected_as_stopped_not_no_proposal():
    review = project_decision_room(_records(), [])[0]
    assert review['proposal_state'] == 'stopped'
    assert review['stopped_by'] == 'critic'
    assert review['stopped_instruments'] == ['SOXX']
    assert review['header']['outcome'] == 'Proposal rejected by Critic'
    stages = {s['key']: s for s in review['stages']}
    assert stages['portfolio']['status_label'] == 'Proposed'
    assert stages['critic']['status_label'] == 'Rejected'
    assert stages['risk']['status_label'] == 'Not reached'


def test_headline_and_cards_never_claim_no_proposal_when_picks_exist():
    review = project_decision_room(_records(), [])[0]
    heading = outcome(review)
    assert 'SOXX' in heading and 'rejected' in heading
    html = review_view(review, 0)
    assert 'No trade proposed' not in html
    assert 'Did not propose a trade' not in html
    assert 'Proposed SOXX.' in html
    assert 'Rejected SOXX' in html
    # Critic reason is quoted verbatim (first sentence only), labelled as original report.
    assert 'original report' in html
    assert 'executable within a $500 lane.' in html
    assert 'More detail follows' not in html


def test_rejection_not_attributed_to_critic_without_structured_evidence():
    # Critic did not list SOXX: do not invent a Critic veto.
    review = project_decision_room(_records(critic_rejected=()), [])[0]
    assert review['proposal_state'] != 'stopped'
    assert review['stopped_by'] is None


def test_zero_pick_hold_cash_is_unchanged():
    records = [{'trace_id': 'q', 'event': 'cycle_terminal', 'timestamp': '2026-09-29T14:01:29+00:00',
                'payload': {'status': 'COMPLETED', 'decision': {'picks': []}, 'results': []}}]
    review = project_decision_room(records, [])[0]
    assert review['proposal_state'] == 'none'
    assert outcome(review) == 'Review finished. No trade proposed.'
