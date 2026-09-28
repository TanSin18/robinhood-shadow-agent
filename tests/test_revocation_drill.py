from datetime import datetime, timedelta, timezone

import pytest


NOW = datetime(2026, 9, 28, 14, tzinfo=timezone.utc)


def drill(tmp_path):
    from scripts.robinhood_revocation_drill import RevocationDrill
    return RevocationDrill(tmp_path / 'agent.db', config_hash='c' * 64,
                           preregistration_hash='p' * 64)


def test_local_delete_without_failed_remote_read_cannot_complete_revocation(tmp_path):
    subject = drill(tmp_path)
    subject.begin(NOW)
    with pytest.raises(ValueError, match='failed revoked-credential read'):
        subject.record_local_credentials_removed(NOW + timedelta(minutes=1))


@pytest.mark.parametrize('error_class', ['AUTH_EXPIRED', 'TIMEOUT', 'SOCKET_REFUSED', 'POLICY_ERROR', 'MALFORMED_RESPONSE'])
def test_non_authentication_failures_are_not_revocation_proof(tmp_path, error_class):
    subject = drill(tmp_path)
    subject.begin(NOW)
    with pytest.raises(ValueError, match='authentication-class'):
        subject.record_revoked_read_failure(error_class, NOW + timedelta(minutes=1))


def test_reauthorization_requires_fresh_read_exact_inventory_and_hashes(tmp_path):
    from broker.read_contracts import READ_METHODS
    subject = drill(tmp_path)
    subject.begin(NOW)
    subject.record_revoked_read_failure('AUTH_REVOKED', NOW + timedelta(minutes=1))
    subject.record_local_credentials_removed(NOW + timedelta(minutes=2))
    wrong = {'effective_read_tools': ['get_accounts'], 'effective_write_tool_count': 0,
             'config_hash': 'c' * 64, 'preregistration_hash': 'p' * 64}
    with pytest.raises(ValueError, match='exact read inventory'):
        subject.verify_reauthorized(greeting=wrong, read_succeeded=True,
                                    now=NOW + timedelta(minutes=3))
    receipt = subject.verify_reauthorized(greeting={
        **wrong, 'effective_read_tools': sorted(READ_METHODS)
    }, read_succeeded=True, now=NOW + timedelta(minutes=3))
    assert receipt['status'] == 'COMPLETED'
    assert set(receipt) == {
        'status', 'begun_at', 'revoked_read_failed_at',
        'local_credentials_removed_at', 'reauthorized_read_passed_at',
        'preregistration_hash', 'config_hash',
    }
