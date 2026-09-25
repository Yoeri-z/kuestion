"""Unit tests for the Qt-free event-log model."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from kernel.envelope import Event
from plugins.eventlog.src.log_model import EventLogEntry, EventLogModel


@dataclass
class Ping:
    value: int = 0


def make_event(
    *,
    sender_id: str = "kuestion.a",
    target_id: str | None = None,
    correlation_id: str | None = None,
    timestamp: float = 123.0,
) -> Event:
    return Event(
        event_type=Ping,
        payload=Ping(7),
        sender_id=sender_id,
        target_id=target_id,
        correlation_id=correlation_id,
        timestamp=timestamp,
    )


def test_record_preserves_every_event_field() -> None:
    model = EventLogModel()

    model.record(
        make_event(
            sender_id="kuestion.a",
            target_id="kuestion.b",
            correlation_id="corr-1",
            timestamp=123.0,
        )
    )

    assert model.entries() == [
        EventLogEntry(
            timestamp=123.0,
            event_type_name="Ping",
            sender_id="kuestion.a",
            target_id="kuestion.b",
            correlation_id="corr-1",
            payload_repr="Ping(value=7)",
        )
    ]


def test_buffer_evicts_the_oldest_entry_at_capacity() -> None:
    model = EventLogModel(capacity=2)

    model.record(make_event(timestamp=1.0))
    model.record(make_event(timestamp=2.0))
    model.record(make_event(timestamp=3.0))

    assert [entry.timestamp for entry in model.entries()] == [2.0, 3.0]


def test_recording_is_safe_from_another_thread_while_reading() -> None:
    model = EventLogModel()
    start = threading.Barrier(2)
    reader_errors: list[BaseException] = []

    def read_entries() -> None:
        start.wait()
        try:
            for _ in range(1000):
                model.entries()
        except BaseException as exc:  # noqa: BLE001 - surface reader failures to the test
            reader_errors.append(exc)

    reader = threading.Thread(target=read_entries)
    reader.start()

    start.wait()
    for index in range(500):
        model.record(make_event(timestamp=float(index)))
    reader.join(timeout=5)

    assert reader_errors == []
    assert len(model.entries()) == 500
