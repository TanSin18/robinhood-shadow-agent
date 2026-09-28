"""Strict deterministic gateway. No model or arbitrary RPC access is exposed."""
import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from broker.base import BrokerError
from broker.policy import Stage1ToolPolicy
from broker.read_contracts import SCHEMAS, structural


class CapabilityError(BrokerError):
    pass


def _tool_value(tool, name):
    if isinstance(tool, dict):
        return tool.get(name)
    return getattr(tool, name, None)


def _direct_payload(result):
    if hasattr(result, 'model_dump'):
        result = result.model_dump(mode='json', by_alias=True)
    if not isinstance(result, dict):
        raise BrokerError('Invalid read payload')
    if result.get('isError'):
        raise BrokerError('Read provider returned an error')
    payload = result.get('structuredContent', result.get('structured_content'))
    if payload is None:
        texts=[]
        for content in result.get('content', []):
            if hasattr(content, 'model_dump'):
                content=content.model_dump(mode='json')
            if isinstance(content,dict) and content.get('type')=='text':
                texts.append(content.get('text',''))
        if len(texts)!=1: raise BrokerError('Missing structured read evidence')
        try: payload=json.loads(texts[0])
        except ValueError: raise BrokerError('Invalid structured read evidence') from None
    if not isinstance(payload,dict) or not isinstance(payload.get('data'),dict):
        raise BrokerError('Invalid read payload')
    return payload


class EffectiveReadGateway:
    """The application's exact eleven-tool capability over the proxy client."""

    def __init__(
        self,
        client,
        config,
        incident_handler,
        clock=None,
        evidence_cache=None,
        *,
        max_agentic_cash_usd,
        snapshot_handler=None,
    ):
        self.client=client
        self.config=config
        self.incident_handler=incident_handler
        self.clock=clock or (lambda: datetime.now().astimezone())
        self.evidence_cache=evidence_cache
        try:
            self.max_agentic_cash_usd=Decimal(str(max_agentic_cash_usd))
        except (ArithmeticError,ValueError):
            raise ValueError('max_agentic_cash_usd must be finite and non-negative') from None
        if not self.max_agentic_cash_usd.is_finite() or self.max_agentic_cash_usd < 0:
            raise ValueError('max_agentic_cash_usd must be finite and non-negative')
        self.snapshot_handler=snapshot_handler
        self.contracts={}
        self.evidence=None
        self._ready=False

    def _fail(self, code, message=None):
        self.incident_handler(code)
        raise CapabilityError(message or code)

    def preflight(self, *, scope_path):
        tools=self.client.list_remote_tools()
        catalog=[]
        by_name={}
        for tool in tools:
            name=_tool_value(tool,'name')
            input_schema=_tool_value(tool,'inputSchema')
            if input_schema is None:
                input_schema=_tool_value(tool,'input_schema')
            if not isinstance(name,str) or not isinstance(input_schema,dict) or name in by_name:
                self._fail('UNEXPECTED_CAPABILITY')
            by_name[name]=input_schema
            catalog.append({'name':name,'inputSchema':structural(input_schema)})
        for name, expected in SCHEMAS.items():
            if name not in by_name or structural(by_name[name]) != expected:
                self._fail('UNEXPECTED_CAPABILITY')
        catalog_hash=hashlib.sha256(
            json.dumps(sorted(catalog,key=lambda item:item['name']),sort_keys=True,separators=(',',':')).encode()
        ).hexdigest()
        account_payload=self._read('get_accounts',{})
        account=self._verify_account(account_payload['data'], scope_path)
        self.rhs_account_number=account.get('rhs_account_number')
        if scope_path == 'full_scope_bounded_cash_fallback':
            portfolio_payload=self._read('get_portfolio',{
                'account_number':self.config.risk.agentic_account_id,
            })
            bounds=self._verify_bounded_cash(portfolio_payload['data'])
        else:
            bounds={
                'status':'NOT_REQUIRED_FOR_READ_ONLY_SCOPE',
                'checked_fields':[],
            }
        self._ready=True
        self.evidence={
            'remote_catalog_hash':catalog_hash,
            'remote_tool_count':len(catalog),
            'effective_read_tools':sorted(SCHEMAS),
            'effective_write_tool_count':0,
            'scope_path':scope_path,
            'account_bounds':bounds,
        }
        return dict(self.evidence)

    def _verify_account(self, data, scope_path):
        accounts=data.get('accounts')
        if not isinstance(accounts,list):
            self._fail('STAGE1_AGENTIC_ACCOUNT_UNVERIFIED')
        matches=[account for account in accounts if isinstance(account,dict) and account.get('account_number')==self.config.risk.agentic_account_id]
        if len(matches)!=1 or matches[0].get('agentic_allowed') is not True:
            self._fail('STAGE1_AGENTIC_ACCOUNT_UNVERIFIED')
        account=matches[0]
        if scope_path not in {'provider_read_only_scope','full_scope_bounded_cash_fallback'}:
            self._fail('STAGE1_OAUTH_SCOPE_UNVERIFIED')
        return account

    def _verify_bounded_cash(self, portfolio):
        buying_power=portfolio.get('buying_power')
        if not isinstance(buying_power,dict):
            self._fail('AGENTIC_ACCOUNT_OUTSIDE_BOUNDS')
        try:
            cash=Decimal(str(portfolio.get('cash')))
            buying=Decimal(str(buying_power.get('buying_power')))
            unleveraged=Decimal(str(buying_power.get('unleveraged_buying_power')))
        except (ArithmeticError,ValueError):
            self._fail('AGENTIC_ACCOUNT_OUTSIDE_BOUNDS')
        values=(cash,buying,unleveraged)
        if (
            any(not value.is_finite() or value < 0 for value in values)
            or cash > self.max_agentic_cash_usd
            or buying != cash
            or unleveraged != cash
        ):
            self._fail('AGENTIC_ACCOUNT_OUTSIDE_BOUNDS')
        if self.snapshot_handler is not None:
            self.snapshot_handler({
                'cash':cash,
                'buying_power':buying,
                'unleveraged_buying_power':unleveraged,
            })
        return {
            'status':'VERIFIED',
            'checked_fields':['cash','buying_power','unleveraged_buying_power'],
        }

    def call(self, tool, arguments):
        Stage1ToolPolicy().authorize(tool)
        if not self._ready:
            raise CapabilityError('Gateway requires preflight')
        # Reuse the mature argument policy without granting its transport authority.
        validator=ReadGateway(None,self.config,self.incident_handler,self.clock)
        validator.contracts=self.contracts
        validator.rhs_account_number=getattr(self,'rhs_account_number',None)
        args=validator.validate(tool,arguments)
        payload=self._read(tool,args)
        return {**payload,'tool':tool,'arguments':dict(args)}

    def _read(self, tool, args):
        from data.evidence import EvidenceEnvelope
        payload=_direct_payload(self.client.call_read(tool,args))
        fetched=self.clock()
        envelope=EvidenceEnvelope.from_payload(
            source_id=f'robinhood-mcp:{tool}',
            payload=payload,
            observed_at=fetched,
            effective_at=fetched,
            fetched_at=fetched,
        )
        if self.evidence_cache is not None and tool not in {'get_equity_orders','get_option_orders','get_crypto_orders'}:
            self.evidence_cache.put(envelope)
        return {
            **payload,
            'source_id':envelope.source_id,
            'content_hash':envelope.content_hash,
            'observed_at':envelope.observed_at.isoformat(),
            'effective_at':envelope.effective_at.isoformat(),
            'fetched_at':envelope.fetched_at.isoformat(),
        }

    def register_contract(self, contract):
        validator=ReadGateway(None,self.config,self.incident_handler,self.clock)
        validator.contracts=self.contracts
        validator.register_contract(contract)
        self.contracts=validator.contracts


def inventory(transport, thread_id):
    servers=[]; cursor=None; seen=set()
    for _ in range(8):
        params={'threadId':thread_id,'detail':'toolsAndAuthOnly'}
        if cursor: params['cursor']=cursor
        page=transport.request('mcpServerStatus/list',params,timeout=30)
        if not isinstance(page.get('data'),list): raise CapabilityError('Malformed capability inventory')
        servers.extend(page['data']); cursor=page.get('nextCursor')
        if not cursor: return servers
        if not isinstance(cursor,str) or cursor in seen: break
        seen.add(cursor)
    raise CapabilityError('Unbounded capability inventory')


class ReadGateway:
    def __init__(self,transport,config,incident_handler,clock):
        self.transport,self.config,self.incident_handler,self.clock=transport,config,incident_handler,clock
        self.thread_id=None; self.contracts={}; self.evidence=None

    def deny(self):
        self.incident_handler('UNEXPECTED_CAPABILITY')
        raise CapabilityError('Read capability denied')

    def preflight(self,thread_id):
        self.thread_id=None
        try:
            active=[s for s in inventory(self.transport,thread_id) if not (s.get('runtimeStatus')=='disabled' and s.get('tools')=={})]
            if len(active)!=1: self.deny()
            server=active[0]
            if server.get('name')!='robinhood-trading' or server.get('authStatus')!='oAuth' or server.get('runtimeStatus') not in {'starting','connected'}: self.deny()
            if set(server.get('tools',{}))!=set(SCHEMAS): self.deny()
            for name,expected in SCHEMAS.items():
                if structural(server['tools'][name].get('inputSchema'))!=expected: self.deny()
            self.thread_id=thread_id
            self.check_notifications()
            self.transport.event_guard=lambda event:self.check_event(event)
            self.evidence={'tools':sorted(SCHEMAS),'schema_hash':hashlib.sha256(json.dumps(SCHEMAS,sort_keys=True).encode()).hexdigest(),'same_session':True,'runtime_status':server['runtimeStatus']}
            return self.evidence
        except CapabilityError:
            self.incident_handler('UNEXPECTED_CAPABILITY'); raise

    def check_event(self,event):
        from agents.isolated_session import validate_notification
        try: validate_notification(event,collector=True)
        except CapabilityError: self.deny()

    def check_notifications(self):
        if getattr(self.transport,'denied_requests',False): self.deny()
        queue=getattr(self.transport,'notifications',[])
        while queue: self.check_event(queue.pop(0))

    def validate(self,tool,args):
        if tool not in SCHEMAS or not isinstance(args,dict): self.deny()
        spec=SCHEMAS[tool]; props=spec.get('properties',{})
        if set(args)-set(props) or set(spec.get('required',[]))-set(args): self.deny()
        for key,value in args.items():
            if key in {'symbols','instrument_ids'}:
                if not isinstance(value,list) or not 1<=len(value)<= (10 if tool=='get_equity_historicals' else 20) or any(not isinstance(v,str) for v in value): self.deny()
            elif not isinstance(value,str) or not 1<=len(value)<=1024: self.deny()
        if 'account_number' in args and args['account_number']!=self.config.risk.agentic_account_id: self.deny()
        if 'rhs_account_number' in args and args['rhs_account_number']!=getattr(self,'rhs_account_number',None): self.deny()
        if tool in {'get_equity_orders','get_option_orders','get_crypto_orders'}:
            account_key='rhs_account_number' if tool=='get_crypto_orders' else 'account_number'
            allowed={account_key,'order_id'} if 'order_id' in args else {account_key,'created_at_gte','cursor'}
            if set(args)-allowed: self.deny()
            if 'created_at_gte' in args:
                try:
                    start=datetime.fromisoformat(args['created_at_gte'].replace('Z','+00:00'))
                    if start.tzinfo is None or start>self.clock(): self.deny()
                except (ValueError,TypeError): self.deny()
        for symbol in args.get('symbols',[]):
            if symbol not in self.config.risk.instrument_whitelist: self.deny()
        if tool=='get_option_quotes' and any(i not in self.contracts for i in args['instrument_ids']): self.deny()
        if tool=='get_option_chains' and (set(args)!={'underlying_symbol'} or args['underlying_symbol'] not in self.config.risk.instrument_whitelist): self.deny()
        if tool=='get_option_instruments':
            if 'ids' in args:
                if set(args)!={'ids'} or any(i not in self.contracts for i in args['ids'].split(',')): self.deny()
            else:
                if set(args)-{'chain_symbol','expiration_dates','state','tradability','cursor'} or args.get('chain_symbol') not in self.config.risk.instrument_whitelist or args.get('state')!='active' or args.get('tradability')!='tradable': self.deny()
                dates=args.get('expiration_dates','').split(',')
                if not 1<=len(dates)<=2: self.deny()
                try:
                    if any(not 7 <= (datetime.fromisoformat(d).date()-self.clock().date()).days <= 45 for d in dates): self.deny()
                except ValueError: self.deny()
        if tool=='get_equity_historicals':
            try:
                start=datetime.fromisoformat(args['start_time'].replace('Z','+00:00')); end=datetime.fromisoformat(args['end_time'].replace('Z','+00:00'))
                if start.tzinfo is None or end.tzinfo is None or not start<end<=self.clock() or end-start>timedelta(days=550): self.deny()
                if args.get('interval')!='day' or args.get('bounds')!='regular' or args.get('adjustment_type')!='split': self.deny()
            except (ValueError,KeyError,TypeError): self.deny()
        return args

    def call(self,tool,arguments):
        args=self.validate(tool,arguments)
        if self.thread_id is None: raise CapabilityError('Gateway requires preflight')
        self.check_notifications()
        self.preflight(self.thread_id)
        response=self.transport.request('mcpServer/tool/call',{'threadId':self.thread_id,'server':'robinhood-trading','tool':tool,'arguments':args},timeout=30)
        self.check_notifications()
        if response.get('isError'): raise BrokerError('Read provider returned an error')
        payload=response.get('structuredContent')
        if payload is None:
            texts=[c.get('text','') for c in response.get('content',[]) if c.get('type')=='text']
            if len(texts)!=1: raise BrokerError('Missing structured read evidence')
            try: payload=json.loads(texts[0])
            except ValueError: raise BrokerError('Invalid structured read evidence') from None
        if not isinstance(payload,dict) or not isinstance(payload.get('data'),dict): raise BrokerError('Invalid read payload')
        return {**payload,'tool':tool,'arguments':dict(args),'observed_at':self.clock().isoformat()}

    def register_contract(self,contract):
        try:
            UUID(contract['id'])
            if contract['chain_symbol'] not in self.config.risk.instrument_whitelist or Decimal(contract['trade_value_multiplier'])!=100 or contract['type'] not in {'call','put'} or Decimal(contract['strike_price'])<=0: raise ValueError()
            datetime.fromisoformat(contract['expiration_date'])
        except (ValueError,KeyError,ArithmeticError): raise BrokerError('Invalid option metadata') from None
        self.contracts[contract['id']]=contract
