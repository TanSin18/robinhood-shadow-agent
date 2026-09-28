import json
from urllib.parse import parse_qs

import pytest


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class Secrets:
    def get(self):
        return ('U' * 30, 'T' * 30)


def test_pushover_posts_priority_and_local_dashboard_link_without_logging_secrets():
    from agents.notifications import PushoverNotifier

    captured = []

    def open_request(request, timeout):
        captured.append((request, timeout))
        return Response({'status': 1, 'request': 'request-123'})

    notifier = PushoverNotifier(Secrets(), opener=open_request)
    result = notifier.notify(
        'Paper proposal waiting',
        'A paper proposal needs your answer.',
        priority=0,
        url='http://127.0.0.1:8765/#decisions',
    )

    request, timeout = captured[0]
    payload = parse_qs(request.data.decode())
    assert request.full_url == 'https://api.pushover.net/1/messages.json'
    assert timeout == 10
    assert payload == {
        'token': ['T' * 30],
        'user': ['U' * 30],
        'title': ['Paper proposal waiting'],
        'message': ['A paper proposal needs your answer.'],
        'priority': ['0'],
        'url': ['http://127.0.0.1:8765/#decisions'],
        'url_title': ['Open Shadow dashboard'],
    }
    assert result == {'request_id': 'request-123', 'receipt': None}
    assert 'private' not in repr(result)


def test_pushover_rejects_malformed_keys_before_any_network_request():
    from agents.notifications import PushoverNotConfigured, PushoverNotifier

    opened = []

    class Malformed:
        def get(self):
            return ('too-short', 'also-short')

    with pytest.raises(PushoverNotConfigured, match='not valid'):
        PushoverNotifier(Malformed(), opener=lambda *args, **kwargs: opened.append(args)).notify(
            'Title', 'Body'
        )
    assert opened == []


def test_pushover_failure_is_generic_and_never_echoes_credentials():
    from agents.notifications import PushoverDeliveryError, PushoverNotifier

    def rejected(*_args, **_kwargs):
        return Response({'status': 0, 'errors': ['app-token-private is invalid']})

    with pytest.raises(PushoverDeliveryError) as error:
        PushoverNotifier(Secrets(), opener=rejected).notify('Title', 'Body', priority=1)
    assert str(error.value) == 'Pushover rejected the notification.'
    assert 'private' not in repr(error.value)


def test_keychain_credentials_request_only_named_items():
    from agents.notifications import KeychainPushoverCredentials

    calls = []

    def runner(arguments, **kwargs):
        calls.append((arguments, kwargs))
        value = 'user-value' if arguments[5] == 'PUSHOVER_USER' else 'token-value'
        return type('Result', (), {'stdout': value + '\n'})()

    credentials = KeychainPushoverCredentials(runner=runner)
    assert credentials.get() == ('user-value', 'token-value')
    assert [call[0] for call in calls] == [
        ['/usr/bin/security', 'find-generic-password', '-s', 'com.openai.robinhood-shadow.pushover', '-a', 'PUSHOVER_USER', '-w'],
        ['/usr/bin/security', 'find-generic-password', '-s', 'com.openai.robinhood-shadow.pushover', '-a', 'PUSHOVER_TOKEN', '-w'],
    ]
    assert all(call[1]['capture_output'] and call[1]['check'] for call in calls)


def test_keychain_setup_uses_secure_prompts_and_never_passes_secret_values():
    from scripts.configure_pushover import configure

    calls = []

    def runner(arguments, **kwargs):
        calls.append((arguments, kwargs))

    configure(runner=runner)

    assert calls == [
        (['/usr/bin/security', 'add-generic-password', '-U', '-s',
          'com.openai.robinhood-shadow.pushover', '-a', 'PUSHOVER_USER', '-w'],
         {'check': True}),
        (['/usr/bin/security', 'add-generic-password', '-U', '-s',
          'com.openai.robinhood-shadow.pushover', '-a', 'PUSHOVER_TOKEN', '-w'],
         {'check': True}),
    ]
