"""Metadata-only installed-child check: fake MCP, zero model turns or live reads."""
import json
from pathlib import Path
import sys
import pytest

def test_installed_child_filters_tools_and_denies_unexpected_server(tmp_path):
    from agents.rpc_transport import RpcTransport
    from agents.isolated_session import command,start,verify_inference_inventory
    from broker.read_gateway import CapabilityError,inventory
    executable='/Applications/ChatGPT.app/Contents/Resources/codex'
    assert Path(executable).is_file(), 'Installed Codex is required for runtime isolation evidence'
    script=tmp_path/'fake_mcp.py'; marker=tmp_path/'called'
    script.write_text('''import sys,json
from pathlib import Path
for line in sys.stdin:
 m=json.loads(line)
 if 'id' not in m: continue
 method=m['method']
 if method=='initialize': result={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'fake','version':'1'}}
 elif method=='tools/list': result={'tools':[{'name':n,'description':'Synthetic test tool','inputSchema':{'type':'object','properties':{}}} for n in ['read_quote','place_order']]}
 elif method=='tools/call':
  Path(sys.argv[1]).write_text('CALLED'); result={'content':[]}
 else: result={}
 print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':result}),flush=True)
''')
    base=command(executable)
    settings=['mcp_servers.isolation_test.command='+json.dumps(sys.executable),'mcp_servers.isolation_test.args='+json.dumps([str(script),str(marker)]),'mcp_servers.isolation_test.enabled=true','mcp_servers.isolation_test.enabled_tools=["read_quote"]']
    with RpcTransport(base+sum((['-c',s] for s in settings),[])) as rpc:
        thread=start(rpc)
        servers=inventory(rpc,thread)
        fake=next(s for s in servers if s['name']=='isolation_test')
        assert set(fake['tools'])=={'read_quote'}
        with pytest.raises(CapabilityError): verify_inference_inventory(rpc,thread)
    assert not marker.exists()
    with RpcTransport(base) as rpc:
        thread=start(rpc)
        assert verify_inference_inventory(rpc,thread)['tools']==[]
