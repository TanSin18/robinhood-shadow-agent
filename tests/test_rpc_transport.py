import sys

import pytest


def test_rpc_correlates_notifications_and_denies_server_requests():
    from agents.rpc_transport import RpcTransport
    script = '''import sys,json
r=json.loads(sys.stdin.readline())
print(json.dumps({'method':'progress','params':{}}),flush=True)
print(json.dumps({'id':'ask','method':'approval','params':{}}),flush=True)
denied=json.loads(sys.stdin.readline())
print(json.dumps({'id':r['id'],'result':{'denied':denied['error']['code']}}),flush=True)
'''
    with RpcTransport([sys.executable, '-u', '-c', script]) as rpc:
        assert rpc.request('ping', {}, timeout=2) == {'denied': -32601}
        assert rpc.notifications == [{'method': 'progress', 'params': {}}]


@pytest.mark.parametrize('reply', [
    'not-json', '{}', '{"id":999,"result":{}}',
    '{"id":1,"error":{"message":"sensitive provider error"}}',
    '{"id":1}', '{"id":1,"result":{},"error":{}}',
])
def test_rpc_fails_closed_on_invalid_response(reply):
    from agents.rpc_transport import RpcTransport, ProtocolError
    script = f'import sys;sys.stdin.readline();print({reply!r},flush=True)'
    with RpcTransport([sys.executable, '-u', '-c', script]) as rpc:
        with pytest.raises(ProtocolError) as error:
            rpc.request('ping', {}, timeout=2)
        assert 'sensitive provider' not in str(error.value)
        assert rpc.process.poll() is not None


def test_rpc_timeout_terminates_child():
    from agents.rpc_transport import RpcTransport, ProtocolError
    with RpcTransport([sys.executable, '-u', '-c', 'import time;time.sleep(10)']) as rpc:
        with pytest.raises(ProtocolError, match='timeout'):
            rpc.request('ping', {}, timeout=.05)
        assert rpc.process.poll() is not None


def test_rpc_rejects_oversized_line():
    from agents.rpc_transport import RpcTransport, ProtocolError
    with RpcTransport([sys.executable, '-u', '-c', "import sys;sys.stdin.readline();print('x'*5000,flush=True)"], max_line_bytes=1024) as rpc:
        with pytest.raises(ProtocolError, match='limit'):
            rpc.request('ping', {}, timeout=2)
