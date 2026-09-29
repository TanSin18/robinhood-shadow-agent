import json
from decimal import Decimal as D
import pytest
from test_bounded_inference import Client, MODELS, SCHEMA, bridge


@pytest.mark.parametrize('failed_count',[2,3,4])
def test_auxiliary_failure_falls_back_by_unique_candidates_only(tmp_path,failed_count):
    c=Client(); b=bridge(tmp_path,c)
    b.set_cost_context({'A':['AAPL',{'instrument':'AAPL'},'MSFT'], 'B':['OPT']},common_input='common')
    count=c.count
    calls=0
    def count_or_fail(**request):
        nonlocal calls
        calls+=1
        if calls==failed_count: raise RuntimeError('private provider body')
        return count(**request)
    c.responses.input_tokens.count=count_or_fail
    b.run(MODELS[0],'full input',SCHEMA)
    row=b.allocation_records()[0]
    assert row['allocation_status']=='UNAVAILABLE'
    assert row['weight_basis']=='fallback_candidate_count'
    assert row['candidate_counts']=={'A':2,'B':1}
    assert {k:D(v) for k,v in row['allocations'].items()}=={'A':D('.000055'),'B':D('.0000275')}
    assert D(row['cost_usd'])==D('.0000825')
    assert 'private' not in json.dumps(row)
    b.close()


def test_mandatory_counter_failure_still_blocks_with_fallback_enabled(tmp_path):
    c=Client(); b=bridge(tmp_path,c)
    b.set_cost_context({'A':['AAPL']})
    def fail(**request): raise RuntimeError('mandatory count failed')
    c.responses.input_tokens.count=fail
    with pytest.raises(ValueError,match='INPUT_TOKEN_COUNT_FAILED'):
        b.run(MODELS[0],'full input',SCHEMA)
    assert c.calls==[] and b.allocation_records()==[]
    b.close()


def test_common_counter_uses_text_only_envelope(tmp_path):
    c=Client(); b=bridge(tmp_path,c)
    b.set_cost_context({'A':['AAPL']},common_input='common')
    b.run(MODELS[0],'full input',SCHEMA)
    assert [r for r in c.counts if r['input']=='common']==[{'model':MODELS[0],'input':'common'}]
    b.close()


def test_bound_is_superseded_in_projection_without_changing_raw_events(tmp_path):
    c=Client(); b=bridge(tmp_path,c)
    b.set_cost_context({'A':['AAPL']})
    b.run(MODELS[0],'full input',SCHEMA)
    raw=b.store.read_json('local_traces')
    from agents.cost_allocation import allocation_trace_view
    view=allocation_trace_view(raw)
    assert len(view)==2
    assert view[0]['superseded_by_actual'] is True
    assert view[1]['superseded_by_actual'] is False
    assert sum(D(r['cost_usd']) for r in view if not r['superseded_by_actual'])==D('.0000825')
    assert b.store.read_json('local_traces')==raw
    b.close()
