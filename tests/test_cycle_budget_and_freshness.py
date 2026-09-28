from datetime import datetime,timedelta,timezone
from decimal import Decimal as D
import pytest
from test_inbox_lanes import setup_runtime
from agents.daily_cycle import FixtureBridge,run_cycle,candidates
from broker.models import Quote

NOW=datetime(2026,9,21,14,tzinfo=timezone.utc)

def test_old_quote_is_candidate_not_execution_permission(tmp_path):
    inbox,cfg=setup_runtime(tmp_path)
    snapshot={'contracts':{},'vols':{'VTI':(D('.2'),NOW)},'quotes':{'VTI':Quote(ticker='VTI',bid=D(100),ask=D('100.2'),timestamp=NOW-timedelta(seconds=90))}}
    result=candidates(snapshot,inbox,cfg,NOW)
    assert result[0]['quote_age_seconds']==90 and result[0]['quote_stale'] is True

@pytest.mark.parametrize('denied_stage',[0,1,2])
def test_budget_denial_retains_completed_stages_without_cards(tmp_path,denied_stage):
    from agents.codex_bridge import BudgetExceeded
    inbox,cfg=setup_runtime(tmp_path)
    class Bridge(FixtureBridge):
        def run(self,*a,**k):
            if self.index==denied_stage: raise BudgetExceeded('test budget')
            return super().run(*a,**k)
    result=run_cycle(inbox,cfg,Bridge(cfg,NOW),NOW,data_mode='fixture')
    assert result['status']=='NOT_ISSUED_BUDGET'
    assert len(result['completed_stages'])==denied_stage
    assert inbox.cards()==[]
    assert inbox.store.read_json('run_states')[-1]['status']=='NOT_ISSUED_BUDGET'

def test_stale_refresh_never_issues(tmp_path):
    from agents.daily_cycle import FixtureReader
    inbox,cfg=setup_runtime(tmp_path)
    class Reader(FixtureReader):
        def refresh(self,now,*args): return super().refresh(now-timedelta(minutes=5),*args)
    result=run_cycle(inbox,cfg,FixtureBridge(cfg,NOW),NOW,data_mode='fixture',reader=Reader(cfg,NOW))
    assert result['status']=='NOT_ISSUED_DATA' and inbox.cards()==[]


def test_stale_candidate_never_enters_agent_packet_but_fresh_peer_does():
    from agents.daily_cycle import agent_candidate_packet
    choices = [
        {'instrument': 'STALE', 'contract': None, 'quote_stale': True},
        {'instrument': 'FRESH', 'contract': None, 'quote_stale': False},
    ]
    assert [row['instrument'] for row in agent_candidate_packet(choices, {}, set())] == ['FRESH']
