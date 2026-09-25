"""Qt-free bounded event trace model.

The plugin's ``on_load`` registers :meth:`EventLogModel.record` as a bus
observer, so it is called on the event thread for every dispatched event while
the UI thread may read :meth:`entries` concurrently — hence the lock.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass

from kernel.envelope import Event

#: Default number of most-recent events retained before the oldest is evicted.
DEFAULT_CAPACITY = 1000


@dataclass(frozen=True)
class EventLogEntry:
    """One observed event, flattened into display-ready fields."""

    timestamp: float
    event_type_name: str
    sender_id: str
    target_id: str | None
    correlation_id: str | None
    payload_repr: str


class EventLogModel:
    """Thread-safe, capacity-bounded trace of every event on the bus."""

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        self._entries: deque[EventLogEntry] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def record(self, event: Event) -> None:
        """Append one observed event (called from the event thread)."""
        entry = EventLogEntry(
            timestamp=event.timestamp,
            event_type_name=event.event_type.__name__,
            sender_id=event.sender_id,
            target_id=event.target_id,
            correlation_id=event.correlation_id,
            payload_repr=repr(event.payload),
        )
        with self._lock:
            self._entries.append(entry)

    def entries(self) -> list[EventLogEntry]:
        """Return a snapshot of the traced events, oldest first."""
        with self._lock:
            return list(self._entries)
