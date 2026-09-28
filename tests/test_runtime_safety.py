from datetime import timedelta, date
from decimal import Decimal as D

from broker.models import Quote
from test_risk_engine import NOW, make_proposal, make_context, make_config
from risk.engine import RiskEngine
from test_inbox_lanes import setup_runtime, issue


def test_equity_cannot_smuggle_option_multiplier():
    verdict = RiskEngine(make_config()).evaluate(make_proposal(multiplier=100), make_context())
    assert not verdict.allowed


def test_option_requires_contract_terms(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    proposal = make_proposal(ticker='AAPL-C',asset_class='option',quantity=D(1),limit_price=D('.20'),multiplier=100,underlying_ticker='AAPL',option_strategy='long_call',max_loss_usd=D(20))
    verdict = inbox.issue(proposal,Quote(ticker='AAPL-C',bid=D('.199'),ask=D('.20'),timestamp=NOW),D('.20'),NOW,NOW)
    assert verdict['status']=='RISK_BLOCKED'


def test_valid_option_lane_fills_and_retains_expiry(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    proposal = make_proposal(ticker='AAPL-C',asset_class='option',quantity=D(1),limit_price=D('.20'),multiplier=100,underlying_ticker='AAPL',option_strategy='long_call',max_loss_usd=D(20),option_type='call',strike=D(250),expiry=date(2026,12,18))
    verdict = inbox.issue(proposal,Quote(ticker='AAPL-C',bid=D('.199'),ask=D('.20'),timestamp=NOW),D('.20'),NOW,NOW)
    assert verdict['status']=='PENDING'
    assert inbox.state('B','agent_alone')['settled_cash']=='480.00'
    assert inbox.state('B','agent_alone')['positions']['AAPL-C']['expiry']=='2026-12-18'
    assert D(inbox.state('A','agent_alone')['settled_cash'])==500


def test_marking_missing_held_quotes_never_publishes_fake_equity(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    issue(inbox)
    records=inbox.mark_accounts({},NOW+timedelta(days=1),'fixture')
    agent=next(r for r in records if r['lane']=='A' and r['track']=='agent_alone')
    assert agent['value'] is None
    assert agent['missing_marks']==['VTI']


def test_marks_update_drawdown_peak_and_daily_baseline(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    issue(inbox)
    next_day=NOW+timedelta(days=1)
    records=inbox.mark_accounts({'VTI':Quote(ticker='VTI',bid=D(200),ask=D('200.2'),timestamp=next_day)},next_day,'fixture')
    state=inbox.state('A','agent_alone')
    assert D(state['peak'])>500
    assert D(state['day_start_value'])==D('450.902')+D('.49')*100
    assert next(r for r in records if r['lane']=='A' and r['track']=='agent_alone')['value'] is not None


def test_no_is_persisted_as_skipped_fill(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    card=issue(inbox)
    inbox.decide(card['id'],'NO',NOW+timedelta(minutes=1))
    assert any(f['status']=='skipped' and f['reason']=='human_no' for f in inbox.store.read_json('fills'))
