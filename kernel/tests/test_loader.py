"""Unit tests for plugin discovery, manifest parsing, dependency ordering,
type checking, and pip-dependency checking.

Note: the Loader puts each search directory's parent on ``sys.path`` so the
search directory acts as an implicit namespace package; plugin packages (and
cross-plugin imports such as ``from plugins.alpha.events import ...``) resolve
under that namespace.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from kernel.bus import EventBus
from kernel.loader import Loader
from kernel.manifest import Manifest
from kernel.registry import TypeRegistry
from kernel.tests._plugin_builder import (
    PING_EVENTS,
    build_plugin,
    demo_plugin_source,
)
from kernel.tracker import Tracker


@pytest.fixture(autouse=True)
def _restore_import_state() -> Iterator[None]:
    """Keep plugin modules, sys.path, and import caches local to each test."""
    modules_before = set(sys.modules)
    path_before = list(sys.path)
    yield
    for name in set(sys.modules) - modules_before:
        del sys.modules[name]
    sys.path[:] = path_before
    importlib.invalidate_caches()


@pytest.fixture
def bus() -> Iterator[EventBus]:
    instance = EventBus(TypeRegistry())
    instance.start()
    yield instance
    instance.stop()


def build_plugins(root: Path, specs: tuple[tuple[str, str], ...]) -> None:
    for package, plugin_id in specs:
        build_plugin(root, package, plugin_id=plugin_id)


def parse_all_manifests(loader: Loader) -> dict[str, Manifest]:
    parsed = loader.parse_manifests(loader.discover())
    return {value.id: value for value in parsed.values() if isinstance(value, Manifest)}


SHARED_TYPE_SOURCE = "class Shared:\n    pass\n"


def test_discovers_plugins_across_search_dirs(tmp_path: Path) -> None:
    builtins = tmp_path / "builtin" / "plugins"
    user = tmp_path / "user" / "plugins"
    build_plugin(builtins, "alpha", plugin_id="kuestion.alpha")
    build_plugin(user, "beta", plugin_id="kuestion.beta")

    discovered = Loader([builtins, user], TypeRegistry()).discover()

    assert set(discovered) == {"plugins.alpha", "plugins.beta"}


def test_ignores_directory_without_manifest(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    (root / "notaplugin").mkdir(parents=True)
    (root / "notaplugin" / "events.py").write_text("")

    assert Loader([root], TypeRegistry()).discover() == {}


def test_user_directory_overrides_builtin_package(tmp_path: Path) -> None:
    builtins = tmp_path / "builtin" / "plugins"
    user = tmp_path / "user" / "plugins"
    build_plugin(builtins, "alpha", plugin_id="kuestion.alpha")
    build_plugin(user, "alpha", plugin_id="kuestion.alpha")

    discovered = Loader([builtins, user], TypeRegistry()).discover()

    assert discovered["plugins.alpha"] == user / "alpha"


def test_user_directory_override_records_a_warning(tmp_path: Path) -> None:
    builtins = tmp_path / "builtin" / "plugins"
    user = tmp_path / "user" / "plugins"
    build_plugin(builtins, "alpha", plugin_id="kuestion.alpha")
    build_plugin(user, "alpha", plugin_id="kuestion.alpha")
    loader = Loader([builtins, user], TypeRegistry())

    loader.discover()

    assert any("alpha" in warning for warning in loader.warnings)


def test_plugins_in_different_search_dirs_share_one_namespace(
    tmp_path: Path, bus: EventBus
) -> None:
    builtins = tmp_path / "builtin" / "plugins"
    user = tmp_path / "user" / "plugins"
    build_plugin(
        builtins,
        "alpha",
        plugin_id="kuestion.alpha",
        events_source=PING_EVENTS,
        imports="from .events import Ping",
        consumes=("Ping",),
        plugin_source=demo_plugin_source("Ping"),
    )
    build_plugin(
        user,
        "beta",
        plugin_id="kuestion.beta",
        imports="from plugins.alpha.events import Ping",
        consumes=("Ping",),
        requires=("kuestion.alpha",),
        plugin_source=demo_plugin_source("Ping", events_module="plugins.alpha.events"),
    )
    loader = Loader([builtins, user], TypeRegistry())

    summary = loader.load_all(bus, Tracker(bus))

    assert summary.loaded == ("kuestion.alpha", "kuestion.beta")
    assert summary.failed == ()


def test_user_directory_override_wins_at_import_time(tmp_path: Path) -> None:
    builtins = tmp_path / "builtin" / "plugins"
    user = tmp_path / "user" / "plugins"
    build_plugin(builtins, "alpha", plugin_id="kuestion.alpha", events_source="VERSION = 'builtin'\n")
    build_plugin(user, "alpha", plugin_id="kuestion.alpha", events_source="VERSION = 'user'\n")
    loader = Loader([builtins, user], TypeRegistry())
    loader.discover()

    events = importlib.import_module("plugins.alpha.events")

    assert events.VERSION == "user"


def test_valid_manifest_parses(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    build_plugin(root, "alpha", plugin_id="kuestion.alpha")
    loader = Loader([root], TypeRegistry())

    parsed = loader.parse_manifests(loader.discover())

    assert isinstance(parsed["plugins.alpha"], Manifest)


def test_missing_manifest_constant_fails_at_manifest_stage(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    build_plugin(root, "alpha", plugin_id="kuestion.alpha", manifest_source="VALUE = 1")
    loader = Loader([root], TypeRegistry())

    result = loader.parse_manifests(loader.discover())["plugins.alpha"]

    assert (result.stage, result.error) == ("manifest", "missing MANIFEST constant")


def test_syntax_error_in_manifest_fails_at_manifest_stage(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    build_plugin(root, "alpha", plugin_id="kuestion.alpha", manifest_source="MANIFEST = (")
    loader = Loader([root], TypeRegistry())

    result = loader.parse_manifests(loader.discover())["plugins.alpha"]

    assert result.stage == "manifest"


def test_invalid_manifest_id_fails_at_manifest_stage(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    build_plugin(root, "alpha", plugin_id="invalid")
    loader = Loader([root], TypeRegistry())

    result = loader.parse_manifests(loader.discover())["plugins.alpha"]

    assert result.stage == "manifest"


def test_linear_chain_orders_dependencies_first(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    build_plugin(root, "alpha", plugin_id="kuestion.alpha")
    build_plugin(root, "beta", plugin_id="kuestion.beta", requires=("kuestion.alpha",))
    build_plugin(root, "gamma", plugin_id="kuestion.gamma", requires=("kuestion.beta",))
    loader = Loader([root], TypeRegistry())

    ordered, _ = loader.resolve_order(parse_all_manifests(loader))

    assert ordered == ["kuestion.alpha", "kuestion.beta", "kuestion.gamma"]


def test_missing_requirement_fails_at_deps_stage(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    build_plugin(root, "beta", plugin_id="kuestion.beta", requires=("kuestion.missing",))
    loader = Loader([root], TypeRegistry())

    _, failed = loader.resolve_order(parse_all_manifests(loader))

    assert failed == ["kuestion.beta"]
    assert "which is not installed" in loader.failures["kuestion.beta"].error


def test_cycle_fails_members_and_cascades_to_dependents(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    build_plugin(root, "alpha", plugin_id="kuestion.alpha", requires=("kuestion.beta",))
    build_plugin(root, "beta", plugin_id="kuestion.beta", requires=("kuestion.alpha",))
    build_plugin(root, "gamma", plugin_id="kuestion.gamma", requires=("kuestion.alpha",))
    loader = Loader([root], TypeRegistry())

    _, failed = loader.resolve_order(parse_all_manifests(loader))

    assert set(failed) == {"kuestion.alpha", "kuestion.beta", "kuestion.gamma"}
    assert "cycle" in loader.failures["kuestion.alpha"].error


def test_independent_plugins_are_ordered_alphabetically(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    specs = (("charlie", "kuestion.charlie"), ("alpha", "kuestion.alpha"), ("bravo", "kuestion.bravo"))
    build_plugins(root, specs)
    loader = Loader([root], TypeRegistry())

    ordered, _ = loader.resolve_order(parse_all_manifests(loader))

    assert ordered == ["kuestion.alpha", "kuestion.bravo", "kuestion.charlie"]


def test_duplicate_type_name_fails_the_second_plugin(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    build_plugin(root, "alpha", plugin_id="kuestion.alpha", events_source=SHARED_TYPE_SOURCE, imports="from .events import Shared", emits=("Shared",))
    build_plugin(root, "beta", plugin_id="kuestion.beta", events_source=SHARED_TYPE_SOURCE, imports="from .events import Shared", emits=("Shared",))
    loader = Loader([root], TypeRegistry())
    manifests = parse_all_manifests(loader)
    ordered, _ = loader.resolve_order(manifests)

    results = loader.check_types(ordered, manifests)

    failed = {result.plugin_id: result for result in results if not result.ok}
    assert set(failed) == {"kuestion.beta"}
    assert "kuestion.alpha" in failed["kuestion.beta"].error


def test_importing_another_plugins_type_is_not_a_duplicate(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    build_plugin(root, "alpha", plugin_id="kuestion.alpha", events_source=SHARED_TYPE_SOURCE, imports="from .events import Shared", emits=("Shared",))
    build_plugin(root, "beta", plugin_id="kuestion.beta", imports="from plugins.alpha.events import Shared", emits=("Shared",), requires=("kuestion.alpha",))
    loader = Loader([root], TypeRegistry())
    manifests = parse_all_manifests(loader)
    ordered, _ = loader.resolve_order(manifests)

    results = loader.check_types(ordered, manifests)

    assert all(result.ok for result in results)


def test_types_declared_in_consumes_are_registered(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    registry = TypeRegistry()
    build_plugin(root, "alpha", plugin_id="kuestion.alpha", events_source=SHARED_TYPE_SOURCE, imports="from .events import Shared", consumes=("Shared",))
    loader = Loader([root], registry)
    manifests = parse_all_manifests(loader)
    ordered, _ = loader.resolve_order(manifests)

    loader.check_types(ordered, manifests)

    assert list(registry.all_types().values()) == ["kuestion.alpha"]


def test_missing_pip_dependency_fails_with_install_hint(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    build_plugin(root, "alpha", plugin_id="kuestion.alpha", pip_deps=("kuestion_missing_package_xyz",))
    loader = Loader([root], TypeRegistry())

    results = loader.check_pip_deps(parse_all_manifests(loader))

    assert results[0].stage == "pip"
    assert "pip install kuestion_missing_package_xyz" in results[0].error


def test_installed_pip_dependency_passes(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    build_plugin(root, "alpha", plugin_id="kuestion.alpha", pip_deps=("pytest",))
    loader = Loader([root], TypeRegistry())

    results = loader.check_pip_deps(parse_all_manifests(loader))

    assert results[0].ok


def test_plugin_implementation_is_not_imported_during_validation(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    sentinel = tmp_path / "executed"
    directory = build_plugin(root, "alpha", plugin_id="kuestion.alpha")
    (directory / "plugin.py").write_text(f"open({str(sentinel)!r}, 'w').close()\n")
    loader = Loader([root], TypeRegistry())

    results = loader.validate()

    assert [result.plugin_id for result in results if result.ok] == ["kuestion.alpha"]
    assert not sentinel.exists()
