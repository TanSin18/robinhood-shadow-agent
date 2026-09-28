from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Callable, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class Notifier(Protocol):
    def notify(self, title: str, body: str) -> None: ...


class MacOSNotifier:
    def __init__(self, runner: Callable[..., object] = subprocess.run) -> None:
        self._runner = runner

    def notify(self, title: str, body: str) -> None:
        self._runner(
            [
                "osascript",
                "-e",
                "on run argv",
                "-e",
                "display notification (item 2 of argv) with title (item 1 of argv)",
                "-e",
                "end run",
                "--",
                title,
                body,
            ],
            check=True,
            timeout=10,
        )


class PushoverDeliveryError(RuntimeError):
    """A deliberately non-sensitive Pushover delivery failure."""


class PushoverNotConfigured(PushoverDeliveryError):
    pass


class PushoverCredentials(Protocol):
    def get(self) -> tuple[str, str]: ...


class KeychainPushoverCredentials:
    """Read dedicated Pushover identifiers from macOS Keychain.

    Secret values are returned to the caller but never included in errors,
    database records, command output, or configuration files.
    """

    def __init__(
        self,
        *,
        service: str = 'com.openai.robinhood-shadow.pushover',
        user_account: str = 'PUSHOVER_USER',
        token_account: str = 'PUSHOVER_TOKEN',
        runner: Callable[..., object] = subprocess.run,
    ) -> None:
        self.service = service
        self.user_account = user_account
        self.token_account = token_account
        self._runner = runner

    def _read(self, account: str) -> str:
        try:
            result = self._runner(
                ['/usr/bin/security', 'find-generic-password', '-s', self.service,
                 '-a', account, '-w'],
                capture_output=True, text=True, check=True, timeout=10,
            )
            value = str(result.stdout).strip()
        except (OSError, subprocess.SubprocessError, AttributeError) as error:
            raise PushoverNotConfigured('Pushover credentials are not configured.') from None
        if not value:
            raise PushoverNotConfigured('Pushover credentials are not configured.')
        return value

    def get(self) -> tuple[str, str]:
        return self._read(self.user_account), self._read(self.token_account)


class EnvironmentPushoverCredentials:
    """Interactive fallback matching the existing Digital Twin names."""

    def get(self) -> tuple[str, str]:
        user = os.getenv('PUSHOVER_USER', '').strip()
        token = os.getenv('PUSHOVER_TOKEN', '').strip()
        if not user or not token:
            raise PushoverNotConfigured('Pushover credentials are not configured.')
        return user, token


class PushoverNotifier:
    endpoint = 'https://api.pushover.net/1/messages.json'

    def __init__(self, credentials: PushoverCredentials, *, opener=urlopen) -> None:
        self.credentials = credentials
        self._opener = opener

    def notify(
        self,
        title: str,
        body: str,
        *,
        priority: int = 0,
        url: str | None = None,
    ) -> dict[str, str | None]:
        if priority not in {-2, -1, 0, 1}:
            raise ValueError('Pushover priority must be between -2 and 1.')
        user, token = self.credentials.get()
        if not re.fullmatch(r'[A-Za-z0-9]{30}', user) or not re.fullmatch(r'[A-Za-z0-9]{30}', token):
            raise PushoverNotConfigured(
                'Pushover credentials are not valid 30-character Pushover keys.'
            )
        fields = {
            'token': token,
            'user': user,
            'title': title[:250],
            'message': body[:1024],
            'priority': str(priority),
        }
        if url:
            fields.update(url=url, url_title='Open Shadow dashboard')
        request = Request(
            self.endpoint,
            data=urlencode(fields).encode(),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST',
        )
        try:
            with self._opener(request, timeout=10) as response:
                payload = json.loads(response.read())
        except PushoverDeliveryError:
            raise
        except Exception:
            raise PushoverDeliveryError('Pushover delivery failed.') from None
        if payload.get('status') != 1:
            raise PushoverDeliveryError('Pushover rejected the notification.')
        return {'request_id': payload.get('request'), 'receipt': payload.get('receipt')}


def configured_notifiers(config, *, include_macos: bool = True) -> dict[str, object]:
    notifiers: dict[str, object] = {}
    if include_macos:
        notifiers['macos'] = MacOSNotifier()
    if config.notifications.pushover_enabled:
        credentials = KeychainPushoverCredentials(
            service=config.notifications.keychain_service,
            user_account=config.notifications.user_account,
            token_account=config.notifications.token_account,
        )
        notifiers['pushover'] = PushoverNotifier(credentials)
    return notifiers
