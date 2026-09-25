"""Unit tests for the example middleware plugin's re-emit handler."""

from __future__ import annotations

import pytest

from kernel.envelope import Event
from plugins.keyregistry.events import Message, ModelRequest
from plugins.trim_history.manifest import MANIFEST
from plugins.trim_history.plugin import TrimHistoryPlugin


def conversation(count: int) -> list[Message]:
    return [Message("user", f"message {index}") for index in range(count)]


def request_with(messages: list[Message]) -> ModelRequest:
    return ModelRequest(
        messages=messages,
        model="gpt-local",
        stream=False,
        attachment_refs=["note.txt"],
    )


@pytest.fixture
def plugin() -> TrimHistoryPlugin:
    instance = TrimHistoryPlugin()
    instance.manifest = MANIFEST
    return instance


def trim(plugin: TrimHistoryPlugin, request: ModelRequest) -> ModelRequest:
    event = Event(event_type=ModelRequest, payload=request, sender_id="kuestion.harness")
    return plugin.trim(event)


def test_handler_trims_a_long_history(plugin: TrimHistoryPlugin) -> None:
    request = request_with(conversation(20))

    result = trim(plugin, request)

    assert len(result.messages) == 10


def test_handler_passes_a_short_history_through_unchanged(plugin: TrimHistoryPlugin) -> None:
    messages = conversation(2)

    result = trim(plugin, request_with(messages))

    assert result.messages == messages


def test_handler_preserves_the_other_request_fields(plugin: TrimHistoryPlugin) -> None:
    request = request_with(conversation(20))

    result = trim(plugin, request)

    assert (result.model, result.stream, result.attachment_refs) == (
        "gpt-local",
        False,
        ["note.txt"],
    )
