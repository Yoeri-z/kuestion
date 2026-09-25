"""The key registry plugin: BYOK model configuration and request execution.

It owns the model-access contract. A directed ``ModelRequest`` is served on a
worker thread (blocking network work must never run on the bus or main thread);
deltas and the final response are directed back at the requester with the
original correlation id.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

from kernel.envelope import Event, reply_to
from kernel.plugin import Plugin, consume

from plugins.keyregistry.events import (
    ModelListChanged,
    ModelListRequest,
    ModelRequest,
    ModelResponse,
    ModelStreamChunk,
)
from plugins.keyregistry.src.client import ModelClient
from plugins.keyregistry.src.config import ModelEntry, ModelRegistry
from plugins.keyregistry.src.config_widget import KeyRegistryWidget
from plugins.keyregistry.src.transport import HttpxTransport, Transport
from plugins.windowing.events import DialogRequested, WidgetSpec

#: Where model entries (including API keys, plaintext) are persisted.
CONFIG_PATH = Path.home() / ".config" / "kuestion" / "models.json"


class KeyRegistryPlugin(Plugin):
    """Configured model endpoints plus the request server."""

    def __init__(
        self,
        transport: Transport | None = None,
        registry_path: Path = CONFIG_PATH,
    ) -> None:
        self._registry = ModelRegistry(registry_path)
        self._transport = transport or HttpxTransport()
        self._client = ModelClient(self._transport)
        self._threads: list[threading.Thread] = []
        self._config_widget: KeyRegistryWidget | None = None

    # -- lifecycle --------------------------------------------------------

    def on_load(self) -> None:
        self._registry.subscribe(self._on_registry_changed)
        self._request_config_dialog()
        self._emit_model_list()

    # -- requests ---------------------------------------------------------

    @consume(ModelRequest)
    def _on_model_request(self, event: Event) -> None:
        worker = threading.Thread(
            target=self._serve,
            args=(event,),
            name="keyregistry-request",
            daemon=True,
        )
        self._threads.append(worker)
        worker.start()

    def _serve(self, event: Event) -> None:
        request: ModelRequest = event.payload
        correlation = event.correlation_id or uuid.uuid4().hex
        entry = self._registry.get(request.model)
        if entry is None:
            self._reply(
                event,
                correlation,
                ModelResponse("", request.model, error=f"unknown model entry {request.model!r}"),
            )
            return

        parts: list[str] = []
        try:
            for chunk in self._client.complete(entry, request):
                if chunk.delta:
                    parts.append(chunk.delta)
                self._reply(event, correlation, ModelStreamChunk(chunk.delta, chunk.done))
            self._reply(event, correlation, ModelResponse("".join(parts), entry.model_id))
        except Exception as exc:  # noqa: BLE001 - never let a request crash the worker
            self._reply(event, correlation, ModelResponse("", entry.model_id, error=str(exc)))

    def _reply(self, event: Event, correlation: str, payload: object) -> None:
        self.bus.emit(
            Event(
                event_type=type(payload),
                payload=payload,
                sender_id=self.manifest.id,
                target_id=event.sender_id,
                correlation_id=correlation,
            )
        )

    # -- config UI --------------------------------------------------------

    def _request_config_dialog(self) -> None:
        self.bus.emit(
            Event(
                event_type=DialogRequested,
                payload=DialogRequested(
                    menu_path="Settings/Models…",
                    action_id="keyregistry.models",
                    title="Models",
                    widget_spec=WidgetSpec(factory=self._make_config_widget),
                ),
                sender_id=self.manifest.id,
            )
        )

    def _make_config_widget(self) -> KeyRegistryWidget:
        if self._config_widget is None:
            self._config_widget = KeyRegistryWidget(self._registry)
        return self._config_widget

    def _on_registry_changed(self) -> None:
        self._emit_model_list()

    @consume(ModelListRequest)
    def _on_model_list_request(self, event: Event) -> None:
        """Reply to a ready plugin with the currently configured entries.

        The initial emit in :meth:`on_load` runs before dependent plugins have
        registered, so their subscriptions miss it. A plugin asks for the list
        once it is ready; the reply is directed back at the requester.
        """
        reply = ModelListChanged(self._registry.names())
        self.bus.emit(reply_to(event, reply, sender_id=self.manifest.id))

    def _emit_model_list(self) -> None:
        self.bus.emit(
            Event(
                event_type=ModelListChanged,
                payload=ModelListChanged(self._registry.names()),
                sender_id=self.manifest.id,
            )
        )

    # -- test / embedding hook -------------------------------------------

    def add_entry(self, entry: ModelEntry) -> None:
        """Register a model entry (subscribers are notified)."""
        self._registry.add(entry)
