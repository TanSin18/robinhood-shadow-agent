"""Unit tests cannot accidentally use the live brokerage collector."""
import pytest
from pathlib import Path
import shutil
import yaml


@pytest.fixture
def portable_settings(tmp_path):
    """Synthetic settings; never load the operator's private configuration."""
    root = Path(__file__).resolve().parents[1]
    raw = yaml.safe_load((root / 'config/settings.yaml').read_text())
    raw['notifications']['dashboard_base_url'] = 'https://shadow-fixture.example.ts.net:8443'
    raw['risk']['agentic_account_id'] = 'fixture-agentic-account'
    path = tmp_path / 'settings.yaml'
    path.write_text(yaml.safe_dump(raw))
    return path


@pytest.fixture
def proxy_source_tree(tmp_path):
    from scripts.build_private_proxy import SOURCES
    root = Path(__file__).resolve().parents[1]
    target = tmp_path / 'proxy-source'
    for name in SOURCES:
        source = root / ('config/broker-proxy.yaml' if name == 'config/broker-proxy.local.yaml' else name)
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    # Exercise exclusion rules against real forbidden inputs, not absent paths.
    for name in ('agents/worker.py', 'broker/robinhood.py', 'data/fixture.db'):
        sentinel = target / name
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text('synthetic forbidden bundle input\n')
    return target

@pytest.fixture(autouse=True)
def no_live_collector(monkeypatch):
    def forbidden(*args,**kwargs):
        raise AssertionError('Live brokerage collector is forbidden in unit tests; inject a fake reader')
    monkeypatch.setattr('agents.market_reader.LiveReader',forbidden)
