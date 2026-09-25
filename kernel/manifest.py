"""Plugin manifest contract and validation.

A manifest is a plain Python module exposing a ``MANIFEST`` constant built from
the :class:`Manifest` dataclass. Keeping the manifest in Python lets event types
be referenced directly as class objects rather than by string name, preserving
static verifiability of the plugin contract surface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
_ENTRY_RE = re.compile(r"^\w+(\.\w+)*:\w+$")


@dataclass(frozen=True, kw_only=True)
class ReEmit:
    """Middleware subscription: re-emit ``event_type`` scoped to ``target_id``
    (``None`` = all consumers of the type). Lower priority runs first."""

    event_type: type
    target_id: str | None = None
    priority: int = 100


@dataclass(frozen=True, kw_only=True)
class Consume:
    """Consume subscription. ``directed_only`` restricts it to events targeted
    at this plugin."""

    event_type: type
    directed_only: bool = False


@dataclass(frozen=True, kw_only=True)
class Manifest:
    """Declarative description of a plugin's contract surface."""

    id: str
    entry: str
    emits: tuple[type, ...] = ()
    consumes: tuple[Consume, ...] = ()
    reemits: tuple[ReEmit, ...] = ()
    requires: tuple[str, ...] = ()
    pip_deps: tuple[str, ...] = ()
    main_thread: bool = False


def validate_manifest(manifest: Manifest) -> list[str]:
    """Return a list of human-readable validation errors (empty when valid)."""
    errors: list[str] = []

    if not _ID_RE.match(manifest.id):
        errors.append(
            f"invalid id: {manifest.id!r} must be a dotted lower_snake identifier"
        )
    if not _ENTRY_RE.match(manifest.entry):
        errors.append(
            f"invalid entry: {manifest.entry!r} must match 'module.path:ClassName'"
        )

    errors.extend(_non_class_errors("emits", manifest.emits))
    errors.extend(_non_class_errors("consumes", manifest.consumes))
    errors.extend(_non_class_errors("reemits", manifest.reemits))

    errors.extend(_duplicate_errors("emits", manifest.emits))
    errors.extend(_duplicate_errors("consumes", manifest.consumes))
    errors.extend(_duplicate_errors("reemits", manifest.reemits))

    if manifest.id in manifest.requires:
        errors.append(
            f"requires must not include the plugin's own id: {manifest.id!r}"
        )

    return errors


def _declared_type(entry: object) -> object:
    return entry if isinstance(entry, type) else getattr(entry, "event_type", entry)


def _non_class_errors(field_name: str, entries: tuple[object, ...]) -> list[str]:
    return [
        f"{field_name} contains non-class event type: {_declared_type(entry)!r}"
        for entry in entries
        if not isinstance(_declared_type(entry), type)
    ]


def _duplicate_errors(field_name: str, entries: tuple[object, ...]) -> list[str]:
    seen: set[object] = set()
    errors: list[str] = []
    for entry in entries:
        if entry in seen:
            errors.append(f"duplicate {field_name} entry")
        else:
            seen.add(entry)
    return errors
