"""The chat window plugin.

Owns the transcript and a main-thread ``ChatWidget``. It runs on its own handler
thread, so it never touches Qt directly: user submissions arrive via a Qt signal
(queued from the widget) and streamed updates are pushed back through the
widget's signals, which Qt queues onto the main thread.
"""

from __future__ import annotations

from kernel.envelope import Event
from kernel.plugin import Plugin, consume

from plugins.chat.src.chat_widget import ChatWidget
from plugins.chat.src.transcript import TranscriptModel, Turn
from plugins.harness.events import (
    ChatMessage,
    ChatStreamChunk,
    ChatTurnComplete,
    ModelListChanged,
    ModelListRequest,
)
from plugins.windowing.events import PanelRequested, WidgetSpec

HARNESS_ID = "kuestion.harness"
KEYREGISTRY_ID = "kuestion.keyregistry"


class ChatPlugin(Plugin):
    """Transcript state plus the chat tab."""

    def __init__(self) -> None:
        self._transcript = TranscriptModel()
        self._widget: ChatWidget | None = None
        self._models: list[str] = []
        self._selected_model: str | None = None

    # -- lifecycle --------------------------------------------------------

    def on_load(self) -> None:
        self._ensure_widget()
        self._request_panel()
        self._request_model_list()

    # -- public state -----------------------------------------------------

    def transcript(self) -> list[Turn]:
        return self._transcript.turns()

    def models(self) -> list[str]:
        return list(self._models)

    def selected_model(self) -> str | None:
        return self._selected_model

    # -- model picker -----------------------------------------------------

    def _request_model_list(self) -> None:
        """Ask the key registry for entries loaded before this plugin existed."""
        self.bus.emit(
            Event(
                event_type=ModelListRequest,
                payload=ModelListRequest(),
                sender_id=self.manifest.id,
                target_id=KEYREGISTRY_ID,
            )
        )

    @consume(ModelListChanged)
    def _on_models_changed(self, event: Event) -> None:
        self._models = list(event.payload.names)
        if self._selected_model not in self._models:
            self._selected_model = self._models[0] if self._models else None
        if self._widget is not None:
            self._widget.models_changed.emit(self._models)

    def _on_model_selected(self, name: str) -> None:
        self._selected_model = name or None

    # -- submitted messages ----------------------------------------------

    def _on_submitted(self, text: str) -> None:
        self._transcript.add_user(text)
        self._transcript.begin_assistant()
        self.bus.emit(
            Event(
                event_type=ChatMessage,
                payload=ChatMessage(text, model=self._selected_model),
                sender_id=self.manifest.id,
                target_id=HARNESS_ID,
            )
        )

    # -- streamed responses ----------------------------------------------

    @consume(ChatStreamChunk)
    def _on_chunk(self, event: Event) -> None:
        delta: str = event.payload.delta
        self._transcript.append_delta(delta)
        if self._widget is not None:
            self._widget.delta_received.emit(delta)

    @consume(ChatTurnComplete)
    def _on_turn_complete(self, event: Event) -> None:
        payload: ChatTurnComplete = event.payload
        self._transcript.complete(payload.text, error=payload.error)
        if self._widget is not None:
            self._widget.turn_completed.emit(payload.error or payload.text)

    # -- panel -------------------------------------------------------------

    def _request_panel(self) -> None:
        self.bus.emit(
            Event(
                event_type=PanelRequested,
                payload=PanelRequested(
                    panel_id="chat",
                    title="Chat",
                    widget_spec=WidgetSpec(factory=self._make_widget),
                    center=True,
                ),
                sender_id=self.manifest.id,
            )
        )

    def _make_widget(self) -> ChatWidget:
        return self._ensure_widget()

    def _ensure_widget(self) -> ChatWidget:
        if self._widget is None:
            self._widget = ChatWidget()
            self._widget.submitted.connect(self._on_submitted)
            self._widget.model_selected.connect(self._on_model_selected)
            self._widget.models_changed.emit(self._models)
        return self._widget
