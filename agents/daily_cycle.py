from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field

from agents.agent import Agent
from agents.codex_bridge import BridgeResult, CodexBridge, CodexSDKModel, ET
from agents.inbox import PaperInbox
from agents.observability import TraceManager
from agents.operator import MarketSchedule
from agents.run import Runner
from agents.schemas import StrictModel, TradeProposal
from broker.models import Quote
from config.loader import load_config
from prompts.registry import PromptRegistry
from risk.engine import RiskEngine
from research.strategy_signals import ETF_UNIVERSE, evaluate_daily_signals, rank_option_candidates

D = Decimal
READS = ('get_accounts','get_portfolio','get_equity_quotes','get_equity_historicals','get_equity_positions','get_option_chains','get_option_instruments','get_option_quotes')


class NewsFact(StrictModel):
    fact: str
    source_url: str
    observed_at: datetime


class Research(StrictModel):
    summary: str
    compared_symbols: list[str]
    news_checked: bool
    news: list[NewsFact]
    missing_evidence: list[str]


class Pick(StrictModel):
    instrument: str
    side: Literal['buy','sell']
    thesis: str
    good_if: str
    invalidation: str
    confidence: float = Field(ge=0,le=1)


class Decision(StrictModel):
    picks: list[Pick] = Field(max_length=2)
    reason: str


class Critique(StrictModel):
    counterargument: str
    rejected_instruments: list[str]


class RefreshReceipt(StrictModel):
    refreshed: bool


def candidates(snapshot, inbox, config, now):
    result=[]
    for symbol,q in snapshot['quotes'].items():
        if q.halted or (now-q.timestamp).total_seconds()<0:
            continue
        contract=snapshot['contracts'].get(symbol)
        underlying=contract['chain_symbol'] if contract else symbol
        vol=snapshot['vols'].get(underlying)
        if vol is None:
            continue
        lane='B' if contract else 'A'
        state=inbox.state(lane,'agent_alone')
        context=inbox._context(state,q,vol[0],vol[1],now)
        cap=RiskEngine(config.risk).sized_notional(context.account_value,vol[0])
        available=max(D(0),min(context.settled_cash,cap-context.position_values.get(symbol,D(0))))
        unit=q.ask*(100 if contract else 1)
        result.append({'instrument':symbol,'lane':lane,'underlying':underlying,'bid':str(q.bid),'ask':str(q.ask),'quote_time':q.timestamp.isoformat(),'quote_age_seconds':(now-q.timestamp).total_seconds(),'quote_stale':(now-q.timestamp).total_seconds()>config.risk.max_quote_age_seconds,'realized_vol_20d':str(vol[0]),'available_risk_notional':str(available),'max_buy_units':str((available/unit).quantize(D(1) if contract else D('.000001'),rounding=ROUND_DOWN)),'contract':contract})
    return result


def agent_candidate_packet(choices, strategy_signals, held):
    """Keep all equities but only signal-backed or held option identifiers."""
    return [candidate for candidate in choices
            if not candidate.get('quote_stale')
            and (not candidate.get('contract')
                 or candidate['instrument'] in strategy_signals
                 or candidate['instrument'] in held)]


def candidate_decisions(choices, signals, research, decision, critic, missing, results):
    """Map structured cycle outputs to public, lane-scoped candidate states."""
    by_instrument = {
        str(choice['instrument']): choice
        for choice in choices
        if isinstance(choice, dict)
        and choice.get('instrument')
        and choice.get('lane') in {'A', 'B'}
    }
    rows = []

    def add(instrument, state, code, reason, source_refs=(), strategy_signal=None):
        candidate = by_instrument.get(str(instrument))
        if not candidate:
            return
        age = candidate.get('quote_age_seconds')
        rows.append(
            {
                'instrument': str(instrument),
                'lane': candidate['lane'],
                'state': state,
                'reason_code': code,
                'reason': str(reason),
                'strategy_signal': strategy_signal,
                'data_freshness': (
                    f'{age:.0f} seconds old' if isinstance(age, (int, float)) else None
                ),
                'source_refs': list(source_refs),
            }
        )

    for symbol in research.get('compared_symbols') or []:
        add(symbol, 'reviewed', 'research_compared', 'Compared by the Research Agent.')
    for signal in signals or []:
        if not isinstance(signal, dict):
            continue
        instrument = signal.get('instrument')
        add(
            instrument,
            'advanced',
            'strategy_signal',
            'A deterministic strategy signal advanced this candidate.',
            (f'signal:{instrument}',) if instrument else (),
            strategy_signal=(
                str(signal['strategy']) if isinstance(signal.get('strategy'), str) else None
            ),
        )
    for pick in decision.get('picks') or []:
        if isinstance(pick, dict):
            add(
                pick.get('instrument'),
                'proposed',
                'portfolio_pick',
                pick.get('thesis') or 'Proposed by the Portfolio Agent.',
            )
    for symbol in critic.get('rejected_instruments') or []:
        add(symbol, 'rejected', 'critic_rejected', 'Rejected by the Critic.')
    for symbol in missing or []:
        add(
            symbol,
            'blocked',
            'current_quote_missing',
            'Current price evidence was unavailable.',
        )
    for result in results or []:
        if not isinstance(result, dict) or result.get('status') != 'RISK_BLOCKED':
            continue
        reasons = result.get('reasons') if isinstance(result.get('reasons'), list) else []
        reason = ', '.join(str(item) for item in reasons)
        add(
            result.get('ticker') or result.get('instrument'),
            'blocked',
            'risk_blocked',
            reason or 'A deterministic risk rule blocked the proposal.',
        )
    return rows


def realized_volatility(bars):
    filtered = sorted((b for b in bars if b and not b.get('interpolated')), key=lambda b:b['begins_at'])[-21:]
    if len(filtered)<21 or len({b['begins_at'] for b in filtered})<21:
        return None
    closes = [float(b['close_price']) for b in filtered]
    if any(not math.isfinite(x) or x<=0 for x in closes):
        return None
    value = statistics.stdev(math.log(b/a) for a,b in zip(closes,closes[1:]))*math.sqrt(252)
    return D(str(value)) if value>0 else None


def claim_daily_cycle(inbox, now, *, enforce_schedule=True):
    from agents.cycle_lifecycle import CycleLifecycle
    lifecycle=CycleLifecycle(inbox.path)
    try: return bool(lifecycle.acquire(now,scheduled=enforce_schedule))
    finally: lifecycle.close()


def market_snapshot(reads, config, now, *, held_contracts=None, require_live_identity=False):
    from data.corporate_actions import CorporateActionError, normalize_live_quote, quote_with_recorded_identity
    accounts=[a for r in reads if r['tool']=='get_accounts' for a in r.get('data',{}).get('accounts',[]) if a]
    matching=[a for a in accounts if a.get('account_number')==config.risk.agentic_account_id and a.get('agentic_allowed') is True]
    if not matching:
        raise ValueError('configured Agentic account not authenticated')
    portfolios=[r for r in reads if r['tool']=='get_portfolio' and r.get('arguments',{}).get('account_number')==config.risk.agentic_account_id]
    if not portfolios:
        raise ValueError('authenticated portfolio read missing')
    quotes,vols,contracts={}, {}, dict(held_contracts or {})
    exclusions=[]; corporate_action_audit=[]
    closes={}
    benchmark=None
    for r in reads:
        data=r.get('data',{})
        if r['tool']=='get_option_instruments':
            for contract in data.get('instruments',[]) or []:
                if contract and contract.get('state')=='active' and contract.get('tradability')=='tradable' and contract.get('chain_symbol') in config.risk.instrument_whitelist and D(contract['trade_value_multiplier'])==100 and datetime.fromisoformat(contract['expiration_date']).date() >= now.date()+timedelta(days=7):
                    contracts[contract['id']]=contract
        if r['tool']=='get_equity_historicals':
            for item in data.get('results',[]) or []:
                # Never use today's incomplete daily bar or future observations.
                bars=[b for b in item.get('bars',[]) or [] if b and datetime.fromisoformat(b['begins_at']).astimezone(ET).date()<now.astimezone(ET).date()]
                vol=realized_volatility(bars)
                closes[item['symbol']]={datetime.fromisoformat(b['begins_at']).astimezone(ET).date().isoformat():b['close_price'] for b in bars if not b.get('interpolated')}
                if vol is not None:
                    vols[item['symbol']] = (vol,datetime.fromisoformat(max(b['begins_at'] for b in bars)))
        if r['tool'] in {'get_equity_quotes','get_option_quotes'}:
            for item in data.get('results',[]) or []:
                if not item:
                    continue
                if require_live_identity:
                    try:
                        identity_audit = []
                        if r['tool']=='get_equity_quotes':
                            item, identity_audit = quote_with_recorded_identity(item, reads)
                        normalized=normalize_live_quote(item,known_at=now)
                        item=normalized.record
                        corporate_action_audit.extend(identity_audit)
                        corporate_action_audit.extend(normalized.audit)
                    except CorporateActionError as error:
                        raw_quote=item.get('quote') if isinstance(item,dict) else None
                        exclusions.append({'instrument':raw_quote.get('symbol') if isinstance(raw_quote,dict) else None,'reason':error.code})
                        continue
                q=item.get('quote')
                if not q:
                    continue
                symbol=q.get('symbol') or q.get('instrument_id')
                if symbol=='VTI' and item.get('close'):
                    benchmark=item['close']
                if D(q['bid_price'])<=0 or D(q['ask_price'])<=0:
                    continue
                stamp=q.get('updated_at') or min(q['venue_ask_time'],q['venue_bid_time'])
                quotes[symbol]=Quote(ticker=symbol,bid=D(q['bid_price']),ask=D(q['ask_price']),timestamp=datetime.fromisoformat(stamp),halted=q.get('state','active')!='active' or q.get('has_traded',True) is False)
    return {'quotes':quotes,'vols':vols,'contracts':contracts,'benchmark':benchmark,'session_closes':closes,'account_last4':config.risk.agentic_account_id[-4:],'corporate_action_audit':corporate_action_audit,'exclusions':exclusions}


def apply_decision(inbox, config, decision, critic, snapshot, now, cycle_id, *, lifecycle=None, strategy_signals=None):
    results=[]
    seen_lanes=set()
    strategy_signals = None if strategy_signals is None else {str(k): v for k, v in strategy_signals.items()}
    for pick in decision.picks:
        symbol=pick.instrument
        contract=snapshot['contracts'].get(symbol)
        lane='B' if contract else 'A'
        underlying=contract['chain_symbol'] if contract else symbol
        deterministic = strategy_signals.get(symbol) if strategy_signals is not None else None
        if pick.side == 'buy' and strategy_signals is not None and deterministic is None:
            results.append({'status':'REJECTED_NO_STRATEGY_SIGNAL','instrument':symbol});continue
        if lane in seen_lanes or underlying not in config.risk.instrument_whitelist or symbol in critic.rejected_instruments:
            results.append({'status':'REJECTED','instrument':symbol});continue
        seen_lanes.add(lane)
        quote=snapshot['quotes'].get(symbol)
        vol=snapshot['vols'].get(underlying)
        if quote is None or (vol is None and pick.side=='buy') or quote.halted:
            results.append({'status':'MISSING_DATA','instrument':symbol});continue
        if contract and pick.side=='buy' and datetime.fromisoformat(contract['expiration_date']).date()<now.date()+timedelta(days=7):
            results.append({'status':'NEAR_EXPIRY_BUY_BLOCKED','instrument':symbol});continue
        # A verified closing sell does not need historical sizing inputs.
        vol=vol or (None,None)
        state=inbox.state(lane,'agent_alone')
        engine=RiskEngine(config.risk)
        context=inbox._context(state,quote,vol[0],vol[1],now)
        multiplier=100 if contract else 1
        if pick.side=='buy':
            available=min(context.settled_cash,max(D(0),engine.sized_notional(context.account_value,vol[0])-context.position_values.get(symbol,D(0))))
            qty=(available/(quote.ask*multiplier)).quantize(D(1) if contract else D('.000001'),rounding=ROUND_DOWN)
        else:
            qty=context.position_quantities.get(symbol,D(0))
        if qty<=0:
            results.append({'status':'UNAFFORDABLE_OR_UNHELD','instrument':symbol});continue
        identifier=f'{cycle_id}-{lane}'
        thesis = deterministic.get('thesis', pick.thesis) if deterministic else pick.thesis
        good_if = deterministic.get('good_if', pick.good_if) if deterministic else pick.good_if
        invalidation = deterministic.get('invalidation', pick.invalidation) if deterministic else pick.invalidation
        confidence = min(pick.confidence, float(deterministic.get('confidence', pick.confidence))) if deterministic else pick.confidence
        proposal=TradeProposal(proposal_id=identifier,client_order_id=identifier,account_id=config.risk.agentic_account_id,ticker=symbol,asset_class='option' if contract else ('etf' if symbol in ETF_UNIVERSE else 'stock'),side=pick.side,quantity=qty,limit_price=quote.ask if pick.side=='buy' else quote.bid,thesis=thesis,good_if=good_if,invalidation=invalidation,confidence=confidence,horizon_days=20,critic_counterargument=critic.counterargument,prompt_versions={r:f'{r}_hardening_v1' for r in ('research','portfolio','critic')},model_name=config.portfolio_model_name,config_hash=config.config_hash,is_closing=pick.side=='sell',multiplier=multiplier,underlying_ticker=underlying if contract else None,option_strategy=f'long_{contract["type"]}' if contract else None,max_loss_usd=qty*quote.ask*multiplier if contract else None)
        if contract:
            proposal=proposal.model_copy(update={'option_type':contract['type'],'strike':D(contract['strike_price']),'expiry':datetime.fromisoformat(contract['expiration_date']).date()})
        proposal=proposal.model_copy(update={'prompt_versions':{r:f'{r}_hardening_v2' for r in ('research','portfolio','critic')}})
        from agents.rehearsal import RehearsalInbox
        issue=inbox.evaluate_proposal if isinstance(inbox,RehearsalInbox) else inbox.issue
        result=issue(proposal,quote,vol[0],vol[1],now,cycle_id=cycle_id,lifecycle=lifecycle)
        results.append({'instrument':symbol,'status':result['status'],'card_id':result.get('id'),'reasons':result.get('reasons',[])})
    return results


def run_cycle(inbox, config, bridge, now, *, data_mode='live_readonly', clock=None, reader=None, cycle_id=None, lifecycle=None, diagnostic_cap_waiver=False):
    from agents.budget import AIInvocationGate, BudgetAllocator, BudgetUnavailable
    from data.database_role import require_database_role
    from agents.codex_bridge import BudgetExceeded
    from agents.safety_events import safety_stopped
    rehearsal=data_mode=='whatif'
    if diagnostic_cap_waiver and not rehearsal:
        raise ValueError('Cap waiver is diagnostic only')
    if rehearsal:
        from agents.rehearsal import RehearsalInbox
        if not isinstance(inbox,RehearsalInbox) or lifecycle is not None:
            raise ValueError('Isolated rehearsal context required')
        inbox.assert_isolated()
    require_database_role(inbox.path,'whatif' if rehearsal else ('fixture' if data_mode=='fixture' else 'live'))
    if data_mode!='fixture' and not rehearsal:
        with inbox.connect() as db:
            if lifecycle is None or not lifecycle.owns(db,cycle_id): raise ValueError('Live cycle ownership is required')
        if reader is None: raise ValueError('Live cycle requires a deterministic reader')
    reader=reader or FixtureReader(config,now)
    trace=TraceManager(inbox.store,otlp_endpoint=config.observability.otlp_endpoint,viewer_base_url=config.observability.trace_viewer_base_url)
    trace.install_sdk_processor()
    prompts=PromptRegistry(Path(__file__).resolve().parents[1]/'prompts')
    cycle_id=cycle_id or uuid4().hex
    agents=[]
    completed={}
    cost_start=len(inbox.store.read_json('api_costs'))
    budget_allocator=BudgetAllocator(inbox.path)
    phase0_reservations=[]
    clock=clock or (lambda: now if data_mode=='fixture' else datetime.now(timezone.utc))

    def trace_event(event, **payload):
        inbox.store.append_json('local_traces', {
            # Telemetry uses wall-clock receipt time so it does not consume or
            # perturb the injected business clock used for freshness/ownership.
            'trace_id': cycle_id, 'event': event,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'data_mode': data_mode, **payload,
        })

    trace_event('cycle_started', trigger=getattr(lifecycle, 'trigger', 'fixture'))

    def check_owner():
        if rehearsal: inbox.assert_isolated()
        if safety_stopped(inbox.path): raise ValueError('Safety stop is active')
        if lifecycle is not None:
            with inbox.connect() as db:
                if not lifecycle.owns(db,cycle_id): raise ValueError('Cycle ownership lost')

    def finish(result):
        result={**result,'cycle_id':cycle_id,'data_mode':data_mode,'timestamp':now.isoformat(),'agents':agents,'completed_stages':completed}
        result['trigger']=getattr(lifecycle,'trigger','fixture')
        if rehearsal:
            result.update(trigger='rehearsal',parent_official_run_id=inbox.parent_official_run_id)
            result.update(diagnostic_noncompliant=bool(diagnostic_cap_waiver),cap_waiver=bool(diagnostic_cap_waiver))
            result.pop('account_last4',None)
        result['api_cost_estimate_usd']=str(sum((D(c['cost_usd']) for c in inbox.store.read_json('api_costs')[cost_start:]),D(0)))
        if phase0_reservations:
            costs=inbox.store.read_json('api_costs')[cost_start:]
            by_stage={stage:(D(costs[index]['cost_usd']) if index<len(costs) else D(0))
                      for index,stage in enumerate(('research','portfolio','critic'))}
            lane_count=len({row['lane'] for row in phase0_reservations}) or 1
            for row in phase0_reservations:
                budget_allocator.settle(row['id'],actual=by_stage[row['stage']]/lane_count)
        if lifecycle is not None and not lifecycle.finish(cycle_id,result['status'],result,clock()):
            raise ValueError('Cycle ownership lost at completion')
        inbox.store.append_json('run_states',result)
        trace_event('cycle_terminal', payload=result)
        return result

    def run(role, schema, request):
        check_owner()
        model=getattr(config,role+'_model_name')
        name={'research':'Research Agent','portfolio':'Portfolio Agent','critic':'Critic'}[role]
        agents.append(name)
        trace_event('stage_started', role=role, agent=name)
        agent=Agent(name=name,instructions=prompts.load(role,'hardening_v2').text,model=CodexSDKModel(bridge,model),output_type=schema)
        output=Runner.run_sync(agent,json.dumps(request,default=str),max_turns=1).final_output
        completed[role]=output.model_dump(mode='json')
        return output

    held_contracts={}
    for track in ('agent_alone','with_approvals'):
        for t,p in inbox.state('B',track)['positions'].items():
            held_contracts[t]={'id':t,'chain_symbol':p['underlying_ticker'],'expiration_date':p['expiry'],'strike_price':p['strike'],'type':p['option_type'],'trade_value_multiplier':str(p['multiplier']),'state':'active','tradability':'tradable','source':'persisted_paper_contract'}
    check_owner()
    reads=reader.collect(now,held_contracts)
    source_hashes={str(read.get('source_id')):str(read.get('content_hash')) for read in reads
                   if read.get('source_id') and read.get('content_hash')}
    observed_at=clock()
    snapshot=market_snapshot(reads,config,observed_at,held_contracts=held_contracts,require_live_identity=data_mode!='fixture')
    trace_event('data_collected', read_tools=sorted({read['tool'] for read in reads}),
                quote_count=len(snapshot['quotes']), volatility_count=len(snapshot['vols']),
                history_counts={ticker: len(history) for ticker, history in snapshot['session_closes'].items()})
    if rehearsal:
        ages=[(observed_at-q.timestamp).total_seconds() for q in snapshot['quotes'].values()]
        rehearsal_freshness={'fresh':sum(0<=age<=config.risk.max_quote_age_seconds for age in ages),
                            'stale_or_future':sum(not 0<=age<=config.risk.max_quote_age_seconds for age in ages),
                            'maximum_age_seconds':max(ages,default=None),
                            'limit_seconds':config.risk.max_quote_age_seconds}
    check_owner()
    inbox.settle_expirations(snapshot['session_closes'],observed_at,cycle_id=cycle_id,lifecycle=lifecycle)
    market_open=MarketSchedule().should_run(observed_at,asset_class='stock',stage=1)
    choices=candidates(snapshot,inbox,config,observed_at)
    fresh_instruments={str(choice['instrument']) for choice in choices if not choice.get('quote_stale')}
    strategy_assessment=evaluate_daily_signals(
        snapshot['session_closes'], ETF_UNIVERSE & config.risk.instrument_whitelist,
        observed_at.astimezone(ET).date())
    option_signals=rank_option_candidates(
        [candidate for candidate in choices if candidate.get('contract') and not candidate.get('quote_stale')],
        strategy_assessment['signals'])
    strategy_assessment['signals']=[
        signal for signal in strategy_assessment['signals']
        if str(signal.get('instrument')) in fresh_instruments
    ]
    strategy_assessment['signals'].extend(option_signals)
    signal_rows=candidate_decisions(choices,strategy_assessment['signals'],
                                    {'compared_symbols':[]},{'picks':[]},
                                    {'rejected_instruments':[]},[],[])
    strategy_blocked={name:details.get('blocked',{})
                      for name,details in strategy_assessment['strategies'].items()}
    trace_event('strategy_evaluated', signals=strategy_assessment['signals'],
                blocked=strategy_blocked,candidate_decisions=signal_rows)
    signal_map={str(signal['instrument']):signal for signal in strategy_assessment['signals']}
    held={ticker for lane in ('A','B') for track in ('agent_alone','with_approvals')
          for ticker in inbox.state(lane,track)['positions']}
    eligible=sorted(set(signal_map)|held)
    model_candidates=agent_candidate_packet(choices,signal_map,held)
    accounts={lane:{track:{k:v for k,v in inbox.state(lane,track).items() if k in {'settled_cash','unsettled_cash','positions'}} for track in ('agent_alone','with_approvals')} for lane in ('A','B')}
    if data_mode!='fixture':
        discovery=[{
            'candidate_id':str(signal['instrument']),
            'asset_class':'etf' if str(signal['instrument']) in ETF_UNIVERSE else ('option' if str(signal['instrument']) in snapshot['contracts'] else 'stock'),
            'qualified':str(signal['instrument']) in fresh_instruments,
        } for signal in strategy_assessment['signals']]
        holding_rows=[{'position_id':ticker,'qualitative_review_required':True}
                      for ticker in held]
        ai_gate=AIInvocationGate().evaluate(discovery,holding_rows)
        trace_event('ai_invocation_gate',invoke=ai_gate.invoke,reason=ai_gate.reason,
                    candidate_ids=list(ai_gate.candidate_ids),reserved_cost_usd='0')
        if not ai_gate.invoke:
            inbox.mark_accounts(snapshot['quotes'],observed_at,data_mode)
            stale_only=bool(choices) and not fresh_instruments
            decision_type='HOLD_OPERATIONAL' if stale_only or snapshot['exclusions'] else 'HOLD_CASH'
            reason=('No candidate has the required fresh, normalized evidence.' if decision_type=='HOLD_OPERATIONAL'
                    else 'Deterministic discovery produced no stock candidate requiring qualitative AI review.')
            return finish({
                'status':'COMPLETED','read_tools':sorted({r['tool'] for r in reads}),
                **({'quote_freshness':rehearsal_freshness,'source_hash_count':len(source_hashes),
                    'stages':{'collection':'completed','strategy':'completed','ai':'not_needed','risk':'not_needed_no_proposals'},
                    'risk_proposals_evaluated':0} if rehearsal else {}),
                'collector_evidence':getattr(reader,'evidence',None),
                'transport_evidence':{'collector':getattr(reader,'evidence',None),'inference':[]},
                'account_last4':snapshot['account_last4'],'quote_count':len(snapshot['quotes']),
                'volatility_count':len(snapshot['vols']),'market_open':market_open,
                'strategy_assessment':strategy_assessment,
                'decision':{'type':decision_type,'picks':[],'reason':reason},
                'critic':None,'results':[],'reason':reason,'news_checked':False,'news':[],
                'missing_evidence':['News was not invoked because AI was not needed.'],
                'ai_gate':{'invoke':False,'reason':ai_gate.reason,'cost_usd':'0'},
                'corporate_action_exclusions':snapshot['exclusions'],
                'source_hashes':source_hashes,'notification_policy':'log_only',
            })
        if rehearsal and not diagnostic_cap_waiver:
            # The current Phase 0 transport lacks hard output-token caps and
            # reserves .06/.14 per call: it cannot certify the registered .20
            # what-if ceiling. Do not spend first and discover the overrun later.
            return finish({'status':'HOLD_OPERATIONAL',
                'ai_gate':{'invoke':True,'reason':ai_gate.reason,'blocker':'REHEARSAL_MODEL_CAP_NOT_CERTIFIED'},
                'quote_count':len(snapshot['quotes']),'volatility_count':len(snapshot['vols']),
                'market_open':market_open,'quote_freshness':rehearsal_freshness,
                'stages':{'collection':'completed','strategy':'completed','ai':'budget_safety_blocked','risk':'not_run'},
                'source_hash_count':len(source_hashes),'results':[]})
        active_lanes=sorted({candidate['lane'] for candidate in model_candidates}
                            | ({'B'} if any(ticker in snapshot['contracts'] for ticker in held) else set())
                            | ({'A'} if any(ticker not in snapshot['contracts'] for ticker in held) else set()))
        active_lanes=active_lanes or ['A']
        try:
            for lane in ([] if diagnostic_cap_waiver else active_lanes):
                for stage,amount in budget_allocator.stage_reservations.items():
                    identifier=budget_allocator.reserve(observed_at,lane=lane,stage=stage,amount=amount)
                    phase0_reservations.append({'id':identifier,'lane':lane,'stage':stage})
        except BudgetUnavailable as error:
            for row in phase0_reservations:
                budget_allocator.settle(row['id'],actual=D(0))
            phase0_reservations.clear()
            return finish({'status':'COMPLETED','decision':{'type':'HOLD_OPERATIONAL','picks':[],'reason':str(error)},'critic':None,'results':[],'reason':str(error),'ai_gate':{'invoke':True,'reason':ai_gate.reason},'news_checked':False,'news':[],'missing_evidence':['BUDGET_MINIMUM_NOT_AVAILABLE']})
    try:
        research_request={'symbols':sorted({str(candidate['instrument']) for candidate in model_candidates}),'now':observed_at.isoformat(),'candidates':model_candidates,'strategy_assessment':strategy_assessment,'news_enabled':False}
        research=run('research',Research,research_request)
        research_rows=candidate_decisions(choices,[],completed['research'],{'picks':[]},
                                          {'rejected_instruments':[]},[],[])
        trace_event('stage_completed',role='research',agent='Research Agent',
                    output=completed['research'],candidate_decisions=research_rows)
        portfolio_request={'research':research.model_dump(mode='json'),'market_open':market_open,'eligible_instruments':eligible,'strategy_signals':strategy_assessment['signals'],'candidates':model_candidates,'paper_accounts':accounts}
        decision=run('portfolio',Decision,portfolio_request)
        portfolio_rows=candidate_decisions(choices,[],{'compared_symbols':[]},
                                           completed['portfolio'],{'rejected_instruments':[]},[],[])
        trace_event('stage_completed',role='portfolio',agent='Portfolio Agent',
                    output=completed['portfolio'],candidate_decisions=portfolio_rows)
        critic_request={'research':research.model_dump(mode='json'),'decision':decision.model_dump(mode='json'),'market_open':market_open,'eligible_instruments':eligible,'strategy_signals':strategy_assessment['signals']}
        critic=run('critic',Critique,critic_request)
        critic_rows=candidate_decisions(choices,[],{'compared_symbols':[]},{'picks':[]},
                                        completed['critic'],[],[])
        trace_event('stage_completed',role='critic',agent='Critic',
                    output=completed['critic'],candidate_decisions=critic_rows)
    except BudgetExceeded:
        return finish({'status':'NOT_ISSUED_BUDGET','reason':'Insufficient remaining estimated AI budget for the next review stage','decision':completed.get('portfolio'),'results':[]})
    completion_time=clock()
    check_owner()
    wanted={p.instrument for p in decision.picks}|{t for lane in ('A','B') for track in ('agent_alone','with_approvals') for t in inbox.state(lane,track)['positions']}
    try:
        refreshed=reader.refresh(completion_time,sorted(config.risk.instrument_whitelist),sorted(wanted & snapshot['contracts'].keys()))
        completion_time=clock()
        # Discard original quotes entirely: a missing refresh is not permission to reuse them.
        context_reads=[r for r in reads if r['tool'] not in {'get_equity_quotes','get_option_quotes'}]
        fresh=market_snapshot(context_reads+refreshed,config,completion_time,held_contracts=snapshot['contracts'],require_live_identity=data_mode!='fixture')
        snapshot['quotes']=fresh['quotes']
        missing=[s for s in wanted if s not in fresh['quotes'] or fresh['quotes'][s].halted or not 0<=(completion_time-fresh['quotes'][s].timestamp).total_seconds()<=config.risk.max_quote_age_seconds]
        refresh_rows=candidate_decisions(choices,[],{'compared_symbols':[]},{'picks':[]},
                                         {'rejected_instruments':[]},missing,[])
        trace_event('final_refresh', quote_count=len(fresh['quotes']), instruments=sorted(wanted),
                    missing_instruments=sorted(missing),candidate_decisions=refresh_rows)
        if missing: return finish({'status':'NOT_ISSUED_DATA','reason':'Current quotes unavailable','decision':completed['portfolio'],'critic':completed['critic'],'results':[],'missing_instruments':sorted(missing)})
    except (ValueError,RuntimeError) as error:
        return finish({'status':'NOT_ISSUED_DATA','reason':'Code-only quote refresh failed','error_type':type(error).__name__,'decision':completed['portfolio'],'critic':completed['critic'],'results':[]})
    check_owner()
    market_open=MarketSchedule().should_run(completion_time,asset_class='stock',stage=1)
    inbox.mark_accounts(snapshot['quotes'],completion_time,data_mode)
    results=apply_decision(inbox,config,decision,critic,snapshot,completion_time,cycle_id,lifecycle=lifecycle,strategy_signals=signal_map) if market_open else []
    risk_rows=(candidate_decisions(choices,[],{'compared_symbols':[]},{'picks':[]},
                                   {'rejected_instruments':[]},[],results)
               if market_open else [])
    trace_event('risk_evaluated',status='completed' if market_open else 'not_run',
                results=results,real_execution='blocked',candidate_decisions=risk_rows)
    inbox.mark_accounts(snapshot['quotes'],completion_time,data_mode)
    result={'status':'COMPLETED','read_tools':sorted({r['tool'] for r in reads}),'collector_evidence':getattr(reader,'evidence',None),'account_last4':snapshot['account_last4'],'quote_count':len(snapshot['quotes']),'volatility_count':len(snapshot['vols']),'market_open':market_open,'strategy_assessment':strategy_assessment,'decision':decision.model_dump(mode='json'),'critic':critic.model_dump(mode='json'),'results':results,'reason':decision.reason,'news_checked':False,'news':[],'missing_evidence':research.missing_evidence+['News disabled pending tool isolation verification'],'source_hashes':source_hashes,'notification_policy':'required_actions_only'}
    result['transport_evidence']={'collector':getattr(reader,'evidence',None),'inference':getattr(bridge,'isolation_evidence',[])}
    # Persist observed benchmark prices, never manufacture an unchanged benchmark.
    if snapshot['benchmark'] and not rehearsal:
        inbox.store.append_json('daily_values',{'timestamp':now.isoformat(),'benchmark':'VTI','close':snapshot['benchmark'],'data_mode':data_mode})
    return finish(result)


class FixtureBridge:
    def __init__(self, config, now):
        self.config,self.now,self.index=config,now,0
        self.last_result=None

    def run(self, model, instructions, schema, **kwargs):
        outputs=[{'summary':'Mocked diversified-market evidence.','compared_symbols':['VTI','AAPL'],'news_checked':False,'news':[],'missing_evidence':['fixture data']}, {'picks':[{'instrument':'VTI','side':'buy','thesis':'Diversified exposure.','good_if':'market breadth improves.','invalidation':'breadth weakens.','confidence':'0.6'}],'reason':'Fixture test proposal.'}, {'counterargument':'A broad selloff could overwhelm diversification.','rejected_instruments':[]}]
        outputs[1]['picks'][0]['confidence']=0.6
        output=outputs[self.index];self.index+=1
        bars=[{'begins_at':(self.now-timedelta(days=253-i)).isoformat(),'close_price':str(100+i)} for i in range(253)]
        reads=[{'tool':'get_accounts','data':{'accounts':[{'account_number':self.config.risk.agentic_account_id,'agentic_allowed':True}]}}, {'tool':'get_portfolio','arguments':{'account_number':self.config.risk.agentic_account_id},'data':{}}, {'tool':'get_equity_quotes','data':{'results':[{'quote':{'symbol':'VTI','instrument_id':'fixture-security-vti','bid_price':'100','ask_price':'100.20','venue_bid_time':self.now.isoformat(),'venue_ask_time':self.now.isoformat()}}]}}, {'tool':'get_equity_historicals','data':{'results':[{'symbol':'VTI','bars':bars}]}}]
        result=BridgeResult(output,reads,{'input_tokens':0,'output_tokens':0},[r['tool'] for r in reads])
        self.last_result=result
        return result


class FixtureReader:
    def __init__(self,config,now): self.config,self.now=config,now; self.refreshes=0
    def collect(self,now,held_contracts): return FixtureBridge(self.config,self.now).run('','',{}).reads
    def refresh(self,now,equity_symbols,option_ids):
        self.refreshes+=1
        return [r for r in FixtureBridge(self.config,now).run('','',{}).reads if r['tool']=='get_equity_quotes']


def run_fixture_cycle(inbox,config,now):
    from data.database_role import require_database_role
    require_database_role(inbox.path,'fixture')
    return run_cycle(inbox,config,FixtureBridge(config,now),now,data_mode='fixture')


def main():
    parser=argparse.ArgumentParser(description='Stage 1 daily shadow cycle')
    parser.add_argument('--config',default='config/settings.local.yaml')
    parser.add_argument('--database',default='data/agent.db')
    parser.add_argument('--mode',choices=['live','fixture'],default='fixture')
    parser.add_argument('--scheduled',action='store_true')
    args=parser.parse_args()
    config=load_config(args.config)
    if args.mode=='fixture' and args.database=='data/agent.db':
        args.database='data/fixture.db'
    from agents.safety_events import safety_stopped
    if safety_stopped(args.database):
        print(json.dumps({'status':'STOPPED_BY_KILL_SWITCH'}));return
    from data.database_role import require_database_role
    require_database_role(args.database,'fixture' if args.mode=='fixture' else 'live')
    inbox=PaperInbox(args.database,config)
    now=datetime.now(timezone.utc)
    from agents.cycle_lifecycle import CycleLifecycle
    lifecycle=CycleLifecycle(inbox.path, config.notifications.dashboard_base_url); claim=None; reader=None
    try:
        if args.mode=='live':
            claim=lifecycle.acquire(now,scheduled=args.scheduled)
            if claim is None:
                print(json.dumps({'status':'SKIPPED_SCHEDULE'}));return
            from agents.readiness import capture_runtime, source_fingerprint, record_background_receipt
            from agents.market_reader import LiveReader
            root=Path(__file__).resolve().parents[1]
            runtime=capture_runtime(root)
            source_hash=source_fingerprint(root)
            reader=LiveReader(inbox.path,config)
        result=run_fixture_cycle(inbox,config,datetime(2026,9,21,14,tzinfo=timezone.utc)) if args.mode=='fixture' else run_cycle(inbox,config,CodexBridge(args.database,config.daily_api_budget_usd,None,config.notifications.dashboard_base_url),now,reader=reader,cycle_id=claim['cycle_id'],lifecycle=lifecycle)
        if args.mode=='live':
            result['trigger']=claim['trigger']
            record_background_receipt(inbox.store,result,runtime,source_hash=source_hash,
                                      config_hash=config.config_hash,completed_at=datetime.now(timezone.utc))
    except Exception as error:
        # Do not echo provider exceptions, prompt contents or account payloads.
        result={'status':'FAILED','error_type':type(error).__name__,'remediation':'Inspect read-only auth, available cost budget and data freshness.'}
        inbox.store.append_json('run_states',result)
        if claim:
            lifecycle.finish(claim['cycle_id'],'FAILED',result,datetime.now(timezone.utc))
        print(json.dumps(result));raise SystemExit(1)
    finally:
        if reader: reader.close()
        lifecycle.close()
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
