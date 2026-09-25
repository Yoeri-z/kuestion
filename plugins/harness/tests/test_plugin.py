"""Unit tests for the harness event handlers against a fake bus."""

from __future__ import annotations

from pathlib import Path

import pytest

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
from plugins.harness.plugin import HarnessPlugin
from kernel.envelope import Event
from kernel.manifest import Manifest


class FakeBus:
    """Records everything emitted, in order."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


@pytest.fixture
def plugin() -> HarnessPlugin:
    instance = HarnessPlugin(model="gpt-local")
    instance.manifest = Manifest(id="kuestion.harness", entry="plugin:HarnessPlugin")
    instance.bus = FakeBus()
    return instance


def send_chat(plugin: HarnessPlugin, text: str, model: str | None = None) -> None:
    plugin._on_chat_message(
        Event(
            event_type=ChatMessage,
            payload=ChatMessage(text, model=model),
            sender_id="kuestion.chat",
        )
    )


def begin_turn(plugin: HarnessPlugin, text: str = "hello") -> str:
    """Submit a chat message and return the correlation id of its request."""
    send_chat(plugin, text)
    return plugin.bus.events[0].correlation_id


def last_event_of_type(plugin: HarnessPlugin, event_type: type) -> Event:
    return next(e for e in reversed(plugin.bus.events) if e.event_type is event_type)


def test_chat_message_emits_request_directed_at_keyregistry(plugin: HarnessPlugin) -> None:
    send_chat(plugin, "hello")

    request = plugin.bus.events[0]
    assert request.event_type is ModelRequest
    assert request.target_id == "kuestion.keyregistry"


def test_chat_message_requests_carry_a_correlation_id(plugin: HarnessPlugin) -> None:
    send_chat(plugin, "hello")

    assert plugin.bus.events[0].correlation_id


def test_chat_message_model_overrides_default(plugin: HarnessPlugin) -> None:
    send_chat(plugin, "hello", model="other-model")

    assert plugin.bus.events[0].payload.model == "other-model"


def test_chat_message_without_model_uses_default(plugin: HarnessPlugin) -> None:
    send_chat(plugin, "hello")

    assert plugin.bus.events[0].payload.model == "gpt-local"


def test_attachment_path_is_parsed_and_included(plugin: HarnessPlugin, tmp_path: Path) -> None:
    note = tmp_path / "note.txt"
    note.write_text("attachment body")

    send_chat(plugin, f"read {note}")

    attachment = last_event_of_type(plugin, AttachmentParsed)
    assert attachment.payload.content == "attachment body"


def test_stream_chunk_maps_to_chat_stream_chunk(plugin: HarnessPlugin) -> None:
    correlation = begin_turn(plugin)

    plugin._on_stream_chunk(
        Event(
            event_type=ModelStreamChunk,
            payload=ModelStreamChunk("Hi", False),
            sender_id="kuestion.keyregistry",
            correlation_id=correlation,
        )
    )

    chunk = last_event_of_type(plugin, ChatStreamChunk)
    assert chunk.payload == ChatStreamChunk("Hi", False)


def test_response_completes_turn_and_records_history(plugin: HarnessPlugin) -> None:
    correlation = begin_turn(plugin)

    plugin._on_model_response(
        Event(
            event_type=ModelResponse,
            payload=ModelResponse("Hi there", "gpt-local"),
            sender_id="kuestion.keyregistry",
            correlation_id=correlation,
        )
    )

    assert last_event_of_type(plugin, ChatTurnComplete).payload == ChatTurnComplete("Hi there")
    assert plugin.history()[-1] == Message("assistant", "Hi there")


def test_stream_chunk_with_unknown_correlation_is_ignored(plugin: HarnessPlugin) -> None:
    plugin._on_stream_chunk(
        Event(
            event_type=ModelStreamChunk,
            payload=ModelStreamChunk("Hi", False),
            sender_id="kuestion.keyregistry",
            correlation_id="unknown",
        )
    )

    assert plugin.bus.events == []


def test_response_error_is_reported_in_turn_complete(plugin: HarnessPlugin) -> None:
    correlation = begin_turn(plugin)

    plugin._on_model_response(
        Event(
            event_type=ModelResponse,
            payload=ModelResponse("", "gpt-local", error="boom"),
            sender_id="kuestion.keyregistry",
            correlation_id=correlation,
        )
    )

    assert last_event_of_type(plugin, ChatTurnComplete).payload.error == "boom"


def test_response_error_is_not_recorded_as_assistant_history(plugin: HarnessPlugin) -> None:
    correlation = begin_turn(plugin)

    plugin._on_model_response(
        Event(
            event_type=ModelResponse,
            payload=ModelResponse("", "gpt-local", error="boom"),
            sender_id="kuestion.keyregistry",
            correlation_id=correlation,
        )
    )

    assert plugin.history() == [Message("user", "hello")]


def test_response_with_unknown_correlation_is_ignored(plugin: HarnessPlugin) -> None:
    plugin._on_model_response(
        Event(
            event_type=ModelResponse,
            payload=ModelResponse("Hi", "gpt-local"),
            sender_id="kuestion.keyregistry",
            correlation_id="unknown",
        )
    )

    assert plugin.bus.events == []
