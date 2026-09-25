"""HTTP request building, SSE parsing, and the concrete transport.

Kept free of Qt and of the plugin lifecycle so it can be tested with a fake
transport and recorded SSE payloads.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Protocol

import httpx

from plugins.keyregistry.events import Message
from plugins.keyregistry.src.config import ModelEntry


@dataclass(frozen=True)
class ChatRequest:
    """A ready-to-send OpenAI-compatible chat completion request."""

    url: str
    headers: dict[str, str]
    body: dict


@dataclass(frozen=True)
class StreamEvent:
    """A parsed SSE event: either a delta or the terminal marker."""

    delta: str
    done: bool


def build_chat_request(
    entry: ModelEntry, messages: list[Message], *, stream: bool
) -> ChatRequest:
    """Build the request for ``entry`` from ``messages``."""
    headers = {"Content-Type": "application/json"}
    headers.update({row.key: row.value for row in entry.headers})
    if entry.api_key:
        headers["Authorization"] = f"Bearer {entry.api_key}"
    body = {
        "model": entry.model_id,
        "stream": stream,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
    }
    return ChatRequest(
        url=f"{entry.base_url.rstrip('/')}/chat/completions",
        headers=headers,
        body=body,
    )


def iter_stream_events(lines: Iterable[str]) -> Iterator[StreamEvent]:
    """Parse OpenAI-style SSE ``lines`` into delta events, always ending with a
    ``done`` event (whether or not the stream carried a ``[DONE]`` marker)."""
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue
        data = stripped[len("data:") :].strip()
        if data == "[DONE]":
            yield StreamEvent("", True)
            return
        delta = _extract_delta(data)
        if delta:
            yield StreamEvent(delta, False)
    yield StreamEvent("", True)


def _extract_delta(data: str) -> str:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return ""
    choices = payload.get("choices") or []
    if not choices:
        return ""
    return choices[0].get("delta", {}).get("content") or ""


class Transport(Protocol):
    """Streaming/synchronous HTTP transport used by :class:`ModelClient`."""

    def stream(self, request: ChatRequest) -> Iterator[str]:
        """Yield response lines for a streaming request."""
        ...

    def send(self, request: ChatRequest) -> str:
        """Return the full response body for a non-streaming request."""
        ...


def raise_for_status(response: httpx.Response) -> None:
    """Raise ``httpx.HTTPStatusError`` for a non-2xx ``response``, including the
    server's status, reason phrase, url and response body.

    ``httpx``'s own ``raise_for_status`` drops the body (and with it the provider's
    error message) and points at generic MDN docs; this surfaces the real reason
    so it can travel on ``ModelResponse.error`` and reach the chat window.
    """
    if response.is_success:
        return
    response.read()
    detail = f"HTTP {response.status_code} {response.reason_phrase} for {response.request.url}"
    body = response.text.strip()
    if body:
        detail = f"{detail}: {body}"
    raise httpx.HTTPStatusError(detail, request=response.request, response=response)


class HttpxTransport:
    """Real transport backed by ``httpx``."""

    def __init__(self, timeout: float = 120.0) -> None:
        self._timeout = timeout

    def stream(self, request: ChatRequest) -> Iterator[str]:
        with httpx.stream(
            "POST",
            request.url,
            headers=request.headers,
            json=request.body,
            timeout=self._timeout,
        ) as response:
            raise_for_status(response)
            yield from response.iter_lines()

    def send(self, request: ChatRequest) -> str:
        response = httpx.post(
            request.url,
            headers=request.headers,
            json=request.body,
            timeout=self._timeout,
        )
        raise_for_status(response)
        return response.text
