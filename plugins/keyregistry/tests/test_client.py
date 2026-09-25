"""Unit tests for :class:`ModelClient` against a fake transport."""

from __future__ import annotations

from collections.abc import Iterator

from plugins.keyregistry.events import Message, ModelRequest
from plugins.keyregistry.src.client import ModelClient
from plugins.keyregistry.src.config import ModelEntry
from plugins.keyregistry.src.transport import ChatRequest


class FakeTransport:
    """Records requests and replays canned lines / body."""

    def __init__(self, lines: list[str] | None = None, body: str = "{}") -> None:
        self.lines = lines or []
        self.body = body
        self.requests: list[ChatRequest] = []

    def stream(self, request: ChatRequest) -> Iterator[str]:
        self.requests.append(request)
        return iter(self.lines)

    def send(self, request: ChatRequest) -> str:
        self.requests.append(request)
        return self.body


def make_entry() -> ModelEntry:
    return ModelEntry(name="local", base_url="http://localhost:1234/v1", model_id="gpt-local")


def make_request(stream: bool = True) -> ModelRequest:
    return ModelRequest(messages=[Message("user", "hi")], model="local", stream=stream)


def test_streaming_complete_yields_deltas_then_done(recorded_sse: list[str]) -> None:
    client = ModelClient(FakeTransport(lines=recorded_sse))

    chunks = list(client.complete(make_entry(), make_request()))

    assert [(c.delta, c.done) for c in chunks] == [("Hel", False), ("lo", False), ("", True)]


def test_complete_sends_request_to_transport(recorded_sse: list[str]) -> None:
    transport = FakeTransport(lines=recorded_sse)

    drained = list(ModelClient(transport).complete(make_entry(), make_request()))

    assert len(drained) == 3
    assert transport.requests[0].body["stream"] is True


def test_non_streaming_complete_returns_single_final_chunk() -> None:
    body = '{"choices":[{"message":{"content":"Hi there"}}]}'
    client = ModelClient(FakeTransport(body=body))

    chunks = list(client.complete(make_entry(), make_request(stream=False)))

    assert len(chunks) == 1
    assert (chunks[0].delta, chunks[0].done) == ("Hi there", True)
