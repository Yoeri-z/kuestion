"""Main-thread scheduling bridge.

The kernel is Qt-agnostic: it accepts an ``on_main_thread`` callable. This bridge
implements it with a queued Qt signal, so callables emitted from any thread are
executed on the thread owning the bridge (the main/Qt thread) once its event
loop is running.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, Signal, Slot


class MainThreadBridge(QObject):
    """Runs scheduled callables on the main thread via a queued connection."""

    _queued = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._queued.connect(self._run, Qt.ConnectionType.QueuedConnection)

    def schedule(self, fn: Callable[[], None]) -> None:
        """Queue ``fn`` to run on the main thread. Safe from any thread."""
        self._queued.emit(fn)

    @Slot(object)
    def _run(self, fn: Callable[[], None]) -> None:
        fn()
