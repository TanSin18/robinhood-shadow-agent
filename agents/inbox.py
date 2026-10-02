"""Transactional paper accounts and durable human approval decisions."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from agents.approval import ApprovalCardRenderer
from agents.schemas import TradeProposal
from broker.models import PaperOrder, Position, Quote
from broker.paper import PaperBroker
from data.store import SQLiteStore
from data.connections import connection
from risk.engine import RiskEngine
from risk.models import RiskContext
from zoneinfo import ZoneInfo
from agents.safety_events import safety_stopped

D = Decimal
ET = ZoneInfo('America/New_York')
# Paper tracks. deterministic_no_ai receives only registered desk-policy (code)
# entries; it never receives AI picks.
PAPER_TRACKS = ('agent_alone', 'with_approvals', 'deterministic_no_ai')
DESK_AUTHOR = 'Desk rule (no AI)'


class PaperInbox:
    def __init__(self, path, config):
        self.path, self.config = Path(path), config
        config.validate_runtime_ready()
        if config.stage != 1 or config.broker != 'paper':
            raise ValueError('paper inbox requires Stage 1')
        self.store = SQLiteStore(path)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS paper_accounts (lane TEXT, track TEXT, payload TEXT, PRIMARY KEY(lane,track));
            CREATE TABLE IF NOT EXISTS approval_inbox (id TEXT PRIMARY KEY, status TEXT, issued TEXT, expires TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS cycle_runs (day TEXT PRIMARY KEY, status TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS weekly_reports (week TEXT PRIMARY KEY, payload TEXT);
            ''')
            for lane, key in [('A','stocks_etfs_starting_cash_usd'),('B','options_starting_cash_usd')]:
                cash = config.paper_lanes[key]
                if cash <= 0:
                    raise ValueError('lane capital must be positive')
                for track in PAPER_TRACKS:
                    state = {'settled_cash':str(cash), 'unsettled_cash':'0', 'positions':{}, 'seen':[], 'fills':[], 'peak':str(cash), 'start':str(cash), 'weekly_start_value':str(cash), 'peak_breaker_latched':False, 'global_kill_switch':False, 'marks':{}}
                    db.execute('INSERT OR IGNORE INTO paper_accounts VALUES (?,?,?)', (lane,track,json.dumps(state)))

    def connect(self):
        return connection(self.path, timeout=15, row_factory=sqlite3.Row)

    def state(self, lane, track, db=None):
        if db is None:
            with self.connect() as conn:
                return self.state(lane,track,conn)
        return json.loads(db.execute('SELECT payload FROM paper_accounts WHERE lane=? AND track=?',(lane,track)).fetchone()[0])

    def _context(self, state, quote, vol, vol_as_of, now):
        values = {ticker: D(p['quantity'])*D(state['marks'].get(ticker,p['average_cost']))*p['multiplier'] for ticker,p in state['positions'].items()}
        value = D(state['settled_cash'])+D(state['unsettled_cash'])+sum(values.values())
        today = [f for f in state['fills'] if datetime.fromisoformat(f['timestamp']).astimezone(ET).date()==now.astimezone(ET).date() and f['status']=='filled']
        sides = {}
        for fill in today:
            sides.setdefault(fill['ticker'],set()).add(fill['side'])
        opening_value = D(state.get('day_start_value', state['start']))
        weekly_start=D(state.get('weekly_start_value',state['start']))
        weekly_loss=(weekly_start-value)/weekly_start if weekly_start>0 else D(1)
        breaker_engaged=(state.get('peak_breaker_latched') is True or state.get('global_kill_switch') is True or weekly_loss>=D('.05'))
        return RiskContext(now=now,stage=1,quote_timestamp=quote.timestamp,bid=quote.bid,ask=quote.ask,account_value=value,current_value=value,peak_value=max(D(state['peak']),value),daily_pnl=value-opening_value,settled_cash=D(state['settled_cash']),position_values=values,position_quantities={t:D(p['quantity']) for t,p in state['positions'].items()},realized_volatility_20d=vol,volatility_as_of=vol_as_of,open_position_count=len(values),orders_today=len(today),traded_sides_today=sides,seen_client_order_ids=frozenset(state['seen']),kill_switch=safety_stopped(self.path) or breaker_engaged,manually_unlocked_after_drawdown=False,auto_approve_requested=False,missing_position_marks=tuple(state.get('missing_marks',[])))

    def mark_accounts(self, quotes, now, data_mode):
        records=[]
        today=now.astimezone(ET).date().isoformat()
        latch_params=None
        try:
            from agents.v17_policy import v17_active, params as v17_params
            if v17_active(now=now):
                latch_params=v17_params()
        except Exception:
            latch_params=None
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for lane in ('A','B'):
                for track in PAPER_TRACKS:
                    state=self.state(lane,track,db)
                    prior=D(state['settled_cash'])+D(state['unsettled_cash'])+sum(D(p['quantity'])*D(state['marks'].get(t,p['average_cost']))*p['multiplier'] for t,p in state['positions'].items())
                    if state.get('mark_day')!=today:
                        state['day_start_value']=str(prior)
                    week=f'{now.astimezone(ET).isocalendar().year:04d}-W{now.astimezone(ET).isocalendar().week:02d}'
                    if state.get('mark_week')!=week:
                        state['weekly_start_value']=str(prior)
                        state['mark_week']=week
                    missing=[]
                    for ticker,position in state['positions'].items():
                        quote=quotes.get(ticker)
                        if quote is None or quote.halted or not 0 <= (now-quote.timestamp).total_seconds() <= self.config.risk.max_quote_age_seconds:
                            missing.append(ticker)
                        else:
                            state['marks'][ticker]=str(quote.bid)
                    state['missing_marks']=missing
                    state['mark_day']=today
                    state['data_mode']=data_mode
                    for t in state['positions']:
                        if t not in missing:
                            state.setdefault('marks_at',{})[t]=quotes[t].timestamp.isoformat()
                    value=None if missing else D(state['settled_cash'])+D(state['unsettled_cash'])+sum(D(p['quantity'])*D(state['marks'][t])*p['multiplier'] for t,p in state['positions'].items())
                    if value is not None:
                        state['peak']=str(max(D(state['peak']),value))
                        peak=D(state['peak'])
                        drawdown=(peak-value)/peak if peak>0 else D(1)
                        if drawdown>=D('.10'):
                            state['peak_breaker_latched']=True
                        if drawdown>=D('.15'):
                            state['global_kill_switch']=True
                        if latch_params is not None:
                            # v1.7: the 10% latch releases after recovery to within 5% of the peak, or the peak is
                            # re-based after 28 latched days. The 15% hard switch is never released here.
                            try:
                                from agents.v17_policy import latch_step
                                latch_event=latch_step(state,value,now.astimezone(ET).date(),latch_params)
                                if latch_event:
                                    db.execute('INSERT INTO daily_values(created_at,payload_json) VALUES (?,?)',(now.isoformat(),json.dumps(
                                        {'kind':'drawdown_latch','event':latch_event,'lane':lane,'track':track,'timestamp':now.isoformat(),'value':str(value)})))
                            except Exception:
                                pass
                    db.execute('UPDATE paper_accounts SET payload=? WHERE lane=? AND track=?',(json.dumps(state),lane,track))
                    record={'kind':'paper_valuation','timestamp':now.isoformat(),'data_mode':data_mode,'lane':lane,'track':track,'value':str(value) if value is not None else None,'missing_marks':missing}
                    records.append(record)
                    db.execute('INSERT INTO daily_values(created_at,payload_json) VALUES (?,?)',(now.isoformat(),json.dumps(record)))
        return records

    def settle_expirations(self, session_closes, now, *, cycle_id=None, lifecycle=None):
        """Paper long-option intrinsic-value settlement; never physical exercise.

        Only an exact expiry-session close is evidence. Missing close leaves a
        frozen, unvalued position. This simplified counterfactual is not a claim
        about Robinhood exercise or assignment handling.
        """
        from agents.maintenance import next_settlement_day
        events=[]
        today=now.astimezone(ET).date()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if lifecycle is not None and not lifecycle.owns(db,cycle_id):
                raise ValueError('Cycle ownership lost before settlement')
            for track in PAPER_TRACKS:
                state=self.state('B',track,db)
                for ticker,p in list(state['positions'].items()):
                    if not p.get('expiry') or p['expiry']>=today.isoformat():
                        continue
                    close=session_closes.get(p['underlying_ticker'],{}).get(p['expiry'])
                    if close is None:
                        continue
                    spot,strike=D(close),D(p['strike'])
                    intrinsic=max(D(0),spot-strike if p['option_type']=='call' else strike-spot)
                    payoff=intrinsic*D(p['quantity'])*p['multiplier']
                    due=next_settlement_day(datetime.fromisoformat(p['expiry']).date())
                    cash='settled_cash' if due<=today else 'unsettled_cash'
                    state[cash]=str(D(state[cash])+payoff)
                    if due>today:
                        state.setdefault('settlements',[]).append({'due':due.isoformat(),'amount':str(payoff)})
                    del state['positions'][ticker]
                    state['marks'].pop(ticker,None)
                    event={'kind':'paper_expiry_cash_settlement','ticker':ticker,'track':track,'payoff':str(payoff),'expiry':p['expiry'],'underlying_close':str(spot),'timestamp':now.isoformat()}
                    events.append(event)
                    db.execute('INSERT INTO fills(created_at,payload_json) VALUES (?,?)',(now.isoformat(),json.dumps(event)))
                db.execute('UPDATE paper_accounts SET payload=? WHERE lane=? AND track=?',(json.dumps(state),'B',track))
        return events

    def _execute(self, db, lane, track, proposal, quote, vol, vol_as_of, now, *, etf_entry_reference=None,
                 ignore_reasons=frozenset(), extra=None):
        """One paper order for one arm. ``ignore_reasons`` is used only by the signed v1.7 core purchase
        (the per-position size caps do not apply to the market core); every other check still applies."""
        state = self.state(lane,track,db)
        engine = RiskEngine(self.config.risk)
        verdict = engine.evaluate(proposal,self._context(state,quote,vol,vol_as_of,now),etf_entry_reference=etf_entry_reference)
        blocking = [r.value for r in verdict.reasons if r.value not in ignore_reasons]
        if blocking:
            return {'status':'RISK_BLOCKED','reasons':blocking}
        from agents.v17_policy import slippage_fraction
        broker = PaperBroker(D(state['start']),now=lambda:now,track=f'{lane}:{track}',slippage=slippage_fraction(now=now))
        broker.settled_cash,broker.unsettled_cash = D(state['settled_cash']),D(state['unsettled_cash'])
        broker.positions = {t:Position.model_validate(p) for t,p in state['positions'].items()}
        order = PaperOrder(client_order_id=proposal.client_order_id or proposal.proposal_id,ticker=proposal.ticker,asset_class=proposal.asset_class,side=proposal.side,quantity=proposal.quantity,limit_price=proposal.limit_price,multiplier=proposal.multiplier,underlying_ticker=proposal.underlying_ticker,option_type=proposal.option_type,strike=proposal.strike,expiry=proposal.expiry)
        fill = broker.submit(order,quote)
        # This runtime only accepts immediate paper fills; resting orders are not silently lost.
        if fill.status != 'filled':
            return {'status':'UNFILLED','reason':fill.reason}
        record = {**fill.model_dump(mode='json'),'side':proposal.side,'timestamp':now.isoformat(),'lane':lane,'comparison':'proposal_time_counterfactual',**(extra or {})}
        if proposal.side=='sell' and proposal.ticker not in broker.positions:
            state.get('guard_stops',{}).pop(proposal.ticker,None)      # the position is closed: its trailing stop goes with it
            if (state.get('core') or {}).get('ticker')==proposal.ticker:
                state.pop('core',None)
        state.update(settled_cash=str(broker.settled_cash),unsettled_cash=str(broker.unsettled_cash),positions={t:p.model_dump(mode='json') for t,p in broker.positions.items()})
        state['seen'].append(order.client_order_id)
        state['fills'].append(record)
        if proposal.side=='sell':
            from agents.maintenance import next_settlement_day
            state.setdefault('settlements',[]).append({'amount':str(proposal.quantity*fill.price*proposal.multiplier),'due':next_settlement_day(now.astimezone(ET).date()).isoformat()})
        state['marks'][proposal.ticker]=str(quote.bid)
        state.setdefault('marks_at',{})[proposal.ticker]=quote.timestamp.isoformat()
        db.execute('UPDATE paper_accounts SET payload=? WHERE lane=? AND track=?',(json.dumps(state),lane,track))
        db.execute('INSERT INTO fills(created_at,payload_json) VALUES (?,?)',(now.isoformat(),json.dumps(record)))
        return record

    def issue(self, proposal, quote, vol, vol_as_of, now, *, cycle_id=None, lifecycle=None):
        if proposal.asset_class not in {'stock','etf','option'} or quote.ticker != proposal.ticker:
            raise ValueError('invalid paper lane or quote instrument')
        lane = 'B' if proposal.asset_class=='option' else 'A'
        if lane=='B' and proposal.side=='buy':
            from agents.v16_policy import options_buys_paused
            if options_buys_paused(now=now):
                # v1.6: options lane paused for new buys; held contracts keep their exits.
                return {'status':'RISK_BLOCKED','reasons':['OPTIONS_LANE_PAUSED_V16']}
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            from data.database_role import database_role
            role=database_role(db)
            if role=='live' and (lifecycle is None or not lifecycle.owns(db,cycle_id)):
                raise ValueError('Live cycle ownership is required')
            previous = db.execute('SELECT payload FROM approval_inbox WHERE id=?',(proposal.proposal_id,)).fetchone()
            if previous:
                prior = json.loads(previous[0])
                if prior['proposal'] != proposal.model_dump(mode='json'):
                    raise ValueError('proposal ID reused with changed content')
                return prior
            fill = self._execute(db,lane,'agent_alone',proposal,quote,vol,vol_as_of,now)
            db.execute('INSERT INTO decision_records(created_at,payload_json) VALUES (?,?)',(now.isoformat(),json.dumps({'proposal_id':proposal.proposal_id,'lane':lane,'status':fill['status'],'reasons':fill.get('reasons',[])})))
            if fill['status'] != 'filled':
                return fill
            state = self.state(lane,'agent_alone',db)
            amount = proposal.quantity*proposal.limit_price*proposal.multiplier
            holdings={'settled cash':D(state['settled_cash']),'unsettled cash':D(state['unsettled_cash']),**{t:D(p['quantity'])*D(state['marks'].get(t,p['average_cost']))*p['multiplier'] for t,p in state['positions'].items()}}
            card = ApprovalCardRenderer().render(proposal,instrument_description='paper option' if lane=='B' else 'stock/ETF',max_loss_usd=D(0) if proposal.side=='sell' else (proposal.max_loss_usd if lane=='B' else amount),holdings_after=holdings,trace_url=self.config.notifications.dashboard_url(f'trace/{proposal.proposal_id}', fragment=False))
            if role=='live':
                from agents.operator import MarketSchedule
                expires=MarketSchedule().session_close(now)
            else:
                expires=now+timedelta(minutes=self.config.approval_expiry_minutes)
            payload = {'id':proposal.proposal_id,'status':'PENDING','lane':lane,'body':card.body,'trace_url':card.trace_url,'proposal':proposal.model_dump(mode='json'),'quote':quote.model_dump(mode='json'),'vol':str(vol) if vol is not None else None,'vol_as_of':vol_as_of.isoformat() if vol_as_of is not None else None,'issued':now.isoformat(),'expires':expires.isoformat(),'comparison':'Proposal-time counterfactual; excludes approval execution latency.'}
            db.execute('INSERT INTO approval_inbox VALUES (?,?,?,?,?)',(proposal.proposal_id,'PENDING',payload['issued'],payload['expires'],json.dumps(payload)))
            from agents.notification_outbox import enqueue
            enqueue(db,'card-'+proposal.proposal_id,'Paper proposal waiting',
                    f'Lane {lane}: a paper proposal needs YES or NO before the market closes.',now,
                    priority=0,url=self.config.notifications.dashboard_url('decisions'))
            return payload

    def issue_desk_card(self, db, proposal, quote, vol, plan, now):
        """v1.5 desk-policy approval card. Caller holds the transaction.

        Fills only via fill_approved_desk_cards at a fresh approval-time quote,
        never at this issue-time quote (registered: fresh approval-time pricing).
        """
        previous = db.execute('SELECT payload FROM approval_inbox WHERE id=?',(proposal.proposal_id,)).fetchone()
        if previous:
            prior = json.loads(previous[0])
            if prior['proposal'] != proposal.model_dump(mode='json'):
                raise ValueError('proposal ID reused with changed content')
            return prior
        amount = proposal.quantity*proposal.limit_price
        body = (f'{DESK_AUTHOR}: buy {proposal.quantity} {proposal.ticker} (paper, Lane A) up to '
                f'${proposal.limit_price:.4f} per share, about ${amount:.2f}. Why: {proposal.thesis} '
                f'Good if: {proposal.good_if} Wrong if: {proposal.invalidation} '
                f'If you say YES, it fills only at a fresh price at or under the limit before '
                f'{datetime.fromisoformat(plan["expires_at"]).astimezone(ET).strftime("%-I:%M %p ET")}. '
                f'Not an AI pick. Paper only.' + (f' {plan["alignment_text"]}' if plan.get('alignment_text') else ''))
        payload = {'id':proposal.proposal_id,'status':'PENDING','lane':'A','author':DESK_AUTHOR,
                   'attribution':'desk_policy_not_ai','fill_policy':'fresh_quote_at_approval',
                   'body':body,'trace_url':self.config.notifications.dashboard_url(f'trace/{proposal.proposal_id}', fragment=False),
                   'proposal':proposal.model_dump(mode='json'),'quote':quote.model_dump(mode='json'),
                   'reference_midpoint':plan['reference_midpoint'],'limit_price':plan['limit_price'],
                   'vol':str(vol[0]) if vol[0] is not None else None,'vol_as_of':vol[1].isoformat() if vol[1] is not None else None,
                   'issued':now.isoformat(),'expires':plan['expires_at'],
                   'comparison':'Approval-time fresh quote within the registered limit.',
                   **({'alignment':plan['alignment']} if plan.get('alignment') else {})}
        db.execute('INSERT INTO approval_inbox VALUES (?,?,?,?,?)',(proposal.proposal_id,'PENDING',payload['issued'],payload['expires'],json.dumps(payload)))
        from agents.notification_outbox import enqueue
        enqueue(db,'card-'+proposal.proposal_id,'Desk rule card waiting',
                f'Lane A: a desk-rule (no AI) paper buy of {proposal.ticker} needs YES or NO.'
                + (f' {plan["alignment_text"]}' if plan.get('alignment_text') else ''),now,
                priority=0,url=self.config.notifications.dashboard_url('decisions'))
        return payload

    def fill_approved_desk_cards(self, quotes, now):
        results=[]
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute("SELECT id,payload FROM approval_inbox WHERE status='APPROVED_AWAITING_FILL'").fetchall()
            for row in rows:
                card=json.loads(row['payload'])
                proposal=TradeProposal.model_validate(card['proposal'])
                expires=datetime.fromisoformat(card['expires'])
                quote=quotes.get(proposal.ticker)
                outcome=None
                if now >= expires:
                    outcome=('APPROVED_NOT_FILLED','approval_window_closed')
                elif quote is None or quote.halted or not 0 <= (now-quote.timestamp).total_seconds() <= self.config.risk.max_quote_age_seconds:
                    results.append({'card_id':card['id'],'status':'WAITING','reason':'NO_FRESH_QUOTE'}); continue
                elif quote.ask*(1+D('0.001')) > proposal.limit_price:
                    results.append({'card_id':card['id'],'status':'WAITING','reason':'ABOVE_LIMIT'}); continue
                if outcome is None:
                    fill=self._execute(db,'A','with_approvals',proposal,quote,D(card['vol']) if card['vol'] else None,
                                       datetime.fromisoformat(card['vol_as_of']) if card['vol_as_of'] else None,now,
                                       etf_entry_reference=D(card['reference_midpoint']))
                    if fill.get('status')=='filled':
                        card['approval_fill']={**fill,'origin':'approval_fresh_quote','attribution':'desk_policy_not_ai'}
                        outcome=('YES',None)
                    elif fill.get('status')=='UNFILLED':
                        results.append({'card_id':card['id'],'status':'WAITING','reason':fill.get('reason')}); continue
                    else:
                        card['approval_fill']=fill
                        outcome=('APPROVED_RISK_BLOCKED','risk_blocked')
                status,reason=outcome
                if reason:
                    db.execute('INSERT INTO fills(created_at,payload_json) VALUES (?,?)',(now.isoformat(),json.dumps(
                        {'client_order_id':proposal.client_order_id,'ticker':proposal.ticker,'status':'skipped','reason':reason,
                         'track':'A:with_approvals','timestamp':now.isoformat()})))
                card.update(status=status,filled_or_closed=now.isoformat())
                db.execute('UPDATE approval_inbox SET status=?,payload=? WHERE id=?',(status,json.dumps(card),card['id']))
                results.append({'card_id':card['id'],'status':status})
        return results

    def cards(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT payload FROM approval_inbox ORDER BY issued DESC')]

    def decide(self, card_id, decision, now=None):
        now = now or datetime.now(timezone.utc)
        if decision not in {'YES','NO','EXPIRED'}:
            raise ValueError('decision must be YES or NO')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM approval_inbox WHERE id=?',(card_id,)).fetchone()
            if row is None:
                raise ValueError('unknown card')
            if row['status'] != 'PENDING':
                raise ValueError('card already resolved')
            card = json.loads(row['payload'])
            issued,expires = datetime.fromisoformat(row['issued']),datetime.fromisoformat(row['expires'])
            if now < issued or (decision=='EXPIRED' and now < expires):
                raise ValueError('invalid decision time')
            status = 'EXPIRED' if now >= expires else decision
            if status=='YES' and card.get('fill_policy')=='fresh_quote_at_approval':
                # Desk-rule card: never fill at the stale issue-time quote.
                card.update(status='APPROVED_AWAITING_FILL',decided=now.isoformat(),
                            response_seconds=int((now-issued).total_seconds()))
                db.execute('UPDATE approval_inbox SET status=?,payload=? WHERE id=?',('APPROVED_AWAITING_FILL',json.dumps(card),card_id))
                db.execute('INSERT INTO cards(created_at,payload_json) VALUES (?,?)',(now.isoformat(),json.dumps({'card_id':card_id,'decision':'YES','response_seconds':card['response_seconds'],'fill_policy':'fresh_quote_at_approval'})))
                return card
            if status=='YES':
                # User-approved design: compare identical proposal-time quotes, explicitly labeled.
                card['approval_fill'] = self._execute(db,card['lane'],'with_approvals',TradeProposal.model_validate(card['proposal']),Quote.model_validate(card['quote']),D(card['vol']) if card['vol'] is not None else None,datetime.fromisoformat(card['vol_as_of']) if card['vol_as_of'] else None,issued)
                state=self.state(card['lane'],'with_approvals',db)
                missing=[t for t in state['positions'] if t not in state.get('marks_at',{}) or not 0 <= (issued-datetime.fromisoformat(state['marks_at'][t])).total_seconds() <= self.config.risk.max_quote_age_seconds]
                value=None if missing else D(state['settled_cash'])+D(state['unsettled_cash'])+sum(D(p['quantity'])*D(state['marks'][t])*p['multiplier'] for t,p in state['positions'].items())
                observation={'kind':'paper_valuation','lane':card['lane'],'track':'with_approvals','timestamp':now.isoformat(),'effective_at':issued.isoformat(),'comparison':'proposal_time_counterfactual','data_mode':state.get('data_mode','fixture'),'value':str(value) if value is not None else None,'missing_marks':missing}
                db.execute('INSERT INTO daily_values(created_at,payload_json) VALUES (?,?)',(now.isoformat(),json.dumps(observation)))
            else:
                record={'client_order_id':card['proposal']['client_order_id'],'ticker':card['proposal']['ticker'],'status':'skipped','reason':'human_no' if status=='NO' else 'expired','track':f'{card["lane"]}:with_approvals','timestamp':now.isoformat()}
                db.execute('INSERT INTO fills(created_at,payload_json) VALUES (?,?)',(now.isoformat(),json.dumps(record)))
            card.update(status=status,decided=now.isoformat(),response_seconds=int((now-issued).total_seconds()))
            db.execute('UPDATE approval_inbox SET status=?,payload=? WHERE id=?',(status,json.dumps(card),card_id))
            db.execute('INSERT INTO cards(created_at,payload_json) VALUES (?,?)',(now.isoformat(),json.dumps({'card_id':card_id,'decision':status,'response_seconds':card['response_seconds']})))
            return card

    def expire(self, now=None):
        now = now or datetime.now(timezone.utc)
        for card in self.cards():
            if card['status']=='PENDING' and now >= datetime.fromisoformat(card['expires']):
                try:
                    self.decide(card['id'],'EXPIRED',now)
                except ValueError:
                    pass  # Another request atomically resolved it.
