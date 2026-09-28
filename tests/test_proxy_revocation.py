from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest

NOW = datetime(2026,9,28,22,tzinfo=timezone.utc)


@pytest.mark.asyncio
@pytest.mark.parametrize('status,expected', [(401, 'AUTH_REJECTED'),
    (403, 'AUTH_REJECTED'), (500, 'INCONCLUSIVE')])
async def test_probe_preserves_http_rejection_through_mcp_translation(monkeypatch, status, expected):
    """Losing HTTP status in SDK error translation must not lose rejection proof."""
    import httpx2
    import mcp.shared._httpx_utils as http_utils
    from broker_proxy.revocation import probe_existing_token
    def respond(request):
        return httpx2.Response(status, json={'error': 'test response'})
    def client(**kwargs):
        return httpx2.AsyncClient(transport=httpx2.MockTransport(respond), **kwargs)
    monkeypatch.setattr(http_utils, 'create_mcp_http_client', client)
    assert await probe_existing_token('test-only-bearer') == expected


class Storage:
    def __init__(self):
        self.token = 'private-test-token'
        self.expires = NOW + timedelta(days=2)
        self.deleted = False
        self.metadata_present = True
    async def get_tokens(self):
        return SimpleNamespace(access_token=self.token) if self.token else None
    def authorization_status(self):
        return {'expires_at':self.expires.isoformat()}
    def delete_tokens_and_client_info(self):
        self.deleted = True
        self.token = None
        self.metadata_present = False
    def credentials_absent(self):
        return self.token is None and not self.metadata_present


@pytest.mark.asyncio
async def test_drill_requires_success_rejection_then_new_authorization(tmp_path):
    from broker_proxy.revocation import advance
    state = tmp_path / 'drill.json'
    storage = Storage()
    async def success(token): return 'READ_SUCCEEDED'
    async def rejected(token): return 'AUTH_REJECTED'
    assert (await advance('begin', state, storage, success, NOW))['status'] == 'AWAITING_REMOTE_REVOKE'
    assert 'private-test-token' not in state.read_text()
    assert state.stat().st_mode & 0o077 == 0
    assert (await advance('verify-revoked', state, storage, rejected, NOW))['status'] == 'REMOTE_REJECTION_VERIFIED'
    await advance('remove-local-credentials', state, storage, rejected, NOW)
    assert storage.deleted
    storage.token = 'new-private-test-token'
    assert (await advance('verify-reauthorized', state, storage, success, NOW))['status'] == 'COMPLETED'


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['INCONCLUSIVE','READ_SUCCEEDED'])
async def test_timeout_or_still_valid_token_is_not_revocation_proof(tmp_path, failure):
    from broker_proxy.revocation import advance
    state=tmp_path/'drill.json'; storage=Storage()
    async def success(token): return 'READ_SUCCEEDED'
    await advance('begin',state,storage,success,NOW)
    async def bad(token): return failure
    with pytest.raises(ValueError,match='REMOTE_REVOCATION_NOT_PROVEN'):
        await advance('verify-revoked',state,storage,bad,NOW)
    assert not storage.deleted


@pytest.mark.asyncio
@pytest.mark.parametrize('changed', ['expired','changed_token','deleted_token'])
async def test_changed_or_expired_credential_cannot_prove_remote_revocation(tmp_path,changed):
    from broker_proxy.revocation import advance
    state=tmp_path/'drill.json'; storage=Storage()
    async def success(token): return 'READ_SUCCEEDED'
    await advance('begin',state,storage,success,NOW)
    if changed=='expired': storage.expires=NOW
    elif changed=='changed_token': storage.token='replacement'
    else: storage.token=None
    async def forbidden(token): raise AssertionError('Must reject before probe')
    with pytest.raises(ValueError):
        await advance('verify-revoked',state,storage,forbidden,NOW)


@pytest.mark.asyncio
async def test_cannot_delete_credential_before_remote_rejection(tmp_path):
    from broker_proxy.revocation import advance
    state=tmp_path/'drill.json'; storage=Storage()
    async def success(token): return 'READ_SUCCEEDED'
    await advance('begin',state,storage,success,NOW)
    with pytest.raises(ValueError,match='INVALID_DRILL_STATE'):
        await advance('remove-local-credentials',state,storage,success,NOW)
    assert not storage.deleted


@pytest.mark.parametrize('status,expected', [(401,'AUTH_REJECTED'),(403,'AUTH_REJECTED'),(500,'INCONCLUSIVE')])
def test_only_http_authorization_rejections_are_evidence(status,expected):
    import httpx2
    from broker_proxy.revocation import classify_probe_error
    response=httpx2.Response(status,request=httpx2.Request('POST','https://agent.robinhood.com/mcp/trading'))
    error=httpx2.HTTPStatusError('redacted',request=response.request,response=response)
    assert classify_probe_error(error)==expected
    assert classify_probe_error(ExceptionGroup('transport',[error]))==expected
    assert classify_probe_error(ExceptionGroup('mixed',[error,TimeoutError()]))=='INCONCLUSIVE'


@pytest.mark.asyncio
async def test_changed_registration_cannot_continue_prior_drill(tmp_path):
    from broker_proxy.revocation import advance
    state=tmp_path/'drill.json'; storage=Storage()
    async def success(token): return 'READ_SUCCEEDED'
    await advance('begin',state,storage,success,NOW,bindings={'config':'old'})
    with pytest.raises(ValueError,match='DRILL_CONFIGURATION_CHANGED'):
        await advance('verify-revoked',state,storage,success,NOW,bindings={'config':'new'})


@pytest.mark.asyncio
async def test_expiry_during_probe_is_not_remote_revocation(tmp_path):
    from broker_proxy.revocation import advance
    state=tmp_path/'drill.json'; storage=Storage()
    async def success(token): return 'READ_SUCCEEDED'
    await advance('begin',state,storage,success,NOW)
    async def rejected(token): return 'AUTH_REJECTED'
    with pytest.raises(ValueError,match='AUTH_EXPIRED'):
        await advance('verify-revoked',state,storage,rejected,NOW,
                      clock=lambda:storage.expires)


@pytest.mark.asyncio
async def test_partial_deletion_can_retry_without_original_token(tmp_path):
    from broker_proxy.revocation import advance
    state=tmp_path/'drill.json'; storage=Storage()
    async def success(token): return 'READ_SUCCEEDED'
    async def rejected(token): return 'AUTH_REJECTED'
    await advance('begin',state,storage,success,NOW)
    await advance('verify-revoked',state,storage,rejected,NOW)
    original=storage.delete_tokens_and_client_info
    def partial():
        storage.token=None
        raise RuntimeError('Interrupted')
    storage.delete_tokens_and_client_info=partial
    with pytest.raises(RuntimeError):
        await advance('remove-local-credentials',state,storage,rejected,NOW)
    storage.delete_tokens_and_client_info=original
    assert (await advance('remove-local-credentials',state,storage,rejected,NOW))['status']=='AWAITING_REAUTHORIZATION'
    assert storage.credentials_absent()


@pytest.mark.asyncio
async def test_delete_state_save_failure_does_not_delete_tokens(tmp_path,monkeypatch):
    from broker_proxy import revocation
    state=tmp_path/'drill.json'; storage=Storage()
    async def success(token): return 'READ_SUCCEEDED'
    async def rejected(token): return 'AUTH_REJECTED'
    await revocation.advance('begin',state,storage,success,NOW)
    await revocation.advance('verify-revoked',state,storage,rejected,NOW)
    def cannot_save(*args): raise OSError('disk unavailable')
    monkeypatch.setattr(revocation,'_save',cannot_save)
    with pytest.raises(OSError):
        await revocation.advance('remove-local-credentials',state,storage,rejected,NOW)
    assert not storage.deleted


def test_keychain_absence_checks_tokens_timing_and_client_registration():
    from broker_proxy.oauth import KeychainOAuthStorage
    class Backend:
        values={}
        def get_password(self,service,account): return self.values.get(account)
    backend=Backend(); storage=KeychainOAuthStorage(backend=backend)
    assert storage.credentials_absent()
    for field in ('tokens','token_timing','client_info'):
        backend.values={field:'present'}
        assert not storage.credentials_absent()
