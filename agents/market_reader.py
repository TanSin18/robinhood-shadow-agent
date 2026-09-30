"""Code-only collection through the application's direct, read-gated MCP session."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from broker.base import BrokerError


def chunks(items,size=20):
    return [items[i:i+size] for i in range(0,len(items),size)]


class MarketReader:
    def __init__(self,gateway,config):
        self.gateway,self.config=gateway,config
        self.excluded=[]

    def refresh(self,now,equity_symbols,option_ids):
        results=[]
        for symbols in chunks(sorted(set(equity_symbols))):
            results.append(self.gateway.call('get_equity_quotes',{'symbols':symbols}))
        for ids in chunks(sorted(set(option_ids))):
            results.append(self.gateway.call('get_option_quotes',{'instrument_ids':ids}))
        return results

    def collect(self,now,held_contracts,*,account_reads=None):
        g=self.gateway
        if account_reads is None:
            account=g.call('get_accounts',{})
            if not any(a and a.get('account_number')==self.config.risk.agentic_account_id and a.get('agentic_allowed') is True for a in account['data'].get('accounts',[])):
                raise BrokerError('Configured Agentic account not authenticated')
            reads=[account,g.call('get_portfolio',{'account_number':self.config.risk.agentic_account_id}),g.call('get_equity_positions',{'account_number':self.config.risk.agentic_account_id})]
        else:
            reads=list(account_reads)
        symbols=sorted(self.config.risk.instrument_whitelist)
        from research.strategy_signals import REGISTERED_DISCOVERY_UNIVERSE
        if len(symbols)>len(REGISTERED_DISCOVERY_UNIVERSE) or not set(symbols)<=REGISTERED_DISCOVERY_UNIVERSE:
            raise BrokerError('Universe exceeds reviewed discovery bound')
        reads+=self.refresh(now,symbols,[])
        # The live provider rejects the 550-day multi-symbol payload; keep each
        # approved history request bounded to one symbol without shortening data.
        for group in chunks(symbols,1):
            reads.append(g.call('get_equity_historicals',{'symbols':group,'start_time':(now-timedelta(days=550)).isoformat(),'end_time':now.isoformat(),'interval':'day','bounds':'regular','adjustment_type':'split'}))
        spots={}
        for read in reads:
            if read['tool']=='get_equity_quotes':
                for item in read['data'].get('results',[]):
                    q=(item or {}).get('quote') or {}
                    if q.get('ask_price'): spots[q['symbol']]=Decimal(q['ask_price'])
        for contract in held_contracts.values(): g.register_contract(contract)
        for symbol in symbols:
            if symbol not in spots: continue
            chains=g.call('get_option_chains',{'underlying_symbol':symbol}); reads.append(chains)
            catalog=chains['data'].get('chains')
            if not isinstance(catalog,list):
                self.excluded.append({'symbol':symbol,'reason':'OPTION_CHAIN_SHAPE_UNAVAILABLE'}); continue
            dates=set()
            for chain in catalog:
                if chain and chain.get('symbol')==symbol:
                    for expiry in chain.get('expiration_dates',[]):
                        if 7<=(datetime.fromisoformat(expiry).date()-now.date()).days<=45: dates.add(expiry)
            if not dates: continue
            args={'chain_symbol':symbol,'expiration_dates':','.join(sorted(dates)[:2]),'state':'active','tradability':'tradable'}
            found=[]; cursors=set()
            for _ in range(5):
                response=g.call('get_option_instruments',args)
                for contract in response['data'].get('instruments',[]) or []:
                    if contract and contract.get('chain_symbol')==symbol and contract.get('state')=='active' and contract.get('tradability')=='tradable' and contract.get('type') in {'call','put'} and abs(Decimal(contract['strike_price'])/spots[symbol]-1)<=Decimal('.1'):
                        g.register_contract(contract); found.append(contract)
                cursor=response['data'].get('next')
                if not cursor: break
                if cursor in cursors: raise BrokerError('Repeated option cursor')
                cursors.add(cursor); args={**args,'cursor':cursor}
            # Strike proximity, then expiry and type; never premium-based selection.
            found=sorted({c['id']:c for c in found}.values(),key=lambda c:(abs(Decimal(c['strike_price'])/spots[symbol]-1),c['expiration_date'],c['type']))[:40]
            reads.append({'tool':'get_option_instruments','data':{'instruments':found}})
        option_ids={c['id'] for r in reads if r['tool']=='get_option_instruments' for c in r['data']['instruments']} | set(held_contracts)
        reads+=self.refresh(now,[],sorted(option_ids))
        # Collection can take longer than the freshness limit. Never hand the
        # initial discovery quotes to agents after history/option-chain reads.
        fresh_equities=self.refresh(datetime.now(timezone.utc),symbols,[])
        reads=[read for read in reads if read['tool']!='get_equity_quotes']+fresh_equities
        return reads


class LiveReader:
    def __init__(self,path,config,client=None,executable=None):
        from agents.safety_events import record_incident,safety_stopped
        from broker.proxy_client import BrokerProxyClient
        from broker.read_gateway import EffectiveReadGateway
        from data.evidence import EvidenceCache
        from agents.preregistration import load_phase0_registration
        if safety_stopped(path): raise BrokerError('Safety stop is active')
        if executable is not None:
            raise BrokerError('Codex-session Robinhood authentication is disabled')
        self.client=client or BrokerProxyClient(config.broker_proxy_socket)
        self.path=Path(path).resolve()
        self.config=config
        try:
            self.client.open()
            authorization=self.client.authorization_evidence()
            registration=load_phase0_registration(
                Path(__file__).resolve().parents[1]/'preregistration.yaml'
            )
            self.max_agentic_cash_usd=registration.max_agentic_cash_usd
            self.gateway=EffectiveReadGateway(
                self.client,
                config,
                lambda code:record_incident(
                    path,code,now=datetime.now(timezone.utc),
                    dashboard_base_url=config.notifications.dashboard_base_url,
                ),
                lambda:datetime.now(timezone.utc),
                EvidenceCache(path.parent/'evidence.db'),
                max_agentic_cash_usd=self.max_agentic_cash_usd,
            )
            self.evidence={
                **authorization,
                **self.gateway.preflight(scope_path=authorization['selected_path']),
            }
            self.reader=MarketReader(self.gateway,config)
        except BaseException:
            self.client.close(); raise
    @staticmethod
    def _items(read, *names):
        data=read.get('data') if isinstance(read,dict) else None
        if not isinstance(data,dict): raise BrokerError('BROKER_SNAPSHOT_INCOMPLETE')
        for name in names:
            value=data.get(name)
            if isinstance(value,list): return value
        raise BrokerError('BROKER_SNAPSHOT_INCOMPLETE')
    def collect(self,now,held_contracts):
        from agents.account_tripwire import evaluate_snapshot,TripwireViolation
        from agents.order_history import collect_histories,load_checkpoint,save_checkpoint
        from agents.safety_events import record_incident
        account_number=self.config.risk.agentic_account_id
        try:
            accounts_read=self.gateway.call('get_accounts',{})
            accounts=self._items(accounts_read,'accounts')
            matches=[a for a in accounts if isinstance(a,dict) and a.get('account_number')==account_number and a.get('agentic_allowed') is True]
            if len(matches)!=1 or not matches[0].get('rhs_account_number'):
                raise BrokerError('ORDER_HISTORY_ACCOUNT_UNVERIFIED')
            account=matches[0]
            if account['rhs_account_number']!=getattr(self.gateway,'rhs_account_number',None):
                raise BrokerError('ORDER_HISTORY_ACCOUNT_UNVERIFIED')
            portfolio_read=self.gateway.call('get_portfolio',{'account_number':account_number})
            positions_read=self.gateway.call('get_equity_positions',{'account_number':account_number})
            portfolio=portfolio_read.get('data') or {}
            positions=self._items(positions_read,'positions','results')
            if positions_read['data'].get('next'):
                raise BrokerError('BROKER_SNAPSHOT_INCOMPLETE')
            reads=[accounts_read,portfolio_read,positions_read]
        except Exception:
            record_incident(self.path,'BROKER_SNAPSHOT_INCOMPLETE',now=now,
                            dashboard_base_url=self.config.notifications.dashboard_base_url)
            raise BrokerError('BROKER_SNAPSHOT_INCOMPLETE') from None
        try:
            since,tracked=load_checkpoint(self.path,account)
            histories=collect_histories(self.gateway.call,account,now=now,since=since,tracked=tracked)
        except Exception:
            record_incident(self.path,'ORDER_HISTORY_INCOMPLETE',now=now,
                            dashboard_base_url=self.config.notifications.dashboard_base_url)
            raise BrokerError('ORDER_HISTORY_INCOMPLETE') from None
        try:
            decision=evaluate_snapshot(
                self.path,
                cash=portfolio.get('cash'),
                positions=positions,
                equity_orders=histories['equity'],
                option_orders=histories['option'],
                crypto_orders=histories['crypto'],
                max_agentic_cash_usd=self.max_agentic_cash_usd,
                cycle_id='broker-read-'+now.isoformat(),
                now=now,
                dashboard_base_url=self.config.notifications.dashboard_base_url,
            )
            save_checkpoint(self.path,account,now,histories)
        except TripwireViolation:
            raise
        except Exception:
            record_incident(self.path,'BROKER_SNAPSHOT_INCOMPLETE',now=now,
                            dashboard_base_url=self.config.notifications.dashboard_base_url)
            raise BrokerError('BROKER_SNAPSHOT_INCOMPLETE') from None
        self.evidence['tripwire']={
            'status':decision.status,
            'snapshot_hash':decision.snapshot_hash,
            'change_class':decision.change_class,
        }
        return self.reader.collect(now,held_contracts,account_reads=reads)
    def refresh(self,*args,**kwargs): return self.reader.refresh(*args,**kwargs)
    def close(self): self.client.close()
