"""Unit tests for the Qt-free dock workspace model."""

from __future__ import annotations

import pytest

from plugins.windowing.src.workspace import WorkspaceModel


def test_add_panel_records_title_and_default_area() -> None:
    model = WorkspaceModel()

    model.add("plugins", "Plugins")

    entry = model.get("plugins")
    assert entry is not None
    assert (entry.title, entry.area) == ("Plugins", "right")


def test_panels_are_sorted_by_panel_id() -> None:
    model = WorkspaceModel()
    model.add("zeta", "Zeta")
    model.add("alpha", "Alpha")

    assert [entry.panel_id for entry in model.panels()] == ["alpha", "zeta"]


def test_first_centered_panel_wins_and_later_requests_become_docks() -> None:
    model = WorkspaceModel()
    model.add("chat", "Chat", center=True)

    model.add("other", "Other", center=True)

    assert model.central_id() == "chat"
    assert model.get("other").center is False


def test_removing_central_panel_clears_central_id() -> None:
    model = WorkspaceModel()
    model.add("chat", "Chat", center=True)

    model.remove("chat")

    assert model.central_id() is None


def test_get_unknown_panel_is_none() -> None:
    assert WorkspaceModel().get("missing") is None


def test_owned_by_returns_that_owners_panels() -> None:
    model = WorkspaceModel()
    model.add("chat", "Chat", owner="kuestion.chat")
    model.add("models", "Models", owner="kuestion.keyregistry")

    assert model.owned_by("kuestion.chat") == ["chat"]


def test_owned_by_unknown_owner_is_empty() -> None:
    assert WorkspaceModel().owned_by("nope") == []


def test_remove_owned_by_removes_only_that_owners_panels() -> None:
    model = WorkspaceModel()
    model.add("chat", "Chat", owner="kuestion.chat")
    model.add("models", "Models", owner="kuestion.keyregistry")

    model.remove_owned_by("kuestion.chat")

    assert model.get("chat") is None
    assert model.get("models") is not None


def test_unknown_area_is_rejected() -> None:
    model = WorkspaceModel()

    with pytest.raises(ValueError):
        model.add("chat", "Chat", area="middle")
