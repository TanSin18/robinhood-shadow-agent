def test_receipt_is_positive_allowlist_not_blacklist():
    from broker_proxy.revocation import receipt
    state={'status':'COMPLETED','begun_at':'2026-09-30T20:30:00+00:00',
           'revoked_read_failed_at':'2026-09-30T20:32:00+00:00',
           'local_credentials_removed_at':'2026-09-30T20:33:00+00:00',
           'reauthorized_read_passed_at':'2026-09-30T20:35:00+00:00',
           'token_fingerprint':'PRIVATE','bindings':{'config_hash':'PRIVATE'},
           'unexpected_secret':'PRIVATE','account_id':'PRIVATE'}
    assert receipt(state)=={k:state[k] for k in ['status','begun_at','revoked_read_failed_at','local_credentials_removed_at','reauthorized_read_passed_at']}


def test_receipt_cli_reads_only_state_no_keychain_or_network(tmp_path,monkeypatch,capsys):
    import json
    from broker_proxy import revocation
    module=tmp_path/'release'/'app'/'broker_proxy'/'revocation.py'
    module.parent.mkdir(parents=True)
    state=tmp_path/'state'/'revocation.json'
    state.parent.mkdir()
    state.write_text(json.dumps({'status':'COMPLETED','begun_at':'2026-09-30T20:30:00+00:00','token_fingerprint':'PRIVATE'}))
    before=state.read_bytes()
    monkeypatch.setattr(revocation,'__file__',str(module))
    monkeypatch.setattr('broker_proxy.identity.require_proxy_identity',lambda:None)
    def forbidden(*a,**kw): raise AssertionError('No credential access')
    monkeypatch.setattr('broker_proxy.oauth.KeychainOAuthStorage',forbidden)
    monkeypatch.setattr('sys.argv',['revocation','receipt'])
    assert revocation.main()==0
    assert json.loads(capsys.readouterr().out)=={'status':'COMPLETED','begun_at':'2026-09-30T20:30:00+00:00'}
    assert state.read_bytes()==before


def test_receipt_rejects_secret_in_known_field():
    import pytest
    from broker_proxy.revocation import receipt
    with pytest.raises(ValueError,match='INVALID_DRILL_RECEIPT'):
        receipt({'status':'COMPLETED','begun_at':'PRIVATE'})
