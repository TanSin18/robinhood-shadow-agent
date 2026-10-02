"""Collector configuration, read from the environment at run time. Values are never printed, logged or stored.

The operator keeps research-provider secrets in the macOS Keychain and passes them to one collector run, e.g.

    FIRM_LAB_MASSIVE_API_KEY="$(security find-generic-password -s firm-lab-research -a massive -w)" python -m firm_lab_collectors.cli massive ...

These are research-data credentials only. Nothing here reads, needs or touches brokerage authentication.
"""
from __future__ import annotations

import os

SEC_USER_AGENT = 'FIRM_LAB_SEC_USER_AGENT'            # "Name contact@example.com": the SEC asks every automated client to identify itself
MASSIVE_API_KEY = 'FIRM_LAB_MASSIVE_API_KEY'
SHARADAR_API_KEY = 'FIRM_LAB_SHARADAR_API_KEY'
SHARADAR_CHANNEL = 'FIRM_LAB_SHARADAR_CHANNEL'        # "direct" (api.sharadar.com) or "nasdaq" (Nasdaq Data Link)
THETADATA_TERMINAL = 'FIRM_LAB_THETADATA_TERMINAL'    # "1" once the operator has a subscription and has started Theta Terminal locally
NAMES = (SEC_USER_AGENT, MASSIVE_API_KEY, SHARADAR_API_KEY, SHARADAR_CHANNEL, THETADATA_TERMINAL)


def value(name, environ=None):
    text = (environ if environ is not None else os.environ).get(name, '')
    return text.strip() or None


def sec_user_agent(environ=None):
    """The declared User-Agent, or None. It must carry a contact address; a made-up or empty one is refused."""
    text = value(SEC_USER_AGENT, environ)
    if not text or '@' not in text or len(text) > 200 or '\n' in text or '\r' in text:
        return None
    return text


def sharadar_channel(environ=None):
    text = (value(SHARADAR_CHANNEL, environ) or '').lower()
    return text if text in ('direct', 'nasdaq') else None


def states(environ=None) -> dict:
    """Which providers are configured. Booleans only: no value, length or fragment of any setting is returned."""
    return {'SEC EDGAR': bool(sec_user_agent(environ)), 'Massive': bool(value(MASSIVE_API_KEY, environ)),
            'Sharadar': bool(value(SHARADAR_API_KEY, environ)) and bool(sharadar_channel(environ)),
            'ThetaData': value(THETADATA_TERMINAL, environ) == '1',
            'U.S. Treasury Fiscal Data': True}                    # public data: nothing to configure
