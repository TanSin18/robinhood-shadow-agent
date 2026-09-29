"""Exact allocation primitives; integration must supply frozen packet token counts.

Budget reservations are not evidence a lane appeared in an AI input. This module
does not read accounts, mutate budgets or invoke a tokenizer/provider.
"""
from decimal import Decimal
from fractions import Fraction
import copy

ARMS = ('agent_alone', 'agent_with_approvals', 'deterministic_no_ai',
        'seeded_random', 'vti', 'cash', 'exposure_matched_vti',
        'lane_b_delta_equivalent_underlying')


def split_stage_input(request, instrument_lanes):
    """Partition actual structured stage content; shared narrative stays common.

    Symbol references are lane-specific input blocks too. Unknown/unmapped
    references remain common; they never invent a represented lane.
    """
    common = copy.deepcopy(request)
    blocks = {}
    def extract(parent, field):
        retained = []
        for item in parent.get(field, []):
            instrument = item.get('instrument') if isinstance(item, dict) else item
            lane = instrument_lanes.get(str(instrument))
            if lane in {'A','B'}:
                blocks.setdefault(lane, []).append(item)
            else:
                retained.append(item)
        if field in parent: parent[field] = retained
    for field in ('candidates','strategy_signals','symbols','eligible_instruments'):
        extract(common, field)
    if isinstance(common.get('decision'), dict): extract(common['decision'],'picks')
    return blocks, common


def _exact_sum(values):
    """Sum finite Decimals without depending on the ambient rounding context."""
    values = list(values)
    exponent = min(value.as_tuple().exponent for value in values)
    units = sum(int(Fraction(value) / Fraction(10)**exponent) for value in values)
    return Decimal((int(units < 0), tuple(map(int, str(abs(units)))), exponent))


def allocate_cost(amount: Decimal, lane_tokens: dict[str, int], *, common_tokens: int = 0) -> dict[str, Decimal]:
    amount = Decimal(amount)
    if not amount.is_finite() or amount < 0:
        raise ValueError('INVALID_ALLOCATION_COST')
    if (not lane_tokens or set(lane_tokens) - {'A', 'B'}
        or any(type(n) is not int or n <= 0 for n in lane_tokens.values())
        or type(common_tokens) is not int or common_tokens < 0):
        raise ValueError('INVALID_REPRESENTED_LANE_TOKENS')
    lanes = sorted(lane_tokens)
    weights = {lane: Fraction(n) + Fraction(common_tokens, len(lanes))
               for lane, n in lane_tokens.items()}
    total = sum(weights.values())
    # Floor at twelve decimal places, then give the exact residual to lowest ID.
    scale = 10**12
    result = {}
    for lane in lanes:
        share = Fraction(amount) * weights[lane] / total
        units = (share.numerator * scale) // share.denominator
        result[lane] = Decimal((0, tuple(map(int, str(units))), -12))
    result[lanes[0]] = _exact_sum([amount] + [result[lane].copy_negate() for lane in lanes[1:]])
    return result


def arm_costs(allocation: dict[str, Decimal]) -> dict:
    """Two AI counterfactuals report one shared cost, not two provider charges."""
    return {'total_unique_cost_usd': _exact_sum([Decimal(0), *allocation.values()]),
            'ai_arm_cost_basis': 'shared_lane_cost_not_additive',
            'lanes': {lane: {arm: allocation.get(lane, Decimal(0))
                            if arm in {'agent_alone', 'agent_with_approvals'} else Decimal(0)
                            for arm in ARMS} for lane in ('A', 'B')}}


def allocation_trace_view(events):
    """Project supersession; never edit or sum duplicate bound/actual events."""
    rows=[copy.deepcopy(row) for row in events if row.get('event')=='attempt_cost_allocation']
    actual={(row.get('cycle_id'),row['role'],row['attempt_id']) for row in rows
            if row['cost_basis']!='uncertain_reserved_bound'}
    for row in rows:
        row['superseded_by_actual']=(row['cost_basis']=='uncertain_reserved_bound' and
            (row.get('cycle_id'),row['role'],row['attempt_id']) in actual)
    return rows
