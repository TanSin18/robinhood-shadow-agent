"""Fail closed before accessing the dedicated proxy's credentials."""

import grp
import os
import pwd


def require_proxy_identity() -> None:
    try:
        identity = pwd.getpwnam("robinhoodproxy")
        if os.geteuid() != identity.pw_uid:
            raise RuntimeError("PROXY_IDENTITY_REQUIRED")
        admin_gid = grp.getgrnam("admin").gr_gid
        groups = os.getgrouplist(identity.pw_name, identity.pw_gid)
    except KeyError as error:
        raise RuntimeError("PROXY_IDENTITY_UNVERIFIED") from error
    if admin_gid in groups:
        raise RuntimeError("PROXY_MUST_BE_STANDARD_USER")
