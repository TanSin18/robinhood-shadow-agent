import json
import sqlite3


def test_stored_replay_preserves_source_and_does_not_invent_missing_inputs(tmp_path):
    source=tmp_path/'official.db'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE run_states (id INTEGER PRIMARY KEY, payload_json TEXT)')
        db.execute('INSERT INTO run_states VALUES (1,?)',(json.dumps({
            'cycle_id':'recorded-cycle','status':'COMPLETED','account_last4':'PRIVATE',
            'decision':{'picks':[{'instrument':'SOXX','side':'buy','reasoning':'SECRET'}]},
            'critic':{'rejected_instruments':['SOXX']},
            'strategy_assessment':{'signals':[{'instrument':'SOXX','lane':'A'}]},
        }),))
    before=source.read_bytes()
    from agents.stored_decision_replay import replay_recorded_decision
    result=replay_recorded_decision(source,'recorded-cycle')
    assert source.read_bytes()==before
    assert result['parent_official_run_id']=='recorded-cycle'
    assert result['status']=='REPLAY_INCOMPLETE'
    assert result['selections'][0]['outcome']=='CRITIC_VETO'
    assert result['selections'][0]['sizing']=='NOT_REACHED'
    assert {'bid','ask','quote_time','settled_cash'}<=set(result['selections'][0]['missing_evidence'])
    assert 'historical_contract_snapshot' not in result['selections'][0]['missing_evidence']
    assert result['official_writes']==0 and result['model_calls']==0
    assert all(x not in json.dumps(result) for x in ('PRIVATE','SECRET'))


def test_missing_lane_is_unknown_not_inferred_from_symbol(tmp_path):
    source=tmp_path/'official.db'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE run_states (id INTEGER PRIMARY KEY, payload_json TEXT)')
        db.execute('INSERT INTO run_states VALUES (1,?)',(json.dumps({
            'cycle_id':'recorded-cycle','status':'COMPLETED',
            'decision':{'picks':[{'instrument':'META'}]},'critic':None,
        }),))
    from agents.stored_decision_replay import replay_recorded_decision
    result=replay_recorded_decision(source,'recorded-cycle')
    assert result['selections'][0]['outcome']=='UNKNOWN'
    assert result['selections'][0]['lane'] is None
    assert 'lane' in result['selections'][0]['missing_evidence']


def test_malformed_rejection_string_does_not_create_a_substring_veto(tmp_path):
    source=tmp_path/'official.db'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE run_states (id INTEGER PRIMARY KEY, payload_json TEXT)')
        db.execute('INSERT INTO run_states VALUES (1,?)',(json.dumps({
            'cycle_id':'recorded-cycle','status':'COMPLETED',
            'decision':{'picks':[{'instrument':'META'}]},
            'critic':{'rejected_instruments':'NOT_META'},
        }),))
    from agents.stored_decision_replay import replay_recorded_decision
    result=replay_recorded_decision(source,'recorded-cycle')
    assert result['selections'][0]['outcome']=='UNKNOWN'
    assert 'critic.rejected_instruments' in result['selections'][0]['missing_evidence']
