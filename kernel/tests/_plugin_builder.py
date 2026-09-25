"""Helpers to build throwaway on-disk plugin packages for kernel tests."""

from __future__ import annotations

from pathlib import Path

KERNEL_MANIFEST_IMPORTS = "from kernel.manifest import Consume, Manifest, ReEmit"


def _tuple_source(items: tuple[str, ...]) -> str:
    if not items:
        return "()"
    if len(items) == 1:
        return f"({items[0]},)"
    return "(" + ", ".join(items) + ")"


def build_plugin(
    root: Path,
    package: str,
    *,
    plugin_id: str,
    events_source: str = "",
    imports: str = "",
    emits: tuple[str, ...] = (),
    consumes: tuple[str, ...] = (),
    reemits: tuple[tuple[str, str | None, int], ...] = (),
    requires: tuple[str, ...] = (),
    pip_deps: tuple[str, ...] = (),
    manifest_source: str | None = None,
    plugin_source: str | None = None,
) -> Path:
    """Write a plugin directory with ``events.py``, ``manifest.py`` and an
    optional ``plugin.py``."""
    directory = root / package
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "__init__.py").write_text("")
    (directory / "events.py").write_text(events_source)

    if manifest_source is None:
        consume_exprs = tuple(f"Consume(event_type={name})" for name in consumes)
        reemit_exprs = tuple(
            f"ReEmit(event_type={name}, target_id={target!r}, priority={priority})"
            for name, target, priority in reemits
        )
        manifest_source = "\n".join(
            [
                KERNEL_MANIFEST_IMPORTS,
                imports,
                "",
                "MANIFEST = Manifest(",
                f"    id={plugin_id!r},",
                "    entry='plugin:DemoPlugin',",
                f"    emits={_tuple_source(emits)},",
                f"    consumes={_tuple_source(consume_exprs)},",
                f"    reemits={_tuple_source(reemit_exprs)},",
                f"    requires={requires!r},",
                f"    pip_deps={pip_deps!r},",
                ")",
            ]
        )

    (directory / "manifest.py").write_text(manifest_source + "\n")
    if plugin_source is not None:
        (directory / "plugin.py").write_text(plugin_source)
    return directory


def demo_plugin_source(event_type: str, *, events_module: str = ".events") -> str:
    """Source for a ``DemoPlugin`` recording lifecycle, instances and received
    events into module-level lists."""
    lines = [
        "from kernel.plugin import Plugin, consume",
        f"from {events_module} import {event_type}",
        "",
        "LOADED = []",
        "UNLOADED = []",
        "RECEIVED = []",
        "INSTANCES = []",
        "",
        "class DemoPlugin(Plugin):",
        f"    @consume({event_type})",
        "    def handle(self, event):",
        "        RECEIVED.append(event.payload)",
        "",
        "    def on_load(self):",
        "        LOADED.append(1)",
        "        INSTANCES.append(self)",
        "",
        "    def on_unload(self):",
        "        UNLOADED.append(1)",
        "",
    ]
    return "\n".join(lines)


PING_EVENTS = "class Ping:\n    pass\n"

EMPTY_PLUGIN_SOURCE = (
    "from kernel.plugin import Plugin\n\n\nclass DemoPlugin(Plugin):\n    pass\n"
)


def build_ping_chain(root: Path) -> None:
    """Write ``alpha <- beta <- gamma``; alpha declares ``Ping``, the
    dependents import it (types are declared once)."""
    build_plugin(
        root,
        "alpha",
        plugin_id="kuestion.alpha",
        events_source=PING_EVENTS,
        imports="from .events import Ping",
        consumes=("Ping",),
        plugin_source=demo_plugin_source("Ping"),
    )
    build_plugin(
        root,
        "beta",
        plugin_id="kuestion.beta",
        imports="from plugins.alpha.events import Ping",
        consumes=("Ping",),
        requires=("kuestion.alpha",),
        plugin_source=demo_plugin_source("Ping", events_module="plugins.alpha.events"),
    )
    build_plugin(
        root,
        "gamma",
        plugin_id="kuestion.gamma",
        imports="from plugins.alpha.events import Ping",
        consumes=("Ping",),
        requires=("kuestion.beta",),
        plugin_source=demo_plugin_source("Ping", events_module="plugins.alpha.events"),
    )
