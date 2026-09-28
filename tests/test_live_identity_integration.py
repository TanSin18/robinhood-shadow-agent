from datetime import datetime, timezone
import pytest
from agents.daily_cycle import market_snapshot
from test_inbox_lanes import setup_runtime

NOW = datetime(2026, 9, 28, 14, tzinfo=timezone.utc)
ID = '11111111-1111-4111-8111-111111111111'

def records(config):
    return [
        {'tool':'get_accounts','data':{'accounts':[{'account_number':config.risk.agentic_account_id,'agentic_allowed':True}]}},
        {'tool':'get_portfolio','arguments':{'account_number':config.risk.agentic_account_id},'data':{}},
        {'tool':'get_equity_quotes','data':{'results':[{'quote':{'symbol':'VTI','bid_price':'100','ask_price':'101','venue_bid_time':NOW.isoformat(),'venue_ask_time':NOW.isoformat()}}]}},
        {'tool':'get_option_chains','arguments':{'underlying_symbol':'VTI'},'source_id':'robinhood-mcp:get_option_chains','content_hash':'a'*64,
         'data':{'chains':[{'symbol':'VTI','underlying_instruments':[{'symbol':'VTI','instrument':f'https://api.robinhood.com/instruments/{ID}/'}]}]}},
    ]

def test_live_quote_without_id_uses_matching_recorded_chain_identity(tmp_path):
    _, cfg=setup_runtime(tmp_path)
    reads=records(cfg)
    snapshot=market_snapshot(reads,cfg,NOW,require_live_identity=True)
    assert set(snapshot['quotes'])=={'VTI'}
    assert snapshot['quotes']['VTI'].bid==100
    assert snapshot['exclusions']==[]
    assert snapshot['corporate_action_audit'][0]['source_hash']=='a'*64
    assert 'instrument_id' not in reads[2]['data']['results'][0]['quote']

def test_observed_live_chain_internal_url_and_blank_underlying_symbol(tmp_path):
    _,cfg=setup_runtime(tmp_path); reads=records(cfg)
    reads[3]['data']['chains'][0]['underlying_instruments']=[{
        'symbol':'','instrument':f'http://edge-internal.brokeback-shard-router.region.rh/instruments/{ID}/'}]
    snapshot=market_snapshot(reads,cfg,NOW,require_live_identity=True)
    assert set(snapshot['quotes'])=={'VTI'}
    assert snapshot['corporate_action_audit'][0]['permanent_security_id']==ID

@pytest.mark.parametrize('change', ['wrong_symbol','conflict','wrong_host','missing_source'])
def test_identity_evidence_must_be_unambiguous_and_provenanced(tmp_path,change):
    _,cfg=setup_runtime(tmp_path); reads=records(cfg); chain=reads[3]['data']['chains'][0]
    if change=='wrong_symbol': chain['underlying_instruments'][0]['symbol']='SPY'
    if change=='conflict': chain['underlying_instruments'].append({'symbol':'VTI','instrument':'https://api.robinhood.com/instruments/22222222-2222-4222-8222-222222222222/'})
    if change=='wrong_host': chain['underlying_instruments'][0]['instrument']=f'https://other.example/instruments/{ID}/'
    if change=='missing_source': reads[3].pop('content_hash')
    snapshot=market_snapshot(reads,cfg,NOW,require_live_identity=True)
    assert not snapshot['quotes']
    assert snapshot['exclusions'][0]['reason']=='CORPORATE_ACTION_UNRESOLVED'

def test_collector_finishes_with_new_equity_prices(tmp_path):
    from agents.market_reader import MarketReader
    _,cfg=setup_runtime(tmp_path)
    class Gateway:
        def __init__(self): self.calls=[]
        def call(self,tool,args):
            self.calls.append(tool)
            if tool=='get_accounts': return records(cfg)[0]
            return {'tool':tool,'data':{'results':[],'chains':[]}}
    gateway=Gateway()
    reads=MarketReader(gateway,cfg).collect(NOW,{})
    assert gateway.calls[-1]=='get_equity_quotes'
    assert len([r for r in reads if r['tool']=='get_equity_quotes'])==1

def test_missing_option_identity_cannot_inherit_underlying_equity_id(tmp_path):
    _,cfg=setup_runtime(tmp_path); reads=records(cfg)
    reads[2]['tool']='get_option_quotes'
    snapshot=market_snapshot(reads,cfg,NOW,require_live_identity=True)
    assert not snapshot['quotes']
    assert snapshot['exclusions'][0]['reason']=='CORPORATE_ACTION_UNRESOLVED'

def test_malformed_quote_raises_structured_normalization_failure():
    from data.corporate_actions import quote_with_recorded_identity, CorporateActionError
    with pytest.raises(CorporateActionError):
        quote_with_recorded_identity({'quote':['malformed']},[])

def test_malformed_quote_is_excluded_without_aborting_snapshot(tmp_path):
    _,cfg=setup_runtime(tmp_path); reads=records(cfg)
    reads[2]['data']['results'][0]['quote']=['malformed']
    snapshot=market_snapshot(reads,cfg,NOW,require_live_identity=True)
    assert not snapshot['quotes']
    assert snapshot['exclusions']==[{'instrument':None,'reason':'CORPORATE_ACTION_UNRESOLVED'}]

def test_historical_reads_fit_provider_single_symbol_limit(tmp_path):
    from agents.market_reader import MarketReader
    from broker.base import BrokerError
    _,cfg=setup_runtime(tmp_path)
    class Gateway:
        def call(self,tool,args):
            if tool=='get_accounts': return records(cfg)[0]
            if tool=='get_equity_historicals':
                if len(args['symbols'])>1: raise BrokerError('UPSTREAM_READ_FAILED')
                return {'tool':tool,'data':{'results':[{'symbol':args['symbols'][0],'bars':[]}]}}
            return {'tool':tool,'data':{'results':[],'chains':[]}}
    reads=MarketReader(Gateway(),cfg).collect(NOW,{})
    observed={item['symbol'] for read in reads if read['tool']=='get_equity_historicals' for item in read['data']['results']}
    assert observed==cfg.risk.instrument_whitelist
