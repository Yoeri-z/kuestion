"""Unit tests for the chat plugin handlers against a fake bus."""

from __future__ import annotations

import pytest

from plugins.chat.plugin import ChatPlugin
from plugins.harness.events import (
    ChatMessage,
    ChatStreamChunk,
    ChatTurnComplete,
    ModelListChanged,
    ModelListRequest,
)
from kernel.envelope import Event
from kernel.manifest import Manifest


class FakeBus:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


@pytest.fixture
def plugin() -> ChatPlugin:
    instance = ChatPlugin()
    instance.manifest = Manifest(id="kuestion.chat", entry="plugin:ChatPlugin")
    instance.bus = FakeBus()
    return instance


def harness_event(event_type: type, payload: object) -> Event:
    return Event(event_type=event_type, payload=payload, sender_id="kuestion.harness")


def models_event(names: list[str]) -> Event:
    return Event(
        event_type=ModelListChanged,
        payload=ModelListChanged(names),
        sender_id="kuestion.keyregistry",
    )


def test_submitted_text_becomes_directed_chat_message(plugin: ChatPlugin) -> None:
    plugin._on_submitted("hello")

    message = plugin.bus.events[0]
    assert message.event_type is ChatMessage
    assert message.target_id == "kuestion.harness"


def test_stream_chunk_appends_to_transcript(plugin: ChatPlugin) -> None:
    plugin._on_submitted("hello")

    plugin._on_chunk(harness_event(ChatStreamChunk, ChatStreamChunk("Hi", False)))

    assert plugin.transcript()[-1].text == "Hi"


def test_turn_complete_finalizes_transcript(plugin: ChatPlugin) -> None:
    plugin._on_submitted("hello")

    plugin._on_turn_complete(harness_event(ChatTurnComplete, ChatTurnComplete("Hi there")))

    turn = plugin.transcript()[-1]
    assert (turn.text, turn.pending) == ("Hi there", False)


def test_turn_complete_records_error(plugin: ChatPlugin) -> None:
    plugin._on_submitted("hello")

    plugin._on_turn_complete(harness_event(ChatTurnComplete, ChatTurnComplete("", error="boom")))

    assert plugin.transcript()[-1].error == "boom"


def test_model_list_is_tracked(plugin: ChatPlugin) -> None:
    plugin._on_models_changed(models_event(["alpha", "beta"]))

    assert plugin.models() == ["alpha", "beta"]


def test_first_model_is_selected_by_default(plugin: ChatPlugin) -> None:
    plugin._on_models_changed(models_event(["alpha", "beta"]))

    assert plugin.selected_model() == "alpha"


def test_existing_selection_is_preserved(plugin: ChatPlugin) -> None:
    plugin._on_models_changed(models_event(["alpha", "beta"]))
    plugin._on_model_selected("beta")

    plugin._on_models_changed(models_event(["alpha", "beta", "gamma"]))

    assert plugin.selected_model() == "beta"


def test_removed_selection_falls_back_to_first(plugin: ChatPlugin) -> None:
    plugin._on_models_changed(models_event(["alpha", "beta"]))
    plugin._on_model_selected("beta")

    plugin._on_models_changed(models_event(["alpha"]))

    assert plugin.selected_model() == "alpha"


def test_empty_model_list_clears_selection(plugin: ChatPlugin) -> None:
    plugin._on_models_changed(models_event(["alpha"]))

    plugin._on_models_changed(models_event([]))

    assert plugin.selected_model() is None


def test_clearing_selection_yields_none(plugin: ChatPlugin) -> None:
    plugin._on_model_selected("")

    assert plugin.selected_model() is None


def test_send_includes_selected_model(plugin: ChatPlugin) -> None:
    plugin._on_models_changed(models_event(["alpha", "beta"]))
    plugin._on_model_selected("beta")

    plugin._on_submitted("hello")

    assert plugin.bus.events[0].payload.model == "beta"


def test_request_model_list_targets_key_registry(plugin: ChatPlugin) -> None:
    plugin._request_model_list()

    request = plugin.bus.events[0]
    assert request.event_type is ModelListRequest
    assert request.target_id == "kuestion.keyregistry"
