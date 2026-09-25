"""Pure history-trimming logic for the example middleware plugin.

Kept Qt-free and bus-free so it can be unit-tested directly.
"""

from __future__ import annotations

from plugins.keyregistry.events import Message

#: How many non-system messages to keep by default.
MAX_HISTORY = 10


def trim_history(messages: list[Message], keep: int = MAX_HISTORY) -> list[Message]:
    """Return every system message plus the most recent ``keep`` other messages.

    A non-positive ``keep`` drops the conversation while still preserving the
    system prompt(s).
    """
    system = [message for message in messages if message.role == "system"]
    conversation = [message for message in messages if message.role != "system"]
    if keep <= 0:
        return system
    return [*system, *conversation[-keep:]]
