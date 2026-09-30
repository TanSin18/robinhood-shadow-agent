from datetime import datetime, timezone
from agents.desk.clock import render_clock


class FakeSchedule:
    def __init__(self, session=True, close_hour=16):
        self.session, self.close_hour = session, close_hour
    def _session(self, local):
        return 'S' if self.session else None
    def session_close(self, local):
        return local.replace(hour=self.close_hour, minute=0, second=0, microsecond=0)


def test_edt_regular_day_shows_registered_steps_and_now():
    now = datetime(2026, 9, 30, 14, 26, tzinfo=timezone.utc)  # 10:26 EDT
    html = render_clock(now, FakeSchedule())
    for text in ('Health check', 'Market opens', 'Team meeting', 'No new buys', 'Close sweep', 'Market closes', 'Daily summary'):
        assert text in html
    assert 'EDT' in html and '10:26a' in html and 'market open' in html
    assert '3:30p' in html and '3:50p' in html and '4:00p' in html
    assert 'style=' not in html and '<script' not in html  # strict CSP


def test_est_after_dst_ends_uses_zoneinfo_not_fixed_offset():
    now = datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)  # 10:00 EST
    html = render_clock(now, FakeSchedule())
    assert 'EST' in html and '10:00a' in html


def test_early_close_shifts_cutoff_sweep_and_close():
    now = datetime(2026, 11, 27, 16, 0, tzinfo=timezone.utc)  # 11:00 EST, 13:00 close
    html = render_clock(now, FakeSchedule(close_hour=13))
    assert '12:30p' in html and '12:50p' in html and '1:00p' in html and 'early close' in html
    assert '3:30p' not in html


def test_no_session_and_unknown_calendar_are_honest():
    now = datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc)
    assert 'No US market session today' in render_clock(now, FakeSchedule(session=False))
    class Broken:
        def _session(self, local): raise RuntimeError('calendar down')
    assert 'unknown' in render_clock(now, Broken())
