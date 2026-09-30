"""Deterministic ETF entry planning. No broker, model, database or card writes.

The production pin deliberately remains absent until operator activation.
Planning is usable for isolated tests before activation; it is not issuance.
"""
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN
from zoneinfo import ZoneInfo

from agents.operator import MarketSchedule
from agents.schemas import TradeProposal
from research.strategy_signals import ETF_UNIVERSE
from risk.engine import RiskEngine

D = Decimal
ET = ZoneInfo('America/New_York')
APPROVED_V15_SHA256 = None
ARMS = ('agent_alone', 'with_approvals', 'deterministic_no_ai')
STRATEGIES = frozenset({'momentum_rotation_126d_trend200_top1',
                        'mean_reversion_drop3_above_ma200'})


def production_enabled(registration_path, now):
    # No environment variable, dashboard switch or draft approval bypasses this.
    # Activation must supply a separately reviewed, byte-pinned registration.
    return False


def entry_deadline(evaluated_at):
    local = evaluated_at.astimezone(ET)
    cutoff = local.replace(hour=15, minute=30, second=0, microsecond=0)
    return min(cutoff, MarketSchedule().session_close(evaluated_at) - timedelta(minutes=30)).astimezone(ZoneInfo('UTC'))


def plan_entry(*, symbol, quote, reference_quote, evaluated_at, now,
               holdings_review_complete, approved_ai_stock_pick, entry_slot_used,
               median_spread_fraction, median_dollar_volume, context, risk_config,
               signal, cycle_id):
    """Plan one arm from trusted evaluate_daily_signals output, not model text.

    The issuance layer must persist the first reference once per official
    cycle and invoke this separately for each arm's holdings/cash. This pure
    function neither authenticates a signal's provenance nor issues a trade.
    """
    def blocked(reason, **details):
        return {'status': 'BLOCKED', 'reason': reason, 'attribution': 'desk_policy_not_ai', **details}
    if symbol not in ETF_UNIVERSE or symbol not in risk_config.instrument_whitelist:
        return blocked('ETF_SCOPE_REQUIRED')
    if signal.get('instrument') != symbol or signal.get('side') != 'buy':
        return blocked('QUALIFIED_ETF_SIGNAL_REQUIRED')
    if signal.get('strategy') not in STRATEGIES:
        return blocked('UNREGISTERED_ETF_STRATEGY')
    if approved_ai_stock_pick is not False:
        return blocked('AI_STOCK_SLOT_PRECEDENCE')
    if entry_slot_used is not False:
        return blocked('LANE_A_SLOT_USED')
    if holdings_review_complete is not True:
        return blocked('HOLDINGS_REVIEW_REQUIRED')
    schedule = MarketSchedule()
    if (now.tzinfo is None or evaluated_at.tzinfo is None or now < evaluated_at
            or schedule.classify(evaluated_at) != schedule.State.TRADING_WINDOW
            or not schedule.should_run(now, asset_class='etf', stage=1)):
        return blocked('OUTSIDE_OFFICIAL_SESSION')
    expires = entry_deadline(evaluated_at)
    if now >= expires:
        return blocked('TRIGGER_EXPIRED')
    for q, at in ((reference_quote, evaluated_at), (quote, now)):
        if q.ticker != symbol or q.halted:
            return blocked('QUOTE_IDENTITY_OR_HALT')
        if not 0 <= (at-q.timestamp).total_seconds() <= 60:
            return blocked('STALE_QUOTE')
        if not q.bid.is_finite() or not q.ask.is_finite() or not 0 < q.bid <= q.ask:
            return blocked('INVALID_QUOTE')
    if median_spread_fraction is None or median_dollar_volume is None:
        return blocked('LIQUIDITY_EVIDENCE_MISSING')
    if (not median_spread_fraction.is_finite() or not median_dollar_volume.is_finite()
            or not 0 <= median_spread_fraction <= D('.003')
            or median_dollar_volume < D('50000000')):
        return blocked('LIQUIDITY_BLOCKED')
    midpoint = (quote.bid+quote.ask)/2
    if midpoint < D(5) or (quote.ask-quote.bid)/midpoint > D('.003'):
        return blocked('FRICTION_BLOCKED')
    reference = (reference_quote.bid+reference_quote.ask)/2
    limit = reference * D('1.005')
    fill = quote.ask * D('1.001')
    if midpoint > limit or fill > limit:
        return blocked('TRIGGER_NOT_FIRED')
    engine = RiskEngine(risk_config)
    vol = context.realized_volatility_20d
    if vol is None or not vol.is_finite() or vol <= 0:
        return blocked('SIZING_HISTORY_REQUIRED')
    available = max(D(0), min(context.settled_cash,
        engine.sized_notional(context.account_value, vol)-context.position_values.get(symbol,D(0))))
    # Reserve at the limit, not the ask; modeled slippage must fit inside it.
    quantity = (available/limit).quantize(D('.000001'), rounding=ROUND_DOWN)
    if quantity*fill < D(1):
        return blocked('BELOW_MINIMUM_NOTIONAL')
    for name in ('strategy','thesis','good_if','invalidation'):
        if not isinstance(signal.get(name),str) or not signal[name]:
            return blocked('SIGNAL_EXIT_PLAN_REQUIRED')
    proposal = TradeProposal(proposal_id=f'{cycle_id}-A-etf', client_order_id=f'{cycle_id}-A-etf',
        account_id=risk_config.agentic_account_id, ticker=symbol, asset_class='etf', side='buy',
        quantity=quantity, limit_price=limit, thesis=signal['thesis'], good_if=signal['good_if'],
        invalidation=signal['invalidation'], horizon_days=20,
        # Required legacy RiskEngine input only; never an ETF forecast or AI score.
        confidence=D('.5'), prompt_versions={}, model_name='deterministic_not_a_model', config_hash='0'*64)
    checked = context.model_copy(update={'now':now,'quote_timestamp':quote.timestamp,'bid':quote.bid,'ask':quote.ask})
    verdict = engine.evaluate(proposal, checked, etf_entry_reference=reference)
    if not verdict.allowed:
        return blocked('RISK_BLOCKED', risk_reasons=[r.value for r in verdict.reasons])
    return {'status':'ELIGIBLE', 'instrument':symbol, 'lane':'A', 'strategy':signal['strategy'],
        'quantity':str(quantity), 'reference_midpoint':str(reference), 'limit_price':str(limit),
        'modeled_fill_price':str(fill), 'expires_at':expires.isoformat(),
        'arms':list(ARMS), 'attribution':'desk_policy_not_ai',
        'with_approvals_action':'PENDING_OPERATOR_YES', 'execution_authorized':False,
        'exit_plan':{'invalidation':signal['invalidation']}}
