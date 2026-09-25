"""Turns a :class:`ModelRequest` into a stream of response chunks.

The transport is injected so tests can supply canned responses; no threading or
event-bus knowledge lives here.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from plugins.keyregistry.events import ModelRequest, ModelStreamChunk
from plugins.keyregistry.src.config import ModelEntry
from plugins.keyregistry.src.transport import Transport, build_chat_request, iter_stream_events


class ModelClient:
    """Executes a model request against a configured entry."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def complete(self, entry: ModelEntry, request: ModelRequest) -> Iterator[ModelStreamChunk]:
        """Yield the response chunks for ``request``.

        Streaming requests yield every delta then a ``done`` chunk;
        non-streaming requests yield a single final chunk.
        """
        chat = build_chat_request(entry, request.messages, stream=request.stream)
        if request.stream:
            for event in iter_stream_events(self._transport.stream(chat)):
                yield ModelStreamChunk(delta=event.delta, done=event.done)
            return
        yield ModelStreamChunk(delta=_extract_content(self._transport.send(chat)), done=True)


def _extract_content(body: str) -> str:
    payload = json.loads(body)
    return payload["choices"][0]["message"]["content"]
