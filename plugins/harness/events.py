"""Event vocabulary for the ``harness`` plugin.

The harness owns the conversation contract. It consumes ``ChatMessage`` from the
chat window, calls out to the key registry using the imported ``Model*`` types,
and broadcasts stream/final events for the UI (and any future history plugin).
"""

from __future__ import annotations

from dataclasses import dataclass

# Re-exported so chat/UI plugins can depend on the harness contract surface.
from plugins.keyregistry.events import (
    Message,
    ModelListChanged,
    ModelListRequest,
    ModelRequest,
    ModelResponse,
    ModelStreamChunk,
)


@dataclass
class ChatMessage:
    """A user message submitted from the chat window.

    ``model`` names the configured model entry to answer with; ``None`` lets the
    harness fall back to its configured default.
    """

    text: str
    model: str | None = None


@dataclass
class AttachmentParsed:
    """A file attachment discovered in a chat message and read by the harness."""

    path: str
    kind: str
    content: str


@dataclass
class ChatStreamChunk:
    """A streamed assistant delta for rendering."""

    delta: str
    done: bool


@dataclass
class ChatTurnComplete:
    """The finalized assistant text for a completed turn.

    ``error`` is set (and ``text`` left empty) when the model call failed; the
    chat window renders the error instead of a response.
    """

    text: str
    error: str | None = None


__all__ = [
    "AttachmentParsed",
    "ChatMessage",
    "ChatStreamChunk",
    "ChatTurnComplete",
    "Message",
    "ModelListChanged",
    "ModelListRequest",
    "ModelRequest",
    "ModelResponse",
    "ModelStreamChunk",
]
