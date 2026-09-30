import json

from agents.daily_cycle import FixtureReader
from test_rehearsal import source, NOW


class Reader(FixtureReader):
    def __init__(self, config, now):
        super().__init__(config, now)
        self.closed = False
    def collect(self, now, held):
        reads = super().collect(now, held)
        for r in reads:
            if r['tool'] == 'get_equity_historicals':
                for item in r['data']['results']:
                    for b in item['bars']:
                        b['volume'] = '5000000'
        return reads
    def close(self):
        self.closed = True


def test_desk_rehearsal_issues_in_disposable_db_and_leaves_official_untouched(tmp_path):
    from agents.desk_rehearsal import run
    import agents.etf_issuer as issuer
    from agents.operator import MarketSchedule
    official, config = source(tmp_path)
    reader = Reader(config, NOW)
    report = run(official.path, config, tmp_path / 'dress', reader_factory=lambda p: reader, now=NOW)
    assert report['status'] == 'COMPLETED', report
    assert report['official_records_unchanged'] is True
    assert report['model_calls'] == 0 and report['real_orders'] == 'blocked'
    assert reader.closed
    # Overrides are restored after the rehearsal.
    assert issuer.LIQUIDITY_INTERIM_LIVE_SPREAD is False
    assert MarketSchedule().classify.__func__ is MarketSchedule.classify
    assert (tmp_path / 'dress' / 'desk.db').exists()
    # Whatever the signal outcome, every issuance happened only in the disposable DB.
    assert json.dumps(report)  # serialisable
    with official.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM approval_inbox').fetchone()[0] == 0


def test_desk_rehearsal_refuses_when_market_closed(tmp_path):
    from datetime import datetime, timezone
    from agents.desk_rehearsal import run
    official, config = source(tmp_path)
    closed = datetime(2026, 9, 27, 14, tzinfo=timezone.utc)  # Sunday
    report = run(official.path, config, tmp_path / 'dress', reader_factory=lambda p: Reader(config, closed), now=closed)
    assert report['status'] == 'NOT_RUN'
