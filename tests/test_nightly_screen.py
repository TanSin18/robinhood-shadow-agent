from datetime import datetime, timezone
from pathlib import Path

from agents.nightly_screen import run_nightly
from test_inbox_lanes import setup_runtime

NOW = datetime(2026, 10, 1, 20, 50, tzinfo=timezone.utc)


def _runner(**kw):
    assert kw['store_path'].parent.name == 'store'
    return {'status': 'COMPLETED', 'universe_file_sha256': 'x', 'funnel': {'universe': 520}, 'collection': {'calls': 1},
            'shortlist': [{'symbol': 'AAA'}], 'as_of_session': '2026-10-01'}


def test_skips_non_trading_day(tmp_path):
    inbox, config = setup_runtime(tmp_path)
    out = run_nightly(config=config, official=inbox.path, directory=tmp_path / 'u', now=NOW, trading_day=False)
    assert out['status'] == 'SKIPPED_NOT_A_TRADING_DAY'


def test_no_universe_and_failed_download_stops_cleanly(tmp_path):
    inbox, config = setup_runtime(tmp_path)
    def fail(url, dest):
        raise OSError('offline')
    out = run_nightly(config=config, official=inbox.path, directory=tmp_path / 'u', now=NOW, trading_day=True,
                      download=fail, runner=_runner)
    assert out['status'] == 'NO_UNIVERSE_FILE' and out['universe_refresh_error'] == 'OSError'


def test_uses_fresh_universe_without_download(tmp_path):
    inbox, config = setup_runtime(tmp_path)
    d = tmp_path / 'u'; d.mkdir()
    (d / 'sp500-2026-09-30.json').write_text('{}')
    def never(url, dest):
        raise AssertionError('no download needed')
    out = run_nightly(config=config, official=inbox.path, directory=d, now=NOW, trading_day=True, download=never, runner=_runner)
    assert out['status'] == 'COMPLETED' and out['shortlist'] == ['AAA'] and out['universe_file'] == 'sp500-2026-09-30.json'


def test_safety_stop_skips(tmp_path):
    inbox, config = setup_runtime(tmp_path)
    (Path(inbox.path).parent / 'STOP_TRADING').write_text('')
    out = run_nightly(config=config, official=inbox.path, directory=tmp_path / 'u', now=NOW, trading_day=True, runner=_runner)
    assert out['status'] == 'SKIPPED_SAFETY_STOP_OR_PAUSE'


def test_deterministic_arm_settles_t_plus_one(tmp_path):
    import json
    from agents.maintenance import run_once
    inbox, _ = setup_runtime(tmp_path)
    with inbox.connect() as db:
        state = inbox.state('A', 'deterministic_no_ai', db)
        state.update(settled_cash='400', unsettled_cash='100', settlements=[{'amount': '100', 'due': '2026-09-29'}])
        db.execute("UPDATE paper_accounts SET payload=? WHERE lane='A' AND track='deterministic_no_ai'", (json.dumps(state),))
    run_once(inbox, datetime(2026, 9, 29, 18, tzinfo=timezone.utc), tmp_path)
    after = inbox.state('A', 'deterministic_no_ai')
    assert after['settled_cash'] == '500' and after['unsettled_cash'] == '0'
