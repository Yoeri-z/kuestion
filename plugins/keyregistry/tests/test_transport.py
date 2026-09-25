"""Unit tests for request building and SSE stream parsing (no network)."""

from __future__ import annotations

import httpx
import pytest

from plugins.keyregistry.events import Message
from plugins.keyregistry.src.config import HeaderRow, ModelEntry
from plugins.keyregistry.src.transport import build_chat_request, iter_stream_events, raise_for_status


def entry(**overrides: object) -> ModelEntry:
    fields: dict = {
        "name": "local",
        "base_url": "http://localhost:1234/v1/",
        "model_id": "gpt-local",
        "headers": [HeaderRow("X-Custom", "value")],
        "api_key": "sk-test",
    }
    fields.update(overrides)
    return ModelEntry(**fields)


def test_request_url_joins_chat_completions() -> None:
    request = build_chat_request(entry(), [Message("user", "hi")], stream=True)

    assert request.url == "http://localhost:1234/v1/chat/completions"


def test_request_headers_merge_custom_and_bearer() -> None:
    request = build_chat_request(entry(), [Message("user", "hi")], stream=True)

    assert request.headers["X-Custom"] == "value"
    assert request.headers["Authorization"] == "Bearer sk-test"


def test_request_body_maps_messages() -> None:
    request = build_chat_request(
        entry(), [Message("system", "s"), Message("user", "u")], stream=True
    )

    assert request.body["messages"] == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
    ]


def test_request_body_carries_stream_flag() -> None:
    request = build_chat_request(entry(), [Message("user", "hi")], stream=False)

    assert request.body["stream"] is False


def test_stream_events_yield_deltas_then_done(recorded_sse: list[str]) -> None:
    events = list(iter_stream_events(recorded_sse))

    assert [(e.delta, e.done) for e in events] == [
        ("Hel", False),
        ("lo", False),
        ("", True),
    ]


def test_stream_without_done_marker_still_terminates_with_done(recorded_sse: list[str]) -> None:
    events = list(iter_stream_events(recorded_sse[:2]))

    assert events[-1].done is True


def http_response(status: int, body: str = "") -> httpx.Response:
    request = httpx.Request("POST", "http://localhost:1234/v1/chat/completions")
    return httpx.Response(status, text=body, request=request)


def test_raise_for_status_allows_success() -> None:
    assert raise_for_status(http_response(200, "ok")) is None


def test_raise_for_status_includes_response_body() -> None:
    response = http_response(400, '{"error": {"message": "invalid api key"}}')

    with pytest.raises(httpx.HTTPStatusError) as raised:
        raise_for_status(response)

    assert "invalid api key" in str(raised.value)


def test_raise_for_status_includes_status_and_url() -> None:
    response = http_response(401, "nope")

    with pytest.raises(httpx.HTTPStatusError) as raised:
        raise_for_status(response)

    assert "HTTP 401" in str(raised.value)
    assert "http://localhost:1234/v1/chat/completions" in str(raised.value)


def test_raise_for_status_includes_reason_phrase() -> None:
    response = http_response(401, "nope")

    with pytest.raises(httpx.HTTPStatusError) as raised:
        raise_for_status(response)

    assert "Unauthorized" in str(raised.value)


def test_raise_for_status_with_empty_body_still_raises() -> None:
    response = http_response(500)

    with pytest.raises(httpx.HTTPStatusError) as raised:
        raise_for_status(response)

    assert "HTTP 500" in str(raised.value)
