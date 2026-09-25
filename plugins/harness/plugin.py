"""The AI harness: owns conversation state and brokers model calls.

It has no UI. It turns a ``ChatMessage`` into a directed ``ModelRequest`` at the
key registry, remembers the correlation id, and forwards the streamed and final
model events to the UI as broadcast ``ChatStreamChunk`` / ``ChatTurnComplete``.
Blocking work stays in the key registry; the harness only does delivery-adjacent
work on its own handler thread.
"""

from __future__ import annotations

import uuid

from kernel.envelope import Event
from kernel.plugin import Plugin, consume

from plugins.harness.events import (
    AttachmentParsed,
    ChatMessage,
    ChatStreamChunk,
    ChatTurnComplete,
    Message,
    ModelRequest,
    ModelResponse,
    ModelStreamChunk,
)
from plugins.harness.src.attachments import find_attachment_paths, read_text_attachments
from plugins.harness.src.conversation import Conversation

KEYREGISTRY_ID = "kuestion.keyregistry"


class HarnessPlugin(Plugin):
    """Conversation state and model-request brokering."""

    def __init__(self, model: str = "default", system_prompt: str | None = None) -> None:
        self._model = model
        self._conversation = Conversation() if system_prompt is None else Conversation(system_prompt)
        self._pending: set[str] = set()

    # -- conversation API -------------------------------------------------

    def history(self) -> list[Message]:
        return self._conversation.history()

    def set_model(self, model: str) -> None:
        self._model = model

    # -- incoming chat ----------------------------------------------------

    @consume(ChatMessage)
    def _on_chat_message(self, event: Event) -> None:
        message: ChatMessage = event.payload
        text: str = message.text
        model = message.model or self._model
        attachments = read_text_attachments(find_attachment_paths(text))
        for attachment in attachments:
            self.bus.emit(
                Event(
                    event_type=AttachmentParsed,
                    payload=attachment,
                    sender_id=self.manifest.id,
                )
            )

        self._conversation.add_user(_augment(text, attachments))
        correlations = uuid.uuid4().hex
        self._pending.add(correlations)
        self.bus.emit(
            Event(
                event_type=ModelRequest,
                payload=self._conversation.assemble_request(model),
                sender_id=self.manifest.id,
                target_id=KEYREGISTRY_ID,
                correlation_id=correlations,
            )
        )

    @consume(ModelStreamChunk)
    def _on_stream_chunk(self, event: Event) -> None:
        if event.correlation_id not in self._pending:
            return
        chunk: ModelStreamChunk = event.payload
        self.bus.emit(
            Event(
                event_type=ChatStreamChunk,
                payload=ChatStreamChunk(delta=chunk.delta, done=chunk.done),
                sender_id=self.manifest.id,
            )
        )

    @consume(ModelResponse)
    def _on_model_response(self, event: Event) -> None:
        if event.correlation_id not in self._pending:
            return
        self._pending.discard(event.correlation_id)
        response: ModelResponse = event.payload
        if response.error is not None:
            self._report_error(response.error)
            return
        self._conversation.add_assistant(response.content)
        self.bus.emit(
            Event(
                event_type=ChatTurnComplete,
                payload=ChatTurnComplete(text=response.content),
                sender_id=self.manifest.id,
            )
        )

    def _report_error(self, error: str) -> None:
        """Surface a failed model call as a completed-but-errored turn."""
        self.bus.emit(
            Event(
                event_type=ChatTurnComplete,
                payload=ChatTurnComplete(text="", error=error),
                sender_id=self.manifest.id,
            )
        )


def _augment(text: str, attachments: list[AttachmentParsed]) -> str:
    if not attachments:
        return text
    blocks = [text]
    for attachment in attachments:
        blocks.append(f"{attachment.path}:\n{attachment.content}")
    return "\n\n".join(blocks)
