"""Plugin discovery and validation-before-load.

The Loader parses only the contract surface (``manifest.py`` + ``events.py``) of
each plugin, validates it, and resolves a load order without ever importing the
implementation module ``plugin.py``. Under the chosen import model a plugin's
**search directory is an implicit namespace package** (named ``plugins`` in
production), so a plugin imports as ``plugins.<directory-name>`` — the manifest
``id`` remains the logical bus/routing identity.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import traceback
from bisect import insort
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from kernel.envelope import Event
from kernel.events import KERNEL_ID, PluginLoadFailed, PluginLoaded
from kernel.manifest import Manifest, validate_manifest
from kernel.plugin import Plugin
from kernel.registry import DuplicateTypeError, TypeRegistry

if TYPE_CHECKING:
    from kernel.bus import EventBus
    from kernel.tracker import Tracker


@dataclass(frozen=True)
class LoadError:
    """A plugin that failed validation, before any instance exists."""

    plugin_id: str
    stage: str
    error: str


@dataclass(frozen=True)
class LoadResult:
    """Outcome of loading/validating a single plugin."""

    plugin_id: str
    ok: bool
    stage: str
    error: str | None = None


@dataclass(frozen=True)
class LoadSummary:
    """Outcome of :meth:`Loader.load_all`."""

    loaded: tuple[str, ...]
    failed: tuple[LoadResult, ...]


class Loader:
    """Discovers, validates, and orders plugins before instantiating them."""

    def __init__(
        self,
        search_dirs: list[Path],
        registry: TypeRegistry,
        on_warning: Callable[[str], None] | None = None,
    ) -> None:
        self._search_dirs = [Path(directory) for directory in search_dirs]
        self._registry = registry
        self._on_warning = on_warning
        self.warnings: list[str] = []
        self.failures: dict[str, LoadResult] = {}
        self._packages: dict[str, str] = {}  # plugin id -> top-level package name
        self._manifests: dict[str, Manifest] = {}
        self._order: list[str] = []
        self._add_to_sys_path()

    # -- discovery ---------------------------------------------------------

    def discover(self) -> dict[str, Path]:
        """Return ``{import_name: directory}`` for every plugin directory found.

        A plugin's import name is ``"<search-dir-name>.<package>"``: the search
        directory acts as an implicit namespace package (named ``plugins`` in
        production), so built-in and user plugins share a single namespace
        instead of exposing every plugin as a top-level module.

        Later search directories (e.g. the user directory) take precedence over
        earlier ones for the same package name.
        """
        candidates: dict[str, tuple[int, Path, str]] = {}
        overridden: list[tuple[str, Path]] = []
        for index, search_dir in enumerate(self._search_dirs):
            if not search_dir.is_dir():
                continue
            for child in sorted(search_dir.iterdir()):
                if not (child.is_dir() and (child / "manifest.py").is_file()):
                    continue
                if child.name in candidates:
                    overridden.append((child.name, candidates[child.name][1]))
                candidates[child.name] = (index, child, f"{search_dir.name}.{child.name}")

        for package, lost_path in overridden:
            self._warn(
                f"plugin package '{package}' from {lost_path} is overridden by "
                f"{candidates[package][1]}"
            )

        return {import_name: child for _, child, import_name in candidates.values()}

    # -- manifest parsing --------------------------------------------------

    def parse_manifests(self, paths: dict[str, Path]) -> dict[str, Manifest | LoadError]:
        """Import each plugin's ``manifest.py`` and validate it.

        Only the contract surface is imported; ``plugin.py`` is never touched.
        Successful results are keyed by manifest id, failures by import name.
        """
        parsed: dict[str, Manifest | LoadError] = {}
        for package, _directory in paths.items():
            try:
                module = importlib.import_module(f"{package}.manifest")
            except Exception:  # noqa: BLE001 - report any import-time failure
                parsed[package] = LoadError(package, "manifest", traceback.format_exc())
                continue

            manifest = getattr(module, "MANIFEST", None)
            if manifest is None:
                parsed[package] = LoadError(package, "manifest", "missing MANIFEST constant")
                continue

            errors = validate_manifest(manifest)
            if errors:
                parsed[package] = LoadError(package, "manifest", "; ".join(errors))
                continue

            self._packages[manifest.id] = package
            parsed[package] = manifest
        return parsed

    # -- dependency ordering -----------------------------------------------

    def resolve_order(self, manifests: dict[str, Manifest]) -> tuple[list[str], list[str]]:
        """Topologically order plugins by ``requires``.

        Returns ``(ordered_ids, failed_ids)``. Missing requirements, dependency
        cycles, and plugins depending on either are recorded as ``deps`` failures.
        Ties are broken alphabetically for deterministic output.
        """
        manifests = dict(manifests)
        ids = set(manifests)
        dep_failures: dict[str, str] = {}

        for plugin_id, manifest in manifests.items():
            for dependency in manifest.requires:
                if dependency not in ids:
                    dep_failures[plugin_id] = (
                        f"requires '{dependency}' which is not installed"
                    )
                    break

        self._cascade(manifests, dep_failures)

        remaining = {plugin_id for plugin_id in ids if plugin_id not in dep_failures}
        for component in self._cyclic_components(manifests, remaining):
            members = ", ".join(sorted(component))
            for plugin_id in component:
                dep_failures[plugin_id] = f"dependency cycle: {members}"

        self._cascade(manifests, dep_failures)

        successful = {plugin_id for plugin_id in ids if plugin_id not in dep_failures}
        ordered = self._topological_order(successful, manifests)

        for plugin_id, error in dep_failures.items():
            self.failures[plugin_id] = LoadResult(plugin_id, False, "deps", error)
        return ordered, sorted(dep_failures)

    # -- type / pip checks -------------------------------------------------

    def check_types(
        self, ordered: list[str], manifests: dict[str, Manifest]
    ) -> list[LoadResult]:
        """Register each plugin's own declared types, in load order.

        Types that live in another plugin's ``events.py`` are imports and are
        skipped here (their owner already registered them).
        """
        results: list[LoadResult] = []
        for plugin_id in ordered:
            manifest = manifests[plugin_id]
            namespace = self._packages.get(plugin_id, plugin_id)
            result = LoadResult(plugin_id, True, "", None)
            for event_type in self._declared_types(manifest):
                if not self._is_own_type(namespace, event_type):
                    continue
                try:
                    self._registry.register(plugin_id, event_type)
                except DuplicateTypeError as exc:
                    result = LoadResult(plugin_id, False, "types", str(exc))
                    break
            results.append(result)
            if not result.ok:
                self.failures[plugin_id] = result
        return results

    def check_pip_deps(self, manifests: dict[str, Manifest]) -> list[LoadResult]:
        """Verify every declared pip dependency is importable."""
        results: list[LoadResult] = []
        for plugin_id, manifest in manifests.items():
            result = LoadResult(plugin_id, True, "", None)
            for dependency in manifest.pip_deps:
                if not self._is_importable(dependency):
                    result = LoadResult(
                        plugin_id,
                        False,
                        "pip",
                        f"missing package '{dependency}' — run pip install {dependency}",
                    )
                    break
            results.append(result)
            if not result.ok:
                self.failures[plugin_id] = result
        return results

    # -- aggregate ---------------------------------------------------------

    def validate(self) -> list[LoadResult]:
        """Run the full validation pipeline and return a result per plugin."""
        self.failures = {}
        self._packages = {}

        parsed = self.parse_manifests(self.discover())
        manifests: dict[str, Manifest] = {}
        for value in parsed.values():
            if isinstance(value, LoadError):
                self.failures[value.plugin_id] = LoadResult(
                    value.plugin_id, False, value.stage, value.error
                )
            else:
                manifests[value.id] = value

        ordered, _ = self.resolve_order(manifests)
        self._manifests = manifests
        self._order = ordered
        for result in self.check_types(ordered, manifests):
            if not result.ok:
                self.failures[result.plugin_id] = result
        for result in self.check_pip_deps(manifests):
            if not result.ok:
                self.failures[result.plugin_id] = result

        results = [self.failures[plugin_id] for plugin_id in sorted(self.failures)]
        results.extend(
            LoadResult(plugin_id, True, "", None)
            for plugin_id in ordered
            if plugin_id not in self.failures
        )
        return results

    # -- instantiation -----------------------------------------------------

    def load_all(self, bus: EventBus, tracker: Tracker) -> LoadSummary:
        """Validate, then import and instantiate every passing plugin in order.

        One plugin's failure never blocks the rest. ``PluginLoaded`` and
        ``PluginLoadFailed`` lifecycle events are published on ``bus``.
        """
        self.validate()
        loaded: list[str] = []
        for plugin_id in self._order:
            result = self._load_one(plugin_id, self._manifests[plugin_id], bus, tracker)
            if result.ok:
                loaded.append(plugin_id)
            else:
                self.failures[plugin_id] = result

        for plugin_id in sorted(self.failures):
            failure = self.failures[plugin_id]
            self._emit(
                bus,
                PluginLoadFailed,
                PluginLoadFailed(plugin_id, failure.error or "", failure.stage),
            )
        return LoadSummary(
            loaded=tuple(loaded),
            failed=tuple(self.failures[plugin_id] for plugin_id in sorted(self.failures)),
        )

    def _load_one(
        self, plugin_id: str, manifest: Manifest, bus: EventBus, tracker: Tracker
    ) -> LoadResult:
        package = self._packages.get(plugin_id, plugin_id)
        module_name, _, class_name = manifest.entry.partition(":")
        try:
            module = importlib.import_module(f"{package}.{module_name}")
        except Exception:  # noqa: BLE001 - report any import-time failure
            return LoadResult(plugin_id, False, "entry", traceback.format_exc())

        plugin_class = getattr(module, class_name, None)
        if plugin_class is None:
            return LoadResult(
                plugin_id,
                False,
                "entry",
                f"entry class '{class_name}' not found in {package}.{module_name}",
            )

        try:
            plugin = plugin_class()
        except Exception:  # noqa: BLE001 - report constructor failure
            return LoadResult(plugin_id, False, "entry", traceback.format_exc())

        plugin.manifest = manifest
        mismatch = self._check_subscriptions(plugin)
        if mismatch is not None:
            return LoadResult(plugin_id, False, "entry", mismatch)

        bus.register(plugin)
        tracker.add(plugin)
        try:
            plugin.on_load()
        except Exception:  # noqa: BLE001 - boundary: surface, roll back, keep going
            tracker.remove(plugin_id)
            bus.unregister(plugin_id)
            return LoadResult(plugin_id, False, "entry", traceback.format_exc())

        self._emit(bus, PluginLoaded, PluginLoaded(plugin_id))
        return LoadResult(plugin_id, True, "", None)

    def _check_subscriptions(self, plugin: Plugin) -> str | None:
        subscriptions = plugin.subscriptions()
        declared_consumes = {entry.event_type for entry in plugin.manifest.consumes}
        for event_type in subscriptions.consumes:
            if event_type not in declared_consumes:
                return f"handler consumes {event_type.__name__} which the manifest does not declare"
        declared_reemits = {(entry.event_type, entry.target_id) for entry in plugin.manifest.reemits}
        for event_type, target_id in subscriptions.reemits:
            if (event_type, target_id) not in declared_reemits:
                return (
                    f"re-emit handler for {event_type.__name__} (target={target_id!r}) "
                    "which the manifest does not declare"
                )
        return None

    def _emit(self, bus: EventBus, event_type: type, payload: object) -> None:
        bus.emit(Event(event_type=event_type, payload=payload, sender_id=KERNEL_ID))

    # -- internals ---------------------------------------------------------

    def _add_to_sys_path(self) -> None:
        """Put each search directory's *parent* on ``sys.path`` so that the
        search directory resolves as an implicit namespace package.

        Parents are inserted so later search directories come first: the user
        directory then shadows a built-in of the same package name, both in
        discovery and when Python resolves ``plugins.<package>``.
        """
        parents: list[str] = []
        for search_dir in self._search_dirs:
            parent = str(search_dir.parent)
            if parent not in parents:
                parents.append(parent)
        for parent in parents:
            while parent in sys.path:
                sys.path.remove(parent)
        for parent in parents:
            sys.path.insert(0, parent)

    def _warn(self, message: str) -> None:
        self.warnings.append(message)
        if self._on_warning is not None:
            self._on_warning(message)

    def _cascade(self, manifests: dict[str, Manifest], failures: dict[str, str]) -> None:
        changed = True
        while changed:
            changed = False
            for plugin_id, manifest in manifests.items():
                if plugin_id in failures:
                    continue
                for dependency in manifest.requires:
                    if dependency in failures:
                        failures[plugin_id] = (
                            f"requires '{dependency}' which failed to load"
                        )
                        changed = True
                        break

    def _cyclic_components(
        self, manifests: dict[str, Manifest], remaining: set[str]
    ) -> list[list[str]]:
        index: dict[str, int] = {}
        low: dict[str, int] = {}
        on_stack: dict[str, bool] = {}
        stack: list[str] = []
        components: list[list[str]] = []
        counter = [0]

        def strongconnect(node: str) -> None:
            index[node] = low[node] = counter[0]
            counter[0] += 1
            stack.append(node)
            on_stack[node] = True
            for neighbour in manifests[node].requires:
                if neighbour not in remaining:
                    continue
                if neighbour not in index:
                    strongconnect(neighbour)
                    low[node] = min(low[node], low[neighbour])
                elif on_stack.get(neighbour):
                    low[node] = min(low[node], index[neighbour])
            if low[node] == index[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack[member] = False
                    component.append(member)
                    if member == node:
                        break
                components.append(component)

        for node in sorted(remaining):
            if node not in index:
                strongconnect(node)

        return [component for component in components if len(component) > 1]

    def _topological_order(
        self, successful: set[str], manifests: dict[str, Manifest]
    ) -> list[str]:
        pending = {
            plugin_id: sum(
                1 for dependency in manifests[plugin_id].requires if dependency in successful
            )
            for plugin_id in successful
        }
        dependents: dict[str, list[str]] = {plugin_id: [] for plugin_id in successful}
        for plugin_id in successful:
            for dependency in manifests[plugin_id].requires:
                if dependency in successful:
                    dependents[dependency].append(plugin_id)

        ready = sorted(plugin_id for plugin_id in successful if pending[plugin_id] == 0)
        ordered: list[str] = []
        while ready:
            plugin_id = ready.pop(0)
            ordered.append(plugin_id)
            for dependent in sorted(dependents[plugin_id]):
                pending[dependent] -= 1
                if pending[dependent] == 0:
                    insort(ready, dependent)
        return ordered

    def _declared_types(self, manifest: Manifest) -> list[type]:
        declared = [
            *manifest.emits,
            *(consume.event_type for consume in manifest.consumes),
            *(reemit.event_type for reemit in manifest.reemits),
        ]
        return list(dict.fromkeys(declared))

    def _is_own_type(self, namespace: str, event_type: type) -> bool:
        module = getattr(event_type, "__module__", "")
        return module == namespace or module.startswith(f"{namespace}.")

    def _is_importable(self, name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            return False
