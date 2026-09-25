"""Event vocabulary for the ``windowing`` plugin.

Other plugins display themselves through these events. Payloads must be
thread-safe: Qt widgets are never sent across the bus. Instead a
:class:`WidgetSpec` describes the UI declaratively (a ``spec`` dict) or as a
``factory`` callable that is invoked on the main thread at delivery time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class WidgetSpec:
    """A thread-safe description of a widget to build on the main thread.

    Exactly one of ``factory`` / ``spec`` is normally set:

    * ``factory`` — a zero-argument callable returning a ``QWidget``; called on
      the main thread.
    * ``spec`` — a recursive dict, e.g. ``{"kind": "label", "text": "hi"}``;
      handled by :func:`windowing.src.widgets.build_widget`.
    """

    factory: Callable[[], object] | None = None
    spec: dict | None = None


@dataclass
class PanelRequested:
    """Ask the windowing plugin to open a widget as a panel.

    By default the widget becomes a dockable panel placed in ``area`` (one of
    ``"left"``, ``"right"``, ``"top"``, ``"bottom"``). With ``center=True`` it
    becomes the central workspace widget instead; only the first centered
    request wins.
    """

    panel_id: str
    title: str
    widget_spec: WidgetSpec
    area: str = "right"
    center: bool = False


@dataclass
class DialogRequested:
    """Ask the windowing plugin to register a menu item that opens a dialog.

    ``menu_path`` is a slash-separated chain (e.g. ``"Settings/Models"``); the
    menu item's label is its last segment. Activating the item opens a
    non-modal dialog titled ``title``, built from ``widget_spec``.
    """

    menu_path: str
    action_id: str
    title: str
    widget_spec: WidgetSpec


@dataclass
class PopupRequested:
    """Ask the windowing plugin to show a widget in its own top-level window."""

    title: str
    widget_spec: WidgetSpec


@dataclass
class MenuRequested:
    """Ask the windowing plugin to register a menu action.

    ``menu_path`` is a slash-separated chain, e.g. ``"Tools/Export"``.
    """

    menu_path: str
    action_id: str
    action_label: str


@dataclass
class MenuItemActivated:
    """Emitted when a registered menu action is triggered."""

    action_id: str
    action_label: str


@dataclass
class ClosePanelRequested:
    """Ask the windowing plugin to close a panel by id."""

    panel_id: str
