"""Example middleware plugin: trim conversation history before it reaches the model.

It re-emits ``ModelRequest`` scoped to ``kuestion.keyregistry`` only, so the chat
window's own view of the conversation is untouched. Because the middleware runs
per-consumer (the key registry is the sole consumer of ``ModelRequest``), the
trim affects the outbound request and nothing else.
"""

from __future__ import annotations

from dataclasses import replace

from kernel.envelope import Event
from kernel.plugin import Plugin, reemit

from plugins.keyregistry.events import ModelRequest
from plugins.trim_history.manifest import PRIORITY, TARGET_ID
from plugins.trim_history.src.trimming import trim_history


class TrimHistoryPlugin(Plugin):
    """Middleware that trims the model request history to the most recent messages."""

    @reemit(ModelRequest, target_id=TARGET_ID, priority=PRIORITY)
    def trim(self, event: Event) -> ModelRequest:
        request: ModelRequest = event.payload
        return replace(request, messages=trim_history(request.messages))
