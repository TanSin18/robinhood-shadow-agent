from agents.desk.research import render


def test_missing_research_never_claims_an_edge():
    html = render({})
    assert 'Not run yet' in html and 'No check recorded yet' in html and 'No night recorded yet' in html
    assert 'Installs with' in render({'promotion': {'unavailable': 'ModuleNotFoundError'}})


def test_research_panel_renders_recorded_values_escaped():
    html = render({
        'backtest': {'verdict': ['x', 'NOT PROVEN: <b>no</b>'], 'summary': {'vti_buy_hold': {'cagr_after_all_tax': 0.08, 'sharpe_rf0': 0.6,
                     'max_drawdown': 0.5, 'trades': 1}}, 'excess_vs_vti': {'signal_full_invest_top1': {'ci90': [-0.02, 0.03]}},
                     'data': {'first_session': '2008-01-02', 'last_session': '2026-09-29'}},
        'promotion': {'rule': 'r', 'arms': {'deterministic_no_ai': {'sessions': 3, 'decisions': 1, 'annual_excess': None, 'ci90': None,
                                                                    'verdict': 'NOT_PROVEN'}}},
        'protective': [{'timestamp': '2026-10-01T19:50:00+00:00', 'status': 'CHECKED', 'fired': 0, 'held': ['SOXX']}],
        'rebase': {'timestamp': '2026-10-01T14:00:00+00:00', 'capital': '25000.00', 'lane': 'A'},
        'screen': {'at': '2026-10-01T20:55:00+00:00', 'status': 'COMPLETED', 'funnel': {'universe': 520, 'shortlist': 12}, 'shortlist': ['AAA']},
    })
    assert '&lt;b&gt;no&lt;/b&gt;' in html and '+8.0%' in html and '-2.0% to +3.0%' in html
    assert 'Rules only (no AI)' in html and 'SOXX' in html and '$25000.00' in html and 'AAA' in html
