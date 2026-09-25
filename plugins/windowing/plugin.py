"""The windowing plugin: main-thread Qt substrate for Kuestion.

It owns the ``QApplication``, the main window, dockable panels, popups, menus
and menu-driven dialogs. All of its handlers run on the main thread
(``main_thread=True`` in the manifest); the kernel schedules them via the
``on_main_thread`` bridge supplied at boot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kernel.envelope import Event
from kernel.events import (
    PluginHandlerError,
    PluginLoadFailed,
    PluginLoaded,
    PluginUnloaded,
)
from kernel.plugin import Plugin, consume
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from plugins.windowing.events import (
    ClosePanelRequested,
    DialogRequested,
    MenuItemActivated,
    MenuRequested,
    PanelRequested,
    PopupRequested,
    WidgetSpec,
)
from plugins.windowing.src.menus import DialogBinding, MenuAction, MenuModel
from plugins.windowing.src.panel import PluginsDialog
from plugins.windowing.src.panel_model import PluginPanelModel
from plugins.windowing.src.widgets import build_widget
from plugins.windowing.src.window import MainWindow
from plugins.windowing.src.workspace import WorkspaceModel

if TYPE_CHECKING:
    from kernel.tracker import Tracker

PLUGINS_DIALOG_ACTION = "kuestion.windowing.plugins"
PLUGINS_DIALOG_PATH = "View/Plugins…"


class WindowingPlugin(Plugin):
    """Qt windowing substrate, menu-driven dialogs and Plugins dialog."""

    def __init__(self) -> None:
        self._model = PluginPanelModel()
        self._menus = MenuModel()
        self._action_labels: dict[str, str] = {}
        self._window: MainWindow | None = None
        self._workspace = WorkspaceModel()
        self._panel_widgets: dict[str, QWidget] = {}
        self._dialogs: dict[str, QWidget] = {}
        self._dialog_owners: dict[str, str | None] = {}
        self._popups: list[tuple[QWidget, str]] = []
        self._plugins_dialog: PluginsDialog | None = None
        self._tracker: Tracker | None = None

    def on_load(self) -> None:
        self._app = QApplication.instance() or QApplication([])
        self._window = MainWindow()
        self._window.show()
        self._register_dialog(
            DialogRequested(
                menu_path=PLUGINS_DIALOG_PATH,
                action_id=PLUGINS_DIALOG_ACTION,
                title="Plugins",
                widget_spec=WidgetSpec(factory=self._make_plugins_dialog),
            ),
            owner=self.manifest.id,
        )

    def on_unload(self) -> None:
        for widget, _owner in self._popups:
            widget.close()
        self._popups.clear()
        for dialog in self._dialogs.values():
            dialog.close()
        self._dialogs.clear()
        self._dialog_owners.clear()
        if self._window is not None:
            self._window.close()
            self._window = None

    def set_tracker(self, tracker: Tracker) -> None:
        """Inject the kernel tracker so the Plugins dialog can toggle plugins."""
        self._tracker = tracker

    # -- UI events --------------------------------------------------------

    @consume(PanelRequested)
    def _on_panel_requested(self, event: Event) -> None:
        request: PanelRequested = event.payload
        widget = build_widget(request.widget_spec, self._activate_action)
        self._panel_widgets[request.panel_id] = widget
        entry = self._workspace.add(
            request.panel_id,
            request.title,
            area=request.area,
            center=request.center,
            owner=event.sender_id,
        )
        window = self._require_window()
        if entry.center:
            window.set_central(widget)
            return
        dock = window.add_panel(entry.panel_id, entry.title, widget, entry.area)
        orientation = (
            Qt.Orientation.Vertical
            if entry.area in ("top", "bottom")
            else Qt.Orientation.Horizontal
        )
        window.resizeDocks([dock], [280], orientation)

    @consume(ClosePanelRequested)
    def _on_close_panel(self, event: Event) -> None:
        request: ClosePanelRequested = event.payload
        self._remove_panel(request.panel_id)

    @consume(PopupRequested)
    def _on_popup_requested(self, event: Event) -> None:
        request: PopupRequested = event.payload
        widget = build_widget(request.widget_spec, self._activate_action)
        widget.setWindowTitle(request.title)
        widget.show()
        self._popups.append((widget, event.sender_id))

    @consume(MenuRequested)
    def _on_menu_requested(self, event: Event) -> None:
        request: MenuRequested = event.payload
        self._menus.add_action(
            request.menu_path,
            request.action_id,
            request.action_label,
            owner=event.sender_id,
        )
        self._action_labels[request.action_id] = request.action_label
        self._rebuild_menu_bar()

    @consume(DialogRequested)
    def _on_dialog_requested(self, event: Event) -> None:
        self._register_dialog(event.payload, owner=event.sender_id)

    # -- Plugins dialog ---------------------------------------------------

    @consume(PluginLoaded)
    def _on_plugin_loaded(self, event: Event) -> None:
        self._model.mark_loaded(event.payload.plugin_id)
        self._refresh_panel()

    @consume(PluginUnloaded)
    def _on_plugin_unloaded(self, event: Event) -> None:
        plugin_id = event.payload.plugin_id
        self._model.mark_unloaded(plugin_id)
        self._remove_plugin_ui(plugin_id)
        self._refresh_panel()

    @consume(PluginLoadFailed)
    def _on_plugin_load_failed(self, event: Event) -> None:
        failure: PluginLoadFailed = event.payload
        self._model.mark_failed(failure.plugin_id, failure.error, failure.stage)
        self._refresh_panel()

    @consume(PluginHandlerError)
    def _on_plugin_handler_error(self, event: Event) -> None:
        error: PluginHandlerError = event.payload
        self._model.mark_handler_error(error.plugin_id, error.error)
        self._refresh_panel()

    # -- internals --------------------------------------------------------

    def _require_window(self) -> MainWindow:
        if self._window is None:
            raise RuntimeError("windowing is not loaded")
        return self._window

    def _register_dialog(self, request: DialogRequested, owner: str) -> None:
        self._menus.add_dialog(
            request.menu_path,
            request.action_id,
            request.title,
            request.widget_spec,
            owner=owner,
        )
        self._rebuild_menu_bar()

    def _remove_panel(self, panel_id: str) -> None:
        entry = self._workspace.get(panel_id)
        self._panel_widgets.pop(panel_id, None)
        self._workspace.remove(panel_id)
        if self._window is None:
            return
        if entry is not None and entry.center:
            self._window.clear_central()
        else:
            self._window.remove_panel(panel_id)

    def _remove_plugin_ui(self, plugin_id: str) -> None:
        """Tear down every panel, popup, menu item and dialog a plugin owns."""
        for panel_id in self._workspace.owned_by(plugin_id):
            self._remove_panel(panel_id)
        remaining: list[tuple[QWidget, str]] = []
        for widget, owner in self._popups:
            if owner == plugin_id:
                widget.close()
            else:
                remaining.append((widget, owner))
        self._popups = remaining
        for action_id in [aid for aid, owner in self._dialog_owners.items() if owner == plugin_id]:
            dialog = self._dialogs.pop(action_id, None)
            if dialog is not None:
                dialog.close()
            self._dialog_owners.pop(action_id, None)
        self._menus.remove_owned_by(plugin_id)
        self._rebuild_menu_bar()

    def _open_dialog(self, action_id: str) -> None:
        binding = self._menus.dialog(action_id)
        if binding is None:
            return
        widget = build_widget(binding.widget_spec, self._activate_action)
        widget.setWindowTitle(binding.title)
        widget.show()
        self._dialogs[action_id] = widget
        self._dialog_owners[action_id] = binding.owner

    def _make_plugins_dialog(self) -> PluginsDialog:
        if self._plugins_dialog is None:
            self._plugins_dialog = PluginsDialog(on_toggle=self._toggle_plugin)
        self._plugins_dialog.refresh(self._model)
        return self._plugins_dialog

    def _toggle_plugin(self, plugin_id: str) -> None:
        if self._tracker is None:
            return
        action = self._model.next_action(plugin_id)
        if action == "disable":
            self._tracker.disable_tree(plugin_id)
        elif action == "enable":
            self._tracker.enable_tree(plugin_id)

    def _refresh_panel(self) -> None:
        if self._plugins_dialog is not None:
            self._plugins_dialog.refresh(self._model)

    def _activate_action(self, action_id: str) -> None:
        label = self._action_labels.get(action_id, action_id)
        payload = MenuItemActivated(action_id=action_id, action_label=label)
        self.bus.emit(
            Event(event_type=MenuItemActivated, payload=payload, sender_id=self.manifest.id)
        )

    def _rebuild_menu_bar(self) -> None:
        menu_bar = self._require_window().menuBar()
        menu_bar.clear()
        for label, subtree in self._menus.tree().items():
            menu = menu_bar.addMenu(label)
            self._populate_menu(menu, subtree)

    def _populate_menu(self, menu: QMenu, subtree: dict) -> None:
        for label, value in subtree.items():
            if isinstance(value, list):
                for item in value:
                    menu.addAction(self._menu_action(menu, item))
            else:
                submenu = menu.addMenu(label)
                self._populate_menu(submenu, value)

    def _menu_action(self, menu: QMenu, item: MenuAction | DialogBinding) -> QAction:
        if isinstance(item, DialogBinding):
            action = QAction(item.action_label, menu)
            action.triggered.connect(
                lambda _checked=False, action_id=item.action_id: self._open_dialog(action_id)
            )
            return action
        action = QAction(item.action_label, menu)
        action.triggered.connect(
            lambda _checked=False, action_id=item.action_id: self._activate_action(action_id)
        )
        return action
