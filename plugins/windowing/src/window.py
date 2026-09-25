"""The main application window: a docking workspace.

Kept free of event/bus logic so :class:`~windowing.plugin.WindowingPlugin` owns
routing and this module owns only Qt structure. The chat panel is the central
widget; everything else is a movable, floatable, closable ``QDockWidget``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QMainWindow, QWidget

_DOCK_AREAS = {
    "left": Qt.DockWidgetArea.LeftDockWidgetArea,
    "right": Qt.DockWidgetArea.RightDockWidgetArea,
    "top": Qt.DockWidgetArea.TopDockWidgetArea,
    "bottom": Qt.DockWidgetArea.BottomDockWidgetArea,
}


class MainWindow(QMainWindow):
    """A ``QMainWindow`` with a central widget and dockable panels."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Kuestion")
        self.resize(960, 640)
        self._panels: dict[str, QDockWidget] = {}

    def set_central(self, widget: QWidget) -> None:
        """Install ``widget`` as the (unique) central workspace widget."""
        self.setCentralWidget(widget)

    def clear_central(self) -> None:
        """Remove and dispose of the current central widget, if any."""
        central = self.takeCentralWidget()
        if central is not None:
            central.setParent(None)
            central.deleteLater()

    def add_panel(self, panel_id: str, title: str, widget: QWidget, area: str) -> QDockWidget:
        """Add ``widget`` as a dock panel in ``area`` and return its dock."""
        dock = QDockWidget(title, self)
        dock.setObjectName(panel_id)
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.addDockWidget(_DOCK_AREAS.get(area, _DOCK_AREAS["right"]), dock)
        self._panels[panel_id] = dock
        return dock

    def remove_panel(self, panel_id: str) -> None:
        """Close and detach the dock panel with ``panel_id``, if present."""
        dock = self._panels.pop(panel_id, None)
        if dock is not None:
            dock.setParent(None)
            dock.deleteLater()
