"""Unit tests for Qt-free menu path parsing and registration."""

from __future__ import annotations

import pytest

from plugins.windowing.events import WidgetSpec
from plugins.windowing.src.menus import MenuModel, parse_menu_path


def test_parse_menu_path_splits_on_slashes() -> None:
    assert parse_menu_path("Tools/Export") == ["Tools", "Export"]


def test_parse_menu_path_ignores_empty_segments() -> None:
    assert parse_menu_path("/Tools//Export/") == ["Tools", "Export"]


def test_parse_menu_path_rejects_path_without_segments() -> None:
    with pytest.raises(ValueError):
        parse_menu_path("///")


def test_action_is_registered_under_its_path() -> None:
    model = MenuModel()

    model.add_action("Tools/Export", "tools.export", "Export…")

    actions = model.actions_for("Tools/Export")
    assert [(a.action_id, a.action_label) for a in actions] == [("tools.export", "Export…")]


def test_actions_for_unknown_path_is_empty() -> None:
    assert MenuModel().actions_for("Nope") == []


def test_actions_under_same_path_accumulate() -> None:
    model = MenuModel()
    model.add_action("Tools", "tools.a", "A")
    model.add_action("Tools", "tools.b", "B")

    assert [a.action_id for a in model.actions_for("Tools")] == ["tools.a", "tools.b"]


def test_tree_nests_menus_by_path_segments() -> None:
    model = MenuModel()
    model.add_action("Tools/Export", "tools.export", "Export…")

    node = model.tree()
    assert node["Tools"]["Export"][0].action_id == "tools.export"


def test_action_builds_activated_event_payload() -> None:
    model = MenuModel()
    model.add_action("Tools/Export", "tools.export", "Export…")

    event = model.actions_for("Tools/Export")[0].to_event()

    assert (event.action_id, event.action_label) == ("tools.export", "Export…")


def test_dialog_is_registered_under_its_path() -> None:
    model = MenuModel()
    spec = WidgetSpec(spec={"kind": "label"})

    model.add_dialog("Settings/Models", "keyregistry.models", "Models", spec)

    binding = model.dialog("keyregistry.models")
    assert binding is not None
    assert (binding.title, binding.widget_spec) == ("Models", spec)


def test_dialog_label_is_derived_from_menu_path() -> None:
    model = MenuModel()

    model.add_dialog("View/Plugins…", "windowing.plugins", "Plugins", WidgetSpec())

    assert model.tree()["View"]["Plugins…"][0].action_label == "Plugins…"


def test_actions_for_excludes_dialogs() -> None:
    model = MenuModel()
    model.add_dialog("View/Plugins…", "windowing.plugins", "Plugins", WidgetSpec())

    assert model.actions_for("View/Plugins…") == []


def test_dialog_for_unknown_action_is_none() -> None:
    assert MenuModel().dialog("nope") is None


def test_remove_owned_by_drops_that_owners_items() -> None:
    model = MenuModel()
    model.add_action("Tools/Export", "tools.export", "Export…", owner="a")
    model.add_dialog("Settings/Models", "models", "Models", WidgetSpec(), owner="b")

    model.remove_owned_by("a")

    assert model.actions_for("Tools/Export") == []
    assert model.dialog("models") is not None


def test_remove_owned_by_keeps_other_owners_items() -> None:
    model = MenuModel()
    model.add_action("Tools/A", "tools.a", "A", owner="a")
    model.add_action("Tools/B", "tools.b", "B", owner="b")

    model.remove_owned_by("a")

    assert [action.action_id for action in model.actions_for("Tools/B")] == ["tools.b"]
