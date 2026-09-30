from urllib.error import HTTPError
import pytest
from test_dashboard import serving, read
from test_inbox_lanes import setup_runtime


def test_frontdoor_preserves_legacy_actions_and_readonly_home(tmp_path, monkeypatch):
    from agents.desk.frontdoor import make_server
    import test_dashboard
    monkeypatch.setattr(test_dashboard, 'make_server', make_server)
    inbox, _ = setup_runtime(tmp_path)
    with serving(inbox) as url:
        page = read(url)
        assert 'Preview — view only' not in page  # one navigation, no second banner
        assert 'data-nav="decisions"' in page
        assert 'href="/legacy#decisions"' in page
        assert 'href="/legacy#controls"' in page
        assert '<form' not in page
        legacy = read(url+'/legacy')
        assert 'Approval inbox' in legacy
        assert 'name="csrf"' in legacy
        assert 'href="/legacy#decisions"' in legacy
        assert 'action="/legacy#decisions"' in legacy
        assert 'href="/">Agent Desk home' in legacy
        assert 'legacy-skin' in legacy and 'Checks &amp; charts' in legacy
        assert 'Confirm pause' in read(url+'/control?action=pause')
        for path in ('/room','/portfolio','/money','/scoreboard','/controls','/health'):
            assert 'href="/legacy#decisions"' in read(url+path)
        assert 'font-face' in read(url+'/assets/agent-desk.css')


def test_frontdoor_keeps_origin_and_csrf_checks(tmp_path, monkeypatch):
    from agents.desk.frontdoor import make_server
    import test_dashboard
    from urllib.request import Request, urlopen
    monkeypatch.setattr(test_dashboard, 'make_server', make_server)
    inbox, _ = setup_runtime(tmp_path)
    with serving(inbox) as url:
        for path in ('/control','/decision'):
            with pytest.raises(HTTPError) as error:
                urlopen(Request(url+path, data=b'csrf=bad&action=pause&confirm=yes', headers={'Origin':'https://evil.example'}))
            assert error.value.code == 403
        response=urlopen(url)
        assert "form-action 'none'" in response.headers['Content-Security-Policy']
        response=urlopen(url+'/legacy')
        assert "form-action 'self'" in response.headers['Content-Security-Policy']


def test_frontdoor_legacy_approval_fills_paper_and_control_redirects(tmp_path, monkeypatch):
    import re
    from datetime import datetime, timezone
    from decimal import Decimal
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
    from broker.models import Quote
    from test_risk_engine import make_proposal
    from agents.desk.frontdoor import make_server
    import test_dashboard
    monkeypatch.setattr(test_dashboard, 'make_server', make_server)
    inbox, _ = setup_runtime(tmp_path)
    now=datetime.now(timezone.utc)
    card=inbox.issue(make_proposal(quantity=Decimal('.49')),
        Quote(ticker='VTI',bid=Decimal(100),ask=Decimal('100.20'),timestamp=now),Decimal('.20'),now,now)
    with serving(inbox) as url:
        read(url)
        assert inbox.cards()[0]['status']=='PENDING'
        page=read(url+'/legacy')
        token=re.search('name="csrf" value="([^"]+)"',page)[1]
        response=urlopen(Request(url+'/decision',data=urlencode({'csrf':token,'id':card['id'],'decision':'YES'}).encode(),headers={'Origin':url}))
        assert '/legacy#decisions' in response.url
        assert inbox.cards()[0]['status']=='YES'
        assert Decimal(inbox.state('A','with_approvals')['settled_cash'])<500
        response=urlopen(Request(url+'/control',data=urlencode({'csrf':token,'action':'pause','confirm':'yes'}).encode(),headers={'Origin':url}))
        assert '/legacy#controls' in response.url
        assert (inbox.path.parent/'STOP_TRADING').exists()
