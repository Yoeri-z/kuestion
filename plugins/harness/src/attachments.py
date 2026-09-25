"""Detect and read text-file attachments referenced in a chat message.

v1 is deliberately simple: any whitespace-delimited token that names an existing
file is treated as an attachment; only files readable as UTF-8 text are kept.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from plugins.harness.events import AttachmentParsed

_PUNCTUATION = ".,;:!?()[]{}\"'"


def find_attachment_paths(text: str) -> list[Path]:
    """Return existing file paths found as tokens in ``text``."""
    paths: list[Path] = []
    for token in text.split():
        candidate = Path(token.strip(_PUNCTUATION))
        if candidate.is_file():
            paths.append(candidate)
    return paths


def read_text_attachments(paths: Iterable[Path]) -> list[AttachmentParsed]:
    """Read each path as UTF-8 text, skipping anything unreadable or binary."""
    attachments: list[AttachmentParsed] = []
    for path in paths:
        try:
            content = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        attachments.append(AttachmentParsed(path=str(path), kind="text", content=content))
    return attachments
