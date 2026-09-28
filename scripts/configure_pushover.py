"""Store Pushover identifiers in macOS Keychain without echoing them."""
from __future__ import annotations

import subprocess
from collections.abc import Callable


SERVICE = 'com.openai.robinhood-shadow.pushover'
ACCOUNTS = ('PUSHOVER_USER', 'PUSHOVER_TOKEN')


def configure(*, runner: Callable[..., object] = subprocess.run) -> None:
    labels = {
        'PUSHOVER_USER': '30-character Pushover User Key',
        'PUSHOVER_TOKEN': '30-character Application API Token',
    }
    for account in ACCOUNTS:
        print(f'Enter the {labels[account]} in the secure macOS Keychain prompt.')
        runner(
            ['/usr/bin/security', 'add-generic-password', '-U', '-s', SERVICE,
             '-a', account, '-w'],
            check=True,
        )
    print('Pushover identifiers saved in macOS Keychain.')


if __name__ == '__main__':
    configure()
