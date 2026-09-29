def test_receipt_is_positive_allowlist_not_blacklist():
    from broker_proxy.revocation import receipt
    state={'status':'COMPLETED','begun_at':'2026-09-30T20:30:00+00:00',
           'revoked_read_failed_at':'2026-09-30T20:32:00+00:00',
           'local_credentials_removed_at':'2026-09-30T20:33:00+00:00',
           'reauthorized_read_passed_at':'2026-09-30T20:35:00+00:00',
           'token_fingerprint':'PRIVATE','bindings':{'config_hash':'PRIVATE'},
           'unexpected_secret':'PRIVATE','account_id':'PRIVATE'}
    result=receipt(state)
    from datetime import datetime
    assert datetime.fromisoformat(result.pop('receipt_generated_at')).tzinfo is not None
    assert result=={k:state[k] for k in ['status','begun_at','revoked_read_failed_at','local_credentials_removed_at','reauthorized_read_passed_at']}


def test_receipt_cli_reads_only_state_no_keychain_or_network(tmp_path,monkeypatch,capsys):
    import json
    from broker_proxy import revocation
    module=tmp_path/'release'/'app'/'broker_proxy'/'revocation.py'
    module.parent.mkdir(parents=True)
    state=tmp_path/'state'/'revocation.json'
    state.parent.mkdir()
    state.write_text(json.dumps({'status':'AWAITING_REMOTE_REVOKE','begun_at':'2026-09-30T20:30:00+00:00','token_fingerprint':'PRIVATE'}))
    before=state.read_bytes()
    monkeypatch.setattr(revocation,'__file__',str(module))
    monkeypatch.setattr('broker_proxy.identity.require_proxy_identity',lambda:None)
    def forbidden(*a,**kw): raise AssertionError('No credential access')
    monkeypatch.setattr('broker_proxy.oauth.KeychainOAuthStorage',forbidden)
    monkeypatch.setattr('sys.argv',['revocation','receipt'])
    assert revocation.main()==0
    result=json.loads(capsys.readouterr().out)
    assert result.pop('receipt_generated_at')
    assert result=={'status':'AWAITING_REMOTE_REVOKE','begun_at':'2026-09-30T20:30:00+00:00'}
    assert state.read_bytes()==before


def test_receipt_rejects_secret_in_known_field():
    import pytest
    from broker_proxy.revocation import receipt
    with pytest.raises(ValueError,match='INVALID_DRILL_RECEIPT'):
        receipt({'status':'COMPLETED','begun_at':'PRIVATE'})


def test_completed_receipt_requires_all_events_in_order():
    import pytest
    from broker_proxy.revocation import receipt
    keys=['begun_at','revoked_read_failed_at','local_credentials_removed_at','reauthorized_read_passed_at']
    valid={'status':'COMPLETED',**{key:f'2026-09-30T20:{30+i}:00+00:00' for i,key in enumerate(keys)}}
    for missing in keys:
        with pytest.raises(ValueError,match='INVALID_DRILL_RECEIPT'):
            receipt({k:v for k,v in valid.items() if k!=missing})
    for left,right in zip(keys,keys[1:]):
        bad={**valid,left:valid[right],right:valid[left]}
        with pytest.raises(ValueError,match='INVALID_DRILL_RECEIPT'):
            receipt(bad)


def test_old_drill_stays_old_when_receipt_is_regenerated():
    from broker_proxy.revocation import receipt
    state={'status':'COMPLETED',**{k:'2026-09-28T20:30:00+00:00' for k in
        ['begun_at','revoked_read_failed_at','local_credentials_removed_at','reauthorized_read_passed_at']}}
    result=receipt(state)
    assert result['begun_at']=='2026-09-28T20:30:00+00:00'
    assert result['receipt_generated_at']!=result['begun_at']
