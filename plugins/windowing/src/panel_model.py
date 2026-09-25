"""Qt-free data model behind the Plugins panel.

The model only tracks plugin lifecycle status and error detail; the panel widget
renders it. Keeping the state machine free of Qt makes it unit-testable without
an event loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LOADED = "loaded"
FAILED = "failed"
DISABLED = "disabled"
ERROR = "error"


@dataclass
class PluginEntry:
    """The panel's view of one plugin."""

    plugin_id: str
    status: str = DISABLED
    error: str = field(default="")
    stage: str = field(default="")


class PluginPanelModel:
    """Tracks per-plugin status as lifecycle events arrive."""

    def __init__(self) -> None:
        self._entries: dict[str, PluginEntry] = {}

    def mark_loaded(self, plugin_id: str) -> None:
        self._update(plugin_id, status=LOADED, error="", stage="")

    def mark_unloaded(self, plugin_id: str) -> None:
        self._update(plugin_id, status=DISABLED, error="", stage="")

    def mark_failed(self, plugin_id: str, error: str, stage: str) -> None:
        self._update(plugin_id, status=FAILED, error=error, stage=stage)

    def mark_handler_error(self, plugin_id: str, error: str) -> None:
        self._update(plugin_id, status=ERROR, error=error, stage="")

    def get(self, plugin_id: str) -> PluginEntry | None:
        return self._entries.get(plugin_id)

    def next_action(self, plugin_id: str) -> str | None:
        """Return ``"disable"``, ``"enable"`` or ``None`` for the toggle button."""
        entry = self._entries.get(plugin_id)
        if entry is None:
            return None
        if entry.status == LOADED:
            return "disable"
        if entry.status == DISABLED:
            return "enable"
        return None

    def entries(self) -> list[PluginEntry]:
        return [self._entries[plugin_id] for plugin_id in sorted(self._entries)]

    def _update(self, plugin_id: str, *, status: str, error: str, stage: str) -> None:
        entry = self._entries.get(plugin_id)
        if entry is None:
            self._entries[plugin_id] = PluginEntry(plugin_id, status, error, stage)
            return
        entry.status = status
        entry.error = error
        entry.stage = stage
