from decimal import Decimal as D
from fractions import Fraction
import pytest

def test_high_precision_cost_is_conserved():
    from agents.cost_allocation import allocate_cost, arm_costs
    amount = D('0.012345678901234567890123456789123')
    result = allocate_cost(amount, {'A':1, 'B':1})
    assert sum(map(Fraction, result.values())) == Fraction(amount)
    assert arm_costs(result)['total_unique_cost_usd'] == amount


def test_common_tokens_split_equally_not_proportionally():
    from agents.cost_allocation import allocate_cost
    # A=300+100 common; B=100+100 common -> 2:1, not 3:1.
    assert allocate_cost(D('.06'), {'A':300,'B':100}, common_tokens=200) == {'A':D('.04'),'B':D('.02')}


def test_unrepresented_b_has_zero_cost_despite_existing_budget_reservation():
    from agents.cost_allocation import allocate_cost, arm_costs
    allocated=allocate_cost(D('.0223001'), {'A':120}, common_tokens=900)
    assert allocated == {'A':D('.0223001')}
    report=arm_costs(allocated)
    assert report['total_unique_cost_usd']==D('.0223001')
    assert report['lanes']['A']['agent_alone']==D('.0223001')
    assert report['lanes']['A']['agent_with_approvals']==D('.0223001')
    assert report['lanes']['B']['agent_alone']==0
    assert report['lanes']['A']['deterministic_no_ai']==0
    assert report['lanes']['A']['seeded_random']==0


def test_residual_goes_to_lowest_lane_and_total_is_exact():
    from agents.cost_allocation import allocate_cost
    result=allocate_cost(D('.000000000001'), {'B':1,'A':1})
    assert result=={'A':D('.000000000001'),'B':D('0')}
    assert sum(result.values())==D('.000000000001')


@pytest.mark.parametrize('tokens,common', [({},0),({'A':0},2),({'A':-1},0),({'C':1},0),({'A':True},0),({'A':1},-1)])
def test_invalid_or_unrepresented_packet_fails_closed(tokens,common):
    from agents.cost_allocation import allocate_cost
    with pytest.raises(ValueError): allocate_cost(D('.01'),tokens,common_tokens=common)


@pytest.mark.parametrize('amount',['NaN','Infinity','-.01'])
def test_invalid_cost_rejected(amount):
    from agents.cost_allocation import allocate_cost
    with pytest.raises(ValueError): allocate_cost(D(amount),{'A':1})
