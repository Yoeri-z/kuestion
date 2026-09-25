"""Shared fixtures for the keyregistry plugin tests."""

from __future__ import annotations

import pytest

RECORDED_SSE = [
    'data: {"choices":[{"delta":{"content":"Hel"}}]}',
    'data: {"choices":[{"delta":{"content":"lo"}}]}',
    "data: [DONE]",
]


@pytest.fixture
def recorded_sse() -> list[str]:
    return list(RECORDED_SSE)
