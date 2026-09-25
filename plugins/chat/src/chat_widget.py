"""The chat window widget.

Created on the main thread. Its handler thread-facing updates arrive through Qt
signals: the plugin *emits* ``delta_received`` / ``turn_completed`` from its own
thread, and Qt queues them onto the main thread, so no widget is ever touched
off-main.

The log is an embedded ``QWebEngineView`` running a local shell page (vendored
KaTeX, no network): the conversation is handed to the page as a list of
``{role, html}`` blocks via ``window.render`` and the page renders Markdown and
LaTeX. Only the changed block is re-rendered, so streaming stays cheap.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QPalette
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from plugins.chat.src.markdown import render_markdown

_WEB_DIR = Path(__file__).resolve().parent / "web"
_SHELL = (_WEB_DIR / "shell.html").read_text(encoding="utf-8")

_RENDER_INTERVAL_MS = 80


def palette_variables(palette: QPalette) -> dict[str, str]:
    """Map a Qt palette onto the chat log's CSS variables.

    Pure: no widget or application state beyond the palette passed in.
    """

    def color(
        role: QPalette.ColorRole,
        group: QPalette.ColorGroup = QPalette.ColorGroup.Active,
    ) -> str:
        return palette.color(group, role).name()

    background = color(QPalette.ColorRole.Base)
    return {
        "--bg": background,
        "--fg": color(QPalette.ColorRole.Text),
        "--bubble": color(QPalette.ColorRole.AlternateBase),
        "--border": color(QPalette.ColorRole.Mid),
        "--muted": color(QPalette.ColorRole.Text, QPalette.ColorGroup.Disabled),
        "--accent": color(QPalette.ColorRole.Highlight),
        "--accent-fg": color(QPalette.ColorRole.HighlightedText),
        "--code-bg": color(QPalette.ColorRole.Window),
        "--button-bg": color(QPalette.ColorRole.Button),
        "--button-fg": color(QPalette.ColorRole.ButtonText),
        "color-scheme": "dark" if QColor(background).lightness() < 128 else "light",
    }


class _ChatPage(QWebEnginePage):
    """A page that opens clicked links externally instead of navigating away."""

    def acceptNavigationRequest(
        self, url: QUrl, navigation_type: QWebEnginePage.NavigationType, is_main_frame: bool
    ) -> bool:
        if navigation_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, navigation_type, is_main_frame)


class _ClipboardBridge(QObject):
    """Exposed to the page as ``kuestionBridge`` so code copy uses the real clipboard."""

    @Slot(str)
    def copy(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)


class ChatWidget(QWidget):
    """A rendered conversation log, a model picker, an input line and a button."""

    submitted = Signal(str)
    delta_received = Signal(str)
    turn_completed = Signal(str)
    models_changed = Signal(list)
    model_selected = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Chat")
        self._blocks: list[tuple[str, str]] = []
        self._streamed = False
        self._loaded = False

        self._view = QWebEngineView()
        self._view.setPage(_ChatPage(self._view))
        self._clipboard = _ClipboardBridge()
        self._channel = QWebChannel(self._view.page())
        self._channel.registerObject("kuestionBridge", self._clipboard)
        self._view.page().setWebChannel(self._channel)
        settings = self._view.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False
        )
        self._view.loadFinished.connect(self._on_load_finished)
        self._view.setHtml(_SHELL, QUrl.fromLocalFile(f"{_WEB_DIR}/"))

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(_RENDER_INTERVAL_MS)
        self._render_timer.timeout.connect(self._render)

        self._combo = QComboBox()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a message…")
        self._send = QPushButton("Send")

        layout = QVBoxLayout(self)
        layout.addWidget(self._view)
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:"))
        model_row.addWidget(self._combo)
        layout.addLayout(model_row)
        row = QHBoxLayout()
        row.addWidget(self._input)
        row.addWidget(self._send)
        layout.addLayout(row)

        self._send.clicked.connect(self._submit)
        self._input.returnPressed.connect(self._submit)
        self._combo.currentTextChanged.connect(self.model_selected)
        self.models_changed.connect(self._apply_models, Qt.ConnectionType.QueuedConnection)
        self.delta_received.connect(self._append_delta, Qt.ConnectionType.QueuedConnection)
        self.turn_completed.connect(self._finalize, Qt.ConnectionType.QueuedConnection)

        style_hints = QGuiApplication.styleHints()
        style_hints.colorSchemeChanged.connect(self._apply_palette)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.PaletteChange:
            self._apply_palette()
        super().changeEvent(event)

    # -- model picker ------------------------------------------------------

    @Slot(list)
    def _apply_models(self, names: list[str]) -> None:
        current = self._combo.currentText()
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItems(list(names))
        if current in names:
            self._combo.setCurrentText(current)
        self._combo.blockSignals(False)
        self.model_selected.emit(self._combo.currentText())

    # -- transcript --------------------------------------------------------

    def _submit(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self._streamed = False
        self.append_user(text)
        self.submitted.emit(text)

    def append_user(self, text: str) -> None:
        self._blocks.append(("user", text))
        self._render()

    @Slot(str)
    def _append_delta(self, delta: str) -> None:
        self._streamed = True
        if not self._blocks or self._blocks[-1][0] != "assistant":
            self._blocks.append(("assistant", ""))
        role, text = self._blocks[-1]
        self._blocks[-1] = (role, text + delta)
        self._render_timer.start()

    @Slot(str)
    def _finalize(self, text: str) -> None:
        self._render_timer.stop()
        if not self._streamed and text:
            if self._blocks and self._blocks[-1][0] == "assistant":
                self._blocks[-1] = ("assistant", text)
            else:
                self._blocks.append(("assistant", text))
        self._render()

    # -- rendering ---------------------------------------------------------

    @Slot()
    def _apply_palette(self) -> None:
        self._run(f"window.applyPalette({json.dumps(palette_variables(self.palette()))});")

    def _on_load_finished(self, ok: bool) -> None:
        self._loaded = True
        self._apply_palette()
        self._render()

    def _render(self) -> None:
        payload = {
            "blocks": [
                {"role": role, "html": render_markdown(text)} for role, text in self._blocks
            ],
        }
        self._run(f"window.render({json.dumps(payload)});")

    def _run(self, javascript: str) -> None:
        if self._loaded:
            self._view.page().runJavaScript(javascript)
