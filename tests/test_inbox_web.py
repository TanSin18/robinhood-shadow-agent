import threading
import re
from datetime import datetime, timezone
from decimal import Decimal
import urllib.error
import urllib.request
from urllib.parse import urlencode

from test_inbox_lanes import setup_runtime
from test_risk_engine import make_proposal
from broker.models import Quote


def test_yes_button_records_decision_and_public_trace_masks_account(tmp_path):
    from agents.inbox_web import make_server
    inbox,_=setup_runtime(tmp_path)
    now=datetime.now(timezone.utc)
    card=inbox.issue(make_proposal(quantity=Decimal('.49')),Quote(ticker='VTI',bid=Decimal(100),ask=Decimal('100.20'),timestamp=now),Decimal('.20'),now,now)
    server=make_server(inbox,port=0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}'
    try:
        page=urllib.request.urlopen(url).read().decode()
        csrf=re.search('name="csrf" value="([^"]+)"',page).group(1)
        result=urllib.request.urlopen(urllib.request.Request(url+'/decision',data=urlencode({'csrf':csrf,'id':card['id'],'decision':'YES'}).encode(),headers={'Origin':url})).read().decode()
        assert 'YES' in result
        assert inbox.cards()[0]['status']=='YES'
        assert Decimal(inbox.state('A','with_approvals')['settled_cash'])<500
        trace=urllib.request.urlopen(url+'/trace/'+card['id']).read().decode()
        assert 'agentic-1' not in trace
        assert '***ic-1' in trace
    finally:
        server.shutdown();server.server_close();thread.join()


def test_local_page_and_origin_csrf_defenses(tmp_path):
    from agents.inbox_web import make_server
    inbox,_ = setup_runtime(tmp_path)
    server = make_server(inbox, port=0)
    thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    url=f'http://127.0.0.1:{server.server_port}'
    try:
        assert 'Approval inbox' in urllib.request.urlopen(url).read().decode()
        request=urllib.request.Request(url+'/decision',data=urlencode({'id':'bad','decision':'YES'}).encode(),headers={'Origin':'https://evil.test'})
        try:
            urllib.request.urlopen(request)
            raise AssertionError('cross-origin request accepted')
        except urllib.error.HTTPError as error:
            assert error.code == 403
        request=urllib.request.Request(url,headers={'Host':'evil.test'})
        try:
            urllib.request.urlopen(request)
            raise AssertionError('host accepted')
        except urllib.error.HTTPError as error:
            assert error.code==403
    finally:
        server.shutdown();server.server_close();thread.join()


def test_exact_configured_tailnet_host_and_https_origin_are_allowed(tmp_path):
    from agents.inbox_web import make_server
    inbox, config = setup_runtime(tmp_path)
    server = make_server(inbox, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    local = f'http://127.0.0.1:{server.server_port}'
    external = config.notifications.dashboard_base_url
    host = external.removeprefix('https://')
    try:
        request = urllib.request.Request(local, headers={'Host': host})
        page = urllib.request.urlopen(request).read().decode()
        asset = urllib.request.Request(
            local + '/assets/decision-room.js',
            headers={'Host': host, 'Origin': external},
        )
        with urllib.request.urlopen(asset) as response:
            assert response.status == 200
            assert 'text/javascript' in response.headers['Content-Type']
            assert b'ShadowDecisionRoom' in response.read()
        denied = urllib.request.Request(
            local + '/assets/decision-room.js',
            headers={'Host': 'unconfigured.tailnet.test:8443'},
        )
        try:
            urllib.request.urlopen(denied)
            raise AssertionError('unconfigured host accepted')
        except urllib.error.HTTPError as error:
            assert error.code == 403
        csrf = re.search('name="csrf" value="([^"]+)"', page).group(1)
        request = urllib.request.Request(
            local + '/control',
            data=urlencode({'csrf': csrf, 'action': 'pause', 'confirm': 'yes'}).encode(),
            headers={'Host': host, 'Origin': external},
        )
        assert urllib.request.urlopen(request).status == 200
    finally:
        server.shutdown();server.server_close();thread.join()
