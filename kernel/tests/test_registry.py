"""Unit tests for the plugin type registry."""

import pytest

from kernel.registry import DuplicateTypeError, TypeRegistry


def make_type(name: str, module: str) -> type:
    return type(name, (), {"__module__": module})


def test_declaring_plugin_returns_the_owner() -> None:
    registry = TypeRegistry()
    event = make_type("Ping", "alpha.events")
    registry.register("kuestion.alpha", event)

    assert registry.declaring_plugin(event) == "kuestion.alpha"


def test_all_types_maps_each_type_to_its_owner() -> None:
    registry = TypeRegistry()
    event = make_type("Ping", "alpha.events")
    registry.register("kuestion.alpha", event)

    assert registry.all_types() == {event: "kuestion.alpha"}


def test_all_types_is_empty_for_a_fresh_registry() -> None:
    assert TypeRegistry().all_types() == {}


def test_all_types_keeps_multiple_types_of_one_plugin() -> None:
    registry = TypeRegistry()
    first = make_type("Ping", "alpha.events")
    second = make_type("Pong", "alpha.events")
    registry.register("kuestion.alpha", first)

    registry.register("kuestion.alpha", second)

    assert registry.all_types() == {first: "kuestion.alpha", second: "kuestion.alpha"}


def test_registering_the_same_class_for_the_same_plugin_twice_is_allowed() -> None:
    registry = TypeRegistry()
    event = make_type("Ping", "alpha.events")
    registry.register("kuestion.alpha", event)

    registry.register("kuestion.alpha", event)

    assert registry.declaring_plugin(event) == "kuestion.alpha"


def test_duplicate_class_name_from_another_plugin_is_rejected() -> None:
    registry = TypeRegistry()
    registry.register("kuestion.alpha", make_type("Ping", "alpha.events"))

    with pytest.raises(DuplicateTypeError) as info:
        registry.register("kuestion.beta", make_type("Ping", "beta.events"))

    assert (info.value.first_plugin, info.value.second_plugin) == ("kuestion.alpha", "kuestion.beta")


def test_same_class_object_redeclared_by_another_plugin_is_rejected() -> None:
    registry = TypeRegistry()
    event = make_type("Ping", "alpha.events")
    registry.register("kuestion.alpha", event)

    with pytest.raises(DuplicateTypeError) as info:
        registry.register("kuestion.beta", event)

    assert (info.value.first_plugin, info.value.second_plugin) == ("kuestion.alpha", "kuestion.beta")


def test_declaring_plugin_unknown_type_raises_keyerror() -> None:
    registry = TypeRegistry()

    with pytest.raises(KeyError):
        registry.declaring_plugin(make_type("Ping", "alpha.events"))
