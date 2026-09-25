"""Unit tests for the active plugin Tracker and ``Loader.load_all``."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from kernel.bus import EventBus
from kernel.envelope import Event
from kernel.loader import Loader
from kernel.manifest import Manifest
from kernel.plugin import Plugin
from kernel.registry import TypeRegistry
from kernel.tests._plugin_builder import (
    EMPTY_PLUGIN_SOURCE,
    PING_EVENTS,
    build_ping_chain,
    build_plugin,
    demo_plugin_source,
)
from kernel.tracker import Tracker


@pytest.fixture(autouse=True)
def _restore_import_state() -> Iterator[None]:
    modules_before = set(sys.modules)
    path_before = list(sys.path)
    yield
    for name in set(sys.modules) - modules_before:
        del sys.modules[name]
    sys.path[:] = path_before
    importlib.invalidate_caches()


@pytest.fixture
def bus() -> Iterator[EventBus]:
    instance = EventBus(TypeRegistry())
    instance.start()
    yield instance
    instance.stop()


class FakePlugin(Plugin):
    pass


def make_plugin(plugin_id: str, requires: tuple[str, ...] = ()) -> Plugin:
    plugin = FakePlugin()
    plugin.manifest = Manifest(id=plugin_id, entry="plugin:FakePlugin", requires=requires)
    return plugin


def make_chain_loader(root: Path) -> Loader:
    build_ping_chain(root)
    return Loader([root], TypeRegistry())


def test_add_and_get_round_trip(bus: EventBus) -> None:
    tracker = Tracker(bus)
    plugin = make_plugin("kuestion.alpha")

    tracker.add(plugin)

    assert tracker.get("kuestion.alpha") is plugin


def test_active_ids_lists_added_plugins(bus: EventBus) -> None:
    tracker = Tracker(bus)

    tracker.add(make_plugin("kuestion.alpha"))
    tracker.add(make_plugin("kuestion.beta"))

    assert tracker.active_ids() == ["kuestion.alpha", "kuestion.beta"]


def test_remove_drops_plugin(bus: EventBus) -> None:
    tracker = Tracker(bus)
    tracker.add(make_plugin("kuestion.alpha"))

    tracker.remove("kuestion.alpha")

    assert tracker.get("kuestion.alpha") is None


def test_dependents_are_transitive(bus: EventBus) -> None:
    tracker = Tracker(bus)
    tracker.add(make_plugin("kuestion.alpha"))
    tracker.add(make_plugin("kuestion.beta", requires=("kuestion.alpha",)))
    tracker.add(make_plugin("kuestion.gamma", requires=("kuestion.beta",)))

    assert tracker.dependents("kuestion.alpha") == {"kuestion.beta", "kuestion.gamma"}


def test_load_all_reports_loaded_plugins(tmp_path: Path, bus: EventBus) -> None:
    loader = make_chain_loader(tmp_path / "plugins")

    summary = loader.load_all(bus, Tracker(bus))

    assert summary.loaded == ("kuestion.alpha", "kuestion.beta", "kuestion.gamma")
    assert summary.failed == ()


def test_load_all_activates_plugins(tmp_path: Path, bus: EventBus) -> None:
    loader = make_chain_loader(tmp_path / "plugins")
    tracker = Tracker(bus)

    loader.load_all(bus, tracker)

    assert tracker.active_ids() == ["kuestion.alpha", "kuestion.beta", "kuestion.gamma"]


def test_load_all_mixes_success_and_failure(tmp_path: Path, bus: EventBus) -> None:
    root = tmp_path / "plugins"
    build_plugin(root, "alpha", plugin_id="kuestion.alpha", plugin_source=EMPTY_PLUGIN_SOURCE)
    build_plugin(root, "beta", plugin_id="kuestion.beta", plugin_source="raise RuntimeError('boom')\n")
    loader = Loader([root], TypeRegistry())
    tracker = Tracker(bus)

    summary = loader.load_all(bus, tracker)

    assert summary.loaded == ("kuestion.alpha",)
    assert tracker.active_ids() == ["kuestion.alpha"]


def test_broken_plugin_import_fails_at_entry_stage(tmp_path: Path, bus: EventBus) -> None:
    root = tmp_path / "plugins"
    build_plugin(root, "beta", plugin_id="kuestion.beta", plugin_source="raise RuntimeError('boom')\n")
    loader = Loader([root], TypeRegistry())

    summary = loader.load_all(bus, Tracker(bus))

    assert summary.failed[0].plugin_id == "kuestion.beta"
    assert summary.failed[0].stage == "entry"


def test_subscription_not_declared_in_manifest_fails_at_entry_stage(
    tmp_path: Path, bus: EventBus
) -> None:
    root = tmp_path / "plugins"
    build_plugin(
        root,
        "alpha",
        plugin_id="kuestion.alpha",
        events_source=PING_EVENTS,
        imports="from .events import Ping",
        consumes=(),
        plugin_source=demo_plugin_source("Ping"),
    )
    loader = Loader([root], TypeRegistry())

    summary = loader.load_all(bus, Tracker(bus))

    assert summary.failed[0].stage == "entry"
    assert "Ping" in summary.failed[0].error


def test_loaded_plugin_consumes_events(tmp_path: Path, bus: EventBus) -> None:
    loader = make_chain_loader(tmp_path / "plugins")
    loader.load_all(bus, Tracker(bus))
    ping = importlib.import_module("plugins.alpha.events")

    bus.emit(Event(event_type=ping.Ping, payload=ping.Ping(), sender_id="kuestion.sender"))
    bus.wait_idle()

    assert len(importlib.import_module("plugins.alpha.plugin").RECEIVED) == 1
