"""Qt-free menu registration model.

The model turns slash-separated menu paths into a nested structure and tracks
the actions registered under each path. The windowing plugin renders this model
into a real ``QMenuBar``; the model itself imports no Qt.
"""

from __future__ import annotations

from dataclasses import dataclass

from plugins.windowing.events import MenuItemActivated, WidgetSpec


def parse_menu_path(menu_path: str) -> list[str]:
    """Split ``"Tools/Export"`` into ``["Tools", "Export"]``.

    Empty segments are ignored; a path with no segments is rejected.
    """
    segments = [segment for segment in menu_path.split("/") if segment]
    if not segments:
        raise ValueError(f"menu path has no segments: {menu_path!r}")
    return segments


@dataclass(frozen=True)
class MenuAction:
    """A registered menu action."""

    action_id: str
    action_label: str
    owner: str | None = None

    def to_event(self) -> MenuItemActivated:
        return MenuItemActivated(action_id=self.action_id, action_label=self.action_label)


@dataclass(frozen=True)
class DialogBinding:
    """A menu item that opens a non-modal dialog built from a spec."""

    action_id: str
    action_label: str
    title: str
    widget_spec: WidgetSpec
    owner: str | None = None


class MenuModel:
    """Accumulates actions and dialogs keyed by their slash-separated path."""

    def __init__(self) -> None:
        self._items: dict[str, list[MenuAction | DialogBinding]] = {}

    def add_action(
        self, menu_path: str, action_id: str, action_label: str, owner: str | None = None
    ) -> None:
        self._items.setdefault(menu_path, []).append(MenuAction(action_id, action_label, owner))

    def add_dialog(
        self,
        menu_path: str,
        action_id: str,
        title: str,
        widget_spec: WidgetSpec,
        owner: str | None = None,
    ) -> None:
        """Register a dialog; the menu label is the path's last segment."""
        label = parse_menu_path(menu_path)[-1]
        self._items.setdefault(menu_path, []).append(
            DialogBinding(action_id, label, title, widget_spec, owner)
        )

    def remove_owned_by(self, owner: str) -> None:
        """Drop every action/dialog contributed by ``owner``."""
        for menu_path in list(self._items):
            kept = [item for item in self._items[menu_path] if item.owner != owner]
            if kept:
                self._items[menu_path] = kept
            else:
                del self._items[menu_path]

    def actions_for(self, menu_path: str) -> list[MenuAction]:
        return [item for item in self._items.get(menu_path, ()) if isinstance(item, MenuAction)]

    def dialog(self, action_id: str) -> DialogBinding | None:
        for items in self._items.values():
            for item in items:
                if isinstance(item, DialogBinding) and item.action_id == action_id:
                    return item
        return None

    def menu_paths(self) -> list[str]:
        return list(self._items)

    def tree(self) -> dict:
        """Return a nested ``{segment: subtree}`` dict with item lists at the
        leaves."""
        root: dict = {}
        for menu_path, items in self._items.items():
            segments = parse_menu_path(menu_path)
            node = root
            for segment in segments[:-1]:
                node = node.setdefault(segment, {})
            node[segments[-1]] = list(items)
        return root
