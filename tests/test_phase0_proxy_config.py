from __future__ import annotations

import json
from pathlib import Path

from config.loader import load_config


def test_main_config_has_socket_but_no_robinhood_oauth_identifier() -> None:
    config = load_config("config/settings.yaml")

    assert config.broker_proxy_socket == Path("data/runtime/robinhood-read.sock")
    assert not hasattr(config, "oauth")
    encoded = json.dumps(config.model_dump(mode="json")).casefold()
    assert "com.openai.robinhood-shadow.oauth" not in encoded
