from datetime import datetime,timezone
from test_inbox_lanes import setup_runtime

def test_dashboard_keeps_catchup_window_visible(tmp_path):
    from agents.dashboard import dashboard_snapshot
    inbox,_=setup_runtime(tmp_path)
    state=dashboard_snapshot(inbox,datetime(2026,9,28,14,10,tzinfo=timezone.utc))
    assert state['today_status']=='WAITING'
    assert state['next_run'].startswith('2026-09-28')

def test_weekly_cost_dates_are_eastern(tmp_path):
    from eval.weekly import report_if_due
    inbox,_=setup_runtime(tmp_path)
    inbox.store.append_json('api_costs',{'timestamp':'2026-10-03T00:30:00+00:00','cost_usd':'0.123'})
    report=report_if_due(inbox,datetime(2026,10,3,1,tzinfo=timezone.utc),tmp_path/'reports')
    assert '$0.123000' in report.read_text()
