from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from broker.models import Quote
from test_risk_engine import make_config, make_context

NOW = datetime(2026, 10, 1, 14, tzinfo=timezone.utc)


def inputs():
    return dict(symbol='VTI', quote=Quote(ticker='VTI', bid=D('99.90'), ask=D('100.10'), timestamp=NOW),
        reference_quote=Quote(ticker='VTI', bid=D('99.90'), ask=D('100.10'), timestamp=NOW),
        evaluated_at=NOW, now=NOW, holdings_review_complete=True,
        approved_ai_stock_pick=False, entry_slot_used=False,
        median_spread_fraction=D('.001'), median_dollar_volume=D('100000000'),
        context=make_context(now=NOW, quote_timestamp=NOW, bid=D('99.90'), ask=D('100.10'),
            volatility_as_of=NOW, account_value=D(500), current_value=D(500), peak_value=D(500),
            settled_cash=D(500), realized_volatility_20d=D('.20')), risk_config=make_config(),
        signal={'instrument':'VTI', 'side':'buy', 'strategy':'momentum_rotation_126d_trend200_top1',
            'thesis':'Registered deterministic trend', 'good_if':'Above 200-session average',
            'invalidation':'Below 200-session average'}, cycle_id='fixture-cycle')


def test_core_proposes_fractional_desk_policy_with_registered_limit():
    from agents.etf_desk_policy import plan_entry
    plan = plan_entry(**inputs())
    assert plan['status'] == 'ELIGIBLE'
    assert plan['limit_price'] == '100.50000'
    assert D(plan['quantity']).as_tuple().exponent == -6
    assert D(plan['quantity']) * D(plan['limit_price']) <= D('50')
    assert plan['modeled_fill_price'] == '100.20010'
    assert plan['arms'] == ['agent_alone','with_approvals','deterministic_no_ai']
    assert plan['attribution'] == 'desk_policy_not_ai'
    assert plan['expires_at'] == '2026-10-01T19:30:00+00:00'


@pytest.mark.parametrize('change,reason', [
    ({'approved_ai_stock_pick':True},'AI_STOCK_SLOT_PRECEDENCE'),
    ({'entry_slot_used':True},'LANE_A_SLOT_USED'),
    ({'holdings_review_complete':False},'HOLDINGS_REVIEW_REQUIRED'),
    ({'median_spread_fraction':None},'LIQUIDITY_EVIDENCE_MISSING'),
    ({'median_dollar_volume':D('10')},'LIQUIDITY_BLOCKED'),
    ({'now':NOW+timedelta(seconds=61)},'STALE_QUOTE'),
    ({'symbol':'AAPL'},'ETF_SCOPE_REQUIRED'),
])
def test_fail_closed_inputs(change,reason):
    from agents.etf_desk_policy import plan_entry
    assert plan_entry(**(inputs()|change))['reason'] == reason


def test_limit_never_chases_new_price():
    from agents.etf_desk_policy import plan_entry
    quote=Quote(ticker='VTI',bid=D(101),ask=D('101.10'),timestamp=NOW)
    assert plan_entry(**(inputs()|{'quote':quote}))['reason']=='TRIGGER_NOT_FIRED'


def test_falling_quote_uses_original_reference_not_current_ask_distance():
    from agents.etf_desk_policy import plan_entry
    quote = Quote(ticker='VTI', bid=D('98.90'), ask=D('99.10'), timestamp=NOW)
    plan = plan_entry(**(inputs() | {'quote': quote}))
    assert plan['status'] == 'ELIGIBLE'
    assert D(plan['limit_price']) == D('100.50')
    assert D(plan['modeled_fill_price']) == D('99.19910')


def test_unregistered_strategy_cannot_enter():
    from agents.etf_desk_policy import plan_entry
    args = inputs()
    args['signal']['strategy'] = 'arbitrary_unregistered'
    assert plan_entry(**args)['reason'] == 'UNREGISTERED_ETF_STRATEGY'


def test_strategy_invalidation_is_preserved_without_invented_time_exit():
    from agents.etf_desk_policy import plan_entry
    args = inputs()
    args['signal'].update(strategy='mean_reversion_drop3_above_ma200',
        invalidation='Below trend or fails to recover within 10 sessions.')
    plan = plan_entry(**args)
    assert plan['exit_plan']['invalidation'] == args['signal']['invalidation']
    assert 'time_exit_sessions' not in plan['exit_plan']


def test_early_close_expiry_and_exact_boundary():
    from agents.etf_desk_policy import entry_deadline
    at=datetime(2026,11,27,15,tzinfo=timezone.utc)
    assert entry_deadline(at)==datetime(2026,11,27,17,30,tzinfo=timezone.utc)


def test_activation_guard_is_closed_and_draft_is_never_live():
    from agents.etf_desk_policy import production_enabled
    assert not production_enabled('docs/superpowers/plans/preregistration-v1.5.0.draft.yaml',NOW)
    assert not production_enabled('preregistration.yaml',NOW)


def test_risk_kill_switch_is_not_bypassed():
    from agents.etf_desk_policy import plan_entry
    args=inputs();args['context']=args['context'].model_copy(update={'kill_switch':True})
    plan=plan_entry(**args)
    assert plan['status']=='BLOCKED' and 'kill_switch' in plan['risk_reasons']


@pytest.mark.parametrize('field,value', [('settled_cash',D('.50')), ('realized_volatility_20d',None)])
def test_missing_cash_or_volatility_never_produces_entry(field,value):
    from agents.etf_desk_policy import plan_entry
    args=inputs();args['context']=args['context'].model_copy(update={field:value})
    assert plan_entry(**args)['status']=='BLOCKED'


def test_expiry_boundary_and_stale_reference_fail_closed():
    from agents.etf_desk_policy import plan_entry
    args=inputs();args['now']=NOW.replace(hour=19,minute=30)
    assert plan_entry(**args)['reason']=='TRIGGER_EXPIRED'
    args=inputs();args['reference_quote']=args['reference_quote'].model_copy(update={'timestamp':NOW-timedelta(seconds=61)})
    assert plan_entry(**args)['reason']=='STALE_QUOTE'


def test_registered_draft_matches_engine_rules_and_stays_inactive():
    import yaml
    from pathlib import Path
    doc=yaml.safe_load(Path('docs/superpowers/plans/preregistration-v1.5.0.draft.yaml').read_text())
    rule=doc['v1_5_review_proposal']['etf_desk_policy']
    assert rule['operator_approved_on']=='2026-09-30'
    assert rule['maximum_limit_distance_fraction']=='0.005'
    assert rule['minimum_notional_usd']=='1.00'
    assert rule['equity_quantity_decimal_places']==6
    assert rule['applies_to']==['agent_alone','with_approvals','deterministic_no_ai']
    assert doc['v1_5_review_proposal']['activation_allowed'] is False
