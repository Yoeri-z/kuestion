"""Unit tests for conversation assembly and history ordering."""

from __future__ import annotations

from plugins.harness.events import Message
from plugins.harness.src.conversation import Conversation


def test_request_prepends_system_prompt() -> None:
    conversation = Conversation(system_prompt="Be brief.")
    conversation.add_user("hi")

    request = conversation.assemble_request(model="default")

    assert request.messages == [Message("system", "Be brief."), Message("user", "hi")]


def test_history_preserves_multi_turn_ordering() -> None:
    conversation = Conversation()
    conversation.add_user("first")
    conversation.add_assistant("reply")
    conversation.add_user("second")

    request = conversation.assemble_request(model="default")

    assert [m.role for m in request.messages] == ["system", "user", "assistant", "user"]


def test_request_is_streaming_against_configured_model() -> None:
    request = Conversation().assemble_request(model="gpt-local")

    assert (request.model, request.stream) == ("gpt-local", True)
