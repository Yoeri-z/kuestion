"""Configuration of model entries and their header rows.

Entries are held in memory and, when a path is configured, persisted to a JSON
file (plaintext, including the API key) so they survive restarts. The registry
is shared between the UI (main) thread and request (worker) threads, so every
mutation is guarded by a lock and notifies subscribers so the UI can react to
changes.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class HeaderRow:
    """An extra HTTP header sent with requests to a model entry."""

    key: str
    value: str


@dataclass
class ModelEntry:
    """A configured OpenAI-compatible endpoint."""

    name: str
    base_url: str
    model_id: str
    headers: list[HeaderRow] = field(default_factory=list)
    api_key: str = ""


class ModelRegistry:
    """Holds the known model entries, keyed by name.

    Thread-safe: mutations take a lock, then notify every subscriber (outside
    the lock, so a subscriber may safely read the registry).
    """

    def __init__(self, path: Path | None = None) -> None:
        self._entries: dict[str, ModelEntry] = {}
        self._lock = threading.Lock()
        self._listeners: list[Callable[[], None]] = []
        self._path = path
        if path is not None:
            self._load(path)

    def subscribe(self, listener: Callable[[], None]) -> None:
        """Register ``listener`` to be called after every mutation."""
        self._listeners.append(listener)

    def add(self, entry: ModelEntry) -> None:
        with self._lock:
            self._entries[entry.name] = entry
        self._notify()

    def remove(self, name: str) -> None:
        with self._lock:
            self._entries.pop(name, None)
        self._notify()

    def get(self, name: str) -> ModelEntry | None:
        with self._lock:
            return self._entries.get(name)

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._entries)

    def entries(self) -> list[ModelEntry]:
        with self._lock:
            return [self._entries[name] for name in sorted(self._entries)]

    def add_header(self, name: str, key: str, value: str) -> None:
        with self._lock:
            self._entry(name).headers.append(HeaderRow(key, value))
        self._notify()

    def remove_header(self, name: str, index: int) -> None:
        with self._lock:
            del self._entry(name).headers[index]
        self._notify()

    def _entry(self, name: str) -> ModelEntry:
        entry = self._entries.get(name)
        if entry is None:
            raise KeyError(f"unknown model entry: {name!r}")
        return entry

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()
        self._save()

    # -- persistence ------------------------------------------------------

    def _load(self, path: Path) -> None:
        try:
            raw = json.loads(path.read_text())
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("ignoring unreadable model config %s: %s", path, exc)
            return
        if not isinstance(raw, list):
            logger.warning("ignoring model config %s: expected a JSON array", path)
            return
        for item in raw:
            try:
                entry = entry_from_dict(item)
            except (KeyError, TypeError) as exc:
                logger.warning("skipping invalid model entry in %s: %s", path, exc)
                continue
            self._entries[entry.name] = entry

    def _save(self) -> None:
        if self._path is None:
            return
        payload = json.dumps([entry_to_dict(entry) for entry in self.entries()], indent=2)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_name(f".{self._path.name}.tmp")
            tmp.write_text(payload)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self._path)
        except OSError as exc:
            logger.warning("could not persist model config %s: %s", self._path, exc)


def entry_to_dict(entry: ModelEntry) -> dict:
    """Serialize an entry to a JSON-friendly dict (API key included, plaintext)."""
    return {
        "name": entry.name,
        "base_url": entry.base_url,
        "model_id": entry.model_id,
        "api_key": entry.api_key,
        "headers": [{"key": row.key, "value": row.value} for row in entry.headers],
    }


def entry_from_dict(data: dict) -> ModelEntry:
    """Rebuild an entry from :func:`entry_to_dict` output."""
    return ModelEntry(
        name=data["name"],
        base_url=data.get("base_url", ""),
        model_id=data.get("model_id", ""),
        api_key=data.get("api_key", ""),
        headers=[HeaderRow(row["key"], row.get("value", "")) for row in data.get("headers", [])],
    )
