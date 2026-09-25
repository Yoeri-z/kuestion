"""Typed event envelope and reply helper."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Event:
    """A single typed message travelling on the bus.

    ``target_id`` of ``None`` means broadcast; otherwise the event is directed
    at exactly one plugin. ``correlation_id`` ties a response to its request.
    """

    event_type: type
    payload: object
    sender_id: str
    target_id: str | None = None
    correlation_id: str | None = None
    timestamp: float = field(default_factory=time.time)


def reply_to(event: Event, payload: object, *, sender_id: str) -> Event:
    """Build a directed reply to ``event``'s sender, reusing (or generating)
    the correlation id so the pair can be matched."""
    return Event(
        event_type=type(payload),
        payload=payload,
        sender_id=sender_id,
        target_id=event.sender_id,
        correlation_id=event.correlation_id or uuid.uuid4().hex,
    )
