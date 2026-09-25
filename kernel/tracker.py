"""Active plugin tracker and hot enable/disable of dependency subtrees.

The tracker owns the set of currently active plugin instances. It remembers
each plugin's manifest and class so a disabled subtree can be re-enabled with
fresh instances without re-importing anything (modules stay in ``sys.modules``
by design).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kernel.envelope import Event
from kernel.events import (
    KERNEL_ID,
    PluginLoadFailed,
    PluginLoaded,
    PluginUnloaded,
)
from kernel.manifest import Manifest
from kernel.plugin import Plugin

if TYPE_CHECKING:
    from kernel.bus import EventBus


class Tracker:
    """Registry of active plugin instances plus subtree toggling."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._active: dict[str, Plugin] = {}
        self._manifests: dict[str, Manifest] = {}
        self._classes: dict[str, type[Plugin]] = {}
        self._order: list[str] = []
        self._disabled: set[str] = set()

    # -- registry ----------------------------------------------------------

    def add(self, plugin: Plugin) -> None:
        plugin_id = plugin.manifest.id
        if plugin_id not in self._manifests:
            self._order.append(plugin_id)
        self._active[plugin_id] = plugin
        self._manifests[plugin_id] = plugin.manifest
        self._classes[plugin_id] = type(plugin)
        self._disabled.discard(plugin_id)

    def remove(self, plugin_id: str) -> None:
        self._active.pop(plugin_id, None)

    def get(self, plugin_id: str) -> Plugin | None:
        return self._active.get(plugin_id)

    def active_ids(self) -> list[str]:
        return list(self._active)

    def is_active(self, plugin_id: str) -> bool:
        return plugin_id in self._active

    def dependents(self, plugin_id: str) -> set[str]:
        """Every known plugin that (transitively) requires ``plugin_id``."""
        dependents: set[str] = set()
        frontier = [plugin_id]
        while frontier:
            current = frontier.pop()
            for candidate, manifest in self._manifests.items():
                if candidate in dependents or candidate == plugin_id:
                    continue
                if current in manifest.requires:
                    dependents.add(candidate)
                    frontier.append(candidate)
        return dependents

    # -- hot toggling ------------------------------------------------------

    def disable_tree(self, plugin_id: str) -> None:
        """Unload ``plugin_id`` and all its dependents, dependents first."""
        if plugin_id not in self._active:
            return
        subtree = {plugin_id} | self.dependents(plugin_id)
        for candidate in reversed([pid for pid in self._order if pid in subtree]):
            plugin = self._active.pop(candidate, None)
            if plugin is None:
                continue
            try:
                plugin.on_unload()
            except Exception as exc:  # noqa: BLE001 - boundary: surface, never crash toggling
                self._emit(PluginLoadFailed, PluginLoadFailed(candidate, str(exc), "entry"))
            self._bus.unregister(candidate)
            self._disabled.add(candidate)
            self._emit(PluginUnloaded, PluginUnloaded(candidate))

    def enable_tree(self, plugin_id: str) -> None:
        """Load ``plugin_id`` and all its known dependents, dependencies first."""
        subtree = {plugin_id} | self.dependents(plugin_id)
        for candidate in [pid for pid in self._order if pid in subtree]:
            if candidate in self._active:
                continue
            manifest = self._manifests.get(candidate)
            if manifest is None:
                continue
            blocker = next((dep for dep in manifest.requires if dep not in self._active), None)
            if blocker is not None:
                self._emit(
                    PluginLoadFailed,
                    PluginLoadFailed(candidate, f"requires '{blocker}' which is disabled", "deps"),
                )
                continue
            self._activate(candidate)

    # -- internals ---------------------------------------------------------

    def _activate(self, plugin_id: str) -> None:
        plugin = self._classes[plugin_id]()
        plugin.manifest = self._manifests[plugin_id]
        self._bus.register(plugin)
        self.add(plugin)
        try:
            plugin.on_load()
        except Exception as exc:  # noqa: BLE001 - boundary: surface, roll back, keep toggling
            self._bus.unregister(plugin_id)
            self.remove(plugin_id)
            self._disabled.add(plugin_id)
            self._emit(PluginLoadFailed, PluginLoadFailed(plugin_id, str(exc), "entry"))
            return
        self._emit(PluginLoaded, PluginLoaded(plugin_id))

    def _emit(self, event_type: type, payload: object) -> None:
        self._bus.emit(Event(event_type=event_type, payload=payload, sender_id=KERNEL_ID))
