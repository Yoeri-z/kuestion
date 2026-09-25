"""Event vocabulary for the ``keyregistry`` plugin.

This plugin owns the model-access contract: other plugins (the harness) import
these types rather than declaring their own. A ``ModelRequest`` is *directed* at
``kuestion.keyregistry``; responses and stream chunks are directed back at the
requester with the original correlation id.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Message:
    """A single chat message in OpenAI-compatible form."""

    role: str
    content: str


@dataclass
class ModelRequest:
    """Ask the key registry to talk to a configured model entry.

    ``model`` names a configured :class:`~keyregistry.src.config.ModelEntry`.
    """

    messages: list[Message]
    model: str
    stream: bool = True
    attachment_refs: list[str] = field(default_factory=list)


@dataclass
class ModelResponse:
    """The final result of a request. ``error`` is set instead of ``content``
    when the request failed (no exceptions cross the bus)."""

    content: str
    model: str
    error: str | None = None


@dataclass
class ModelStreamChunk:
    """One streamed delta; ``done`` marks the final chunk."""

    delta: str
    done: bool


@dataclass
class ModelListChanged:
    """Broadcast the configured model-entry names whenever they change."""

    names: list[str]


@dataclass
class ModelListRequest:
    """Ask the key registry to re-publish the configured model list.

    A plugin emits this (directed at the key registry) once it is ready, so it
    receives the entries that were loaded from storage before it registered —
    the boot-time ``ModelListChanged`` emit in ``on_load`` happens before
    dependent plugins exist. The reply is a directed ``ModelListChanged``.
    """
