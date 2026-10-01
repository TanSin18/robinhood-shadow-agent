"""Analyst desk: AI writes commentary and news notes, code computes regime and shadow Kelly. Never trades."""
import hashlib
import json
import math
import random
import sqlite3
from datetime import date, datetime, timedelta, timezone

import pytest

from agents.analyst import auction, commentary, hook, kelly, news, regime
from agents.analyst.store import AnalystStore, StoreError

NOW_AM = datetime(2026, 10, 5, 14, 7, tzinfo=timezone.utc)     # 10:07 ET Monday
NOW_PM = datetime(2026, 10, 5, 20, 20, tzinfo=timezone.utc)    # 16:20 ET


def _series(n=700, seed=3):
    rng = random.Random(seed)
    closes, c, d = [], 100.0, date(2023, 1, 2)
    for i in range(n):
        stressed = 300 <= i < 380
        c *= math.exp(rng.gauss(-0.002 if stressed else 0.0006, 0.03 if stressed else 0.006))
        closes.append((d.isoformat(), c))
        d += timedelta(days=1)
    return closes


# ------------------------------------------------------------------ pure parts
def test_regime_finds_the_stressed_block_and_is_deterministic():
    r1 = regime.fit(regime.log_returns(_series()))
    r2 = regime.fit(regime.log_returns(_series()))
    assert r1['status'] == 'OK' and r1['log_likelihood'] == r2['log_likelihood']
    vols = [s['vol_daily_pct'] for s in r1['states']]
    assert vols == sorted(vols) and [s['name'] for s in r1['states']] == ['calm', 'normal', 'stressed']
    labels = r1['_labels']
    days = [d for d, _ in _series()]
    stressed = sum(labels.get(d) == 'stressed' for d in days[310:370])
    assert stressed >= 45
    assert abs(sum(r1['current_probabilities'].values()) - 1) < 1e-6
    assert regime.stability(r1, r2) == {'compared_sessions': 20, 'relabelled': 0}
    assert regime.fit(regime.log_returns(_series(60)))['status'] == 'TOO_FEW_SESSIONS'


def test_kelly_is_zero_without_a_significant_edge_and_never_above_the_cap():
    flat = [(f'2024-01-{i:02d}', 100 + (i % 2)) for i in range(1, 29)] * 3
    flat = [(f'd{i:04d}', c) for i, (_, c) in enumerate(flat)]
    k = kelly.size(flat)
    assert k['all']['kelly_disciplined'] == 0.0
    up = [(f'd{i:04d}', 100 * (1.004 ** i) * (1 + 0.001 * ((-1) ** i))) for i in range(400)]
    k = kelly.size(up)
    assert k['all']['t_stat'] > 2 and k['all']['kelly_raw'] > 1 and k['all']['kelly_disciplined'] == 0.25
    assert 0 < k['risk_engine_fraction'] <= 0.25


def test_auction_read_labels_the_day():
    bars = [{'day': f'd{i}', 'open': 100, 'high': 101, 'low': 99, 'close': 100, 'volume': 1000} for i in range(25)]
    bars.append({'day': 'today', 'open': 100.2, 'high': 104, 'low': 100, 'close': 103.8, 'volume': 3000})
    r = auction.read(bars)
    assert r['day_type'] == 'trend day up' and r['close_location'] > 0.8 and r['volume_vs_avg20'] == 3.0
    assert auction.read(bars[:10])['status'] == 'TOO_FEW_SESSIONS'


def test_bars_use_the_real_session_date_and_today_only_after_the_close():
    read = {'data': {'results': [{'bars': [
        {'begins_at': '2026-10-02T00:00:00Z', 'open_price': '1', 'high_price': '2', 'low_price': '1', 'close_price': '1.5', 'volume': 10},
        {'begins_at': '2026-10-05T00:00:00Z', 'open_price': '1', 'high_price': '2', 'low_price': '1', 'close_price': '1.7', 'volume': 10}]}]}}
    assert [b['day'] for b in hook.parse_bars(read, NOW_AM)] == ['2026-10-02']
    assert [b['day'] for b in hook.parse_bars(read, NOW_PM)] == ['2026-10-02', '2026-10-05']


RSS = b'''<?xml version="1.0"?><rss><channel>
<item><title>Chip stocks rally &amp; SOXX jumps</title><link>https://example.com/a</link><source>Example</source>
<pubDate>Mon, 05 Oct 2026 12:00:00 GMT</pubDate></item>
<item><title>Old story</title><link>https://example.com/b</link><pubDate>Mon, 21 Sep 2026 12:00:00 GMT</pubDate></item>
<item><title>No https</title><link>http://example.com/c</link><pubDate>Mon, 05 Oct 2026 12:00:00 GMT</pubDate></item>
</channel></rss>'''


class _Resp:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n):
        return self.data[:n]


def test_news_keeps_recent_https_items_and_refuses_entities():
    items = news.parse_rss(RSS, 'SOXX', NOW_AM)
    assert [i['title'] for i in items] == ['Chip stocks rally & SOXX jumps']
    with pytest.raises(ValueError):
        news.parse_rss(b'<!DOCTYPE x [<!ENTITY a "b">]><rss/>', 'SOXX', NOW_AM)
    got, problems = news.collect(['SOXX'], NOW_AM, opener=lambda req, timeout: _Resp(RSS))
    assert got and got[0]['id'] == 'news:1' and {'ticker': '*', 'error': 'EDGAR_SKIPPED_NO_CONTACT_FILE'} in problems


def test_commentary_checks_citations_numbers_and_order_language():
    pkt = commentary.packet('morning', features={'SOXX': {'price': 568.64, 'pct_vs_ma200': 25.72}},
                            headlines=[{'id': 'news:1', 'ticker': 'SOXX', 'title': 't'}])
    good = {'headline': 'Chips lead', 'market_read': 'SOXX sits 25.72% above its average.', 'decision_read': '', 'regime_read': '',
            'auction_read': '', 'news': [{'ticker': 'SOXX', 'sentiment': 'positive', 'relevance': 'high', 'note': 'n', 'headline_ids': ['news:1']}],
            'watch': [], 'cited_numbers': [{'source_id': 'feature:SOXX', 'field': 'pct_vs_ma200', 'value': 25.72}]}
    assert commentary.check(good, pkt) == {'ok': True, 'flags': []}
    bad = dict(good, market_read='SOXX will go to 900. Buy now, a sure thing.',
               cited_numbers=[{'source_id': 'feature:SOXX', 'field': 'price', 'value': 600}],
               news=[{**good['news'][0], 'headline_ids': ['news:9']}])
    flags = commentary.check(bad, pkt)['flags']
    assert 'CITATION_MISMATCH:feature:SOXX.price' in flags and 'UNCITED_NUMBER:900' in flags
    assert 'ORDER_LIKE_LANGUAGE' in flags and 'HYPE:sure thing' in flags and 'UNKNOWN_HEADLINE:SOXX' in flags


# ------------------------------------------------------------------ hook
def _official(tmp_path, status='COMPLETED'):
    data = tmp_path / 'runtime' / 'data'
    data.mkdir(parents=True)
    db = sqlite3.connect(data / 'agent.db')
    db.execute('CREATE TABLE cycle_runs (day TEXT PRIMARY KEY, status TEXT, payload TEXT)')
    db.execute('INSERT INTO cycle_runs VALUES (?,?,?)', ('2026-10-05', status, '{}'))
    db.execute('CREATE TABLE decision_capsules (hash TEXT, cycle_id TEXT, created_at TEXT, payload TEXT)')
    cap = {'observed_at': '2026-10-05T14:02:00+00:00',
           'outcome': {'decision': {'type': 'DESK_ENTRY', 'reason': 'Desk rule', 'signal_instruments': ['SOXX']}},
           'strategy_assessment': {'features': {'SOXX': {'price': '568.64', 'ma200': '452.31', 'momentum_126d': '0.73', 'one_day_return': '0.002'}},
                                   'signals': [{'instrument': 'SOXX'}]}, 'inputs': {}}
    db.execute('INSERT INTO decision_capsules VALUES (?,?,?,?)', ('h', 'c', '2026-10-05T14:02:00+00:00', json.dumps(cap)))
    db.execute('CREATE TABLE paper_accounts (lane TEXT, track TEXT, payload TEXT)')
    db.execute('INSERT INTO paper_accounts VALUES (?,?,?)', ('A', 'agent_alone', json.dumps(
        {'positions': {'SOXX': {'quantity': '2.32209', 'average_cost': '566.64'}}, 'marks': {'SOXX': '566.49'}})))
    db.commit()
    db.close()
    return data / 'agent.db'


class _Inbox:
    def __init__(self, path):
        self.path = path


class _Risk:
    def model_copy(self, update=None):
        return self


class _Config:
    risk = _Risk()

    def model_copy(self, update=None):
        return self


class _Client:
    def __init__(self):
        self.prompts = []

    def __call__(self, model, prompt, schema, envelope):
        self.prompts.append(prompt)
        assert model == commentary.MODEL and envelope == commentary.ENVELOPE
        return ({'headline': 'Chips lead', 'market_read': 'Quiet tape.', 'decision_read': 'The desk rule bought SOXX.',
                 'regime_read': '', 'auction_read': '', 'news': [], 'watch': ['SOXX trend'], 'cited_numbers': []}, 900, 300)


class _Reader:
    def __init__(self):
        self.calls = []

        class G:
            pass
        self.gateway = G()
        self.gateway.call = self.call

    def call(self, tool, args):
        assert tool == 'get_equity_historicals' and args['interval'] == 'day'
        self.calls.append(args['symbols'][0])
        closes = _series(380, seed=len(self.calls))
        start = datetime(2025, 3, 20, tzinfo=timezone.utc)
        bars = [{'begins_at': (start + timedelta(days=i)).isoformat().replace('+00:00', 'Z'), 'open_price': c, 'high_price': c * 1.01,
                 'low_price': c * 0.99, 'close_price': c, 'volume': 1000} for i, (_, c) in enumerate(closes)]
        return {'data': {'results': [{'bars': bars}]}}

    def close(self):
        pass


def _no_net(req, timeout):
    raise OSError('offline in tests')


def test_store_refuses_the_official_directory(tmp_path):
    official = _official(tmp_path)
    with pytest.raises(StoreError):
        AnalystStore(official.parent / 'analyst.db', official)


def test_hook_disabled_until_init_and_waits_for_the_official_run(tmp_path):
    official = _official(tmp_path, status='RUNNING')
    path = tmp_path / 'diag' / 'analyst' / 'analyst.db'
    assert hook.tick(_Inbox(official), _Config(), NOW_AM, path=path) is None
    AnalystStore(path, official)
    assert hook.tick(_Inbox(official), _Config(), NOW_AM, path=path, client_factory=_Client, opener=_no_net) is None


def test_morning_and_close_write_notes_and_never_touch_the_official_db(tmp_path):
    official = _official(tmp_path)
    before = hashlib.sha256(official.read_bytes()).hexdigest()
    path = tmp_path / 'diag' / 'analyst' / 'analyst.db'
    store = AnalystStore(path, official)
    client = _Client()
    out = hook.tick(_Inbox(official), _Config(), NOW_AM, path=path, client_factory=lambda: client, opener=_no_net)
    assert out['morning']['note']['status'] == 'WRITTEN' and store.meta('morning_done') == '2026-10-05'
    assert 'HEADLINES_UNTRUSTED' in client.prompts[0] and '"holding:A:agent_alone:SOXX"' in client.prompts[0]
    assert hook.tick(_Inbox(official), _Config(), NOW_AM + timedelta(minutes=1), path=path, client_factory=_Client, opener=_no_net) is None
    reader = _Reader()
    out = hook.tick(_Inbox(official), _Config(), NOW_PM, path=path, client_factory=lambda: client, opener=_no_net,
                    reader_factory=lambda: reader)
    assert out['close']['note']['status'] == 'WRITTEN' and out['close']['regime_status'] == 'OK'
    assert len(reader.calls) == len(hook.UNIVERSE)
    assert store.latest('regimes')['status'] == 'OK' and '_labels' not in store.latest('regimes')
    assert 'SOXX' in store.latest('kelly')['tickers'] and store.latest('auction')['tickers']['SOXX']['status'] == 'OK'
    assert hashlib.sha256(official.read_bytes()).hexdigest() == before
    assert store.spent() > 0 and store.spent() < 1


def test_a_failing_job_is_contained_and_retries_are_capped(tmp_path):
    official = _official(tmp_path)
    path = tmp_path / 'diag' / 'analyst' / 'analyst.db'
    store = AnalystStore(path, official)

    def broken():
        raise RuntimeError('reader down')
    for i in range(4):
        out = hook.tick(_Inbox(official), _Config(), NOW_PM + timedelta(minutes=i), path=path, client_factory=_Client,
                        opener=_no_net, reader_factory=broken)
        if i < 2:
            assert out['close']['status'] == 'ANALYST_JOB_FAILED'
        else:
            assert out is None
    assert store.meta('close_attempts:2026-10-05') == '2'
