"""Unit tests for the example plugin's pure history-trimming logic."""

from __future__ import annotations

from plugins.keyregistry.events import Message
from plugins.trim_history.src.trimming import trim_history


def conversation(count: int) -> list[Message]:
    return [Message("user", f"message {index}") for index in range(count)]


def test_short_history_is_returned_unchanged() -> None:
    history = conversation(3)

    result = trim_history(history, keep=5)

    assert result == history


def test_keeps_only_the_most_recent_messages() -> None:
    history = conversation(5)

    result = trim_history(history, keep=2)

    assert result == [Message("user", "message 3"), Message("user", "message 4")]


def test_assistant_messages_count_as_conversation() -> None:
    history = [Message("user", "message 0"), Message("assistant", "reply 0")]

    result = trim_history(history, keep=1)

    assert result == [Message("assistant", "reply 0")]


def test_keep_equal_to_the_conversation_length_is_returned_unchanged() -> None:
    history = conversation(3)

    result = trim_history(history, keep=3)

    assert result == history


def test_system_messages_are_hoisted_to_the_front() -> None:
    history = [
        Message("user", "message 0"),
        Message("system", "be brief"),
        Message("user", "message 1"),
    ]

    result = trim_history(history, keep=1)

    assert result == [Message("system", "be brief"), Message("user", "message 1")]


def test_system_messages_do_not_count_toward_the_limit() -> None:
    history = [Message("system", "be brief"), *conversation(4)]

    result = trim_history(history, keep=2)

    assert result == [
        Message("system", "be brief"),
        Message("user", "message 2"),
        Message("user", "message 3"),
    ]


def test_zero_limit_drops_the_conversation_but_keeps_system() -> None:
    history = [Message("system", "be brief"), Message("user", "hello")]

    result = trim_history(history, keep=0)

    assert result == [Message("system", "be brief")]


def test_negative_limit_also_drops_the_conversation() -> None:
    history = [Message("system", "be brief"), Message("user", "hello")]

    result = trim_history(history, keep=-1)

    assert result == [Message("system", "be brief")]


def test_empty_history_stays_empty() -> None:
    result = trim_history([], keep=10)

    assert result == []


def test_all_system_messages_are_kept() -> None:
    history = [Message("system", "be brief"), Message("system", "and kind")]

    result = trim_history(history, keep=0)

    assert result == history
