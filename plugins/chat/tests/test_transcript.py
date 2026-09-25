"""Unit tests for the Qt-free transcript model state machine."""

from __future__ import annotations

from plugins.chat.src.transcript import TranscriptModel


def test_send_records_user_turn() -> None:
    transcript = TranscriptModel()

    transcript.add_user("hello")

    assert [(t.role, t.text) for t in transcript.turns()] == [("user", "hello")]


def test_begin_assistant_creates_pending_turn() -> None:
    transcript = TranscriptModel()

    transcript.begin_assistant()

    assert transcript.turns()[-1].pending is True


def test_append_delta_accumulates_into_assistant_turn() -> None:
    transcript = TranscriptModel()
    transcript.begin_assistant()

    transcript.append_delta("Hel")
    transcript.append_delta("lo")

    assert transcript.turns()[-1].text == "Hello"


def test_complete_finalizes_pending_turn() -> None:
    transcript = TranscriptModel()
    transcript.begin_assistant()
    transcript.append_delta("partial")

    transcript.complete("Hi there")

    turn = transcript.turns()[-1]
    assert (turn.text, turn.pending) == ("Hi there", False)


def test_turns_preserve_user_then_assistant_order() -> None:
    transcript = TranscriptModel()
    transcript.add_user("q")
    transcript.begin_assistant()
    transcript.append_delta("a")

    assert [t.role for t in transcript.turns()] == ["user", "assistant"]


def test_append_delta_without_begin_creates_assistant_turn() -> None:
    transcript = TranscriptModel()

    transcript.append_delta("orphan")

    assert transcript.turns()[-1].role == "assistant"


def test_complete_without_begin_creates_finalized_turn() -> None:
    transcript = TranscriptModel()

    transcript.complete("done")

    assert transcript.turns()[-1].pending is False
