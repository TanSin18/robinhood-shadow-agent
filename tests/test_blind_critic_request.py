"""v1.5 Critic input: complete, blind dossiers (SOXX 2026-09-29 regression)."""
import json
from datetime import datetime, timezone
from decimal import Decimal as D

from agents.daily_cycle import blind_critic_request, LANE_GUIDE
from broker.models import Quote

NOW = datetime(2026, 10, 1, 14, tzinfo=timezone.utc)


class Model:
    def __init__(self, data): self.data = data
    def model_dump(self, mode='json'): return dict(self.data)


class Pick(Model):
    @property
    def instrument(self): return self.data['instrument']


class Decision:
    def __init__(self, picks, reason): self.picks, self.reason = picks, reason
    def model_dump(self, mode='json'): return {'picks': [p.data for p in self.picks], 'reason': self.reason}


class Inbox:
    def state(self, lane, track):
        return {'settled_cash': '500', 'unsettled_cash': '0', 'positions': {}}


def test_critic_gets_price_cash_fractional_and_lane_but_not_portfolio_reasoning():
    snap = {'quotes': {'SOXX': Quote(ticker='SOXX', bid=D('560.5'), ask=D('560.9'), timestamp=NOW),
                       'META': Quote(ticker='META', bid=D('715'), ask=D('715.4'), timestamp=NOW)},
            'contracts': {}}
    picks = [Pick({'instrument': 'META', 'side': 'buy', 'thesis': 'Mean reversion above MA200.',
                   'good_if': 'Recovers.', 'invalidation': 'Below MA200.', 'confidence': 0.6})]
    decision = Decision(picks, 'SECRET PORTFOLIO NARRATIVE: META is Lane B')
    req = blind_critic_request(Model({'summary': 'r'}), decision, snap, Inbox(), True, ['META'], [], [])
    text = json.dumps(req)
    assert 'SECRET PORTFOLIO NARRATIVE' not in text
    sel = req['selections'][0]
    assert sel['paper_context']['lane'] == 'A'
    assert sel['paper_context']['fractional_allowed'] is True
    assert sel['paper_context']['settled_cash'] == '500'
    assert sel['evidence']['bid'] == '715' and sel['evidence']['ask'] == '715.4'
    assert sel['evidence']['asset_class'] == 'stock'
    assert req['lane_guide'] == LANE_GUIDE and 'META' in LANE_GUIDE['A']
    assert sel['preliminary_sizing']['executable'] is False
