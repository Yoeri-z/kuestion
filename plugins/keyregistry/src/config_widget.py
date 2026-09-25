"""The key-registry configuration widget.

Created on the main thread and shown from the ``Settings/Models…`` menu. It
edits the shared :class:`~keyregistry.src.config.ModelRegistry`; every mutation
goes through the registry so subscribers (the plugin's ``ModelListChanged``
emit) stay in sync.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from plugins.keyregistry.src.config import HeaderRow, ModelEntry, ModelRegistry


class KeyRegistryWidget(QWidget):
    """A list of model entries with an editor form and header rows."""

    def __init__(self, registry: ModelRegistry) -> None:
        super().__init__()
        self._registry = registry
        self._current: str | None = None

        self._list = QListWidget()
        self._name = QLineEdit()
        self._base_url = QLineEdit()
        self._model_id = QLineEdit()
        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._headers = QTableWidget(0, 2)
        self._headers.setHorizontalHeaderLabels(["Header", "Value"])

        form = QFormLayout()
        form.addRow("Name", self._name)
        form.addRow("Base URL", self._base_url)
        form.addRow("Model id", self._model_id)
        form.addRow("API key", self._api_key)

        self._add_entry = QPushButton("Add entry")
        self._remove_entry = QPushButton("Remove entry")
        self._save = QPushButton("Save entry")
        self._add_header = QPushButton("Add header")
        self._remove_header = QPushButton("Remove header")

        left = QVBoxLayout()
        left.addWidget(QLabel("Model entries"))
        left.addWidget(self._list)
        entry_row = QHBoxLayout()
        entry_row.addWidget(self._add_entry)
        entry_row.addWidget(self._remove_entry)
        left.addLayout(entry_row)

        right = QVBoxLayout()
        right.addLayout(form)
        right.addWidget(QLabel("Headers"))
        right.addWidget(self._headers)
        header_row = QHBoxLayout()
        header_row.addWidget(self._add_header)
        header_row.addWidget(self._remove_header)
        right.addLayout(header_row)
        right.addWidget(self._save)

        root = QHBoxLayout(self)
        root.addLayout(left)
        root.addLayout(right)

        self._list.currentTextChanged.connect(self._load)
        self._add_entry.clicked.connect(self._add)
        self._remove_entry.clicked.connect(self._remove)
        self._save.clicked.connect(self._save_entry)
        self._add_header.clicked.connect(lambda: self._headers.insertRow(self._headers.rowCount()))
        self._remove_header.clicked.connect(self._remove_selected_header)

        self.refresh()

    # -- view refresh -----------------------------------------------------

    def refresh(self) -> None:
        """Rebuild the entry list and re-select the current entry."""
        self._list.blockSignals(True)
        self._list.clear()
        self._list.addItems(self._registry.names())
        self._list.blockSignals(False)
        if self._current is not None and self._registry.get(self._current) is not None:
            self._select(self._current)
        else:
            self._current = None
            self._clear_form()

    def _select(self, name: str) -> None:
        matches = self._list.findItems(name, Qt.MatchFlag.MatchExactly)
        if matches:
            self._list.setCurrentItem(matches[0])

    def _load(self, name: str) -> None:
        entry = self._registry.get(name)
        if entry is None:
            self._current = None
            self._clear_form()
            return
        self._current = name
        self._name.setText(entry.name)
        self._base_url.setText(entry.base_url)
        self._model_id.setText(entry.model_id)
        self._api_key.setText(entry.api_key)
        self._headers.setRowCount(0)
        for row in entry.headers:
            self._append_header(row.key, row.value)

    def _clear_form(self) -> None:
        self._name.clear()
        self._base_url.clear()
        self._model_id.clear()
        self._api_key.clear()
        self._headers.setRowCount(0)

    # -- entry mutations --------------------------------------------------

    def _add(self) -> None:
        name = self._unique_name()
        self._registry.add(ModelEntry(name=name, base_url="", model_id=""))
        self.refresh()
        self._select(name)

    def _remove(self) -> None:
        if self._current is None:
            return
        self._registry.remove(self._current)
        self._current = None
        self.refresh()

    def _save_entry(self) -> None:
        name = self._name.text().strip()
        if not name:
            return
        if self._current is not None and name != self._current:
            self._registry.remove(self._current)
        self._registry.add(
            ModelEntry(
                name=name,
                base_url=self._base_url.text().strip(),
                model_id=self._model_id.text().strip(),
                headers=self._read_headers(),
                api_key=self._api_key.text(),
            )
        )
        self.refresh()
        self._select(name)

    # -- header rows ------------------------------------------------------

    def _append_header(self, key: str, value: str) -> None:
        row = self._headers.rowCount()
        self._headers.insertRow(row)
        self._headers.setItem(row, 0, QTableWidgetItem(key))
        self._headers.setItem(row, 1, QTableWidgetItem(value))

    def _read_headers(self) -> list[HeaderRow]:
        rows: list[HeaderRow] = []
        for index in range(self._headers.rowCount()):
            key = self._item_text(index, 0)
            if key:
                rows.append(HeaderRow(key, self._item_text(index, 1)))
        return rows

    def _item_text(self, row: int, column: int) -> str:
        item = self._headers.item(row, column)
        return item.text() if item is not None else ""

    def _remove_selected_header(self) -> None:
        row = self._headers.currentRow()
        if row >= 0:
            self._headers.removeRow(row)

    def _unique_name(self) -> str:
        existing = set(self._registry.names())
        index = 1
        while f"model-{index}" in existing:
            index += 1
        return f"model-{index}"
