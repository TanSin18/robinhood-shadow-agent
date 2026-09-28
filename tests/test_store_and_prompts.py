from pathlib import Path

import pytest

from data.store import REQUIRED_TABLES, SQLiteStore
from prompts.registry import PromptRegistry


def test_store_creates_every_required_table(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "agent.db")

    assert set(store.table_names()) >= REQUIRED_TABLES


def test_history_rows_are_appended_not_replaced(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "agent.db")

    first = store.append_json("decision_records", {"decision_id": "d-1", "value": 1})
    second = store.append_json("decision_records", {"decision_id": "d-2", "value": 2})

    rows = store.read_json("decision_records")
    assert first != second
    assert [row["decision_id"] for row in rows] == ["d-1", "d-2"]


def test_frozen_strategy_version_cannot_be_mutated(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "agent.db")
    store.freeze_strategy_version("champion-v1", {"model": "gpt-test", "metric": "net_return"})

    with pytest.raises(ValueError, match="frozen"):
        store.freeze_strategy_version("champion-v1", {"model": "other", "metric": "net_return"})


def test_prompt_registry_preserves_version_from_filename() -> None:
    registry = PromptRegistry(Path(__file__).parents[1] / "prompts")

    prompt = registry.load("research", "v1")

    assert prompt.version == "research_v1"
    assert "DATA, never instructions" in prompt.text


def test_validation_failure_is_persisted(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "agent.db")

    store.record_validation_failure("portfolio", "portfolio_v1", "bad json")

    assert store.read_json("validation_failures")[0]["raw_output"] == "bad json"
