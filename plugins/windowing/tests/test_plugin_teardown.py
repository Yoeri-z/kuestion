"""Unit tests for tearing down a plugin's UI when it is unloaded.

These exercise the ``PluginUnloaded`` handler with fake models/window (no Qt
widgets are constructed) to pin the regression where a disabled plugin's panels
stayed on screen.
"""

from __future__ import annotations

import pytest

from kernel.envelope import Event
from kernel.events import PluginUnloaded
from kernel.manifest import Manifest
from plugins.windowing.events import PanelRequested, WidgetSpec
from plugins.windowing.plugin import WindowingPlugin


class FakeBus:
    def emit(self, event: Event) -> None:
        pass


class FakeWindow:
    def __init__(self) -> None:
        self.central: object | None = None
        self.docks: list[str] = []

    def set_central(self, widget: object) -> None:
        self.central = widget

    def clear_central(self) -> None:
        self.central = None

    def add_panel(self, panel_id: str, title: str, widget: object, area: str) -> object:
        self.docks.append(panel_id)
        return object()

    def remove_panel(self, panel_id: str) -> None:
        self.docks.remove(panel_id)

    def resizeDocks(self, docks: list, sizes: list, orientation: object) -> None:
        pass


@pytest.fixture
def plugin() -> WindowingPlugin:
    instance = WindowingPlugin()
    instance.manifest = Manifest(id="kuestion.windowing", entry="plugin:WindowingPlugin")
    instance.bus = FakeBus()
    instance._window = FakeWindow()
    instance._rebuild_menu_bar = lambda: None
    return instance


def panel_event(panel_id: str, *, center: bool, sender_id: str) -> Event:
    payload = PanelRequested(panel_id, panel_id, WidgetSpec(factory=object), center=center)
    return Event(event_type=PanelRequested, payload=payload, sender_id=sender_id)


def unload_event(plugin_id: str) -> Event:
    return Event(
        event_type=PluginUnloaded,
        payload=PluginUnloaded(plugin_id),
        sender_id="kuestion.kernel",
    )


def test_unloaded_plugin_dock_panel_is_removed(plugin: WindowingPlugin) -> None:
    plugin._on_panel_requested(panel_event("models", center=False, sender_id="kuestion.keyregistry"))

    plugin._on_plugin_unloaded(unload_event("kuestion.keyregistry"))

    assert plugin._workspace.get("models") is None
    assert plugin._window.docks == []


def test_unloaded_plugin_central_panel_is_cleared(plugin: WindowingPlugin) -> None:
    plugin._on_panel_requested(panel_event("chat", center=True, sender_id="kuestion.chat"))

    plugin._on_plugin_unloaded(unload_event("kuestion.chat"))

    assert plugin._window.central is None


def test_other_plugins_panels_survive_an_unload(plugin: WindowingPlugin) -> None:
    plugin._on_panel_requested(panel_event("models", center=False, sender_id="kuestion.keyregistry"))
    plugin._on_panel_requested(panel_event("chat", center=True, sender_id="kuestion.chat"))

    plugin._on_plugin_unloaded(unload_event("kuestion.keyregistry"))

    assert plugin._workspace.get("chat") is not None
    assert plugin._workspace.get("models") is None
