"""Registry mapping event types to the plugin that declares them.

Event type names are globally unique across the loaded plugin set: a plugin that
needs a type declared by another plugin must import it rather than redeclare it.
"""

from __future__ import annotations


class DuplicateTypeError(Exception):
    """Raised when two plugins declare an event type with the same name."""

    def __init__(self, event_type: type, first_plugin: str, second_plugin: str) -> None:
        self.event_type = event_type
        self.first_plugin = first_plugin
        self.second_plugin = second_plugin
        super().__init__(
            f"event type '{event_type.__name__}' already declared by plugin "
            f"'{first_plugin}' (requested by '{second_plugin}')"
        )


class TypeRegistry:
    """Records which plugin declares each event type."""

    def __init__(self) -> None:
        self._owners: dict[type, str] = {}
        self._by_name: dict[str, type] = {}

    def register(self, plugin_id: str, event_type: type) -> None:
        """Register ``event_type`` as declared by ``plugin_id``.

        Re-registering the same class for the same plugin is idempotent; any
        other collision raises :class:`DuplicateTypeError`.
        """
        existing = self._by_name.get(event_type.__name__)
        if existing is not None and existing is not event_type:
            raise DuplicateTypeError(event_type, self._owners[existing], plugin_id)
        if existing is event_type:
            owner = self._owners[event_type]
            if owner != plugin_id:
                raise DuplicateTypeError(event_type, owner, plugin_id)
            return
        self._owners[event_type] = plugin_id
        self._by_name[event_type.__name__] = event_type

    def declaring_plugin(self, event_type: type) -> str:
        return self._owners[event_type]

    def all_types(self) -> dict[type, str]:
        return dict(self._owners)
