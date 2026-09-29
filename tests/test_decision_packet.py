import copy
import json
import pytest


def packet(*args):
    from agents.decision_packet import build_critic_packet
    return build_critic_packet(*args)


def test_critic_is_informed_not_primed():
    selection={'instrument':'SOXX','side':'buy','thesis':'Public thesis',
               'reasoning':'SECRET_REASONING','reason':'SECRET_REASON','quantity':'1000'}
    evidence={'bid':'560','ask':'561','quote_time':'2026-09-29T14:00:00+00:00',
              'source_ids':['quote:1'],'raw_orders':['PRIVATE_ORDER']}
    context={'lane':'A','fractional_allowed':True,'settled_cash':'500',
             'held_quantity':'0','pending_quantity':'0','account_id':'PRIVATE_ACCOUNT'}
    original=copy.deepcopy((selection,evidence,context))
    result=packet(selection,evidence,context)
    encoded=json.dumps(result)
    assert not any(s in encoded for s in ('SECRET','PRIVATE','1000'))
    assert result['selection']['thesis']=='Public thesis'
    assert result['evidence']['bid']=='560'
    assert result['paper_context']['fractional_allowed'] is True
    assert result['preliminary_sizing']=={'status':'NOT_COMPUTED','executable':False}
    assert (selection,evidence,context)==original


def test_unknown_cash_fractional_and_quote_time_remain_unknown():
    result=packet({'instrument':'META'}, {'bid':'100','ask':'101'}, {'lane':'A'})
    assert result['paper_context']['fractional_allowed'] is None
    assert result['paper_context']['settled_cash'] is None
    assert {'quote_time','settled_cash','fractional_allowed'}<=set(result['missing_evidence'])


def test_empty_quote_timestamp_and_incomplete_option_terms_are_missing():
    result=packet({'instrument':'OPT'},
                  {'asset_class':'option','quote_time':'','contract':{'id':'OPT','chain_symbol':'META'}},
                  {'lane':'B'})
    assert {'quote_time','contract.type','contract.expiration_date',
            'contract.strike_price','contract.trade_value_multiplier'}<=set(result['missing_evidence'])


@pytest.mark.parametrize('evidence',[
    {'asset_class':42}, {'asset_class':'crypto'}, {'source_ids':['']},
    {'source_ids':['   ']},
    {'asset_class':'option','contract':{'id':'OPT','chain_symbol':42}},
])
def test_malformed_evidence_is_not_treated_as_complete(evidence):
    with pytest.raises(ValueError):
        packet({'instrument':'OPT'},evidence,{'lane':'B' if evidence.get('contract') else 'A'})


@pytest.mark.parametrize('evidence,context',[
    ({'asset_class':'stock'},{'lane':'B'}),
    ({'asset_class':'option','contract':{'id':'OPT','chain_symbol':'META'}},{'lane':'A'}),
    ({'asset_class':'option','contract':{'chain_symbol':'META'}},{'lane':'B'}),
    ({'asset_class':'option','contract':{'id':'OTHER','chain_symbol':'META'}},{'lane':'B'}),
])
def test_lane_or_contract_identity_cannot_be_inferred_or_moved(evidence,context):
    with pytest.raises(ValueError,match='LANE_OR_CONTRACT_MISMATCH'):
        packet({'instrument':'OPT'},evidence,context)


def test_contract_fields_are_allowlisted_and_options_are_whole_contracts():
    result=packet({'instrument':'OPT'},
                  {'asset_class':'option','contract':{'id':'OPT','chain_symbol':'META',
                   'type':'call','strike_price':'100','expiration_date':'2026-10-16',
                   'trade_value_multiplier':'100','raw_history':'PRIVATE_HISTORY'}},
                  {'lane':'B'})
    assert result['paper_context']['fractional_allowed'] is False
    assert result['evidence']['contract']['id']=='OPT'
    assert 'PRIVATE_HISTORY' not in json.dumps(result)


@pytest.mark.parametrize('value',['NaN','Infinity','-1',True,{'account':'PRIVATE'}])
def test_invalid_money_does_not_enter_agent_context(value):
    with pytest.raises(ValueError,match='INVALID_PACKET_NUMBER'):
        packet({'instrument':'META'},{'bid':value},{'lane':'A'})
