"""In-memory conversation state: a system prompt plus ordered message history."""

from __future__ import annotations

from plugins.harness.events import Message, ModelRequest

DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."


class Conversation:
    """Holds one conversation's messages and assembles model requests."""

    def __init__(self, system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> None:
        self._system_prompt = system_prompt
        self._history: list[Message] = []

    def add_user(self, text: str) -> None:
        self._history.append(Message("user", text))

    def add_assistant(self, text: str) -> None:
        self._history.append(Message("assistant", text))

    def history(self) -> list[Message]:
        return list(self._history)

    def assemble_request(self, model: str, *, stream: bool = True) -> ModelRequest:
        """Build a request of the system prompt followed by the full history."""
        messages = [Message("system", self._system_prompt), *self._history]
        return ModelRequest(messages=messages, model=model, stream=stream)
