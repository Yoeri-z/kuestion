"""The Plugins panel widget and its non-modal dialog host.

Renders a :class:`~windowing.panel_model.PluginPanelModel` as a tree of plugins
with status, expandable error detail and a per-plugin enable/disable toggle.
The toggle invokes a callback (the windowing plugin wires it to the kernel
tracker); the widget itself knows nothing about the kernel.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QDialog,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from plugins.windowing.src.panel_model import PluginPanelModel

ToggleCallback = Callable[[str], None]

_TOGGLE_LABELS = {"disable": "Disable", "enable": "Enable"}


class PluginsPanel(QWidget):
    """A view over a :class:`PluginPanelModel` with per-plugin toggle buttons."""

    def __init__(self, on_toggle: ToggleCallback | None = None) -> None:
        super().__init__()
        self._on_toggle = on_toggle
        self._tree = QTreeWidget()
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels(["Plugin", "Status", "Detail", ""])
        layout = QVBoxLayout(self)
        layout.addWidget(self._tree)

    def refresh(self, model: PluginPanelModel) -> None:
        self._tree.clear()
        for entry in model.entries():
            item = QTreeWidgetItem([entry.plugin_id, entry.status, entry.error])
            if entry.stage:
                QTreeWidgetItem(item, ["stage", entry.stage, ""])
            self._tree.addTopLevelItem(item)
            self._add_toggle(model, entry.plugin_id, item)
        self._tree.expandAll()

    def _add_toggle(self, model: PluginPanelModel, plugin_id: str, item: QTreeWidgetItem) -> None:
        action = model.next_action(plugin_id)
        if action is None or self._on_toggle is None:
            return
        button = QPushButton(_TOGGLE_LABELS[action])
        button.clicked.connect(lambda _checked=False, pid=plugin_id: self._on_toggle(pid))
        self._tree.setItemWidget(item, 3, button)


class PluginsDialog(QDialog):
    """A non-modal dialog wrapping a :class:`PluginsPanel`."""

    def __init__(self, on_toggle: ToggleCallback | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Plugins")
        self.setModal(False)
        self.resize(640, 400)
        self._panel = PluginsPanel(on_toggle=on_toggle)
        layout = QVBoxLayout(self)
        layout.addWidget(self._panel)

    def refresh(self, model: PluginPanelModel) -> None:
        self._panel.refresh(model)
