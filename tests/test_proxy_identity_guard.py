from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('uid,groups,allowed', [
    (501, [20, 80], False),
    (503, [20, 501], False),
    (502, [20, 80, 501], False),
    (502, [20, 501], True),
])
def test_only_dedicated_non_admin_identity_can_authorize(monkeypatch, uid, groups, allowed):
    from broker_proxy.identity import require_proxy_identity
    import os, pwd, grp

    monkeypatch.setattr(os, 'geteuid', lambda: uid)
    monkeypatch.setattr(pwd, 'getpwnam', lambda _: SimpleNamespace(pw_uid=502, pw_gid=20, pw_name='robinhoodproxy'))
    monkeypatch.setattr(os, 'getgrouplist', lambda *_: groups)
    monkeypatch.setattr(grp, 'getgrnam', lambda _: SimpleNamespace(gr_gid=80))
    if allowed:
        require_proxy_identity()
    else:
        with pytest.raises(RuntimeError, match='PROXY_'):
            require_proxy_identity()


def test_authorization_cli_rejects_main_user_before_oauth(monkeypatch, capsys):
    import os, sys
    from scripts import authorize_robinhood

    import pwd
    monkeypatch.setattr(os, 'geteuid', lambda: 501)
    # The dedicated proxy account exists on the operator's Mac; model it so the check is portable.
    monkeypatch.setattr(pwd, 'getpwnam', lambda _: SimpleNamespace(pw_uid=502, pw_gid=20, pw_name='robinhoodproxy'))
    monkeypatch.setattr(sys, 'argv', ['authorize_robinhood'])
    async def forbidden():
        raise AssertionError('OAuth was entered from the main user')
    monkeypatch.setattr(authorize_robinhood, '_authorize', forbidden)
    assert authorize_robinhood.main() == 2
    assert 'PROXY_IDENTITY_REQUIRED' in capsys.readouterr().out
