"""Unit tests for the Qt-palette -> log CSS-variable mapping.

Pure: a ``QPalette`` in, a CSS-variable dict out — no widget, no web engine.
"""

from __future__ import annotations

from PySide6.QtGui import QPalette

from plugins.chat.src.chat_widget import palette_variables


def palette_with(base: str, text: str) -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.Text, text)
    return palette


def test_dark_base_selects_dark_color_scheme() -> None:
    variables = palette_variables(palette_with(base="#232323", text="#ffffff"))

    assert variables["--bg"] == "#232323"
    assert variables["color-scheme"] == "dark"


def test_light_base_selects_light_color_scheme() -> None:
    variables = palette_variables(palette_with(base="#ffffff", text="#000000"))

    assert variables["color-scheme"] == "light"


def test_variables_mirror_named_palette_roles() -> None:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, "#202020")
    palette.setColor(QPalette.ColorRole.Mid, "#303030")

    variables = palette_variables(palette)

    assert variables["--code-bg"] == "#202020"
    assert variables["--border"] == "#303030"
