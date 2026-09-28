from decimal import Decimal as D

import pytest

from config.loader import load_config
from eval.scoreboard import ScoreboardInputs, build_scoreboard
from risk.engine import RiskEngine
from test_risk_engine import make_config, make_context, make_proposal


def test_benchmarks_do_not_pay_for_agents():
    board = build_scoreboard(ScoreboardInputs(D(500), D(10), D(8), D(4), D(1), D(1), D('.40')))
    assert [x.net_value for x in board.lines] == [D('508.60'), D('506.60'), D(504), D(500)]
    assert [x.api_cost for x in board.lines] == [D('.40'), D('.40'), D(0), D(0)]


def test_shipped_budget_stops_after_forty_cents_and_universe_is_seeded():
    from agents.observability import DailyBudget
    from test_observability_and_operation import FakeNotifier
    config = load_config('config/settings.yaml')
    budget = DailyBudget(config.daily_api_budget_usd, FakeNotifier())
    assert budget.record(D('.39'))
    assert not budget.can_spend(D('.02'))
    assert config.starting_cash_usd == 500
    assert config.risk.instrument_whitelist == frozenset('SPY QQQ VTI SOXX XLE XLU GLD TLT AAPL MSFT NVDA AMZN GOOGL META'.split())


@pytest.mark.parametrize('held,qty', [('0', '1'), ('1', '2')])
def test_closing_claim_cannot_create_unheld_shares(held, qty):
    context = make_context().model_copy(update={'position_quantities': {'VTI': D(held)}})
    verdict = RiskEngine(make_config()).evaluate(make_proposal(side='sell', is_closing=True, quantity=D(qty)), context)
    assert 'insufficient_position' in [r.value for r in verdict.reasons]


def test_risk_cash_check_is_independent_of_paper_broker():
    verdict = RiskEngine(make_config()).evaluate(make_proposal(), make_context(settled_cash=D('100.39')))
    assert 'insufficient_settled_cash' in [r.value for r in verdict.reasons]


def test_volatility_caps_size_and_fails_closed():
    engine = RiskEngine(make_config())
    assert engine.sized_notional(D(500), D('.40')) == D(25)
    assert engine.sized_notional(D(500), D('.04')) == D(125)
    with pytest.raises(ValueError):
        engine.sized_notional(D(500), D(0))


def test_good_if_comes_from_proposal():
    from agents.approval import ApprovalCardRenderer
    p = make_proposal().model_copy(update={'good_if': 'Revenue grows faster than costs.'})
    card = ApprovalCardRenderer().render(p, instrument_description='ETF', max_loss_usd=D(100), holdings_after={'cash':D(400)}, trace_url='http://127.0.0.1:8765/trace/x')
    assert 'Revenue grows faster than costs.' in card.body
