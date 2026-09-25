"""Console entry point for Kuestion.

Boot sequence (Phase 6):

1. Create the ``QApplication`` early so Qt-dependent ``on_load`` hooks can build
   widgets.
2. Construct the kernel with a main-thread bridge, so main-thread plugin
   deliveries are queued onto the Qt thread.
3. Load all plugins in dependency order.
4. Run the Qt event loop; on exit stop the bus and unload plugins.

Pass ``--check`` to validate and load without entering the event loop (handy on
headless machines).
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from kernel.bus import EventBus
from kernel.loader import Loader, LoadSummary
from kernel.registry import TypeRegistry
from kernel.tracker import Tracker

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILTIN_PLUGINS = REPO_ROOT / "plugins"
USER_PLUGINS = Path.home() / ".config" / "kuestion" / "plugins"


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    registry = TypeRegistry()
    loader = Loader([BUILTIN_PLUGINS, USER_PLUGINS], registry, on_warning=_print_warning)

    # The loader puts the plugin search directories' parents on ``sys.path``
    # (so ``plugins`` is an implicit namespace package); only now can the
    # built-in windowing bridge be imported.
    from plugins.windowing.src.bridge import MainThreadBridge

    bridge = MainThreadBridge()
    bus = EventBus(registry, on_main_thread=bridge.schedule)
    bus.start()
    tracker = Tracker(bus)

    try:
        summary = loader.load_all(bus, tracker)
        _inject_tracker(tracker)
        _print_summary(summary)
        if "--check" in sys.argv:
            return 0
        return app.exec()
    finally:
        _unload_all(tracker)
        bus.stop()


def _inject_tracker(tracker: Tracker) -> None:
    """Hand the tracker to the windowing plugin so its Plugins dialog can
    enable/disable plugins (a kernel service, like the main-thread bridge)."""
    windowing = tracker.get("kuestion.windowing")
    if windowing is not None and hasattr(windowing, "set_tracker"):
        windowing.set_tracker(tracker)


def _unload_all(tracker: Tracker) -> None:
    for plugin_id in reversed(tracker.active_ids()):
        plugin = tracker.get(plugin_id)
        if plugin is None:
            continue
        try:
            plugin.on_unload()
        except Exception as exc:  # noqa: BLE001 - shutdown must not raise
            print(f"  warning unload of {plugin_id} failed: {exc}")


def _print_summary(summary: LoadSummary) -> None:
    print(f"kuestion: loaded {len(summary.loaded)} plugin(s)")
    for plugin_id in summary.loaded:
        print(f"  loaded  {plugin_id}")
    for failure in summary.failed:
        print(f"  failed  {failure.plugin_id} [{failure.stage}]: {failure.error}")


def _print_warning(message: str) -> None:
    print(f"  warning {message}")


if __name__ == "__main__":
    raise SystemExit(main())
