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
        self.seats = []

    def __call__(self, model, prompt, schema, envelope):
        from agents.analyst import team
        seat = next(k for k, p in team.PROMPTS.items() if prompt.startswith(p))
        self.prompts.append(prompt)
        self.seats.append(seat)
        assert model == team.MODELS[seat] and envelope == team.ENVELOPES[seat]
        out = {'pip': {'base_rate': 'Trend rules like this lagged VTI after tax.', 'setups': [], 'cited_numbers': []},
               'biscuit': {'summary': 'No relevant news.', 'news': [], 'cited_numbers': []},
               'maple': {'portfolio_read': 'Mostly cash.', 'points': [], 'cited_numbers': []},
               'pickle': {'verdicts': [{'target': 'official_decision', 'verdict': 'sound', 'reasons': ['rule followed'], 'fail_codes': []}],
                          'lessons': [{'lesson': 'Check the chop label before trusting a momentum rank.', 'check_next': 'Is SOXX still labelled trending?'}],
                          'cited_numbers': []},
               'bubbles': {'headline': 'Chips lead', 'market_read': 'Quiet tape.', 'decision_read': 'The desk rule bought SOXX.',
                           'regime_read': '', 'auction_read': '', 'news': [], 'watch': ['SOXX trend'], 'cited_numbers': []}}[seat]
        return out, 900, 300


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
        start = datetime(2026, 10, 5, tzinfo=timezone.utc) - timedelta(days=379)     # last bar is the test's "today"
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
    assert len(reader.calls) == len(hook.UNIVERSE) + 1          # one VTI-only check that today's bar is published
    assert store.latest("regimes")["status"] == "OK" and "_labels" not in store.latest("regimes")
    g = store.latest("guard")
    assert g["exits"][0]["ticker"] == "SOXX" and g["exits"][0]["status"] == "OK" and "SOXX" in g["chop"]
    assert g["entry_gate"] and g["entry_gate"][0]["ticker"] == "SOXX"
    assert 'SOXX' in store.latest('kelly')['tickers'] and store.latest('auction')['tickers']['SOXX']['status'] == 'OK'
    assert hashlib.sha256(official.read_bytes()).hexdigest() == before
    assert store.spent() > 0 and store.spent() < 1


def test_a_failing_job_is_contained_and_retries_are_capped(tmp_path):
    official = _official(tmp_path)
    path = tmp_path / 'diag' / 'analyst' / 'analyst.db'
    store = AnalystStore(path, official)

    def broken():
        raise RuntimeError('reader down')
    late = datetime(2026, 10, 5, 23, 40, tzinfo=timezone.utc)       # after the wait-for-today's-bar period
    for i in range(4):
        out = hook.tick(_Inbox(official), _Config(), late + timedelta(minutes=i), path=path, client_factory=_Client,
                        opener=_no_net, reader_factory=broken)
        if i < 2:
            assert out['close']['status'] == 'ANALYST_JOB_FAILED'
        else:
            assert out is None
    assert store.meta('close_attempts:2026-10-05') == '2'


def test_disciplined_kelly_needs_the_full_history_edge_too():
    rng = random.Random(1)
    closes, c = [], 100.0
    labels = {}
    for i in range(800):
        calm = i % 2 == 0
        r = (0.004 if calm else -0.004) + rng.gauss(0, 0.002)
        c *= 1 + r
        d = f'd{i:04d}'
        closes.append((d, c))
        labels[d] = 'calm' if calm else 'normal'
    k = kelly.size(closes, labels, 'calm')
    assert k['regime']['t_stat'] > 2 and k['all']['t_stat'] < 2
    assert k['regime']['kelly_disciplined'] == 0.0 and k['regime']['disciplined_note']


def test_headline_cap_spreads_across_tickers():
    heads = [{'id': f'news:{i}', 'ticker': 'SOXX' if i < 20 else f'T{i}', 'title': 't'} for i in range(60)]
    pkt = commentary.packet('morning', headlines=heads)
    h = pkt['HEADLINES_UNTRUSTED']
    assert len(h) == commentary.MAX_HEADLINES and sum(x['ticker'] == 'SOXX' for x in h) == 4


def test_truncated_or_non_json_output_is_a_named_model_error():
    from agents.ai_trader.model import ModelError, OpenAIResponsesClient

    class R:
        model = commentary.MODEL
        status = 'incomplete'
        output_text = '{"headline": "cut'

    class API:
        class responses:
            class input_tokens:
                @staticmethod
                def count(**kw):
                    return type('C', (), {'input_tokens': 10})()

            @staticmethod
            def create(**kw):
                return R()
    client = OpenAIResponsesClient(API())
    with pytest.raises(ModelError, match='OUTPUT_TRUNCATED'):
        client(commentary.MODEL, 'p', commentary.SCHEMA, commentary.ENVELOPE)
    R.status = 'completed'
    with pytest.raises(ModelError, match='OUTPUT_NOT_JSON'):
        client(commentary.MODEL, 'p', commentary.SCHEMA, commentary.ENVELOPE)


def _bars(closes, spread=0.01):
    return [{'day': f'2026-{1 + i // 28:02d}-{1 + i % 28:02d}', 'open': c, 'high': c * (1 + spread), 'low': c * (1 - spread), 'close': c,
             'volume': 1000} for i, c in enumerate(closes)]


def test_chop_gate_tells_a_trend_from_a_range():
    from agents.analyst import guard
    trend = guard.chop_label(_bars([100 * 1.004 ** i for i in range(200)]))
    rng = random.Random(5)
    chop = guard.chop_label(_bars([100 + 2 * math.sin(i / 2) + rng.gauss(0, 0.5) for i in range(200)], spread=0.02))
    assert trend['label'] in ('TRENDING', 'OVEREXTENDED') and trend['adx14'] > 20
    assert chop['label'] in ('CHOPPY', 'LOW_VOL') and chop['gate'] == 'sit out'
    assert guard.chop_label(_bars([100] * 20))['status'] == 'TOO_FEW_SESSIONS'


def test_exit_guard_trails_locks_profit_and_flags_give_back():
    from agents.analyst import guard
    up = [100 * 1.01 ** i for i in range(60)]                       # +80% run since entry
    bars = _bars([90] * 150 + up)
    entry = bars[150]['day']
    h = {'account': 'A:agent_alone', 'ticker': 'SOXX', 'quantity': 1, 'average_cost': 100.0, 'entry_day': entry}
    g = guard.exit_guard(h, bars)
    assert g['verdict'] == 'HOLD' and g['guard_stop'] > 100 and 'chandelier' in g['guard_stop_rule'] or 'lock' in g['guard_stop_rule']
    falling = bars + _bars([up[-1] * 0.97 ** i for i in range(1, 15)])[:14]
    for i, b in enumerate(falling[-14:]):
        b['day'] = f'2026-12-{i + 1:02d}'
    g2 = guard.exit_guard(h, falling)
    assert g2['verdict'] == 'WOULD_SELL' and any('give-back' in t or 'chandelier' in t or 'lock' in t for t in g2['triggers'])
    loss = guard.exit_guard({**h, 'average_cost': 200.0}, bars)
    assert '8%' in loss['guard_stop_rule'] or loss['verdict'] == 'WOULD_SELL'


def test_the_whole_team_writes_in_order_and_pickle_sees_the_others(tmp_path):
    official = _official(tmp_path)
    path = tmp_path / 'diag' / 'analyst' / 'analyst.db'
    store = AnalystStore(path, official)
    client = _Client()
    out = hook.tick(_Inbox(official), _Config(), NOW_AM, path=path, client_factory=lambda: client, opener=_no_net)
    assert client.seats == ['pip', 'biscuit', 'maple', 'pickle', 'bubbles']
    assert set(out['morning']['note']['team']) == {'pip', 'biscuit', 'maple', 'pickle', 'bubbles'}
    pickle_prompt = client.prompts[3]
    assert '"TEAM_NOTES"' in pickle_prompt and 'Trend rules like this lagged VTI' in pickle_prompt
    assert '"TEAM_NOTES"' not in client.prompts[0]
    with store.connect() as db:
        kinds = sorted(k for (k,) in db.execute('SELECT kind FROM notes'))
    assert kinds == ['morning', 'morning:biscuit', 'morning:maple', 'morning:pickle', 'morning:pip']


def test_a_failing_seat_does_not_stop_the_team(tmp_path):
    from agents.ai_trader.model import ModelError
    official = _official(tmp_path)
    path = tmp_path / 'diag' / 'analyst' / 'analyst.db'
    AnalystStore(path, official)
    base = _Client()

    def flaky(model, prompt, schema, envelope):
        from agents.analyst import team
        if prompt.startswith(team.PROMPTS['maple']):
            raise ModelError('OUTPUT_TRUNCATED')
        return base(model, prompt, schema, envelope)
    out = hook.tick(_Inbox(official), _Config(), NOW_AM, path=path, client_factory=lambda: flaky, opener=_no_net)
    team = out['morning']['note']['team']
    assert team['maple']['status'] == 'ModelError' and team['bubbles']['status'] == 'WRITTEN'


def test_close_waits_for_todays_bar_then_runs(tmp_path):
    official = _official(tmp_path)
    path = tmp_path / 'diag' / 'analyst' / 'analyst.db'
    store = AnalystStore(path, official)

    class Yesterday(_Reader):                      # the broker has only published bars through the previous session
        def call(self, tool, args):
            self.calls.append(args['symbols'][0])
            bars = [{'begins_at': f'2026-10-0{d}T00:00:00Z', 'open_price': 1, 'high_price': 1, 'low_price': 1, 'close_price': 1, 'volume': 1}
                    for d in (1, 2)]
            return {'data': {'results': [{'bars': bars}]}}
    reader = Yesterday()
    out = hook.tick(_Inbox(official), _Config(), NOW_PM, path=path, client_factory=_Client, opener=_no_net, reader_factory=lambda: reader)
    assert out is None and reader.calls == ['VTI'] and store.meta('close_done') is None
    assert store.meta('close_attempts:2026-10-05') is None                     # waiting costs no attempt
    again = hook.tick(_Inbox(official), _Config(), NOW_PM + timedelta(minutes=2), path=path, client_factory=_Client, opener=_no_net,
                      reader_factory=lambda: reader)
    assert again is None and reader.calls == ['VTI']                           # no second read inside 10 minutes
    late = datetime(2026, 10, 5, 23, 35, tzinfo=timezone.utc)                  # 19:35 ET: stop waiting, run and say the bars are stale
    client = _Client()

    class Stale(_Reader):
        def call(self, tool, args):
            read = super().call(tool, args)
            read['data']['results'][0]['bars'].pop()        # today's bar never arrived
            return read
    out = hook.tick(_Inbox(official), _Config(), late, path=path, client_factory=lambda: client, opener=_no_net, reader_factory=lambda: Stale())
    assert out['close']['bars_through'] == '2026-10-04' and '"stale": true' in client.prompts[-1]


def test_ask_answers_from_the_packet_checks_numbers_and_stores(tmp_path):
    from agents.analyst import ask
    official = _official(tmp_path)
    store = AnalystStore(tmp_path / 'diag' / 'analyst' / 'analyst.db', official)
    seen = {}

    def client(model, prompt, schema, envelope):
        seen['prompt'] = prompt
        assert model == ask.MODEL and envelope == ask.ENVELOPE
        return ({'answer': 'The desk rule bought SOXX because it ranked first; it sits 25.72% above its average.', 'missing': '',
                 'sources': ['decision', 'feature:SOXX'], 'follow_ups': ['What would make it sell?'],
                 'cited_numbers': [{'source_id': 'feature:SOXX', 'field': 'pct_vs_ma200', 'value': 25.72}]}, 1200, 200)
    pkt = {'decision': {'id': 'decision', 'type': 'DESK_ENTRY'}, 'feature:SOXX': {'id': 'feature:SOXX', 'pct_vs_ma200': 25.72}}
    out = ask.answer(store, '  Why did we buy   SOXX today? ', pkt, NOW_AM, client, day='2026-10-05', context='room')
    assert out['status'] == 'ANSWERED' and out['checks']['ok'] and '"Why did we buy SOXX today?"' in seen['prompt']
    with store.connect() as db:
        row = db.execute('SELECT question, status, context FROM qa').fetchone()
    assert row == ('Why did we buy SOXX today?', 'ANSWERED', 'room') and 0 < store.spent('2026-10-05') < 1
    with pytest.raises(ask.AskError):
        ask.answer(store, 'x' * 501, pkt, NOW_AM, client, day='2026-10-05')
    with pytest.raises(ask.AskError):
        ask.answer(store, '   ', pkt, NOW_AM, client, day='2026-10-05')


def test_ask_records_a_model_failure_and_stops_at_the_daily_limit(tmp_path, monkeypatch):
    from agents.analyst import ask
    from agents.ai_trader.model import ModelError
    official = _official(tmp_path)
    store = AnalystStore(tmp_path / 'diag' / 'analyst' / 'analyst.db', official)

    def broken(model, prompt, schema, envelope):
        raise ModelError('OUTPUT_TRUNCATED')
    out = ask.answer(store, 'What happened?', {}, NOW_AM, broken, day='2026-10-05')
    assert out['status'] == 'FAILED_ModelError'
    monkeypatch.setattr(ask, 'MAX_PER_DAY', 1)
    assert ask.answer(store, 'Again?', {}, NOW_AM, broken, day='2026-10-05') == {'status': 'DAILY_QUESTION_LIMIT'}


def test_ask_accepts_numbers_from_rule_text_and_refers_to_earlier_questions(tmp_path):
    from agents.analyst import ask
    official = _official(tmp_path)
    store = AnalystStore(tmp_path / 'diag' / 'analyst' / 'analyst.db', official)
    prompts = []

    def client(model, prompt, schema, envelope):
        prompts.append(prompt)
        return ({'answer': 'A holding is sold at 15:50 if it is 8% below cost or under its 200-day average; 77.5 is invented.', 'missing': '',
                 'sources': ['rule_book_matches'], 'follow_ups': [], 'cited_numbers': []}, 900, 120)
    pkt = {'rule_book_matches': [{'name': 'Protective stop', 'condition': '8% below cost, or at/below the 200-day average', 'when': '15:50 ET'}]}
    out = ask.answer(store, 'When do we sell?', pkt, NOW_AM, client, day='2026-10-05')
    assert out['checks']['flags'] == ['NUMBER_NOT_IN_RECORDS:77.5']   # numbers written in the rule text are known; the invented one is not
    nested = {'run': {'id': 'run', 'fills': [{'ticker': 'SOXX', 'price': '566.640000'}]}}
    good = {'answer': 'SOXX filled at 566.64.', 'cited_numbers': [{'source_id': 'run', 'field': 'fills.price', 'value': 566.64}]}
    assert ask.check(good, nested) == {'ok': True, 'flags': []}
    bad = {'answer': 'SOXX filled at 570.10.', 'cited_numbers': [{'source_id': 'run', 'field': 'fills.price', 'value': 570.1}]}
    assert ask.check(bad, nested)['flags'] == ['CITATION_NOT_IN_RECORDS:run.fills.price', 'NUMBER_NOT_IN_RECORDS:570.10']
    ask.answer(store, 'And why?', pkt, NOW_AM, client, day='2026-10-05')
    assert '"EARLIER_QUESTIONS"' in prompts[1] and 'When do we sell?' in prompts[1] and '"EARLIER_QUESTIONS"' not in prompts[0]


def test_ask_keeps_half_the_daily_cap_for_the_team(tmp_path, monkeypatch):
    from agents.analyst import ask
    official = _official(tmp_path)
    store = AnalystStore(tmp_path / 'diag' / 'analyst' / 'analyst.db', official)
    monkeypatch.setattr(ask, 'ASK_DAILY_USD', '0.03')

    def client(model, prompt, schema, envelope):
        return ({'answer': 'Nothing traded.', 'missing': '', 'sources': [], 'follow_ups': [], 'cited_numbers': []}, 18000, 3000)
    assert ask.answer(store, 'One?', {}, NOW_AM, client, day='2026-10-05')['status'] == 'ANSWERED'
    assert ask.answer(store, 'Two?', {}, NOW_AM, client, day='2026-10-05') == {'status': 'DAILY_QUESTION_BUDGET'}


def test_cli_ask_reads_one_json_request_and_respects_pause(tmp_path, capsys):
    import io
    from agents.analyst import cli
    official = _official(tmp_path)
    path = tmp_path / 'diag' / 'analyst' / 'analyst.db'
    store = AnalystStore(path, official)

    def client(model, prompt, schema, envelope):
        return ({'answer': 'The desk held.', 'missing': '', 'sources': ['decision'], 'follow_ups': [], 'cited_numbers': []}, 500, 60)
    args = ['ask', '--official-database', str(official), '--path', str(path)]
    req = json.dumps({'question': 'What happened?', 'context': 'room', 'packet': {'decision': {'id': 'decision', 'type': 'HOLD'}}})
    assert cli.main(args, stdin=io.StringIO(req), client=client) == 0
    assert json.loads(capsys.readouterr().out) == {'status': 'ANSWERED', 'flags': []}
    cli.main(args, stdin=io.StringIO('not json'), client=client)
    assert json.loads(capsys.readouterr().out)['status'] == 'INVALID_REQUEST'
    cli.main(args, stdin=io.StringIO(json.dumps({'question': ' ', 'packet': {}})), client=client)
    assert json.loads(capsys.readouterr().out)['status'] == 'EMPTY_QUESTION'
    store.set_meta('paused', '1')
    cli.main(args, stdin=io.StringIO(req), client=client)
    assert json.loads(capsys.readouterr().out)['status'] == 'ANALYST_PAUSED'
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM qa').fetchone()[0] == 1


def test_cli_rerun_lets_todays_job_run_once_more(tmp_path, capsys):
    from agents.analyst import cli
    official = _official(tmp_path)
    path = tmp_path / 'diag' / 'analyst' / 'analyst.db'
    store = AnalystStore(path, official)
    day = datetime.now(timezone.utc).astimezone(hook.ET).date().isoformat()
    store.set_meta('close_done', day)
    store.set_meta(f'close_attempts:{day}', '2')
    store.set_meta('morning_done', day)
    assert cli.main(['rerun', '--official-database', str(official), '--path', str(path), '--job', 'close']) == 0
    capsys.readouterr()
    assert store.meta('close_done') != day and store.meta(f'close_attempts:{day}') == '0' and store.meta('morning_done') == day
    with pytest.raises(SystemExit):
        cli.main(['rerun', '--official-database', str(official), '--path', str(path)])


def test_memory_scores_yesterdays_calls_and_feeds_them_back(tmp_path):
    from agents.analyst import memory
    official = _official(tmp_path)
    store = AnalystStore(tmp_path / 'diag' / 'analyst' / 'analyst.db', official)
    day1 = datetime(2026, 10, 5, 20, 30, tzinfo=timezone.utc)
    store.add('notes', '2026-10-05', {'headline': 'Chips firm, banks soft.', 'decision_read': 'The desk held SOXX.', 'watch': ['SOXX trend'],
                                      'news': [{'ticker': 'SOXX', 'sentiment': 'positive', 'note': 'AI demand.'},
                                               {'ticker': 'XLF', 'sentiment': 'negative', 'note': 'Bank worries.'},
                                               {'ticker': 'META', 'sentiment': 'mixed', 'note': 'Not a call.'}]}, day1, kind='close', model='m', checks_json={})
    store.add('notes', '2026-10-05', {'summary': 's', 'news': [{'ticker': 'SOXX', 'sentiment': 'positive', 'note': 'Same view.'}]}, day1,
              kind='close:biscuit', model='m', checks_json={})
    store.add('notes', '2026-10-05', {'verdicts': [], 'lessons': [{'lesson': 'Check the chop label before trusting a rank.', 'check_next': 'SOXX label'},
                                                                 {'lesson': 'Say when bars are stale.', 'check_next': 'as_of'},
                                                                 {'lesson': 'A third one is dropped.', 'check_next': ''}]}, day1,
              kind='close:pickle', model='m', checks_json={})
    kept = memory.record(store, '2026-10-05', 'close', '2026-10-05', day1, regime='calm')
    assert kept == {'calls': 4, 'lessons': 2}                                    # two Bubbles calls, one Buttercup call, the regime label; mixed is not a call
    assert memory.record(store, '2026-10-05', 'close', '2026-10-05', day1, regime='calm')['lessons'] == 0      # a rerun adds nothing twice
    bars = {'SOXX': [{'day': '2026-10-05', 'close': 100.0}], 'XLF': [{'day': '2026-10-05', 'close': 50.0}],
            'SPY': [{'day': '2026-10-05', 'close': 400.0}], 'VTI': [{'day': '2026-10-05', 'close': 200.0}]}
    assert memory.score(store, bars) == 0                                        # the next session has not closed yet
    card = memory.scorecard(store)
    assert card['sentiment_calls_scored'] == 0 and card['verdict'] == 'TOO_FEW_TO_JUDGE' and card['calls_waiting_for_next_close'] == 4
    for t, c in (('SOXX', 102.0), ('XLF', 50.5), ('SPY', 402.0), ('VTI', 201.0)):
        bars[t].append({'day': '2026-10-06', 'close': c})
    assert memory.score(store, bars) == 4 and memory.score(store, bars) == 0
    card = memory.scorecard(store)
    assert card['sentiment_calls_scored'] == 3 and card['hits'] == 2 and card['hit_rate_pct'] == 66.7 and card['verdict'] == 'TOO_FEW_TO_JUDGE'
    assert card['avg_next_day_pct_after_positive'] == 2.0 and card['avg_next_day_pct_after_negative'] == 1.0
    assert card['regime_avg_abs_next_day_move_pct'] == {'calm': {'sessions': 1, 'avg_abs_move_pct': 0.5}}
    block = memory.block(store, '2026-10-06')
    assert block['memory:last_note']['headline'] == 'Chips firm, banks soft.' and block['memory:last_note']['watch'] == ['SOXX trend']
    assert block['memory:call:SOXX'] == {'id': 'memory:call:SOXX', 'called_on': '2026-10-05', 'call': 'positive', 'scored_on': '2026-10-06',
                                         'next_day_return_pct': 2.0, 'spy_return_pct': 0.5, 'hit': True}
    assert block['memory:call:XLF']['hit'] is False and 'memory:call:META' not in block
    assert block['memory:scorecard']['needed_before_any_verdict'] == 60
    assert [x['lesson'] for x in block['MEMORY_LESSONS']] == ['Say when bars are stale.', 'Check the chop label before trusting a rank.']
    out = {'headline': 'SOXX rose 2% after the positive call; the record is too short to trust.', 'news': [], 'watch': [],
           'cited_numbers': [{'source_id': 'memory:call:SOXX', 'field': 'next_day_return_pct', 'value': 2.0}]}
    assert commentary.check(out, block)['ok']


def test_scorecard_gives_a_verdict_only_with_enough_calls(tmp_path):
    from agents.analyst import memory
    store = AnalystStore(tmp_path / 'diag' / 'analyst' / 'analyst.db', _official(tmp_path))
    memory.ensure(store)
    with store.connect() as db:
        for i in range(60):
            db.execute('INSERT INTO calls(day,at,seat,kind,ticker,call,basis_day,note,scored_day,outcome_json) VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (f'd{i}', '', 'bubbles', 'sentiment', 'SOXX', 'positive', '', '', 'x', json.dumps({'next_day_return_pct': 1.0, 'hit': i < 33})))
    assert memory.scorecard(store)['verdict'] == 'NO_EVIDENCE_IT_BEATS_A_COIN_FLIP'          # 33 of 60 is inside coin-flip range
    with store.connect() as db:
        db.execute("UPDATE calls SET outcome_json=? WHERE day IN ('d33','d34','d35','d36','d37','d38','d39','d40')", (json.dumps({'next_day_return_pct': 1.0, 'hit': True}),))
    assert memory.scorecard(store)['verdict'] == 'BETTER_THAN_A_COIN_FLIP'                   # 41 of 60


def test_close_job_carries_memory_into_the_packet_and_records_lessons(tmp_path):
    official = _official(tmp_path)
    path = tmp_path / 'diag' / 'analyst' / 'analyst.db'
    store = AnalystStore(path, official)
    store.add('notes', '2026-10-02', {'headline': 'Friday note', 'watch': ['VTI'], 'news': []}, NOW_PM - timedelta(days=3), kind='close', model='m', checks_json={})
    client = _Client()
    out = hook.tick(_Inbox(official), _Config(), NOW_PM, path=path, client_factory=lambda: client, opener=_no_net, reader_factory=lambda: _Reader())
    assert out['close']['memory']['lessons'] == 1 and out['close']['memory']['calls'] >= 1      # the critic's lesson and at least the regime label
    assert all('"memory:last_note"' in p and 'Friday note' in p and '"memory:scorecard"' in p for p in client.prompts)
    from agents.analyst import memory
    assert memory.lessons(store, '2026-10-05')[0]['lesson'].startswith('Check the chop label')
