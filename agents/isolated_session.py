"""Installed app-server sessions; metadata is checked before any model turn."""
import json
import os
from pathlib import Path
import re
import time
import tomllib
import hashlib
import shutil

from agents.rpc_transport import RpcTransport
from broker.read_gateway import CapabilityError, SCHEMAS, inventory

# Where the ChatGPT app has shipped the Codex executable. The app update of 2026-10-02 moved it from the first to the second.
CODEX_LOCATIONS=('/Applications/ChatGPT.app/Contents/Resources/codex','/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex')

def find_codex(executable=None):
    """An explicit path, else PATH, else the first known location that is a file. None when it is nowhere."""
    return executable or shutil.which('codex') or next((p for p in CODEX_LOCATIONS if Path(p).is_file()),None)

def require_codex(executable=None):
    found=find_codex(executable)
    if not found or not Path(found).is_file():
        # The same error type a missing executable raised before this change, with a message that says what was checked.
        raise FileNotFoundError('CODEX_EXECUTABLE_NOT_FOUND: not on PATH and not at '+' or '.join(CODEX_LOCATIONS))
    return found

def cli_identity(executable=None):
    path=Path(require_codex(executable)).resolve()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(executable, *, collector=False, model=None):
    # Image viewing is switched off with features.view_image: codex-cli 0.159.0 ignores the older tools.view_image key and
    # says so in a configWarning, which validate_notification treats as an unexpected capability. No warning is tolerated.
    # Empty maps merge with user config. Disable each inherited server explicitly.
    config_path=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'config.toml'
    cfg=tomllib.loads(config_path.read_text()) if config_path.exists() else {}
    names=set(cfg.get('mcp_servers',{})) | {'robinhood-trading'}
    if any(not re.fullmatch(r'[A-Za-z0-9_-]+',n) for n in names): raise CapabilityError('Unsupported inherited server name')
    settings=['features.apps=false','features.plugins=false','features.shell_tool=false','features.unified_exec=false','features.multi_agent=false','features.tool_suggest=false','project_doc_max_bytes=0','features.view_image=false','web_search="disabled"','model_reasoning_effort="low"']
    settings += [f'mcp_servers.{name}.enabled=false' for name in sorted(names)]
    if collector:
        settings += ['mcp_servers.robinhood-trading.enabled=true','mcp_servers.robinhood-trading.url="https://agent.robinhood.com/mcp/trading"','mcp_servers.robinhood-trading.enabled_tools='+json.dumps(sorted(SCHEMAS))]
    if model: settings += ['model='+json.dumps(model)]
    return [executable,'app-server','--strict-config',*sum((['-c',s] for s in settings),[])]


def start(transport,model=None):
    transport.request('initialize',{'clientInfo':{'name':'shadow_runtime','version':'2'},'capabilities':{'experimentalApi':True}},timeout=30)
    transport.send({'method':'initialized'})
    # Process-local only: do not change the user's saved remote-control preference.
    remote=transport.request('remoteControl/disable',{'ephemeral':True},timeout=30)
    if remote.get('status')!='disabled': raise CapabilityError('Remote access to worker is not disabled')
    params={'ephemeral':True,'cwd':transport.directory.name,'approvalPolicy':'never','sandbox':'read-only','environments':[]}
    if model: params['model']=model
    return transport.request('thread/start',params,timeout=30)['thread']['id']


def verify_inference_inventory(transport,thread):
    servers=inventory(transport,thread)
    if any(s.get('runtimeStatus')!='disabled' or s.get('tools')!={} for s in servers):
        raise CapabilityError('Inference has an unexpected MCP capability')
    for event in getattr(transport,'notifications',[]): validate_notification(event)
    if getattr(transport,'denied_requests',False): raise CapabilityError('Unexpected server request')
    transport.event_guard=validate_notification
    return {'same_session':True,'tools':[],'remote_control':'disabled'}


BENIGN_NOTIFICATIONS={'thread/started','thread/status/changed','turn/started','item/agentMessage/delta','item/reasoning/summaryTextDelta','item/reasoning/summaryPartAdded','item/reasoning/textDelta','account/rateLimits/updated','deprecationNotice','warning'}

def validate_notification(event, *, collector=False):
    method=event.get('method'); p=event.get('params',{})
    if 'id' in event: raise CapabilityError('Unexpected server request')
    if method=='remoteControl/status/changed' and p.get('status')=='disabled': return
    if method in BENIGN_NOTIFICATIONS: return
    if collector and method=='mcpServer/startupStatus/updated' and p.get('name')=='robinhood-trading' and p.get('status') in {'starting','ready'}: return
    if collector and method=='item/mcpToolCall/progress': return
    if not collector and method in {'item/started','item/completed','thread/tokenUsage/updated','turn/completed'}: return
    label=method if isinstance(method,str) and re.fullmatch(r'[A-Za-z0-9/_-]{1,120}',method) else '<invalid>'
    raise CapabilityError(f'Unexpected capability or protocol notification: {label}')


def collect_turn(transport,thread,turn):
    deadline=time.monotonic()+240; final=None; usage=None
    while time.monotonic()<deadline:
        event=transport.notifications.pop(0) if transport.notifications else transport.read_event(timeout=max(0,deadline-time.monotonic()))
        if 'id' in event: raise CapabilityError('Unexpected permission or tool request')
        method=event.get('method',''); p=event.get('params',{})
        validate_notification(event)
        correlated=method in {'item/started','item/completed','thread/tokenUsage/updated','turn/completed'}
        if correlated and p.get('threadId')!=thread: raise CapabilityError('Missing or wrong session identity')
        if correlated and method!='turn/completed' and p.get('turnId')!=turn: raise CapabilityError('Missing or wrong turn identity')
        if p.get('threadId') not in {None,thread}: raise CapabilityError('Uncorrelated session event')
        if p.get('turnId') not in {None,turn}: raise CapabilityError('Uncorrelated turn event')
        if method in {'item/started','item/completed'}:
            item=p.get('item',{})
            if item.get('type') not in {'userMessage','agentMessage','reasoning'}: raise CapabilityError('Unexpected inference action')
            if method=='item/completed' and item['type']=='agentMessage': final=item.get('text')
        elif method=='thread/tokenUsage/updated':
            u=p['tokenUsage']['last']
            usage={'input_tokens':u['inputTokens'],'cached_input_tokens':u['cachedInputTokens'],'output_tokens':u['outputTokens']}
            if any(type(v)!=int or v<0 for v in usage.values()) or usage['cached_input_tokens']>usage['input_tokens']: raise ValueError('Invalid usage')
        elif method=='turn/completed':
            completed=p.get('turn',{})
            if completed.get('id')!=turn or completed.get('status')!='completed' or completed.get('error'): raise ValueError('Incomplete model turn')
            if final is None or usage is None: raise ValueError('Missing output or usage')
            output=json.loads(final)
            if not isinstance(output,dict): raise ValueError('Invalid structured output')
            return output,usage
        elif method.startswith(('item/command','item/mcp','item/file','item/tool','item/web')):
            raise CapabilityError('Unexpected inference action')
        elif method=='error': raise ValueError('Model protocol error')
    raise TimeoutError('Model turn deadline exceeded')
