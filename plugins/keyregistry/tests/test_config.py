"""Unit tests for the model-entry registry, its header table and persistence."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from plugins.keyregistry.src.config import HeaderRow, ModelEntry, ModelRegistry


def make_entry(name: str = "local", **overrides: object) -> ModelEntry:
    fields: dict = {
        "name": name,
        "base_url": "http://localhost:1234/v1",
        "model_id": "gpt-local",
    }
    fields.update(overrides)
    return ModelEntry(**fields)


def test_added_entry_is_retrievable() -> None:
    registry = ModelRegistry()

    registry.add(make_entry("local"))

    assert registry.get("local").model_id == "gpt-local"


def test_removed_entry_is_gone() -> None:
    registry = ModelRegistry()
    registry.add(make_entry("local"))

    registry.remove("local")

    assert registry.get("local") is None


def test_entries_are_sorted_by_name() -> None:
    registry = ModelRegistry()
    registry.add(make_entry("zeta"))
    registry.add(make_entry("alpha"))

    assert [entry.name for entry in registry.entries()] == ["alpha", "zeta"]


def test_header_row_is_appended_to_entry() -> None:
    registry = ModelRegistry()
    registry.add(make_entry("local"))

    registry.add_header("local", "X-Custom", "value")

    assert registry.get("local").headers == [HeaderRow("X-Custom", "value")]


def test_header_row_is_removed_by_index() -> None:
    registry = ModelRegistry()
    registry.add(make_entry("local"))
    registry.add_header("local", "A", "1")
    registry.add_header("local", "B", "2")

    registry.remove_header("local", 0)

    assert registry.get("local").headers == [HeaderRow("B", "2")]


def test_names_lists_entries_sorted() -> None:
    registry = ModelRegistry()
    registry.add(make_entry("zeta"))
    registry.add(make_entry("alpha"))

    assert registry.names() == ["alpha", "zeta"]


def test_subscriber_is_notified_on_add() -> None:
    registry = ModelRegistry()
    notifications: list[list[str]] = []
    registry.subscribe(lambda: notifications.append(registry.names()))

    registry.add(make_entry("local"))

    assert notifications == [["local"]]


def test_subscriber_is_notified_on_header_change() -> None:
    registry = ModelRegistry()
    registry.add(make_entry("local"))
    notifications: list[int] = []
    registry.subscribe(lambda: notifications.append(len(registry.get("local").headers)))

    registry.add_header("local", "A", "1")

    assert notifications == [1]


def test_subscriber_is_notified_on_remove_header() -> None:
    registry = ModelRegistry()
    registry.add(make_entry("local"))
    registry.add_header("local", "A", "1")
    notifications: list[int] = []
    registry.subscribe(lambda: notifications.append(len(registry.get("local").headers)))

    registry.remove_header("local", 0)

    assert notifications == [0]


def test_subscriber_is_notified_on_remove() -> None:
    registry = ModelRegistry()
    registry.add(make_entry("local"))
    notifications: list[int] = []
    registry.subscribe(lambda: notifications.append(len(registry.names())))

    registry.remove("local")

    assert notifications == [0]


def test_adding_header_to_unknown_entry_raises() -> None:
    registry = ModelRegistry()

    with pytest.raises(KeyError):
        registry.add_header("missing", "A", "1")


def test_removing_header_from_unknown_entry_raises() -> None:
    registry = ModelRegistry()

    with pytest.raises(KeyError):
        registry.remove_header("missing", 0)


def test_concurrent_adds_are_all_recorded() -> None:
    registry = ModelRegistry()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda n: registry.add(make_entry(f"entry-{n:03d}")), range(200)))

    assert len(registry.names()) == 200


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    return tmp_path / "models.json"


def persisted_names(path: Path) -> list[str]:
    return [item["name"] for item in json.loads(path.read_text())]


def test_entries_round_trip_through_the_config_file(config_path: Path) -> None:
    registry = ModelRegistry(config_path)
    registry.add(
        make_entry(
            "local",
            model_id="gpt-local",
            api_key="sk-1",
            headers=[HeaderRow("X-A", "1")],
        )
    )

    reloaded = ModelRegistry(config_path).get("local")

    assert (reloaded.model_id, reloaded.api_key) == ("gpt-local", "sk-1")
    assert reloaded.headers == [HeaderRow("X-A", "1")]


def test_missing_config_file_starts_empty(config_path: Path) -> None:
    registry = ModelRegistry(config_path)

    assert registry.entries() == []


def test_corrupt_config_file_starts_empty(config_path: Path) -> None:
    config_path.write_text("{ not valid json")

    registry = ModelRegistry(config_path)

    assert registry.names() == []


def test_non_array_config_file_starts_empty(config_path: Path) -> None:
    config_path.write_text(json.dumps({"models": []}))

    registry = ModelRegistry(config_path)

    assert registry.names() == []


def test_invalid_entry_in_config_file_is_skipped(config_path: Path) -> None:
    config_path.write_text(
        json.dumps([{"name": "ok", "base_url": "u", "model_id": "m"}, {"nope": 1}])
    )

    registry = ModelRegistry(config_path)

    assert registry.names() == ["ok"]


def test_invalid_entry_is_not_rewritten_on_save(config_path: Path) -> None:
    config_path.write_text(
        json.dumps([{"name": "ok", "base_url": "u", "model_id": "m"}, {"nope": 1}])
    )
    registry = ModelRegistry(config_path)

    registry.add(make_entry("other"))

    assert persisted_names(config_path) == ["ok", "other"]


def test_add_is_persisted_to_config_file(config_path: Path) -> None:
    registry = ModelRegistry(config_path)

    registry.add(make_entry("local"))

    assert persisted_names(config_path) == ["local"]


def test_remove_is_persisted_to_config_file(config_path: Path) -> None:
    registry = ModelRegistry(config_path)
    registry.add(make_entry("local"))

    registry.remove("local")

    assert json.loads(config_path.read_text()) == []


def test_header_change_is_persisted_to_config_file(config_path: Path) -> None:
    registry = ModelRegistry(config_path)
    registry.add(make_entry("local"))

    registry.add_header("local", "X-A", "1")

    assert ModelRegistry(config_path).get("local").headers == [HeaderRow("X-A", "1")]


def test_config_file_is_owner_only(config_path: Path) -> None:
    registry = ModelRegistry(config_path)

    registry.add(make_entry("local"))

    assert config_path.stat().st_mode & 0o777 == 0o600
