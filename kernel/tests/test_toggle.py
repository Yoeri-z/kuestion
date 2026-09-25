"""Unit tests for hot enable/disable of plugin dependency subtrees."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from kernel.bus import EventBus
from kernel.envelope import Event
from kernel.events import PluginLoadFailed, PluginLoaded, PluginUnloaded
from kernel.loader import Loader
from kernel.manifest import Manifest
from kernel.plugin import Plugin, consume
from kernel.registry import TypeRegistry
from kernel.tests._plugin_builder import build_ping_chain
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


class LifecycleRecorder(Plugin):
    def __init__(self) -> None:
        self.loaded: list[str] = []
        self.unloaded: list[str] = []
        self.failed: list[PluginLoadFailed] = []

    @consume(PluginLoaded)
    def _on_loaded(self, event: Event) -> None:
        self.loaded.append(event.payload.plugin_id)

    @consume(PluginUnloaded)
    def _on_unloaded(self, event: Event) -> None:
        self.unloaded.append(event.payload.plugin_id)

    @consume(PluginLoadFailed)
    def _on_failed(self, event: Event) -> None:
        self.failed.append(event.payload)


def observe(bus: EventBus) -> LifecycleRecorder:
    observer = LifecycleRecorder()
    observer.manifest = Manifest(id="kuestion.observer", entry="plugin:LifecycleRecorder")
    bus.register(observer)
    return observer


def load_chain(root: Path, bus: EventBus) -> Tracker:
    build_ping_chain(root)
    loader = Loader([root], TypeRegistry())
    tracker = Tracker(bus)
    loader.load_all(bus, tracker)
    return tracker


def emit_ping(bus: EventBus) -> None:
    ping = importlib.import_module("plugins.alpha.events")
    bus.emit(Event(event_type=ping.Ping, payload=ping.Ping(), sender_id="kuestion.sender"))


def test_disable_removes_subtree_from_active(tmp_path: Path, bus: EventBus) -> None:
    tracker = load_chain(tmp_path / "plugins", bus)

    tracker.disable_tree("kuestion.alpha")

    assert tracker.active_ids() == []


def test_disable_middle_plugin_keeps_upstream_active(tmp_path: Path, bus: EventBus) -> None:
    tracker = load_chain(tmp_path / "plugins", bus)

    tracker.disable_tree("kuestion.beta")

    assert tracker.active_ids() == ["kuestion.alpha"]


def test_disable_emits_unload_events_bottom_up(tmp_path: Path, bus: EventBus) -> None:
    observer = observe(bus)
    tracker = load_chain(tmp_path / "plugins", bus)

    tracker.disable_tree("kuestion.alpha")
    bus.wait_idle()

    assert observer.unloaded == ["kuestion.gamma", "kuestion.beta", "kuestion.alpha"]


def test_disabled_plugin_stops_consuming(tmp_path: Path, bus: EventBus) -> None:
    tracker = load_chain(tmp_path / "plugins", bus)
    tracker.disable_tree("kuestion.alpha")

    emit_ping(bus)
    bus.wait_idle()

    assert importlib.import_module("plugins.alpha.plugin").RECEIVED == []


def test_disable_then_enable_restores_consumption(tmp_path: Path, bus: EventBus) -> None:
    tracker = load_chain(tmp_path / "plugins", bus)
    tracker.disable_tree("kuestion.alpha")
    tracker.enable_tree("kuestion.alpha")

    emit_ping(bus)
    bus.wait_idle()

    assert tracker.active_ids() == ["kuestion.alpha", "kuestion.beta", "kuestion.gamma"]
    assert len(importlib.import_module("plugins.alpha.plugin").RECEIVED) == 1


def test_disable_then_enable_runs_on_load_again(tmp_path: Path, bus: EventBus) -> None:
    tracker = load_chain(tmp_path / "plugins", bus)
    tracker.disable_tree("kuestion.alpha")

    tracker.enable_tree("kuestion.alpha")

    assert importlib.import_module("plugins.alpha.plugin").LOADED == [1, 1]


def test_enable_creates_a_fresh_plugin_instance(tmp_path: Path, bus: EventBus) -> None:
    tracker = load_chain(tmp_path / "plugins", bus)
    tracker.disable_tree("kuestion.alpha")

    tracker.enable_tree("kuestion.alpha")

    instances = importlib.import_module("plugins.alpha.plugin").INSTANCES
    assert len(instances) == 2
    assert instances[0] is not instances[1]


def test_enable_emits_loaded_events(tmp_path: Path, bus: EventBus) -> None:
    observer = observe(bus)
    tracker = load_chain(tmp_path / "plugins", bus)
    tracker.disable_tree("kuestion.alpha")
    bus.wait_idle()
    observer.loaded.clear()

    tracker.enable_tree("kuestion.alpha")
    bus.wait_idle()

    assert observer.loaded == ["kuestion.alpha", "kuestion.beta", "kuestion.gamma"]


def test_enabling_with_disabled_requirement_fails(tmp_path: Path, bus: EventBus) -> None:
    observer = observe(bus)
    tracker = load_chain(tmp_path / "plugins", bus)
    tracker.disable_tree("kuestion.alpha")
    bus.wait_idle()
    observer.failed.clear()

    tracker.enable_tree("kuestion.beta")
    bus.wait_idle()

    assert observer.failed[0].stage == "deps"
    assert "disabled" in observer.failed[0].error


def test_enabling_with_disabled_requirement_leaves_tree_inactive(
    tmp_path: Path, bus: EventBus
) -> None:
    tracker = load_chain(tmp_path / "plugins", bus)
    tracker.disable_tree("kuestion.alpha")

    tracker.enable_tree("kuestion.beta")

    assert tracker.active_ids() == []
