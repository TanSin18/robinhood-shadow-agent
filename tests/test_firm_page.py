from test_ai_trader import *  # noqa: F401,F403 (shared fixtures)
from test_ai_trader import _official


def test_firm_page_not_set_up_and_with_a_card(tmp_path, monkeypatch):
    from agents.desk import firm_page
    import agents.ai_trader.hook as hook
    official = _official(tmp_path, day='2026-10-05')
    trader = tmp_path / 'diag' / 'ai-trader' / 'trader.db'
    monkeypatch.setattr(hook, 'default_path', lambda _o: trader)
    assert 'Not set up yet' in firm_page.render({'firm': firm_page.load(official)})
    s = TraderStore(trader, official); s.bind_spec(SPEC)
    s.set_mode('PAPER', at=ET_OPEN, by='operator', spec=SPEC, official_first_run_completed=True)
    morning(s, FakeClient())
    html = firm_page.render({'firm': firm_page.load(official), 'inbox_csrf': 'tok'})
    assert 'C · random picks (control)' in html and 'SOXX' in html and 'value="CUT"' in html
    assert 'NOT A RECOMMENDATION' in html and 'TOO EARLY' in html


def test_frontdoor_firm_answer_records_a_cut(tmp_path, monkeypatch):
    import re
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
    import agents.ai_trader.hook as hook
    import test_dashboard
    from test_dashboard import serving, read
    from test_inbox_lanes import setup_runtime
    from agents.desk.frontdoor import make_server
    monkeypatch.setattr(test_dashboard, 'make_server', make_server)
    trader = tmp_path / 'diag' / 'ai-trader' / 'trader.db'
    monkeypatch.setattr(hook, 'default_path', lambda _o: trader)
    inbox, _ = setup_runtime(tmp_path)
    s = TraderStore(trader); s.bind_spec(SPEC)
    s.set_mode('PAPER', at=ET_OPEN, by='operator', spec=SPEC, official_first_run_completed=True)
    now = datetime.now(timezone.utc)
    morning(s, FakeClient())
    with s.connect() as db:
        db.execute("UPDATE operator_cards SET expires_at=?", ((now + timedelta(hours=1)).isoformat(),))
        card = db.execute('SELECT id FROM operator_cards').fetchone()[0]
    with serving(inbox) as url:
        page = read(url + '/firm')
        token = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        urlopen(Request(url + '/firm/answer', data=urlencode({'csrf': token, 'card': card, 'answer': 'CUT'}).encode()))
    with s.connect() as db:
        status, frac = db.execute('SELECT status, cut_fraction FROM operator_cards').fetchone()
    assert status == 'APPROVED_AWAITING_FILL' and frac == '0.5'
