"""Shared Qt test fixtures for the windowing plugin.

A single ``QApplication`` is created for the whole test session. Widgets are
constructed but never shown and no event loop is ever started.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def qapp() -> Iterator[QApplication]:
    app = QApplication.instance() or QApplication([])
    yield app
