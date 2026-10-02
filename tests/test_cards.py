from datetime import datetime, timedelta, timezone

import pytest

from agents.cards import (AGENTIC_CASH_CAP_USD, Card, CardError, CardStore, LABEL, read_view)

NOW = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)


def card(**kw):
    base = dict(id='c1', source='official_rule', recipe_id='registered_momentum_126_200_top1', ticker='SOXX', instrument='share',
                facts=('Ranked first on the registered momentum rule', 'Close above its 200-session average'),
                kills='A close at or below the long-term average, or momentum turning negative.', created_at=NOW,
                side='buy', quantity='1.5', est_cost_usd='850.00', max_loss_usd='850.00', opinion='')
    base.update(kw)
    return Card(**base)


def test_store_needs_its_own_directory(tmp_path):
    (tmp_path / 'agent.db').write_text('')
    with pytest.raises(CardError):
        CardStore(tmp_path / 'cards.db')


@pytest.mark.parametrize('bad,code', [
    (dict(source='explore'), 'EXPLORE_FROZEN'),
    (dict(opinion='Could run a long way, maybe 5x.'), 'OPINION_MUST_NOT_CONTAIN_NUMBERS'),
    (dict(opinion='A good trade with a clear target.'), 'OPINION_HYPE_NOT_ALLOWED'),
    (dict(kills='Below 200 day average'), 'KILLS_MUST_NOT_CONTAIN_NUMBERS'),
    (dict(facts=()), 'FACTS_REQUIRED'),
    (dict(max_loss_usd=None), 'SIZE_COST_AND_MAX_LOSS_REQUIRED'),
    (dict(source='watch'), 'WATCH_NOTES_ARE_NOT_ORDERS'),
])
def test_validation(bad, code):
    with pytest.raises(CardError, match=code):
        card(**bad).validate()


def test_explore_opens_in_november():
    card(source='explore', created_at=datetime(2026, 11, 2, tzinfo=timezone.utc)).validate()


def test_copy_cap_and_watch_notes(tmp_path):
    assert card().copy_status() == (True, None)
    ok, why = card(est_cost_usd=str(AGENTIC_CASH_CAP_USD + 1)).copy_status()
    assert not ok and '$1,200' in why
    watch = card(source='watch', side=None, quantity=None, est_cost_usd=None, max_loss_usd=None, opinion='Interesting franchise.')
    assert watch.copy_status()[0] is False


def test_watch_limit_five_per_day(tmp_path):
    store = CardStore(tmp_path / 'cards' / 'cards.db')
    for i in range(5):
        store.add(card(id=f'w{i}', source='watch', side=None, quantity=None, est_cost_usd=None, max_loss_usd=None))
    with pytest.raises(CardError, match='WATCH_LIMIT'):
        store.add(card(id='w5', source='watch', side=None, quantity=None, est_cost_usd=None, max_loss_usd=None))


def test_answer_journal_ack_and_record_from_journal(tmp_path):
    store = CardStore(tmp_path / 'cards' / 'cards.db')
    assert store.add(card()) == {'status': 'NO_RECORD_YET'}
    with pytest.raises(CardError):
        store.answer('c1', 'paper_only', at=NOW, by='agent')
    store.answer('c1', 'may_copy_live', at=NOW)
    with pytest.raises(CardError, match='ALREADY_ANSWERED'):
        store.answer('c1', 'skip', at=NOW)
    view = store.view()
    assert view['cards'][0]['answer']['answer'] == 'may_copy_live' and view['cards'][0]['label'] == LABEL
    ack = view['acks'][0]
    assert (ack['ticker'], ack['side'], ack['quantity'], ack['status']) == ('SOXX', 'buy', '1.5', 'DECLARED_NOT_ENFORCED')
    store.record_outcome('c1', at=NOW + timedelta(days=9), pnl_usd='-40.00', premium_in_usd='0', premium_out_usd='0')
    rec = store.add(card(id='c2'))
    assert rec['status'] == 'RECORDED' and rec['fires'] == 1 and rec['losses'] == 1
    assert [j['event'] for j in reversed(store.view()['journal'])] == ['issued', 'answered', 'outcome', 'issued']


def test_uncopyable_card_cannot_be_answered_live(tmp_path):
    store = CardStore(tmp_path / 'cards' / 'cards.db')
    store.add(card(est_cost_usd='5000'))
    with pytest.raises(CardError, match='NOT_COPYABLE'):
        store.answer('c1', 'may_copy_live', at=NOW)


def test_expired_card_cannot_be_answered(tmp_path):
    store = CardStore(tmp_path / 'cards' / 'cards.db')
    store.add(card(expires_at=NOW))
    with pytest.raises(CardError, match='EXPIRED'):
        store.answer('c1', 'skip', at=NOW)


def test_read_view_never_creates(tmp_path):
    assert read_view(tmp_path / 'none' / 'cards.db')['exists'] is False
    assert not (tmp_path / 'none').exists()


def test_inbox_page_separates_sources_and_shows_no_official_pnl(tmp_path):
    from agents.desk.inbox_page import render
    store = CardStore(tmp_path / 'cards' / 'cards.db')
    store.add(card())
    store.add(card(id='w1', source='watch', ticker='MRNA', side=None, quantity=None, est_cost_usd=None, max_loss_usd=None,
                   opinion='Platform company; outcome depends on pipeline results.'))
    html = render({'card_inbox': store.view(), 'inbox_csrf': 'tok'})
    assert html.index('From the registered rule') < html.index('SOXX') < html.index('Watch notes') < html.index('MRNA')
    assert 'No record yet' in html and 'AI opinion' in html and 'NOT A RECOMMENDATION' in html
    assert 'value="may_copy_live" disabled' in html          # live copy stays off
    assert 'vs start' not in html and 'Portfolio value' not in html


def test_frontdoor_records_an_answer_and_refuses_live_copy(tmp_path, monkeypatch):
    import re
    from urllib.error import HTTPError
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
    import agents.cards as cards
    import test_dashboard
    from test_dashboard import serving, read
    from test_inbox_lanes import setup_runtime
    from agents.desk.frontdoor import make_server
    monkeypatch.setattr(test_dashboard, 'make_server', make_server)
    target = tmp_path / 'diag' / 'cards' / 'cards.db'
    monkeypatch.setattr(cards, 'default_path', lambda _official: target)
    inbox, _ = setup_runtime(tmp_path)
    CardStore(target).add(card(created_at=datetime.now(timezone.utc)))
    with serving(inbox) as url:
        page = read(url + '/inbox')
        token = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        assert "form-action 'self'" in urlopen(url + '/inbox').headers['Content-Security-Policy']
        with pytest.raises(HTTPError) as live:
            urlopen(Request(url + '/inbox/answer', data=urlencode({'csrf': token, 'card': 'c1', 'answer': 'may_copy_live'}).encode()))
        assert live.value.code == 409
        with pytest.raises(HTTPError) as bad:
            urlopen(Request(url + '/inbox/answer', data=urlencode({'csrf': 'nope', 'card': 'c1', 'answer': 'skip'}).encode()))
        assert bad.value.code == 403
        urlopen(Request(url + '/inbox/answer', data=urlencode({'csrf': token, 'card': 'c1', 'answer': 'paper_only'}).encode()))
        assert 'You answered: <strong>Paper only' in read(url + '/inbox')
