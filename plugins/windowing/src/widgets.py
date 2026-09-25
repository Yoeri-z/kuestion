"""Build Qt widgets from declarative :class:`WidgetSpec` descriptions.

Must run on the main thread. The supported ``spec`` kinds are ``label``,
``button``, ``lineedit``, ``vbox`` and ``hbox`` (the last two recurse into their
``children``). Unknown kinds raise :class:`ValueError`.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from plugins.windowing.events import WidgetSpec

ActionCallback = Callable[[str], None]


def build_widget(widget_spec: WidgetSpec, on_action: ActionCallback | None = None) -> QWidget:
    """Return a widget for ``widget_spec``.

    ``on_action`` is invoked with a button's ``action_id`` when it is clicked.
    """
    if widget_spec.factory is not None:
        return widget_spec.factory()  # type: ignore[return-value]
    if widget_spec.spec is None:
        raise ValueError("WidgetSpec must set either 'factory' or 'spec'")
    return _build(widget_spec.spec, on_action)


def _build(spec: dict, on_action: ActionCallback | None) -> QWidget:
    kind = spec.get("kind")
    if kind == "label":
        return QLabel(spec.get("text", ""))
    if kind == "button":
        return _build_button(spec, on_action)
    if kind == "lineedit":
        widget = QLineEdit()
        widget.setPlaceholderText(spec.get("placeholder", ""))
        if "text" in spec:
            widget.setText(spec["text"])
        return widget
    if kind == "vbox":
        return _build_container(QVBoxLayout, spec.get("children", ()), on_action)
    if kind == "hbox":
        return _build_container(QHBoxLayout, spec.get("children", ()), on_action)
    raise ValueError(f"unknown widget spec kind: {kind!r}")


def _build_button(spec: dict, on_action: ActionCallback | None) -> QPushButton:
    button = QPushButton(spec.get("text", ""))
    action_id = spec.get("action_id")
    if action_id is not None and on_action is not None:
        button.clicked.connect(lambda: on_action(action_id))
    return button


def _build_container(
    layout_type: type, children: list[dict], on_action: ActionCallback | None
) -> QWidget:
    container = QWidget()
    layout = layout_type(container)
    for child_spec in children:
        layout.addWidget(_build(child_spec, on_action))
    return container
