"""Read-only preflight for the dedicated broker proxy OS boundary."""
from __future__ import annotations

import argparse
import grp
import json
import os
import pwd
import stat
from pathlib import Path

from broker_proxy.config import load_broker_proxy_config


def check(config_path='config/broker-proxy.local.yaml') -> dict:
    config = load_broker_proxy_config(config_path)
    failures = []
    try:
        proxy = pwd.getpwnam(config.proxy_user)
    except KeyError:
        proxy = None; failures.append('PROXY_USER_MISSING')
    try:
        group = grp.getgrnam(config.socket_group)
    except KeyError:
        group = None; failures.append('SOCKET_GROUP_MISSING')
    if proxy and proxy.pw_uid == config.operator_uid:
        failures.append('PROXY_NOT_SEPARATE_IDENTITY')
    if group and config.proxy_user not in group.gr_mem:
        failures.append('PROXY_GROUP_MEMBERSHIP_MISSING')
    if group:
        try:
            operator = pwd.getpwuid(config.operator_uid).pw_name
            if operator not in group.gr_mem:
                failures.append('OPERATOR_GROUP_MEMBERSHIP_MISSING')
        except KeyError:
            failures.append('OPERATOR_UID_UNKNOWN')
    runtime = config.socket_path.parent
    if runtime.exists():
        details = runtime.stat()
        if stat.S_IMODE(details.st_mode) != 0o770:
            failures.append('RUNTIME_MODE_INVALID')
        if proxy and details.st_uid != proxy.pw_uid:
            failures.append('RUNTIME_OWNER_INVALID')
        if group and details.st_gid != group.gr_gid:
            failures.append('RUNTIME_GROUP_INVALID')
    else:
        failures.append('RUNTIME_DIRECTORY_MISSING')
    return {'status':'PASSED' if not failures else 'FAILED',
            'proxy_identity_separate': bool(proxy and proxy.pw_uid != config.operator_uid),
            'socket_group_verified': bool(group), 'failures':failures}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='config/broker-proxy.local.yaml')
    args=parser.parse_args(); result=check(args.config)
    print(json.dumps(result,sort_keys=True))
    return 0 if result['status']=='PASSED' else 2


if __name__=='__main__': raise SystemExit(main())

