"""Qt-free transcript model: the chat state machine."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Turn:
    """One message in the transcript."""

    role: str
    text: str = ""
    pending: bool = field(default=False)
    error: str | None = None


class TranscriptModel:
    """Tracks the user and assistant turns of the current conversation."""

    def __init__(self) -> None:
        self._turns: list[Turn] = []

    def add_user(self, text: str) -> None:
        self._turns.append(Turn("user", text))

    def begin_assistant(self) -> Turn:
        """Append an empty, pending assistant turn and return it."""
        turn = Turn("assistant", "", pending=True)
        self._turns.append(turn)
        return turn

    def append_delta(self, delta: str) -> None:
        self._current_assistant().text += delta

    def complete(self, text: str, *, error: str | None = None) -> None:
        turn = self._current_assistant()
        turn.text = text
        turn.error = error
        turn.pending = False

    def turns(self) -> list[Turn]:
        return list(self._turns)

    def _current_assistant(self) -> Turn:
        if self._turns and self._turns[-1].role == "assistant":
            return self._turns[-1]
        return self.begin_assistant()
