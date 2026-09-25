"""Plugin author API: the :class:`Plugin` base class and the declarative
``@consume`` / ``@reemit`` subscription decorators.

Decorators record intent on the handler function itself; :meth:`Plugin.subscriptions`
collects those marks per instance so the bus can wire routing without executing
any handler. The manifest remains the contract of record for scoping/priority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from kernel.bus import EventBus
    from kernel.manifest import Manifest

_CONSUMES_ATTR = "__kuestion_consumes__"
_REEMITS_ATTR = "__kuestion_reemits__"


@dataclass(frozen=True)
class ReEmitHandler:
    """A middleware callable together with its priority (lower runs first)."""

    handler: Callable[..., object]
    priority: int


@dataclass(frozen=True)
class Subscriptions:
    """Collected subscriptions of one plugin instance."""

    consumes: dict[type, list[Callable[..., None]]]
    reemits: dict[tuple[type, str | None], list[ReEmitHandler]]


def consume(event_type: type) -> Callable[[Callable[..., None]], Callable[..., None]]:
    """Decorator marking a handler as a consumer of ``event_type``."""

    def decorator(handler: Callable[..., None]) -> Callable[..., None]:
        marks = list(getattr(handler, _CONSUMES_ATTR, ()))
        marks.append(event_type)
        setattr(handler, _CONSUMES_ATTR, marks)
        return handler

    return decorator


def reemit(
    event_type: type,
    target_id: str | None = None,
    priority: int = 100,
) -> Callable[[Callable[..., object]], Callable[..., object]]:
    """Decorator marking a handler as re-emitting middleware for ``event_type``."""

    def decorator(handler: Callable[..., object]) -> Callable[..., object]:
        marks = list(getattr(handler, _REEMITS_ATTR, ()))
        marks.append((event_type, target_id, priority))
        setattr(handler, _REEMITS_ATTR, marks)
        return handler

    return decorator


class Plugin:
    """Base class for all plugins.

    ``manifest`` and ``bus`` are injected by the Loader after instantiation;
    they are not set in ``__init__`` so plugin constructors stay cheap and
    argument-free.
    """

    manifest: Manifest
    bus: EventBus

    def on_load(self) -> None:
        """Called after the plugin has been registered with the bus."""

    def on_unload(self) -> None:
        """Called before the plugin is unregistered from the bus."""

    def subscriptions(self) -> Subscriptions:
        """Collect the decorated handlers of this instance into routing maps."""
        consumes: dict[type, list[Callable[..., None]]] = {}
        reemits: dict[tuple[type, str | None], list[ReEmitHandler]] = {}

        for cls in reversed(type(self).__mro__):
            for name, member in vars(cls).items():
                if not callable(member):
                    continue
                handler: Any = getattr(self, name)
                for event_type in getattr(member, _CONSUMES_ATTR, ()):
                    consumes.setdefault(event_type, []).append(handler)
                for event_type, target_id, priority in getattr(member, _REEMITS_ATTR, ()):
                    reemits.setdefault((event_type, target_id), []).append(
                        ReEmitHandler(handler, priority)
                    )

        return Subscriptions(consumes=consumes, reemits=reemits)
