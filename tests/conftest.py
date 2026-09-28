"""Unit tests cannot accidentally use the live brokerage collector."""
import pytest

@pytest.fixture(autouse=True)
def no_live_collector(monkeypatch):
    def forbidden(*args,**kwargs):
        raise AssertionError('Live brokerage collector is forbidden in unit tests; inject a fake reader')
    monkeypatch.setattr('agents.market_reader.LiveReader',forbidden)
