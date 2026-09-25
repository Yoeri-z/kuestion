"""Unit tests for the plugin manifest contract and validation."""

from dataclasses import dataclass

from kernel.manifest import Consume, Manifest, ReEmit, validate_manifest


@dataclass
class Alpha:
    value: int = 0


@dataclass
class Beta:
    value: int = 0


def make_manifest(**overrides: object) -> Manifest:
    base = {"id": "kuestion.demo", "entry": "plugin:DemoPlugin"}
    return Manifest(**(base | overrides))


def test_valid_manifest_produces_no_errors() -> None:
    manifest = make_manifest(
        emits=(Alpha,),
        consumes=(Consume(event_type=Alpha),),
        reemits=(ReEmit(event_type=Beta),),
        requires=("kuestion.other",),
    )

    assert validate_manifest(manifest) == []


def test_id_without_dot_is_rejected() -> None:
    errors = validate_manifest(make_manifest(id="demo"))

    assert errors == ["invalid id: 'demo' must be a dotted lower_snake identifier"]


def test_id_starting_with_uppercase_is_rejected() -> None:
    errors = validate_manifest(make_manifest(id="Kuestion.demo"))

    assert errors == ["invalid id: 'Kuestion.demo' must be a dotted lower_snake identifier"]


def test_entry_without_colon_is_rejected() -> None:
    errors = validate_manifest(make_manifest(entry="plugin.DemoPlugin"))

    assert errors == ["invalid entry: 'plugin.DemoPlugin' must match 'module.path:ClassName'"]


def test_entry_with_dotted_module_is_accepted() -> None:
    errors = validate_manifest(make_manifest(entry="pkg.plugin:DemoPlugin"))

    assert errors == []


def test_non_class_in_emits_is_rejected() -> None:
    errors = validate_manifest(make_manifest(emits=(42,)))

    assert errors == ["emits contains non-class event type: 42"]


def test_non_class_event_type_in_consumes_is_rejected() -> None:
    errors = validate_manifest(make_manifest(consumes=(Consume(event_type=42),)))

    assert errors == ["consumes contains non-class event type: 42"]


def test_non_class_event_type_in_reemits_is_rejected() -> None:
    errors = validate_manifest(make_manifest(reemits=(ReEmit(event_type=42),)))

    assert errors == ["reemits contains non-class event type: 42"]


def test_duplicate_emits_is_rejected() -> None:
    errors = validate_manifest(make_manifest(emits=(Alpha, Alpha)))

    assert errors == ["duplicate emits entry"]


def test_duplicate_consumes_is_rejected() -> None:
    errors = validate_manifest(
        make_manifest(consumes=(Consume(event_type=Alpha), Consume(event_type=Alpha)))
    )

    assert errors == ["duplicate consumes entry"]


def test_duplicate_reemits_is_rejected() -> None:
    errors = validate_manifest(
        make_manifest(reemits=(ReEmit(event_type=Alpha), ReEmit(event_type=Alpha)))
    )

    assert errors == ["duplicate reemits entry"]


def test_reemits_with_distinct_scopes_are_allowed() -> None:
    reemits = (
        ReEmit(event_type=Alpha),
        ReEmit(event_type=Alpha, target_id="kuestion.other"),
        ReEmit(event_type=Alpha, priority=1),
    )

    assert validate_manifest(make_manifest(reemits=reemits)) == []


def test_self_require_is_rejected() -> None:
    errors = validate_manifest(make_manifest(requires=("kuestion.demo",)))

    assert errors == ["requires must not include the plugin's own id: 'kuestion.demo'"]
