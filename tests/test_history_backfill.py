from datetime import date, datetime, timedelta, timezone

import pytest

from research.history_backfill import BackfillError, HistoryStore, backfill, export, windows


def _bars(start, end):
    day, out = start, []
    while day < end:
        out.append({'begins_at': f'{day.isoformat()}T13:30:00Z', 'open_price': '10', 'close_price': '11', 'volume': '5'})
        day += timedelta(days=1)
    return out


def test_walks_back_until_empty_and_respects_gateway_bound(tmp_path):
    now = datetime(2026, 9, 30, 21, tzinfo=timezone.utc)
    seen = []

    def call(tool, args):
        start, end = (datetime.fromisoformat(args[k]) for k in ('start_time', 'end_time'))
        assert tool == 'get_equity_historicals' and end - start <= timedelta(days=550) and end <= now
        seen.append(start)
        if start.date() < date(2022, 1, 1):
            return {'data': {'results': [{'symbol': 'SPY', 'bars': []}]}}
        return {'data': {'results': [{'symbol': 'SPY', 'bars': _bars(start.date(), end.date())}]}}

    store = HistoryStore(tmp_path / 'h' / 'history.db', tmp_path / 'official' / 'agent.db')
    result = backfill(call, ['SPY'], store, now, floor=date(2005, 1, 1))
    assert result['stopped'] is None and result['symbols']['SPY']['first_day'] >= '2022-01-01'
    assert all(a > b for a, b in zip(seen, seen[1:]))
    sha = export(store, tmp_path / 'h' / 'bars.csv')
    assert len(sha) == 64 and '2026-09-30' not in (tmp_path / 'h' / 'bars.csv').read_text()


def test_stops_on_first_provider_error(tmp_path):
    def call(tool, args):
        raise RuntimeError('provider down')
    store = HistoryStore(tmp_path / 'h' / 'history.db')
    result = backfill(call, ['SPY', 'QQQ'], store, datetime(2026, 9, 30, tzinfo=timezone.utc))
    assert result['calls'] == 1 and result['stopped'] == 'PROVIDER_ERROR:RuntimeError'


def test_store_must_not_share_official_directory(tmp_path):
    with pytest.raises(BackfillError):
        HistoryStore(tmp_path / 'history.db', tmp_path / 'agent.db')


def test_windows_reach_floor():
    ws = list(windows(datetime(2026, 9, 30, tzinfo=timezone.utc), date(2020, 1, 1)))
    assert ws[-1][0].date() == date(2020, 1, 1) and all(e - s <= timedelta(days=550) for s, e in ws)
