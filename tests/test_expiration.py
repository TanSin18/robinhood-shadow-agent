from datetime import date, datetime, timezone
from decimal import Decimal as D

from broker.models import Quote
from test_inbox_lanes import setup_runtime
from test_risk_engine import NOW, make_proposal


def test_long_option_cash_settlement_uses_exact_expiry_close_and_is_idempotent(tmp_path):
    inbox,_=setup_runtime(tmp_path)
    p=make_proposal(ticker='AAPL-C',asset_class='option',quantity=D(1),limit_price=D('.20'),multiplier=100,underlying_ticker='AAPL',option_strategy='long_call',max_loss_usd=D(20),option_type='call',strike=D(250),expiry=date(2026,10,2))
    inbox.issue(p,Quote(ticker=p.ticker,bid=D('.199'),ask=D('.20'),timestamp=NOW),D('.20'),NOW,NOW)
    after=datetime(2026,10,5,14,tzinfo=timezone.utc)
    # A later quote is not evidence of the expiry payoff.
    assert inbox.settle_expirations({'AAPL':{'2026-10-05':'300'}},after)==[]
    events=inbox.settle_expirations({'AAPL':{'2026-10-02':'251'}},after)
    assert events[0]['payoff']=='100'
    assert inbox.state('B','agent_alone')['positions']=={}
    assert D(inbox.state('B','agent_alone')['settled_cash'])==580
    assert inbox.settle_expirations({'AAPL':{'2026-10-02':'251'}},after)==[]
