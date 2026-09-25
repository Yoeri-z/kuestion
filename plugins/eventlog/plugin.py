"""The event-log plugin: a read-only tap on every event on the bus.

It registers the kernel observer tap on load (seeing broadcast, directed and
dead-lettered events without subscribing) and unregisters on unload. The trace
is shown through the existing ``View/Event Log…`` dialog contract.
"""

from __future__ import annotations

from kernel.envelope import Event
from kernel.plugin import Plugin

from plugins.eventlog.src.log_model import EventLogModel
from plugins.eventlog.src.log_widget import EventLogWidget
from plugins.windowing.events import DialogRequested, WidgetSpec

MENU_PATH = "View/Event Log…"
ACTION_ID = "eventlog.log"
DIALOG_TITLE = "Event Log"


class EventLogPlugin(Plugin):
    """Records every bus event and exposes it as a dialog."""

    def __init__(self, model: EventLogModel | None = None) -> None:
        self._model = model or EventLogModel()
        self._widget: EventLogWidget | None = None

    def on_load(self) -> None:
        self.bus.add_observer(self._model.record)
        self.bus.emit(
            Event(
                event_type=DialogRequested,
                payload=DialogRequested(
                    menu_path=MENU_PATH,
                    action_id=ACTION_ID,
                    title=DIALOG_TITLE,
                    widget_spec=WidgetSpec(factory=self._make_widget),
                ),
                sender_id=self.manifest.id,
            )
        )

    def on_unload(self) -> None:
        self.bus.remove_observer(self._model.record)

    def _make_widget(self) -> EventLogWidget:
        if self._widget is None:
            self._widget = EventLogWidget(self._model)
        return self._widget
