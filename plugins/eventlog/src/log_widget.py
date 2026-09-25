"""The event-log dialog widget.

Created on the main thread through the ``WidgetSpec(factory=…)`` path, it
renders the current :class:`~plugins.eventlog.src.log_model.EventLogModel`
snapshot into a table; the Refresh button re-reads it.
"""

from __future__ import annotations

import time

from PySide6.QtWidgets import (
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from plugins.eventlog.src.log_model import EventLogModel

COLUMNS = ("Time", "Type", "Sender", "Target", "Correlation", "Payload")


class EventLogWidget(QWidget):
    """A table of observed events with a manual refresh."""

    def __init__(self, model: EventLogModel) -> None:
        super().__init__()
        self._model = model
        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(list(COLUMNS))
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)

        root = QVBoxLayout(self)
        root.addWidget(refresh)
        root.addWidget(self._table)

        self.refresh()

    def refresh(self) -> None:
        """Replace the table contents with the latest snapshot."""
        entries = self._model.entries()
        self._table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            values = (
                time.strftime("%H:%M:%S", time.localtime(entry.timestamp)),
                entry.event_type_name,
                entry.sender_id,
                entry.target_id or "",
                entry.correlation_id or "",
                entry.payload_repr,
            )
            for column, value in enumerate(values):
                self._table.setItem(row, column, QTableWidgetItem(value))
        self._table.scrollToBottom()
