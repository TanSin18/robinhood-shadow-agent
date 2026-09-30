import json
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal

import pytest

from agents import universe_screen as us

NOW = datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc)   # 17:00 ET, after the close


def spy_rows(tickers):
    return [['Fund Name:', 'SPDR S&P 500'], ['Name', 'Ticker', 'Weight'], *[[f'Co {t}', t, '0.1'] for t in tickers]]


def ivv_csv(tickers):
    head = 'iShares Core S&P 500 ETF\nFund Holdings as of,"Sep 30, 2026"\n \nTicker,Name,Sector,Asset Class,Weight (%)\n'
    return head + ''.join(f'{t},Co,IT,Equity,0.1\n' for t in tickers) + 'USD,Cash,Cash,Cash,0.1\n'


def names(n):
    import itertools, string
    out = []
    for a, b, c in itertools.product(string.ascii_uppercase, repeat=3):
        out.append(a + b + c)
        if len(out) == n:
            return out


def test_universe_keeps_only_tickers_both_issuers_list():
    base = names(470)
    spy = us.parse_spy_rows(spy_rows(base + ['BRK.B', 'ONLYSPY'[:5]]))
    ivv = us.parse_ivv_csv(ivv_csv(base + ['BRKB', 'IVVX']))
    u = us.build_universe(spy, ivv, as_of='2026-09-30', etfs=['SPY', 'XLK'])
    assert 'BRK.B' in u['stocks'] and 'IVVX' not in u['stocks'] and 'ONLYS' not in u['stocks']
    assert u['differences'] == {'only_spy': ['ONLYS'], 'only_ivv': ['IVVX']}
    assert 'SURVIVORSHIP-BIASED' in u['label']
    with pytest.raises(us.ScreenError):
        us.build_universe(base[:10], base[:10], as_of='x', etfs=[])


def bars_response(symbol, days, price=Decimal('100'), volume=Decimal('1000000'), drop_last=None):
    start = NOW.astimezone(us.ET).date() - timedelta(days=days)
    bars = []
    for i in range(days):
        d = start + timedelta(days=i)
        p = price * (Decimal(1) + Decimal(i) / Decimal(1000))
        if drop_last and i == days - 1:
            p = p * (1 + drop_last)
        bars.append({'begins_at': datetime(d.year, d.month, d.day, 13, 30, tzinfo=timezone.utc).isoformat(),
                     'close_price': str(p), 'volume': str(volume)})
    # today's incomplete bar must be ignored
    t = NOW.astimezone(us.ET).date()
    bars.append({'begins_at': datetime(t.year, t.month, t.day, 13, 30, tzinfo=timezone.utc).isoformat(), 'close_price': '1', 'volume': '1'})
    return {'data': {'results': [{'symbol': symbol, 'bars': bars}]}}


def test_store_must_live_apart_from_official_database(tmp_path):
    (tmp_path / 'data').mkdir()
    with pytest.raises(us.ScreenError):
        us.BarStore(tmp_path / 'data' / 'universe.db', tmp_path / 'data' / 'agent.db')
    us.BarStore(tmp_path / 'data' / 'universe-screen' / 'universe.db', tmp_path / 'data' / 'agent.db')


def test_plan_caps_backfill_and_fetch_stops_on_budget_and_errors(tmp_path):
    store = us.BarStore(tmp_path / 's' / 'u.db')
    work = us.plan([f'S{i}' for i in range(200)], store, NOW.date(), budget={**us.BUDGET, 'max_backfill_symbols': 120})
    assert len(work['backfill']) == 120 and len(work['backfill_deferred']) == 80
    calls = []

    def call(tool, args):
        calls.append(args['symbols'][0])
        if len(calls) == 3:
            raise RuntimeError('provider says no')
        return bars_response(args['symbols'][0], 30)
    out = us.fetch(call, {'backfill': ['A', 'B', 'C', 'D'], 'incremental': []}, store, NOW)
    assert out['fetched'] == 2 and out['stopped'] == 'PROVIDER_ERROR:RuntimeError'
    assert all(d < NOW.astimezone(us.ET).date().isoformat() for d, _, _ in store.closes('A'))
    out = us.fetch(lambda t, a: bars_response(a['symbols'][0], 5), {'backfill': ['E', 'F', 'G'], 'incremental': []}, store, NOW,
                   budget={**us.BUDGET, 'max_calls': 2})
    assert out['fetched'] == 2 and out['stopped'] == 'BUDGET_REACHED'


def test_screen_filters_and_shortlists_with_reasons(tmp_path):
    store = us.BarStore(tmp_path / 's' / 'u.db')
    feed = {'GOOD': bars_response('GOOD', 400, drop_last=Decimal('-0.05')),      # qualifies for mean reversion
            'THIN': bars_response('THIN', 400, volume=Decimal('10')),              # fails dollar volume
            'CHEAP': bars_response('CHEAP', 400, price=Decimal('2')),              # fails price
            'NEW': bars_response('NEW', 100)}                                      # too little history
    for sym, resp in feed.items():
        store.put(sym, us.parse_bars(resp, NOW.astimezone(us.ET).date())[sym], NOW.isoformat())
    universe = {'stocks': ['GOOD', 'THIN', 'CHEAP', 'NEW', 'MISSING'], 'etfs': []}
    out = us.screen(universe, store, NOW.astimezone(us.ET).date())
    reasons = {e['symbol']: e['reason'] for e in out['excluded']}
    assert reasons == {'THIN': 'DOLLAR_VOLUME_BELOW_50M', 'CHEAP': 'PRICE_BELOW_5', 'NEW': 'HISTORY_100_BELOW_253',
                       'MISSING': 'NO_HISTORY_CACHED'}
    assert out['funnel']['passed_filters'] == 1
    assert [s['symbol'] for s in out['shortlist']] == ['GOOD']


def test_run_records_shadow_payload_and_refuses_safety_stop(tmp_path, monkeypatch):
    official = tmp_path / 'data' / 'agent.db'
    official.parent.mkdir()
    upath = tmp_path / 'universe.json'
    upath.write_text(json.dumps({'as_of': '2026-09-30', 'label': 'SURVIVORSHIP-BIASED', 'stocks': ['GOOD'], 'etfs': []}))

    class Gateway:
        def call(self, tool, args):
            assert tool == 'get_equity_historicals'
            return bars_response(args['symbols'][0], 400, drop_last=Decimal('-0.05'))
    monkeypatch.setattr('agents.safety_events.safety_stopped', lambda p: False)
    payload = us.run(config=None, official=official, universe_path=upath, store_path=tmp_path / 'data' / 'screen' / 'u.db',
                     now=NOW, gateway_factory=lambda c, p, s: (Gateway(), lambda: None))
    assert payload['mode'] == 'shadow_only_not_used_by_official_cycle' and payload['status'] == 'COMPLETED'
    assert payload['shortlist'][0]['symbol'] == 'GOOD'
    monkeypatch.setattr('agents.safety_events.safety_stopped', lambda p: True)
    with pytest.raises(us.ScreenError):
        us.run(config=None, official=official, universe_path=upath, store_path=tmp_path / 'data' / 'screen' / 'u.db',
               now=NOW, gateway_factory=lambda c, p, s: (Gateway(), lambda: None))


def test_stdlib_xlsx_reader_reads_shared_and_inline_strings(tmp_path):
    import zipfile
    path = tmp_path / 'h.xlsx'
    sheet = ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
             '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
             '<row r="2"><c r="A2" t="inlineStr"><is><t>Apple</t></is></c><c r="B2" t="s"><v>2</v></c><c r="C2"><v>6.5</v></c></row>'
             '</sheetData></worksheet>')
    strings = ('<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
               '<si><t>Name</t></si><si><t>Ticker</t></si><si><t>AAPL</t></si></sst>')
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('xl/worksheets/sheet1.xml', sheet)
        z.writestr('xl/sharedStrings.xml', strings)
    rows = us.read_xlsx_rows(path)
    assert rows == [['Name', 'Ticker'], ['Apple', 'AAPL', '6.5']]
    assert us.parse_spy_rows(rows) == ['AAPL']
