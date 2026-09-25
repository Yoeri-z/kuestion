"""Unit tests for the declarative :func:`build_widget` spec builder."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from plugins.windowing.events import WidgetSpec
from plugins.windowing.src.widgets import build_widget


def test_factory_kind_returns_the_factory_result() -> None:
    sentinel = QWidget()

    built = build_widget(WidgetSpec(factory=lambda: sentinel))

    assert built is sentinel


def test_label_spec_builds_label_with_text() -> None:
    built = build_widget(WidgetSpec(spec={"kind": "label", "text": "hello"}))

    assert isinstance(built, QLabel)
    assert built.text() == "hello"


def test_button_spec_builds_button_with_text() -> None:
    built = build_widget(WidgetSpec(spec={"kind": "button", "text": "Send"}))

    assert isinstance(built, QPushButton)
    assert built.text() == "Send"


def test_lineedit_spec_wires_placeholder() -> None:
    built = build_widget(WidgetSpec(spec={"kind": "lineedit", "placeholder": "Type here"}))

    assert isinstance(built, QLineEdit)
    assert built.placeholderText() == "Type here"


def test_lineedit_spec_wires_text() -> None:
    built = build_widget(WidgetSpec(spec={"kind": "lineedit", "text": "hi"}))

    assert isinstance(built, QLineEdit)
    assert built.text() == "hi"


def test_vbox_spec_builds_vertical_layout_with_children() -> None:
    spec = {"kind": "vbox", "children": [{"kind": "label", "text": "a"}, {"kind": "label", "text": "b"}]}

    built = build_widget(WidgetSpec(spec=spec))

    assert isinstance(built.layout(), QVBoxLayout)
    assert built.layout().count() == 2


def test_hbox_spec_builds_horizontal_layout() -> None:
    spec = {"kind": "hbox", "children": [{"kind": "label", "text": "a"}]}

    built = build_widget(WidgetSpec(spec=spec))

    assert isinstance(built.layout(), QHBoxLayout)


def test_button_action_id_invokes_callback_on_click() -> None:
    activated: list[str] = []
    built = build_widget(
        WidgetSpec(spec={"kind": "button", "text": "Go", "action_id": "go"}),
        on_action=activated.append,
    )

    built.click()

    assert activated == ["go"]


def test_unknown_spec_kind_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_widget(WidgetSpec(spec={"kind": "nope"}))
