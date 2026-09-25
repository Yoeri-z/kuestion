"""Unit tests for attachment path detection and text-file reading."""

from __future__ import annotations

from pathlib import Path

from plugins.harness.src.attachments import find_attachment_paths, read_text_attachments


def test_finds_existing_file_path_in_text(tmp_path: Path) -> None:
    note = tmp_path / "note.txt"
    note.write_text("contents")

    paths = find_attachment_paths(f"please read {note} now")

    assert paths == [note]


def test_ignores_tokens_that_are_not_files() -> None:
    paths = find_attachment_paths("no files here")

    assert paths == []


def test_reads_text_file_into_attachment(tmp_path: Path) -> None:
    note = tmp_path / "note.txt"
    note.write_text("hello attachment")

    attachments = read_text_attachments([note])

    assert len(attachments) == 1
    assert (attachments[0].path, attachments[0].content) == (str(note), "hello attachment")


def test_skips_files_that_are_not_valid_text(tmp_path: Path) -> None:
    binary = tmp_path / "blob.bin"
    binary.write_bytes(b"\xff\xfe\x00\x01")

    attachments = read_text_attachments([binary])

    assert attachments == []
